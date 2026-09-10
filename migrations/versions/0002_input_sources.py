"""input_sources table

Revision ID: 0002_input_sources
Revises: 0001_initial
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_input_sources"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "input_sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("connector", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False, server_default="auto"),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("schedule_cron", sa.String(64), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(16), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("last_stats", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_input_sources_name", "input_sources", ["name"], unique=True)
    op.create_index("ix_input_sources_connector", "input_sources", ["connector"])


def downgrade() -> None:
    op.drop_index("ix_input_sources_connector", table_name="input_sources")
    op.drop_index("ix_input_sources_name", table_name="input_sources")
    op.drop_table("input_sources")
