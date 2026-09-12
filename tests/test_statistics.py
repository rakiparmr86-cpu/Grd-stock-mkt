from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.calculations.statistics import (
    confidence_interval,
    correlation_matrix,
    descriptive_stats,
    forecast,
    full_report,
    growth_trend,
    regression,
    volatility_downside,
)


# ── 6.1 descriptive stats ────────────────────────────────────────────────
def test_descriptive_stats_matches_manual():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = descriptive_stats(s)
    assert out["count"] == 5
    assert out["mean"] == pytest.approx(3.0)
    assert out["median"] == pytest.approx(3.0)
    assert out["variance"] == pytest.approx(2.5)
    assert out["std"] == pytest.approx(2.5 ** 0.5)
    assert out["min"] == 1.0 and out["max"] == 5.0
    assert out["percentiles"][50] == pytest.approx(3.0)


def test_descriptive_stats_flags_outlier():
    s = pd.Series([10.0, 11.0, 9.0, 10.0, 12.0, 300.0])
    out = descriptive_stats(s)
    assert len(out["outliers"]) == 1
    assert out["outliers"][0]["value"] == 300.0


def test_descriptive_stats_empty_series():
    assert descriptive_stats(pd.Series(dtype=float)) == {"count": 0}


# ── 6.2 growth and trend ─────────────────────────────────────────────────
def test_growth_trend_annual_cagr_and_yoy():
    # exact 10% compound growth for 2 steps -> CAGR is exactly 10%
    s = pd.Series([100.0, 110.0, 121.0], index=["2022", "2023", "2024"])
    out = growth_trend(s, periods_per_year=1)
    assert out["latest_yoy_pct"] == pytest.approx(10.0)
    assert out["cagr_pct"] == pytest.approx(10.0)
    assert out["trend_direction"] == "up"
    assert "qoq_pct" not in out


def test_growth_trend_quarterly_has_qoq_and_yoy():
    s = pd.Series(np.linspace(100, 180, 8), index=[f"Q{i}" for i in range(8)])
    out = growth_trend(s, periods_per_year=4)
    assert "qoq_pct" in out
    assert out["latest_qoq_pct"] is not None
    assert out["latest_yoy_pct"] is not None


def test_growth_trend_insufficient_data():
    out = growth_trend(pd.Series([1.0]))
    assert out["insufficient_data"] is True


def test_growth_trend_cagr_undefined_for_negative_start():
    s = pd.Series([-5.0, 10.0, 20.0])
    out = growth_trend(s)
    assert out["cagr_pct"] is None


# ── 6.3 correlation ───────────────────────────────────────────────────────
def test_correlation_perfectly_correlated():
    df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [2, 4, 6, 8, 10]})
    out = correlation_matrix(df)
    assert out["matrix"]["a"]["b"] == pytest.approx(1.0)
    assert out["pairs_by_strength"][0]["correlation"] == pytest.approx(1.0)


def test_correlation_inverse():
    df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [5, 4, 3, 2, 1]})
    out = correlation_matrix(df)
    assert out["matrix"]["a"]["b"] == pytest.approx(-1.0)


# ── 6.4 regression ────────────────────────────────────────────────────────
def test_linear_regression_recovers_exact_coefficients():
    rng = np.arange(20, dtype=float)
    x1, x2 = rng, rng ** 2  # not collinear with x1, unlike e.g. rng[::-1]
    y = 2 * x1 + 3 * x2 + 5  # noiseless
    df = pd.DataFrame({"y": y, "x1": x1, "x2": x2})
    out = regression(df, target="y", features=["x1", "x2"], method="linear")
    assert out["coefficients"]["x1"] == pytest.approx(2.0, abs=1e-6)
    assert out["coefficients"]["x2"] == pytest.approx(3.0, abs=1e-6)
    assert out["intercept"] == pytest.approx(5.0, abs=1e-6)
    assert out["r_squared"] == pytest.approx(1.0, abs=1e-6)


def test_regression_insufficient_data():
    df = pd.DataFrame({"y": [1.0, 2.0], "x1": [1.0, 2.0], "x2": [1.0, 2.0]})
    out = regression(df, target="y", features=["x1", "x2"], method="linear")
    assert out["insufficient_data"] is True


def test_ridge_regression_runs_and_fits_well():
    rng = np.arange(30, dtype=float)
    x1 = rng
    y = 4 * x1 + 1
    df = pd.DataFrame({"y": y, "x1": x1})
    out = regression(df, target="y", features=["x1"], method="ridge", alpha=0.01)
    assert out["method"] == "ridge"
    assert out["r_squared"] > 0.99
    assert "p_values" not in out


# ── 6.5 forecasting ───────────────────────────────────────────────────────
def test_forecast_insufficient_data():
    out = forecast(pd.Series([1.0, 2.0]), periods_ahead=1)
    assert out["insufficient_data"] is True


def test_forecast_ets_returns_interval():
    s = pd.Series(np.linspace(100, 150, 10))
    out = forecast(s, periods_ahead=2)
    assert out["method"] == "ets"
    assert len(out["forecast"]) == 2
    assert len(out["confidence_intervals"]) == 2
    for ci in out["confidence_intervals"]:
        assert ci["low"] <= ci["high"]


def test_forecast_seasonal_detected_with_enough_cycles():
    seasonal = np.tile([10, 20, 30, 40], 4).astype(float) + np.arange(16) * 0.5
    s = pd.Series(seasonal)
    out = forecast(s, periods_ahead=4, seasonal_periods=4)
    assert out["seasonal"] is True
    assert out["method"] == "ets_seasonal"


def test_forecast_no_seasonal_without_enough_cycles():
    s = pd.Series(np.linspace(10, 20, 6))
    out = forecast(s, periods_ahead=1, seasonal_periods=4)
    assert out["seasonal"] is False


# ── 6.6 volatility / downside ─────────────────────────────────────────────
def test_volatility_downside_monotonic_series_has_no_downside():
    s = pd.Series(np.linspace(100, 200, 20))
    out = volatility_downside(s)
    assert out["downside_deviation"] == pytest.approx(0.0)
    assert out["max_drawdown_pct"] == pytest.approx(0.0)


def test_volatility_downside_detects_drawdown():
    s = pd.Series([100.0, 120.0, 90.0, 95.0])
    out = volatility_downside(s)
    assert out["max_drawdown_pct"] == pytest.approx((90.0 - 120.0) / 120.0 * 100)
    assert out["downside_deviation"] > 0


def test_volatility_downside_insufficient_data():
    out = volatility_downside(pd.Series([1.0]))
    assert out["insufficient_data"] is True


# ── 6.7 confidence interval ────────────────────────────────────────────────
def test_confidence_interval_95():
    out = confidence_interval(point_estimate=100.0, standard_error=10.0, confidence=0.95)
    assert out["low"] == pytest.approx(100 - 1.959963984540054 * 10, abs=1e-6)
    assert out["high"] == pytest.approx(100 + 1.959963984540054 * 10, abs=1e-6)


# ── orchestration ──────────────────────────────────────────────────────────
def test_full_report_runs_all_sections():
    years = [str(y) for y in range(2018, 2024)]
    sales = pd.Series([100, 110, 121, 133, 146, 161], index=years, dtype=float)
    profit = pd.Series([10, 12, 15, 17, 20, 24], index=years, dtype=float)
    df = pd.DataFrame({"sales": sales, "profit": profit})

    report = full_report(df, target="profit", features=["sales"], periods_per_year=1)
    assert set(report["metrics"].keys()) == {"sales", "profit"}
    for metric_report in report["metrics"].values():
        assert "descriptive_stats" in metric_report
        assert "growth_trend" in metric_report
        assert "volatility_downside" in metric_report
        assert "forecast" in metric_report
    assert "correlation" in report
    assert "regression" in report
    assert report["regression"]["r_squared"] > 0.9
