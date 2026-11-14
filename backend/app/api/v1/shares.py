"""Patient side of doctor sharing: create (token + PIN shown once), list with access log, revoke."""

import uuid

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import (
    enforce_same_site_request,
    get_app_settings,
    get_current_patient,
    get_share_service,
    require_consent,
)
from app.core.config import Settings
from app.core.errors import AppError, ErrorResponse
from app.schemas.share import ShareCreated, ShareCreateRequest, ShareList, ShareRead
from app.services.share_service import ShareService

router = APIRouter(
    prefix="/patient/shares",
    tags=["sharing"],
    dependencies=[Depends(enforce_same_site_request), Depends(get_current_patient)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ShareCreated,
    summary="Share an approved snapshot with a doctor (QR link + PIN, shown once)",
    dependencies=[Depends(require_consent)],
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def create_share(
    body: ShareCreateRequest,
    response: Response,
    service: ShareService = Depends(get_share_service),
    settings: Settings = Depends(get_app_settings),
) -> ShareCreated:
    if body.expires_in_minutes > settings.share_max_expiry_minutes:
        raise AppError(f"Shares can last at most {settings.share_max_expiry_minutes} minutes.")
    created = await service.create(
        snapshot_id=body.snapshot_id, scope=body.scope, expires_in_minutes=body.expires_in_minutes
    )
    response.headers["Cache-Control"] = "no-store"
    return ShareCreated(
        share_id=created.grant.id,
        scope=created.grant.scope,
        expires_at=created.grant.expires_at,
        share_url=created.share_url,
        token=created.token,
        pin=created.pin,
    )


@router.get("", response_model=ShareList, summary="Your shares with their access log")
async def list_shares(service: ShareService = Depends(get_share_service)) -> ShareList:
    return ShareList(
        items=[ShareRead.model_validate(s) for s in await service.list_with_access_log()]
    )


@router.delete("/{share_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke a share now")
async def revoke_share(
    share_id: uuid.UUID, service: ShareService = Depends(get_share_service)
) -> Response:
    await service.revoke(share_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
