"""Add ingestion_runs.ticker

Lets the "did this upload ever get analyzed" tracker correlate an upload
with any Analysis run for the same ticker, without having to re-derive it
from the connector config JSON at read time.

Revision ID: 0007_ingestion_run_ticker
Revises: 0006_ingestion_runs
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_ingestion_run_ticker"
down_revision: str | None = "0006_ingestion_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ingestion_runs", sa.Column("ticker", sa.String(32), nullable=True))
    op.create_index("ix_ingestion_runs_ticker", "ingestion_runs", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_runs_ticker", table_name="ingestion_runs")
    op.drop_column("ingestion_runs", "ticker")
