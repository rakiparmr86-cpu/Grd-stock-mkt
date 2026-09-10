"""Document parser + metadata enrichment.

Supported: .pdf (pypdf), .txt / .md, .html (very light tag strip).
Returns plain text plus best-effort metadata (title, detected tickers, doc type).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_TICKER_RE = re.compile(r"\b[A-Z][A-Z0-9&\-]{1,14}\b")
_DOCTYPE_HINTS = {
    "annual report": "annual_report",
    "quarterly": "quarterly_report",
    "q1": "quarterly_report",
    "q2": "quarterly_report",
    "q3": "quarterly_report",
    "q4": "quarterly_report",
    "announcement": "announcement",
    "press release": "news",
    "news": "news",
    "research": "research_note",
}


@dataclass
class ParsedDocument:
    text: str
    metadata: dict = field(default_factory=dict)


def _strip_html(raw: str) -> str:
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _detect_doctype(text: str, filename: str) -> str:
    haystack = f"{filename}\n{text[:2000]}".lower()
    for hint, dtype in _DOCTYPE_HINTS.items():
        if hint in haystack:
            return dtype
    return "other"


def _detect_tickers(text: str, known: set[str] | None = None) -> list[str]:
    cands = set(_TICKER_RE.findall(text[:5000]))
    if known:
        cands &= known
    # drop obvious English words / units
    noise = {"THE", "AND", "FOR", "WITH", "THIS", "THAT", "FROM", "INR", "USD", "LTD", "PLC"}
    return sorted(c for c in cands if c not in noise)[:10]


def parse_document(
    path: str | Path,
    *,
    known_tickers: set[str] | None = None,
    extra_metadata: dict | None = None,
) -> ParsedDocument:
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix == ".pdf":
        from pypdf import PdfReader  # lazy — only PDFs need it

        reader = PdfReader(str(p))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages)
        title = (reader.metadata.title if reader.metadata else None) or p.stem
    elif suffix in {".txt", ".md"}:
        text = p.read_text(encoding="utf-8", errors="ignore")
        title = p.stem
    elif suffix in {".html", ".htm"}:
        text = _strip_html(p.read_text(encoding="utf-8", errors="ignore"))
        title = p.stem
    else:
        raise ValueError(f"unsupported document type: {suffix}")

    meta = {
        "source_path": str(p),
        "filename": p.name,
        "title": title,
        "doc_type": _detect_doctype(text, p.name),
        "tickers": _detect_tickers(text, known_tickers),
        "chars": len(text),
    }
    if extra_metadata:
        meta.update(extra_metadata)
    return ParsedDocument(text=text, metadata=meta)
