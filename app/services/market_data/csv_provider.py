from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.services.market_data.base import MarketDataProvider


class CSVProvider(MarketDataProvider):
    """Reads ``<MARKET_DATA_DIR>/<TICKER>.csv``.

    Expected header (case-insensitive, aliases handled by normalization):
    ``date,open,high,low,close,volume``.
    """

    name = "csv"

    def __init__(self, base_dir: str | None = None) -> None:
        self.base_dir = Path(base_dir or settings.market_data_dir)

    def _path(self, ticker: str) -> Path:
        return self.base_dir / f"{ticker.upper()}.csv"

    def supports(self, ticker: str) -> bool:
        return self._path(ticker).exists()

    def fetch_ohlcv(
        self,
        ticker: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        path = self._path(ticker)
        if not path.exists():
            raise FileNotFoundError(f"no CSV for {ticker} at {path}")
        df = pd.read_csv(path)
        df["ticker"] = ticker.upper()
        if start is not None or end is not None:
            ts = pd.to_datetime(df.iloc[:, 0], utc=True, errors="coerce")
            if start is not None:
                df = df[ts >= pd.Timestamp(start, tz="UTC")]
            if end is not None:
                df = df[ts <= pd.Timestamp(end, tz="UTC")]
        return df
