"""Route a :class:`ConnectorResult` to the right downstream pipeline.

    kind == "docs"  → app.services.rag.ingest.ingest_text  → Qdrant
    kind == "rows"  → app.services.market_data.repository   → TimescaleDB
                       (row_kind "ohlcv" | "fundamental")

Returns a small stats dict per result; the caller aggregates them.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.services.inputs.base import ConnectorKind, ConnectorResult
from app.services.market_data.repository import upsert_fundamentals, upsert_ohlcv
from app.services.rag.ingest import ingest_text

log = get_logger(__name__)


def route_result(result: ConnectorResult, *, source_name: str) -> dict[str, Any]:
    if result.kind == ConnectorKind.DOCS:
        docs_in = chunks = 0
        for doc in result.docs:
            docs_in += 1
            key = doc.source_key or f"{source_name}:{docs_in}"
            meta = {"input_source": source_name, **doc.metadata}
            res = ingest_text(doc.text, source_key=key, metadata=meta)
            chunks += res.get("chunks", 0)
        return {"kind": "docs", "docs": docs_in, "chunks": chunks}

    if result.kind == ConnectorKind.ROWS:
        if result.rows is None or result.rows.empty:
            return {"kind": "rows", "row_kind": result.row_kind, "written": 0}
        if result.row_kind == "ohlcv":
            n = upsert_ohlcv(result.rows)
        elif result.row_kind == "fundamental":
            n = upsert_fundamentals(result.rows.to_dict("records"))
        else:
            log.warning("sink: unknown row_kind %r — skipped", result.row_kind)
            n = 0
        return {"kind": "rows", "row_kind": result.row_kind, "written": n}

    return {"kind": "unknown", "written": 0}


def run_connector(connector, *, source_name: str, dry_run: bool = False,
                  max_results: int | None = None) -> dict[str, Any]:
    """Iterate a connector's ``fetch()`` and route every result.

    ``dry_run`` still iterates (so a crawler actually fetches) but writes nothing;
    useful for the ``POST /inputs/test`` preview.
    """
    stats = {"results": 0, "docs": 0, "chunks": 0, "rows_written": 0, "errors": []}
    for i, result in enumerate(connector.fetch()):
        if max_results is not None and i >= max_results:
            break
        stats["results"] += 1
        try:
            if dry_run:
                if result.kind == ConnectorKind.DOCS:
                    stats["docs"] += len(result.docs)
                else:
                    stats["rows_written"] += 0 if result.rows is None else len(result.rows)
                continue
            got = route_result(result, source_name=source_name)
            stats["docs"] += got.get("docs", 0)
            stats["chunks"] += got.get("chunks", 0)
            stats["rows_written"] += got.get("written", 0)
        except Exception as exc:  # noqa: BLE001 - collect, keep going
            log.exception("sink route failed (%s result %d)", source_name, i)
            stats["errors"].append(str(exc))
    return stats
