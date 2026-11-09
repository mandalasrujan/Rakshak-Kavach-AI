"""Dependency health checks for /health. Failures are logged by type only."""

import asyncio

import structlog
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.schemas.health import CheckStatus, HealthChecks, HealthResponse

log = structlog.get_logger(__name__)
_TIMEOUT_SECONDS = 2.0


class HealthService:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], redis: Redis) -> None:
        self._sessionmaker = sessionmaker
        self._redis = redis

    async def _database(self) -> CheckStatus:
        try:
            async with asyncio.timeout(_TIMEOUT_SECONDS), self._sessionmaker() as session:
                await session.execute(text("SELECT 1"))
            return "ok"
        except Exception as exc:
            log.warning("health.database_unavailable", error_type=type(exc).__name__)
            return "unavailable"

    async def _redis_ping(self) -> CheckStatus:
        try:
            async with asyncio.timeout(_TIMEOUT_SECONDS):
                await self._redis.ping()
            return "ok"
        except Exception as exc:
            log.warning("health.redis_unavailable", error_type=type(exc).__name__)
            return "unavailable"

    async def check(self) -> HealthResponse:
        database, redis = await asyncio.gather(self._database(), self._redis_ping())
        status = "ok" if database == "ok" and redis == "ok" else "unavailable"
        return HealthResponse(status=status, checks=HealthChecks(database=database, redis=redis))
