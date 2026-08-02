# Session Log: 02-08-2026 12:20 - cal1b-closed-data1-ratified-implemented-review-folded

## Quick Reference (for AI scanning)

**Confidence keywords:** CAL-1b close, PR #162, PR #163, DATA-1, PR #164, ENT-070,
`benchmark_rate`, migration 0060, `RULE_TYPE_COMPLETENESS`, TB3MS, H.15, Board of Governors,
FRED, capture-first, yield-vs-return, savepoint semantics, dangling savepoint, severity
downgrade, CTRL-034 Execution 2, item-3 amendment, demo stage 22, 13-z suite, count pin
26/43/139, P1 seven-ledger sweep, P2 shared-tree mutation hazard, autonomous merge, workflows,
adversarial review, verifier fold

**Projects:** investment-risk-platform (Wave 14: CAL-1b close → DATA-1)

**Outcome:** CAL-1 fully closed (PRs #162/#163 merged, both merged-main CI runs observed green);
DATA-1 planned on a six-lane recon, verifier-folded (28 findings), user-ratified (OQ-1…12),
planning merged (PR #164), and implemented in three commits with a four-lane adversarial review
whose 24 findings — including two defects proven by execution — were all folded. The battery
re-run came back **RED (1 failed / 2,949 passed)** on ONE test — the review fold's own new PG
correction test, which committed and then read in the same session where `set_tenant_context` is
transaction-local (the documented MD-H1 trap); fixed to verify in a fresh session, that suite
re-run green (6/6), and the clean fresh-schema battery then came back **GREEN: 2,950 passed / 0
failed, `PYTEST_EXIT=0`** — the evidence of record. DATA-1 is gate-complete but UNCOMMITTED (the
review fold) and UNPUSHED at session end.

## Decisions Made

- **DATA-1 = CAPTURE-FIRST (OQ-DATA-1-1a, ratified).** The ratified candidate was "a T-bill
  monthly YIELD series", but the rf leg admits vendor-published RETURNS only (ENT-052's
  twice-ratified never-derive constraint, REQ-PRF-004, SR-1's registered assumption), and no
  public-domain publisher publishes a monthly T-bill RETURN series (return series are commercial
  index products, barred by the no-vendor-contract rule). Decision: capture the yield VERBATIM on
  a new entity; the yield→period-return registered model + Sharpe re-source becomes a NAMED CARRY
  (trigger: the first governed consumer binding the real rf series). Rejected: re-scaling at
  capture into `benchmark_return` (never-derive violation with paperwork) and switching to a
  published return series (none exists public-domain).
- **Per-tenant tenancy for a PUBLIC-DOMAIN dataset (OQ-2).** CTRL-034 item 3 said open/public ⇒
  SYSTEM rows, but that arm presumes a hybrid-capable reference table; the hybrid set is CLOSED at
  7 vocabularies and the MARKET audit family has no SYSTEM chain. Decision: per-tenant capture, no
  AD-013-R3 — plus an **H-05-approved clarifying amendment to item 3** so future onboardings don't
  re-litigate it.
- **`RULE_TYPE_COMPLETENESS` minted as the fourth generic evaluator (OQ-4),** with the expected key
  set carried LITERALLY in the persisted rule's params — REF-1's ratified trigger wording honored
  verbatim. No migration (the `rule_type` column is an unconstrained String(50)).
- **The P3-8 trading-calendar wiring re-defers IN FULL, a third time, as an EXPLICIT ratified
  decision (OQ-5),** trigger = the first captured DAILY benchmark series; REQ-PRF-002 recorded
  RE-POINTED, not discharged. The record states the divergence from the roadmap pointer's literal
  text rather than blending half-delivery into a claim.
- **ENT-070 `benchmark_rate` minted** as the third series-observation table under the ENT-009
  benchmark header, with `quote_basis` IN the logical key (the ~15bp discount-vs-investment gap is
  a real same-date collision) and `observation_convention` ON the row — which PAYS OQ-CAL-1-9's
  capture-time convention-field option by design.
- **CTRL-034 Operational stamp DEFERRED to the observed close** (review fold reverted an
  implementation-time stamp): a status is a claim about observed operation.
- **The first full-PG battery was declared VOID as evidence** (P2 shared-tree rule) because the
  review's mutation lane was live in the same tree; the battery was re-run on a purged quiescent
  tree instead of arguing timing.

## Key Learnings

- **A refusal computed after `begin_nested()` leaves a DANGLING savepoint.** The
  `series_start`-precedes-horizon check raised from outside the try/except that owned the
  savepoint, so a catch-and-commit caller persisted the refused batch UNGATED — rows, horizon and
  head event — with completeness never having run, refuting the verb's own "fail-closed before any
  surviving write" contract. Lesson: every refusal whose inputs are known pre-savepoint must FIRE
  pre-savepoint; and the negative control must be HOSTILE (catch, then commit anyway).
- **Never delegate a verb's refusal contract to a MUTABLE rule attribute.** `severity` is in the DQ
  rule's `_UPDATABLE` set; a WARNING downgrade made `run_quality_check` return WARN without
  raising, so the refresh returned a fabricated SUCCESS dict over rolled-back data. The raise must
  be the verb's own, severity-independent.
- **Committed FAIL evidence × an ANY-FAIL-forever gate latches permanently.** `assert_passed_
  quality_checks` scans the whole append-only history, so one committed completeness FAIL blocks
  the target forever, even after full remediation. Two ratified mechanisms can be individually
  right and jointly wrong.
- **A census that pins only endpoints is transposition-blind.** Interior values of a hand-encoded
  dataset rest entirely on provenance — and "THREE independent extraction passes" was an
  overstatement when all three shared one render-proxy channel (common-mode failure). Independence
  is about the CHANNEL, not the count.
- **Never overlap a mutation-testing lane with a gate battery on the same tree** (P2, sharpened):
  a live mutant was observed in `dq/rules.py` while the battery ran. The battery's verdict becomes
  unusable regardless of how it turns out.
- **Two guards fired on exactly what they guard** — the DQ registry set-equality census (three
  suites) and `test_ci_pg_coverage` (the new PG suite had no CI step). Guards that fire on
  legitimate new work are still working guards.
- **A capture-only series must still be readable.** The draft claimed "the existing benchmark read
  surface serves it" — false, the router reads levels/returns by name. A write-only field is a
  disclosure gap (SCH-2 lesson) and leaves CTRL-034 item 1 with no consuming read to cite.
- The `_SeriesSpec` generic core absorbed a THIRD series table with zero copied protocol code —
  the ENT-052 parameterization paid off exactly as designed.

## Solutions & Fixes

- **Dangling savepoint:** compute `params`/`_expected_months` BEFORE `session.begin_nested()`;
  `test_horizon_before_series_start_refuses_with_NOTHING_persisted` catches the refusal, commits
  the session anyway, and asserts zero rows / horizon None / zero audit events.
- **Severity downgrade:** after `run_quality_check`, `if not evaluation.passed: raise
  BenchmarkSeriesValueError(...)` — the backstop that makes the refusal severity-independent;
  `test_severity_downgrade_cannot_fabricate_success` executes `update_dq_rule(severity="WARNING")`
  and proves the refusal plus the unwind.
- **Tenant-scoped → head-scoped rule:** `completeness_rule_code_for(benchmark)` returns
  `benchmark_rate.monthly_completeness.<uuid>` (fits `code` String(150)); consumers switched to
  the helper (unit) or a `LIKE prefix.%` match (PG/13-z).
- **Missing endpoint tests:** three tests appended to
  `apps/backend/tests/test_benchmark_series_endpoints.py` — 403 without `marketdata.view`, 404 for
  an unknown/foreign benchmark, and a happy path asserting `rate_value == "0.036600000000"` (the
  persisted canonical NUMERIC form as a STRING).
- **PG audit-unwind pins:** the savepoint twin now asserts zero `MARKET.BENCHMARK_RATE_CREATE` and
  zero `REFERENCE.UPDATE` for the tenant after a FAIL.
- **Correction verb on PG:** `test_correction_verb_on_the_authoritative_engine` in a test tenant
  (fabricating a correction on the REAL series in the demo tenant would violate test-data realism
  — the narrowing from the ratified demo content is recorded).
- **Observation-convention mismatch:** the refresh's add-only diff now refuses a captured date
  re-supplied under a different `observation_convention` instead of absorbing it silently.
- **P4 dry run, non-vacuous:** staged a real `benchmark` + `benchmark_rate` row, downgraded (table
  and column dropped with data present), re-upgraded, and verified FORCE RLS + the policy + the
  partial-unique index were rebuilt.
- **Battery log gotcha:** the pytest summary line was absent from the redirected log; the pass
  count was derived from the progress dots (2,943 dots, zero F/E) with `PYTEST_EXIT=0` as the
  authoritative signal.

## Files Modified

Created:

- `packages/shared-python/src/irp_shared/marketdata/benchmark_rates.py`: the ENT-070 rail —
  `_RATE_SPEC` over the shared `_SeriesSpec` core, capture/supersede/correct/reconstruct/list, and
  `refresh_benchmark_rates` (add-only, forward-only horizon, one-series-per-head, effective-only
  completeness, savepoint FAIL semantics, severity-independent refusal, head-scoped rule code).
- `packages/shared-python/src/irp_shared/marketdata/tb3ms_rates.py`: 30 hand-encoded TB3MS
  literals 2024-01..2026-06 + `TB3MS_SERIES_START` + `TB3MS_COMPLETE_THROUGH`, with the honest
  provenance block (two full passes + one sampled, all via one proxy channel).
- `migrations/versions/0060_benchmark_rate.py`: the ENT-070 table (0029 pattern verbatim) +
  `benchmark.rates_complete_through`.
- `packages/shared-python/src/irp_shared/demo/data1_stage22.py`: the live capture stage.
- `packages/shared-python/tests/test_benchmark_rates.py`: 20 unit tests incl. the census with four
  interior anchors and every refresh arm + the fold's hostile controls.
- `packages/shared-python/tests/test_benchmark_rates_pg.py`: RLS by table name, forged-tenant
  denial, FORCE-RLS/policy catalog assertions, the savepoint twin with audit pins, the correction
  exercise.
- `packages/shared-python/tests/test_demo_stage9zzzzzzzzzzzzz_data1_pg.py`: the 13-z suite (the
  FINAL-POSITION relay; the no-derived-return negative pin).
- `10_delivery_backlog/data_1_decision_record.md`: Parts 0–8 (49 grounding facts, the collision
  analysis, OQ-1…12, the verifier fold, the ratification record, the implementation log, the
  review fold).

Edited:

- `packages/shared-python/src/irp_shared/marketdata/models.py`: `BenchmarkRate` + the rate
  vocabularies + the coherence map + `Benchmark.rates_complete_through`.
- `packages/shared-python/src/irp_shared/dq/rules.py`: `RULE_TYPE_COMPLETENESS` +
  `evaluate_completeness` (both-directions set equality) + the registry.
- `packages/shared-python/src/irp_shared/dq/service.py`, `dq/__init__.py`: the two stale
  "a future P1A-4 ingestion calls" docstrings corrected.
- `apps/backend/src/irp_backend/api/marketdata.py`: `GET /benchmarks/{id}/rates` + `BenchmarkRateOut`.
- `apps/frontend/openapi.json`, `apps/frontend/src/api/generated/api-types.d.ts`: regenerated.
- `.github/workflows/ci.yml`: the stage-22 step + the benchmark-rate PG suite step.
- Registers: `04_data_model/canonical_data_model_standard.md` (ENT-070 row, next-free → ENT-071),
  `04_data_model/audit_event_taxonomy.md` (the `MARKET.BENCHMARK_RATE_*` R-07 activation),
  `09_compliance_controls/vendor_onboarding_diligence_checklist.md` (Execution 2 + the item-3
  amendment + the Execution-1 stale-citation re-point), `09_compliance_controls/control_matrix_skeleton.md`
  (CTRL-034 evidence; Operational deferred to close), `02_requirements/requirements_backbone.md` +
  `requirements_traceability_matrix.md` (REQ-DQR-001 four evaluators; REQ-PRF-002 re-pointed),
  `docs/project_memory/current_state.md`, `10_delivery_backlog/delivery_roadmap.md`.
- 21 test files: migration head pins relayed `0059` → `0060`; `test_synthetic.py` glob → `0061`;
  three suites' DQ registry census pins → the four-member set; the 12-z suite demoted to POSITIONAL.

## Setup & Config

- Local PG: container `irp_pg_local` (up 2 weeks, `0.0.0.0:5432`). Schema reset =
  `DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO irp; GRANT
  USAGE ON SCHEMA public TO PUBLIC;` then `alembic upgrade head`.
- Battery invocation (post-fold, hardened): `PYTHONDONTWRITEBYTECODE=1 DATABASE_URL=... IRP_TEST_DATABASE_URL=...
  pytest -p no:cacheprovider > <log> 2>&1; echo PYTEST_EXIT=$?` — plain log, no pipe.
- `gh` at `~/.local/bin/gh`; the allowlist in `.claude/settings.json` covers `gh pr create|merge|
  view|checks|list`, `gh run list|view|watch`. Note: invoking `~/.local/bin/gh` by absolute path is
  BLOCKED by the classifier — use bare `gh`.
- FE gates: `make gen-api` (regenerate openapi.json + api-types.d.ts), `npm run -w apps/frontend
  typecheck`, `npm run -w apps/frontend test` (207 tests).
- Migration head at session end: `0060_benchmark_rate`. Next free canonical id: ENT-071.

## Pending Tasks

- **The full-PG battery must be OBSERVED GREEN before the push.** Run 2 (the fold's first
  battery) came back **RED: 1 failed / 2,949 passed** — `test_benchmark_rates_pg.py::
  test_correction_verb_on_the_authoritative_engine`, a test added BY the review fold. Cause: it
  committed and then read in the SAME session, but `set_tenant_context` is TRANSACTION-LOCAL and
  auto-clears at COMMIT, so RLS correctly returned zero rows (`NoResultFound`). Fixed to verify in
  a FRESH session (which also proves durability); that suite re-ran 6/6 green against live PG, and
  **run 3 (fresh schema, purged, quiescent) came back GREEN: 2,950 passed / 0 failed,
  `PYTEST_EXIT=0`** — the observed evidence of record. Remaining: commit the review fold
  (uncommitted at session end), push `data-1`, open the PR, `gh pr checks --watch`,
  `gh pr merge --merge`, the P1 seven-ledger verify-on-main sweep, merged-main CI watch.
- **CLOSE-GATE ITEM FOR THE USER:** the ratified "independent hand re-verification of all 30 TB3MS
  literals" is UNDISCHARGED — all three extraction passes shared one render-proxy channel. Needs
  an independent channel (the Board's H.15 archive/DDP) or a human pass before the close stamps.
- **CTRL-034 Implemented → Operational** stamps at the close, after the battery is observed.
- Closeout: the roadmap close row, current_state final truth, memory files
  (`data-1-planning-state.md` NEW, `delivery-roadmap-state.md`, `MEMORY.md`).
- Named carries recorded: the yield→period-return model + Sharpe re-source (trigger: first
  governed consumer of the real rf series); the P3-8 trading-calendar wiring (trigger: first
  captured DAILY benchmark series).
- NEXT SLICE after DATA-1: **LQ-1**.
- Open anomaly (unchanged, never reproduced): `test_limit_registry::
  test_only_concentration_is_dimensional_and_basis_bearing`.

## Errors & Workarounds

- **Battery run 2 RED on the fold's own new test** — `test_correction_verb_on_the_authoritative_
  engine` committed then read in the same session; `set_tenant_context` is transaction-local and
  auto-clears at COMMIT, so the post-commit read saw zero rows under RLS (`NoResultFound`). This
  is the trap `persistent_tenant_context`'s own docstring documents ("the MD-H1 annex-4 incident:
  a PG test read 0 rows post-commit because the re-arm was forgotten"). Fixed by verifying in a
  fresh session — stronger, since it also proves the correction is durable. **The CAL-1b lesson
  repeated exactly: a fold is not folded until its own control passes on the real engine.**
- **First full-PG battery VOIDED** — the review's quant lane was mutation-testing in the shared
  working tree (`MUTANT A`/`MUTANT B` markers observed live in `dq/rules.py`). Workaround: verified
  the tree reverted (`git status` clean, zero mutation markers in tree and diff), purged
  `__pycache__`, re-ran the battery with `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`.
- **Six-lane recon workflow lost two lanes** to "Connection closed mid-response". Workaround:
  `Workflow({scriptPath, resumeFromRunId})` — the four finished lanes replayed from cache and only
  the two failed lanes re-ran.
- **`~/.local/bin/gh` blocked by the permission classifier**; bare `gh` (allowlisted) worked.
- **FRED direct fetch returns 403** to this environment; the Board's DDP CSV was also unreachable
  anonymously. Workaround: `r.jina.ai` render proxy — recorded as the acquisition path and as a
  common-mode residual in the provenance.
- **Merged-main CI watch died on a network reset** mid-Pytest (`connection reset by peer`);
  re-watched and confirmed `success`.
- **Battery log had no pytest summary line** (redirect + warnings summary swallowed it). Workaround:
  derive counts from the progress dots and trust `PYTEST_EXIT`.
- **`DataQualityResult` has no `created_at`** — a fold test ordered by it and failed; switched to
  filtering `outcome == "FAIL"` and asserting the singleton.
- **mypy on `**kwargs` dicts:** `dict[str, object]` splatted into a typed signature failed; replaced
  the shared-kwargs dict with a local closure in the demo stage.

## Key Exchanges

- **"What is still running?"** → Nothing was; the prior battery had finished (2,909/0) before the
  session log was written. Answered plainly and resumed the CAL-1b ship sequence.
- **"Is it running?" / "Is it still working in the background?"** → Reported honest live state from
  the transcript directory: five recon lanes finished ~09:32–09:34, one still active at 09:51.
- **"Proceed" at the DATA-1 gate** → ratified OQ-DATA-1-1…12 as recommended, including the entity
  mint, the audit-triple R-07 act, the H-05 licensing position, and the explicit third deferral.
- **Model switched to `claude-opus-5[1m]` at session end**, immediately before `/compress`.

## Custom Notes

None

---

## Quick Resume Context

CAL-1 is fully closed (PRs #162/#163, both merged-main CI runs observed green) and DATA-1 —
the first genuinely external dataset — is planned, ratified (PR #164 merged), implemented in three
commits on branch `data-1`, and review-folded (24 findings, all folded, two defects proven by
execution). The review fold is UNCOMMITTED and the branch is UNPUSHED. Battery run 2 came back RED on one
test — the fold's own new PG correction test (post-commit read under a transaction-local tenant
GUC); it is fixed and its suite re-ran 6/6 green, and a clean fresh-schema full battery was
launched at session end and came back **GREEN (2,950 passed / 0 failed)**. All gates are now
satisfied — `make check`, the P4 non-vacuous dry run, FE typecheck + 207 FE tests, and the clean
full-PG battery. The immediate next step is to commit the fold, push, PR, watch-then-merge, run the
P1 seven-ledger sweep, and close. **One item belongs to
the user at the close gate: the ratified independent hand re-verification of the 30 TB3MS literals
is undischarged, because all three extraction passes shared one render-proxy channel.**

---

## Raw Session Log

*(Condensed chronological transcript — the session ran long; every user message is reproduced
verbatim, with assistant actions summarized faithfully rather than quoted in full.)*

**[continuation]** Session resumed post-compaction mid-`/compress` of the previous session. Delivered
the Step-6 confirmation for the CAL-1b log.

**USER: `/compact`, then "What is still running?"**
→ Answered: nothing; the prior full-PG battery (2,909 passed / 0 failed, alembic clean) had
completed before the log was saved. Resumed the CAL-1b ship sequence: staged the 20 fold files
explicitly (never `git add -A`), committed `1c94b15`, pushed `cal-1b`, opened **PR #162**, watched
checks (all six green on both runs), merged → `33aca0d`, ran the P1 seven-ledger verify-on-main
sweep (all five slice commits ancestors; merged tree byte-identical), watched merged-main CI
(first watch died on a network reset; re-watched → success, run 30720860960). Wrote the CAL-1b
closeout (roadmap close row, slice-table CLOSED annotation, current_state refresh — including
correcting a misattribution where the CAL-1b bullet carried CAL-1a's fold findings), `make check`
green, **PR #163** → merged `e3253a9`, its main CI observed green (run 30749799312). Memory updated.

**USER: "Try again"** (after an empty response)
→ Confirmed the re-watch result and resumed the closeout.

**USER: "proceed"**
→ Ultracode on. Launched a six-lane DATA-1 recon workflow at pinned HEAD `e3253a9`: the rf series
today, the capture rails, the DQ/completeness deferral chain, CTRL-034, requirements+ADRs, and a
web-research lane on the T-bill dataset. Two lanes died on connection errors; resumed via
`resumeFromRunId` so the four finished lanes replayed from cache. 193 facts total. Surfaced the
central collision (yield vs return), drafted `data_1_decision_record.md` (Parts 0–4, G1–G49,
OQ-1…12), then ran a four-lane refute-by-default verifier: 28 findings (1 BLOCKING — the draft
presented the third calendar deferral as half-delivered; 5 HIGH including a false
zero-ingestion-callers claim and a composite paraphrase inside quotation marks; 10 MED; 10 LOW).
All folded in place; Part 5 records the fold. Committed `4a99172`, pushed, briefed the gate in
plain language.

**USER: "Proceed"** (the DATA-1 ratification gate)
→ Recorded Part 6 (the ratification acts) + the roadmap decisions-log row, committed `78dd64c`,
opened **PR #164**, checks green, merged → `de20d4b`, main CI observed green (run 30753677594).
Branched `data-1` and implemented:
- **`567d2a4`** — models + vocabularies + coherence map + `rates_complete_through`; migration
  `0060`; `RULE_TYPE_COMPLETENESS` + evaluator + registry; the rail; the 30 TB3MS literals (a third
  extraction pass at implementation); the read endpoint; 17 rail tests + 7 completeness tests;
  21 head-pin relays; the synthetic glob → 0061; the two stale dq docstrings.
- **`12ae033`** — demo stage 22, the 13-z suite (FINAL-POSITION relay), the 12-z demotion, the PG
  RLS/savepoint suite, two CI steps, regenerated FE types.
- **`4522908`** — CTRL-034 Execution 2 + the item-3 amendment + the Execution-1 citation re-point;
  the ENT-070 registry row + next-free; the taxonomy activation; the CTRL-034 matrix row;
  REQ-DQR-001 and REQ-PRF-002 in both registers; current_state; record Part 7.

Gates: `make check` green throughout; **P4 dry run executed non-vacuously** on `0060` (staged rows,
downgrade dropped table+column, re-upgrade rebuilt RLS/policy/index); FE typecheck + 207 FE tests
green. Launched the full-PG battery and, in parallel, a four-lane adversarial review.

The battery returned `PYTEST_EXIT=0` with 2,943 progress dots and zero failures — but a file-state
notice revealed the review's quant lane was mutation-testing in the shared tree, so the result was
declared VOID as evidence per the P2 standing rule.

Review returned: 1 BLOCKING (the shared-tree overlap itself), 7 HIGH, 9 MED, 7 LOW. Verified the
tree clean (zero mutation markers), then folded every finding — including the two proven by
execution (dangling savepoint; severity-downgrade fabricated success) with hostile negative
controls, the head-scoped rule, the missing endpoint tests, the PG audit pins, the correction
exercise on PG, the CTRL-034 Operational revert, and the provenance rewordings that moved the
ratified independent hand re-verification to the close gate. Wrote Part 8. `make check` green on
the folded tree; purged caches; reset the schema; launched the battery re-run
(`PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`) — at ~63% with zero failures when the session
log was written.

**USER: `/model opus[1m]`, then `/compress`**
→ While writing this log the battery finished: **RED, 1 failed / 2,949 passed**. The single
failure was `test_correction_verb_on_the_authoritative_engine` — a test the review fold itself
added — failing with `NoResultFound` because it committed and then read in the same session, where
`set_tenant_context` is transaction-local and clears at COMMIT (RLS then legitimately returns zero
rows). Rewrote it to verify in a fresh session (also proving durability); the PG rate suite re-ran
**6/6 green** against live PG; reset the schema and ran a clean full battery, which came back
**GREEN: 2,950 passed / 0 failed, `PYTEST_EXIT=0`**. The log was corrected twice to record the
OBSERVED results rather than in-flight optimism — the same P6 standard the fold had just applied to
three other artifacts. Session ended at the declared pause boundary (the model recommendation had
changed to Opus 5), with the fold gate-complete but uncommitted.
