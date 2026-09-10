"""LLM factory + a safe offline fallback.

If ``LLM_PROVIDER=openai`` and a key is present we return a real ChatOpenAI.
Otherwise every agent falls back to :class:`EchoLLM`, which returns deterministic
templated text so the whole graph runs with no network / no key.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class LLMResponse:
    content: str

    def json(self, default: Any = None) -> Any:
        try:
            return json.loads(self.content)
        except json.JSONDecodeError:
            return default


class EchoLLM:
    """Offline stand-in. Produces plausible structured output from the prompt."""

    provider = "echo"

    def invoke(self, prompt: str, *, as_json: bool = False) -> LLMResponse:
        if as_json:
            return LLMResponse(json.dumps({
                "summary": "offline stub: no LLM configured",
                "bullets": ["Set LLM_PROVIDER=openai and OPENAI_API_KEY for real analysis."],
                "score": 0.5,
            }))
        return LLMResponse("Offline stub response. Configure an LLM provider for real output.")


class OpenAILLM:
    provider = "openai"

    def __init__(self, model: str) -> None:
        from langchain_openai import ChatOpenAI

        self._llm = ChatOpenAI(model=model, api_key=settings.openai_api_key, temperature=0.2)

    def invoke(self, prompt: str, *, as_json: bool = False) -> LLMResponse:
        msg = self._llm.invoke(prompt)
        return LLMResponse(msg.content if isinstance(msg.content, str) else str(msg.content))


def get_llm() -> OpenAILLM | EchoLLM:
    if settings.llm_provider == "openai" and settings.openai_api_key:
        log.info("LLM: OpenAI %s", settings.llm_model)
        return OpenAILLM(settings.llm_model)
    log.warning("LLM: offline echo stub (no provider/key configured)")
    return EchoLLM()
