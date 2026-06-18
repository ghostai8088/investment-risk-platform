# Developer Setup

This is the Step 1D engineering scaffold. There is no domain functionality yet.

## Prerequisites

- Python 3.12+ (the ratified backend runtime, AD-003)
- Node 20+ (for the frontend, AD-003)
- Docker (optional, for the container scaffold)

## Backend / Python

```bash
make setup        # create .venv, install dev deps and local packages
make lint         # ruff format --check + ruff check
make typecheck    # mypy
make test         # pytest
make secret-scan  # scripts/secret_scan.py
make docs-check   # scripts/check_docs.py
make check        # all of the above
```

Run the API locally:

```bash
.venv/bin/uvicorn irp_backend.main:app --reload
# GET http://localhost:8000/health  -> {"status":"ok"}
# GET http://localhost:8000/version
```

## Frontend / Node

```bash
make fe-check     # npm install, lint, typecheck, test, build
npm run -w apps/frontend dev   # local dev server
```

## Containers (optional)

```bash
cp .env.example .env           # set local-only values; never commit .env (BR-10)
docker compose build
docker compose up
```

## Database migrations (foundation slice)

The foundation tables (audit, entitlement, calculation-run) are created by Alembic against PostgreSQL. With the
docker-compose `db` running and `DATABASE_URL` set (see `.env.example`):

```bash
.venv/bin/pip install "psycopg[binary]"        # PostgreSQL driver (not needed for unit tests)
.venv/bin/alembic upgrade head                 # apply the foundation schema + RLS + append-only triggers
.venv/bin/alembic downgrade base               # revert
```

Unit tests do not need PostgreSQL — they run on in-memory SQLite (AD-011). The CI `migration` job validates the PostgreSQL
schema, row-level security, and append-only triggers against a real Postgres service.

## Ground rules

- No secrets in source (BR-10). Configuration comes from the environment.
- No domain endpoints until they bind to the entitlement (BR-11), audit (BR-12), and lineage (BR-13) frameworks.
- All checks must pass before merge; CI enforces them (see `08_testing_qa/ci_enforcement_overview.md`).
