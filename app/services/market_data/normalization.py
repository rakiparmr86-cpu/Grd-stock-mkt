"""Turn any provider's raw frame into the canonical OHLCV shape.

Canonical columns: ``ticker, ts (tz-aware UTC), open, high, low, close, volume``
indexed by ``ts``.
"""

from __future__ import annotations

import pandas as pd

_ALIASES: dict[str, str] = {
    "date": "ts",
    "datetime": "ts",
    "timestamp": "ts",
    "time": "ts",
    "o": "open",
    "h": "high",
    "l": "low",
    "c": "close",
    "close_price": "close",
    "last": "close",
    "ltp": "close",
    "v": "volume",
    "vol": "volume",
    "traded_qty": "volume",
    "total_traded_quantity": "volume",
    "symbol": "ticker",
    "scrip": "ticker",
}

_REQUIRED = ["ts", "open", "high", "low", "close", "volume"]


def normalize_ohlcv(
    raw: pd.DataFrame,
    *,
    ticker: str | None = None,
    source: str = "unknown",
    tz: str = "UTC",
) -> pd.DataFrame:
    df = raw.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    df = df.rename(columns={k: v for k, v in _ALIASES.items() if k in df.columns})

    if "ticker" not in df.columns:
        if ticker is None:
            raise ValueError("ticker missing from frame and not provided")
        df["ticker"] = ticker

    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"cannot normalize; missing columns after aliasing: {missing}")

    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df["volume"] = df["volume"].fillna(0.0)
    df["source"] = source

    df = (
        df[["ticker", "ts", "open", "high", "low", "close", "volume", "source"]]
        .drop_duplicates(subset=["ticker", "ts"])
        .sort_values("ts")
        .set_index("ts")
    )
    return df
