# P3-C1 Implementation Plan — Hardening / Consolidation Slice

> **Status: PLAN RATIFIED (OQ-P3-C1-1…8 approved 2026-07-07); implementation is a SEPARATE approval.**
> Decision basis: `p3_c1_decision_record.md` (OD-P3-C1-A…H). Exemplar: the P3-4-R0
> behavior-preserving refactor (`a9b6567`) for the extraction discipline.

## Part 0 — Preconditions
P3-1…P3-5 CLOSED and CI-green (head `0026_var`, #103). No new number ships here; the slice is one commit
(no pre-step needed — the extraction IS the slice).

## Part 1 — Module map
- `packages/shared-python/src/irp_shared/risk/bootstrap.py` — `assert_model_version_of` gains the
  `status == "REGISTERED"` check (→ `UnregisteredModelError`).
- `packages/shared-python/src/irp_shared/model/models.py` — the `status` comment updated (enforcing at the
  RISK bind since P3-C1; still not a validation gate).
- `packages/shared-python/src/irp_shared/calc/models.py` + `calc/service.py` — additive
  `CalculationRun.failure_reason` (Text, nullable) + `update_run_status(..., failure_reason=None)` (sets the
  row field on any terminal transition when provided; audit payload UNCHANGED).
- `migrations/versions/0027_run_failure_reason.py` — `ALTER TABLE calculation_run ADD COLUMN failure_reason
  TEXT` (nullable; additive; the `environment_id` precedent; downgrade drops it).
- NEW `packages/shared-python/src/irp_shared/risk/scaffold.py` — `execute_governed_run(...)`: the shared
  lifecycle tail (create_run → RUNNING → DEPENDS_ON → compute callback → presence-gate → FAILED[+persisted
  reason] | write rows + per-row ORIGIN + COMPLETED), parameterized by run_type, DQ rule descriptor, compute
  callback (pins in → rows+gaps out), reason formatter (each binder's format VERBATIM), and result entity
  type. Consumed by `risk/service.py`, `risk/factor_service.py`, `risk/covariance_service.py`,
  `risk/var_service.py` — their pre-create gates/adjudication stay in place; only the tail is replaced.
  **Escape hatch (OD-P3-C1-D): any binder whose exact behavior cannot be preserved is left untouched and the
  divergence recorded.**
- `risk/models.py` + `exposure/models.py` — the seven column conversions to `PreciseDecimal` (NO migration;
  PG DDL identical).
- `apps/backend/src/irp_backend/api/risk.py` (+ any sibling using `_ERROR_MAP`) — `_map_error(exc)` MRO
  helper replacing the ten exact-type lookups; the four GET-run endpoints surface `run.failure_reason`.
- The five binders — the ambiguous-input (both-modes) refusal; `factor_service._adjudicate_pins` — the
  base-uniformity check.

## Part 2 — Behavior-preservation contract (the R0 bar)
- The FULL existing suite passes with changes ONLY where a test asserted the old gap itself (the hardcoded
  `failure_reason=None` reads; the silent both-modes preference).
- For each of the four binders: an identical-input run produces the identical audit-event sequence, lineage
  edges, DQ rows, and result rows before/after the extraction (spot-asserted per binder in the new tests).
- The tightenings (status-bind, both-modes, base-uniformity) are each proven by a NEW negative test and are
  pre-create refusals (zero run/rows/audit).

## Part 3 — Tests
1. **Status-bind:** a `status=None` version minted via the generic registration is refused by ALL FOUR risk
   binders (`UnregisteredModelError`, zero runs) and by each run endpoint (422); the governed registrars'
   versions still bind (REGISTERED).
2. **failure_reason:** for each of the four binders, drive the existing FAILED path → POST returns the reason
   AND a subsequent GET run returns the SAME string (not None); COMPLETED runs read None; the audit
   `CALC.RUN_STATUS_CHANGE` payload shape is UNCHANGED (asserted).
3. **Scaffold preservation:** per binder, one COMPLETED and one FAILED scenario asserting the exact
   event-type sequence + lineage-edge set + reason format equals the pre-extraction shape (golden
   assertions written from the CURRENT behavior before refactoring).
4. **PreciseDecimal parity:** >float53 values roundtrip exactly through each converted column on SQLite
   (write→expire→re-read equality); `alembic check` stays clean on PG (CI).
5. **_map_error:** a subclass of a mapped exception maps to the parent's status (unit test); all existing
   endpoint refusal tests unchanged.
6. **Ambiguous input:** each of the five binders refuses both-modes input (422 at the endpoint; zero writes).
7. **Mixed-base probe:** a hand-minted FACTOR_EXPOSURE_INPUT snapshot with mixed-base atoms refuses
   pre-create (the P3-3 adjudication addition).
8. **Fences/heads:** migration head `0026_var` → `0027_run_failure_reason` flips (8 files + synthetic glob
   0027→0028); the runtime-numpy fence population still passes; no new permission codes.

## Part 4 — Acceptance criteria
- Full suite + full-PG cycle green; `alembic check` clean; downgrade smoke green (0027 downgrade drops the
  column cleanly).
- Zero behavior change on governed COMPLETED paths except: FAILED reasons persist + surface on read; the
  three tightenings refuse what they document; subclassed refusals map instead of 500ing.
- `audit/service.py` untouched; no new permission/audit code/entity; the deferral register SHRINKS by the
  items landed and RECORDS the two follow-ups (captured-table parity; exposure scaffold).

## Part 5 — Review log
Shared with `p3_c1_decision_record.md` Part 5 (single-pass). The implementation gets the independent-context
adversarial review (the plan-Part-6 gate below).

## Part 6 — Implementation kickoff prompt (when approved)
STEP P3-C1: build EXACTLY per `p3_c1_decision_record.md` (OD-P3-C1-A…H) + this plan. Golden-capture the four
binders' current sequences FIRST, then extract. Validate (full suite + full-PG + migration cycle + drift +
downgrade smoke), run the independent-context adversarial review, fold, HOLD the commit for explicit approval
(Tier 2). Then push + CI-watch + the Tier-0 closeout.
