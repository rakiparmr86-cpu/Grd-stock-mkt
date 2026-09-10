from __future__ import annotations

from app.core.config import settings
from app.services.market_data.api_provider import APIProvider
from app.services.market_data.base import MarketDataProvider
from app.services.market_data.csv_provider import CSVProvider
from app.services.market_data.excel_provider import ExcelProvider
from app.services.market_data.nse_provider import NSEProvider

_REGISTRY: dict[str, type[MarketDataProvider]] = {
    "csv": CSVProvider,
    "excel": ExcelProvider,
    "api": APIProvider,
    "nse": NSEProvider,
}


def get_provider(name: str | None = None) -> MarketDataProvider:
    key = (name or settings.market_data_provider).lower()
    try:
        return _REGISTRY[key]()
    except KeyError as exc:  # pragma: no cover
        raise ValueError(
            f"unknown market data provider {key!r}; choose from {sorted(_REGISTRY)}"
        ) from exc
