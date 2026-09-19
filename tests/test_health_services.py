"""GET /health/services — one status per dependency (Postgres/Redis/Qdrant/
Celery worker), independent of each other so one failure doesn't hide the
rest, and checked concurrently rather than sequentially (a real bug found
live: run one after another, four checks with their own 1.5-2s timeouts
could add up to several real seconds of total latency, making a working
Refresh button look stuck). Monkeypatches each dependency's client
class/module at its own import location, since the checks import them
lazily inside their own function bodies."""

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
        celery_app.control, "ping",
        lambda timeout=None, limit=None: [{"celery@worker1": {"ok": "pong"}}],
    )
    monkeypatch.setattr(
        celery_app.control, "inspect",
        lambda **_kw: type("I", (), {
            "active": lambda self: {"celery@worker1": [{"name": "t.demo"}]},
            "reserved": lambda self: {"celery@worker1": []},
            "registered": lambda self: {"celery@worker1": ["a", "b"]},
        })(),
    )


async def test_all_services_up(monkeypatch):
    _patch_all_healthy(monkeypatch)
    out = await services(_FakeDb())
    assert out["services"]["postgres"]["status"] == "up"
    assert out["services"]["redis"]["status"] == "up"
    assert out["services"]["qdrant"]["status"] == "up"
    assert out["services"]["celery_worker"]["status"] == "up"
    assert "1 worker(s)" in out["services"]["celery_worker"]["detail"]
    assert out["services"]["celery_beat"]["status"] == "unknown"


async def test_postgres_down_does_not_affect_other_checks(monkeypatch):
    _patch_all_healthy(monkeypatch)
    out = await services(_FakeDb(raises=True))
    assert out["services"]["postgres"]["status"] == "down"
    assert "connection refused" in out["services"]["postgres"]["detail"]
    assert out["services"]["redis"]["status"] == "up"
    assert out["services"]["qdrant"]["status"] == "up"
    assert out["services"]["celery_worker"]["status"] == "up"


async def test_no_worker_responds_reports_celery_down(monkeypatch):
    _patch_all_healthy(monkeypatch)
    from app.workers.celery_app import celery_app
    monkeypatch.setattr(celery_app.control, "ping", lambda timeout=None, limit=None: [])

    out = await services(_FakeDb())
    assert out["services"]["celery_worker"]["status"] == "down"


async def test_redis_down_reported_independently(monkeypatch):
    _patch_all_healthy(monkeypatch)
    import redis
    monkeypatch.setattr(redis.Redis, "from_url", lambda *a, **kw: _FakeRedis(raises=True))

    out = await services(_FakeDb())
    assert out["services"]["redis"]["status"] == "down"
    assert out["services"]["postgres"]["status"] == "up"


async def test_celery_ping_called_with_limit_one():
    """The actual bug: without ``limit=1``, Celery's ``control.ping()``
    always waits out the *entire* timeout to collect replies from every
    possible worker, even when the first (and only) worker replies
    instantly — a deterministic ~1.5s tax on every single health check."""
    calls = []

    class _Control:
        def ping(self, timeout=None, limit=None):
            calls.append({"timeout": timeout, "limit": limit})
            return [{"celery@worker1": {"ok": "pong"}}]

    import app.workers.celery_app as celery_module
    original_control = celery_module.celery_app.control
    celery_module.celery_app.control = _Control()
    try:
        out = await services(_FakeDb())
    finally:
        celery_module.celery_app.control = original_control

    assert calls == [{"timeout": 1.5, "limit": 1}]
    assert out["services"]["celery_worker"]["status"] == "up"


async def test_review_info_and_links_attached_when_up(monkeypatch):
    _patch_all_healthy(monkeypatch)
    out = (await services(_FakeDb()))["services"]
    assert out["qdrant"]["link"].endswith("/dashboard")
    info = out["celery_worker"]["info"]
    assert info["celery@worker1: running now"] == 1
    assert info["celery@worker1: registered tasks"] == 2
    assert "hint" in out["redis"]


async def test_info_failure_never_turns_service_down(monkeypatch):
    _patch_all_healthy(monkeypatch)
    out = (await services(_FakeDb()))["services"]
    assert out["redis"]["status"] == "up"
    assert out["redis"].get("info", {}) == {}
