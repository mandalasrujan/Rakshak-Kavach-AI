"""Patient-facing lab data: normalized results (M8) and deterministic comparisons (M9)."""

import uuid
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lab_result import LabResult
from app.repositories.lab_result_repository import LabResultRepository
from app.services.lab_comparison import LabComparison, LabPoint, compare
from app.services.lab_normalization import load_dictionary


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

    async def trends(self, *, test_code: str | None) -> list[LabComparison]:
        """Compare each canonical test across documents. Unknown tests are never compared."""
        dictionary = load_dictionary()
        grouped: dict[str, list[LabPoint]] = defaultdict(list)
        for row in await self._results.list(test_code=test_code):
            if row.test_code is None or row.test_code not in dictionary.tests:
                continue
            grouped[row.test_code].append(
                LabPoint(
                    result_id=row.id,
                    document_id=row.document_id,
                    chunk_id=row.chunk_id,
                    page=row.page,
                    raw_value=row.raw_value,
                    raw_unit=row.raw_unit,
                    canonical_value=row.canonical_value,
                    canonical_ref_low=row.canonical_ref_low,
                    canonical_ref_high=row.canonical_ref_high,
                    effective_date=row.collected_on or row.reported_on,
                    date_ambiguous=row.date_ambiguous,
                    validation_status=row.validation_status,
                )
            )
        return [
            compare(code, dictionary.tests[code].name, dictionary.tests[code].unit, points)
            for code, points in sorted(grouped.items())
        ]
