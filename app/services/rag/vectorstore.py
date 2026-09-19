"""Qdrant wrapper — collection lifecycle, upsert, search."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

try:  # keep this module importable without the optional dep installed
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qm
    from qdrant_client.http.exceptions import UnexpectedResponse
except ModuleNotFoundError:  # pragma: no cover
    QdrantClient = None  # type: ignore[assignment,misc]
    qm = None  # type: ignore[assignment]
    UnexpectedResponse = None  # type: ignore[assignment,misc]

# qdrant-client's own default (5s) is too short for a cold local Qdrant under
# Docker/WSL2, where disk I/O is slow enough that plain collection creation
# can itself take a few seconds — that alone was enough to make every upload
# fail with "timed out" on its first hit after a container restart.
_DEFAULT_TIMEOUT_S = 30.0


@dataclass
class SearchHit:
    id: str
    score: float
    text: str
    metadata: dict[str, Any]


class QdrantStore:
    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection: str | None = None,
        dim: int = 384,
    ) -> None:
        if QdrantClient is None:  # pragma: no cover
            raise RuntimeError("qdrant-client is not installed; `pip install -e .`")
        self.collection = collection or settings.qdrant_collection
        self.dim = dim
        self.client = QdrantClient(
            url=url or settings.qdrant_url,
            api_key=(api_key or settings.qdrant_api_key) or None,
            timeout=_DEFAULT_TIMEOUT_S,
        )

    def ensure_collection(self) -> None:
        """Idempotent by design, not just by the existence check up front:
        ``upsert()`` calls this on *every* call, so under load (several docs
        from one upload, each triggering their own call) two calls can each
        see the collection missing and both attempt to create it — the
        loser gets a 409 from Qdrant, not a real failure, since the
        collection ends up exactly as intended either way. Treat that 409
        as success rather than letting it surface as an ingestion error.
        """
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection in existing:
            return
        log.info("creating Qdrant collection %s (dim=%d)", self.collection, self.dim)
        try:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(size=self.dim, distance=qm.Distance.COSINE),
            )
        except UnexpectedResponse as exc:
            if exc.status_code != 409:
                raise
            log.info("Qdrant collection %s already exists (lost a create race) — continuing",
                     self.collection)
            return
        for field in ("ticker", "doc_type", "source_id"):
            try:
                self.client.create_payload_index(
                    self.collection, field_name=field,
                    field_schema=qm.PayloadSchemaType.KEYWORD,
                )
            except UnexpectedResponse as exc:
                if exc.status_code != 409:
                    raise

    def upsert(
        self,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        ids: list[str] | None = None,
    ) -> list[str]:
        self.ensure_collection()
        ids = ids or [str(uuid.uuid4()) for _ in vectors]
        self.client.upsert(
            collection_name=self.collection,
            points=qm.Batch(ids=ids, vectors=vectors, payloads=payloads),
        )
        return ids

    def search(
        self,
        vector: list[float],
        *,
        limit: int = 6,
        ticker: str | None = None,
        doc_type: str | None = None,
    ) -> list[SearchHit]:
        must: list[qm.FieldCondition] = []
        if ticker:
            must.append(qm.FieldCondition(key="ticker", match=qm.MatchValue(value=ticker)))
        if doc_type:
            must.append(qm.FieldCondition(key="doc_type", match=qm.MatchValue(value=doc_type)))
        flt = qm.Filter(must=must) if must else None
        # QdrantClient.search() was removed in newer qdrant-client releases in
        # favor of query_points() (same filter/limit semantics, wraps hits in
        # a QueryResponse with a `.points` list).
        res = self.client.query_points(
            collection_name=self.collection, query=vector,
            limit=limit, query_filter=flt,
        ).points
        return [
            SearchHit(
                id=str(p.id),
                score=float(p.score),
                text=(p.payload or {}).get("text", ""),
                metadata={k: v for k, v in (p.payload or {}).items() if k != "text"},
            )
            for p in res
        ]

    def get_by_source(self, source_id: str) -> list[dict[str, Any]]:
        """Every chunk belonging to one ingested document, in chunk order —
        for reconstructing a document's full text (standalone document
        analysis), not a similarity search. Uses ``scroll`` rather than
        ``query_points``/``search``: those need a query vector and rank by
        relevance, which makes no sense here — we want *all* of one
        document's chunks, not the ones nearest to some vector."""
        points, _next_offset = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=qm.Filter(
                must=[qm.FieldCondition(key="source_id", match=qm.MatchValue(value=source_id))]
            ),
            limit=1000,
            with_payload=True,
        )
        chunks = [dict(p.payload or {}) for p in points]
        chunks.sort(key=lambda c: c.get("chunk", 0))
        return chunks

    def delete_by_source(self, source_id: str) -> None:
        self.client.delete(
            collection_name=self.collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[qm.FieldCondition(key="source_id",
                                            match=qm.MatchValue(value=source_id))]
                )
            ),
        )


_store: QdrantStore | None = None


def get_store(dim: int = 384) -> QdrantStore:
    global _store
    if _store is None:
        _store = QdrantStore(dim=dim)
    return _store
