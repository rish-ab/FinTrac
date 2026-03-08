import os
from pathlib import Path

# =============================================================
# src/config.py
#
# Single source of truth for all configuration values.
#
# HOW IT WORKS:
# pydantic-settings reads your .env file and maps each variable
# to a typed Python attribute. If a required variable is missing
# from .env, the app crashes at startup with a clear error —
# better than a cryptic failure 10 minutes into a request.
#
# HOW TO USE IT:
# Never import os.environ directly anywhere in the codebase.
# Always import settings from here:
#
#   from src.config import settings
#   url = settings.OLLAMA_BASE_URL
#
# This means if you rename an env variable, you change it in
# one place (here) and the rest of the codebase is unaffected.
# =============================================================

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # ── OLLAMA (local AI) ──────────────────────────────────────
    OLLAMA_MODEL:       str = "mistral"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_BASE_URL:    str = "http://host.docker.internal:11434"

    # ── MARIADB ────────────────────────────────────────────────
    DB_USER:            str = "fintrac_user"
    DB_PASSWORD:        str = "changeme"
    DB_NAME:            str = "fintrac"
    DB_HOST:            str = "mariadb"
    DB_PORT:            int = 3306

    # Assembled from parts so docker-compose env vars map cleanly
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # ── REDIS ──────────────────────────────────────────────────
    REDIS_URL:          str = "redis://redis:6379/0"

    # ── APP ────────────────────────────────────────────────────
    APP_ENV:            str = "development"     # development | production
    LOG_LEVEL:          str = "INFO"

    # Tells pydantic-settings to read from .env file
    # extra="ignore" means unknown .env variables don't cause errors
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


# Single instance imported everywhere
settings = Settings()