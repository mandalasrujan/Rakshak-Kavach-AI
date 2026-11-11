"""Transaction-scoped patient context for PostgreSQL row-level security.

`set_patient_context` binds a session to one patient. Every transaction the session opens then
runs `set_config('app.patient_id', <id>, true)` -- the parameterised form of
`SET LOCAL app.patient_id` -- so the setting dies with the transaction and RLS policies only
expose that patient's rows. Unbound sessions see no patient-owned rows at all.
"""

import uuid
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

PATIENT_CONTEXT_KEY = "rk_patient_id"
_SET_LOCAL = text("SELECT set_config('app.patient_id', :patient_id, true)")


@event.listens_for(Session, "after_begin")
def _apply_patient_context(session: Session, _transaction: Any, connection: Any) -> None:
    patient_id = session.info.get(PATIENT_CONTEXT_KEY)
    if patient_id is not None:
        connection.execute(_SET_LOCAL, {"patient_id": str(patient_id)})


async def set_patient_context(session: AsyncSession, patient_id: uuid.UUID) -> None:
    bound = session.info.get(PATIENT_CONTEXT_KEY)
    if bound is not None and bound != patient_id:
        raise RuntimeError("session is already bound to a different patient")
    session.info[PATIENT_CONTEXT_KEY] = patient_id
    if session.in_transaction():  # transaction already open: apply to it now
        await session.execute(_SET_LOCAL, {"patient_id": str(patient_id)})
