# Grd-stk-mkt

Multi-agent stock-market analysis platform.

Data providers → normalization → TimescaleDB → calculation engine → rule/signal
engine → **LangGraph agent layer** → report renderer → notifications.
A parallel RAG pipeline ingests documents (annual/quarterly reports, announcements,
news, personal notes) into Qdrant and feeds the RAG Research agent.

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
cp .env.example .env                # then edit secrets
docker compose up -d postgres redis qdrant
pip install -e ".[dev]"
alembic upgrade head
python scripts/seed_data.py          # demo watchlist + rules
uvicorn app.main:app --reload        # http://localhost:8000/docs

# workers (separate shells)
celery -A app.workers.celery_app worker -l info
celery -A app.workers.celery_app beat -l info
```

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
