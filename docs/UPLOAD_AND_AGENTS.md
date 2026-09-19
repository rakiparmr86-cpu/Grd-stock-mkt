# Upload flow and how the agents collaborate

This page explains two things in plain terms:

1. What happens to a file after you upload it (nothing is "analyzed" automatically).
2. How the analysis agents work together when you press Run.

The key idea: **uploading and analyzing are two separate steps.** Upload only stores data. Analysis only happens when you ask for it.

---

## Part 1 — Upload flow (data in)

```
Browser (Inputs tab)
   │  POST /inputs/upload   (file + optional ticker, excel_mode, row_kind)
   ▼
API saves the file to disk, picks a connector by file extension
   │  Celery task: run_adhoc_connector  (returns immediately, work is in background)
   ▼
IngestionRun row created  status="running"      ← what the Uploads tab shows live
   │
   ▼
Connector reads the file  ──►  sink.route_result()  decides where it goes:
```

### Two destinations, depending on file type

| File | Connector mode | Goes to | Used later by |
|---|---|---|---|
| CSV, or Excel with `excel_mode=rows` | **rows** | Postgres/Timescale: `ohlcv` (prices) or `fundamentals` table | Ticker analysis (technical + fundamental agents) |
| PDF, image (OCR), or Excel with `excel_mode=docs` | **docs** | Text is chunked, embedded, stored in **Qdrant** | RAG research agent, and Document analysis |

- `row_kind` (`ohlcv` or `fundamental`) says what a rows-file contains.
- `ticker` tags the data so it can be matched to a stock. A docs file may have no ticker.
- When the connector finishes, the `IngestionRun` becomes `ok` or `error`, with `stats` (rows written, chunks, `source_ids`).
- `source_ids` records which Qdrant documents this upload created, so the exact file can be fetched again later.

### What does NOT happen

Nothing runs analysis for you. The **Uploads** tab has an "Analyzed?" column that only turns to `yes` when:

- **ticker upload:** an analysis run for the same ticker started *after* the upload finished, or
- **document upload:** a Document analysis run exists for that exact upload.

Reason for the manual step: every analysis calls an LLM (cost, time), and uploading ten files should not fire ten reports.

---

## Part 2 — Analysis flow (data out)

You start analysis in one of two ways:

| Path | Trigger | Needs |
|---|---|---|
| **Ticker analysis** | Analysis tab -> Run (`POST /runs`) | At least 30 daily price bars for the ticker |
| **Document analysis** | Uploads tab -> "Analyze document" (`POST /runs/document`) | An uploaded PDF/Excel/image that produced text chunks. No ticker, no prices |

Both create an `AnalysisRun` (the row you see in Recent runs; document runs show "📄 Document" in the Ticker column).

### Ticker analysis, step by step

```
1. Load prices from DB                      (< 30 bars -> "skipped: insufficient_data")
2. Calculation engine: SMA, RSI, MACD, volatility, volume ratio ...
3. Rule / signal engine: do any active rules fire?
        no rule fired and "always run agents" not ticked  ->  stop ("no_signal")
        rule fired, or forced                              ->  continue
4. Multi-agent pipeline (below)
5. Render HTML report, save Report + Signals + AgentDecisions
6. Optional email alert
```

Steps 1-3 are plain code (no LLM), so they are fast and free. The agents only start at step 4. That is what "Gate #1 / Gate #2" means: the two early exits.

### The agents (LangGraph)

Agents do **not** talk to each other directly. They share one **state object** (`app/agents/state.py`), like a shared whiteboard. Each agent reads what it needs, adds its own result, and names who goes next.

```
supervisor -> technical_analyst -> fundamental_analyst -> rag_research
                                                              |
                          (any analyst can jump to)           v
                                                        risk_critic -> report_writer -> END
```

| # | Agent | Reads | Does | Adds to the whiteboard |
|---|---|---|---|---|
| 0 | **Supervisor** | fired signals, strategy params | Picks which analysts run and in what order. Default plan: technical, fundamental, RAG | `plan` |
| 1 | **Technical analyst** | indicators + signals | Deterministic score from SMA / RSI / MACD / volume, then the LLM writes the narrative | a *finding*: stance (bullish / neutral / bearish), score, bullets |
| 2 | **Fundamental analyst** | latest `fundamentals` row, and history if 4+ periods | Scores P/E, debt/equity, margin; adds trend + forecast and ratio report when history exists. Says "no data" if none | a *finding*: valuation stance (cheap / fair / expensive), forecast |
| 3 | **RAG research** | Qdrant documents for the ticker | Searches your uploaded PDFs/Excel (ticker-tagged first, then any indexed document if none match), LLM summarizes guidance and risks with citations. Degrades to "no documents matched" | a *finding*: narrative + citations |
| 4 | **Risk critic** | all findings + indicators | Weighted conviction (technical 45%, fundamental 35%, RAG 20%), flags (high volatility, buy into overbought, technical vs fundamental disagree), verdict `go` / `caution` / `no-go` | `risk_review` |
| 5 | **Report writer** | everything above | Maps verdict to BUY / HOLD / AVOID, writes the thesis, assembles sections and chart | `report_payload` |

How they "collaborate":

- **Sequential hand-off.** Each analyst sets `next_agent` to the next name in the supervisor's plan. Skipped analysts never run.
- **Findings accumulate.** The `findings` list is append-only, so analysts add to it and never overwrite each other.
- **Critic is the cross-check.** It is the only agent that sees all analyst results at once. It is where disagreement (technical bullish, fundamental expensive) is caught and lowers the verdict.
- **Writer is the only one that produces the final answer.** A conflicting `sell` signal downgrades BUY to HOLD.
- **Everything is audited.** Every agent appends a decision (input, output, rationale, latency) to the state. These are saved as `agent_decisions` and shown under "Agent decisions" in Run Detail.

Where the LLM is used: technical narrative, fundamental narrative, RAG summary, risk critique, report thesis. The scores, flags and verdict are plain code, so they are reproducible and testable without an LLM.

### Document analysis (much simpler)

```
Analyze document click
   -> Celery: analyze_document_task
   -> open AnalysisRun (context: kind=document, ingestion_run_id)
   -> fetch ALL chunks of that upload from Qdrant (in order)
   -> ONE LLM call over the text
   -> render HTML report (+ one "document_analyst" decision)
```

No multi-agent graph, no prices, no rules. It answers "what does this document say?" and nothing more.

---

## Part 3 — How the two halves connect

```
Upload CSV prices + fundamentals ─┐
                                  ├─> ticker analysis (technical + fundamental agents)
Upload PDF tagged with ticker ────┴─> also feeds RAG research agent (searches by ticker)

Upload PDF with no ticker ───────────> Document analysis only (standalone)
```

So for the fullest report on a stock, upload all three: prices (CSV), fundamentals (Excel rows), and documents (PDF). Then run **one** ticker analysis. The RAG agent picks up the documents, the fundamental agent picks up the fundamentals, the technical agent uses prices.

## Where things live (code map)

| Concern | File |
|---|---|
| Upload API | `app/api/v1/inputs.py` |
| File -> connector choice | `app/services/inputs/upload.py` |
| Rows vs docs routing | `app/services/inputs/sink.py` |
| Background tasks | `app/workers/tasks/inputs.py`, `app/workers/tasks/analysis.py` |
| Ticker pipeline (gates) | `app/services/orchestrator.py` |
| Agent graph + state | `app/agents/graph.py`, `app/agents/state.py` |
| Each agent | `app/agents/*_analyst.py`, `rag_research.py`, `risk_critic.py`, `report_writer.py` |
| Document analysis | `app/services/document_analysis.py` |
| Vector store | `app/services/rag/vectorstore.py` |
| Live status in UI | Uploads tab, Activity tab, Health tab |

## Not built yet

- PDF connector does not accept a `ticker` (image and Excel-docs do), so a ticker-tagged PDF is not linked to a stock automatically.
- Topic / sector analysis and multi-ticker / portfolio analysis.
- Automatic analysis after upload (deliberately left manual).
