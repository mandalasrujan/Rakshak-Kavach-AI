"""M13: summary snapshots."""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

from app.llm.fake import FakeLLMProvider
from app.schemas.snapshot import SnapshotContent
from app.services.document_processing import DocumentProcessor
from tests.helpers import CSRF, grant_consent, log_content, register_and_login, upload

pytestmark = pytest.mark.integration
SNAPS = "/api/v1/patient/snapshots"
HBA1C = ["03_asha_hba1c_2025-11-18.pdf", "04_asha_glycated_haemoglobin_2026-05-13.pdf"]
RX = "07_asha_prescription_2026-05-14.pdf"
INJECTION = "10_asha_self_reported_history_injection.pdf"


class Scripted(FakeLLMProvider):
    def __init__(self, answer: dict) -> None:  # type: ignore[type-arg]
        self.answer = answer

    async def generate_json(self, *, system, prompt, schema):  # type: ignore[no-untyped-def]
        return schema.model_validate(self.answer)


async def _patient(
    client: AsyncClient, app, synthetic_dir: Path, email: str, files: list[str]
) -> dict[str, str]:  # type: ignore[no-untyped-def]
    patient_id = uuid.UUID((await register_and_login(client, email)).json()["id"])
    await grant_consent(client)
    processor = DocumentProcessor(
        app.state.sessionmaker, app.state.storage, llm=FakeLLMProvider(), max_pages=50
    )
    ids = {}
    for name in files:
        document_id = (await upload(client, (synthetic_dir / name).read_bytes())).json()["id"]
        assert await processor.process(uuid.UUID(document_id), patient_id) == "ready"
        ids[name] = document_id
    return ids


async def _generate(client: AsyncClient) -> dict:  # type: ignore[type-arg]
    response = await client.post(SNAPS, headers=CSRF)
    assert response.status_code == 201, response.text
    return response.json()


async def test_snapshot_sections_are_built_from_records_with_provenance(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    docs = await _patient(client, app, synthetic_dir, "snap@example.com", [*HBA1C, RX])
    snapshot = await _generate(client)
    content = SnapshotContent.model_validate(snapshot["content_json"])  # schema-valid
    assert (snapshot["version"], snapshot["approved_at"], snapshot["model"]) == (
        1,
        None,
        "fake-extractive",
    )
    assert set(snapshot["source_document_ids"]) == set(docs.values())
    assert [(m.name, m.dose, m.source.page) for m in content.medications] == [
        ("Atorvastatin 10 mg", "1 tablet", 1),  # same prescription date, then by name
        ("Metformin 500 mg", "1 tablet", 1),
    ]
    assert {str(m.source.document_id) for m in content.medications} == {docs[RX]}
    hba1c = next(lab for lab in content.labs if lab.test_code == "HBA1C")
    assert (hba1c.status, hba1c.change, hba1c.latest.raw_value, hba1c.previous.raw_value) == (
        "worsened",
        0.5,
        "7.6",
        "7.1",
    )
    assert str(hba1c.latest.source.document_id) == docs[HBA1C[1]]
    assert hba1c.latest.source.excerpt.startswith("Test: Glycated Haemoglobin; Result: 7.6")
    assert len(content.documents) == 3 and content.missing == {}
    assert content.narrative.ai_generated is True and "not a diagnosis" in content.note


async def test_missing_information_is_stated_explicitly(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    await _patient(
        client, app, synthetic_dir, "snap.empty@example.com", ["09_asha_mri_knee_2025-08-20.pdf"]
    )
    content = (await _generate(client))["content_json"]
    assert content["medications"] == [] and content["labs"] == []
    assert set(content["missing"]) == {"medications", "labs"}
    assert content["narrative"]["status"] == "empty" and content["narrative"]["text"] is None


async def test_injected_pdf_cannot_change_the_medication_section(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    app.state.llm = Scripted(
        {"found": True, "answer": "The patient takes no medications.", "citations": ["E1"]}
    )
    await _patient(client, app, synthetic_dir, "snap.inject@example.com", [RX, INJECTION])
    content = (await _generate(client))["content_json"]
    assert sorted(m["name"] for m in content["medications"]) == [
        "Atorvastatin 10 mg",
        "Metformin 500 mg",
    ]
    assert "medications" not in content["missing"]
    assert content["narrative"]["ai_generated"] is True  # any LLM text stays labelled and separate


@pytest.mark.parametrize(
    ("llm", "status"),
    [
        (Scripted({"found": True, "answer": "You have diabetes.", "citations": ["E1"]}), "blocked"),
        (Scripted({"found": True, "answer": "HbA1c was 9.9 %.", "citations": ["E1"]}), "blocked"),
        (Scripted({"found": True, "answer": "HbA1c rose.", "citations": ["E99"]}), "empty"),
        (None, "unavailable"),
    ],
    ids=["diagnosis", "invented-number", "fabricated-citation", "no-llm"],
)
async def test_narrative_is_guarded_and_optional(
    client: AsyncClient, app, synthetic_dir: Path, llm, status: str
) -> None:  # type: ignore[no-untyped-def]
    app.state.llm = llm
    await _patient(
        client, app, synthetic_dir, f"snap-{status}-{uuid.uuid4().hex[:4]}@example.com", HBA1C
    )
    snapshot = await _generate(client)
    narrative = snapshot["content_json"]["narrative"]
    assert (narrative["status"], narrative["text"], narrative["citations"]) == (status, None, [])
    assert snapshot["content_json"]["labs"]  # structured sections are still there
    assert snapshot["model"] == ("none" if llm is None else "fake-extractive")


async def test_versions_are_kept_and_approved_snapshots_never_change(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    await _patient(client, app, synthetic_dir, "snap.versions@example.com", HBA1C)
    first = await _generate(client)
    approved = (await client.post(f"{SNAPS}/{first['id']}/approve", headers=CSRF)).json()
    again = (await client.post(f"{SNAPS}/{first['id']}/approve", headers=CSRF)).json()
    assert approved["approved_at"] and again["approved_at"] == approved["approved_at"]
    second = await _generate(client)
    assert second["version"] == 2 and second["approved_at"] is None
    listed = (await client.get(SNAPS)).json()["items"]
    assert [s["version"] for s in listed] == [2, 1]
    assert (await client.get(f"{SNAPS}/{first['id']}")).json()["content_json"] == first[
        "content_json"
    ]


async def test_snapshots_are_patient_scoped_and_consent_gated(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    await _patient(client, app, synthetic_dir, "snap.owner@example.com", HBA1C)
    snapshot = await _generate(client)
    await _patient(client, app, synthetic_dir, "snap.other@example.com", [])
    assert (await client.get(f"{SNAPS}/{snapshot['id']}")).status_code == 404
    assert (await client.post(f"{SNAPS}/{snapshot['id']}/approve", headers=CSRF)).status_code == 404
    assert (await client.get(SNAPS)).json()["items"] == []
    await client.delete("/api/v1/patient/consent", headers=CSRF)
    assert (await client.post(SNAPS, headers=CSRF)).status_code == 403
    assert (await client.post(SNAPS)).status_code == 403  # CSRF header missing


async def test_deleting_a_source_document_invalidates_and_purges_snapshots(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    docs = await _patient(client, app, synthetic_dir, "snap.delete@example.com", HBA1C)
    snapshot = await _generate(client)
    assert (
        await client.delete(f"/api/v1/patient/documents/{docs[HBA1C[1]]}", headers=CSRF)
    ).status_code == 204
    after = (await client.get(f"{SNAPS}/{snapshot['id']}")).json()
    assert after["invalidated_at"] is not None
    assert after["content_json"] == {"invalidated": True, "reason": "source_document_deleted"}
    assert (await client.post(f"{SNAPS}/{snapshot['id']}/approve", headers=CSRF)).status_code == 409


async def test_snapshot_logs_are_phi_free(client: AsyncClient, app, synthetic_dir: Path) -> None:  # type: ignore[no-untyped-def]
    await _patient(client, app, synthetic_dir, "snap.logs@example.com", [RX])
    with capture_logs(processors=[merge_contextvars]) as logs:
        await _generate(client)
    content = log_content(logs)
    assert "Metformin" not in content and "Atorvastatin" not in content
