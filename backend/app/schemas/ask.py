import uuid

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
