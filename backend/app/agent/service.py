"""Runs the agent for a patient: single questions (/ask) and persisted chats."""

import time
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.checkpointer import PatientCheckpointSaver
from app.agent.graph import build_agent_graph, turn_input
from app.core.config import Settings
from app.core.errors import (
    ConsentRequiredError,
    LLMUnavailableError,
    NotFoundError,
    RateLimitedError,
    ServiceUnavailableError,
)
from app.llm.base import LLMError, LLMProvider
from app.models.chat import Chat
from app.repositories.audit_repository import AuditRepository
from app.repositories.chat_repository import ChatRepository
from app.services.rate_limiter import RateLimiter

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AgentReply:
    found: bool
    answer: str
    citations: list[dict[str, Any]]
    urgent: bool
    chat_id: uuid.UUID | None = None


class AgentService:
    def __init__(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        *,
        llm: LLMProvider | None,
        redis: Redis,
        settings: Settings,
        sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session = session
        self._patient_id = patient_id
        self._llm = llm
        self._limiter = RateLimiter(redis)
        self._settings = settings
        self._sessionmaker = sessionmaker
        self._chats = ChatRepository(session, patient_id)

    async def _enforce_rate_limit(self) -> None:
        try:
            result = await self._limiter.hit(
                f"rl:ask:patient:{self._patient_id}",
                limit=self._settings.ask_max_per_hour,
                window_seconds=3600,
            )
        except RedisError as exc:
            raise ServiceUnavailableError() from exc  # fail closed
        if not result.allowed:
            raise RateLimitedError(headers={"Retry-After": str(result.retry_after_seconds)})

    def _checkpointer(self) -> PatientCheckpointSaver:
        return PatientCheckpointSaver(self._sessionmaker, self._patient_id)

    async def _run(self, question: str, chat_id: uuid.UUID | None) -> AgentReply:
        if self._llm is None:
            raise LLMUnavailableError()
        await self._enforce_rate_limit()
        graph = build_agent_graph(
            session=self._session,
            patient_id=self._patient_id,
            llm=self._llm,
            settings=self._settings,
            chat_id=chat_id,
            checkpointer=self._checkpointer() if chat_id else None,
        )
        config = {"configurable": {"thread_id": str(chat_id)}} if chat_id else None
        started = time.perf_counter()
        try:
            state = await graph.ainvoke(turn_input(question), config=config)
        except LLMError as exc:
            log.warning(
                "agent.llm_error", patient_id=str(self._patient_id), error_type=type(exc).__name__
            )
            raise LLMUnavailableError() from exc
        if state["outcome"] == "no_consent":
            raise ConsentRequiredError()
        response = state["response"]
        log.info(
            "agent.answered",
            patient_id=str(self._patient_id),
            chat_id=str(chat_id) if chat_id else None,
            outcome=state["outcome"],
            found=response["found"],
            cited=len(response["citations"]),
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return AgentReply(chat_id=chat_id, **response)

    async def ask(self, question: str) -> AgentReply:
        """Single question, no stored conversation."""
        return await self._run(question, None)

    async def _owned_chat(self, chat_id: uuid.UUID) -> Chat:
        chat = await self._chats.get(chat_id)
        if chat is None:  # also for other patients' chats: no existence leak
            raise NotFoundError("Chat not found.")
        return chat

    async def create_chat(self) -> Chat:
        chat = await self._chats.create()
        await self._session.commit()
        return chat

    async def list_chats(self, *, limit: int, offset: int) -> list[Chat]:
        return await self._chats.list_chats(limit=limit, offset=offset)

    async def send(self, chat_id: uuid.UUID, question: str) -> AgentReply:
        await self._owned_chat(chat_id)
        return await self._run(question, chat_id)

    async def history(self, chat_id: uuid.UUID) -> list[dict[str, str]]:
        await self._owned_chat(chat_id)
        saved = await self._checkpointer().aget_tuple({"configurable": {"thread_id": str(chat_id)}})
        return list(saved.checkpoint["channel_values"].get("messages", [])) if saved else []

    async def delete_chat(self, chat_id: uuid.UUID) -> None:
        await self._owned_chat(chat_id)
        await self._chats.delete([chat_id])  # checkpoints, writes and citations cascade
        await AuditRepository(self._session).add(
            patient_id=self._patient_id,
            actor_type="patient",
            action="chat.deleted",
            target_id=chat_id,
        )
        await self._session.commit()
