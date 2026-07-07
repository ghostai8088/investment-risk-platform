# Methodology — Factor-Exposure Allocation (indicator loadings, CURRENCY family) v1

> **Model:** `risk.factor_exposure.allocation` · **Version:** `v1` · **Referent:** `model_version.methodology_ref` points here.
> **Status:** REGISTERED; `validation_status = UNVALIDATED` (recorded, **non-enforcing until P7**). This doc IS the methodology referent the governed `model_version` binds (P3-3, ENT-028 family, OD-P3-3-A/C/G/J).

## Purpose & applicability
The platform's second governed **risk** number: the factor exposure of a portfolio's positions as
a **deterministic indicator-loading allocation** — the fundamental-factor-model
membership-exposure form. Each governed market-value atom (`exposure_aggregate`, the position's
signed market value in base currency) is allocated to **exactly one** factor of the run's declared
CURRENCY-family factor set. Applicable to the pinned atoms of a **COMPLETED** exposure run and a
pinned `factor` (EV definition) set of the `CURRENCY` family.

**NOT applicable to** (deferred — see Known limitations): vendor-beta or regression-estimated
factor exposures; non-CURRENCY factor families; contribution-to-risk/return (attribution);
anything consuming `factor_return` series.

## Inputs & data policy
- **Inputs:** the immutable `exposure_aggregate` atoms of one COMPLETED exposure run + the
  selected `factor` EV definitions, pinned into a `FACTOR_EXPOSURE_INPUT` `dataset_snapshot` as
  `COMPONENT_KIND_EXPOSURE` (IA-row pin) + `COMPONENT_KIND_FACTOR` (EV pin) components. The
  compute reads **only** the pinned snapshot content — never a live exposure/factor read — so a
  result is reproducible under a later factor-definition amend or exposure re-run.
- **Data policy:** point-in-time — a pure function of the pinned atom set + factor set. **No
  estimation window, no history, no decay, no factor returns.** (History becomes load-bearing at
  P3-4 covariance, not here.)
- **Missing data:** an atom whose `mark_currency` matches **no** pinned factor fails the
  fail-closed DQ gate (`risk.factor_exposure.completeness`) → a committed FAILED run with zero
  result rows. There is **no residual/UNMAPPED bucket** in v1.

## Formulas & numerical standards
For each pinned atom `a` and its matched factor `f` (exact string match
`a.mark_currency == f.currency_code`):

```
loading(a, f)          = 1                       (indicator/membership loading)
factor_exposure(a, f)  = quantize_HALF_UP(loading × a.exposure_amount, 6)
```

- **Dimension:** the CURRENCY family — the mapping attribute is the atom's captured
  `mark_currency`, matched EXACTLY (no normalization) against the factor definition's
  `currency_code` scope.
- **Partition:** the factor set must map every atom to exactly one factor. A duplicate
  `currency_code` in the set (an ambiguous partition) is a **pre-create refusal**; an unmapped
  atom is a **post-create FAILED run** (zero rows).
- **Units / sign:** base currency, per the pinned atom; **signs preserved** (a short atom
  allocates negative exposure — QS-22; no abs/gross/net coercion; gross/net variants deferred).
- **Rounding / precision:** `quantize_HALF_UP(..., 6)` into `Numeric(28,6)` (the
  `exposure_amount` column scale; the QS-04 registered HALF_UP exception). With `loading = 1` the
  quantization is **idempotent** on the already-6dp atom — the result is exact by construction.
- **Sum-to-total (the REQ-MKT-003 acceptance):** because the mapping is a partition and the
  loading is 1, `Σ_f Σ_a factor_exposure(a, f) = Σ_a a.exposure_amount` **exactly (ε = 0)** —
  contributions sum to the pinned input total with zero tolerance.

## Assumptions
Mirrored verbatim into `model_assumption` rows on the registered version:
- Indicator (membership) loadings: `loading = 1` per matched atom; fractional/beta loadings are a
  deferred v2.
- The CURRENCY dimension = the pinned atom's captured `mark_currency`, matched exactly against the
  factor's `currency_code` scope (`mark_currency` is a declared proxy for denomination currency).
- The factor set is a partition: every pinned atom maps to exactly one pinned factor; an unmapped
  atom fails the run closed (no residual bucket).
- `factor_exposure = quantize_HALF_UP(loading × exposure_amount, 6)` (`Numeric(28,6)`, base
  currency; idempotent — exact by construction).
- Signs preserved (no abs/gross/net coercion).
- Contributions sum to the pinned input total exactly (ε = 0) by the partition construction.

## Limitations
Mirrored verbatim into `model_limitation` rows:
- **Allocation exposures only** — NOT vendor-supplied betas (no factor-loading input is captured)
  and NOT regression-estimated loadings (need adjusted-price return history + estimation); both
  deferred as named prerequisites.
- **CURRENCY family only in v1**; ASSET_CLASS/INDUSTRY/COUNTRY/STYLE/MACRO/MARKET dimensions
  deferred (need an instrument pin or captured loadings).
- **`mark_currency` approximates denomination currency** — an instrument marked in a non-native
  currency would misallocate (the instrument-denomination dimension is deferred).
- **Factor returns are NOT consumed** (their first consumer is P3-4 covariance / regression v2).
- **No residual/UNMAPPED bucket** — an unmapped atom fails the whole run closed.
- `validation_status = UNVALIDATED` — recorded but non-enforcing until the P7 validation workflow.

## Validation / reproduction tests
- **Allocation reproduction:** the kernel reproduces hand-computed allocations exactly (e.g. a
  USD atom of `+1000000.000000` against a `{USD, EUR}` factor set → `USD-factor exposure =
  +1000000.000000`, loading `1`); a short atom preserves its sign.
- **Sum-to-total:** `Σ` of result rows equals `Σ` of the pinned atoms **exactly**, per factor and
  overall (ε = 0).
- **Run reproducibility:** a re-run over the same snapshot yields identical rows; the result is
  **invariant under a later factor-definition amend** (EV `record_version` bump) and **under a
  later exposure re-run** (snapshot-pinned).
- **Governance:** a run with an unregistered `model_version` is refused pre-create (zero
  run/rows); every row binds `dataset_snapshot` + `calculation_run` + a registered
  `model_version`.

## Known limitations
This is the allocation floor of factor exposure. Beta/regression loadings, non-CURRENCY
dimensions, residual-bucket semantics, per-factor stored totals, and contribution-to-risk are
**out of scope for v1** and are taken up by later slices (a captured factor-loading slice; the
P3-4 covariance substrate). A future `v2` `model_version` would carry its own methodology doc
(which must also carry forward the standalone-spread CS01 limitation recorded in the 2026-07-06
retrospective audit for the sensitivity method family); this `v1` referent is immutable.
