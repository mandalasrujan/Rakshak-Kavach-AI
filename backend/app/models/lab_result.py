"""Normalized lab results (PROJECT_SPEC.md section 4: lab_results), one per lab-table row.

raw_* columns keep the source text verbatim; chunk_id/document_id/page give provenance.
"""

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LabResult(Base):
    __tablename__ = "lab_results"
    __table_args__ = (Index("ix_lab_results_patient_id_test_code", "patient_id", "test_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_name: Mapped[str] = mapped_column(Text, nullable=False)
    raw_value: Mapped[str] = mapped_column(Text, nullable=False)
    raw_unit: Mapped[str] = mapped_column(Text, nullable=False)
    raw_reference: Mapped[str] = mapped_column(Text, nullable=False)
    test_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    canonical_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    canonical_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ref_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    canonical_ref_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    canonical_ref_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    collected_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    reported_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_ambiguous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    dictionary_version: Mapped[str] = mapped_column(String(32), nullable=False)
