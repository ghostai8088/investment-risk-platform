"""Application configuration.

Loaded from the environment only — no secrets in source (BR-10). Defaults are safe,
non-secret development values. ``database_url`` is unused in Step 1D (no schema yet).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_version: str = "0.1.0"
    database_url: str | None = None


settings = Settings()
