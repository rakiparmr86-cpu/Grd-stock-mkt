"""Risk / Critic agent.

Cross-checks the analyst findings for disagreement, thin evidence, and obvious
risk flags (high volatility, overbought entry, high leverage). Produces a
combined conviction score and a go / caution / no-go verdict.
"""

from __future__ import annotations

import time

from app.agents._common import make_decision
from app.agents.llm import get_llm
from app.agents.state import AnalysisState
from app.core.logging import get_logger

log = get_logger(__name__)

_WEIGHTS = {"technical_analyst": 0.45, "fundamental_analyst": 0.35, "rag_research": 0.20}


def risk_critic_node(state: AnalysisState) -> AnalysisState:
    t0 = time.time()
    findings = {f["agent"]: f for f in state.get("findings", [])}
    ind = state.get("indicators", {})

    weighted, wsum = 0.0, 0.0
    for agent, w in _WEIGHTS.items():
        f = findings.get(agent)
        if not f or f.get("stance") == "no_data":
            continue
        weighted += w * float(f.get("score", 0.0))
        wsum += w
    conviction = round(weighted / wsum, 3) if wsum else 0.0

    flags: list[str] = []
    vol = next((v for k, v in ind.items() if k.startswith("volatility_")), None)
    if vol is not None and vol > 0.6:
        flags.append(f"elevated annualized volatility ({vol:.0%})")
    rsi = next((v for k, v in ind.items() if k.startswith("rsi_")), None)
    buy_signal = any(s.get("signal_type") == "buy" for s in state.get("signals", []))
    if buy_signal and rsi is not None and rsi > 70:
        flags.append(f"buy signal into overbought RSI ({rsi:.0f})")

    stances = {a: findings[a].get("stance") for a in findings}
    tech, fund = stances.get("technical_analyst"), stances.get("fundamental_analyst")
    if tech and fund and fund != "no_data":
        bullish_tech = tech == "bullish"
        bullish_fund = fund == "cheap"
        if bullish_tech != bullish_fund:
            flags.append(f"technical ({tech}) vs fundamental ({fund}) disagree")

    if conviction > 0.35 and not flags:
        verdict = "go"
    elif conviction > 0.15:
        verdict = "caution"
    else:
        verdict = "no-go"

    critique = get_llm().invoke(
        f"Critique this trade idea for {state.get('ticker')}. "
        f"Conviction={conviction}, flags={flags}, stances={stances}. "
        f"Give 2-3 sentences on the main risk."
    ).content

    review = {
        "conviction": conviction,
        "verdict": verdict,
        "flags": flags,
        "stances": stances,
        "critique": critique,
    }
    log.info("risk_critic %s -> %s (conviction=%.2f, %d flags)",
             state.get("ticker"), verdict, conviction, len(flags))
    dec = make_decision("risk_critic", 4, {"findings": list(findings)}, review,
                        f"verdict={verdict}", int((time.time() - t0) * 1000))
    return {"risk_review": review, "decisions": [dec]}
