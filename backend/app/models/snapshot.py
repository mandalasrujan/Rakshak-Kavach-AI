"""Summary snapshots (PROJECT_SPEC.md section 4: summary_snapshots).

Every generation is a new version; approved snapshots are never edited. Deleting a source
document invalidates the snapshot and purges its content (M12/M13).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ARRAY, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SummarySnapshot(Base):
    __tablename__ = "summary_snapshots"
    __table_args__ = (
        UniqueConstraint("patient_id", "version", name="uq_summary_snapshots_patient_id_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_document_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
