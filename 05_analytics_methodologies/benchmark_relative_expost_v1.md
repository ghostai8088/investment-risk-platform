# Methodology — Ex-post Benchmark-Relative Performance (active return / TE / TD / IR) v1

> **Model:** `perf.benchmark_relative` · **Version:** `v1` · **Referent:** `model_version.methodology_ref` points here.
> **Status:** REGISTERED; `validation_status = UNVALIDATED` (recorded, **non-enforcing until P7**). This doc IS the methodology referent the governed `model_version` binds (P3-8, ENT-054, OD-P3-8-A).

## Purpose & applicability

The platform's **eighth** governed number and the **first governed consumer of a captured vendor
return series** (ENT-052 `benchmark_return`): realized, ex-post performance of a portfolio **relative
to a benchmark**. It answers "how did the book do *versus* its benchmark, after the fact" — the
counterpart to P3-7's *ex-ante* (forecast) tracking error, and it closes the P3-7 OD-G deferral.
Four metrics: **active return** (per sub-period), **tracking difference**, realized **tracking
error**, and **information ratio**.

## Inputs & data policy

ONE COMPLETED `PORTFOLIO_RETURN` run (PM-1) supplies the portfolio side — its pinned `DIETZ_PERIOD`
rows ARE the per-sub-period returns `r_p,i` (with their `period_start`/`period_end`); no
re-derivation. The caller names `(benchmark_id, return_basis)`; `return_type` is fixed `SIMPLE`. The
benchmark side is the pinned `benchmark_return` rows whose `return_date ∈ (period_start_i,
period_end_i]` — the SAME half-open windows as PM-1's flows, so the sub-periods partition the span
exactly. Both are pinned into a `BENCHMARK_RELATIVE_INPUT` snapshot (`COMPONENT_KIND_PORTFOLIO_RETURN`
rows + one `COMPONENT_KIND_BENCHMARK_RETURN` series component); the compute reads ONLY the pinned
content (AD-014) — a later PM-1 re-run OR a benchmark vendor correction cannot move a historical
result (test-proven, TR-09). NO live read.

## Formulas & numerical standards

```
a_i = r_p,i - r_b,i                          per sub-period (arithmetic active return)
r_b,i = prod_d (1 + r_d) - 1                  compounded over pinned SIMPLE rows in (start_i, end_i]
TD  = R_p - R_b,  R = prod_i (1 + r_i) - 1    tracking difference (compounded-return difference)
TE  = sqrt( sum_i (a_i - mean_a)^2 / (n-1) )  realized tracking error (unbiased SAMPLE stdev)
IR  = mean(a_i) / TE                          information ratio (Grinold-Kahn)
```

- **Conditional emission (declared, tested):** `ACTIVE_RETURN` (per sub-period) + `TRACKING_DIFFERENCE`
  (one summary row) are ALWAYS emitted; `TRACKING_ERROR` + `INFORMATION_RATIO` only when **n ≥ 2**
  sub-periods (a 1-observation volatility is not a statistic); `INFORMATION_RATIO` additionally
  OMITTED when TE quantizes to 0 (a perfectly-tracking book is a legitimate input — IR is undefined,
  not garbage; omission over refusal, recorded per-run via the row counts).
- **Precision:** `Decimal` at 50-digit context; every value `quantize_HALF_UP` to **12** decimal
  places (the `Numeric(20,12)` fraction/ratio scale). **UNANNUALIZED.**
- **Exact-linkage adjudication:** the compute recomputes `Π(1+r_i)−1` from the pinned `DIETZ_PERIOD`
  rows and requires EXACT equality with the pinned `TWR_LINKED` value (both computed from the same
  12dp inputs by PM-1) — a mismatch is a malformed hand-mint → refused.

## Assumptions

1. **Arithmetic** active returns (the standard TE input; geometric excess is a declared non-goal).
2. **Unbiased SAMPLE** (n−1) tracking error (the P3-4 covariance precedent); n ≥ 2 required.
3. Benchmark **geometric compounding** of pinned SIMPLE rows over the PM-1 half-open sub-period
   windows; a window with ZERO benchmark rows is a **pre-create refusal** (no imputation).
4. **Snapshot-only compute** (AD-014): invariant under a later PM-1 re-run AND a benchmark
   vendor supersede/correction (TR-09).
5. `benchmark_currency == base_currency` (no FX translation of return series in v1); caller-chosen
   `return_basis` echoed on every row; **UNANNUALIZED** — DECLARED so these are never conflated with
   the (annualized) UCITS ex-post disclosure figures.

## Validation / reproduction tests

- **Hand golden (independently cross-checked, TEST-only):** portfolio `(0.03, −0.02, 0.01)` vs
  benchmark `(0.025, −0.015, 0.005)` → active `(0.005, −0.005, 0.005)`; `mean = 0.001666666667`;
  `TE = 0.005773502692` (n−1 sample stdev — cross-checked against `statistics.stdev`);
  `IR = 0.288675134647`; `R_p = 0.019494000000`, `R_b = 0.014673125000`, `TD = 0.004820875000`.
- **Reproduction:** an identical re-run reproduces the series exactly; the pinned snapshot is
  invariant under a later PM-1 re-run AND a benchmark_return CORRECTION appended after the snapshot
  (TR-09 — the first FR-series-supersede reproducibility proof in the perf family).
- **Reachable refusals:** every alignment / currency / basis / linkage / missing-input gate raises
  pre-create; a result-magnitude beyond `Numeric(20,12)` is a committed FAILED run.

## Governed-number contract

RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND; IA TRUE append-only `benchmark_relative_result` (per-
sub-period `ACTIVE_RETURN` rows + `TRACKING_DIFFERENCE`/`TRACKING_ERROR`/`INFORMATION_RATIO` summary
rows; grain `(calculation_run_id, metric_type, period_start)`); hard-FK provenance incl. the single
`portfolio_return_run_id` + `benchmark_id`; symmetric tenant RLS (NEVER hybrid); reproducible under
input correction; `CALC.RUN_*` audit (`PERF.BENCHMARK_RELATIVE_CREATE` reserved, NOT minted).
**Entitlement REUSES `perf.run`/`perf.view`** (a benchmark-relative number is a performance number —
no new mint; `auditor_3l` holds `perf.view`); `run_type = 'BENCHMARK_RELATIVE'` (the family, ≠ every
metric).

## Known limitations (recorded; mirror the `model_limitation` rows)

1. **CAPTURED-HOLDINGS BOOK — propagated from PM-1.** The portfolio return understates total return
   by uncaptured income; that bias flows into EVERY P3-8 number against a TOTAL-return benchmark.
   First-class; mitigation operational (capture the cash), never imputation. Named again per OD-K.
2. **Missing-day compounding hazard.** A benchmark vendor gap inside a window silently understates
   the compounded benchmark return; trading-calendar completeness validation is DEFERRED (a
   zero-row window refuses; a sparse one is flagged, `n_benchmark_obs` recorded as evidence).
3. **Gross-vs-basis comparability** — the caller owns the `return_basis` choice; no silent
   fee/basis adjustment.
4. **Unannualized; arithmetic; single benchmark; no active share / relative VaR / attribution;**
   LOG return_type reserved.
5. `validation_status = UNVALIDATED` — recorded, non-enforcing until the P7 validation workflow.
