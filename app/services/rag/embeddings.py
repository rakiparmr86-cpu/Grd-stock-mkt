"""Embedding generator.

``openai`` — calls the OpenAI embeddings endpoint (needs OPENAI_API_KEY).
``local``  — deterministic hashing embedder; zero deps, good enough to wire the
             pipeline end-to-end and run tests offline. Swap for a real
             sentence-transformers model when you want quality.
"""

from __future__ import annotations

import abc
import hashlib
import math

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class Embedder(abc.ABC):
    dim: int

    @abc.abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class HashingEmbedder(Embedder):
    """Bag-of-hashed-words → L2-normalized vector. Deterministic, offline."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in text.lower().split():
            h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:8], "little")
            v[h % self.dim] += 1.0
            v[(h // self.dim) % self.dim] -= 0.5
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


class OpenAIEmbedder(Embedder):
    def __init__(self, model: str, dim: int) -> None:
        self.model = model
        self.dim = dim
        self._client = None

    def _lazy(self):
        if self._client is None:
            from openai import OpenAI  # imported lazily

            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY not set")
            self._client = OpenAI(api_key=settings.openai_api_key)
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        client = self._lazy()
        resp = client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]


def get_embedder() -> Embedder:
    if settings.embeddings_provider == "openai":
        log.info("using OpenAI embedder: %s", settings.embeddings_model)
        return OpenAIEmbedder(settings.embeddings_model, settings.embeddings_dim)
    log.info("using local hashing embedder (dim=384)")
    return HashingEmbedder(dim=384)
