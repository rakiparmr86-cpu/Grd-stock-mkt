"""Input-source ingestion tasks.

    run_input_source(source_id)      one saved source
    run_all_active_input_sources()   fan-out over every active source
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.database import session_scope
from app.core.logging import get_logger
from app.repositories.input_source import InputSourceRepository
from app.services.inputs.registry import get_connector
from app.services.inputs.sink import run_connector
from app.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.inputs.run_input_source", bind=True)
def run_input_source(self, source_id: int) -> dict:
    with session_scope() as db:
        src = InputSourceRepository(db).get(source_id)
        if src is None:
            return {"source_id": source_id, "status": "not_found"}
        name, connector, config = src.name, src.connector, dict(src.config or {})
        src.last_status = "running"
        src.last_run_at = datetime.now(timezone.utc)

    try:
        conn = get_connector(connector, config)
        stats = run_connector(conn, source_name=name)
        status = "error" if stats.get("errors") else "ok"
        error = "; ".join(stats.get("errors", []))[:2000] or None
    except Exception as exc:  # noqa: BLE001
        log.exception("input source %s failed", name)
        stats, status, error = {}, "error", str(exc)

    with session_scope() as db:
        src = InputSourceRepository(db).get(source_id)
        if src:
            src.last_status = status
            src.last_error = error
            src.last_stats = stats
            src.last_run_at = datetime.now(timezone.utc)
    return {"source_id": source_id, "name": name, "status": status, "stats": stats}


@celery_app.task(name="app.workers.tasks.inputs.run_adhoc_connector")
def run_adhoc_connector(connector: str, config: dict, source_name: str) -> dict:
    """One-off run of a connector that isn't backed by a saved ``InputSource``
    (frontend file upload / 'crawl this URL now')."""
    try:
        conn = get_connector(connector, config)
        stats = run_connector(conn, source_name=source_name)
        status = "error" if stats.get("errors") else "ok"
    except Exception as exc:  # noqa: BLE001
        log.exception("ad-hoc connector %s failed", source_name)
        stats, status = {"errors": [str(exc)]}, "error"
    return {"source_name": source_name, "connector": connector,
            "status": status, "stats": stats}


@celery_app.task(name="app.workers.tasks.inputs.run_all_active_input_sources")
def run_all_active_input_sources() -> dict:
    with session_scope() as db:
        ids = InputSourceRepository(db).list_active_ids()
    for sid in ids:
        run_input_source.delay(sid)
    return {"dispatched": len(ids)}
