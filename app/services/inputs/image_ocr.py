"""ImageOcrConnector — images (scans, screenshots, charts with captions) → docs.

OCR backend is pluggable:

    {"backend": "stub"}        # default — emits empty text + a warning (offline)
    {"backend": "tesseract", "lang": "eng"}      # needs: pip install ".[ocr]"
    {"backend": "api", "url": "https://ocr.example/v1", "api_key_env": "OCR_KEY"}

Config
------
    {"paths": ["data/documents/scan1.png"]}
    {"dir": "data/documents/images", "glob": "**/*.{png,jpg,jpeg,tif}"}
    {"doc_type": "scanned_document", "backend": "tesseract"}
"""

from __future__ import annotations

import glob as _glob
from collections.abc import Iterator
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.inputs.base import ConfigError, ConnectorResult, DocItem, InputConnector

log = get_logger(__name__)

_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")


def _ocr_stub(path: Path, cfg: dict) -> str:
    log.warning("image_ocr backend=stub: no text extracted from %s "
                "(set backend=tesseract or api)", path.name)
    return ""


def _ocr_tesseract(path: Path, cfg: dict) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("tesseract backend needs: pip install \".[ocr]\"") from exc
    return pytesseract.image_to_string(Image.open(path), lang=cfg.get("lang", "eng"))


def _ocr_api(path: Path, cfg: dict) -> str:
    import os

    url = cfg["url"].rstrip("/") + "/ocr"
    headers = {}
    if cfg.get("api_key_env"):
        key = os.environ.get(cfg["api_key_env"])
        if not key:
            raise RuntimeError(f"OCR api: {cfg['api_key_env']} not set")
        headers["Authorization"] = f"Bearer {key}"
    with open(path, "rb") as fh:
        resp = httpx.post(url, headers=headers, files={"file": fh}, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data.get("text") or data.get("result") or ""


_BACKENDS = {"stub": _ocr_stub, "tesseract": _ocr_tesseract, "api": _ocr_api}


class ImageOcrConnector(InputConnector):
    name = "image_ocr"

    def validate(self) -> None:
        if not self._cfg("paths") and not self._cfg("dir"):
            raise ConfigError("image_ocr: provide 'paths' or 'dir'")
        backend = self._cfg("backend", getattr(settings, "ocr_backend", "stub"))
        if backend not in _BACKENDS:
            raise ConfigError(f"image_ocr: unknown backend {backend!r}")

    def _files(self) -> list[Path]:
        if self._cfg("paths"):
            return [Path(p) for p in self._cfg("paths")]
        root = Path(self._cfg("dir"))
        pat = self._cfg("glob")
        if pat:
            return sorted(Path(p) for p in _glob.glob(str(root / pat), recursive=True))
        return sorted(p for p in root.rglob("*") if p.suffix.lower() in _EXT)

    def fetch(self) -> Iterator[ConnectorResult]:
        backend = self._cfg("backend", getattr(settings, "ocr_backend", "stub"))
        ocr = _BACKENDS[backend]
        doc_type = self._cfg("doc_type", "scanned_document")
        for path in self._files():
            if not path.exists():
                log.warning("image not found: %s", path)
                continue
            try:
                text = ocr(path, self.config).strip()
            except Exception as exc:  # noqa: BLE001
                log.warning("OCR failed %s: %s", path, exc)
                continue
            yield ConnectorResult.of_docs(
                [DocItem(
                    text=text,
                    source_key=str(path.resolve()),
                    metadata={"filename": path.name, "title": path.stem,
                              "doc_type": doc_type, "ocr_backend": backend,
                              "chars": len(text)},
                )]
            )
