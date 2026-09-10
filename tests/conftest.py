from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    """250 sessions of deterministic synthetic OHLCV, indexed by ts."""
    rng = np.random.default_rng(42)
    n = 250
    idx = pd.date_range("2024-01-01", periods=n, freq="B", tz="UTC")
    rets = rng.normal(0.0004, 0.015, n)
    close = 1000 * np.exp(np.cumsum(rets))
    open_ = close * (1 + rng.normal(0, 0.003, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
    vol = np.abs(rng.normal(1_000_000, 200_000, n))
    return pd.DataFrame(
        {"ticker": "TEST", "open": open_, "high": high, "low": low,
         "close": close, "volume": vol},
        index=idx,
    )
