"""Create or update the application's LOGIN role (a non-owner member of `rakshak_app`).

Run as the migration owner after `alembic upgrade head`:
    python -m app.db.app_role
Environment: MIGRATION_DATABASE_URL, APP_DB_USER, APP_DB_PASSWORD. The password is never logged.
"""

import asyncio
import os
import re

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.logging import configure_logging

APP_GROUP_ROLE = "rakshak_app"
_ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_MIN_PASSWORD_LENGTH = 16

log = structlog.get_logger(__name__)


async def ensure_app_login_role(owner_url: str, username: str, password: str) -> None:
    if not _ROLE_NAME.fullmatch(username):
        raise ValueError("APP_DB_USER must be a lowercase identifier")
    if len(password) < _MIN_PASSWORD_LENGTH or "change-me" in password:
        raise ValueError(
            f"APP_DB_PASSWORD must be {_MIN_PASSWORD_LENGTH}+ chars, not a placeholder"
        )
    engine = create_async_engine(owner_url, hide_parameters=True)
    try:
        async with engine.begin() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_roles WHERE rolname = :name"), {"name": username}
            )
            verb = "ALTER" if exists else "CREATE"
            # format(%I, %L) quotes the identifier and password server-side (no SQL injection).
            statement = await conn.scalar(
                text(
                    f"SELECT format('{verb} ROLE %I WITH LOGIN NOSUPERUSER NOBYPASSRLS "
                    "NOCREATEDB NOCREATEROLE INHERIT PASSWORD %L', "
                    "CAST(:name AS text), CAST(:password AS text))"
                ),
                {"name": username, "password": password},
            )
            await conn.exec_driver_sql(statement)
            grant = await conn.scalar(
                text(f"SELECT format('GRANT {APP_GROUP_ROLE} TO %I', CAST(:name AS text))"),
                {"name": username},
            )
            await conn.exec_driver_sql(grant)
            owned = await conn.scalar(
                text("SELECT count(*) FROM pg_tables WHERE tableowner = :name"), {"name": username}
            )
            if owned:
                raise RuntimeError("the application role must not own any tables")
    finally:
        await engine.dispose()
    log.info("db.app_role_ready", role=username, action=verb.lower())


def main() -> None:
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    owner_url = os.environ.get("MIGRATION_DATABASE_URL")
    username = os.environ.get("APP_DB_USER")
    password = os.environ.get("APP_DB_PASSWORD")
    if not (owner_url and username and password):
        raise SystemExit("MIGRATION_DATABASE_URL, APP_DB_USER and APP_DB_PASSWORD are required")
    asyncio.run(ensure_app_login_role(owner_url, username, password))


if __name__ == "__main__":
    main()
