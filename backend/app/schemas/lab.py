import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class LabResultRead(BaseModel):
    """A normalized result with its verbatim source values and provenance."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_id: uuid.UUID
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
    collected_on: date | None
    reported_on: date | None
    date_ambiguous: bool
    validation_status: str
    dictionary_version: str


class LabResultList(BaseModel):
    items: list[LabResultRead]
    total: int
    limit: int
    offset: int


class LabPointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    result_id: uuid.UUID
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    page: int
    raw_value: str
    raw_unit: str
    canonical_value: float | None
    canonical_ref_low: float | None
    canonical_ref_high: float | None
    effective_date: date | None
    date_ambiguous: bool


class LabTrendRead(BaseModel):
    """Deterministic comparison of the latest and previous results (computed in Python)."""

    model_config = ConfigDict(from_attributes=True)

    test_code: str
    test_name: str
    canonical_unit: str
    status: str
    reason: str
    direction: str | None
    change: float | None
    percent_change: float | None
    latest: LabPointRead | None
    previous: LabPointRead | None
    history: list[LabPointRead]


class LabTrendList(BaseModel):
    items: list[LabTrendRead]
    note: str
