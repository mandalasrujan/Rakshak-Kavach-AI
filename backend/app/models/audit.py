"""Append-only audit log (PROJECT_SPEC.md section 4: audit_log). IDs and metadata only, no PHI.

No foreign key to patients: audit rows must outlive the records they describe. A database
trigger (migration 0002) rejects UPDATE and DELETE.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ACTOR_TYPES = ("patient", "doctor", "system")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint("actor_type IN ('patient', 'doctor', 'system')", name="actor_type"),
        Index("ix_audit_log_patient_id_created_at", "patient_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # Attribute is `details` because `metadata` is reserved on declarative models.
    details: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
