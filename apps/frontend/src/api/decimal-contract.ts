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
/** Every schema key that names a governed row DTO — derived, so a NEW result family is covered the
 * moment `make gen-api` emits it. */
type RowOutKey = Extract<keyof Schemas, `${string}RowOut`>;

/** Governed DTOs carrying decimals that do NOT follow the `*RowOut` naming — captured-input and
 * control-plane surfaces. These must stay CURATED: no naming rule identifies them.
 *
 * **This list exists because RM-1 nearly deleted it.** The guard was rewritten from a hand-curated
 * array to a derived `*RowOut` mapped type; the array had 22 entries and only 15 matched that
 * template, so the rewrite silently dropped these 7 — added deliberately at FE-3 ("guard the moment
 * a decimal could be wired") and API-2b (the LimitOut backfill). Caught by adversarial review, not
 * by tsc: dropping a name from a guard cannot fail a compile. Derive what a rule can identify;
 * curate the rest — and never let "exhaustive by construction" mean "narrower than what it
 * replaced". */
type ExtraGovernedDtoKey =
  | "PositionOut"
  | "ValuationOut"
  | "BreachOut"
  | "BreachActionOut"
  | "BreachNotificationOut"
  | "LimitOut"
  | "LimitHealthOut";

/** Every governed DTO the contract covers: the derived row families PLUS the curated extras. */
type GuardedDtoKey = RowOutKey | ExtraGovernedDtoKey;

/** The DTOs that FAIL the contract — i.e. grew a non-count `number` field. `never` when the whole
 * surface is clean; otherwise a union naming exactly which ones regressed. */
type DtosWithNonCountNumbers = {
  [K in GuardedDtoKey]: OnlyCountsAreNumbers<Schemas[K]> extends true ? never : K;
}[GuardedDtoKey];

/** Passes iff `T` is `never`. A failure prints the offending DTO names in the error. */
type AssertNever<T extends never> = T;

/** EXHAUSTIVE over every governed DTO: the `*RowOut` families derived from the schema keys, plus
 * the curated non-`RowOut` set above. A new result family is guarded automatically; a new
 * non-`RowOut` governed DTO must be added to `ExtraGovernedDtoKey` — and THAT is the residual gap,
 * stated rather than glossed, because no naming rule can close it. */
export type OnlyCountsAreNumbersOnEveryRowOut = AssertNever<DtosWithNonCountNumbers>;

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
