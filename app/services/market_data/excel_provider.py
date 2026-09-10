from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.services.market_data.base import MarketDataProvider


class ExcelProvider(MarketDataProvider):
    """Reads an ``.xlsx`` workbook.

    Layout A: one sheet per ticker (sheet name == ticker).
    Layout B: single sheet with a ``ticker`` / ``symbol`` column.
    """

    name = "excel"

    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or Path(settings.market_data_dir) / "market.xlsx")

    def supports(self, ticker: str) -> bool:
        return self.path.exists()

    def fetch_ohlcv(
        self,
        ticker: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        if not self.path.exists():
            raise FileNotFoundError(f"workbook not found: {self.path}")
        xls = pd.ExcelFile(self.path)
        if ticker.upper() in {s.upper() for s in xls.sheet_names}:
            sheet = next(s for s in xls.sheet_names if s.upper() == ticker.upper())
            df = xls.parse(sheet)
            df["ticker"] = ticker.upper()
        else:
            df = xls.parse(xls.sheet_names[0])
            df.columns = [str(c).strip().lower() for c in df.columns]
            key = "ticker" if "ticker" in df.columns else "symbol"
            df = df[df[key].astype(str).str.upper() == ticker.upper()]
        return df
