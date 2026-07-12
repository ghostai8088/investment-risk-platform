# Deterministic factor-shock scenario P&L v1 (`risk.scenario.factor_shock`)

The TENTH governed number (P3-6, ENT-029/030). Realizes the reserved-since-genesis stress/scenario
pair: a versioned, saved **scenario definition** (a set of per-factor shocks) applied linearly to a
governed factor-exposure run to produce a deterministic, reproducible scenario P&L.

## Purpose & applicability

Answer "what would this portfolio lose if these factors moved by these amounts?" — the supervisory
stress-testing shape (BCBS "Stress testing principles" 2018; FRTB/MAR standardised shocks ×
sensitivities, BCBS d457; CCAR/DFAST + EBA supervisor-published scenarios). v1 is deliberately a
GOVERNANCE layer over minimal math: the substance is versioned, auditable, reproducible scenario
definitions (BR-8), not novel quantitative modelling.

## Inputs & data policy

- **Exposures** — the per-factor `factor_exposure_result` rows of ONE COMPLETED `FACTOR_EXPOSURE`
  run (P3-3), aggregated to a per-factor total (`exposure_i = Σ` over the run's atoms for factor i).
  CURRENCY factor family only (the platform v1 scope; enforced).
- **Shocks** — the OPEN `scenario_shock` rows of a `scenario_definition`. Each `shock_value` is a
  signed **RETURN fraction** (`-0.10` = −10%). Shocks are **captured, DECLARED values** whatever
  their provenance — hypothetical, offline-derived from a historical episode, or regulatory-
  prescribed (the `scenario_type` label records which; it is provenance, not an attestation).
- Both are pinned into a `SCENARIO_INPUT` snapshot (`COMPONENT_KIND_FACTOR_EXPOSURE` +
  `COMPONENT_KIND_SCENARIO`); the run reads ONLY the pinned content (AD-014). A later shock supersede
  cannot move a historical run (TR-09).

## Formula & numerical standards

Per exposed factor `i`:

```
pnl_i = quantize_HALF_UP(exposure_i × shock_i, 6)      (base currency, Numeric(28,6))
total = Σ_i pnl_i                                       (Σ of the quantized per-factor rows)
```

An exposed factor the scenario does NOT name has `shock_i = 0` (partial coverage — see Assumptions).
Quantization is applied ONCE per per-factor row, then summed, so the stored TOTAL equals the sum of
the stored per-factor rows EXACTLY (no re-rounding drift; test-asserted). No revaluation, no
convexity/gamma — strictly linear first-order (`dV = Σ x_i · r_i`, the same linear factor substrate
every risk number uses). See `numerical_quant_standards.md`.

## Assumptions (declared; mirrored into `model_assumption`)

- Deterministic linear first-order P&L; the shock vector is the pinned scenario content, NOT a request
  parameter (version identity is `code_version` alone).
- **Partial coverage (OD-P3-6-G):** a deterministic scenario is a COMPLETE specification of what
  moves — an exposed-but-unnamed factor is UNCHANGED (shock 0), NOT statistically imputed. Every
  exposed factor gets a result row (its shock echoed, 0 included); the TOTAL row carries
  `n_factors_exposed`, `n_factors_shocked` (exposed AND shocked), and `n_shocks_unmatched` (shocks
  naming a non-exposed factor — applied to nothing, recorded loudly). A shock on a non-exposed factor
  produces no row.
- CURRENCY factor family, RETURN shock type; base currency = the exposure run's base.

## Validation / reproduction tests

- A full-stack golden over a REAL chain (portfolio → exposure → factor-exposure → scenario) with the
  P&L hand-derived from the fixture in the test (the golden-derivation rule).
- TR-09 BOTH sides: a post-run shock supersede does not move the historical result; a re-run against
  the same snapshot reproduces byte-identically.
- Coverage-count assertions (exposed / shocked / unmatched); the exact-sum invariant (TOTAL = Σ rows).
- Append-only + `run_type != metric_type` + zero-`RISK.*`-audit + migration-head + entitlement-parity
  guards; the magnitude gate (a committed FAILED run, no RUNNING orphan).

## Governed-number contract

RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND. `scenario_result` is IA TRUE append-only (a re-run is a new
run + new rows). Registered `risk.scenario.factor_shock` v1; run family `SCENARIO` REUSING
`risk.run`/`risk.view` (no permission mint); `CALC.RUN_*` audit reused; `RISK.SCENARIO_CREATE`
RESERVED-not-emitted (the standing EVT-220 pattern). `audit/service.py` FROZEN.

## Known limitations

- **Linear only** — no revaluation, convexity, gamma, or path dependence; a large shock on a nonlinear
  book is mis-stated with no warning beyond this limitation.
- **Declared shocks only.** Recorded follow-ons: **v2** = in-platform historical-window replay (shocks
  computed from the captured `factor_return` series over a named window — a COMPUTED scenario needing
  window/compounding conventions); **v3** = worst-case / plausibility-constrained scenario search
  (Studer 1997; Breuer, Jandačka, Rheinberger & Summer 2009). Also out of v1: reverse stress testing,
  ES integration, multi-period / propagated scenarios, and non-CURRENCY factor families.
- `scenario_type=REGULATORY` is a label, not an approval — maker-checker on definitions is the P7
  validation workflow. Inherits the captured-holdings-book limitation from the exposure run.
- `validation_status` UNVALIDATED (non-enforcing until P7).
