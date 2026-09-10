"""Glue: (file | text) → parse → chunk → embed → Qdrant."""

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


def source_id_for(value: str) -> str:
    """Stable id for a non-file source (URL, connector item key, ...)."""
    return hashlib.sha1(value.encode()).hexdigest()[:16]


def _ingest_parsed(
    text: str,
    metadata: dict[str, Any],
    *,
    source_id: str,
    store: QdrantStore | None = None,
    replace: bool = True,
) -> dict[str, Any]:
    embedder = get_embedder()
    store = store or get_store(dim=embedder.dim)

    if replace:
        try:
            store.delete_by_source(source_id)
        except Exception as exc:  # pragma: no cover
            log.warning("delete_by_source failed (first ingest?): %s", exc)

    chunks = chunk_text(text, metadata=metadata)
    if not chunks:
        log.warning("no chunks produced for source_id=%s", source_id)
        return {"source_id": source_id, "chunks": 0}

    vectors = embedder.embed([c.text for c in chunks])
    payloads = [
        {
            "text": c.text,
            "source_id": source_id,
            "ticker": (metadata.get("tickers") or [None])[0],
            "tickers": metadata.get("tickers", []),
            "doc_type": metadata.get("doc_type", "other"),
            "title": metadata.get("title"),
            "filename": metadata.get("filename"),
            "url": metadata.get("url"),
            "chunk": c.index,
        }
        for c in chunks
    ]
    ids = store.upsert(vectors, payloads)
    log.info("ingested source_id=%s -> %d chunks", source_id, len(ids))
    return {"source_id": source_id, "chunks": len(ids),
            "doc_type": metadata.get("doc_type")}


def ingest_document(
    path: str | Path,
    *,
    store: QdrantStore | None = None,
    known_tickers: set[str] | None = None,
    extra_metadata: dict[str, Any] | None = None,
    replace: bool = True,
) -> dict[str, Any]:
    path = Path(path)
    parsed = parse_document(path, known_tickers=known_tickers, extra_metadata=extra_metadata)
    return _ingest_parsed(parsed.text, parsed.metadata, source_id=_source_id(path),
                          store=store, replace=replace)


def ingest_text(
    text: str,
    *,
    source_key: str,
    metadata: dict[str, Any] | None = None,
    store: QdrantStore | None = None,
    replace: bool = True,
) -> dict[str, Any]:
    """Ingest raw text (a crawled page, OCR output, an API record).

    ``source_key`` is any stable string identifying this item (a URL, a
    ``connector:name/item`` key); it is hashed into the ``source_id`` used for
    idempotent replace.
    """
    meta = {"doc_type": "other", **(metadata or {})}
    if not text or not text.strip():
        return {"source_id": source_id_for(source_key), "chunks": 0}
    return _ingest_parsed(text, meta, source_id=source_id_for(source_key),
                          store=store, replace=replace)
