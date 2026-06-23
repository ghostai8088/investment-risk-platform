# Next Actions

> **As of 2026-06-24.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** P1B-1 reference data `6568cb1` (run #28). **DONE:** P1B-2 (legal_entity/issuer/counterparty) `32c7778`
(run #31). **DONE:** P1B-3 plan `43c042e`; **DONE:** P1B-3 implementation `8545ed6` and **CI-green** (run #34,
8-lens reviewed). P1B-3 (instrument EV + `instrument_terms` **FR** — the platform's first real bitemporal entity
— + `identifier_xref` EV; deterministic identifier resolution; EVT-142 `REFERENCE.CORRECTION` activated) is
**CLOSED**.

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (docs-only; no code) — commit on explicit approval.

**NEXT — P1B-4 PLANNING ONLY (on explicit approval):** plan **P1B-4 = `corporate_action` (EV, effective-dated
reference data)** via the UltraCode planning workflow → a committed plan doc. The corporate_action **reference
entity only** (effective-dated declarations) — **NO** application to positions, **NO** valuation/position
adjustment, **NO** event-processing engine, **NO** day-count/roll math. **Do NOT implement P1B-4 — planning only
— and do not start until the plan is approved.**

## Exact next prompt to run (when the user is ready to start P1B-4 PLANNING)
> "Begin P1B-4 planning only: corporate_action. Do not write code, do not create migrations, do not implement.
> Reuse the P1A rails + the P1B-1/P1B-2/P1B-3 reference patterns (EV entity, per-tenant SYMMETRIC RLS —
> proprietary, NEVER hybrid; REFERENCE.* audit; MANUAL-source lineage; additive entitlements; tenant-filtered
> resolvers with the explicit tenant predicate). Per OD-P1B-B: `corporate_action` = EV effective-dated reference
> data — the reference ENTITY only. STRICT EXCLUSIONS: no application of corporate actions to positions; no
> valuation/position adjustment; no event-processing/lifecycle engine; no day-count/roll math (QS-10/11 → P1C);
> no portfolio/positions/valuations/market/pricing/risk/exposure/reporting/SSO; no P1C/P2+. Run the UltraCode
> multi-lens planning workflow, write the plan doc (mirror the P1B-2/P1B-3 plan structure incl. a paste-ready
> kickoff), and do not commit until I approve. Return the plan summary."

(The committed `10_delivery_backlog/p1b_implementation_plan.md` P1B-4 section is the source of truth; produce a
`p1b4_implementation_plan.md`.)

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — plan, implementation, and commit are distinct approvals.
- **Do not start P1B-4 implementation** until its plan is approved. **P1B-4 planning is the next step, on approval.**

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity symmetric-RLS + Instrument/identifier
  symmetric-RLS & FR-bitemporal shipped; the P1B-4 build adds a corporate_action RLS step) + downgrade smoke,
  Documentation check, Secret scan.
- `gh` CLI is **not installed** — query GitHub Actions via the REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done for P1B-1/P1B-2/P1B-3).

## Stop conditions (halt and ask)
- Any request to start **P1B-4 implementation** before its plan is approved.
- Any request to apply corporate actions to positions / adjust valuations / build an event-processing engine, or
  to pull in **P1B-5**, **P1C/P2+**, or a domain (portfolio/positions/valuations/market/risk/reporting/SSO/etc.).
- Any change to **`audit/service.py`** (frozen) or any new audit code / permission / role without the governed
  update (R-07).
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice);
  do not start new work.
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
