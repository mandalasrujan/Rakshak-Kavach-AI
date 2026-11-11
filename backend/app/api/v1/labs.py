"""Patient lab data: normalized results with provenance and deterministic comparisons."""

from fastapi import APIRouter, Depends, Query

from app.api.deps import enforce_same_site_request, get_current_patient, get_lab_service
from app.core.errors import ErrorResponse
from app.schemas.lab import LabResultList, LabResultRead, LabTrendList, LabTrendRead
from app.services.lab_comparison import COMPARISON_NOTE
from app.services.lab_service import LabService

router = APIRouter(
    prefix="/patient/labs",
    tags=["labs"],
    dependencies=[Depends(enforce_same_site_request), Depends(get_current_patient)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
TEST_CODE = Query(default=None, pattern=r"^[A-Z0-9_]{1,32}$", description="Canonical test code")


@router.get("", response_model=LabResultList, summary="Your normalized lab results")
async def list_lab_results(
    test_code: str | None = TEST_CODE,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: LabService = Depends(get_lab_service),
) -> LabResultList:
    items, total = await service.list_results(test_code=test_code, limit=limit, offset=offset)
    return LabResultList(
        items=[LabResultRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/trends",
    response_model=LabTrendList,
    summary="Previous-vs-latest comparison per test",
    description=(
        "Computed deterministically in Python from normalized results (no LLM). Status is "
        "relative to each report's own reference range and is not a diagnosis."
    ),
)
async def lab_trends(
    test_code: str | None = TEST_CODE,
    service: LabService = Depends(get_lab_service),
) -> LabTrendList:
    items = await service.trends(test_code=test_code)
    return LabTrendList(items=[LabTrendRead.model_validate(i) for i in items], note=COMPARISON_NOTE)
