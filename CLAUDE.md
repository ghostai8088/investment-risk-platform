# investment-risk-platform — Claude entry pointer

Full-scope enterprise investment-risk platform (multi-tenant, auditable, reproducible, governed — NOT an MVP).
This file is the auto-loaded pointer; the discipline lives in the documents below. **Read them before acting.**

## Read in this order
1. `docs/project_memory/claude_operating_instructions.md` — the cadence, review pattern, verification &
   objectivity standing rules, commit discipline, engineering conventions, prohibited behavior.
2. `docs/project_memory/current_state.md` — the entry-point snapshot (re-verify HEAD/CI at session start).
3. `docs/project_memory/phase_status.md` — the per-phase ledger.
4. `docs/project_memory/next_actions.md` — the next gated step + exact prompts.
5. The latest resume anchor under `10_delivery_backlog/` (currently `p3_2_closeout_p3_3_readiness.md`).

## Hard invariants (non-negotiable)
- **Commit/push ONLY on explicit user approval, per artifact.** Planning-first; plan / implement / commit are
  separate approvals. Do not start the next slice until directed.
- **`packages/shared-python/src/irp_shared/audit/service.py` is FROZEN** — never modify it.
- **No BYPASSRLS app path; no hybrid/SYSTEM_TENANT behavior** beyond the closed 5-table hybrid set; proprietary
  data = symmetric FORCE RLS.
- **No new audit code, permission, or role** outside the governed R-07 mint; no secrets in source (BR-10).
- **Verification gates are never waived** (`make check`, full-PG validation, CI-watch-to-green, reproduction
  tests) — model confidence is not evidence; see the standing rules in `claude_operating_instructions.md`.
- Governed derived numbers bind `dataset_snapshot` + `calculation_run` + a registered `model_version` (where a
  model applies) and are IA append-only; captured inputs bind none of those. Pick the pattern correctly.

## Environment quick facts
- The git repo is THIS directory (on this machine it sits nested under
  `~/Projects/investment_risk_platform/`); branch `main`; origin is SSH.
- `gh` is NOT installed — query CI via the public GitHub REST API.
- Local PG validation uses the single reused container `irp_pg_local` (`postgres:16`); see the standing rule in
  the operating instructions. Reset the schema between full pytest runs against the same DB.
