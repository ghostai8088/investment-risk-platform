# BT-1 Implementation Plan — VaR backtesting (the 8-step build contract)

> Executes ONLY on explicit direction after `bt_1_decision_record.md` OQ ratification. Branch
> `bt-1-impl` off `main`; lands via the PR flow (Claude pushes, the USER opens+merges after CI
> green). Every step ends with `ruff format` + `ruff check` on the touched files (the CI #136
> lesson); fixtures TD-1-realistic; dedup-by-default (the clean-code standing bar).

## Step 0 — Branch + pre-checks

`git checkout -b bt-1-impl` off the current `main`; confirm migration head `0032_benchmark_relative`,
CI green, working tree clean. Verify the frozen-file fence targets untouched throughout.

## Step 1 — Pure kernel: `risk/var_backtest_kernel.py`

- `exception_indicator(realized_pnl, var_value) -> int` — `1` iff `−realized_pnl > var_value`
  (STRICT, OD-F); pure Decimal.
- `kupiec_lr(n, x, coverage_p) -> Decimal` — the POF statistic at 50-digit context, quantize
  HALF_UP to 12dp internally (stored at the OQ-6 scale by the binder); the `x=0`/`x=N` edges under
  the `0⁰=1` convention (drop the vanishing terms analytically, no `ln(0)`); raises on `n < 1`,
  `x > n`, `coverage_p` outside (0, 1). Decimal `ln` at prec 50.
- `kupiec_decision(lr, alpha) -> str` — REJECT / FAIL_TO_REJECT against the FIXED χ²(1) criticals
  `{0.05: 3.841459, 0.01: 6.634897}`; unknown alpha raises (the registrar constrains upstream).
- `basel_zone(n_exceptions) -> str` — GREEN 0–4 / YELLOW 5–9 / RED ≥10 (the caller enforces the
  (0.99, 250) domain; the kernel is the pure table).
- **Goldens INDEPENDENTLY cross-checked** (float `math.log`, verified at plan time — N=250,
  p=0.01: x=5 → LR ≈ 1.9568 FAIL_TO_REJECT at 0.05; x=10 → LR ≈ 12.9555 REJECT; x=0 → LR ≈ 5.0252,
  which REJECTS at 0.05 — POF is TWO-SIDED, too FEW exceptions also rejects; a test pins that
  behavior explicitly). `VarBacktestKernelError(ValueError)`.

## Step 2 — Registrar + methodology doc

`risk/bootstrap.py`: `register_var_backtest_model` via the established risk-registrar shape —
`risk.var_backtest` / "VaR backtesting (exception count, Kupiec POF, Basel zone, v1)" / model_type
`VAR_BACKTEST` / label `v1` + the DECLARED `alpha` parameter (the P3-5 declared-parameter identity:
same label + different alpha or code_version ⇒ 409). Assumptions + limitations tuples mirror the
decision record Parts 1+3. Methodology doc
`05_analytics_methodologies/var_backtesting_v1.md` with the seven required sections.

## Step 3 — Snapshot support

`snapshot/models.py`: `PURPOSE_VAR_BACKTEST_INPUT` + `COMPONENT_KIND_VAR`.
`snapshot/serialize.py`: `var_result_content(row)` — the full immutable `var_result` column set
(scales: `var_value`/`sigma` `_SCALE_MONEY(6)`, `confidence_level` 4dp, `z_score` 12dp).
`snapshot/service.py`: `build_var_backtest_snapshot(session, *, acting_tenant, actor,
portfolio_return_run_id, var_run_ids)` — pins ALL rows of the return run (REUSE
`_list_portfolio_return_rows` + `portfolio_return_content` from P3-8) + ALL `var_result` rows of
each listed VaR run (models-only risk read); `VAR_BACKTEST_BINDING_PREDICATE` registered; new
`_reresolve_content` branch for `COMPONENT_KIND_VAR`; `VarBacktestSnapshotError` in the verify
except-tuple. Fails closed BEFORE any write on an empty side.

## Step 4 — Migration `0033_var_backtest` + ENT-055 ORM

`risk/models.py`: `METRIC_TYPE_EXCEPTION_INDICATOR` / `_EXCEPTION_COUNT` / `_KUPIEC_LR` /
`_BASEL_ZONE` + `VarBacktestResult`: NOT-NULL FKs (calculation_run_id, input_snapshot_id,
model_version_id, portfolio_return_run_id → `calculation_run.run_id`, portfolio_id); `metric_type`
String(30); `period_start`/`period_end` Date; `metric_value` Numeric(28,6) (OQ-6);
`realized_pnl`/`var_value` Numeric(28,6) NULLABLE echoes; `n_pairs`/`n_exceptions` Integer;
`confidence_level` Numeric(6,4); `horizon_days` Integer; `var_metric_type` String(30) (which method
was backtested); `test_decision` String(20) NULLABLE; `basel_zone` String(10) NULLABLE;
`base_currency` String(3); UNIQUE `(calculation_run_id, metric_type, period_start)`; ORM
before_update/before_delete guard; aggregator registration. Migration `0033`: table + indexes +
FKs + symmetric FORCE RLS + P0001 trigger; **assert every identifier ≤ 63 chars in-plan** (short FK
names from the start — `fk_var_backtest_result_portfolio_return_run` style); single head; SQLite
build + local-PG upgrade/downgrade smoke 0033↔0032 before proceeding.

## Step 5 — Binder: `risk/var_backtest_service.py`

`run_var_backtest(session, *, acting_tenant, actor, code_version, environment_id,
model_version_id, portfolio_return_run_id=None, var_run_ids=None, snapshot_id=None)`; the
`execute_governed_run` scaffold. Pre-create adjudication (BOTH paths, pinned-JSON only — NO perf
import; fence-kept LOCAL `_RETURN_RUN_TYPE="PORTFOLIO_RETURN"` + sync test):

- return side: DIETZ rows present, single run/portfolio/base, CONTIGUOUS ordered sub-periods,
  exactly one TWR_LINKED + exact-linkage cross-check (the P3-8 gates, reused shape);
- VaR side: ≥1 row, uniform `metric_type`/`confidence_level`/`horizon_days`/`base_currency` ==
  return base; no duplicate `window_end`;
- ALIGNMENT (OD-E): every VaR row pairs to exactly one DIETZ sub-period
  (`period_start == window_end`, `period_end == period_start + horizon_days` calendar days);
  ANY unpaired forecast ⇒ refuse; realized periods used at most once;
- identity (OD-H): each VaR row's `exposure_run_id` re-resolved under tenant; its
  `exposure_aggregate.portfolio_id` (models-only read) == the pinned return `portfolio_id`;
  portfolio + return-run + model FK targets re-resolved under tenant (P3-5);
- the TypeError-inclusive malformed-pin wrapper (P3-C3).
Compute: per-pair indicators + count + `kupiec_lr` + decision (+ zone iff (0.99, 250)); the
magnitude gate covers EVERY persisted Numeric column — `metric_value` AND the `realized_pnl`/
`var_value` echoes (`_MAX_RESULT_ABS = 1E21` against the Numeric(28,6) `1E22` ceiling — the P3-8
HIGH-fold lesson, one order inside). Post-create FAILED on a gate trip; list/resolve functions with
explicit tenant predicates.

## Step 6 — API + FE

`api/risk.py` (or the runs router the risk families share): POST `/risk/models/var-backtest`,
POST `/risk/var-backtests/runs`, GET `/risk/var-backtests/runs/{id}`, GET
`/risk/var-backtests/{result_id}` — gated `risk.run`/`risk.view`; error map += the new
input/snapshot errors (422/409/404 per the P3-8 uniform-422 convention — an unknown `var_run_id`
or `portfolio_return_run_id` in the body is a 422 refusal, not a 404). Fixed-point serialization.
FE: `types.ts` family `var-backtests` (runType `VAR_BACKTEST`, permissionFamily `risk`) +
`RUN_TYPE_TO_FAMILY` + `runDetailUrl` + `FAMILY_ROW_COLUMNS` (metric/period/value/realized_pnl/
var_value/decision/zone/n_pairs); `RunsList` filter set; vitest additions.

## Step 7 — Docs

Canonical registry ENT-055 row (+ ENT-053/ENT-027-VaR consumer notes); backbone + RTM: REQ row
under the risk/validation capability (CAP-1/CTRL-018 outcomes-analysis leg) marking SR 11-7
outcomes analysis first-executable; audit taxonomy: NO new code (CALC.RUN_* reuse) — note only;
entitlement SoD: `risk.*` REUSE note citing the parity test; roadmap left for closeout.

## Step 8 — Tests + ci.yml (SAME commit)

`test_var_backtest.py` (SQLite): kernel goldens + independent float cross-check; full-stack
build+consume goldens over BOTH VaR methods (two runs); alignment refusal battery (unpaired
forecast, duplicate window_end, horizon mismatch, gap/overlap, foreign portfolio, currency
mismatch, mixed methods); conditional emission (zone only at (0.99, 250); decision at both alphas);
TR-09 (a VaR re-run + a return re-run cannot move a historical backtest); magnitude/echo-gate
FAILED runs; append-only; run_type≠metric; migration head; fence sync (`_RETURN_RUN_TYPE`);
`risk.*` permission-parity (no new codes); methodology-doc sections.
`test_var_backtest_pg.py`: RLS visibility / no-context zero rows / forged-tenant 42501 / P0001
trigger / closed hybrid set / cross-tenant snapshot consume / audit chain — + the ci.yml PG step in
the SAME commit. Endpoint tests mirroring the P3-8 file. FE vitest. TD-1 realism throughout
(economically plausible VaR magnitudes vs MVs; extremes only in labeled boundary tests).

## Then

Unreduced validation (make check + full local-PG + downgrade smoke + fe-check + diff fence) →
FULL review (OQ-9 mode) → fold → revalidate → push `bt-1-impl` → USER opens+merges the PR →
closeout PR (docs + memory + any fold-deferred items recorded).
