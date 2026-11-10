"""Worker-side document pipeline: consent check → validate → mark ready/failed.

Idempotent: terminal documents are skipped, and a document left in `processing` by a crashed
attempt is processed again from scratch.
"""

import asyncio
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.storage import ObjectStorage
from app.models.document import FAILED, PROCESSING, READY, Document
from app.repositories.audit_repository import AuditRepository
from app.repositories.document_repository import DocumentRepository
from app.services.consent_service import ConsentService
from app.services.pdf_validation import PdfRejectedError, count_pages

log = structlog.get_logger(__name__)


class DocumentProcessor:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        storage: ObjectStorage,
        *,
        max_pages: int,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._storage = storage
        self._max_pages = max_pages

    async def process(self, document_id: uuid.UUID, patient_id: uuid.UUID) -> str:
        async with self._sessionmaker() as session:
            document = await DocumentRepository(session, patient_id).get(document_id)
            if document is None:
                log.warning("document.missing", document_id=str(document_id))
                return "missing"
            if document.status in (READY, FAILED):
                return document.status
            if not await ConsentService(session, patient_id).has_active_consent():
                return await self._fail(session, document, "consent_revoked")

            document.status = PROCESSING
            await session.commit()
            data = await self._storage.get(document.storage_key)
            try:
                pages = await asyncio.to_thread(count_pages, data, max_pages=self._max_pages)
            except PdfRejectedError as exc:
                return await self._fail(session, document, exc.reason)

            document.pages = pages
            document.status, document.failure_reason = READY, None
            await self._audit(session, document, "document.ready", {"pages": pages})
            await session.commit()
            log.info("document.ready", document_id=str(document.id), patient_id=str(patient_id))
            return READY

    async def mark_failed(self, document_id: uuid.UUID, patient_id: uuid.UUID, reason: str) -> None:
        async with self._sessionmaker() as session:
            document = await DocumentRepository(session, patient_id).get(document_id)
            if document is not None and document.status not in (READY, FAILED):
                await self._fail(session, document, reason)

    async def _fail(self, session: AsyncSession, document: Document, reason: str) -> str:
        document.status, document.failure_reason = FAILED, reason
        await self._audit(session, document, "document.failed", {"reason": reason})
        await session.commit()
        log.warning("document.failed", document_id=str(document.id), reason=reason)
        return FAILED

    @staticmethod
    async def _audit(
        session: AsyncSession, document: Document, action: str, details: dict[str, object]
    ) -> None:
        await AuditRepository(session).add(
            patient_id=document.patient_id,
            actor_type="system",
            action=action,
            target_id=document.id,
            details=details,
        )
