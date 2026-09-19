"""Analyze one previously-uploaded document on its own — no ticker, no
OHLCV gate. Complements ``app.services.orchestrator.analyze_ticker``, which
requires both: this is the "Manual Document Analysis" path for a PDF/Excel/
image upload that should be summarized for its own content (a research
note, an annual report, a scanned filing), independent of any stock.

Reuses the RAG ingestion pipeline's own output rather than re-parsing the
file: a docs-mode ingestion already extracted and chunked the document's
text into Qdrant (see ``app.services.inputs.sink.route_result``, which now
records each chunk batch's ``source_id`` onto the ``IngestionRun.stats``
JSONB precisely so this can find them again). If an ingestion produced no
document chunks — because it was rows-mode (OHLCV/fundamentals), or failed,
or the Qdrant collection was cleared since — there's nothing to analyze,
and that's reported clearly rather than guessed at.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.llm import EchoLLM, get_llm
from app.core.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.history import AgentDecision, Report
from app.repositories.agent_decision import AgentDecisionRepository
from app.repositories.ingestion_run import IngestionRunRepository
from app.repositories.report import ReportRepository
from app.services.document_stats import _fmt, analyze_text, report_sections
from app.services.rag.vectorstore import get_store
from app.services.reports.prediction_report import (
    build_prediction_model,
    charts_b64,
    html_tables,
    is_screener_workbook,
)
from app.services.reports.renderer import render_report

log = get_logger(__name__)

_PROMPT = """You are a research analyst. You have been given the full text of
one uploaded document ("{filename}"). Using ONLY the content below, write:

1. A 2-3 sentence executive summary
2. 4-8 bullet points on the key facts, figures, or claims in the document
3. Any notable risks, red flags, or open questions raised by the document

Do not invent facts that aren't present in the text below. If the content
looks truncated or thin, say so rather than filling gaps.

Document text:
{text}
"""

# Keep the prompt within a sane token budget — a truncation notice is more
# honest than silently feeding the LLM a document cut off mid-sentence with
# no indication anything was left out.
_MAX_CHARS = 12000


class DocumentAnalysisError(ValueError):
    """Raised for a genuinely unrecoverable request — no matching ingestion
    run, or nothing indexed to analyze. Distinct from a bare ``ValueError``
    so API layers can map it to a 404/422 rather than a generic 500."""


def _document_text(ingestion_run) -> str:
    source_ids = (ingestion_run.stats or {}).get("source_ids") or []
    if not source_ids:
        raise DocumentAnalysisError(
            f"ingestion run #{ingestion_run.id} ({ingestion_run.source_name!r}) has no "
            "indexed document text — it was either ingested as rows (OHLCV/fundamentals, "
            "not documents), or the ingestion failed/produced zero chunks."
        )

    store = get_store()
    chunks: list[dict] = []
    for source_id in source_ids:
        chunks.extend(store.get_by_source(source_id))
    if not chunks:
        raise DocumentAnalysisError(
            f"ingestion run #{ingestion_run.id}'s document chunks are no longer in Qdrant "
            "(the collection may have been cleared since) — re-upload to analyze."
        )

    text = "\n\n".join(c["text"] for c in chunks if c.get("text"))
    if not text.strip():
        raise DocumentAnalysisError(
            f"ingestion run #{ingestion_run.id}'s chunks contain no extractable text."
        )
    return text


def _source_workbook(ingestion_run) -> Path | None:
    """The original uploaded file, recovered from the chunk metadata."""
    for source_id in (ingestion_run.stats or {}).get("source_ids") or []:
        for chunk in get_store().get_by_source(source_id)[:1]:
            name = chunk.get("filename")
            if name:
                path = Path(settings.uploads_dir) / name
                return path if path.exists() else None
    return None


def analyze_document(ingestion_run_id: int, *, run_id: int) -> dict[str, Any]:
    """Summarize/analyze one uploaded document and persist the result as a
    ``Report`` under ``run_id``. Deliberately does not open or close the
    ``AnalysisRun`` itself — same convention as ``analyze_ticker``, which
    also takes an already-open ``run_id`` and leaves run lifecycle to its
    caller (the Celery task or the sync API route), so both analysis kinds
    are wrapped identically.
    """
    with session_scope() as db:
        ingestion_run = IngestionRunRepository(db).get(ingestion_run_id)
        if ingestion_run is None:
            raise DocumentAnalysisError(f"ingestion run #{ingestion_run_id} not found")
        source_name = ingestion_run.source_name
        text = _document_text(ingestion_run)
        workbook = _source_workbook(ingestion_run)

    stats = analyze_text(text)
    prediction = None
    if workbook and is_screener_workbook(workbook):
        try:
            prediction = build_prediction_model(workbook)
        except ValueError as exc:
            log.warning("prediction report skipped for %s: %s", source_name, exc)
    # a prediction report replaces the generic per-sheet dump for statement workbooks
    sections = [] if prediction else report_sections(stats)
    narrative = ""
    llm = get_llm()
    if not isinstance(llm, EchoLLM):
        try:
            narrative = llm.invoke(
                _PROMPT.format(filename=source_name, text=text[:_MAX_CHARS])
            ).content
            sections.insert(0, {"heading": "Summary (LLM)", "body": narrative, "bullets": []})
        except Exception as exc:  # noqa: BLE001 - local analysis still stands
            log.warning("LLM summary skipped for %s: %s", source_name, exc)

    top = [m for sh in stats["sheets"] for m in sh["metrics"][:2]][:3]
    summary = narrative[:280] or "; ".join(
        f"{m['label']} {_fmt(m['first'])}→{_fmt(m['latest'])}" for m in top
    ) or f"{stats['overview']['words']:,} words analyzed locally"

    payload = {
        "title": (f"{prediction['company']} — prediction report" if prediction
                  else f"Document analysis — {source_name}"),
        "run_id": run_id,
        "sections": sections,
        "document_analysis": stats,
    }
    if prediction:
        payload["prediction_model"] = prediction
        payload["tables"] = html_tables(prediction)
        base = prediction["scenarios"]["base"]
        summary = (f"Base case {prediction['outlook'][1]['period']}: sales "
                   f"{base['sales']:,.0f}, EPS {base['eps']:.2f}, implied price "
                   f"{base['implied_price']:,.0f} ({base['upside_downside_pct']:+.1f}%); "
                   f"signal {prediction['overall']}")
    # graphs are embedded in the HTML only; the stored payload stays small
    render_payload = {**payload, "charts": charts_b64(prediction)} if prediction else payload
    rendered = render_report(render_payload, slug="document")

    with session_scope() as db:
        report = ReportRepository(db).add(Report(
            run_id=run_id, ticker=None, title=payload["title"],
            summary=summary, html_path=rendered.get("html_path"),
            payload=payload,
        ))
        report_id = report.id
        AgentDecisionRepository(db).add(AgentDecision(
            run_id=run_id, agent="document_analyst", step=0,
            input={"ingestion_run_id": ingestion_run_id, "source_name": source_name},
            output={"narrative": narrative, "sheets": len(stats["sheets"])},
            rationale="document analyzed locally" + (" + LLM" if narrative else ""),
        ))

    return {"status": "ok", "run_id": run_id, "report_id": report_id, "source_name": source_name}
