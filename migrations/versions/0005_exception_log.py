"""Add exception_logs table

Persists unexpected failures (unhandled API exceptions, websocket handler
errors, Celery task failures) so they're queryable/deletable from the
Exceptions page instead of only ever existing as a text log line.

Revision ID: 0005_exception_log
Revises: 0004_ohlcv_source_width
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0005_exception_log"
down_revision: str | None = "0004_ohlcv_source_width"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exception_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("context", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_exception_logs_source", "exception_logs", ["source"])
    op.create_index("ix_exception_logs_created_at", "exception_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_exception_logs_created_at", table_name="exception_logs")
    op.drop_index("ix_exception_logs_source", table_name="exception_logs")
    op.drop_table("exception_logs")
