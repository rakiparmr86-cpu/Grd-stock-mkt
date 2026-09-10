"""Glue: file → parse → chunk → embed → Qdrant."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.services.rag.chunker import chunk_text
from app.services.rag.embeddings import get_embedder
from app.services.rag.parser import parse_document
from app.services.rag.vectorstore import QdrantStore, get_store

log = get_logger(__name__)


def _source_id(path: Path) -> str:
    h = hashlib.sha1()
    h.update(str(path.resolve()).encode())
    h.update(str(path.stat().st_mtime).encode())
    return h.hexdigest()[:16]


def ingest_document(
    path: str | Path,
    *,
    store: QdrantStore | None = None,
    known_tickers: set[str] | None = None,
    extra_metadata: dict[str, Any] | None = None,
    replace: bool = True,
) -> dict[str, Any]:
    path = Path(path)
    embedder = get_embedder()
    store = store or get_store(dim=embedder.dim)

    parsed = parse_document(path, known_tickers=known_tickers, extra_metadata=extra_metadata)
    sid = _source_id(path)
    if replace:
        try:
            store.delete_by_source(sid)
        except Exception as exc:  # pragma: no cover
            log.warning("delete_by_source failed (first ingest?): %s", exc)

    chunks = chunk_text(parsed.text, metadata=parsed.metadata)
    if not chunks:
        log.warning("no chunks produced for %s", path)
        return {"source_id": sid, "chunks": 0}

    vectors = embedder.embed([c.text for c in chunks])
    payloads = [
        {
            "text": c.text,
            "source_id": sid,
            "ticker": (parsed.metadata.get("tickers") or [None])[0],
            "tickers": parsed.metadata.get("tickers", []),
            "doc_type": parsed.metadata.get("doc_type", "other"),
            "title": parsed.metadata.get("title"),
            "filename": parsed.metadata.get("filename"),
            "chunk": c.index,
        }
        for c in chunks
    ]
    ids = store.upsert(vectors, payloads)
    log.info("ingested %s -> %d chunks (source_id=%s)", path.name, len(ids), sid)
    return {"source_id": sid, "chunks": len(ids), "doc_type": parsed.metadata.get("doc_type")}
