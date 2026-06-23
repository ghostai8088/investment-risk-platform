# Next Actions

> **As of 2026-06-25.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the **P1B block** (P1B-1 `6568cb1` / P1B-2 `32c7778` / P1B-3 `8545ed6` / P1B-4 `060b2a4`, all CI-green) →
**P1B closeout / P1C readiness** (`e99633a`) → **P1C-0 decision record + P1C implementation plan** (`705d3ba`) →
**P1C-1 portfolio-hierarchy implementation plan** (`b52ad9e`) → **P1C-0 RATIFICATION** (this turn: AD-017; REQ-PPM-001
In-Progress; `PORTFOLIO.*` reserved; OD-013 + OD-025 closed; `portfolio.*` grants; p1c0_decision_record → Ratified).

**COMMIT-PENDING:** this P1C-0 ratification (governance markdown/YAML + these memory files; no code) — commit on explicit approval.

**NEXT — P1C-1 BUILD (on explicit approval only):** implement the `portfolio` EV hierarchy + ABAC scope anchor per
`10_delivery_backlog/p1c1_implementation_plan.md` §20 kickoff prompt — migration `0012`, a new `irp_shared/portfolio/`
package, **activate** the now-RESERVED `PORTFOLIO.CREATE`/`.UPDATE`, grant `data_steward` `portfolio.view`+`portfolio.edit`,
bounded ancestor+descendant resolvers, symmetric RLS, **no ABAC enforcement** (anchor only). Then P1C-2 transactions →
P1C-3 positions → P1C-4 valuations → P1C-5 as-of views → P1C-6 synthetic dataset (each separately planned + approved).

## Exact next prompt to run (when the user is ready for the P1C-1 build)
> "Begin P1C-1 implementation only: the portfolio / fund / strategy / account hierarchy + ABAC scope anchor, per
> 10_delivery_backlog/p1c1_implementation_plan.md (§20 kickoff). Build the single `portfolio` EV table (migration 0012),
> the `irp_shared/portfolio/` package (models/events/service/binder + bounded ancestor & descendant resolvers), activate
> the RESERVED PORTFOLIO.CREATE/UPDATE caller-side (audit/service.py FROZEN), grant data_steward portfolio.view+edit,
> symmetric proprietary RLS, MANUAL-source lineage, generic DQ, the backend router, tests (logic/endpoint/PG incl. the
> anchor-not-enforce scope fence), the CI RLS step, and the in-slice governance doc updates. NO transactions/positions/
> valuations/holdings/aggregation/ABAC-enforcement/dataset_snapshot. UltraCode 8-lens review, then make check + PG validate.
> Do not commit until I approve. Return the implementation report."

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — closeout, plan, implementation, and commit are distinct approvals.
- **Do not start the P1C-1 build** until explicitly directed (its plan + the P1C-0 ratification are done; the build is a
  separate approval). P1C-2/3/4 and P2+ stay unplanned; P1B-5 stays conditional/deferred.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity + Instrument/identifier FR-bitemporal +
  **Corporate-action symmetric-RLS** all shipped; the P1C build adds positions/valuations RLS + FR-bitemporal
  steps) + downgrade smoke, Documentation check, Secret scan.
- `gh` CLI is **not installed** — query GitHub Actions via the REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done throughout P1B).

## Stop conditions (halt and ask)
- Any request to start the **P1C-1 build** is fine **on explicit approval** (plan + ratification done); but do NOT pull in
  **P1C-2/3/4** (transactions/positions/valuations), exposure aggregation, `dataset_snapshot`, ABAC enforcement, or any
  P2+ domain (market/risk/pricing/reporting/SSO) — those are separate, later, planned slices.
- Any request to start **P1B-5** (conditional/deferred) ahead of a bulk-loading driver.
- Any change to **`audit/service.py`** (frozen) or any new audit code / permission / role without the governed
  update (R-07).
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
