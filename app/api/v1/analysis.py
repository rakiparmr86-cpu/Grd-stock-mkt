from __future__ import annotations

import io
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.analysis import StatisticsRequest
from app.services.calculations.statistics import full_report
from app.services.inputs.screener_excel import transpose_statement_sheet

router = APIRouter()


def _build_frame(payload: StatisticsRequest) -> pd.DataFrame:
    bad_lengths = {
        name: len(values) for name, values in payload.series.items()
        if len(values) != len(payload.index)
    }
    if bad_lengths:
        raise HTTPException(
            422, f"series length must match index length ({len(payload.index)}): {bad_lengths}"
        )
    if payload.target and payload.target not in payload.series:
        raise HTTPException(422, f"target {payload.target!r} not found in series")
    if payload.features:
        missing = [f for f in payload.features if f not in payload.series]
        if missing:
            raise HTTPException(422, f"features not found in series: {missing}")
    return pd.DataFrame(payload.series, index=payload.index)


@router.post("/statistics")
def analyze_statistics(payload: StatisticsRequest) -> dict:
    """Run descriptive stats / growth / correlation / regression / forecast /
    volatility over caller-supplied period-indexed data (any format — this
    doesn't assume OHLCV or a particular source)."""
    df = _build_frame(payload)
    return full_report(
        df,
        target=payload.target,
        features=payload.features,
        periods_per_year=payload.periods_per_year,
        forecast_periods=payload.forecast_periods,
        seasonal_periods=payload.seasonal_periods,
        regression_method=payload.regression_method,
    )


@router.post("/excel")
async def analyze_excel_statement(
    file: Annotated[UploadFile, File(description="a Screener.in-style statement export (.xlsx)")],
    sheet: Annotated[str, Form(description="sheet name, e.g. 'Profit & Loss'")],
    target: Annotated[str | None, Form()] = None,
    features: Annotated[str | None, Form(description="comma-separated metric names")] = None,
    periods_per_year: Annotated[int, Form()] = 1,
    forecast_periods: Annotated[int, Form()] = 1,
    seasonal_periods: Annotated[int | None, Form()] = None,
    regression_method: Annotated[str, Form()] = "linear",
) -> dict:
    """Same analysis as ``/statistics``, but sourced straight from an
    uploaded row-per-metric / column-per-period statement sheet (Screener's
    Profit & Loss / Quarters / Balance Sheet / Cash Flow export shape)."""
    data = await file.read()
    try:
        raw = pd.read_excel(io.BytesIO(data), sheet_name=sheet, header=None)
    except ValueError as exc:
        raise HTTPException(422, f"could not read sheet {sheet!r}: {exc}") from exc

    try:
        df = transpose_statement_sheet(raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    if target and target not in df.columns:
        raise HTTPException(422, f"target {target!r} not found among this sheet's metrics")
    feature_list = [f.strip() for f in features.split(",")] if features else None
    if feature_list:
        missing = [f for f in feature_list if f not in df.columns]
        if missing:
            raise HTTPException(422, f"features not found among this sheet's metrics: {missing}")

    if regression_method not in ("linear", "ridge", "lasso"):
        raise HTTPException(422, "regression_method must be linear, ridge, or lasso")

    return full_report(
        df,
        target=target,
        features=feature_list,
        periods_per_year=periods_per_year,
        forecast_periods=forecast_periods,
        seasonal_periods=seasonal_periods,
        regression_method=regression_method,  # type: ignore[arg-type]
    )
