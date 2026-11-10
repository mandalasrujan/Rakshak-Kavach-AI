"""Chunks, scoped to one patient (patient_id is required at construction)."""

import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk

if TYPE_CHECKING:
    from app.services.extraction import ExtractedChunk


class ChunkRepository:
    def __init__(self, session: AsyncSession, patient_id: uuid.UUID) -> None:
        self._session = session
        self._patient_id = patient_id

    async def replace_for_document(
        self, document_id: uuid.UUID, chunks: Sequence["ExtractedChunk"]
    ) -> None:
        """Delete then insert in the caller's transaction, so re-runs never duplicate chunks."""
        await self._session.execute(
            delete(Chunk).where(
                Chunk.patient_id == self._patient_id, Chunk.document_id == document_id
            )
        )
        self._session.add_all(
            Chunk(
                patient_id=self._patient_id,
                document_id=document_id,
                page=chunk.page,
                kind=chunk.kind,
                text=chunk.text,
            )
            for chunk in chunks
        )
        await self._session.flush()
