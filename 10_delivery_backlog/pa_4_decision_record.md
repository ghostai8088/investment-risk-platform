# PA-4 Decision Record — residual/idiosyncratic variance (Wave-4 slice 3, the v2 companion)

> **Status: DRAFT — awaiting OQ ratification (OQ-PA-4-1…6).** The Wave-4 companion slice, chosen at
> planning per the ratified roadmap's own criterion ("whichever the PA-3 record judges the tighter
> dependency"): **residual/idiosyncratic variance** — carry the part of a proxied private
> instrument's risk that the factor regression does NOT explain into VaR, instead of silently
> dropping it. The SECOND direct consumer of PA-3's output (its `residual_stdev`), and the first
> honest leg against the platform-wide "specific/idiosyncratic risk = 0" limitation carried
> first-class since P3-3/P3-5. Delivered under the delivery-autonomy grant (Claude self-drives; the
> USER merges the PR).

## Part 1 — Problem

PA-3 estimates a proxied instrument's factor loadings by OLS and reports, per estimate, the
**residual stdev** — the volatility the CURRENCY factors do NOT explain (R² < 1). Today that number
is persisted as honest evidence and then **ignored by every risk number**: VaR sees only
`x'Σx` (factor risk), so a proxied private book's VaR **understates** its risk by exactly the
unexplained leg — the failure mode the differentiation thesis (§2.1) exists to eliminate. The fix is
the textbook decomposition (Sharpe 1963, the single-index model; Grinold & Kahn 2000 "specific
risk"): total variance = systematic (factor) variance + idiosyncratic residual variance, residuals
uncorrelated with factors and with each other (the diagonal convention).

**The fork this slice resolves (OQ-PA-4-1):** the PA-2 close minted two v2 candidates — (A)
proxy-aware active-risk (relax `_assert_partitioning_exposure_run` with a true-book-value
denominator) and (B) this slice. B is the tighter PA-3 dependency (it consumes `residual_stdev`
directly; A consumes nothing PA-3 produced) and the thesis-direct one (A widens a surface; B stops
an understatement). A stays on the register, trigger unchanged.

*(Naming note: early records used "PA-3" for the money-weighted IRR/capital-calls deferral; the
ratified Wave-4 assigned PA-3 to regression weights. The IRR item KEEPS its register slot and will
be re-labelled (PA-5/PM-2-shaped) when its trigger fires — recorded here to prevent collision.)*

## Part 2 — External benchmarks (rule 6; citations verified 2026-07-14)

- **Sharpe (1963), "A Simplified Model for Portfolio Analysis," *Management Science* 9(2), 277–293**
  — the single-index model: a security's variance = β²·σ_m² + σ_e² with residuals independent
  across securities; portfolio residual variance is the weighted sum of squared residual terms (the
  DIAGONAL convention). *Disposition:* adopted for v1 exactly — per-instrument residual variances
  add (no residual cross-correlation), stated as a declared assumption.
- **Grinold & Kahn (2000), *Active Portfolio Management*** (verified at P3-7) — the factor-model
  specific-risk treatment; residual risk diversifies across names. *Disposition:* consistent with
  the diagonal v1; a residual-correlation model is a recorded v2.
- **Sharpe (1992)** (verified at PA-3) — style-analysis R² as the explained fraction; 1−R² the
  unexplained. *Disposition:* the interpretation leg — PA-3's `residual_stdev` IS the unexplained
  volatility this slice carries into VaR.

## Part 3 — Decisions

- **OD-PA-4-A — the fork: residual variance (B) over proxy-aware active-risk (A).** Rationale in
  Part 1. A remains a recorded register item with its existing trigger (a partial-proxy book that
  needs active risk).
- **OD-PA-4-B — the shape: a NEW registered VaR family through the SAME parametric-VaR binder**
  (the VAR-HS-1/PA-2 one-binder-dispatches-on-bound-model precedent): **`risk.var.parametric_total`
  v1** (code-version-only identity — the z/confidence/horizon declarations mirror the parametric
  family). `σ_total² = x'Σx + Σ_i (MV_i · σ_e,i,daily)²` over the proxied instruments;
  `VaR = z·σ_total`. **Reuses `var_result`** (metric_type `VAR_PARAMETRIC_TOTAL`) — the existing
  parametric family is untouched (byte-identical; a total-risk run is a DIFFERENT registered model).
- **OD-PA-4-C — inputs: the VAR_INPUT snapshot for this family ADDITIONALLY pins, per proxied
  instrument,** (i) its open `proxy_mapping` rows (which instruments are proxied — REUSED
  `COMPONENT_KIND_PROXY_MAPPING`), (ii) its source EXPOSURE atom (the instrument MV — REUSED
  `COMPONENT_KIND_EXPOSURE`), and (iii) the cited PROXY_WEIGHT_ESTIMATE run's `ESTIMATION_SUMMARY`
  row (`residual_stdev` + the period span — a NEW `COMPONENT_KIND_PROXY_WEIGHT` pin, the BT-1
  pin-a-prior-governed-run flavor). The promoted weight's `source_calculation_run_id` is the
  citation chain: pinned weight → its estimate run → its summary row (fail-closed if the cited run
  is missing/not-COMPLETED/wrong-instrument). Binding-predicate switch with SYMMETRIC refusal (the
  PA-2 load-bearing-predicate precedent): the total family refuses a plain VAR_INPUT and the plain
  family refuses a total-predicate snapshot.
- **OD-PA-4-D — the frequency conversion (declared):** `residual_stdev` is at APPRAISAL-PERIOD
  frequency; Σ is DAILY. v1 declares **calendar-day √-time de-scaling from the pinned span**:
  `σ_e,daily = σ_e,period / √d̄`, `d̄ = (summary.period_end − summary.period_start) / n_periods`
  in calendar days — deterministic from pinned content alone (AD-014), no live read, no imputation;
  `d̄ ≤ 0` fails closed. The trading-day refinement (× √(365/252)-style adjustments) is a recorded
  v2; irregular spacing uses the honest MEAN period (inherited from PA-1, restated).
- **OD-PA-4-E — scope: proxied instruments only, diagonal residuals.** A residual term is added for
  each instrument that has (i) open REGRESSION-method proxy weights in the pinned set AND (ii) a
  valid cited estimate run. Indicator (non-proxied) instruments keep zero idiosyncratic risk — the
  P3-3 limitation stands for them, restated first-class. Residuals are independent (Sharpe-1963
  diagonal); MANUAL-method proxy weights carry NO residual (no estimation evidence — the analyst's
  judgment carries no measured unexplained leg; recorded).
- **OD-PA-4-F — persistence evidence: ONE additive nullable column** `residual_variance`
  (`Numeric(38,20)`, the covariance scale) on `var_result` — **migration `0038`** — echoing
  `Σ_i (MV_i·σ_e,i,daily)²` so a reader can decompose total vs factor risk without recomputing
  (NULL on all prior/parametric/HS rows). Magnitude-gated raw before quantize (the standing
  envelope discipline).
- **OD-PA-4-G — reuse everything else:** `risk.run`/`risk.view` (no mint); `CALC.RUN_*` audit
  (reserved-not-emitted for the family); the run surfaces in the FE runs view automatically; FULL
  4-finder review with a Fable-class numeric finder (methodology slice) + Fable fold synthesis (the
  PA-3 lesson).

**Recorded v1 limitations:** diagonal residuals (no residual correlation — v2); non-proxied
instruments still carry zero idiosyncratic risk; the residual is hostage to PA-3's estimation
quality (short series ⇒ noisy σ_e — the std errors stay visible on the estimate); calendar-day
√-time conversion (trading-day v2); ES/HS legs unchanged (the total treatment lands on the
parametric family first — the HS analogue is a recorded v2).

## Part 4 — Verification plan

Hand-derived golden: a two-instrument book (one proxied with a known σ_e, one indicator) — σ_total²
and VaR derived first-principles in-test and byte-matched; the DECOMPOSITION check
(`metric_value² − residual_variance` reproduces the plain-family σ² on the same pins); the
plain-family INVARIANCE check (an identical book with no proxied instruments: total ≡ parametric,
byte-exact); refusal battery (missing/wrong-type/non-COMPLETED cited estimate run,
instrument-mismatch, `d̄ ≤ 0`, MANUAL-weight-no-residual, symmetric predicate refusals both
directions) with no RUNNING orphan; magnitude → committed FAILED; TR-09 both sides under an
estimate re-promotion; PG RLS/append-only leg + CI step; migration 0038 + downgrade smoke; endpoint
register/run/read. Full battery + `make check` + CI-watch-to-green.

## Part 5 — Open questions for ratification

- **OQ-PA-4-1 — The fork: residual/idiosyncratic variance (B) as the Wave-4 companion; proxy-aware
  active-risk (A) stays a registered trigger-based item.** *Recommend APPROVE — B is the tighter
  PA-3 dependency and directly stops a risk understatement; A widens a surface nothing currently
  needs.*
- **OQ-PA-4-2 — The shape: NEW family `risk.var.parametric_total` v1 through the SAME parametric
  binder, reusing `var_result` (OD-B).** *Recommend APPROVE — the VAR-HS-1/PA-2 precedent; the
  plain family stays byte-identical.*
- **OQ-PA-4-3 — The pins + predicate switch (OD-C), incl. the NEW `COMPONENT_KIND_PROXY_WEIGHT`
  and the citation chain through the promoted weight's `source_calculation_run_id`.** *Recommend
  APPROVE — reproducible from the snapshot alone; symmetric refusal both directions.*
- **OQ-PA-4-4 — The declared calendar-day √-time frequency conversion from the pinned span
  (OD-D).** *Recommend APPROVE — deterministic from pins, no imputation; trading-day refinement a
  recorded v2. The one real methodology judgment call.*
- **OQ-PA-4-5 — The additive `var_result.residual_variance` evidence column, migration `0038`
  (OD-F).** *Recommend APPROVE — decomposable evidence beats an opaque total; additive + nullable.*
- **OQ-PA-4-6 — Scope-outs per OD-E/G (diagonal residuals; zero idio for non-proxied/MANUAL; no
  mint; HS/ES analogues deferred).** *Recommend APPROVE.*
