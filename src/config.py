# =============================================================
# src/config.py
# Single source of truth for all configuration values.
# =============================================================

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # ── OLLAMA (local AI) ──────────────────────────────────────
    OLLAMA_MODEL:       str = "mistral"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_BASE_URL:    str = "http://host.docker.internal:11434"

    # ── MARIADB ────────────────────────────────────────────────
    DB_USER:     str = "fintrac_user"
    DB_PASSWORD: str = "changeme"
    DB_NAME:     str = "fintrac"
    DB_HOST:     str = "mariadb"
    DB_PORT:     int = 3306

    @property
    def DATABASE_URL(self) -> str:
        """Sync URL — used by Alembic (not async)"""
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        """Async URL — used by the running FastAPI app (aiomysql driver)"""
        return (
            f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # ── REDIS ──────────────────────────────────────────────────
    REDIS_URL:   str = "redis://redis:6379/0"

    # ── JWT ──────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "dev-secret-change-in-production"

    # ── APP ────────────────────────────────────────────────────
    APP_ENV:     str = "development"
    LOG_LEVEL:   str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()