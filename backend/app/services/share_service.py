"""Patient side of doctor sharing: create (token + PIN shown once), list with access log, revoke."""

import asyncio
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.core.security import PasswordService
from app.models.share import ShareGrant
from app.repositories.audit_repository import AuditRepository
from app.repositories.share_repository import ShareRepository
from app.repositories.snapshot_repository import SnapshotRepository

log = structlog.get_logger(__name__)
TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def share_status(grant: ShareGrant, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    if grant.revoked_at is not None:
        return "revoked"
    if grant.locked_at is not None:
        return "locked"
    if grant.expires_at <= now:
        return "expired"
    return "active"


@dataclass(frozen=True)
class CreatedShare:
    grant: ShareGrant
    token: str
    pin: str
    share_url: str


class ShareService:
    def __init__(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        *,
        settings: Settings,
        passwords: PasswordService,
    ) -> None:
        self._session = session
        self._patient_id = patient_id
        self._settings = settings
        self._passwords = passwords
        self._shares = ShareRepository(session, patient_id)

    async def create(
        self, *, snapshot_id: uuid.UUID, scope: str, expires_in_minutes: int
    ) -> CreatedShare:
        snapshot = await SnapshotRepository(self._session, self._patient_id).get(snapshot_id)
        if snapshot is None:
            raise NotFoundError("Snapshot not found.")
        if snapshot.approved_at is None or snapshot.invalidated_at is not None:
            raise ConflictError("Only an approved, valid snapshot can be shared.")
        token = secrets.token_urlsafe(TOKEN_BYTES)
        pin = f"{secrets.randbelow(10**6):06d}"
        grant = await self._shares.add_grant(
            snapshot_id=snapshot.id,
            token_hash=hash_token(token),
            pin_hash=await asyncio.to_thread(self._passwords.hash, pin),
            scope=scope,
            expires_at=datetime.now(UTC) + timedelta(minutes=expires_in_minutes),
        )
        await AuditRepository(self._session).add(
            patient_id=self._patient_id,
            actor_type="patient",
            action="share.created",
            target_id=grant.id,
            details={
                "scope": scope,
                "expires_in_minutes": expires_in_minutes,
                "snapshot_version": snapshot.version,
            },
        )
        await self._session.commit()
        log.info("share.created", share_id=str(grant.id), patient_id=str(self._patient_id))
        # The token travels in the URL fragment, which browsers never send to servers.
        return CreatedShare(grant, token, pin, f"{self._settings.frontend_origin}/share#t={token}")

    async def list_with_access_log(self) -> list[dict[str, Any]]:
        grants = await self._shares.grants()
        sessions = await self._shares.sessions_for([g.id for g in grants])
        views = await self._shares.view_counts([s.id for s in sessions])
        now = datetime.now(UTC)
        return [
            {
                "id": g.id,
                "snapshot_id": g.snapshot_id,
                "scope": g.scope,
                "created_at": g.created_at,
                "expires_at": g.expires_at,
                "revoked_at": g.revoked_at,
                "locked_at": g.locked_at,
                "failed_pin_attempts": g.failed_pin_attempts,
                "status": share_status(g, now),
                "sessions": [
                    {
                        "id": s.id,
                        "declared_name": s.declared_name,
                        "declared_reg_no": s.declared_reg_no,
                        "created_at": s.created_at,
                        "expires_at": s.expires_at,
                        "ended_at": s.ended_at,
                        "views": views.get(s.id, 0),
                    }
                    for s in sessions
                    if s.share_grant_id == g.id
                ],
            }
            for g in grants
        ]

    async def revoke(self, grant_id: uuid.UUID) -> None:
        grant = await self._shares.grant(grant_id, for_update=True)
        if grant is None:
            raise NotFoundError("Share not found.")
        if grant.revoked_at is None:
            grant.revoked_at = datetime.now(UTC)
            await AuditRepository(self._session).add(
                patient_id=self._patient_id,
                actor_type="patient",
                action="share.revoked",
                target_id=grant.id,
                details={"reason": "patient_request"},
            )
            await self._session.commit()
