# Next Actions

> **As of 2026-06-22.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the two P1B-0 planning docs are **committed at `dbed93e`** (CI-green). Remaining uncommitted: the
`docs/project_memory/*` artifacts (pending their own commit approval — recommended message:
`Add durable project-memory artifacts for session recovery`, or `Update project-memory artifacts after P1B-0 commit`).

**1. Record the P1B-0 ratifications — planning/governance docs only, no code, ONLY on explicit approval.**
These are the gating prerequisites for P1B-1 (see `decision_summary.md` OD-P1B-A/C/E/F/J): **AD-013-R1** in
`11_decision_log/architecture_decision_log.md`; **REQ-SMR-005** + the CAP-2.5 re-partition + the ENT-001/ENT-007
annotations in `02_requirements/` and `04_data_model/`; (the `REFERENCE.*` audit category + entitlement
additions are minted inside the P1B-1 slice, not standalone).

**2. Plan P1B-1** (currency / calendar / rating_scale) via the UltraCode planning workflow → committed plan
doc — **on explicit approval**. The first reference-data slice and the first hybrid global+tenant RLS.

**3. Then, on explicit direction, implement P1B-1** — mint the REFERENCE audit category + new permissions in
this slice. **Do not begin implementation before the ratifications are recorded and the slice is approved.**

## Exact next prompt to run (when the user is ready to start P1B-1 implementation)
> "Begin P1B-1 implementation only: currency / calendar / rating_scale. Use the P1A rails. Implement the new
> `irp_shared.reference` package (web-framework-free), migration `0008`, the `currency`/`calendar`/`rating_scale`
> EV entities with hybrid global+tenant RLS (OD-P1B-C), the REFERENCE.* audit codes (OD-P1B-E), the new
> entitlement permissions (OD-P1B-F), origin lineage (OD-P1B-I), generic DQ, and endpoints. Do NOT build
> issuer/counterparty/instrument/corporate_action or any P1C/P2+ domain. Run the UltraCode multi-lens review,
> fix in-scope findings, run `make check`, and do not commit until I approve."

(Adjust per the committed `p1b_implementation_plan.md` P1B-1 section, which is the source of truth.)

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — plan, implementation, and commit are distinct approvals.
- **Do not start the next slice** until the user directs it.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check`
  drift + the per-rail RLS/append-only steps + downgrade smoke, Documentation check, Secret scan.
- `gh` CLI is **not installed** — query GitHub Actions via the REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as was done for the `0282359` fix).

## Stop conditions (halt and ask)
- Any request to start **P1B implementation** before the P1B-0 ratifications are recorded.
- Any request that pulls in **P1C/P2+** or a domain (portfolio/positions/valuations/market/risk/etc.).
- Any change to **`audit/service.py`** (frozen) or any new audit code / permission / role without the
  governed update (R-07).
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice);
  do not start new work.
- Missing or ambiguous approval → ask; do not assume.
