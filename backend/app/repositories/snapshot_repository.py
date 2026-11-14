"""Summary snapshots, scoped to one patient (patient_id is required at construction)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import any_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.snapshot import SummarySnapshot

INVALIDATED_CONTENT = {"invalidated": True, "reason": "source_document_deleted"}


class SnapshotRepository:
    def __init__(self, session: AsyncSession, patient_id: uuid.UUID) -> None:
        self._session = session
        self._patient_id = patient_id

    async def next_version(self) -> int:
        result = await self._session.execute(
            select(func.coalesce(func.max(SummarySnapshot.version), 0)).where(
                SummarySnapshot.patient_id == self._patient_id
            )
        )
        return int(result.scalar_one()) + 1

    async def add(
        self,
        *,
        version: int,
        content: dict[str, Any],
        source_document_ids: list[uuid.UUID],
        model: str,
    ) -> SummarySnapshot:
        snapshot = SummarySnapshot(
            patient_id=self._patient_id,
            version=version,
            content_json=content,
            source_document_ids=source_document_ids,
            model=model,
        )
        self._session.add(snapshot)
        await self._session.flush()
        return snapshot

    async def get(
        self, snapshot_id: uuid.UUID, *, for_update: bool = False
    ) -> SummarySnapshot | None:
        query = select(SummarySnapshot).where(
            SummarySnapshot.id == snapshot_id, SummarySnapshot.patient_id == self._patient_id
        )
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        return (await self._session.execute(query)).scalar_one_or_none()

    async def list_all(self) -> list[SummarySnapshot]:
        result = await self._session.execute(
            select(SummarySnapshot)
            .where(SummarySnapshot.patient_id == self._patient_id)
            .order_by(SummarySnapshot.version.desc())
        )
        return list(result.scalars())

    async def invalidate_citing(self, document_id: uuid.UUID) -> list[uuid.UUID]:
        """Invalidate snapshots built from a deleted document and purge their content."""
        result = await self._session.execute(
            update(SummarySnapshot)
            .where(
                SummarySnapshot.patient_id == self._patient_id,
                document_id == any_(SummarySnapshot.source_document_ids),
                SummarySnapshot.invalidated_at.is_(None),
            )
            .values(invalidated_at=datetime.now(UTC), content_json=INVALIDATED_CONTENT)
            .returning(SummarySnapshot.id)
        )
        return list(result.scalars())
