"""Data access for patients. Every query is keyed by the patient's own id or email."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient


class PatientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, patient_id: uuid.UUID) -> Patient | None:
        return await self._session.get(Patient, patient_id)

    async def get_by_email(self, email: str) -> Patient | None:
        result = await self._session.execute(select(Patient).where(Patient.email == email))
        return result.scalar_one_or_none()

    async def add(self, *, email: str, password_hash: str) -> Patient:
        patient = Patient(email=email, password_hash=password_hash)
        self._session.add(patient)
        await self._session.flush()
        return patient

    async def update_password_hash(self, patient: Patient, password_hash: str) -> None:
        patient.password_hash = password_hash
        await self._session.flush()
