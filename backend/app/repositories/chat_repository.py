"""Chats and citations, scoped to one patient (patient_id is required at construction)."""

import uuid
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, MessageCitation


class ChatRepository:
    def __init__(self, session: AsyncSession, patient_id: uuid.UUID) -> None:
        self._session = session
        self._patient_id = patient_id

    async def create(self) -> Chat:
        chat = Chat(patient_id=self._patient_id)
        self._session.add(chat)
        await self._session.flush()
        return chat

    async def get(self, chat_id: uuid.UUID) -> Chat | None:
        result = await self._session.execute(
            select(Chat).where(Chat.id == chat_id, Chat.patient_id == self._patient_id)
        )
        return result.scalar_one_or_none()

    async def list_chats(self, *, limit: int, offset: int) -> list[Chat]:
        result = await self._session.execute(
            select(Chat)
            .where(Chat.patient_id == self._patient_id)
            .order_by(Chat.created_at.desc(), Chat.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    async def add_citations(self, chat_id: uuid.UUID, document_ids: Iterable[uuid.UUID]) -> None:
        rows = [
            {"chat_id": chat_id, "document_id": d, "patient_id": self._patient_id}
            for d in set(document_ids)
        ]
        if rows:
            await self._session.execute(
                insert(MessageCitation).values(rows).on_conflict_do_nothing()
            )

    async def chats_citing(self, document_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self._session.execute(
            select(MessageCitation.chat_id).where(
                MessageCitation.patient_id == self._patient_id,
                MessageCitation.document_id == document_id,
            )
        )
        return list(result.scalars())

    async def delete(self, chat_ids: Iterable[uuid.UUID]) -> int:
        """Delete chats; checkpoints, pending writes and citations cascade with them."""
        ids = list(chat_ids)
        if not ids:
            return 0
        result = await self._session.execute(
            delete(Chat).where(Chat.patient_id == self._patient_id, Chat.id.in_(ids))
        )
        return result.rowcount or 0
