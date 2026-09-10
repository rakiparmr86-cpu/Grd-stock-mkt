from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ── Watchlist ────────────────────────────────────────────────────────
class WatchlistItemIn(BaseModel):
    ticker: str
    exchange: str = "NSE"
    weight: float = 1.0


class WatchlistItemOut(ORMModel):
    id: int
    ticker: str
    exchange: str
    weight: float


class WatchlistCreate(BaseModel):
    name: str
    description: str | None = None
    items: list[WatchlistItemIn] = Field(default_factory=list)


class WatchlistOut(ORMModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    items: list[WatchlistItemOut]


# ── Strategy / Rule ─────────────────────────────────────────────────
class RuleCreate(BaseModel):
    name: str
    signal_type: Literal["buy", "sell", "alert"] = "buy"
    expression: dict[str, Any]
    priority: int = 100
    cooldown_minutes: int = 0
    is_active: bool = True


class RuleOut(ORMModel):
    id: int
    strategy_id: int
    name: str
    signal_type: str
    expression: dict[str, Any]
    priority: int
    cooldown_minutes: int
    is_active: bool


class StrategyCreate(BaseModel):
    name: str
    description: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    thresholds: dict[str, float] = Field(default_factory=dict)
    rules: list[RuleCreate] = Field(default_factory=list)


class StrategyOut(ORMModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    params: dict[str, Any]
    rules: list[RuleOut]
