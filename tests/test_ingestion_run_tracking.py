"""_start_ingestion_run / _finish_ingestion_run: the two helpers that make an
ad-hoc upload or saved-source run show up in the Activity feed with a real
"running" status while its Celery task is still executing — DB access is
monkeypatched so these stay fast, offline unit tests."""

from __future__ import annotations

from app.workers.tasks.inputs import _finish_ingestion_run, _start_ingestion_run


class _FakeIngestionRunRepo:
    def __init__(self, db):
        self.db = db

    def add(self, obj):
        obj.id = 42
        self.db.added.append(obj)
        return obj

    def get(self, id_):
        return self.db.added[0] if self.db.added and self.db.added[0].id == id_ else None


class _FakeSession:
    def __init__(self):
        self.added = []


class _FakeScope:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc_info):
        return False


def test_start_ingestion_run_creates_row_with_running_status(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr("app.workers.tasks.inputs.session_scope", lambda: _FakeScope(session))
    monkeypatch.setattr("app.workers.tasks.inputs.IngestionRunRepository", _FakeIngestionRunRepo)

    run_id = _start_ingestion_run(
        task_id="task-123", source_name="Upload: report.xlsx", connector="excel",
    )

    assert run_id == 42
    row = session.added[0]
    assert row.task_id == "task-123"
    assert row.source_name == "Upload: report.xlsx"
    assert row.connector == "excel"
    assert row.status == "running"
    assert row.finished_at is None


def test_finish_ingestion_run_sets_final_status_and_stats(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr("app.workers.tasks.inputs.session_scope", lambda: _FakeScope(session))
    monkeypatch.setattr("app.workers.tasks.inputs.IngestionRunRepository", _FakeIngestionRunRepo)

    run_id = _start_ingestion_run(task_id=None, source_name="Seed CSVs", connector="csv")
    _finish_ingestion_run(run_id, status="ok", stats={"rows_written": 2000}, error=None)

    row = session.added[0]
    assert row.status == "ok"
    assert row.stats == {"rows_written": 2000}
    assert row.error is None
    assert row.finished_at is not None


def test_finish_ingestion_run_on_missing_row_is_a_silent_no_op(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr("app.workers.tasks.inputs.session_scope", lambda: _FakeScope(session))
    monkeypatch.setattr("app.workers.tasks.inputs.IngestionRunRepository", _FakeIngestionRunRepo)

    _finish_ingestion_run(999, status="ok", stats={}, error=None)  # must not raise
