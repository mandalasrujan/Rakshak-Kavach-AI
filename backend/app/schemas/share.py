import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Scope = Literal["summary_only", "full_records"]


class ShareCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: uuid.UUID
    scope: Scope = "summary_only"
    expires_in_minutes: int = Field(default=60, ge=10, le=10080)


class ShareSessionRead(BaseModel):
    id: uuid.UUID
    declared_name: str | None
    declared_reg_no: str | None
    created_at: datetime
    expires_at: datetime
    ended_at: datetime | None
    views: int


class ShareRead(BaseModel):
    id: uuid.UUID
    snapshot_id: uuid.UUID
    scope: Scope
    status: Literal["active", "expired", "revoked", "locked"]
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    locked_at: datetime | None
    failed_pin_attempts: int
    sessions: list[ShareSessionRead]


class ShareCreated(BaseModel):
    """Returned once: the token and PIN are stored only as hashes and cannot be fetched again."""

    share_id: uuid.UUID
    scope: Scope
    expires_at: datetime
    share_url: str
    token: str
    pin: str


class ShareList(BaseModel):
    items: list[ShareRead]


class DoctorSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=128)
    pin: str = Field(pattern=r"^\d{6}$")
    declared_name: str | None = Field(default=None, max_length=120)
    declared_reg_no: str | None = Field(default=None, max_length=60)


class DoctorSessionStarted(BaseModel):
    scope: Scope
    expires_at: datetime


class DoctorView(BaseModel):
    scope: Scope
    session_expires_at: datetime
    snapshot_version: int
    approved_at: datetime
    summary: dict[str, Any]
