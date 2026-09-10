"""Connector registry — name → class, plus config hints for the API/UI."""

from __future__ import annotations

from typing import Any

from app.services.inputs.base import InputConnector
from app.services.inputs.csv import CsvConnector
from app.services.inputs.excel import ExcelConnector
from app.services.inputs.http_api import HttpApiConnector
from app.services.inputs.image_ocr import ImageOcrConnector
from app.services.inputs.pdf import PdfConnector
from app.services.inputs.web_crawler import WebCrawlerConnector

_REGISTRY: dict[str, type[InputConnector]] = {
    "excel": ExcelConnector,
    "csv": CsvConnector,
    "pdf": PdfConnector,
    "image_ocr": ImageOcrConnector,
    "web_crawler": WebCrawlerConnector,
    "http_api": HttpApiConnector,
}

# Human-facing hints (what each connector emits + the config keys it reads).
_HINTS: dict[str, dict[str, Any]] = {
    "excel": {"emits": "rows|docs", "required": ["path"],
              "optional": ["mode", "row_kind", "sheet", "ticker", "doc_type"]},
    "csv": {"emits": "rows", "required": ["path|dir"],
            "optional": ["glob", "row_kind", "ticker", "sep"]},
    "pdf": {"emits": "docs", "required": ["paths|dir"], "optional": ["glob", "doc_type"]},
    "image_ocr": {"emits": "docs", "required": ["paths|dir"],
                  "optional": ["backend", "lang", "glob", "doc_type", "url", "api_key_env"]},
    "web_crawler": {"emits": "docs", "required": ["start_urls"],
                    "optional": ["allowed_domains", "max_depth", "max_pages",
                                 "same_domain_only", "respect_robots", "delay_seconds",
                                 "include_patterns", "exclude_patterns", "auth", "doc_type"]},
    "http_api": {"emits": "rows|docs", "required": ["url"],
                 "optional": ["mode", "row_kind", "json_path", "next_path", "max_pages",
                              "text_fields", "id_field", "meta_fields", "ticker", "auth"]},
}


def get_connector(name: str, config: dict[str, Any] | None = None) -> InputConnector:
    try:
        cls = _REGISTRY[name]
    except KeyError as exc:
        raise ValueError(
            f"unknown connector {name!r}; choose from {sorted(_REGISTRY)}"
        ) from exc
    return cls(config or {})


def list_connectors() -> list[dict[str, Any]]:
    return [{"name": name, **_HINTS.get(name, {})} for name in sorted(_REGISTRY)]
