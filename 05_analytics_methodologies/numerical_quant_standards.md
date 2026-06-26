# Numerical & Quant Standards

## Document Control

| Field | Value |
|---|---|
| Document ID | ANALYTICS-NUMSTD-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-06 Quant/Risk Methodology AI |
| Approver | H-02 Head of Model Risk |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | temporal_reproducibility_standard.md, canonical_data_model_standard.md, model_governance_independence_policy.md, control_matrix_skeleton.md |
| Supported Build Rules | BR-1, BR-2, BR-6, BR-9, BR-14 |

## 1. Purpose

Define the numerical conventions every calculation must follow so results are correct, comparable, reproducible, and testable.
These standards are the ground rules beneath each domain methodology (market/credit/counterparty/liquidity/scenario) and the
assertion basis for benchmark tests (BR-1) and reproducibility (TR-13).

## 2A. Ratified Defaults (Step 1C)

Concrete platform defaults. All are **configurable per methodology/tenant** where noted, but these apply unless a documented
exception is registered with the model version.

| Topic | Ratified default | Notes |
|---|---|---|
| Money storage | `DECIMAL` with scale **10**; computation in a decimal context of **≥34 significant digits** (decimal128-equivalent) | No binary float for money (QS-01) |
| Display rounding | Round to the currency's **minor unit** (e.g., USD 2 dp) at presentation only | Internal precision preserved (QS-03) |
| Rounding mode | **Round-half-to-even** (banker's rounding) | Global default for aggregation; **registered exception — `ROUND_HALF_UP` for deterministic canonical serialization / `quantize`** (the snapshot/derived-result reproducibility path: e.g. P2-3 `exposure_aggregate.exposure_amount` `Numeric(28,6)` + the effective composite `fx_rate` `Numeric(28,12)`), so the self-recompute is exact-by-construction (QS-04; TR-13) |
| FX base currency | **USD** as platform base/reporting currency | Configurable per tenant/portfolio (QS-07) |
| FX conversion | Triangulate via base (USD); **mid** rates; rate as-of the valuation date from the designated source; rate version bound to run | QS-08/09 |
| Missing data | **No silent zero-fill.** Use last-known-good with staleness flag within a configurable window (**default 5 business days** for liquid market data); beyond window mark stale + raise DQ exception; proxies only via approved `proxy_mapping` | QS-15/16/17 |
| RNG algorithm | **PCG64** for single-stream; **Philox (counter-based)** for parallel reproducible substreams | Fixed and documented (QS-19) |
| Monte Carlo seeds | Each stochastic run records a **root seed**; parallel paths derive deterministic substreams from the root seed (Philox) so results are independent of thread/worker count; seed + path count bound to the run | QS-18/20; TR-14 |
| Reproduction tolerance | **ε_rel = 1e-12, ε_abs = 1e-9** (same inputs+seed ⇒ effectively exact) | Used by TR-13 and CTRL-018 |
| Benchmark/acceptance tolerance | Default **ε_rel = 1e-6** for analytic methods; Monte Carlo benchmark tolerance set per methodology from standard error | QS-23; CTRL-001 |
| Timestamps / timezone | Store **UTC**, ISO 8601, microsecond precision; business/valuation dates as `date` with a named market calendar; convert only for display | QS-12 |

## 2. Monetary & Numeric Representation (QS)

| ID | Standard |
|---|---|
| QS-01 | Money is stored and computed as **decimal** with explicit precision/scale; **binary floating point is prohibited for monetary values**. |
| QS-02 | Every monetary value carries an ISO 4217 currency; no "naked" amounts. |
| QS-03 | Internal computation precision exceeds display precision; rounding occurs only at defined boundaries. |
| QS-04 | Rounding convention is explicit per context (default: round-half-to-even / banker's rounding for aggregation); documented per methodology. **Registered exception:** deterministic **canonical serialization / `quantize` uses `ROUND_HALF_UP`** (the snapshot + derived-result reproducibility path — e.g. P2-3 `exposure_amount` and the effective composite `fx_rate`), so a stored value re-computes exactly from its stored, rounded inputs (supports TR-13). |
| QS-05 | Rates and ratios are stored unitless with explicit convention (decimal vs percent vs basis points stated, never ambiguous). |
| QS-06 | No silent `NaN`/`Inf`/null-to-zero: undefined results fail loudly and are flagged, not coerced (BR-14 limitation noted). |

## 3. FX Conversion (QS)

| ID | Standard |
|---|---|
| QS-07 | FX rates sourced from a designated source per run; the rate's as-of date matches the calculation's valuation date. |
| QS-08 | Cross rates are derived by triangulation through a defined base currency; direction (quote convention) is explicit. |
| QS-09 | The FX rate version used is bound to the calculation run (reproducibility). The **effective composite rate** produced by a triangulated/reciprocal path is itself a governed numeric value: the **multiplicative composite** of its legs, `ROUND_HALF_UP`-quantized to its declared scale, **version-pinned to the run** via the snapshot-captured FX components (P2-3 `exposure_aggregate.fx_rate` + `fx_legs` — leg references, sign-preserving; no abs/gross/net coercion, QS-06/QS-22). |

## 4. Dates, Calendars & Day-Count (QS)

| ID | Standard |
|---|---|
| QS-10 | Day-count conventions (e.g., ACT/360, ACT/365F, 30/360) are specified per instrument/methodology — never assumed. |
| QS-11 | Holiday calendars (`calendar`, ENT-006) are referenced explicitly; business-day rolling convention (following / modified following / preceding) is declared. |
| QS-12 | All timestamps are UTC; business/valuation dates are explicit and tied to a calendar where roll matters. |

## 5. Curves, Surfaces & Interpolation (QS)

| ID | Standard |
|---|---|
| QS-13 | Interpolation/extrapolation methods for curves and surfaces are declared per methodology (e.g., linear, log-linear, spline); extrapolation beyond data is flagged. |
| QS-14 | Annualization conventions (volatility, returns) are explicit and consistent (e.g., trading-day vs calendar-day basis stated). |

## 6. Missing / Stale Data Treatment (QS)

| ID | Standard |
|---|---|
| QS-15 | Missing inputs are handled by declared rules (proxy, last-good-with-staleness-flag, or exclude-with-flag) — never silent zero-fill. **Operationalized at skeleton in P1A-3** (REQ-DQR-001): the DQ rules engine's no-silent-failure contract (QS-06/15/16/BR-14) surfaces a failing/errored generic rule as a raised exception or a persisted flagged `data_quality_result`, audited `DATA.VALIDATE outcome='failure'`; domain-specific missing/stale handling (proxy, last-known-good window QS-16) arrives with the domain data slices (PUB/PRV, P2/P4). |
| QS-16 | Stale valuations (esp. private assets) are flagged with the valuation date and staleness threshold; downstream results inherit the flag. |
| QS-17 | Proxy mappings (`proxy_mapping`, ENT-019) used in a calculation are recorded as part of lineage and assumptions. |

## 7. Determinism & Stochastic Methods (QS)

| ID | Standard |
|---|---|
| QS-18 | Stochastic calculations (Monte Carlo VaR, PFE, etc.) use a **recorded RNG seed**; the seed and path count are bound to the run (TR-14). |
| QS-19 | The RNG algorithm is fixed and documented; parallelization must be reproducible (deterministic stream partitioning). |
| QS-20 | Convergence criteria / number of paths are configurable and recorded; methodology documents expected Monte Carlo error. |

## 8. Aggregation, Netting & Tolerance (QS)

| ID | Standard |
|---|---|
| QS-21 | Aggregation order is defined where it affects rounding; sums use higher internal precision before final rounding (QS-03). |
| QS-22 | Netting/diversification rules are defined by the domain methodology; this standard fixes only the numeric handling (no double counting; consistent sign conventions). |
| QS-23 | **Reproduction tolerance:** results compare equal if within absolute tolerance `ε_abs` and relative tolerance `ε_rel` (defaults to be ratified, OD-028); used by TR-13 reproducibility and BR-1 benchmark tests. |

## 9. Declaration Requirement

| ID | Standard |
|---|---|
| QS-24 | Every calculation module **declares**: inputs, conventions used (QS refs), assumptions, and limitations (BR-2, BR-14), registered with its model version (model governance). |

## 10. Open Decisions

| ID | Open Decision |
|---|---|
| ~~OD-028~~ | **Resolved (§2A):** reproduction ε_rel=1e-12/ε_abs=1e-9; benchmark ε_rel=1e-6 default. Per-metric MC overrides still set per methodology. |
| ~~OD-029~~ | **Resolved (§2A):** round-half-to-even default; documented per-methodology exceptions allowed. |
| ~~OD-030~~ | **Resolved (§2A):** USD base default (configurable); triangulate via base, mid rates, designated source. |
| ~~OD-031~~ | **Resolved (§2A):** PCG64 single-stream, Philox counter-based for reproducible parallelism. |

## 11. Dependencies

- temporal_reproducibility_standard.md (TR-13/14 seeds, snapshots, tolerance linkage).
- canonical_data_model_standard.md (currency, calendar, proxy entities).
- model_governance_independence_policy.md (declaration → inventory registration).
- AD-006 (calculation-engine pattern).
