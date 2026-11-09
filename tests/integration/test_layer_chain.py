"""M1 acceptance: one request creates a row through router -> service -> repository -> model."""

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from tests.helpers import PASSWORD, register

pytestmark = pytest.mark.integration


async def test_request_creates_row_through_every_layer(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    response = await register(client, "Layer.Chain@Example.com")
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "created_at"}
    assert body["email"] == "layer.chain@example.com"

    async with app.state.engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT id, email, password_hash FROM patients WHERE email = :e"),
                {"e": "layer.chain@example.com"},
            )
        ).one()
    assert str(row.id) == body["id"]
    assert row.password_hash.startswith("$argon2id$")
    assert PASSWORD not in row.password_hash
