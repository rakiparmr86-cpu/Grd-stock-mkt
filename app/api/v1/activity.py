"""Unified activity feed — merges recent rows from every history table
(analysis runs, agent decisions, signals, reports, alerts, ingestion runs)
into one time-sorted list, so the frontend has a single place to show "what
is going on in the project right now" instead of a different tab per table.

Polled, not pushed: there's no websocket/SSE infrastructure in this project,
so "real-time" here means the frontend re-fetches this endpoint on an
interval (same pattern ``TaskWatcher`` already uses for task polling).

Ingestion (uploads, crawls, saved-source runs) is tracked via
``IngestionRun`` rather than reading ``InputSource.last_run_at`` directly —
that field only ever remembers the *latest* run and doesn't exist at all for
an ad-hoc upload (mode=ingest_once), so it used to be the one thing that
never showed up here while in progress or after a one-off run. IngestionRun
covers both cases with a real "running" status while the Celery task is
still executing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter

from app.api.deps import (
    AgentDecisionRepo,
    AlertRepo,
    IngestionRunRepo,
    ReportRepo,
    RunRepo,
    SignalRepo,
)

router = APIRouter()


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _run_events(runs) -> list[dict[str, Any]]:
    """Each run contributes up to two *point-in-time* events — "started" and,
    once it's done, "finished" — not a single row whose status stays live.
    The "started" event's status reflects whether the run has since finished
    (``"started"``) or is still genuinely in flight (``"running"``) — it
    must not just say "running" forever, or a run from days ago reads as
    stuck when it's actually long since complete (its "finished" event, with
    the real outcome, is right there in the feed too)."""
    events = []
    for r in runs:
        ticker = (r.context or {}).get("ticker")
        events.append({
            "id": f"run-start:{r.id}", "type": "run_started", "at": _iso(r.started_at),
            "ticker": ticker, "run_id": r.id,
            "title": f"Run #{r.id} started ({ticker or 'unknown ticker'})",
            "detail": f"trigger={r.trigger}",
            "status": "running" if not r.finished_at else "started",
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


def _ingestion_events(runs) -> list[dict[str, Any]]:
    """Same "started" (point-in-time) / "finished" (final status) pattern as
    ``_run_events`` — a still-running ingest genuinely shows ``"running"``;
    once it completes, that same "started" event flips to ``"started"`` so
    it doesn't read as stuck, and a "finished" event with the real
    ok/error status and stats appears alongside it."""
    events = []
    for r in runs:
        events.append({
            "id": f"ingest-start:{r.id}", "type": "ingestion_started", "at": _iso(r.started_at),
            "ticker": None, "run_id": None,
            "title": f"Ingest \"{r.source_name}\" started",
            "detail": f"connector={r.connector}",
            "status": "running" if not r.finished_at else "started",
        })
        if r.finished_at:
            detail = f"connector={r.connector}"
            if r.stats:
                detail += f", {r.stats}"
            if r.error:
                detail += f", error={r.error}"
            events.append({
                "id": f"ingest-finish:{r.id}", "type": "ingestion_finished",
                "at": _iso(r.finished_at), "ticker": None, "run_id": None,
                "title": f"Ingest \"{r.source_name}\" finished — {r.status}",
                "detail": detail,
                "status": r.status,
            })
    return events


@router.get("")
def list_activity(
    runs: RunRepo, decisions: AgentDecisionRepo, signals: SignalRepo,
    reports: ReportRepo, alerts: AlertRepo, ingestion_runs: IngestionRunRepo,
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
        *_ingestion_events(ingestion_runs.list_recent(limit)),
    ]
    events = [e for e in events if e["at"] is not None]
    events.sort(key=lambda e: e["at"], reverse=True)
    return events[:limit]
