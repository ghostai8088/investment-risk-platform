# Session Log: 27-07-2026 10:56 - wave-12-close-rm1-sch2-planning

## Quick Reference (for AI scanning)

**Confidence keywords:** Wave-12 close review, ultracode, 10 auditors, guard-layer HIGH, write fence bypassable, refusal-detail dead branch, deadlock_503, closure-teeth prose shape, CTRL-021 backfill, RM-1, rolling metrics, 21st governed number, ENT-064, migration 0053, GIPS 2020, 2.A.12, 4.A.1.j, 2.A.23.b, Lo 2002 Eq. 19, Magdon-Ismail, Chekhlov, monthly grid relink, irregular sub-periods, heteroskedastic, max drawdown, window-local rebasing, four-column grain, suppression flag, SCH-2, CALENDAR_MONTH_END, last weekday, preceding convention, family dispatch registry, model_version_id nullable, total-enumeration CHECK, pre-anchor tick, end-of-day tick, as_of_known_at, EmptySnapshotError, two-table downgrade cascade, demo stage 15, recommendation-before-verification

**Projects:** investment-risk-platform (`ghostai8088/investment-risk-platform`)

**Outcome:** Wave 12 closed and ratified (8th consecutive clean runtime close, 2 guard-layer HIGHs folded); RM-1 and SCH-2 both planned, adversarially verified and ratified; SCH-2 implementation ~80% complete on branch `sch-2-planning`.

---

## Decisions Made

### Wave-12 close (OQ-W12C-1/2/3, all = A, 2026-07-26)
- **Accepted the close verdict.** Five slices shipped-as-ratified; zero runtime defects. But the guard layer took its first two HIGHs — both OPS-1 review folds whose delivered form failed its own ratified claim. Folded at the close with executed negative controls.
- **Wave 13 = "analytics breadth on the governed rails":** RM-1 → SR-1 → OPS-H1 → FE-M1. Wave-14 tee = real-data onboarding carrying the dimensional analytics.
- **Process batch, all four adopted:** (a) recommendation-before-verification extended to review folds — a shipped guard carries its EXECUTED negative control; (b) conformance-pin every hand-mirrored contract, and accept the CI-Python-3.12/local-3.13 asymmetry as recorded; (c) every closeout leaves a control-matrix trace; (d) interim — `DEMO_TENANT_ID` never enters `IRP_TENANT_IDS` until OPS-H1.

### RM-1 (OQ-RM-1-1…7, all = A as revised, 2026-07-26)
- **Relink to calendar months and REFUSE a misaligned series.** A standard deviation over cash-flow-delimited sub-periods is defensibly wrong, not merely imprecise (Lo Eq. 19: variance ∝ interval length ⇒ heteroskedastic by construction; the statistic would partly reflect the client's cash-flow schedule). GIPS resolves it architecturally: sub-period returns are inputs only, linked up to a calendar grid.
- **Annualization decided per metric:** volatility ×√12 from the STORED value; returns never below a 12-month window (GIPS 2.A.12 is a hard MUST NOT), enforced at the registered parameter domain with the kernel guard relabelled defense-in-depth; MDD never (no horizon-scaling law exists for a bounded saturating statistic).
- **MDD:** `1 + m > 0` precondition, window-local rebasing, `V₀` included as an observation, `0 ≤ MDD ≤ 1` asserted as a post-condition.
- **Windows {12, 36} as a registered model parameter** (not caller-supplied — keeps the SEC anti-cherry-picking exposure out of the data layer).
- **Suppression = nullable value + explicit flag + CHECK**, one row per (metric, window) per run.
- **Demo:** purpose-built past-dated book, 19 month-ends + 1 mid-month, designed multi-month drawdown. N=22 → counts 24/39/131.
- **The operability carry went INTO scope** as a preceding slice (SCH-2) rather than being carried.

### SCH-2 (OQ-SCH-2-1…8, all = A as revised, 2026-07-27)
- **`model_version_id` relaxes to nullable under a per-family TOTAL-ENUMERATION CHECK.** The implication form fails OPEN for any unenumerated family; the exclusive-exhaustive form fails closed, so family 3 requires a migration (deliberate — the DB becomes a genuine third gate).
- **Month-end grid = the LAST WEEKDAY** (QS-11 `preceding` convention over a weekend-only predicate). A pure calendar month-end fails 30.6% of real months; the weekday rule cuts it to holiday collisions (2.8%, next 2027-05-31). Full ENT-006 holiday resolution rides Wave-14.
- **The tick is an END-OF-DAY instant** — it becomes a bitemporal cutoff, and a midnight tick makes same-day marks invisible.
- **OQ-7 = accept the burned month + runbook + a minimal read.** A failed fire permanently occupies its bucket; preserving the append-only ledger and idempotency was preferred over designing a re-fire path against the anti-double-fire invariant.
- **OQ-8 = `EXPOSURE_AGGREGATE`** (the real run_type) rather than a short `"EXPOSURE"` — `target_run_type` already ships on `limit_definition`/`breach` holding real run_types and is rendered in the OPS-1 UI.
- **Sequencing re-confirmed SCH-2-before-RM-1** after the size was honestly revised M → M/L.

---

## Key Learnings

### The pattern that recurred all session: my errors cluster in claims about the codebase I could have checked but reasoned about instead
Five instances, all caught by something adversarial rather than by me:
1. The SCH-2 roadmap row claimed the portfolio column was "the one deferral that does not trip" — omitting that `model_version_id` NOT NULL blocks the model-less exposure family. LIM-1's record had already flagged the exact collision.
2. RM-1's month-alignment criterion was **vacuous for any within-month series** — the record contained a claim its own rule contradicted (the campaign span contains no month-end, so the test passed over the empty set).
3. A GIPS clause quoted with the permissive half removed ("or the last business day"), which would have made the platform reject compliant books while citing the standard it was breaking.
4. SCH-2's claim that CI exercised the downgrade — no demo stage creates a schedule at all, so the smoke deleted zero rows and passed while testing nothing.
5. SCH-2's fence claim — three other modules violate the same "nothing imports me" docstring, so the proposed test would have failed on day one.

### Guards that don't guard
Both Wave-12 HIGHs were this class: an eslint fence enumerating literal import paths (so the natural src-root form passed clean), and a conformance test whose key assertion sat in a provably dead branch. Neither had runtime exposure; both were ratified as enforcing. **A guard ships with its negative control executed against the actual bypass form, or it is decoration.**

### Numbers that render cleanly and mean nothing
Three RM-1 findings were the same failure mode: a drawdown that could exceed 100% or move the wrong way on a legal input; a "not computable" state stored as zero and indistinguishable from three legitimate zeros; and two governed numbers definitionally identical at the headline window.

### Building it disproves what reasoning about it concluded
Twice in SCH-2 implementation:
- The demo stage failed instantly with `EmptySnapshotError` because I had pinned `as_of_known_at` to the tick. "As known at the month-end" excludes everything recorded afterwards. The verifier's reason for pinning (two fires of one tick could differ) is **unreachable** — the unique constraint permits exactly one fire per tick — while the cost is real: a late-arriving month-end mark would be permanently invisible. Reverted.
- Replacing rather than adding the start-boundary guard regressed the INTERVAL cadence: the clamp makes `tick == anchor`, which satisfies the new tick test while being a FUTURE tick. Both legs are required.

### Verifier-pass economics
Three consecutive slices, each returned NOT RATIFIABLE on first draft: RM-1 (7 blocking + 20 material), SCH-2 (8 blocking + ~14 material). In both, the *direction* survived every attack and the *specification* did not. ≥2-finder convergence = CONFIRMED proved out again (both SCH-2 lanes independently refuted the anchor-separation claim).

### Infrastructure failures that look like code failures
"CI / DB migration (Postgres) failing" read like a schema defect. The failing step was "Initialize containers", which precedes any project step, and the same commit had passed the full job on a sibling event. Re-running identical content confirmed it. **Identify the failing STEP, then look for a same-content control, before touching migrations.**

---

## Files Modified

### Wave-12 close (merged `646b6a6`)
- `10_delivery_backlog/wave_12_close_review.md` — NEW, RATIFIED
- `apps/backend/src/irp_backend/deps.py` — hoisted `deadlock_503`
- `apps/backend/src/irp_backend/api/{limits,breaches}.py` — 503 mapping on all five limit verbs; refusal-detail wire pins
- `apps/frontend/eslint.config.js` — write fence rebuilt on `patterns`
- `apps/frontend/write-fence.test.ts` — NEW, ESLint-API pin with negative controls
- `scripts/check_docs.py` — closure teeth broadened to the `**Status:**` prose shape
- `09_compliance_controls/control_matrix_skeleton.md` — CTRL-021/031 backfilled
- `packages/shared-python/tests/test_ci_pg_coverage.py` — comment-strip + multi-path hardening

### RM-1 planning (merged `3211904`)
- `10_delivery_backlog/rm_1_decision_record.md` — NEW, RATIFIED (16 ODs, corrected rule-6 citations, OQ-RM-1-1…7)
- `10_delivery_backlog/delivery_roadmap.md` — Part 2.16 (Wave 13) + SCH-2 row + decision-log rows

### SCH-2 (branch `sch-2-planning`, HEAD `9544881`)
- `10_delivery_backlog/sch_2_decision_record.md` — NEW, RATIFIED
- `migrations/versions/0053_schedule_cadence_family.py` — NEW: two relaxations, three total-enumeration CHECKs, two-table downgrade sandwich
- `packages/shared-python/src/irp_shared/scheduling/events.py` — `CADENCE_CALENDAR_MONTH_END`, `TARGET_RUN_TYPE_EXPOSURE_AGGREGATE`; `SCHEDULABLE_RUN_TYPES` moved out
- `packages/shared-python/src/irp_shared/scheduling/service.py` — cadence-aware fail-closed `current_tick`, `_outside_start_boundary` (both legs), `FAMILY_REGISTRY`, `_dispatch_var`/`_dispatch_exposure`, registry-driven `_validate_config` + FK guard
- `packages/shared-python/src/irp_shared/scheduling/models.py` — nullability + rationale
- `apps/worker/src/irp_worker/scheduler.py` — `OUTCOME_UNRECORDED` sentinel, family-specific phase-ordering docstring
- `packages/shared-python/src/irp_shared/demo/sch2_stage15.py` — NEW demo stage (drives a real tick)
- `packages/shared-python/tests/test_scheduler.py` — +9 cadence/registry tests
- `packages/shared-python/tests/test_scheduler_cadence_pg.py` — NEW: behavioral CHECK matrix + executed negative control + non-superuser downgrade-body test
- `packages/shared-python/tests/test_demo_stage9zzzzzz_sch2_pg.py` — NEW stage-15 suite
- `.github/workflows/ci.yml` — two new PG steps
- 10 suites: migration-head pins `0052` → `0053`; `test_synthetic.py` next-free-slot guard bumped

---

## Pending Tasks

1. **Full PG battery was still running** at compress time (fresh schema, post-fix). Confirm green.
2. **SCH-2 remaining implementation:**
   - the minimal schedule read surface (OQ-7 — no API router for schedules exists today)
   - doc amendments: `audit_event_taxonomy.md:85` (the DC-2 `interval_days: None` payload change), `scheduling/{models,events,service}.py` and `0049` docstrings ("v1 = INTERVAL/VAR/run_var"), the two "nothing imports me" fence docstrings + the narrow-but-true inbound sweep
   - `make check`, `gen-api-check`, downgrade smoke
3. **4-finder adversarial review (Fable 5)** then push, CI to green, PR.
4. **Then RM-1 implementation** (ENT-064, migration `0054` once 0053 lands).
5. Wave-13 slices after: SR-1, OPS-H1, FE-M1 (React-19 before the 2026-10-24 allowlist expiry).

---

## Quick Resume Context

Wave 12 is closed and merged. RM-1 (rolling metrics, the 21st governed number) and SCH-2 (month-end cadence + family dispatch registry) are both planned, adversarially verified and ratified — SCH-2 runs first because RM-1's monthly grid needs month-end exposure runs that nothing could produce. SCH-2 implementation is ~80% done on branch `sch-2-planning` (HEAD `9544881`): the grid, registry, migration `0053`, demo stage and PG suites are all green; remaining are the minimal read surface, doc amendments, `make check`, the 4-finder review and the push. The standing lesson driving this session: verify cheaply-checkable claims against code rather than reasoning about them — five self-inflicted errors were caught only by adversarial verification or by running the tests.

---

## Raw Session Log

*(Full conversation preserved in the Claude Code transcript at
`/Users/andrewcox/.claude/projects/-Users-andrewcox-Projects-investment-risk-platform/19fbf1ce-c768-4810-a4da-2751c2f1a3fc.jsonl`.)*

Session arc, in order:

1. **Wave-12 close review** — 10 refute-by-default auditors under ultracode over `dd63ba7..6f8d923` (5 slice, 4 cross-cutting, 1 agenda-claims verifier), each HIGH/MED attacked by 2 adversarial refuters. 32 agents, ~2.0M tokens. Verdict: zero runtime defects (8th consecutive clean close) but two guard-layer HIGHs — the OPS-1 write fence bypassable by unlisted import forms, and the refusal-detail pin's SoD assertion a provably dead branch. Both folded at the close with executed negative controls, plus three MEDs (phase-2 FK-KEY-SHARE tick×HTTP 40P01 with no limits-router 503 map; closure teeth blind to the `**Status:**` prose shape; control-matrix sweep skipped at API-2/OPS-1). Gates: `make check` 2036, full-PG 2463/0, fe-check 148, downgrade smoke clean. Ratified OQ-W12C-1/2/3 all = A.

2. **RM-1 planning** — 5 parallel recon readers + external methodology research (GIPS 2020, Lo 2002, Magdon-Ismail, Chekhlov, SEC marketing rule, all fetched as primaries). Two recon claims refuted by hand-verification. The research changed the slice: a standard deviation over irregular sub-periods is defensibly wrong, so the design relinks to calendar months and refuses misaligned series. Two-lane pre-ratification verifier pass returned NOT RATIFIABLE (7 blocking + 20 material), including a vacuous alignment criterion that contradicted the record's own example and a truncated GIPS citation. All folded; ratified OQ-RM-1-1…7 as revised; the operability carry went into scope as SCH-2.

3. **CI infrastructure failure** — "DB migration (Postgres) failing" on the planning PR diagnosed as a service-container startup failure (failing step "Initialize containers"; same commit green on the push event). Re-ran failed jobs via the REST API; attempt 2 green with no code change.

4. **SCH-2 planning** — recon of the scheduler, then a two-lane verifier pass returning NOT RATIFIABLE (8 blocking + ~14 material, including three false claims in the draft). Both lanes independently refuted the anchor-separation claim. Ratified OQ-SCH-2-1…8 as revised, with two new gate questions (the burned month, the family-key vocabulary) and an honest M → M/L size revision.

5. **SCH-2 implementation** — the cadence-aware fail-closed grid, both start-boundary legs, the family dispatch registry, migration `0053`, ORM nullability, the worker `UNRECORDED` sentinel, 9 new unit tests (the cadence vocabulary previously had zero coverage), the demo stage driving a real tick, the PG CHECK matrix with its executed negative control, the non-superuser downgrade-body test, and CI wiring. Four bugs found by running the tests: `str(None)` → `"None"` rejected by PG; FK violations masking the CHECK in the matrix; a stale next-free-migration guard; and the `as_of_known_at` pin producing an empty snapshot — which reverted a decision the verifier had asked for, on the grounds that its motivating scenario is unreachable under the idempotency constraint.
