"""Calculation engine.

Takes a normalized OHLCV frame and a spec of indicators to compute, returns a
tidy frame plus a ``latest`` dict the signal engine can evaluate rules against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.services.calculations import indicators as ind

# Default indicator set — override per strategy via ``params["indicators"]``.
DEFAULT_SPEC: list[dict[str, Any]] = [
    {"fn": "sma", "window": 20},
    {"fn": "sma", "window": 50},
    {"fn": "sma", "window": 200},
    {"fn": "ema", "span": 20},
    {"fn": "ema", "span": 50},
    {"fn": "rsi", "period": 14},
    {"fn": "macd", "fast": 12, "slow": 26, "signal": 9},
    {"fn": "atr", "period": 14},
    {"fn": "volume_ratio", "window": 20},
    {"fn": "returns", "periods": 1},
    {"fn": "returns", "periods": 5},
    {"fn": "volatility", "window": 20},
    {"fn": "bollinger", "window": 20, "num_std": 2.0},
]

_OHLCV_COLS = {"open", "high", "low", "close", "volume"}
_NON_INDICATOR_COLS = {"ticker", "source", "open", "high", "low", "volume"}


@dataclass
class CalculationResult:
    frame: pd.DataFrame          # full history with indicator columns
    latest: dict[str, float]     # last row as {indicator_name: value}
    meta: dict[str, Any] = field(default_factory=dict)


class CalculationEngine:
    def __init__(self, spec: list[dict[str, Any]] | None = None) -> None:
        self.spec = spec or DEFAULT_SPEC

    def run(self, ohlcv: pd.DataFrame) -> CalculationResult:
        missing = _OHLCV_COLS - set(ohlcv.columns)
        if missing:
            raise ValueError(f"OHLCV frame missing columns: {sorted(missing)}")
        df = ohlcv.sort_index().copy()
        close, vol = df["close"], df["volume"]

        for item in self.spec:
            fn = item["fn"]
            if fn == "sma":
                df[f"sma_{item['window']}"] = ind.sma(close, item["window"])
            elif fn == "ema":
                df[f"ema_{item['span']}"] = ind.ema(close, item["span"])
            elif fn == "rsi":
                p = item.get("period", 14)
                df[f"rsi_{p}"] = ind.rsi(close, p)
            elif fn == "macd":
                df = df.join(ind.macd(close, item.get("fast", 12), item.get("slow", 26),
                                      item.get("signal", 9)))
            elif fn == "atr":
                p = item.get("period", 14)
                df[f"atr_{p}"] = ind.atr(df, p)
            elif fn == "volume_ratio":
                w = item.get("window", 20)
                df[f"volume_ratio_{w}"] = ind.volume_ratio(vol, w)
            elif fn == "returns":
                n = item.get("periods", 1)
                df[f"returns_{n}"] = ind.returns(close, n, log=item.get("log", False))
            elif fn == "volatility":
                w = item.get("window", 20)
                df[f"volatility_{w}"] = ind.volatility(close, w, item.get("annualize", 252))
            elif fn == "bollinger":
                df = df.join(ind.bollinger(close, item.get("window", 20),
                                           item.get("num_std", 2.0)))
            else:  # pragma: no cover - guardrail
                raise ValueError(f"unknown indicator fn: {fn!r}")

        latest_row = df.iloc[-1] if len(df) else pd.Series(dtype=float)
        latest = {
            k: (None if pd.isna(v) else float(v))
            for k, v in latest_row.items()
            if k not in _NON_INDICATOR_COLS
        }
        return CalculationResult(frame=df, latest=latest, meta={"rows": len(df)})


def compute_indicators(
    ohlcv: pd.DataFrame, spec: list[dict[str, Any]] | None = None
) -> CalculationResult:
    """Convenience wrapper."""
    return CalculationEngine(spec).run(ohlcv)
