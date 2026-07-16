# Desmoothed private-asset returns v1 (`perf.return.desmoothed_geltner`)

The ELEVENTH governed number (PA-1, ENT-056) and the differentiation-thesis payload (§2.1): the
platform stops passing smoothed appraisal marks through as truth. A governed **Geltner AR(1)
unsmoothing** of a captured private-asset appraisal mark series, with the introduced uncertainty
stated honestly.

## Purpose & applicability

Appraisal-based valuations (private equity, private credit, real estate, infrastructure) smooth
away volatility and lag market moves — the observed return series UNDERSTATES risk ("volatility
laundering"). Desmoothing before risk measurement is standard institutional private-market
practice; the Geltner filter is the most widely cited baseline. v1 applies to the appraisal mark
series of ONE `(portfolio, instrument)` pair (the PA-0 convention: a private asset's appraised
NAV/unit mark IS a `valuation` row under a documented private `asset_class`).

> **FL-1 applicability note (2026-07-16):** FL-1's factor-loading estimation (the
> `risk.factor_exposure.loadings` family) routes a PUBLIC instrument's raw marks through this
> service at **α = 1** — the identity boundary (`r_true = r_observed` exactly; property-tested).
> The run exists to satisfy PA-3's pinned-provenance chain, NOT to desmooth (a public instrument's
> observed returns need no unsmoothing). The "appraisal-based / private-asset" scope above describes
> the α < 1 unsmoothing use; the α = 1 identity pass-through is a deliberate, disclosed reuse of the
> shipped path (a dedicated raw-return pin kind is the recorded cleaner v2). See
> `factor_exposure_loadings_v1.md`.

## Inputs & data policy

- **Marks** — the CURRENT-HEAD `valuation` rows of the (portfolio, instrument) pair with
  `valuation_date` in the caller-declared window `[window_start, window_end]`, pinned into a
  `DESMOOTHING_INPUT` snapshot (REUSED `COMPONENT_KIND_VALUATION`); the run reads ONLY the pinned
  content (AD-014). A later mark correction cannot move a historical run (TR-09; test-proven both
  sides).
- **α (speed of adjustment)** — a DECLARED registration parameter (part of the model-version
  identity), NOT a request parameter and NOT estimated in-run. Domain `0 < α ≤ 1` (α = 1 is the
  no-smoothing boundary). **Offline estimation procedure (recorded):** fit the observed series'
  first-order autocorrelation ρ₁ and set `α ≈ 1 − ρ₁` (the conventional Geltner identification);
  document the estimation window with the registration's `code_version`.

## Formula & numerical standards

Observed simple returns from consecutive marks, then the Geltner (1991/1993) inversion:

```
r_a,t = mark_t / mark_{t−1} − 1                       (observed; quantize_HALF_UP 12dp)
r_t   = (r_a,t − (1−α)·r_a,t−1) / α                   (desmoothed; quantize_HALF_UP 12dp)
```

The FIRST observed return seeds the recursion and yields NO desmoothed row (no imputation — the
standard treatment): `n` marks → `n−1` observed returns → `n−2` desmoothed rows. Each per-period
`DESMOOTHED_PERIOD` row echoes its consumed inputs (`observed_return`, `begin_mark`, `end_mark`,
`alpha`) so the arithmetic is auditable row-by-row. Computed in Decimal at 50-digit context
(`Numeric(20,12)` results); sample stdev via the P3-5 Decimal-sqrt convention. See
`numerical_quant_standards.md`.

**The honest-uncertainty statement (OD-PA-1-C):** the ONE `DESMOOTHING_SUMMARY` row carries
`metric_value` = the sample stdev (n−1) of the desmoothed series and `observed_stdev` = the sample
stdev of the observed series **over the SAME periods** (like-for-like: `observed[1:]` aligns 1:1
with the desmoothed rows) — "risk was understated by THIS much", computed, not implied. The
volatility ratio is derivable, deliberately not stored.

## Assumptions (declared; mirrored into `model_assumption`)

- The AR(1) single-lag smoothing structure is ASSUMED (`r_a,t = α·r_t + (1−α)·r_a,t−1`).
- α is DECLARED (offline-estimated); the desmoothed series is a MODEL OUTPUT whose error compounds
  an α mis-specification — not an observation.
- The AR(1) step is per-OBSERVATION: appraisal cadence (quarterly by convention) is not
  schema-enforced; irregular spacing is accepted and recorded.
- Simple returns of strictly positive marks; single-currency series.

## Validation / reproduction tests

- Kernel goldens hand-derived in-test (marks 100.00→102.00→104.55→103.5045, α=0.4 ⇒ observed
  [0.02, 0.025, −0.01], desmoothed [0.0325, −0.0625]; summary stdevs 0.0475√2 vs 0.0175√2).
- Property tests: α=1 ⇒ identity (boundary-labeled); stdev-inflation on a positively-
  autocorrelated series (the mechanism the thesis targets).
- TR-09 BOTH sides; the pre-create refusal battery (short series, non-positive/duplicate/mixed
  marks, ambiguous input, unregistered model, out-of-domain α) with NO RUNNING orphan; append-only
  + `run_type != metric_type` + zero-`PERF.*`-audit + migration-head guards; PG RLS + append-only +
  forged-tenant + cross-tenant + audit-chain proofs.

## Governed-number contract

RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND. `desmoothed_return_result` is IA TRUE append-only (a
re-run is a new run + new rows). Registered `perf.return.desmoothed_geltner` v1 with the
**declared-α version identity** (`alpha=` a strict-parsed `model_assumption`; a same-label
re-register with a different α is a governed 409). Run family `DESMOOTHED_RETURN` REUSING
`perf.run`/`perf.view` (no permission mint); `CALC.RUN_*` audit reused;
`PERF.DESMOOTHED_RETURN_CREATE` RESERVED-not-emitted (the standing EVT-230 pattern).
`audit/service.py` FROZEN.

## Known limitations

- **Single-lag AR(1) only** — residual higher-order autocorrelation survives one pass. Recorded
  v2s: **Getmansky-Lo-Makarov (2004)** MA(q) profile inversion; **Okunev-White (2003)** iterative
  higher-order filter (removes autocorrelation of any order by repeated application — verified
  citation: Okunev & White, "Hedge Fund Risk Factors and Value at Risk of Credit Trading
  Strategies", SSRN 460641, Oct 2003; published as Loudon, Okunev & White, *J. Fixed Income* 16(2),
  2006).
- **α mis-specification propagates one-for-one** — the honest-uncertainty summary quantifies the
  volatility change, not the α estimation error itself (an α confidence band is a v2 candidate).
- Irregular appraisal spacing accepted (calendar-regularity gate = v2); single currency (no FX);
  simple returns (no log leg); money-weighted/IRR + capital calls live in the recorded PA-3 item.
- The desmoothed series is not yet consumed downstream — projecting it through `proxy_mapping`
  into the factor-risk chain is PA-2 (the Wave-3 sequence).
- `validation_status` UNVALIDATED (non-enforcing until P7).

## References

- Geltner, D. (1991), "Smoothing in Appraisal-Based Returns", *J. Real Estate Finance and
  Economics* 4(3), 327–345.
- Geltner, D. (1993), "Estimating Market Values from Appraised Values without Assuming an
  Efficient Market", *J. Real Estate Research* 8(3), 325–345.
- Getmansky, M., Lo, A. W., & Makarov, I. (2004), "An econometric model of serial correlation and
  illiquidity in hedge fund returns", *J. Financial Economics* 74(3), 529–609.
- Okunev, J. & White, D. (2003), "Hedge Fund Risk Factors and Value at Risk of Credit Trading
  Strategies", SSRN 460641; published as Loudon, Okunev & White (2006), *J. Fixed Income* 16(2),
  46–61.
