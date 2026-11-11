"""Patient-scoped semantic search over chunk embeddings (pgvector, exact cosine search).

Isolation is layered: the explicit patient_id filter here, plus PostgreSQL RLS on `chunks`
(the session must be bound with set_patient_context or no rows are visible at all).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import READY, Document


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page: int
    kind: str
    text: str
    similarity: float


class VectorStore(Protocol):
    async def search(
        self,
        query_embedding: Sequence[float],
        *,
        embedding_model: str,
        limit: int,
        min_similarity: float,
    ) -> list[RetrievedChunk]: ...


class PgVectorStore:
    def __init__(self, session: AsyncSession, patient_id: uuid.UUID) -> None:
        self._session = session
        self._patient_id = patient_id

    async def search(
        self,
        query_embedding: Sequence[float],
        *,
        embedding_model: str,
        limit: int,
        min_similarity: float,
    ) -> list[RetrievedChunk]:
        distance = Chunk.embedding.cosine_distance(list(query_embedding))
        result = await self._session.execute(
            select(
                Chunk.id,
                Chunk.document_id,
                Chunk.page,
                Chunk.kind,
                Chunk.text,
                distance.label("distance"),
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.patient_id == self._patient_id,
                Chunk.embedding_model == embedding_model,  # never mix embedding spaces
                Chunk.embedding.is_not(None),
                Document.status == READY,
            )
            .order_by(distance, Chunk.id)
            .limit(limit)
        )
        hits = [
            RetrievedChunk(
                chunk_id=row.id,
                document_id=row.document_id,
                page=row.page,
                kind=row.kind,
                text=row.text,
                similarity=1.0 - float(row.distance),
            )
            for row in result
        ]
        return [hit for hit in hits if hit.similarity >= min_similarity]
