from __future__ import annotations

from sqlalchemy import select

from app.models.config import Schedule
from app.repositories.base import BaseRepository


class ScheduleRepository(BaseRepository[Schedule]):
    model = Schedule

    def list_active(self) -> list[Schedule]:
        return list(self.db.execute(
            select(Schedule).where(Schedule.is_active.is_(True))
        ).scalars())
