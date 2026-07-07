# Methodology — Parametric Portfolio VaR (delta-normal, zero-mean, 1-day) v1

> **Model:** `risk.var.parametric` · **Version:** `v1` · **Referent:** `model_version.methodology_ref` points here.
> **Status:** REGISTERED; `validation_status = UNVALIDATED` (recorded, **non-enforcing until P7**). This doc IS the methodology referent the governed `model_version` binds (P3-5, ENT-027, OD-P3-5-A/D/F/G).

## Purpose & applicability
The platform's fourth governed **risk** number and its first **composed** one: the zero-mean
delta-normal (variance-covariance) 1-day portfolio Value-at-Risk under the linear factor model
`ΔV = Σᵢ xᵢ·rᵢ` — the exposure vector `x` from ONE COMPLETED factor-exposure run (P3-3, base
currency) against the sample covariance matrix `Σ` from ONE COMPLETED covariance run (P3-4).
ENT-027 `risk_result` is realized as the single-summary-row `var_result`. Applicable when every
exposure factor is covered by the covariance factor set (a coverage gap fails closed — never a
zero-variance imputation).

**NOT applicable to** (deferred — see Known limitations): Expected Shortfall; historical
simulation (factor-based OR full-revaluation); Monte-Carlo; multi-horizon √h scaling;
component/marginal VaR; backtesting.

## Inputs & data policy
- **Inputs:** the `factor_exposure_result` rows of one COMPLETED FACTOR_EXPOSURE run + the
  `covariance_result` rows of one COMPLETED COVARIANCE run, pinned into a `VAR_INPUT`
  `dataset_snapshot` as `COMPONENT_KIND_FACTOR_EXPOSURE` + `COMPONENT_KIND_COVARIANCE`
  components (both IA-row pins — the source rows are TRUE append-only; drift impossible). The
  compute reads **only** the pinned snapshot content — never a live result read — so a later
  upstream RE-RUN cannot move a historical VaR (test-proven). **No factor-definition pin** —
  both row types are self-describing.
- **Data policy:** the confidence level, horizon, and z constant are **declared at model
  registration** and are part of the version identity (OD-P3-5-D — the OD-P3-4-G window
  precedent); never request parameters. The consumed covariance must carry the v1
  `COVARIANCE`/`SIMPLE`/`DAILY` vocabulary with a uniform window; the exposure rows must carry
  a uniform `base_currency`; both pinned sets must each come from ONE run. **Coverage is
  fail-closed:** every exposure `factor_id` must be present in the covariance factor set and
  every needed canonical pair present — a gap is a pre-create refusal (422), NO imputation.
- **Missing data:** an upstream run with zero visible result rows refuses the snapshot build
  BEFORE any write (409).

## Formulas & numerical standards
```
x_i       = Σ over the exposure run's rows for factor i of exposure_amount   (base currency)
radicand  = xᵀ Σ x = Σ_i Σ_j x_i·σ_ij·x_j                                    (currency²)
σ_p       = sqrt(radicand)            VaR_α = z_α · σ_p                      (h = 1; zero mean)
```
- **Grain:** ONE summary row per COMPLETED run (`(calculation_run_id, metric_type)`;
  `VAR_PARAMETRIC` v1, `ES_PARAMETRIC` reserved by value). Positive `var_value` = potential loss
  at the declared confidence over 1 day, in the run-uniform base currency.
- **z constants (NO runtime quantile function):** the v1 confidence vocabulary is enumerated —
  `0.9500 → z = 1.644853626951`, `0.9900 → z = 2.326347874041` — recorded to 12dp, dual-sourced
  from published standard-normal tables and test-verified BOTH by the stdlib `math.erf`
  round-trip `Φ(z) = (1+erf(z/√2))/2 = α` (to 1e-12) AND by an independent bisection inversion.
  Implementing an inverse-normal-CDF is a separately verified numerical method — deferred
  (capability-is-not-evidence).
- **Rounding / precision:** computed in `Decimal` at 50-digit context precision (`Decimal.sqrt`
  is correctly rounded to context); `σ_p` and `VaR` `quantize_HALF_UP` to 6dp into
  `Numeric(28,6)` (the platform currency scale — no new precision departure).
- **The radicand quantization floor (declared):** `Σ` is PSD in exact arithmetic but stored at
  20dp; for near-null-space `x` the quantized radicand can dip below zero by at most
  `F²·max(xᵢ²)·5e-21`. The declared tolerance `tol = F²·max(xᵢ²)·1e-19` (20× headroom)
  separates the storage artifact — a radicand in `[−tol, 0)` is treated as 0 — from a genuinely
  non-PSD input, which FAILS the run closed (a committed FAILED run + DQ evidence + zero rows).
  The clamp bound is a mirrored model assumption, not a silent fix.

## Assumptions
Mirrored content-identically into `model_assumption` rows (plain-ASCII spellings stored; plus the
registration-supplied `confidence_level=`/`horizon_days=`/`z_score=` declarations):
- Zero-mean delta-normal parametric VaR under the linear factor model `dV = Σᵢ(xᵢ·rᵢ)`:
  `σ_p = √(xᵀΣx)`; `VaR_α = z_α·σ_p` (1-day; no √h scaling).
- Inputs: the per-factor CURRENCY-exposure totals of ONE COMPLETED factor-exposure run (base
  currency, signed) × the sample covariance matrix of ONE COMPLETED covariance run
  (SIMPLE/DAILY, unannualized); every exposure factor MUST be covered by the covariance factor
  set — a gap fails closed (NO zero-variance imputation).
- `z_α` is a REGISTERED constant from an enumerated confidence vocabulary — no runtime
  inverse-normal-CDF is computed.
- Radicand quantization floor: `xᵀΣx` in `[−tol, 0)` with `tol = F²·max(xᵢ²)·1e-19` (the 20dp
  storage-quantum bound, 20× headroom) is treated as 0; below `−tol` the run FAILS closed (a
  non-PSD input).
- Computed in Decimal at 50-digit context precision; σ/VaR `quantize_HALF_UP` to 6 decimal
  places (the `Numeric(28,6)` base-currency scale).

## Limitations
Mirrored content-identically into `model_limitation` rows:
- **SPECIFIC/IDIOSYNCRATIC RISK = 0** — the linear CURRENCY-family indicator-loading factor
  model carries NO residual variance term: portfolio risk outside the factor covariance is
  invisible to this number (the allocation-v1 limitation propagates). This is the largest
  honesty gap of this metric.
- **Joint normality of factor returns assumed** — tail risk is understated for fat-tailed
  returns; the empirical-distribution alternative (factor-based historical simulation) is a
  recorded roadmap method.
- **1-day horizon only** (the covariance is daily/unannualized); multi-horizon √h scaling is a
  later, separately declared transform.
- **Parametric method only; ONE confidence level per registered version** (the
  declared-parameter identity); ES (closed-form seam `ES = σ·φ(z)/(1−α)`), historical
  simulation, and Monte-Carlo are later, separately declared model versions/families
  (user-directed roadmap, 2026-07-07).
- **Inherits the sample-covariance estimation error** (equal weights, no shrinkage;
  rank-deficient for F ≥ N).
- `validation_status = UNVALIDATED` — recorded, non-enforcing until the P7 validation workflow.

## Validation / reproduction tests
The five legs of the dual-path verification standing rule:
1. **Hand-computed exact references:** perfect-square constructions (the 3-4-5 exposure triangle
   over uncorrelated 1%-vol factors ⇒ σ_p = 500 exactly; a fully-correlated pair ⇒ σ_p = 7
   exactly) reproduced exactly at 6dp through kernel AND full stack.
2. **Independent-implementation cross-check:** `z·numpy.sqrt(x@Σ@x)` on synthetic data agrees
   within relative ε = 1e-9 (numpy TEST-ONLY; the `irp_shared` runtime fence covers it).
3. **Property tests:** positive homogeneity `VaR(λx) = λ·VaR(x)` — exact for the UNROUNDED values; the STORED (6dp-quantized) σ and VaR each satisfy it within `(λ+1)/2` quanta (each quantize contributes a half-quantum; quantization does not commute with scaling), exact at the quantum only where the unrounded value terminates within 6dp (e.g. perfect-square radicands for σ);
   confidence monotonicity (`VaR₉₉ > VaR₉₅` for σ > 0); invariance under exposure-row order.
4. **z-constant verification:** the `math.erf` round-trip reproduces α to 1e-12 for both
   registered constants (dual-sourced literature values quoted above).
5. **Exact re-run reproducibility + pin invariance:** same-snapshot re-run byte-identical;
   consume-existing ≡ build-in-request; the pinned VaR is INVARIANT under a later upstream
   exposure/covariance re-run (new rows under new runs are invisible to the pin).

## Known limitations
This is the parametric floor of the VaR family. ES, factor-based historical simulation
(feasible with current data — the nearest-next method, per the user-directed roadmap),
full-revaluation historical (data-blocked on adjusted prices), Monte-Carlo (needs a seeded
simulator + revaluation engine; binds `random_seed`, QS-18), √h multi-horizon scaling,
component/marginal VaR, backtesting (P7-adjacent), a specific-risk term, and a runtime quantile
function are **out of scope for v1** and arrive as separately declared model versions/families.
A future `v2` referent must carry forward the cross-family limitations recorded by the
2026-07-06 retrospective audit rule; this `v1` referent is immutable.
