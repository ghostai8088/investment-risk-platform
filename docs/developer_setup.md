# Developer Setup

The live project state is `docs/project_memory/current_state.md`; the operative slice sequence is
`10_delivery_backlog/delivery_roadmap.md`.

## Prerequisites

- Python 3.12+ (the ratified backend runtime, AD-003; CI runs 3.12)
- Node 20+ (for the frontend, AD-003; if installed via nvm, ensure its `bin` is on PATH)
- Docker (for the local PostgreSQL container)

## Backend / Python

```bash
make setup        # create .venv, install dev deps and local packages
make lint         # ruff format --check + ruff check
make typecheck    # mypy
make test         # pytest (SQLite; PG-only suites skip without IRP_TEST_DATABASE_URL)
make secret-scan  # scripts/secret_scan.py
make docs-check   # scripts/check_docs.py
make check        # all of the above
```

Enable the fast pre-commit gate (MD-H1; format + lint on every commit — the CI-#136 class becomes
uncommittable; full `make check` remains the pre-push bar):

```bash
git config core.hooksPath .githooks
```

Run the API locally (needs the database at head — see below):

```bash
DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \
  .venv/bin/uvicorn irp_backend.main:app --app-dir apps/backend/src --reload
# GET http://localhost:8000/health  -> {"status":"ok"}
```

Domain endpoints authenticate via the DEV header shim (`X-User-Id`/`X-Tenant-Id` — DR-P1A0-3, not a security
boundary until SSO); entitlement + RLS behind it are enforced.

## Frontend / Node

```bash
make fe-check                  # npm install, lint, typecheck, test, build
npm run -w apps/frontend dev   # dev server; proxies /risk to localhost:8000
```

See `apps/frontend/README.md` for the full run recipe including a verified dev-session seeding snippet.

## Local PostgreSQL + migrations

A single reused container (`irp_pg_local`, postgres:16) serves local full-suite validation:

```bash
docker run -d --name irp_pg_local -e POSTGRES_DB=irp -e POSTGRES_USER=irp -e POSTGRES_PASSWORD=irp \
  -p 5432:5432 postgres:16                       # once; later: docker start irp_pg_local
DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp .venv/bin/alembic upgrade head
DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp .venv/bin/alembic check   # drift gate
```

Run the FULL suite (incl. the PG-only RLS/append-only proofs):

```bash
DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \
IRP_TEST_DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \
  .venv/bin/python -m pytest packages/shared-python/tests apps/backend/tests
```

**Reset the schema between full runs** (some suites self-seed system-tenant rows; a second run against the same
schema fails spuriously) — and restore the default PUBLIC grant CI gets for free:

```sql
DROP SCHEMA public CASCADE; CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO irp; GRANT USAGE ON SCHEMA public TO PUBLIC;
```

Never grant schema USAGE to `irp_ops` directly (a per-role ACL entry breaks the downgrade smoke's DROP ROLE;
migrations manage that role's grants).

## Ground rules

- No secrets in source (BR-10). Configuration comes from the environment.
- Every domain endpoint binds to the entitlement (BR-11), audit (BR-12), and lineage (BR-13) frameworks; governed
  derived numbers additionally bind snapshot + run + registered model version (AD-014).
- `packages/shared-python/src/irp_shared/audit/service.py` is FROZEN — never modify it.
- All checks must pass before merge; CI enforces them (see `08_testing_qa/ci_enforcement_overview.md`).
