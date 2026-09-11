from __future__ import annotations

from sqlalchemy import select

from app.models.history import Report
from app.repositories.base import BaseRepository


class ReportRepository(BaseRepository[Report]):
    model = Report

    def list_filtered(
        self, *, ticker: str | None = None, run_id: int | None = None, limit: int = 50,
    ) -> list[Report]:
        stmt = select(Report).order_by(Report.id.desc()).limit(limit)
        if ticker:
            stmt = stmt.where(Report.ticker == ticker.upper())
        if run_id is not None:
            stmt = stmt.where(Report.run_id == run_id)
        return list(self.db.execute(stmt).scalars())
