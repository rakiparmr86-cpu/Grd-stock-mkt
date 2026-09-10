"""CsvConnector — one or many CSV/TSV files as price/fundamental rows.

Config
------
    {"path": "data/market/RELIANCE.csv", "row_kind": "ohlcv", "ticker": "RELIANCE"}
    {"dir": "data/market", "glob": "*.csv", "row_kind": "ohlcv"}   # ticker = filename stem
    {"path": "fundamentals.csv", "row_kind": "fundamental"}
    {"path": "data.tsv", "sep": "\\t"}
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
    InputConnector,
)
from app.services.market_data.normalization import normalize_ohlcv

log = get_logger(__name__)


class CsvConnector(InputConnector):
    name = "csv"
    default_kind = ConnectorKind.ROWS

    def validate(self) -> None:
        if not self._cfg("path") and not self._cfg("dir"):
            raise ConfigError("csv: provide 'path' or 'dir'")
        if self._cfg("row_kind", "ohlcv") not in ("ohlcv", "fundamental"):
            raise ConfigError("csv: 'row_kind' must be 'ohlcv' or 'fundamental'")

    def _files(self) -> list[Path]:
        if self._cfg("path"):
            return [Path(self._cfg("path"))]
        root = Path(self._cfg("dir"))
        return sorted(root.glob(self._cfg("glob", "*.csv")))

    def fetch(self) -> Iterator[ConnectorResult]:
        sep = self._cfg("sep", ",")
        row_kind = self._cfg("row_kind", "ohlcv")
        ticker_cfg = self._cfg("ticker")
        for path in self._files():
            if not path.exists():
                log.warning("csv not found: %s", path)
                continue
            df = pd.read_csv(path, sep=sep)
            if row_kind == "ohlcv":
                ticker = ticker_cfg or path.stem.upper()
                norm = normalize_ohlcv(df, ticker=ticker, source=f"csv:{path.name}")
                if not norm.empty:
                    yield ConnectorResult.of_rows(norm, "ohlcv", file=path.name)
            else:
                recs = df.to_dict("records")
                if ticker_cfg:
                    for r in recs:
                        r.setdefault("ticker", ticker_cfg)
                yield ConnectorResult(kind=ConnectorKind.ROWS, row_kind="fundamental",
                                      rows=pd.DataFrame(recs), meta={"file": path.name})
