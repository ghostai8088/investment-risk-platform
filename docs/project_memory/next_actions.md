# Next Actions

> **As of 2026-06-25.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the **P1B block** + **P1C-0** (AD-017) → **P1C-1 BUILD** (`bb89c74`, #43): `portfolio` EV hierarchy → **P1C-2 BUILD**
(`abb230f`, #46): `transaction` IA append-only → **P1C-3 BUILD** (`4ee124e`, #49): `position` FR — the **first FR domain
entity** → **P1C-3 memory** (`2f7d647`/`b38f182`, #50/#51) → **CI hygiene** (`67741fb`, #52: Actions → Node-24 majors;
Node-20 warning eliminated) → **P1C-4 plan** (`92a0264`, #53; OD-P1C4-1..6 signed off) → **P1C-4 BUILD** (`c5c5806`, CI-green
run #54; 8-lens reviewed, 0 block, 1 LOW folded): the `valuation` FR bitemporal captured mark history — the platform's
**second FR domain entity**. **REQ-PPM-003 is now Done** (both transaction + valuation conjuncts).

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (P1C-4 closeout; no code) — commit on explicit approval.

**NEXT — P1C-5 PLANNING ONLY (on explicit approval):** plan the **as-of holdings / portfolio views** slice — **read-only**
views composed from the captured `position` (+ optionally `valuation`) FR entities via their shipped `reconstruct_*_as_of`
reads, **no computation beyond safe reconstruction/composition**. **Fences:** NO exposure aggregation; NO market value rollup
(unless explicitly approved as **display-only from captured marks**); NO `dataset_snapshot`; no new persisted entity.
**Planning only — do NOT implement P1C-5.** Then P1C-6 synthetic dataset (separately planned + approved).

## Exact next prompt to run (when the user is ready for P1C-5 planning)
> "Begin P1C-5 planning only: as-of holdings / portfolio views (read-only). Do not write application code; do not create
> migrations; do not implement. Produce the P1C-5 implementation plan (mirror p1c4_implementation_plan.md): READ-ONLY as-of
> holdings/portfolio views composed from the captured `position` (+ optionally `valuation`) FR entities via their shipped
> `reconstruct_position_as_of` / `reconstruct_valuation_as_of` reads — NO new persisted entity, NO migration, NO computation
> beyond safe reconstruction/composition. Define: APIs (read-only view endpoints), entitlement (reuse position.view /
> valuation.view; no new write verb), RLS behavior (inherited tenant isolation on the underlying tables), lineage/audit
> (reads emit no governed-write events), tests, acceptance, risks, open decisions, controls, doc updates, and an 8-lens
> UltraCode adversarial review. STRICT EXCLUSIONS: NO exposure aggregation, NO market value rollup (unless explicitly
> approved as display-only from captured marks), NO dataset_snapshot, NO risk/pricing/valuation model, NO market-data
> ingestion, NO reporting/dashboards, NO P1C-6 (synthetic dataset) or P2+ work. Do not commit until I approve."

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — closeout, plan, implementation, and commit are distinct approvals.
- **Do not start the P1C-5 build** until its plan is approved (P1C-5 PLANNING is the next step; plan / implement / commit
  are separate approvals). **No exposure aggregation / no compute beyond safe reconstruction**; **P1C-6 (synthetic dataset)
  stays unplanned**; P2+ stays unplanned; P1B-5 stays conditional/deferred.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity + Instrument/identifier FR-bitemporal +
  Corporate-action symmetric-RLS + **Portfolio symmetric-RLS** + **Transaction symmetric-RLS + append-only** + **Position
  symmetric-RLS + FR-bitemporal** + **Valuation symmetric-RLS + FR-bitemporal** all shipped) + downgrade smoke, Documentation
  check, Secret scan. (P1C-5 as-of holdings views are read-only — likely no new migration/RLS step unless a new entity is persisted.)
- `gh` CLI is **not installed** — query GitHub Actions via the REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done throughout P1B/P1C). CI runs warning-free on the Node-24 action majors.

## Stop conditions (halt and ask)
- Any request to start **P1C-5 planning** is fine **on explicit approval**; but do NOT pull in the **build**, or
  **exposure aggregation / market value rollup (beyond display-only) / dataset_snapshot / risk / pricing / valuation model /
  market-data ingestion**, ABAC enforcement, the P1C-6 synthetic dataset, or any P2+ domain — separate, later, planned slices.
- Any request to start **P1B-5** (conditional/deferred) ahead of a bulk-loading driver.
- Any change to **`audit/service.py`** (frozen) or any new audit code / permission / role without the governed
  update (R-07).
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
