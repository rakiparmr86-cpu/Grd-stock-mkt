"""Saved input sources — a connector name + its config, optionally scheduled."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# NOTE: these mirror the server_default values hand-written into
# migrations/versions/0002_input_sources.py. Keep the two in sync — this is
# exactly the drift `alembic check` (see docs/DATABASE.md) is meant to catch.


class InputSource(Base, TimestampMixin):
    __tablename__ = "input_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    connector: Mapped[str] = mapped_column(String(32), index=True)  # registry key
    # "rows" | "docs" | "auto" (let the connector decide from its config)
    kind: Mapped[str] = mapped_column(String(8), default="auto", server_default="auto")
    config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    schedule_cron: Mapped[str | None] = mapped_column(String(64))  # "*/30 * * * *"

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(16))  # ok | error | running
    last_error: Mapped[str | None] = mapped_column(Text)
    last_stats: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
