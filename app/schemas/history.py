from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.common import ORMModel


class SignalOut(ORMModel):
    id: int
    run_id: int | None
    rule_id: int | None
    ticker: str
    signal_type: str
    strength: float
    price: float | None
    triggered_at: datetime
    detail: dict[str, Any]


class ReportOut(ORMModel):
    id: int
    run_id: int | None
    ticker: str | None
    title: str
    summary: str | None
    html_path: str | None
    pdf_path: str | None
    payload: dict[str, Any]
    created_at: datetime


class RunOut(ORMModel):
    id: int
    trigger: str
    strategy_id: int | None
    watchlist_id: int | None
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    context: dict[str, Any]
