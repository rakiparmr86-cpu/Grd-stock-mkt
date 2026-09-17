"""Deterministic scenario-based projection: "what does the next year look
like if growth is X%", as opposed to ``statistics.forecast`` which asks
"what does the historical trend imply" (ETS/ARIMA). The two are
complementary — a scenario table for management-style what-ifs, a
statistical forecast with confidence intervals for a data-driven read.

Mirrors the standard sell-side quick model: apply a scenario growth rate to
the trailing-twelve-month actual, derive EPS from share count, then value it
at a scenario target P/E.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

__all__ = ["scenario_projection", "multi_year_outlook", "fiscal_year_labels"]

_YEAR_MONTH = re.compile(r"^(\d{4})-\d{2}$")


def fiscal_year_labels(last_period: str) -> tuple[str, Callable[[int], str]]:
    """Best-effort "FY26 / TTM", "FY27E", ... labels from a "YYYY-MM" period
    (the shape ``load_fundamentals_frame``'s period index and Screener's own
    statement columns both use) — falls back to generic "TTM" / "Year +N"
    labels when the period doesn't match that shape (e.g. "Q1FY25")."""
    m = _YEAR_MONTH.match(last_period)
    if not m:
        return "TTM", (lambda i: f"Year +{i}")
    fy = int(m.group(1)) % 100
    return f"FY{fy} / TTM", (lambda i: f"FY{fy + i}E")


def scenario_projection(
    ttm_sales: float,
    ttm_net_profit: float,
    shares_outstanding: float,
    current_price: float,
    sales_growth: dict[str, float],
    profit_growth: dict[str, float],
    target_pe: dict[str, float],
) -> dict[str, dict[str, float]]:
    """One year ahead, one row per scenario (e.g. "bear"/"base"/"bull").

    ``sales_growth``, ``profit_growth``, and ``target_pe`` must all use the
    same scenario keys. EPS is net profit / share count for that scenario
    (no buyback/dilution modeling); implied price is EPS x target P/E.
    """
    scenarios = set(sales_growth)
    if set(profit_growth) != scenarios or set(target_pe) != scenarios:
        raise ValueError(
            "sales_growth, profit_growth, and target_pe must share the same scenario keys"
        )
    if shares_outstanding <= 0:
        raise ValueError("shares_outstanding must be positive")

    rows: dict[str, dict[str, float]] = {}
    for name in scenarios:
        sales = ttm_sales * (1 + sales_growth[name])
        net_profit = ttm_net_profit * (1 + profit_growth[name])
        eps = net_profit / shares_outstanding
        implied_price = eps * target_pe[name]
        rows[name] = {
            "sales": sales,
            "net_profit": net_profit,
            "eps": eps,
            "target_pe": float(target_pe[name]),
            "implied_price": implied_price,
            "upside_downside_pct": (implied_price - current_price) / current_price * 100
            if current_price
            else None,
        }
    return rows


def multi_year_outlook(
    ttm_sales: float,
    ttm_net_profit: float,
    shares_outstanding: float,
    sales_growth: float,
    profit_growth: float,
    years: int,
    start_label: str = "TTM",
    year_label_fn: Callable[[int], str] | None = None,
) -> list[dict[str, Any]]:
    """Compound a single growth rate (typically the base case) forward
    ``years`` periods — the deterministic counterpart to ``growth_trend``'s
    historical CAGR, projected rather than measured."""
    if shares_outstanding <= 0:
        raise ValueError("shares_outstanding must be positive")

    rows: list[dict[str, Any]] = [{
        "period": start_label,
        "sales": ttm_sales,
        "net_profit": ttm_net_profit,
        "eps": ttm_net_profit / shares_outstanding,
    }]
    sales, net_profit = ttm_sales, ttm_net_profit
    for i in range(1, years + 1):
        sales *= 1 + sales_growth
        net_profit *= 1 + profit_growth
        label = year_label_fn(i) if year_label_fn else f"Year +{i}"
        rows.append({
            "period": label,
            "sales": sales,
            "net_profit": net_profit,
            "eps": net_profit / shares_outstanding,
        })
    return rows
