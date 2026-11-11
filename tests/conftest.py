"""Shared fixtures.

Integration tests use TEST_DATABASE_URL / TEST_REDIS_URL when set (CI service containers or
local services). Otherwise they start pgvector/pgvector:pg16 and redis via Testcontainers.
If neither is possible they are skipped with an explicit reason.
"""

import os
import signal
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

# Windows does not define POSIX signals like SIGUSR1, which arq.Worker.close() references.
if not hasattr(signal, "SIGUSR1"):
    signal.SIGUSR1 = getattr(signal, "SIGTERM", 15)  # type: ignore[attr-defined]

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings
from app.db.app_role import ensure_app_login_role
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]
TEST_JWT_SECRET = "test-only-jwt-secret-not-used-anywhere-else-0123456789"
TEST_APP_ROLE = "rakshak_test_app"
FRONTEND_ORIGIN = "https://app.example.com"


def alembic_config(database_url: str) -> Config:
    cfg = Config(str(ROOT / "backend" / "alembic.ini"))
    cfg.attributes["database_url"] = database_url
    cfg.attributes["skip_logging_config"] = True
    return cfg


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        yield url
        return
    try:
        from testcontainers.postgres import PostgresContainer

        container = PostgresContainer("pgvector/pgvector:pg16", driver="asyncpg")
        container.start()
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable: set TEST_DATABASE_URL or run Docker ({exc!r})")
    try:
        yield container.get_connection_url()
    finally:
        container.stop()


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    url = os.environ.get("TEST_REDIS_URL")
    if url:
        yield url
        return
    try:
        from testcontainers.redis import RedisContainer

        container = RedisContainer("redis:7.4-alpine")
        container.start()
    except Exception as exc:
        pytest.skip(f"Redis unavailable: set TEST_REDIS_URL or run Docker ({exc!r})")
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/15"
    finally:
        container.stop()


@pytest.fixture(scope="session")
def migrated_database_url(database_url: str) -> str:
    """Owner URL (migrations, test assertions). The owner bypasses RLS; the app never uses it."""
    command.upgrade(alembic_config(database_url), "head")
    return database_url


@pytest.fixture(scope="session")
def app_database_url(migrated_database_url: str) -> str:
    """URL of a non-owner LOGIN role in `rakshak_app`, exactly as production connects."""
    import asyncio
    import secrets

    password = secrets.token_urlsafe(24)
    asyncio.run(ensure_app_login_role(migrated_database_url, TEST_APP_ROLE, password))
    url = make_url(migrated_database_url).set(username=TEST_APP_ROLE, password=password)
    return url.render_as_string(hide_password=False)


@pytest.fixture
async def admin_engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "jwt_secret_key": TEST_JWT_SECRET,
        "frontend_origin": FRONTEND_ORIGIN,
        "cookie_secure": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def settings_factory(app_database_url: str, redis_url: str, tmp_path: Path):  # type: ignore[no-untyped-def]
    def factory(**overrides: object) -> Settings:
        values = {
            "database_url": app_database_url,
            "llm_provider": "fake",
            "redis_url": redis_url,
            "storage_local_path": str(tmp_path / "storage"),
            **overrides,
        }
        return make_settings(**values)

    return factory


@pytest.fixture
def settings(settings_factory) -> Settings:  # type: ignore[no-untyped-def]
    return settings_factory()


async def reset_state(app) -> None:  # type: ignore[no-untyped-def]
    """Truncate via the owner engine (the app role has no TRUNCATE privilege)."""
    async with app.state.admin_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE patients, audit_log CASCADE"))
    await app.state.redis.flushdb()


@pytest.fixture
async def app(settings: Settings, admin_engine: AsyncEngine):  # type: ignore[no-untyped-def]
    application = create_app(settings)
    application.state.admin_engine = admin_engine  # test-only handle for assertions
    async with application.router.lifespan_context(application):
        await reset_state(application)
        yield application


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://testserver") as http:
        yield http


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncIterator[Redis]:
    redis = Redis.from_url(redis_url, decode_responses=True)
    try:
        yield redis
    finally:
        await redis.aclose()


@pytest.fixture(scope="session")
def synthetic_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The deterministic synthetic PDFs from scripts/generate_synthetic_pdfs.py."""
    from scripts.generate_synthetic_pdfs import generate

    out = tmp_path_factory.mktemp("synthetic")
    generate(out)
    return out
