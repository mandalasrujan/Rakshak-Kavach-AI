import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    failure_reason: str | None
    pages: int | None
    uploaded_at: datetime


class DocumentList(BaseModel):
    items: list[DocumentRead]
    total: int
    limit: int
    offset: int
