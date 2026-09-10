"""Market-data ingestion tasks."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.config import Watchlist, WatchlistItem
from app.services.market_data import get_provider, normalize_ohlcv
from app.services.market_data.repository import upsert_ohlcv
from app.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.market_data.refresh_ticker")
def refresh_ticker(ticker: str, provider: str | None = None, lookback_days: int = 400,
                   interval: str = "1d") -> dict:
    prov = get_provider(provider)
    start = datetime.utcnow() - timedelta(days=lookback_days)
    raw = prov.fetch_ohlcv(ticker, start=start, interval=interval)
    df = normalize_ohlcv(raw, ticker=ticker, source=prov.name)
    n = upsert_ohlcv(df, interval=interval)
    return {"ticker": ticker, "rows": n, "provider": prov.name}


@celery_app.task(name="app.workers.tasks.market_data.refresh_watchlist")
def refresh_watchlist(watchlist_id: int, provider: str | None = None) -> dict:
    with session_scope() as db:
        items = list(db.execute(
            select(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id)
        ).scalars())
        tickers = [i.ticker for i in items]
    results = []
    for t in tickers:
        try:
            results.append(refresh_ticker.run(t, provider=provider))
        except Exception as exc:  # noqa: BLE001
            log.exception("refresh failed for %s", t)
            results.append({"ticker": t, "error": str(exc)})
    return {"watchlist_id": watchlist_id, "results": results}


@celery_app.task(name="app.workers.tasks.market_data.refresh_all_watchlists")
def refresh_all_watchlists(provider: str | None = None) -> dict:
    with session_scope() as db:
        ids = list(db.execute(
            select(Watchlist.id).where(Watchlist.is_active.is_(True))
        ).scalars())
    for wid in ids:
        refresh_watchlist.delay(wid, provider=provider)
    return {"dispatched": len(ids)}
