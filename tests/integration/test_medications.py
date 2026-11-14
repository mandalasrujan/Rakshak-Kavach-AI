"""Integration tests for medication history: multi-visit grouping, dosage change preservation,
deduplication within visits, and patient isolation.
"""

import uuid

import pymupdf
import pytest
from httpx import AsyncClient

from app.services.document_processing import DocumentProcessor
from tests.helpers import grant_consent, register_and_login, upload

pytestmark = pytest.mark.integration


def _create_prescription_pdf(prescription_date: str, lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    text = f"Prescription Date: {prescription_date}\n\nPrescribed Medications:\n"
    for line in lines:
        text += f"- {line}\n"
    page.insert_text((50, 72), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


async def test_medication_history_two_visits_and_patient_isolation(
    client: AsyncClient, app
) -> None:  # type: ignore[no-untyped-def]
    # 1. Register test patient 1
    login_res = await register_and_login(client, "patient.visits@example.com")
    patient_id = uuid.UUID(login_res.json()["id"])
    await grant_consent(client)

    # 2. Create Visit 1 PDF:
    # Metformin 500 mg, Atorvastatin 10 mg, Vitamin D3 1000 IU
    # Plus duplicate Metformin line to verify intra-visit deduplication
    v1_pdf = _create_prescription_pdf(
        "10/01/2026",
        [
            "Metformin 500 mg — twice daily with meals.",
            "Atorvastatin 10 mg — nightly.",
            "Vitamin D3 1000 IU — daily.",
            "Metformin 500 mg — twice daily with meals.",  # duplicate row within visit
        ],
    )
    v1_upload = (await upload(client, v1_pdf, "visit1_prescription.pdf")).json()
    v1_doc_id = uuid.UUID(v1_upload["id"])

    # 3. Create Visit 2 PDF:
    # Metformin 500 mg, Atorvastatin 20 mg (dosage change), Vitamin D3 2000 IU (dosage change)
    v2_pdf = _create_prescription_pdf(
        "15/04/2026",
        [
            "Metformin 500 mg — twice daily with meals.",
            "Atorvastatin 20 mg — nightly.",
            "Vitamin D3 2000 IU — daily.",
        ],
    )
    v2_upload = (await upload(client, v2_pdf, "visit2_prescription.pdf")).json()
    v2_doc_id = uuid.UUID(v2_upload["id"])

    # 4. Process both documents
    processor = DocumentProcessor(
        app.state.sessionmaker, app.state.storage, llm=app.state.llm, max_pages=50
    )
    await processor.process(v1_doc_id, patient_id)
    await processor.process(v2_doc_id, patient_id)

    # 5. Query patient medications API
    res = await client.get("/api/v1/patient/medications")
    assert res.status_code == 200
    data = res.json()

    # Verify visits grouping exists
    assert "visits" in data
    visits = data["visits"]
    assert len(visits) == 2, f"Expected 2 visits, got {len(visits)}"

    # Visit 2 should be first (ordered by start_date desc)
    visit2 = next(v for v in visits if v["document_id"] == str(v2_doc_id))
    visit1 = next(v for v in visits if v["document_id"] == str(v1_doc_id))

    assert visit1["date"] == "2026-01-10"
    assert visit2["date"] == "2026-04-15"

    # Verify Visit 1 medications (exactly 3, duplicate Metformin removed)
    v1_meds = visit1["medications"]
    assert len(v1_meds) == 3, f"Expected 3 deduplicated meds in Visit 1, got {len(v1_meds)}"
    v1_by_name = {m["name"]: m for m in v1_meds}
    assert "Metformin" in v1_by_name
    assert v1_by_name["Metformin"]["dose"] == "500 mg"
    assert "twice daily with meals" in v1_by_name["Metformin"]["frequency"]

    assert "Atorvastatin" in v1_by_name
    assert v1_by_name["Atorvastatin"]["dose"] == "10 mg"
    assert v1_by_name["Atorvastatin"]["frequency"] == "nightly"

    assert "Vitamin D3" in v1_by_name
    assert v1_by_name["Vitamin D3"]["dose"] == "1000 IU"
    assert v1_by_name["Vitamin D3"]["frequency"] == "daily"

    # Verify Visit 2 medications (dosage changes preserved)
    v2_meds = visit2["medications"]
    assert len(v2_meds) == 3
    v2_by_name = {m["name"]: m for m in v2_meds}
    assert "Metformin" in v2_by_name
    assert v2_by_name["Metformin"]["dose"] == "500 mg"
    assert "twice daily with meals" in v2_by_name["Metformin"]["frequency"]

    assert "Atorvastatin" in v2_by_name
    assert v2_by_name["Atorvastatin"]["dose"] == "20 mg"  # changed from 10 mg
    assert v2_by_name["Atorvastatin"]["frequency"] == "nightly"

    assert "Vitamin D3" in v2_by_name
    assert v2_by_name["Vitamin D3"]["dose"] == "2000 IU"  # changed from 1000 IU
    assert v2_by_name["Vitamin D3"]["frequency"] == "daily"

    # Verify items list has all 6 non-duplicate items
    assert len(data["items"]) == 6

    # 6. Verify cross-patient isolation (another patient cannot access these medications)
    await register_and_login(client, "other.patient@example.com")
    other_res = await client.get("/api/v1/patient/medications")
    assert other_res.status_code == 200
    other_data = other_res.json()
    assert other_data["items"] == []
    assert other_data["visits"] == []

    # Other patient cannot access Patient 1's source document
    doc_res = await client.get(f"/api/v1/patient/documents/{v1_doc_id}/file")
    assert doc_res.status_code == 404
