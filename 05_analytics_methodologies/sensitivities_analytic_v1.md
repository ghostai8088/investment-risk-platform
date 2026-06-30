# Methodology — Analytic Curve-Node Sensitivities (DV01 / spread-DV01) v1

> **Model:** `risk.sensitivity.analytic` · **Version:** `v1` · **Referent:** `model_version.methodology_ref` points here.
> **Status:** REGISTERED; `validation_status = UNVALIDATED` (recorded, **non-enforcing until P7**). This doc IS the methodology referent the governed `model_version` binds (P3-1, ENT-028, OD-P3-1-C/D/G).

## Purpose & applicability
The first reproducible governed **risk** number on the platform: the analytic first-order
sensitivity (DV01 / spread-DV01) of a **unit (notional = 1) zero-coupon claim** at each captured
yield/spread-curve node, to a 1bp move of that node. It is **curve-intrinsic** — a property of the
captured `curve` / `curve_point` nodes — and is the analytic building block of key-rate / spread
risk. Applicable to captured `ZERO_RATE`, `DISCOUNT_FACTOR`, and `SPREAD` curve nodes.

**NOT applicable to** (deferred — see Known limitations): instrument- or position-attributed
key-rate DV01; option/vega risk; anything requiring interpolation, bootstrapping, or a
pricing/discounting engine.

## Inputs & data policy
- **Inputs:** captured `curve` (ENT-021, FR) headers + their immutable `curve_point` nodes
  (`tenor_days`, `value_type`, `point_value`), pinned into a `SENSITIVITY_INPUT`
  `dataset_snapshot` as `COMPONENT_KIND_CURVE` components. The compute reads **only** the pinned
  snapshot content — never a live curve read — so a result is reproducible under a later curve
  correction.
- **Data policy:** point-in-time as-of compute. **No estimation window, no history, no decay** — a
  sensitivity is a function of the single as-of curve. (History/estimation become load-bearing only
  for later factor/covariance/VaR methods, not this one.)
- **Missing data:** a pinned curve with **no usable node** (no `ZERO_RATE`/`DISCOUNT_FACTOR`/`SPREAD`
  node) fails the fail-closed DQ gate → a committed FAILED run with zero result rows. `PAR_RATE`
  nodes are skipped (not computed).

## Formulas & numerical standards
For a unit zero-coupon claim maturing at node tenor `T` (years), `PV = DF(T)` and
`dPV/d(rate) = -T · DF`, so per a **+1bp** single-node bump:

```
DV01 = -T · DF · 1bp
```

- **Day-count:** `T = tenor_days / 365` (**ACT/365 Fixed**).
- **Compounding:** **continuous** — `DF = exp(-rate · T)`.
- **Bump:** `1bp = 0.0001` absolute.
- **Per `value_type`:**
  - `ZERO_RATE` z → `DF = exp(-z·T)`; `DV01 = -T·DF·1bp`. (`sensitivity_type = DV01`)
  - `DISCOUNT_FACTOR` → the captured `DF` is used **directly** in `-T·DF·1bp` (no implied-zero on
    the compute path — the identity holds however `DF` was obtained). (`sensitivity_type = DV01`)
  - `SPREAD` (the value_type carried by `CREDIT_SPREAD` curves) → `DF = exp(-s·T)`;
    `spread-DV01 = -T·DF·1bp`. (`sensitivity_type = SPREAD_DV01`)
  - `PAR_RATE` → **rejected/deferred** (par→zero needs bootstrapping = curve construction).
- **Evaluation:** AT the captured nodes only — there is deliberately **NO interpolation** between
  nodes (the curve module is captured-never-computed).
- **Rounding / precision:** `quantize_HALF_UP(..., 12)` into `Numeric(28,12)` (the column scale).
  The transcendental `exp` is computed at 50-digit precision then quantized — deterministic,
  Python-only (the kernel never touches the DB, so there is no SQLite/PG split).
- **Units / sign:** per unit notional; sign is the analytic derivative sign (a long position has
  negative DV01 to a rate rise) — recorded as a convention.

## Assumptions
Mirrored verbatim into `model_assumption` rows on the registered version:
- `T = tenor_days / 365` (ACT/365 Fixed).
- Continuous compounding `DF = exp(-rate · T)`.
- `1bp = 0.0001` absolute; analytic closed-form `DV01 = -T·DF·1bp` for a unit zero-coupon claim.
- `DISCOUNT_FACTOR` nodes use the captured DF directly; `ZERO_RATE` use `DF=exp(-z·T)`; `SPREAD` use
  `spread-DV01 = -T·exp(-s·T)·1bp`.
- Evaluated AT captured nodes only — no interpolation.
- Results quantized HALF_UP to 12 dp.

## Limitations
Mirrored verbatim into `model_limitation` rows:
- **Curve-intrinsic only** — NOT instrument- or position-attributed key-rate DV01 (a true instrument
  DV01 needs captured cash-flow terms + interpolation + discounting; deferred).
- `PAR_RATE` nodes are not supported (bootstrapping deferred).
- No interpolation between nodes; no convexity / cross-gamma / second-order terms.
- `validation_status = UNVALIDATED` — recorded but non-enforcing until the P7 validation workflow.

## Validation / reproduction tests
- **Closed-form reproduction:** `node_dv01` / `node_spread_dv01` reproduce hand-computed references
  within ε (e.g. 1Y `ZERO_RATE` 5% → `-0.000095122942`; 2Y `DISCOUNT_FACTOR` 0.90 → `-0.000180000000`).
- **Run reproducibility:** a re-run over the same snapshot yields byte-identical rows; the result is
  **invariant under a later curve supersede/correction** (snapshot-pinned).
- **Governance:** a run with an unregistered `model_version` is refused pre-create (zero run/rows);
  every row binds `dataset_snapshot` + `calculation_run` + a registered `model_version`.

## Known limitations
This is the curve-intrinsic analytic floor. Instrument/position attribution, interpolation,
PAR_RATE, convexity, and option greeks are **out of scope for v1** and are taken up by later P3
slices (which first capture instrument cash-flow terms). A future `v2` `model_version` would carry
its own methodology doc and assumptions; this `v1` referent is immutable.
