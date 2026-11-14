"""Deterministic medication extraction from prescription-table rows and bullet items (no LLM).

M5 renders non-lab table rows into narrative text as "Medicine: X; Dose: Y; ...". Lines that
contain a medicine/drug header or narrative prescription bullet become one medication record each.
Values are normalized and kept verbatim.
"""

import re
from dataclasses import dataclass

from app.models.chunk import NARRATIVE

_NAME_HEADERS = (
    "medicine",
    "medication",
    "drug",
    "drug name",
    "medicine name",
    "medication name",
    "prescribed medication",
    "prescription",
    "item name",
    "rx",
)
_DOSE_HEADERS = ("dose", "dosage", "strength")
_FREQ_HEADERS = ("frequency", "regimen", "timing", "schedule")
_INSTR_HEADERS = ("instructions", "directions", "sig", "advice", "special instructions")
_DURATION_HEADERS = ("duration", "days", "period")

_DOSE_REGEX = re.compile(
    r"^(?P<name>.+?)\s+(?P<dose>\d+(?:\.\d+)?\s*(?:mg|mcg|µg|ug|g|iu|ml|tablets?|capsules?|pills?|drops?|units?|meq|puffs?|sachets?)(?:/\w+)?)\b\s*$",
    re.I,
)

_BULLET_PREFIX = re.compile(r"^[-*•\u2013\u2014]\s+|\d+[.)]\s+", re.I)
_SEPARATORS = re.compile(r"\s*(?:\u2014|\u2013|--|\s-\s|:\s*|·|\u00b7)\s*")
_MED_FORM_OR_UNIT = re.compile(
    r"\b(?:\d+(?:\.\d+)?\s*(?:mg|mcg|µg|ug|g|iu|ml|tablets?|capsules?|units?|meq)|tab(?:let)?|cap(?:sule)?|syr(?:up)?|inj(?:ection)?|drops?|ointment|gel|solution)\b",
    re.I,
)


@dataclass(frozen=True)
class ExtractedMedication:
    chunk_index: int
    page: int
    name: str
    dose: str | None
    frequency: str | None
    duration: str | None
    raw_text: str


def _fields(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in line.split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            fields[key.strip().lower()] = " ".join(value.split())
    return fields


def _parse_bullet_line(line: str) -> tuple[str, str | None, str | None, str | None] | None:
    """Parse narrative prescription items like '- Metformin 500 mg — twice daily with meals.'"""
    if not _BULLET_PREFIX.match(line) and not line.lower().startswith("rx:"):
        return None

    if line.lower().startswith("rx:"):
        content = line[3:].strip()
    else:
        content = _BULLET_PREFIX.sub("", line).strip()

    if not content:
        return None

    parts = _SEPARATORS.split(content, maxsplit=2)
    med_candidate = parts[0].strip()

    # Must contain a dose unit, drug formulation or form to avoid capturing general narrative advice
    if not _MED_FORM_OR_UNIT.search(med_candidate) and not _MED_FORM_OR_UNIT.search(content):
        return None

    freq_candidate = parts[1].strip().rstrip(".") if len(parts) >= 2 else None
    dur_candidate = parts[2].strip().rstrip(".") if len(parts) > 2 else None

    # Check if duration is specified inside the frequency text (e.g. 'for 90 days')
    if not dur_candidate and freq_candidate:
        dur_match = re.search(r"\bfor\s+(\d+\s*(?:days?|weeks?|months?))\b", freq_candidate, re.I)
        if dur_match:
            dur_candidate = dur_match.group(1)

    # Extract dose if embedded in med_candidate
    dose_match = _DOSE_REGEX.match(med_candidate)
    if dose_match:
        name = dose_match.group("name").strip()
        dose = dose_match.group("dose").strip()
    else:
        name = med_candidate
        dose = None

    return name, dose, freq_candidate, dur_candidate


def extract_medications(chunks: list) -> list[ExtractedMedication]:  # type: ignore[type-arg]
    # Track (page, name_lower, dose_lower, freq_lower, dur_lower) to prevent genuine duplicate
    # extractions within the same page / visit caused by chunk text overlap
    seen_dedup: set[tuple[int, str, str, str, str]] = set()
    found: list[ExtractedMedication] = []

    for index, chunk in enumerate(chunks):
        if chunk.kind != NARRATIVE:
            continue

        raw_lines = chunk.text.split("\n")
        expanded_lines: list[str] = []
        for rl in raw_lines:
            parts = re.split(
                r"(?=(?:^|\s+)[-*•]\s+|\b\d+[.)]\s+|\b(?:medicine|medication|drug|rx):\s*)",
                rl,
                flags=re.I,
            )
            expanded_lines.extend(parts)

        for line in expanded_lines:
            line = line.strip()
            if not line:
                continue

            fields = _fields(line)
            name_key = next((h for h in _NAME_HEADERS if fields.get(h)), None)

            if name_key:
                raw_name = fields[name_key]
                dose = next((fields[h] for h in _DOSE_HEADERS if fields.get(h)), None)
                frequency = next((fields[h] for h in _FREQ_HEADERS if fields.get(h)), None)
                instructions = next((fields[h] for h in _INSTR_HEADERS if fields.get(h)), None)
                duration = next((fields[h] for h in _DURATION_HEADERS if fields.get(h)), None)

                if instructions:
                    if frequency:
                        if instructions.lower() not in frequency.lower():
                            frequency = f"{frequency} ({instructions})"
                    else:
                        frequency = instructions

                # If dose was not in a separate column, check if embedded in the name
                if dose is None and (m := _DOSE_REGEX.match(raw_name)):
                    name = m.group("name").strip()
                    dose = m.group("dose").strip()
                else:
                    name = raw_name

            else:
                bullet_parsed = _parse_bullet_line(line)
                if not bullet_parsed:
                    continue
                name, dose, frequency, duration = bullet_parsed

            if not name:
                continue

            dedup_key = (
                chunk.page,
                name.lower().strip(),
                (dose or "").lower().strip(),
                (frequency or "").lower().strip(),
                (duration or "").lower().strip(),
            )
            if dedup_key in seen_dedup:
                continue
            seen_dedup.add(dedup_key)

            found.append(
                ExtractedMedication(
                    chunk_index=index,
                    page=chunk.page,
                    name=name,
                    dose=dose,
                    frequency=frequency,
                    duration=duration,
                    raw_text=line,
                )
            )
    return found
