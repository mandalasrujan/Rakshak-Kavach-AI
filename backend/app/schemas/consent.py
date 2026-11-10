from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConsentGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notice_version: str = Field(min_length=1, max_length=32)


class ConsentStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notice_version: str
    notice_text: str
    granted: bool
    granted_notice_version: str | None
    granted_at: datetime | None
    revoked_at: datetime | None
