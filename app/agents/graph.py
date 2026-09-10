"""LangGraph wiring.

    supervisor ──► technical_analyst ──► fundamental_analyst ──► rag_research
        │                │                     │                    │
        └────────────────┴─────────────────────┴────────────────────┘
                                   ▼
                              risk_critic ──► report_writer ──► END

The supervisor writes an ordered ``plan``; each analyst sets ``next_agent`` to
the following planned analyst (or ``risk_critic`` when it's last), so analysts
the supervisor skipped are never executed.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.fundamental_analyst import fundamental_analyst_node
from app.agents.rag_research import rag_research_node
from app.agents.report_writer import report_writer_node
from app.agents.risk_critic import risk_critic_node
from app.agents.state import AnalysisState
from app.agents.supervisor import route_after_supervisor, supervisor_node
from app.agents.technical_analyst import technical_analyst_node
from app.core.logging import get_logger

log = get_logger(__name__)

_ANALYSTS = ("technical_analyst", "fundamental_analyst", "rag_research")


def _route(state: AnalysisState) -> str:
    return state.get("next_agent", "risk_critic")


def build_graph():
    g = StateGraph(AnalysisState)
    g.add_node("supervisor", supervisor_node)
    g.add_node("technical_analyst", technical_analyst_node)
    g.add_node("fundamental_analyst", fundamental_analyst_node)
    g.add_node("rag_research", rag_research_node)
    g.add_node("risk_critic", risk_critic_node)
    g.add_node("report_writer", report_writer_node)

    g.set_entry_point("supervisor")
    branch = {a: a for a in _ANALYSTS} | {"risk_critic": "risk_critic"}
    g.add_conditional_edges("supervisor", route_after_supervisor, branch)
    for a in _ANALYSTS:
        g.add_conditional_edges(a, _route, branch)
    g.add_edge("risk_critic", "report_writer")
    g.add_edge("report_writer", END)
    return g.compile()


_GRAPH = None


def run_analysis(initial: dict[str, Any]) -> AnalysisState:
    """Execute the graph once for a single ticker/signal bundle."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    seed: AnalysisState = {
        "findings": [], "decisions": [], "errors": [],
        **initial,  # type: ignore[typeddict-item]
    }
    log.info("running agent graph for %s (run_id=%s)",
             initial.get("ticker"), initial.get("run_id"))
    return _GRAPH.invoke(seed)  # type: ignore[return-value]
