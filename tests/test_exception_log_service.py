"""log_exception(): builds the persisted row correctly and never lets a
logging failure mask or replace the original exception it was called for."""

from __future__ import annotations

from app.services.exception_log import log_exception


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


class _FakeScope:
    def __init__(self, session, *, raise_on_enter=False):
        self._session = session
        self._raise_on_enter = raise_on_enter

    def __enter__(self):
        if self._raise_on_enter:
            raise RuntimeError("db is down")
        return self._session

    def __exit__(self, *exc_info):
        return False


def test_log_exception_persists_message_traceback_and_context(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(
        "app.services.exception_log.session_scope", lambda: _FakeScope(session)
    )
    try:
        raise ValueError("bad ticker")
    except ValueError as exc:
        log_exception("api", exc, context={"path": "/runs"})

    assert len(session.added) == 1
    row = session.added[0]
    assert row.source == "api"
    assert row.message == "bad ticker"
    assert "ValueError" in row.traceback
    assert "bad ticker" in row.traceback
    assert row.context == {"path": "/runs"}


def test_log_exception_defaults_context_to_empty_dict(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(
        "app.services.exception_log.session_scope", lambda: _FakeScope(session)
    )
    log_exception("run", ValueError("x"))
    assert session.added[0].context == {}


def test_log_exception_swallows_its_own_failure(monkeypatch):
    monkeypatch.setattr(
        "app.services.exception_log.session_scope",
        lambda: _FakeScope(_FakeSession(), raise_on_enter=True),
    )
    # must not raise — a broken exception logger can't be allowed to mask
    # or replace the real exception the caller is already handling
    log_exception("api", ValueError("original problem"))
