# Investment Risk Platform — Monorepo

Full-scope enterprise investment risk platform. This repository contains both the **governance baseline**
(numbered `00_`–`11_` directories) and the **application monorepo** (`apps/`, `packages/`, `services` via `apps/worker`,
`infra/`). Multi-tenant, auditable, reproducible, governed — NOT an MVP.

> Status (maintained in `docs/project_memory/current_state.md` — read THAT for the live picture): the P0.5–P3
> foundation is DELIVERED and CI-green — the frozen audit framework + hash chain, FORCE-RLS multi-tenancy,
> entitlement/lineage/data-quality rails, reference & portfolio core, the captured market-data layer (FX, prices,
> curves, benchmarks, factor returns), the reproducibility primitive (`dataset_snapshot` + `calculation_run` +
> registered `model_version`), FOUR governed risk numbers (analytic sensitivities, factor exposures, factor
> covariance, parametric VaR), and the first read-only frontend (the risk runs & results view, dev-shim session).
> Credit/liquidity/counterparty risk, stress, limits/breach, reporting dashboards, real SSO, and vendor adapters
> are NOT yet built — the operative sequence is `10_delivery_backlog/delivery_roadmap.md`. Ratified decisions:
> `11_decision_log/architecture_decision_log.md`; non-negotiable build rules: `00_ai_operating_model/build_rules.md`.

## Layout

```
00_…11_/                 Governance baseline (operating model, ADRs, standards, controls)
apps/
  backend/               Python 3.12+ FastAPI service (AD-003). Governed domain + system endpoints.
  frontend/              TypeScript + React + Vite (AD-003). Read-only risk runs & results view (FE-1).
  worker/                Python worker skeleton (AD-006) + the audit-chain verification CLI. No calcs yet.
packages/
  shared-python/         `irp_shared` — the domain library (audit/entitlement/lineage/DQ/snapshot/calc/
                         reference/portfolio/marketdata/exposure/risk; web-framework-free).
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

Every module aligns to the accepted ADRs and build rules (BR-1…BR-19). Every domain module **binds** to the
entitlement (BR-11), audit (BR-12), and lineage (BR-13) frameworks — this is enforced, not aspirational: governed
derived numbers additionally bind `dataset_snapshot` + `calculation_run` + a registered `model_version` and land in
append-only tables under FORCE RLS. `packages/shared-python/src/irp_shared/audit/service.py` is FROZEN.
