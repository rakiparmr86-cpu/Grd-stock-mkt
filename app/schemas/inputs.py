from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

Connector = Literal["excel", "csv", "pdf", "image_ocr", "web_crawler", "http_api"]


class InputSourceCreate(BaseModel):
    name: str
    connector: Connector
    kind: Literal["rows", "docs", "auto"] = "auto"
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    schedule_cron: str | None = None


class InputSourceUpdate(BaseModel):
    connector: Connector | None = None
    kind: Literal["rows", "docs", "auto"] | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None
    schedule_cron: str | None = None


class InputSourceOut(ORMModel):
    id: int
    name: str
    connector: str
    kind: str
    config: dict[str, Any]
    is_active: bool
    schedule_cron: str | None
    last_run_at: datetime | None
    last_status: str | None
    last_error: str | None
    last_stats: dict[str, Any]


class InputTestRequest(BaseModel):
    connector: Connector
    config: dict[str, Any] = Field(default_factory=dict)
    max_results: int = 5


class InputRunResponse(BaseModel):
    mode: Literal["async", "sync", "dry_run"]
    task_id: str | None = None
    source_id: int | None = None
    stats: dict[str, Any] | None = None


# ── frontend-driven inputs ─────────────────────────────────────────
class CrawlRequest(BaseModel):
    urls: list[str] = Field(min_length=1)
    max_depth: int = 1
    max_pages: int = 50
    same_domain_only: bool = True
    allowed_domains: list[str] | None = None
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    delay_seconds: float | None = None
    doc_type: str = "web"
    # auth block names ENV VARS, never raw secrets — see DATA_FORMATS.md
    auth: dict[str, Any] | None = None
    # persist as a reusable InputSource instead of a one-off run
    save_as: str | None = None
    schedule_cron: str | None = None
    is_active: bool = True


class UploadItemResult(BaseModel):
    filename: str
    stored_path: str
    connector: str
    kind: Literal["rows", "docs"]
    mode: Literal["ingest_once", "save_source"]
    task_id: str | None = None
    source_id: int | None = None
    error: str | None = None


class UploadResponse(BaseModel):
    items: list[UploadItemResult]
