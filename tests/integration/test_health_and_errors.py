"""M1: /health, request IDs, error schema, security headers."""

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.main import create_app

pytestmark = pytest.mark.integration


async def test_health_ok_with_request_id(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}
    assert len(response.headers["X-Request-ID"]) == 32
    assert response.headers["X-Content-Type-Options"] == "nosniff"


async def test_valid_request_id_is_propagated_and_invalid_one_replaced(
    client: AsyncClient,
) -> None:
    ok = await client.get("/health", headers={"X-Request-ID": "trace-abc_123.4"})
    assert ok.headers["X-Request-ID"] == "trace-abc_123.4"
    bad = await client.get("/health", headers={"X-Request-ID": "bad id\n<script>"})
    assert bad.headers["X-Request-ID"] != "bad id\n<script>"
    assert len(bad.headers["X-Request-ID"]) == 32


async def test_not_found_uses_error_schema(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist", headers={"X-Request-ID": "rid-404"})
    assert response.status_code == 404
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "request_id": "rid-404"}
    }


async def test_health_reports_503_when_redis_unavailable(settings_factory) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings_factory(redis_url="redis://127.0.0.1:1/0"))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://testserver") as http:
            response = await http.get("/health")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "ok", "redis": "unavailable"}


async def test_unhandled_exception_returns_generic_500(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    boom = APIRouter()

    @boom.get("/api/v1/_boom")
    async def _boom() -> None:
        raise RuntimeError("internal detail with possible PHI")

    app.include_router(boom)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://testserver") as http:
            response = await http.get("/api/v1/_boom", headers={"X-Request-ID": "rid-500"})
    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "Internal server error.",
            "request_id": "rid-500",
        }
    }
    assert "PHI" not in response.text
    assert response.headers["X-Request-ID"] == "rid-500"


async def test_openapi_is_served_under_api_v1(client: AsyncClient) -> None:
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {
        "/health",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/patient/me",
    } <= set(paths)
