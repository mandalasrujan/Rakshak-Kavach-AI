"""Grant, revoke and check consent for one patient. Every change is audited atomically."""

import uuid
from dataclasses import dataclass
from datetime import datetime

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import consent_notice
from app.core.errors import ConsentNoticeOutdatedError, ConsentRequiredError
from app.repositories.audit_repository import AuditRepository
from app.repositories.consent_repository import ConsentRepository
from app.repositories.share_repository import ShareRepository

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ConsentStatus:
    notice_version: str
    notice_text: str
    granted: bool
    granted_notice_version: str | None
    granted_at: datetime | None
    revoked_at: datetime | None


class ConsentService:
    def __init__(self, session: AsyncSession, patient_id: uuid.UUID) -> None:
        self._session = session
        self._patient_id = patient_id
        self._consents = ConsentRepository(session, patient_id)
        self._audit = AuditRepository(session)

    async def has_active_consent(self) -> bool:
        """True only for an unrevoked consent to the *current* notice version."""
        active = await self._consents.get_active()
        return active is not None and active.notice_version == consent_notice.CONSENT_NOTICE_VERSION

    async def ensure_granted(self) -> None:
        if not await self.has_active_consent():
            raise ConsentRequiredError()

    async def status(self) -> ConsentStatus:
        latest = await self._consents.get_latest()
        return ConsentStatus(
            notice_version=consent_notice.CONSENT_NOTICE_VERSION,
            notice_text=consent_notice.CONSENT_NOTICE_TEXT,
            granted=await self.has_active_consent(),
            granted_notice_version=latest.notice_version if latest else None,
            granted_at=latest.granted_at if latest else None,
            revoked_at=latest.revoked_at if latest else None,
        )

    async def grant(self, notice_version: str) -> ConsentStatus:
        if notice_version != consent_notice.CONSENT_NOTICE_VERSION:
            raise ConsentNoticeOutdatedError()
        active = await self._consents.get_active()
        if active is not None and active.notice_version == notice_version:
            return await self.status()  # idempotent
        try:
            if active is not None:  # consent to an older notice is replaced
                await self._consents.revoke(active)
            record = await self._consents.add(notice_version)
            await self._audit.add(
                patient_id=self._patient_id,
                actor_type="patient",
                action="consent.granted",
                target_id=record.id,
                details={"notice_version": notice_version},
            )
            await self._session.commit()
        except IntegrityError:  # concurrent grant: the other request won
            await self._session.rollback()
            return await self.status()
        log.info("consent.granted", patient_id=str(self._patient_id), notice_version=notice_version)
        return await self.status()

    async def revoke(self) -> ConsentStatus:
        """Revoke consent: uploads and chat stop immediately and all active shares are revoked."""
        active = await self._consents.get_active()
        if active is None:
            return await self.status()  # idempotent
        await self._consents.revoke(active)
        revoked_shares = await ShareRepository(self._session, self._patient_id).revoke_active()
        await self._audit.add(
            patient_id=self._patient_id,
            actor_type="patient",
            action="consent.revoked",
            target_id=active.id,
            details={"notice_version": active.notice_version, "shares_revoked": revoked_shares},
        )
        await self._session.commit()
        log.info("consent.revoked", patient_id=str(self._patient_id))
        return await self.status()
