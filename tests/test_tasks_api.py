"""GET /api/v1/tasks/{id} — status of an async Celery task, without needing a
real Redis/worker (AsyncResult is monkeypatched)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.main import app
from app.models.user import User

PW = "pw12345678"


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    User.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        c.post("/api/v1/auth/register", json={"email": "t@t.com", "password": PW})
        token = c.post(
            "/api/v1/auth/login", data={"username": "t@t.com", "password": PW}
        ).json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c
    app.dependency_overrides.clear()


class _FakeAsyncResult:
    def __init__(self, task_id, app=None):
        self.id = task_id

    @property
    def status(self):
        return _STATE

    def ready(self):
        return _STATE in ("SUCCESS", "FAILURE")

    def successful(self):
        return _STATE == "SUCCESS"

    def failed(self):
        return _STATE == "FAILURE"

    @property
    def result(self):
        return _RESULT


_STATE = "PENDING"
_RESULT = None


def test_pending_task_has_no_result(client, monkeypatch):
    global _STATE, _RESULT
    _STATE, _RESULT = "PENDING", None
    monkeypatch.setattr("app.api.v1.tasks.AsyncResult", _FakeAsyncResult)

    r = client.get("/api/v1/tasks/some-id")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "task_id": "some-id", "status": "PENDING", "ready": False,
        "successful": None, "result": None, "error": None,
    }


def test_successful_task_returns_result(client, monkeypatch):
    global _STATE, _RESULT
    _STATE, _RESULT = "SUCCESS", {"stats": {"chunks": 3}}
    monkeypatch.setattr("app.api.v1.tasks.AsyncResult", _FakeAsyncResult)

    body = client.get("/api/v1/tasks/ok-id").json()
    assert body["status"] == "SUCCESS"
    assert body["ready"] is True
    assert body["successful"] is True
    assert body["result"] == {"stats": {"chunks": 3}}
    assert body["error"] is None


def test_failed_task_returns_error_not_result(client, monkeypatch):
    global _STATE, _RESULT
    _STATE, _RESULT = "FAILURE", RuntimeError("boom")
    monkeypatch.setattr("app.api.v1.tasks.AsyncResult", _FakeAsyncResult)

    body = client.get("/api/v1/tasks/bad-id").json()
    assert body["status"] == "FAILURE"
    assert body["successful"] is False
    assert body["result"] is None
    assert "boom" in body["error"]


def test_requires_auth():
    with TestClient(app) as c:
        assert c.get("/api/v1/tasks/x").status_code == 401
