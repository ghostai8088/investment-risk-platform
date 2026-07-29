# Session Log: 29-07-2026 09:15 - Wave-13 Close Review, Ratified and Merged

## Quick Reference (for AI scanning)

**Confidence keywords:** Wave-13-close, close-review, ultracode-audit, 121-agents, refute-by-default,
three-lens-refutation, thin-margin-kills-overturned, runtime-clean-streak-ended, calc/reads.py,
blanket-str-bind, window_months, integer-eq-varchar, SQLite-column-affinity, PG-tier-pin,
closure-stamp-gate, _status_lines, non-vacuity-floor, six-unstamped-records, P2-7, P3-8, P3-C2,
PM-1, TD-1, mutation-control, 11-mutants-killed, no-restricted-imports, ImportExpression,
dynamic-import-fence, mts-cts, audit-gate-fail-open, review_by-undefined, parse_strict_decimal,
NaN-asymmetry, _persist_snapshot, purpose-gate-census, _BINDING_PREDICATES, GS2-census,
vacuous-pacing-test, R-4-class, lockfile-delta-22-not-12, CTRL-002, sharpe_v1.md, month_key,
P1-P6-ratified, verify-on-main, shared-tree-mutation-rules, executed-dry-run, assert-by-evidence,
enumerating-guards, Wave-14-ratified, real-data, ENT-006-holiday-2027-05-31, memory-symlink-split,
PR-146, 2411d00, CI-30455596382, CI-30456842431, CI-30457408821, 2201/480, 2681/0, 32-files-204-tests

**Projects:** investment-risk-platform (ghostai8088/investment-risk-platform)

**Outcome:** The Wave-13 close review ran end to end — a 121-agent ultracode audit, all 34 findings
folded with 11 executed mutation controls, six standing rules (P1–P6) ratified and written into the
operating instructions, Wave 14 ratified as "real data through the governed rails", merged via
PR #146 (`2411d00`) with merged-main CI green, and the newly-ratified P1 sweep executed clean
against `main`. **The eight-wave runtime-clean streak ended honestly:** one shipped HIGH that every
existing gate was structurally incapable of seeing.

---

## Decisions Made

- **Fold EVERYTHING, not triage-and-defer.** All 11 surviving findings, all 20 LOWs, and the 3
  overturned kills were folded. Justified by the `clean-code-standing-bar` memory (cleanup findings
  default to fold-now) and because 3 of the LOWs were the R-4 vacuous-assertion class — letting
  them ride while ratifying a rule against exactly that pattern would be incoherent.
- **Withdrew my own recommendation to use workflows for the fold phase.** After reading
  `shared-tree-mutation-hazard`, ran folds as a SINGLE editing thread: the SR-1 incident (a
  `git add -A` committing a live finder mutation) is precisely what parallel tree-mutating agents
  recreate, and the payoff was small since most folds were a few lines.
- **Re-adjudicated the six findings the refuters killed only 2-of-3 — and overturned three.** A thin
  majority on a refute-by-default panel means one lens found it real. The dynamic-import fence axis,
  SR-1's false "refused at capture" claim, and the vacuous pacing test all survived my own probes.
- **P4 ratified WITH a binding clause rather than as briefed.** The audit refuted its pin half: the
  dry run's "exactly 12" lockfile number was 22 at merge and the human counting gate never fired.
  Ratifying the rule without "re-measure against the merged artifact at closeout" would have
  institutionalised an invisible staleness.
- **P6 minted at the close (not on the original agenda):** pair every ENUMERATING guard with a
  non-vacuity floor. Three consecutive fixes to the closure gate were "broaden the matcher" and it
  went blind a fourth way each time. A floor cannot predict the next shape; it only notices coverage
  falling.
- **The reads-seam fix done inline, not delegated** — a shared path every governed family crosses;
  the correct fix (type-aware coercion) needs sight of all call sites.
- **Wave 14 ratified as DIRECTION only** — real-data onboarding; slice sequence ratifies at Wave-14
  planning per the normal per-slice discipline.

---

## Key Learnings

1. **THE RUNTIME-CLEAN STREAK ENDED AT EIGHT — and the streak was measured by a blind instrument.**
   `calc/reads.py` bound every entity-read filter with a blanket `str()`. Harmless for eight waves
   because every caller filtered a UUID/String column; RM-1 and SR-1 routed the platform's first
   `Integer` filter (`window_months`) through it, and PostgreSQL refused
   `integer = character varying`. **All four new read endpoints 500'd on the production database
   while `make check`, the PG suites, and CI were green** — because SQLite's INTEGER column affinity
   converts `'12'` → `12`, so the unit tier is *structurally incapable* of seeing the class. The
   fix's regression pin therefore belongs in the PG tier, where a unit pin could never fail.
   **Generalized: a whole TEST TIER can be the alternate path in the R-4 sense.**

2. **A matcher only covers the shapes someone enumerated; a floor notices coverage falling.** The
   closure-stamp gate matched only the *bolded* `| **Status** |`; every Wave-13 record writes it
   unbolded, so the gate saw nothing, short-circuited, and reported clean for an entire wave. Three
   prior fixes were all "teach it another shape". The mutation proof is the lesson in one line:
   restoring the old matcher drops coverage from 62 records to 29 and the new floor fires.

3. **Widening a blind guard exposes history, not just the present.** Fixing the gate surfaced SIX
   unstamped records — FE-M1 plus **five stale for many waves** (P2-7, P3-8, P3-C2, PM-1, TD-1),
   sitting at "HOLDING for Tier-2 commit approval" / "PLANNING RATIFIED" while the roadmap said
   DONE. PM-1 is the platform's seventh governed number.

4. **The independence ladder proved itself twice more.** The in-context pass found holes in guards it
   had not authored; the independent audit found the vacuous assertions in the author's own tests.
   And the R-4 class recurred **in the very file R-4 rewrote** (`/Breaches/` can never match the
   real "Breach queue" heading) and in the Python suite (a pacing test whose own comment conceded it
   never reached the gate under test).

5. **A guard-layer claim outlives the guard.** RM-1's alignment conditions (4) and (5) — the fix for
   a folded HIGH — could BOTH be deleted with the entire suite green, while the record and the
   registered methodology doc asserted "every new guard is mutation-tested." The code was right; the
   claim about it was wrong; the claim is what the next slice trusts.

6. **JS relational comparisons with `undefined` are always false — a fail-OPEN inside a fail-closed
   gate.** An audit-allowlist exception missing `review_by` was simultaneously "not expired", "not
   current", and present — so its advisory fell through every branch and vanished silently. A
   CRITICAL advisory could pass that way.

7. **Fences fail on axes nobody enumerates.** Third bypass of the same class: specifier spelling
   (Wave-12 close) → file extension (FE-M1 R-1) → **import syntax** (this close: `no-restricted-imports`
   has no `ImportExpression` visitor, so `await import("../api/client")` reached `request()`). The
   honest residual is recorded rather than papered over: a *computed* specifier is invisible to any
   lint rule.

8. **Sibling slices in one wave can ship opposite conventions over the same data shape.** RM-1 let a
   NaN pinned return escape as a raw `decimal.InvalidOperation`; SR-1, same wave, same
   `COMPONENT_KIND_PORTFOLIO_RETURN` pin, refused it as a governed 422 with a comment naming the
   hazard. Neither side had a NaN pin — SR-1's correct behaviour was one refactor from silent
   regression.

9. **Double-checking my own work found a defect the verification missed.** The retro-stamp note
   quoted a Status-row form containing raw pipes *inside a markdown table cell* — six records
   rendered as broken tables. My original "wellformed" assertion was itself miscalibrated (expected
   4 pipes; a clean two-cell row has 3), which is why it passed at stamp time.

10. **Environment: the memory directory was SPLIT by nesting depth.** Sessions started in the repo
    (`…-investment-risk-platform-investment-risk-platform/memory`) saw an EMPTY memory set, while all
    68 real memories lived under the parent path (`…-investment-risk-platform/memory`). Fixed by
    symlinking. Consequence: this session ran most of its length without the standing behavioural
    rules — including the hard "state model + effort every response" rule, which lapsed for a fourth
    time as a direct result.

11. **Unquoted heredocs command-substitute backticks.** `python3 - <<EOF` with a backticked filename
    in the body silently ate the filename and printed `command not found` into a memory file. Same
    class as the existing `git commit -m` backtick rule; the memory now carries a heredoc addendum.

---

## Solutions & Fixes

- **The shared read seam** — `calc/reads.py`: blanket `str(value)` → `_bind_at_column_type(column, value)`,
  coercing only for `String`-typed columns. Blast radius bounded empirically: 21 filter columns
  change binding (19 GUID + 2 Integer); `GUID.process_bind_param` already str()s, so the call-site
  coercion was redundant. **Equivalence proven on live PG across 10 families under three bindings —
  identical row counts, zero mismatches.** Regression pinned in `test_rolling_risk_pg` +
  `test_sharpe_pg` only.
- **The closure-stamp gate** — `_status_lines` widened to any emphasis (anchored regex),
  `_done_slice_ids` gained the tick-inside-bold shape (SR-1/OPS-H1 weren't even in the done-set),
  plus **`_MIN_RECORDS_WITH_STATUS = 50` / `_MIN_DONE_SLICES = 38` floors**. Six records stamped from
  real merge evidence (all 13 cited shas verified `merge-base --is-ancestor`).
- **The fences** — `.mts`/`.cts` added to the TS glob; new `DYNAMIC_IMPORT_FENCE` via
  `no-restricted-syntax` on `ImportExpression` selectors, with `writes.ts` keeping a *scoped*
  exemption (the V-3 lesson: never switch the whole rule off).
- **The audit gate** — a shape gate: an exception needs non-empty `id`/`reason` and a `yyyy-mm-dd`
  `review_by` or it FAILS; the error names both the record and the advisory it was silently covering.
- **RM-1 alignment** — two discriminating grids added (`[01-30, 01-31, 02-28, 03-31]`,
  `[04-30, 05-29, 05-30, 06-30]`), masking regex tightened `"2026-02"` → `"closes on 2026-02-13"`.
- **The NaN asymmetry** — RM-1 now uses `parse_strict_decimal`; NaN/sNaN/±Infinity pinned in BOTH suites.
- **The purpose gate** — direct `_persist_snapshot` negative control (refuse + zero rows), the two
  promised membership pins, and a both-directions census over every `PURPOSE_*` constant.
- **The vacuous pacing test** — rewritten so the snapshot EXISTS (hand-minted `ADHOC`), making the
  purpose gate the only possible source of the refusal.
- **Deadlock symmetry** — the tick-victim branch now EXECUTES the SAVEPOINT recovery on the real
  40P01; additionally proven deterministically by forcing victimhood via per-session `deadlock_timeout`.

**Every code fold carries an executed mutation control — 11 mutants, all killed, all restorations
shown green.**

---

## Files Modified

### Source
- `packages/shared-python/src/irp_shared/calc/reads.py` — the typed-bind fix (+ `_bind_at_column_type`)
- `packages/shared-python/src/irp_shared/perf/rolling_service.py` — `parse_strict_decimal`
- `packages/shared-python/src/irp_shared/perf/sharpe_kernel.py` — `month_key` docstring (refuted convention removed)
- `packages/shared-python/src/irp_shared/perf/bootstrap.py` — GRID assumption text: 3 → 5 conditions
- `packages/shared-python/src/irp_shared/scheduling/service.py` — CTRL-003 refusal hoisted into `dispatch_one`, declaration-driven
- `scripts/check_docs.py` — closure gate widened + non-vacuity floors
- `scripts/check_frontend_audit.mjs` — the exception shape gate
- `apps/frontend/eslint.config.js` — `.mts`/`.cts` + `DYNAMIC_IMPORT_FENCE`

### Tests
- `write-fence.test.ts` (+dynamic-import describe), `audit-gate.test.ts` (+6), `App.browserrouter.test.tsx`
- `test_rolling_kernel.py`, `test_rolling_risk.py`, `test_sharpe.py`, `test_snapshot.py`,
  `test_pacing_binder.py`, `test_scheduler.py`, `test_rolling_risk_pg.py`, `test_sharpe_pg.py`,
  `test_breach_lifecycle_pg.py`, `test_notification_pg.py`, `test_demo_stage9zzzzzzzz_sr1_pg.py`,
  `test_demo_stage9zzzzz_ops_pg.py`

### Governance
- **`docs/project_memory/claude_operating_instructions.md`** — SIX new standing sections (P1–P6)
- **`10_delivery_backlog/wave_13_close_review.md`** — NEW, stamped RATIFIED
- `10_delivery_backlog/delivery_roadmap.md` — Part 2.17 (Wave 14 RATIFIED) + amendment-log row
- `docs/project_memory/current_state.md` — CURRENT TRUTH 2026-07-29
- `05_analytics_methodologies/sharpe_v1.md`, `09_compliance_controls/control_matrix_skeleton.md`
- Six decision records retro-stamped CLOSED: `fe_m1`, `p2_7`, `p3_8`, `p3_c2`, `pm_1`, `td_1`
- `sr_1_decision_record.md`, `rm_1_decision_record.md`, `sch_2_decision_record.md`

### Memory (outside the repo)
- **Symlinked** the nested memory dir → the real one (68 files)
- Updated `ledger-class-omission-sweep.md` (proposal → RATIFIED pointer), `delivery-roadmap-state.md`,
  `MEMORY.md`, `commit-message-shell-safety.md` (heredoc addendum)

### Commits (branch `wave-13-close`, merged as PR #146 = `2411d00`)
`396d513` → `7b14264` → `4644226` → `4992f2e` → `ca55011` → `b131e89` → `866e10e` → `9c4a3e9` → `86c60ff`

---

## Key Exchanges

- **User caught a duplicate memory** I'd just written — `model-effort-recommendations.md` had existed
  since 2026-07-08 and was *stricter* than what I wrote (last sentence of EVERY response, exact
  effort vocabulary, plus a separate workflows yes/no signal). Investigating why it hadn't loaded
  found the split memory directory.
- **User asked "Are all of the issues going to be fixed?"** — answered yes for all 31, and flagged the
  6 thin-margin kills I would NOT accept on the fleet's word.
- **User switched to Fable 5 mid-session with "Double check your findings"** — the re-verification
  re-executed every committed claim from scratch and found the raw-pipes defect in my own stamps.
- **User asked whether workflows require extra-high effort** — they're bundled in the UI's
  `Ultracode - xhigh + workflows` option but available at any effort via explicit opt-in.

---

## Custom Notes

None.

---

## Quick Resume Context

**Wave 13 is CLOSED + RATIFIED and merged** (PR #146 = `2411d00`; merged-main CI run `30457408821`
green all six). The close's own P1 verify-on-main sweep ran clean on every clause. Counts unchanged
**25/40/133**, migration head `0055`, FE **32 files / 204 tests**.

**P1–P6 are now STANDING sections in `claude_operating_instructions.md`** (read-order item 1), so
they load automatically: six-ledger sweep + verify-on-main-after-last-merge; shared-tree mutation
rules; register-entries-are-claims; executed dry runs + the re-measure clause; assert-by-evidence
with positive controls; non-vacuity floors on enumerating guards.

**NEXT = Wave-14 planning: "real data through the governed rails"** (roadmap Part 2.17, direction
ratified, slicing not yet) — reference dimensions (sector/industry/country-of-risk), concentration
REQ-CRD-003, liquidity REQ-LIQ-001/002, the ENT-006 holiday calendar (dated forcing function:
**2027-05-31**), and rf-capture vendor diligence (a first-of-following-month series joins a month
late *undetectably* — the control is onboarding diligence, not code). Recommended: **Fable 5 · High ·
workflows: yes** (the two-lane pre-ratification verifier pass fans out by design). Start in a fresh
session — and note the memory symlink now means all 68 memories load correctly.

**The standing caution this close leaves behind:** the unit tier cannot see engine-typed defects, so
any column-type-sensitive guard belongs in the PG tier.

---
