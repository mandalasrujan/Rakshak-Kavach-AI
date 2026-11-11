"""Deterministic medication extraction from prescription-table rows (no LLM).

M5 renders non-lab table rows into narrative text as "Medicine: X; Dose: Y; ...". Lines that
start with a medicine/drug header become one medication record each, values kept verbatim.
"""

import re
from dataclasses import dataclass

from app.models.chunk import NARRATIVE

_NAME_HEADERS = ("medicine", "medication", "drug", "drug name")
_HEADER_PATTERN = "|".join(re.escape(h) for h in _NAME_HEADERS)
_LINE = re.compile(rf"^(?:{_HEADER_PATTERN})\s*:", re.I)


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


def extract_medications(chunks: list) -> list[ExtractedMedication]:  # type: ignore[type-arg]
    seen: set[str] = set()
    found: list[ExtractedMedication] = []
    for index, chunk in enumerate(chunks):
        if chunk.kind != NARRATIVE:
            continue
        for line in chunk.text.split("\n"):
            line = line.strip()
            if not _LINE.match(line) or line in seen:  # chunk overlap can repeat a row
                continue
            seen.add(line)
            fields = _fields(line)
            name = next((fields[h] for h in _NAME_HEADERS if fields.get(h)), "")
            if not name:
                continue
            found.append(
                ExtractedMedication(
                    chunk_index=index,
                    page=chunk.page,
                    name=name,
                    dose=fields.get("dose") or fields.get("dosage"),
                    frequency=fields.get("frequency"),
                    duration=fields.get("duration"),
                    raw_text=line,
                )
            )
    return found
