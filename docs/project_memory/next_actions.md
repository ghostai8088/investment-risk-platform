# Next Actions

> **As of 2026-06-25.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the **P1B block** + **P1C-0** (AD-017) → **P1C-1 BUILD** (`bb89c74`, #43): `portfolio` EV hierarchy → **P1C-2 BUILD**
(`abb230f`, #46): `transaction` IA append-only → **P1C-3 BUILD** (`4ee124e`, #49): `position` FR → **P1C-4 BUILD** (`c5c5806`,
#54): `valuation` FR captured marks (**REQ-PPM-003 Done**) → **P1C-4 memory** (`6e3dcc1`, #55) → **P1C-5 plan** (`8a14173`,
#56; OD-P1C5-1..6 signed off) → **P1C-5 BUILD** (`0bef45b`, CI-green run #57; 8-lens reviewed, 0 block, 2 LOW fence folds):
read-only as-of holdings / portfolio views — the platform's **first read-model / composition package** (`irp_shared/holdings/`
+ `GET /portfolios/{id}/holdings`; **no entity, no migration, no write endpoint, no audit/lineage/DQ**). **No REQ status change.**

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (P1C-5 closeout; no code) — commit on explicit approval.

**NEXT — P1C-6 PLANNING ONLY (on explicit approval):** plan the **deterministic synthetic dataset** slice — a synthetic
reference seed pack + synthetic portfolio hierarchy + synthetic transactions / positions / valuations, built with **`uuid5`
deterministic IDs** + **fixed timestamps**, **no real client/vendor data**, shipped as a **labeled never-auto-run seed
module** (explicit invocation only). **Fences:** no real/sensitive data; no production auto-run seed; no market data
ingestion; no risk calculations; no exposure aggregation; no reporting/dashboard build; no P2+ work.
**Planning only — do NOT implement P1C-6.**

## Exact next prompt to run (when the user is ready for P1C-6 planning)
> "Begin P1C-6 planning only: deterministic synthetic dataset. Do not write application code; do not create migrations; do
> not implement. Produce the P1C-6 implementation plan (mirror p1c5_implementation_plan.md): a DETERMINISTIC synthetic
> dataset — a synthetic reference seed pack (currencies/calendars/instruments/legal entities), a synthetic portfolio
> hierarchy, and synthetic transactions / positions / valuations — built via the existing governed create paths, with
> `uuid5` deterministic IDs (fixed namespace) + FIXED timestamps (no host-clock/random dependence), shipped as a LABELED
> never-auto-run seed module (explicit invocation only; NEVER wired to a production post-migrate / auto-run path). Define:
> module placement + invocation contract, determinism strategy, the synthetic data shape per entity, tenant scoping,
> idempotency/re-run behavior, tests (determinism + idempotency + no-auto-run guard), acceptance, risks, open decisions,
> controls, doc updates, and an 8-lens UltraCode adversarial review. STRICT EXCLUSIONS: NO real/sensitive data, NO
> production auto-run seed, NO market data ingestion, NO risk calculations, NO exposure aggregation, NO reporting/dashboard
> build, NO real SSO, NO P2+ work. Do not commit until I approve."

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — closeout, plan, implementation, and commit are distinct approvals.
- **Do not start the P1C-6 build** until its plan is approved (P1C-6 PLANNING is the next step; plan / implement / commit
  are separate approvals). **No real/sensitive data, no production auto-run seed**; P2+ stays unplanned; P1B-5 stays
  conditional/deferred.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity + Instrument/identifier FR-bitemporal +
  Corporate-action symmetric-RLS + **Portfolio symmetric-RLS** + **Transaction symmetric-RLS + append-only** + **Position
  symmetric-RLS + FR-bitemporal** + **Valuation symmetric-RLS + FR-bitemporal** all shipped) + downgrade smoke, Documentation
  check, Secret scan. **P1C-5 (read-only holdings views) added NO new migration/RLS step** — the migration job's last domain
  step is still Valuation; that absence is the structural proof no table was persisted. (P1C-6 synthetic dataset is a seed
  module — also no new migration/RLS step unless it persists a new entity, which it must not.)
- `gh` CLI is **not installed** — query GitHub Actions via the REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done throughout P1B/P1C). CI runs warning-free on the Node-24 action majors.

## Stop conditions (halt and ask)
- Any request to start **P1C-6 planning** is fine **on explicit approval**; but do NOT pull in the **build**, or
  **real/sensitive data / a production auto-run seed / market-data ingestion / risk / exposure aggregation / reporting /
  dashboards**, ABAC enforcement, or any P2+ domain — separate, later, planned slices.
- Any request to start **P1B-5** (conditional/deferred) ahead of a bulk-loading driver.
- Any change to **`audit/service.py`** (frozen) or any new audit code / permission / role without the governed
  update (R-07).
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
