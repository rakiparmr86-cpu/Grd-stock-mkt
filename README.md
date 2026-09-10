# Grd-stk-mkt

Multi-agent stock-market analysis platform.

Data providers → normalization → TimescaleDB → calculation engine → rule/signal
engine → **LangGraph agent layer** → report renderer → notifications.
A parallel RAG pipeline ingests documents (annual/quarterly reports, announcements,
news, personal notes) into Qdrant and feeds the RAG Research agent.

## Documentation

All docs live in [`docs/`](docs/):

- **[docs/OVERVIEW.md](docs/OVERVIEW.md)** — plain-language tour, no tech background needed. **Start here.**
- **[docs/TECHNICAL.md](docs/TECHNICAL.md)** — what's built, how it fits together, the signal-rule grammar, known stubs.
- **[docs/WORKFLOW.md](docs/WORKFLOW.md)** — setup, dev loop, feature recipes, the post-change update checklist, change log.
- **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)** — every environment variable: default, effect, failure mode.
- **[docs/RULES.md](docs/RULES.md)** — copy-paste signal-rule expressions.
- **[docs/DATA_FORMATS.md](docs/DATA_FORMATS.md)** — file/column formats each input connector expects.

```
React frontend (later)
        │  REST / WebSocket
        ▼
   FastAPI API ──────┬───────────────┬──────────────┐
        │            ▼               ▼              ▼
        │      Config DB       Analysis history   Auth / users
        ▼
  Celery + Redis + Celery Beat  (task / scheduler layer)
        │
   ┌────┴───────────────┐
   ▼                    ▼
 Market data         Document sources
   │                    │
 Normalization       Parser → Chunker → Embeddings
   │                    │
 TimescaleDB          Qdrant (local RAG)
   │                    │
 Calculation engine    │
   │                    │
 Rule / Signal engine  │
   │  signal?           │
   ▼ yes                │
 LangGraph agent layer ◄┘
   Supervisor → {Technical, Fundamental, RAG Research} → Risk/Critic → Report Writer
   │
   ▼
 Report renderer (HTML / matplotlib / PDF) → Notification service (email; WhatsApp/Telegram later)
```

## Stack

| Concern | Choice |
| --- | --- |
| API | FastAPI + Uvicorn |
| ORM / migrations | SQLAlchemy 2.0 + Alembic |
| Relational + time series | PostgreSQL 16 + TimescaleDB extension |
| Vector store | Qdrant |
| Cache / broker / locks | Redis |
| Tasks / schedule | Celery + Celery Beat |
| Agents | LangGraph + LangChain |
| Reports | Jinja2 + Matplotlib (+ optional WeasyPrint for PDF) |

## Storage layout

- **PostgreSQL** — configuration, watchlists, strategies, rules, fundamentals,
  alert history, analysis history, agent run / audit records.
- **TimescaleDB extension** — OHLCV + indicator time series (hypertables).
- **Qdrant** — annual / quarterly reports, corporate announcements, news,
  research notes, own analysis, strategy knowledge.
- **Redis** — cache, Celery queue, locks / state.

## Quick start

```bash
cp .env.example .env                # then edit secrets (SECRET_KEY!)
docker compose up -d postgres redis qdrant
pip install -e ".[dev]"
alembic upgrade head
python scripts/seed_data.py          # demo data + login: demo@grd-stk-mkt.local / demo12345
uvicorn app.main:app --reload        # http://localhost:8000/docs

# workers (separate shells)
celery -A app.workers.celery_app worker -l info
celery -A app.workers.celery_app beat -l info

# frontend (separate shell) — sign in with the demo login
cd frontend/my-react-app && npm install && npm run dev   # http://localhost:5173
```

`/inputs/*` needs a bearer token — the frontend handles it after sign-in; for
curl, `POST /auth/login` (`username`=email) then send `Authorization: Bearer …`.
Bootstrap a user without the API: `python scripts/create_user.py EMAIL PASSWORD`.

Or run everything in containers:

```bash
docker compose up --build
```

## Layout

```
app/
  core/            settings, db session, logging, security
  models/          SQLAlchemy models  (config / market / history / user)
  schemas/         Pydantic request/response models
  api/v1/          FastAPI routers
  services/
    market_data/   provider ABC + NSE/Excel/CSV/API + normalization
    inputs/        connector ABC + csv/excel/pdf/image_ocr/web_crawler/http_api
                   + auth + registry + sink (rows→TimescaleDB, docs→Qdrant)
    calculations/  indicator library + calculation engine
    signals/       dynamic rule / signal engine
    rag/           parser, chunker, embeddings, Qdrant store, ingest
    reports/       HTML + chart renderer
    notifications/ channel ABC + email
  agents/          LangGraph state, graph, and the six agents
  workers/         Celery app, beat schedule, task modules
migrations/        Alembic
scripts/           seed / maintenance
tests/
```

Every external integration (NSE, LLM provider, SMTP, embeddings) ships as a
working stub with a `TODO` marking where credentials / real calls go.
