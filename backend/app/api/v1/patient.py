"""Patient-scoped routes. Every route requires an authenticated patient."""

from fastapi import APIRouter, Depends

from app.api.deps import enforce_same_site_request, get_current_patient
from app.core.errors import ErrorResponse
from app.models.patient import Patient
from app.schemas.patient import PatientRead

router = APIRouter(
    prefix="/patient",
    tags=["patient"],
    dependencies=[Depends(enforce_same_site_request), Depends(get_current_patient)],
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "CSRF protection rejected"},
    },
)


@router.get("/me", response_model=PatientRead, summary="Current patient's account")
async def read_me(patient: Patient = Depends(get_current_patient)) -> PatientRead:
    return PatientRead.model_validate(patient)
