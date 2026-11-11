"""M9: deterministic comparison logic (pure Python, no database, no LLM)."""

import ast
import random
import uuid
from datetime import date
from pathlib import Path

import pytest

from app.services import lab_comparison
from app.services.lab_comparison import (
    COMPARISON_NOTE,
    FALLING,
    IMPROVED,
    INSUFFICIENT_DATA,
    NOT_COMPARABLE,
    RISING,
    STABLE,
    STATUSES,
    UNCHANGED,
    WORSENED,
    LabPoint,
    compare,
)


def point(value, when, *, low=None, high=None, status="ok", ambiguous=False, raw=None):  # type: ignore[no-untyped-def]
    return LabPoint(
        result_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        page=1,
        raw_value=raw if raw is not None else str(value),
        raw_unit="%",
        canonical_value=value if status == "ok" else None,
        canonical_ref_low=low,
        canonical_ref_high=high,
        effective_date=when,
        date_ambiguous=ambiguous,
        validation_status=status,
    )


def hba1c(*points):  # type: ignore[no-untyped-def]
    return compare("HBA1C", "HbA1c", "%", points)


def test_same_test_two_dates_rising_away_from_range_is_worsened() -> None:
    before, after = (
        point(7.1, date(2025, 11, 18), high=5.6),
        point(7.6, date(2026, 5, 13), high=5.6),
    )
    result = hba1c(after, before)
    assert (result.status, result.reason, result.direction) == (
        WORSENED,
        "further_from_reference_range",
        RISING,
    )
    assert (result.change, result.percent_change) == (0.5, 7.04)
    assert (result.latest, result.previous) == (after, before)  # provenance kept on both points


def test_falling_toward_range_is_improved() -> None:
    result = hba1c(point(7.6, date(2026, 1, 1), high=5.6), point(6.8, date(2026, 4, 1), high=5.6))
    assert (result.status, result.direction, result.change) == (IMPROVED, FALLING, -0.8)


def test_small_change_is_stable_and_unchanged() -> None:
    result = compare(
        "CHOL",
        "Total Cholesterol",
        "mg/dL",
        [
            point(200.0, date(2026, 1, 1), high=200),
            point(203.0, date(2026, 3, 1), high=200),
        ],
    )
    assert (result.status, result.reason, result.direction) == (
        STABLE,
        "within_tolerance",
        UNCHANGED,
    )


def test_change_inside_the_range_is_stable() -> None:
    result = compare(
        "HGB",
        "Hemoglobin",
        "g/dL",
        [
            point(12.5, date(2026, 1, 1), low=12, high=15.5),
            point(14.5, date(2026, 3, 1), low=12, high=15.5),
        ],
    )
    assert (result.status, result.reason, result.direction) == (
        STABLE,
        "within_reference_range",
        RISING,
    )


def test_multiple_history_compares_latest_two_and_orders_history() -> None:
    oldest = point(6.5, date(2025, 1, 1), high=5.6)
    middle = point(7.4, date(2025, 6, 1), high=5.6)
    newest = point(7.0, date(2026, 1, 1), high=5.6)
    result = hba1c(newest, oldest, middle)
    assert result.history == (oldest, middle, newest)
    assert (result.previous, result.latest, result.status) == (middle, newest, IMPROVED)


@pytest.mark.parametrize(
    ("points", "status", "reason"),
    [
        ([point(7.1, date(2026, 1, 1))], INSUFFICIENT_DATA, "single_result"),
        (
            [point(7.1, date(2026, 1, 1)), point(None, date(2026, 2, 1), status="missing_value")],
            INSUFFICIENT_DATA,
            "missing_value",
        ),
        (
            [point(7.1, date(2026, 1, 1)), point(None, date(2026, 2, 1), status="unknown_unit")],
            NOT_COMPARABLE,
            "incompatible_units",
        ),
        ([point(7.1, date(2026, 1, 1)), point(7.5, None)], INSUFFICIENT_DATA, "missing_date"),
        ([point(7.1, date(2026, 1, 1)), point(7.5, date(2026, 1, 1))], NOT_COMPARABLE, "same_date"),
        ([], INSUFFICIENT_DATA, "single_result"),
    ],
    ids=["single", "missing-value", "incompatible-units", "missing-date", "same-date", "none"],
)
def test_unusable_histories_are_never_compared(points, status: str, reason: str) -> None:  # type: ignore[no-untyped-def]
    result = hba1c(*points)
    assert (result.status, result.reason, result.change, result.direction) == (
        status,
        reason,
        None,
        None,
    )


def test_missing_reference_range_reports_direction_but_no_judgement() -> None:
    result = hba1c(point(7.1, date(2026, 1, 1)), point(7.6, date(2026, 3, 1)))
    assert (result.status, result.reason, result.direction, result.change) == (
        INSUFFICIENT_DATA,
        "no_reference_range",
        RISING,
        0.5,
    )


def test_ambiguous_dates_that_could_flip_order_are_not_compared() -> None:
    # 04/05/2026 could be 4 May or 5 April; the other result is 20 April -> order uncertain.
    flip = hba1c(
        point(7.0, date(2026, 5, 4), high=5.6, ambiguous=True),
        point(7.5, date(2026, 4, 20), high=5.6),
    )
    assert (flip.status, flip.reason) == (NOT_COMPARABLE, "ambiguous_date_order")
    # Same ambiguity against a November 2025 result: either reading is later -> comparable.
    safe = hba1c(
        point(7.0, date(2026, 5, 4), high=5.6, ambiguous=True),
        point(7.5, date(2025, 11, 18), high=5.6),
    )
    assert safe.status == IMPROVED


def test_comparison_is_deterministic_regardless_of_input_order() -> None:
    points = [
        point(v, date(2025, m, 1), low=4, high=5.6)
        for v, m in [(6.1, 1), (5.9, 3), (7.2, 7), (6.4, 9)]
    ]
    expected = hba1c(*points)
    for seed in range(5):
        shuffled = points[:]
        random.Random(seed).shuffle(shuffled)  # noqa: S311 (test ordering, not crypto)
        assert hba1c(*shuffled) == expected
    assert expected.change == round(6.4 - 7.2, 6) and expected.percent_change == -11.11


def test_zero_previous_value_has_no_percent_change() -> None:
    result = compare(
        "EOS_PCT",
        "Eosinophils",
        "%",
        [point(0.0, date(2026, 1, 1), high=6), point(2.0, date(2026, 2, 1), high=6)],
    )
    assert result.percent_change is None and result.change == 2.0


def test_module_has_no_llm_or_network_imports() -> None:
    tree = ast.parse(Path(lab_comparison.__file__).read_text())
    imported = {
        name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for name in (
            [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
        )
    }
    assert imported <= {"uuid", "collections.abc", "dataclasses", "datetime", "itertools"}


def test_outputs_make_no_diagnostic_or_treatment_claims() -> None:
    forbidden = ("diagnos", "diabet", "disease", "treat", "medicat", "prescri", "dose", "risk of")
    assert "not a diagnosis" in COMPARISON_NOTE and "doctor" in COMPARISON_NOTE
    cases = [
        hba1c(point(7.1, date(2025, 1, 1), high=5.6), point(9.6, date(2026, 1, 1), high=5.6)),
        hba1c(point(9.6, date(2025, 1, 1), high=5.6), point(5.0, date(2026, 1, 1), high=5.6)),
        hba1c(point(7.1, date(2025, 1, 1))),
    ]
    for result in cases:
        assert result.status in STATUSES
        text = f"{result.status} {result.reason} {result.note}".lower().replace(
            "not a diagnosis", ""
        )
        assert not any(word in text for word in forbidden)
