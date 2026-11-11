"""M3: versioned consent, grant/revoke, require_consent, append-only audit log."""

import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.api.deps import require_consent
from app.core import consent_notice
from app.main import create_app
from tests.helpers import CSRF, grant_consent, register_and_login

pytestmark = pytest.mark.integration
CONSENT = "/api/v1/patient/consent"


async def _audit_rows(app) -> list:  # type: ignore[no-untyped-def]
    async with app.state.admin_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT patient_id, actor_type, action, target_id, metadata "
                "FROM audit_log ORDER BY created_at"
            )
        )
        return list(result)


async def test_status_before_consent_shows_current_notice(client: AsyncClient) -> None:
    await register_and_login(client, "notice@example.com")
    body = (await client.get(CONSENT)).json()
    assert body["granted"] is False
    assert body["notice_version"] == consent_notice.CONSENT_NOTICE_VERSION
    assert "Gemini" in body["notice_text"]
    assert body["granted_at"] is None


async def test_grant_and_revoke_are_audited(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    me = (await register_and_login(client, "audit@example.com")).json()
    granted = (await grant_consent(client)).json()
    assert granted["granted"] is True
    assert granted["granted_notice_version"] == consent_notice.CONSENT_NOTICE_VERSION

    revoked = await client.delete(CONSENT, headers=CSRF)
    assert revoked.status_code == 200
    assert revoked.json()["granted"] is False
    assert revoked.json()["revoked_at"] is not None

    rows = await _audit_rows(app)
    assert [r.action for r in rows] == ["consent.granted", "consent.revoked"]
    for row in rows:
        assert str(row.patient_id) == me["id"]
        assert row.actor_type == "patient"
        assert row.metadata == {"notice_version": consent_notice.CONSENT_NOTICE_VERSION}
        assert "audit@example.com" not in str(row.metadata)


async def test_grant_and_revoke_are_idempotent(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    await register_and_login(client, "idem@example.com")
    await grant_consent(client)
    await grant_consent(client)
    assert (await client.delete(CONSENT, headers=CSRF)).status_code == 200
    assert (await client.delete(CONSENT, headers=CSRF)).status_code == 200
    async with app.state.admin_engine.connect() as conn:
        records = (await conn.execute(text("SELECT count(*) FROM consent_records"))).scalar_one()
    assert records == 1
    assert [r.action for r in await _audit_rows(app)] == ["consent.granted", "consent.revoked"]


async def test_outdated_notice_version_is_rejected(client: AsyncClient) -> None:
    await register_and_login(client, "stale@example.com")
    response = await client.post(CONSENT, json={"notice_version": "1999-01-01"}, headers=CSRF)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "consent_notice_outdated"
    assert (await client.get(CONSENT)).json()["granted"] is False


async def test_new_notice_version_requires_fresh_consent(
    client: AsyncClient,
    app,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[no-untyped-def]
) -> None:
    await register_and_login(client, "bump@example.com")
    await grant_consent(client)
    monkeypatch.setattr(consent_notice, "CONSENT_NOTICE_VERSION", "2099-01-01")
    assert (await client.get(CONSENT)).json()["granted"] is False
    regranted = (await grant_consent(client)).json()
    assert regranted["granted"] is True
    assert regranted["granted_notice_version"] == "2099-01-01"
    async with app.state.admin_engine.connect() as conn:
        active = (
            await conn.execute(
                text("SELECT count(*) FROM consent_records WHERE revoked_at IS NULL")
            )
        ).scalar_one()
    assert active == 1


async def test_consent_is_scoped_to_the_patient(client: AsyncClient) -> None:
    await register_and_login(client, "first@example.com")
    await grant_consent(client)
    await register_and_login(client, "second@example.com")
    assert (await client.get(CONSENT)).json()["granted"] is False


async def test_consent_routes_require_auth_and_csrf(client: AsyncClient) -> None:
    assert (await client.get(CONSENT)).status_code == 401
    await register_and_login(client, "csrf.consent@example.com")
    notice = (await client.get(CONSENT)).json()
    no_header = await client.post(CONSENT, json={"notice_version": notice["notice_version"]})
    assert no_header.status_code == 403
    assert (await client.delete(CONSENT)).status_code == 403
    cross_site = await client.get(CONSENT, headers={"Origin": "https://evil.example"})
    assert cross_site.status_code == 403


async def test_require_consent_blocks_until_granted_and_after_revoke(
    settings, admin_engine
) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    app.state.admin_engine = admin_engine
    probe = APIRouter()

    @probe.post("/api/v1/patient/_needs_consent")
    async def _needs_consent(_patient=Depends(require_consent)) -> dict[str, bool]:  # type: ignore[no-untyped-def]
        return {"ok": True}

    app.include_router(probe)
    async with app.router.lifespan_context(app):
        async with app.state.admin_engine.begin() as conn:
            await conn.execute(text("TRUNCATE TABLE patients, audit_log CASCADE"))
        await app.state.redis.flushdb()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://testserver") as http:
            url = "/api/v1/patient/_needs_consent"
            assert (await http.post(url, headers=CSRF)).status_code == 401
            await register_and_login(http, "gate@example.com")
            blocked = await http.post(url, headers=CSRF)
            assert blocked.status_code == 403
            assert blocked.json()["error"]["code"] == "consent_required"
            await grant_consent(http)
            assert (await http.post(url, headers=CSRF)).status_code == 200
            await http.delete(CONSENT, headers=CSRF)
            assert (await http.post(url, headers=CSRF)).status_code == 403


async def test_audit_log_rejects_update_and_delete(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    await register_and_login(client, "immutable@example.com")
    await grant_consent(client)
    for statement in ("UPDATE audit_log SET action = 'tampered'", "DELETE FROM audit_log"):
        with pytest.raises(DBAPIError, match="append-only"):
            async with app.state.admin_engine.begin() as conn:
                await conn.execute(text(statement))
    assert [r.action for r in await _audit_rows(app)] == ["consent.granted"]
