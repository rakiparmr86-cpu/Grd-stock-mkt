"""Fundamental Analyst agent.

Pulls the latest ``Fundamental`` row for the ticker and scores valuation /
profitability / leverage. Degrades to "no data" cleanly when fundamentals are
absent. When enough history exists (>= 4 periods, e.g. from an ingested
Screener-style statement — see ``app.services.inputs.excel``), also runs the
calculation engine's data-driven trend + forecast over revenue/net income —
a statistical cross-check on top of the single-period valuation score above,
not a replacement for it.
"""

from __future__ import annotations

import time

from sqlalchemy import select

from app.agents._common import advance_plan, make_decision
from app.agents.llm import get_llm
from app.agents.state import AnalysisState
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.market import Fundamental
from app.services.calculations.ratios import full_ratio_report
from app.services.calculations.scenario import fiscal_year_labels
from app.services.calculations.statistics import full_report
from app.services.market_data.repository import (
    load_fundamentals_frame,
    load_fundamentals_frame_full,
)

log = get_logger(__name__)

_MIN_PERIODS_FOR_TREND = 4
_TREND_METRICS = ("revenue", "net_income")

_PROMPT = """You are a fundamental analyst. Summarize the financial health of
{ticker} in 3-4 bullets given: {metrics}. End with valuation stance
(cheap/fair/expensive)."""


def _latest_fundamental(ticker: str) -> Fundamental | None:
    with session_scope() as db:
        row = db.execute(
            select(Fundamental)
            .where(Fundamental.ticker == ticker.upper())
            .order_by(Fundamental.reported_at.desc().nullslast(), Fundamental.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is not None:
            db.expunge(row)
        return row


def _score(f: Fundamental) -> tuple[float, list[str]]:
    notes: list[str] = []
    score = 0.0
    if f.pe is not None:
        if f.pe < 15:
            score += 0.25
            notes.append(f"low P/E ({f.pe:.1f})")
        elif f.pe > 40:
            score -= 0.25
            notes.append(f"rich P/E ({f.pe:.1f})")
    if f.debt_to_equity is not None:
        if f.debt_to_equity < 0.5:
            score += 0.2
            notes.append(f"low leverage (D/E {f.debt_to_equity:.2f})")
        elif f.debt_to_equity > 2:
            score -= 0.2
            notes.append(f"high leverage (D/E {f.debt_to_equity:.2f})")
    if f.net_income is not None and f.revenue:
        margin = f.net_income / f.revenue
        score += 0.15 if margin > 0.1 else -0.1
        notes.append(f"net margin {margin:.1%}")
    return max(-1.0, min(1.0, score)), notes


def _history_full_report(ticker: str) -> dict | None:
    """The calculation engine's full report (descriptive stats, growth/CAGR,
    forecast, and — when both are available — a revenue-vs-net-income
    regression) over every ``Fundamental`` row on file for this ticker.

    This is the same structure ``app.services.reports.excel_writeback``
    consumes for the "GRD Calculation" sheet, so a run's report can be
    exported to Excel later without recomputing anything. Returns ``None``
    when there isn't enough history (< 4 periods with real values) on either
    metric to forecast responsibly, rather than a forecast built on too
    little data.
    """
    frame = load_fundamentals_frame(ticker)
    cols = [m for m in _TREND_METRICS
            if m in frame.columns and frame[m].dropna().shape[0] >= _MIN_PERIODS_FOR_TREND]
    if not cols:
        return None
    target, features = (None, None)
    if "net_income" in cols and "revenue" in cols:
        target, features = "net_income", ["revenue"]
    return full_report(frame[cols], target=target, features=features,
                       periods_per_year=1, forecast_periods=5, include_backtest=True)


def _latest_price(state: AnalysisState) -> float | None:
    """Best-effort latest close from the OHLCV tail the orchestrator already
    loaded for this run — used to derive P/E (when the statement has none),
    P/B, and the EV multiples, none of which can be computed from a
    statement alone."""
    records = state.get("price_frame_records") or []
    if not records:
        return None
    close = records[-1].get("close")
    return float(close) if close is not None else None


def _ratio_report(ticker: str, price: float | None) -> dict | None:
    """Margins / Returns / Valuation / Quality ratios (see
    ``app.services.calculations.ratios``) computed over every ``Fundamental``
    row on file, including whatever Balance Sheet / Cash Flow line items
    happen to be in each row's free-form ``metrics``. Returns ``None`` when
    there's no fundamentals data at all — individual ratios still degrade
    gracefully (``insufficient_data``) when only some inputs are present."""
    frame = load_fundamentals_frame_full(ticker)
    if frame.empty:
        return None
    return full_ratio_report(frame, price=price)


def _forecast_summary(report: dict, ticker: str) -> dict | None:
    """Flatten ``_history_full_report``'s per-metric sections into the
    {metric: {cagr_pct, trend_direction, forecast_next, confidence_interval_95,
    forecast_path}} shape the web/mobile report views render —
    ``forecast_path`` is one entry per forecasted year (``forecast_periods=5``
    in ``_history_full_report``) with that year's real fiscal-year label
    (e.g. "FY27E", from ``fiscal_year_labels`` — the same labeling
    ``scripts/write_grd_calculation.py`` uses for the Excel multi-year
    outlook, not a generic "Y1"/"Y2"), value, 95% CI, and YoY % versus the
    prior year (the last *actual* value for year 1, chained
    forecast-over-forecast after that). Skips metrics that turned out to lack
    enough data even though the report as a whole ran."""
    frame = load_fundamentals_frame(ticker)
    _, year_label_fn = fiscal_year_labels(str(frame.index[-1]) if len(frame) else "")
    out: dict[str, dict] = {}
    for metric, sections in report.get("metrics", {}).items():
        fc = sections.get("forecast", {})
        if fc.get("insufficient_data"):
            continue
        trend = sections.get("growth_trend", {})
        points, cis = fc["forecast"], fc["confidence_intervals"]
        prev = float(frame[metric].dropna().iloc[-1]) if metric in frame.columns else None
        path = []
        for year, (val, ci) in enumerate(zip(points, cis, strict=True), start=1):
            yoy_pct = (val - prev) / prev * 100 if prev else None
            path.append({"year": year, "period": year_label_fn(year), "value": val,
                        "ci_low": ci["low"], "ci_high": ci["high"], "yoy_pct": yoy_pct})
            prev = val
        out[metric] = {
            "cagr_pct": trend.get("cagr_pct"),
            "latest_yoy_pct": trend.get("latest_yoy_pct"),
            "trend_direction": trend.get("trend_direction"),
            "forecast_next": points[0],
            "confidence_interval_95": cis[0],
            "forecast_path": path,
        }
    return out or None


def _forecast_bullets(forecast: dict) -> list[str]:
    bullets = []
    for metric, f in forecast.items():
        label = metric.replace("_", " ")
        cagr = f.get("cagr_pct")
        cagr_txt = f"{cagr:.1f}% CAGR" if cagr is not None else "CAGR n/a"
        path_txt = ", ".join(
            f"{p['period']} {p['value']:,.0f}"
            + (f" ({p['yoy_pct']:+.1f}% YoY)" if p["yoy_pct"] is not None else "")
            for p in f["forecast_path"]
        )
        bullets.append(
            f"{label}: {cagr_txt} historical, trending {f['trend_direction']} — "
            f"5-year forecast: {path_txt}"
        )
    return bullets


def fundamental_analyst_node(state: AnalysisState) -> AnalysisState:
    t0 = time.time()
    ticker = state.get("ticker", "")
    f = _latest_fundamental(ticker)

    if f is None:
        finding = {
            "agent": "fundamental_analyst",
            "stance": "no_data",
            "score": 0.0,
            "bullets": ["No fundamentals on file for this ticker."],
            "narrative": "",
        }
        dec = make_decision("fundamental_analyst", 2, {"ticker": ticker}, finding,
                            "no fundamentals", int((time.time() - t0) * 1000))
        return {"findings": [finding],
                "next_agent": advance_plan(state, "fundamental_analyst"),
                "decisions": [dec]}

    score, notes = _score(f)
    stance = "cheap" if score > 0.2 else "expensive" if score < -0.2 else "fair"
    metrics = {"period": f.period, "pe": f.pe, "eps": f.eps, "revenue": f.revenue,
               "net_income": f.net_income, "debt_to_equity": f.debt_to_equity, **f.metrics}
    narrative = get_llm().invoke(_PROMPT.format(ticker=ticker, metrics=metrics)).content

    fundamentals_report = _history_full_report(ticker)
    forecast = _forecast_summary(fundamentals_report, ticker) if fundamentals_report else None
    if forecast:
        notes = [*notes, *_forecast_bullets(forecast)]
    ratio_report = _ratio_report(ticker, _latest_price(state))

    finding = {
        "agent": "fundamental_analyst",
        "stance": stance,
        "score": round(score, 3),
        "bullets": notes,
        "narrative": narrative,
        "period": f.period,
        "forecast": forecast,
        "fundamentals_report": fundamentals_report,
        "ratio_report": ratio_report,
    }
    log.info("fundamental_analyst %s -> %s (%.2f)", ticker, stance, score)
    dec = make_decision("fundamental_analyst", 2, {"metrics": metrics}, finding,
                        f"stance={stance} score={score:.2f}",
                        int((time.time() - t0) * 1000))
    return {"findings": [finding],
            "next_agent": advance_plan(state, "fundamental_analyst"),
            "decisions": [dec]}
