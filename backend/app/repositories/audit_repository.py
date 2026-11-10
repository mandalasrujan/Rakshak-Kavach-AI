"""Append-only access to audit_log. There are intentionally no update or delete methods."""

import uuid
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

ActorType = Literal["patient", "doctor", "system"]


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        patient_id: uuid.UUID,
        actor_type: ActorType,
        action: str,
        target_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Record an event. `details` must hold IDs, codes or versions only, never PHI."""
        entry = AuditLog(
            patient_id=patient_id,
            actor_type=actor_type,
            action=action,
            target_id=target_id,
            details=details or {},
        )
        self._session.add(entry)
        await self._session.flush()
        return entry
