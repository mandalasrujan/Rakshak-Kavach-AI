"""Patient consent: read the current notice and status, grant, revoke."""

from fastapi import APIRouter, Depends

from app.api.deps import enforce_same_site_request, get_consent_service, get_current_patient
from app.core.errors import ErrorResponse
from app.schemas.consent import ConsentGrantRequest, ConsentStatusRead
from app.services.consent_service import ConsentService

router = APIRouter(
    prefix="/patient/consent",
    tags=["consent"],
    dependencies=[Depends(enforce_same_site_request), Depends(get_current_patient)],
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "CSRF protection rejected"},
    },
)


@router.get("", response_model=ConsentStatusRead, summary="Current notice and consent status")
async def read_consent(service: ConsentService = Depends(get_consent_service)) -> ConsentStatusRead:
    return ConsentStatusRead.model_validate(await service.status())


@router.post(
    "",
    response_model=ConsentStatusRead,
    summary="Grant consent to the current notice version",
    responses={409: {"model": ErrorResponse, "description": "Notice version is outdated"}},
)
async def grant_consent(
    body: ConsentGrantRequest, service: ConsentService = Depends(get_consent_service)
) -> ConsentStatusRead:
    return ConsentStatusRead.model_validate(await service.grant(body.notice_version))


@router.delete("", response_model=ConsentStatusRead, summary="Revoke consent")
async def revoke_consent(
    service: ConsentService = Depends(get_consent_service),
) -> ConsentStatusRead:
    return ConsentStatusRead.model_validate(await service.revoke())
