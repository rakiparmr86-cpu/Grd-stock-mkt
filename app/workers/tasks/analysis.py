"""Analysis / scanning tasks — the bridge from signals to the agent layer."""

from __future__ import annotations

from sqlalchemy import select

from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.config import Strategy, Watchlist, WatchlistItem
from app.services.orchestrator import analyze_ticker, close_run, open_run
from app.workers.celery_app import celery_app
from app.workers.tasks.notifications import send_report_alert

log = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.analysis.analyze_ticker_task", bind=True)
def analyze_ticker_task(self, ticker: str, strategy_id: int | None = None,
                        run_id: int | None = None, notify_to: str | None = None,
                        force_agents: bool = False) -> dict:
    own_run = run_id is None
    if own_run:
        run_id = open_run("manual", strategy_id=strategy_id, context={"ticker": ticker})
    try:
        result = analyze_ticker(ticker, run_id=run_id, strategy_id=strategy_id,
                                force_agents=force_agents)
        if own_run:
            close_run(run_id, "done")
    except Exception as exc:  # noqa: BLE001
        log.exception("analyze_ticker_task failed for %s", ticker)
        if own_run:
            close_run(run_id, "error", str(exc))
        raise

    if notify_to and result.get("report"):
        send_report_alert.delay(run_id=run_id, ticker=ticker, recipient=notify_to,
                                report=result["report"])
    return {"run_id": run_id, "ticker": ticker, "status": result.get("status")}


@celery_app.task(name="app.workers.tasks.analysis.scan_watchlist")
def scan_watchlist(watchlist_id: int, strategy_id: int | None = None,
                   notify_to: str | None = None) -> dict:
    with session_scope() as db:
        wl = db.get(Watchlist, watchlist_id)
        tickers = [i.ticker for i in db.execute(
            select(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id)
        ).scalars()]
        if strategy_id is None:
            strategy_id = db.execute(
                select(Strategy.id).where(Strategy.is_active.is_(True)).limit(1)
            ).scalar_one_or_none()

    run_id = open_run("schedule", strategy_id=strategy_id, watchlist_id=watchlist_id,
                      context={"tickers": tickers})
    fired = 0
    try:
        for t in tickers:
            res = analyze_ticker(t, run_id=run_id, strategy_id=strategy_id)
            if res.get("signals"):
                fired += 1
                if notify_to and res.get("report"):
                    send_report_alert.delay(run_id=run_id, ticker=t,
                                            recipient=notify_to, report=res["report"])
        close_run(run_id, "done")
    except Exception as exc:  # noqa: BLE001
        log.exception("scan_watchlist failed")
        close_run(run_id, "error", str(exc))
        raise
    return {"run_id": run_id, "watchlist_id": watchlist_id, "scanned": len(tickers),
            "with_signals": fired}


@celery_app.task(name="app.workers.tasks.analysis.scan_all_watchlists")
def scan_all_watchlists() -> dict:
    with session_scope() as db:
        ids = list(db.execute(
            select(Watchlist.id).where(Watchlist.is_active.is_(True))
        ).scalars())
    for wid in ids:
        scan_watchlist.delay(wid)
    return {"dispatched": len(ids)}
