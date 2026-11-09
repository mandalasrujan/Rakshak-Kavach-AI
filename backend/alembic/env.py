"""Async Alembic environment. Migrations run as the owner role (MIGRATION_DATABASE_URL)."""

import asyncio
import os

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app import models  # noqa: F401  (registers all tables on Base.metadata)
from app.core.logging import configure_logging
from app.db.base import Base

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    url = (
        config.attributes.get("database_url")
        or os.environ.get("MIGRATION_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )
    if not url:
        raise RuntimeError("Set MIGRATION_DATABASE_URL (or DATABASE_URL) to run migrations")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_database_url(), hide_parameters=True)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if not config.attributes.get("skip_logging_config"):
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
