"""M9: deterministic comparisons over real uploaded synthetic reports."""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.services.document_processing import DocumentProcessor
from app.services.lab_comparison import COMPARISON_NOTE
from tests.helpers import grant_consent, register_and_login, upload

pytestmark = pytest.mark.integration
TRENDS = "/api/v1/patient/labs/trends"
ASHA_FILES = [
    "02_asha_lipid_mgdl_2025-11-18.pdf",  # lipids in mg/dL
    "03_asha_hba1c_2025-11-18.pdf",  # "HbA1c"
    "04_asha_glycated_haemoglobin_2026-05-13.pdf",  # renamed: "Glycated Haemoglobin"
    "05_asha_lipid_mmol_2026-05-13.pdf",  # lipids in mmol/L
    "06_asha_fasting_glucose_mmol_ambiguous_date.pdf",  # single glucose, ambiguous date
]


async def _upload_all(
    client: AsyncClient, app, synthetic_dir: Path, email: str, files: list[str]
) -> dict[str, str]:  # type: ignore[no-untyped-def]
    patient_id = uuid.UUID((await register_and_login(client, email)).json()["id"])
    await grant_consent(client)
    processor = DocumentProcessor(
        app.state.sessionmaker, app.state.storage, llm=app.state.llm, max_pages=50
    )
    ids = {}
    for name in files:
        document_id = (await upload(client, (synthetic_dir / name).read_bytes())).json()["id"]
        assert await processor.process(uuid.UUID(document_id), patient_id) == "ready"
        ids[name] = document_id
    return ids


async def test_trends_across_renamed_tests_and_units(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    docs = await _upload_all(client, app, synthetic_dir, "trends@example.com", ASHA_FILES)
    body = (await client.get(TRENDS)).json()
    assert body["note"] == COMPARISON_NOTE
    trends = {t["test_code"]: t for t in body["items"]}
    assert set(trends) == {"CHOL", "GLU_FASTING", "HBA1C", "HDL", "LDL", "TRIG"}

    hba1c = trends["HBA1C"]  # "HbA1c" 7.1 % (Nov 2025) vs "Glycated Haemoglobin" 7.6 % (May 2026)
    assert (hba1c["status"], hba1c["direction"], hba1c["change"], hba1c["percent_change"]) == (
        "worsened",
        "rising",
        0.5,
        7.04,
    )
    assert (hba1c["previous"]["raw_value"], hba1c["latest"]["raw_value"]) == ("7.1", "7.6")
    assert hba1c["latest"]["document_id"] == docs["04_asha_glycated_haemoglobin_2026-05-13.pdf"]
    assert hba1c["previous"]["document_id"] == docs["03_asha_hba1c_2025-11-18.pdf"]
    assert hba1c["latest"]["page"] == 1 and uuid.UUID(hba1c["latest"]["chunk_id"])

    chol = trends["CHOL"]  # 212 mg/dL vs 5.9 mmol/L (= 228.153 mg/dL), converted before comparing
    assert (chol["previous"]["canonical_value"], chol["latest"]["canonical_value"]) == (
        212.0,
        228.153,
    )
    assert (chol["latest"]["raw_value"], chol["latest"]["raw_unit"]) == ("5.9", "mmol/L")
    assert (chol["change"], chol["status"]) == (16.153, "worsened")

    hdl = trends["HDL"]  # 46 mg/dL vs 1.1 mmol/L: falls but stays inside "> 40" / "> 1.0"
    assert (hdl["status"], hdl["direction"], hdl["reason"]) == (
        "stable",
        "falling",
        "within_reference_range",
    )

    glucose = trends["GLU_FASTING"]
    assert (glucose["status"], glucose["reason"], glucose["change"]) == (
        "insufficient_data",
        "single_result",
        None,
    )
    assert glucose["latest"]["date_ambiguous"] is True

    only = (await client.get(TRENDS, params={"test_code": "HBA1C"})).json()["items"]
    assert [t["test_code"] for t in only] == ["HBA1C"]


async def test_trends_are_patient_scoped(client: AsyncClient, app, synthetic_dir: Path) -> None:  # type: ignore[no-untyped-def]
    await _upload_all(client, app, synthetic_dir, "trend-a@example.com", ASHA_FILES[1:3])
    ravi = await _upload_all(
        client, app, synthetic_dir, "trend-b@example.com", ["13_ravi_hba1c_ifcc_2026-03-23.pdf"]
    )
    items = (await client.get(TRENDS)).json()["items"]
    assert [t["test_code"] for t in items] == ["HBA1C"]
    only = items[0]
    assert only["status"] == "insufficient_data"  # Asha's two HbA1c results are invisible
    assert [p["document_id"] for p in only["history"]] == [
        ravi["13_ravi_hba1c_ifcc_2026-03-23.pdf"]
    ]
    assert only["latest"]["canonical_value"] == round(0.0915 * 53 + 2.15, 6)


async def test_trends_require_auth(client: AsyncClient) -> None:
    assert (await client.get(TRENDS)).status_code == 401
