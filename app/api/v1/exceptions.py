"""Exceptions page: list persisted failures, hard-delete once resolved.

Hard delete is the point — this is a working log to triage and clear, not an
audit trail that must be kept forever (that's what ``AgentDecision`` /
``AnalysisRun`` are for). There's no soft-delete flag or undo.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import DbSession, ExceptionLogRepo
from app.models.history import ExceptionLog

router = APIRouter()


def _out(e: ExceptionLog) -> dict[str, Any]:
    return {
        "id": e.id, "source": e.source, "message": e.message,
        "traceback": e.traceback, "context": e.context,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@router.get("")
def list_exceptions(exceptions: ExceptionLogRepo, limit: int = 100) -> list[dict[str, Any]]:
    return [_out(e) for e in exceptions.list_recent(limit)]


@router.delete("/{exception_id}", status_code=204)
def delete_exception(exception_id: int, db: DbSession, exceptions: ExceptionLogRepo) -> None:
    row = exceptions.get(exception_id)
    if row:
        exceptions.delete(row)
        db.commit()
