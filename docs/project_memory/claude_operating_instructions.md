# Claude Operating Instructions

> **As of HEAD `f941d50` (amended 2026-07-06 for the Opus 4.8 → Fable 5 model change).** How Claude Code works
> on this project. Read with `current_state.md`, `next_actions.md`, and `decision_summary.md`. These encode the
> user's required cadence — follow them exactly. (`CLAUDE.md` at the repo root is the auto-loaded entry pointer.)

## Operating model (UltraCode)
> **Delivery autonomy (granted 2026-07-12).** Claude self-drives the plan → implement → review → commit →
> push cycle WITHOUT per-step / per-artifact approval. The user's control points are now (a) opening + merging
> every PR to `main` (branch protection; Claude never touches the token) and (b) genuine DECISIONS — the Tier-3
> OQ sign-off ledger, design forks, scope/sequencing changes. Where the text below says "approval required
> before commit," read it as "commit + push autonomously; the gate is the PR merge + any genuine decision." The
> other hard invariants are UNCHANGED (frozen `audit/service.py`; no BYPASSRLS / no new audit-permission-role
> outside the R-07 mint; verification gates never waived; adversarial review still runs before the push).

Planning-first, per-slice; Claude commits + pushes autonomously:
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
- **Standing review angle — fixture realism (TD-1, 2026-07-09):** every slice's review checks that new
  economic-value fixtures are economically plausible by default; deliberately extreme values are allowed ONLY in
  clearly-labeled boundary/adversarial tests (the three-bucket rule + per-domain bands live in
  `08_testing_qa/test_data_realism.md`).
- **Standing review angle — vacuous / bypassable controls (Wave-11 close, 2026-07-24):** for every governed
  gate/SoD/lifecycle control, ask two questions at design AND review time — (a) *can it pass VACUOUSLY?* (its
  precondition set is empty — MG-2's review-with-zero-1L-response; the empty-`var_run_ids` snapshot); (b) *can it
  be BYPASSED via an alternate lifecycle path or a co-submitted field?* (MG-3's suspend→edit→resume and the no-op
  `status=` alongside a governing edit). Both MG-2's and MG-3's sole HIGH were this class. A gate that fires only
  in the "obvious" state is not a control until the alternate paths are closed.
- **≥3-finder convergence = CONFIRMED-blocking (Wave-11 close, 2026-07-24):** when three or more independent
  finders converge on the SAME finding, treat it as CONFIRMED-blocking, not PLAUSIBLE — empirically the strongest
  real-HIGH signal (MG-3's change-gate bypass; PPF-3's consume-path double-count both surfaced this way). Do not
  discount it as duplicate noise.
- **Recommendation-before-verification (Wave-12 close, 2026-07-26, OQ-W12C-3a — STANDING, generalized to review
  folds):** any ratification-gate option OR shipped guard that is CHEAPLY TESTABLE must carry its EXECUTED test
  in the decision record before the gate — an audit run on the actually-proposed tree (the OQ-1=C downgrade was
  ratified before the gate ran on it), a reachability probe (the OPS-1 demo asserted SoD controls it could not
  reach), and for every shipped fence/pin/conformance gate its NEGATIVE CONTROL run against the actual
  bypass/failure form (the Wave-12 close's only two HIGHs were guards ratified as enforcing whose delivered form
  had never been shown to fire: the write fence missed the natural src-root import spelling; the refusal-detail
  pin's key assertion was a dead branch). "Verified with a probe" means the probe covered the ADVERSARIAL form,
  not a listed one. This generalizes OQ-W10C-5 from CI teeth to all guard code.
- **The conformance-pin pattern is the standing answer to hand-mirrored contracts (Wave-12 close, OQ-W12C-3b):**
  whenever one artifact hand-mirrors another (nginx prefixes ↔ vite proxy; PG suites ↔ ci.yml steps; a job's
  install list ↔ its suites' imports; FE refusal markers ↔ backend `_ERROR_MAP` details; an eslint fence ↔ its
  bypass forms), ship a machine pin with a negative control rather than relying on discipline. A gate that
  depends on remembering is not a gate.
- **Closeout control-matrix trace (Wave-12 close, OQ-W12C-3c):** every slice closeout either updates
  `09_compliance_controls/control_matrix_skeleton.md` or states "no control moved" in its decision record —
  the API-2/OPS-1 closeouts skipped the sweep silently and left the flagship SoD row (CTRL-021) stale.
- **Citation-verification lane for methodology slices (2026-07-30 — the rule-6a strengthening; see the
  amended roadmap Part 4 rule 6a for the binding text):** every regulatory/academic citation in a decision
  record enters ONLY as a verbatim quoted passage with a paragraph/page locator, and the pre-ratification
  verifier pass includes a lane that reads ONLY the cited source (never the draft's framing) and answers
  "does it say what the record claims?". The class this kills: RM-1's truncated GIPS quote would have
  refused compliant books; CON-1 v1 cited three regulatory texts for the OPPOSITE of what they say, and the
  ratified fix was itself refuted on the same class (para-87 adjacent-paragraph misread) — a confidently
  wrong citation launders a guess as authority, worse than no citation.
- **Demo-tick consequence (REPLACED the OQ-W12C-3d interim prohibition at OPS-H1, 2026-07-28):** the
  stage-14 clock is seed-time-relative (backdated two days; the curated walk preserved exactly), so
  enrolling `DEMO_TENANT_ID` in `IRP_TENANT_IDS` is now an OPERATOR CHOICE with a documented
  consequence, not a prohibition: the demo lifecycle RUNS — the overdue breach escalates on the first
  tick as governed, correct behavior — and re-seeding restores the pristine walk. Never present the
  old prohibition as current.

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
- **Tier 2 — commit + push + PR + merge autonomously (delivery autonomy 2026-07-12, EXTENDED 2026-07-14:
  "I will defer to you on when to create pull requests and merge").** Any production/shared/API code change;
  any migration; any new permission / audit code / canonical id / component kind / vocab value; any edit to
  ratified-decision text, methodology docs, numerical conventions, or acceptance criteria; anything touching
  frozen files or the RLS/tenancy surface. These proceed to commit + push on a feature branch, then Claude
  opens the PR and merges it to `main` — the merge preconditions replacing the human gate are the adversarial
  review folded + `make check` + full-PG + CI-to-green + branch protection's required checks (never merge
  before ALL pass). **Starting the next roadmap slice is autonomous** (the sequence is
  `delivery_roadmap.md`); a genuine RE-SEQUENCING, scope change, or design fork still surfaces to the user
  WITH a recommendation (a Tier-3 decision, below).
- **Tier 3 — the explicit OQ sign-off ledger (unchanged).** Methodology/model choices, grains, entity mappings,
  scope narrowings.
- **Auto-escalation:** ANY failed check (make check / docs-check / secret-scan / PG / CI), or ANY file outside
  the declared tier footprint, promotes the change to Tier 2. **CI-watch-to-green is mandatory at every tier.**
  Changing THESE gate rules is itself Tier 2/3.

## Commit discipline
- **Commit + push autonomously at every tier (delivery autonomy 2026-07-12; PR create + merge added
  2026-07-14).** No per-artifact pre-commit approval. Work lands on a **feature branch** pushed to `origin`;
  Claude opens the PR (GitHub REST API, keychain-cached credential — `gh` not installed) and merges it once
  the review is folded and `make check` + full-PG + CI + the branch-protection required checks are ALL green.
  Tier 3 genuine DECISIONS still get user sign-off before being encoded. CI-watch-to-green after each push
  stays mandatory.
- **Per-commit pre-checks:** run `make check` (lint, format, mypy, pytest, secret-scan, docs-check); confirm
  the staged set is exactly the intended files; no generated artifacts / `node_modules` / `dist` / caches /
  `.pyc` / secrets / `.env` staged; the scope-specific exclusions hold.
- **Both-tier verification before EVERY push (2026-07-30 — the `dbce327` lesson made standing):** a push is
  preceded by the full local gate battery for EVERY tier the diff touches — `make check` always; the full-PG
  battery (fresh schema, ALL configured testpaths) whenever the diff touches a migration, PG-tier code, or a
  demo stage; the FE checks whenever it touches the frontend. Never push on a partial signal: `dbce327` went
  red because `make check` ran BEFORE the tests that pin the migration head were written, and the first PG
  run that session covered one of three configured testpaths.
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
- **The next slice starts autonomously (delivery autonomy, 2026-07-12); WHAT comes next defaults to `10_delivery_backlog/delivery_roadmap.md`** (no per-slice option menus). Claude self-drives plan → implement → review → commit → push → PR → merge (the 2026-07-14 extension — see the Tier-2 gate above; this line previously said "leaves the PR for the user to merge", corrected at the Wave-4 close). A genuine re-sequencing (deviating from the roadmap order) or scope/design ambiguity still surfaces to the user WITH a recommendation before acting; re-sequencing follows the roadmap's Part 4 rules.
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
- **Governed-result read seam (AD-019, 2026-07-24):** a new **"latest/list governed number"** read goes through
  `calc/reads.py` (`list_governed_results`/`latest_run_rows`) + its typed wrappers (`latest_var_for_portfolio`,
  `latest_sensitivities`, …) — **never** an ad-hoc `select(<ResultModel>)…join(CalculationRun)` for latest-run
  selection scattered in a service/router. The second legit shape is a **by-run-id matrix read** (covariance
  `covariance_service.py`/`private_covariance_service.py`, joining CalculationRun only for the `run_type`
  self-defense filter) — keep those centralized in the result's own service, not scattered. This keeps the future
  analytical-plane read re-point (Snowflake, hybrid/additive) a handful-of-modules change. Bypassing = review reject.

## Design-completeness checklist (standing, 2026-07-12; MD-H1)
The judgment-gap bug class no mechanical guardrail catches — run these four questions at DESIGN time for
every new gate/input/scope, not just at review time (each line names the shipped incident it would have caught):
- **Every gate: both sides?** (one-sided TR-09; the horizon-blind Basel zone gate — P3-7/BT-1)
- **Every list/collection input: empty behavior defined and refused-or-handled?** (the empty `var_run_ids`
  snapshot — BT-1)
- **Every doc-stated scope or convention: enforced in code, not just documented?** (the CURRENCY-family
  proxy scope, doc-stated but ungated — PA-0)
- **Every failure path: no RUNNING orphan, whole-unit rollback?** (the NaN 500 + RUNNING orphan — BT-1)

## Closeout sweep (standing, Wave-11 close 2026-07-24)
Beyond stamping the decision record CLOSED (CI-enforced) + the roadmap/current_state sweep: at every slice
closeout, **sweep the downstream governance docs a control moved** — check `09_compliance_controls/control_matrix_skeleton.md`
for any CTRL row this slice took from *Planned/Designed* → *Operational* and update its Status cell. (Wave-11
miss: CTRL-021/CTRL-031 read "Planned" though MG-2/MG-3 shipped the person-level SoD + breach 1L/2L separation —
the same "downstream doc left stale after the code shipped" class as the closure-stamp recurrence.)

## The seven-ledger omission sweep + verify-on-main (standing, RATIFIED at the Wave-13 close 2026-07-29 as six, P1; SEVENTH ledger added 2026-07-30)
At EVERY slice closeout, sweep the seven ledgers where an omission leaves NO diff for a review to see:
(1) `04_data_model/canonical_data_model_standard.md` — new ENT ids have registry rows AND the "next free id"
pointer is right; (2) `04_data_model/audit_event_taxonomy.md` — minted vs reserved is accurate (or the
"deliberately minted nothing" sentence is updated); (3) `09_compliance_controls/control_matrix_skeleton.md` —
touch a control or state "no control moved" (OQ-W12C-3c); (4) `docs/project_memory/current_state.md` CURRENT
TRUTH; (5) `02_requirements/` backbone + RTM both halves; (6) counts — MEASURED on a fresh battery, never
derived; (7) **the record's OWN delivery claims (added 2026-07-30): every "shipped / enforced / delivered /
implemented" claim in the slice's decision and close records is verified against the MERGED diff and cited
to its artifact (file, test name, or commit) before close** — REF-1's merged, ratified record carried FIVE
false or undelivered claims (an unimplemented ratified write-freeze among them), found only because the
NEXT slice's recon happened to re-read it; a record written from plan memory measures intent. **THEN the
verify-on-main clause: it is a CLOSEOUT step, it runs AFTER THE LAST MERGE, and it covers
EVERY artifact the slice claims to have delivered — review folds included** (cheap form:
`git merge-base --is-ancestor <sha> origin/main`). Evidence class: RM-1's sweep commit was authored and never
merged; FE-M1's R-4 fold raced its own PR — a sweep run on the branch measures intent, only the main check
measures delivery.

## Shared-tree mutation rules (standing, RATIFIED at the Wave-13 close 2026-07-29, P2)
Whenever ANY agent may hold the tree (reviews, mutation batteries, parallel finders): **never `git add -A`** —
stage explicit paths; **grep the COMMIT, not the tree** for mutation markers before pushing
(`git grep -n "MUTATED" <rev> -- packages apps scripts`); **purge `__pycache__` and re-run every gate** after a
mutation battery (`PYTHONDONTWRITEBYTECODE=1`); finders mutate in ISOLATED copies; a green gate from a
contaminated tree is NOT evidence — re-run and report the re-run. (SR-1: a `git add -A` committed a live
finder mutation + a scratch file; a stale `.pyc` served a mutated constant through a full battery.)

## Register entries are claims about the code (standing, RATIFIED at the Wave-13 close 2026-07-29, P3)
At planning recon, any register/deferral/debt entry the slice stands on is VERIFIED against today's code, not
trusted — stale in either direction counts (an entry describing a fixed thing as open, or register silence on
a thing that exists). Three Wave-13 slices demonstrated the class (OPS-H1's H1-9, FE-M1's node:20/audit-gate
finds, SCH-2's holder-set comment).

## Executed dry runs for migration/dependency-floor slices (standing, RATIFIED at the Wave-13 close 2026-07-29, P4)
The pre-ratification verifier pass for a migration or dependency-floor slice RUNS the migration in a throwaway
workspace copy — reading, grep, and the upstream guide all missed both of FE-M1's blocking findings; ten
minutes of executing found them. **Binding clause (the audit's refutation of the pin half): every number a dry
run produces is a DATED point-in-time reading of a mutable registry and MUST be re-measured against the merged
artifact at closeout — never carried forward as a pin** (FE-M1's "exactly 12" lockfile delta was 22 entries at
merge and the human counting gate did not fire).

## Assert by evidence, not by absence (standing, RATIFIED at the Wave-13 close 2026-07-29, P5)
A test's positive result must be produced by the PROPERTY UNDER TEST: assert the call/render/row that proves
the path ran, not merely the absence of a wrong artifact — and any by-absence assertion carries a positive
control that fails when the mechanism breaks. The class shipped three times in one wave, in two languages
(FE-M1's R-4; the session-gate matcher in the same file; the pacing purpose test whose own comment conceded
the alternate path). A whole test TIER can be the alternate path (SQLite's column affinity vs the PG-only
`window_months` 500).

## Non-vacuity floors on enumerating guards (standing, RATIFIED at the Wave-13 close 2026-07-29, P6)
Any guard that works by ENUMERATION (a matcher over document shapes, a lint fence over import forms, a
discovery scan over modules) ships WITH a coverage floor that fails loudly when the guard's in-scope
population collapses — because a matcher covers only the shapes someone thought of, while a floor notices
coverage falling whatever the next shape is. Evidence: the closure-stamp gate was broadened three times and
went blind a fourth way (guarding 29 of 62 records, silently); the import fences are on their third
un-enumerated bypass axis. In-tree exemplars: the closure gate's two floors, the GS2 exact census, the
`_BINDING_PREDICATES`/`PURPOSE_*` set-equality censuses, `test_ci_pg_coverage.py`.

## Lessons are recorded as acts, not facts (standing, RATIFIED 2026-07-30, P7)
Every lesson or review fold lands in EXACTLY ONE of three declared forms, stated at the fold:
- **(a) a MECHANICAL GATE**, preferring — in measured order of durability — **exact set-equality census >
  coverage floor > enumerating matcher**, with its negative control executed against the adversarial form
  (OQ-W12C-3a). The 2026-07-30 error-trend audit (4-lane, over all 23 session logs + this document + the
  memory corpus) measured the hierarchy: the closure-stamp class recurred FIVE times AFTER mechanization,
  each at the matcher's enumeration boundary; the import fences were bypassed on three unenumerated axes;
  the fail-closed npm-audit gate was found fail-OPEN — while exact censuses have zero recorded recurrences.
- **(b) PROCEDURAL PROSE binding an EXECUTED act to a defined trigger moment** ("before X, run/do Y") — the
  prose form with zero recorded recurrences (P4's executed dry runs; downgrade-requires-re-audit; the
  read-the-mutation-memory-before-folding act that prevented a Wave-13-close recurrence).
- **(c) an EXPLICIT recurrence acceptance**, recorded with the reason the class cannot be (a) or (b).
**DECLARATIVE prose ("remember that X is true") is NOT a valid countermeasure form** — the audit found every
top recurring class (id-namespace collisions ×2 in one day, citation misreads across RM-1→CON-1,
schema-reset pollution, shell-quoting) was declarative-prose-only. Corollary: when a MECHANIZED class
recurs anyway, the fold widens the gate's enumeration AXIS or upgrades it up the (a)-hierarchy — never
just teaches the matcher the one missed shape (the closure gate's three broadenings each did the latter,
and each went blind a new way).

## Pre-flight manifests per change class (standing, RATIFIED 2026-07-30 — P7's companion; the `dbce327` class)
Before DRAFTING a change, enumerate what its change class touches — a lookup, not a CI discovery. Every
newly discovered pin/fence is ADDED to this manifest in the fold that found it (a pin discovered downstream
of drafting is a manifest gap to fix in the same fold). Seeded 2026-07-30 from the error-trend audit:
- **New migration:** the migration-head pin population (`grep -rn` the current head id across
  `packages/*/tests` + `apps/*/tests` — ~21 assertions at REF-1); `test_synthetic.py`'s next-free-slot
  glob; the closed-set fences (HYBRID_TABLES declaration==union(migrations) parity, `APPEND_ONLY_TABLES`
  membership decision, `FAMILY_REGISTRY`/`ck_schedule_model_version_by_family` CHECK); every DDL
  identifier ≤ 63 chars named explicitly in BOTH ORM and migration (`test_migration_identifiers.py`);
  `alembic check` drift; the per-table CI RLS step; the downgrade smoke; guarded audit `ACTION_*`
  constants (raw string literals are rejected by a shipped guard).
- **New governed number family:** COMPONENT_KIND + registry/CHECK migration; model registration +
  validation; snapshot+run+model binding; rule-7 entity/time reads + FE in-slice; demo stage + the
  final-position count-pin relay; PG-tier pins on non-String filters; the seven-ledger sweep (P1).
- **New permission/role:** the R-07 mint; per-code SoD pins (the 3L auditor exclusion is PER CODE — a
  single view code across tenancy classes re-commits REF-1's SoD defect); control-matrix row;
  `entitlement_sod_model.md`.
- **New entity:** ENT next-free id (CHECK THE NAMESPACE — collisions hit twice in one day at REF-1);
  canonical-model registry row; `__temporal_class__` declaration; CI RLS step; six/seven-ledger sweep.
- **New demo stage:** the stage-ordering filename (`ls` the tests dir, never a record); the count-pin
  relay to final position; schema reset BEFORE each full-PG run; superuser-bypasses-RLS scoping (never
  "everything in the table"); the already-seeded double-run path.
- **A module importing a package it did not import before (ADDED at PERF-0, which found this the
  expensive way — a red CI run):** there are TWO independent fence layers and they are in different
  files. (1) The importing package's OWN import-direction test (e.g. `test_synthetic.py::
  test_import_direction`, and the `test_*_import_direction` siblings — ~23 fences repo-wide, one per
  package). (2) The imported package's REPO-WIDE leaf fence, which lives in the IMPORTED package's
  test file, not the importer's — `test_fx_rate.py::test_nothing_imports_marketdata`,
  `test_snapshot.py::test_nothing_imports_snapshot`. Amending only the first leaves the second red.
  Enumerate BOTH before drafting: `grep -rn "def test_nothing_imports\|import_direction" */tests`.
  Amend in place WITH the rationale at the fence; check for an existing exemption whose reasoning
  already covers the new case (`synthetic` rode `demo`'s: orchestrator seed tooling that drives real
  capture services and that nothing imports).
- **Dependency/toolchain change:** the P4 executed dry run; the audit gate re-run on the ACTUAL proposed
  tree; dry-run numbers re-measured at closeout, never carried as pins.

## The governed-binder conformance census (standing, RATIFIED at the Wave-14 close 2026-08-02, P8)
One test enumerates every module registering a governed family and asserts, **by exact set equality**, that
each calls `assert_model_version_of` — or is on an explicitly declared exception list carrying a written
reason (`exposure/service.py` is model-less by design). Evidence: LQ-1's BLOCKING — the 24th family was the
only one of twenty-four missing the call, and no gate noticed for a full slice PLUS a close review.
**A per-family convention with 23 correct instances and one wrong one is precisely what a census is for**;
23 correct instances are also exactly what makes the 24th invisible to reading. In-tree: the census lives in
`test_model_registry.py` with a `len(binders) > 20` floor (P6), so the population collapsing fails loudly.

## A refusal is not shipped until a test has made it FIRE (standing, RATIFIED at the Wave-14 close 2026-08-02, P9)
**Mechanical limb:** a census asserting that every declared refusal constant, and every custom `*Error`
raised in a governed binder or snapshot builder, is named in at least one test that asserts it FIRES.
**Procedural limb, bound to the fold moment:** *a fold is not folded until its own negative control has been
executed against the pre-fold code and shown to fail.* Evidence: LQ-1 shipped four `LiquiditySnapshotError`
refusals plus `GAP_STALE_TIERS` and `GAP_CORRUPT_PINNED_CONTENT` with **zero test references** anywhere; the
project had already shipped a structurally UNFIREABLE refusal at CON-1. **LQ-1 wrote this rule itself, in
its own Part 10, and its own slice violated it six times over** — which is why it is a census and not a
sentence. Corollary, and the reason "the refusal exists in the source" is never evidence: a refusal that
cannot fire and a refusal that never fires are indistinguishable from the diff.

## A fold applies to the CLASS, not the site (standing, RATIFIED at the Wave-14 close 2026-08-02, P10)
When a review fold repairs a defect at a call site, its **closing step** greps the symbol, enumerates every
sibling site, and records **per site**: fixed, or not-fixed-because. The fold's record sentence may quantify
over **only the sites it enumerated**. Evidence: PERF-0 F2 fixed 2 of 6 — and the erratum's own segment was
one of the four omitted; CAL-1b's unconsumed pin fixed 1 of 2 binders; LQ-1 B1 fixed the parse and left the
consumer untested. In-tree exemplar: `holiday_binding.assert_boundaries_covered`, which exists because the
CAL-1b coverage check was carried inline and identically by two binders and the fold moved the pair to one
site so a third consumer inherits both sides rather than re-forgetting one.

## A permission mint needs its holder-set pin, route census, and SoD row (standing, RATIFIED at the Wave-14 close 2026-08-02, P11)
Best form is data-driven: a declared expected holder map in `test_entitlement_bootstrap.py` compared by
**exact set equality**, so a newly minted code with no pin fails by construction; plus one platform-wide
route→code census walking every router mounted in `main.py`. Evidence: LQ-1's two codes were
mutation-proven blind in BOTH directions, with no route census and no `entitlement_sod_model.md` row, one
slice after CON-1 pinned all three of its own; and four pre-existing unrouted codes nobody had ever counted.
**Implementation warning (measured, not theorised):** a naive `app.routes` walk yields `_IncludedRouter`
wrappers with no `.methods` and produces a **green census over zero routes** — one such vacuous instance
already exists at `test_schedules_endpoint.py:346`. Recurse through `original_router.routes`, or build from
`app.openapi()`.

## Execute the plainest alternative client before recording an impossibility (standing, RATIFIED at the Wave-14 close 2026-08-02, P12)
No governed record may state that a resource is unreachable, a check is impossible, or a residual must be
carried for environmental reasons, **until the plainest alternative has been executed and its output
pasted**. A tool's refusal is evidence about the tool. Evidence: DATA-1's TB3MS residual — a user-facing
standing residual in the control matrix, resting on a single WebFetch 403, discharged by `curl` in under
three minutes with all 30 literals exact against the publisher of record. Re-executed at the Wave-14 close
fold: the archived NYSE 2023 calendar, likewise reached by plain `curl` after the live page proved useless.

## Kills are reserved for factual refutation (standing, drafted 2026-08-02, RATIFIED at the Wave-15 planning gate 2026-08-04, P13)
In an adversarial review, a finding may be killed only by a **factual refutation** — a demonstration that
the claim is untrue of the code as it stands. An **executed, uncontradicted reproduction may not be killed
on severity votes**: if the reproduction stands and only its importance is disputed, the finding is
DOWNGRADED with the dispute recorded, never discarded. *Grounded:* the Wave-14 close's 2-of-3 refutation
rule overturned 14 of 17 close calls on re-adjudication — about 53% of kills wrong at fold-relevant
severity, comparable to Wave 13's 3-of-6. The failure mode is specific: a majority of judges finding a real
defect *unimportant* reads identically, in the tally, to a majority finding it *unreal*. **RATIFIED at the
Wave-15 planning gate (OQ-W15P-8, 2026-08-04). This header stayed "PROPOSED" for three days after
ratification — caught at the Wave-16 planning fold, the same stale-row class as the Part-6 P14 note.**

## A gate is not green until its exit code is quoted (standing, RATIFIED 2026-08-05, P14)
**Procedural prose, bound to the moment of writing any completion or status claim.** No message may state
that a gate passed unless it quotes that gate's **captured exit code from a log written in the same
session**; no message may state that CI is green unless it quotes the **run conclusion for the branch head
SHA**. Pipes are not permitted in the capture path — a truncating pipe drops the summary AND masks the exit
code (already recorded at DATA-1, and it recurred). *Grounded:* the third recurrence in a single wave of *a
gate reported green having never been run*. At LQ-1 two gates were reported green unrun; at the Wave-14
close fold the branch was reported "both tiers green" while **all six pushes were red in CI from fold 1** —
`ruff format` sits ahead of lint, mypy and pytest in the Backend job, so a cosmetic failure silently made
four gates non-executing, and running `make check` honestly then surfaced two further failures that had
been invisible behind it. The available tell was ignored: a Backend job finishing in 31 seconds cannot have
run 2,400 tests. **RATIFIED 2026-08-05 by the user.** Deliberately NOT self-ratified when drafted:
a rule whose whole purpose is to constrain how the builder reports its own work is not one the
builder should enact for itself — that is structurally the same move as a control that verifies its
own existence, the defect class this rule exists to prevent. **Corollary now binding: an
implausibly fast gate is itself a signal.** A job that finishes far too quickly for the work it
claims has not done the work; read WHICH STEP failed before diagnosing, because everything after a
failing step never ran at all.

## Two proofs sharing an assumption count as one proof (standing, RATIFIED 2026-08-07, P15)
When a claim matters, at least one proof must be constructed under **different assumptions** than the
implementation — a different engine, a different process, a different author, or a fresh context.
Redundant evidence is not independent evidence: adding more proofs helps only if they do not share the
assumption that is wrong. *Grounded, twice in one wave:* RPT-1's blocking B1 (`portfolio_code` unpinned)
was invisible to BOTH its proof tiers because the unit test and the deployed restore proof each re-supplied
the same constant — no quantity of additional testing of either kind could have found it; and the SQLite
FK gap (115 tests writing dangling foreign keys, all green) was every suite sharing the assumption that
the parent existed, found only when PostgreSQL — a different engine — refused. Application is judgement,
not ceremony: the per-slice fresh-context audit and the full-PG battery both already satisfy this for
their domains; the rule exists so that a NEW claim's evidence plan is checked for shared assumptions
before the evidence is trusted, not after an audit finds the blind spot. **RATIFIED 2026-08-07 by the
user ("proceed" on the Wave-15 close review §5-E, wording as proposed in §3). Deliberately not
self-enacted when drafted:** proposed at the close review as an explicit ratification item, on the P14
precedent that an evidence-sufficiency rule for the builder's own claims should not be enacted by the
builder on its own authority.

## A control-status citation is re-verified against the branch tip before the PR (standing, drafted 2026-08-07, RATIFIED 2026-08-08, P16)
A control matrix row that moves a control to *Implemented* or *Operational* on OBSERVED evidence cites a
CI run. **The last act before opening or updating the PR is to run
`git diff --name-only <cited-sha>..HEAD` and confirm it names NO production file** — no source, no
migration, no proof harness; records only. Not "is the cited SHA an ancestor of the tip", which it always
will be, and which is why the weak check never fires. If anything else appears, the proof re-runs on the
new head and the citation moves, in **every** document that carries it (a citation is typically repeated
across the slice record, the control matrix, the canonical entity row and the roadmap — REPRO-1's was in
four).

*The check is a diff, not an equality, and the first draft of this rule got that wrong.* "The cited run's
head SHA equals the branch tip" is unsatisfiable by construction: the commit that WRITES the citation
moves the tip, so the rule would fail on its own act. The property that actually matters is that no code
the cited step exercises has changed since the evidence was produced — which a records-only diff
establishes and an equality test cannot. Caught by trying to apply the rule rather than by re-reading it,
which is the same lesson as everything else in this slice.

*Grounded, twice in one slice, one generation apart.* CTRL-018 first cited a run whose alarm arm was
satisfied by a no-recipient sentinel and whose trigger arm counted `pg_trigger` rows that exist for
DISABLED triggers — both arms incapable of failing, as the builder's own commit message had already
recorded. The fold that corrected it then cited a run that two further folds left 486 lines behind,
across every module the cited step exercises. The second occurrence is the reason this is a rule: the
first was a mistake, the second was the same mistake made by the correction, which means reading the row
carefully is not the control. **The trigger moment is what makes it mechanical** — not "keep citations
fresh", which is the bare-instruction shape P7 forbids, but a named check at a named moment with a
named comparison.

**RATIFIED 2026-08-08 by the user (AskUserQuestion, "Ratify as written"), after the rule had been
corrected on first use and had then fired correctly at its trigger moment on four consecutive
re-citations.** Like P14 and P15, it constrains how the builder evidences its own claims, so it was
proposed rather than self-enacted; it was followed as practice from the moment it was drafted.

## A permission is not MINTED until a migration delivers it to running databases (standing, RATIFIED 2026-08-08, P17)
Permissions live in a Python constant (`entitlement/bootstrap.py`) that seeds a **new** database. A
database already running never sees a newly-added code. So **appending to that constant is not a
mint** — it is a mint for future deployments only, and deny-by-default then 403s every holder in
production while every from-empty test passes. That was true of every permission minted between P0.5
and RPT-2's migration `0064`, across many waves, and nothing caught it: the defect is invisible to
exactly the tests a new permission ships with.

**The mechanical gate (this is the rule, not the prose):** a test asserts that every code in the
bootstrap constant is also named by some migration. It fires on the next mint, by construction,
whether or not anyone remembers this paragraph.

**And the sync must not resurrect revoked grants.** A catalog-sync migration cannot distinguish
"never delivered" from "deliberately revoked by an administrator", so a naive sync silently restores
an entitlement someone removed on purpose — turning a governance action into a transient one. The
sync consults a revocation record, or at minimum logs and skips previously-revoked grants.
Ratifying the sync without this would institutionalise the resurrection, which is why the two
clauses are one rule.

**RATIFIED 2026-08-08 by the user at the Wave-16 close gate (option A + the revocation fix),** on
the close review's finding that ratifying the sync alone "institutionalises that behaviour" and is
"the difference between deny-by-default with governed mints being true and being aspirational".

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
