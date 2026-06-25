# Next Actions

> **As of 2026-06-24.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the **P1B block** (P1B-1…P1B-4, all CI-green) → **P1B closeout / P1C readiness** (`e99633a`) → **P1C-0 decision
record + P1C implementation plan** (`705d3ba`) → **P1C-1 plan** (`b52ad9e`) → **P1C-0 ratification** (`dca7bc0`: AD-017;
REQ-PPM-001 In-Progress; PORTFOLIO.* reserved; OD-013/OD-025 closed) → **P1C-1 BUILD** (`bb89c74`, CI-green run #43): the
`portfolio` EV hierarchy + ABAC scope anchor — the platform's **first domain entity** → **P1C-1 memory refresh** (`d1d6829`)
→ **P1C-2 plan** (`c398215`, run #45) → **P1C-2 BUILD** (`abb230f`, CI-green run #46; 8-lens reviewed, 0 block, 2 LOW
folded): the `transaction` IA append-only capture log — the platform's **first domain IA / append-only entity**.

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (P1C-2 closeout; no code) — commit on explicit approval.

**NEXT — P1C-3 PLANNING ONLY (on explicit approval):** plan the `position` slice (ENT-011, **FR bitemporal**) — positions
are **captured directly** (reuse the P1B-3 `instrument_terms` FR protocol: `FullReproducibleMixin`, effective-dated
supersede + as-known correction, both-axes reconstruction), **NOT derived from transactions**. **Fences:** NO derivation
from transactions, NO market value calculation, NO exposure aggregation. **Planning only — do NOT implement P1C-3.** Then
P1C-4 valuations (FR) → P1C-5 as-of holdings views → P1C-6 synthetic dataset (each separately planned + approved).

## Exact next prompt to run (when the user is ready for P1C-3 planning)
> "Begin P1C-3 planning only: position (ENT-011, FR bitemporal). Do not write application code; do not create
> migrations; do not implement. Produce the P1C-3 implementation plan (mirror p1c2_implementation_plan.md): the
> `position` FR entity (reuse the instrument_terms FR protocol — FullReproducibleMixin, effective-dated supersede +
> as-known correction, both-axes as-of reconstruction; NOT append-only), captured DIRECTLY and keyed to portfolio +
> instrument (cross-tenant fail-closed at the service layer), POSITION.* audit family (EVT-170 corridor; R-07
> reservation), position permissions, symmetric RLS, MANUAL-source lineage, the 22-section structure, and an 8-lens
> UltraCode adversarial review. STRICT EXCLUSIONS: captured directly — NO derivation from transactions, NO market value
> calculation, NO exposure aggregation, NO dataset_snapshot, NO risk/pricing/market-data/valuation. Do not commit until I approve."

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — closeout, plan, implementation, and commit are distinct approvals.
- **Do not start the P1C-3 build** until its plan is approved (P1C-3 PLANNING is the next step; plan / implement / commit
  are separate approvals). **No derivation from transactions** (positions are captured directly); P1C-4/5/6 and P2+
  stay unplanned; P1B-5 stays conditional/deferred.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity + Instrument/identifier FR-bitemporal +
  Corporate-action symmetric-RLS + **Portfolio symmetric-RLS** + **Transaction symmetric-RLS + append-only** all shipped;
  the P1C-3 build adds a position RLS + **FR-bitemporal** step) + downgrade smoke, Documentation check, Secret scan.
- `gh` CLI is **not installed** — query GitHub Actions via the REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done throughout P1B/P1C).

## Stop conditions (halt and ask)
- Any request to start **P1C-3 planning** is fine **on explicit approval**; but do NOT pull in the **build**, or
  **derivation from transactions / valuations / holdings / market values**, exposure aggregation, `dataset_snapshot`, ABAC
  enforcement, or any P2+ domain (market/risk/pricing/reporting/SSO) — those are separate, later, planned slices.
- Any request to start **P1B-5** (conditional/deferred) ahead of a bulk-loading driver.
- Any change to **`audit/service.py`** (frozen) or any new audit code / permission / role without the governed
  update (R-07).
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
