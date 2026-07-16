# Regression-estimated proxy weights v1 (`risk.proxy_weight.regression`)

> The TWELFTH governed number (PA-3, ENT-057) and the Wave-4 loop-closer: it makes PA-1's
> desmoothed appraisal-return series an actual INPUT to the proxy factor weights that PA-2 consumes,
> replacing judgment-only captured weights with evidence + stated uncertainty.

## Purpose & applicability

Estimate a private instrument's public-factor loadings from its own return history rather than by
analyst judgment alone. The target is the instrument's **desmoothed** appraisal return series
(PA-1's governed output — the honest, de-lagged series); the regressors are the candidate public
factors' returns. This is the estimation leg the platform reserved at PA-0 (`MAPPING_METHOD_REGRESSION`)
and recorded as PA-2's v2. Applicable to any private instrument that already has a COMPLETED
`DESMOOTHED_RETURN` run and CURRENCY-family candidate factors with captured returns spanning the
appraisal window.

## Inputs & data policy

Consumed ONLY from a pinned `PROXY_WEIGHT_INPUT` snapshot (AD-014 — never a live read; TR-09):

- the consumed `DESMOOTHED_RETURN` run's per-period `DESMOOTHED_PERIOD` rows
  (`COMPONENT_KIND_DESMOOTHED_RETURN`) — the regression **target** `y` + each period's span; and
- per candidate factor: one `COMPONENT_KIND_FACTOR` definition pin + one `COMPONENT_KIND_FACTOR_RETURN`
  window over the appraisal span (the covariance-window flavor).

A later mark/return correction of either side cannot move a historical estimate (TR-09 both sides).

## Formula & numerical standards

Unconstrained ORDINARY LEAST SQUARES with an intercept:

    y = X b + e,   X = [1 | f_1 | … | f_k]   (n × (k+1)),   b = (XᵀX)⁻¹ Xᵀy

- Each period's regressor is the factor's returns **compounded over `(period_start, period_end]`**
  (`∏(1+r) − 1`) — frequency alignment of daily/irregular factor returns to the appraisal period.
- Reports per coefficient (intercept + `k` slopes) the estimate AND its **standard error**
  `se_j = √(s²·[(XᵀX)⁻¹]_jj)`, `s² = eᵀe/(n−(k+1))`; plus `R²` and the residual stdev — the
  honest-uncertainty statement.
- Computed in `Decimal` at 50-digit context (Gauss-Jordan inverse, partial pivoting); results
  quantize_HALF_UP to 12dp (`Numeric(20,12)`). The RAW fit is magnitude-gated against the column
  envelope (`|value| < 1E8`) BEFORE quantize — the P3-6/PA-1/PA-2 detonation-guard discipline.

## Assumptions (declared; mirrored into `model_assumption`)

- `min_observations=N` is the DECLARED model identity (`(code_version, min_observations)`, on the
  RD-2 `model/assumptions.py` rails; `N ≥ 3`). The run additionally enforces `n ≥ max(N, k+2)` so a
  residual degree of freedom (hence a standard error) always exists.
- Unconstrained OLS: NO sum-to-1, NO non-negativity (PA-0 deliberately admits negative / no-sum proxy
  weights). CURRENCY-family candidate factors only (the PA-2 boundary). Single-currency target series.

## Validation / reproduction tests

- Full-stack golden: a real chain (marks → desmoothed run → candidate factors → estimate) with every
  persisted coefficient / std-error / R² / residual-stdev asserted BYTE-IDENTICAL to an independent
  `estimate_ols` recomputation on the extracted `(y, X)`.
- Pre-create refusal battery (too-few periods, non-CURRENCY candidate, wrong-purpose snapshot,
  per-period coverage gap, singular/collinear design, constant target) with NO RUNNING orphan.
- Magnitude gate → committed FAILED (zero rows). Append-only / `run_type ≠ metric_type`. The
  promotion loop (a REGRESSION capture cites a COMPLETED estimate run; a wrong-type run is refused).

## Governed-number contract

RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND (all NOT-NULL FKs) + IA TRUE append-only (P0001 trigger +
ORM guard) + symmetric tenant-scoped RLS (NEVER hybrid). `run_type='PROXY_WEIGHT_ESTIMATE'` (the
family, ≠ the metric); REUSES `risk.run`/`risk.view` (no mint); `CALC.RUN_*`-audited
(`RISK.PROXY_WEIGHT_ESTIMATE_CREATE` RESERVED, not minted). Rows: one `WEIGHT` per candidate factor
+ one `INTERCEPT` + one `ESTIMATION_SUMMARY`; grain `(calculation_run_id, metric_type, factor_id)`.

**Estimate → promote (OD-PA-3-A/E):** an estimate is MODEL OUTPUT, NEVER auto-written into
`proxy_mapping`. Promotion is a deliberate second step — `risk.promote_proxy_weight_estimate`
resolves the cited COMPLETED `PROXY_WEIGHT_ESTIMATE` run (the run-TYPE gate; `marketdata` imports no
`calc`, so this lives one layer up) then writes a `REGRESSION`-method `proxy_mapping` row whose
`source_calculation_run_id` cites the run: a CAPTURE when the `(instrument, factor)` key has no open
head, else a citation-carrying SUPERSEDE (a RE-promotion — the steady-state loop as new marks
arrive: re-estimate → review → re-promote). The analyst chooses the weight VALUE to promote (not
auto-read from the run) — a human decision point by design. The blur guard holds on every path
(REGRESSION requires a citation; MANUAL forbids one; the HTTP supersede body carries no citation
field, so an API-level REGRESSION supersede always refuses); a CORRECTION can never mint REGRESSION
(v1 recorded limitation — re-promote instead). PA-2's proxy factor-exposure runs then consume the
promoted rows unchanged.

## FL-1 (2026-07-16): repointed at PUBLIC instruments for factor loadings

FL-1 reuses this OLS machinery UNCHANGED to estimate the factor loadings of PUBLIC instruments
(the `risk.factor_exposure.loadings` family; see `factor_exposure_loadings_v1.md`). The estimate →
promote loop, the per-coefficient std errors, the R², and the pinned-provenance chain all carry
over verbatim. Three disclosures for the public-instrument use:

- **The α = 1 return source.** A public instrument's raw marks have no smoothing to invert, so they
  ride the SHIPPED desmoothing path at **α = 1** — the Geltner identity (`r_true = r_observed`
  exactly; see `desmoothing_geltner_v1.md`'s FL-1 applicability note). The `DESMOOTHED_RETURN` run
  exists to satisfy this referent's pinned-provenance chain, NOT to transform; a dedicated
  raw-return pin kind is the recorded cleaner v2.
- **Price-return betas.** The platform captures valuation marks, not dividends, so the estimated
  betas are PRICE-return betas — they understate total-return covariation for high-yield
  instruments (a recorded limitation; the std errors stay first-class).
- **Widened candidate families.** The candidate-factor gate widened from CURRENCY-only to
  `LOADING_FACTOR_FAMILIES` (the FRTB five broad classes + the Barra families; OTHER/unknown still
  refused) so a public instrument can load on MARKET/RATES/CREDIT_SPREAD/COMMODITY factors. The
  unconstrained-OLS-vs-classic-RBSA divergence below is unchanged; single-name RBSA over a short
  window still yields noisy betas.

## Known limitations

- Estimates regress a MODEL OUTPUT (the desmoothed series) — desmoothing model risk (the declared α)
  propagates into the weights (stated; the source run id is pinned).
- Appraisal series are SHORT → wide standard errors (reported per coefficient, never hidden).
- Unconstrained OLS can produce weights an analyst should reject — which is WHY promotion is
  human-mediated.
- v2s (recorded): Sharpe-1992 constrained style analysis; Dimson-1979 / Asness-Krail-Liew-2001
  summed-lag betas on the RAW series (a cross-check for smoothing); regression on multi-family
  (equity/credit) factors beyond CURRENCY.

## References

- Sharpe, W.F. (1992), "Asset Allocation: Management Style and Performance Measurement," *JPM* 18(2).
- Scholes, M. & Williams, J. (1977) and Dimson, E. (1979), "Risk measurement when shares are subject
  to infrequent trading," *JFE* — lagged/aggregated-coefficient beta corrections.
- Asness, C., Krail, R. & Liew, J. (2001), "Do Hedge Funds Hedge?," *JPM* 27(3) — summed-lag betas on
  smoothed series.
- Getmansky, M., Lo, A. & Makarov, I. (2004) — the smoothed-returns process (PA-0/PA-1 shared cite).
