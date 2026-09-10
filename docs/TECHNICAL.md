# TECHNICAL.md

Reference for the parts of the system that are **already built**. Pair this with
[OVERVIEW.md](OVERVIEW.md) (plain-language tour), [WORKFLOW.md](WORKFLOW.md) (how
to run and extend it) and [../README.md](../README.md) (the one-screen overview).

> Status legend: **✅ implemented** · **🟡 stub / offline fallback** (works end to
> end but not production-grade) · **⬜ not started**

---

## 1. What this system is

A multi-agent stock-analysis pipeline:

```
market data ─► normalize ─► TimescaleDB ─► calculation engine ─► rule/signal engine
                                                                        │ signal fires
 documents ─► parse ─► chunk ─► embed ─► Qdrant ──────────┐              ▼
                                                          └──► LangGraph agents
                                        (Supervisor → Technical / Fundamental / RAG
                                         → Risk-Critic → Report Writer)
                                                          │
                                             report renderer (HTML + chart)
                                                          │
                                             notification service (email)
```

Everything is driven by **Celery + Beat** on a schedule, or on demand through the
**FastAPI** API. A React frontend skeleton exists but is not wired yet.

---

## 2. Stack

| Concern | Choice | Status |
| --- | --- | --- |
| API | FastAPI + Uvicorn, `/api/v1` prefix, WebSocket at `/ws/signals` | ✅ |
| ORM / migrations | SQLAlchemy 2.0 (typed `Mapped[...]`), Alembic | ✅ |
| Relational + time series | PostgreSQL 16 + TimescaleDB extension (hypertables on `ohlcv`, `indicator_points`) | ✅ |
| Vector store | Qdrant | ✅ wrapper, 🟡 needs `qdrant-client` installed |
| Cache / broker / locks | Redis | ✅ |
| Tasks / schedule | Celery 5 + Celery Beat (static + DB-driven schedule) | ✅ |
| Input connectors | csv/excel/pdf/http_api ✅ · web_crawler (bs4, auth hook) ✅ · image_ocr 🟡 (stub; tesseract/api opt-in) | ✅ |
| Agents | LangGraph + LangChain | ✅ graph, 🟡 LLM falls back to offline echo without a key |
| Embeddings | OpenAI **or** offline hashing embedder | ✅ / 🟡 |
| Reports | Jinja2 + Matplotlib (base64 PNG), optional WeasyPrint PDF | ✅ / 🟡 PDF behind flag |
| Notifications | SMTP email (MailHog in dev) | ✅ email · ⬜ WhatsApp/Telegram |
| Frontend | Vite + React 19 (`frontend/my-react-app`) | 🟡 skeleton only |
| Auth | JWT (PyJWT) + bcrypt (passlib), OAuth2 password flow | ✅ |
| Tests | pytest (indicators + signal engine + offline agent graph) | ✅ 16 pass, 1 skips without langgraph |

---

## 3. Repo layout

```
Grd-stock-mkt/
├── app/
│   ├── main.py                  FastAPI app, CORS, WebSocket
│   ├── core/
│   │   ├── config.py            Settings (pydantic-settings, .env)  ✅
│   │   ├── database.py          engine, SessionLocal, get_db(), session_scope()  ✅
│   │   ├── logging.py           stdout logger  ✅
│   │   └── security.py          hash/verify pw, JWT encode/decode  ✅
│   ├── models/                  SQLAlchemy models (see §6)
│   │   ├── base.py              DeclarativeBase + naming convention + TimestampMixin
│   │   ├── user.py              users
│   │   ├── config.py            watchlists, strategies, rules, thresholds, schedules
│   │   ├── inputs.py            input_sources (connector + config + cron)
│   │   ├── market.py            instruments, ohlcv, fundamentals, indicator_points
│   │   └── history.py           analysis_runs, signals, reports, alerts, agent_decisions
│   ├── schemas/                 Pydantic v2 request/response models
│   ├── api/
│   │   ├── deps.py              DbSession, get_current_user, CurrentUser
│   │   └── v1/                  routers: auth, watchlists, strategies, rules, inputs,
│   │                            runs, signals, reports, health  (see §8)
│   ├── services/
│   │   ├── market_data/         provider ABC + nse/excel/csv/api + normalization + repo
│   │   ├── inputs/              connector ABC + csv/excel/pdf/image_ocr/web_crawler/
│   │   │                        http_api + auth + registry + sink  (see §11a)
│   │   ├── calculations/        indicators.py (vectorised) + engine.py
│   │   ├── signals/             engine.py — JSON-AST rule evaluator (see §5)
│   │   ├── rag/                 parser, chunker, embeddings, vectorstore, ingest
│   │   ├── reports/             charts.py, renderer.py, templates/report.html.j2
│   │   ├── notifications/       base ABC, email channel, service registry
│   │   └── orchestrator.py      the end-to-end pipeline for one ticker (see §7)
│   └── workers/
│       ├── celery_app.py        Celery instance + config
│       ├── beat_schedule.py     static + `schedules` table + `input_sources` cron
│       └── tasks/               market_data · analysis · rag · inputs · notifications
├── migrations/                  Alembic (0001_initial creates all tables + hypertables)
├── scripts/seed_data.py         demo watchlist + strategy + rules + synthetic OHLCV + a note
├── tests/                       conftest fixture + test_indicators + test_signal_engine
│                                + test_agents_graph (offline)
├── frontend/my-react-app/       Vite React 19 skeleton  🟡
├── docker-compose.yml           timescaledb, redis, qdrant, mailhog, api, worker, beat
├── Dockerfile                   python:3.11-slim, installs the package
├── alembic.ini · pyproject.toml · Makefile
```

---

## 4. Calculation engine  ✅

**Files:** `app/services/calculations/indicators.py`, `engine.py`

- `indicators.py` — pure functions on pandas Series/DataFrame, **no TA-Lib**:
  `sma`, `ema`, `rsi` (Wilder), `macd` (line/signal/hist DataFrame), `true_range`,
  `atr`, `volume_ratio`, `returns` (simple or log), `volatility` (annualised),
  `bollinger`.
- `engine.py` — `CalculationEngine(spec).run(ohlcv)` → `CalculationResult`:
  - `.frame` — full history with every indicator column joined on
  - `.latest` — last row as `{indicator_name: float | None}` (this is what the
    signal engine and agents consume)
  - `.meta` — `{"rows": n}`
  - `DEFAULT_SPEC` covers SMA 20/50/200, EMA 20/50, RSI 14, MACD 12/26/9, ATR 14,
    volume ratio 20, returns 1 & 5, volatility 20, Bollinger 20/2. Override per
    strategy via `strategy.params["indicators"]` (list of `{"fn": ..., ...}`).
- Input frame **must** have `open, high, low, close, volume`; raises `ValueError`
  otherwise. Non-indicator columns (`ticker`, `source`, OHLV) are stripped from
  `.latest`.

**Extension point:** add a function to `indicators.py`, then a branch in
`CalculationEngine.run()` and an entry in `DEFAULT_SPEC`. See WORKFLOW §"Add an indicator".

---

## 5. Rule / signal engine  ✅

**File:** `app/services/signals/engine.py`

Rules live in the DB (`rules.expression`, JSONB) as a small **JSON AST**. No
`eval` — every operator is explicit. Evaluated against a `latest` dict and,
optionally, the full `frame` (needed for cross / offset).

### Grammar

```jsonc
// operands
{"const": 30}                                  // literal number/str/bool
{"indicator": "rsi_14"}                         // current bar value
{"indicator": "ema_20", "offset": 1}            // N bars back (needs frame)
{"price": "close"}                              // alias for {"indicator":"close"}

// comparisons: gt | lt | gte | lte | eq | ne
{"op": "lt", "left": {"indicator": "rsi_14"}, "right": {"const": 30}}

// boolean: and | or  (args: [...])   ·  not (args: [expr])
{"op": "and", "args": [ <expr>, <expr> ]}

// range
{"op": "between", "value": {"indicator": "rsi_14"},
 "low": {"const": 40}, "high": {"const": 60}}

// series cross (needs frame): cross_up | cross_down
{"op": "cross_up", "left": {"indicator": "ema_20"}, "right": {"indicator": "ema_50"}}
```

### API

- `evaluate_rule(expression, latest, frame=None) -> RuleMatch(matched, strength, detail)`
  `strength` = fraction of leaf comparisons that were true (0 if `matched` is False).
  `detail["trace"]` lists every leaf with its operands + result.
- `SignalEngine(rules).evaluate(ticker, latest, frame) -> EngineResult(ticker, signals[])`
  — sorts rules by `priority` asc, skips `is_active=False`, returns one dict per
  rule with `matched`, `signal_type` (`buy|sell|alert`), `strength`, `price`,
  `detail`, plus `error` entries for rules referencing missing indicators.
- `RuleEvaluationError` is raised for malformed AST / missing series; the engine
  catches it per-rule so one bad rule never kills a scan.

**Test it live:** `POST /api/v1/rules/test` with `{expression, indicators}`.

**Not yet done:** `cooldown_minutes` is stored on the rule but not enforced;
`sell` signals don't yet reconcile against open positions (no positions table).

---

## 6. Data model  ✅

Migration `0001_initial.py` creates everything from `Base.metadata`, enables
`timescaledb` if the role allows it, and promotes `ohlcv` + `indicator_points`
to hypertables. `0002_input_sources.py` adds `input_sources`. Later changes use
`alembic revision --autogenerate`.

| Table | Key columns | Notes |
| --- | --- | --- |
| `users` | email (uniq), hashed_password, is_active, is_superuser | JWT `sub` = `users.id` |
| `input_sources` | name (uniq), connector, kind, `config` JSONB, is_active, schedule_cron, last_run_at/status/error/stats | pluggable inputs (§11a); Beat reads `schedule_cron` |
| `watchlists` / `watchlist_items` | name; (watchlist_id, ticker) uniq, weight | `is_active` gates scheduled scans |
| `strategies` | name (uniq), `params` JSONB, is_active | `params` feeds calc spec + agent plan |
| `rules` | strategy_id, signal_type, `expression` JSONB, priority, cooldown_minutes | the AST from §5 |
| `thresholds` | (strategy_id, key) uniq, value | free-form knobs e.g. `min_conviction` |
| `schedules` | name (uniq), task (dotted path), cron, `args` JSONB, is_active | read by Beat at boot |
| `instruments` | (ticker, exchange) uniq, sector, isin, `meta` | reference / RAG ticker detection |
| `ohlcv` | (ticker, interval, ts) uniq | **hypertable**; `interval` ∈ 1m/5m/15m/1h/1d |
| `fundamentals` | (ticker, period) uniq; revenue, net_income, eps, pe, debt_to_equity, `metrics` | consumed by Fundamental agent |
| `indicator_points` | (ticker, interval, name, ts) uniq; value, `extra` | **hypertable**; persisted after each run |
| `analysis_runs` | trigger (schedule/manual/signal), status, started/finished, `context` | one row per pipeline invocation |
| `signals` | run_id, rule_id, ticker, signal_type, strength, price, `detail` | persisted matched rules |
| `reports` | run_id, ticker, title, summary, html_path, pdf_path, `payload` | `payload` = agent output minus chart b64 |
| `alerts` | signal_id/report_id, channel, recipient, status (queued/sent/failed), error | notification audit |
| `agent_decisions` | run_id, agent, step, `input`, `output`, rationale, latency_ms | **full agent audit trail** |

---

## 7. Orchestrator — the pipeline  ✅

**File:** `app/services/orchestrator.py`

`analyze_ticker(ticker, run_id=None, strategy_id=None, interval="1d", persist=True, force_agents=False)`:

1. `load_ohlcv_frame()` from DB (needs ≥ 30 rows, else `status="skipped"`).
2. `compute_indicators(frame)` → `calc.latest`, `calc.frame`.
3. Load active `rules` (+ `strategy.params`) → `SignalEngine.evaluate()`.
4. `persist` → `upsert_indicator_points()`.
5. If **no signal fired** and not `force_agents` → return `status="no_signal"`.
6. Build `price_frame_records` (tail 260 rows, NaN→None) for the chart.
7. `run_analysis(...)` — invoke the LangGraph graph (§9).
8. `render_report(payload)` → HTML (+PDF) on disk under `REPORTS_DIR`.
9. If `persist` and `run_id` → write `signals`, `agent_decisions`, `reports` rows.

Helpers: `open_run(trigger, ...) -> run_id`, `close_run(run_id, status, error)`.

---

## 8. API surface  ✅

Base prefix `/api/v1`. Interactive docs at `/docs`.

| Method & path | Purpose |
| --- | --- |
| `GET /health` · `GET /health/ready` | liveness · checks Postgres + Redis + Qdrant |
| `POST /auth/register` · `POST /auth/login` · `GET /auth/me` | JWT bearer; login is OAuth2 password form |
| `GET/POST /watchlists` · `GET /watchlists/{id}` · `POST /watchlists/{id}/items` · `DELETE /watchlists/{id}` | |
| `GET/POST /strategies` · `GET /strategies/{id}` · `PATCH /strategies/{id}/active` | creating a strategy also creates its rules + thresholds |
| `GET /rules` · `POST /rules/strategy/{id}` · `PATCH /rules/{id}` · `DELETE /rules/{id}` · `POST /rules/test` | `/test` dry-runs an AST against a supplied indicators dict |
| `GET /inputs/connectors` | available connector types + their config keys |
| `GET/POST /inputs` · `GET/PATCH/DELETE /inputs/{id}` | CRUD for saved input sources (connector + config + optional cron) |
| `POST /inputs/{id}/run` · `POST /inputs/test` | run a saved source (async by default); `/test` dry-runs a connector config with capped results, no writes |
| `POST /runs` | trigger analysis for a ticker; `async_=true` → Celery task id, `false` → runs inline and returns the result |
| `GET /runs` · `GET /runs/{id}` · `GET /runs/{id}/decisions` | run history + per-agent audit |
| `GET /signals` | filter by `ticker` / `run_id` |
| `GET /reports` · `GET /reports/{id}` · `GET /reports/{id}/html` | last serves the rendered HTML file |
| `WS /ws/signals` | accepts a socket, echoes `{"type":"ack"}` — **placeholder**; real impl should subscribe to a Redis pub/sub channel the tasks publish to |

Auth is **defined but not enforced** on the resource routers yet — add
`user: CurrentUser` (from `app/api/deps.py`) to lock endpoints down.

---

## 9. Agent layer  ✅ (🟡 offline LLM by default)

**Files:** `app/agents/` — `graph.py`, `state.py`, `llm.py`, `supervisor.py`,
`technical_analyst.py`, `fundamental_analyst.py`, `rag_research.py`,
`risk_critic.py`, `report_writer.py`, `_common.py`

```
supervisor ──► technical_analyst ──► fundamental_analyst ──► rag_research
     │               │                      │                     │
     └───────────────┴──────────────────────┴─────────────────────┘
                                 ▼
                            risk_critic ──► report_writer ──► END
```

- **State** (`state.py`, a `TypedDict`): `findings`, `decisions`, `errors` are
  reducer lists (`operator.add`); `plan` / `next_agent` drive routing.
- **Supervisor** writes an ordered `plan` (from `strategy.params["analysts"]` or a
  heuristic). Each analyst sets `next_agent` to the next planned analyst, or
  `risk_critic` when it's last — so **skipped analysts never run** (verified by
  `tests/test_agents_graph.py`).
- **Technical analyst** — deterministic score from MA position, RSI, MACD hist,
  volume ratio; LLM only phrases the narrative. Stance bull/neutral/bear.
- **Fundamental analyst** — reads latest `fundamentals` row; scores P/E, D/E,
  net margin. Clean `stance="no_data"` path when nothing on file.
- **RAG research** — embeds a query, searches Qdrant (ticker-filtered then
  unfiltered fallback), LLM synthesises bullets + citations. Degrades to
  "no documents" when Qdrant is empty/unreachable.
- **Risk / critic** — weighted conviction (`technical 0.45 / fundamental 0.35 /
  rag 0.20`), flags (high volatility, buy-into-overbought, technical vs
  fundamental disagreement) → verdict `go | caution | no-go`.
- **Report writer** — assembles `report_payload` the renderer consumes:
  `recommendation {action, confidence, thesis}`, per-analyst `sections`,
  `signals`, `indicators`, `chart_b64`. `verdict → action` = go/BUY,
  caution/HOLD, no-go/AVOID; downgrades BUY to HOLD on a conflicting sell signal.
- **LLM** (`llm.py`): `get_llm()` returns `OpenAILLM` when `LLM_PROVIDER=openai`
  **and** `OPENAI_API_KEY` is set, else `EchoLLM` — deterministic templated text
  so the whole graph runs offline and in CI.

Every node appends an `agent_decisions`-shaped dict to `state["decisions"]`
(agent, step, input, output, rationale, latency_ms) — persisted by the orchestrator.

---

## 10. Market data  ✅

**Files:** `app/services/market_data/`

- `base.py` — `MarketDataProvider` ABC: `fetch_ohlcv(ticker, start, end, interval)`,
  optional `fetch_fundamentals`, `supports()`.
- Providers: `csv_provider.py` (reads `MARKET_DATA_DIR/<TICKER>.csv`) ✅,
  `excel_provider.py` (sheet-per-ticker or a `ticker` column) ✅,
  `api_provider.py` (generic REST — adapt `_params` / `_extract` to your vendor) 🟡,
  `nse_provider.py` (NSE cookie handshake + `quote-equity` snapshot — **snapshot
  only, not true history**; prefer a licensed feed for prod) 🟡.
- `factory.py` — `get_provider(name=None)` (defaults to `MARKET_DATA_PROVIDER`).
- `normalization.py` — `normalize_ohlcv(raw, ticker=, source=)`: lower-cases and
  aliases columns (`date/timestamp → ts`, `ltp/last → close`, …), coerces types,
  UTC-tz the timestamp, dedupes on `(ticker, ts)`, indexes by `ts`.
- `repository.py` — `upsert_ohlcv(df)`, `load_ohlcv_frame(ticker, limit=750)`,
  `upsert_indicator_points(ticker, frame)` — all PG `ON CONFLICT DO UPDATE`.

---

## 11. RAG pipeline  ✅ (🟡 needs `qdrant-client`, uses offline embedder by default)

**Files:** `app/services/rag/`

- `parser.py` — `parse_document(path)` for `.pdf` (pypdf) / `.txt` / `.md` /
  `.html`; best-effort metadata: `title`, `doc_type` (annual_report /
  quarterly_report / announcement / news / research_note / other), detected
  `tickers`, `chars`.
- `chunker.py` — `chunk_text(text, max_words=350, overlap_words=60)` — paragraph
  packing with overlap; hard-splits mega-paragraphs.
- `embeddings.py` — `get_embedder()` → `OpenAIEmbedder` or `HashingEmbedder`
  (deterministic, offline, dim 384). **Dim must match the Qdrant collection.**
- `vectorstore.py` — `QdrantStore`: `ensure_collection` (cosine + keyword
  payload indexes on ticker/doc_type/source_id), `upsert`, `search(vector,
  ticker=, doc_type=)`, `delete_by_source`.
- `ingest.py` —
  `ingest_document(path, replace=True)` = parse → chunk → embed → upsert
  (`source_id` = sha1(path + mtime)); **`ingest_text(text, source_key=, metadata=)`**
  does the same from in-memory text (crawled pages, OCR output, API records),
  hashing `source_key` for idempotent replace.
- Task `ingest_pending_documents` scans `data/documents/`, tracks done files in
  `data/documents/.ingested.txt`.
- `qdrant-client` and `pypdf` are imported lazily/guarded, so the package
  imports fine without them; `QdrantStore()` raises a clear error if the client
  is missing.

---

## 11a. Input layer — pluggable connectors  ✅

**Files:** `app/services/inputs/`

One contract for every data source. A **connector** pulls from somewhere and
yields `ConnectorResult` objects; `sink.py` routes them — **structured rows →
TimescaleDB**, **documents → Qdrant** — so connectors never touch a DB.

```
connector.fetch() ─► ConnectorResult(kind="rows", rows=<df>, row_kind="ohlcv|fundamental")
                  └► ConnectorResult(kind="docs", docs=[DocItem(text, metadata, source_key)])
      │
   sink.route_result ─► upsert_ohlcv / upsert_fundamentals   (rows)
                     └► rag.ingest_text                        (docs)
```

| Connector | Emits | Reads (config keys) |
| --- | --- | --- |
| `csv` | rows | `path`\|`dir`, `glob`, `row_kind`, `ticker`, `sep` |
| `excel` | rows **or** docs | `path`, `mode`, `row_kind`, `sheet`, `ticker`, `doc_type` |
| `pdf` | docs | `paths`\|`dir`, `glob`, `doc_type` |
| `image_ocr` | docs | `paths`\|`dir`, `backend` (`stub`\|`tesseract`\|`api`), `lang`, `url`, `api_key_env` |
| `web_crawler` | docs | `start_urls`, `allowed_domains`, `max_depth`, `max_pages`, `same_domain_only`, `respect_robots`, `delay_seconds`, `include_patterns`, `exclude_patterns`, `auth` |
| `http_api` | rows **or** docs | `url`, `method`, `mode`, `json_path`, `next_path`, `max_pages`, `text_fields`, `id_field`, `meta_fields`, `ticker`, `auth` |

- `base.py` — `InputConnector` ABC (`validate()` hook, `fetch() -> Iterator`),
  `ConnectorResult`, `DocItem`, `ConnectorKind`.
- `registry.py` — `get_connector(name, config)`, `list_connectors()` (name +
  emits + config hints, surfaced at `GET /api/v1/inputs/connectors`).
- `auth.py` — HTTP auth strategies for `web_crawler` / `http_api`:
  `none` · `bearer` (`token_env`) · `header` · `cookie` (`cookie_env`) ·
  `form_login` (`login_url`, `user_env`, `password_env`, …). **Credentials are
  read from named environment variables at run time — never stored in the
  connector config or the DB.**
- `web_crawler.py` — BFS, same-domain by default, depth + page caps,
  `robots.txt`-aware, include/exclude regex on URLs, polite `delay_seconds`;
  BeautifulSoup for extraction with a regex fallback if `bs4` is absent.
- `image_ocr.py` — pluggable OCR backend. `stub` (default) emits empty text +
  a warning so the pipeline still runs; `tesseract` needs `pip install ".[ocr]"`;
  `api` POSTs the image to a configured endpoint.
- `sink.py` — `route_result()` and `run_connector(connector, source_name,
  dry_run=, max_results=)`; `dry_run` still iterates (a crawler really fetches)
  but writes nothing — used by `POST /inputs/test`.

**Saved sources & scheduling** — `input_sources` table (model
`app/models/inputs.py`): `name`, `connector`, `kind`, `config` (JSONB),
`is_active`, `schedule_cron`, plus `last_run_at` / `last_status` / `last_error`
/ `last_stats`. Tasks in `app/workers/tasks/inputs.py`:
`run_input_source(source_id)` and `run_all_active_input_sources()`. Beat sweeps
all active sources hourly (`sweep-input-sources`); any source with a
`schedule_cron` also gets its own Beat entry.

---

## 12. Reports & notifications

**Reports** ✅ — `app/services/reports/`
- `charts.py::price_with_indicators_png(frame)` → base64 PNG (price + SMA
  overlays + Bollinger fill + RSI subplot).
- `renderer.py::render_report(payload, slug=)` → writes
  `REPORTS_DIR/<ts>_<slug>.html`; PDF via WeasyPrint only if
  `REPORTS_ENABLE_PDF=true` and the lib is installed.
- Template: `templates/report.html.j2` (theme-aware, self-contained).

**Notifications** — `app/services/notifications/`
- `base.py` — `Notification` dataclass + `NotificationChannel` ABC (`send()`
  must not raise).
- `email.py` ✅ — SMTP with text + optional HTML alt + file attachments; dev uses
  MailHog (`localhost:1025`, UI `:8025`).
- `service.py` — `notify(recipient, subject, body_text, ...)` via a channel
  registry. **WhatsApp / Telegram**: add a channel class + registry entry. ⬜

---

## 13. Workers & schedule  ✅

**Files:** `app/workers/`

- `celery_app.py` — broker/backend from settings, `timezone="Asia/Kolkata"`,
  30-min hard task limit, includes the four task modules.
- `beat_schedule.py::build_beat_schedule()` — static entries
  (`refresh-watchlist-eod` 18:00 Mon–Fri, `intraday-scan` every 15 min 09–15
  Mon–Fri, `reindex-new-documents` every 4 h, `sweep-input-sources` hourly)
  **plus** every active row in the `schedules` table and every `input_sources`
  row that has a `schedule_cron`. DB failure at boot is non-fatal.
- Tasks:
  - `market_data.refresh_ticker / refresh_watchlist / refresh_all_watchlists`
  - `analysis.analyze_ticker_task / scan_watchlist / scan_all_watchlists`
    (open a run → analyze each ticker → dispatch alerts → close run)
  - `inputs.run_input_source / run_all_active_input_sources`
    (build connector → iterate `fetch()` → `sink` → update `last_*`)
  - `rag.ingest_document_task / ingest_pending_documents`
  - `notifications.send_report_alert` (writes an `alerts` row, sends, updates status)

---

## 14. Frontend  🟡

`frontend/my-react-app/` — Vite 8 + React 19 + oxlint. Default scaffold only
(`App.jsx`, `main.jsx`, assets). **Nothing calls the API yet.** No router, no
data layer, no auth wiring. See WORKFLOW §"Wire the frontend".

---

## 15. Conventions

- **Offline-first / degrade gracefully** — no external service (LLM, Qdrant, NSE,
  SMTP) may hard-fail the pipeline. Provide a stub path.
- **Audit everything the agents do** — append to `state["decisions"]`; the
  orchestrator persists it to `agent_decisions`.
- **DB access outside request handlers** uses `with session_scope() as db:`
  (commits on clean exit, rolls back on exception). Request handlers use the
  `DbSession` dependency.
- **Config only through `app.core.config.settings`** — never read `os.environ`
  directly.
- **Models are the schema source of truth** — migration 0001 builds from
  metadata; keep new changes in autogenerated revisions.
- Ruff, line length 100, `from __future__ import annotations` in every module.

---

## 16. Tests

`pytest -q` → **28 passed, 1 skipped** (the skip is `test_agents_graph.py` when
`langgraph` isn't installed).

- `tests/conftest.py` — `ohlcv` fixture: 250 deterministic synthetic sessions.
- `test_indicators.py` — indicator maths + engine contract.
- `test_signal_engine.py` — AST operators, priority ordering, error handling.
- `test_agents_graph.py` — graph runs offline; skipped analysts don't execute.
- `test_inputs.py` — connector registry + validation, auth strategy selection,
  crawler link-following / domain + page caps / `_strip_html`, CSV→OHLCV rows,
  image-OCR stub, and `sink` routing (docs→ingest, rows→upsert) incl. dry-run.

**Gaps:** no API/route tests, no orchestrator integration test, no migration
test, no frontend tests.

---

## 17. Known stubs / TODO markers

| Area | What's missing |
| --- | --- |
| `nse_provider.py` | real historical feed (currently a single snapshot) |
| `api_provider.py` | `_params` / `_extract` are guesses — adapt to a real vendor |
| `inputs/image_ocr.py` | default backend is `stub` (no text); real OCR needs `.[ocr]` (tesseract) or an OCR API |
| `inputs/http_api.py` | `json_path` / `text_fields` mapping is generic — tune per vendor |
| `inputs/web_crawler.py` | no JS rendering (static HTML only); no incremental/etag crawl |
| `llm.py` | real provider only with `OPENAI_API_KEY`; no retry/rate-limit/cost tracking |
| `main.py::/ws/signals` | echo placeholder — wire to Redis pub/sub |
| signal engine | `cooldown_minutes` not enforced; no positions/PNL model |
| notifications | WhatsApp + Telegram channels |
| API routers | auth not enforced on resource endpoints |
| frontend | everything past the Vite scaffold |
| observability | no metrics/tracing; logging is plain stdout |
