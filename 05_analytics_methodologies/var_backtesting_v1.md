# VaR backtesting v1 (`risk.var_backtest`)

> BT-1 (ENT-055 `var_backtest_result`) — the NINTH governed number. Registered model
> `risk.var_backtest` v1 with the DECLARED Kupiec significance level `alpha` (the P3-5
> declared-parameter identity). The platform's first executable SR 11-7 "outcomes analysis".

## Purpose & applicability

Accountability for the shipped VaR numbers: line each historical VaR forecast up against the
realized flow-adjusted P&L of the SAME portfolio over the SAME horizon, count the exceptions
(losses exceeding VaR), and judge the count with the standard minimal battery — the Kupiec (1995)
proportion-of-failures coverage test and the Basel (BCBS January 1996) traffic-light zone.
Applies to ONE VaR method per run (`VAR_PARAMETRIC` xor `VAR_HISTORICAL`); comparing methods is
two runs side by side. This is model-risk monitoring evidence, not a capital calculation.

## Inputs & data policy

- **Realized side:** ONE COMPLETED `PORTFOLIO_RETURN` run (PM-1). Per pinned `DIETZ_PERIOD` row:
  `P&L_i = end_mv − begin_mv − net_external_flow` (the flow-adjusted ACTUAL-P&L leg). The pinned
  rows must be a well-formed PM-1 output: one run/portfolio/base, CONTIGUOUS ordered sub-periods,
  exactly one `TWR_LINKED` row (a shape check), and the **MV-CHAIN integrity gate** —
  `begin_mv_{i+1} == end_mv_i` (the same boundary valuation appears on both sides of a well-formed
  PM-1 output), adjudicating exactly the columns the P&L consumes. (The plan's exact-linkage
  cross-check was consciously replaced — recomputing the geometric link needs perf's compounding
  kernel and NOTHING imports perf; see `bt_1_decision_record.md` Part 5.5.)
- **Forecast side:** N ≥ 1 COMPLETED `VAR` runs' pinned `var_result` rows — uniform `metric_type`,
  `confidence_level`, `horizon_days`, and `base_currency` (== the return run's base). No duplicate
  `window_end`.
- **Alignment (all-or-nothing):** each VaR forecast applies as of its `window_end`; it pairs with
  EXACTLY the DIETZ sub-period where `period_start == window_end` and
  `period_end == period_start + horizon_days` CALENDAR days. ANY unpaired forecast refuses the
  whole run pre-create. NO imputation, no silent partial pairing.
- **Identity:** every VaR row's `exposure_run_id` (the P3-5 column names the consumed
  FACTOR-EXPOSURE run) must resolve (acting tenant) to `factor_exposure_result` rows of the SAME
  `portfolio_id` the return run measured — backtesting portfolio A's VaR against portfolio B's
  returns refuses.
- All reads are the SNAPSHOT'S PINNED CONTENT (`PURPOSE_VAR_BACKTEST_INPUT`:
  `COMPONENT_KIND_PORTFOLIO_RETURN` + `COMPONENT_KIND_VAR`) — never a live result read (AD-014;
  TR-09: a later re-run of either side cannot move a historical backtest).

## Formulas & numerical standards

- Exception: `e_i = 1` iff `−P&L_i > VaR_i` — STRICT (a loss exactly AT VaR is not an exception).
- Kupiec POF: `LR = −2 ln[(1−p)^(N−x) p^x] + 2 ln[(1−x/N)^(N−x) (x/N)^x]` with
  `p = 1 − confidence_level`, `N` pairs, `x` exceptions; asymptotically χ²(1); TWO-SIDED (too few
  exceptions also rejects). The `x=0`/`x=N` edges drop vanishing terms analytically (`0⁰ = 1`).
- Decision: `REJECT` iff `LR >` the FIXED χ²(1) critical value for the declared alpha
  (`0.05 → 3.841459`, `0.01 → 6.634897`). NO p-value/erf at runtime — Decimal-pure.
- Basel zone: GREEN 0–4 / YELLOW 5–9 / RED ≥ 10, emitted ONLY when `confidence_level == 0.99` AND
  `n_pairs == 250` AND `horizon_days == 1` (the table is defined over 250 ONE-DAY observations) —
  never scaled or extrapolated.
- Decimal at 50-digit context (`Decimal.ln`); the LR quantized HALF_UP to 12dp internally, then
  HALF_UP to the stored `Numeric(28,6)` scale — and **the decision is taken on that STORED 6dp
  value against the 6dp critical**, so a persisted row always reproduces its own decision (a
  knife-edge LR within ~5e-7 of a critical follows the stored value). P&L/VaR echoes at the money
  6dp scale (the VaR echo re-quantized at parse — also the NaN gate).

## Assumptions

Mirrored into `model_assumption` rows at registration (see
`risk/bootstrap.py::VAR_BACKTEST_ASSUMPTIONS_BASE` + the declared `alpha=` row). The declared
alpha is part of the version identity: same label + a different alpha (or `code_version`) is a
governed 409; the vocabulary is exactly the fixed critical set.

## Validation / reproduction tests

- Kernel goldens INDEPENDENTLY cross-checked against stdlib float `math.log` (≤ 1e-9): N=250,
  p=0.01 → x=5: LR = 1.956809788231 (FAIL_TO_REJECT @ 0.05); x=10: LR = 12.955491062356 (REJECT);
  x=0: LR = 5.025167926751 (REJECTS — the two-sided property, pinned); the x=N edge computes.
- Full-stack goldens over BOTH VaR methods; the alignment refusal battery (unpaired forecast,
  duplicate `window_end`, horizon mismatch, gap/overlap, foreign portfolio, currency mismatch,
  mixed methods); conditional emission (zone only at (0.99, 250); decisions at both alphas);
  TR-09 re-run invariance; the magnitude/echo gates; append-only; RLS (PG).
- See `packages/shared-python/tests/test_var_backtest.py` / `test_var_backtest_pg.py`.

## Governed-number contract

Every row binds `dataset_snapshot` + `calculation_run` (`run_type='VAR_BACKTEST'`) + the
REGISTERED `model_version`; IA TRUE append-only (P0001 trigger + ORM guard); symmetric FORCE RLS;
grain `(calculation_run_id, metric_type, period_start)`. Rows: per-pair `EXCEPTION_INDICATOR`
(0/1 + `realized_pnl`/`var_value` evidence echoes) + `EXCEPTION_COUNT` + `KUPIEC_LR`
(+ `test_decision`) + `BASEL_ZONE` (dedicated string column) on its domain only. Permissions:
`risk.run`/`risk.view` REUSED — no new code. Pre-create refusal (422) for every ill-formed input;
post-create FAILED (committed run + DQ evidence + zero rows) for magnitude-gate trips.

## Known limitations

Mirrored into `model_limitation` rows (see `VAR_BACKTEST_LIMITATIONS`): the captured-holdings
ANTI-CONSERVATIVE P&L bias (the PM-1 carry, third naming); ACTUAL-P&L leg only (hypothetical/clean
P&L deferred — no static repricing engine); Kupiec-only (Christoffersen independence = BT-2; no
Basel multiplier arithmetic; no p-values); small-N asymptotics recorded via `n_pairs` on every
row; calendar-day horizon interpretation; one method per run.
