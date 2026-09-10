from __future__ import annotations

from collections.abc import Iterator

import pandas as pd
import pytest

from app.services.inputs import ConnectorKind, ConnectorResult, DocItem, get_connector
from app.services.inputs.auth import BearerAuth, FormLoginAuth, NoAuth, build_auth
from app.services.inputs.base import ConfigError, InputConnector
from app.services.inputs.registry import list_connectors
from app.services.inputs.sink import run_connector
from app.services.inputs.web_crawler import WebCrawlerConnector, _strip_html


# ── registry ────────────────────────────────────────────────────────
def test_registry_lists_all_connectors():
    names = {c["name"] for c in list_connectors()}
    assert names == {"excel", "csv", "pdf", "image_ocr", "web_crawler", "http_api"}


def test_get_connector_unknown_raises():
    with pytest.raises(ValueError):
        get_connector("telepathy", {})


def test_connector_validates_config_on_construction():
    with pytest.raises(ConfigError):
        get_connector("web_crawler", {})  # missing start_urls
    with pytest.raises(ConfigError):
        get_connector("csv", {})  # missing path/dir


# ── auth ────────────────────────────────────────────────────────────
def test_build_auth_types():
    assert isinstance(build_auth(None), NoAuth)
    assert isinstance(build_auth({"type": "bearer", "token_env": "X"}), BearerAuth)
    assert isinstance(build_auth({"type": "form_login", "login_url": "u",
                                  "user_env": "U", "password_env": "P"}), FormLoginAuth)
    with pytest.raises(ValueError):
        build_auth({"type": "mind-meld"})


def test_bearer_auth_missing_env_raises(monkeypatch):
    monkeypatch.delenv("NOPE_TOKEN", raising=False)
    import httpx

    with pytest.raises(RuntimeError):
        BearerAuth("NOPE_TOKEN").prepare(httpx.Client())


# ── web crawler ────────────────────────────────────────────────────
def test_strip_html_extracts_title_text_links():
    html = """<html><head><title>Sched</title></head><body>
      <script>ignore()</script><p>Hello world</p>
      <a href="/Schedular/Detail/1">d1</a><a href="https://other.com/x">ext</a>
    </body></html>"""
    title, text, hrefs = _strip_html(html)
    assert title == "Sched"
    assert "Hello world" in text and "ignore" not in text
    assert "/Schedular/Detail/1" in hrefs


class _Resp:
    def __init__(self, text: str, status: int = 200, ct: str = "text/html; charset=utf-8"):
        self.text, self.status_code, self.headers = text, status, {"content-type": ct}


class _FakeClient:
    def __init__(self, pages: dict[str, str]):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url: str):
        if url in self.pages:
            return _Resp(self.pages[url])
        return _Resp("<html></html>", status=404)


def test_crawler_follows_links_within_domain_and_depth(monkeypatch):
    pages = {
        "https://console.grdworld.com/Schedular/Index":
            '<title>Index</title><a href="/Schedular/Detail/1">d1</a>'
            '<a href="https://evil.com/x">ext</a>',
        "https://console.grdworld.com/Schedular/Detail/1":
            "<title>Detail 1</title><p>row body</p>",
    }
    conn = WebCrawlerConnector({
        "start_urls": ["https://console.grdworld.com/Schedular/Index"],
        "max_depth": 1, "respect_robots": False, "delay_seconds": 0,
    })
    monkeypatch.setattr(conn, "_client", lambda: _FakeClient(pages))
    results = list(conn.fetch())
    urls = [r.docs[0].metadata["url"] for r in results]
    assert "https://console.grdworld.com/Schedular/Index" in urls
    assert "https://console.grdworld.com/Schedular/Detail/1" in urls
    assert all("evil.com" not in u for u in urls)  # off-domain rejected
    assert all(r.kind == ConnectorKind.DOCS for r in results)


def test_crawler_respects_max_pages(monkeypatch):
    pages = {f"https://x.test/p{i}": f'<a href="/p{i+1}">n</a>' for i in range(10)}
    conn = WebCrawlerConnector({
        "start_urls": ["https://x.test/p0"], "max_depth": 9, "max_pages": 3,
        "respect_robots": False, "delay_seconds": 0,
    })
    monkeypatch.setattr(conn, "_client", lambda: _FakeClient(pages))
    assert len(list(conn.fetch())) == 3


# ── csv connector → rows ───────────────────────────────────────────
def test_csv_connector_emits_normalized_ohlcv(tmp_path):
    p = tmp_path / "RELIANCE.csv"
    p.write_text("date,open,high,low,close,volume\n"
                 "2024-01-01,100,105,99,104,1000\n"
                 "2024-01-02,104,106,103,105,1200\n")
    conn = get_connector("csv", {"path": str(p), "row_kind": "ohlcv"})
    results = list(conn.fetch())
    assert len(results) == 1
    res = results[0]
    assert res.kind == ConnectorKind.ROWS and res.row_kind == "ohlcv"
    assert list(res.rows["ticker"].unique()) == ["RELIANCE"]
    assert {"open", "high", "low", "close", "volume"} <= set(res.rows.columns)


# ── image_ocr stub (offline, no PIL) ──────────────────────────────
def test_image_ocr_stub_yields_empty_doc(tmp_path):
    img = tmp_path / "scan.png"
    img.write_bytes(b"\x89PNG\r\n")  # stub backend never opens it
    conn = get_connector("image_ocr", {"paths": [str(img)], "backend": "stub"})
    results = list(conn.fetch())
    assert len(results) == 1
    doc = results[0].docs[0]
    assert doc.text == "" and doc.metadata["ocr_backend"] == "stub"


# ── sink routing ─────────────────────────────────────────────────
class _StubConnector(InputConnector):
    name = "stub"

    def fetch(self) -> Iterator[ConnectorResult]:
        yield ConnectorResult.of_docs([DocItem(text="hello doc", source_key="k1",
                                               metadata={"doc_type": "news"})])
        yield ConnectorResult.of_rows(
            pd.DataFrame([{"ticker": "T", "open": 1, "high": 2, "low": 1, "close": 2,
                           "volume": 10}]), "ohlcv")


def test_run_connector_routes_docs_and_rows(monkeypatch):
    calls: dict[str, list] = {}

    def _fake_ingest(text, **kw):
        calls.setdefault("docs", []).append(text)
        return {"chunks": 2}

    def _fake_upsert(df, **kw):
        calls.setdefault("rows", []).append(len(df))
        return len(df)

    monkeypatch.setattr("app.services.inputs.sink.ingest_text", _fake_ingest)
    monkeypatch.setattr("app.services.inputs.sink.upsert_ohlcv", _fake_upsert)
    stats = run_connector(_StubConnector({}), source_name="unit")
    assert stats["results"] == 2
    assert stats["chunks"] == 2
    assert stats["docs"] == 1
    assert stats["rows_written"] == 1
    assert calls["docs"] == ["hello doc"]


def test_run_connector_dry_run_writes_nothing(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("dry_run must not write")

    monkeypatch.setattr("app.services.inputs.sink.ingest_text", _boom)
    monkeypatch.setattr("app.services.inputs.sink.upsert_ohlcv", _boom)
    stats = run_connector(_StubConnector({}), source_name="unit", dry_run=True)
    assert stats["results"] == 2 and stats["docs"] == 1
