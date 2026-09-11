"""Unit tests for the repository layer, against an in-memory SQLite DB.

Only ``User`` and ``Watchlist``/``WatchlistItem`` have no JSONB columns, so
they're the ones that can run on SQLite. The JSONB-bearing repositories
(Strategy, Rule, InputSource, AnalysisRun, Signal, Report, …) are exercised
live against real Postgres instead — see ``test_auth_api.py`` for the pattern
and docs/DATABASE.md for why (SQLite has no JSONB dialect support).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.config import Watchlist, WatchlistItem
from app.models.user import User
from app.repositories.user import UserRepository
from app.repositories.watchlist import WatchlistRepository


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    User.__table__.create(bind=engine)
    Watchlist.__table__.create(bind=engine)
    WatchlistItem.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


# ── BaseRepository generics (via UserRepository) ───────────────────────
def test_add_flushes_and_assigns_pk(db):
    repo = UserRepository(db)
    user = repo.add(User(email="a@b.com", hashed_password="x"))
    assert user.id is not None  # flushed, not committed
    assert db.get(User, user.id) is user


def test_get_returns_none_for_missing(db):
    assert UserRepository(db).get(999) is None


def test_delete_stages_removal(db):
    repo = UserRepository(db)
    user = repo.add(User(email="a@b.com", hashed_password="x"))
    uid = user.id
    repo.delete(user)
    db.flush()
    assert repo.get(uid) is None


def test_list_with_where_and_limit(db):
    repo = UserRepository(db)
    for i in range(5):
        repo.add(User(email=f"u{i}@b.com", hashed_password="x", is_superuser=(i % 2 == 0)))
    admins = repo.list(User.is_superuser.is_(True))
    assert {u.email for u in admins} == {"u0@b.com", "u2@b.com", "u4@b.com"}
    assert len(repo.list(limit=2)) == 2


# ── UserRepository ──────────────────────────────────────────────────
def test_by_email_finds_and_misses(db):
    repo = UserRepository(db)
    repo.add(User(email="demo@x.dev", hashed_password="h"))
    db.commit()
    assert repo.by_email("demo@x.dev") is not None
    assert repo.by_email("nope@x.dev") is None


# ── WatchlistRepository ─────────────────────────────────────────────
def test_watchlist_list_with_items_and_tickers(db):
    repo = WatchlistRepository(db)
    wl = repo.add(Watchlist(name="Core", description="demo"))
    repo.add_item(wl, "reliance", weight=2.0)
    repo.add_item(wl, "tcs")
    db.commit()

    loaded = repo.list_with_items()
    assert len(loaded) == 1
    assert {i.ticker for i in loaded[0].items} == {"RELIANCE", "TCS"}  # upper-cased
    assert repo.tickers(wl.id) == ["RELIANCE", "TCS"]


def test_watchlist_list_active_ids_excludes_inactive(db):
    repo = WatchlistRepository(db)
    on = repo.add(Watchlist(name="On", is_active=True))
    repo.add(Watchlist(name="Off", is_active=False))
    db.commit()
    assert repo.list_active_ids() == [on.id]
