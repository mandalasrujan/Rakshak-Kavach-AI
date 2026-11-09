"""ARQ worker entrypoint: `arq worker.main.WorkerSettings`.

Only a liveness task is registered in Phase 1; ARQ requires at least one function.
"""

from typing import Any

import structlog
from arq.connections import RedisSettings

from app.core.logging import configure_logging
from worker.config import get_worker_config

log = structlog.get_logger(__name__)


async def healthcheck(ctx: dict[str, Any]) -> str:
    """Trivial job used to verify that the worker consumes the queue."""
    return "ok"


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging(get_worker_config().log_level)
    log.info("worker.started")


async def shutdown(ctx: dict[str, Any]) -> None:
    log.info("worker.stopped")


class WorkerSettings:
    functions = (healthcheck,)
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_worker_config().redis_url)
    # `arq --check` (container healthcheck) passes only while this key is refreshed.
    health_check_interval = 10
