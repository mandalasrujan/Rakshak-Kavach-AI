"""Doctor side of sharing: PIN exchange, read-only scoped view, end session.

This router never uses the patient session cookie or patient dependencies. The doctor session
lives in its own httpOnly cookie, path-scoped to /api/v1/share, so browsers never send it to
patient endpoints (and patient endpoints would not accept it).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import (
    client_ip,
    enforce_same_site_request,
    get_app_settings,
    get_share_access_service,
)
from app.core.config import SHARE_COOKIE_NAME, Settings
from app.core.errors import ErrorResponse
from app.schemas.share import DoctorSessionRequest, DoctorSessionStarted, DoctorView
from app.services.share_access import ShareAccessService

COOKIE_PATH = "/api/v1/share"

router = APIRouter(
    prefix="/share",
    tags=["doctor share"],
    dependencies=[Depends(enforce_same_site_request)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)


def _cookie_options(settings: Settings) -> dict[str, object]:
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "strict",
        "path": COOKIE_PATH,
    }


@router.post(
    "/sessions",
    response_model=DoctorSessionStarted,
    summary="Exchange the share token and PIN for a 30-minute read-only session",
)
async def start_session(
    body: DoctorSessionRequest,
    request: Request,
    response: Response,
    service: ShareAccessService = Depends(get_share_access_service),
    settings: Settings = Depends(get_app_settings),
) -> DoctorSessionStarted:
    started = await service.start_session(
        token=body.token,
        pin=body.pin,
        declared_name=body.declared_name,
        declared_reg_no=body.declared_reg_no,
        client_ip=client_ip(request),
    )
    max_age = max(1, int((started.expires_at - datetime.now(UTC)).total_seconds()))
    response.set_cookie(
        SHARE_COOKIE_NAME, started.token, max_age=max_age, **_cookie_options(settings)
    )  # type: ignore[arg-type]
    return DoctorSessionStarted(scope=started.scope, expires_at=started.expires_at)  # type: ignore[arg-type]


@router.get(
    "/view",
    response_model=DoctorView,
    summary="The approved snapshot, limited to the share's scope",
)
async def view(
    request: Request, service: ShareAccessService = Depends(get_share_access_service)
) -> DoctorView:
    return DoctorView.model_validate(await service.view(request.cookies.get(SHARE_COOKIE_NAME)))


@router.post(
    "/session/end", status_code=status.HTTP_204_NO_CONTENT, summary="End the doctor session"
)
async def end_session(
    request: Request,
    service: ShareAccessService = Depends(get_share_access_service),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    await service.end_session(request.cookies.get(SHARE_COOKIE_NAME))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SHARE_COOKIE_NAME, **_cookie_options(settings))  # type: ignore[arg-type]
    return response
