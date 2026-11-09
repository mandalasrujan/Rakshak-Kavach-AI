"""Small HTTP helpers for auth tests."""

from httpx import AsyncClient, Response

CSRF = {"X-CSRF-Protection": "1"}
PASSWORD = "correct-horse-battery-staple"


async def register(client: AsyncClient, email: str, password: str = PASSWORD) -> Response:
    return await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}, headers=CSRF
    )


async def login(client: AsyncClient, email: str, password: str = PASSWORD) -> Response:
    return await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}, headers=CSRF
    )


async def register_and_login(client: AsyncClient, email: str) -> Response:
    created = await register(client, email)
    assert created.status_code == 201, created.text
    response = await login(client, email)
    assert response.status_code == 200, response.text
    return response
