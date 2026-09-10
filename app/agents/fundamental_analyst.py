"""Fundamental Analyst agent.

Pulls the latest ``Fundamental`` row for the ticker and scores valuation /
profitability / leverage. Degrades to "no data" cleanly when fundamentals are
absent.
"""

from __future__ import annotations

import time

from sqlalchemy import select

from app.agents._common import advance_plan, make_decision
from app.agents.llm import get_llm
from app.agents.state import AnalysisState
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.market import Fundamental

log = get_logger(__name__)

_PROMPT = """You are a fundamental analyst. Summarize the financial health of
{ticker} in 3-4 bullets given: {metrics}. End with valuation stance
(cheap/fair/expensive)."""


def _latest_fundamental(ticker: str) -> Fundamental | None:
    with session_scope() as db:
        row = db.execute(
            select(Fundamental)
            .where(Fundamental.ticker == ticker.upper())
            .order_by(Fundamental.reported_at.desc().nullslast(), Fundamental.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is not None:
            db.expunge(row)
        return row


def _score(f: Fundamental) -> tuple[float, list[str]]:
    notes: list[str] = []
    score = 0.0
    if f.pe is not None:
        if f.pe < 15:
            score += 0.25
            notes.append(f"low P/E ({f.pe:.1f})")
        elif f.pe > 40:
            score -= 0.25
            notes.append(f"rich P/E ({f.pe:.1f})")
    if f.debt_to_equity is not None:
        if f.debt_to_equity < 0.5:
            score += 0.2
            notes.append(f"low leverage (D/E {f.debt_to_equity:.2f})")
        elif f.debt_to_equity > 2:
            score -= 0.2
            notes.append(f"high leverage (D/E {f.debt_to_equity:.2f})")
    if f.net_income is not None and f.revenue:
        margin = f.net_income / f.revenue
        score += 0.15 if margin > 0.1 else -0.1
        notes.append(f"net margin {margin:.1%}")
    return max(-1.0, min(1.0, score)), notes


def fundamental_analyst_node(state: AnalysisState) -> AnalysisState:
    t0 = time.time()
    ticker = state.get("ticker", "")
    f = _latest_fundamental(ticker)

    if f is None:
        finding = {
            "agent": "fundamental_analyst",
            "stance": "no_data",
            "score": 0.0,
            "bullets": ["No fundamentals on file for this ticker."],
            "narrative": "",
        }
        dec = make_decision("fundamental_analyst", 2, {"ticker": ticker}, finding,
                            "no fundamentals", int((time.time() - t0) * 1000))
        return {"findings": [finding],
                "next_agent": advance_plan(state, "fundamental_analyst"),
                "decisions": [dec]}

    score, notes = _score(f)
    stance = "cheap" if score > 0.2 else "expensive" if score < -0.2 else "fair"
    metrics = {"period": f.period, "pe": f.pe, "eps": f.eps, "revenue": f.revenue,
               "net_income": f.net_income, "debt_to_equity": f.debt_to_equity, **f.metrics}
    narrative = get_llm().invoke(_PROMPT.format(ticker=ticker, metrics=metrics)).content

    finding = {
        "agent": "fundamental_analyst",
        "stance": stance,
        "score": round(score, 3),
        "bullets": notes,
        "narrative": narrative,
        "period": f.period,
    }
    log.info("fundamental_analyst %s -> %s (%.2f)", ticker, stance, score)
    dec = make_decision("fundamental_analyst", 2, {"metrics": metrics}, finding,
                        f"stance={stance} score={score:.2f}",
                        int((time.time() - t0) * 1000))
    return {"findings": [finding],
            "next_agent": advance_plan(state, "fundamental_analyst"),
            "decisions": [dec]}
