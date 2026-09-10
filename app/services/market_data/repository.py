"""Persistence helpers for OHLCV / indicator points (plain SQLAlchemy upserts)."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.market import IndicatorPoint, OHLCV

log = get_logger(__name__)


def upsert_ohlcv(df: pd.DataFrame, *, interval: str = "1d") -> int:
    """``df`` is a normalized frame (index=ts, cols incl. ticker/open/.../volume)."""
    if df.empty:
        return 0
    rows = []
    for ts, r in df.iterrows():
        rows.append({
            "ticker": str(r["ticker"]).upper(),
            "interval": interval,
            "ts": ts.to_pydatetime(),
            "open": float(r["open"]), "high": float(r["high"]),
            "low": float(r["low"]), "close": float(r["close"]),
            "volume": float(r.get("volume", 0) or 0),
            "source": str(r.get("source", "unknown")),
        })
    with session_scope() as db:
        stmt = pg_insert(OHLCV).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "interval", "ts"],
            set_={c: stmt.excluded[c] for c in ("open", "high", "low", "close",
                                                "volume", "source")},
        )
        db.execute(stmt)
    log.info("upserted %d OHLCV rows (%s)", len(rows), rows[0]["ticker"])
    return len(rows)


def load_ohlcv_frame(ticker: str, *, interval: str = "1d", limit: int = 750) -> pd.DataFrame:
    with session_scope() as db:
        stmt = (
            select(OHLCV)
            .where(OHLCV.ticker == ticker.upper(), OHLCV.interval == interval)
            .order_by(OHLCV.ts.desc())
            .limit(limit)
        )
        rows = list(db.execute(stmt).scalars())
    if not rows:
        return pd.DataFrame(columns=["ticker", "open", "high", "low", "close", "volume"])
    data = [
        {"ts": r.ts, "ticker": r.ticker, "open": float(r.open), "high": float(r.high),
         "low": float(r.low), "close": float(r.close), "volume": float(r.volume)}
        for r in reversed(rows)
    ]
    return pd.DataFrame(data).set_index("ts")


def upsert_indicator_points(
    ticker: str, frame: pd.DataFrame, *, interval: str = "1d",
    names: list[str] | None = None,
) -> int:
    cols = names or [c for c in frame.columns
                     if c not in {"ticker", "open", "high", "low", "close", "volume",
                                  "source"}]
    rows = []
    for ts, r in frame.iterrows():
        for name in cols:
            val = r.get(name)
            if pd.isna(val):
                continue
            rows.append({"ticker": ticker.upper(), "interval": interval, "name": name,
                         "ts": ts.to_pydatetime(), "value": float(val), "extra": {}})
    if not rows:
        return 0
    with session_scope() as db:
        stmt = pg_insert(IndicatorPoint).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "interval", "name", "ts"],
            set_={"value": stmt.excluded["value"]},
        )
        db.execute(stmt)
    return len(rows)
