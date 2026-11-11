"""M8: normalized lab results stored with provenance, flagged values, isolation."""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

from app.db.patient_context import set_patient_context
from app.services.document_processing import DocumentProcessor
from scripts.generate_synthetic_pdfs import ASHA, LabRow, LabSection, Report, build_pdf
from tests.helpers import grant_consent, register_and_login, upload

pytestmark = pytest.mark.integration
LABS = "/api/v1/patient/labs"
CBC = "01_asha_cbc_lft_2025-11-18.pdf"


async def _process(
    client: AsyncClient, app, data: bytes, email: str
) -> tuple[uuid.UUID, uuid.UUID]:  # type: ignore[no-untyped-def]
    patient_id = uuid.UUID((await register_and_login(client, email)).json()["id"])
    await grant_consent(client)
    document_id = uuid.UUID((await upload(client, data)).json()["id"])
    processor = DocumentProcessor(
        app.state.sessionmaker, app.state.storage, llm=app.state.llm, max_pages=50
    )
    assert await processor.process(document_id, patient_id) == "ready"
    return patient_id, document_id


def _odd_report(tmp_path: Path) -> bytes:
    report = Report(
        "odd.pdf",
        ASHA,
        "lab_report",
        "Mixed Panel",
        "Test Lab (Synthetic)",
        "20/06/2026",
        "21/06/2026",
        "2026-06-20",
        lab_pages=[
            LabSection(
                "Mixed Panel",
                (
                    LabRow("Hemoglobin", "124", "g/dL", "12.0 - 15.5"),
                    LabRow("Ferritin Index", "40", "ng/mL", "20 - 200"),
                    LabRow("Fasting Plasma Glucose", "Positive", "mg/dL", "70 - 99"),
                    LabRow("Serum Creatinine", "1.1", "furlongs", "0.6 - 1.2"),
                    LabRow("TSH", "2.1", "µIU/mL", "0.4 - 4.0"),
                ),
            )
        ],
    )
    build_pdf(report, tmp_path)
    return (tmp_path / "odd.pdf").read_bytes()


async def test_lab_rows_become_normalized_results_with_provenance(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    _, document_id = await _process(
        client, app, (synthetic_dir / CBC).read_bytes(), "labs@example.com"
    )
    body = (await client.get(LABS)).json()
    assert body["total"] == 11
    hemoglobin = next(r for r in body["items"] if r["test_code"] == "HGB")
    assert hemoglobin | {"id": None, "chunk_id": None} == {
        "id": None,
        "chunk_id": None,
        "document_id": str(document_id),
        "page": 1,
        "raw_name": "Hemoglobin",
        "raw_value": "12.4",
        "raw_unit": "g/dL",
        "raw_reference": "12.0 - 15.5",
        "test_code": "HGB",
        "value": 12.4,
        "unit": "g/dL",
        "canonical_value": 12.4,
        "canonical_unit": "g/dL",
        "ref_low": 12.0,
        "ref_high": 15.5,
        "canonical_ref_low": 12.0,
        "canonical_ref_high": 15.5,
        "collected_on": "2025-11-18",
        "reported_on": "2025-11-19",
        "date_ambiguous": False,
        "validation_status": "ok",
        "dictionary_version": "2026-11-11",
    }
    async with app.state.admin_engine.connect() as conn:  # every result points at its source row
        rows = (
            await conn.execute(
                text(
                    "SELECT l.raw_name, l.raw_value, l.page, c.page AS chunk_page, c.text, "
                    "c.document_id FROM lab_results l JOIN chunks c ON c.id = l.chunk_id"
                )
            )
        ).all()
    assert len(rows) == 11
    for row in rows:
        assert row.page == row.chunk_page and row.document_id == document_id
        assert f"Test: {row.raw_name}; Result: {row.raw_value};" in row.text
    assert {r["page"] for r in body["items"] if r["test_code"] == "ALT"} == {2}


async def test_unusable_values_are_stored_flagged_and_logged_without_values(
    client: AsyncClient, app, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    with capture_logs(processors=[merge_contextvars]) as logs:
        _, document_id = await _process(client, app, _odd_report(tmp_path), "odd@example.com")
    statuses = {r["raw_name"]: r for r in (await client.get(LABS)).json()["items"]}
    assert {name: r["validation_status"] for name, r in statuses.items()} == {
        "Hemoglobin": "implausible_value",
        "Ferritin Index": "unknown_test",
        "Fasting Plasma Glucose": "non_numeric_value",
        "Serum Creatinine": "unknown_unit",
        "TSH": "ok",
    }
    assert statuses["Hemoglobin"]["raw_value"] == "124"  # kept, never "corrected"
    assert statuses["Hemoglobin"]["canonical_value"] is None
    flagged = [e for e in logs if e["event"] == "lab.value_flagged"]
    assert sorted(e["reason"] for e in flagged) == [
        "implausible_value",
        "non_numeric_value",
        "unknown_test",
        "unknown_unit",
    ]
    assert all(e["document_id"] == str(document_id) for e in flagged)
    for private in ("124", "Positive", "Ferritin", "furlongs"):
        assert private not in repr(logs)


async def test_reprocessing_replaces_results(client: AsyncClient, app, synthetic_dir: Path) -> None:  # type: ignore[no-untyped-def]
    patient_id, document_id = await _process(
        client, app, (synthetic_dir / CBC).read_bytes(), "relab@example.com"
    )
    first = {r["id"] for r in (await client.get(LABS)).json()["items"]}
    async with app.state.admin_engine.begin() as conn:
        await conn.execute(
            text("UPDATE documents SET status = 'processing' WHERE id = :d"), {"d": document_id}
        )
    processor = DocumentProcessor(
        app.state.sessionmaker, app.state.storage, llm=app.state.llm, max_pages=50
    )
    await processor.process(document_id, patient_id)
    second = (await client.get(LABS)).json()
    assert second["total"] == 11 and not first & {r["id"] for r in second["items"]}


async def test_lab_results_are_patient_scoped(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    await _process(client, app, (synthetic_dir / CBC).read_bytes(), "labs-a@example.com")
    patient_b = uuid.UUID((await register_and_login(client, "labs-b@example.com")).json()["id"])
    assert (await client.get(LABS)).json()["total"] == 0
    async with app.state.sessionmaker() as session:  # RLS: no context, no rows; B sees none
        assert (await session.execute(text("SELECT count(*) FROM lab_results"))).scalar_one() == 0
        await set_patient_context(session, patient_b)
        assert (await session.execute(text("SELECT count(*) FROM lab_results"))).scalar_one() == 0


async def test_lab_list_filters_validates_and_requires_auth(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    assert (await client.get(LABS)).status_code == 401
    await _process(client, app, (synthetic_dir / CBC).read_bytes(), "filter@example.com")
    alt = (await client.get(LABS, params={"test_code": "ALT"})).json()
    assert alt["total"] == 1 and alt["items"][0]["raw_name"] == "ALT (SGPT)"
    page = (await client.get(LABS, params={"limit": 5, "offset": 10})).json()
    assert (page["total"], len(page["items"])) == (11, 1)
    assert (await client.get(LABS, params={"test_code": "alt; drop"})).status_code == 422
