"""Pluggable input layer — one contract for every data source.

A **connector** pulls from somewhere (an Excel file, a PDF, a folder of images,
a website, an HTTP API) and yields :class:`ConnectorResult` objects. A result is
either:

* ``kind == "rows"`` — a normalized pandas frame headed for TimescaleDB
  (``row_kind`` = ``"ohlcv"`` or ``"fundamental"``), or
* ``kind == "docs"`` — a list of :class:`DocItem` headed for the Qdrant document
  library.

The :mod:`app.services.inputs.sink` module routes results to the right pipeline,
so connectors never touch the DB or Qdrant directly.
"""

from __future__ import annotations

import abc
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import pandas as pd


class ConnectorKind(StrEnum):
    ROWS = "rows"
    DOCS = "docs"


@dataclass
class DocItem:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    # a stable key for idempotent re-ingest (URL, path, "sheet:Q1" ...)
    source_key: str = ""


@dataclass
class ConnectorResult:
    kind: ConnectorKind
    docs: list[DocItem] = field(default_factory=list)
    rows: pd.DataFrame | None = None
    row_kind: str | None = None  # "ohlcv" | "fundamental"
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def of_docs(cls, docs: list[DocItem], **meta: Any) -> ConnectorResult:
        return cls(kind=ConnectorKind.DOCS, docs=docs, meta=meta)

    @classmethod
    def of_rows(cls, rows: pd.DataFrame, row_kind: str, **meta: Any) -> ConnectorResult:
        return cls(kind=ConnectorKind.ROWS, rows=rows, row_kind=row_kind, meta=meta)


class ConfigError(ValueError):
    """Raised by ``validate()`` when a connector's config dict is unusable."""


class InputConnector(abc.ABC):
    """Base class. Subclasses set ``name`` and implement ``fetch``."""

    name: str = "base"
    #: what this connector can emit; ``ROWS``/``DOCS`` connectors that support
    #: both (excel, http_api) leave this None and decide from config.
    default_kind: ConnectorKind | None = None

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.validate()

    # -- lifecycle -----------------------------------------------------
    def validate(self) -> None:  # noqa: B027 - optional hook, not abstract
        """Override to fail fast on a bad config (raise :class:`ConfigError`)."""

    @abc.abstractmethod
    def fetch(self) -> Iterator[ConnectorResult]:
        """Yield one or more results. May stream (a crawler yields per page)."""

    # -- helpers -----------------------------------------------------
    def _cfg(self, key: str, default: Any = None, *, required: bool = False) -> Any:
        if required and key not in self.config:
            raise ConfigError(f"{self.name}: missing required config key {key!r}")
        return self.config.get(key, default)
