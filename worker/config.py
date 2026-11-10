"""Worker configuration. Read from environment variables only."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    redis_url: str
    database_url: str
    storage_backend: Literal["local"] = "local"
    storage_local_path: str = "./storage"
    max_pdf_pages: int = Field(default=50, ge=1, le=1000)


@lru_cache
def get_worker_config() -> WorkerConfig:
    return WorkerConfig()  # type: ignore[call-arg]
