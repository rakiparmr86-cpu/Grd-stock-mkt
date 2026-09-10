from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@dataclass(frozen=True)
class OHLCVBar:
    ticker: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    interval: str = "1d"
    source: str = "unknown"


class MarketDataProvider(abc.ABC):
    """Contract every data source implements.

    Implementations return a *raw* DataFrame; ``normalize_ohlcv`` turns it into
    the canonical ``ticker, ts, open, high, low, close, volume`` shape.
    """

    name: str = "base"

    @abc.abstractmethod
    def fetch_ohlcv(
        self,
        ticker: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        ...

    def fetch_fundamentals(self, ticker: str) -> pd.DataFrame:  # optional
        raise NotImplementedError(f"{self.name} provider has no fundamentals feed")

    def supports(self, ticker: str) -> bool:
        return True
