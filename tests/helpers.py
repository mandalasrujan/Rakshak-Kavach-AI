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


async def grant_consent(client: AsyncClient) -> Response:
    notice = await client.get("/api/v1/patient/consent")
    assert notice.status_code == 200, notice.text
    response = await client.post(
        "/api/v1/patient/consent",
        json={"notice_version": notice.json()["notice_version"]},
        headers=CSRF,
    )
    assert response.status_code == 200, response.text
    return response


async def upload(client: AsyncClient, data: bytes, filename: str = "report.pdf") -> Response:
    return await client.post(
        "/api/v1/patient/documents",
        files={"file": (filename, data, "application/pdf")},
        headers=CSRF,
    )


_LOG_METADATA_KEYS = {"request_id", "timestamp", "path", "duration_ms", "status_code", "level"}


def log_content(logs: list[dict[str, object]]) -> str:
    """Log values that could carry content (IDs, timings and paths excluded), so PHI checks do
    not false-positive on random UUIDs or durations that happen to contain the same digits."""
    return " | ".join(
        str(value)
        for entry in logs
        for key, value in entry.items()
        if key not in _LOG_METADATA_KEYS and not key.endswith("_id")
    )
