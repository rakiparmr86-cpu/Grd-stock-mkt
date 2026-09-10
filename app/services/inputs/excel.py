"""ExcelConnector — a workbook as price/fundamental rows OR as documents.

Config
------
    # rows → TimescaleDB
    {"path": "data/market/book.xlsx", "mode": "rows", "row_kind": "ohlcv",
     "sheet": "RELIANCE", "ticker": "RELIANCE"}     # sheet/ticker optional
    {"path": "fundamentals.xlsx", "mode": "rows", "row_kind": "fundamental"}

    # docs → Qdrant (each sheet becomes a text table)
    {"path": "notes.xlsx", "mode": "docs", "doc_type": "research_note"}
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from app.core.logging import get_logger
from app.services.inputs.base import (
    ConfigError,
    ConnectorKind,
    ConnectorResult,
    DocItem,
    InputConnector,
)
from app.services.market_data.normalization import normalize_ohlcv

log = get_logger(__name__)


class ExcelConnector(InputConnector):
    name = "excel"

    def validate(self) -> None:
        if not self._cfg("path"):
            raise ConfigError("excel: 'path' is required")
        mode = self._cfg("mode", "rows")
        if mode not in ("rows", "docs"):
            raise ConfigError("excel: 'mode' must be 'rows' or 'docs'")
        if mode == "rows" and self._cfg("row_kind", "ohlcv") not in ("ohlcv", "fundamental"):
            raise ConfigError("excel: 'row_kind' must be 'ohlcv' or 'fundamental'")

    @property
    def default_kind(self) -> ConnectorKind:  # type: ignore[override]
        return ConnectorKind.DOCS if self._cfg("mode", "rows") == "docs" else ConnectorKind.ROWS

    def _sheets(self, xls: pd.ExcelFile) -> list[str]:
        want = self._cfg("sheet")
        if want is None:
            return xls.sheet_names
        return [want] if not isinstance(want, list) else want

    def fetch(self) -> Iterator[ConnectorResult]:
        path = Path(self._cfg("path"))
        if not path.exists():
            raise FileNotFoundError(f"excel workbook not found: {path}")
        xls = pd.ExcelFile(path)
        mode = self._cfg("mode", "rows")

        if mode == "docs":
            doc_type = self._cfg("doc_type", "spreadsheet")
            for sheet in self._sheets(xls):
                df = xls.parse(sheet)
                text = f"# {path.stem} — {sheet}\n\n{df.to_markdown(index=False)}"
                yield ConnectorResult.of_docs([DocItem(
                    text=text, source_key=f"{path.resolve()}::{sheet}",
                    metadata={"filename": path.name, "sheet": sheet,
                              "title": f"{path.stem} / {sheet}", "doc_type": doc_type},
                )])
            return

        row_kind = self._cfg("row_kind", "ohlcv")
        ticker = self._cfg("ticker")
        for sheet in self._sheets(xls):
            df = xls.parse(sheet)
            if row_kind == "ohlcv":
                tk = ticker or (sheet if sheet.upper() == sheet else None)
                norm = normalize_ohlcv(df, ticker=tk, source=f"excel:{path.name}")
                if not norm.empty:
                    yield ConnectorResult.of_rows(norm, "ohlcv", sheet=sheet)
            else:  # fundamental
                recs = df.to_dict("records")
                if ticker:
                    for r in recs:
                        r.setdefault("ticker", ticker)
                yield ConnectorResult(kind=ConnectorKind.ROWS, row_kind="fundamental",
                                      rows=pd.DataFrame(recs), meta={"sheet": sheet})
