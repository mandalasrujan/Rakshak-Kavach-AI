"""M4: worker-side validation, consent re-check, idempotency."""

import uuid
from pathlib import Path

import pymupdf
import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.services.document_processing import DocumentProcessor
from tests.helpers import CSRF, grant_consent, register_and_login, upload

pytestmark = pytest.mark.integration
CBC = "01_asha_cbc_lft_2025-11-18.pdf"


async def _uploaded(client: AsyncClient, data: bytes, email: str) -> tuple[str, str]:
    patient_id = (await register_and_login(client, email)).json()["id"]
    await grant_consent(client)
    response = await upload(client, data)
    assert response.status_code == 202, response.text
    return response.json()["id"], patient_id


def _processor(app, max_pages: int = 50) -> DocumentProcessor:  # type: ignore[no-untyped-def]
    return DocumentProcessor(
        app.state.sessionmaker, app.state.storage, llm=app.state.llm, max_pages=max_pages
    )


async def _status(client: AsyncClient, document_id: str) -> tuple[str, str | None]:
    body = (await client.get(f"/api/v1/patient/documents/{document_id}")).json()
    return body["status"], body["failure_reason"]


def _encrypted_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "synthetic")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    doc.close()
    return data


@pytest.mark.parametrize(
    ("make_data", "max_pages", "reason"),
    [
        (lambda d: _encrypted_pdf(), 50, "encrypted_pdf"),
        (lambda d: (d / CBC).read_bytes(), 1, "too_many_pages"),
        (lambda d: b"%PDF-1.4\nthis is not really a pdf", 50, "unreadable_pdf"),
    ],
    ids=["encrypted", "too-many-pages", "corrupt"],
)
async def test_invalid_pdfs_fail_with_reason(
    client: AsyncClient,
    app,
    synthetic_dir: Path,
    make_data,
    max_pages: int,
    reason: str,  # type: ignore[no-untyped-def]
) -> None:
    document_id, patient_id = await _uploaded(client, make_data(synthetic_dir), "bad@example.com")
    result = await _processor(app, max_pages).process(uuid.UUID(document_id), uuid.UUID(patient_id))
    assert result == "failed"
    assert await _status(client, document_id) == ("failed", reason)


async def test_revoked_consent_stops_processing(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    document_id, patient_id = await _uploaded(
        client, (synthetic_dir / CBC).read_bytes(), "revoked@example.com"
    )
    await client.delete("/api/v1/patient/consent", headers=CSRF)
    await _processor(app).process(uuid.UUID(document_id), uuid.UUID(patient_id))
    assert await _status(client, document_id) == ("failed", "consent_revoked")


async def test_processing_is_idempotent_and_patient_scoped(
    client: AsyncClient,
    app,
    synthetic_dir: Path,  # type: ignore[no-untyped-def]
) -> None:
    document_id, patient_id = await _uploaded(
        client, (synthetic_dir / CBC).read_bytes(), "idem.proc@example.com"
    )
    processor = _processor(app)
    wrong_owner = await processor.process(uuid.UUID(document_id), uuid.uuid4())
    assert wrong_owner == "missing"  # a job with the wrong patient_id cannot touch the document
    assert await processor.process(uuid.UUID(document_id), uuid.UUID(patient_id)) == "ready"
    assert await processor.process(uuid.UUID(document_id), uuid.UUID(patient_id)) == "ready"
    async with app.state.admin_engine.connect() as conn:
        ready_events = (
            await conn.execute(
                text("SELECT count(*) FROM audit_log WHERE action = 'document.ready'")
            )
        ).scalar_one()
    assert ready_events == 1


async def _chunks(app, document_id: str) -> list:  # type: ignore[no-untyped-def]
    async with app.state.admin_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT patient_id, document_id, page, kind, text FROM chunks "
                "WHERE document_id = :d ORDER BY kind, page, text"
            ),
            {"d": document_id},
        )
        return list(result)


async def test_processing_stores_patient_scoped_chunks(
    client: AsyncClient,
    app,
    synthetic_dir: Path,  # type: ignore[no-untyped-def]
) -> None:
    data = (synthetic_dir / CBC).read_bytes()
    doc_a, patient_a = await _uploaded(client, data, "chunks-a@example.com")
    doc_b, patient_b = await _uploaded(client, data, "chunks-b@example.com")
    processor = _processor(app)
    for document_id, patient_id in ((doc_a, patient_a), (doc_b, patient_b)):
        assert await processor.process(uuid.UUID(document_id), uuid.UUID(patient_id)) == "ready"

    rows_a, rows_b = await _chunks(app, doc_a), await _chunks(app, doc_b)
    assert {str(r.patient_id) for r in rows_a} == {patient_a}
    assert {str(r.patient_id) for r in rows_b} == {patient_b}
    lab_pages = [r.page for r in rows_a if r.kind == "lab_row"]
    assert (lab_pages.count(1), lab_pages.count(2)) == (6, 5)
    assert any(r.text.startswith("Test: Hemoglobin; Result: 12.4") for r in rows_a)

    async with app.state.admin_engine.connect() as conn:
        details = (
            await conn.execute(
                text(
                    "SELECT metadata FROM audit_log "
                    "WHERE action = 'document.ready' AND target_id = :d"
                ),
                {"d": doc_a},
            )
        ).scalar_one()
    assert details == {
        "pages": 2,
        "lab_rows": 11,
        "narrative_chunks": len(rows_a) - 11,
        "lab_results_flagged": 0,
    }


async def test_reprocessing_after_a_crash_replaces_chunks(
    client: AsyncClient,
    app,
    synthetic_dir: Path,  # type: ignore[no-untyped-def]
) -> None:
    document_id, patient_id = await _uploaded(
        client, (synthetic_dir / CBC).read_bytes(), "crash@example.com"
    )
    processor = _processor(app)
    await processor.process(uuid.UUID(document_id), uuid.UUID(patient_id))
    first = await _chunks(app, document_id)
    async with app.state.admin_engine.begin() as conn:  # simulate a worker dying mid-job
        await conn.execute(
            text("UPDATE documents SET status = 'processing' WHERE id = :d"), {"d": document_id}
        )
    assert await processor.process(uuid.UUID(document_id), uuid.UUID(patient_id)) == "ready"
    second = await _chunks(app, document_id)
    assert [(r.page, r.kind, r.text) for r in second] == [(r.page, r.kind, r.text) for r in first]


async def test_image_only_upload_fails_with_no_text_layer(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    doc = pymupdf.open()
    doc.new_page().draw_rect(pymupdf.Rect(50, 50, 300, 300), fill=(0, 0, 0))
    data = doc.tobytes()
    doc.close()
    document_id, patient_id = await _uploaded(client, data, "scan@example.com")
    await _processor(app).process(uuid.UUID(document_id), uuid.UUID(patient_id))
    assert await _status(client, document_id) == ("failed", "no_text_layer")
    assert await _chunks(app, document_id) == []
