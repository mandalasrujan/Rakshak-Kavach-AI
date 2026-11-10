"""Patient-facing document operations: upload (202 + queue), list, get."""

import hashlib
import uuid
from dataclasses import dataclass

import structlog
from arq.connections import ArqRedis
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ServiceUnavailableError, UnsupportedFileTypeError
from app.core.storage import ObjectStorage
from app.models.document import FAILED, QUEUED, Document
from app.repositories.audit_repository import AuditRepository
from app.repositories.document_repository import DocumentRepository
from app.services.pdf_validation import PDF_MAGIC

log = structlog.get_logger(__name__)

PROCESS_DOCUMENT_JOB = "process_document"


@dataclass(frozen=True)
class UploadResult:
    document: Document
    accepted: bool  # True: newly queued (202). False: existing duplicate returned (200).


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        *,
        storage: ObjectStorage,
        queue: ArqRedis,
    ) -> None:
        self._session = session
        self._patient_id = patient_id
        self._documents = DocumentRepository(session, patient_id)
        self._audit = AuditRepository(session)
        self._storage = storage
        self._queue = queue

    async def upload(self, data: bytes) -> UploadResult:
        if not data.startswith(PDF_MAGIC):  # magic bytes, not the client's content type
            raise UnsupportedFileTypeError()
        file_hash = hashlib.sha256(data).hexdigest()

        existing = await self._documents.get_by_hash(file_hash)
        if existing is not None:
            if existing.status != FAILED:
                return UploadResult(existing, accepted=False)
            existing.status, existing.failure_reason = QUEUED, None
            await self._record(existing, "document.requeued")
            await self._enqueue(existing)
            return UploadResult(existing, accepted=True)

        storage_key = f"patients/{self._patient_id}/{uuid.uuid4().hex}.pdf"
        await self._storage.put(storage_key, data)
        try:
            document = await self._documents.add(storage_key=storage_key, file_hash=file_hash)
            await self._record(document, "document.uploaded", {"size_bytes": len(data)})
        except IntegrityError:  # concurrent upload of the same file won the race
            await self._session.rollback()
            await self._storage.delete(storage_key)
            winner = await self._documents.get_by_hash(file_hash)
            if winner is None:
                raise
            return UploadResult(winner, accepted=False)
        await self._enqueue(document)
        return UploadResult(document, accepted=True)

    async def _record(
        self, document: Document, action: str, details: dict[str, int] | None = None
    ) -> None:
        await self._audit.add(
            patient_id=self._patient_id,
            actor_type="patient",
            action=action,
            target_id=document.id,
            details=details,
        )
        await self._session.commit()

    async def _enqueue(self, document: Document) -> None:
        try:
            await self._queue.enqueue_job(
                PROCESS_DOCUMENT_JOB,
                str(document.id),
                str(self._patient_id),
                _job_id=f"{PROCESS_DOCUMENT_JOB}:{document.id}:{uuid.uuid4().hex[:12]}",
            )
        except RedisError as exc:
            document.status, document.failure_reason = FAILED, "enqueue_failed"
            await self._session.commit()
            log.error("document.enqueue_failed", document_id=str(document.id))
            raise ServiceUnavailableError() from exc
        log.info("document.queued", document_id=str(document.id), patient_id=str(self._patient_id))

    async def list(self, *, limit: int, offset: int) -> tuple[list[Document], int]:
        return (
            await self._documents.list(limit=limit, offset=offset),
            await self._documents.count(),
        )

    async def get(self, document_id: uuid.UUID) -> Document:
        document = await self._documents.get(document_id)
        if document is None:  # also for other patients' documents: no existence leak
            raise NotFoundError("Document not found.")
        return document
