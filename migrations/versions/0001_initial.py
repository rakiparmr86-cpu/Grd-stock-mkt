"""initial schema + timescale hypertables

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-09

This first migration creates every table from the SQLAlchemy metadata (so it
never drifts from the models), enables the TimescaleDB extension when available,
and promotes the ``ohlcv`` and ``indicator_points`` tables to hypertables.
Later schema changes should use ``alembic revision --autogenerate``.
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


def upgrade() -> None:
    bind = op.get_bind()

    timescale = False
    try:
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
        timescale = True
    except Exception:  # pragma: no cover - plain postgres / no superuser
        pass

    Base.metadata.create_all(bind=bind)

    if timescale:
        for table, time_col in _HYPERTABLES:
            bind.execute(
                sa.text(
                    f"SELECT create_hypertable('{table}', '{time_col}', "
                    "if_not_exists => TRUE, migrate_data => TRUE)"
                )
            )


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
