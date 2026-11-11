"""M12: patient-requested document deletion, residual-data checks, retries, races."""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db.patient_context import set_patient_context
from app.llm.fake import FakeLLMProvider
from app.services.document_deletion import DocumentDeletionService
from app.services.document_processing import DocumentProcessor
from tests.helpers import CSRF, grant_consent, login, register_and_login, upload

pytestmark = pytest.mark.integration
DOCS = "/api/v1/patient/documents"
OLD, NEW = "03_asha_hba1c_2025-11-18.pdf", "04_asha_glycated_haemoglobin_2026-05-13.pdf"
RX = "07_asha_prescription_2026-05-14.pdf"


def _processor(app, llm=None) -> DocumentProcessor:  # type: ignore[no-untyped-def]
    return DocumentProcessor(
        app.state.sessionmaker, app.state.storage, llm=llm or app.state.llm, max_pages=50
    )


async def _patient(
    client: AsyncClient, app, synthetic_dir: Path, email: str, files
) -> tuple[uuid.UUID, dict[str, str]]:  # type: ignore[no-untyped-def]
    patient_id = uuid.UUID((await register_and_login(client, email)).json()["id"])
    await grant_consent(client)
    ids = {}
    for name in files:
        document_id = (await upload(client, (synthetic_dir / name).read_bytes())).json()["id"]
        assert await _processor(app).process(uuid.UUID(document_id), patient_id) == "ready"
        ids[name] = document_id
    return patient_id, ids


async def _rows(app, document_id: str) -> dict[str, int]:  # type: ignore[no-untyped-def]
    counts = {}
    async with app.state.admin_engine.connect() as conn:
        for table in ("documents", "chunks", "lab_results", "medications", "message_citations"):
            column = "id" if table == "documents" else "document_id"
            counts[table] = (
                await conn.execute(
                    text(f"SELECT count(*) FROM {table} WHERE {column} = :d"),  # noqa: S608
                    {"d": document_id},
                )
            ).scalar_one()
    return counts


async def test_deletion_removes_the_document_and_everything_derived_from_it(
    client: AsyncClient, app, synthetic_dir: Path, settings
) -> None:  # type: ignore[no-untyped-def]
    _, docs = await _patient(client, app, synthetic_dir, "delete@example.com", [OLD, NEW, RX])
    target = docs[NEW]
    citing = (await client.post("/api/v1/patient/chats", headers=CSRF)).json()["id"]
    reply = (
        await client.post(
            f"/api/v1/patient/chats/{citing}/messages",
            json={"question": "Is my HbA1c getting worse?"},
            headers=CSRF,
        )
    ).json()
    assert target in {c["document_id"] for c in reply["citations"]}
    unrelated = (await client.post("/api/v1/patient/chats", headers=CSRF)).json()["id"]
    await client.post(
        f"/api/v1/patient/chats/{unrelated}/messages",
        json={"question": "Which medication was prescribed?"},
        headers=CSRF,
    )
    async with app.state.admin_engine.connect() as conn:
        storage_key = (
            await conn.execute(
                text("SELECT storage_key FROM documents WHERE id = :d"), {"d": target}
            )
        ).scalar_one()
    stored = Path(settings.storage_local_path) / storage_key
    assert stored.exists() and (await _rows(app, target))["chunks"] > 0

    assert (await client.delete(f"{DOCS}/{target}", headers=CSRF)).status_code == 204

    # Residual-data checks: database, file, conversation state, audit.
    assert await _rows(app, target) == dict.fromkeys(
        ("documents", "chunks", "lab_results", "medications", "message_citations"), 0
    )
    assert not stored.exists()
    async with app.state.admin_engine.connect() as conn:
        chats = set((await conn.execute(text("SELECT id::text FROM chats"))).scalars())
        checkpoint_chats = set(
            (
                await conn.execute(text("SELECT DISTINCT chat_id::text FROM chat_checkpoints"))
            ).scalars()
        )
        audit = (
            await conn.execute(
                text(
                    "SELECT metadata FROM audit_log "
                    "WHERE action = 'document.deleted' AND target_id = :d"
                ),
                {"d": target},
            )
        ).scalar_one()
    assert citing not in chats and citing not in checkpoint_chats  # the citing chat is gone
    assert unrelated in chats and unrelated in checkpoint_chats  # other chats are kept
    assert set(audit) == {"chunks", "lab_results", "medications", "chats", "snapshots_invalidated"}
    assert audit["chats"] == 1
    assert all(isinstance(v, int) for v in audit.values())

    # Nothing is reachable through the API, SQL-backed labs, or RAG.
    assert (await client.get(f"{DOCS}/{target}")).status_code == 404
    assert target not in {d["id"] for d in (await client.get(DOCS)).json()["items"]}
    labs = (await client.get("/api/v1/patient/labs", params={"test_code": "HBA1C"})).json()
    assert [r["document_id"] for r in labs["items"]] == [docs[OLD]]
    trend = (await client.get("/api/v1/patient/labs/trends", params={"test_code": "HBA1C"})).json()[
        "items"
    ][0]
    assert trend["status"] == "insufficient_data"
    answer = (
        await client.post(
            "/api/v1/patient/ask",
            json={"question": "What was my glycated haemoglobin?"},
            headers=CSRF,
        )
    ).json()
    assert (
        target not in {c["document_id"] for c in answer["citations"]}
        and "7.6" not in answer["answer"]
    )
    assert (await client.get(f"/api/v1/patient/chats/{citing}/messages")).status_code == 404


async def test_deletion_is_patient_scoped_and_needs_no_consent(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    _, docs = await _patient(client, app, synthetic_dir, "del-owner@example.com", [OLD])
    await register_and_login(client, "del-intruder@example.com")
    assert (await client.delete(f"{DOCS}/{docs[OLD]}", headers=CSRF)).status_code == 404
    assert (await _rows(app, docs[OLD]))["documents"] == 1
    assert (await login(client, "del-owner@example.com")).status_code == 200
    await client.delete("/api/v1/patient/consent", headers=CSRF)  # deletion still allowed
    assert (await client.delete(f"{DOCS}/{docs[OLD]}", headers=CSRF)).status_code == 204


async def test_deletion_requires_auth_and_csrf(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    assert (await client.delete(f"{DOCS}/{uuid.uuid4()}", headers=CSRF)).status_code == 401
    _, docs = await _patient(client, app, synthetic_dir, "del-csrf@example.com", [OLD])
    assert (await client.delete(f"{DOCS}/{docs[OLD]}")).status_code == 403


async def test_storage_failure_changes_nothing_and_retry_succeeds(
    client: AsyncClient, app, synthetic_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    _, docs = await _patient(client, app, synthetic_dir, "del-retry@example.com", [NEW])
    before = await _rows(app, docs[NEW])

    async def broken(key: str) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(app.state.storage, "delete", broken)
    failed = await client.delete(f"{DOCS}/{docs[NEW]}", headers=CSRF)
    assert (failed.status_code, failed.json()["error"]["code"]) == (503, "service_unavailable")
    assert await _rows(app, docs[NEW]) == before  # nothing deleted, safe to retry

    monkeypatch.undo()
    assert (await client.delete(f"{DOCS}/{docs[NEW]}", headers=CSRF)).status_code == 204
    assert (await _rows(app, docs[NEW]))["chunks"] == 0
    assert (await client.delete(f"{DOCS}/{docs[NEW]}", headers=CSRF)).status_code == 404


async def test_pending_job_after_deletion_recreates_nothing(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    patient_id = uuid.UUID(
        (await register_and_login(client, "del-queued@example.com")).json()["id"]
    )
    await grant_consent(client)
    document_id = (await upload(client, (synthetic_dir / NEW).read_bytes())).json()["id"]
    assert len(await app.state.arq.queued_jobs()) == 1  # job still pending in Redis
    assert (await client.delete(f"{DOCS}/{document_id}", headers=CSRF)).status_code == 204
    assert await _processor(app).process(uuid.UUID(document_id), patient_id) == "missing"
    assert await _rows(app, document_id) == dict.fromkeys(
        ("documents", "chunks", "lab_results", "medications", "message_citations"), 0
    )


async def test_deletion_during_processing_recreates_nothing(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    patient_id = uuid.UUID((await register_and_login(client, "del-race@example.com")).json()["id"])
    await grant_consent(client)
    document_id = uuid.UUID((await upload(client, (synthetic_dir / NEW).read_bytes())).json()["id"])

    class DeletesWhileEmbedding(FakeLLMProvider):
        async def embed_documents(self, texts):  # type: ignore[no-untyped-def]
            async with app.state.sessionmaker() as session:  # the patient deletes mid-job
                await set_patient_context(session, patient_id)
                await DocumentDeletionService(
                    session, patient_id, storage=app.state.storage
                ).delete(document_id)
            return await super().embed_documents(texts)

    assert (
        await _processor(app, DeletesWhileEmbedding()).process(document_id, patient_id) == "missing"
    )
    assert await _rows(app, str(document_id)) == dict.fromkeys(
        ("documents", "chunks", "lab_results", "medications", "message_citations"), 0
    )


async def test_reupload_after_deletion_creates_a_new_document(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    _, docs = await _patient(client, app, synthetic_dir, "del-reupload@example.com", [OLD])
    await client.delete(f"{DOCS}/{docs[OLD]}", headers=CSRF)
    again = await upload(client, (synthetic_dir / OLD).read_bytes())
    assert again.status_code == 202 and again.json()["id"] != docs[OLD]
