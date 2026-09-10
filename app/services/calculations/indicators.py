"""Vectorised technical indicators.

Every function takes plain pandas Series / DataFrames and returns pandas objects,
so they compose and are trivially unit-testable. No TA-Lib dependency.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "sma",
    "ema",
    "rsi",
    "macd",
    "true_range",
    "atr",
    "volume_ratio",
    "returns",
    "volatility",
    "bollinger",
]


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean().rename(f"sma_{window}")


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean().rename(f"ema_{span}")


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.where(avg_loss != 0.0, 100.0)
    return out.rename(f"rsi_{period}")


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "macd_signal": signal_line, "macd_hist": hist}
    )


def true_range(df: pd.DataFrame) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rename("true_range")


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = true_range(df)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean().rename(f"atr_{period}")


def volume_ratio(volume: pd.Series, window: int = 20) -> pd.Series:
    avg = volume.rolling(window=window, min_periods=window).mean()
    return (volume / avg).rename(f"volume_ratio_{window}")


def returns(series: pd.Series, periods: int = 1, log: bool = False) -> pd.Series:
    if log:
        out = np.log(series / series.shift(periods))
    else:
        out = series.pct_change(periods=periods)
    return out.rename(f"returns_{periods}")


def volatility(series: pd.Series, window: int = 20, annualize: int | None = 252) -> pd.Series:
    daily = returns(series, 1)
    vol = daily.rolling(window=window, min_periods=window).std()
    if annualize:
        vol = vol * np.sqrt(annualize)
    return vol.rename(f"volatility_{window}")


def bollinger(series: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = sma(series, window)
    sd = series.rolling(window=window, min_periods=window).std()
    return pd.DataFrame(
        {
            "bb_mid": mid,
            "bb_upper": mid + num_std * sd,
            "bb_lower": mid - num_std * sd,
        }
    )
