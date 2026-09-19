"""analyze_document(): the "Manual Document Analysis" path — summarizes one
previously-uploaded document (PDF/Excel/image) with no ticker and no OHLCV
gate. DB/LLM/Qdrant access is monkeypatched so these stay fast, offline unit
tests, following the same pattern as tests/test_fundamental_analyst.py."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.document_analysis import DocumentAnalysisError, analyze_document


class _FakeScope:
    def __init__(self, db):
        self._db = db

    def __enter__(self):
        return self._db

    def __exit__(self, *exc_info):
        return False


class _FakeIngestionRunRepo:
    def __init__(self, db):
        self._db = db

    def get(self, id_):
        return self._db.ingestion_runs.get(id_)


class _FakeReportRepo:
    def __init__(self, db):
        self._db = db

    def add(self, obj):
        obj.id = len(self._db.reports) + 1
        self._db.reports.append(obj)
        return obj


class _FakeAgentDecisionRepo:
    def __init__(self, db):
        self._db = db

    def add(self, obj):
        self._db.decisions.append(obj)
        return obj


class _FakeDb:
    def __init__(self, ingestion_runs):
        self.ingestion_runs = ingestion_runs
        self.reports = []
        self.decisions = []


class _FakeStore:
    def __init__(self, chunks_by_source):
        self._chunks_by_source = chunks_by_source

    def get_by_source(self, source_id):
        return self._chunks_by_source.get(source_id, [])


class _FakeLLM:
    def __init__(self, content="fake narrative"):
        self._content = content

    def invoke(self, _prompt):
        return SimpleNamespace(content=self._content)


def _ingestion_run(id_, *, source_name="upload:report.pdf", stats=None):
    return SimpleNamespace(id=id_, source_name=source_name, stats=stats or {})


def _patch(monkeypatch, *, db, store=None, llm=None):
    monkeypatch.setattr("app.services.document_analysis.session_scope", lambda: _FakeScope(db))
    monkeypatch.setattr(
        "app.services.document_analysis.IngestionRunRepository", _FakeIngestionRunRepo,
    )
    monkeypatch.setattr("app.services.document_analysis.ReportRepository", _FakeReportRepo)
    monkeypatch.setattr(
        "app.services.document_analysis.AgentDecisionRepository", _FakeAgentDecisionRepo,
    )
    monkeypatch.setattr("app.services.document_analysis.get_store", lambda: store or _FakeStore({}))
    monkeypatch.setattr("app.services.document_analysis.get_llm", lambda: llm or _FakeLLM())
    monkeypatch.setattr(
        "app.services.document_analysis.render_report",
        lambda payload, slug="report": {"html_path": f"/reports/{slug}.html"},
    )


def test_analyze_document_happy_path(monkeypatch):
    run = _ingestion_run(1, stats={"source_ids": ["src1"]})
    db = _FakeDb({1: run})
    store = _FakeStore({"src1": [
        {"text": "second chunk", "chunk": 1},
        {"text": "first chunk", "chunk": 0},
    ]})
    llm = _FakeLLM(content="Executive summary: this document says X.")
    _patch(monkeypatch, db=db, store=store, llm=llm)

    result = analyze_document(1, run_id=42)

    assert result["status"] == "ok"
    assert result["run_id"] == 42
    assert result["source_name"] == "upload:report.pdf"
    assert len(db.reports) == 1
    report = db.reports[0]
    assert report.run_id == 42
    assert report.ticker is None
    assert "this document says X" in report.summary
    assert report.payload["sections"][0]["body"] == "Executive summary: this document says X."
    assert len(db.decisions) == 1
    assert db.decisions[0].agent == "document_analyst"


def test_analyze_document_missing_ingestion_run_raises(monkeypatch):
    db = _FakeDb({})
    _patch(monkeypatch, db=db)

    with pytest.raises(DocumentAnalysisError, match="not found"):
        analyze_document(999, run_id=1)


def test_analyze_document_rows_mode_ingestion_has_nothing_to_analyze(monkeypatch):
    """A ticker/OHLCV upload (row_kind=fundamental/ohlcv) never produces
    document chunks — must fail clearly, not silently analyze nothing."""
    run = _ingestion_run(1, stats={"rows_written": 500})  # no source_ids at all
    db = _FakeDb({1: run})
    _patch(monkeypatch, db=db)

    with pytest.raises(DocumentAnalysisError, match="no indexed document text"):
        analyze_document(1, run_id=1)


def test_analyze_document_chunks_missing_from_qdrant_raises(monkeypatch):
    run = _ingestion_run(1, stats={"source_ids": ["src1"]})
    db = _FakeDb({1: run})
    store = _FakeStore({})  # source_id recorded, but nothing in Qdrant anymore
    _patch(monkeypatch, db=db, store=store)

    with pytest.raises(DocumentAnalysisError, match="no longer in Qdrant"):
        analyze_document(1, run_id=1)


def test_analyze_document_concatenates_multiple_source_ids_in_chunk_order(monkeypatch):
    """A multi-sheet Excel-as-docs upload produces one source_id per sheet —
    all of them must be pulled in and each kept in its own chunk order."""
    run = _ingestion_run(1, stats={"source_ids": ["sheet1", "sheet2"]})
    db = _FakeDb({1: run})
    store = _FakeStore({
        "sheet1": [{"text": "A", "chunk": 0}, {"text": "B", "chunk": 1}],
        "sheet2": [{"text": "C", "chunk": 0}],
    })
    captured = {}

    class _CapturingLLM:
        def invoke(self, prompt):
            captured["prompt"] = prompt
            return SimpleNamespace(content="ok")

    _patch(monkeypatch, db=db, store=store, llm=_CapturingLLM())
    analyze_document(1, run_id=1)

    assert "A" in captured["prompt"]
    assert "B" in captured["prompt"]
    assert "C" in captured["prompt"]
