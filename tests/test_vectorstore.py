"""QdrantStore.search() regression test.

qdrant-client removed ``QdrantClient.search()`` in favor of ``query_points()``
in newer releases. Because ``rag_research_node`` wraps retrieval in a bare
try/except and treats any failure as "no documents" (a deliberate
offline-degradation feature — see TECHNICAL.md §9), the old ``.search()`` call
failed *silently* on any qdrant-client new enough not to have it: every RAG
query quietly returned zero hits instead of raising. This test pins the
correct call so it can't regress the same way again.
"""

from __future__ import annotations

import pytest

pytest.importorskip("qdrant_client")

from app.services.rag.vectorstore import QdrantStore  # noqa: E402


class _FakePoint:
    def __init__(self, id_, score, payload):
        self.id = id_
        self.score = score
        self.payload = payload


class _FakeQueryResponse:
    def __init__(self, points):
        self.points = points


class _FakeClient:
    """Stands in for QdrantClient. ``search()`` raises — if QdrantStore ever
    calls it again (the removed API), the test fails loudly instead of the
    silent "no hits" the real bug produced."""

    def __init__(self, points):
        self._points = points
        self.last_call: dict | None = None

    def query_points(self, **kwargs):
        self.last_call = kwargs
        return _FakeQueryResponse(self._points)

    def search(self, *a, **kw):  # pragma: no cover - guard, must not be hit
        raise AssertionError(
            "QdrantStore.search() called the removed QdrantClient.search() API "
            "instead of query_points()"
        )


def _store_with_fake_client(points) -> tuple[QdrantStore, _FakeClient]:
    store = QdrantStore.__new__(QdrantStore)  # skip __init__: no real connection
    store.collection = "test_collection"
    store.dim = 4
    fake = _FakeClient(points)
    store.client = fake
    return store, fake


def test_search_calls_query_points_with_the_vector():
    store, fake = _store_with_fake_client(
        [_FakePoint("1", 0.9, {"text": "hello", "ticker": "HDFCBANK", "doc_type": "web"})]
    )
    hits = store.search([0.1, 0.2, 0.3, 0.4], limit=3)

    assert fake.last_call["query"] == [0.1, 0.2, 0.3, 0.4]
    assert fake.last_call["collection_name"] == "test_collection"
    assert fake.last_call["limit"] == 3
    assert len(hits) == 1
    assert hits[0].text == "hello"
    assert hits[0].score == 0.9
    assert hits[0].metadata["ticker"] == "HDFCBANK"
    assert "text" not in hits[0].metadata  # text is split out, not duplicated


def test_search_filters_by_ticker_and_doc_type():
    store, fake = _store_with_fake_client([])
    store.search([0.0] * 4, ticker="HDFCBANK", doc_type="fundamentals_snapshot")

    flt = fake.last_call["query_filter"]
    assert flt is not None
    conditions = {c.key: c.match.value for c in flt.must}
    assert conditions == {"ticker": "HDFCBANK", "doc_type": "fundamentals_snapshot"}


def test_search_no_filter_when_no_args():
    store, fake = _store_with_fake_client([])
    store.search([0.0] * 4)
    assert fake.last_call["query_filter"] is None
