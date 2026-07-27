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
  | "tenor_days"
  // PPF-1 (ENT-060): the pure-private factor-return counts + declared min-members floor.
  | "member_count"
  | "period_count"
  | "min_members"
  // A bitemporal row-version integer (FR-versioned captured-input DTOs), not a governed decimal.
  | "record_version"
  // API-2b (breach lifecycle): per-breach monotonic ordering integers, not governed decimals.
  | "seq"
  | "epoch_seq"
  | "expected_seq"
  // RM-1 (ENT-064): the trailing window length in MONTHS — a declared model parameter and part of
  // the four-column grain, an integer. `n_observations` is already listed above.
  | "window_months"
  // NOTIF-1 (breach notification): the source audit-event cursor position, an integer.
  | "source_sequence_no";

/** Keys of `T` whose value can be a `number`. A governed decimal is `string`, so it never qualifies
 * — unless it regressed to `number` or `number | string`. (`-?` strips optionality so nullable
 * fields are checked on their non-null value.) */
type NumberKeys<T> = { [K in keyof T]-?: number extends NonNullable<T[K]> ? K : never }[keyof T];

/** Passes (`true`) iff every `number` field on `T` is a known count — i.e. no decimal regressed. */
type OnlyCountsAreNumbers<T> = Exclude<NumberKeys<T>, CountKey> extends never ? true : false;

/** EXHAUSTIVE guard over every governed row DTO. If any grows a non-count `number` field, `tsc`
 * fails on that row's line. (Includes es-backtest + pacing — not yet FE-displayed families, but
 * governed decimals all the same, guarded from the moment they could be wired.) */
/** Every schema key that names a governed row DTO. */
type RowOutKey = Extract<keyof Schemas, `${string}RowOut`>;

/** The row DTOs that FAIL the contract — i.e. grew a non-count `number` field. `never` when the
 * whole surface is clean; otherwise a union naming exactly which rows regressed. */
type RowOutsWithNonCountNumbers = {
  [K in RowOutKey]: OnlyCountsAreNumbers<Schemas[K]> extends true ? never : K;
}[RowOutKey];

/** Passes iff `T` is `never`. A failure prints the offending row names in the error. */
type AssertNever<T extends never> = T;

/** EXHAUSTIVE BY CONSTRUCTION over every governed row DTO — derived from the schema keys, so a NEW
 * family's DTO is guarded from the moment `make gen-api` emits it, with no list to remember.
 *
 * This replaced a hand-curated ARRAY at RM-1. That array was "exhaustive" only by discipline: I
 * proved by mutation that deleting a row's entry left that DTO silently unguarded — the very
 * failure FE-2 shipped this guard to prevent ("a sampled compile-time contract guard is false
 * security — make it exhaustive"). Curation cannot be the mechanism when forgetting is the risk. */
export type OnlyCountsAreNumbersOnEveryRowOut = AssertNever<RowOutsWithNonCountNumbers>;

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
  AssertString<Schemas["PurePrivateFactorRowOut"]["metric_value"]>,
  // RM-1: NULLABLE by design — NULL exactly when the row is suppressed. `NonNullable` asserts the
  // NON-null branch is a string, so a suppressed row stays representable while a decimal that
  // regressed to `number` still fails here.
  AssertString<NonNullable<Schemas["RollingRiskRowOut"]["metric_value"]>>,
];
