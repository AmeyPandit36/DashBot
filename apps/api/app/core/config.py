"""Application configuration.

All settings are environment-driven. Nothing secret is ever shipped to the
frontend: the Gemini key and storage credentials live only in this process.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", API_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core -----------------------------------------------------------
    APP_NAME: str = "Agentic BI"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # --- Security -------------------------------------------------------
    SECRET_KEY: str = "dev-only-insecure-secret-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    AUTH_COOKIE_NAME: str = "abi_session"
    COOKIE_SECURE: bool = False
    COOKIE_DOMAIN: str | None = None
    PASSWORD_MIN_LENGTH: int = 8
    RATE_LIMIT_PER_MINUTE: int = 240
    LOGIN_RATE_LIMIT_PER_MINUTE: int = 20

    # --- Persistence ----------------------------------------------------
    # Production: postgresql+psycopg2://user:pass@host:5432/agentic_bi
    DATABASE_URL: str = f"sqlite:///{API_ROOT / 'data' / 'agentic_bi.db'}"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE_SECONDS: int = 1800

    # --- Storage --------------------------------------------------------
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    STORAGE_LOCAL_ROOT: str = str(API_ROOT / "data" / "storage")
    S3_BUCKET: str | None = None
    S3_REGION: str | None = None
    S3_ENDPOINT_URL: str | None = None
    S3_ACCESS_KEY_ID: str | None = None
    S3_SECRET_ACCESS_KEY: str | None = None

    # --- DuckDB analytical layer ---------------------------------------
    DUCKDB_MEMORY_LIMIT: str = "1GB"
    DUCKDB_THREADS: int = 2
    QUERY_TIMEOUT_SECONDS: float = 15.0
    QUERY_ROW_LIMIT: int = 5000
    MAX_UPLOAD_BYTES: int = 50 * 1024 * 1024
    MAX_EXCEL_SHEETS: int = 25

    # --- Background processing -----------------------------------------
    REDIS_URL: str | None = None
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None
    USE_CELERY: bool = False
    JOB_MAX_RETRIES: int = 2

    # --- AI -------------------------------------------------------------
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "text-embedding-004"
    GEMINI_TIMEOUT_SECONDS: float = 45.0
    GEMINI_MAX_RETRIES: int = 2
    LLM_ENABLED: bool = True
    EMBEDDING_DIM: int = 256
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # --- Tenancy / defaults --------------------------------------------
    DEFAULT_ORGANIZATION_NAME: str = "My organisation"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins(self) -> list[str]:
        origins = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        return origins or ["http://localhost:3000"]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def llm_configured(self) -> bool:
        return bool(self.GEMINI_API_KEY) and self.LLM_ENABLED

    @property
    def storage_root(self) -> Path:
        return Path(self.STORAGE_LOCAL_ROOT)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
