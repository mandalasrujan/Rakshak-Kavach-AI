"""Patient-requested deletion of one document and everything derived from it (M12).

Order matters for retry safety:
1. Lock the patient's own document row (404 for anyone else's).
2. Delete the stored file (idempotent). If storage fails, nothing in the database changed,
   so the request can simply be retried.
3. In one transaction: delete chats that cited the document (their LangGraph checkpoints,
   pending writes and citations cascade), then the document itself (chunks with embeddings,
   lab results and medications cascade), invalidate summary snapshots built from it (content
   purged), and append a PHI-free audit event.
A worker still holding a job for this document finds no row (or waits on the lock) and
writes nothing.
"""

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ServiceUnavailableError
from app.core.storage import ObjectStorage
from app.models.chunk import Chunk
from app.models.lab_result import LabResult
from app.models.medication import Medication
from app.repositories.audit_repository import AuditRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.snapshot_repository import SnapshotRepository

log = structlog.get_logger(__name__)


class DocumentDeletionService:
    def __init__(
        self, session: AsyncSession, patient_id: uuid.UUID, *, storage: ObjectStorage
    ) -> None:
        self._session = session
        self._patient_id = patient_id
        self._storage = storage

    async def _count(self, model: type, document_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(model)
            .where(
                model.patient_id == self._patient_id,  # type: ignore[attr-defined]
                model.document_id == document_id,  # type: ignore[attr-defined]
            )
        )
        return int(result.scalar_one())

    async def delete(self, document_id: uuid.UUID) -> None:
        document = await DocumentRepository(self._session, self._patient_id).get_for_update(
            document_id
        )
        if document is None:
            raise NotFoundError("Document not found.")
        try:
            await self._storage.delete(document.storage_key)
        except OSError as exc:
            await self._session.rollback()
            log.error("document.file_delete_failed", document_id=str(document_id))
            raise ServiceUnavailableError() from exc

        counts = {
            "chunks": await self._count(Chunk, document_id),
            "lab_results": await self._count(LabResult, document_id),
            "medications": await self._count(Medication, document_id),
        }
        chats = ChatRepository(self._session, self._patient_id)
        counts["chats"] = await chats.delete(await chats.chats_citing(document_id))
        invalidated = await SnapshotRepository(self._session, self._patient_id).invalidate_citing(
            document_id
        )
        counts["snapshots_invalidated"] = len(invalidated)
        await self._session.delete(document)
        await AuditRepository(self._session).add(
            patient_id=self._patient_id,
            actor_type="patient",
            action="document.deleted",
            target_id=document_id,
            details=counts,  # counts only: no names, values or file names
        )
        await self._session.commit()
        log.info(
            "document.deleted",
            document_id=str(document_id),
            patient_id=str(self._patient_id),
            **counts,
        )
