import pytest
from pydantic import ValidationError

from app.core.config import Settings
from tests.conftest import TEST_JWT_SECRET

BASE = {
    "database_url": "postgresql+asyncpg://u:p@localhost:5432/db",
    "redis_url": "redis://localhost:6379/0",
    "jwt_secret_key": TEST_JWT_SECRET,
}


def build(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{**BASE, **overrides})  # type: ignore[arg-type]


def test_valid_settings_and_secure_defaults() -> None:
    settings = build()
    assert settings.cookie_secure is True
    assert settings.access_token_expire_minutes == 30
    assert settings.access_token_ttl_seconds == 1800
    assert TEST_JWT_SECRET not in repr(settings)  # SecretStr hides the value


@pytest.mark.parametrize(
    "secret", ["too-short", "change-me-generate-a-long-random-secret-0123456789"]
)
def test_weak_or_placeholder_jwt_secret_rejected(secret: str) -> None:
    with pytest.raises(ValidationError):
        build(jwt_secret_key=secret)


def test_non_async_database_url_rejected() -> None:
    with pytest.raises(ValidationError):
        build(database_url="postgresql://u:p@localhost/db")


def test_insecure_cookie_allowed_only_outside_production() -> None:
    assert build(cookie_secure=False).cookie_secure is False
    with pytest.raises(ValidationError):
        build(app_env="production", cookie_secure=False, frontend_origin="https://x.example")


def test_production_requires_https_frontend_origin() -> None:
    with pytest.raises(ValidationError):
        build(app_env="production", frontend_origin="http://x.example")
    assert build(app_env="production", frontend_origin="https://x.example/").frontend_origin == (
        "https://x.example"
    )


def test_missing_required_settings_fail() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
