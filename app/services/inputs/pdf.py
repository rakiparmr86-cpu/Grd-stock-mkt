"""PdfConnector — one or many PDFs → document library.

Config
------
    {"paths": ["data/documents/AR2024.pdf"]}          # explicit files
    {"dir": "data/documents", "glob": "**/*.pdf"}     # or a folder
    {"doc_type": "annual_report"}                     # optional override
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from app.core.logging import get_logger
from app.services.inputs.base import ConfigError, ConnectorResult, DocItem, InputConnector
from app.services.rag.parser import parse_document

log = get_logger(__name__)


class PdfConnector(InputConnector):
    name = "pdf"

    def validate(self) -> None:
        if not self._cfg("paths") and not self._cfg("dir"):
            raise ConfigError("pdf: provide 'paths' or 'dir'")

    def _files(self) -> list[Path]:
        if self._cfg("paths"):
            return [Path(p) for p in self._cfg("paths")]
        root = Path(self._cfg("dir"))
        return sorted(root.glob(self._cfg("glob", "**/*.pdf")))

    def fetch(self) -> Iterator[ConnectorResult]:
        override = self._cfg("doc_type")
        for path in self._files():
            if not path.exists():
                log.warning("pdf not found: %s", path)
                continue
            try:
                parsed = parse_document(path)
            except Exception as exc:  # noqa: BLE001
                log.warning("pdf parse failed %s: %s", path, exc)
                continue
            meta = dict(parsed.metadata)
            if override:
                meta["doc_type"] = override
            yield ConnectorResult.of_docs(
                [DocItem(text=parsed.text, source_key=str(path.resolve()), metadata=meta)]
            )
