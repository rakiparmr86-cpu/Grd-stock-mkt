"""The agent graph must run offline (EchoLLM) and produce a report payload."""

from __future__ import annotations

import pytest

from app.services.calculations import compute_indicators

pytest.importorskip("langgraph")


def test_graph_runs_offline(ohlcv, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    from app.agents.graph import build_graph

    calc = compute_indicators(ohlcv)
    graph = build_graph()
    state = graph.invoke({
        "run_id": 0,
        "ticker": "TEST",
        "strategy_params": {"analysts": ["technical_analyst"]},
        "signals": [{"rule": "demo", "signal_type": "buy", "strength": 1.0,
                     "price": calc.latest["close"], "matched": True}],
        "indicators": calc.latest,
        "price_frame_records": [],
        "findings": [], "decisions": [], "errors": [],
    })
    assert "report_payload" in state
    assert state["report_payload"]["recommendation"]["action"] in {"BUY", "HOLD", "AVOID"}
    agents_run = {d["agent"] for d in state["decisions"]}
    assert {"supervisor", "technical_analyst", "risk_critic", "report_writer"} <= agents_run
    # fundamental/rag were NOT in the plan -> must not have run
    assert "fundamental_analyst" not in agents_run
