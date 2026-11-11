"""Deterministic lab-row normalization (M8). No LLM, no network, pure functions.

Each table row from M5 becomes one result that keeps the source text verbatim (raw_*) next to
parsed and canonical values. Anything that cannot be parsed or converted is kept with a
validation status explaining why, never silently changed or guessed.
"""

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from importlib import resources
from typing import Any

import yaml

OK = "ok"
UNKNOWN_TEST = "unknown_test"
MISSING_VALUE = "missing_value"
NON_NUMERIC_VALUE = "non_numeric_value"
CENSORED_VALUE = "censored_value"  # "<0.5", ">90": below/above a detection limit
UNKNOWN_UNIT = "unknown_unit"  # missing, unrecognised, or not convertible for this test
IMPLAUSIBLE_VALUE = "implausible_value"

_TEST_COLUMNS = frozenset({"test", "test name", "investigation", "parameter", "analyte"})
_RESULT_COLUMNS = frozenset({"result", "results", "value", "observed value"})
_UNIT_COLUMNS = frozenset({"unit", "units"})
_REFERENCE_COLUMNS = frozenset(
    {
        "reference range",
        "reference",
        "ref range",
        "ref. range",
        "normal range",
        "biological reference interval",
        "reference interval",
        "normal value",
    }
)

_PLAIN_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
_THOUSANDS_NUMBER = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
_VALUE = re.compile(r"^(?P<qualifier>[<>≤≥]=?)?\s*(?P<number>\d[\d,]*(?:\.\d+)?)\s*(?P<rest>.*)$")
_RANGE_BOTH = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|\u2013|to)\s*(\d+(?:\.\d+)?)")  # \u2013: en dash
_RANGE_UPPER = re.compile(r"^(?:<=|<|≤|up\s*to|upto|less\s+than)\s*(\d+(?:\.\d+)?)", re.I)
_RANGE_LOWER = re.compile(r"^(?:>=|>|≥|more\s+than|greater\s+than)\s*(\d+(?:\.\d+)?)", re.I)
_DATE = r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})"
_COLLECTED = re.compile(
    r"(?:sample\s+collected|collected\s+on|collection\s+date|date\s+of\s+collection)\s*:?\s*"
    + _DATE,
    re.I,
)
_REPORTED = re.compile(r"(?:report\s+date|reported\s+on|date\s+of\s+report)\s*:?\s*" + _DATE, re.I)


@dataclass(frozen=True)
class LabTest:
    code: str
    name: str
    unit: str
    conversions: dict[str, tuple[float, float]]  # unit -> (slope, intercept)
    plausible: tuple[float, float]


@dataclass(frozen=True)
class LabDictionary:
    version: str
    unit_aliases: dict[str, str]
    tests: dict[str, LabTest]
    aliases: dict[str, str]  # normalized alias -> code


@dataclass(frozen=True)
class DocumentDates:
    collected_on: date | None
    reported_on: date | None
    ambiguous: bool  # the effective date (collected, else reported) could be day/month swapped


@dataclass(frozen=True)
class NormalizedLab:
    page: int
    raw_name: str
    raw_value: str
    raw_unit: str
    raw_reference: str
    test_code: str | None
    value: float | None
    unit: str | None
    canonical_value: float | None
    canonical_unit: str | None
    ref_low: float | None
    ref_high: float | None
    canonical_ref_low: float | None
    canonical_ref_high: float | None
    validation_status: str


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().replace("*", "").strip(" :").split())


def _unit_key(unit: str) -> str:
    return unit.replace("μ", "µ").replace("³", "^3").replace(" ", "").lower()


@lru_cache
def load_dictionary() -> LabDictionary:
    data: dict[str, Any] = yaml.safe_load(
        resources.files("app.data").joinpath("lab_tests.yaml").read_text(encoding="utf-8")
    )
    tests: dict[str, LabTest] = {}
    aliases: dict[str, str] = {}
    for item in data["tests"]:
        code = str(item["code"])
        tests[code] = LabTest(
            code=code,
            name=item["name"],
            unit=item["unit"],
            conversions={u: (float(s), float(i)) for u, (s, i) in item.get("convert", {}).items()},
            plausible=(float(item["plausible"][0]), float(item["plausible"][1])),
        )
        for alias in [item["name"], *item["aliases"]]:
            key = _normalize_name(alias)
            if aliases.get(key, code) != code:
                raise ValueError(f"alias {alias!r} maps to two tests")
            aliases[key] = code
    return LabDictionary(
        version=str(data["version"]),
        unit_aliases={_unit_key(k): v for k, v in data["unit_aliases"].items()},
        tests=tests,
        aliases=aliases,
    )


def resolve_test(raw_name: str, dictionary: LabDictionary | None = None) -> str | None:
    d = dictionary or load_dictionary()
    name = _normalize_name(raw_name)
    if name in d.aliases:
        return d.aliases[name]
    without_parentheses = _normalize_name(re.sub(r"\([^)]*\)", " ", name))
    return d.aliases.get(without_parentheses)


def normalize_unit(raw_unit: str, dictionary: LabDictionary | None = None) -> str | None:
    d = dictionary or load_dictionary()
    return d.unit_aliases.get(_unit_key(raw_unit)) if raw_unit.strip() else None


def parse_number(text: str) -> float | None:
    text = text.strip()
    if _PLAIN_NUMBER.fullmatch(text):
        return float(text)
    if _THOUSANDS_NUMBER.fullmatch(text):
        return float(text.replace(",", ""))
    return None  # e.g. "12,4" (decimal comma vs thousands separator is ambiguous)


def parse_value(raw: str) -> tuple[float | None, str, str]:
    """Return (value, status, trailing text such as an inline unit)."""
    text = raw.strip()
    if not text:
        return None, MISSING_VALUE, ""
    match = _VALUE.match(text)
    if match is None:
        return None, NON_NUMERIC_VALUE, ""
    number = parse_number(match["number"])
    rest = match["rest"]
    if number is None or rest[:1] in {".", ","} or rest[:1].isdigit():
        return None, NON_NUMERIC_VALUE, ""  # e.g. "12.4.5", "1,23"
    if match["qualifier"]:
        return None, CENSORED_VALUE, rest.strip()
    return number, OK, rest.strip()


def parse_reference(raw: str) -> tuple[float | None, float | None]:
    text = raw.strip()
    if match := _RANGE_BOTH.search(text):
        return float(match[1]), float(match[2])
    if match := _RANGE_UPPER.match(text):
        return None, float(match[1])
    if match := _RANGE_LOWER.match(text):
        return float(match[1]), None
    return None, None


def _to_date(day: str, month: str, year: str) -> tuple[date | None, bool]:
    try:
        parsed = date(int(year), int(month), int(day))  # DD/MM/YYYY, explicitly
    except ValueError:
        return None, False
    ambiguous = int(day) <= 12 and int(month) <= 12 and day.lstrip("0") != month.lstrip("0")
    return parsed, ambiguous


def parse_document_dates(texts: list[str]) -> DocumentDates:
    collected = reported = None
    collected_ambiguous = reported_ambiguous = False
    for text in texts:
        if collected is None and (match := _COLLECTED.search(text)):
            collected, collected_ambiguous = _to_date(*match.groups())
        if reported is None and (match := _REPORTED.search(text)):
            reported, reported_ambiguous = _to_date(*match.groups())
    ambiguous = collected_ambiguous if collected is not None else reported_ambiguous
    return DocumentDates(collected, reported, ambiguous)


def _column(cells: dict[str, str], names: frozenset[str]) -> str:
    return next((value for header, value in cells.items() if header.lower() in names), "")


def _convert(test: LabTest, unit: str, value: float | None) -> float | None:
    if value is None:
        return None
    slope, intercept = (1.0, 0.0) if unit == test.unit else test.conversions[unit]
    return round(slope * value + intercept, 6)


def normalize_row(
    cells: tuple[tuple[str, str], ...], page: int, dictionary: LabDictionary | None = None
) -> NormalizedLab:
    d = dictionary or load_dictionary()
    by_header = dict(cells)
    raw_name = _column(by_header, _TEST_COLUMNS)
    raw_value = _column(by_header, _RESULT_COLUMNS)
    raw_unit = _column(by_header, _UNIT_COLUMNS)
    raw_reference = _column(by_header, _REFERENCE_COLUMNS)

    value, status, inline_unit = parse_value(raw_value)
    raw_unit = raw_unit or inline_unit
    unit = normalize_unit(raw_unit, d)
    ref_low, ref_high = parse_reference(raw_reference)
    code = resolve_test(raw_name, d)
    test = d.tests.get(code) if code else None

    canonical = canonical_low = canonical_high = None
    if test is None:
        status = UNKNOWN_TEST
    elif unit is None or (unit != test.unit and unit not in test.conversions):
        status = UNKNOWN_UNIT if status == OK else status
    else:
        canonical_low, canonical_high = (
            _convert(test, unit, ref_low),
            _convert(test, unit, ref_high),
        )
        if status == OK:
            canonical = _convert(test, unit, value)
            low, high = test.plausible
            if canonical is None or not low <= canonical <= high:
                status, canonical = IMPLAUSIBLE_VALUE, None

    return NormalizedLab(
        page=page,
        raw_name=raw_name,
        raw_value=raw_value,
        raw_unit=raw_unit,
        raw_reference=raw_reference,
        test_code=code,
        value=value,
        unit=unit,
        canonical_value=canonical,
        canonical_unit=test.unit if test else None,
        ref_low=ref_low,
        ref_high=ref_high,
        canonical_ref_low=canonical_low,
        canonical_ref_high=canonical_high,
        validation_status=status,
    )
