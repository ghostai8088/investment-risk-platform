# Session Log: 01-08-2026 17:20 - cal1-ratified-cal1a-shipped-cal1b-convention-move

## Quick Reference (for AI scanning)

**Confidence keywords:** CAL-1, CAL-1a, CAL-1b, ENT-006, holiday calendar, XNYS, NYSE Rule 7.2,
Memorial Day 2027, calmath, BUSINESS_MONTH_END, migration 0059, holidays_complete_through,
period_key, partial unique, HOLIDAY_CALENDAR snapshot component, AD-014, perf.rolling_risk v2,
perf.sharpe v2, assumption literals, month_end_convention, declared_month_end_parameters,
grandfather parity, QS-11, CTRL-034, vendor diligence checklist, R-10/H-05, refresh_calendar_holidays,
add-only, demo stage 21, count pin 26/43/139, PR #159, PR #160, PR #161, autonomous merge,
pause-on-changed-recommendation, adversarial review, mutation proof, P4 dry run, Wave 14

**Projects:** investment-risk-platform (Wave 14, slice 3 = CAL-1)

**Outcome:** CAL-1 planned → ratified → split → CAL-1a shipped and closed (3 autonomous merges:
PRs #159/#160/#161); CAL-1b (the atomic holiday-convention move) fully implemented, adversarially
reviewed (1 BLOCKING / 4 HIGH / 7 MED / 7 LOW, all folded), `make check` green and the final
full-PG battery GREEN (2,909 passed) — the fold is gate-complete but uncommitted/unmerged.

## Decisions Made

- **CAL-1 RATIFIED (OQ-CAL-1-1…12, all as recommended; user "proceed" on the briefed gate).** The
  ratification included **CTRL-034's mint under H-05 approval** — a governance act the user had to
  perform, the first control mint since P0.5.
- **v2 = NEW version labels on the SAME model codes**, never an amend (no amend path exists in the
  registry). The convention is carried by **registrar-stamped assumption literals**
  (`month_end_convention=BUSINESS` + `holiday_calendar=XNYS`), parsed by a declared-parameters
  gate — absent ⇒ the implicit v1 grandfather, ambiguous/stray ⇒ fail-closed. **Not** label-parsed
  (the planning verifier refuted that framing).
- **A NEW cadence kind `BUSINESS_MONTH_END`** carries the scheduler side; `CALENDAR_MONTH_END` is
  grandfathered and live grids never move. Transition = pause-and-recreate (there is no RETIRED
  status; PAUSED is the platform's only retirement state).
- **AD-014-conformant reproducibility:** a `HOLIDAY_CALENDAR` snapshot COMPONENT_KIND pins the
  resolved holiday set into every v2 run. The pre-verifier draft had recommended the cheaper
  audit-trail-only option **without citing AD-014** — ruled BLOCKING and rebuilt.
- **A DB-grain period key** (`scheduled_run.period_key` + partial unique) is the double-fire
  backstop; the due-select month check is only the polite first layer. The draft's "closes
  structurally" claim was false under concurrency (three review lanes concurred).
- **CAL-1a/1b split taken** at the wave plan's ratified line: CAL-1a = dataset + refresh verb +
  the diligence control (no migration); CAL-1b = the atomic convention move (migration 0059).
- **The dataset is hand-encoded literals, never runtime-derived** — a naive observance rule
  fabricates holidays on real trading days (NYSE Rule 7.2).
- **P3-8 completeness + `RULE_TYPE_COMPLETENESS` re-deferred to DATA-1** (OQ-CAL-1-10).
- **New standing rule (user request):** pause when the next-step model/effort recommendation
  CHANGES from the previous one, so the user can adjust settings before work starts. Workflows
  need no pause (Claude controls those directly); model/effort are the user's `/model` setting.

## Key Learnings

- **A negative control must attack the LIKELY wrong input, and a fold is not folded until its own
  test passes.** A fold script aborted mid-way and silently LOST three edits that had been
  reported as applied; caught only because the fold's new tests ran immediately after.
- **NYSE Rule 7.2:** a Saturday New Year's Day is NOT observed on the preceding Friday when that
  Friday is a month-end — so 2027-12-31 and 2032-12-31 are TRADING days, 2028/2033 carry nine
  holidays, and a naive Sat→Fri encoding corrupts the month-end collision census from 4 to 6.
- **Two encodings agreeing is only as strong as their independence.** The census + an independent
  in-test derivation is the pair; an executed mutation check showed the census ALONE missed 5 of 6
  single-date perturbations.
- **A false "verified:" claim can ship inside a freshly-minted compliance artifact** — the CAL-1a
  checklist claimed no runtime reader of `calendar_holiday` existed; the calendar-detail endpoint
  reads it.
- **A security test can be satisfied by an EASIER refusal than the one it claims.** The PG
  cross-tenant test proved the parent-head UPDATE refusal, not the child WITH CHECK — a
  server-stamping regression would have passed it. Assert the refused TABLE by name.
- **A raw `ValueError` from a pure helper escapes every governed conversion boundary** unless each
  boundary converts it: it aborted all four tick phases for a tenant (the B3 class re-entered
  through a new door) and surfaced as a raw 500 in the binders.
- **Registers and records go stale in both directions** — the recon found ENT-006 already REALIZED
  (partial) with tables since 0008, and the ratified OQ text bound a CAL-1a verb to a CAL-1b column.
- **Half a lockstep move can ship untested:** Sharpe v2 had zero discriminating coverage (a
  threading-deletion mutant survived the whole unit tier AND the demo, whose book never diverges
  under holidays) while RM-1's side was genuinely mutation-hardened.
- **The demo battery is a first-class defect finder** — it caught `MultipleResultsFound` (two
  completed PORTFOLIO_RETURN runs exist in the demo tenant), a missing GRANT, and a new FK
  blocking another suite's cleanup, none of which any unit test could see.

## Solutions & Fixes

- **`_pm1_return_run_id`**: derive the return run from the v1 `RollingRiskResult` binding (not
  "any COMPLETED PORTFOLIO_RETURN run"), refusing loudly on an ambiguous baseline.
- **`current_tick`**: wrap the BUSINESS branch's calmath call in `try/except ValueError` →
  `ScheduleError`, restoring "every exit is a clean ScheduleError".
- **Both perf binders**: widen the alignment catch from `RollingKernelError` to `ValueError`
  (the former subclasses it) so an exhausted-month pin is a governed 422.
- **`parse_pinned_holidays`**: move the coverage parse INSIDE the malformed-content envelope.
- **Unconsumed-pin refusal**: a WEEKEND-convention run over a snapshot pinning a holiday calendar
  is refused in both binders (the rf leg's every-pin-consumed principle).
- **`_resolve_business_calendar`**: add the explicit own-OR-SYSTEM predicate (RLS alone left the
  refusal unenforceable on SQLite and under superuser PG).
- **`test_reference_pg`'s fixture**: clear calendar-bound schedules + children (under
  `session_replication_role = 'replica'`, since the P0001 trigger fires for superusers) before the
  calendar wipe — the new FK blocked it.
- **`test_scheduler_cadence_pg`**: add `calendar` to the constrained role's GRANT list.
- Two of my own test bugs: "latest event" ordered by UUID id (use `sequence_no`); a full
  `session.rollback()` discarding the test's own setup (use `begin_nested()`).

## Files Modified

### Created

- `packages/shared-python/src/irp_shared/calmath.py`: the pure leaf (zero irp_shared imports);
  empty set = v1 grandfather; fail-loud exhausted-month floor.
- `packages/shared-python/src/irp_shared/reference/xnys_holidays.py`: 118 hand-encoded XNYS dates
  2024–2035 + `XNYS_RULE_72_OPEN_FRIDAYS` + `XNYS_COMPLETE_THROUGH`.
- `packages/shared-python/src/irp_shared/perf/holiday_binding.py`: `parse_pinned_holidays`, shared
  by both binders.
- `packages/shared-python/src/irp_shared/demo/cal1b_stage21.py`: the demo stage at the real
  2027-05-28 boundary.
- `migrations/versions/0059_business_month_end.py`: the schedule FK, coverage column, period key +
  partial unique, widened cadence CHECKs.
- `09_compliance_controls/vendor_onboarding_diligence_checklist.md`: CTRL-034's artifact.
- `10_delivery_backlog/cal_1_decision_record.md`: Parts 0–9.
- Tests: `test_calmath.py`, `test_holiday_binding.py`,
  `test_demo_stage9zzzzzzzzzzzz_cal1b_pg.py` (twelve z).

### Modified (selected)

- `reference/calendar.py`: `refresh_calendar_holidays` (add-only, dedupe first-wins, forward-only
  coverage advance).
- `perf/bootstrap.py`: the v2 block (literals, gate, both v2 registrars).
- `perf/rolling_service.py` / `perf/sharpe_service.py`: version capture, declared-parameter parse,
  pin adjudication, threading, the widened catches, the unconsumed-pin refusal.
- `snapshot/service.py` + `models.py`: the 27th COMPONENT_KIND, the narrow serializer, both
  builders' `holiday_calendar_code`, the re-derive verify branch.
- `scheduling/service.py`, `events.py`, `models.py`; `apps/worker/src/irp_worker/scheduler.py`.
- Registers: ENT-006 (fully realized), REQ-SMR-004 (QS-11 DISCHARGED, both halves), REQ-PRF-002/003,
  control matrix (CTRL-034 + CTRL-003 disposition), audit taxonomy, `current_state.md`,
  `delivery_roadmap.md`, `05_analytics_methodologies/rolling_risk_v1.md` (v2 section), `ci.yml`.

## Setup & Config

- `gh` at `~/.local/bin/gh`; the autonomous pattern `gh pr create` → `gh pr checks --watch` →
  `gh pr merge --merge` executed three more times this session (#159, #160, #161 — seven total).
- Local PG: container `irp_pg_local`, `postgresql+psycopg://irp:irp@localhost:5432/irp`; schema
  reset before EVERY full-PG run (`DROP SCHEMA public CASCADE` + the four GRANTs + alembic upgrade).
- Migration head moved `0058` → **`0059_business_month_end`**; 21 head-pin assertions relayed;
  `test_synthetic`'s next-free-slot glob moved to `0060`.
- Demo count pin relayed `26/41/136` → **`26/43/139`** (MEASURED on a fresh battery).

## Pending Tasks

- **The final full-PG battery on the folded CAL-1b tree came back GREEN at session end: 2,909
  passed / 0 failed, alembic head clean** (`make check` also green). The fold is therefore
  gate-complete and UNCOMMITTED — the immediate next steps are: commit the fold, push `cal-1b`,
  open the PR, watch-then-merge, then the P1 verify-on-main sweep and the CAL-1b closeout row.
- After CAL-1b closes: **DATA-1** (the first genuinely external dataset, which re-executes the
  CTRL-034 checklist), then **LQ-1**.
- Carried to DATA-1 by ratification: `RULE_TYPE_COMPLETENESS` + the P3-8 trading-calendar wiring.
- Open anomaly (unchanged, from LIM-2): `test_limit_registry::test_only_concentration_is_dimensional_and_basis_bearing`
  failed twice under the full battery, never reproduced.

## Errors & Workarounds

- **`MultipleResultsFound`** in the demo stage (two completed PORTFOLIO_RETURN runs) → derive from
  the v1 rolling binding.
- **`ForeignKeyViolation`** on `test_reference_pg`'s calendar wipe (the new schedule FK) → clear
  bound schedules first under replica mode.
- **`InsufficientPrivilege`** on `calendar` in the cadence PG suite → add the GRANT.
- **Raw `ValueError` escaping** the poll loop and the binders → convert at `current_tick`, widen
  the binder catches.
- **Fold script aborted mid-way, losing three edits** silently → caught by running the fold's own
  tests immediately; recorded as a process near-miss in Part 9.
- **Mangled import blocks** from scripted multi-name import edits (three times) → fixed by hand;
  the pattern is fragile and worth avoiding.
- **A markdown-lint failure** (heading spacing, wrapped lines starting with `+`) and several E501s
  → `make format` plus targeted rewraps.

## Key Exchanges

- User: *"proceed"* on the CAL-1 gate → ratified all twelve OQs including the H-05 control mint.
- User: *"Can you add an operating rule to pause when the next suggested model, level of effort, or
  workflow usage changes from the previous? … Unless you are capable of changing those yourself."*
  → Saved as a standing memory; clarified that workflows ARE Claude's to control, model/effort are
  not, so only model/effort changes trigger a pause.
- User: *"Proceed as far as you can until you need my input"* → drove CAL-1a end-to-end and CAL-1b
  to the pre-push gate without further input.

## Custom Notes

None

---

## Quick Resume Context

CAL-1 is ratified and CAL-1a is closed (PRs #159/#160/#161, all merged autonomously). CAL-1b — the
atomic holiday-convention move — is fully implemented on branch `cal-1b` (commits `c741ace`,
`83acdd1`, `853e953`, `a6f2967` + an uncommitted review fold), `make check` green, with the
four-lane adversarial review folded (1 BLOCKING / 4 HIGH / 7 MED / 7 LOW). The only thing
outstanding is the final full-PG battery, then commit → push → PR → autonomous merge → P1
verify-on-main → the CAL-1b closeout row. NEXT SLICE after that: DATA-1.

---

## Raw Session Log

The full conversation is preserved in the session transcript at
`~/.claude/projects/-Users-andrewcox-Projects-investment-risk-platform-investment-risk-platform/70b746c9-a66f-4a2f-a168-ed3b64166457.jsonl`.
This session ran from the PERF-0/#158 close through CAL-1 planning, ratification, CAL-1a delivery
and closeout, and CAL-1b implementation + review fold; its decisions, learnings, fixes, files,
config, pending work and errors are captured in full in the sections above.
