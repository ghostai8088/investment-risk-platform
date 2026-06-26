# Claude Operating Instructions

> **As of 2026-06-26.** How Claude Code works on this project. Read with `current_state.md`, `next_actions.md`,
> and `decision_summary.md`. These encode the user's required cadence — follow them exactly.

## Operating model (UltraCode)
The project uses an **UltraCode multi-agent** model for planning and review:
- **Planning workflow:** before implementing a slice, run a multi-lens planning workflow (N parallel reviewer
  lenses → a synthesis agent producing the plan markdown). Commit the plan doc (on approval) before coding.
- **Implementation:** done directly (single-threaded) to keep conventions consistent — NOT fanned out across
  agents writing files in parallel.
- **Adversarial review:** after implementing, run a multi-lens review workflow (read-only) over the actual
  code/tests/docs; the agents return structured findings; reconcile (synthesize) into an in-scope fix list.
- Use the **Workflow** tool for these fan-outs. Workflows run in the background and notify on completion —
  do not poll aggressively; wait for the task-notification (a 0-byte output file means "not done", not "failed").
  If a synthesis agent fails (e.g. a transient limit), synthesize the reviewers' findings manually.

## Multi-agent review pattern
- Typical lenses: Product/Requirements, Chief Architect, Data Architecture, Security/RLS, Audit/Controls,
  Data Quality, Lineage, QA/Test, Scope (subset per slice).
- Each reviewer reads the artifact + verifies against the repo and returns: verdict, severity-tagged findings
  (with file/section + fix + in-scope flag), scope/fact issues, confirmations.
- **Ground the reviewers** with verified facts (commit hashes, contracts, baselines) so they reason against
  reality, not hallucinations. Apply **only in-scope** findings; record deferred ones.
- Reviews routinely catch real errors (e.g. wrong temporal class vs AD-005, baseline conflicts, test-passes-for-
  wrong-reason). Treat "block" verdicts seriously and fix before committing.

## Commit discipline
- **Commit/push ONLY on explicit user approval**, per artifact. Branch is `main`; pushes go to `origin/main`.
- **Per-commit pre-checks:** run `make check` (lint, format, mypy, pytest, secret-scan, docs-check); confirm
  the staged set is exactly the intended files; no generated artifacts / `node_modules` / `dist` / caches /
  `.pyc` / secrets / `.env` staged; the scope-specific exclusions hold.
- **Commit message trailer:** end with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- After pushing: return the commit hash, confirm remote sync (0 ahead/0 behind), confirm CI triggered, and
  watch the relevant CI job to green (REST API; `gh` not installed). A red CI on the just-committed slice is
  fixed before moving on (test-only fixes allowed; reproduce PG-only failures with Docker `postgres:16`).

## Scope-control rules
- **Planning-first, thin slices.** No domain functionality during foundation/skeleton/planning phases.
- **Do not start the next slice until directed.** Plan / implement / commit are separate approvals.
- **Genericity:** type/scheme/status columns are controlled-vocab **strings** (no enum/CHECK); polymorphic
  `(entity_type, entity_id)`, no domain FK — new families extend by value, never a migration.
- **No new audit code, permission, or role** without the governed update (R-07 owns the taxonomy/catalog).
- **Never modify `packages/shared-python/src/irp_shared/audit/service.py`** (frozen audit framework).
- **Honor the ratified baselines** (AD-005 temporal classes, AD-013 tenancy, the canonical model, the RTM).
  A deviation is a recorded ADR/requirement amendment, never a silent "confirm".

## Required return format after each implementation
Report, in order: (1) files created/updated; (2) DB/migration changes; (3) tests added; (4) CI impact;
(5) controls now executable; (6) UltraCode reviewer findings; (7) fixes applied after review; (8) known
placeholders; (9) whether the slice is complete; (10) confirmation `make check` passes; (11) confirmation no
excluded scope was added; (12) recommended commit message; (13) recommended next step. (Planning turns use the
analogous plan/decision return format the user specifies.) **Then hold for commit approval.**

## Engineering conventions (load-bearing)
- SQLAlchemy 2.0 (`Mapped`/`mapped_column`); `GUID` TypeDecorator (native uuid on PG, CHAR(36) on SQLite),
  surfaces as `str`. **psycopg3 native-uuid trap:** use ORM/`GUID` for inserts, `CAST(:x AS uuid)` for raw
  by-id mutations, `str()` for raw uuid reads.
- Temporal mixins EV/IA/FR; declare `__temporal_class__` (BR-19). IA append-only enforced by an ORM
  before_update/before_delete guard **and** the `irp_prevent_mutation()` P0001 DB trigger on tables in
  `APPEND_ONLY_TABLES`. IA-status-mutable records (CalculationRun, ingestion_batch) are deliberately NOT in
  `APPEND_ONLY_TABLES`.
- RLS: `set_config` (never parameterized `SET`); FORCE RLS + `USING` + explicit `WITH CHECK`; PG tests under
  the constrained `irp_app` role (grant UPDATE/DELETE on IA tables so append-only proves the **P0001 trigger**,
  not a 42501 privilege denial); **re-set tenant context after any commit before a read-back** (commit clears
  the transaction-local GUC — the `0282359` lesson).
- Migrations sequential (head `0016_dataset_snapshot`; **advanced from `0015_valuation` at P2-1** (`3629baa`) — the first migration since P1C-4, persisting ENT-049/050; the next migration lands when **P2-2 FX is implemented**); `alembic check` is a drift gate
  (`compare_type=False`); NAMING_CONVENTION `pk_/ix_/uq_/fk_`; register new models in `irp_shared.models`.
  Each new tenant table → add a CI RLS step. **Hybrid (AD-013-R1) tables** use the asymmetric loop
  (`USING own OR SYSTEM_TENANT` / `WITH CHECK own`) — the symmetric loop stays for proprietary/tenant-scoped
  tables; the SYSTEM literal must NEVER appear in `WITH CHECK`.
- FastAPI: `get_tenant_session` (sets context), `require_permission` (deny-by-default, module-level guard
  singletons to avoid B008), `uuid.UUID` path params (422 + indistinguishable 404), single end-of-request commit.

## Prohibited behavior
- Committing/pushing without explicit approval; starting the next slice unprompted.
- Writing application code during a planning/decision turn.
- Adding excluded/out-of-phase scope (domain entities, P1C/P2+, dashboards, reporting, real SSO, etc.).
- Modifying `audit/service.py`; minting audit codes/permissions/roles outside the governed process.
- Putting secrets in source (BR-10); staging artifacts/caches/env files.
- Reading/copying/printing/using a **credential file** (e.g. a stray GitHub PAT) found on disk — never inspect
  token contents; flag it for the user to revoke/rotate. (One was found in the parent dir and resolved on
  2026-06-22 — see `current_state.md` Housekeeping; git auth is now an SSH key.)
- Declaring a background workflow "dead" from weak signals — wait for the harness completion notification.
- Reporting success without verification (state failures with output; say when a step was skipped).
