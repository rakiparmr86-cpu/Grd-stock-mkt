"""Market data: instruments, OHLCV time series, fundamentals, indicator points.

OHLCV and IndicatorPoint are meant to be TimescaleDB hypertables. The Alembic
migration calls ``create_hypertable`` on them; plain PostgreSQL still works
(they are ordinary tables without the extension).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Instrument(Base, TimestampMixin):
    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("ticker", "exchange"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    exchange: Mapped[str] = mapped_column(String(16), default="NSE")
    name: Mapped[str | None] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(120))
    isin: Mapped[str | None] = mapped_column(String(12), index=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class OHLCV(Base):
    __tablename__ = "ohlcv"
    __table_args__ = (UniqueConstraint("ticker", "interval", "ts"),)

    # ``ts`` is part of the primary key (composite id+ts) because TimescaleDB
    # requires every unique index / PK on a hypertable to include the
    # partitioning column — create_hypertable() rejects a bare `id` PK.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    interval: Mapped[str] = mapped_column(String(8), default="1d")  # 1m,5m,15m,1h,1d
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, index=True)
    open: Mapped[float] = mapped_column(Numeric(18, 4))
    high: Mapped[float] = mapped_column(Numeric(18, 4))
    low: Mapped[float] = mapped_column(Numeric(18, 4))
    close: Mapped[float] = mapped_column(Numeric(18, 4))
    volume: Mapped[float] = mapped_column(Numeric(20, 2), default=0)
    source: Mapped[str | None] = mapped_column(String(32))


class Fundamental(Base, TimestampMixin):
    __tablename__ = "fundamentals"
    __table_args__ = (UniqueConstraint("ticker", "period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    period: Mapped[str] = mapped_column(String(16))  # FY2024, Q1FY25, ...
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # normalized headline numbers; anything else goes in ``metrics``
    revenue: Mapped[float | None] = mapped_column(Float)
    net_income: Mapped[float | None] = mapped_column(Float)
    eps: Mapped[float | None] = mapped_column(Float)
    pe: Mapped[float | None] = mapped_column(Float)
    debt_to_equity: Mapped[float | None] = mapped_column(Float)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)


class IndicatorPoint(Base):
    __tablename__ = "indicator_points"
    __table_args__ = (UniqueConstraint("ticker", "interval", "name", "ts"),)

    # see OHLCV.ts — composite id+ts PK so create_hypertable() accepts it.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    interval: Mapped[str] = mapped_column(String(8), default="1d")
    name: Mapped[str] = mapped_column(String(48), index=True)  # rsi_14, macd, ema_20 ...
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, index=True)
    value: Mapped[float] = mapped_column(Float)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)  # e.g. macd signal/hist
