"""Snapshot content schema (validated before storage) and API shapes."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SNAPSHOT_SCHEMA_VERSION = 1


class SourceRef(BaseModel):
    document_id: uuid.UUID
    page: int
    chunk_id: uuid.UUID
    excerpt: str


class SnapshotMedication(BaseModel):
    name: str
    dose: str | None
    frequency: str | None
    duration: str | None
    start_date: date | None
    source: SourceRef


class SnapshotLabPoint(BaseModel):
    raw_value: str
    raw_unit: str
    canonical_value: float | None
    date: date | None
    date_ambiguous: bool
    source: SourceRef


class SnapshotLab(BaseModel):
    test_code: str
    test_name: str
    canonical_unit: str
    status: str
    reason: str
    direction: str | None
    change: float | None
    percent_change: float | None
    latest: SnapshotLabPoint | None
    previous: SnapshotLabPoint | None


class SnapshotDocument(BaseModel):
    document_id: uuid.UUID
    uploaded_at: datetime
    pages: int | None


class SnapshotNarrative(BaseModel):
    """Optional AI-written summary; always labelled, grounded and guard-checked."""

    status: Literal["ok", "empty", "blocked", "unavailable"]
    ai_generated: Literal[True] = True
    text: str | None = None
    citations: list[SourceRef] = Field(default_factory=list)


class SnapshotContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = SNAPSHOT_SCHEMA_VERSION
    medications: list[SnapshotMedication]
    labs: list[SnapshotLab]
    documents: list[SnapshotDocument]
    missing: dict[str, str]  # section -> explicit "not found in your records" statement
    narrative: SnapshotNarrative
    note: str


class SnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    model: str
    generated_at: datetime
    approved_at: datetime | None
    invalidated_at: datetime | None
    source_document_ids: list[uuid.UUID]
    content_json: dict  # type: ignore[type-arg]


class SnapshotList(BaseModel):
    items: list[SnapshotRead]
