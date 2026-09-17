"""Unified activity feed — merges recent rows from every history table
(analysis runs, agent decisions, signals, reports, alerts, input-source runs)
into one time-sorted list, so the frontend has a single place to show "what
is going on in the project right now" instead of a different tab per table.

Polled, not pushed: there's no websocket/SSE infrastructure in this project,
so "real-time" here means the frontend re-fetches this endpoint on an
interval (same pattern ``TaskWatcher`` already uses for task polling).

One real limitation, called out rather than hidden: ``InputSource`` only
ever stores its *latest* run (``last_run_at``/``last_status``/``last_stats``)
— there's no per-run history table for input sources the way there is for
analysis runs. So an input source contributes at most one activity entry
(its most recent run), not a full history, until such a table exists.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter

from app.api.deps import (
    AgentDecisionRepo,
    AlertRepo,
    InputSourceRepo,
    ReportRepo,
    RunRepo,
    SignalRepo,
)

router = APIRouter()


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _run_events(runs) -> list[dict[str, Any]]:
    events = []
    for r in runs:
        ticker = (r.context or {}).get("ticker")
        events.append({
            "id": f"run-start:{r.id}", "type": "run_started", "at": _iso(r.started_at),
            "ticker": ticker, "run_id": r.id,
            "title": f"Run #{r.id} started ({ticker or 'unknown ticker'})",
            "detail": f"trigger={r.trigger}",
            "status": "running",
        })
        if r.finished_at:
            outcome = (r.context or {}).get("outcome")
            reason = (r.context or {}).get("reason")
            detail = f"status={r.status}"
            if outcome:
                detail += f", outcome={outcome}"
            if reason:
                detail += f", reason={reason}"
            if r.error:
                detail += f", error={r.error}"
            events.append({
                "id": f"run-finish:{r.id}", "type": "run_finished", "at": _iso(r.finished_at),
                "ticker": ticker, "run_id": r.id,
                "title": f"Run #{r.id} finished ({ticker or 'unknown ticker'})",
                "detail": detail,
                "status": r.status,
            })
    return events


def _decision_events(decisions, ticker_by_run: dict[int, str | None]) -> list[dict[str, Any]]:
    events = []
    for d in decisions:
        agent_label = d.agent.replace("_", " ").title()
        events.append({
            "id": f"decision:{d.id}", "type": "agent_decision", "at": _iso(d.created_at),
            "ticker": ticker_by_run.get(d.run_id), "run_id": d.run_id,
            "title": f"{agent_label} — run #{d.run_id}, step {d.step}",
            "detail": (d.rationale or "decision recorded")
            + (f" ({d.latency_ms} ms)" if d.latency_ms is not None else ""),
            "status": "ok",
        })
    return events


def _signal_events(signals) -> list[dict[str, Any]]:
    return [{
        "id": f"signal:{s.id}", "type": "signal", "at": _iso(s.triggered_at),
        "ticker": s.ticker, "run_id": s.run_id,
        "title": f"{s.signal_type.upper()} signal — {s.ticker}",
        "detail": f"strength={s.strength:.2f}" + (f", price={s.price}" if s.price else ""),
        "status": s.signal_type,
    } for s in signals]


def _report_events(reports) -> list[dict[str, Any]]:
    return [{
        "id": f"report:{r.id}", "type": "report", "at": _iso(r.created_at),
        "ticker": r.ticker, "run_id": r.run_id,
        "title": f"Report generated — {r.ticker or 'unknown ticker'}",
        "detail": r.summary or r.title,
        "status": "ok",
    } for r in reports]


def _alert_events(alerts) -> list[dict[str, Any]]:
    return [{
        "id": f"alert:{a.id}", "type": "alert", "at": _iso(a.created_at),
        "ticker": None, "run_id": None,
        "title": f"Alert {a.status} via {a.channel}",
        "detail": f"to {a.recipient}" + (f" — {a.error}" if a.error else ""),
        "status": a.status,
    } for a in alerts]


def _input_source_events(sources) -> list[dict[str, Any]]:
    events = []
    for s in sources:
        if not s.last_run_at:
            continue
        detail = f"connector={s.connector}"
        if s.last_stats:
            detail += f", {s.last_stats}"
        if s.last_error:
            detail += f", error={s.last_error}"
        events.append({
            "id": f"input:{s.id}", "type": "input_source", "at": _iso(s.last_run_at),
            "ticker": None, "run_id": None,
            "title": f"Input source \"{s.name}\" — {s.last_status or 'unknown'}",
            "detail": detail,
            "status": s.last_status,
        })
    return events


@router.get("")
def list_activity(
    runs: RunRepo, decisions: AgentDecisionRepo, signals: SignalRepo,
    reports: ReportRepo, alerts: AlertRepo, sources: InputSourceRepo,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Every event type's own query is capped at ``limit`` before merging, so
    a burst in one table (e.g. many agent decisions in one run) can't crowd
    out everything else — the final merged+sorted list is then also capped
    at ``limit``."""
    recent_runs = runs.list_recent(limit)
    ticker_by_run = {r.id: (r.context or {}).get("ticker") for r in recent_runs}

    events = [
        *_run_events(recent_runs),
        *_decision_events(decisions.list_recent(limit), ticker_by_run),
        *_signal_events(signals.list_filtered(limit=limit)),
        *_report_events(reports.list_filtered(limit=limit)),
        *_alert_events(alerts.list(order_by=alerts.model.created_at.desc(), limit=limit)),
        *_input_source_events(sources.list_all()),
    ]
    events = [e for e in events if e["at"] is not None]
    events.sort(key=lambda e: e["at"], reverse=True)
    return events[:limit]
