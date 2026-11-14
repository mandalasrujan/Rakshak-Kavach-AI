"""Doctor side of sharing (M14). Deliberately isolated from every patient service.

1. `start_session`: token (from the URL fragment) + 6-digit PIN → 30-minute doctor session.
   Unknown, expired, revoked or locked shares all get the same generic 401. Wrong PINs are
   counted under a row lock; the 5th failure locks the share permanently.
2. `view`: read-only, returns only the approved snapshot, cut down to the share's scope.
3. `end_session`.
Pre-auth lookups go through SECURITY DEFINER functions that map a token hash to its owner;
everything after that runs under the owner's RLS context. Tokens, PINs and content are never
logged; audit rows carry IDs and reason codes only.
"""

import asyncio
import copy
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    InvalidPinError,
    RateLimitedError,
    ServiceUnavailableError,
    ShareUnavailableError,
)
from app.core.security import PasswordService
from app.db.patient_context import set_patient_context
from app.models.share import FULL_RECORDS, ShareGrant
from app.repositories.audit_repository import AuditRepository
from app.repositories.share_repository import (
    ShareRepository,
    owner_of_session_token,
    owner_of_share_token,
)
from app.repositories.snapshot_repository import SnapshotRepository
from app.services.rate_limiter import RateLimiter
from app.services.share_service import hash_token, share_status

log = structlog.get_logger(__name__)
SESSION_TOKEN_BYTES = 32


@dataclass(frozen=True)
class DoctorSessionToken:
    token: str
    expires_at: datetime
    scope: str


def scoped_view(content: dict[str, Any], scope: str) -> dict[str, Any]:
    """summary_only: values without sources or the document list; full_records: everything."""
    view = copy.deepcopy(content)
    if scope == FULL_RECORDS:
        return view
    view.pop("documents", None)
    view["narrative"]["citations"] = []
    for medication in view["medications"]:
        medication.pop("source", None)
    for lab in view["labs"]:
        for key in ("latest", "previous"):
            if lab.get(key):
                lab[key].pop("source", None)
    return view


class ShareAccessService:
    def __init__(
        self, session: AsyncSession, *, redis: Redis, settings: Settings, passwords: PasswordService
    ) -> None:
        self._session = session  # unbound until a token resolves to an owner
        self._limiter = RateLimiter(redis)
        self._settings = settings
        self._passwords = passwords

    async def _rate_limit(self, client_ip: str) -> None:
        try:
            result = await self._limiter.hit(
                f"rl:share:ip:{client_ip}",
                limit=self._settings.share_exchange_max_per_ip,
                window_seconds=self._settings.share_exchange_window_seconds,
            )
        except RedisError as exc:
            raise ServiceUnavailableError() from exc
        if not result.allowed:
            raise RateLimitedError(headers={"Retry-After": str(result.retry_after_seconds)})

    async def _deny(self, grant: ShareGrant, reason: str) -> None:
        await AuditRepository(self._session).add(
            patient_id=grant.patient_id,
            actor_type="doctor",
            action="share.access_denied",
            target_id=grant.id,
            details={"reason": reason},
        )
        await self._session.commit()
        log.warning("share.access_denied", share_id=str(grant.id), reason=reason)

    async def start_session(
        self,
        *,
        token: str,
        pin: str,
        declared_name: str | None,
        declared_reg_no: str | None,
        client_ip: str,
    ) -> DoctorSessionToken:
        await self._rate_limit(client_ip)
        token_hash = hash_token(token)
        owner = await owner_of_share_token(self._session, token_hash)
        if owner is None:
            log.warning("share.access_denied", reason="unknown_token")
            raise ShareUnavailableError()
        await set_patient_context(self._session, owner)
        shares = ShareRepository(self._session, owner)
        grant = await shares.grant_by_token_hash(token_hash)  # row lock
        if grant is None:
            raise ShareUnavailableError()
        status = share_status(grant)
        if status != "active":
            await self._deny(grant, status)
            raise ShareUnavailableError()

        if not await asyncio.to_thread(self._passwords.verify, grant.pin_hash, pin):
            grant.failed_pin_attempts += 1
            audit = AuditRepository(self._session)
            await audit.add(
                patient_id=owner,
                actor_type="doctor",
                action="share.pin_failed",
                target_id=grant.id,
                details={"attempt": grant.failed_pin_attempts},
            )
            if grant.failed_pin_attempts >= self._settings.share_pin_max_attempts:
                grant.locked_at = datetime.now(UTC)
                await audit.add(
                    patient_id=owner, actor_type="doctor", action="share.locked", target_id=grant.id
                )
                log.warning("share.locked", share_id=str(grant.id))
            await self._session.commit()
            raise InvalidPinError()

        session_token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        expires_at = min(
            datetime.now(UTC) + timedelta(minutes=self._settings.doctor_session_minutes),
            grant.expires_at,
        )
        doctor_session = await shares.add_session(
            share_grant_id=grant.id,
            token_hash=hash_token(session_token),
            declared_name=(declared_name or "").strip()[:120] or None,
            declared_reg_no=(declared_reg_no or "").strip()[:60] or None,
            expires_at=expires_at,
        )
        await AuditRepository(self._session).add(
            patient_id=owner,
            actor_type="doctor",
            action="share.session_started",
            target_id=doctor_session.id,
            details={"share_id": str(grant.id), "scope": grant.scope},
        )
        await self._session.commit()
        log.info("share.session_started", share_id=str(grant.id), session_id=str(doctor_session.id))
        return DoctorSessionToken(session_token, expires_at, grant.scope)

    async def _active_session(self, session_token: str | None):  # type: ignore[no-untyped-def]
        if not session_token:
            raise ShareUnavailableError()
        token_hash = hash_token(session_token)
        owner = await owner_of_session_token(self._session, token_hash)
        if owner is None:
            raise ShareUnavailableError()
        await set_patient_context(self._session, owner)
        shares = ShareRepository(self._session, owner)
        doctor_session = await shares.session_by_token_hash(token_hash)
        grant = await shares.grant(doctor_session.share_grant_id) if doctor_session else None
        now = datetime.now(UTC)
        if (
            doctor_session is None
            or grant is None
            or doctor_session.ended_at is not None
            or doctor_session.expires_at <= now
            or share_status(grant, now) != "active"
        ):
            raise ShareUnavailableError()
        return owner, doctor_session, grant

    async def view(self, session_token: str | None) -> dict[str, Any]:
        owner, doctor_session, grant = await self._active_session(session_token)
        snapshot = await SnapshotRepository(self._session, owner).get(grant.snapshot_id)
        if snapshot is None or snapshot.approved_at is None or snapshot.invalidated_at is not None:
            raise ShareUnavailableError()
        await AuditRepository(self._session).add(
            patient_id=owner,
            actor_type="doctor",
            action="share.viewed",
            target_id=doctor_session.id,
            details={"share_id": str(grant.id), "scope": grant.scope},
        )
        await self._session.commit()
        return {
            "scope": grant.scope,
            "session_expires_at": doctor_session.expires_at,
            "snapshot_version": snapshot.version,
            "approved_at": snapshot.approved_at,
            "summary": scoped_view(snapshot.content_json, grant.scope),
        }

    async def end_session(self, session_token: str | None) -> None:
        try:
            _, doctor_session, _ = await self._active_session(session_token)
        except ShareUnavailableError:
            return  # idempotent
        doctor_session.ended_at = datetime.now(UTC)
        await self._session.commit()
