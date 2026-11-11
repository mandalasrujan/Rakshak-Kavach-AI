"""Deterministic previous-vs-latest lab comparison (M9). Plain Python only.

This module must never import an LLM client: every number here is computed in code.
Statuses describe position relative to each report's *own* reference range, never a
diagnosis or a treatment suggestion.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from itertools import product

IMPROVED = "improved"  # moved closer to (or into) the reference range
WORSENED = "worsened"  # moved further from the reference range
STABLE = "stable"
INSUFFICIENT_DATA = "insufficient_data"
NOT_COMPARABLE = "not_comparable"
STATUSES = frozenset({IMPROVED, WORSENED, STABLE, INSUFFICIENT_DATA, NOT_COMPARABLE})

RISING, FALLING, UNCHANGED = "rising", "falling", "unchanged"
STABLE_RELATIVE_TOLERANCE = 0.02  # |change| <= 2% of the previous value counts as unchanged
MAX_AMBIGUOUS_DATES = 8
COMPARISON_NOTE = (
    "Each value is compared with the reference range printed on its own report. "
    "This is not a diagnosis; discuss any changes with your doctor."
)


@dataclass(frozen=True)
class LabPoint:
    result_id: uuid.UUID
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    page: int
    raw_value: str
    raw_unit: str
    canonical_value: float | None
    canonical_ref_low: float | None
    canonical_ref_high: float | None
    effective_date: date | None  # collected_on, else reported_on
    date_ambiguous: bool
    validation_status: str


@dataclass(frozen=True)
class LabComparison:
    test_code: str
    test_name: str
    canonical_unit: str
    status: str
    reason: str
    direction: str | None
    change: float | None
    percent_change: float | None
    latest: LabPoint | None
    previous: LabPoint | None
    history: tuple[LabPoint, ...]
    note: str = COMPARISON_NOTE


def _sort_key(point: LabPoint, when: date) -> tuple[date, str]:
    return when, str(point.result_id)


def _swapped(day_month: date) -> date | None:
    try:
        return date(day_month.year, day_month.day, day_month.month)
    except ValueError:
        return None


def _order_is_certain(points: list[LabPoint]) -> bool:
    """True if every day/month reading of ambiguous dates gives the same latest two results."""
    options = [
        [p.effective_date, *([s] if p.date_ambiguous and (s := _swapped(p.effective_date)) else [])]
        for p in points
    ]
    if sum(len(o) > 1 for o in options) > MAX_AMBIGUOUS_DATES:
        return False
    outcomes = set()
    for dates in product(*options):
        ranked = sorted(zip(points, dates, strict=True), key=lambda pd: _sort_key(pd[0], pd[1]))
        outcomes.add((ranked[-1][0].result_id, ranked[-2][0].result_id))
    return len(outcomes) == 1


def _distance(point: LabPoint) -> float:
    value = point.canonical_value or 0.0
    low, high = point.canonical_ref_low, point.canonical_ref_high
    if low is not None and value < low:
        return round(low - value, 6)
    if high is not None and value > high:
        return round(value - high, 6)
    return 0.0


def _has_range(point: LabPoint) -> bool:
    return point.canonical_ref_low is not None or point.canonical_ref_high is not None


def compare(
    test_code: str, test_name: str, canonical_unit: str, points: Sequence[LabPoint]
) -> LabComparison:
    usable = [
        p
        for p in points
        if p.validation_status == "ok" and p.canonical_value is not None and p.effective_date
    ]
    history = tuple(sorted(usable, key=lambda p: _sort_key(p, p.effective_date)))  # type: ignore[arg-type]

    def result(status: str, reason: str, **fields: object) -> LabComparison:
        defaults: dict[str, object] = {
            "direction": None,
            "change": None,
            "percent_change": None,
            "latest": history[-1] if history else None,
            "previous": history[-2] if len(history) > 1 else None,
        }
        return LabComparison(
            test_code,
            test_name,
            canonical_unit,
            status,
            reason,
            history=history,
            **{**defaults, **fields},  # type: ignore[arg-type]
        )

    if len(history) < 2:
        excluded = {p.validation_status for p in points if p not in usable}
        if "unknown_unit" in excluded:
            return result(NOT_COMPARABLE, "incompatible_units")
        if any(p.effective_date is None for p in points if p.validation_status == "ok"):
            return result(INSUFFICIENT_DATA, "missing_date")
        return result(INSUFFICIENT_DATA, "missing_value" if excluded else "single_result")

    latest, previous = history[-1], history[-2]
    if not _order_is_certain(list(history)):
        return result(NOT_COMPARABLE, "ambiguous_date_order")
    if latest.effective_date == previous.effective_date:
        return result(NOT_COMPARABLE, "same_date")

    old, new = previous.canonical_value, latest.canonical_value
    if old is None or new is None:  # unreachable: `usable` requires values; kept for typing
        return result(INSUFFICIENT_DATA, "missing_value")
    change = round(new - old, 6)
    percent = round(change / abs(old) * 100, 2) if old else None
    if abs(change) <= abs(old) * STABLE_RELATIVE_TOLERANCE:
        return result(
            STABLE, "within_tolerance", direction=UNCHANGED, change=change, percent_change=percent
        )
    direction = RISING if change > 0 else FALLING
    fields = {"direction": direction, "change": change, "percent_change": percent}
    if not (_has_range(latest) and _has_range(previous)):
        return result(INSUFFICIENT_DATA, "no_reference_range", **fields)
    before, after = _distance(previous), _distance(latest)
    if after < before:
        return result(IMPROVED, "closer_to_reference_range", **fields)
    if after > before:
        return result(WORSENED, "further_from_reference_range", **fields)
    return result(STABLE, "within_reference_range", **fields)
