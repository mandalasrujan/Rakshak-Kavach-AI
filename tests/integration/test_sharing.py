"""M14: doctor scoped sharing -- security tests (failure paths first, not just the happy path)."""

import ast
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

from app.services.document_processing import DocumentProcessor
from tests.conftest import FRONTEND_ORIGIN, reset_state
from tests.helpers import CSRF, grant_consent, log_content, register_and_login, upload

pytestmark = pytest.mark.integration
SHARES, SESSIONS, VIEW = "/api/v1/patient/shares", "/api/v1/share/sessions", "/api/v1/share/view"
FILES = [
    "03_asha_hba1c_2025-11-18.pdf",
    "04_asha_glycated_haemoglobin_2026-05-13.pdf",
    "07_asha_prescription_2026-05-14.pdf",
]
ROOT = Path(__file__).resolve().parents[2]


def _doctor(app) -> AsyncClient:  # type: ignore[no-untyped-def]
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver")


async def _patient(client: AsyncClient, app, synthetic_dir: Path, email: str) -> dict:  # type: ignore[no-untyped-def, type-arg]
    patient_id = uuid.UUID((await register_and_login(client, email)).json()["id"])
    await grant_consent(client)
    processor = DocumentProcessor(
        app.state.sessionmaker, app.state.storage, llm=app.state.llm, max_pages=50
    )
    docs = {}
    for name in FILES:
        document_id = (await upload(client, (synthetic_dir / name).read_bytes())).json()["id"]
        assert await processor.process(uuid.UUID(document_id), patient_id) == "ready"
        docs[name] = document_id
    snapshot = (await client.post("/api/v1/patient/snapshots", headers=CSRF)).json()
    await client.post(f"/api/v1/patient/snapshots/{snapshot['id']}/approve", headers=CSRF)
    return {"patient_id": patient_id, "snapshot": snapshot, "docs": docs}


async def _share(
    client: AsyncClient, snapshot_id: str, scope: str = "summary_only", minutes: int = 60
) -> dict:  # type: ignore[type-arg]
    response = await client.post(
        SHARES,
        json={"snapshot_id": snapshot_id, "scope": scope, "expires_in_minutes": minutes},
        headers=CSRF,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _exchange(doctor: AsyncClient, token: str, pin: str, **extra: str):  # type: ignore[no-untyped-def]
    return await doctor.post(SESSIONS, json={"token": token, "pin": pin, **extra}, headers=CSRF)


def _wrong(pin: str) -> str:
    return f"{(int(pin) + 1) % 10**6:06d}"


async def _sql(app, statement: str, **params):  # type: ignore[no-untyped-def]
    async with app.state.admin_engine.begin() as conn:
        return await conn.execute(text(statement), params)


# --- creation ---------------------------------------------------------------------------


async def test_share_requires_an_approved_snapshot_consent_and_csrf(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    ctx = await _patient(client, app, synthetic_dir, "share.rules@example.com")
    draft = (await client.post("/api/v1/patient/snapshots", headers=CSRF)).json()
    body = {"snapshot_id": draft["id"], "scope": "summary_only", "expires_in_minutes": 60}
    assert (await client.post(SHARES, json=body, headers=CSRF)).status_code == 409  # not approved
    approved = {**body, "snapshot_id": ctx["snapshot"]["id"]}
    assert (
        await client.post(SHARES, json={**approved, "scope": "everything"}, headers=CSRF)
    ).status_code == 422
    assert (
        await client.post(SHARES, json={**approved, "expires_in_minutes": 5000}, headers=CSRF)
    ).status_code == 400
    assert (await client.post(SHARES, json=approved)).status_code == 403  # no CSRF header
    await client.delete("/api/v1/patient/consent", headers=CSRF)
    assert (await client.post(SHARES, json=approved, headers=CSRF)).status_code == 403


async def test_token_and_pin_are_shown_once_and_stored_only_as_hashes(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    ctx = await _patient(client, app, synthetic_dir, "share.hash@example.com")
    share = await _share(client, ctx["snapshot"]["id"])
    assert len(share["pin"]) == 6 and share["pin"].isdigit() and len(share["token"]) >= 43
    assert (
        share["share_url"] == f"{FRONTEND_ORIGIN}/share#t={share['token']}"
    )  # fragment, not query
    row = (
        await _sql(
            app, "SELECT token_hash, pin_hash FROM share_grants WHERE id = :i", i=share["share_id"]
        )
    ).one()
    assert row.token_hash == hashlib.sha256(share["token"].encode()).hexdigest()
    assert row.pin_hash.startswith("$argon2id$") and share["pin"] not in row.pin_hash
    listed = (await client.get(SHARES)).text
    assert share["token"] not in listed and share["pin"] not in listed


# --- PIN exchange and session ------------------------------------------------------------


async def test_correct_pin_opens_a_30_minute_read_only_session(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    ctx = await _patient(client, app, synthetic_dir, "share.ok@example.com")
    share = await _share(client, ctx["snapshot"]["id"])
    async with _doctor(app) as doctor:
        started = await _exchange(
            doctor, share["token"], share["pin"], declared_name="Dr. Test (Synthetic)"
        )
        assert started.status_code == 200
        cookie = started.headers["set-cookie"].lower()
        for attribute in (
            "rk_share=",
            "httponly",
            "secure",
            "samesite=strict",
            "path=/api/v1/share",
        ):
            assert attribute in cookie
        expires = datetime.fromisoformat(started.json()["expires_at"])
        assert timedelta(minutes=29) < expires - datetime.now(UTC) <= timedelta(minutes=30)
        view = await doctor.get(VIEW)
        assert view.status_code == 200 and view.headers["referrer-policy"] == "no-referrer"
        assert view.json()["snapshot_version"] == 1
        for method in ("post", "put", "patch", "delete"):  # read-only
            assert (await getattr(doctor, method)(VIEW, headers=CSRF)).status_code == 405
    sessions = (await client.get(SHARES)).json()["items"][0]["sessions"]
    assert sessions[0]["declared_name"] == "Dr. Test (Synthetic)" and sessions[0]["views"] == 1


async def test_session_never_outlives_the_share(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    ctx = await _patient(client, app, synthetic_dir, "share.short@example.com")
    share = await _share(client, ctx["snapshot"]["id"], minutes=10)
    async with _doctor(app) as doctor:
        started = (await _exchange(doctor, share["token"], share["pin"])).json()
    assert datetime.fromisoformat(started["expires_at"]) == datetime.fromisoformat(
        share["expires_at"]
    )


async def test_five_wrong_pins_lock_the_share_permanently(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    ctx = await _patient(client, app, synthetic_dir, "share.lock@example.com")
    share = await _share(client, ctx["snapshot"]["id"])
    async with _doctor(app) as earlier, _doctor(app) as attacker:
        assert (await _exchange(earlier, share["token"], share["pin"])).status_code == 200
        for _ in range(5):
            wrong = await _exchange(attacker, share["token"], _wrong(share["pin"]))
            assert (wrong.status_code, wrong.json()["error"]["code"]) == (401, "invalid_pin")
        right = await _exchange(attacker, share["token"], share["pin"])
        assert (right.status_code, right.json()["error"]["code"]) == (401, "share_unavailable")
        assert (await earlier.get(VIEW)).status_code == 401  # existing sessions die with the lock
    row = (
        await _sql(
            app,
            "SELECT failed_pin_attempts, locked_at FROM share_grants WHERE id = :i",
            i=share["share_id"],
        )
    ).one()
    assert row.failed_pin_attempts == 5 and row.locked_at is not None
    actions = list(
        (
            await _sql(
                app, "SELECT action FROM audit_log WHERE action LIKE 'share.%' ORDER BY created_at"
            )
        ).scalars()
    )
    assert actions.count("share.pin_failed") == 5 and "share.locked" in actions
    assert (await client.get(SHARES)).json()["items"][0]["status"] == "locked"


@pytest.mark.parametrize(
    "change", ["expire_share", "revoke_share", "expire_session", "end_session"]
)
async def test_expired_revoked_or_ended_access_is_rejected(
    client: AsyncClient, app, synthetic_dir: Path, change: str
) -> None:  # type: ignore[no-untyped-def]
    ctx = await _patient(client, app, synthetic_dir, f"share.{change}@example.com")
    share = await _share(client, ctx["snapshot"]["id"])
    async with _doctor(app) as doctor:
        assert (await _exchange(doctor, share["token"], share["pin"])).status_code == 200
        replayable = doctor.cookies.get("rk_share", path="/api/v1/share")
        assert replayable
        assert (await doctor.get(VIEW)).status_code == 200
        if change == "expire_share":
            await _sql(
                app,
                "UPDATE share_grants SET expires_at = now() - interval '1 second' WHERE id = :i",
                i=share["share_id"],
            )
        elif change == "revoke_share":
            assert (
                await client.delete(f"{SHARES}/{share['share_id']}", headers=CSRF)
            ).status_code == 204
        elif change == "expire_session":
            await _sql(app, "UPDATE doctor_sessions SET expires_at = now() - interval '1 second'")
        else:
            assert (await doctor.post("/api/v1/share/session/end", headers=CSRF)).status_code == 204
            doctor.cookies.set(
                "rk_share", replayable, path="/api/v1/share"
            )  # replay the old cookie
        denied = await doctor.get(VIEW)
        assert (denied.status_code, denied.json()["error"]["code"]) == (401, "share_unavailable")
        again = await _exchange(doctor, share["token"], share["pin"])
        assert again.status_code == (200 if change in {"expire_session", "end_session"} else 401)


async def test_unknown_tampered_and_malformed_credentials(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    ctx = await _patient(client, app, synthetic_dir, "share.tamper@example.com")
    share = await _share(client, ctx["snapshot"]["id"])
    async with _doctor(app) as doctor:
        unknown = await _exchange(doctor, "x" * 43, share["pin"])
        tampered = await _exchange(
            doctor, share["token"][:-1] + ("A" if share["token"][-1] != "A" else "B"), share["pin"]
        )
        for response in (unknown, tampered):
            assert (response.status_code, response.json()["error"]["code"]) == (
                401,
                "share_unavailable",
            )
        malformed = await _exchange(doctor, share["token"], "12345")
        assert malformed.status_code == 422 and "12345" not in malformed.text
        assert (await doctor.get(VIEW)).status_code == 401  # no cookie at all
        doctor.cookies.set(
            "rk_share", "forged-session-token-value-000000000000000", path="/api/v1/share"
        )
        assert (await doctor.get(VIEW)).status_code == 401
        evil = await doctor.post(
            SESSIONS,
            json={"token": share["token"], "pin": share["pin"]},
            headers={**CSRF, "Origin": "https://evil.example"},
        )
        assert evil.status_code == 403


async def test_token_reuse_needs_the_pin_each_time_and_dies_on_revoke(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    ctx = await _patient(client, app, synthetic_dir, "share.reuse@example.com")
    share = await _share(client, ctx["snapshot"]["id"])
    async with _doctor(app) as first, _doctor(app) as second:
        assert (await _exchange(first, share["token"], share["pin"])).status_code == 200
        assert (
            await _exchange(second, share["token"], share["pin"])
        ).status_code == 200  # re-scan, re-PIN
        await client.delete(f"{SHARES}/{share['share_id']}", headers=CSRF)
        assert (await first.get(VIEW)).status_code == 401 and (
            await second.get(VIEW)
        ).status_code == 401
    starts = (
        await _sql(app, "SELECT count(*) FROM audit_log WHERE action = 'share.session_started'")
    ).scalar_one()
    assert starts == 2


# --- scope and isolation ------------------------------------------------------------------


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


async def test_scope_limits_the_data_returned(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    ctx = await _patient(client, app, synthetic_dir, "share.scope@example.com")
    views = {}
    for scope in ("summary_only", "full_records"):
        share = await _share(client, ctx["snapshot"]["id"], scope=scope)
        async with _doctor(app) as doctor:
            await _exchange(doctor, share["token"], share["pin"])
            views[scope] = (await doctor.get(VIEW)).json()
    summary, full = views["summary_only"]["summary"], views["full_records"]["summary"]
    assert "documents" not in summary and "source" not in _keys(summary)
    assert summary["narrative"]["citations"] == []
    assert summary["medications"] and summary["labs"]  # spec: both scopes get meds and labs
    assert len(full["documents"]) == 3 and "source" in _keys(full)
    assert {m["source"]["document_id"] for m in full["medications"]} == {ctx["docs"][FILES[2]]}


async def test_doctor_sees_only_the_approved_snapshot_version(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    ctx = await _patient(client, app, synthetic_dir, "share.frozen@example.com")
    share = await _share(client, ctx["snapshot"]["id"])
    await client.post("/api/v1/patient/snapshots", headers=CSRF)  # a newer draft exists
    async with _doctor(app) as doctor:
        await _exchange(doctor, share["token"], share["pin"])
        view = (await doctor.get(VIEW)).json()
    assert view["snapshot_version"] == 1
    approved = ctx["snapshot"]["content_json"]["labs"]
    assert [(lab["test_code"], lab["latest"]["raw_value"]) for lab in view["summary"]["labs"]] == [
        (lab["test_code"], lab["latest"]["raw_value"]) for lab in approved
    ]


async def test_doctor_session_cannot_reach_patient_apis(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    ctx = await _patient(client, app, synthetic_dir, "share.apis@example.com")
    share = await _share(client, ctx["snapshot"]["id"])
    async with _doctor(app) as doctor:
        await _exchange(doctor, share["token"], share["pin"])
        session_token = doctor.cookies.get("rk_share", path="/api/v1/share")
        doctor.cookies.set(
            "rk_share", session_token, path="/"
        )  # even if the browser sent it everywhere
        doctor.cookies.set("rk_access", session_token)  # or presented it as a patient cookie
        for path in (
            "/api/v1/patient/me",
            "/api/v1/patient/documents",
            "/api/v1/patient/labs",
            "/api/v1/patient/chats",
            "/api/v1/patient/snapshots",
            SHARES,
        ):
            assert (await doctor.get(path)).status_code == 401, path
        assert (
            await doctor.delete(f"/api/v1/patient/documents/{ctx['docs'][FILES[0]]}", headers=CSRF)
        ).status_code == 401


async def test_shares_are_isolated_between_patients(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    a = await _patient(client, app, synthetic_dir, "share.a@example.com")
    share_a = await _share(client, a["snapshot"]["id"])
    b = await _patient(client, app, synthetic_dir, "share.b@example.com")
    assert (await client.get(SHARES)).json()["items"] == []
    assert (await client.delete(f"{SHARES}/{share_a['share_id']}", headers=CSRF)).status_code == 404
    body = {"snapshot_id": a["snapshot"]["id"], "scope": "full_records", "expires_in_minutes": 60}
    assert (
        await client.post(SHARES, json=body, headers=CSRF)
    ).status_code == 404  # B cannot share A's
    async with _doctor(app) as doctor:
        await _exchange(doctor, share_a["token"], share_a["pin"])
        view = (await doctor.get(VIEW)).json()
    assert view["snapshot_version"] == 1
    assert b["docs"][FILES[0]] not in str(view)
    async with app.state.sessionmaker() as session:  # RLS without context: nothing visible
        for table in ("share_grants", "doctor_sessions", "summary_snapshots"):
            assert (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0  # noqa: S608


async def test_consent_revocation_and_document_deletion_revoke_shares(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    ctx = await _patient(client, app, synthetic_dir, "share.cascade@example.com")
    first, second = (
        await _share(client, ctx["snapshot"]["id"]),
        await _share(client, ctx["snapshot"]["id"]),
    )
    async with _doctor(app) as doctor:
        await _exchange(doctor, first["token"], first["pin"])
        await client.delete(f"/api/v1/patient/documents/{ctx['docs'][FILES[0]]}", headers=CSRF)
        assert (await doctor.get(VIEW)).status_code == 401  # snapshot invalidated, shares revoked
    statuses = {s["id"]: s["status"] for s in (await client.get(SHARES)).json()["items"]}
    assert statuses == {first["share_id"]: "revoked", second["share_id"]: "revoked"}

    ctx2 = await _patient(client, app, synthetic_dir, "share.consent@example.com")
    share = await _share(client, ctx2["snapshot"]["id"])
    async with _doctor(app) as doctor:
        await _exchange(doctor, share["token"], share["pin"])
        await client.delete("/api/v1/patient/consent", headers=CSRF)
        assert (await doctor.get(VIEW)).status_code == 401


async def test_pin_exchange_is_rate_limited_per_ip(
    settings_factory, admin_engine, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    from app.main import create_app

    app = create_app(settings_factory(share_exchange_max_per_ip=3))
    app.state.admin_engine = admin_engine
    async with app.router.lifespan_context(app):
        await reset_state(app)
        async with _doctor(app) as doctor:
            statuses = [(await _exchange(doctor, "y" * 43, "000000")).status_code for _ in range(4)]
    assert statuses == [401, 401, 401, 429]


# --- logs, audit and code isolation --------------------------------------------------------


async def test_tokens_pins_and_phi_never_reach_logs_or_audit(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    ctx = await _patient(client, app, synthetic_dir, "share.logs@example.com")
    with capture_logs(processors=[merge_contextvars]) as logs:
        share = await _share(client, ctx["snapshot"]["id"], scope="full_records")
        async with _doctor(app) as doctor:
            await _exchange(doctor, share["token"], _wrong(share["pin"]))
            await _exchange(doctor, share["token"], share["pin"], declared_name="Dr. Private Name")
            session_token = doctor.cookies.get("rk_share", path="/api/v1/share")
            await doctor.get(VIEW)
    dumped = log_content(logs)
    for secret in (share["token"], share["pin"], session_token, "Metformin", "Dr. Private Name"):
        assert secret not in dumped
    audit = " ".join(str(m) for m in (await _sql(app, "SELECT metadata FROM audit_log")).scalars())
    for secret in (share["token"], share["pin"], session_token, "Metformin", "Private"):
        assert secret not in audit


def test_doctor_code_never_imports_patient_services() -> None:
    forbidden = (
        "app.services.consent_service",
        "app.services.document_service",
        "app.services.lab_service",
        "app.services.snapshot_service",
        "app.agent",
        "app.services.document_deletion",
    )
    for module in ("backend/app/api/v1/share.py", "backend/app/services/share_access.py"):
        tree = ast.parse((ROOT / module).read_text())
        imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        assert not {m for m in imported if m.startswith(forbidden)}, module
        assert "get_current_patient" not in names and "get_patient_session" not in names
