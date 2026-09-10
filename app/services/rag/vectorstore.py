"""Qdrant wrapper — collection lifecycle, upsert, search."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


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
        self.collection = collection or settings.qdrant_collection
        self.dim = dim
        self.client = QdrantClient(
            url=url or settings.qdrant_url,
            api_key=(api_key or settings.qdrant_api_key) or None,
        )

    def ensure_collection(self) -> None:
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection in existing:
            return
        log.info("creating Qdrant collection %s (dim=%d)", self.collection, self.dim)
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=qm.VectorParams(size=self.dim, distance=qm.Distance.COSINE),
        )
        for field in ("ticker", "doc_type", "source_id"):
            self.client.create_payload_index(
                self.collection, field_name=field,
                field_schema=qm.PayloadSchemaType.KEYWORD,
            )

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
        res = self.client.search(
            collection_name=self.collection, query_vector=vector,
            limit=limit, query_filter=flt,
        )
        return [
            SearchHit(
                id=str(p.id),
                score=float(p.score),
                text=(p.payload or {}).get("text", ""),
                metadata={k: v for k, v in (p.payload or {}).items() if k != "text"},
            )
            for p in res
        ]

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
