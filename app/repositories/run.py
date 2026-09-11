from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.models.history import AnalysisRun
from app.repositories.base import BaseRepository


class AnalysisRunRepository(BaseRepository[AnalysisRun]):
    model = AnalysisRun

    def list_recent(self, limit: int = 50) -> list[AnalysisRun]:
        stmt = select(AnalysisRun).order_by(AnalysisRun.id.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars())

    def open_run(
        self, trigger: str, *, strategy_id: int | None = None,
        watchlist_id: int | None = None, context: dict[str, Any] | None = None,
    ) -> AnalysisRun:
        run = AnalysisRun(
            trigger=trigger, strategy_id=strategy_id, watchlist_id=watchlist_id,
            status="running", started_at=datetime.now(timezone.utc), context=context or {},
        )
        return self.add(run)

    def close(self, run: AnalysisRun, *, status: str = "done", error: str | None = None) -> None:
        run.status = status
        run.error = error
        run.finished_at = datetime.now(timezone.utc)
