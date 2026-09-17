from __future__ import annotations

from sqlalchemy import select

from app.models.history import ExceptionLog
from app.repositories.base import BaseRepository


class ExceptionLogRepository(BaseRepository[ExceptionLog]):
    model = ExceptionLog

    def list_recent(self, limit: int = 100) -> list[ExceptionLog]:
        stmt = select(ExceptionLog).order_by(ExceptionLog.created_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars())
