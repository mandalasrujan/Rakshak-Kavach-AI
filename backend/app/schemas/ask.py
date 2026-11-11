import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000)


class CitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    page: int
    chunk_id: uuid.UUID
    excerpt: str


class AskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    found: bool
    answer: str
    citations: list[CitationRead]
    urgent: bool = False  # true: a fixed safety message replaced the normal answer (M11)


class ChatAnswer(AskResponse):
    chat_id: uuid.UUID


class ChatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class ChatList(BaseModel):
    items: list[ChatRead]
    limit: int
    offset: int


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatHistory(BaseModel):
    chat_id: uuid.UUID
    messages: list[ChatMessage]
