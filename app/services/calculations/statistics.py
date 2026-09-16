"""General-purpose statistical analysis over any period-indexed numeric series.

Unlike ``indicators.py`` (technical indicators over daily OHLCV bars), these
functions work on *any* time-ordered metric — fundamentals extracted from a
financial statement (Sales, Net profit, ...), OHLCV-derived returns, or
anything else with a value per period. Every function takes plain pandas
Series/DataFrames and returns plain dicts (JSON-serializable), so they compose
and are trivially unit-testable — same philosophy as the indicators module.

Covers, in order:
  6.1 descriptive_stats        — mean/median/std/variance/percentiles/min/max
  6.2 growth_trend             — YoY, QoQ, CAGR, rolling mean, EWMA
  6.3 correlation_matrix       — pairwise correlation (screening, not causation)
  6.4 regression               — OLS / Ridge / Lasso, profit~drivers
  6.5 forecast                 — ETS or ARIMA/SARIMA, gated on history length
  6.6 volatility_downside      — std, downside deviation, max drawdown
  6.7 confidence_interval      — generic normal-approx interval helper
  6.8 backtest_forecast        — walk-forward forecast accuracy (MAPE/RMSE/hit rate)
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd

__all__ = [
    "descriptive_stats",
    "growth_trend",
    "correlation_matrix",
    "regression",
    "forecast",
    "volatility_downside",
    "confidence_interval",
    "backtest_forecast",
    "full_report",
]

_Z95 = 1.959963984540054


def _clean(series: pd.Series) -> pd.Series:
    """Numeric, sorted-by-index, NaN/inf dropped."""
    s = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    return s.sort_index().dropna()


def _jsonable(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        return None if pd.isna(v) else float(v)
    if isinstance(v, (np.integer, int)):
        return int(v)
    return v


# ── 6.1 descriptive statistics ──────────────────────────────────────────
def descriptive_stats(series: pd.Series) -> dict[str, Any]:
    """Mean, median, std, variance, percentiles, min/max, and simple outlier
    flags (via a MAD-based modified z-score, robust to the outlier itself
    inflating a plain standard deviation and masking its own detection) to
    surface unusual observations."""
    s = _clean(series)
    if s.empty:
        return {"count": 0}

    mean, std = float(s.mean()), float(s.std(ddof=1)) if len(s) > 1 else 0.0
    median = float(s.median())
    mad = float((s - median).abs().median())
    modified_z = 0.6745 * (s - median) / mad if mad else pd.Series(0.0, index=s.index)
    outliers = [
        {
            "period": str(idx),
            "value": _jsonable(val),
            "modified_z_score": _jsonable(modified_z.loc[idx]),
        }
        for idx, val in s.items()
        if mad and abs(modified_z.loc[idx]) > 3.5
    ]
    return {
        "count": int(len(s)),
        "mean": mean,
        "median": float(s.median()),
        "std": std,
        "variance": float(s.var(ddof=1)) if len(s) > 1 else 0.0,
        "min": float(s.min()),
        "max": float(s.max()),
        "percentiles": {
            p: float(s.quantile(p / 100)) for p in (5, 10, 25, 50, 75, 90, 95)
        },
        "skew": float(s.skew()) if len(s) > 2 else None,
        "kurtosis": float(s.kurtosis()) if len(s) > 3 else None,
        "outliers": outliers,
    }


# ── 6.2 growth and trend analysis ───────────────────────────────────────
def growth_trend(
    series: pd.Series,
    periods_per_year: int = 1,
    rolling_window: int = 3,
    ewm_span: int = 3,
) -> dict[str, Any]:
    """YoY / QoQ growth, CAGR, rolling mean, and an EWMA trend line.

    ``periods_per_year`` says how the index is spaced: 1 for annual data (YoY
    = period-over-period), 4 for quarterly (YoY = 4 periods back, QoQ = 1
    period back).
    """
    s = _clean(series)
    if len(s) < 2:
        return {"count": int(len(s)), "insufficient_data": True}

    yoy_periods = periods_per_year if periods_per_year > 1 else 1
    yoy = s.pct_change(periods=yoy_periods) * 100
    result: dict[str, Any] = {
        "count": int(len(s)),
        "yoy_pct": {str(k): _jsonable(v) for k, v in yoy.items() if pd.notna(v)},
        "latest_yoy_pct": _jsonable(yoy.iloc[-1]) if pd.notna(yoy.iloc[-1]) else None,
    }
    if periods_per_year == 4:
        qoq = s.pct_change(periods=1) * 100
        result["qoq_pct"] = {str(k): _jsonable(v) for k, v in qoq.items() if pd.notna(v)}
        result["latest_qoq_pct"] = (
            _jsonable(qoq.iloc[-1]) if pd.notna(qoq.iloc[-1]) else None
        )

    first, last = float(s.iloc[0]), float(s.iloc[-1])
    n_years = (len(s) - 1) / periods_per_year
    if first > 0 and last > 0 and n_years > 0:
        cagr = (last / first) ** (1 / n_years) - 1
        result["cagr_pct"] = float(cagr * 100)
    else:
        result["cagr_pct"] = None  # undefined for non-positive start/end values

    window = min(rolling_window, len(s))
    rolling_mean = s.rolling(window=window, min_periods=window).mean()
    ewma = s.ewm(span=min(ewm_span, len(s)), adjust=False).mean()
    result["rolling_mean"] = {str(k): _jsonable(v) for k, v in rolling_mean.items() if pd.notna(v)}
    result["ewma"] = {str(k): _jsonable(v) for k, v in ewma.items()}
    result["trend_direction"] = (
        "up" if last > first else "down" if last < first else "flat"
    )
    return result


# ── 6.3 correlation analysis ────────────────────────────────────────────
def correlation_matrix(
    df: pd.DataFrame, method: Literal["pearson", "spearman"] = "pearson"
) -> dict[str, Any]:
    """Pairwise correlation for screening candidate drivers.

    Correlation is not causation — this is diagnostic input for choosing
    regression features, not a conclusion on its own.
    """
    numeric = df.apply(pd.to_numeric, errors="coerce")
    corr = numeric.corr(method=method)
    pairs = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            v = corr.loc[a, b]
            if pd.notna(v):
                pairs.append({"a": a, "b": b, "correlation": _jsonable(v)})
    pairs.sort(key=lambda p: abs(p["correlation"]), reverse=True)
    return {
        "method": method,
        "matrix": {c: {c2: _jsonable(corr.loc[c, c2]) for c2 in cols} for c in cols},
        "pairs_by_strength": pairs,
        "note": "correlation is for screening/diagnostics only, not causal evidence",
    }


# ── 6.4 regression ───────────────────────────────────────────────────────
def regression(
    df: pd.DataFrame,
    target: str,
    features: list[str],
    method: Literal["linear", "ridge", "lasso"] = "linear",
    alpha: float = 1.0,
) -> dict[str, Any]:
    """Estimate how ``target`` responds to ``features``.

    ``method="linear"`` runs OLS (statsmodels) and reports p-values / CIs on
    the coefficients. ``ridge``/``lasso`` run scikit-learn's regularized fit
    (no p-values — regularization biases them) for when multicollinearity
    among fundamentals makes plain OLS unstable.
    """
    cols = [target, *features]
    data = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    n = len(data)
    if n < len(features) + 2:
        return {
            "insufficient_data": True,
            "rows_available": n,
            "rows_required": len(features) + 2,
        }

    y = data[target].to_numpy(dtype=float)
    x = data[features].to_numpy(dtype=float)

    if method == "linear":
        import statsmodels.api as sm

        x_design = sm.add_constant(x, has_constant="add")
        fit = sm.OLS(y, x_design).fit()
        coefs = dict(zip(features, fit.params[1:], strict=True))
        p_values = dict(zip(features, fit.pvalues[1:], strict=True))
        ci = fit.conf_int(alpha=0.05)[1:]
        return {
            "method": "linear",
            "target": target,
            "features": features,
            "intercept": _jsonable(fit.params[0]),
            "coefficients": {k: _jsonable(v) for k, v in coefs.items()},
            "p_values": {k: _jsonable(v) for k, v in p_values.items()},
            "confidence_intervals_95": {
                f: {"low": _jsonable(lo), "high": _jsonable(hi)}
                for f, (lo, hi) in zip(features, ci, strict=True)
            },
            "r_squared": _jsonable(fit.rsquared),
            "adjusted_r_squared": _jsonable(fit.rsquared_adj),
            "n_observations": n,
        }

    from sklearn.linear_model import Lasso, Ridge
    from sklearn.metrics import r2_score
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x)
    model = Ridge(alpha=alpha) if method == "ridge" else Lasso(alpha=alpha)
    model.fit(x_scaled, y)
    pred = model.predict(x_scaled)
    # unscale coefficients back to original feature units for readability
    coefs_original = model.coef_ / scaler.scale_
    intercept_original = model.intercept_ - float(np.dot(model.coef_, scaler.mean_ / scaler.scale_))
    return {
        "method": method,
        "target": target,
        "features": features,
        "alpha": alpha,
        "intercept": _jsonable(intercept_original),
        "coefficients": dict(zip(features, (_jsonable(c) for c in coefs_original), strict=True)),
        "r_squared": _jsonable(r2_score(y, pred)),
        "n_observations": n,
        "note": "regularized fit — coefficients are biased toward zero, no p-values reported",
    }


# ── 6.5 time-series forecasting ─────────────────────────────────────────
_MIN_PERIODS_FOR_ETS = 4
_MIN_PERIODS_FOR_SEASONAL = 8  # need >= 2 full cycles for a seasonal model


def forecast(
    series: pd.Series,
    periods_ahead: int = 1,
    seasonal_periods: int | None = None,
    method: Literal["auto", "ets", "arima"] = "auto",
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Forecast the next ``periods_ahead`` points with a confidence interval.

    Deliberately conservative: refuses to fit a seasonal model without at
    least two full seasonal cycles of history, and refuses ETS/ARIMA below a
    minimum series length — short series get a documented reason instead of
    a fabricated confidence interval.
    """
    s = _clean(series)
    n = len(s)
    if n < _MIN_PERIODS_FOR_ETS:
        return {
            "insufficient_data": True,
            "rows_available": n,
            "rows_required": _MIN_PERIODS_FOR_ETS,
            "reason": "too few periods for ETS/ARIMA — avoid forcing a model onto a short series",
        }

    use_seasonal = bool(
        seasonal_periods and n >= seasonal_periods * 2 and n >= _MIN_PERIODS_FOR_SEASONAL
    )
    chosen = method
    z = _Z95 if confidence == 0.95 else float(
        __import__("scipy.stats", fromlist=["norm"]).norm.ppf(0.5 + confidence / 2)
    )

    if method in ("auto", "ets"):
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        model = ExponentialSmoothing(
            s.to_numpy(dtype=float),
            trend="add",
            seasonal="add" if use_seasonal else None,
            seasonal_periods=seasonal_periods if use_seasonal else None,
            initialization_method="estimated",
        ).fit()
        point = model.forecast(periods_ahead)
        resid_std = float(np.std(model.resid, ddof=1)) if len(model.resid) > 1 else 0.0
        chosen = "ets_seasonal" if use_seasonal else "ets"
    else:
        from statsmodels.tsa.arima.model import ARIMA

        order = (1, 1, 1)
        seasonal_order = (
            (1, 1, 1, seasonal_periods) if use_seasonal and seasonal_periods else (0, 0, 0, 0)
        )
        model = ARIMA(
            s.to_numpy(dtype=float), order=order, seasonal_order=seasonal_order,
        ).fit()
        pred = model.get_forecast(periods_ahead)
        point = pred.predicted_mean
        resid_std = float(np.sqrt(pred.var_pred_mean.mean()))
        chosen = "sarima" if use_seasonal else "arima"

    forecast_points = [float(v) for v in np.asarray(point)]
    margin = z * resid_std
    return {
        "method": chosen,
        "seasonal": use_seasonal,
        "periods_ahead": periods_ahead,
        "forecast": forecast_points,
        "confidence_level": confidence,
        "confidence_intervals": [
            {"low": p - margin, "high": p + margin} for p in forecast_points
        ],
        "residual_std": resid_std,
        "n_observations": n,
    }


# ── 6.6 volatility and downside analysis ────────────────────────────────
def volatility_downside(
    series: pd.Series, minimum_acceptable_return: float = 0.0
) -> dict[str, Any]:
    """Variability, downside deviation, and drawdown — quantifying
    instability rather than just central tendency."""
    s = _clean(series)
    if len(s) < 2:
        return {"insufficient_data": True, "rows_available": int(len(s))}

    rets = s.pct_change().dropna()
    downside = rets[rets < minimum_acceptable_return]
    downside_deviation = (
        float(np.sqrt((downside ** 2).mean())) if len(downside) else 0.0
    )

    cum_max = s.cummax()
    drawdown = (s - cum_max) / cum_max
    max_drawdown_idx = drawdown.idxmin()

    return {
        "n_observations": int(len(s)),
        "return_std": float(rets.std(ddof=1)) if len(rets) > 1 else 0.0,
        "downside_deviation": downside_deviation,
        "pct_periods_negative": float((rets < 0).mean() * 100) if len(rets) else 0.0,
        "max_drawdown_pct": float(drawdown.min() * 100),
        "max_drawdown_period": str(max_drawdown_idx),
        "current_drawdown_pct": float(drawdown.iloc[-1] * 100),
    }


# ── 6.7 confidence / prediction intervals ───────────────────────────────
def confidence_interval(
    point_estimate: float, standard_error: float, confidence: float = 0.95
) -> dict[str, Any]:
    """Generic normal-approximation interval — used wherever a single point
    forecast would otherwise be reported without a range."""
    from scipy import stats

    z = float(stats.norm.ppf(0.5 + confidence / 2))
    margin = z * standard_error
    return {
        "point_estimate": float(point_estimate),
        "confidence_level": confidence,
        "low": float(point_estimate - margin),
        "high": float(point_estimate + margin),
    }


# ── 6.8 forecast reliability (walk-forward backtest) ────────────────────
def backtest_forecast(
    series: pd.Series, min_train_periods: int = _MIN_PERIODS_FOR_ETS,
) -> dict[str, Any]:
    """Walk ``forecast()`` forward one period at a time and score its
    one-step-ahead point forecast against what actually happened —
    "is this forecast trustworthy", not just "what does it predict".

    Refits on every expanding window from ``min_train_periods`` onward.
    Skips (rather than fails) a window ``forecast()`` itself can't fit.
    """
    s = _clean(series)
    n = len(s)
    if n < min_train_periods + 1:
        return {
            "insufficient_data": True, "rows_available": n,
            "rows_required": min_train_periods + 1,
            "reason": "not enough history to hold out even one period for backtesting",
        }

    errors: list[float] = []
    pct_errors: list[float] = []
    hits: list[bool] = []
    for cutoff in range(min_train_periods, n):
        train = s.iloc[:cutoff]
        actual = float(s.iloc[cutoff])
        try:
            fc = forecast(train, periods_ahead=1, seasonal_periods=None)
        except Exception:  # noqa: BLE001 — one bad window shouldn't kill the whole backtest
            continue
        if fc.get("insufficient_data"):
            continue
        predicted = fc["forecast"][0]
        errors.append(predicted - actual)
        if actual:
            pct_errors.append(abs((predicted - actual) / actual) * 100)
        prev = float(train.iloc[-1])
        hits.append((predicted - prev) * (actual - prev) >= 0)

    if not errors:
        return {"insufficient_data": True, "rows_available": n,
                "reason": "no backtest window produced a usable forecast"}

    errors_arr = np.asarray(errors)
    return {
        "n_backtests": len(errors),
        "mae": float(np.mean(np.abs(errors_arr))),
        "rmse": float(np.sqrt(np.mean(errors_arr ** 2))),
        "mape_pct": float(np.mean(pct_errors)) if pct_errors else None,
        "directional_hit_rate_pct": float(np.mean(hits) * 100) if hits else None,
    }


# ── orchestration ────────────────────────────────────────────────────────
def full_report(
    df: pd.DataFrame,
    target: str | None = None,
    features: list[str] | None = None,
    periods_per_year: int = 1,
    forecast_periods: int = 1,
    seasonal_periods: int | None = None,
    regression_method: Literal["linear", "ridge", "lasso"] = "linear",
    include_backtest: bool = False,
) -> dict[str, Any]:
    """Run 6.1-6.7 across every numeric column of a period-indexed frame.

    ``target``/``features`` (both column names in ``df``) enable the
    correlation + regression sections; without them only the per-metric
    sections (descriptive stats, growth/trend, forecast, volatility) run.
    ``include_backtest`` adds 6.8 per metric — off by default since it
    refits ``forecast()`` once per historical period and is only cheap for
    the small (annual/quarterly) series this module is meant for, not a
    750-row daily OHLCV column.
    """
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(
        pd.to_numeric(df[c], errors="coerce")
    )]
    per_metric: dict[str, Any] = {}
    for col in numeric_cols:
        s = df[col]
        per_metric[col] = {
            "descriptive_stats": descriptive_stats(s),
            "growth_trend": growth_trend(s, periods_per_year=periods_per_year),
            "volatility_downside": volatility_downside(s),
            "forecast": forecast(
                s, periods_ahead=forecast_periods, seasonal_periods=seasonal_periods
            ),
        }
        if include_backtest:
            per_metric[col]["backtest"] = backtest_forecast(s)

    report: dict[str, Any] = {"metrics": per_metric}
    if len(numeric_cols) > 1:
        report["correlation"] = correlation_matrix(df[numeric_cols])
    if target and features:
        report["regression"] = regression(df, target, features, method=regression_method)
    return report
