"""ohlcv.source: widen VARCHAR(32) -> VARCHAR(255)

Uploaded-file sources are "csv:<12-hex-prefix>_<original filename>" (or the
excel/http_api equivalents) — routinely longer than 32 chars, which made a
real upload fail its entire batch insert with StringDataRightTruncation.

Revision ID: 0004_ohlcv_source_width
Revises: 0003_user_username
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_ohlcv_source_width"
down_revision: str | None = "0003_user_username"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("ohlcv", "source", type_=sa.String(255), existing_type=sa.String(32))


def downgrade() -> None:
    op.alter_column("ohlcv", "source", type_=sa.String(32), existing_type=sa.String(255))
