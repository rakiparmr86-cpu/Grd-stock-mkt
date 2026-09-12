from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StatisticsRequest(BaseModel):
    """Any period-indexed numeric data — fundamentals extracted from a
    financial statement, a price series, or anything else with one value per
    period. Not tied to OHLCV or any particular ingestion path."""

    index: list[str] = Field(..., description="period labels, e.g. ['2021', '2022', '2023']")
    series: dict[str, list[float | None]] = Field(
        ..., description="metric name -> one value per index entry (null for missing)"
    )
    periods_per_year: int = Field(1, description="1 for annual data, 4 for quarterly")
    forecast_periods: int = 1
    seasonal_periods: int | None = None
    target: str | None = Field(None, description="metric name to regress, e.g. 'net_profit'")
    features: list[str] | None = Field(None, description="metric names to regress target on")
    regression_method: Literal["linear", "ridge", "lasso"] = "linear"
