"""Documents, scoped to one patient (patient_id is required at construction)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


class DocumentRepository:
    def __init__(self, session: AsyncSession, patient_id: uuid.UUID) -> None:
        self._session = session
        self._patient_id = patient_id

    async def get(self, document_id: uuid.UUID) -> Document | None:
        result = await self._session.execute(
            select(Document).where(
                Document.id == document_id, Document.patient_id == self._patient_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_hash(self, file_hash: str) -> Document | None:
        result = await self._session.execute(
            select(Document).where(
                Document.patient_id == self._patient_id, Document.file_hash == file_hash
            )
        )
        return result.scalar_one_or_none()

    async def list(self, *, limit: int, offset: int) -> list[Document]:
        result = await self._session.execute(
            select(Document)
            .where(Document.patient_id == self._patient_id)
            .order_by(Document.uploaded_at.desc(), Document.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    async def count(self) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.patient_id == self._patient_id)
        )
        return int(result.scalar_one())

    async def add(self, *, storage_key: str, file_hash: str) -> Document:
        document = Document(
            patient_id=self._patient_id, storage_key=storage_key, file_hash=file_hash
        )
        self._session.add(document)
        await self._session.flush()
        return document
