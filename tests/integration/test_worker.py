"""M0: the ARQ worker consumes jobs from Redis and is configured for `arq --check`."""

import importlib
import uuid

import pytest
from arq import create_pool
from arq.connections import RedisSettings
from arq.worker import Worker

pytestmark = pytest.mark.integration


@pytest.fixture
def worker_module(redis_url: str, database_url: str, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("DATABASE_URL", database_url)
    import worker.config

    worker.config.get_worker_config.cache_clear()
    import worker.main

    yield importlib.reload(worker.main)
    worker.config.get_worker_config.cache_clear()


def test_worker_settings(worker_module, redis_url: str) -> None:  # type: ignore[no-untyped-def]
    settings = worker_module.WorkerSettings
    assert worker_module.healthcheck in settings.functions
    assert settings.health_check_interval <= 30
    assert settings.redis_settings.database == RedisSettings.from_dsn(redis_url).database


async def test_worker_processes_a_job(worker_module, redis_url: str) -> None:  # type: ignore[no-untyped-def]
    redis_settings = RedisSettings.from_dsn(redis_url)
    pool = await create_pool(redis_settings)
    await pool.flushdb()
    job = await pool.enqueue_job("healthcheck")
    assert job is not None
    worker = Worker(
        functions=[worker_module.healthcheck],
        redis_settings=redis_settings,
        burst=True,
        poll_delay=0.05,
        handle_signals=False,
    )
    await worker.main()
    await worker.close()
    assert await job.result(timeout=5) == "ok"
    await pool.aclose()


class _FlakyProcessor:
    def __init__(self) -> None:
        self.failed: list[str] = []

    async def process(self, document_id, patient_id) -> str:  # type: ignore[no-untyped-def]
        raise ConnectionError("transient")

    async def mark_failed(self, document_id, patient_id, reason: str) -> None:  # type: ignore[no-untyped-def]
        self.failed.append(reason)


async def test_process_document_retries_then_marks_failed(worker_module) -> None:  # type: ignore[no-untyped-def]
    from arq import Retry

    processor = _FlakyProcessor()
    ids = (str(uuid.uuid4()), str(uuid.uuid4()))
    for attempt in range(1, worker_module.MAX_TRIES):
        with pytest.raises(Retry):
            await worker_module.process_document(
                {"document_processor": processor, "job_try": attempt}, *ids
            )
    assert processor.failed == []
    result = await worker_module.process_document(
        {"document_processor": processor, "job_try": worker_module.MAX_TRIES}, *ids
    )
    assert result == "failed"
    assert processor.failed == ["processing_error"]
    assert worker_module.WorkerSettings.max_tries == worker_module.MAX_TRIES
    assert worker_module.process_document in worker_module.WorkerSettings.functions
