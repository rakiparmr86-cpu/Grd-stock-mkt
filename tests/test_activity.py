"""GET /activity — merges recent AnalysisRun/AgentDecision/Signal/Report/
Alert/IngestionRun rows into one time-sorted feed. Calls the route function
directly with fake repos rather than a full DB fixture (same pattern as
tests/test_report_excel_endpoint.py) since these models use Postgres JSONB
columns SQLite can't model."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.api.v1.activity import list_activity


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=UTC)


class _FakeRunRepo:
    def __init__(self, runs):
        self._runs = runs

    def list_recent(self, limit):
        return self._runs[:limit]


class _FakeDecisionRepo:
    def __init__(self, decisions):
        self._decisions = decisions

    def list_recent(self, limit):
        return self._decisions[:limit]


class _FakeSignalRepo:
    def __init__(self, signals):
        self._signals = signals

    def list_filtered(self, *, limit):
        return self._signals[:limit]


class _FakeReportRepo:
    def __init__(self, reports):
        self._reports = reports

    def list_filtered(self, *, limit):
        return self._reports[:limit]


class _FakeColumn:
    def desc(self):
        return self


class _FakeAlertModel:
    created_at = _FakeColumn()  # stands in for the real order_by(model.created_at.desc())


class _FakeAlertRepo:
    model = _FakeAlertModel

    def __init__(self, alerts):
        self._alerts = alerts

    def list(self, *, order_by, limit):
        return self._alerts[:limit]


class _FakeIngestionRunRepo:
    def __init__(self, runs):
        self._runs = runs

    def list_recent(self, limit):
        return self._runs[:limit]


def _ingest(id_, *, name, connector="excel", started, finished=None, status="ok",
           stats=None, error=None):
    return SimpleNamespace(
        id=id_, source_name=name, connector=connector,
        started_at=_dt(started), finished_at=_dt(finished) if finished else None,
        status=status, stats=stats or {}, error=error,
    )


def _run(id_, *, ticker, trigger="manual", status="done", started, finished=None,
        outcome=None, reason=None, error=None):
    return SimpleNamespace(
        id=id_, trigger=trigger, status=status,
        started_at=_dt(started), finished_at=_dt(finished) if finished else None,
        error=error, context={"ticker": ticker, "outcome": outcome, "reason": reason},
    )


def test_run_started_and_finished_both_appear():
    runs = [_run(1, ticker="RELIANCE", started="2026-01-01T10:00:00",
                finished="2026-01-01T10:05:00", outcome="ok")]
    out = list_activity(
        _FakeRunRepo(runs), _FakeDecisionRepo([]), _FakeSignalRepo([]),
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeIngestionRunRepo([]),
    )
    types = {e["type"] for e in out}
    assert types == {"run_started", "run_finished"}
    finished = next(e for e in out if e["type"] == "run_finished")
    assert finished["ticker"] == "RELIANCE"
    assert "outcome=ok" in finished["detail"]

    # a completed run's "started" event must not still read "running" —
    # that's what confused a user into thinking a long-finished run was stuck
    started = next(e for e in out if e["type"] == "run_started")
    assert started["status"] == "started"


def test_unfinished_run_started_event_says_running():
    runs = [_run(2, ticker="TCS", started="2026-01-01T10:00:00")]
    out = list_activity(
        _FakeRunRepo(runs), _FakeDecisionRepo([]), _FakeSignalRepo([]),
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeIngestionRunRepo([]),
    )
    assert out[0]["status"] == "running"


def test_run_without_finish_has_no_finished_event():
    runs = [_run(2, ticker="TCS", started="2026-01-01T10:00:00")]
    out = list_activity(
        _FakeRunRepo(runs), _FakeDecisionRepo([]), _FakeSignalRepo([]),
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeIngestionRunRepo([]),
    )
    assert [e["type"] for e in out] == ["run_started"]


def test_events_are_sorted_newest_first_across_types():
    runs = [_run(1, ticker="X", started="2026-01-01T09:00:00")]
    decisions = [SimpleNamespace(
        id=5, agent="risk_critic", run_id=1, step=4, rationale="verdict=go",
        latency_ms=120, created_at=_dt("2026-01-01T11:00:00"),
    )]
    signals = [SimpleNamespace(
        id=9, ticker="X", run_id=1, signal_type="buy", strength=0.8, price=100.0,
        triggered_at=_dt("2026-01-01T10:00:00"),
    )]
    out = list_activity(
        _FakeRunRepo(runs), _FakeDecisionRepo(decisions), _FakeSignalRepo(signals),
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeIngestionRunRepo([]),
    )
    assert [e["type"] for e in out] == ["agent_decision", "signal", "run_started"]


def test_decision_ticker_resolved_from_its_run():
    runs = [_run(3, ticker="INFY", started="2026-01-01T09:00:00")]
    decisions = [SimpleNamespace(
        id=1, agent="technical_analyst", run_id=3, step=1, rationale=None,
        latency_ms=None, created_at=_dt("2026-01-01T09:01:00"),
    )]
    out = list_activity(
        _FakeRunRepo(runs), _FakeDecisionRepo(decisions), _FakeSignalRepo([]),
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeIngestionRunRepo([]),
    )
    decision_event = next(e for e in out if e["type"] == "agent_decision")
    assert decision_event["ticker"] == "INFY"
    assert "decision recorded" in decision_event["detail"]


def test_ingestion_still_running_shows_live_status():
    """The whole point of tracking ingestion via IngestionRun instead of
    InputSource.last_run_at: an ad-hoc upload (which has no InputSource row
    at all) or a still-in-flight run must show up with a real "running"
    status, not stay invisible until it finishes."""
    runs = [_ingest(1, name="Upload: report.xlsx", started="2026-01-01T08:00:00", finished=None)]
    out = list_activity(
        _FakeRunRepo([]), _FakeDecisionRepo([]), _FakeSignalRepo([]),
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeIngestionRunRepo(runs),
    )
    assert len(out) == 1
    assert out[0]["type"] == "ingestion_started"
    assert out[0]["status"] == "running"


def test_ingestion_finished_shows_started_and_finished_events():
    runs = [_ingest(2, name="Seed CSVs", started="2026-01-01T08:00:00",
                    finished="2026-01-01T08:00:05", status="ok",
                    stats={"rows_written": 2000})]
    out = list_activity(
        _FakeRunRepo([]), _FakeDecisionRepo([]), _FakeSignalRepo([]),
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeIngestionRunRepo(runs),
    )
    types = {e["type"] for e in out}
    assert types == {"ingestion_started", "ingestion_finished"}
    started = next(e for e in out if e["type"] == "ingestion_started")
    assert started["status"] == "started"  # not "running" — it already finished
    finished = next(e for e in out if e["type"] == "ingestion_finished")
    assert finished["status"] == "ok"
    assert finished["title"] == 'Ingest "Seed CSVs" finished — ok'
    assert "rows_written" in finished["detail"]


def test_ingestion_error_status_and_message_surface():
    runs = [_ingest(3, name="GRD console", started="2026-01-01T08:00:00",
                    finished="2026-01-01T08:00:01", status="error",
                    error="auth: environment variable 'GRDWORLD_USER' is not set")]
    out = list_activity(
        _FakeRunRepo([]), _FakeDecisionRepo([]), _FakeSignalRepo([]),
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeIngestionRunRepo(runs),
    )
    finished = next(e for e in out if e["type"] == "ingestion_finished")
    assert finished["status"] == "error"
    assert "GRDWORLD_USER" in finished["detail"]


def test_limit_caps_the_final_merged_list():
    runs = [_run(i, ticker="X", started=f"2026-01-01T09:{i:02d}:00") for i in range(10)]
    out = list_activity(
        _FakeRunRepo(runs), _FakeDecisionRepo([]), _FakeSignalRepo([]),
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeIngestionRunRepo([]), limit=3,
    )
    assert len(out) == 3
