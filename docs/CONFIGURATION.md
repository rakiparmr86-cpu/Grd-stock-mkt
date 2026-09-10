# CONFIGURATION.md

Every setting, its default, what it does, and what breaks if it's wrong.

- Source of truth: `app/core/config.py` (`Settings`). Nothing reads `os.environ`
  directly — always go through `app.core.config.settings`.
- Loaded from real environment variables **and** a `.env` file in the project
  root (env vars win). Unknown keys are ignored.
- Names are case-insensitive; `SECRET_KEY` and `secret_key` are the same.
- `docker-compose.yml` overrides the host-facing ones (`POSTGRES_HOST=postgres`,
  `REDIS_URL=redis://redis:6379/0`, `QDRANT_URL=http://qdrant:6333`,
  `SMTP_HOST=mailhog`) for in-container runs.

---

## App

| Var | Default | Purpose / effect if wrong |
| --- | --- | --- |
| `APP_NAME` | `grd-stk-mkt` | Cosmetic; shows in `/health` and logs. |
| `ENV` | `dev` | `dev` \| `staging` \| `prod`. `dev` + `DEBUG` turns on SQL echo. |
| `DEBUG` | `true` | Verbose logging / SQL echo. Set `false` in prod. |
| `API_V1_PREFIX` | `/api/v1` | Path prefix for all routers. Change → every client URL changes. |
| `SECRET_KEY` | `change-me` | **Signs JWTs.** Must be a long random string (≥ 32 chars) in any shared env; changing it invalidates all existing tokens. `/inputs/*` requires a valid token — see [../scripts/create_user.py](../scripts/create_user.py). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT lifetime. No refresh token yet — on expiry the frontend returns to sign-in. |
| `ALGORITHM` | `HS256` | JWT signing algo. Leave unless you know why. |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Browser origins allowed to call the API. Add the Vite dev origin (`http://localhost:5173`) when wiring the frontend. JSON list. |

## Logging

Console always on. Two rotating files under `LOG_DIR` (API **and** Celery
workers write to both):

| Var | Default | Purpose |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Threshold for the console and `app.log`. |
| `LOG_DIR` | `./logs` | Directory for the log files. **Set empty (`LOG_DIR=`) to disable file logging** (console only) — useful for read-only containers / stdout-only setups. |
| `LOG_FILE` | `app.log` | Everything at `LOG_LEVEL` and above. |
| `ERROR_LOG_FILE` | `errors.log` | **The common exception log** — `WARNING` and above from anywhere in the backend, with full tracebacks (`logger.exception` / unhandled request errors / Celery `task_failure`). This is the file to tail when something breaks. |
| `LOG_FILE_MAX_BYTES` | `5000000` | Rotate each file at this size… |
| `LOG_FILE_BACKUPS` | `5` | …keeping this many rotations (`errors.log.1` … `errors.log.5`). |

`logs/` is git-ignored. Unhandled API exceptions are caught by a middleware in
`app/main.py` (logged with traceback, then Starlette's normal 500 response);
Celery failures are caught by a `task_failure` handler in
`app/workers/celery_app.py`.

## PostgreSQL / TimescaleDB

| Var | Default | Purpose / effect if wrong |
| --- | --- | --- |
| `POSTGRES_HOST` | `localhost` | DB host. In Docker: `postgres`. |
| `POSTGRES_PORT` | `5432` | |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | `grd` / `grd` | Change for anything real. |
| `POSTGRES_DB` | `grd_stk_mkt` | Database name. |
| `DATABASE_URL` | *(unset)* | Full SQLAlchemy URL. **If set, overrides all `POSTGRES_*`.** Must start `postgresql+psycopg://`. |

If the DB is unreachable: API `/health/ready` reports `postgres: error`; Celery
Beat logs `dynamic schedule load skipped` and runs with static schedule only;
most tasks fail loudly.

## Redis

| Var | Default | Purpose |
| --- | --- | --- |
| `REDIS_URL` | `redis://localhost:6379/0` | Cache / locks. |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | Task queue. Worker + Beat + API must agree. |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/2` | Task results / status. |

## Qdrant (vector store)

| Var | Default | Purpose / effect if wrong |
| --- | --- | --- |
| `QDRANT_URL` | `http://localhost:6333` | In Docker: `http://qdrant:6333`. |
| `QDRANT_API_KEY` | *(empty)* | Only if your Qdrant requires it. |
| `QDRANT_COLLECTION` | `grd_documents` | Collection name. Created on first ingest with the **embedder's** vector dim. |

If down/empty: the RAG Research agent degrades to "no documents"; ingestion
tasks error. **Changing the embedder changes the vector dim** — you must drop &
recreate the collection or ingests will fail.

## Embeddings / LLM

| Var | Default | Purpose / effect if wrong |
| --- | --- | --- |
| `EMBEDDINGS_PROVIDER` | `local` | `local` = offline hashing embedder (dim **384**); `openai` = real (needs key, dim per model, default 1536). |
| `EMBEDDINGS_MODEL` | `text-embedding-3-small` | Used when provider is `openai`. |
| `EMBEDDINGS_DIM` | `1536` | Must match the model. The `local` embedder ignores this and uses 384. |
| `LLM_PROVIDER` | `openai` | `openai` **and** `OPENAI_API_KEY` set → real agents; otherwise the graph runs with the offline `EchoLLM` (placeholder prose). |
| `LLM_MODEL` | `gpt-4o-mini` | Chat model for the agents. |
| `OPENAI_API_KEY` | *(empty)* | Enables real embeddings and/or LLM. Never commit it. |

## Market data (the built-in `MarketDataProvider`, separate from input connectors)

| Var | Default | Purpose |
| --- | --- | --- |
| `MARKET_DATA_PROVIDER` | `csv` | `csv` \| `excel` \| `api` \| `nse`. Which provider `refresh_ticker` uses. |
| `MARKET_DATA_API_URL` / `MARKET_DATA_API_KEY` | *(empty)* | For `MARKET_DATA_PROVIDER=api`; adapt `api_provider.py` to the vendor. |
| `MARKET_DATA_DIR` | `./data/market` | Where the `csv` provider looks for `<TICKER>.csv`. |

## Input layer (pluggable connectors)

| Var | Default | Purpose |
| --- | --- | --- |
| `DOCUMENTS_DIR` | `./data/documents` | Folder the `pdf` connector / `ingest_pending_documents` scan. |
| `UPLOADS_DIR` | `./data/uploads` | Where `POST /inputs/upload` stores browser uploads (git-ignored). |
| `UPLOAD_MAX_MB` | `25` | Per-file upload size limit; larger files are rejected 422. |
| `OCR_BACKEND` | `stub` | Default backend for the `image_ocr` connector when its config doesn't override: `stub` (no text) \| `tesseract` (needs `pip install ".[ocr]"`) \| `api`. |
| `OCR_LANG` | `eng` | Tesseract language pack. |
| `CRAWLER_USER_AGENT` | `GrdStkMktCrawler/1.0` | Default UA for the `web_crawler` connector. |
| `CRAWLER_DEFAULT_DELAY_SECONDS` | `1.0` | Politeness delay between crawler requests. |
| `CRAWLER_ALLOW_PRIVATE` | `false` | If `true`, `POST /inputs/crawl` will fetch private / loopback / link-local hosts. **Dev only** — leave `false` in any shared env (SSRF protection). |

**Connector auth secrets** are *not* settings — each source's `config.auth`
block names env vars (e.g. `GRDWORLD_USER`, `GRDWORLD_PASS`,
`VENDOR_TOKEN`), read at run time by the **worker** process. Put them in the
worker's environment, never in the DB or the connector config. See
[DATA_FORMATS.md](DATA_FORMATS.md#auth) and TECHNICAL.md §11a.

## Notifications

| Var | Default | Purpose |
| --- | --- | --- |
| `SMTP_HOST` / `SMTP_PORT` | `localhost` / `1025` | Dev = MailHog (`docker compose up mailhog`, UI at `:8025`). |
| `SMTP_USER` / `SMTP_PASSWORD` | *(empty)* | Set for a real relay. |
| `SMTP_FROM` | `alerts@grd-stk-mkt.local` | From address. |
| `SMTP_TLS` | `false` | STARTTLS for real relays. |
| `NOTIFY_DEFAULT_CHANNEL` | `email` | Only `email` exists today. |

## Reports

| Var | Default | Purpose |
| --- | --- | --- |
| `REPORTS_DIR` | `./data/reports` | Rendered HTML/PDF output. Served by `GET /reports/{id}/html`. |
| `REPORTS_ENABLE_PDF` | `false` | `true` needs `pip install ".[pdf]"` (WeasyPrint). PDF render is skipped with a warning if the lib is missing. |

---

## Minimum viable `.env`

Fully offline (no API keys, everything degrades gracefully):

```
SECRET_KEY=dev-only-not-secret
POSTGRES_HOST=localhost
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
QDRANT_URL=http://localhost:6333
LLM_PROVIDER=local
EMBEDDINGS_PROVIDER=local
```

To turn on real analysis, add `LLM_PROVIDER=openai` + `OPENAI_API_KEY=...`
(optionally `EMBEDDINGS_PROVIDER=openai` too — then recreate the Qdrant
collection because the vector dim changes from 384 → 1536).
