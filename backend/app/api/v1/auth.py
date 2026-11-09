"""Patient authentication: register, login (sets httpOnly cookie), logout."""

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import client_ip, enforce_same_site_request, get_app_settings, get_auth_service
from app.core.config import ACCESS_COOKIE_NAME, Settings
from app.core.errors import ErrorResponse
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.patient import PatientRead
from app.services.auth_service import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(enforce_same_site_request)],
    responses={403: {"model": ErrorResponse, "description": "CSRF protection rejected"}},
)


def _cookie_options(settings: Settings) -> dict[str, object]:
    return {"httponly": True, "secure": settings.cookie_secure, "samesite": "lax", "path": "/"}


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=PatientRead,
    summary="Register a patient account",
    responses={409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)
async def register(
    body: RegisterRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> PatientRead:
    patient = await service.register(
        email=body.email, password=body.password.get_secret_value(), client_ip=client_ip(request)
    )
    return PatientRead.model_validate(patient)


@router.post(
    "/login",
    response_model=PatientRead,
    summary="Log in and receive an httpOnly session cookie",
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_app_settings),
) -> PatientRead:
    result = await service.login(
        email=body.email, password=body.password.get_secret_value(), client_ip=client_ip(request)
    )
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        result.access_token.token,
        max_age=settings.access_token_ttl_seconds,
        **_cookie_options(settings),  # type: ignore[arg-type]
    )
    return PatientRead.model_validate(result.patient)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out: revoke the current token and clear the cookie",
)
async def logout(
    request: Request,
    service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    await service.logout(request.cookies.get(ACCESS_COOKIE_NAME))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(ACCESS_COOKIE_NAME, **_cookie_options(settings))  # type: ignore[arg-type]
    return response
