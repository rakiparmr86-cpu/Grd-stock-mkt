from __future__ import annotations

from sqlalchemy import select

from app.models.history import IngestionRun
from app.repositories.base import BaseRepository


class IngestionRunRepository(BaseRepository[IngestionRun]):
    model = IngestionRun

    def list_recent(self, limit: int = 100) -> list[IngestionRun]:
        stmt = select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars())
