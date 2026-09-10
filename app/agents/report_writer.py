"""Report Writer agent.

Assembles the final structured ``report_payload`` the renderer consumes:
recommendation, thesis, per-analyst sections, chart, indicator table.
"""

from __future__ import annotations

import time

import pandas as pd

from app.agents._common import make_decision
from app.agents.llm import get_llm
from app.agents.state import AnalysisState
from app.core.logging import get_logger
from app.services.reports.charts import price_with_indicators_png

log = get_logger(__name__)

_VERDICT_TO_ACTION = {"go": "BUY", "caution": "HOLD", "no-go": "AVOID"}


def report_writer_node(state: AnalysisState) -> AnalysisState:
    t0 = time.time()
    ticker = state.get("ticker", "")
    review = state.get("risk_review", {})
    findings = {f["agent"]: f for f in state.get("findings", [])}

    signal_types = {s.get("signal_type") for s in state.get("signals", [])}
    action = _VERDICT_TO_ACTION.get(review.get("verdict", ""), "HOLD")
    if "sell" in signal_types and action == "BUY":
        action = "HOLD"  # conflicting signal — don't overstate

    thesis = get_llm().invoke(
        f"Write a 2-3 sentence investment thesis for {ticker}. "
        f"Action={action}, conviction={review.get('conviction')}, "
        f"technical={findings.get('technical_analyst', {}).get('narrative', '')[:400]}, "
        f"fundamental={findings.get('fundamental_analyst', {}).get('narrative', '')[:400]}, "
        f"research={findings.get('rag_research', {}).get('narrative', '')[:400]}"
    ).content

    sections = []
    for key, heading in (
        ("technical_analyst", "Technical analysis"),
        ("fundamental_analyst", "Fundamental analysis"),
        ("rag_research", "Document research"),
    ):
        f = findings.get(key)
        if not f:
            continue
        sections.append({
            "heading": heading,
            "body": f.get("narrative") or "",
            "bullets": f.get("bullets", []),
        })
    if review.get("critique"):
        sections.append({"heading": "Risk review",
                         "body": review["critique"],
                         "bullets": review.get("flags", [])})

    chart_b64 = None
    records = state.get("price_frame_records") or []
    if records:
        try:
            frame = pd.DataFrame(records)
            if "ts" in frame.columns:
                frame = frame.set_index("ts")
            chart_b64 = price_with_indicators_png(frame, title=f"{ticker} price")
        except Exception as exc:  # noqa: BLE001
            log.warning("chart render failed: %s", exc)

    payload = {
        "title": f"{ticker} — analysis report",
        "run_id": state.get("run_id"),
        "strategy": state.get("strategy_params", {}).get("name"),
        "recommendation": {
            "action": action,
            "confidence": abs(review.get("conviction", 0.0)),
            "thesis": thesis,
        },
        "signals": state.get("signals", []),
        "sections": sections,
        "indicators": {k: v for k, v in state.get("indicators", {}).items()
                       if v is not None},
        "chart_b64": chart_b64,
    }
    log.info("report_writer %s -> action=%s", ticker, action)
    dec = make_decision("report_writer", 5, {"verdict": review.get("verdict")},
                        {"action": action}, f"action={action}",
                        int((time.time() - t0) * 1000))
    return {"report_payload": payload, "decisions": [dec]}
