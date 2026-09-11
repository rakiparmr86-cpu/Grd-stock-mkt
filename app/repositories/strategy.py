from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.config import Strategy
from app.repositories.base import BaseRepository


class StrategyRepository(BaseRepository[Strategy]):
    model = Strategy

    def list_with_rules(self) -> list[Strategy]:
        stmt = select(Strategy).options(selectinload(Strategy.rules))
        return list(self.db.execute(stmt).scalars())

    def by_name(self, name: str) -> Strategy | None:
        return self.db.execute(
            select(Strategy).where(Strategy.name == name)
        ).scalar_one_or_none()

    def active_id(self) -> int | None:
        """First active strategy's id — used as a default when none is given."""
        return self.db.execute(
            select(Strategy.id).where(Strategy.is_active.is_(True)).limit(1)
        ).scalar_one_or_none()
