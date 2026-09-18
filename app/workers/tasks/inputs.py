"""Input-source ingestion tasks.

    run_input_source(source_id)      one saved source
    run_all_active_input_sources()   fan-out over every active source
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.history import IngestionRun
from app.repositories.ingestion_run import IngestionRunRepository
from app.repositories.input_source import InputSourceRepository
from app.services.exception_log import log_exception
from app.services.inputs.registry import get_connector
from app.services.inputs.sink import run_connector
from app.workers.celery_app import celery_app

log = get_logger(__name__)


def _start_ingestion_run(
    *, task_id: str | None, source_name: str, connector: str,
    input_source_id: int | None = None, ticker: str | None = None,
) -> int:
    with session_scope() as db:
        run = IngestionRunRepository(db).add(IngestionRun(
            task_id=task_id, source_name=source_name, connector=connector,
            input_source_id=input_source_id, ticker=ticker, status="running",
        ))
        return run.id


def _finish_ingestion_run(run_id: int, *, status: str, stats: dict, error: str | None) -> None:
    with session_scope() as db:
        run = IngestionRunRepository(db).get(run_id)
        if run:
            run.status = status
            run.stats = stats
            run.error = error
            run.finished_at = datetime.now(UTC)


@celery_app.task(name="app.workers.tasks.inputs.run_input_source", bind=True)
def run_input_source(self, source_id: int) -> dict:
    with session_scope() as db:
        src = InputSourceRepository(db).get(source_id)
        if src is None:
            return {"source_id": source_id, "status": "not_found"}
        name, connector, config = src.name, src.connector, dict(src.config or {})
        src.last_status = "running"
        src.last_run_at = datetime.now(UTC)

    ingestion_id = _start_ingestion_run(
        task_id=self.request.id, source_name=name, connector=connector,
        input_source_id=source_id, ticker=config.get("ticker"),
    )

    try:
        conn = get_connector(connector, config)
        stats = run_connector(conn, source_name=name)
        status = "error" if stats.get("errors") else "ok"
        error = "; ".join(stats.get("errors", []))[:2000] or None
    except Exception as exc:  # noqa: BLE001
        log.exception("input source %s failed", name)
        log_exception("input_source", exc, context={"source_id": source_id, "name": name})
        stats, status, error = {}, "error", str(exc)

    _finish_ingestion_run(ingestion_id, status=status, stats=stats, error=error)
    with session_scope() as db:
        src = InputSourceRepository(db).get(source_id)
        if src:
            src.last_status = status
            src.last_error = error
            src.last_stats = stats
            src.last_run_at = datetime.now(UTC)
    return {"source_id": source_id, "name": name, "status": status, "stats": stats}


@celery_app.task(name="app.workers.tasks.inputs.run_adhoc_connector", bind=True)
def run_adhoc_connector(self, connector: str, config: dict, source_name: str) -> dict:
    """One-off run of a connector that isn't backed by a saved ``InputSource``
    (frontend file upload / 'crawl this URL now') — still tracked in
    ``ingestion_runs`` so it shows up (with live status) in the Activity feed
    even though it will never appear in "Saved input sources"."""
    ingestion_id = _start_ingestion_run(
        task_id=self.request.id, source_name=source_name, connector=connector,
        ticker=config.get("ticker"),
    )
    try:
        conn = get_connector(connector, config)
        stats = run_connector(conn, source_name=source_name)
        status = "error" if stats.get("errors") else "ok"
        error = "; ".join(stats.get("errors", []))[:2000] or None
    except Exception as exc:  # noqa: BLE001
        log.exception("ad-hoc connector %s failed", source_name)
        log_exception("input_source", exc, context={"source_name": source_name})
        stats, status, error = {"errors": [str(exc)]}, "error", str(exc)

    _finish_ingestion_run(ingestion_id, status=status, stats=stats, error=error)
    return {"source_name": source_name, "connector": connector,
            "status": status, "stats": stats}


@celery_app.task(name="app.workers.tasks.inputs.run_all_active_input_sources")
def run_all_active_input_sources() -> dict:
    with session_scope() as db:
        ids = InputSourceRepository(db).list_active_ids()
    for sid in ids:
        run_input_source.delay(sid)
    return {"dispatched": len(ids)}
