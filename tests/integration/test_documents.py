"""M4: upload (202), validation, per-patient dedup, scoping, queue → worker → ready."""

import uuid
from pathlib import Path

import pytest
from arq.worker import Worker
from httpx import AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import text

from app.services.document_processing import DocumentProcessor
from tests.helpers import CSRF, grant_consent, register_and_login, upload
from worker.main import process_document

pytestmark = pytest.mark.integration
DOCS = "/api/v1/patient/documents"
CBC = "01_asha_cbc_lft_2025-11-18.pdf"


async def _patient_with_consent(client: AsyncClient, email: str) -> str:
    patient_id = (await register_and_login(client, email)).json()["id"]
    await grant_consent(client)
    return patient_id


async def test_upload_requires_active_consent(client: AsyncClient, synthetic_dir: Path) -> None:
    data = (synthetic_dir / CBC).read_bytes()
    await register_and_login(client, "noconsent@example.com")
    blocked = await upload(client, data)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "consent_required"
    await grant_consent(client)
    assert (await upload(client, data)).status_code == 202
    await client.delete("/api/v1/patient/consent", headers=CSRF)
    other = (synthetic_dir / "02_asha_lipid_mgdl_2025-11-18.pdf").read_bytes()
    assert (await upload(client, other)).status_code == 403


async def test_upload_stores_file_queues_job_and_audits(
    client: AsyncClient,
    app,
    synthetic_dir: Path,
    settings,  # type: ignore[no-untyped-def]
) -> None:
    patient_id = await _patient_with_consent(client, "upload@example.com")
    data = (synthetic_dir / CBC).read_bytes()
    response = await upload(client, data, filename="Asha Verma HbA1c.pdf")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert set(body) == {"id", "status", "failure_reason", "pages", "uploaded_at"}

    async with app.state.engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT patient_id, storage_key, file_hash FROM documents WHERE id = :i"),
                {"i": body["id"]},
            )
        ).one()
        audit = (
            await conn.execute(
                text("SELECT action, actor_type, target_id FROM audit_log WHERE action LIKE 'doc%'")
            )
        ).one()
    assert str(row.patient_id) == patient_id
    assert row.storage_key.startswith(f"patients/{patient_id}/")
    assert "Asha" not in row.storage_key  # random key, never the client file name
    stored = Path(settings.storage_local_path) / row.storage_key
    assert stored.read_bytes() == data
    assert (audit.action, audit.actor_type, str(audit.target_id)) == (
        "document.uploaded",
        "patient",
        body["id"],
    )

    jobs = await app.state.arq.queued_jobs()
    assert [(j.function, j.args) for j in jobs] == [("process_document", (body["id"], patient_id))]


@pytest.mark.parametrize("payload", [b"hello world", b"", b"GIF89a%PDF-1.4"])
async def test_non_pdf_content_is_rejected_by_magic_bytes(
    client: AsyncClient,
    settings,
    payload: bytes,  # type: ignore[no-untyped-def]
) -> None:
    await _patient_with_consent(client, f"magic-{uuid.uuid4().hex[:6]}@example.com")
    response = await upload(client, payload, filename="looks-like.pdf")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file_type"
    assert not list(Path(settings.storage_local_path).rglob("*.pdf"))


async def test_oversized_upload_is_rejected(settings_factory) -> None:  # type: ignore[no-untyped-def]
    from httpx import ASGITransport

    from app.main import create_app

    app = create_app(settings_factory(max_upload_mb=1))
    async with app.router.lifespan_context(app):
        async with app.state.engine.begin() as conn:
            await conn.execute(text("TRUNCATE TABLE patients, audit_log CASCADE"))
        await app.state.redis.flushdb()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://testserver") as http:
            await _patient_with_consent(http, "big@example.com")
            response = await upload(http, b"%PDF-1.7\n" + b"0" * (1024 * 1024))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


async def test_dedup_is_per_patient(client: AsyncClient, synthetic_dir: Path) -> None:
    data = (synthetic_dir / CBC).read_bytes()
    await _patient_with_consent(client, "dup-a@example.com")
    first = await upload(client, data)
    again = await upload(client, data)
    assert (first.status_code, again.status_code) == (202, 200)
    assert again.json()["id"] == first.json()["id"]
    assert (await client.get(DOCS)).json()["total"] == 1

    await _patient_with_consent(client, "dup-b@example.com")
    other_patient = await upload(client, data)
    assert other_patient.status_code == 202  # same file from a second patient is accepted
    assert other_patient.json()["id"] != first.json()["id"]


async def test_documents_are_scoped_to_their_owner(
    client: AsyncClient, synthetic_dir: Path
) -> None:
    await _patient_with_consent(client, "owner@example.com")
    owned = (await upload(client, (synthetic_dir / CBC).read_bytes())).json()
    assert (await client.get(f"{DOCS}/{owned['id']}")).status_code == 200

    await _patient_with_consent(client, "intruder@example.com")
    stolen = await client.get(f"{DOCS}/{owned['id']}")
    assert stolen.status_code == 404
    assert stolen.json()["error"]["code"] == "not_found"
    assert (await client.get(DOCS)).json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


async def test_list_is_paginated_newest_first(client: AsyncClient, synthetic_dir: Path) -> None:
    await _patient_with_consent(client, "pages@example.com")
    ids = []
    for name in (CBC, "02_asha_lipid_mgdl_2025-11-18.pdf", "03_asha_hba1c_2025-11-18.pdf"):
        ids.append((await upload(client, (synthetic_dir / name).read_bytes())).json()["id"])
    page = (await client.get(DOCS, params={"limit": 2, "offset": 0})).json()
    assert page["total"] == 3
    assert [d["id"] for d in page["items"]] == [ids[2], ids[1]]
    assert (await client.get(DOCS, params={"limit": 0})).status_code == 422


async def test_document_routes_require_auth_and_csrf(client: AsyncClient) -> None:
    assert (await client.get(DOCS)).status_code == 401
    await _patient_with_consent(client, "csrf.docs@example.com")
    no_csrf = await client.post(DOCS, files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})
    assert no_csrf.status_code == 403
    assert no_csrf.json()["error"]["code"] == "csrf_rejected"


async def test_enqueue_failure_marks_failed_and_reupload_requeues(
    client: AsyncClient,
    app,
    synthetic_dir: Path,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[no-untyped-def]
) -> None:
    await _patient_with_consent(client, "queue-down@example.com")
    data = (synthetic_dir / CBC).read_bytes()

    async def _down(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RedisConnectionError("down")

    monkeypatch.setattr(app.state.arq, "enqueue_job", _down)
    failed = await upload(client, data)
    assert failed.status_code == 503
    doc = (await client.get(DOCS)).json()["items"][0]
    assert (doc["status"], doc["failure_reason"]) == ("failed", "enqueue_failed")

    monkeypatch.undo()
    retried = await upload(client, data)
    assert retried.status_code == 202
    assert retried.json()["id"] == doc["id"]
    assert retried.json()["status"] == "queued"


async def test_upload_goes_queued_to_ready_through_the_worker(
    client: AsyncClient,
    app,
    synthetic_dir: Path,  # type: ignore[no-untyped-def]
) -> None:
    await _patient_with_consent(client, "e2e@example.com")
    document = (await upload(client, (synthetic_dir / CBC).read_bytes())).json()
    assert document["status"] == "queued"

    processor = DocumentProcessor(app.state.sessionmaker, app.state.storage, max_pages=50)
    worker = Worker(
        functions=[process_document],
        redis_settings=None,
        redis_pool=app.state.arq,
        ctx={"document_processor": processor},
        burst=True,
        poll_delay=0.05,
        handle_signals=False,
    )
    await worker.main()

    ready = (await client.get(f"{DOCS}/{document['id']}")).json()
    assert (ready["status"], ready["pages"], ready["failure_reason"]) == ("ready", 2, None)
    async with app.state.engine.connect() as conn:
        actions = (
            await conn.execute(
                text(
                    "SELECT action, actor_type FROM audit_log WHERE target_id = :i "
                    "ORDER BY created_at"
                ),
                {"i": document["id"]},
            )
        ).all()
    assert [tuple(a) for a in actions] == [
        ("document.uploaded", "patient"),
        ("document.ready", "system"),
    ]
