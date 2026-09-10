"""Build the Celery Beat schedule.

Static defaults live here; dynamic entries are read from the ``schedules`` table
(populated via the API) so you can add/adjust runs without a redeploy.
"""

from __future__ import annotations

from celery.schedules import crontab

from app.core.logging import get_logger

log = get_logger(__name__)

_STATIC: dict = {
    "refresh-watchlist-eod": {
        "task": "app.workers.tasks.market_data.refresh_all_watchlists",
        "schedule": crontab(minute=0, hour=18, day_of_week="1-5"),  # 18:00 IST Mon-Fri
        "args": (),
    },
    "intraday-scan": {
        "task": "app.workers.tasks.analysis.scan_all_watchlists",
        "schedule": crontab(minute="*/15", hour="9-15", day_of_week="1-5"),
        "args": (),
    },
    "reindex-new-documents": {
        "task": "app.workers.tasks.rag.ingest_pending_documents",
        "schedule": crontab(minute=30, hour="*/4"),
        "args": (),
    },
}


def _cron_from_str(expr: str) -> crontab:
    minute, hour, dom, month, dow = expr.split()
    return crontab(minute=minute, hour=hour, day_of_month=dom,
                   month_of_year=month, day_of_week=dow)


def build_beat_schedule() -> dict:
    schedule = dict(_STATIC)
    try:
        from sqlalchemy import select

        from app.core.database import session_scope
        from app.models.config import Schedule

        with session_scope() as db:
            rows = db.execute(select(Schedule).where(Schedule.is_active.is_(True))).scalars()
            for row in rows:
                schedule[f"db:{row.name}"] = {
                    "task": row.task,
                    "schedule": _cron_from_str(row.cron),
                    "kwargs": row.args or {},
                }
    except Exception as exc:  # DB may not be up when beat boots
        log.warning("dynamic schedule load skipped: %s", exc)
    return schedule
