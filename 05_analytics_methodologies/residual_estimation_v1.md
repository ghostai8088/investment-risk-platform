# Residual-estimator conventions v1 (`risk.proxy_weight.regression`) — RS-1

The idiosyncratic residual variance σ_e² of a proxy-weight OLS estimate — the specific-risk input
to total parametric VaR/ES (PA-4) — is estimated under a DECLARED **estimator convention** carried
by the model version. RS-1 adds two conventions to the raw v1; each is a new declared version, never
a silent replacement.

## Purpose & applicability

Applies to the private-instrument proxy-weight family (`risk.proxy_weight.regression`, ENT-057).
The OLS factor regression is UNCHANGED across all conventions (same loadings, same coefficient
standard errors, same R²); the convention re-estimates ONLY the residual (specific-risk) variance —
the Barra/Axioma vendor-standard separation (factor inference from the regression; specific risk
modelled separately). The three conventions:

| Convention | What it does | Declared identity |
|---|---|---|
| `RAW` (grandfathered v1) | classical unbiased sample residual variance `s² = e'e/(n−(k+1))` | `min_observations` (an ABSENT `estimator_convention` ⇒ RAW) |
| `EWMA_RISKMETRICS` (OD-RS-1-A) | exponentially-weighted mean of squared residuals | `min_observations`, `estimator_convention`, `decay_lambda` |
| `SHRINKAGE_CROSS_SECTIONAL_EB` (OD-RS-1-B) | empirical-Bayes shrinkage toward the cohort pool | `estimator_convention` (method-as-identity; NO numeric) |

## EWMA (`EWMA_RISKMETRICS`), pinned

With the OLS residual series `e_0..e_{n-1}` in TIME order (oldest first):

    σ_e² = Σ_i w_i e_i²,   w_i = (1−λ) λ^(n−1−i) / (1 − λ^n)

so Σ w_i = 1 and the MOST RECENT residual (`i = n−1`) carries the largest weight (λ⁰ = 1);
equivalently the RiskMetrics recursion σ²_t = λ σ²_{t−1} + (1−λ) e²_{t−1}. Declared choices, both
recorded as limitations: **no `n−k` degrees-of-freedom correction** (the RiskMetrics biased
normalization by Σw_i = 1; the effective sample size is `1/Σ w_i²` < n), and the residual **mean is
taken as zero** by convention. `decay_lambda` (0 < λ < 1) is a DECLARED model-identity parameter —
RiskMetrics' 0.94-daily/0.97-monthly are NOT transferable to appraisal-PERIOD marks, so a different
λ is a new declared version; the RMSE-fitted λ is a recorded v2.

## Shrinkage (`SHRINKAGE_CROSS_SECTIONAL_EB`), pinned

A TRANSFORM over a comparable COHORT of promoted raw estimates (it runs no OLS). Per member `i`
with raw variance `s_i²` estimated on `n_i − k_i` residual df:

    pool         σ_pool²  = (1/N) Σ_j s_j²                    (equal-weighted cross-section)
    sampling var v_i      = 2 s_i⁴ / (n_i − k_i)              (Gaussian var-of-a-variance)
    cross disp   S²_cross = (1/(N−1)) Σ_j (s_j² − σ_pool²)²
    prior disp   τ²       = max(0, S²_cross − v̄),  v̄ = (1/N) Σ_j v_j
    intensity    w_i      = v_i / (v_i + τ²)                  (per-instrument, DATA-DRIVEN)
    shrunk       s_i²(shr)= w_i σ_pool² + (1 − w_i) s_i²

The intensity is heterogeneous (Efron-Morris / James-Stein empirical Bayes): a noisier/shorter-
series estimate (larger `v_i`) shrinks MORE; a widely-dispersed cohort (larger `τ²`) shrinks LESS.
**Method-as-identity**: the declared identity is the METHOD; there is NO declared `w` — every `w_i`
is COMPUTED and fully reproducible from the pinned per-member `(s_i², residual df)` alone (the fit
is not minted as a separate governed number). **Fail-closed** below `N = 3` comparable members
(τ² is not identifiable under the James-Stein dimension) — never an arbitrary intensity.

## Declared identity

RAW/EWMA are OLS-regression conventions run via `run_proxy_weight_estimate`; the EB shrinkage is a
transform run via `run_residual_shrinkage` (per target instrument, pinning the whole cohort). A
version bound to the wrong operation fails closed (`WrongModelVersionError` — the registry-map
dispatch). The estimator convention + its companion literals are REGISTRAR-STAMPED, never
caller-suppliable from the generic `/models` endpoint; a same-label re-register with a different
declaration is a governed 409.

## Downstream

The convention changes ONLY `residual_stdev` on the `ESTIMATION_SUMMARY` row. The total-VaR/ES-total
residual leg consumes σ_e byte-unchanged (it only √t-descales and squares-sums-sqrts), so no
downstream math is altered — a total-VaR run over a shrunk/EWMA estimate binds one of these versions.

## External benchmarks (roadmap Part 4 rule 6 — sources checked 2026-07-17)

- **RiskMetrics EWMA** — J.P. Morgan/Reuters, *RiskMetrics — Technical Document*, 4th ed. (Dec 1996),
  §5. The recursion σ²_t = λ σ²_{t−1} + (1−λ) r²_{t−1}, mean assumed zero; λ = 0.94 daily / 0.97
  monthly chosen by minimizing forecast RMSE. VERIFIED (formula + λ values + selection method; the
  exact §/equation numbers to be confirmed against the primary text — the LZW-compressed PDF did not
  text-extract for a character-exact quote, disclosed).
- **Axioma** specific risk as "the EWMA stdev of daily specific returns" — the shape RS-1's EWMA
  mirrors (the equal-weighted RAW v1 is the un-decayed λ→1⁻ limit).
- **Barra USE4** — MSCI, *The Barra US Equity Model (USE4) Methodology Notes* (Aug 2011). Bayesian
  shrinkage of specific risk toward the (cap-weighted) cross-sectional mean specific volatility, with
  a data-driven intensity. VERIFIED (target + concept + data-driven intensity). RS-1 is USE4-faithful
  on the intensity; the equal-weighted pool (vs cap-weighted) and the Gaussian `v_i = 2s⁴/(n−k)`
  approximation are disclosed simplifications, each a recorded v2.
- **Ledoit-Wolf (2004, JPM 30(4):110–119)** is EXPLICITLY NOT the primary for this leg: its
  constant-correlation estimator leaves the DIAGONAL VARIANCES UNSHRUNK (`f_ii = s_ii`) — it shrinks
  correlations, not variances — so it is the wrong citation for a residual-variance shrinkage
  (reserved for COVARIANCE shrinkage, a distinct wave-unassigned deferral).

## Known limitations (first-class; mirrored into `model_limitation` rows)

Per convention, the registered `model_limitation` rows carry: EWMA — the effective-sample-size
(`1/Σw_i²` < n), the declared-λ non-transferability, the biased/zero-mean convention; EB shrinkage —
the comparable-cohort rule (cross-asset-class pooling is a misuse), the N≥3 fail-closed floor, the
Gaussian sampling-variance approximation, the equal-weighted-pool simplification. All conventions
inherit the family's standing rows (estimates are model output, promotion is human-mediated,
`validation_status` UNVALIDATED until a 2L outcome).

## Reproducibility & governance

Every convention is deterministic Decimal (prec-50, single terminal quantize to the `Numeric(20,12)`
scale). RAW/EWMA reproduce from the pinned `PROXY_WEIGHT_INPUT` snapshot; the EB shrinkage reproduces
from the pinned `RESIDUAL_SHRINKAGE_INPUT` cohort snapshot (every `w_i` recomputed from captured
content — never a live estimate read; TR-09). Snapshot/run/model-bound, IA append-only.
