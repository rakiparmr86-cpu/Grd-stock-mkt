"""GET /exceptions, DELETE /exceptions/{id} — same fake-repo pattern as
tests/test_report_excel_endpoint.py (avoids a full DB fixture since these
models use Postgres JSONB columns SQLite can't model)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.api.v1.exceptions import delete_exception, list_exceptions


class _FakeExceptionRepo:
    def __init__(self, rows):
        self._rows = {r.id: r for r in rows}
        self.deleted = []

    def list_recent(self, limit):
        return list(self._rows.values())[:limit]

    def get(self, id_):
        return self._rows.get(id_)

    def delete(self, row):
        self.deleted.append(row.id)
        del self._rows[row.id]


class _FakeDb:
    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True


def _row(id_, *, source="api", message="boom", traceback_="Traceback...", context=None):
    return SimpleNamespace(
        id=id_, source=source, message=message, traceback=traceback_,
        context=context or {}, created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_list_exceptions_shapes_output():
    repo = _FakeExceptionRepo([_row(1, context={"run_id": 5})])
    out = list_exceptions(repo)
    assert out == [{
        "id": 1, "source": "api", "message": "boom", "traceback": "Traceback...",
        "context": {"run_id": 5}, "created_at": "2026-01-01T00:00:00+00:00",
    }]


def test_delete_exception_removes_and_commits():
    repo = _FakeExceptionRepo([_row(1)])
    db = _FakeDb()
    delete_exception(1, db, repo)
    assert repo.deleted == [1]
    assert db.committed is True


def test_delete_missing_exception_is_a_silent_no_op():
    repo = _FakeExceptionRepo([])
    db = _FakeDb()
    delete_exception(999, db, repo)  # must not raise
    assert repo.deleted == []
    assert db.committed is False
