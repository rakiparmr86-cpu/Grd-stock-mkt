from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.history import Signal
from app.schemas.history import SignalOut

router = APIRouter()


@router.get("", response_model=list[SignalOut])
def list_signals(db: DbSession, ticker: str | None = None, run_id: int | None = None,
                 limit: int = 100) -> list[Signal]:
    q = select(Signal).order_by(Signal.triggered_at.desc()).limit(limit)
    if ticker:
        q = q.where(Signal.ticker == ticker.upper())
    if run_id is not None:
        q = q.where(Signal.run_id == run_id)
    return list(db.execute(q).scalars())
