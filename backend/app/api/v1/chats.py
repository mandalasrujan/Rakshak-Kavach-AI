"""Chats with the Medical History Agent; conversation state is persisted per chat."""

import uuid

from fastapi import APIRouter, Depends, Query, Response, status

from app.agent.service import AgentService
from app.api.deps import (
    enforce_same_site_request,
    get_agent_service,
    get_current_patient,
    require_consent,
)
from app.core.errors import ErrorResponse
from app.schemas.ask import AskRequest, ChatAnswer, ChatHistory, ChatList, ChatRead

router = APIRouter(
    prefix="/patient/chats",
    tags=["chats"],
    dependencies=[Depends(enforce_same_site_request), Depends(get_current_patient)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse, "description": "CSRF rejected or consent required"},
        404: {"model": ErrorResponse},
    },
)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ChatRead,
    summary="Start a chat",
    dependencies=[Depends(require_consent)],
)
async def create_chat(service: AgentService = Depends(get_agent_service)) -> ChatRead:
    return ChatRead.model_validate(await service.create_chat())


@router.get("", response_model=ChatList, summary="Your chats (newest first)")
async def list_chats(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: AgentService = Depends(get_agent_service),
) -> ChatList:
    chats = await service.list_chats(limit=limit, offset=offset)
    return ChatList(items=[ChatRead.model_validate(c) for c in chats], limit=limit, offset=offset)


@router.get("/{chat_id}/messages", response_model=ChatHistory, summary="Chat history")
async def chat_history(
    chat_id: uuid.UUID, service: AgentService = Depends(get_agent_service)
) -> ChatHistory:
    return ChatHistory.model_validate(
        {"chat_id": chat_id, "messages": await service.history(chat_id)}
    )


@router.post(
    "/{chat_id}/messages",
    response_model=ChatAnswer,
    summary="Ask a question in a chat",
    dependencies=[Depends(require_consent)],
    responses={429: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def send_message(
    chat_id: uuid.UUID, body: AskRequest, service: AgentService = Depends(get_agent_service)
) -> ChatAnswer:
    return ChatAnswer.model_validate(await service.send(chat_id, body.question))


@router.delete(
    "/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat and its stored conversation",
)
async def delete_chat(
    chat_id: uuid.UUID, service: AgentService = Depends(get_agent_service)
) -> Response:
    await service.delete_chat(chat_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
