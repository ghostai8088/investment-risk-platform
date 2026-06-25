# Next Actions

> **As of 2026-06-25.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the **P1B block** (P1B-1…P1B-4, all CI-green) → **P1C-0** (`705d3ba` + ratification `dca7bc0`: AD-017) → **P1C-1
BUILD** (`bb89c74`, run #43): `portfolio` EV hierarchy + ABAC scope anchor — the **first domain entity** → **P1C-1 memory**
(`d1d6829`) → **P1C-2 plan** (`c398215`, #45) → **P1C-2 BUILD** (`abb230f`, run #46): the `transaction` IA append-only log —
the **first domain IA entity** → **P1C-2 memory** (`f3fd7c9`, #47) → **P1C-3 plan** (`42cc02c`, #48; OD-P1C3-1..5 signed off)
→ **P1C-3 BUILD** (`4ee124e`, CI-green run #49; 8-lens reviewed, 0 block, 1 LOW folded): the `position` FR bitemporal
captured holdings master — the platform's **first FR domain entity**.

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (P1C-3 closeout; no code) — commit on explicit approval.

**NEXT — P1C-4 PLANNING ONLY (on explicit approval):** plan the `valuation` slice (ENT-013, **FR bitemporal**) — valuations
are **captured marks** (reuse the same `position`/`instrument_terms` FR protocol: `FullReproducibleMixin`, effective-dated
supersede + as-known correction, both-axes reconstruction), **NOT computed by a valuation model**. **Fences:** NO valuation
model, NO price lookup, NO market value rollup, NO exposure aggregation. **Planning only — do NOT implement P1C-4.** Then
P1C-5 as-of holdings views → P1C-6 synthetic dataset (each separately planned + approved).

## Exact next prompt to run (when the user is ready for P1C-4 planning)
> "Begin P1C-4 planning only: valuation (ENT-013, FR bitemporal). Do not write application code; do not create
> migrations; do not implement. Produce the P1C-4 implementation plan (mirror p1c3_implementation_plan.md): the
> `valuation` FR entity (reuse the position/instrument_terms FR protocol — FullReproducibleMixin, effective-dated supersede
> + as-known correction, both-axes as-of reconstruction; NOT append-only), captured MARKS (a captured value-as-of + source
> label per portfolio + instrument + valuation_date, OD-P1C-F) keyed to portfolio + instrument (cross-tenant fail-closed at
> the service layer), VALUATION.* audit family (EVT-180 corridor; R-07 reservation), valuation permissions, symmetric RLS,
> MANUAL-source lineage, the 24-section structure, and an 8-lens UltraCode adversarial review. STRICT EXCLUSIONS: captured
> marks — NO valuation model, NO price lookup, NO market-data ingestion, NO market value rollup, NO exposure aggregation,
> NO dataset_snapshot, NO risk/pricing model. Do not commit until I approve."

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — closeout, plan, implementation, and commit are distinct approvals.
- **Do not start the P1C-4 build** until its plan is approved (P1C-4 PLANNING is the next step; plan / implement / commit
  are separate approvals). **No valuation model / no price lookup** (valuations are captured marks); P1C-5/6 and P2+
  stay unplanned; P1B-5 stays conditional/deferred.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity + Instrument/identifier FR-bitemporal +
  Corporate-action symmetric-RLS + **Portfolio symmetric-RLS** + **Transaction symmetric-RLS + append-only** + **Position
  symmetric-RLS + FR-bitemporal** all shipped; the P1C-4 build adds a valuation RLS + **FR-bitemporal** step) + downgrade
  smoke, Documentation check, Secret scan.
- `gh` CLI is **not installed** — query GitHub Actions via the REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done throughout P1B/P1C).

## Stop conditions (halt and ask)
- Any request to start **P1C-4 planning** is fine **on explicit approval**; but do NOT pull in the **build**, or
  **a valuation model / price lookup / market values / market-data ingestion**, market value rollup, exposure aggregation,
  `dataset_snapshot`, ABAC enforcement, or any P2+ domain (market/risk/pricing/reporting/SSO) — separate, later, planned slices.
- Any request to start **P1B-5** (conditional/deferred) ahead of a bulk-loading driver.
- Any change to **`audit/service.py`** (frozen) or any new audit code / permission / role without the governed
  update (R-07).
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
