"""Share grants and doctor sessions, scoped to one patient (RLS context must be set)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.share import DoctorSession, ShareGrant


async def owner_of_share_token(session: AsyncSession, token_hash: str) -> uuid.UUID | None:
    """SECURITY DEFINER lookup (migration 0011): token hash -> owner patient_id, nothing else."""
    return (
        await session.execute(text("SELECT share_grant_owner(:h)"), {"h": token_hash})
    ).scalar_one_or_none()


async def owner_of_session_token(session: AsyncSession, token_hash: str) -> uuid.UUID | None:
    return (
        await session.execute(text("SELECT doctor_session_owner(:h)"), {"h": token_hash})
    ).scalar_one_or_none()


class ShareRepository:
    def __init__(self, session: AsyncSession, patient_id: uuid.UUID) -> None:
        self._session = session
        self._patient_id = patient_id

    async def add_grant(self, **values: object) -> ShareGrant:
        grant = ShareGrant(patient_id=self._patient_id, **values)
        self._session.add(grant)
        await self._session.flush()
        return grant

    async def grants(self) -> list[ShareGrant]:
        result = await self._session.execute(
            select(ShareGrant)
            .where(ShareGrant.patient_id == self._patient_id)
            .order_by(ShareGrant.created_at.desc(), ShareGrant.id)
        )
        return list(result.scalars())

    async def grant(self, grant_id: uuid.UUID, *, for_update: bool = False) -> ShareGrant | None:
        query = select(ShareGrant).where(
            ShareGrant.id == grant_id, ShareGrant.patient_id == self._patient_id
        )
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        return (await self._session.execute(query)).scalar_one_or_none()

    async def grant_by_token_hash(self, token_hash: str) -> ShareGrant | None:
        result = await self._session.execute(
            select(ShareGrant)
            .where(ShareGrant.patient_id == self._patient_id, ShareGrant.token_hash == token_hash)
            .with_for_update()  # serialises concurrent PIN attempts
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def revoke_active(self, *, snapshot_ids: Sequence[uuid.UUID] | None = None) -> int:
        query = update(ShareGrant).where(
            ShareGrant.patient_id == self._patient_id, ShareGrant.revoked_at.is_(None)
        )
        if snapshot_ids is not None:
            if not snapshot_ids:
                return 0
            query = query.where(ShareGrant.snapshot_id.in_(list(snapshot_ids)))
        result = await self._session.execute(query.values(revoked_at=datetime.now(UTC)))
        return result.rowcount or 0

    async def add_session(self, **values: object) -> DoctorSession:
        doctor_session = DoctorSession(patient_id=self._patient_id, **values)
        self._session.add(doctor_session)
        await self._session.flush()
        return doctor_session

    async def session_by_token_hash(self, token_hash: str) -> DoctorSession | None:
        result = await self._session.execute(
            select(DoctorSession).where(
                DoctorSession.patient_id == self._patient_id, DoctorSession.token_hash == token_hash
            )
        )
        return result.scalar_one_or_none()

    async def sessions_for(self, grant_ids: Sequence[uuid.UUID]) -> list[DoctorSession]:
        if not grant_ids:
            return []
        result = await self._session.execute(
            select(DoctorSession)
            .where(
                DoctorSession.patient_id == self._patient_id,
                DoctorSession.share_grant_id.in_(list(grant_ids)),
            )
            .order_by(DoctorSession.created_at.desc())
        )
        return list(result.scalars())

    async def view_counts(self, session_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not session_ids:
            return {}
        result = await self._session.execute(
            select(AuditLog.target_id, func.count())
            .where(
                AuditLog.patient_id == self._patient_id,
                AuditLog.action == "share.viewed",
                AuditLog.target_id.in_(list(session_ids)),
            )
            .group_by(AuditLog.target_id)
        )
        return {target: count for target, count in result}
