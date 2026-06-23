# Next Actions

> **As of 2026-06-23.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** P1B-1 reference data committed `6568cb1` (CI-green run #28). **DONE:** the P1B-2 implementation plan
committed `410cc7e` (CI-green run #29). **DONE:** P1B-2 implementation committed `32c7778` and **CI-green**
(run #31, 7-lens reviewed). P1B-2 (legal_entity core + issuer/counterparty 1:1 profiles; symmetric RLS;
proprietary-never-hybrid evidence; LEI partial-unique; hierarchy STRUCTURE + bounded ultimate-parent resolver)
is **CLOSED**.

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (docs-only; no code) — commit on explicit approval.

**NEXT — P1B-3 PLANNING ONLY (on explicit approval):** plan **P1B-3 = instrument (EV identity) +
`instrument_terms` (FR — the first real bitemporal usage) + `identifier_xref` (EV)** via the UltraCode planning
workflow → a committed plan doc. Deterministic single-result-or-`AmbiguousIdentifier` resolution (OD-P1B-G);
cross-vendor precedence deferred (OD-012 → P1C). **Do NOT implement P1B-3 — planning only — and do not start
until the plan is approved.**

## Exact next prompt to run (when the user is ready to start P1B-3 PLANNING)
> "Begin P1B-3 planning only: instrument + instrument_terms + identifier_xref. Do not write code, do not create
> migrations, do not implement. Reuse the P1A rails + the P1B-1/P1B-2 reference patterns (EV entities, the FR
> mixin for instrument_terms, per-tenant SYMMETRIC RLS — proprietary, NEVER hybrid; REFERENCE.* audit; MANUAL-
> source lineage; additive entitlements; tenant-filtered resolvers). Per OD-P1B-A: `instrument` = EV identity +
> `instrument_terms` = FR (FullReproducibleMixin — the FIRST real bitemporal usage; reconstructable as-of). Per
> OD-P1B-G: `identifier_xref` = EV with deterministic single-result-or-AmbiguousIdentifier resolution, partial-
> unique (tenant_id, scheme, value) WHERE valid_to IS NULL; cross-vendor precedence (OD-012) DEFERRED to P1C.
> `instrument`'s issuer FK targets the `issuer` PROFILE (not the bare legal_entity core). Run the UltraCode
> multi-lens planning workflow, write the plan doc (mirror the P1B-1/P1B-2 plan structure incl. a §21 kickoff),
> and do not commit until I approve. Return the plan summary."

(The committed `10_delivery_backlog/p1b_implementation_plan.md` P1B-3 section is the source of truth; produce a
`p1b3_implementation_plan.md`.)

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — plan, implementation, and commit are distinct approvals.
- **Do not start P1B-3 implementation** until its plan is approved. **P1B-3 planning is the next step, on approval.**

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check`
  drift + the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity symmetric-RLS shipped; the
  P1B-3 build adds an instrument/identifier RLS step incl. FR temporal coverage) + downgrade smoke, Documentation
  check, Secret scan.
- `gh` CLI is **not installed** — query GitHub Actions via the REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as was done for P1B-1/P1B-2).
- **FR note:** P1B-3 is the FIRST persisted FR/bitemporal usage — `instrument_terms` reconstruct-as-of queries
  need their own tests; apply the native-uuid trap to FR temporal SQL.

## Stop conditions (halt and ask)
- Any request to start **P1B-3 implementation** before its plan is approved.
- Any request to pull in **P1B-4/P1B-5**, **P1C/P2+**, or a domain (portfolio/positions/valuations/market/risk/
  reporting/SSO/etc.).
- Any change to **`audit/service.py`** (frozen) or any new audit code / permission / role without the governed
  update (R-07).
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice);
  do not start new work.
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
