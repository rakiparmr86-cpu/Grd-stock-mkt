# WORKFLOW.md

The **living** guide: how to start, what to do, in what order — and how to keep
this file current as the system grows. New here? Start with
[OVERVIEW.md](OVERVIEW.md). For *what already exists*, read
[TECHNICAL.md](TECHNICAL.md).

> Rule: **after every meaningful change, update the relevant recipe below and add
> a line to §9 Change log.** A PR that changes behaviour without touching this
> file is incomplete.

---

## 1. First-time setup (do this once)

Run from the project root: `D:\newdata\Grd-stk-mkt\Grd-stock-mkt`

```bash
# 1. env file
copy .env.example .env
#    edit .env: set SECRET_KEY; leave OPENAI_API_KEY blank to run fully offline

# 2. infra containers (Postgres+Timescale, Redis, Qdrant, MailHog)
docker compose up -d postgres redis qdrant mailhog

# 3. python deps into a venv
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# 4. database schema
alembic upgrade head

# 5. demo data + a demo login (demo@grd-stk-mkt.local / demo12345)
python scripts/seed_data.py
#    or make your own: python scripts/create_user.py you@example.com 'a-password' --superuser

# 6. sanity check
pytest -q            # expect: 48 passed, 1 skipped (49 with langgraph installed)
```

Frontend (optional, separate shell):

```bash
cd frontend/my-react-app
npm install
npm run dev          # http://localhost:5173  → sign in with the demo login
```

> `command.txt` in the repo still lists the old path `D:\newdata\Grd-stk-mkt`.
> Use the paths in this file instead.

---

## 2. Daily dev loop

```bash
.venv\Scripts\activate
docker compose up -d postgres redis qdrant mailhog     # if not already running

# terminal A — API (hot reload)
uvicorn app.main:app --reload                          # http://localhost:8000/docs

# terminal B — Celery worker
celery -A app.workers.celery_app worker -l info --pool=solo   # --pool=solo on Windows

# terminal C — Celery Beat (only if testing schedules)
celery -A app.workers.celery_app beat -l info

# terminal D — frontend (if working on UI)
cd frontend/my-react-app && npm run dev
```

Make targets exist for most of these: `make up`, `make migrate`, `make seed`,
`make api`, `make worker`, `make beat`, `make test`, `make lint`, `make fmt`.

Before pushing: `ruff format app tests && ruff check app tests && pytest -q`.

---

## 3. The runtime pipeline — what triggers what

```
                 ┌─ POST /api/v1/runs {ticker, async_}         (manual, on demand)
 trigger  ───────┤
                 └─ Celery Beat → analysis.scan_all_watchlists  (every 15 min, mkt hours)
                                     └► scan_watchlist(wl_id)
                                            └► for each ticker:
   orchestrator.analyze_ticker(ticker, run_id, strategy_id)
     1. load_ohlcv_frame            ── from `ohlcv` (needs ≥30 rows)
     2. compute_indicators          ── calc engine → latest + frame
     3. SignalEngine.evaluate       ── active rules for the strategy
     4. upsert_indicator_points
     5. no signal & not forced?     ── stop here (status=no_signal)
     6. run_analysis (LangGraph)    ── supervisor → analysts → risk_critic → report_writer
     7. render_report               ── HTML (+PDF) under data/reports/
     8. persist                     ── signals, agent_decisions, reports rows
   → analysis.scan_watchlist then dispatches notifications.send_report_alert
```

Data comes in separately, three ways:
- `market_data.refresh_*` tasks pull OHLCV via the configured provider,
  normalize, and upsert.
- `rag.ingest_pending_documents` pulls files from `data/documents/` into Qdrant.
- **input sources** (`inputs.run_input_source`) — any connector you've saved
  (Excel / PDF / image OCR / web crawler / HTTP API); `sink.py` routes each
  result to TimescaleDB (rows) or Qdrant (docs). See §4 "Wire an input source".

Manual one-shot without the scheduler:

```bash
curl -X POST localhost:8000/api/v1/runs -H "content-type: application/json" ^
     -d "{\"ticker\":\"RELIANCE\",\"strategy_id\":1,\"async_\":false,\"force_agents\":true}"
```

---

## 4. Recipes — how to add each kind of thing

Each recipe lists the files to touch **in order**, then the "done when" checks.

### Add a technical indicator
1. `app/services/calculations/indicators.py` — add the pure function (returns a
   named Series or a DataFrame of named columns).
2. `app/services/calculations/engine.py` — add an `elif item["fn"] == "..."`
   branch in `CalculationEngine.run()`; add a default entry to `DEFAULT_SPEC` if
   it should always compute.
3. `app/services/calculations/__init__.py` — export it if it's part of the public
   surface.
4. `tests/test_indicators.py` — add a maths test + assert the key appears in
   `compute_indicators(ohlcv).latest`.
5. **Done when:** `pytest -q` green; the new key is usable in a rule expression
   (`{"indicator": "<name>"}`).

### Add a signal-engine operator
1. `app/services/signals/engine.py` — handle the new `op` in `_eval()` (and
   `_resolve_series()` if it needs series). Keep it explicit — no `eval`.
2. Update the grammar block in `engine.py`'s module docstring **and**
   `TECHNICAL.md` §5.
3. `tests/test_signal_engine.py` — true case, false case, error case.
4. **Done when:** `POST /api/v1/rules/test` accepts an expression using it.

### Add a market-data provider
1. `app/services/market_data/<name>_provider.py` — subclass
   `MarketDataProvider`, implement `fetch_ohlcv` (return a raw frame; let
   `normalize_ohlcv` shape it).
2. `app/services/market_data/factory.py` — register in `_REGISTRY`.
3. `.env.example` — document any new `MARKET_DATA_*` vars; add them to
   `app/core/config.py::Settings`.
4. `tests/` — a test with a fixture file or a mocked HTTP response.
5. **Done when:** `MARKET_DATA_PROVIDER=<name>` + `refresh_ticker.run("X")`
   populates `ohlcv`.

### Add an input connector (Excel / PDF / crawler / API / …)
1. `app/services/inputs/<name>.py` — subclass `InputConnector`; implement
   `fetch() -> Iterator[ConnectorResult]` and (optionally) `validate()` to reject
   a bad config early. Yield `ConnectorResult.of_docs([DocItem(...)])` for
   unstructured text, or `ConnectorResult.of_rows(df, "ohlcv"|"fundamental")` for
   structured rows (shape OHLCV frames with `normalize_ohlcv`). Never touch the
   DB / Qdrant — `sink.py` does that.
2. `app/services/inputs/registry.py` — add to `_REGISTRY` and `_HINTS`.
3. `app/schemas/inputs.py` — add the name to the `Connector` `Literal`.
4. HTTP sources: reuse `app/services/inputs/auth.py` (`build_auth(cfg["auth"])`);
   read secrets from **env vars named in the config**, never from the config.
5. New settings → `app/core/config.py` + `.env.example`.
6. `tests/test_inputs.py` — registry membership, `validate()` rejects a bad
   config, and a `fetch()` test (mock the client / use a `tmp_path` file).
7. Update `TECHNICAL.md` §11a table + §2 stack row.
8. **Done when:** `POST /api/v1/inputs/test` with `{"connector":"<name>","config":{…}}`
   returns stats, and a saved source runs via `POST /inputs/{id}/run`.

### Wire an input source (no code — via the API)
1. `GET /api/v1/inputs/connectors` — see the connector types + config keys.
2. `POST /api/v1/inputs` — `{name, connector, config, schedule_cron?}`. The
   config is validated against the connector on create.
3. `POST /api/v1/inputs/{id}/run` (async by default) — or wait for the hourly
   `sweep-input-sources` Beat job / a per-source `schedule_cron`.
4. Check `last_status` / `last_stats` on `GET /api/v1/inputs/{id}`; docs land in
   Qdrant, rows in `ohlcv` / `fundamentals`.
   *Crawler behind a login:* set `config.auth` to a `form_login` / `bearer` /
   `cookie` block that names env vars, and put those vars in the worker's env.

### Add an agent to the LangGraph
1. `app/agents/<agent>.py` — a node `def <agent>_node(state) -> dict:` returning
   partial state; append a decision dict via `app/agents/_common.py::make_decision`.
2. `app/agents/graph.py` — `g.add_node(...)`; wire edges. If it's an analyst,
   add its name to `_ANALYSTS` and to the supervisor's routing `branch`, and
   call `advance_plan(state, "<agent>")` for `next_agent`.
3. `app/agents/supervisor.py` — include it in `_ALL_ANALYSTS` / the plan
   heuristic so it actually gets scheduled.
4. `app/agents/state.py` — add any new state keys (use `Annotated[list, add]`
   for accumulators).
5. `tests/test_agents_graph.py` — assert it runs when planned and is skipped
   when not.
6. Update `TECHNICAL.md` §9 diagram + descriptions.
7. **Done when:** `GET /api/v1/runs/{id}/decisions` shows the new agent's row.

### Add an API endpoint
1. `app/schemas/` — request/response Pydantic models (`from_attributes=True` via
   `ORMModel` for DB reads).
2. `app/api/v1/<area>.py` — the route; use `DbSession` and (to protect it)
   `user: CurrentUser`.
3. `app/api/v1/router.py` — `include_router` if it's a new area.
4. `tests/` — add a `TestClient` test (see `tests/test_auth_api.py` for the
   SQLite + `get_db`-override fixture; JSONB-heavy tables need Postgres instead).
5. To require a login, add `dependencies=[Depends(get_current_user)]` to the
   `include_router(...)` call in `app/api/v1/router.py` (see `_auth` there).
6. Update `TECHNICAL.md` §8 table.

### Add / change a DB model
1. Edit the model under `app/models/`; if it's a new module, import it in
   `app/models/__init__.py` so Alembic sees it.
2. `alembic revision --autogenerate -m "what changed"` → review the file in
   `migrations/versions/` (autogen misses enum/type/index renames — fix by hand).
3. `alembic upgrade head`; test `alembic downgrade -1` then `upgrade head` again.
4. Update `scripts/seed_data.py` if the demo data needs the new field.
5. Update `TECHNICAL.md` §6 table.
6. **Done when:** fresh DB via `alembic upgrade head` matches a DB built from
   models; `pytest -q` green.

### Add a notification channel (WhatsApp / Telegram)
1. `app/services/notifications/<channel>.py` — subclass `NotificationChannel`;
   `send()` returns `{"status": "sent"|"failed", ...}` and **never raises**.
2. `app/services/notifications/service.py` — add to the `_CHANNELS` registry.
3. `app/core/config.py` + `.env.example` — credentials/config vars.
4. `app/models/history.py::Alert.channel` already free-form — no migration needed.
5. **Done when:** `notify(recipient, subj, body, channel="<channel>")` delivers
   and writes an `alerts` row.

### Ingest documents for RAG
1. Drop `.pdf` / `.txt` / `.md` / `.html` into `data/documents/`.
2. `celery -A app.workers.celery_app call app.workers.tasks.rag.ingest_pending_documents`
   (or wait for the 4-hourly Beat job).
3. Verify: Qdrant UI at `http://localhost:6333/dashboard`, collection
   `grd_documents`.
4. If you switch `EMBEDDINGS_PROVIDER`, the vector **dim changes** — drop and
   recreate the collection (`QdrantStore.ensure_collection` only creates when
   absent).

### Frontend
- Files: `src/api.js` (base URL + token in `localStorage` + `api()` wrapper +
  `login/register/me/logout`), `src/AuthForm.jsx` (sign-in / create-account),
  `src/App.jsx` (auth gate → Inputs console: upload, crawl, sources table).
- Flow: no token → `<AuthForm>`; `register` (JSON) → auto `login` (form-encoded,
  `username` = email) → token stored → `me()` confirms → console. A 401 from any
  call throws `AuthError`, clears the token, and returns to sign-in.
- API base: `VITE_API_BASE` (default `http://localhost:8000/api/v1`); CORS in
  `app/core/config.py::cors_origins` allows `:5173`.
- `npm install && npm run dev` → `http://localhost:5173`; `npm run build` → `dist/`.
- **Adding a screen:** import `api` from `./api` (token is attached for you),
  add a component, mount it in `App`'s `Console`. New protected endpoints just
  work; handle `AuthError` by calling the passed `onExpire`/`onSignOut`.
- Next screens: watchlist list, trigger-run button, run detail with the
  agent-decisions timeline, report iframe (`GET /reports/{id}/html`). Live
  signals: `/ws/signals` (still an echo stub).

---

## 5. Bigger pieces still to build (pick up in roughly this order)

1. **Enforce auth** on the remaining resource routers (`watchlists`,
   `strategies`, `rules`, `runs`, `signals`, `reports`) — `/inputs/*` and a
   `users` seed are done; copy the router-level `dependencies=_auth` pattern in
   `app/api/v1/router.py`.
2. **Real WebSocket** — publish from `analysis` tasks to a Redis channel;
   `/ws/signals` subscribes and streams.
3. **Positions / PnL model** so `sell` signals mean something; enforce
   `rule.cooldown_minutes`.
4. **Real market-data feed** (licensed vendor via `api_provider`) replacing the
   NSE snapshot.
5. **Frontend app** — sign-in + Inputs console exist; next: watchlist/strategy
   editors, run history + agent-decision timeline, report viewer (§Frontend recipe).
6. **LLM hardening** — retries, timeouts, token/cost logging into
   `agent_decisions.tokens`.
7. **Observability** — structured logs, Prometheus metrics, task dashboards.
8. **CI** — GitHub Actions: ruff + pytest + `alembic upgrade head` on a throwaway
   Postgres.

---

## 6. Release / deploy checklist

- [ ] `ruff check` + `pytest -q` green
- [ ] `alembic upgrade head` runs clean on a **fresh** DB
- [ ] `.env` for the target env (real `SECRET_KEY`, DB, Redis, Qdrant, SMTP, keys)
- [ ] `docker compose build` (or CI image build) succeeds
- [ ] `docker compose up -d` → `GET /api/v1/health/ready` returns all `ok`
- [ ] worker + beat containers healthy; one manual `POST /runs` produces a report
- [ ] `TECHNICAL.md` + this file reflect what shipped
- [ ] §9 Change log updated, version bumped in `pyproject.toml` + `app/__init__.py`

---

## 7. "After new development" — the update checklist

Run through this **every time** you finish a feature or fix:

| Did you… | Then update… |
| --- | --- |
| change/add behaviour | the matching **recipe in §4** of this file |
| add/rename a config var | `app/core/config.py`, `.env.example` **and** `CONFIGURATION.md` |
| change the DB schema | new Alembic revision + `TECHNICAL.md` §6 + `seed_data.py` if needed |
| add an API route | `TECHNICAL.md` §8 table |
| change the agent graph | `TECHNICAL.md` §9 diagram + text |
| add / change a signal operator or indicator | `RULES.md` (recap + an example) |
| add / change an input connector | `DATA_FORMATS.md` + `TECHNICAL.md` §11a |
| add a new external integration | `TECHNICAL.md` §2 stack table + §17 stubs list |
| finish something that was a stub | move it from §17 (TECHNICAL) / §5 (here) and note it in §9 |
| add a dependency | `pyproject.toml` (`dependencies` or `[dev]` / `[pdf]` / `[ocr]`) |
| anything user-visible | `README.md` if the one-screen picture changed |
| always | add a dated line to **§9 Change log**; run `ruff` + `pytest` |

---

## 8. Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| `pytest` skips `test_agents_graph` | `langgraph` not installed — `pip install -e ".[dev]"` pulls it; the skip is expected otherwise |
| `analyze_ticker` returns `status="insufficient_data"` | fewer than 30 `ohlcv` rows — run `python scripts/seed_data.py` or a `refresh_ticker` |
| agent output is generic boilerplate | no LLM configured — set `LLM_PROVIDER=openai` + `OPENAI_API_KEY` (offline `EchoLLM` is intentional) |
| RAG agent always says "no documents" | Qdrant down, empty, or dim mismatch — check `:6333/dashboard`, re-run ingest, recreate collection if you changed the embedder |
| Celery worker hangs / errors on Windows | add `--pool=solo` (or `-P threads`) to the worker command |
| `alembic upgrade` fails on `CREATE EXTENSION timescaledb` | non-superuser DB role — migration catches this and continues without hypertables; grant the extension or use the `timescale/timescaledb` image |
| emails "sent" but not received | check MailHog UI at `http://localhost:8025` (dev never sends real mail) |
| `health/ready` shows `qdrant: error` | container not up, or `QDRANT_URL` wrong (in Docker it's `http://qdrant:6333`) |
| frontend shows the sign-in screen and login fails | API not running / wrong `VITE_API_BASE`, or no user yet — `python scripts/seed_data.py` (demo login) or `scripts/create_user.py` |
| `/inputs/*` returns 401 from curl | send `-H "Authorization: Bearer <token>"`; get the token from `POST /auth/login` (form fields `username`, `password`) |
| `pip install` pulls `bcrypt` 5.x and hashing errors | fixed — `security.py` calls `bcrypt` directly (passlib was dropped); ensure `bcrypt>=4.0` is installed |

---

## 9. Change log (newest first)

Add a line per change. Format: `YYYY-MM-DD — <area>: <what changed> (<who/PR>)`.

- 2026-09-10 — auth: `/inputs/*` now requires a bearer token (router-level
  `Depends(get_current_user)`). Password hashing switched from passlib to
  `bcrypt` directly (`security.py`) — passlib 1.7.4 breaks on bcrypt ≥ 5;
  `pyproject` dep `passlib[bcrypt]` → `bcrypt>=4.0`. `scripts/create_user.py`
  added; `seed_data.py` seeds `demo@grd-stk-mkt.local` / `demo12345`. Frontend:
  `src/api.js` (token + `api()` wrapper) + `src/AuthForm.jsx` (login / register)
  + `App.jsx` auth gate. Tests: +8 (`test_security.py`, `test_auth_api.py`);
  `pytest -q` → 48 pass, 1 skip. Docs: TECHNICAL §2/§8/§14/§16/§17, WORKFLOW,
  CONFIGURATION, OVERVIEW.
- 2026-09-10 — inputs (frontend): `POST /inputs/upload` (multipart CSV/Excel/
  PDF/image → ad-hoc ingest or saved source) and `POST /inputs/crawl` (URL →
  web_crawler, SSRF-guarded, `save_as` optional). New `run_adhoc_connector`
  task, `inputs/upload.py` + `inputs/ssrf.py`, settings `UPLOADS_DIR` /
  `UPLOAD_MAX_MB` / `CRAWLER_ALLOW_PRIVATE`, CORS `:5173`. `frontend/App.jsx`
  rebuilt as an Inputs console (upload / crawl / sources table). Tests: +12
  (`pytest -q` → 40 pass, 1 skip). Docs: OVERVIEW (plain-language "two ways in"
  + Inputs page), TECHNICAL §8/§11a/§14, CONFIGURATION, DATA_FORMATS.
- 2026-09-10 — docs: added `CONFIGURATION.md` (env-var reference), `RULES.md`
  (signal-rule cookbook), `DATA_FORMATS.md` (connector input formats + auth).
- 2026-09-10 — inputs: pluggable input layer (`app/services/inputs/`) — one
  `InputConnector` contract routing to **both** pipelines via `sink.py` (rows →
  TimescaleDB, docs → Qdrant). Connectors: csv, excel (rows|docs), pdf,
  image_ocr (stub/tesseract/api), web_crawler (bs4 + robots + `auth.py`
  strategies: bearer/cookie/header/form_login, secrets from env vars),
  http_api (rows|docs, pagination). New `input_sources` table + migration
  `0002`, `GET/POST /api/v1/inputs*` + `/inputs/test`, Celery
  `tasks/inputs.py`, Beat `sweep-input-sources` + per-source cron.
  `rag.ingest_text()` added; `qdrant-client`/`pypdf` imports made lazy/guarded.
  Deps: beautifulsoup4, lxml, tabulate; `[ocr]` extra. Tests: +12 (`test_inputs.py`).
- 2026-09-10 — docs: moved all docs under `docs/`; added plain-language
  `docs/OVERVIEW.md` and a `docs/README.md` index.
- 2026-09-10 — docs: added `TECHNICAL.md` + `WORKFLOW.md`.
- 2026-09-10 — frontend: Vite + React 19 skeleton scaffolded under
  `frontend/my-react-app/` (not wired to the API).
- 2026-09-09 — init: backend scaffold — FastAPI API, SQLAlchemy models +
  Alembic 0001, market-data providers + normalization, calculation engine,
  JSON-AST signal engine, RAG pipeline (parser/chunker/embeddings/Qdrant),
  LangGraph 6-agent layer with offline LLM fallback, report renderer,
  email notifications, Celery + Beat tasks, seed script, tests (16 pass).
