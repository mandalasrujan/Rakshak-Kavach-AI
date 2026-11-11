"""Application settings, loaded from environment variables only (no hardcoded secrets)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ACCESS_COOKIE_NAME = "rk_access"
SHARE_COOKIE_NAME = "rk_share"  # doctor session; path-scoped to /api/v1/share
CSRF_HEADER_NAME = "X-CSRF-Protection"
REQUEST_ID_HEADER = "X-Request-ID"
_MIN_SECRET_LENGTH = 32
# Fixed by the `chunks.embedding vector(768)` column; changing it needs a migration.
EMBEDDING_DIMENSION = 768


class LLMSettings(BaseSettings):
    """Provider settings shared by the API and the worker (configuration stays centralized)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: Literal["gemini", "fake"] = "gemini"
    gemini_api_key: SecretStr | None = None
    gemini_chat_model: str | None = None
    gemini_embedding_model: str | None = None
    llm_timeout_seconds: float = Field(default=30, gt=0, le=300)

    @field_validator("gemini_api_key", "gemini_chat_model", "gemini_embedding_model", mode="before")
    @classmethod
    def _placeholders_are_unset(cls, value: object) -> object:
        if isinstance(value, str) and (not value.strip() or value.strip().startswith("<")):
            return None  # .env.example placeholders count as "not configured"
        return value


def reject_fake_llm_in_production(app_env: str, llm_provider: str) -> None:
    if app_env == "production" and llm_provider == "fake":
        raise ValueError("LLM_PROVIDER=fake is for offline development and tests only")


class Settings(LLMSettings):
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

    rag_top_k: int = Field(default=6, ge=1, le=20)
    rag_min_similarity: float = Field(default=0.2, ge=0, le=1)
    ask_max_per_hour: int = Field(default=60, ge=1)

    share_max_expiry_minutes: int = Field(default=1440, ge=10, le=10080)
    doctor_session_minutes: int = Field(default=30, ge=5, le=120)
    share_pin_max_attempts: int = Field(default=5, ge=1, le=10)
    share_exchange_max_per_ip: int = Field(default=20, ge=1)
    share_exchange_window_seconds: int = Field(default=900, ge=1)

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
        reject_fake_llm_in_production(self.app_env, self.llm_provider)
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
