"""End-to-end pipeline for one ticker:

    load OHLCV → calculation engine → rule/signal engine
        └─ if a signal fires → LangGraph agents → report renderer → persistence
                                   └─ returns report + alert intent

Used by the Celery analysis tasks and by the ``POST /runs`` API endpoint.
"""

from __future__ import annotations

from typing import Any

from app.agents.graph import run_analysis
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.history import AgentDecision, Report, Signal
from app.repositories.agent_decision import AgentDecisionRepository
from app.repositories.report import ReportRepository
from app.repositories.rule import RuleRepository
from app.repositories.run import AnalysisRunRepository
from app.repositories.signal import SignalRepository
from app.repositories.strategy import StrategyRepository
from app.services.calculations.engine import compute_indicators
from app.services.market_data.repository import load_ohlcv_frame, upsert_indicator_points
from app.services.reports.renderer import render_report
from app.services.signals.engine import SignalEngine

log = get_logger(__name__)


def _active_rules(db, strategy_id: int | None) -> tuple[list, dict[str, Any]]:
    rules = RuleRepository(db).list_active(strategy_id)
    params: dict[str, Any] = {}
    if strategy_id is not None:
        strat = StrategyRepository(db).get(strategy_id)
        if strat:
            params = {"name": strat.name, **(strat.params or {})}
    return rules, params


def analyze_ticker(
    ticker: str,
    *,
    run_id: int | None = None,
    strategy_id: int | None = None,
    interval: str = "1d",
    persist: bool = True,
    force_agents: bool = False,
) -> dict[str, Any]:
    ticker = ticker.upper()
    frame = load_ohlcv_frame(ticker, interval=interval)
    if frame.empty or len(frame) < 30:
        log.warning("insufficient OHLCV for %s (%d rows)", ticker, len(frame))
        return {"ticker": ticker, "status": "skipped", "reason": "insufficient_data"}

    calc = compute_indicators(frame)
    with session_scope() as db:
        rules, strategy_params = _active_rules(db, strategy_id)

    engine = SignalEngine(rules)
    result = engine.evaluate(ticker, calc.latest, calc.frame)
    fired = [s for s in result.signals if s.get("matched")]

    out: dict[str, Any] = {
        "ticker": ticker,
        "status": "ok",
        "indicators": calc.latest,
        "signals": fired,
        "agent_run": None,
        "report": None,
    }

    if persist:
        upsert_indicator_points(ticker, calc.frame, interval=interval)

    if not fired and not force_agents:
        out["status"] = "no_signal"
        return out

    tail = calc.frame.tail(260).reset_index().rename(columns={"index": "ts"})
    records = [
        {**{k: (None if r[k] != r[k] else r[k]) for k in tail.columns}}  # NaN->None
        for _, r in tail.iterrows()
    ]

    agent_state = run_analysis({
        "run_id": run_id or 0,
        "ticker": ticker,
        "strategy_params": strategy_params,
        "signals": fired,
        "indicators": calc.latest,
        "price_frame_records": records,
    })
    out["agent_run"] = {
        "risk_review": agent_state.get("risk_review"),
        "decisions": agent_state.get("decisions", []),
    }

    payload = agent_state.get("report_payload") or {}
    rendered = render_report(payload, slug=ticker.lower()) if payload else {}
    out["report"] = {**payload, **rendered}

    if persist and run_id is not None:
        _persist(run_id, ticker, fired, agent_state, payload, rendered)

    return out


def _persist(run_id, ticker, fired, agent_state, payload, rendered) -> None:
    with session_scope() as db:
        signals = SignalRepository(db)
        for s in fired:
            signals.add(Signal(
                run_id=run_id, rule_id=s.get("rule_id"), ticker=ticker,
                signal_type=s.get("signal_type", "alert"),
                strength=float(s.get("strength", 0.0)), price=s.get("price"),
                detail=s.get("detail", {}),
            ))

        decisions = AgentDecisionRepository(db)
        for i, d in enumerate(agent_state.get("decisions", [])):
            decisions.add(AgentDecision(
                run_id=run_id, agent=d.get("agent", "?"), step=d.get("step", i),
                input=d.get("input", {}), output=d.get("output", {}),
                rationale=d.get("rationale"), latency_ms=d.get("latency_ms"),
            ))

        if payload:
            rec = payload.get("recommendation", {})
            ReportRepository(db).add(Report(
                run_id=run_id, ticker=ticker,
                title=payload.get("title", f"{ticker} report"),
                summary=rec.get("thesis"),
                html_path=rendered.get("html_path"),
                pdf_path=rendered.get("pdf_path"),
                payload={k: v for k, v in payload.items() if k != "chart_b64"},
            ))


def open_run(trigger: str, *, strategy_id=None, watchlist_id=None,
             context: dict | None = None) -> int:
    with session_scope() as db:
        run = AnalysisRunRepository(db).open_run(
            trigger, strategy_id=strategy_id, watchlist_id=watchlist_id, context=context,
        )
        return run.id


def close_run(run_id: int, status: str = "done", error: str | None = None) -> None:
    with session_scope() as db:
        runs = AnalysisRunRepository(db)
        run = runs.get(run_id)
        if run:
            runs.close(run, status=status, error=error)
