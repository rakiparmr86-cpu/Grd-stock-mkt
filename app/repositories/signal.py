from __future__ import annotations

from sqlalchemy import select

from app.models.history import Signal
from app.repositories.base import BaseRepository


class SignalRepository(BaseRepository[Signal]):
    model = Signal

    def list_filtered(
        self, *, ticker: str | None = None, run_id: int | None = None, limit: int = 100,
    ) -> list[Signal]:
        stmt = select(Signal).order_by(Signal.triggered_at.desc()).limit(limit)
        if ticker:
            stmt = stmt.where(Signal.ticker == ticker.upper())
        if run_id is not None:
            stmt = stmt.where(Signal.run_id == run_id)
        return list(self.db.execute(stmt).scalars())
