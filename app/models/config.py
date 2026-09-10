"""Configuration DB: watchlists, strategies, rules, thresholds, schedules."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Watchlist(Base, TimestampMixin):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan"
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), index=True
    )
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    exchange: Mapped[str] = mapped_column(String(16), default="NSE")
    weight: Mapped[float] = mapped_column(default=1.0)

    watchlist: Mapped[Watchlist] = relationship(back_populates="items")


class Strategy(Base, TimestampMixin):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # free-form knobs the calculation + agent layers read
    params: Mapped[dict] = mapped_column(JSONB, default=dict)

    rules: Mapped[list["Rule"]] = relationship(
        back_populates="strategy", cascade="all, delete-orphan"
    )
    thresholds: Mapped[list["Threshold"]] = relationship(
        back_populates="strategy", cascade="all, delete-orphan"
    )


class Rule(Base, TimestampMixin):
    """A dynamic rule evaluated by the signal engine.

    ``expression`` is a small JSON AST, e.g.::

        {"op": "and", "args": [
            {"op": "lt", "left": {"indicator": "rsi_14"}, "right": {"const": 30}},
            {"op": "cross_up", "left": {"indicator": "ema_20"},
             "right": {"indicator": "ema_50"}}
        ]}
    """

    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    signal_type: Mapped[str] = mapped_column(String(16), default="buy")  # buy | sell | alert
    expression: Mapped[dict] = mapped_column(JSONB)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=0)

    strategy: Mapped[Strategy] = relationship(back_populates="rules")


class Threshold(Base):
    __tablename__ = "thresholds"
    __table_args__ = (UniqueConstraint("strategy_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[float] = mapped_column()

    strategy: Mapped[Strategy] = relationship(back_populates="thresholds")


class Schedule(Base, TimestampMixin):
    """Named schedule consumed by Celery Beat (see app.workers.beat_schedule)."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    task: Mapped[str] = mapped_column(String(200))  # dotted celery task path
    cron: Mapped[str] = mapped_column(String(64))  # "*/15 9-16 * * 1-5"
    args: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
