from __future__ import annotations

import asyncio

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.orm import Session

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


def _safe_info(fn, *args) -> dict:
    """Review details are a bonus on top of the up/down verdict — never let
    a failure gathering them turn a healthy service into an error."""
    try:
        return fn(*args) or {}
    except Exception:  # noqa: BLE001
        return {}


def _postgres_info(db: Session) -> dict:
    version = db.execute(text("SHOW server_version")).scalar()
    size = db.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()))")).scalar()
    conns = db.execute(
        text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
    ).scalar()
    info: dict = {"version": version, "database size": size, "connections": conns}
    for table in ("analysis_runs", "ingestion_runs", "reports", "ohlcv", "fundamentals"):
        try:
            info[f"rows: {table}"] = db.execute(text(f"SELECT count(*) FROM {table}")).scalar()  # noqa: S608 - fixed names
        except Exception:  # noqa: BLE001
            db.rollback()
    return info


def _redis_info() -> dict:
    import redis

    r = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
    server = r.info()
    broker = redis.Redis.from_url(settings.celery_broker_url, socket_connect_timeout=2)
    return {
        "version": server.get("redis_version"),
        "memory used": server.get("used_memory_human"),
        "connected clients": server.get("connected_clients"),
        "tasks waiting in queue": broker.llen("celery"),
    }


def _qdrant_info() -> dict:
    from qdrant_client import QdrantClient

    client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=2,
    )
    info: dict = {"url": settings.qdrant_url}
    for c in client.get_collections().collections:
        info[f"collection: {c.name}"] = f"{client.count(c.name).count} chunks"
    return info


def _celery_info(worker_names: list[str]) -> dict:
    from app.workers.celery_app import celery_app

    insp = celery_app.control.inspect(timeout=1.0, destination=worker_names)
    active = insp.active() or {}
    reserved = insp.reserved() or {}
    registered = insp.registered() or {}
    info: dict = {"broker": settings.celery_broker_url}
    for name in worker_names:
        info[f"{name}: running now"] = len(active.get(name, []))
        info[f"{name}: reserved (queued on worker)"] = len(reserved.get(name, []))
        info[f"{name}: registered tasks"] = len(registered.get(name, []))
        for i, t in enumerate(active.get(name, [])[:5]):
            info[f"{name}: active task {i + 1}"] = t.get("name")
    return info


def _check_postgres(db: Session) -> dict:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "up"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "detail": str(exc)}


def _check_redis() -> dict:
    try:
        import redis

        redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2).ping()
        return {"status": "up"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "detail": str(exc)}


def _check_qdrant() -> dict:
    try:
        from qdrant_client import QdrantClient

        QdrantClient(
            url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=2,
        ).get_collections()
        return {"status": "up"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "detail": str(exc)}


def _check_celery_worker() -> dict:
    try:
        from app.workers.celery_app import celery_app

        # ``limit=1``: stop as soon as one worker replies, rather than
        # Celery's default of always waiting out the full ``timeout`` to
        # collect replies from every possible worker — without it, this
        # check took a deterministic ~1.5s on *every* call regardless of how
        # fast the (single, local) worker actually responded.
        pongs = celery_app.control.ping(timeout=1.5, limit=1) or []
        worker_names = [name for entry in pongs for name in entry]
        return (
            {"status": "up", "detail": f"{len(worker_names)} worker(s): {', '.join(worker_names)}"}
            if worker_names
            else {"status": "down", "detail": "no worker responded to ping within 1.5s"}
        )
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "detail": str(exc)}


@router.get("/health/services")
async def services(db: DbSession) -> dict:
    """One combined status check for every moving part this project depends
    on — Postgres/Redis/Qdrant reachability plus whether a Celery worker is
    actually listening. Distinct from ``/health/ready`` (which is meant for
    an orchestrator's readiness probe): this is for a human looking at a
    dashboard, so it reports each service individually rather than
    collapsing everything into one ok/degraded verdict, and includes Celery
    worker/beat, which ``/health/ready`` doesn't check at all.

    Every check runs concurrently (each is a blocking call, dispatched to its
    own thread) rather than one after another — sequentially, four checks
    with their own 1.5-2s timeouts could add up to several real seconds of
    total latency even when every dependency is healthy; concurrently, the
    whole endpoint takes about as long as the single slowest check.

    Celery Beat has no equivalent of a worker's ``ping`` — it doesn't consume
    from the broker or respond to control commands, it only publishes tasks
    on a schedule — so there is no reliable way to ask "is Beat running"
    from here. That's reported as ``unknown`` with an explanation rather
    than a guess.
    """
    postgres, redis_, qdrant, celery_worker = await asyncio.gather(
        asyncio.to_thread(_check_postgres, db),
        asyncio.to_thread(_check_redis),
        asyncio.to_thread(_check_qdrant),
        asyncio.to_thread(_check_celery_worker),
    )
    if postgres["status"] == "up":
        postgres["info"] = _safe_info(_postgres_info, db)
    if redis_["status"] == "up":
        redis_["info"] = _safe_info(_redis_info)
        redis_["hint"] = (
            "No web page. Inspect with: docker exec grd-stock-mkt-redis-1 redis-cli info"
        )
    if qdrant["status"] == "up":
        qdrant["info"] = _safe_info(_qdrant_info)
        qdrant["link"] = f"{settings.qdrant_url.rstrip('/')}/dashboard"
    if celery_worker["status"] == "up":
        names = [n.strip() for n in celery_worker["detail"].split(":", 1)[1].split(",")]
        celery_worker["info"] = await asyncio.to_thread(_safe_info, _celery_info, names)
        celery_worker["hint"] = (
            "No web page. Live view: celery -A app.workers.celery_app inspect active "
            "(or run Flower). Worker log: the terminal / logs\celery_worker.out.log"
        )
    return {
        "services": {
            "postgres": postgres,
            "redis": redis_,
            "qdrant": qdrant,
            "celery_worker": celery_worker,
            "celery_beat": {
                "status": "unknown",
                "detail": "Beat doesn't respond to control pings — check whether a scheduled "
                         "task's last-run time is advancing to tell if it's actually running",
            },
        }
    }
