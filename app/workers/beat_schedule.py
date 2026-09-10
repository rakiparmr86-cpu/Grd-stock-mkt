"""Build the Celery Beat schedule.

Static defaults live here; dynamic entries come from two tables so you can adjust
runs without a redeploy:

* ``schedules``     — arbitrary ``task`` + cron (see the API)
* ``input_sources`` — any row with a ``schedule_cron`` gets its own
  ``run_input_source`` entry; the rest are swept hourly by ``sweep-input-sources``.
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
    # input sources without their own cron are swept hourly
    "sweep-input-sources": {
        "task": "app.workers.tasks.inputs.run_all_active_input_sources",
        "schedule": crontab(minute=15),
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
        from app.models.inputs import InputSource

        with session_scope() as db:
            for row in db.execute(
                select(Schedule).where(Schedule.is_active.is_(True))
            ).scalars():
                schedule[f"db:{row.name}"] = {
                    "task": row.task,
                    "schedule": _cron_from_str(row.cron),
                    "kwargs": row.args or {},
                }

            for src in db.execute(
                select(InputSource).where(
                    InputSource.is_active.is_(True),
                    InputSource.schedule_cron.is_not(None),
                )
            ).scalars():
                schedule[f"input:{src.name}"] = {
                    "task": "app.workers.tasks.inputs.run_input_source",
                    "schedule": _cron_from_str(src.schedule_cron),
                    "kwargs": {"source_id": src.id},
                }
    except Exception as exc:  # DB may not be up when beat boots
        log.warning("dynamic schedule load skipped: %s", exc)
    return schedule
