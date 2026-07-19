# Methodology — Total Parametric VaR (factor + idiosyncratic residual, 1-day) v2

> **Model:** `risk.var.parametric_total` · **Version:** `v2` · **Referent:** `model_version.methodology_ref` points here.
> **Status:** REGISTERED; `validation_status = UNVALIDATED` (recorded, **non-enforcing until the VW-1 validation workflow records one**). This doc IS the methodology referent the governed `model_version` binds.
>
> **What v2 changes (BT-2, 2026-07-15, OD-BT-2-C).** The arithmetic is v1's, UNCHANGED and byte-for-byte: v2 adds ONE
> declared identity parameter, **`max_estimate_age_days`** — a STALENESS POLICY on the cited residual estimates. v1 had
> no notion of estimate age: a years-stale `σ_e` drove current total VaR indefinitely and silently (the gap the Wave-4
> close review minted as the estimate-staleness register item). v2 declares a maximum age and REFUSES a run that cites a
> staler estimate, and every total run now ECHOES the age it saw.
>
> **v1 is immutable and still binds** (registrations made before this slice keep working, UNGATED — a grandfathered path
> must not gain a new refusal). The v1 referent stays untouched at `var_parametric_total_v1.md`; this v2 referent carries
> its body forward per the 2026-07-06 retrospective-audit carry-forward rule. To stand a lingering v1 down, a 2L
> validator RECORDS a REJECTED validation against it (VW-1): every new v1 bind then refuses at the shared
> `assert_model_version_of` seam.

## Purpose & applicability
The platform's **13th governed number** and the parametric-VaR family's total-risk sibling:
`risk.var.parametric` (P3-5) carries **zero idiosyncratic risk** by construction (the linear
CURRENCY-family indicator/proxy-loading factor model has no residual term — its largest recorded
honesty gap). PA-4 adds the diagonal (Sharpe 1963 single-index) IDIOSYNCRATIC residual variance of
every PROXIED instrument whose proxy weight was estimated by a governed regression (PA-3,
ENT-057) and PROMOTED (a `REGRESSION`-method `proxy_mapping`), so total portfolio risk = the
SAME factor variance the plain family computes + the sum of each proxied instrument's own
residual variance. Applicable whenever the book contains one or more REGRESSION-proxied
instruments with a completed, cited proxy-weight estimate; degrades EXACTLY to the plain family
(byte-identical σ/VaR) when it does not.

**NOT applicable to** (deferred — see Known limitations): residual cross-correlation/shrinkage
(Barra Bayesian) or EWMA weighting (Axioma); MANUAL-method or non-proxied instruments (zero
idiosyncratic risk, the P3-3 limitation restated for them); multi-horizon √h scaling; historical-
simulation/ES total analogues.

**Backtesting (BT-2, 2026-07-15):** v1 scoped backtesting OUT; **BT-2 admits `VAR_PARAMETRIC_TOTAL` to the governed
backtest lane** (`risk.var_backtest`) — with the honest-pairing doctrine attached, NOT as a constant swap. Every VaR here
is a 1-DAY forecast while an appraisal-marked book's private leg only moves on mark dates, so the daily pairing is biased
TWO WAYS by construction (suppressed off-mark, clustered on-mark) and the unconditional Kupiec/Basel verdict is NOT valid
evidence of adequacy in either direction on such a book. See `var_backtesting_v1.md`'s BT-2 scope amendment for the full
doctrine and read rule.

## Inputs & data policy
- **Inputs:** everything `risk.var.parametric`'s `VAR_INPUT` snapshot pins (the `factor_exposure_
  result` rows of one COMPLETED factor-exposure run + the `covariance_result` rows of one
  COMPLETED covariance run) **PLUS**, per distinct instrument of the pinned exposure rows with an
  OPEN `REGRESSION`-method `proxy_mapping`: the open mapping row(s) (`COMPONENT_KIND_PROXY_
  MAPPING`, the PA-2 per-row FR pin flavor) and the cited proxy-weight estimate's `ESTIMATION_
  SUMMARY` row (`COMPONENT_KIND_PROXY_WEIGHT`, the `var_result` IA-row pin flavor). The compute
  reads **only** the pinned snapshot content — never a live proxy/estimate read.
- **Binding predicate:** `VAR_TOTAL_BINDING_PREDICATE` is LOAD-BEARING and **symmetric** (the
  OD-PA-2-C precedent) — the total model refuses a plain-predicate snapshot (the idiosyncratic
  leg would be silently dropped) and the plain model refuses a total-predicate snapshot (the
  idiosyncratic evidence would be silently discarded).
- **Citation adjudication (build-time, fail-closed BEFORE any write):** a proxied instrument's
  open `REGRESSION` mapping(s) must cite EXACTLY ONE distinct, COMPLETED proxy-weight-estimate
  run whose `ESTIMATION_SUMMARY` names the SAME instrument — missing, ambiguous (>1 distinct
  cited run), or wrong-instrument citations refuse the snapshot build (409).
- **Service-side adjudication (pre-create, both entry paths):** every `PROXY_WEIGHT` pin must be
  an `ESTIMATION_SUMMARY` row (a wrong-type pin refuses); every pinned `PROXY_MAPPING` must
  carry `mapping_method = REGRESSION` (the predicate's contract — a MANUAL-method pin carries no
  estimation evidence and must not smuggle a residual in; 2026-07 review fold); every
  `PROXY_WEIGHT` pin must have a corresponding `PROXY_MAPPING` pin for the SAME instrument AND a
  corresponding pinned `FACTOR_EXPOSURE` row (instrument-mismatch, either direction, refuses);
  NO duplicate `PROXY_WEIGHT` pin per instrument; the pinned `series_currency` MUST equal the
  run-uniform `base_currency` (the currency-match gate — **no FX conversion**, a v1 limitation);
  a missing, negative, or source-column-envelope-exceeding `residual_stdev` refuses (a pinned
  residual of exactly ZERO is a legitimate accepted input contributing zero variance).
- **Data policy:** confidence, horizon, and z are declared exactly as the plain family (SAME
  assumption-prefix machinery); the total family ADDITIONALLY declares `appraisal_days` (the
  residual's calendar-day appraisal cadence, e.g. 91 for quarterly, ≥ 1) — the pinned
  `ESTIMATION_SUMMARY` row carries no period-span dates, so the cadence is declared like
  confidence/horizon, never derived from a pin.
- **MV<sub>i</sub>:** the proxied instrument's TOTAL pinned factor exposure (Σ over its pinned
  `FACTOR_EXPOSURE` rows of `exposure_amount`) — the projected market exposure the factor model
  already sees, consistent with the factor leg (avoids a partial-proxy partition ambiguity).

## Formulas & numerical standards
```
factor_var        = xᵀ Σ x                                              (currency²; the plain family's radicand, clamped)
d_trading          = appraisal_days * (252/365)                          (DECLARED trading-day conversion)
σ_e,i,daily        = σ_e,i,period / √(d_trading)                         (per proxied instrument i)
residual_variance  = Σᵢ (MVᵢ · σ_e,i,daily)²                              (currency²; diagonal — Sharpe 1963)
σ_total            = √(factor_var + residual_variance)   VaR_α = z_α · σ_total   (h = 1)
```
- **Grain:** the SAME `var_result` table, grain `(calculation_run_id, metric_type)` —
  `VAR_PARAMETRIC_TOTAL` (migration `0038_var_residual_variance`, an additive nullable
  `residual_variance` `Numeric(38,20)` column; NO new table/RLS — `var_result` is already IA +
  symmetric RLS from `0026_var`).
- **Decomposition evidence:** `residual_variance` is persisted so a reader can decompose total vs
  factor risk WITHOUT recomputing: `σ_factor² ≈ σ_total² − residual_variance`. The identity is
  exact in unrounded arithmetic (at the prec-50 compute context it holds to within the context
  rounding, ≈ σ²·1E-49); the PERSISTED columns are each independently `quantize_HALF_UP`'d to
  their own scale (`sigma` 6dp, `residual_variance` 20dp), so the column-level identity is
  approximate evidence with a SCALE-DEPENDENT bound — each quantize moves a σ by ≤ half a 6dp
  quantum, so each σ² moves by ≤ σ·1E-6; worst case ≈ `(σ_total + σ_plain)·1E-6` (+ the 20dp
  residual quantum), NOT a flat quantum (2026-07 numeric-finder correction).
- **Rounding / precision:** computed in `Decimal` at 50-digit context precision (matching the
  plain family and the PA-3 estimate); `σ_total`/`VaR` `quantize_HALF_UP` to 6dp
  (`Numeric(28,6)`); `residual_variance` to 20dp (`Numeric(38,20)`, the covariance-scale
  precedent). `σ_total`/`VaR`/`residual_variance` are magnitude-gated against their result-column
  envelopes before persistence (the P3-5 `_MAX_RESULT_ABS` precedent, extended); the gate
  compares under the DEFAULT Decimal context deliberately — the prec-28 rounding of a prec-50
  value closes the boundary windows just under each bound, so nothing that passes the gate can
  overflow a result column at INSERT (probe-verified at all three boundaries, 2026-07 review; a
  genuinely out-of-range input becomes a committed FAILED run with evidence, never a PG 500).
- **Zero-proxied-instrument invariance:** with no proxied instrument, `residual_variance = 0` and
  `σ_total = √factor_var` — BYTE-IDENTICAL to the plain family on the same factor pins (the
  binder reuses the SAME clamped radicand the plain kernel would sqrt).

## Assumptions
Mirrored content-identically into `model_assumption` rows (plus the registration-supplied
`confidence_level=`/`horizon_days=`/`z_score=`/`appraisal_days=` declarations):
- Total parametric VaR: `σ_total = √(x'·Σ·x + Σᵢ(MVᵢ·σ_e,i,daily)²)`; `VaR_α = z_α·σ_total`
  (1-day). The FACTOR leg `x'·Σ·x` is the plain parametric family unchanged; the IDIOSYNCRATIC
  leg adds, per PROXIED instrument, its cited proxy-weight estimate's residual variance (Sharpe
  1963 single-index diagonal — residuals independent across instruments and of the factors).
- Idiosyncratic inputs: per proxied instrument, the pinned open REGRESSION `proxy_mapping` (which
  instruments are proxied + the citation) × the cited `PROXY_WEIGHT_ESTIMATE` run's
  `ESTIMATION_SUMMARY` row (`residual_stdev`). MV<sub>i</sub> = the instrument's total pinned
  factor exposure (the projected market exposure the factor model sees — consistent with the
  factor leg). Indicator (non-proxied) and MANUAL-method instruments carry ZERO idiosyncratic
  variance (no estimation evidence — the P3-3 limitation stands for them, restated).
- Frequency conversion (DECLARED): `σ_e,daily = σ_e,period / √d_t`,
  `d_t = appraisal_days·(252/365)`; `appraisal_days` is a DECLARED model-identity parameter (the
  appraisal cadence, e.g. 91 for quarterly) — the `ESTIMATION_SUMMARY` carries no span, so the
  cadence is declared like confidence/horizon, not derived. Calendar-aware per-period
  trading-day counts are a recorded future version.
- **Estimate staleness (DECLARED, v2 — BT-2/OD-BT-2-C):** `max_estimate_age_days` bounds how old a cited residual
  estimate may be AT THE RUN'S OWN ECONOMIC AS-OF. **Age** = the pinned covariance `window_end` (this run's as-of)
  − the cited estimate's **regression SPAN END** (its `PROXY_WEIGHT_INPUT` snapshot header's `as_of_valuation_date` =
  the last desmoothed period end). The anchor is deliberate: the question a staleness policy asks is *how old is the DATA
  under this `σ_e`*, not when the estimate happened to be computed (the pin's `system_from` — which a re-run preserves
  but which says nothing about data recency). `age > max_estimate_age_days` (strict) ⇒ **pre-create refusal** (422, zero
  run), per cited estimate. A NEGATIVE age (an estimate whose data ends AFTER the as-of — a look-ahead) PASSES: the
  ratified policy is a MAXIMUM age; a look-ahead gate is a different, unratified concern (recorded).
  **Reproducibility (AD-014):** both sides are fixed by the snapshot — `window_end` is pinned content and the header is
  reached through the PINNED `input_snapshot_id`; the header read is live, but `dataset_snapshot` is true-append-only, so
  the same snapshot re-run later yields the same age (the PM-1 drift-free-live-read precedent).
- **The age ECHO:** every total run records `var_result.estimate_age_days` = the MAX age across cited estimates (the
  binding constraint). NULL when nothing was measurable (no proxied instruments; or an UNGATED v1 bind whose estimate
  snapshot cannot be resolved — the echo is EVIDENCE, the gate is POLICY, and a grandfathered path gains no refusal).
  The column is deliberately EXCLUDED from the pinned `var_result` content (adding a pin key would false-drift every
  historical snapshot).
- `z_α` is a REGISTERED constant from the enumerated confidence vocabulary — no runtime
  inverse-normal-CDF. Computed in Decimal at 50-digit context; σ/VaR `quantize_HALF_UP` to 6dp
  (`Numeric(28,6)`); `residual_variance` echoed at 20dp (`Numeric(38,20)`).

## Limitations
Mirrored content-identically into `model_limitation` rows:
- DIAGONAL residuals only (Sharpe 1963; Barra/Axioma vendor-standard) — no residual
  cross-correlation; residual shrinkage (Barra Bayesian) + EWMA weighting (Axioma) are v2s.
- The residual is hostage to the PA-3 estimate quality (short appraisal series ⇒ noisy `σ_e`;
  the estimate's per-coefficient std errors stay visible on the pinned estimate).
- Non-proxied and MANUAL-method instruments carry ZERO idiosyncratic risk (the allocation-v1
  specific-risk=0 limitation propagates for them).
- Flat 252/365 trading-day ratio over the MEAN period (calendar-aware per-period counts a v2);
  1-day horizon only; historical-simulation + ES total analogues are recorded v2s.
- No FX conversion — a proxied instrument's estimate `series_currency` must equal the book's
  `base_currency`; a mismatch refuses rather than converting.
- `validation_status = UNVALIDATED` — recorded, non-enforcing until the P7 validation workflow.

(The specific-risk=0 limitation of the PLAIN family is thereby PARTIALLY discharged — for
REGRESSION-cited instruments only; it still propagates for everyone else. Recorded here outside
the mirrored list: the registered rows are the byte-transliterated bullets above.)

## Validation / reproduction tests
1. **Hand-computed exact references (kernel):** `test_var_total_kernel.py` — MV=1000,
   `σ_e,period`=4%/quarter, `appraisal_days`=91, `factor_var`=100 ⇒ `residual_variance =
   25.46659689516832373975`, `σ_total = 11.201187` (independently derived, 50-digit-precision
   Decimal); the zero-instrument degrade-to-`√factor_var` case; a 3-4-5 diagonal-sum construction
   (independent instruments' contributions sum as squares, no cross term).
2. **Hand-derived golden through the governed CONSUME path:** `test_var_total.py` — the plain
   family's REF1 3-4-5 triangle (x=(30000, 40000), diag 1E-4-variance factors ⇒ `factor_var =
   250000`) plus ONE proxied instrument (MV=30000, `σ_e,period`=4%, `appraisal_days`=91) ⇒
   `residual_variance = 22919.93720565149136577708`, `σ_total = 522.417397`,
   `VaR₉₅ = 859.300151` — byte-matched.
3. **Decomposition + independent cross-check (governed build path, real computed covariance,
   TWO proxied instruments):** `σ_total² − residual_variance ≈` the plain family's `σ²` on the
   SAME upstream runs, asserted against the DERIVED bound `(σ_total + σ_plain)·1E-6` (not a flat
   tolerance); an independent FRESH kernel recomputation from the pinned content byte-matches
   the persisted row — the multi-instrument diagonal summation exercised end-to-end.
4. **Zero-proxied-instrument invariance:** total ≡ plain, byte-exact (both `sigma`/`var_value`);
   **consume-existing ≡ build-in-request + exact re-run reproducibility** (a second run consuming
   the first's governed-built snapshot is byte-identical under a new run id).
5. **Refusal battery:** the symmetric binding-predicate refusal (both directions); missing/
   ambiguous/wrong-instrument cited-run citation (build-time, nothing persisted); wrong-type/
   MANUAL-method-mapping/instrument-mismatch/duplicate/currency-mismatch/negative-or-NULL-or-
   envelope-`residual_stdev` pins (service-time, hand-minted snapshots); a MANUAL-only mapping
   carries zero idiosyncratic risk; a generically-minted `appraisal_days=0` version refuses at
   BIND time (the declared-identity floor); TR-09 BOTH SIDES (a later re-promotion does not move
   an already-pinned estimate AND a fresh run picks up the new estimate).
6. **Post-create FAILED (reachable):** a column-legal-but-extreme pinned `residual_stdev`
   (< 1E8) driving `residual_variance` past `Numeric(38,20)` produces a committed FAILED run
   with a magnitude-naming reason — never a PG overflow 500 (the plain-family
   `column_legal_extreme_magnitude` twin).
7. **PG proofs:** `test_var_total_pg.py` — the `residual_variance` column round-trips its FULL
   20dp precision under a native PG `NUMERIC` (vs SQLite's fixed-scale TEXT emulation, the P3-4
   covariance-precision lesson); tenant isolation of a total-family row; the P0001 append-only
   trigger still blocks UPDATE and DELETE on a row carrying a non-NULL `residual_variance`;
   wired into CI as an explicit migration-job step (the per-slice PG-step pattern).

## Known limitations
This is the FIRST total-risk (factor + idiosyncratic) VaR number and remains a diagonal,
1-day-only, no-FX-conversion floor. Residual shrinkage/EWMA, calendar-aware per-period trading-
day counts, ES/historical-simulation total analogues, and a runtime quantile function are **out of scope** and arrive as
separately declared model versions/families. **Backtesting of the total series is NO LONGER a scope-out** — BT-2 admits
it under the recorded doctrine (above). The **staleness policy is a MAXIMUM age only**: it does not gate look-ahead
estimates, does not consider the estimate's own quality (the PA-3 std errors stay the reader's evidence), and does not
expire a promoted `proxy_mapping` — a stale promotion whose estimate is re-run fresh is out of this gate's reach.
UNGATED pre-BT-2 `v1` registrations remain bindable (the recorded grandfather; VW-1's REJECTED verdict is the stand-down
lever). A future version must carry forward the cross-family limitations recorded by the 2026-07-06 retrospective audit
rule; **this `v2` referent is immutable**.

**Dated amendment (HG-1, 2026-07-17):** the allocation-v1/CURRENCY-family attributions above
predate FL-1 — unproxied and MANUAL-method instruments carry zero idiosyncratic variance under
ANY bound exposure family. Registrar constants corrected at HG-1.

**Dated amendment (RS-1, stamped at the Wave-7 close 2026-07-19):** the "shrinkage (Barra
Bayesian) + EWMA weighting (Axioma) are v2s" statements above are SUPERSEDED for the residual
leg — RS-1 realized `EWMA_RISKMETRICS` and `SHRINKAGE_CROSS_SECTIONAL_EB` as declared estimator
conventions on `risk.proxy_weight.regression` (see `residual_estimation_v1.md`): the cited σ_e
this method consumes may now be EWMA-weighted or EB-shrunk, unchanged in how it enters the
diagonal residual term; residual CROSS-correlation remains open. The registrar's limitation
constant for NEW registrations was reworded at RS-1; the "Mirrored content-identically" claim
above holds for the rows registered at BT-2 and stands as history for them — new registrations
carry the RS-1 wording.
