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
