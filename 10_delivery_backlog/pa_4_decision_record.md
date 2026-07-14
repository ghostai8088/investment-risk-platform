# PA-4 Decision Record — residual/idiosyncratic variance (Wave-4 slice 3, the v2 companion)

> **Status: CLOSED 2026-07-14** (RATIFIED 2026-07-14; OQ-PA-4-1…6 all approved — incl. the amended OQ-4, the
> trading-day-adjusted frequency conversion from the vendor-practice benchmark). The Wave-4 companion slice, chosen at
> planning per the ratified roadmap's own criterion ("whichever the PA-3 record judges the tighter
> dependency"): **residual/idiosyncratic variance** — carry the part of a proxied private
> instrument's risk that the factor regression does NOT explain into VaR, instead of silently
> dropping it. The SECOND direct consumer of PA-3's output (its `residual_stdev`), and the first
> honest leg against the platform-wide "specific/idiosyncratic risk = 0" limitation carried
> first-class since P3-3/P3-5. Delivered under the delivery-autonomy grant as EXTENDED
> 2026-07-14 mid-slice: Claude self-drove plan→implement→review→commit→push AND opened + merged
> the PRs (the original "USER merges the PR" sentence here predated the extension — amended at
> the Wave-4 close).

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

**Vendor-practice benchmark (user-directed 2026-07-14; sources checked same day):**

- **MSCI Private Asset Factor Models** (Burgiss data; PE/infrastructure/credit) — private-asset
  "true" returns decompose into (a) factors SHARED with listed assets, (b) pure-private factors,
  and (c) an **asset-specific residual**, after desmoothing (theirs Bayesian; ours Geltner v1).
  *Disposition:* a STRUCTURAL match to the platform's capture→desmooth→proxy→residual chain —
  every major carries the residual for private assets, so PA-4 closes a gap where the current
  residual-of-zero state is the outlier. MSCI's Bayesian desmoothing, pure-private factors, and
  peer-group synthesis are recorded v2/v3 candidates for the PA chain.
- **MSCI Barra (USE4/GEM3)** — per-security specific risk estimated from the residual-return time
  series, DIAGONAL, with **Bayesian shrinkage** (size-decile means) correcting the tendency to
  over-predict high-vol and under-predict low-vol names. *Disposition:* validates OD-E's diagonal
  convention as vendor-standard; shrinkage on the residual estimate = a recorded v2.
- **Axioma (AXWW4/AXUS4)** — idiosyncratic risk as the **EWMA stdev of daily specific returns**
  (60/125-day half-lives), Newey-West autocorrelation adjustments, daily re-estimation.
  *Disposition:* EWMA weighting of the residual = a recorded v2; equal-weighted v1 mirrors the
  platform's covariance convention (OD-P3-4-A).
- **Horizon-scaling practice** — √-time conversion on a **TRADING-day grid** (252/yr; ~63/quarter)
  is the universal market-risk convention; calendar-day grids are reserved for 24/7-priced assets.
  The √t rule assumes low autocorrelation — which the Geltner desmoothing (PA-1) exists to restore,
  an honest supporting note. *Disposition:* **this benchmark UPGRADES OD-D/OQ-4** — v1 adopts the
  trading-day-adjusted conversion (below) rather than plain calendar-day.

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
- **OD-PA-4-D — the frequency conversion (declared; AMENDED per the vendor-practice benchmark):**
  `residual_stdev` is at APPRAISAL-PERIOD frequency; Σ is DAILY (per captured-return day, a
  trading-day grid). v1 declares **trading-day-adjusted √-time de-scaling from the pinned span**:
  `σ_e,daily = σ_e,period / √d̄_t`, where `d̄_t = d̄_cal × (252/365)` and
  `d̄_cal = (summary.period_end − summary.period_start) / n_periods` in calendar days — both
  constants DECLARED model assumptions, everything else deterministic from pinned content alone
  (AD-014), no live read, no imputation; `d̄_cal ≤ 0` fails closed. Plain calendar-day de-scaling
  (the rejected alternative) would understate the daily residual ~17–20% against the universal
  trading-day market-risk convention. A calendar-aware per-period trading-day count (pinning
  holiday calendars) is the recorded v2; irregular spacing uses the honest MEAN period (inherited
  from PA-1, restated).
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
quality (short series ⇒ noisy σ_e — the std errors stay visible on the estimate); the √t conversion
uses a DECLARED flat 252/365 trading-day ratio over the MEAN period (calendar-aware per-period
counts + Barra-style shrinkage / Axioma-style EWMA on the residual are recorded v2s); ES/HS legs
unchanged (the total treatment lands on the parametric family first — the HS analogue is a
recorded v2).

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
- **OQ-PA-4-4 — The declared TRADING-DAY-adjusted √-time frequency conversion from the pinned span
  (OD-D, as amended by the vendor-practice benchmark: `d̄_t = d̄_cal × 252/365`, both constants
  declared).** *Recommend APPROVE — deterministic from pins + two declared constants; aligned with
  the universal market-risk convention (Barra/Axioma/PORT all model on trading-day grids); plain
  calendar-day (the earlier draft) would understate the residual ~17–20% and is recorded as the
  rejected alternative. The calendar-aware per-period count is the v2. The one real methodology
  judgment call.*
- **OQ-PA-4-5 — The additive `var_result.residual_variance` evidence column, migration `0038`
  (OD-F).** *Recommend APPROVE — decomposable evidence beats an opaque total; additive + nullable.*
- **OQ-PA-4-6 — Scope-outs per OD-E/G (diagonal residuals; zero idio for non-proxied/MANUAL; no
  mint; HS/ES analogues deferred).** *Recommend APPROVE.*

## Part 6 — Review dispositions + closure

**Implemented 2026-07-14 (all OQs ratified 2026-07-14).** The 13th governed number:
`risk.var.parametric_total` v1 on the SAME `var_result` (metric_type `VAR_PARAMETRIC_TOTAL`),
migration `0038_var_residual_variance` (one additive nullable `residual_variance
Numeric(38,20)`). Full stack: the residual kernel (`risk/var_total_kernel.py`);
`COMPONENT_KIND_PROXY_WEIGHT` + `proxy_weight_estimate_content` + `build_var_total_snapshot`
under the load-bearing symmetric `VAR_TOTAL_BINDING_PREDICATE`; one-binder dispatch in `run_var`
(the PA-2 precedent); `POST /risk/models/var-parametric-total` + `VarRowOut.residual_variance`;
the methodology referent `05_analytics_methodologies/var_parametric_total_v1.md` + ENT-027/RTM
notes; the battery (`test_var_total{,_kernel,_pg}.py` + `test_var_total_endpoint.py`) incl. the
explicit CI PG step.

### Part 6.1 — The TWO in-build design refinements (amendments to the ratified ODs)

- **OD-D REFINEMENT — declared `appraisal_days` (commit `f7d1b7f`), superseding pin-the-span.**
  OD-C(iii)/OD-D as ratified derived `d̄_cal` from the pinned `ESTIMATION_SUMMARY`'s period span —
  but the summary row carries NO span dates (a factual discovery, not a preference). The cadence
  became the FOURTH declared model-identity parameter (`appraisal_days=N`, N ≥ 1 enforced at
  parse-back per the review, `d̄_t = appraisal_days × 252/365`) — auditable like
  confidence/horizon/z, no desmoothed-run pin needed. OD-B's version identity is accordingly
  `(code_version, confidence, horizon, z, appraisal_days)`.
- **OD-C REFINEMENT — MV from factor-exposure sums (commit `232c3ea`), superseding the
  exposure-atom pin.** OD-C(ii)'s ratified EXPOSURE-atom MV pin was dropped: MV_i = Σ of the
  instrument's pinned `FACTOR_EXPOSURE` `exposure_amount` rows — the projected market exposure
  the factor leg already sees (consistent legs; no partial-proxy partition ambiguity; one fewer
  component kind pinned). No EXPOSURE component appears in a total snapshot.

### Part 6.2 — Review dispositions (4-finder adversarial review, 2026-07-14, Fable)

Four finders (numeric — the mandated Fable-class residual/√-time + decomposition pass;
adversarial binder; governance/consistency; test-completeness): **26 findings → 23 folded, 3
accepted/deferred with reasons. Zero HIGH-severity math defects — every golden number survived
independent 120-digit re-derivation byte-exactly, and a 6000-case fuzz confirmed the
zero-proxied-instrument byte-invariance.**

- **Numeric (6):** goldens/z-constants/invariance CONFIRMED. Folded: the `appraisal_days=0`
  generic-mint identity hole (parse-time floor, the `_hs_window_floor` precedent — also found
  independently by the adversarial finder); the MV accumulation escaping the prec-50 context; the
  false "RAW gated BEFORE quantize" comment (replaced with the probe-verified truth: the
  DEFAULT-context abs() closes the overflow boundary windows, with an explicit do-not-wrap
  warning); the scale-dependent decomposition bound (doc + a DERIVED test tolerance
  `(σ_total+σ_plain)·1E-6` replacing the underived 0.001); a wrong digit-string in a
  hand-reference comment; the PROXY_WEIGHT component comment claiming the pin carries a span.
  Recorded, not taken: restructuring to quantize-then-gate (the plain-family order) — the comment
  fix was chosen as the no-behavior-change fold; the alternative is safe if ever wanted.
- **Adversarial binder (5; 12/12 empirical probes):** folded: the `mapping_method` vocabulary
  gate in `_adjudicate_total_proxies` (a hand-minted MANUAL mapping pin + matching summary
  COMPLETED with the residual attached — probe-verified; now refused + tested); the kernel
  docstring's wrong failure lifecycle (post-create FAILED, not pre-create; both kernel raises now
  honestly labeled binder-unreachable defensive). Attacked and HELD: cross-tenant/provenance (no
  FK stamping from proxy pins, no existence oracle — the P3-5 principal-finding class does not
  re-open); zero-proxy-pin consume parity; duplicate-mapping single-counting; refusal
  completeness (5 malformed-pin mutations all governed 422, zero orphans); predicate leakage into
  HS/backtest consumers (purpose + `METRIC_TYPES` gates hold). Accepted nit: the backtest
  refusal message says "unknown VaR metric_type" for the now-known total family (message text
  stable; the exclusion itself is the recorded v1 scope-out, now documented at the tuple).
- **Governance (6):** folded: the registered `model_limitation` set missing the no-FX bullet the
  doc claimed mirrored (added to `VAR_TOTAL_LIMITATIONS`); five doc/code mirror-drift spots +
  the `specific-risk-= 0` typo (doc now byte-transliterates; the PARTIALLY-discharged expansion
  moved outside the mirrored list); the ENT-027 row's truncated `OD-PA-4-A…D` citation (→ A…G);
  the `METRIC_TYPES` comment re-documented as the BACKTESTABLE subset with the deliberate
  total-exclusion warning; `var_result_content`'s now-false "FULL column set" claim (docs-only —
  adding the key would false-drift every historical BT-1 pin). Clean: hard invariants
  (audit/service.py untouched; no mint; no BYPASSRLS), import fences, exports, serializer/verify
  parity, API gating/MRO. Closeout-scoped: the stale roadmap slice-3 row (updated at closeout
  WITHOUT claiming the partial-proxy `1−Σw` leg — that stays honestly open).
- **Test-completeness (9):** folded: the MISSING CI PG step for `test_var_total_pg.py` (the
  P3-7-review miss-class, recurring — found independently by the fold-synthesis pre-check); the
  magnitude→FAILED total-path test (the every-family precedent, was zero-coverage); TR-09's
  second side (a fresh run picks up the re-promoted estimate — byte-asserted at 6.25× the
  golden); consume-existing ≡ build-in-request + exact re-run reproducibility (a governed-built
  total snapshot consumed happy-path — previously only hand-minted/refusal consumes); the 0038
  chain assertion; the PG DELETE probe (plain-twin symmetry); snapshot-persistence asserts on
  the three build-refusal tests; the residual_stdev boundary trio (zero=accepted-zero-variance
  semantics defined, NULL-pin refused, envelope-exact refused); the multi-proxied-instrument
  end-to-end leg (the governed build-path decomposition test now runs TWO proxied instruments
  with distinct estimates). Reconciled against the adversarial finder: the "non-COMPLETED cited
  run" collapse is SOUND through governed paths (scaffold inserts rows only on the success path
  immediately before COMPLETED) — folded as fixture-docstring precision, not code.

### Part 6.3 — Deferrals (recorded, not folded)

1. **Backtesting the total series** — the standing v1 scope-out (RTM + methodology Known
   limitations), now also guarded by the re-documented `METRIC_TYPES` comment; a total-VaR
   backtest is its own ratifiable slice.
2. **Quantize-then-gate restructure** of the total magnitude gate — behavior-identical
   alternative to the chosen comment fix; take it only with fresh boundary probes.
3. **Residual shrinkage/EWMA, calendar-aware per-period trading-day counts, HS/ES total
   analogues** — the ratified OD-E/OD-G v2s, unchanged.

### Part 6.4 — Post-fold validation

`ruff format --check` + `ruff check` clean; `mypy` clean (173 files); the full pytest suite
green incl. the local-PG leg (schema-reset `irp_pg_local`, head `0038_var_residual_variance`);
`alembic check` no drift; downgrade→upgrade smoke clean; `audit/service.py` FROZEN untouched;
CI-watch-to-green on the fold commit. (Known pre-existing, PA-4-unrelated: the
data_quality/lineage/synthetic PG cross-module seed collision under a single unreset full-suite
session — isolated runs green; a test-infra item, not a product defect.)

### Part 6.5 — CLOSED (2026-07-14)

Impl + review folds merged via **PR #30** = `8ef70db` (commits `d3a6eae` → `f7d1b7f` → `232c3ea`
→ `c04768e`; branch CI green runs 29351248611 + 29355954232; merged-main CI run 29357190562
green). Closeout (roadmap DONE row + log entry + `current_state` pointer + the autonomy-extension
doc amendment) via **PR #31** = `2354a3f` (CI run 29358298194 green). Migration head
`0038_var_residual_variance`. **The FIRST slice opened AND merged by Claude under the 2026-07-14
extended autonomy grant.** Meaning: the first honest idiosyncratic leg — the P3-3/P3-5
specific-risk=0 limitation partially discharged for REGRESSION-cited instruments. Next: the
Wave-4 close review. (This closure block was stamped AT the Wave-4 close — the closeout PR #31
omitted it, caught by the close audit.)
