# P3-C2 Implementation Plan — Hardening / Consolidation (Wave-1 slice 3)

> Build contract for P3-C2 (decisions: `p3_c2_decision_record.md`, OD-P3-C2-A…F; gated on OQ-P3-C2-1…6).
> NO migration; NO new permission/audit code/entity/number. Planned against HEAD `440f868`.

## Step 1 — Exposure scaffold + `failure_reason` adoption (OD-B) — golden-capture FIRST
1. **Golden capture (written GREEN before the refactor):** `test_p3c2_exposure_scaffold_preservation.py` —
   capture the COMPLETED-path audit-event sequence (ordered `(event_type, action, outcome)` by `sequence_no`),
   the ORIGIN edges (per-row, run-stamped), and the DQ evidence for a governed exposure run; capture the
   FAILED-path audit sequence + the reason string. Assert them against the CURRENT `run_exposure` so the capture
   is proven accurate.
2. **Refactor** `run_exposure`: replace the hand-rolled create→RUNNING→build→gate→[FAILED|rows+ORIGIN+COMPLETED]
   tail with `execute_governed_run(session, …, model_version_id=None, run_type=RUN_TYPE_EXPOSURE_AGGREGATE,
   rule_code/name/target=the exposure completeness descriptors, result_entity_type="exposure_aggregate",
   compute=_compute, format_reason=lambda gate, gaps: str(gate))`. The `_compute(run)` closure calls
   `_read_components` + `_build_rows` (which needs `run`) and returns `(rows, gaps)`. Delete the now-dead
   `_run_completeness_gate` (its descriptors move to the call site — verify character-identical to the risk
   binders' pattern).
3. **Re-run the golden capture**: COMPLETED path byte-identical; FAILED path NOW additionally (a) persists
   `failure_reason` on the run row and (b) carries the snapshot→run DEPENDS_ON edge — assert BOTH new behaviors
   explicitly (the two intended improvements) while everything else matches the capture.
4. **Endpoint** `apps/backend/src/irp_backend/api/exposure.py`: `GET /exposure/runs/{run_id}` surfaces
   `failure_reason=run.failure_reason` (was hardcoded None — the P3-C1 GET-endpoint pattern).

## Step 2 — Exposure runs in the FE listing (OD-C)
5. **`packages/shared-python/src/irp_shared/exposure/queries.py`** (NEW): `list_exposure_runs(session, *,
   acting_tenant, status=None, limit=50, offset=0)` — the `list_risk_runs` mirror, fenced to
   `run_type == RUN_TYPE_EXPOSURE_AGGREGATE` ONLY; same `RiskRunQueryError`-class refusal (a new
   `ExposureRunQueryError`), same `created_at DESC, run_id` order, same caps. Explicit tenant predicate + RLS.
6. **`GET /exposure/runs`** (exposure router, gated `exposure.view`): the `RiskRunListOut`-shaped response;
   `ExposureRunQueryError` → 422 via the shared `deps.map_refusal`.
7. **Frontend** (`apps/frontend/src`): the runs list fetches `/risk/runs` AND `/exposure/runs`, merges by
   `created_at DESC` (client-side stable sort), and adds `exposure` to `FAMILIES` + `RUN_TYPE_TO_FAMILY` +
   `FAMILY_ROW_COLUMNS` (the `exposure_aggregate` row shape: portfolio/instrument/exposure_type/signed_quantity/
   mark_value/fx_rate/exposure_amount — decimals as strings, verbatim). The run-detail route serves the exposure
   family via `GET /exposure/runs/{id}`. A `/exposure/runs` 403 (no `exposure.view`) is caught and the exposure
   rows simply omitted (the risk list still renders) — NOT a hard failure of the page.
8. **Tests:** backend `test_exposure_runs_list_endpoint.py` (mirror `test_risk_runs_list_endpoint.py`: tenant
   separation, the EXPOSURE_AGGREGATE fence — a VAR run never appears, 422 filters, 403 without `exposure.view`,
   pagination determinism); frontend vitest (exposure rows merged + ordered; the 403-omits-gracefully path; the
   exposure detail table renders decimals verbatim).

## Step 3 — Captured-input `PreciseDecimal` parity (OD-D)
9. Convert the ten columns (OD-D list) from `Numeric(p,s)` to `PreciseDecimal(p,s)` in
   `position/valuation/marketdata/reference` models. `coupon_rate(12,6)` untouched.
10. **`alembic check` MUST stay a no-op** (assert in the run): PreciseDecimal → `NUMERIC(p,s)` on PG is
    byte-identical DDL. If `alembic check` reports drift, STOP — the type is not rendering identically and the
    scope assumption is wrong.
11. **Tests:** extend the existing per-table suites with a bind/result roundtrip at a float53-UNSAFE value (e.g.
    a 17-significant-digit quantity) proving SQLite now preserves it exactly (was lossy pre-conversion); a
    type-fence test asserting each converted column's SQLAlchemy type is `PreciseDecimal`.

## Step 4 — DQ-rule race (OD-E)
12. `dq/gates.py::ensure_presence_rule`: on SELECT-miss, `try: with session.begin_nested(): rule =
    register_dq_rule(…)` / `except IntegrityError: session` rolls back to the savepoint and re-SELECTs (returns
    the peer's committed rule). Preserve the exact return type + audit semantics on the WINNING branch.
13. **Test** (`test_p3c2_hardening.py`): simulate the race deterministically — pre-insert the rule in a nested
    savepoint from a second identity, then call `ensure_presence_rule` and assert it RESOLVES (no IntegrityError
    escapes) and returns the existing rule; assert the losing-branch audit row does NOT survive (savepoint
    unwind). PG-only concurrency proof if feasible; otherwise the deterministic savepoint simulation + a note.

## Step 5 — Validate + review
14. `make check`; full-PG suite (clean schema reset) + `alembic check` no-op + downgrade smoke (head stays
    `0028`); the frontend suite (lint/typecheck/format/test/build). Diff-fence: no migration file, no
    `audit/service.py` change, no new permission.
15. The 6-finder review (line-scan / governance-tenancy / cross-file / exposure-lifecycle-preservation /
    concurrency+precision numeric / test-quality) → fold → HOLD Tier-2 commit approval.

## Definition of done
`run_exposure` on the shared scaffold with FAILED runs persisting reasons + keeping DEPENDS_ON (golden-proven
otherwise-identical); exposure runs listable via `exposure.view` and visible in the FE view (risk list unaffected;
permission separation intact); every ≥16-digit captured decimal column exact on both engines with `alembic check`
a no-op; the DQ-rule race resolves cleanly under a savepoint with no dangling audit; all gates green; 6-finder
review folded.
