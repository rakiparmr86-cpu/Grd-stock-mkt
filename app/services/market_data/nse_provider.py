from __future__ import annotations

from datetime import datetime

import httpx
import pandas as pd

from app.core.logging import get_logger
from app.services.market_data.base import MarketDataProvider

log = get_logger(__name__)

_NSE_BASE = "https://www.nseindia.com"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{_NSE_BASE}/",
}


class NSEProvider(MarketDataProvider):
    """National Stock Exchange of India.

    NSE has no official public historical API and gates requests behind cookies
    obtained by first hitting the site root. This client does that handshake; if
    NSE changes its endpoints or rate-limits you, fall back to CSV/Excel export.

    TODO: consider a licensed vendor (e.g. a broker API) for production use.
    """

    name = "nse"

    def __init__(self) -> None:
        self._client = httpx.Client(headers=_HEADERS, timeout=20.0, follow_redirects=True)
        self._primed = False

    def _prime(self) -> None:
        if self._primed:
            return
        self._client.get(f"{_NSE_BASE}/")
        self._client.get(f"{_NSE_BASE}/market-data/securities-available-for-trading")
        self._primed = True

    def fetch_ohlcv(
        self,
        ticker: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        self._prime()
        # Equity quote endpoint — intraday/last snapshot. For true history use a
        # vendor feed and the APIProvider instead.
        url = f"{_NSE_BASE}/api/quote-equity"
        resp = self._client.get(url, params={"symbol": ticker.upper()})
        resp.raise_for_status()
        data = resp.json()
        price = data.get("priceInfo", {})
        row = {
            "ticker": ticker.upper(),
            "date": data.get("metadata", {}).get("lastUpdateTime")
            or datetime.utcnow().isoformat(),
            "open": price.get("open"),
            "high": price.get("intraDayHighLow", {}).get("max"),
            "low": price.get("intraDayHighLow", {}).get("min"),
            "close": price.get("lastPrice"),
            "volume": data.get("securityInfo", {}).get("tradedVolume", 0),
        }
        log.info("NSEProvider snapshot for %s: close=%s", ticker, row["close"])
        return pd.DataFrame([row])

    def __del__(self) -> None:  # pragma: no cover
        try:
            self._client.close()
        except Exception:
            pass
