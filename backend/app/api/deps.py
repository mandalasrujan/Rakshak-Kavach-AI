"""FastAPI dependencies shared by routers."""

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ACCESS_COOKIE_NAME, CSRF_HEADER_NAME, Settings
from app.core.errors import CsrfRejectedError
from app.models.patient import Patient
from app.services.auth_service import AuthService
from app.services.health_service import HealthService

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def get_health_service(request: Request, redis: Redis = Depends(get_redis)) -> HealthService:
    return HealthService(request.app.state.sessionmaker, redis)


def get_auth_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_app_settings),
) -> AuthService:
    return AuthService(
        session=session,
        redis=redis,
        settings=settings,
        passwords=request.app.state.password_service,
        tokens=request.app.state.token_service,
    )


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce_same_site_request(
    request: Request, settings: Settings = Depends(get_app_settings)
) -> None:
    """CSRF protection (ADR 0004).

    Rejects requests from any origin other than the configured frontend, browser requests
    marked cross-site, and unsafe-method requests without the custom CSRF header.
    """
    origin = request.headers.get("origin")
    if origin is not None and origin.rstrip("/") != settings.frontend_origin:
        raise CsrfRejectedError()
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise CsrfRejectedError()
    if request.method not in _SAFE_METHODS and request.headers.get(CSRF_HEADER_NAME) != "1":
        raise CsrfRejectedError()


async def get_current_patient(
    request: Request, auth_service: AuthService = Depends(get_auth_service)
) -> Patient:
    return await auth_service.authenticate(request.cookies.get(ACCESS_COOKIE_NAME))
