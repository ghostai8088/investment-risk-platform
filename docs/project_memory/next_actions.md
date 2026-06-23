# Next Actions

> **As of 2026-06-22.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** P1B-1 reference-data implementation committed `6568cb1` and **CI-green** (run #28). **DONE:** the
**P1B-2 implementation PLAN** committed `410cc7e` and **CI-green** (run #29), 7-lens UltraCode reviewed/hardened.

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (docs-only; no code) — commit on explicit approval.

**NEXT — P1B-2 IMPLEMENTATION (on explicit approval ONLY):** build **P1B-2 = legal_entity core + issuer /
counterparty role profiles** per `10_delivery_backlog/p1b2_implementation_plan.md`. The plan's **§21 is the
paste-ready kickoff prompt** (source of truth). **Do NOT start until explicitly directed.**

## Exact next prompt to run (when the user is ready to start P1B-2 IMPLEMENTATION)
Use the **§21 kickoff prompt in `10_delivery_backlog/p1b2_implementation_plan.md`** verbatim. In brief it directs:
> "Begin P1B-2 implementation only: legal_entity core + issuer / counterparty role profiles. Implement per the
> committed plan — extend `irp_shared.reference` (LegalEntity/Issuer/Counterparty EV models + binders + the
> explicitly-tenant-filtered resolvers + a bounded cycle-safe resolve_ultimate_parent, NO exposure math),
> migration **0009** with the **SYMMETRIC** RLS loop (NEVER hybrid/SYSTEM_TENANT, no append-only), reuse
> REFERENCE.CREATE/UPDATE (own event per entity; audit/service.py FROZEN), additive `reference.legal_entity.*`
> perms (matching the issuer/counterparty recipient set — excludes auditor_3l), `api/reference_entities.py`
> endpoints, MANUAL-source lineage, the full test matrix (incl. valid-core-first CREATE + UPDATE fail-closed,
> symmetric-RLS PG + positive policy assertion + closed-hybrid-set unchanged), and the in-slice doc updates.
> Run the UltraCode multi-lens review, fix in-scope findings, `make check` + the new legal-entity RLS PG step,
> and do not commit until I approve."

**Hard exclusions (the P1B-2 fences):** no instrument/instrument_terms/identifier_xref/corporate_action; no
ratings assignments; no netting/CSA/collateral/exposure column; no exposure-rollup CALCULATION (structure
only); no hybrid/SYSTEM_TENANT; no ingestion; no P1B-3/4/5.

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — plan, implementation, and commit are distinct approvals.
- **Do not start P1B-2 implementation** until the user directs it (the plan is committed; the BUILD is not approved).

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check`
  drift + the per-rail/per-entity RLS steps (Reference hybrid-RLS shipped; the P1B-2 build adds a legal-entity
  symmetric-RLS step) + downgrade smoke, Documentation check, Secret scan.
- `gh` CLI is **not installed** — query GitHub Actions via the REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as was done for P1B-1).

## Stop conditions (halt and ask)
- Any request to start **P1B-2 implementation** before it is explicitly approved.
- Any request to pull in **P1B-3/P1B-4/P1B-5**, **P1C/P2+**, or a domain (portfolio/positions/valuations/market/
  risk/reporting/SSO/etc.).
- Any change to **`audit/service.py`** (frozen) or any new audit code / permission / role without the governed
  update (R-07).
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice);
  do not start new work.
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
