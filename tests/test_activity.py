"""GET /activity — merges recent AnalysisRun/AgentDecision/Signal/Report/
Alert/InputSource rows into one time-sorted feed. Calls the route function
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


class _FakeInputSourceRepo:
    def __init__(self, sources):
        self._sources = sources

    def list_all(self):
        return self._sources


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
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeInputSourceRepo([]),
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
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeInputSourceRepo([]),
    )
    assert out[0]["status"] == "running"


def test_run_without_finish_has_no_finished_event():
    runs = [_run(2, ticker="TCS", started="2026-01-01T10:00:00")]
    out = list_activity(
        _FakeRunRepo(runs), _FakeDecisionRepo([]), _FakeSignalRepo([]),
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeInputSourceRepo([]),
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
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeInputSourceRepo([]),
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
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeInputSourceRepo([]),
    )
    decision_event = next(e for e in out if e["type"] == "agent_decision")
    assert decision_event["ticker"] == "INFY"
    assert "decision recorded" in decision_event["detail"]


def test_input_source_without_a_run_yet_is_skipped():
    sources = [
        SimpleNamespace(id=1, name="never run", connector="csv", last_run_at=None,
                        last_status=None, last_stats={}, last_error=None),
        SimpleNamespace(id=2, name="ran once", connector="excel",
                        last_run_at=_dt("2026-01-01T08:00:00"),
                        last_status="ok", last_stats={"rows_written": 40}, last_error=None),
    ]
    out = list_activity(
        _FakeRunRepo([]), _FakeDecisionRepo([]), _FakeSignalRepo([]),
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeInputSourceRepo(sources),
    )
    assert len(out) == 1
    assert out[0]["title"] == 'Input source "ran once" — ok'


def test_limit_caps_the_final_merged_list():
    runs = [_run(i, ticker="X", started=f"2026-01-01T09:{i:02d}:00") for i in range(10)]
    out = list_activity(
        _FakeRunRepo(runs), _FakeDecisionRepo([]), _FakeSignalRepo([]),
        _FakeReportRepo([]), _FakeAlertRepo([]), _FakeInputSourceRepo([]), limit=3,
    )
    assert len(out) == 3
