# The agents: how they collaborate (interview guide)

A walkthrough of the multi-agent part of this project, from the request that starts it to the rows it writes, with a **real run** (INFY, captured from this codebase) and the questions an interviewer is likely to ask.

Files referenced: `app/agents/` (graph, state, six agents), `app/services/orchestrator.py` (the pipeline around the graph), `app/workers/tasks/analysis.py` (Celery entry), `app/services/document_analysis.py` (the single-step document path).

---

## 1. The 30-second pitch

> "Analysis runs as a pipeline. Cheap, deterministic code (indicators and a rule engine) decides whether anything is worth analyzing. If so, a LangGraph of six nodes runs: a supervisor picks which analysts to run, three analysts (technical, fundamental, document research) each add a finding to a shared state, a risk critic cross-checks all findings into one verdict, and a report writer turns that into a recommendation and an HTML report. Every step is logged as an audit row. The LLM only writes prose; every score, flag and verdict is plain code, so the whole thing runs and tests offline."

---

## 2. Big picture

```
POST /runs  ──►  Celery task  ──►  orchestrator.analyze_ticker()
                                     │
                     ┌───────────────┴───────────────────────────────┐
                     │  PLAIN CODE (no LLM, fast, free)              │
                     │  1. load OHLCV            < 30 bars → SKIP    │  Gate 1
                     │  2. calculation engine    (SMA, RSI, MACD...) │
                     │  3. rule / signal engine  nothing fires and   │  Gate 2
                     │     and not forced → STOP ("no_signal")       │
                     └───────────────┬───────────────────────────────┘
                                     ▼
                     ┌───────────────────────────────────────────────┐
                     │  AGENT GRAPH (LangGraph, 6 nodes, sequential) │
                     │                                               │
                     │  supervisor ─► technical ─► fundamental ─►    │
                     │                RAG research ─► risk_critic ─► │
                     │                report_writer ─► END           │
                     └───────────────┬───────────────────────────────┘
                                     ▼
                  render HTML  ·  save Report + Signals + AgentDecisions
                  optional email alert
```

Two ideas to keep in mind:

1. **The agents are the expensive part, so they are behind two gates.** Most requests stop before the graph. That is deliberate cost control.
2. **"Agent" here means a graph node with a single responsibility that reads and writes shared state.** It is not an autonomous loop that picks its own tools. That choice is discussed in section 9.

---

## 3. The shared state: how agents "talk"

Agents never call each other. They read and write one typed dictionary, `AnalysisState` (`app/agents/state.py`). Think of it as a whiteboard that travels through the graph.

| Field | Written by | Meaning |
|---|---|---|
| `ticker`, `run_id`, `strategy_params` | orchestrator | inputs |
| `signals` | orchestrator | rules that fired |
| `indicators` | orchestrator | latest SMA/RSI/MACD/... values |
| `price_frame_records` | orchestrator | last ~260 bars, for the chart |
| `plan` | supervisor | ordered list of analysts to run |
| `next_agent` | every node | who runs next (the routing signal) |
| `findings` | each analyst | **append-only list**, one dict per analyst |
| `risk_review` | risk critic | conviction, verdict, flags, critique |
| `report_payload` | report writer | final structured report |
| `decisions` | every node | **append-only audit log** |
| `errors` | (declared, currently unused) | reserved for node errors |

**The important detail:** `findings`, `decisions` and `errors` are declared as `Annotated[list, operator.add]`. That is a LangGraph **reducer**: when a node returns `{"findings": [x]}`, LangGraph *concatenates* it onto the existing list instead of replacing it. Without that, the second analyst would overwrite the first. This is the mechanism that makes several agents collaborate on one result safely.

Each node returns only the keys it changes (a partial update), not the whole state.

---

## 4. The six nodes

### 4.1 Supervisor: the planner (`supervisor.py`)
- **Reads:** fired signals, `strategy_params`.
- **Does:** builds the ordered plan. If the strategy names analysts (`params["analysts"]`), it uses them. Otherwise: always technical, fundamental if `use_fundamentals` is true (default), and always RAG.
- **Writes:** `plan`, `next_agent = plan[0]`, one decision row.
- **LLM:** none. It is a heuristic router. (It imports the LLM factory but does not call it.)
- **Why it exists:** it makes the pipeline configurable per strategy (skip fundamentals for a pure technical strategy) without changing the graph.

### 4.2 Technical analyst (`technical_analyst.py`)
- **Reads:** `indicators`, `signals`.
- **Does:** a deterministic score from indicators, clipped to [-1, 1]:

  | Condition | Points |
  |---|---|
  | close vs SMA20 / SMA50 / SMA200 | ±0.15 / ±0.15 / ±0.20 |
  | RSI < 30 / > 70 | +0.15 / −0.15 |
  | MACD histogram positive / negative | +0.15 / −0.15 |
  | volume ratio > 1.5 | +0.10 |

  Stance: score > 0.2 bullish, < −0.2 bearish, else neutral.
- **Writes:** a finding `{agent, stance, score, bullets, narrative}`.
- **LLM:** only for the `narrative` sentence.

### 4.3 Fundamental analyst (`fundamental_analyst.py`)
- **Reads:** the latest `fundamentals` row for the ticker, plus full history.
- **Does:** scores P/E, debt/equity and net margin; when 4 or more periods exist it also runs the statistics engine (CAGR, ETS forecast with 95% interval, revenue-to-profit regression, backtest) and the ratio report (ROE, margins, EV multiples).
- **Writes:** a finding with `stance` (cheap / fair / expensive), the forecast and the full reports (kept so the Excel export needs no recomputation).
- **Degrades:** no fundamentals on file → finding with `stance: "no_data"`, score 0, and the critic ignores it.

### 4.4 RAG research (`rag_research.py`)
- **Reads:** the ticker.
- **Does:** embeds a query, searches Qdrant (top 6 by cosine similarity, ticker-tagged chunks first, then any chunk), and asks the LLM to summarize the hits with citations.
- **Writes:** a finding with `narrative`, `citations`, and a `score` equal to the average similarity.
- **Degrades:** Qdrant down, empty, or no hits → a finding saying "No indexed documents matched", never an exception (the retrieval is wrapped in `try/except`).

### 4.5 Risk critic (`risk_critic.py`): the aggregator
- **Reads:** all `findings`, plus indicators and signals.
- **Does:**
  - **Conviction** = weighted average of analyst scores, weights technical 0.45, fundamental 0.35, RAG 0.20. Analysts with `no_data` are dropped and the weights re-normalised.
  - **Flags:** annualized volatility above 60%; a buy signal while RSI is above 70; technical and fundamental stances disagree.
  - **Verdict:** `go` if conviction > 0.35 and no flags; `caution` if > 0.15; otherwise `no-go`.
- **Writes:** `risk_review`.
- **LLM:** only for a 2-3 sentence critique of the main risk.
- **This is the real "collaboration" step:** it is the only node that sees every analyst's output at once, so it is where disagreement between analysts is detected and turned into a lower verdict.

### 4.6 Report writer (`report_writer.py`)
- **Reads:** `risk_review`, findings, signals, indicators, price records.
- **Does:** maps verdict to action (go → BUY, caution → HOLD, no-go → AVOID). A conflicting `sell` signal downgrades BUY to HOLD. Builds the sections (technical, fundamental, research, risk review), a chart, the indicator table and the forecast.
- **Writes:** `report_payload`.
- **LLM:** only the 2-3 sentence thesis.

---

## 5. How routing works

`graph.py` builds a `StateGraph(AnalysisState)`:

```python
set_entry_point("supervisor")
add_conditional_edges("supervisor", route_after_supervisor, branch)
for a in ("technical_analyst", "fundamental_analyst", "rag_research"):
    add_conditional_edges(a, _route, branch)      # reads state["next_agent"]
add_edge("risk_critic", "report_writer")
add_edge("report_writer", END)
```

- The supervisor sets `next_agent` to the first analyst in its plan.
- Each analyst finishes by calling `advance_plan(state, "<me>")`, which returns the next name in the plan, or `"risk_critic"` when it was last.
- A **conditional edge** reads `state["next_agent"]` and jumps there. So the graph shape is fixed, but the path is decided at run time by the plan.
- Analysts the supervisor skipped are never run.
- The compiled graph is cached in a module-level variable (`_GRAPH`), so it is built once per worker process.

Execution is **sequential**. The analysts are independent of each other, so this could be parallel; it is sequential because the run is dominated by the LLM and Qdrant calls of a single ticker and the simplicity is worth more than saved seconds (section 9).

---

## 6. A real run, step by step (INFY, captured from this code)

Input: 500 daily bars ingested, `force_agents=True` (no rule fired, so the run was forced past Gate 2). LLM not configured, so narratives are the offline stub; **all scores and verdicts below are real**.

**Before the graph (plain code)**

```
close 2099.89 | SMA20 2172.78 | SMA50 2231.90 | SMA200 1653.73
RSI14 40.41 | MACD histogram -12.40 | volume ratio 1.00 | volatility(20d) 24%
Gate 1: 500 bars >= 30 → pass.   Gate 2: 0 signals, but forced → continue.
```

**Inside the graph**

| Step | Node | Latency | What it decided |
|---|---|---|---|
| 0 | supervisor | 0 ms | plan = `[technical_analyst, fundamental_analyst, rag_research]` |
| 1 | technical_analyst | 106 ms | stance **bearish**, score **−0.25** |
| 2 | fundamental_analyst | 8 ms | **no_data** (no fundamentals loaded for INFY), score 0 |
| 3 | rag_research | 3138 ms | 6 hits from Qdrant (first call includes model and client warm-up) |
| 4 | risk_critic | 0 ms | conviction **−0.171**, verdict **no-go**, no flags |
| 5 | report_writer | 525 ms | action **AVOID**, confidence 0.171 |

**The arithmetic, so you can defend it**

Technical score:

| Rule | Result | Points |
|---|---|---|
| close 2099.89 < SMA20 2172.78 | below | −0.15 |
| close < SMA50 2231.90 | below | −0.15 |
| close > SMA200 1653.73 | above | +0.20 |
| RSI 40.4 (not < 30, not > 70) | neutral | 0 |
| MACD histogram −12.4 | negative | −0.15 |
| volume ratio 1.00 (not > 1.5) | nothing | 0 |
| **Total** | | **−0.25 → bearish** |

Critic: fundamental is `no_data`, so only technical (0.45) and RAG (0.20) count and the weights are re-normalised by their sum (0.65). Conviction −0.171 is below 0.15 → **no-go** → the writer maps it to **AVOID**. No risk flags fired (volatility 24% is under 60%, no buy signal, and there was no fundamental stance to disagree with).

**What the outputs became**
- `agent_decisions`: 6 rows (one per node) with input, output, rationale and latency.
- `reports`: 1 row + an HTML file with 4 sections (Technical analysis, Fundamental analysis, Document research, Risk review).
- `signals`: none (none fired).

---

## 7. From API call to database rows

1. `POST /runs` with `{ticker, async_: true, force_agents}`.
2. The route returns **202** immediately with a task id. The work is queued in Redis.
3. A **Celery worker** runs `analyze_ticker_task`. It opens an `AnalysisRun` row, calls `analyze_ticker()`, then closes the run with `context.outcome` (`ok`, `no_signal`, `skipped`) so the UI can explain *why* there is no report.
4. `analyze_ticker()` runs the two gates, then `run_analysis()` (the graph).
5. `_persist()` writes `Signal`, `AgentDecision` and `Report` rows for that `run_id`. The HTML file is written to `data/reports/`.
6. The frontend polls `/tasks/{id}` for completion, then reads `/runs/{id}`, `/reports?run_id=`, `/runs/{id}/decisions`.

**Convention worth mentioning:** the pure analysis function (`analyze_ticker`) takes an already-open `run_id` and never opens or closes the run itself. The caller (Celery task or API route) owns the run lifecycle. This is why the document path (`analyze_document`) follows the same shape.

**Audit trail:** `agent_decisions` stores each node's input, output, rationale and latency. The UI's "Agent decisions" table and the Activity feed read from it. That answers "why did it say AVOID?" after the fact.

---

## 8. The single-step document agent

For an uploaded PDF or Excel with no ticker, there is no graph. `analyze_document()`:

1. Fetches every chunk of that upload back from Qdrant, in order (`scroll` by `source_id`, not similarity search).
2. Runs local Python analysis (per-sheet metric trends, key figure lines, or, for a Screener workbook, the full prediction report with scenarios and charts).
3. Optionally adds an LLM summary if a key is configured.
4. Writes one `document_analyst` decision row and a report.

It reuses the same run and report tables, so the UI treats it like any other run (shown as "📄 Document").

---

## 9. Design decisions and trade-offs (the "why")

| Decision | Why | Cost |
|---|---|---|
| **Deterministic scores and verdicts; LLM only for prose** | Reproducible, testable offline, cheap, explainable. An interviewer can ask "why AVOID" and you can show the arithmetic | Less flexible than letting a model reason; thresholds are fixed |
| **Two gates before the agents** | Most tickers on most days have nothing to analyze; do not pay for six nodes and LLM calls to say so | A run can legitimately end with no report (surfaced as `no_signal`/`skipped`, not an error) |
| **Shared state with append-only reducers** | Agents stay decoupled: any can be added or removed without the others knowing | Implicit contract through dict keys (TypedDict helps, but is not enforced at runtime) |
| **Supervisor as a heuristic router** | Predictable, free, and strategy-configurable | Not adaptive. It does not look at the data to decide which analysts are worth running |
| **Sequential execution** | Simple, deterministic ordering, easy tracing | Slower than parallel fan-out; analysts are independent so parallel is a straightforward upgrade |
| **Graceful degradation per agent** | A missing input (no fundamentals, Qdrant down) should reduce coverage, not fail the run | The critic must handle `no_data` and re-normalise weights |
| **Offline `EchoLLM` fallback** | The whole graph runs with no key or network: CI, demos, laptops | Narrative text is a placeholder until a provider is configured |
| **Manual trigger, not auto-analyze on upload** | LLM cost and noise; user intent | One extra click |
| **Audit rows for every node** | Explainability and debugging | Storage; `tokens` column exists but is not filled |

---

## 10. Honest limitations (say these before they are asked)

1. **The RAG agent's `score` is a retrieval similarity (0 to 1), and the critic treats it as a directional score.** A document that is highly relevant but bearish would push conviction *up*. Similarity is not sentiment. A better design is to have the RAG agent output a stance from its summary, or exclude it from the weighted average. In the INFY run the hashed-embedding similarities were near 0, so the effect was negligible, but it is a real modelling flaw.
2. **The local embedder is a word-count hash**, so retrieval matches shared words, not meaning. It is for offline wiring; use OpenAI embeddings for real semantic search.
3. **The supervisor does not use the data or the LLM.** "Supervisor" is a configurable router more than a reasoning agent.
4. **The `errors` state field is declared but nothing appends to it**, and the `tokens` audit column is not populated.
5. **Fixed thresholds** (P/E 15 and 40, RSI 30/70, weights 0.45/0.35/0.20) are reasonable defaults, not tuned or backtested per sector. Banks and lenders look "Weak" on operating cash flow by nature.
6. **Sequential and single-shot:** no tool use, no retries, no loops, no memory across runs. Each run starts from scratch.
7. **Forecasts are trend extrapolations.** They know nothing about the economy or company events.

---

## 11. How I would extend it

**Add a new analyst** (for example, news sentiment):
1. Create `app/agents/news_analyst.py` with a node `def news_analyst_node(state) -> dict` that returns `{"findings": [finding], "next_agent": advance_plan(state, "news_analyst"), "decisions": [decision]}`.
2. Register it in `graph.py`: `add_node`, add it to `_ANALYSTS`, and it gets the same conditional edges.
3. Add it to the supervisor's default plan and to `_WEIGHTS` in the critic.
4. Add a section in the report writer.

No other node changes. That is the payoff of the shared-state design.

**Parallel analysts:** replace the chain with a fan-out from the supervisor to the three analysts and a join before the critic. The reducers already merge `findings` correctly, which is why this is a small change.

**Fix the RAG scoring:** have the RAG node emit a `stance` from its summary and give the critic a rule to ignore findings without one.

---

## 12. Testing

- `tests/test_agents_graph.py` runs the **whole graph offline** (real indicators, `EchoLLM`), which is only possible because the decisions are deterministic.
- Statistics, ratios, scenario maths and the prediction report each have their own unit tests.
- The API layers are tested with fake repositories, so they need no database.

---

## 13. Likely interview questions

**Q: Why LangGraph and not just a Python function that calls each step?**
A: The steps would work as a plain function. LangGraph gave a typed shared state with reducers, conditional edges that follow a plan chosen at run time, and a compiled graph that is easy to extend (add a node and its edges). If it stayed at three fixed steps I would use a function; the routing and state-merging are what earn the dependency.

**Q: How do the agents collaborate if they never call each other?**
A: Through the shared state. Analysts append findings (reducer concatenates), the critic reads all findings together and produces one verdict, the writer reads that. Coordination is by data, not by messages.

**Q: What stops one agent overwriting another's result?**
A: The `Annotated[list, operator.add]` reducer on `findings` and `decisions`. Each node returns a one-element list and LangGraph appends it.

**Q: Where is the LLM actually used, and what if it is down?**
A: Only to write text: the technical and fundamental narratives, the RAG summary, the critique and the thesis. Scores, flags and verdicts are code. With no key the factory returns an offline stub, so the run still completes; only the prose is placeholder.

**Q: How do you keep costs down?**
A: Two gates before any LLM call (enough price data, and a rule fired or the user forced it), the analysis is user-triggered rather than automatic, and there are at most five short LLM calls per run.

**Q: What happens if an agent has no data?**
A: It returns a `no_data` finding (fundamental) or a "no documents matched" finding (RAG) with score 0. The critic excludes `no_data` findings and re-normalises the weights.

**Q: How do you make the results explainable?**
A: Every node writes an `agent_decisions` row with input, output, rationale and latency, and the report shows the risk flags and per-analyst bullets. For any verdict I can show the score arithmetic (section 6).

**Q: How would you scale it?**
A: The API is stateless; analysis runs in Celery workers, so add workers. Within a run, fan the independent analysts out in parallel. The bottlenecks are the LLM and Qdrant calls, not the maths.

**Q: How do you test something with an LLM in it?**
A: By keeping the decisions deterministic and swapping the LLM for a stub. The graph test runs end to end offline.

**Q: What is the weakest part?**
A: The RAG similarity being used as a directional score (section 10, item 1), and the fixed thresholds. I would fix the first by emitting a stance from the RAG summary, and the second by backtesting thresholds per sector.

**Q: Why is the supervisor not an LLM?**
A: The decision it makes (which analysts to run) is a configuration choice today, so an LLM would add cost and non-determinism for no benefit. It becomes worth it if the choice depends on the data, for example skipping fundamentals for an ETF.

**Q: How does a run's result get to the UI without blocking?**
A: The API returns 202 and a task id; the worker records the run with an `outcome`; the UI polls the task and then loads the run, its reports and decisions. The `outcome` (`ok`, `no_signal`, `skipped`) lets the UI explain an empty result.

---

## 14. Numbers and names to remember

- **6 nodes:** supervisor, technical, fundamental, RAG research, risk critic, report writer.
- **2 gates:** at least 30 daily bars; a rule fired or `force_agents`.
- **Weights:** technical 0.45, fundamental 0.35, RAG 0.20.
- **Verdict cut-offs:** go above 0.35 with no flags; caution above 0.15; otherwise no-go.
- **Actions:** go → BUY, caution → HOLD, no-go → AVOID.
- **State reducers:** `findings`, `decisions`, `errors` (`operator.add`).
- **Tables written:** `analysis_runs`, `signals`, `agent_decisions`, `reports`.
- **LLM calls per run:** at most five, all for text.

See also: [ANALYSIS_METHODS.md](ANALYSIS_METHODS.md) for the maths, [UPLOAD_AND_AGENTS.md](UPLOAD_AND_AGENTS.md) for the upload flow, [TECHNICAL.md](TECHNICAL.md) for the subsystem map.
