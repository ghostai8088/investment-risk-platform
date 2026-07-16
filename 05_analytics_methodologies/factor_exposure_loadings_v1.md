# Factor-exposure loadings projection v1 (`risk.factor_exposure.loadings`)

FL-1 (ENT-028 family; the multi-family substrate) — the **proxy projection GENERALIZED**: fractional
signed multi-factor loadings over the widened admitted families, sourced from the same governed
`proxy_mapping` (ENT-019). The THIRD registered model family writing `factor_exposure_result`,
through the SAME `run_factor_exposure` binder (the PA-2 one-binder-dispatches-on-bound-model
precedent, extended to a registry map). This referent is self-declared immutable.

## Purpose & applicability

An instrument's exposure to a factor system is expressed as a set of **loadings** — signed
sensitivities (betas), one per factor, not necessarily summing to one (Sharpe (1992), *J. Portfolio
Management* 18(2), the returns-based style analysis frame — the platform's cited lineage at PA-3).
Where the allocation family PARTITIONS a book by currency and the proxy family projects a
private-asset book onto CURRENCY factors, the loadings family projects ANY instrument onto the
widened admitted family set (`LOADING_FACTOR_FAMILIES` — the FRTB five broad classes + the Barra
cross-sectional families; OTHER/unknown refused). The loadings are a governed input: captured, or —
the recommended source — REGRESSION-estimated (PA-3's OLS pointed at public instruments; see
Estimation below) and promoted through the SAME governance loop.

## Inputs & data policy

- The pinned `exposure_aggregate` atoms of ONE COMPLETED exposure run + the pinned `factor` EV
  definitions **+ the pinned CURRENT-HEAD `proxy_mapping` loading rows of every atom's instrument**
  (`COMPONENT_KIND_PROXY_MAPPING`; binding predicate `v1:exposure-run-atoms+factor-list+loading-rows`).
  AD-014 pinned-content-only reads; a later loading supersede cannot move a historical run (TR-09).
- The loading rows are sourced from the WIDENED ENT-019 `proxy_mapping` (originally private-asset-
  only). `private_instrument_id` is a recorded misnomer for public rows — it retains its name
  because it is a pin-serializer key and renaming it would false-drift every historical pin
  (ENT-058 `instrument_factor_loading` is the reserved clean-schema v2).
- The loadings binder REFUSES a snapshot whose predicate is not its own (the 3×3 symmetry: each of
  the three factor-exposure families requires exactly its predicate and refuses the other two).

## Formula & numerical standards

Per pinned atom, per pinned loading row `(instrument, factor f, loading β_f)`:

```
exposure_f = quantize_HALF_UP(β_f × atom, 6)     (signed; loading β_f echoed at 12dp)
```

Multiple factors per instrument; the loading is fractional and signed. The raw product is computed
at 50-digit precision and envelope-gated (`|β_f × atom| ≥ 1E21` → a committed FAILED run, never a
quantize detonation — the shared kernel). **The coverage gate**: every pinned atom MUST carry ≥ 1
loading row — an UNLOADED atom refuses the run CLOSED (no indicator fallback, unlike the proxy
family; no silent zero — a silently-dropped atom would UNDER-COUNT the downstream VaR). A captured
ZERO loading IS coverage (a declared "this atom projects to nothing"; it emits no row and its whole
value is the honest residual). The carried PA-2 guard: every loading factor must be in the run's
pinned factor list (no silent dropping). See `numerical_quant_standards.md`.

## Projection, not partition

The loadings family is a PROJECTION: `Σ exposure = Σ_atoms(atom · Σ_f β_f) ≠ Σ atoms` in general.
The loaded-atom residual `(1 − Σ_f β_f) · atom` is honestly UNMODELED — derivable, never imputed,
no synthetic residual factor. REQ-MKT-003's ε = 0 sum-to-total acceptance holds for the ALLOCATION
family only (unchanged since PA-2); the allocation family's identity is byte-untouched by FL-1 and
guarded by an invariance regression.

## Estimation (the loadings source)

The recommended loadings source is PA-3's REGRESSION machinery pointed at public instruments: the
OLS estimate → per-coefficient betas + standard errors + R² → the `promote_proxy_weight_estimate`
governance loop, unchanged. The return source rides PA-1's desmoothing path at **α = 1** (the
Geltner identity transform, `r_true = r_observed` exactly — see `desmoothing_geltner_v1.md`, whose
Purpose is amended for this public-instrument use): the α = 1 run exists to satisfy the
pinned-provenance chain, NOT to transform. Vendor-supplied betas are the recorded v2 (an empty
capture table until a feed exists), flowing through the SAME promote step. **Honesty carried
forward:** the regression runs on PRICE returns (marks — no dividend capture exists), so estimated
betas are price-return betas; single-name RBSA over a short window yields noisy betas — the standard
errors and R² stay first-class on the estimate rows.

## Validation / reproduction tests

- The fractional multi-factor projection golden (hand-derived: a 50000 atom, loadings
  {MARKET 0.8, STYLE −0.2} → {40000, −10000}, Σ = 30000 ≠ 50000 — the projection, one signed leg).
- The family widening (a MARKET/STYLE loading is admitted where the allocation/proxy families
  refuse it); the three moved probe tests (STYLE/MARKET now admitted → the OTHER catch-all refused).
- The COVERAGE GATE: an unloaded atom refuses the run closed; a captured zero loading IS coverage.
- **The through-VaR invariance:** a loadings run over CURRENCY factors at weights {0.6, 0.3} yields
  a VaR BYTE-IDENTICAL to the PROXY run over the same weights — VaR consumes loadings rows unchanged
  (no silent drop, no double-count).
- The 3×3 predicate symmetry (each family refuses the other two families' snapshots).

## Governed-number contract

The THIRD registered model family writing `factor_exposure_result`: run family `FACTOR_EXPOSURE`
REUSED, `risk.run`/`risk.view` REUSED, `CALC.RUN_*` reused, **NO migration, NO new canonical id**
(the loading column, the 4-tuple grain, and the unconstrained component kinds all pre-exist).
`code_version`-only identity — the loadings are pinned content, never parameters. The ONE
`run_factor_exposure` binder dispatches on the bound model's code via the `_EXPOSURE_FAMILIES`
registry map. `audit/service.py` FROZEN. The FRTB family names (RATES/CREDIT_SPREAD/COMMODITY +
the CURRENCY≡FX, MARKET≡equity aliases) are VOCABULARY — they classify factors and confer NO FRTB
capital-calculation semantics.

## Downstream consumption (v1 boundary)

VaR / HS-VaR / total consume ABSOLUTE exposures per factor and accept loadings runs unchanged (the
through-VaR invariance proves the chain). **SCENARIO refuses a non-CURRENCY loadings run** at its
run-binder family gate (`scenario_service.py`; shock semantics per FRTB class are methodology work,
not a gate flip — the recorded MF-1-or-later candidate). **ACTIVE RISK refuses a loadings run** (its
allocation-only model-code whitelist — a loadings-aware denominator is the recorded v2, open since
PA-2). Covariance consumes factor returns, not exposure rows (not a consumer).

## Known limitations

- The loaded-atom residual is unmodeled; the loadings family is a projection, not a partition.
- Price-return betas (no dividend capture) + short-window single-name regression noise — the
  standard errors and R² stay first-class; any loadings-family validation must cite them.
- The demo tenant stays CURRENCY-only through FL-1 (the MG-1 flagship AWC premise holds until MF-1
  closes it with the TRIGGERED re-validation).
- `validation_status` UNVALIDATED (non-enforcing until a 2L validator records an outcome, VW-1).
