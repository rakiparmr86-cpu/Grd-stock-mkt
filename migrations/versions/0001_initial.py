"""initial schema + timescale hypertables

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-09

This first migration creates the tables that existed when it was authored, and
enables the TimescaleDB extension when available, promoting ``ohlcv`` and
``indicator_points`` to hypertables. It builds from ``Base.metadata`` but is
**pinned to an explicit table list** (``_OWNED_TABLES``) rather than "whatever
Base.metadata has right now" — models added later (e.g. ``input_sources`` in
``0002``) must NOT be picked up here, or this migration and the one that adds
them both try to create the same table. Later schema changes should use
``alembic revision --autogenerate`` (see docs/DATABASE.md) and create their own
tables — never widen ``_OWNED_TABLES``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.models import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HYPERTABLES = (("ohlcv", "ts"), ("indicator_points", "ts"))

# The schema as of this revision. Frozen on purpose — see module docstring.
_OWNED_TABLES = {
    "users",
    "watchlists", "watchlist_items",
    "strategies", "rules", "thresholds", "schedules",
    "instruments", "ohlcv", "fundamentals", "indicator_points",
    "analysis_runs", "signals", "reports", "alerts", "agent_decisions",
}


def _owned_tables() -> list[sa.Table]:
    return [t for name, t in Base.metadata.tables.items() if name in _OWNED_TABLES]


def upgrade() -> None:
    bind = op.get_bind()

    timescale = False
    try:
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
        timescale = True
    except Exception:  # pragma: no cover - plain postgres / no superuser
        pass

    Base.metadata.create_all(bind=bind, tables=_owned_tables())

    if timescale:
        for table, time_col in _HYPERTABLES:
            bind.execute(
                sa.text(
                    f"SELECT create_hypertable('{table}', '{time_col}', "
                    "if_not_exists => TRUE, migrate_data => TRUE)"
                )
            )


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=_owned_tables())
