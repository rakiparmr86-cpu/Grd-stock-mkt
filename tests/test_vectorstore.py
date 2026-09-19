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

from types import SimpleNamespace

import pytest

pytest.importorskip("qdrant_client")

from qdrant_client.http.exceptions import UnexpectedResponse  # noqa: E402

from app.services.rag.vectorstore import QdrantStore  # noqa: E402


def _unexpected_response(status_code: int) -> UnexpectedResponse:
    return UnexpectedResponse(status_code=status_code, reason_phrase="", content=b"", headers={})


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

    def scroll(self, **kwargs):
        self.last_call = kwargs
        return self._points, None


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


def test_get_by_source_returns_chunks_sorted_by_index():
    """Standalone document analysis needs a document's full text back in the
    right order — get_by_source uses scroll() (all matching points), not
    query_points()/search() (nearest-to-a-vector), and must not rely on
    Qdrant returning them in chunk order on its own."""
    points = [
        _FakePoint("p2", None, {"text": "second", "source_id": "doc1", "chunk": 1}),
        _FakePoint("p1", None, {"text": "first", "source_id": "doc1", "chunk": 0}),
    ]
    store, fake = _store_with_fake_client(points)
    chunks = store.get_by_source("doc1")

    assert [c["text"] for c in chunks] == ["first", "second"]
    flt = fake.last_call["scroll_filter"]
    conditions = {c.key: c.match.value for c in flt.must}
    assert conditions == {"source_id": "doc1"}


class _FakeCollectionsClient:
    """Stands in for QdrantClient in ensure_collection() tests. ``upsert()``
    calls ``ensure_collection()`` on every call (not once), so under real
    concurrent load two calls can each see the collection missing and both
    try to create it — the loser gets a 409 from Qdrant even though the
    collection ends up exactly as intended. This must be swallowed, not
    surfaced as an ingestion error."""

    def __init__(self, *, existing_names=(), create_raises=None, index_raises=None):
        self._existing = [SimpleNamespace(name=n) for n in existing_names]
        self._create_raises = create_raises
        self._index_raises = index_raises
        self.create_collection_calls = 0
        self.create_payload_index_calls = 0

    def get_collections(self):
        return SimpleNamespace(collections=self._existing)

    def create_collection(self, **kwargs):
        self.create_collection_calls += 1
        if self._create_raises is not None:
            raise self._create_raises

    def create_payload_index(self, *a, **kwargs):
        self.create_payload_index_calls += 1
        if self._index_raises is not None:
            raise self._index_raises


def test_ensure_collection_skips_create_when_already_listed():
    store = QdrantStore.__new__(QdrantStore)
    store.collection = "grd_documents"
    store.dim = 4
    store.client = _FakeCollectionsClient(existing_names=["grd_documents"])

    store.ensure_collection()  # must not raise, must not attempt to create
    assert store.client.create_collection_calls == 0


def test_ensure_collection_creates_when_missing():
    store = QdrantStore.__new__(QdrantStore)
    store.collection = "grd_documents"
    store.dim = 4
    store.client = _FakeCollectionsClient(existing_names=[])

    store.ensure_collection()
    assert store.client.create_collection_calls == 1
    assert store.client.create_payload_index_calls == 3  # ticker, doc_type, source_id


def test_ensure_collection_swallows_409_lost_create_race():
    store = QdrantStore.__new__(QdrantStore)
    store.collection = "grd_documents"
    store.dim = 4
    store.client = _FakeCollectionsClient(
        existing_names=[], create_raises=_unexpected_response(409),
    )

    store.ensure_collection()  # must not raise — the end state is what we wanted anyway


def test_ensure_collection_reraises_non_409_create_failure():
    store = QdrantStore.__new__(QdrantStore)
    store.collection = "grd_documents"
    store.dim = 4
    store.client = _FakeCollectionsClient(
        existing_names=[], create_raises=_unexpected_response(500),
    )

    with pytest.raises(UnexpectedResponse):
        store.ensure_collection()


def test_ensure_collection_swallows_409_on_payload_index_too():
    store = QdrantStore.__new__(QdrantStore)
    store.collection = "grd_documents"
    store.dim = 4
    store.client = _FakeCollectionsClient(
        existing_names=[], index_raises=_unexpected_response(409),
    )

    store.ensure_collection()  # must not raise
