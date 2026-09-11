"""Generic repository base — a thin, typed wrapper around a SQLAlchemy Session.

Convention (see docs/DATABASE.md and docs/TECHNICAL.md §15):

* One repository per **aggregate root**, not per table. A repo takes a
  ``Session`` in its constructor — never opens its own.
* **Repositories never commit.** ``add``/``delete`` stage the change and
  ``flush()`` (so a new PK is available), but the caller — a route (via the
  shared ``DbSession``), a Celery task (via ``session_scope``), or a service —
  owns the transaction boundary.
* Repos return ORM models. Converting to a Pydantic response schema happens at
  the API boundary (``app/schemas/``), not here.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Subclass and set ``model``. Add domain-specific query methods there —
    this base only covers the generic get/list/add/delete every repo needs."""

    model: type[ModelT]

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, ident: object) -> ModelT | None:
        """Fetch by primary key, or ``None``."""
        return self.db.get(self.model, ident)

    def list(
        self,
        *where: ColumnElement[bool],
        order_by: object = None,
        limit: int | None = None,
    ) -> Sequence[ModelT]:
        stmt = select(self.model)
        if where:
            stmt = stmt.where(*where)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        if limit is not None:
            stmt = stmt.limit(limit)
        return self.db.execute(stmt).scalars().all()

    def add(self, obj: ModelT) -> ModelT:
        """Stage + flush (so ``obj.id`` is populated). Does **not** commit."""
        self.db.add(obj)
        self.db.flush()
        return obj

    def delete(self, obj: ModelT) -> None:
        self.db.delete(obj)
