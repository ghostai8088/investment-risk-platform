# Proxy factor-exposure projection v1 (`risk.factor_exposure.proxy`)

PA-2 (ENT-028 family; **ENT-019 `proxy_mapping`'s FIRST GOVERNED CONSUMER**) — the thesis §2.1
end-to-end demonstration: a private holding, projected through its captured proxy weights onto the
public CURRENCY factors, flows through the EXISTING governed chain (factor-exposure → covariance →
VaR/active-risk/scenario) so a private asset carries honest, factor-based risk.

## Purpose & applicability

Private assets have no market-observable factor loadings; institutional practice expresses them as
loadings on public factor systems (the public-market-equivalent tradition — Kaplan & Schoar (2005),
*J. Finance* 60(4), for the benchmarking form). v1 consumes the CAPTURED `proxy_mapping` weights
(PA-0: a governance judgment, `mapping_method`-recorded) over ONE mixed public+private book.

## Inputs & data policy

- The pinned `exposure_aggregate` atoms of ONE COMPLETED exposure run + the pinned `factor` EV
  definitions (the allocation-v1 pins, REUSED) **+ the pinned CURRENT-HEAD `proxy_mapping` rows of
  every atom's instrument** (`COMPONENT_KIND_PROXY_MAPPING`; binding predicate
  `v1:exposure-run-atoms+factor-list+proxy-rows`). AD-014 pinned-content-only reads; a later
  weight supersede cannot move a historical run (TR-09, both sides test-proven).
- The proxy binder REFUSES a snapshot whose predicate lacks the proxy rows (a plain allocation-v1
  snapshot would silently degrade the model).

## Formula & numerical standards

Per pinned atom:

```
proxied  (>= 1 pinned proxy row):  exposure_f = quantize_HALF_UP(weight_f × atom, 6)  per proxy factor f
unproxied:                          the allocation-v1 mark-currency indicator rule (loading 1)
```

A proxied instrument's rows REPLACE its indicator row. `loading` = the captured weight (signed,
12dp). **An explicit captured ZERO weight is a "no loading on this leg" judgment** (capture
validates finiteness only): the leg emits no row and the instrument STAYS proxied — never the
indicator fallback. The unallocated residual of a partial proxy (`1 − Σw`) stays UNMODELED
(PA-0 OD-D) — derivable as `atom − Σ allocated`, never imputed. Fail-closed adjudication gates
(the consume-existing trust boundary): an unpinned proxy factor; a proxy pin matching no atom;
a duplicate (instrument, factor) pin; a non-finite weight; the predicate/model pairing checked
in BOTH directions. The raw product is computed at 50-digit precision and envelope-gated
(`|weight × atom| ≥ 1E21` → a committed FAILED run, never a quantize detonation). The
contributions-sum-to-total identity (REQ-MKT-003) holds per-UNPROXIED-atom; a proxied atom sums
to `Σw × atom` BY DESIGN (both regimes test-asserted). See `numerical_quant_standards.md`.

## Validation / reproduction tests

- The mixed-book projection golden (hand-derived: 30000 indicator + {30000, 15000} proxied from a
  50000 atom at weights {0.6, 0.3}).
- **The end-to-end invariance golden:** the proxied private book's parametric VaR is BYTE-IDENTICAL
  to the VaR of the public book holding the same per-factor exposure vector — the thesis statement
  as an exact assertion, run through the REAL covariance + VaR chain.
- TR-09 both sides under a post-run weight supersede; the fail-closed refusal battery (unpinned
  proxy factor; proxy-model-over-plain-snapshot) with no RUNNING orphan; the no-proxy-rows
  degradation to the indicator rule; replace-not-add vs the allocation model.

## Governed-number contract

The SECOND registered model family writing `factor_exposure_result` (the VAR-HS-1
one-table/many-models precedent): run family `FACTOR_EXPOSURE` REUSED, `risk.run`/`risk.view`
REUSED, `CALC.RUN_*` reused, NO migration, NO new canonical id. `code_version`-only identity — the
weights are pinned content, never parameters (the P3-6 shock-vector precedent). The ONE
`run_factor_exposure` binder dispatches on the bound model's code. `audit/service.py` FROZEN.

## Downstream consumption (v1 boundary)

VaR / HS-VaR / scenario consume ABSOLUTE exposures and accept proxy runs unchanged (the
invariance golden proves the chain end-to-end). **ACTIVE RISK refuses a proxy run in v1**: its
weight normalization divides by the summed pinned rows — the net book value only under a
PARTITIONING run; a partial proxy would silently redistribute the unmodeled residual. The gate
fails closed on both entry paths; a proxy-aware denominator is the recorded v2.

## Known limitations

- **Captured MANUAL-judgment weights only** — regression-estimated weights from the PA-1 DESMOOTHED
  return series (the moment PA-1's output becomes an input) are the recorded v2.
- CURRENCY-family proxy factors only (the platform-wide v1 scope; PA-0 OD-H); multi-family
  proxying rides the regression v2.
- The partial-proxy residual is unmodeled — a residual/idiosyncratic variance term is a v2
  candidate.
- `validation_status` UNVALIDATED (non-enforcing until P7).
