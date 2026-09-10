# DATA_FORMATS.md

What each input source must look like. Covers the built-in `MarketDataProvider`
files and every input connector. Connector reference: [TECHNICAL.md](TECHNICAL.md) §11a.

Two destinations:

- **rows** → PostgreSQL/TimescaleDB (`ohlcv` or `fundamentals`)
- **docs** → Qdrant document library (chunked + embedded)

---

## OHLCV (price) rows

Canonical columns, after normalisation: `ticker, ts, open, high, low, close,
volume`. `normalize_ohlcv()` lower-cases headers and accepts these **aliases**,
so most exports work unchanged:

| Canonical | Accepted headers |
| --- | --- |
| `ts` | `date`, `datetime`, `timestamp`, `time` |
| `open` | `open`, `o` |
| `high` | `high`, `h` |
| `low` | `low`, `l` |
| `close` | `close`, `c`, `close_price`, `last`, `ltp` |
| `volume` | `volume`, `v`, `vol`, `traded_qty`, `total_traded_quantity` |
| `ticker` | `ticker`, `symbol`, `scrip` (or supplied out-of-band) |

Rules:

- **Date**: anything pandas can parse (`2024-01-31`, `31-01-2024`,
  `2024-01-31 15:30:00`, epoch). Parsed as UTC. Unparseable rows are dropped.
- Rows missing `open/high/low/close` are dropped; missing `volume` → `0`.
- Duplicates on `(ticker, ts)` are collapsed (last wins on upsert).
- If the file has no ticker column you must supply it (filename stem for the
  `csv` connector, `ticker` in the connector config, or the sheet name for
  Excel).

Minimal CSV (`data/market/RELIANCE.csv`):

```csv
date,open,high,low,close,volume
2024-01-01,2740.00,2765.30,2732.10,2758.85,4120000
2024-01-02,2758.85,2779.00,2751.20,2770.40,3890000
```

## Fundamental rows

Recognised numeric columns go to their own DB fields; **anything else is kept in
`metrics` (JSONB)** — you don't have to trim your export.

Required: `ticker`, `period` (free text — `FY2024`, `Q1FY25`, …).
Recognised: `revenue`, `net_income`, `eps`, `pe`, `debt_to_equity`.
Optional: `reported_at` (a date).

```csv
ticker,period,revenue,net_income,eps,pe,debt_to_equity,roce
RELIANCE,FY2024,1000000,75000,110.5,24.3,0.42,0.13
TCS,FY2024,240000,46000,125.0,29.1,0.05,0.55
```

`(ticker, period)` is unique — re-uploading a period overwrites it.

---

## Connector-by-connector

### `csv`
```jsonc
{"path": "data/market/RELIANCE.csv", "row_kind": "ohlcv", "ticker": "RELIANCE"}
{"dir": "data/market", "glob": "*.csv", "row_kind": "ohlcv"}   // ticker = filename stem
{"path": "fundamentals.csv", "row_kind": "fundamental"}
{"path": "data.tsv", "sep": "\t"}
```
File = the OHLCV or fundamental shape above.

### `excel`
```jsonc
// rows: one sheet per ticker (sheet name = TICKER) or a ticker/symbol column
{"path": "book.xlsx", "mode": "rows", "row_kind": "ohlcv"}
{"path": "book.xlsx", "mode": "rows", "row_kind": "ohlcv", "sheet": "RELIANCE", "ticker": "RELIANCE"}
{"path": "fundamentals.xlsx", "mode": "rows", "row_kind": "fundamental"}

// docs: each sheet becomes a Markdown table in the library
{"path": "notes.xlsx", "mode": "docs", "doc_type": "research_note"}
```
Needs `openpyxl` (installed with the package). Same column rules as CSV.

### `pdf`  → docs
```jsonc
{"paths": ["data/documents/AR2024.pdf"]}
{"dir": "data/documents", "glob": "**/*.pdf", "doc_type": "annual_report"}
```
Text-based PDFs only — scanned/image PDFs extract little; run them through
`image_ocr` or an OCR step first. `doc_type` is auto-detected from filename +
first page (annual_report / quarterly_report / announcement / news /
research_note / other) unless you override it.

### `image_ocr`  → docs
```jsonc
{"paths": ["data/documents/scan1.png"], "backend": "stub"}         // default: no text
{"dir": "data/documents/images", "backend": "tesseract", "lang": "eng"}
{"paths": ["chart.png"], "backend": "api", "url": "https://ocr.example/v1", "api_key_env": "OCR_KEY"}
```
Accepts `.png .jpg .jpeg .tif .tiff .bmp .webp`. `stub` (default) emits **empty
text** + a warning so the pipeline still runs; `tesseract` needs
`pip install ".[ocr]"` and the Tesseract binary on `PATH`; `api` POSTs the image
file to `<url>/ocr`.

### `web_crawler`  → docs
```jsonc
{
  "start_urls": ["https://console.grdworld.com/Schedular/Index"],
  "allowed_domains": ["console.grdworld.com"],   // default: domains of start_urls
  "max_depth": 1,            // 0 = only the start pages
  "max_pages": 50,
  "same_domain_only": true,
  "respect_robots": true,
  "delay_seconds": 1.0,
  "include_patterns": ["/Schedular/"],   // regex; a link must match ONE to be queued
  "exclude_patterns": ["\\.pdf$", "/logout"],
  "auth": { ... see below ... }
}
```
Static HTML only (no JavaScript rendering). Extracts visible text + `<title>` +
links (BeautifulSoup, regex fallback). One document per page, `doc_type` `web`.

### `http_api`  → rows or docs
```jsonc
// rows
{"url": "https://vendor/api/ohlcv?symbol=RELIANCE", "mode": "rows", "row_kind": "ohlcv",
 "json_path": "data.candles", "ticker": "RELIANCE",
 "auth": {"type": "bearer", "token_env": "VENDOR_TOKEN"}}

// docs, with pagination
{"url": "https://news/api/latest", "mode": "docs", "json_path": "articles",
 "text_fields": ["title", "body"], "id_field": "id",
 "meta_fields": ["url", "published_at"], "doc_type": "news",
 "next_path": "paging.next", "max_pages": 10}
```
`json_path` is a dotted path to the list in the response. For `rows`, list items
must carry the OHLCV/fundamental aliases above. For `docs`, `text_fields` are
concatenated into the document body; `meta_fields` are copied to metadata.

---

## From the frontend: upload & crawl-now

Two endpoints turn a browser action into an input run without pre-defining a
source. They still execute on the **Celery worker** (async) — Beat/worker must be
running, or use the saved-source `?async_=false` path.

**All `/inputs/*` routes require a bearer token.** Get one from
`POST /auth/login` (form fields `username` = email, `password`) and send it as
`Authorization: Bearer <access_token>`. The frontend does this automatically once
you sign in; seed a login with `python scripts/seed_data.py` (demo user) or
`python scripts/create_user.py EMAIL PASSWORD`.

### `POST /inputs/upload`  (multipart/form-data)

| Field | Values | Notes |
| --- | --- | --- |
| `files` | one or more | `.csv .tsv .xlsx .xls .xlsm .pdf .png .jpg .jpeg .tif .tiff .bmp .webp`; ≤ `UPLOAD_MAX_MB` each |
| `mode` | `ingest_once` (default) \| `save_source` | `save_source` also creates an `InputSource` row |
| `excel_mode` | `docs` (default) \| `rows` | how `.xlsx` is read |
| `row_kind` | `ohlcv` (default) \| `fundamental` | for CSV/Excel rows |
| `doc_type` | free text | overrides auto-detection for doc-type files |
| `ticker` | e.g. `RELIANCE` | when a rows file has no ticker column |
| `name_prefix`, `schedule_cron` | | only used with `mode=save_source` |
| `run_now` | `true` (default) | queue the run immediately |

Extension → connector: `.csv/.tsv`→`csv`, `.xlsx/.xls/.xlsm`→`excel`,
`.pdf`→`pdf`, images→`image_ocr`. File contents must match that connector's
format (see the sections above). Files are stored under `UPLOADS_DIR` with a
sanitised, uuid-prefixed name.

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
        -d 'username=demo@grd-stk-mkt.local&password=demo12345' | jq -r .access_token)

curl -H "Authorization: Bearer $TOKEN" \
     -F "files=@AR2024.pdf" -F "files=@prices.csv" \
     -F "mode=ingest_once" -F "row_kind=ohlcv" \
     localhost:8000/api/v1/inputs/upload
```

### `POST /inputs/crawl`  (application/json)

```jsonc
{
  "urls": ["https://console.grdworld.com/Schedular/Index"],
  "max_depth": 1, "max_pages": 25, "same_domain_only": true,
  "include_patterns": ["/Schedular/"], "exclude_patterns": [],
  "auth": { ...env-var-named block, see below... },
  "save_as": "GRD console",        // omit → one-off; set → saved InputSource
  "schedule_cron": "0 * * * *"     // only with save_as
}
```

- Every URL is checked by the **SSRF guard**: `http`/`https` only, and the host
  must not resolve to loopback / private / link-local / reserved space
  (override with `CRAWLER_ALLOW_PRIVATE=true`, dev only).
- `auth` uses the same blocks as below — **it names env vars, you never put a
  password in this request body.** The vars must exist in the worker's env.
- Response: `{"mode": "async", "task_id": "...", "source_id": <if saved>}`.

---

## Auth

For `web_crawler` and `http_api`. **Credentials are read from environment
variables named in the config — never stored in the config or DB.** Put the vars
in the *worker* process environment.

```jsonc
{"type": "none"}
{"type": "bearer", "token_env": "VENDOR_TOKEN"}
{"type": "header", "headers": {"X-API-Key": {"env": "GRD_API_KEY"}}}
{"type": "cookie", "cookie_env": "GRDWORLD_COOKIE"}        // raw Cookie header value
{"type": "form_login",
 "login_url": "https://console.grdworld.com/Account/Login",
 "user_field": "Email", "password_field": "Password",
 "user_env": "GRDWORLD_USER", "password_env": "GRDWORLD_PASS",
 "extra_fields": {"RememberMe": "true"}}
```

`form_login` POSTs the form once, then reuses the session cookies for the crawl.

---

## Folder conventions

| Path | Used by |
| --- | --- |
| `data/market/<TICKER>.csv` | built-in `csv` MarketDataProvider, `csv` connector default `dir` |
| `data/market/*.xlsx` | `excel` connector |
| `data/documents/**` | `pdf` connector, `ingest_pending_documents` task |
| `data/documents/.ingested.txt` | ledger of already-ingested files (delete a line to re-ingest) |
| `data/uploads/` | files from `POST /inputs/upload` (git-ignored) |
| `data/reports/` | rendered reports (git-ignored) |
