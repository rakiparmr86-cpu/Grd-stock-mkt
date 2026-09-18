"""GET /inputs/uploads-tracker — every ingestion (ad-hoc upload or
saved-source run) with an ``analyzed`` flag: true only when an Analysis run
for the same ticker started *after* the ingestion finished. Same fake-repo
pattern as tests/test_activity.py."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.api.v1.inputs import uploads_tracker


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=UTC)


class _FakeIngestionRunRepo:
    def __init__(self, runs):
        self._runs = runs

    def list_recent(self, limit):
        return self._runs[:limit]


class _FakeRunRepo:
    def __init__(self, runs):
        self._runs = runs

    def list_recent(self, limit):
        return self._runs[:limit]


def _ingest(id_, *, name, ticker=None, started, finished=None, status="ok", stats=None, error=None):
    return SimpleNamespace(
        id=id_, source_name=name, connector="excel", ticker=ticker,
        started_at=_dt(started), finished_at=_dt(finished) if finished else None,
        status=status, stats=stats or {}, error=error,
    )


def _run(ticker, started):
    return SimpleNamespace(context={"ticker": ticker}, started_at=_dt(started))


def test_upload_analyzed_when_run_happens_after_ingestion_finishes():
    ingestion = [_ingest(1, name="Upload: infy.csv", ticker="INFY",
                        started="2026-01-01T10:00:00", finished="2026-01-01T10:00:05")]
    runs = [_run("INFY", "2026-01-01T10:05:00")]  # after the ingestion finished
    out = uploads_tracker(_FakeIngestionRunRepo(ingestion), _FakeRunRepo(runs))
    assert out["total"] == 1
    assert out["analyzed"] == 1
    assert out["pending"] == 0
    assert out["items"][0]["analyzed"] is True


def test_upload_not_analyzed_when_only_a_prior_run_exists():
    """A run from before the upload finished couldn't have seen this data —
    must not count as "analyzed", or the tracker would lie."""
    ingestion = [_ingest(1, name="Upload: infy.csv", ticker="INFY",
                        started="2026-01-01T10:00:00", finished="2026-01-01T10:00:05")]
    runs = [_run("INFY", "2026-01-01T09:00:00")]  # before the ingestion even started
    out = uploads_tracker(_FakeIngestionRunRepo(ingestion), _FakeRunRepo(runs))
    assert out["analyzed"] == 0
    assert out["pending"] == 1
    assert out["items"][0]["analyzed"] is False


def test_upload_without_ticker_is_never_analyzed():
    ingestion = [_ingest(1, name="Upload: notes.pdf", ticker=None,
                        started="2026-01-01T10:00:00", finished="2026-01-01T10:00:05")]
    out = uploads_tracker(_FakeIngestionRunRepo(ingestion), _FakeRunRepo([]))
    assert out["items"][0]["analyzed"] is False


def test_still_running_upload_is_never_analyzed():
    ingestion = [_ingest(1, name="Upload: big.xlsx", ticker="RELIANCE",
                        started="2026-01-01T10:00:00", finished=None)]
    runs = [_run("RELIANCE", "2026-01-01T11:00:00")]
    out = uploads_tracker(_FakeIngestionRunRepo(ingestion), _FakeRunRepo(runs))
    assert out["items"][0]["analyzed"] is False


def test_ticker_matching_is_case_insensitive():
    ingestion = [_ingest(1, name="Upload: infy.csv", ticker="infy",
                        started="2026-01-01T10:00:00", finished="2026-01-01T10:00:05")]
    runs = [_run("INFY", "2026-01-01T10:05:00")]
    out = uploads_tracker(_FakeIngestionRunRepo(ingestion), _FakeRunRepo(runs))
    assert out["items"][0]["analyzed"] is True


def test_summary_counts_mixed_analyzed_and_pending():
    ingestion = [
        _ingest(1, name="a", ticker="X", started="2026-01-01T09:00:00",
               finished="2026-01-01T09:00:01"),
        _ingest(2, name="b", ticker="Y", started="2026-01-01T09:00:00",
               finished="2026-01-01T09:00:01"),
        _ingest(3, name="c", ticker=None, started="2026-01-01T09:00:00",
               finished="2026-01-01T09:00:01"),
    ]
    runs = [_run("X", "2026-01-01T10:00:00")]  # only X was ever analyzed
    out = uploads_tracker(_FakeIngestionRunRepo(ingestion), _FakeRunRepo(runs))
    assert out["total"] == 3
    assert out["analyzed"] == 1
    assert out["pending"] == 2
