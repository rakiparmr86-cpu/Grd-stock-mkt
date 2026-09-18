"""GET /health/services — one status per dependency (Postgres/Redis/Qdrant/
Celery worker), independent of each other so one failure doesn't hide the
rest. Monkeypatches each dependency's client class/module at its own import
location, since the route imports them lazily inside the function body."""

from __future__ import annotations

from app.api.v1.health import services


class _FakeDb:
    def __init__(self, *, raises=False):
        self._raises = raises

    def execute(self, *_a, **_kw):
        if self._raises:
            raise RuntimeError("connection refused")


class _FakeRedis:
    def __init__(self, *, raises=False):
        self._raises = raises

    def ping(self):
        if self._raises:
            raise ConnectionError("redis down")


class _FakeQdrantClient:
    def __init__(self, *, raises=False, **_kw):
        self._raises = raises

    def get_collections(self):
        if self._raises:
            raise RuntimeError("qdrant unreachable")


def _patch_all_healthy(monkeypatch):
    import qdrant_client
    import redis

    monkeypatch.setattr(redis.Redis, "from_url", lambda *a, **kw: _FakeRedis())
    monkeypatch.setattr(qdrant_client, "QdrantClient", lambda *a, **kw: _FakeQdrantClient())

    from app.workers.celery_app import celery_app
    monkeypatch.setattr(
        celery_app.control, "ping", lambda timeout=None: [{"celery@worker1": {"ok": "pong"}}],
    )


def test_all_services_up(monkeypatch):
    _patch_all_healthy(monkeypatch)
    out = services(_FakeDb())
    assert out["services"]["postgres"]["status"] == "up"
    assert out["services"]["redis"]["status"] == "up"
    assert out["services"]["qdrant"]["status"] == "up"
    assert out["services"]["celery_worker"]["status"] == "up"
    assert "1 worker(s)" in out["services"]["celery_worker"]["detail"]
    assert out["services"]["celery_beat"]["status"] == "unknown"


def test_postgres_down_does_not_affect_other_checks(monkeypatch):
    _patch_all_healthy(monkeypatch)
    out = services(_FakeDb(raises=True))
    assert out["services"]["postgres"]["status"] == "down"
    assert "connection refused" in out["services"]["postgres"]["detail"]
    assert out["services"]["redis"]["status"] == "up"
    assert out["services"]["qdrant"]["status"] == "up"
    assert out["services"]["celery_worker"]["status"] == "up"


def test_no_worker_responds_reports_celery_down(monkeypatch):
    _patch_all_healthy(monkeypatch)
    from app.workers.celery_app import celery_app
    monkeypatch.setattr(celery_app.control, "ping", lambda timeout=None: [])

    out = services(_FakeDb())
    assert out["services"]["celery_worker"]["status"] == "down"


def test_redis_down_reported_independently(monkeypatch):
    _patch_all_healthy(monkeypatch)
    import redis
    monkeypatch.setattr(redis.Redis, "from_url", lambda *a, **kw: _FakeRedis(raises=True))

    out = services(_FakeDb())
    assert out["services"]["redis"]["status"] == "down"
    assert out["services"]["postgres"]["status"] == "up"
