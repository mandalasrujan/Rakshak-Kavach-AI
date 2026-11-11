"""Medications, scoped to one patient (patient_id is required at construction)."""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medication import Medication
from app.services.medication_extraction import ExtractedMedication


class MedicationRepository:
    def __init__(self, session: AsyncSession, patient_id: uuid.UUID) -> None:
        self._session = session
        self._patient_id = patient_id

    async def replace_for_document(
        self,
        document_id: uuid.UUID,
        medications: Sequence[tuple[uuid.UUID, ExtractedMedication]],  # (chunk_id, item)
        *,
        start_date: date | None,
    ) -> None:
        await self._session.execute(
            delete(Medication).where(
                Medication.patient_id == self._patient_id, Medication.document_id == document_id
            )
        )
        self._session.add_all(
            Medication(
                patient_id=self._patient_id,
                document_id=document_id,
                chunk_id=chunk_id,
                page=item.page,
                name=item.name,
                dose=item.dose,
                frequency=item.frequency,
                duration=item.duration,
                start_date=start_date,
                raw_text=item.raw_text,
                validation_status="ok",
            )
            for chunk_id, item in medications
        )
        await self._session.flush()

    async def list(self, *, limit: int = 50) -> list[Medication]:
        result = await self._session.execute(
            select(Medication)
            .where(Medication.patient_id == self._patient_id)
            .order_by(Medication.start_date.desc().nulls_last(), Medication.name, Medication.id)
            .limit(limit)
        )
        return list(result.scalars())
