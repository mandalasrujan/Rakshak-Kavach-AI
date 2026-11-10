"""ARQ worker entrypoint: `arq worker.main.WorkerSettings`."""

import uuid
from typing import Any

import structlog
from arq import Retry
from arq.connections import RedisSettings

from app.core.logging import configure_logging
from app.core.storage import create_storage
from app.db.session import create_engine, create_sessionmaker
from app.models.document import FAILED
from app.services.document_processing import DocumentProcessor
from worker.config import get_worker_config

log = structlog.get_logger(__name__)

MAX_TRIES = 3


async def healthcheck(ctx: dict[str, Any]) -> str:
    """Trivial job used to verify that the worker consumes the queue."""
    return "ok"


async def process_document(ctx: dict[str, Any], document_id: str, patient_id: str) -> str:
    """Thin job wrapper: logic lives in DocumentProcessor. Job args are IDs only (no PHI).

    Unexpected errors are retried with backoff; after the last try the document is marked
    failed so it never stays queued forever.
    """
    processor: DocumentProcessor = ctx["document_processor"]
    doc_id, owner_id = uuid.UUID(document_id), uuid.UUID(patient_id)
    try:
        return await processor.process(doc_id, owner_id)
    except Exception as exc:
        attempt = int(ctx.get("job_try", 1))
        log.warning(
            "document.processing_error",
            document_id=document_id,
            attempt=attempt,
            error_type=type(exc).__name__,
        )
        if attempt < MAX_TRIES:
            raise Retry(defer=attempt * 5) from exc
        await processor.mark_failed(doc_id, owner_id, "processing_error")
        return FAILED


async def startup(ctx: dict[str, Any]) -> None:
    config = get_worker_config()
    configure_logging(config.log_level)
    engine = create_engine(config.database_url)
    ctx["engine"] = engine
    ctx["document_processor"] = DocumentProcessor(
        create_sessionmaker(engine),
        create_storage(config.storage_backend, config.storage_local_path),
        max_pages=config.max_pdf_pages,
    )
    log.info("worker.started")


async def shutdown(ctx: dict[str, Any]) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()
    log.info("worker.stopped")


class WorkerSettings:
    functions = (healthcheck, process_document)
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_worker_config().redis_url)
    max_tries = MAX_TRIES
    job_timeout = 300
    # `arq --check` (container healthcheck) passes only while this key is refreshed.
    health_check_interval = 10
