"""M15 backend support: medications list and owner-only source PDFs for page links."""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.services.document_processing import DocumentProcessor
from tests.helpers import grant_consent, register_and_login, upload

pytestmark = pytest.mark.integration
RX = "07_asha_prescription_2026-05-14.pdf"


async def test_medications_and_source_pdf_are_owner_only(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    assert (await client.get("/api/v1/patient/medications")).status_code == 401
    patient_id = uuid.UUID((await register_and_login(client, "dash@example.com")).json()["id"])
    await grant_consent(client)
    data = (synthetic_dir / RX).read_bytes()
    document_id = (await upload(client, data)).json()["id"]
    processor = DocumentProcessor(
        app.state.sessionmaker, app.state.storage, llm=app.state.llm, max_pages=50
    )
    await processor.process(uuid.UUID(document_id), patient_id)

    meds = (await client.get("/api/v1/patient/medications")).json()["items"]
    assert sorted(m["name"] for m in meds) == ["Atorvastatin 10 mg", "Metformin 500 mg"]
    assert {(m["document_id"], m["page"]) for m in meds} == {(document_id, 1)}

    pdf = await client.get(f"/api/v1/patient/documents/{document_id}/file")
    assert pdf.status_code == 200 and pdf.content == data
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["cache-control"] == "no-store"
    assert pdf.headers["x-content-type-options"] == "nosniff"

    await register_and_login(client, "dash.other@example.com")
    assert (await client.get(f"/api/v1/patient/documents/{document_id}/file")).status_code == 404
    assert (await client.get("/api/v1/patient/medications")).json()["items"] == []
