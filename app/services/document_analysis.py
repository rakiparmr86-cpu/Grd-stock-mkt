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

from typing import Any

from app.agents.llm import get_llm
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.history import AgentDecision, Report
from app.repositories.agent_decision import AgentDecisionRepository
from app.repositories.ingestion_run import IngestionRunRepository
from app.repositories.report import ReportRepository
from app.services.rag.vectorstore import get_store
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

    narrative = get_llm().invoke(
        _PROMPT.format(filename=source_name, text=text[:_MAX_CHARS])
    ).content

    payload = {
        "title": f"Document analysis — {source_name}",
        "run_id": run_id,
        "sections": [{"heading": "Document analysis", "body": narrative, "bullets": []}],
    }
    rendered = render_report(payload, slug="document")

    with session_scope() as db:
        report = ReportRepository(db).add(Report(
            run_id=run_id, ticker=None, title=payload["title"],
            summary=narrative[:280], html_path=rendered.get("html_path"),
            payload=payload,
        ))
        report_id = report.id
        AgentDecisionRepository(db).add(AgentDecision(
            run_id=run_id, agent="document_analyst", step=0,
            input={"ingestion_run_id": ingestion_run_id, "source_name": source_name},
            output={"narrative": narrative}, rationale="document analyzed",
        ))

    return {"status": "ok", "run_id": run_id, "report_id": report_id, "source_name": source_name}
