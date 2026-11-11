"""Patient-facing lab data: normalized results (M8) and deterministic comparisons (M9)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lab_result import LabResult
from app.repositories.lab_result_repository import LabResultRepository


class LabService:
    def __init__(self, session: AsyncSession, patient_id: uuid.UUID) -> None:
        self._results = LabResultRepository(session, patient_id)

    async def list_results(
        self, *, test_code: str | None, limit: int, offset: int
    ) -> tuple[list[LabResult], int]:
        return (
            await self._results.list(test_code=test_code, limit=limit, offset=offset),
            await self._results.count(test_code=test_code),
        )
