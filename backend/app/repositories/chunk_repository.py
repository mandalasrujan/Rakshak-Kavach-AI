"""Chunks, scoped to one patient (patient_id is required at construction)."""

import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk

if TYPE_CHECKING:
    from app.services.extraction import ExtractedChunk


class ChunkRepository:
    def __init__(self, session: AsyncSession, patient_id: uuid.UUID) -> None:
        self._session = session
        self._patient_id = patient_id

    async def replace_for_document(
        self,
        document_id: uuid.UUID,
        chunks: Sequence["ExtractedChunk"],
        *,
        embeddings: Sequence[list[float]],
        embedding_model: str,
    ) -> list[Chunk]:
        """Delete then insert in the caller's transaction, so re-runs never leave stale or
        duplicate chunks/embeddings. Returns the new rows in extraction order."""
        if len(embeddings) != len(chunks):
            raise ValueError("one embedding per chunk is required")
        await self._session.execute(
            delete(Chunk).where(
                Chunk.patient_id == self._patient_id, Chunk.document_id == document_id
            )
        )
        rows = [
            Chunk(
                id=uuid.uuid4(),
                patient_id=self._patient_id,
                document_id=document_id,
                page=chunk.page,
                kind=chunk.kind,
                text=chunk.text,
                embedding=embedding,
                embedding_model=embedding_model,
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        self._session.add_all(rows)
        await self._session.flush()
        return rows

    async def texts(self, chunk_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not chunk_ids:
            return {}
        result = await self._session.execute(
            select(Chunk.id, Chunk.text).where(
                Chunk.patient_id == self._patient_id, Chunk.id.in_(list(chunk_ids))
            )
        )
        return {chunk_id: text for chunk_id, text in result}
