"""LangGraph checkpointer on the application's own PostgreSQL tables.

Every operation opens a session bound to one patient (`set_patient_context`), so conversation
state -- which contains retrieved document text -- is protected by the same row-level security
as all other patient data, and is deleted with its chat (FK cascade).
"""

import uuid
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.patient_context import set_patient_context
from app.models.chat import Chat, ChatCheckpoint, ChatCheckpointWrite


class PatientCheckpointSaver(BaseCheckpointSaver[int]):
    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], patient_id: uuid.UUID
    ) -> None:
        super().__init__()
        self._sessionmaker = sessionmaker
        self._patient_id = patient_id

    async def _session(self) -> AsyncSession:
        session = self._sessionmaker()
        await set_patient_context(session, self._patient_id)
        return session

    @staticmethod
    def _ids(config: RunnableConfig) -> tuple[uuid.UUID, str]:
        configurable = config["configurable"]
        return uuid.UUID(configurable["thread_id"]), configurable.get("checkpoint_ns", "")

    def _tuple(self, row: ChatCheckpoint, writes: list[ChatCheckpointWrite]) -> CheckpointTuple:
        thread = {"thread_id": str(row.chat_id), "checkpoint_ns": row.checkpoint_ns}
        return CheckpointTuple(
            config={"configurable": {**thread, "checkpoint_id": row.checkpoint_id}},
            checkpoint=self.serde.loads_typed((row.checkpoint_type, row.checkpoint)),
            metadata=self.serde.loads_typed((row.metadata_type, row.checkpoint_metadata)),
            parent_config=(
                {"configurable": {**thread, "checkpoint_id": row.parent_checkpoint_id}}
                if row.parent_checkpoint_id
                else None
            ),
            pending_writes=[
                (w.task_id, w.channel, self.serde.loads_typed((w.value_type, w.value)))
                for w in writes
            ],
        )

    async def _writes(
        self, session: AsyncSession, row: ChatCheckpoint
    ) -> list[ChatCheckpointWrite]:
        result = await session.execute(
            select(ChatCheckpointWrite)
            .where(
                ChatCheckpointWrite.chat_id == row.chat_id,
                ChatCheckpointWrite.checkpoint_ns == row.checkpoint_ns,
                ChatCheckpointWrite.checkpoint_id == row.checkpoint_id,
            )
            .order_by(ChatCheckpointWrite.task_id, ChatCheckpointWrite.idx)
        )
        return list(result.scalars())

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        chat_id, namespace = self._ids(config)
        query = select(ChatCheckpoint).where(
            ChatCheckpoint.chat_id == chat_id, ChatCheckpoint.checkpoint_ns == namespace
        )
        if checkpoint_id := get_checkpoint_id(config):
            query = query.where(ChatCheckpoint.checkpoint_id == checkpoint_id)
        else:
            query = query.order_by(ChatCheckpoint.checkpoint_id.desc()).limit(1)
        async with await self._session() as session:
            row = (await session.execute(query)).scalar_one_or_none()
            return self._tuple(row, await self._writes(session, row)) if row else None

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        query = select(ChatCheckpoint).order_by(ChatCheckpoint.checkpoint_id.desc())
        if config is not None:
            chat_id, namespace = self._ids(config)
            query = query.where(
                ChatCheckpoint.chat_id == chat_id, ChatCheckpoint.checkpoint_ns == namespace
            )
        if before is not None and (before_id := get_checkpoint_id(before)):
            query = query.where(ChatCheckpoint.checkpoint_id < before_id)
        async with await self._session() as session:
            yielded = 0
            for row in (await session.execute(query)).scalars():
                item = self._tuple(row, await self._writes(session, row))
                if filter and any(item.metadata.get(k) != v for k, v in filter.items()):
                    continue
                yield item
                yielded += 1
                if limit is not None and yielded >= limit:
                    return

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        chat_id, namespace = self._ids(config)
        checkpoint_type, checkpoint_bytes = self.serde.dumps_typed(checkpoint)
        metadata_type, metadata_bytes = self.serde.dumps_typed(
            get_checkpoint_metadata(config, metadata)
        )
        values = {
            "chat_id": chat_id,
            "checkpoint_ns": namespace,
            "checkpoint_id": checkpoint["id"],
            "patient_id": self._patient_id,
            "parent_checkpoint_id": config["configurable"].get("checkpoint_id"),
            "checkpoint_type": checkpoint_type,
            "checkpoint": checkpoint_bytes,
            "metadata_type": metadata_type,
            "checkpoint_metadata": metadata_bytes,
        }
        async with await self._session() as session:
            statement = insert(ChatCheckpoint).values(values)
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=["chat_id", "checkpoint_ns", "checkpoint_id"],
                    set_={
                        k: statement.excluded[k]
                        for k in ("checkpoint_type", "checkpoint", "metadata_type", "metadata")
                    },
                )
            )
            await session.commit()
        return {
            "configurable": {
                "thread_id": str(chat_id),
                "checkpoint_ns": namespace,
                "checkpoint_id": checkpoint["id"],
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        chat_id, namespace = self._ids(config)
        rows = []
        for index, (channel, value) in enumerate(writes):
            value_type, value_bytes = self.serde.dumps_typed(value)
            rows.append(
                {
                    "chat_id": chat_id,
                    "checkpoint_ns": namespace,
                    "checkpoint_id": config["configurable"]["checkpoint_id"],
                    "task_id": task_id,
                    "idx": WRITES_IDX_MAP.get(channel, index),
                    "patient_id": self._patient_id,
                    "channel": channel,
                    "value_type": value_type,
                    "value": value_bytes,
                    "task_path": task_path,
                }
            )
        if not rows:
            return
        async with await self._session() as session:
            statement = insert(ChatCheckpointWrite).values(rows)
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=["chat_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"],
                    set_={k: statement.excluded[k] for k in ("channel", "value_type", "value")},
                )
                if all(r["idx"] < 0 for r in rows)
                else statement.on_conflict_do_nothing()
            )
            await session.commit()

    async def adelete_thread(self, thread_id: str) -> None:
        async with await self._session() as session:
            chat = await session.get(Chat, uuid.UUID(thread_id))
            if chat is not None and chat.patient_id == self._patient_id:
                await session.delete(chat)  # checkpoints and writes cascade
                await session.commit()
