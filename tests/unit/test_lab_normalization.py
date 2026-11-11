"""M8: deterministic lab normalization (no database, no LLM)."""

from datetime import date
from pathlib import Path

import pytest

from app.services.extraction import extract_pdf
from app.services.lab_normalization import (
    CENSORED_VALUE,
    IMPLAUSIBLE_VALUE,
    MISSING_VALUE,
    NON_NUMERIC_VALUE,
    OK,
    UNKNOWN_TEST,
    UNKNOWN_UNIT,
    load_dictionary,
    normalize_row,
    normalize_unit,
    parse_document_dates,
    parse_reference,
    parse_value,
    resolve_test,
)
from scripts.generate_synthetic_pdfs import _reports


def _row(name: str, value: str, unit: str = "", reference: str = ""):  # type: ignore[no-untyped-def]
    cells = (("Test", name), ("Result", value), ("Unit", unit), ("Reference Range", reference))
    return normalize_row(cells, page=1)


def test_dictionary_is_complete_and_consistent() -> None:
    d = load_dictionary()
    assert len(d.tests) >= 40 and d.version
    units = set(d.unit_aliases.values())
    for test in d.tests.values():
        assert test.unit in units, test.code
        assert set(test.conversions) <= units, test.code
        assert test.plausible[0] < test.plausible[1]


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("HbA1c", "HBA1C"),
        ("Glycated Haemoglobin", "HBA1C"),
        ("HbA1c (IFCC)", "HBA1C"),
        ("hemoglobin A1c", "HBA1C"),
        ("Haemoglobin", "HGB"),
        ("ALT (SGPT)", "ALT"),
        ("SGPT", "ALT"),
        ("  Serum   Creatinine : ", "CREAT"),
        ("Total Cholesterol*", "CHOL"),
        ("Fasting Plasma Glucose", "GLU_FASTING"),
        ("Ferritin Index", None),
        ("", None),
    ],
)
def test_equivalent_test_names_resolve_to_one_code(raw: str, code: str | None) -> None:
    assert resolve_test(raw) == code


@pytest.mark.parametrize(
    ("raw", "unit"),
    [
        ("mg/dl", "mg/dL"),
        ("MG/DL", "mg/dL"),
        ("µmol/L", "µmol/L"),
        ("μmol/L", "µmol/L"),
        ("umol/l", "µmol/L"),
        ("x10^3/µL", "x10^3/µL"),
        ("10^3/uL", "x10^3/µL"),
        ("mL/min/1.73m2", "mL/min/1.73m2"),
        ("furlongs", None),
        ("", None),
    ],
)
def test_unit_spellings_are_normalized(raw: str, unit: str | None) -> None:
    assert normalize_unit(raw) == unit


@pytest.mark.parametrize(
    ("raw", "value", "status"),
    [
        ("12.4", 12.4, OK),
        (" 7 ", 7.0, OK),
        ("1,234", 1234.0, OK),
        ("12.4 g/dL", 12.4, OK),
        ("<0.5", None, CENSORED_VALUE),
        ("> 90", None, CENSORED_VALUE),
        ("Positive", None, NON_NUMERIC_VALUE),
        ("12,4", None, NON_NUMERIC_VALUE),
        ("12.4.5", None, NON_NUMERIC_VALUE),
        ("", None, MISSING_VALUE),
        ("  ", None, MISSING_VALUE),
    ],
)
def test_numeric_parsing(raw: str, value: float | None, status: str) -> None:
    assert parse_value(raw)[:2] == (value, status)


@pytest.mark.parametrize(
    ("raw", "bounds"),
    [
        ("12.0 - 15.5", (12.0, 15.5)),
        ("3.9 to 5.5", (3.9, 5.5)),
        ("0.4\u20134.0", (0.4, 4.0)),
        ("< 200", (None, 200.0)),
        ("<=5.6", (None, 5.6)),
        ("Up to 40", (None, 40.0)),
        ("> 40", (40.0, None)),
        ("≥ 60", (60.0, None)),
        ("Negative", (None, None)),
        ("", (None, None)),
    ],
)
def test_reference_ranges(raw: str, bounds: tuple[float | None, float | None]) -> None:
    assert parse_reference(raw) == bounds


def test_compatible_units_convert_deterministically_and_keep_source_values() -> None:
    glucose = _row("Fasting Plasma Glucose", "7.4", "mmol/L", "3.9 - 5.5")
    assert glucose.validation_status == OK
    assert (glucose.raw_value, glucose.value, glucose.unit) == ("7.4", 7.4, "mmol/L")
    assert (glucose.canonical_value, glucose.canonical_unit) == (133.2, "mg/dL")
    assert (glucose.ref_low, glucose.ref_high) == (3.9, 5.5)  # source units kept
    assert (glucose.canonical_ref_low, glucose.canonical_ref_high) == (70.2, 99.0)

    hba1c = _row("HbA1c (IFCC)", "53", "mmol/mol", "20 - 42")
    assert hba1c.canonical_value == round(0.0915 * 53 + 2.15, 6)  # intercept, not just factor
    assert hba1c.canonical_unit == "%"

    creatinine = _row("Serum Creatinine", "118", "µmol/L")
    assert creatinine.canonical_value == pytest.approx(118 / 88.4, rel=1e-6)

    assert _row("Fasting Plasma Glucose", "7.4", "mmol/L") == glucose.__class__(
        **{
            **glucose.__dict__,
            "raw_reference": "",
            "ref_low": None,
            "ref_high": None,
            "canonical_ref_low": None,
            "canonical_ref_high": None,
        }
    )


@pytest.mark.parametrize(
    ("row", "status"),
    [
        (("Fasting Plasma Glucose", "7.4", "g/dL"), UNKNOWN_UNIT),  # incompatible unit
        (("Hemoglobin", "12.4", ""), UNKNOWN_UNIT),  # missing unit
        (("Hemoglobin", "124", "g/dL"), IMPLAUSIBLE_VALUE),
        (("Ferritin Index", "40", "ng/mL"), UNKNOWN_TEST),
        (("Hemoglobin", "Positive", "g/dL"), NON_NUMERIC_VALUE),
        (("Hemoglobin", "", "g/dL"), MISSING_VALUE),
    ],
)
def test_unusable_values_are_flagged_not_changed(row: tuple[str, str, str], status: str) -> None:
    result = _row(*row)
    assert result.validation_status == status
    assert result.canonical_value is None
    assert result.raw_value == row[1]


def test_document_dates_are_parsed_as_dd_mm_and_ambiguity_is_flagged() -> None:
    clear = parse_document_dates(["Sample Collected: 18/11/2025; Report Date: 19/11/2025"])
    assert (clear.collected_on, clear.reported_on, clear.ambiguous) == (
        date(2025, 11, 18),
        date(2025, 11, 19),
        False,
    )
    ambiguous = parse_document_dates(["Sample Collected: 04/05/2026; Report Date: 06/05/2026"])
    assert (ambiguous.collected_on, ambiguous.ambiguous) == (date(2026, 5, 4), True)
    same_day_month = parse_document_dates(["Sample Collected: 05/05/2026"])
    assert same_day_month.ambiguous is False
    invalid = parse_document_dates(["Sample Collected: 31/02/2026"])
    assert invalid.collected_on is None
    assert parse_document_dates(["no dates here"]) == parse_document_dates([])


# Hand-labelled ground truth for every lab row in the synthetic reports.
EXPECTED_CODES = {
    "Hemoglobin": "HGB",
    "RBC Count": "RBC",
    "Hematocrit": "HCT",
    "MCV": "MCV",
    "Total WBC Count": "WBC",
    "Platelet Count": "PLT",
    "Total Bilirubin": "TBIL",
    "ALT (SGPT)": "ALT",
    "AST (SGOT)": "AST",
    "Alkaline Phosphatase": "ALP",
    "Albumin": "ALB",
    "Total Cholesterol": "CHOL",
    "LDL Cholesterol": "LDL",
    "HDL Cholesterol": "HDL",
    "Triglycerides": "TRIG",
    "HbA1c": "HBA1C",
    "Glycated Haemoglobin": "HBA1C",
    "Fasting Plasma Glucose": "GLU_FASTING",
    "Serum Creatinine": "CREAT",
    "Blood Urea": "UREA",
    "eGFR": "EGFR",
    "Uric Acid": "URIC",
    "TSH": "TSH",
    "Free T4": "FT4",
    "Free T3": "FT3",
    "HbA1c (IFCC)": "HBA1C",
}


def test_synthetic_reports_precision_and_recall(synthetic_dir: Path) -> None:
    true_positive = false_positive = false_negative = 0
    for report in _reports():
        chunks = extract_pdf((synthetic_dir / report.filename).read_bytes(), max_pages=50).chunks
        got = [(c.page, normalize_row(c.cells, c.page)) for c in chunks if c.kind == "lab_row"]
        expected = [
            (index + 1, row)
            for index, section in enumerate(report.lab_pages)
            for row in section.rows
        ]
        for (page, result), (expected_page, row) in zip(got, expected, strict=False):
            correct = (
                page == expected_page
                and result.validation_status == OK
                and result.test_code == EXPECTED_CODES[row.test]
                and result.raw_value == row.result
                and result.value == float(row.result)
            )
            true_positive += correct
            false_positive += not correct
        false_negative += max(len(expected) - len(got), 0)
        false_positive += max(len(got) - len(expected), 0)
    precision = true_positive / (true_positive + false_positive)
    recall = true_positive / (true_positive + false_negative)
    assert (precision, recall, true_positive) == (1.0, 1.0, 30)  # all 30 synthetic lab rows


def test_normalization_is_deterministic(synthetic_dir: Path) -> None:
    data = (synthetic_dir / "05_asha_lipid_mmol_2026-05-13.pdf").read_bytes()
    first = [
        normalize_row(c.cells, c.page) for c in extract_pdf(data, max_pages=50).chunks if c.cells
    ]
    second = [
        normalize_row(c.cells, c.page) for c in extract_pdf(data, max_pages=50).chunks if c.cells
    ]
    assert first == second
    assert [r.canonical_value for r in first] == [228.153, 146.946, 42.537, 185.997]
