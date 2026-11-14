"""Doctor sharing (PROJECT_SPEC.md section 4: share_grants, doctor_sessions)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SUMMARY_ONLY = "summary_only"
FULL_RECORDS = "full_records"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ShareGrant(Base):
    __tablename__ = "share_grants"
    __table_args__ = (CheckConstraint("scope IN ('summary_only', 'full_records')", name="scope"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("summary_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)  # SHA-256
    pin_hash: Mapped[str] = mapped_column(Text, nullable=False)  # argon2id
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_pin_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DoctorSession(Base):
    __tablename__ = "doctor_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    share_grant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("share_grants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)  # SHA-256
    declared_name: Mapped[str | None] = mapped_column(String(120), nullable=True)  # unverified
    declared_reg_no: Mapped[str | None] = mapped_column(String(60), nullable=True)  # unverified
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
