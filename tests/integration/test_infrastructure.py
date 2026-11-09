"""M0/M1 infrastructure: pgvector image, Alembic migrations, metadata in sync."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app import models  # noqa: F401
from app.db.base import Base
from tests.conftest import alembic_config

pytestmark = pytest.mark.integration


async def test_pgvector_extension_is_available(migrated_database_url: str) -> None:
    engine = create_async_engine(migrated_database_url)
    async with engine.connect() as conn:
        version = (await conn.execute(text("SHOW server_version_num"))).scalar_one()
        available = (
            await conn.execute(text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"))
        ).scalar_one_or_none()
    await engine.dispose()
    assert int(version) // 10000 == 16
    assert available == 1


def test_migrations_downgrade_and_upgrade(migrated_database_url: str) -> None:
    cfg = alembic_config(migrated_database_url)
    try:
        command.downgrade(cfg, "base")
    finally:
        command.upgrade(cfg, "head")


async def test_models_match_migrations(migrated_database_url: str) -> None:
    engine = create_async_engine(migrated_database_url)
    async with engine.connect() as conn:
        diff = await conn.run_sync(
            lambda sync_conn: compare_metadata(MigrationContext.configure(sync_conn), Base.metadata)
        )
    await engine.dispose()
    assert diff == []
