# Investment Risk Platform — Monorepo

Full-scope enterprise investment risk platform. This repository contains both the **governance baseline**
(numbered `00_`–`11_` directories) and the **application monorepo** (`apps/`, `packages/`, `services` via `apps/worker`,
`infra/`). Step 1D establishes the **engineering enforcement scaffold only** — there is no domain/risk functionality yet.

> Status: **Step 1D — scaffolding**. No market/credit/liquidity/counterparty risk, scenarios, reporting, dashboards, or
> database schema are implemented. See `11_decision_log/architecture_decision_log.md` and `03_architecture/` for ratified
> decisions, and `00_ai_operating_model/build_rules.md` for the non-negotiable build rules enforced by CI.

## Layout

```
00_…11_/                 Governance baseline (operating model, ADRs, standards, controls)
apps/
  backend/               Python 3.12+ FastAPI service (AD-003). System endpoints only.
  frontend/              TypeScript + React + Vite shell (AD-003).
  worker/                Python calculation-run worker skeleton (AD-006). No calcs yet.
packages/
  shared-python/         Shared Python library (temporal-class markers, version).
  shared-ts/             Shared TypeScript types.
infra/docker/            Dockerfiles (AD-010).
migrations/              Empty Alembic framework (no schema yet).
scripts/                 check_docs.py, secret_scan.py (CI placeholders).
.github/workflows/ci.yml CI: lint, types, tests, secret scan, docs check.
```

## Quickstart

Prerequisites: Python 3.12+ and Node 20+.

```bash
# Backend / Python toolchain
make setup        # create .venv, install dev deps + local packages
make check        # ruff format check, ruff lint, mypy, pytest, secret scan, docs check

# Frontend / Node toolchain
make fe-check     # npm install, lint, typecheck, test, build
```

See `docs/developer_setup.md` for details. **Never commit secrets** (BR-10); copy `.env.example` to `.env` for local config.

## Alignment

Every file in this scaffold aligns to the accepted ADRs (AD-003…AD-010) and build rules (BR-1…BR-19). Future domain modules
**must** bind to the entitlement (BR-11), audit (BR-12), and lineage (BR-13) frameworks; the only endpoints permitted before
those frameworks exist are the system health/version probes.
