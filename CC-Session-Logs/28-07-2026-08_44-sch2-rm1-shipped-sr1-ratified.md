# Session Log: 28-07-2026 08:44 - SCH-2 & RM-1 Shipped, SR-1 Ratified

## Quick Reference (for AI scanning)

**Confidence keywords:** investment-risk-platform, SCH-2, RM-1, SR-1, ENT-064, ENT-065, rolling_risk_result, sharpe_ratio_result, migration-0053, migration-0054, migration-0055, 21st-governed-number, 22nd-governed-number, rolling-volatility, maximum-drawdown, window-local-rebasing, GIPS-2.A.12, GIPS-2.A.23.b, GIPS-4.C.36, Sharpe-1994, Lo-2002, Chekhlov, Magdon-Ismail, perf/stats_kernel.py, perf/rolling_kernel.py, perf/rolling_service.py, estimator-lift, decimal-contract.ts, mutation-testing, 4-finder-review, verifier-pass, ledger-class-omission-sweep, count-pin-relay, suppression-encoding, four-column-grain, PR#133, PR#134, PR#135, PR#136, PR#137, PR#138, b6e7ba0, b802626, 8de96f4, eceac08, counts-24/39/132, Fable-5, Opus-5

**Projects:** investment-risk-platform (ghostai8088/investment-risk-platform), Wave 13

**Outcome:** Two governed-platform slices shipped and closed (SCH-2 month-end cadence, RM-1 rolling risk = the 21st governed number), a systematic doc-drift sweep fixed five omissions spanning three slices, and SR-1 (Sharpe) was drafted, two-lane verified (3 BLOCKING folded) and ratified at the gate.

---

## Decisions Made

### SCH-2 (merged PR #133 = `8c8c17b`)
- **`as_of_known_at` pin REVERTED** post-ratification — building the demo produced `EmptySnapshotError`; known-time means "as RECORDED at T", so pinning makes late-arriving marks permanently invisible, and the verifier's motivating two-fires scenario is unreachable under `uq(schedule_id, scheduled_for)`. Recorded as a Part 4b amendment.
- **`produces_run_on_failure` REMOVED** from the family registry — false on the only scheduled path (the pre-create gate is the snapshot build's completeness gate, not upstream resolution). Removed rather than corrected because the distinction is not a family property.
- **`MAX_INTERVAL_DAYS = 36_525`** runaway envelope added in three layers after the review found an `OverflowError` escape.

### RM-1 (merged PR #135 = `b6e7ba0`, CI #652)
- **Monthly grid defended on STANDARDS grounds** (GIPS 4.A.1.j), not on a claim of homogeneity — the record states the honest limit (calendar months are 28–31 days, so the grid is itself heteroskedastic by ~5.2%).
- **Five-condition alignment gate** (up from three) after review found two month-ends can share a month under the business-day allowance, producing a one-day "month".
- **Window-local rebasing + `V₀` as an observation** for maximum drawdown; `MDD₃₆ ≥ MDD₁₂` explicitly does NOT prove this (holds under run-global too).
- **Suppression as a first-class state** (nullable value + NOT NULL flag + reason under a total-enumeration CHECK) because `0` is a legitimate value for all three metrics.
- **Four-column grain** `(calculation_run_id, metric_type, window_months, period_start)`.
- **CHECK declared in ORM as well as migration** so the SQLite unit tier enforces it too (the SCH-2 lesson).
- **Estimator lift** to `perf/stats_kernel.py` with each family re-wrapping at its own boundary; `StatsKernelError` deliberately a `ValueError`, NOT an `ArithmeticError`.
- **PM-1's `PORTFOLIO_RETURN_ASSUMPTIONS` left byte-untouched** — `resolve_or_register_version` returns an existing version untouched on a SELECT hit, so editing would diverge v1 text across tenants.
- **Counts corrected TWICE**: ratified 24/39/131 → measured 24/38/132 → corrected to **24/39/132** (see Key Learnings #5).

### SR-1 (ratified 2026-07-28, planning merged PR #138 = `eceac08`)
- **OQ-SR-1-1 = A** — Sharpe (1994) differential-return form with a **DISCLOSED n−1 divisor divergence** (the paper's own endnote uses population σ; ours is ~4.3% smaller SR at n=12), single-quantization, magnitude gate from birth, √12 iid annualization.
- **OQ-SR-1-2 = A** — risk-free series rides ENT-052 as an ordinary benchmark head (vendor-published monthly returns; zero schema change). ENT-021 curve + registered yield→return model recorded as the costed alternative.
- **OQ-SR-1-3 = A** — NEW ENT-065 `sharpe_ratio_result` with `risk_free_benchmark_id` NOT NULL, rather than a nullable provenance column on ENT-064.
- **OQ-SR-1-4 = A** — RM-1's suppress-and-disclose convention; P3-8's omit convention diverges and its shipped rows stay untouched.
- **OQ-SR-1-6 = A** — sizing **M** (revised up from the roadmap's S/M).

---

## Key Learnings

1. **Mutation-test the NUMBER, not only the guards you thought of.** RM-1's refusal/alignment logic was well covered; its positive computational path was unpinned. An arithmetic-sum mutant replacing the geometric link shipped a 2.8pp error on the headline statistic with every tier green.

2. **My tests fail by asserting things TRUE AND UNINFORMATIVE, not things false.** Five instances this session: an invented fixture vector (mean coincidentally matched, stdev didn't); a test restating the implementation (a mutation swapping √12 for an equivalent literal passed); a test whose earlier precondition fired first (proving the wrong guard); a test mutating an append-only row (testing the append-only guard, not the purpose gate); a "pin" asserting only non-None.

3. **I made a shipped guard WEAKER while claiming to strengthen it.** Rewriting `decimal-contract.ts` from a curated 22-entry array to a derived `*RowOut` mapped type, I read a truncated view showing 15 entries and silently dropped 7 (`BreachOut`, `PositionOut`, …). **Derive what a rule can identify; curate the rest — and never let "exhaustive by construction" mean narrower than what it replaced.**

4. **`MDD₃₆ ≥ MDD₁₂` does not prove window-local rebasing** — it holds under a run-global peak too. Asserted in four places including a REGISTERED model_assumption. My first replacement fixture ALSO failed to discriminate: when the run peak IS the window's opening level, the conventions coincide (rebasing is a scale factor; the ratio is scale-invariant).

5. **A measurement that contradicts a ratified expectation is evidence of a defect SOMEWHERE — assuming it sits in the EXPECTATION is the comfortable reading.** Measuring 38 validations against a ratified 39, I "corrected" the record down. Wrong: every prior new-code demo stage files an INITIAL validation record and mine omitted it. The correction would have quietly ratified the gap.

6. **Omission-class defects leave no diff, so reviews cannot see them.** Five ledger omissions spanned three slices and were found only when the NEXT slice's recon tripped over them. **A slice's debt surfaces when the next one tries to stand on it.** Countermeasure: a six-ledger closeout sweep, now in memory.

7. **Count pins are relay batons, not monuments.** The platform's only absolute-count pin collated BEFORE later stages, pinning an intermediate total it could never fail on — which is how SCH-2 shipped a merged record claiming "counts unchanged" while its stage 15 adds a COMPLETED run.

8. **The `env.py` naming-convention trap:** `op.create_table` DOES apply `ck_%(table_name)s_%(constraint_name)s` because `target_metadata` is passed, so passing a full CHECK name mints a doubled, 63-char-truncated, hash-suffixed name. **`alembic check` does not compare CHECK constraints**, so the drift gate is blind to it. Pass the suffix only, on both sides.

9. **A verifier pass has now returned NOT RATIFIABLE on the first draft four slices running** (ES-1 lesson holding). In every case the design DIRECTION survived and the SPECIFICATION did not, and the worst defects were the author's own reasoning.

---

## Files Modified

### SCH-2 (merged)
- `packages/shared-python/src/irp_shared/scheduling/{service,models,events,queries}.py` — cadence-aware grid, family dispatch registry, `MAX_INTERVAL_DAYS`, `redact_failure_reason`, read-only queries
- `apps/backend/src/irp_backend/api/schedules.py` (NEW) — `GET /schedules{,/runs}` gated `schedule.view`
- `migrations/versions/0053_schedule_cadence_family.py` (NEW)
- `packages/shared-python/src/irp_shared/demo/sch2_stage15.py` (NEW)
- Suites: `test_scheduler.py`, `test_scheduler_cadence_pg.py`, `test_demo_stage9zzzzzz_sch2_pg.py`, `test_schedules_endpoint.py`

### RM-1 (merged)
- `migrations/versions/0054_rolling_risk_result.py` (NEW) — ENT-064
- `packages/shared-python/src/irp_shared/perf/stats_kernel.py` (NEW) — the domain-neutral estimator lift
- `packages/shared-python/src/irp_shared/perf/rolling_kernel.py` (NEW) — grid, alignment, drawdown, annualization
- `packages/shared-python/src/irp_shared/perf/rolling_service.py` (NEW) — binder + rule-7 reads
- `packages/shared-python/src/irp_shared/perf/{models,events,bootstrap}.py` — ENT-064 model, run type, registered model
- `packages/shared-python/src/irp_shared/snapshot/{service,models,__init__}.py` — `PURPOSE_ROLLING_RISK_INPUT` + builder
- `packages/shared-python/src/irp_shared/demo/rm1_stage16.py` (NEW) — stage 16, 7 `z`
- `apps/backend/src/irp_backend/api/perf.py` — `/perf/rolling-risk{,/latest,/{id}}`
- `apps/frontend/src/api/decimal-contract.ts` — derived `RowOutKey` + curated `ExtraGovernedDtoKey`
- `05_analytics_methodologies/rolling_risk_v1.md` (NEW); `02_requirements/{requirements_backbone,requirements_traceability_matrix}.md` — REQ-MKT-006 + REQ-PRF-003
- Suites: `test_rolling_kernel.py`, `test_rolling_risk.py`, `test_stats_kernel.py`, `test_rolling_risk_pg.py`, `test_demo_stage9zzzzzzz_rm1_pg.py`

### Doc-drift sweep (PR #137 = `8de96f4`)
- `04_data_model/canonical_data_model_standard.md` — ENT-064 recorded as minted, next free = ENT-065; **four missing registry rows added** (ENT-061/062/063/064)
- `04_data_model/audit_event_taxonomy.md` — PERF row records "still exactly three after a fourth perf family"
- `09_compliance_controls/control_matrix_skeleton.md` — CTRL-003 trace for SCH-2's enforcement-shape change
- `docs/project_memory/current_state.md` — CURRENT TRUTH block brought current
- `10_delivery_backlog/{sch_2,rm_1}_decision_record.md` — control-matrix trace sections

### SR-1 (planning merged)
- `10_delivery_backlog/sr_1_decision_record.md` (NEW) — drafted, two-lane verified, 27 findings folded, ratified
- `10_delivery_backlog/delivery_roadmap.md` — SR-1 row + decision-log entry

---

## Pending Tasks

**SR-1 implementation** (ratified, Part 6 checklist written):
1. Migration `0055` + ENT-065 `sharpe_ratio_result` — four-column grain, `portfolio_id` + `period_end` + `rf_return_basis` (verifier-added), suppression trio + CHECK in ORM *and* migration (suffix-only both sides)
2. Sharpe kernel + binder — single-quantization, suppression predicate on unquantized σ, magnitude gate from birth covering the annualized pair member
3. Risk-free capture (18 rows, one per MEASURED month) + `PURPOSE_SHARPE_INPUT` + builder
4. Demo stage 17 (`sr1_stage17.py`, suite `test_demo_stage9zzzzzzzz_sr1_pg.py` — **EIGHT `z`**, verify by `ls`)
5. **PG suite FROM BIRTH** + golden-value tests on the number
6. Count-pin relay: demote stage-16's "FINAL" pin; new pin at **25/40/133**
7. Rule-7 reads, `REQ-PRF-004` (CAP-20.6) backbone+RTM same commit, methodology doc `sharpe_v1.md`
8. **Inherited-debt folds:** `test_synthetic.py` guard → `0056*` + its stale 0053-era comment; `_BINDING_PREDICATES` missing `PACING_` and `ROLLING_RISK_`; move the `SNAPSHOT_PURPOSES` check into `_persist_snapshot` + membership pins; the lying ORM comment at `perf/models.py:351-355`; CAP-20 taxonomy row never visibly extended by RM-1
9. 4-finder review + gates (`make check`, fresh-schema full-PG, downgrade smoke, `gen-api-check`, `fe-check`) + PR

**Wave 13 remainder:** OPS-H1 (hygiene) → FE-M1 (React-19/router-8, allowlist expiry **2026-10-24**)

**Proposal for the Wave-13 close:** ratify the ledger-class omission sweep as a standing closeout step in `claude_operating_instructions.md`.

---

## Quick Resume Context

`main` is at `eceac08` (PR #138, SR-1 planning). Wave 13 has TWO slices closed — SCH-2 (month-end cadence, migration `0053`) and RM-1 (rolling risk, ENT-064, migration `0054`, the **21st governed number**) — with demo counts at **24/39/132**. SR-1 (Sharpe, the 22nd governed number) is **RATIFIED** with its decision record merged; implementation has not started. Start from `sr_1_decision_record.md` Part 6 and the Pending Tasks list above; every reused primitive was verified by the engineering verifier lane to actually exist, so the build starts on checked premises.

Two standing rules from this session now in memory: **mutation-test the number, not only the guards you thought of**, and **run the six-ledger omission sweep at every closeout** (`ledger-class-omission-sweep.md`).
