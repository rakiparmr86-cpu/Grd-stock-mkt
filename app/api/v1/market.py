from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, select

from app.api.deps import DbSession, get_export_user
from app.models.market import OHLCV
from app.services.price_forecast import (
    ForecastError,
    build_price_forecast,
    forecast_excel,
    forecast_html,
)

router = APIRouter()
# download links are opened by a browser/phone, so they take ?access_token= too
export_router = APIRouter(dependencies=[Depends(get_export_user)])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/tickers")
def list_price_tickers(db: DbSession, interval: str = "1d") -> list[dict]:
    """Tickers that have price bars on file, for a chart picker."""
    rows = db.execute(
        select(OHLCV.ticker, func.count(), func.max(OHLCV.ts))
        .where(OHLCV.interval == interval)
        .group_by(OHLCV.ticker)
        .order_by(OHLCV.ticker)
    ).all()
    return [{"ticker": t, "bars": n, "last": last.isoformat() if last else None}
            for t, n, last in rows]


@router.get("/ohlcv/{ticker}")
def get_ohlcv(
    ticker: str,
    db: DbSession,
    limit: Annotated[int, Query(ge=5, le=1000)] = 120,
    interval: str = "1d",
) -> dict:
    """The latest ``limit`` bars for one ticker, oldest first (chart order)."""
    rows = list(db.execute(
        select(OHLCV)
        .where(OHLCV.ticker == ticker.upper(), OHLCV.interval == interval)
        .order_by(OHLCV.ts.desc())
        .limit(limit)
    ).scalars())
    if not rows:
        raise HTTPException(404, f"no price data for {ticker.upper()}")
    rows.reverse()
    return {
        "ticker": ticker.upper(),
        "interval": interval,
        "bars": [
            {"ts": r.ts.isoformat(), "open": float(r.open), "high": float(r.high),
             "low": float(r.low), "close": float(r.close), "volume": float(r.volume)}
            for r in rows
        ],
    }


def _forecast_or_422(ticker: str, history: int, ahead: int) -> dict:
    try:
        return build_price_forecast(ticker, history=history, ahead=ahead)
    except ForecastError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/forecast/{ticker}")
def get_forecast(
    ticker: str,
    history: Annotated[int, Query(ge=30, le=500)] = 120,
    ahead: Annotated[int, Query(ge=5, le=60)] = 20,
) -> dict:
    """Recent closes plus an ETS/ARIMA forecast with a 95% interval."""
    return _forecast_or_422(ticker, history, ahead)


@export_router.get("/forecast/{ticker}/html", response_class=HTMLResponse)
def forecast_html_page(
    ticker: str,
    history: Annotated[int, Query(ge=30, le=500)] = 120,
    ahead: Annotated[int, Query(ge=5, le=60)] = 20,
) -> str:
    return forecast_html(_forecast_or_422(ticker, history, ahead))


@export_router.get("/forecast/{ticker}/excel")
def forecast_excel_file(
    ticker: str,
    history: Annotated[int, Query(ge=30, le=500)] = 120,
    ahead: Annotated[int, Query(ge=5, le=60)] = 20,
) -> Response:
    data = forecast_excel(_forecast_or_422(ticker, history, ahead))
    return Response(
        content=data, media_type=_XLSX,
        headers={"Content-Disposition":
                 f'attachment; filename="{ticker.upper()}_forecast.xlsx"'},
    )
