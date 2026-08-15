# Session Log: 11-08-2026 09:24 - REPRO-2 part 2 shipped, RPT-3 complete, Wave-17 build complete

## Quick Reference (for AI scanning)

**Confidence keywords:** REPRO-2, RPT-3, Wave-17, CTRL-018, reproduction adapters, families.py,
PERF_RUN_TYPES, ROLLING_RISK, SHARPE, REPORT_FAMILIES, GenerateReport.tsx, run picker, wire
constants, report input refused, report provenance refused, carry (d), carry (f), carry (m),
demo stage 24, prove_reproduction.sh, mutation battery, R-D1..R-D7, R-E1, P14, P15, P18, P19,
different-engine review, fresh-context audit, vacuous assertion, subset vs containment,
REQ-RPT-001, requirements backbone, RTM, ultracode, workflows, verifier pass 1, verifier pass 2,
Fable usage limit, PRs #197 #198 #199 #200, merges 28-31

**Projects:** investment-risk-platform (multi-tenant governed investment-risk platform)

**Outcome:** Wave-17's build is COMPLETE — REPRO-2 (both parts) and RPT-3 shipped across four
merges (#197, #198, #199, #200), taking the reproduction control from 3 to 19 governed families
and making governed reports generable from a browser; next is the Wave-17 close review.

## Decisions Made

- **REPRO-2 was split into two parts, and part 1 shipped with the gap REPORTED rather than
  absorbed.** Sixteen adapters rushed produce exactly the defect the exclusion-truth obligation
  exists to catch; an absent family is visible in the coverage census, a wrong one is not.
- **`compared_fields` INVERTED to derived-from-the-model** (model columns minus what is explicitly
  excused). REPRO-1's hand-written lists silently omitted six governed columns; deriving makes
  that omission unrepresentable rather than merely detectable.
- **Four of REPRO-1's "not yet adapted" registry reasons were declared FALSE and corrected**, with
  the class recorded: a reason is prose until an adapter executes against it.
- **The exclusion-truth obligation discharged BY CONSTRUCTION** (zero discretionary exclusions),
  with a census that demands the ratified tamper proof the day one appears.
- **Demo stage 24 seeded LAST**, not inside `run_demo_campaign` — adding a schedule to a shared
  demo tenant changes what every subsequent tick does. No existing assertion was relaxed.
- **RPT-3 gate (4/4 as recommended):** extend `PERF_RUN_TYPES` (not a new route); REQ-RPT-001 →
  **In-Progress with the CREDIT family named** (Implemented would falsify the row's own title);
  **P15's different-engine review replaced for one slice by a fresh-context Opus audit** (Fable
  limit) with a binding condition; ratify + merge the record before implementation.
- **Carry (d) answered with VISIBILITY, not idempotency**; **carry (f) SURFACED, not paid**.
- **SHARPE deliberately NOT added to `PERF_RUN_TYPES`** — widening a listing on symmetry alone is
  how a closed set decays into a habit. Recorded drift with a trigger.

## Key Learnings

- **A subset assertion is not a containment assertion.** `returned_types <= PERF_RUN_TYPES` stays
  true when the set SHRINKS — the exact regression it claimed to catch — and the fixture made it
  `set() <= …`. Say what must be IN the set. Two documents claimed it was pinned.
- **A proof rewritten under review is the one most likely to be half-delivered.** Verifier pass 2
  rewrote proof 5 from `id` to `report_code` specifically to make it implementable; the
  implementable half is the half the build dropped.
- **Pass 2 finds its best work in pass 1's folds** — held for a fourth consecutive cycle. The
  rewritten refusal design was wrong AGAIN in a new way (one checklist under both constants); the
  "500+" honesty fix shipped a wrong number in the opposite direction.
- **An unreachable guard reads as protection and provides none.** Two replacement tests passed
  without killing their mutants because the guards were unreachable by contract.
- **An anchor is a claim about BYTES.** Anchors moved four times in REPRO-2 part 2 (formatter,
  dedupe, cross-module refactor); write them against the formatted bytes.
- **A stale image reproduces status codes and DB state perfectly.** `prove_reproduction.sh` had
  never rebuilt the backend; only the first assertion on a response BODY exposed it.
- **A verifier's LOW can be a real defect waiting.** Pass 2 predicted the Reports-screen stub
  breakage as LOW; it happened exactly.
- **The fresh-context same-engine audit did NOT return null** (2 HIGH, 4 MEDIUM, 5 LOW) — evidence
  it is worth running, explicitly NOT evidence it substitutes for a different engine.

## Solutions & Fixes

- Sixteen adapters in `reproduction/families.py`: one factory for thirteen standard-shape families,
  dedicated builders for ROLLING_RISK/SHARPE (window recovery) and PROXY_WEIGHT_ESTIMATE (dual
  binder by declared estimator convention + a derived target recovery).
- The shrinkage-target recovery moved to `residual_shrinkage_service.recover_shrinkage_target`
  when the import-direction fence refused `reproduction` importing `snapshot`.
- `_resolve_convention` maps `WrongModelVersionError → ReproductionUnsupported` (the reachable
  guard) after the battery proved the `else:` arm unreachable.
- `scripts/measure_sweep.py` — refuses to report a time for a sweep that judged nothing.
- Full-PG recipe: reset **+ `alembic upgrade head`**; skipping the migrate step produces ~281
  failures impersonating an RLS catastrophe.
- RPT-3: `Array.isArray` guard at the wire boundary; a wrong shape costs a LABEL, not the screen.
- The carry-(f) staleness binding reads `rpt_2_slice_record.md` by walking UP for the repo root
  (cwd-insensitive) — two pre-existing fence tests fail when vitest runs from the repo root.

## Files Modified

- `packages/shared-python/src/irp_shared/reproduction/families.py`: NEW — the sixteen adapters.
- `packages/shared-python/src/irp_shared/reproduction/registry.py`: eager install; census 19+2.
- `packages/shared-python/src/irp_shared/risk/residual_shrinkage_service.py`: `recover_shrinkage_target`.
- `packages/shared-python/src/irp_shared/demo/repro2_stage24.py` + `campaign.py`: demo stage 24.
- `packages/shared-python/src/irp_shared/perf/queries.py`: `ROLLING_RISK` → `PERF_RUN_TYPES`.
- `apps/frontend/src/views/ops/Reproduction.tsx` (+ test): the reproduction ops screen.
- `apps/frontend/src/views/reports/GenerateReport.tsx` (+ test): the generate flow, 16 tests.
- `apps/backend/src/irp_backend/api/schedule_admin.py`: `ScheduleOut` → `ScheduleWriteOut`.
- `infra/deploy/prove_reproduction.sh`: second-tenant discovery arm; `backend` added to the build.
- `02_requirements/requirements_backbone.md` + `requirements_traceability_matrix.md`: REQ-RPT-001.
- `scripts/mutants.toml`: groups `repro-2b` (7) and `rpt-3` (1).
- Records: `repro_2_slice_record.md`, `rpt_3_decision_record.md`, `rpt_3_slice_record.md`,
  `delivery_roadmap.md`, `ops_h1_decision_record.md`, `claude_operating_instructions.md`.

## Setup & Config

- Fable 5 usage limit reached mid-session; resets ~2026-08-14. Opus 5 [1m] for the remainder.
- 22 of 33 pass-2 workflow agents died on that limit; findings recovered from
  `subagents/workflows/<run>/journal.jsonl` and hand-verified.
- Local PG: `irp_pg_local`, `postgresql+psycopg://irp:irp@localhost:5432/irp`, env var
  `IRP_TEST_DATABASE_URL`. Superuser is `irp`, not `postgres`.
- Killed a runaway pytest (PID 35932) idle since 2026-08-03 at 100% CPU on the user's MacBook Pro.
- CI watch is a plain shell poll — no model tokens while it runs (asked and answered this session).

## Pending Tasks

- **The Wave-17 close review** — needs `proceed ultracode` (multi-lens fan-out; Wave-16's close is
  the pattern). All four Wave-17 slices are merged.
- TS→7 rides its mechanical trigger (both peer tools declaring TS-7 support).
- Carries unpulled with triggers: (c)/(h) real-browser E2E, (d) generate idempotency, (f) upstream
  VaR scope propagation, SHARPE's listing entry, CONCENTRATION/LIQUIDITY reproduction.
- Two pre-existing cwd-sensitive fence tests (`router-fence`, `write-fence`).

## Errors & Workarounds

- **Full-PG red (281 failed)** — my own skipped `alembic upgrade head`. Recorded in memory.
- **Deploy proof failed 3×**: guessed SYSTEM tenant literal; undefined `ANCHOR_DATE` (caught by
  `set -u`); stale backend image. All caught by EXECUTING, not reading.
- **`families.py` duplicated 527 lines** from a `cat >>` plus a python insert; deduplicated after
  an exact-block comparison.
- **Battery survivors**: 5 first run, then 2 replacement tests passing without killing, then a
  third targeting `cohort[0]` where wrong and right answers coincide.
- **Demo seeding broke stage 15** (two dispatches where it asserts one) → moved to stage 24.
- **CI-parity gate** refused the new PG suite until CI actually ran it.
- **Classifier blocked two compound git commands**; retried as single commands.

## Key Exchanges

- User asked whether the CI watch consumes Fable tokens in the background — it does not; tokens are
  spent only at turn boundaries when a completion notification re-invokes the model.
- User asked whether "ultracode" needs the Effort slider changed — no: Effort is per-call reasoning,
  the keyword is the multi-agent opt-in; their own question demonstrated the keyword working.
- User asked which machine had the runaway process — their MacBook Pro, PID 35932, ~7,510 CPU-minutes
  since Aug 3, killed.
- User reported the Fable limit and switched to Opus for the remaining four days.

## Custom Notes

None

---

## Quick Resume Context

Wave 17's build is COMPLETE: ONBOARD-1, ALERT-1, REPRO-2 (parts 1 and 2) and RPT-3 are all merged
(#191–#200; the last four merges this session were #197, #198, #199, #200), every one verified on
main with main CI green. CTRL-018 now checks 19 governed families instead of 3, and governed
reports are generable from a browser. The immediate next step is the **Wave-17 close review** — a
fresh-context multi-lens sweep, then a close fold, then a gate — which needs `proceed ultracode`.
Fable is unavailable until ~2026-08-14, so P15's different-engine review has a ratified
single-slice substitute (fresh-context same-engine audit) whose limits are recorded rather than
glossed.

---

## Raw Session Log

The authoritative turn-by-turn transcript for this session is the Claude Code JSONL at:

`~/.claude/projects/-Users-andrewcox-Projects-investment-risk-platform-investment-risk-platform/70b746c9-a66f-4a2f-a168-ed3b64166457.jsonl`

It is deliberately referenced rather than reproduced here, on the same ground as the six prior
session logs: writing a "verbatim" transcript from memory would fabricate a record, and this
session's recurring subject was precisely that failure class — a test named for a proof it did not
deliver, a subset assertion described as a containment pin, a registry reason that read well and
was false about its own binder, and a module documenting false prose that shipped false prose as
its own header. A pointer to the real artifact is worth more than a plausible reconstruction.

### Chronology (merge by merge)

1. **#197 = `80e6b9f`** (28th) — REPRO-2 part 1: registry-driven tenant discovery, the schedule
   write path, the verdict read. Different-engine review (Fable) found 6; CI found a 7th (a
   superseded test passing through a different refusal that shares exit code 2).
2. **#198 = `4908b65`** (29th) — REPRO-2 part 2: sixteen adapters (census 3+18 → 19+2), demo stage
   24, the deployed second-tenant discovery arm, the `/ops/reproduction` screen. Sweep measured on
   the real demo book: 18/18 MATCH, 149 rows, 1.99s vs a 5-minute split trigger. Review found 3.
3. **#199 = `341e3e0`** (30th) — RPT-3 planning: two adversarial passes, 66 findings; gate ratified
   4/4 as recommended.
4. **#200 = `3bccce0`** (31st) — RPT-3 implementation + the fresh-context audit fold.
