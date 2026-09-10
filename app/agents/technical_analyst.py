"""Technical Analyst agent.

Reads the calculation-engine indicators + triggered signals and produces a
structured technical read. Uses the LLM to phrase the narrative; the numeric
scoring is deterministic so it stays testable offline.
"""

from __future__ import annotations

import time

from app.agents._common import advance_plan, make_decision
from app.agents.llm import get_llm
from app.agents.state import AnalysisState
from app.core.logging import get_logger

log = get_logger(__name__)

_PROMPT = """You are a technical analyst. Given these indicators and triggered
rules for {ticker}, write 3-5 concise bullet points on trend, momentum, and
volume, then a one-line stance (bullish/neutral/bearish).

Indicators: {indicators}
Triggered rules: {signals}
"""


def _score(ind: dict[str, float]) -> tuple[float, list[str]]:
    notes: list[str] = []
    score = 0.0
    close = ind.get("close")
    for ma, w in (("sma_20", 0.15), ("sma_50", 0.15), ("sma_200", 0.2)):
        if close is not None and ind.get(ma) is not None:
            if close > ind[ma]:
                score += w
                notes.append(f"price above {ma}")
            else:
                score -= w
                notes.append(f"price below {ma}")
    rsi = next((v for k, v in ind.items() if k.startswith("rsi_")), None)
    if rsi is not None:
        if rsi < 30:
            score += 0.15
            notes.append(f"RSI oversold ({rsi:.1f})")
        elif rsi > 70:
            score -= 0.15
            notes.append(f"RSI overbought ({rsi:.1f})")
    if ind.get("macd_hist") is not None:
        score += 0.15 if ind["macd_hist"] > 0 else -0.15
        notes.append(f"MACD histogram {'positive' if ind['macd_hist'] > 0 else 'negative'}")
    vr = next((v for k, v in ind.items() if k.startswith("volume_ratio_")), None)
    if vr is not None and vr > 1.5:
        score += 0.1
        notes.append(f"volume {vr:.1f}x average")
    return max(-1.0, min(1.0, score)), notes


def technical_analyst_node(state: AnalysisState) -> AnalysisState:
    t0 = time.time()
    ind = state.get("indicators", {})
    signals = state.get("signals", [])
    score, notes = _score(ind)
    stance = "bullish" if score > 0.2 else "bearish" if score < -0.2 else "neutral"

    llm = get_llm()
    narrative = llm.invoke(
        _PROMPT.format(ticker=state.get("ticker"), indicators=ind, signals=signals)
    ).content

    finding = {
        "agent": "technical_analyst",
        "stance": stance,
        "score": round(score, 3),
        "bullets": notes,
        "narrative": narrative,
    }
    log.info("technical_analyst %s -> %s (%.2f)", state.get("ticker"), stance, score)
    dec = make_decision("technical_analyst", 1, {"indicators": ind}, finding,
                        f"stance={stance} score={score:.2f}",
                        int((time.time() - t0) * 1000))
    return {"findings": [finding], "next_agent": advance_plan(state, "technical_analyst"),
            "decisions": [dec]}
