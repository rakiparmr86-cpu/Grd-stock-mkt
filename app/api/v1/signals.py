from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SignalRepo
from app.models.history import Signal
from app.schemas.history import SignalOut

router = APIRouter()


@router.get("", response_model=list[SignalOut])
def list_signals(signals: SignalRepo, ticker: str | None = None, run_id: int | None = None,
                 limit: int = 100) -> list[Signal]:
    return signals.list_filtered(ticker=ticker, run_id=run_id, limit=limit)
