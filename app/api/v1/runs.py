from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.history import AgentDecision, AnalysisRun
from app.schemas.history import RunOut

router = APIRouter()


class RunRequest(BaseModel):
    ticker: str
    strategy_id: int | None = None
    notify_to: str | None = None
    force_agents: bool = False
    async_: bool = True


@router.get("", response_model=list[RunOut])
def list_runs(db: DbSession, limit: int = 50) -> list[AnalysisRun]:
    return list(
        db.execute(select(AnalysisRun).order_by(AnalysisRun.id.desc()).limit(limit)).scalars()
    )


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: DbSession) -> AnalysisRun:
    run = db.get(AnalysisRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run


@router.get("/{run_id}/decisions")
def get_run_decisions(run_id: int, db: DbSession) -> list[dict]:
    rows = db.execute(
        select(AgentDecision).where(AgentDecision.run_id == run_id).order_by(AgentDecision.step)
    ).scalars()
    return [
        {"agent": d.agent, "step": d.step, "rationale": d.rationale,
         "output": d.output, "latency_ms": d.latency_ms}
        for d in rows
    ]


@router.post("", status_code=202)
def trigger_run(payload: RunRequest) -> dict:
    """Kick off analysis for one ticker. Async by default (Celery)."""
    if payload.async_:
        from app.workers.tasks.analysis import analyze_ticker_task

        task = analyze_ticker_task.delay(
            payload.ticker, strategy_id=payload.strategy_id,
            notify_to=payload.notify_to, force_agents=payload.force_agents,
        )
        return {"mode": "async", "task_id": task.id}

    from app.services.orchestrator import analyze_ticker, close_run, open_run

    run_id = open_run("manual", strategy_id=payload.strategy_id,
                      context={"ticker": payload.ticker})
    try:
        result = analyze_ticker(payload.ticker, run_id=run_id,
                                strategy_id=payload.strategy_id,
                                force_agents=payload.force_agents)
        close_run(run_id, "done")
    except Exception as exc:  # noqa: BLE001
        close_run(run_id, "error", str(exc))
        raise HTTPException(500, str(exc)) from exc
    return {"mode": "sync", "run_id": run_id, "result": result}
