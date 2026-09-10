"""RAG Research agent.

Retrieves the most relevant document chunks from Qdrant for the ticker and asks
the LLM to synthesize qualitative context (guidance, risks, management tone,
recent announcements). Fully degrades when Qdrant is empty/unreachable.
"""

from __future__ import annotations

import time

from app.agents._common import advance_plan, make_decision
from app.agents.llm import get_llm
from app.agents.state import AnalysisState
from app.core.logging import get_logger
from app.services.rag.embeddings import get_embedder
from app.services.rag.vectorstore import get_store

log = get_logger(__name__)

_QUERY_TMPL = (
    "{ticker} outlook: recent results, management guidance, risks, "
    "corporate announcements, analyst commentary"
)
_PROMPT = """You are a research analyst. Using ONLY the context below, write
4-6 bullets on {ticker}: recent developments, guidance, and key risks. If the
context is thin, say so.

Context:
{context}
"""


def rag_research_node(state: AnalysisState) -> AnalysisState:
    t0 = time.time()
    ticker = state.get("ticker", "")
    hits: list = []
    try:
        embedder = get_embedder()
        store = get_store(dim=embedder.dim)
        qvec = embedder.embed_one(_QUERY_TMPL.format(ticker=ticker))
        hits = store.search(qvec, limit=6, ticker=ticker) or store.search(qvec, limit=6)
    except Exception as exc:  # noqa: BLE001
        log.warning("RAG retrieval failed: %s", exc)

    if not hits:
        finding = {
            "agent": "rag_research",
            "score": 0.0,
            "bullets": ["No indexed documents matched this ticker."],
            "citations": [],
            "narrative": "",
        }
        dec = make_decision("rag_research", 3, {"ticker": ticker}, finding,
                            "no hits", int((time.time() - t0) * 1000))
        return {"findings": [finding],
                "next_agent": advance_plan(state, "rag_research"),
                "decisions": [dec]}

    context = "\n\n".join(f"[{i+1}] ({h.metadata.get('doc_type','?')}) {h.text[:800]}"
                          for i, h in enumerate(hits))
    narrative = get_llm().invoke(_PROMPT.format(ticker=ticker, context=context)).content
    citations = [
        {"title": h.metadata.get("title"), "doc_type": h.metadata.get("doc_type"),
         "filename": h.metadata.get("filename"), "score": round(h.score, 3)}
        for h in hits
    ]

    finding = {
        "agent": "rag_research",
        "score": round(min(1.0, sum(h.score for h in hits) / len(hits)), 3),
        "bullets": [f"{len(hits)} relevant chunks retrieved"],
        "citations": citations,
        "narrative": narrative,
    }
    log.info("rag_research %s -> %d hits", ticker, len(hits))
    dec = make_decision("rag_research", 3, {"query": _QUERY_TMPL.format(ticker=ticker)},
                        {"citations": citations}, f"{len(hits)} hits",
                        int((time.time() - t0) * 1000))
    return {"findings": [finding],
            "next_agent": advance_plan(state, "rag_research"),
            "decisions": [dec]}
