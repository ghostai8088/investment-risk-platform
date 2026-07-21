/**
 * Compile-time guard (FE-2, OQ-FE-1-7 mechanized): a governed value must NEVER reach the DOM as a
 * JS `number` — the backend serializes exact fixed-point decimals as strings, and a `Number()`/JSON
 * numeric parse destroys the PreciseDecimal contract (the ONE historical place a governed number
 * failed to check out was the UI: the FL-1 ES `z×σ` display). This file is types only (nothing runs
 * at runtime); it is compiled by `tsc --noEmit` (in `make fe-check` + CI), so a violation is a red
 * build.
 *
 * The guarantee is EXHAUSTIVE, not sampled (the FE-2 review HIGH fold): `OnlyCountsAreNumbers`
 * asserts that on EVERY generated governed row DTO the only fields typed `number` are known INTEGER
 * COUNTS (curated in `CountKey`). Every other field — ids/codes/dates/currencies AND every governed
 * DECIMAL — is a string. So if a backend change ever declares a response decimal as `Decimal`
 * instead of `str` (it would then serialize as `number | string`), that field becomes a `number`
 * key absent from `CountKey`, and `tsc` fails HERE — for the WHOLE surface, not a sampled few.
 */
import type { components } from "./generated/api-types";

type Schemas = components["schemas"];

/** The integer/count fields legitimately typed `number` on the governed row DTOs (curated from the
 * current generated schema: every `n_*` count, the `*_days`, `period_index`, `min_observations`).
 * Add a genuinely-new INTEGER here when the backend ships one; NEVER add a decimal — a decimal
 * belongs in `string`, and keeping it out of this set is exactly what makes the guard bite. */
type CountKey =
  | "estimate_age_days"
  | "horizon_days"
  | "min_observations"
  | "n_benchmark_obs"
  | "n_constituents"
  | "n_exceptions"
  | "n_factors"
  | "n_factors_exposed"
  | "n_factors_shocked"
  | "n_flows"
  | "n_observations"
  | "n_pairs"
  | "n_periods"
  | "n_regressors"
  | "n_shocks_unmatched"
  | "period_index"
  | "tenor_days";

/** Keys of `T` whose value can be a `number`. A governed decimal is `string`, so it never qualifies
 * — unless it regressed to `number` or `number | string`. (`-?` strips optionality so nullable
 * fields are checked on their non-null value.) */
type NumberKeys<T> = { [K in keyof T]-?: number extends NonNullable<T[K]> ? K : never }[keyof T];

/** Passes (`true`) iff every `number` field on `T` is a known count — i.e. no decimal regressed. */
type OnlyCountsAreNumbers<T> = Exclude<NumberKeys<T>, CountKey> extends never ? true : false;

/** Passes iff `T` is exactly `true` (a `false` — a decimal-turned-number — is a constraint error). */
type AssertTrue<T extends true> = T;

/** EXHAUSTIVE guard over every governed row DTO. If any grows a non-count `number` field, `tsc`
 * fails on that row's line. (Includes es-backtest + pacing — not yet FE-displayed families, but
 * governed decimals all the same, guarded from the moment they could be wired.) */
export type OnlyCountsAreNumbersOnEveryRowOut = [
  AssertTrue<OnlyCountsAreNumbers<Schemas["SensitivityRowOut"]>>,
  AssertTrue<OnlyCountsAreNumbers<Schemas["FactorExposureRowOut"]>>,
  AssertTrue<OnlyCountsAreNumbers<Schemas["CovarianceRowOut"]>>,
  AssertTrue<OnlyCountsAreNumbers<Schemas["VarRowOut"]>>,
  AssertTrue<OnlyCountsAreNumbers<Schemas["ActiveRiskRowOut"]>>,
  AssertTrue<OnlyCountsAreNumbers<Schemas["ExposureRowOut"]>>,
  AssertTrue<OnlyCountsAreNumbers<Schemas["PortfolioReturnRowOut"]>>,
  AssertTrue<OnlyCountsAreNumbers<Schemas["BenchmarkRelativeRowOut"]>>,
  AssertTrue<OnlyCountsAreNumbers<Schemas["VarBacktestRowOut"]>>,
  AssertTrue<OnlyCountsAreNumbers<Schemas["ScenarioRowOut"]>>,
  AssertTrue<OnlyCountsAreNumbers<Schemas["DesmoothedReturnRowOut"]>>,
  AssertTrue<OnlyCountsAreNumbers<Schemas["ProxyWeightRowOut"]>>,
  AssertTrue<OnlyCountsAreNumbers<Schemas["EsBacktestRowOut"]>>,
  AssertTrue<OnlyCountsAreNumbers<Schemas["PacingRowOut"]>>,
];

/** Illustrative companion: a handful of named governed decimals asserted `string` outright — human
 * documentation of the contract the exhaustive guard above enforces structurally. */
type AssertString<T extends string> = T;
export type GovernedDecimalIsString = [
  AssertString<Schemas["CovarianceRowOut"]["covariance_value"]>,
  AssertString<Schemas["SensitivityRowOut"]["sensitivity_value"]>,
  AssertString<Schemas["VarRowOut"]["var_value"]>,
  AssertString<Schemas["ExposureRowOut"]["exposure_amount"]>,
  AssertString<Schemas["ProxyWeightRowOut"]["metric_value"]>,
  AssertString<NonNullable<Schemas["ScenarioRowOut"]["pnl"]>>,
  AssertString<Schemas["PortfolioReturnRowOut"]["return_value"]>,
];
