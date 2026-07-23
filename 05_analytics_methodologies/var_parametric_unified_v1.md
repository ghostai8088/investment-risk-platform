# Methodology — Unified public+private Parametric VaR (factor + pure-private block + residual, 1-day) v1

> **Model:** `risk.var.parametric_unified` · **Version:** `v1` · **Referent:** `model_version.methodology_ref` points here.
> **Status:** REGISTERED; `validation_status = UNVALIDATED` (recorded, **non-enforcing until the VW-1 validation workflow records one**). This doc IS the methodology referent the governed `model_version` binds (PPF-3, the §2.1 unification arc's final slice, OD-PPF-3-A…G).

## Purpose & applicability
The platform's **twentieth** governed number and the **differentiator's headline**: the unified
public+private portfolio VaR that finally accounts for the pure-private systematic risk PPF-1 (the
pure-private return series) and PPF-2 (its covariance block Ω_pp) built. Measured against the MSCI
Private Equity / Private Credit Factor Model decomposition (Shepard & Liu 2014; MSCI 2025) —
**True Return = (β·PublicFactor + PurePrivate + AssetSpecific) × Leverage** — PA-4's total VaR had
PublicFactor (`x'Σx`) and lumped PurePrivate+AssetSpecific into ONE **independent** diagonal residual
(no cross-fund private co-movement). PPF-3 **repartitions**: it moves the pure-private-segment
members' non-public variance out of that independent diagonal and into the **correlated** Ω_pp block,
so the number captures that a portfolio's private funds **co-move** in their pure-private risk.

Applicable to a portfolio that holds one or more private funds which are current-head **MANUAL**
members of a `PRIVATE`-family pure-private segment (PPF-1) covered by a completed PPF-2
`risk.covariance.private` (Ω_pp) run, plus the usual public factor-exposure + DAILY covariance +
promoted REGRESSION proxy substrate. It degrades EXACTLY to PA-4's total VaR when the portfolio holds
a single private fund (the pure-private block has no off-diagonal — a **coherence property**,
regression-tested), and to the plain family when it holds none.

**NOT applicable to / deferred (see Known limitations):** the public↔private cross-covariance
(block-diagonal v1); leverage (unlevered v1); the asset-specific split of a multi-member segment's
residual; a residual-autocorrelation diagnostic; multi-horizon √h; historical-simulation / ES unified
analogues; a backtest (the BT-2 honest-pairing doctrine applies as it does to total VaR).

## Inputs & data policy
Pinned into a `VAR_INPUT` `dataset_snapshot` (a NEW binding predicate, so the unified snapshot is
consumable ONLY by the unified binder — OD-3-F):
- the public **FACTOR_EXPOSURE** run rows (the factor leg `x` + each instrument's `MV_i`);
- the public DAILY **COVARIANCE** run rows (Σ);
- per REGRESSION-proxied instrument, its open **PROXY_MAPPING** (REGRESSION) + the cited
  **PROXY_WEIGHT** ESTIMATION_SUMMARY row (`residual_stdev`) — the residual leg substrate;
- the PPF-2 **COVARIANCE** (`run_type=COVARIANCE_PRIVATE`, APPRAISAL) run rows (Ω_pp);
- per private fund, its current-head **MANUAL** `proxy_mapping` membership onto its pure-private
  segment — the key that forms `p` and drives the repartition.

**Data policy:** the compute reads ONLY the pinned content (never a live read; TR-09). The declared
`appraisal_days` (the Ω_pp de-scale cadence, calendar days ≥ 1), `confidence_level`/`horizon_days`/
`z_score`, and `max_estimate_age_days` (the staleness policy on the residual leg's cited estimates)
are model-version identity. Fail-closed: a held segment absent from the pinned Ω_pp run; a stale
cited estimate beyond the declared max age; a currency mismatch; an ill-formed pin — all refuse
pre-create.

## Formulas & numerical standards
```
σ²_unified = x'Σx  +  p'(Ω_pp / d_t)·p  +  Σ_{i : i ∉ any pure-private segment carried in p} (MV_i·σ_e,i,daily)²
VaR_α      = z_α · sqrt(σ²_unified)                                                          [1-day, UNLEVERED]
```
- **Leg 1 (public factor)** `x'Σx` — the plain parametric radicand (unchanged).
- **Leg 2 (pure-private block)** `p'(Ω_pp/d_t)·p`, `p_s = Σ_{i ∈ MANUAL-members(s) ∩ portfolio} MV_i`;
  `Ω_pp,daily = Ω_pp / d_t`, `d_t = appraisal_days·(252/365)` (variance ∝ time under i.i.d.; the whole
  matrix de-scales by `1/d_t` — the covariance analog of PA-4's `σ_e/√d_t`). The portfolio's
  held-segment **principal sub-block** of the PSD Ω_pp is used.
- **Leg 3 (idiosyncratic residual, REPARTITIONED)** the PA-4 diagonal residual over **only**
  proxied instruments that are NOT members of any pure-private segment in `p`. A private-segment
  member's non-public variance is leg 2 alone — **no double-count** (PA-4's `σ_e²` is the WHOLE
  non-public residual `Var(PurePrivate)+Var(AssetSpecific)`, already inside leg 2's `Var(pp)`).
- **The value over total VaR** = `σ²_unified − σ²_total = 2·Σ_{s<t} p_s·p_t·Ω_pp[s,t]/d_t + (small
  diagonal estimator difference)` — precisely the Ω_pp **off-diagonal** cross-fund co-movement.
- **Rounding / precision:** Decimal at 50-digit context; `σ`/`VaR` `quantize_HALF_UP` to 6dp
  (`Numeric(28,6)`); `private_variance` echoed at 20dp (`Numeric(38,20)`). PSD by construction (Gram
  Σ + PSD Ω_pp sub-block + non-negative diagonal residual); a non-finite / negative-total guard fails
  the run closed (defensive; unreachable over adjudicated pins).

## Assumptions
Mirrored content-identically into `model_assumption` rows (plain-ASCII spellings stored; plus the
registration-supplied `confidence_level=`/`horizon_days=`/`z_score=`/`appraisal_days=`/
`max_estimate_age_days=`): the three-leg repartitioned formula; the repartition (no double-count);
the `p`-vector = segment-grouped `MV_i` + the held-segment sub-block; the Ω_pp `1/d_t` de-scale
(i.i.d.-legitimized by desmoothing, Getmansky-Lo-Makarov 2004); block-diagonal vs Σ (approximately
orthogonal by construction); UNLEVERED (leverage=1).

## Limitations
Mirrored content-identically into `model_limitation` rows: block-diagonal ONLY (v2 = a global-factor
linkage, MSCI Barra Integrated Model / Shepard 2015); single-member/thin segments do NOT identify
pure-private-systematic from asset-specific (the block treats the whole member residual as
pure-private; v2 = estimate `a_i = pp_i − pp_s`); a lone private fund reduces to ≈ total VaR;
UNLEVERED (v2 = MSCI relative-leverage; full look-through is data-constrained); √-time transports the
second moment cleanly under i.i.d. but VaR **tail**-scaling degrades under jumps (Danielsson-Zigrand
2006; v2 = a Ljung-Box residual-ACF control); inherits PA-4's residual-leg limitations for the
non-private-segment members; no backtest in v1; `validation_status = UNVALIDATED`.

## Validation / reproduction tests
1. **Kernel hand-computed + `numpy` cross-check:** the private-block quadratic form `p'(Ω/d_t)·p`
   and `sigma_unified` against a hand-computed 2-segment reference at the column scale + an
   independent `numpy` evaluation (numpy TEST-ONLY; `irp_shared` runtime imports NO numpy).
2. **The reduction guardrail (OD-3-G):** for a portfolio with a SINGLE private fund,
   `σ_unified ≈ σ_total,PA4` (the pure-private block has no off-diagonal; the repartition merely
   relabels the residual) — FAILS under a naive additive formula (the anti-double-count guard).
3. **The cross-fund guardrail:** for two single-member segments,
   `σ²_unified − σ²_total = 2·MV_PE·MV_PC·Ω_pp[PE,PC]/d_t` exactly — the only genuinely new term;
   also FAILS under the naive formula.
4. **Repartition completeness:** every private-segment member is EXCLUDED from leg 3 and its variance
   appears in leg 2; a non-private-segment proxied instrument keeps its leg-3 residual.
5. **Isolation (OD-3-F):** a unified snapshot is refused by the plain/total binders (per-family exact
   predicate) and vice-versa; a unified run's row carries `metric_type=VAR_PARAMETRIC_UNIFIED` +
   `private_variance` + `private_covariance_run_id`, excluded from `var_result_content` (no false
   drift on historical BT-1 pins).
6. **Pin invariance (TR-09):** the result is invariant under a post-pin re-run of any upstream
   (public covariance, Ω_pp, exposure, estimate) — the pins capture the versions consumed.

## Known limitations
This is the block-diagonal, unlevered, i.i.d.-scaled floor of the unified number — the assembly that
completes the §2.1 arc. The four recorded v2 seams (a global-factor public↔private linkage; the
asset-specific split for multi-member segments; relative leverage; a residual-ACF tail control) each
carry the disclosure forward; a `v2` referent must carry all four (the carry-forward rule). This
`v1` referent is immutable.

## Sources (Rule-6 external benchmarks)
- Getmansky, Lo & Makarov (2004), "An Econometric Model of Serial Correlation and Illiquidity in
  Hedge-Fund Returns," *Journal of Financial Economics* 74(3): 529–609 (NBER WP 9571) — the
  MA-smoothing model + the downward variance bias `Σθ_j² < 1`; the unsmoothed series is ≈ i.i.d.
  (the √-time legitimizer).
- Geltner (1993), "Estimating Market Values from Appraised Values without Assuming an Efficient
  Market," *Journal of Real Estate Research* 8(3): 325–346 — the appraisal-smoothing level
  correction.
- Okunev & White (2003), "Hedge Fund Risk Factors and Value at Risk of Credit Trading Strategies,"
  SSRN 460641 — the all-order autocorrelation-removal desmoother.
- Danielsson & Zigrand (2006), "On time-scaling of risk and the square-root-of-time rule," *Journal
  of Banking & Finance* 30(10): 2701–2713 — √-time exact only under i.i.d.; the tail caveat.
- Marcato & Key (2007), "Index Smoothing and the Volatility of UK Commercial Property," IPF — ≤2
  lags typically suffice.
- Shepard & Liu (2014), "The Barra Private Equity Model," MSCI Model Insight; the MSCI Private Equity
  Factor Model note; "The MSCI Private Credit Factor Model" (MSCI, Sept 2025) — the
  `(β·Public + PurePrivate + AssetSpecific) × Leverage` decomposition + the relative-leverage outer
  multiplier. *(MSCI PDFs are image scans — exact equations UNVERIFIED; decomposition corroborated via
  MSCI HTML + the 2025 Private Credit note.)*
- Shepard (2015), "Multi-Asset Class Risk: Seeing the Forest and the Trees," MSCI; the Barra
  Integrated Model — the global-factor linkage that is the state-of-the-art beyond block-diagonal
  (the recorded v2).
- ILPA Principles 3.0 (2019) — unlevered-and-levered dual reporting (the unlevered-labeling norm).
- BCBS d457 (2019), FRTB — liquidity-horizon scaling + the look-through leverage hierarchy (no
  supervisory unified-VaR mandate; the nearest touchpoints support the architecture).
