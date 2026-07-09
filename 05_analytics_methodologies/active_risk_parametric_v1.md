# Methodology — Ex-ante Active Risk (parametric tracking error, factor model, 1-day) v1

> **Model:** `risk.active_risk.parametric` · **Version:** `v1` · **Referent:** `model_version.methodology_ref` points here.
> **Status:** REGISTERED; `validation_status = UNVALIDATED` (recorded, **non-enforcing until P7**). This doc IS the methodology referent the governed `model_version` binds (P3-7, ENT-027, OD-P3-7-B/D).

## Purpose & applicability
The platform's **sixth** governed **risk** number: the **ex-ante (forecast)** parametric
**tracking error** — the factor-model active-risk standard deviation
`TE = √(wₐᵀ Σ wₐ)` where `wₐ = w_p − w_b` is the vector of **active weights** (portfolio minus
benchmark, per factor), `Σ` the sample covariance from ONE COMPLETED covariance run (P3-4). Both
sides map through the **same** allocation-v1 CURRENCY-factor model (Barra-style methodological
symmetry): the portfolio side from ONE COMPLETED factor-exposure run (P3-3), the benchmark side
from a captured benchmark membership set (P2-6). ENT-027 `risk_result` is realized as the
single-summary-row `active_risk_result`. This is a **standard deviation** (an active-return
volatility), **not** a quantile — there is no `z` factor (contrast parametric VaR).

**This number is EX-ANTE (a forecast).** It MUST NOT be read as the regulatory **ex-post** UCITS
tracking-error disclosure (ESMA 2012/832: "the volatility of the difference between the return of
the fund and the return of the benchmark"), which requires realized return series — see Known
limitations.

**NOT applicable to** (deferred): ex-post / realized tracking error; active return / tracking
difference; information ratio; active share; relative VaR; benchmark-relative sensitivities;
annualization / √T scaling; performance attribution.

## Inputs & data policy
- **Inputs**, pinned into an `ACTIVE_RISK_INPUT` `dataset_snapshot`:
  - `COMPONENT_KIND_FACTOR_EXPOSURE` — the `factor_exposure_result` rows of ONE COMPLETED
    factor-exposure run (the portfolio side; IA-row pins);
  - `COMPONENT_KIND_COVARIANCE` — the `covariance_result` rows of ONE COMPLETED covariance run
    (`Σ`; IA-row pins);
  - `COMPONENT_KIND_FACTOR` — the `factor` EV definitions of the covariance factor set (the
    `currency_code → factor` mapping the benchmark side needs);
  - `COMPONENT_KIND_BENCHMARK` — the captured `benchmark_constituent` rows of the declared
    `(benchmark_id, effective_date)` membership (FR-version pins — a later vendor
    supersede/correction is invisible to the pinned set; TR-09).
  The compute reads **only** the pinned snapshot content — never a live read — so a later upstream
  re-run or vendor restatement cannot move a historical TE (test-proven).
- **Data policy:** the v1 conventions ARE the version identity (no free numeric request
  parameters). Coverage is **fail-closed** (NO imputation): every portfolio factor AND every
  benchmark-mapped currency factor must be in the covariance factor set; every needed canonical
  pair must be present. A benchmark constituent with a **NULL currency is a pre-create refusal**
  (naming the gap) — never imputed to the benchmark header currency (which would misattribute
  currency risk). A currency that maps to no factor, a total benchmark weight ≤ 0, or a zero
  portfolio value each refuse pre-create.
- **Missing data:** an upstream run with zero visible rows, or an empty membership set, refuses the
  snapshot build BEFORE any write.

## Formulas & numerical standards
```
w_p[f]    = ( Σ over the exposure run's rows for factor f of exposure_amount ) / portfolio_value
portfolio_value = Σ over ALL pinned exposure rows of exposure_amount        (net signed, base ccy)
w_b[f]    = ( Σ over constituents whose currency maps to factor f of weight ) / Σ(all weights)
w_a[f]    = w_p[f] − w_b[f]                                                  (over the Σ factor set)
radicand  = wₐᵀ Σ wₐ = Σ_i Σ_j w_a[i]·σ_ij·w_a[j]                            (a variance, fraction²)
TE        = √(radicand)                                                     (daily, unannualized)
```
- **Precision:** `Decimal` at 50-digit context; `Decimal.sqrt` correctly rounded; `te_value`
  `quantize_HALF_UP` to **12** decimal places (the `Numeric(20,12)` return-fraction scale — TE is a
  return volatility, NOT a currency amount).
- **Radicand floor (the P3-5 OD-P3-5-G pattern):** `Σ` is PSD in exact arithmetic but stored at
  20dp, so a near-null-space `wₐ` can dip a tiny amount below zero. `radicand ∈ [−tol, 0)` with
  `tol = F²·max_i(w_i²)·1E-19` is clamped to 0 (a **benchmark-matching portfolio** → `wₐ = 0` →
  TE 0, a valid result). Below `−tol` is a genuinely non-PSD input → a **post-create FAILED** run
  with DQ evidence.
- **Units:** DAILY, UNANNUALIZED (the covariance substrate is daily). Naive `√T` annualization
  biases TE under serial correlation (Pope & Yadav 1994) and is a later, separately declared
  transform.

## Assumptions
1. **Linear factor model** — active risk is fully explained by the pinned factor covariance over the
   CURRENCY-factor partition; both the portfolio and benchmark map through the **same**
   `build_factor_index` (methodological symmetry).
2. **Active weights** `wₐ = w_p − w_b`, dimensionless: `w_p` from the pinned factor exposures ÷ the
   pinned net book value; `w_b` from the pinned benchmark constituents normalized by their captured
   weight sum, mapped currency→factor.
3. **`code_version` is the sole version identity** (OD-P3-7-D) — there is NO numeric request
   parameter (no confidence/horizon/z); the v1 conventions ARE the identity.
4. **Snapshot-only compute** — the number reads ONLY the pinned `FACTOR_EXPOSURE`/`COVARIANCE`/
   `FACTOR`/`BENCHMARK` content; no live read (AD-014), so it is invariant under upstream re-runs and
   benchmark restatements.
5. **Fail-closed inputs** — a NULL or unmappable `constituent_currency`, a non-positive benchmark
   weight sum, a zero portfolio value, an uncovered factor, or a missing covariance pair is REFUSED
   pre-create (no imputation).

## Validation / reproduction tests
- **Exact hand reference:** `w_a = (0.2, −0.2)` over uncorrelated factors (variance 4E-4 / 9E-4) →
  `radicand = 5.2E-5` → **TE = 0.007211102551** (through the full governed consume path); kernel
  references `w = (0.03, 0.04)` → 0.0005 (uncorrelated) / 0.0007 (fully correlated).
- **Independent cross-check:** a numpy float recomputation of `√(wₐᵀΣwₐ)` from the pinned content
  agrees within ε (numpy is TEST-ONLY, import-fenced out of the runtime).
- **Reproduction:** an identical re-run reproduces the number exactly; a pinned snapshot is invariant
  under a later covariance re-run AND a benchmark supersede/correction (TR-09, test-proven).
- **Benchmark-match:** `w_p = w_b ⇒ wₐ = 0 ⇒` TE 0 (a valid result, not an error).
- **Reachable failure:** a genuinely non-PSD pinned matrix commits a FAILED run with DQ evidence.

## Governed-number contract
RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND; IA TRUE append-only `active_risk_result` (one summary row
per COMPLETED run, grain `(calculation_run_id, metric_type='TRACKING_ERROR')`); hard-FK provenance
to the factor-exposure run, the covariance run, and the benchmark, plus the pinned
`benchmark_effective_date` and the `portfolio_value` denominator as evidence; symmetric tenant RLS
(NEVER hybrid); reproducible under input correction (TR-09); `CALC.RUN_*` audit (no `RISK.*` code
minted — `RISK.ACTIVE_RISK_CREATE` reserved). Entitlement reuses `risk.view`/`risk.run`.

## External-benchmark basis (roadmap rule 6)
Roll (1992, *JPM*) — TE as active-return volatility; Grinold & Kahn (2000) — the factor-model form
`ψ² = wₐᵀΣwₐ` (+ specific term); Pope & Yadav (1994, *JPM*) — grounds daily-unannualized reporting;
CESR/10-788 (2010) — relative-VaR sibling (recorded seam); ESMA 2012/832 (rev. 2014/937) — the
ex-post definition deliberately not shipped; MSCI Barra Risk Model Handbook (2007) — both-sides-
through-one-model symmetry. Full dispositions in `10_delivery_backlog/p3_7_decision_record.md` Part 2.

## Known limitations (recorded; mirror the `model_limitation` rows)
1. **Specific/idiosyncratic active risk = 0** — the CURRENCY-family indicator-loading model carries
   no residual term (Grinold-Kahn's specific term is zero here; the allocation-v1 limitation
   propagates to both sides).
2. **Ex-ante only.** Ex-post/realized TE, active return, tracking difference, and information ratio
   are DEFERRED — they need a portfolio return series (a flow-adjusted performance-measurement
   methodology, its own planned slice). The shipped number is a forecast.
3. **Daily, unannualized** — `√T` scaling is a later declared transform.
4. **Benchmark weights normalized** by their captured sum (vendor rounding); missing currencies
   refuse, never impute.
5. Inherits the sample-covariance estimation error (equal weights, no shrinkage; rank-deficient for
   `F ≥ N`). Relative VaR / active share / benchmark-relative sensitivities are recorded seams.
6. `validation_status = UNVALIDATED` — recorded, non-enforcing until the P7 validation workflow.
