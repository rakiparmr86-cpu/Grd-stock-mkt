"""HttpApiConnector — a JSON REST endpoint as rows OR documents.

Config
------
    # rows → TimescaleDB
    {"url": "https://vendor/api/ohlcv?symbol=RELIANCE", "mode": "rows",
     "row_kind": "ohlcv", "json_path": "data.candles", "ticker": "RELIANCE",
     "auth": {"type": "bearer", "token_env": "VENDOR_TOKEN"}}

    # docs → Qdrant (each list item becomes a text record)
    {"url": "https://news/api/latest", "mode": "docs", "json_path": "articles",
     "text_fields": ["title", "body"], "id_field": "id",
     "meta_fields": ["url", "published_at"], "doc_type": "news"}

    # pagination (optional): follows ``next_path`` until absent, max ``max_pages``
    {"next_path": "paging.next", "max_pages": 10}
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pandas as pd

from app.core.logging import get_logger
from app.services.inputs.auth import build_auth
from app.services.inputs.base import (
    ConfigError,
    ConnectorKind,
    ConnectorResult,
    DocItem,
    InputConnector,
)
from app.services.market_data.normalization import normalize_ohlcv

log = get_logger(__name__)


def _dig(obj: Any, dotted: str | None) -> Any:
    if not dotted:
        return obj
    for part in dotted.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


class HttpApiConnector(InputConnector):
    name = "http_api"

    def validate(self) -> None:
        if not self._cfg("url"):
            raise ConfigError("http_api: 'url' is required")
        if self._cfg("mode", "rows") not in ("rows", "docs"):
            raise ConfigError("http_api: 'mode' must be 'rows' or 'docs'")

    @property
    def default_kind(self) -> ConnectorKind:  # type: ignore[override]
        return ConnectorKind.DOCS if self._cfg("mode", "rows") == "docs" else ConnectorKind.ROWS

    def _client(self) -> httpx.Client:
        client = httpx.Client(
            headers={"Accept": "application/json",
                     "User-Agent": self._cfg("user_agent", "GrdStkMkt/1.0")},
            timeout=float(self._cfg("timeout", 30)),
            follow_redirects=True,
        )
        build_auth(self._cfg("auth")).prepare(client)
        return client

    def fetch(self) -> Iterator[ConnectorResult]:
        url = self._cfg("url")
        method = self._cfg("method", "GET").upper()
        body = self._cfg("body")
        json_path = self._cfg("json_path")
        next_path = self._cfg("next_path")
        max_pages = int(self._cfg("max_pages", 1))
        mode = self._cfg("mode", "rows")

        with self._client() as client:
            page = 0
            while url and page < max_pages:
                page += 1
                resp = client.request(method, url, json=body if method != "GET" else None)
                resp.raise_for_status()
                payload = resp.json()
                items = _dig(payload, json_path)
                if isinstance(items, dict):
                    items = [items]
                if not isinstance(items, list):
                    log.warning("http_api: json_path %r did not yield a list", json_path)
                    items = []

                if mode == "rows":
                    yield from self._rows(items)
                else:
                    yield self._docs(items, url)

                url = _dig(payload, next_path) if next_path else None

    # -----------------------------------------------------------------
    def _rows(self, items: list[dict]) -> Iterator[ConnectorResult]:
        row_kind = self._cfg("row_kind", "ohlcv")
        df = pd.DataFrame(items)
        if df.empty:
            return
        if row_kind == "ohlcv":
            norm = normalize_ohlcv(df, ticker=self._cfg("ticker"), source="http_api")
            if not norm.empty:
                yield ConnectorResult.of_rows(norm, "ohlcv")
        else:
            if self._cfg("ticker"):
                df["ticker"] = df.get("ticker", self._cfg("ticker"))
            yield ConnectorResult(kind=ConnectorKind.ROWS, row_kind="fundamental", rows=df)

    def _docs(self, items: list[dict], url: str) -> ConnectorResult:
        text_fields = self._cfg("text_fields", ["text"])
        id_field = self._cfg("id_field", "id")
        meta_fields = self._cfg("meta_fields", [])
        doc_type = self._cfg("doc_type", "api")
        ticker = self._cfg("ticker")
        docs: list[DocItem] = []
        for it in items:
            text = "\n\n".join(str(it[f]) for f in text_fields if it.get(f))
            key = f"{url}#{it.get(id_field, len(docs))}"
            meta = {"doc_type": doc_type, "source_url": url,
                    **{f: it.get(f) for f in meta_fields}}
            if it.get("title"):
                meta["title"] = it["title"]
            if ticker:
                meta["tickers"] = [ticker.upper()]
            docs.append(DocItem(text=text, source_key=key, metadata=meta))
        return ConnectorResult.of_docs(docs, url=url)
