# Command reference: setup to running

Every command needed to install, configure and run the project, in order. Written for **Windows + PowerShell**. Run them from the project root unless a step says otherwise.

```powershell
cd D:\newdata\Grd-stk-mkt\grd_st_mkt
```

Bash equivalents differ only in path style and the virtualenv activate script (`source .venv/Scripts/activate`).

## What you need installed first

| Tool | Version | Check with |
|---|---|---|
| Python | 3.11 or newer | `python --version` |
| Docker Desktop | running | `docker --version` |
| Node.js + npm | 20 or newer (web and mobile apps) | `node --version` |
| Git | any | `git --version` |

Optional: Tesseract OCR (only for reading text from images), WeasyPrint (only for PDF reports).

---

## 1. One-time setup

### 1.1 Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Dependencies are declared in `pyproject.toml` (there is no `requirements.txt`). `-e` installs the project in editable mode, so code changes apply without reinstalling.

Optional extras:

```powershell
pip install -e ".[pdf]"     # PDF report rendering (WeasyPrint)
pip install -e ".[ocr]"     # image OCR (pytesseract + pillow); also install Tesseract itself
```

If PowerShell blocks the activate script:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

You can skip activating and call the tools directly instead, for example `.\.venv\Scripts\python.exe` or `.\.venv\Scripts\celery.exe`.

### 1.2 Configuration file

```powershell
copy .env.example .env
```

Open `.env` and set at least:

| Variable | Why |
|---|---|
| `SECRET_KEY` | change to a long random string |
| `OPENAI_API_KEY` | optional. Without it, analysis still works locally and only the AI narrative text is skipped |
| `EMBEDDINGS_PROVIDER` | `local` works offline; `openai` gives better document search and needs the key |

Every variable is explained in [CONFIGURATION.md](CONFIGURATION.md).

### 1.3 Infrastructure containers

```powershell
docker compose up -d postgres redis qdrant mailhog
docker compose ps
```

| Container | Purpose | Port |
|---|---|---|
| postgres (TimescaleDB) | main database | 5432 |
| redis | Celery queue and results | 6379 |
| qdrant | vector store for documents | 6333 (dashboard: `/dashboard`) |
| mailhog | catches outgoing alert emails | 1025 SMTP, 8025 web inbox |

Wait until postgres shows `healthy` in `docker compose ps`.

### 1.4 Database schema and demo data

```powershell
alembic upgrade head
python scripts/seed_data.py
```

Create a login user (the seed script may already add a demo user):

```powershell
python scripts/create_user.py you@example.com YourPassword --name "Your Name"
python scripts/create_user.py admin@example.com AdminPass --superuser
```

Options: `--username SIMPLE_NAME` (login without an email), `--inactive`.

### 1.5 Web frontend packages (once)

```powershell
cd frontend\my-react-app
npm install
cd ..\..
```

### 1.6 Mobile app packages (once)

```powershell
cd grd_mb
npm install
cd ..
```

---

## 2. Run everything (day to day)

Open a separate terminal for each of these. Start them in this order.

### Terminal 1: containers (skip if already up)

```powershell
docker compose up -d postgres redis qdrant mailhog
```

### Terminal 2: API

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app
```

- API docs page: http://localhost:8000/docs
- Health check: http://localhost:8000/api/v1/health/services

To let a phone reach it, bind to all network interfaces:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0
```

### Terminal 3: Celery worker (does the uploads and analysis)

```powershell
.\.venv\Scripts\celery.exe -A app.workers.celery_app worker -l info --pool=solo
```

`--pool=solo` is required on Windows. Without a running worker, uploads stay "queued" and analysis never runs. The worker only reads the code and `.env` at startup, so restart it after any backend change.

### Terminal 4 (optional): Celery Beat, the scheduler

```powershell
.\.venv\Scripts\celery.exe -A app.workers.celery_app beat -l info
```

Only needed for scheduled scans and scheduled input sources.

### Terminal 5: web frontend

```powershell
cd frontend\my-react-app
npm run dev
```

Opens at http://localhost:5170. Sign in with the user you created (the demo seed user is `demo@grd` / `1223456`).

### Terminal 6 (optional): mobile app

```powershell
cd grd_mb
npx expo start --web        # in the browser, http://localhost:8081
npx expo start              # phone with Expo Go: scan the QR (needs the setup in section 2.1)
```

Testing on a real phone needs extra steps: the API must listen on your network and the firewall must allow it. See **section 2.1**.

The Android emulator (`npx expo start --android`) needs Android Studio and the Android SDK, which are not required for Expo Go. Without the SDK, Expo prints "Failed to resolve the Android SDK path". That message is only a warning; ignore it, or hide it for one session with `$env:ANDROID_HOME = "$env:LOCALAPPDATA"`.

### 2.1 Testing on a real phone (Expo Go over Wi-Fi)

The app loads from Expo but **logs in through the API**. If the API only listens on `127.0.0.1` (localhost), the phone can load the app and then fails to log in ("can't reach the API" after a long wait). Work through these once, in order.

**Step 1: find your PC's Wi-Fi/LAN address.** Ignore the WSL and Hyper-V ("vEthernet") addresses.

```powershell
ipconfig
```

Use the IPv4 address of your real adapter (for example `192.168.1.20`). The phone must be on the same network.

**Step 2: run the API on all interfaces.** Use a terminal:

```powershell
cd D:
ewdata\Grd-stk-mkt\grd_st_mkt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
```

Or in VS Code, choose **"API: uvicorn (LAN, for phone testing via grd_mb)"** in Run and Debug. The other API entries use `127.0.0.1` and will not work from a phone. The startup line must say `Uvicorn running on http://0.0.0.0:8000`. `make api-lan` does the same.

Check what it is listening on:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object LocalAddress
```

`0.0.0.0` is right. `127.0.0.1` means the phone cannot connect and no firewall setting will fix that.

**Step 3: allow the port through Windows Firewall.** Run once in an **Administrator** PowerShell:

```powershell
New-NetFirewallRule -DisplayName "GRD API 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private,Domain
```

If your network is set to "Public", change it to Private, or add `Public` to `-Profile`.

**Step 4: test from the PC using the LAN address** (not `localhost`):

```powershell
curl.exe http://192.168.1.20:8000/api/v1/health
```

Expect `{"status":"ok",...}`. "Failed to connect" means Step 2 or 3 is not done.

**Step 5: test from the phone's browser.** Open `http://192.168.1.20:8000/api/v1/health` on the phone. If the PC test passed but this does not load, the router is separating devices (guest Wi-Fi or "AP isolation"). Join the main Wi-Fi.

**Step 6: start Expo with the right address.** Because of the extra network adapters, Expo can pick the wrong one, so set it explicitly:

```powershell
cd D:
ewdata\Grd-stk-mkt\grd_st_mkt\grd_mb
$env:REACT_NATIVE_PACKAGER_HOSTNAME = "192.168.1.20"
$env:EXPO_PUBLIC_API_BASE = "http://192.168.1.20:8000/api/v1"
npx expo start -c
```

`-c` clears Expo's cache. Scan the QR code with Expo Go. If the login fails, the error shows the exact address the app tried; compare it with your PC address.

**Mobile checklist**

| Symptom | Cause |
|---|---|
| App loads, login hangs then "can't reach the API" | API bound to `127.0.0.1`, or firewall closed (Steps 2, 3) |
| PC test works, phone browser does not | Wi-Fi isolation or different network (Step 5) |
| Error shows the wrong IP | Set `EXPO_PUBLIC_API_BASE` and restart with `-c` (Step 6) |
| Code change not showing, or an old syntax error persists | Expo cache: stop it and run `npx expo start -c`; close unsaved editor copies of the file |
| Screen shows old behaviour after changing `.env` or backend code | Restart the API and the Celery worker; they do not reload `.env` |

To run the app on a phone with no PC at all, build an APK (Expo cloud build), which still needs an API address the phone can reach. This is not set up in the project.

### URLs at a glance

| What | URL |
|---|---|
| Web app | http://localhost:5170 |
| API docs | http://localhost:8000/docs |
| Service health | http://localhost:8000/api/v1/health/services |
| Qdrant dashboard | http://localhost:6333/dashboard |
| Mailhog inbox | http://localhost:8025 |
| Mobile app (web build) | http://localhost:8081 |

---

## 3. Everything in Docker instead (no local Python)

The compose file can also run the API, worker and scheduler as containers. It runs migrations first.

```powershell
docker compose build
docker compose up -d
docker compose logs -f api worker
```

Stop everything:

```powershell
docker compose down          # keeps data volumes
docker compose down -v       # also deletes all data (database, queue, vectors)
```

In this mode the API is at http://localhost:8000 and you only need the web frontend (`npm run dev`) on top.

---

## 4. Make shortcuts

If you have `make` (Git Bash or WSL), these wrap the commands above:

| Command | Does |
|---|---|
| `make install` | install package and dev dependencies |
| `make up` / `make down` | start / stop containers |
| `make migrate` | apply migrations |
| `make seed` | load demo data |
| `make api` / `make api-lan` | run the API / run it reachable from a phone |
| `make worker` / `make beat` | run Celery worker / scheduler |
| `make test` | run tests |
| `make lint` / `make fmt` | ruff + mypy / auto-format |

---

## 5. Database commands (Alembic)

Never edit tables by hand. Details in [DATABASE.md](DATABASE.md).

```powershell
alembic upgrade head                         # apply all pending migrations
alembic downgrade -1                         # roll back the last one
alembic current                              # which revision the database is on
alembic history --indicate-current           # full history
alembic revision --autogenerate -m "add foo table"   # new migration after changing a model
alembic check                                # fail if models and migrations disagree
```

Look inside the database:

```powershell
docker exec -it grd-stock-mkt-postgres-1 psql -U grd -d grd_stk_mkt
```

Container names come from the folder name. If yours differ, list them with `docker ps`.

Useful queries once inside `psql`:

```sql
select id, trigger, status, context from analysis_runs order by id desc limit 5;
select id, source_name, status from ingestion_runs order by id desc limit 5;
select ticker, count(*) from ohlcv group by 1;
select ticker, count(*) from fundamentals group by 1;
```

---

## 6. Checking that things work

```powershell
docker compose ps                                    # containers up and healthy
curl.exe http://localhost:8000/api/v1/health/services
.\.venv\Scripts\celery.exe -A app.workers.celery_app inspect active       # tasks running now
.\.venv\Scripts\celery.exe -A app.workers.celery_app inspect registered   # tasks the worker knows
docker exec grd-stock-mkt-redis-1 redis-cli llen celery                   # tasks waiting (0 = none stuck)
docker logs --tail 50 grd-stock-mkt-qdrant-1
```

The web app's **Health** tab shows the same checks with details.

---

## 7. Tests and code quality

```powershell
pytest -q                                   # all tests
pytest tests/test_document_analysis.py -q   # one file
ruff check app tests                        # lint
ruff format app tests                       # format
mypy app                                    # type check
```

Web frontend:

```powershell
cd frontend\my-react-app
npm run lint
npm run build          # production build into dist/
```

Mobile app:

```powershell
cd grd_mb
npx tsc --noEmit       # type check
npx expo lint
npx expo export --platform web --output-dir dist-web   # proves it bundles
```

---

## 8. Other project commands

Build the "GRD Calculation" Excel sheet from a Screener workbook (never modifies the source file):

```powershell
python scripts/write_grd_calculation.py SOURCE.xlsx
python scripts/write_grd_calculation.py SOURCE.xlsx --output OUT.xlsx --statement-sheet "Profit & Loss" --target "Net profit" --features Sales
```

Trigger a background task by hand:

```powershell
.\.venv\Scripts\celery.exe -A app.workers.celery_app call app.workers.tasks.rag.ingest_pending_documents
```

Request a ticker analysis from the command line (replace the token with one from login):

```powershell
$t = (curl.exe -s -X POST http://localhost:8000/api/v1/auth/login -d "username=demo@grd&password=1223456" | ConvertFrom-Json).access_token
curl.exe -X POST http://localhost:8000/api/v1/runs -H "Authorization: Bearer $t" -H "Content-Type: application/json" -d '{"ticker":"INFY","async_":true,"force_agents":true}'
```

---

## 9. Troubleshooting quick fixes

| Symptom | Fix |
|---|---|
| Login hangs, or "can't reach the API" | API not running, or the containers stopped. Run `docker compose up -d postgres redis qdrant mailhog`, then start uvicorn |
| Health tab: "no worker responded to ping" | Worker not running. Start the Celery worker command from section 2 |
| Uploads stay "queued" forever | Same: no worker |
| Containers vanished after a reboot or Docker restart | `docker compose up -d postgres redis qdrant mailhog` |
| Code change has no effect on uploads or analysis | Restart the Celery worker (it does not auto-reload) |
| `no such table` or missing column | `alembic upgrade head` |
| Analysis says "insufficient data" | The ticker needs at least 30 daily price bars ingested |
| Report shows placeholder text | No `OPENAI_API_KEY`: analysis still works, only AI narrative text is skipped |
| Two workers competing after moving folders | Stop all Celery processes, then start one: `Get-CimInstance Win32_Process \| Where-Object { $_.CommandLine -match 'celery' } \| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }` |
| Phone: app loads but login fails or hangs | API not on `0.0.0.0` or firewall closed: see section 2.1 |
| Port already in use | Find it: `Get-NetTCPConnection -LocalPort 8000 -State Listen`, then stop that process id |
| `Activate.ps1` blocked | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

## 10. Wiping data (destructive)

These cannot be undone.

```powershell
docker compose down -v                                   # deletes database, queue and vector data
Remove-Item -Recurse -Force data\uploads\*               # uploaded files
```

After `down -v`, redo section 1.3 and 1.4 (containers, `alembic upgrade head`, seed).
