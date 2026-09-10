from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.calculations import compute_indicators
from app.services.calculations.indicators import atr, ema, macd, rsi, sma, volume_ratio


def test_sma_matches_manual():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    assert sma(s, 3).tolist()[2:] == [2.0, 3.0, 4.0]


def test_ema_first_valid_at_span():
    s = pd.Series(np.arange(1, 21), dtype=float)
    e = ema(s, 10)
    assert e.isna().sum() == 9
    assert e.iloc[-1] == pytest.approx(15.24, abs=0.5)


def test_rsi_bounds_and_all_gains():
    up = pd.Series(np.arange(1, 60), dtype=float)
    r = rsi(up, 14).dropna()
    assert (r <= 100).all() and (r >= 0).all()
    assert r.iloc[-1] == pytest.approx(100.0)


def test_rsi_constant_series_is_neutralish():
    flat = pd.Series([50.0] * 40)
    r = rsi(flat, 14).dropna()
    # no gains and no losses -> defined as 100 by convention in our impl
    assert (r == 100.0).all()


def test_macd_columns():
    s = pd.Series(np.linspace(100, 200, 120))
    m = macd(s)
    assert list(m.columns) == ["macd", "macd_signal", "macd_hist"]
    assert m["macd"].iloc[-1] > 0  # uptrend -> positive macd


def test_atr_positive(ohlcv):
    a = atr(ohlcv, 14).dropna()
    assert (a > 0).all()


def test_volume_ratio_centered_near_one(ohlcv):
    vr = volume_ratio(ohlcv["volume"], 20).dropna()
    assert 0.3 < vr.mean() < 3.0


def test_engine_latest_has_core_indicators(ohlcv):
    result = compute_indicators(ohlcv)
    for key in ("rsi_14", "sma_20", "sma_200", "macd", "macd_hist", "atr_14"):
        assert key in result.latest
    assert result.meta["rows"] == len(ohlcv)


def test_engine_rejects_bad_frame():
    with pytest.raises(ValueError):
        compute_indicators(pd.DataFrame({"close": [1, 2, 3]}))
