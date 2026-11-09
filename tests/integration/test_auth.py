"""M2: registration, login, protected route, logout."""

import pytest
from httpx import AsyncClient

from tests.helpers import CSRF, PASSWORD, login, register, register_and_login

pytestmark = pytest.mark.integration


async def test_register_login_me_logout_flow(client: AsyncClient) -> None:
    created = await register(client, "asha@example.com")
    assert created.status_code == 201

    logged_in = await login(client, "ASHA@example.com ")
    assert logged_in.status_code == 200
    assert logged_in.json()["id"] == created.json()["id"]
    assert "token" not in logged_in.text  # token only travels in the httpOnly cookie

    me = await client.get("/api/v1/patient/me")
    assert me.status_code == 200
    assert me.json() == created.json()

    out = await client.post("/api/v1/auth/logout", headers=CSRF)
    assert out.status_code == 204
    assert (await client.get("/api/v1/patient/me")).status_code == 401


async def test_login_cookie_is_httponly_secure_samesite_lax(client: AsyncClient) -> None:
    response = await register_and_login(client, "cookie@example.com")
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("rk_access=")
    for attribute in ("httponly", "secure", "samesite=lax", "path=/", "max-age=1800"):
        assert attribute in cookie


async def test_duplicate_email_is_rejected_case_insensitively(client: AsyncClient) -> None:
    assert (await register(client, "dup@example.com")).status_code == 201
    response = await register(client, "DUP@Example.com")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_wrong_password_and_unknown_email_get_identical_errors(
    client: AsyncClient,
) -> None:
    await register(client, "known@example.com")
    wrong = await login(client, "known@example.com", "not-the-right-password")
    unknown = await login(client, "nobody@example.com", PASSWORD)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"] == "invalid_credentials"
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert "set-cookie" not in wrong.headers


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": PASSWORD},
        {"email": "short@example.com", "password": "Tiny9!pass"},
        {"email": "long@example.com", "password": "x" * 129},
        {"email": "extra@example.com", "password": PASSWORD, "is_admin": True},
    ],
    ids=["bad-email", "short-password", "long-password", "unknown-field"],
)
async def test_register_validation_errors_use_schema_and_never_echo_input(
    client: AsyncClient, payload: dict[str, object]
) -> None:
    response = await client.post("/api/v1/auth/register", json=payload, headers=CSRF)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]
    assert all(set(d) == {"loc", "msg", "type"} for d in error["details"])
    assert str(payload["password"]) not in response.text


async def test_logout_without_session_is_idempotent(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/logout", headers=CSRF)
    assert response.status_code == 204
