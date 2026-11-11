"""Application factory. Run with: uvicorn --factory app.main:create_app"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from arq.connections import ArqRedis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import CSRF_HEADER_NAME, REQUEST_ID_HEADER, Settings, get_settings
from app.core.errors import ErrorResponse, register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_context import RequestContextMiddleware
from app.core.security import PasswordService, TokenService
from app.core.storage import create_storage
from app.db.session import create_engine, create_sessionmaker
from app.llm.base import LLMNotConfiguredError
from app.llm.factory import create_llm_provider

API_PREFIX = "/api/v1"
log = structlog.get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        app.state.redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        # Job queue client (arq needs raw bytes, so a separate client from app.state.redis).
        app.state.arq = ArqRedis.from_url(
            settings.redis_url, socket_connect_timeout=2, socket_timeout=2
        )
        app.state.storage = create_storage(settings.storage_backend, settings.storage_local_path)
        try:
            app.state.llm = create_llm_provider(settings)
        except LLMNotConfiguredError:
            app.state.llm = None  # /ask answers 503 until the provider is configured
            log.warning("llm.not_configured", provider=settings.llm_provider)
        try:
            yield
        finally:
            if app.state.llm is not None:
                await app.state.llm.aclose()
            await app.state.arq.aclose()
            await app.state.redis.aclose()
            await engine.dispose()

    app = FastAPI(
        title="Rakshak Kavach AI API",
        version="0.1.0",
        description="Patient health records assistant API.",
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    app.state.settings = settings
    app.state.password_service = PasswordService()
    app.state.token_service = TokenService(settings)
    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", CSRF_HEADER_NAME, REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestContextMiddleware, header_name=REQUEST_ID_HEADER)  # outermost

    app.include_router(health_router)
    app.include_router(api_router, prefix=API_PREFIX)
    return app
