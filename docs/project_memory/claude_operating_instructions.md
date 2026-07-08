# Claude Operating Instructions

> **As of HEAD `f941d50` (amended 2026-07-06 for the Opus 4.8 → Fable 5 model change).** How Claude Code works
> on this project. Read with `current_state.md`, `next_actions.md`, and `decision_summary.md`. These encode the
> user's required cadence — follow them exactly. (`CLAUDE.md` at the repo root is the auto-loaded entry pointer.)

## Operating model (UltraCode)
Planning-first, per-slice, commit-only-on-approval:
- **Planning:** the plan/decision-record markdown is authored single-threaded, then adversarially reviewed
  (see below) and committed **on approval** before any coding.
- **Implementation:** done directly (single-threaded) to keep conventions consistent — NOT fanned out across
  agents writing files in parallel.
- **Adversarial review:** after implementing, the slice is reviewed through the review pattern below and the
  in-scope findings are folded before the commit gate.
- *(Tooling note: the legacy "Workflow tool" fan-out described in earlier revisions of this doc no longer
  exists in the current harness. Its replacements are below; references to "8-lens UltraCode review" in older
  slice docs map to this review pattern.)*

## Adversarial review pattern
- **The property that matters is CONTEXT INDEPENDENCE:** a review run inside the authoring context inherits the
  author's blind spots at any model capability level. Prefer, in descending order of independence:
  (1) **`/code-review ultra`** — the user-triggered multi-agent cloud review of the slice branch/diff (the model
  cannot launch it; the user runs it after implementation and the model folds the findings);
  (2) **explicitly authorized subagent passes** in fresh contexts — fewer, deeper lenses (typically 2–3:
  quant/correctness, security/controls/RLS, scope/consistency) rather than many shallow ones;
  (3) a **disciplined single-pass** in-session review — acceptable as the floor for planning documents, and it
  must be honestly labeled as single-pass, never dressed up as independent multi-agent review.
- **Implementation slices get (1) and/or (2). Planning slices may use (3).**
- Each review pass is **refute-by-default**: verify every material claim against the repo (symbols, signatures,
  constants, grains, permission sets, EVT decades, control mappings) — read, don't recall. **Ground reviewers**
  with verified facts (commit hashes, contracts, baselines).
- **Record findings and their dispositions (folded / refuted / deferred), not verdict tallies** — "N approve /
  M approve_with_changes" counts are only meaningful when the reviewers were genuinely independent contexts.
- Apply **only in-scope** findings; record deferred ones. Reviews routinely catch real errors (wrong temporal
  class vs AD-005, baseline conflicts, test-passes-for-wrong-reason, a 500→404 fail-closed bug). Treat "block"
  findings seriously and fix before committing.

## Verification & objectivity (standing rules)
- **No quantitative claim from model recall.** Every formula, convention, day-count, sign, tolerance, or
  financial-domain assertion in a methodology doc or kernel must trace to (a) an executed test whose reference
  values were computed INDEPENDENTLY of the implementation (hand-computed, or an independent library on
  synthetic data), or (b) a citation to an authoritative source — never to what the model "knows".
- **External ground truth over self-consistency.** A test whose expected values were derived from the
  implementation's own logic proves nothing about economic correctness (a consistently wrong convention passes
  its own tests). For estimation/simulation methods (P3-4 covariance onward), acceptance includes **dual-path
  verification**: property tests (e.g. PSD, symmetry), cross-checks against an independent implementation, and
  analytic-vs-simulation agreement within declared tolerance, plus seeded determinism (QS-18).
- **Capability is not evidence.** Verification gates (`make check`, full-PG validation, CI-watch-to-green,
  reproduction-under-correction tests) are NEVER waived because output looks authoritative or the model is
  more capable. Only executed verification counts.
- **Objectivity over agreement.** Lead assessments with the strongest objection; state block verdicts plainly;
  if the user's instruction conflicts with a ratified baseline OR a materially better alternative exists, say
  so BEFORE acting. Never soften findings to match the user's perceived preference.
- **No status decay (the 2026-07-06 retrospective-audit lesson).** An implementation slice's R-07 governance
  amendments MUST flip every planning-era status qualifier its plan introduced: before closing a slice, grep
  the five governance docs (canonical model / audit taxonomy / temporal standard / entitlement model / control
  matrix) for `PLANNED`, `NOT implemented`, `NOT minted`, `NOT activated`, `will pin`, `ratified-in-planning`
  naming that slice, and update each to the realized state (commit hash + CI run). See
  `10_delivery_backlog/retrospective_model_upgrade_audit.md` for the defect class this prevents.

## Gate tiers (approval algorithm — USER-RATIFIED 2026-07-06)
The tier is computed from the **objective footprint of the diff** (`git diff` paths + change class), NEVER from
the model's self-assessed confidence ("zero areas of concern" is not a criterion — the assessor is the author).
- **Tier 0 — no approval; proceed, commit, report after.** Read-only work (audits/reviews/analysis); docs-only
  changes that alter **status, not decisions** (project-memory refreshes; status-decay fixes with hash/CI
  evidence; cross-refs/typos); local tooling (containers/venv). Conditions: no code, no migration, no
  ratified-decision text touched; docs-check + secret-scan green.
- **Tier 1 — proceed and land; flag for async spot-check.** Test-only additions that pass; test-only fixes for
  a red CI on a just-committed slice; R-07 governance amendments that mechanically **record** an
  already-approved decision (incl. flipping a sign-off ledger to RATIFIED after explicit user approval).
  Conditions: fully covered by executable verification; trivially revertible; no new decision embedded.
- **Tier 2 — approval required BEFORE commit.** Any production/shared/API code change (even with green tests —
  tests prove consistency, not intent); any migration; any new permission / audit code / canonical id /
  component kind / vocab value; any edit to ratified-decision text, methodology docs, numerical conventions, or
  acceptance criteria; anything touching frozen files or the RLS/tenancy surface; **starting any new slice**
  (plan or implementation) — direction control is the user's.
- **Tier 3 — the explicit OQ sign-off ledger (unchanged).** Methodology/model choices, grains, entity mappings,
  scope narrowings.
- **Auto-escalation:** ANY failed check (make check / docs-check / secret-scan / PG / CI), or ANY file outside
  the declared tier footprint, promotes the change to Tier 2. **CI-watch-to-green is mandatory at every tier.**
  Changing THESE gate rules is itself Tier 2/3.

## Commit discipline
- **Commit/push per the gate tiers above** (Tier 0/1 land-and-report; Tier 2/3 explicit approval per artifact). Branch is `main`; pushes go to `origin/main`.
- **Per-commit pre-checks:** run `make check` (lint, format, mypy, pytest, secret-scan, docs-check); confirm
  the staged set is exactly the intended files; no generated artifacts / `node_modules` / `dist` / caches /
  `.pyc` / secrets / `.env` staged; the scope-specific exclusions hold.
- **Commit message trailer:** end with a `Co-Authored-By` trailer naming the **model that actually performed the
  work in that session** (e.g. `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`), so commit provenance stays
  accurate across model changes — never a stale hard-coded model name.
- After pushing: return the commit hash, confirm remote sync (0 ahead/0 behind), confirm CI triggered, and
  watch the relevant CI job to green (REST API; `gh` not installed). A red CI on the just-committed slice is
  fixed before moving on (test-only fixes allowed; reproduce PG-only failures with Docker `postgres:16`).

## Provenance & dates (standing rule)
- **Authoritative provenance = commit hashes, GitHub Actions run IDs, migration heads, and the `origin/main`
  HEAD.** Sequence and "what shipped when" are established from Git/GitHub metadata, never from the host
  calendar. When recording or ordering work, cite these — not a date.
- **Calendar `as_of` dates are informational only** unless explicitly derived from Git/GitHub metadata (a
  commit/CI timestamp). Treat the `as_of` field in the project-memory artifacts as best-effort labelling.
- **Host-clock drift is recorded ONCE in `uncertain_values` and not repeated.** Do NOT re-surface the
  host-clock-drift caveat in reports; raise the date-uncertainty point ONLY when: (1) a generated artifact
  materially depends on today's date; (2) there is a genuine conflict between commit/CI chronology and a
  calendar date; or (3) the user specifically asks about date accuracy. Otherwise stay silent on it — set the
  `as_of` date and move on.

## Local PG validation container (standing rule)
- PG validation uses a **single, stable, reused** local container named **`irp_pg_local`** (`postgres:16`;
  `irp:irp@localhost:5432/irp`) — **start-if-absent, reuse-if-present**. Do NOT create a fresh per-slice
  `irp_pg_pNN` name (the name churn is what made the cleanup note recur).
- The container is **ephemeral local tooling, not a deliverable**: a temporary local Postgres validation
  container may be **stopped after validation**, and torn down **silently** (`docker stop irp_pg_local`) as part
  of end-of-slice cleanup once CI is green. **Do NOT surface a recurring "container still running / please
  `docker stop …`" housekeeping note in reports** — it is noise the user has already actioned; re-emitting an
  already-resolved cleanup reminder is the exact anti-pattern this rule (and the dates rule above) forbid. Only
  mention the container if it is genuinely still running AND in the way of the user's next step.
- **Local container cleanup is NOT a repo/code change** — starting or stopping `irp_pg_local` touches nothing
  under version control. It does **not** affect CI, migrations, or the committed project state; it never needs a
  commit and is never reported as one.

## Scope-control rules
- **Planning-first, thin slices.** No domain functionality during foundation/skeleton/planning phases.
- **Do not start the next slice until directed.** Plan / implement / commit are separate approvals. WHAT comes next defaults to `10_delivery_backlog/delivery_roadmap.md` (no per-slice option menus); re-sequencing follows its Part 4 rules — on genuine ambiguity, ask the user WITH a recommendation.
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
- Migrations sequential (head `0021_benchmark`; **advanced from `0020_curves` at P2-6** (`b6284a4`) — persisting ENT-009 `benchmark` (EV definition) + `benchmark_constituent` (FR/bitemporal membership); NEITHER table append-only — no P0001 trigger; **the full P2 captured market-data foundation is complete**; the next migration lands when a **P3 risk entity is implemented**); `alembic check` is a drift gate
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
