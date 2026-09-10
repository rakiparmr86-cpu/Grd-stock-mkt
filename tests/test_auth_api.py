"""API-level check of the login gate on /inputs.

Uses an in-memory SQLite DB with only the ``users`` table created (enough for
auth), and overrides the ``get_db`` dependency.
"""

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
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    User.__table__.create(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_inputs_requires_auth(client):
    r = client.get("/api/v1/inputs/connectors")
    assert r.status_code == 401


def test_register_login_then_reach_inputs(client):
    r = client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": PW})
    assert r.status_code == 201, r.text

    r = client.post("/api/v1/auth/login", data={"username": "a@b.com", "password": PW})
    assert r.status_code == 200
    token = r.json()["access_token"]

    r = client.get(
        "/api/v1/inputs/connectors", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    assert any(c["name"] == "web_crawler" for c in r.json())

    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["email"] == "a@b.com"


def test_login_wrong_password_401(client):
    client.post("/api/v1/auth/register", json={"email": "c@d.com", "password": PW})
    r = client.post("/api/v1/auth/login", data={"username": "c@d.com", "password": "nope"})
    assert r.status_code == 401


def test_duplicate_register_409(client):
    client.post("/api/v1/auth/register", json={"email": "e@f.com", "password": PW})
    r = client.post("/api/v1/auth/register", json={"email": "e@f.com", "password": PW})
    assert r.status_code == 409
