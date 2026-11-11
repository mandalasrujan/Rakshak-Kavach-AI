"""Patient medications from prescription tables, with source provenance."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import enforce_same_site_request, get_current_patient, get_patient_session
from app.core.errors import ErrorResponse
from app.models.patient import Patient
from app.repositories.medication_repository import MedicationRepository

router = APIRouter(
    prefix="/patient/medications",
    tags=["medications"],
    dependencies=[Depends(enforce_same_site_request), Depends(get_current_patient)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


class MedicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    page: int
    name: str
    dose: str | None
    frequency: str | None
    duration: str | None
    start_date: date | None


class MedicationList(BaseModel):
    items: list[MedicationRead]


@router.get("", response_model=MedicationList, summary="Medications found in your prescriptions")
async def list_medications(
    patient: Patient = Depends(get_current_patient),
    session: AsyncSession = Depends(get_patient_session),
) -> MedicationList:
    items = await MedicationRepository(session, patient.id).list(limit=200)
    return MedicationList(items=[MedicationRead.model_validate(m) for m in items])
