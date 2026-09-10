"""Application settings, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_name: str = "grd-stk-mkt"
    env: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"

    # Postgres / Timescale
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "grd"
    postgres_password: str = "grd"
    postgres_db: str = "grd_stk_mkt"
    database_url: str | None = None

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "grd_documents"

    # Embeddings / LLM
    embeddings_provider: Literal["openai", "local"] = "local"
    embeddings_model: str = "text-embedding-3-small"
    embeddings_dim: int = 1536
    llm_provider: Literal["openai", "local"] = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""

    # Market data
    market_data_provider: Literal["nse", "excel", "csv", "api"] = "csv"
    market_data_api_url: str = ""
    market_data_api_key: str = ""
    market_data_dir: str = "./data/market"

    # Input layer (pluggable connectors → market data / document library)
    documents_dir: str = "./data/documents"
    ocr_backend: Literal["stub", "tesseract", "api"] = "stub"
    ocr_lang: str = "eng"
    crawler_user_agent: str = "GrdStkMktCrawler/1.0"
    crawler_default_delay_seconds: float = 1.0

    # Notifications
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "alerts@grd-stk-mkt.local"
    smtp_tls: bool = False
    notify_default_channel: Literal["email"] = "email"

    # Reports
    reports_dir: str = "./data/reports"
    reports_enable_pdf: bool = False

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
