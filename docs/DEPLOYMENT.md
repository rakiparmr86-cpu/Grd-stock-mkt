# Hosting the whole project on a server (architecture, containers, CI/CD, Kubernetes)

How the project runs in production, what already exists in this repo, what you would add, and the actual step-by-step process. It is honest about the gaps: the repo has a Dockerfile, a full Docker Compose file, a CI pipeline and a Kubernetes migration Job, but **no CD pipeline, no production compose file and no Kubernetes app manifests yet**. Those are given here as ready-to-copy templates, marked *(proposed)*.

Related: [COMMANDS.md](COMMANDS.md) (local commands), [CONFIGURATION.md](CONFIGURATION.md) (every setting), [DATABASE.md](DATABASE.md) (migrations), [../kubernetes/README.md](../kubernetes/README.md).

---

## 1. What runs where

```
                        Internet
                           │  HTTPS (443)
                           ▼
                ┌──────────────────────┐
                │  Reverse proxy       │  Caddy / Nginx / Ingress
                │  · TLS certificates  │
                │  · serves web app    │  static files (Vite build)
                │  · /api → API        │
                └───────┬──────────────┘
                        │
        ┌───────────────┼───────────────────────────────┐
        ▼               ▼                               ▼
   Web app (static)   API (FastAPI/uvicorn)      Mobile app (Expo)
                      stateless, N replicas       calls the same /api
                        │        │
          enqueue tasks │        │ read / write
                        ▼        ▼
                     Redis     Postgres + TimescaleDB ◄──────────┐
                  (queue db1,   prices, fundamentals,            │
                   results db2)  runs, reports, decisions         │
                        │                                         │
                        ▼                                         │
        ┌─────────────────────────────┐                           │
        │ Celery worker(s)            │───────────────────────────┘
        │ uploads, ingestion, agents, │──► Qdrant (vector store: RAG chunks)
        │ reports                     │──► OpenAI API (optional, outbound)
        └─────────────────────────────┘──► SMTP (alert emails, outbound)
        ┌─────────────────────────────┐
        │ Celery beat (exactly 1)     │  schedules → Redis
        └─────────────────────────────┘

        Shared files (data/uploads, data/reports)  ← API and workers both need them
```

### The components

| Component | Image | Stateful? | Scale | Notes |
|---|---|---|---|---|
| API | project `Dockerfile` | no | horizontal | `uvicorn app.main:app`; probes `/api/v1/health`, `/api/v1/health/ready` |
| Celery worker | same image | no (needs shared files) | horizontal | does all the slow work |
| Celery beat | same image | no | **exactly 1** | two beats would double every scheduled job |
| Postgres + TimescaleDB | `timescale/timescaledb:2.15.3-pg16` | **yes** | 1 primary | hypertables for prices; managed service also works |
| Redis | `redis:7-alpine` | small | 1 | Celery broker (db 1) and results (db 2); losing it loses queued tasks only |
| Qdrant | `qdrant/qdrant:v1.11.0` | **yes** | 1 | the RAG vector store |
| Web app | Nginx/Caddy serving the Vite `dist/` | no | any | static |
| Mailhog | dev only | no | none | replace with real SMTP in production |

**One image, three roles.** The API, the worker and beat all use the same Docker image; only the start command differs. That guarantees they run identical code.

---

## 2. What exists in the repo today

| Piece | Status | Where |
|---|---|---|
| Container image | done | `Dockerfile` (python:3.11-slim, installs the package, runs uvicorn) |
| Full stack in Docker Compose | done, with a gap (section 3) | `docker-compose.yml` (postgres, redis, qdrant, mailhog, migrate, api, worker, beat) |
| CI: lint, tests, migrations | done | `.github/workflows/ci.yml` |
| Kubernetes: migration Job | done | `kubernetes/migrate-job.yaml` and README |
| Kubernetes: app Deployments, Ingress, storage | **not yet** | templates in section 7 |
| CD: build image, push, deploy | **not yet** | template in section 6 |
| Web app container / static hosting | **not yet** | section 5 |
| Production compose with HTTPS | **not yet** | section 5 |
| Mobile release build | not set up | section 9 |

### What CI does today (`ci.yml`)
On every push to `main` and every pull request:
1. Starts Postgres (TimescaleDB) and Redis as service containers.
2. Installs the package, runs `ruff check` and `pytest`.
3. Proves migrations: `alembic upgrade head`, then `downgrade base` and `upgrade head` again, then `alembic check` (fails if models changed without a migration).

It does not build or push an image, and it does not deploy.

---

## 3. Two things to fix before hosting

### 3.1 API and worker must share the `data/` folder
The API saves uploaded files to `data/uploads`, and the **worker** reads them. The worker writes HTML reports to `data/reports`, and the **API** serves them. They also read `data/documents` and write logs.

In `docker-compose.yml` the `api`, `worker` and `beat` services have **no volume for `/app/data`**, so an upload saved by the API container is invisible to the worker container. Locally this never shows because both run on one disk.

Fix: add one shared named volume to all three services:

```yaml
services:
  api:
    volumes: [ "appdata:/app/data", "applogs:/app/logs" ]
  worker:
    volumes: [ "appdata:/app/data", "applogs:/app/logs" ]
  beat:
    volumes: [ "appdata:/app/data", "applogs:/app/logs" ]
volumes:
  appdata:
  applogs:
```

On Kubernetes this becomes a `ReadWriteMany` volume (NFS, EFS, Azure Files, CephFS) or, better long term, object storage (S3/MinIO) instead of local paths. That is a code change (the file paths are plain filesystem paths today), not just configuration.

### 3.2 Do not ship the demo user
`scripts/seed_data.py` creates a demo login with a known password. In production either do not run the seed at all, or delete that user, and create your own with `scripts/create_user.py`.

---

## 4. Configuration for production

Everything is environment variables (loaded from `.env`). The important ones:

| Variable | Production value |
|---|---|
| `ENV` | `prod` |
| `DEBUG` | `false` |
| `SECRET_KEY` | a long random string (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `POSTGRES_HOST/USER/PASSWORD/DB` | your database, with a strong password |
| `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Redis DB 0 / 1 / 2 |
| `QDRANT_URL`, `QDRANT_API_KEY` | the Qdrant address, and an API key |
| `LLM_PROVIDER`, `OPENAI_API_KEY`, `LLM_MODEL` | optional; without a key the AI narrative text is a placeholder and everything else works |
| `EMBEDDINGS_PROVIDER` | `openai` for real semantic search (`local` is a word-hash for offline use) |
| `SMTP_HOST/PORT/USER/PASSWORD/TLS/FROM` | a real mail server (not Mailhog) |
| `CORS_ORIGINS` | your web origin, only needed if the web app is on a different origin from the API (skip it by serving both from one domain, section 5) |

Keep secrets out of git: use a `.env.prod` on the server (mode 600), Docker secrets, or a Kubernetes `Secret`. The existing `migrate-job.yaml` already expects a ConfigMap `grd-stk-mkt-config` (non-secret values) and a Secret `grd-stk-mkt-secrets` (`SECRET_KEY`, DB password, API keys).

**Changing embeddings changes the vector size** (local 384 vs OpenAI 1536): recreate the Qdrant collection and re-ingest documents when you switch.

---

## 5. Option A: one server with Docker Compose (recommended to start)

Best for a demo, an interview, a small team. One VM (2 vCPU, 4 GB RAM is enough to start; add RAM if Qdrant holds many documents), Docker, and a domain name.

**Idea:** Caddy terminates HTTPS, serves the built web app, and forwards `/api/*` to the API. Web and API share one origin, so no CORS setup and the web app calls `/api/v1`.

### 5.1 One-time server setup

```bash
# Ubuntu 22.04+
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER            # log out and in again
sudo ufw allow 22 && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable
```

Point your domain's DNS `A` record at the server IP.

### 5.2 Get the code and build the web app

```bash
git clone <your-repo-url> grd && cd grd
cp .env.example .env.prod                # then edit it (section 4)
chmod 600 .env.prod

cd frontend/my-react-app
npm ci
VITE_API_BASE=/api/v1 npm run build      # output in dist/
cd ../..
```

`VITE_API_BASE` is baked in at build time.

### 5.3 `Caddyfile` *(proposed)*

```
grd.example.com {
    encode gzip
    handle /api/* {
        reverse_proxy api:8000
    }
    handle {
        root * /srv/web
        try_files {path} /index.html
        file_server
    }
}
```

Caddy gets and renews the HTTPS certificate on its own.

### 5.4 `docker-compose.prod.yml` *(proposed)*

Reuse the existing service definitions and override for production:

```yaml
# docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d
services:
  postgres:
    ports: !reset []          # not reachable from outside the host
    restart: unless-stopped
  redis:
    ports: !reset []
    restart: unless-stopped
  qdrant:
    ports: !reset []
    restart: unless-stopped
  mailhog:
    profiles: ["dev"]         # do not start it in production

  migrate:
    env_file: .env.prod
  api:
    image: ghcr.io/OWNER/grd-stk-mkt:latest     # or: build: .
    env_file: .env.prod
    ports: !reset []          # only Caddy talks to it
    restart: unless-stopped
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
    volumes: [ "appdata:/app/data", "applogs:/app/logs" ]
  worker:
    image: ghcr.io/OWNER/grd-stk-mkt:latest
    env_file: .env.prod
    restart: unless-stopped
    command: celery -A app.workers.celery_app worker -l info --concurrency=2
    volumes: [ "appdata:/app/data", "applogs:/app/logs" ]
  beat:
    image: ghcr.io/OWNER/grd-stk-mkt:latest
    env_file: .env.prod
    restart: unless-stopped
    volumes: [ "appdata:/app/data", "applogs:/app/logs" ]

  caddy:
    image: caddy:2
    restart: unless-stopped
    ports: [ "80:80", "443:443" ]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ./frontend/my-react-app/dist:/srv/web:ro
      - caddy_data:/data
    depends_on: [ api ]

volumes:
  appdata:
  applogs:
  caddy_data:
```

Notes:
- `--pool=solo` is a **Windows-only** requirement. On Linux the default worker pool is fine; `--concurrency=2` sets two processes.
- `--workers 2` gives the API two processes. Each holds its own database connection pool.
- Compose's `migrate` service runs `alembic upgrade head` first and the app services wait for it (`depends_on ... service_completed_successfully`).

### 5.5 First start

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose ps
docker compose logs -f migrate api worker

# create your user (do NOT run seed_data.py in production)
docker compose exec api python scripts/create_user.py you@example.com 'StrongPassword' --superuser
```

Open `https://grd.example.com`, sign in, and check the **Health** tab: Postgres, Redis, Qdrant and the Celery worker should all be up.

### 5.6 Updating (deploy a new version)

```bash
git pull
cd frontend/my-react-app && npm ci && VITE_API_BASE=/api/v1 npm run build && cd ../..
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Compose re-runs `migrate` first, then restarts `api`, `worker` and `beat` on the new image.

---

## 6. CI/CD: the actual process

**CI (exists):** every pull request is linted, tested, and its migrations are proven reversible.

**CD (proposed):** on a merge to `main`, after CI passes, build the image once, push it to a registry, and deploy that exact image.

```
 developer ─► pull request ─► CI (lint, tests, migration checks)
                                   │ merge to main
                                   ▼
                          build image, tag with commit SHA
                                   │
                                   ▼
                          push to registry (GHCR)
                                   │
                    ┌──────────────┴───────────────┐
                    ▼                              ▼
        Compose host: ssh, pull image,     Kubernetes: apply migrate Job,
        `up -d` (migrate runs first)       wait, then roll out Deployments
                    │                              │
                    └──────────────┬───────────────┘
                                   ▼
                     smoke test: GET /api/v1/health/ready
                                   │ fail → roll back to previous SHA
```

### 6.1 `.github/workflows/cd.yml` *(proposed)*

```yaml
name: cd
on:
  push:
    branches: [main]

permissions:
  contents: read
  packages: write

jobs:
  image:
    runs-on: ubuntu-latest
    outputs:
      tag: ${{ steps.meta.outputs.version }}
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: type=sha
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }},ghcr.io/${{ github.repository }}:latest

  web:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22 }
      - run: npm ci && VITE_API_BASE=/api/v1 npm run build
        working-directory: frontend/my-react-app
      - uses: actions/upload-artifact@v4
        with: { name: web-dist, path: frontend/my-react-app/dist }

  deploy:
    needs: [image, web]
    runs-on: ubuntu-latest
    environment: production            # lets you require a manual approval
    steps:
      - uses: actions/download-artifact@v4
        with: { name: web-dist, path: dist }
      - name: Deploy over SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            cd ~/grd && git pull
            docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod pull
            docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d
      - name: Publish web build
        run: scp -r dist/* ${{ secrets.SERVER_USER }}@${{ secrets.SERVER_HOST }}:~/grd/frontend/my-react-app/dist/
        # (needs the SSH key configured; or serve the web app from its own container image)
      - name: Smoke test
        run: curl --fail --retry 10 --retry-delay 5 https://grd.example.com/api/v1/health/ready
```

Secrets to add in GitHub → Settings → Secrets: `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`. Tag images by commit SHA so a rollback is "redeploy the previous SHA".

### 6.2 Database changes in a deploy
Migrations run **before** the new app serves traffic and are never run by the app pods themselves (with more than one replica they would race). Follow *expand → migrate → contract* so both a rollout and a rollback survive a half-applied state (details in `kubernetes/README.md` and `DATABASE.md`). Take a `pg_dump` before any migration that drops a column.

---

## 7. Option B: Kubernetes

Choose this when you need several replicas, zero-downtime rolling updates, or your organisation already runs a cluster (managed AKS/EKS/GKE, or k3s on a VM for a lightweight one). For one small team it is more moving parts than Compose; say so in an interview and explain when you would move.

### 7.1 What goes where

| Workload | Kind | Replicas | Storage |
|---|---|---|---|
| API | Deployment + Service | 2+ | shared data volume |
| Worker | Deployment | 2+ (scale on queue length) | shared data volume |
| Beat | Deployment (`strategy: Recreate`) | **1** | shared data volume |
| Migrations | Job (exists) | once per release | none |
| Qdrant | StatefulSet + PVC | 1 | its own persistent volume |
| Postgres + TimescaleDB | a managed service, or a Helm chart / operator | 1 primary | its own persistent volume |
| Redis | a managed service or a Helm chart | 1 | small |
| Web app | Deployment (Nginx) or a static host / CDN | 2 | none |
| Ingress | Ingress + cert-manager | | TLS |

Do not hand-roll Postgres in a Deployment. Use a managed database or an operator, because backups and failover are the hard part.

### 7.2 Manifests *(proposed; names match the existing migrate Job)*

```yaml
# configmap + secret (values are examples)
apiVersion: v1
kind: ConfigMap
metadata: { name: grd-stk-mkt-config }
data:
  ENV: "prod"
  DEBUG: "false"
  POSTGRES_HOST: "postgres"
  POSTGRES_DB: "grd_stk_mkt"
  POSTGRES_USER: "grd"
  REDIS_URL: "redis://redis:6379/0"
  CELERY_BROKER_URL: "redis://redis:6379/1"
  CELERY_RESULT_BACKEND: "redis://redis:6379/2"
  QDRANT_URL: "http://qdrant:6333"
  EMBEDDINGS_PROVIDER: "openai"
---
apiVersion: v1
kind: Secret
metadata: { name: grd-stk-mkt-secrets }
stringData:
  SECRET_KEY: "<random>"
  POSTGRES_PASSWORD: "<password>"
  OPENAI_API_KEY: "<key>"
  QDRANT_API_KEY: "<key>"
---
# shared files for uploads and reports (ReadWriteMany storage class required)
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: grd-data }
spec:
  accessModes: [ReadWriteMany]
  resources: { requests: { storage: 20Gi } }
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: grd-stk-mkt-api }
spec:
  replicas: 2
  selector: { matchLabels: { app: grd-stk-mkt, component: api } }
  template:
    metadata: { labels: { app: grd-stk-mkt, component: api } }
    spec:
      containers:
        - name: api
          image: ghcr.io/OWNER/grd-stk-mkt:SHA
          command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
          envFrom:
            - configMapRef: { name: grd-stk-mkt-config }
            - secretRef: { name: grd-stk-mkt-secrets }
          ports: [{ containerPort: 8000 }]
          readinessProbe:
            httpGet: { path: /api/v1/health/ready, port: 8000 }
            periodSeconds: 10
          livenessProbe:
            httpGet: { path: /api/v1/health, port: 8000 }
            periodSeconds: 20
          resources:
            requests: { cpu: 200m, memory: 384Mi }
            limits: { cpu: "1", memory: 1Gi }
          volumeMounts: [{ name: data, mountPath: /app/data }]
      volumes:
        - name: data
          persistentVolumeClaim: { claimName: grd-data }
---
apiVersion: v1
kind: Service
metadata: { name: grd-stk-mkt-api }
spec:
  selector: { app: grd-stk-mkt, component: api }
  ports: [{ port: 80, targetPort: 8000 }]
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: grd-stk-mkt-worker }
spec:
  replicas: 2
  selector: { matchLabels: { app: grd-stk-mkt, component: worker } }
  template:
    metadata: { labels: { app: grd-stk-mkt, component: worker } }
    spec:
      containers:
        - name: worker
          image: ghcr.io/OWNER/grd-stk-mkt:SHA
          command: ["celery", "-A", "app.workers.celery_app", "worker", "-l", "info", "--concurrency=2"]
          envFrom:
            - configMapRef: { name: grd-stk-mkt-config }
            - secretRef: { name: grd-stk-mkt-secrets }
          resources:
            requests: { cpu: 250m, memory: 512Mi }
            limits: { cpu: "1", memory: 1500Mi }
          volumeMounts: [{ name: data, mountPath: /app/data }]
      volumes:
        - name: data
          persistentVolumeClaim: { claimName: grd-data }
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: grd-stk-mkt-beat }
spec:
  replicas: 1
  strategy: { type: Recreate }        # never two beats at once
  selector: { matchLabels: { app: grd-stk-mkt, component: beat } }
  template:
    metadata: { labels: { app: grd-stk-mkt, component: beat } }
    spec:
      containers:
        - name: beat
          image: ghcr.io/OWNER/grd-stk-mkt:SHA
          command: ["celery", "-A", "app.workers.celery_app", "beat", "-l", "info"]
          envFrom:
            - configMapRef: { name: grd-stk-mkt-config }
            - secretRef: { name: grd-stk-mkt-secrets }
---
apiVersion: apps/v1
kind: StatefulSet
metadata: { name: qdrant }
spec:
  serviceName: qdrant
  replicas: 1
  selector: { matchLabels: { app: qdrant } }
  template:
    metadata: { labels: { app: qdrant } }
    spec:
      containers:
        - name: qdrant
          image: qdrant/qdrant:v1.11.0
          ports: [{ containerPort: 6333 }]
          volumeMounts: [{ name: storage, mountPath: /qdrant/storage }]
  volumeClaimTemplates:
    - metadata: { name: storage }
      spec:
        accessModes: [ReadWriteOnce]
        resources: { requests: { storage: 10Gi } }
---
apiVersion: v1
kind: Service
metadata: { name: qdrant }
spec:
  selector: { app: qdrant }
  ports: [{ port: 6333 }]
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: grd-stk-mkt
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt
spec:
  tls: [{ hosts: [grd.example.com], secretName: grd-tls }]
  rules:
    - host: grd.example.com
      http:
        paths:
          - { path: /api, pathType: Prefix, backend: { service: { name: grd-stk-mkt-api, port: { number: 80 } } } }
          - { path: /, pathType: Prefix, backend: { service: { name: grd-stk-mkt-web, port: { number: 80 } } } }
```

### 7.3 Deploy order (what the CD job runs)

```bash
kubectl apply -f kubernetes/configmap.yaml -f kubernetes/secret.yaml -f kubernetes/storage.yaml
# 1. schema first, gated
kubectl apply -f kubernetes/migrate-job.yaml
kubectl wait --for=condition=complete --timeout=300s job/grd-stk-mkt-migrate
# 2. then the app, rolling
kubectl set image deployment/grd-stk-mkt-api    api=ghcr.io/OWNER/grd-stk-mkt:$SHA
kubectl set image deployment/grd-stk-mkt-worker worker=ghcr.io/OWNER/grd-stk-mkt:$SHA
kubectl set image deployment/grd-stk-mkt-beat   beat=ghcr.io/OWNER/grd-stk-mkt:$SHA
kubectl rollout status deployment/grd-stk-mkt-api --timeout=180s
# roll back if it fails
kubectl rollout undo deployment/grd-stk-mkt-api
```

Scaling: `kubectl scale deployment/grd-stk-mkt-worker --replicas=4`, or use KEDA to scale workers on the Redis queue length (`llen celery`). Never scale beat above 1.

---

## 8. RAG in production

The RAG part is: **files → parse → chunk → embed → Qdrant → retrieve**. Hosting decisions that matter:

| Concern | Guidance |
|---|---|
| Qdrant storage | Persistent volume (`/qdrant/storage`). Losing it loses the index (but not the source files if you keep them) |
| Where ingestion runs | In the Celery worker. Upload → API saves the file → worker parses, chunks, embeds, writes to Qdrant. Both need the shared `data/` folder (section 3.1) |
| Embeddings | `local` is a word-hash (offline, keyword-like). `openai` (`text-embedding-3-small`, 1536 dimensions) gives real semantic search, costs a little per document, and needs outbound HTTPS |
| Changing embedding model | Vector size changes: recreate the collection and re-ingest everything |
| DB and vector store are linked | `ingestion_runs.stats.source_ids` point at Qdrant documents. If you restore Postgres without Qdrant, "Analyze document" reports that the chunks are gone. **Back up both at the same time** |
| Qdrant security | Set `QDRANT_API_KEY`, do not publish ports 6333/6334, keep it on the internal network |
| Qdrant version | Server is pinned to v1.11.0 while the Python client is newer (a warning shows in logs). Upgrade the server image in step with the client |
| Dashboard | `http://<qdrant>:6333/dashboard` is available inside the network; expose it only through an authenticated tunnel |

---

## 9. Mobile app in production

Expo Go (QR code) is for development. For a real release, build an app that points at your HTTPS API:

```bash
cd grd_mb
npm install -g eas-cli
eas login
eas build:configure
EXPO_PUBLIC_API_BASE=https://grd.example.com/api/v1 eas build -p android --profile preview
```

Because the API is on HTTPS, no cleartext exception is needed. The address is baked in at build time. See the earlier "run on phone without the PC" notes in [COMMANDS.md](COMMANDS.md) section 2.1.

---

## 10. Security checklist

- [ ] `ENV=prod`, `DEBUG=false`, a strong random `SECRET_KEY`.
- [ ] HTTPS only. **The report download links carry the login token in the URL (`?access_token=`)**; without HTTPS that token is exposed. Consider short-lived, single-purpose download tokens for a public deployment.
- [ ] No demo user; create your own with `create_user.py`.
- [ ] Postgres, Redis and Qdrant are not reachable from the internet (no published ports; firewall or network policy).
- [ ] Qdrant has an API key; Redis has a password if it leaves a private network.
- [ ] The Docker image runs as root today. Add a non-root `USER` to the `Dockerfile` for production.
- [ ] Secrets are in a `Secret` / `.env.prod` (mode 600), never in git.
- [ ] Uploads are limited (`UPLOAD_MAX_MB`, allowed extensions are enforced) and URLs for the crawler are checked against private addresses (SSRF guard exists).
- [ ] There is no API rate limiting yet; put it on the reverse proxy (Caddy/Nginx/Ingress) if the API is public.
- [ ] CORS lists only your web origin (or is unnecessary because everything is one origin).

---

## 11. Operations

**Monitoring today:** the Health tab (Postgres, Redis, Qdrant, worker, with details), the Activity tab, the Exceptions tab (unexpected errors and task failures are stored), log files in `logs/`, and `docker compose logs` / `kubectl logs`.
**Add for production:** an uptime check on `/api/v1/health/ready`, log shipping (Loki, ELK or your cloud's logging), and alerts on queue length and failed tasks.

**Backups**

| What | How | Frequency |
|---|---|---|
| Postgres | `docker compose exec postgres pg_dump -U grd grd_stk_mkt \| gzip > backup.sql.gz` (or the managed service's snapshots) | daily, and before any contracting migration |
| Qdrant | snapshot API: `POST /collections/grd_documents/snapshots`, copy the snapshot off the host | daily, taken at the same time as Postgres |
| `data/uploads`, `data/reports` | copy the volume / object storage versioning | daily |
| Configuration | `.env.prod` in a password manager | on change |

Test a restore at least once.

**Troubleshooting on the server**

| Symptom | Check |
|---|---|
| Uploads stay "queued" | worker running? `docker compose ps`, `docker compose logs worker`; Health tab shows the worker |
| Uploaded file "not found" in the worker | the API and worker do not share `data/` (section 3.1) |
| Analysis works locally, fails in the container | env vars missing in `.env.prod`; check `docker compose exec api env \| grep -i postgres` |
| Login works, calls fail with CORS errors | web and API on different origins; use the single-domain setup or set `CORS_ORIGINS` |
| Slow first analysis | first embedding/Qdrant call is a cold start; later calls are faster |
| A scheduled job runs twice | two beat instances |

---

## 12. Which option to choose

| | Compose on one VM | Kubernetes | Managed pieces (RDS/Timescale, Redis, Qdrant Cloud) |
|---|---|---|---|
| Effort | low | high | medium |
| Downtime on update | seconds | none (rolling) | depends on the compute you choose |
| Scaling | vertical, or a few workers | horizontal, automatic | horizontal for compute |
| Ops burden | you run the databases | you run the cluster | provider runs the databases |
| Good for | demo, interview, small team | several teams, uptime targets | teams that do not want to run databases |

A sensible path: Compose on one VM now, move the databases to managed services when data matters, and move the app to Kubernetes when you need several replicas or rolling updates.

---

## 13. How to explain this in an interview

> "The system is stateless app containers (API, worker, one scheduler) built from one image, plus three stateful stores: Postgres with TimescaleDB for prices and results, Qdrant for the document vectors, and Redis as the task queue. CI lints, tests and proves the migrations are reversible on every pull request. On merge, CD builds the image once, tags it with the commit SHA, runs the migration as a gated step, then rolls the app out and smoke-tests the readiness endpoint, rolling back to the previous SHA if it fails. I would start on one VM with Compose and Caddy for HTTPS, and move to Kubernetes when I need rolling updates and several replicas. The two things I had to get right are shared file storage between the API and the workers, and running exactly one scheduler."

Points that show depth: migrations are a separate gated step (apps never migrate on startup); one image for three roles; beat is a singleton; RAG and Postgres must be backed up together because document rows point at vector ids; the AI is optional so the platform runs and tests offline.
