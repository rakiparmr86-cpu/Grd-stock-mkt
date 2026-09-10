"""Supervisor: decides which analysts to run for this signal, in what order."""

from __future__ import annotations

import time

from app.agents.llm import get_llm
from app.agents.state import AnalysisState
from app.core.logging import get_logger

log = get_logger(__name__)

_ALL_ANALYSTS = ["technical_analyst", "fundamental_analyst", "rag_research"]


def supervisor_node(state: AnalysisState) -> AnalysisState:
    t0 = time.time()
    params = state.get("strategy_params", {})
    requested = params.get("analysts")

    if requested:
        plan = [a for a in requested if a in _ALL_ANALYSTS]
    else:
        # heuristic: always do technical; add fundamental if we have any
        # fundamentals hint; always try RAG (it degrades gracefully).
        plan = ["technical_analyst"]
        if params.get("use_fundamentals", True):
            plan.append("fundamental_analyst")
        plan.append("rag_research")

    signal_types = {s.get("signal_type") for s in state.get("signals", [])}
    rationale = (
        f"{len(state.get('signals', []))} signal(s) {sorted(signal_types)}; "
        f"running {plan}"
    )
    log.info("supervisor plan for %s: %s", state.get("ticker"), plan)

    decision = {
        "agent": "supervisor",
        "step": 0,
        "input": {"signals": state.get("signals", []), "params": params},
        "output": {"plan": plan},
        "rationale": rationale,
        "latency_ms": int((time.time() - t0) * 1000),
    }
    return {"plan": plan, "next_agent": plan[0] if plan else "risk_critic",
            "decisions": [decision]}


def route_after_supervisor(state: AnalysisState) -> str:
    return state.get("next_agent", "risk_critic")
