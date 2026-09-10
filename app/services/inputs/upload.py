"""Helpers for frontend-driven inputs: save an uploaded file and pick a connector.

A browser upload lands here → `save_upload()` writes it under ``UPLOADS_DIR`` with
a safe, unique name → `connector_for_path()` maps the extension to a connector +
a base config → the API either ingests it once (ad-hoc task) or saves it as an
``InputSource``.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

# extension → (connector name, kind hint)
_DOC_EXT = {".pdf": "pdf",
            ".png": "image_ocr", ".jpg": "image_ocr", ".jpeg": "image_ocr",
            ".tif": "image_ocr", ".tiff": "image_ocr", ".bmp": "image_ocr",
            ".webp": "image_ocr"}
_ROW_EXT = {".csv": "csv", ".tsv": "csv",
            ".xlsx": "excel", ".xls": "excel", ".xlsm": "excel"}
ALLOWED_SUFFIXES = set(_DOC_EXT) | set(_ROW_EXT)

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class UploadError(ValueError):
    pass


def _safe_stem(name: str) -> str:
    stem = Path(name).name
    stem = _SAFE.sub("_", stem).strip("._") or "file"
    return stem[:120]


def save_upload(filename: str, data: bytes, *, subdir: str | None = None) -> Path:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UploadError(
            f"unsupported file type {suffix!r}; allowed: {sorted(ALLOWED_SUFFIXES)}"
        )
    max_bytes = settings.upload_max_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise UploadError(f"file too large ({len(data)/1e6:.1f} MB > {settings.upload_max_mb} MB)")

    root = Path(settings.uploads_dir)
    if subdir:
        root = root / _SAFE.sub("_", subdir)
    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"{uuid.uuid4().hex[:12]}_{_safe_stem(filename)}"
    dest.write_bytes(data)
    log.info("saved upload %s (%d bytes) -> %s", filename, len(data), dest)
    return dest


def connector_for_path(
    path: str | Path,
    *,
    excel_mode: str = "docs",
    row_kind: str = "ohlcv",
    doc_type: str | None = None,
    ticker: str | None = None,
) -> tuple[str, str, dict]:
    """Return ``(connector_name, kind, base_config)`` for a saved file.

    ``kind`` is ``"rows"`` or ``"docs"`` (what this file will produce).
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UploadError(f"no connector for {suffix!r}")

    if suffix in _DOC_EXT:
        name = _DOC_EXT[suffix]
        cfg: dict = {"paths": [str(p)]}
        if doc_type:
            cfg["doc_type"] = doc_type
        if name == "image_ocr":
            cfg["backend"] = settings.ocr_backend
        return name, "docs", cfg

    name = _ROW_EXT[suffix]
    if name == "csv":
        cfg = {"path": str(p), "row_kind": row_kind}
        if suffix == ".tsv":
            cfg["sep"] = "\t"
        if ticker:
            cfg["ticker"] = ticker
        return name, "rows", cfg

    # excel
    if excel_mode == "rows":
        cfg = {"path": str(p), "mode": "rows", "row_kind": row_kind}
        if ticker:
            cfg["ticker"] = ticker
        return name, "rows", cfg
    cfg = {"path": str(p), "mode": "docs"}
    if doc_type:
        cfg["doc_type"] = doc_type
    return name, "docs", cfg
