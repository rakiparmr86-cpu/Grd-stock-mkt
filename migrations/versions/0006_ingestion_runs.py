"""Add ingestion_runs table

Tracks every connector execution — ad-hoc uploads (mode=ingest_once) and
saved-InputSource runs alike — from the moment it's queued, so an in-progress
or one-off ingest shows up in the Activity feed instead of leaving no trace
until (or unless) it's saved as a reusable source.

Revision ID: 0006_ingestion_runs
Revises: 0005_exception_log
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006_ingestion_runs"
down_revision: str | None = "0005_exception_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(64), nullable=True),
        sa.Column(
            "input_source_id", sa.Integer(),
            sa.ForeignKey("input_sources.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("connector", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("stats", JSONB(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ingestion_runs_task_id", "ingestion_runs", ["task_id"])
    op.create_index("ix_ingestion_runs_started_at", "ingestion_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_runs_started_at", table_name="ingestion_runs")
    op.drop_index("ix_ingestion_runs_task_id", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
