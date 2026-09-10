# kubernetes/

Manifests for running grd-stk-mkt on a cluster. The point of this folder for
**database management**: migrations run as their own step, gated before the app.

## Migration strategy

Run `alembic upgrade head` in a **Job** (or a Deployment `initContainer`) that
must succeed before the API / worker / beat pods start serving. Never let an app
pod run migrations on startup — with >1 replica they race.

- `migrate-job.yaml` — a `Job` that runs `alembic upgrade head`. In CD, apply it
  and wait (`kubectl wait --for=condition=complete job/grd-stk-mkt-migrate`)
  before `kubectl rollout` of the Deployments. Bump the job name (or use
  `generateName`) per release so a new image gets a new Job.
- Alternative: copy the `initContainer` block from `migrate-job.yaml`'s pod spec
  into each Deployment. Simpler, but the migration then reruns per pod (harmless
  — it's idempotent — just noisier).

## Expand → migrate → contract

Keep each migration backward-compatible for one release so a rollout and a
rollback both survive a half-applied state:

1. Release N: additive migration (new nullable columns / tables). Code writes
   old + new.
2. Release N+1: backfill migration; code reads new.
3. Release N+2: contracting migration (drop old columns).

## Files

| File | Purpose |
| --- | --- |
| `migrate-job.yaml` | one-shot `alembic upgrade head` |
| _(add)_ `configmap.yaml`, `secret.yaml` | non-secret env + `SECRET_KEY` / DB creds |
| _(add)_ `api-deployment.yaml`, `worker-deployment.yaml`, `beat-deployment.yaml` | the app tiers |

The app image is the repo `Dockerfile`; set `image:` to your registry path.
