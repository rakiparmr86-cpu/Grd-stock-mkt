from __future__ import annotations

from sqlalchemy import select

from app.models.inputs import InputSource
from app.repositories.base import BaseRepository


class InputSourceRepository(BaseRepository[InputSource]):
    model = InputSource

    def by_name(self, name: str) -> InputSource | None:
        return self.db.execute(
            select(InputSource).where(InputSource.name == name)
        ).scalar_one_or_none()

    def list_all(self) -> list[InputSource]:
        return list(self.db.execute(select(InputSource).order_by(InputSource.id)).scalars())

    def list_active_ids(self) -> list[int]:
        return list(self.db.execute(
            select(InputSource.id).where(InputSource.is_active.is_(True))
        ).scalars())

    def list_active_scheduled(self) -> list[InputSource]:
        stmt = select(InputSource).where(
            InputSource.is_active.is_(True), InputSource.schedule_cron.is_not(None)
        )
        return list(self.db.execute(stmt).scalars())
