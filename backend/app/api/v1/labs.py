"""Patient lab data: normalized results with provenance."""

from fastapi import APIRouter, Depends, Query

from app.api.deps import enforce_same_site_request, get_current_patient, get_lab_service
from app.core.errors import ErrorResponse
from app.schemas.lab import LabResultList, LabResultRead
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
