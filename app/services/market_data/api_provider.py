from __future__ import annotations

from datetime import datetime

import httpx
import pandas as pd

from app.core.config import settings
from app.core.logging import get_logger
from app.services.market_data.base import MarketDataProvider

log = get_logger(__name__)


class APIProvider(MarketDataProvider):
    """Generic REST provider.

    Expects a JSON endpoint returning a list of bars. Point ``MARKET_DATA_API_URL``
    at your vendor and adapt ``_params`` / ``_extract`` to their schema.
    """

    name = "api"

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (base_url or settings.market_data_api_url).rstrip("/")
        self.api_key = api_key or settings.market_data_api_key

    def _params(self, ticker: str, start: datetime | None, end: datetime | None,
                interval: str) -> dict[str, str]:
        params = {"symbol": ticker, "interval": interval}
        if start:
            params["from"] = start.date().isoformat()
        if end:
            params["to"] = end.date().isoformat()
        return params

    @staticmethod
    def _extract(payload: object) -> list[dict]:
        # TODO: adapt to the real vendor response envelope.
        if isinstance(payload, dict):
            for key in ("data", "candles", "results", "bars"):
                if key in payload and isinstance(payload[key], list):
                    return payload[key]  # type: ignore[return-value]
        if isinstance(payload, list):
            return payload
        raise ValueError("unrecognized API payload shape")

    def fetch_ohlcv(
        self,
        ticker: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        if not self.base_url:
            raise RuntimeError("MARKET_DATA_API_URL is not configured")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        url = f"{self.base_url}/ohlcv"
        log.info("APIProvider GET %s %s", url, ticker)
        resp = httpx.get(url, params=self._params(ticker, start, end, interval),
                         headers=headers, timeout=30.0)
        resp.raise_for_status()
        rows = self._extract(resp.json())
        df = pd.DataFrame(rows)
        df["ticker"] = ticker.upper()
        return df
