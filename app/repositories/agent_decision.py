from __future__ import annotations

from sqlalchemy import select

from app.models.history import AgentDecision
from app.repositories.base import BaseRepository


class AgentDecisionRepository(BaseRepository[AgentDecision]):
    model = AgentDecision

    def list_for_run(self, run_id: int) -> list[AgentDecision]:
        stmt = (
            select(AgentDecision)
            .where(AgentDecision.run_id == run_id)
            .order_by(AgentDecision.step)
        )
        return list(self.db.execute(stmt).scalars())
