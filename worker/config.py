"""Worker configuration. Read from environment variables only."""

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict

from app.core.config import LLMSettings, reject_fake_llm_in_production


class WorkerConfig(LLMSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    redis_url: str = Field(
        default_factory=lambda: os.environ.get("REDIS_URL") or os.environ.get("TEST_REDIS_URL", "")
    )
    database_url: str = Field(
        default_factory=lambda: (
            os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL", "")
        )
    )
    storage_backend: Literal["local"] = "local"
    storage_local_path: str = "./storage"
    max_pdf_pages: int = Field(default=50, ge=1, le=1000)

    @model_validator(mode="after")
    def _production_guards(self) -> "WorkerConfig":
        reject_fake_llm_in_production(self.app_env, self.llm_provider)
        if not self.redis_url:
            raise ValueError("redis_url is required (set REDIS_URL or TEST_REDIS_URL)")
        if not self.database_url:
            raise ValueError("database_url is required (set DATABASE_URL or TEST_DATABASE_URL)")
        return self


@lru_cache
def get_worker_config() -> WorkerConfig:
    return WorkerConfig()  # type: ignore[call-arg]
