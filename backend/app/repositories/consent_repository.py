"""Consent records, scoped to one patient (patient_id is required at construction)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consent import ConsentRecord


class ConsentRepository:
    def __init__(self, session: AsyncSession, patient_id: uuid.UUID) -> None:
        self._session = session
        self._patient_id = patient_id

    async def get_active(self) -> ConsentRecord | None:
        result = await self._session.execute(
            select(ConsentRecord).where(
                ConsentRecord.patient_id == self._patient_id,
                ConsentRecord.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_latest(self) -> ConsentRecord | None:
        result = await self._session.execute(
            select(ConsentRecord)
            .where(ConsentRecord.patient_id == self._patient_id)
            .order_by(ConsentRecord.granted_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def add(self, notice_version: str) -> ConsentRecord:
        record = ConsentRecord(
            patient_id=self._patient_id,
            notice_version=notice_version,
            granted_at=datetime.now(UTC),
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def revoke(self, record: ConsentRecord) -> None:
        record.revoked_at = datetime.now(UTC)
        await self._session.flush()
