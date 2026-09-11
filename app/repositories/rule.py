from __future__ import annotations

from sqlalchemy import select

from app.models.config import Rule
from app.repositories.base import BaseRepository


class RuleRepository(BaseRepository[Rule]):
    model = Rule

    def list_for_strategy(self, strategy_id: int | None = None) -> list[Rule]:
        stmt = select(Rule)
        if strategy_id is not None:
            stmt = stmt.where(Rule.strategy_id == strategy_id)
        return list(self.db.execute(stmt).scalars())

    def list_active(self, strategy_id: int | None = None) -> list[Rule]:
        stmt = select(Rule).where(Rule.is_active.is_(True))
        if strategy_id is not None:
            stmt = stmt.where(Rule.strategy_id == strategy_id)
        return list(self.db.execute(stmt).scalars())
