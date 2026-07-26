# Developer Setup

The live project state is `docs/project_memory/current_state.md`; the operative slice sequence is
`10_delivery_backlog/delivery_roadmap.md`.

## Prerequisites

- Python 3.12+ (the ratified backend runtime, AD-003; CI runs 3.12)
- Node 24 (the version CI pins — active LTS; Node 20 went EOL 2026-04). Node 20 will still
  build but is no longer what the gates run, so version-sensitive failures may not reproduce.
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
  .venv/bin/python -m pytest
```

Bare `pytest` (no paths) is deliberate: it uses `pyproject.toml`'s `testpaths`, which is what CI's own
`pytest` step runs. Naming paths by hand previously omitted `apps/worker/tests`, so the worker tier
was silently outside the local full run.

A caution about what a local PG run can and cannot prove: your `.venv` has **all three** packages
installed (`make setup` installs shared-python, backend and worker), so a local run cannot detect a
CI job whose `pip install` list is missing a package a test imports. That failure mode is real — the
CI PostgreSQL job installed only `shared-python` while two of its suites import `irp_worker` /
`irp_backend` inside test functions, so they failed to collect with `ModuleNotFoundError` in CI while
passing locally. Rehearsing CI's step *ordering* locally does not rehearse its *environment*. To
check an install-surface change, build a throwaway venv with exactly the job's install list:

```bash
python3 -m venv /tmp/civenv && /tmp/civenv/bin/pip install -r requirements-dev.txt
/tmp/civenv/bin/pip install -e packages/shared-python -e apps/backend -e apps/worker "psycopg[binary]"
/tmp/civenv/bin/python -m pytest <the suites that job runs>
```

Finally, mirror CI's **downgrade smoke** — the step that proves every migration's `downgrade()` still
works against real seeded rows. It is the last step of the CI migration job and has repeatedly caught
things nothing else does (most recently an FK violation from demo rows referencing the migration-seeded
permission catalog):

```bash
DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp .venv/bin/alembic downgrade base
```

Run it AFTER the full suite (so it exercises the seeded state), and re-`upgrade head` afterwards. Note
it also drops the `irp_ops` role, so it fails if any OTHER local database still holds objects owned by
that role — drop stray `irp_*` databases first or the error will look like a migration defect.

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
