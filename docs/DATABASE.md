# DATABASE.md

How the database is managed and how every change stays tracked and reviewable.

**Which database:** one **PostgreSQL** instance (TimescaleDB image), database
`grd_stk_mkt` by default. It holds *all* relational data — `users` (auth),
config, watchlists, strategies, rules, input sources, market fundamentals, and
the analysis history / audit tables. `/auth/login` reads the `users` table here.
Redis (cache/queue) and Qdrant (vectors) are separate and are **not** touched by
migrations. Connection: `settings.sqlalchemy_url` — see
[CONFIGURATION.md](CONFIGURATION.md#postgresql--timescaledb).

## Approach: versioned migrations (Alembic), not init scripts

The relational schema lives in **SQLAlchemy models** (`app/models/`). Every
change to it is a **numbered, reversible migration** under
`migrations/versions/`, generated from the models and committed to git. There is
no `docker-entrypoint-initdb.d/*.sql` — those only run once on an empty volume,
never version what's applied, and can't roll back.

| | numbered `*.sql` in `initdb.d` | Alembic migrations (this project) |
| --- | --- | --- |
| Applies to an existing DB | ❌ first boot only | ✅ any DB, any time |
| Records what's applied | ❌ | ✅ `alembic_version` table |
| Rollback | ❌ | ✅ `downgrade()` per revision |
| Generated from the code's models | ❌ hand-written | ✅ `--autogenerate` + review |
| Detects drift (model vs DB) | ❌ | ✅ `alembic check` |
| Two devs add a change at once | ❌ silent clash | ✅ two heads → explicit `merge` |
| Data backfills / conditional logic | awkward | ✅ Python in the migration |

You can still write **raw SQL** inside a migration when the DSL is clumsy —
`op.execute("...")` (migration `0001` does exactly this for the TimescaleDB
hypertables). You keep the SQL; you also get versioning, rollback and an audit
trail around it.

## Layout

```
app/models/            the schema — source of truth (imported in models/__init__.py)
migrations/
  env.py               wires Alembic to app.core.config.settings + Base.metadata
  script.py.mako       template for new revision files
  versions/
    0001_initial.py        all tables + timescaledb hypertables
    0002_input_sources.py   input_sources
alembic.ini            config (script location, post-write ruff hook)
```

`alembic_version` (one row, the current revision id) is created automatically in
the target database on first `upgrade`.

## The workflow

### Change the schema

1. Edit / add a model in `app/models/`. New module → import it in
   `app/models/__init__.py` so autogenerate sees it.
2. Generate the migration:
   ```bash
   make db-new m="add positions table"      # alembic revision --autogenerate -m ...
   ```
3. **Read the generated file.** Autogenerate is good but not perfect — it misses
   renames (sees drop+add), some server defaults, CHECK constraints, and
   enum/type changes. Fix by hand; add a real `downgrade()`.
4. Apply and exercise the rollback:
   ```bash
   make db-up        # upgrade head
   make db-redo      # downgrade -1 then upgrade head — proves downgrade() works
   ```
5. Update `scripts/seed_data.py` if the demo data needs the new column, and
   `docs/TECHNICAL.md` §6 (the table list).
6. Commit the model change **and** the migration together in one PR.

### Everyday commands

| Command | What it does |
| --- | --- |
| `make db-up` | apply all pending migrations (`alembic upgrade head`) |
| `make db-down` | roll back one (`alembic downgrade -1`) |
| `make db-current` | which revision the DB is on |
| `make db-history` | full history, current marked |
| `make db-heads` | head revision(s) — **more than one = unmerged branch** |
| `make db-check` | non-zero exit if models changed without a migration (CI uses this) |
| `make db-dump` | write `schema.sql` (a plain-SQL snapshot for review / ERD tools) |
| `alembic downgrade <rev>` / `alembic upgrade <rev>` | move to a specific revision |
| `alembic stamp head` | mark an already-correct DB as up to date without running DDL |

### Two people added migrations at once

`make db-heads` shows two heads. Resolve with a merge revision (no DDL, just
joins the history):

```bash
alembic merge -m "merge x and y" <head1> <head2>
make db-up
```

## Conventions

- **One migration per logical change**, with a message that reads as a changelog
  line (`add positions table`, `index signals.ticker`, `backfill instrument.sector`).
- File names: autogenerate produces `<12-hex>_<slug>.py`. The two hand-seeded
  ones use `0001_` / `0002_` for readability; either is fine — order comes from
  the `down_revision` chain, not the filename.
- **Every migration is reversible.** If a `downgrade()` genuinely can't restore
  data, say so in a comment and make it drop cleanly.
- **Schema vs data.** DDL and reference data that the app needs to boot go in
  migrations. Demo / fixture data goes in `scripts/seed_data.py` (never a
  migration).
- **Big backfills** ship as their own migration, separate from the DDL that adds
  the column, so a slow data step can't hold a DDL lock.
- Don't edit a migration that has run anywhere shared — add a new one.

## Production / staging

- Deploys run `alembic upgrade head` **before** the new app version serves
  traffic:
  - **docker compose** — the `migrate` one-shot service runs first; `api`,
    `worker`, `beat` have `depends_on: migrate: {condition: service_completed_successfully}`.
  - **Kubernetes** — a `Job` (or an `initContainer`) that runs
    `alembic upgrade head`; the Deployment rolls out only after it succeeds. See
    [`kubernetes/`](../kubernetes/).
- Keep migrations **backward-compatible for one release** (expand → migrate →
  contract): add nullable columns / new tables first, deploy code that writes
  both old and new, backfill, then a later migration drops the old shape. This
  lets a rollout and a rollback both work mid-migration.
- Set a guard for long statements in risky migrations:
  `op.execute("SET lock_timeout = '5s'")` / `statement_timeout` at the top.
- Take a backup (`pg_dump`) before a contracting migration in prod.

## CI

`.github/workflows/ci.yml` spins up a throwaway Postgres and runs:

1. `ruff check` + `pytest -q`
2. `alembic upgrade head` — every migration applies cleanly from empty
3. `alembic downgrade base` then `alembic upgrade head` — every `downgrade()` works
4. `alembic check` — the models match the migrations (no forgotten `db-new`)

A PR that changes `app/models/` without a matching migration fails step 4.

## TimescaleDB note

`ohlcv` and `indicator_points` are promoted to **hypertables** in `0001`
(`SELECT create_hypertable(...)`). Plain PostgreSQL also works — `0001` only
runs the hypertable calls if the `timescaledb` extension could be created. If
you add a time-series table later, call `create_hypertable` in its migration the
same way.
