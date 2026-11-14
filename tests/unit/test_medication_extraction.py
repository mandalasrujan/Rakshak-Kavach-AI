"""Unit tests for deterministic medication extraction and prescription date parsing."""

from datetime import date

from app.models.chunk import NARRATIVE
from app.services.extraction import ExtractedChunk
from app.services.lab_normalization import parse_document_dates
from app.services.medication_extraction import extract_medications


def _chunk(text: str, page: int = 1) -> ExtractedChunk:
    return ExtractedChunk(page=page, kind=NARRATIVE, text=text)


def test_prescription_dates_parsed_correctly() -> None:
    # Prescription Date with DD/MM/YYYY
    d1 = parse_document_dates(["Prescription Date: 10/01/2026\nPatient: John Doe"])
    assert d1.reported_on == date(2026, 1, 10)

    # Visit Date with YYYY-MM-DD
    d2 = parse_document_dates(["Visit Date: 2026-04-15\nPrescribed on: 2026-04-15"])
    assert d2.reported_on == date(2026, 4, 15)

    # Consultation Date
    d3 = parse_document_dates(["Consultation Date: 14/05/2026"])
    assert d3.reported_on == date(2026, 5, 14)

    # Generic Date header
    d4 = parse_document_dates(["Date: 05/11/2025"])
    assert d4.reported_on == date(2025, 11, 5)


def test_table_with_leading_index_and_aliases() -> None:
    text = (
        "S.No: 1; Medicine Name: Metformin 500 mg; Dose: 1 tablet; "
        "Frequency: Twice daily; Duration: 90 days\n"
        "Item: 2; Drug Name: Atorvastatin; Dose: 10 mg; Timing: Nightly; Instructions: with water\n"
        "#: 3; Prescribed Medication: Vitamin D3; Strength: 1000 IU; Regimen: Daily"
    )
    meds = extract_medications([_chunk(text)])
    assert len(meds) == 3

    assert meds[0].name == "Metformin 500 mg"
    assert meds[0].dose == "1 tablet"
    assert meds[0].frequency == "Twice daily"
    assert meds[0].duration == "90 days"

    assert meds[1].name == "Atorvastatin"
    assert meds[1].dose == "10 mg"
    assert meds[1].frequency == "Nightly (with water)"

    assert meds[2].name == "Vitamin D3"
    assert meds[2].dose == "1000 IU"
    assert meds[2].frequency == "Daily"


def test_narrative_bullet_lines_and_dosage_parsing() -> None:
    text = (
        "Prescriptions:\n"
        "- Metformin 500 mg — twice daily with meals.\n"
        "- Atorvastatin 10 mg — nightly.\n"
        "- Vitamin D3 1000 IU — daily."
    )
    meds = extract_medications([_chunk(text)])
    assert len(meds) == 3

    assert meds[0].name == "Metformin"
    assert meds[0].dose == "500 mg"
    assert meds[0].frequency == "twice daily with meals"

    assert meds[1].name == "Atorvastatin"
    assert meds[1].dose == "10 mg"
    assert meds[1].frequency == "nightly"

    assert meds[2].name == "Vitamin D3"
    assert meds[2].dose == "1000 IU"
    assert meds[2].frequency == "daily"


def test_general_advice_and_narrative_notes_not_extracted() -> None:
    text = (
        "Presenting complaint: tiredness for two months.\n"
        "History: type 2 diabetes for six years.\n"
        "Plan: continue Metformin 500 mg twice daily; start Atorvastatin 10 mg at night.\n"
        "- Advised low salt and low carbohydrate diet.\n"
        "- Walk 30 minutes daily.\n"
        "- Follow up in 3 months."
    )
    meds = extract_medications([_chunk(text)])
    assert meds == []


def test_deduplication_within_same_page_chunks() -> None:
    text = (
        "- Metformin 500 mg — twice daily with meals.\n"
        "- Metformin 500 mg — twice daily with meals.\n"
        "Medicine: Atorvastatin; Dose: 10 mg; Frequency: Nightly\n"
        "Medicine: Atorvastatin; Dose: 10 mg; Frequency: Nightly\n"
    )
    # Both in same chunk and across repeated chunks on page 1
    chunk1 = _chunk(text, page=1)
    chunk2 = _chunk(text, page=1)
    meds = extract_medications([chunk1, chunk2])
    assert len(meds) == 2
    assert {m.name for m in meds} == {"Metformin", "Atorvastatin"}
