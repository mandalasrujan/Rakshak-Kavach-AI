"""Normalized lab results, scoped to one patient (patient_id is required at construction)."""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lab_result import LabResult
from app.services.lab_normalization import NormalizedLab


class LabResultRepository:
    def __init__(self, session: AsyncSession, patient_id: uuid.UUID) -> None:
        self._session = session
        self._patient_id = patient_id

    async def replace_for_document(
        self,
        document_id: uuid.UUID,
        results: Sequence[tuple[uuid.UUID, NormalizedLab]],  # (chunk_id, result)
        *,
        collected_on: date | None,
        reported_on: date | None,
        date_ambiguous: bool,
        dictionary_version: str,
    ) -> None:
        await self._session.execute(
            delete(LabResult).where(
                LabResult.patient_id == self._patient_id, LabResult.document_id == document_id
            )
        )
        self._session.add_all(
            LabResult(
                patient_id=self._patient_id,
                document_id=document_id,
                chunk_id=chunk_id,
                collected_on=collected_on,
                reported_on=reported_on,
                date_ambiguous=date_ambiguous,
                dictionary_version=dictionary_version,
                **{field: getattr(result, field) for field in NormalizedLab.__dataclass_fields__},
            )
            for chunk_id, result in results
        )
        await self._session.flush()

    async def list(
        self, *, test_code: str | None = None, limit: int | None = None, offset: int = 0
    ) -> list[LabResult]:
        query = select(LabResult).where(LabResult.patient_id == self._patient_id)
        if test_code is not None:
            query = query.where(LabResult.test_code == test_code)
        query = query.order_by(
            LabResult.test_code, LabResult.collected_on, LabResult.reported_on, LabResult.id
        )
        if limit is not None:
            query = query.limit(limit).offset(offset)
        return list((await self._session.execute(query)).scalars())

    async def count(self, *, test_code: str | None = None) -> int:
        query = (
            select(func.count())
            .select_from(LabResult)
            .where(LabResult.patient_id == self._patient_id)
        )
        if test_code is not None:
            query = query.where(LabResult.test_code == test_code)
        return int((await self._session.execute(query)).scalar_one())
