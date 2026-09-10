"""Shared state passed between LangGraph nodes."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AnalysisState(TypedDict, total=False):
    # ── inputs ────────────────────────────────────────────────
    run_id: int
    ticker: str
    strategy_params: dict[str, Any]
    signals: list[dict[str, Any]]          # from the rule engine
    indicators: dict[str, float]           # calc engine "latest"
    price_frame_records: list[dict[str, Any]]  # tail of OHLCV+indicators for charts

    # ── supervisor routing ───────────────────────────────────
    plan: list[str]                        # ordered analyst names to run
    next_agent: str

    # ── analyst outputs (each appends one dict) ──────────────
    findings: Annotated[list[dict[str, Any]], operator.add]

    # ── downstream ───────────────────────────────────────────
    risk_review: dict[str, Any]
    report_payload: dict[str, Any]

    # ── audit ────────────────────────────────────────────────
    decisions: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
