from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import settings

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "env": settings.env}


@router.get("/health/ready")
def ready(db: DbSession) -> dict:
    checks: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["postgres"] = f"error: {exc}"

    try:
        import redis

        redis.Redis.from_url(settings.redis_url).ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"

    try:
        from qdrant_client import QdrantClient

        QdrantClient(url=settings.qdrant_url,
                     api_key=settings.qdrant_api_key or None).get_collections()
        checks["qdrant"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["qdrant"] = f"error: {exc}"

    ok = all(v == "ok" for v in checks.values())
    return {"status": "ok" if ok else "degraded", "checks": checks}


@router.get("/health/services")
def services(db: DbSession) -> dict:
    """One combined status check for every moving part this project depends
    on — Postgres/Redis/Qdrant reachability plus whether a Celery worker is
    actually listening. Distinct from ``/health/ready`` (which is meant for
    an orchestrator's readiness probe): this is for a human looking at a
    dashboard, so it reports each service individually rather than
    collapsing everything into one ok/degraded verdict, and includes Celery
    worker/beat, which ``/health/ready`` doesn't check at all.

    Celery Beat has no equivalent of a worker's ``ping`` — it doesn't consume
    from the broker or respond to control commands, it only publishes tasks
    on a schedule — so there is no reliable way to ask "is Beat running"
    from here. That's reported as ``unknown`` with an explanation rather
    than a guess.
    """
    svc: dict[str, dict] = {}

    try:
        db.execute(text("SELECT 1"))
        svc["postgres"] = {"status": "up"}
    except Exception as exc:  # noqa: BLE001
        svc["postgres"] = {"status": "down", "detail": str(exc)}

    try:
        import redis

        redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2).ping()
        svc["redis"] = {"status": "up"}
    except Exception as exc:  # noqa: BLE001
        svc["redis"] = {"status": "down", "detail": str(exc)}

    try:
        from qdrant_client import QdrantClient

        QdrantClient(
            url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=2,
        ).get_collections()
        svc["qdrant"] = {"status": "up"}
    except Exception as exc:  # noqa: BLE001
        svc["qdrant"] = {"status": "down", "detail": str(exc)}

    try:
        from app.workers.celery_app import celery_app

        pongs = celery_app.control.ping(timeout=1.5) or []
        worker_names = [name for entry in pongs for name in entry]
        svc["celery_worker"] = (
            {"status": "up", "detail": f"{len(worker_names)} worker(s): {', '.join(worker_names)}"}
            if worker_names
            else {"status": "down", "detail": "no worker responded to ping within 1.5s"}
        )
    except Exception as exc:  # noqa: BLE001
        svc["celery_worker"] = {"status": "down", "detail": str(exc)}

    svc["celery_beat"] = {
        "status": "unknown",
        "detail": "Beat doesn't respond to control pings — check whether a scheduled "
                 "task's last-run time is advancing to tell if it's actually running",
    }

    return {"services": svc}
