"""Document ingestion tasks for the RAG pipeline."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.repositories.instrument import InstrumentRepository
from app.services.rag.ingest import ingest_document
from app.workers.celery_app import celery_app

log = get_logger(__name__)

_DOC_DIR = Path("./data/documents")
_STATE_FILE = _DOC_DIR / ".ingested.txt"
_SUFFIXES = {".pdf", ".txt", ".md", ".html", ".htm"}


def _known_tickers() -> set[str]:
    try:
        with session_scope() as db:
            return InstrumentRepository(db).all_tickers()
    except Exception:  # noqa: BLE001
        return set()


@celery_app.task(name="app.workers.tasks.rag.ingest_document_task")
def ingest_document_task(path: str, metadata: dict | None = None) -> dict:
    return ingest_document(path, known_tickers=_known_tickers(), extra_metadata=metadata)


@celery_app.task(name="app.workers.tasks.rag.ingest_pending_documents")
def ingest_pending_documents() -> dict:
    _DOC_DIR.mkdir(parents=True, exist_ok=True)
    done = set(_STATE_FILE.read_text().splitlines()) if _STATE_FILE.exists() else set()
    known = _known_tickers()
    ingested = []
    for p in sorted(_DOC_DIR.rglob("*")):
        if p.suffix.lower() not in _SUFFIXES or str(p) in done:
            continue
        try:
            res = ingest_document(p, known_tickers=known)
            ingested.append({"path": str(p), **res})
            done.add(str(p))
        except Exception as exc:  # noqa: BLE001
            log.exception("ingest failed for %s", p)
            ingested.append({"path": str(p), "error": str(exc)})
    _STATE_FILE.write_text("\n".join(sorted(done)))
    return {"ingested": ingested, "collection": settings.qdrant_collection}
