# Next Actions

> **As of 2026-06-25.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the entire **P1B Security-Master & Reference-Data block** — P1B-1 (`6568cb1`), P1B-2 (`32c7778`),
P1B-3 (`8545ed6`), P1B-4 (`060b2a4`) — all CLOSED and CI-green. P1B-4 (`corporate_action`, EV capture-only;
status lifecycle + `REFERENCE.STATUS_CHANGE`/EVT-143) was implemented `060b2a4`, **CI-green (run #37)**, 8-lens
reviewed.

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (docs-only; no code) — commit on explicit approval.

**NEXT — P1B CLOSEOUT / P1C READINESS review, then P1C PLANNING ONLY (on explicit approval):** produce a P1B
closeout / P1C readiness doc (the rails + reference-entity inventory a P1C plan reuses — mirroring
`10_delivery_backlog/p1a_closeout_p1b_readiness.md`), then plan **P1C** (portfolio / positions / valuations —
the first **domain-analytics** slice; AD-005: positions/valuations are **FR** bitemporal). **P1B-5** (reference-
data ingestion mapping) stays **conditional/deferred**. **Do NOT implement P1C — planning only — and do not
start until the closeout/readiness review + P1C plan are approved.**

## Exact next prompt to run (when the user is ready for the P1B closeout / P1C readiness review)
> "Do the P1B closeout / P1C readiness review only. Do not write code, do not create migrations, do not
> implement. Produce a closeout doc (mirror 10_delivery_backlog/p1a_closeout_p1b_readiness.md): inventory the
> reusable rails + reference entities (tenant-context/RLS, audit+hash-chain, entitlements, data_source, lineage,
> model registry, data quality, ingestion staging, the EV/IA/FR temporal mixins, REFERENCE.* incl.
> CREATE/UPDATE/CORRECTION/STATUS_CHANGE, the symmetric + asymmetric RLS loops, currency/calendar/rating/
> legal_entity/issuer/counterparty/instrument/instrument_terms/identifier_xref/corporate_action); confirm the
> P1B requirements status (REQ-SMR-001..005 In-Progress with their deferrals); enumerate the P1C entities and
> open decisions (OD-012 precedence, OD-015 netting/CSA, exposure-rollup calc, positions/valuations FR). Do not
> commit until I approve. Return the closeout summary." — THEN, separately: "Begin P1C planning only."

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — closeout, plan, implementation, and commit are distinct approvals.
- **Do not start P1C implementation** until its plan is approved. The P1B closeout / P1C readiness review is the
  next step, on approval; P1B-5 stays conditional/deferred.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity + Instrument/identifier FR-bitemporal +
  **Corporate-action symmetric-RLS** all shipped; the P1C build adds positions/valuations RLS + FR-bitemporal
  steps) + downgrade smoke, Documentation check, Secret scan.
- `gh` CLI is **not installed** — query GitHub Actions via the REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done throughout P1B).

## Stop conditions (halt and ask)
- Any request to start **P1C implementation** before the closeout/readiness review + P1C plan are approved.
- Any request to start **P1B-5** (conditional/deferred), or to pull in a domain (positions/valuations/market/
  risk/exposure/reporting/SSO/etc.) ahead of its planned slice.
- Any change to **`audit/service.py`** (frozen) or any new audit code / permission / role without the governed
  update (R-07).
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
