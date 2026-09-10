"""Token-ish text chunker with overlap.

Uses a word count as a cheap proxy for tokens (~0.75 words/token). Splits on
paragraph boundaries first, then packs paragraphs into windows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PARA_RE = re.compile(r"\n\s*\n")
_WS_RE = re.compile(r"[ \t]+")


@dataclass
class Chunk:
    index: int
    text: str
    metadata: dict


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def chunk_text(
    text: str,
    *,
    metadata: dict | None = None,
    max_words: int = 350,
    overlap_words: int = 60,
) -> list[Chunk]:
    metadata = metadata or {}
    paragraphs = [p for p in (_clean(p) for p in _PARA_RE.split(text)) if p]
    if not paragraphs:
        return []

    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_words = 0

    def flush() -> None:
        nonlocal buf, buf_words
        if not buf:
            return
        body = " ".join(buf).strip()
        chunks.append(Chunk(index=len(chunks), text=body,
                            metadata={**metadata, "chunk": len(chunks)}))
        if overlap_words > 0:
            tail = body.split()[-overlap_words:]
            buf = [" ".join(tail)]
            buf_words = len(tail)
        else:
            buf, buf_words = [], 0

    for para in paragraphs:
        words = para.split()
        if buf_words + len(words) > max_words and buf:
            flush()
        # a single mega-paragraph: hard-split it
        if len(words) > max_words:
            for i in range(0, len(words), max_words - overlap_words):
                piece = " ".join(words[i : i + max_words])
                chunks.append(Chunk(index=len(chunks), text=piece,
                                    metadata={**metadata, "chunk": len(chunks)}))
            continue
        buf.append(para)
        buf_words += len(words)

    flush()
    return chunks
