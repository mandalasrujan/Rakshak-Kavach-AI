"""Application settings, loaded from environment variables only (no hardcoded secrets)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ACCESS_COOKIE_NAME = "rk_access"
CSRF_HEADER_NAME = "X-CSRF-Protection"
REQUEST_ID_HEADER = "X-Request-ID"
_MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    database_url: str
    redis_url: str

    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=5, le=1440)

    # DEVELOPMENT ONLY when false; rejected in production (see validator below).
    cookie_secure: bool = True
    frontend_origin: str = "http://localhost:5173"

    storage_backend: Literal["local"] = "local"
    storage_local_path: str = "./storage"
    max_upload_mb: int = Field(default=10, ge=1, le=100)

    login_max_attempts_per_email: int = Field(default=5, ge=1)
    login_max_attempts_per_ip: int = Field(default=20, ge=1)
    login_window_seconds: int = Field(default=900, ge=1)
    register_max_attempts_per_ip: int = Field(default=10, ge=1)
    register_window_seconds: int = Field(default=3600, ge=1)

    @field_validator("database_url")
    @classmethod
    def _async_postgres_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// scheme")
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def _strong_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < _MIN_SECRET_LENGTH:
            raise ValueError(f"JWT_SECRET_KEY must be at least {_MIN_SECRET_LENGTH} characters")
        if "change-me" in secret.lower():
            raise ValueError("JWT_SECRET_KEY still contains the .env.example placeholder")
        return value

    @field_validator("frontend_origin")
    @classmethod
    def _origin_format(cls, value: str) -> str:
        value = value.rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("FRONTEND_ORIGIN must be an http(s) origin")
        return value

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.app_env == "production":
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE=false is development-only")
            if not self.frontend_origin.startswith("https://"):
                raise ValueError("FRONTEND_ORIGIN must use https in production")
        return self

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def access_token_ttl_seconds(self) -> int:
        return self.access_token_expire_minutes * 60


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
