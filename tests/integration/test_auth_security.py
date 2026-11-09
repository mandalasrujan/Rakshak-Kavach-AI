"""M2 security: unauthenticated and cross-site rejection, token abuse, rate limits, log hygiene."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

from app.core.config import ACCESS_COOKIE_NAME
from app.core.security import PATIENT_AUDIENCE, TOKEN_ISSUER
from app.main import create_app
from tests.conftest import FRONTEND_ORIGIN, TEST_JWT_SECRET
from tests.helpers import CSRF, PASSWORD, login, register, register_and_login

pytestmark = pytest.mark.integration
ME = "/api/v1/patient/me"


def _token(patient_id: str, **overrides: object) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": patient_id,
        "jti": uuid.uuid4().hex,
        "iss": TOKEN_ISSUER,
        "aud": PATIENT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    claims.update(overrides)
    return jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")


# --- unauthenticated access -------------------------------------------------------------


async def test_protected_route_rejects_missing_cookie(client: AsyncClient) -> None:
    response = await client.get(ME)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize("value", ["garbage", "a.b.c", ""])
async def test_protected_route_rejects_malformed_cookie(client: AsyncClient, value: str) -> None:
    client.cookies.set(ACCESS_COOKIE_NAME, value)
    assert (await client.get(ME)).status_code == 401


async def test_expired_token_is_rejected(client: AsyncClient) -> None:
    created = (await register(client, "expired@example.com")).json()
    past = int((datetime.now(UTC) - timedelta(seconds=5)).timestamp())
    client.cookies.set(ACCESS_COOKIE_NAME, _token(created["id"], exp=past))
    assert (await client.get(ME)).status_code == 401


async def test_bearer_header_is_not_accepted(client: AsyncClient) -> None:
    created = (await register(client, "bearer@example.com")).json()
    response = await client.get(ME, headers={"Authorization": f"Bearer {_token(created['id'])}"})
    assert response.status_code == 401


async def test_token_for_deleted_patient_is_rejected(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    await register_and_login(client, "gone@example.com")
    async with app.state.engine.begin() as conn:
        await conn.execute(text("DELETE FROM patients"))
    assert (await client.get(ME)).status_code == 401


async def test_revoked_token_cannot_be_replayed_after_logout(client: AsyncClient) -> None:
    await register_and_login(client, "replay@example.com")
    stolen = client.cookies.get(ACCESS_COOKIE_NAME)
    assert stolen
    assert (await client.post("/api/v1/auth/logout", headers=CSRF)).status_code == 204
    client.cookies.set(ACCESS_COOKIE_NAME, stolen)
    assert (await client.get(ME)).status_code == 401


async def test_patient_only_sees_own_account(client: AsyncClient) -> None:
    asha = (await register(client, "asha.own@example.com")).json()
    await register_and_login(client, "ravi.own@example.com")
    me = (await client.get(ME)).json()
    assert me["email"] == "ravi.own@example.com"
    assert me["id"] != asha["id"]


# --- cross-site / CSRF --------------------------------------------------------------------


async def test_state_changing_request_without_csrf_header_is_rejected(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/register", json={"email": "csrf@example.com", "password": PASSWORD}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_rejected"


@pytest.mark.parametrize(
    "headers",
    [{"Origin": "https://evil.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}],
    ids=["foreign-origin", "null-origin", "sec-fetch-cross-site"],
)
async def test_cross_site_calls_are_rejected(client: AsyncClient, headers: dict[str, str]) -> None:
    await register_and_login(client, f"xsite-{uuid.uuid4().hex[:6]}@example.com")
    me = await client.get(ME, headers=headers)
    assert me.status_code == 403
    login_attempt = await client.post(
        "/api/v1/auth/login",
        json={"email": "x@example.com", "password": PASSWORD},
        headers={**CSRF, **headers},
    )
    assert login_attempt.status_code == 403


async def test_same_site_frontend_origin_is_accepted(client: AsyncClient) -> None:
    await register_and_login(client, "frontend@example.com")
    response = await client.get(
        ME, headers={"Origin": FRONTEND_ORIGIN, "Sec-Fetch-Site": "same-site"}
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


async def test_cors_preflight_only_allows_frontend_origin(client: AsyncClient) -> None:
    preflight = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-csrf-protection",
    }
    evil = await client.options(
        "/api/v1/auth/login", headers={"Origin": "https://evil.example", **preflight}
    )
    assert "access-control-allow-origin" not in evil.headers
    good = await client.options(
        "/api/v1/auth/login", headers={"Origin": FRONTEND_ORIGIN, **preflight}
    )
    assert good.status_code == 200
    assert good.headers["access-control-allow-origin"] == FRONTEND_ORIGIN


# --- rate limiting ------------------------------------------------------------------------


async def _client_for(app) -> AsyncClient:  # type: ignore[no-untyped-def]
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver")


async def test_login_is_rate_limited_per_email(settings_factory) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings_factory(login_max_attempts_per_email=3))
    async with app.router.lifespan_context(app), await _client_for(app) as http:
        await app.state.redis.flushdb()
        async with app.state.engine.begin() as conn:
            await conn.execute(text("TRUNCATE patients"))
        await register(http, "limited@example.com")
        statuses = [
            (await login(http, "limited@example.com", "wrong-password-xx")).status_code
            for _ in range(3)
        ]
        blocked = await login(http, "limited@example.com")  # even the right password
    assert statuses == [401, 401, 401]
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["Retry-After"]) > 0


async def test_login_is_rate_limited_per_ip(settings_factory) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings_factory(login_max_attempts_per_ip=2))
    async with app.router.lifespan_context(app), await _client_for(app) as http:
        await app.state.redis.flushdb()
        first = await login(http, "a@example.com")
        second = await login(http, "b@example.com")
        third = await login(http, "c@example.com")
    assert [first.status_code, second.status_code, third.status_code] == [401, 401, 429]


async def test_successful_login_resets_email_counter(settings_factory) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings_factory(login_max_attempts_per_email=2))
    async with app.router.lifespan_context(app), await _client_for(app) as http:
        await app.state.redis.flushdb()
        async with app.state.engine.begin() as conn:
            await conn.execute(text("TRUNCATE patients"))
        await register(http, "reset@example.com")
        await login(http, "reset@example.com", "wrong-password-xx")
        assert (await login(http, "reset@example.com")).status_code == 200
        assert (await login(http, "reset@example.com", "wrong-password-xx")).status_code == 401
        assert (await login(http, "reset@example.com")).status_code == 200


async def test_registration_is_rate_limited_per_ip(settings_factory) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings_factory(register_max_attempts_per_ip=1))
    async with app.router.lifespan_context(app), await _client_for(app) as http:
        await app.state.redis.flushdb()
        async with app.state.engine.begin() as conn:
            await conn.execute(text("TRUNCATE patients"))
        assert (await register(http, "r1@example.com")).status_code == 201
        assert (await register(http, "r2@example.com")).status_code == 429


async def test_auth_fails_closed_when_redis_is_down(settings_factory) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings_factory(redis_url="redis://127.0.0.1:1/0"))
    async with app.router.lifespan_context(app), await _client_for(app) as http:
        login_response = await login(http, "down@example.com")
        http.cookies.set(ACCESS_COOKIE_NAME, _token(str(uuid.uuid4())))
        me = await http.get(ME)
    assert login_response.status_code == 503
    assert me.status_code == 503


# --- log hygiene --------------------------------------------------------------------------


async def test_auth_flow_never_logs_email_password_or_token(client: AsyncClient) -> None:
    email = "private.person@example.com"
    with capture_logs(processors=[merge_contextvars]) as logs:
        await register(client, email)
        await login(client, email, "wrong-password-xx")
        await login(client, email)
        await client.get(ME)
        await client.post("/api/v1/auth/logout", headers=CSRF)
    token = client.cookies.get(ACCESS_COOKIE_NAME) or ""
    dumped = repr(logs)
    assert logs, "expected structured log events"
    assert email not in dumped
    assert PASSWORD not in dumped
    assert "wrong-password-xx" not in dumped
    assert not token or token not in dumped
    events = {entry["event"] for entry in logs}
    assert {
        "auth.register.succeeded",
        "auth.login.failed",
        "auth.login.succeeded",
        "http.request",
    } <= events
    assert all("request_id" in e for e in logs)
