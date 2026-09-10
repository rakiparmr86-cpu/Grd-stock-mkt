"""Helpers shared by analyst nodes."""

from __future__ import annotations

from app.agents.state import AnalysisState


def advance_plan(state: AnalysisState, just_ran: str) -> str:
    """Return the next node name after ``just_ran`` finishes."""
    plan = state.get("plan", [])
    if just_ran in plan:
        idx = plan.index(just_ran)
        if idx + 1 < len(plan):
            return plan[idx + 1]
    return "risk_critic"


def make_decision(agent: str, step: int, inp: dict, out: dict, rationale: str,
                  latency_ms: int) -> dict:
    return {
        "agent": agent,
        "step": step,
        "input": inp,
        "output": out,
        "rationale": rationale,
        "latency_ms": latency_ms,
    }
