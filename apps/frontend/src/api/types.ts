/**
 * API DTO types + the view-config registry (FE-2, supersedes OD-FE-1-G's hand-written mirrors —
 * OpenAPI codegen now pays rent: 12 families / 24+ endpoints). The DTO types below ALIAS the
 * generated `src/api/generated/api-types.d.ts` (regenerated from the backend's own `/openapi.json`;
 * a CI drift-check fails on any un-regenerated backend change), and FAMILY_ROW_COLUMNS' keys are
 * BOUND to the generated per-family `*RowOut` types so the FL-1 drift class is a `tsc` error.
 *
 * Decimal-valued fields are `string` ON PURPOSE and must stay strings all the way to the DOM: the
 * backend serializes exact fixed-point decimals (verified — every governed `*RowOut` decimal
 * generates to TS `string`), and one `Number()` here would silently destroy the platform's
 * PreciseDecimal contract at the last step (OQ-FE-1-7 — preserved through FE-2).
 */
import type { components } from "./generated/api-types";

type Schemas = components["schemas"];

export type RiskRunSummary = Schemas["RiskRunSummaryOut"];

export type RiskRunList = Schemas["RiskRunListOut"];

/** The run envelope RunDetail reads — derived from a representative generated `*RunOut` (a
 * rename/removal of it is a `tsc` error). It is a near-superset, NOT byte-identical across families:
 * `ExposureRunOut` alone omits `model_version_id` (present on the other 12), so this type is
 * slightly wider than an exposure run's actual header — harmless, since RunDetail renders an absent
 * field the same as `null` ("—"). The `rows` shape is kept permissive so RunDetail renders any
 * family's rows verbatim; the per-family row FIELD KEYS are the drift-guarded part (bound in
 * FAMILY_ROW_COLUMNS below), and a decimal never reaching the DOM as a number is guarded exhaustively
 * in `decimal-contract.ts`. */
export type RunDetailBase = Omit<Schemas["SensitivityRunOut"], "rows"> & {
  rows: Record<string, string | number | null>[];
};

/** The FE-3 governance-walk read DTOs — aliased to the generated schemas (OD-FE-3-D), so a
 * backend rename/removal is a `tsc` error and the CI drift-check stays honest. Decimal fields on
 * these (`quantity`, `mark_value`, `loading`, `exposure_amount`, …) are `string` and stay strings
 * to the DOM (rendered via `verbatim`). */
export type PortfolioSummary = Schemas["PortfolioOut"];
export type Position = Schemas["PositionOut"];
export type Valuation = Schemas["ValuationOut"];
export type FactorExposureRow = Schemas["FactorExposureRowOut"];
export type ExposureRow = Schemas["ExposureRowOut"];
export type PortfolioReturnRow = Schemas["PortfolioReturnRowOut"];
export type CovarianceRow = Schemas["CovarianceRowOut"];
export type VarBacktestRow = Schemas["VarBacktestRowOut"];
export type EsBacktestRow = Schemas["EsBacktestRowOut"];
export type ValidationSummary = Schemas["ValidationSummaryOut"];
export type ValidationDetail = Schemas["ValidationDetailOut"];

/** The run families and their API path segments (the run detail route carries the family so a
 * deep link needs exactly ONE fetch — OD-FE-1-B). The four RISK families are gated ``risk.view``
 * and listed by ``/risk/runs``; ``exposure`` (P3-C2 OD-C) is gated ``exposure.view`` and listed
 * by ``/exposure/runs`` — a SEPARATE permission family, so the runs view selects the source per
 * family rather than merging two independently-paginated endpoints. */
export const FAMILIES = {
  sensitivities: { runType: "SENSITIVITY", label: "Sensitivities", permissionFamily: "risk" },
  "factor-exposures": {
    runType: "FACTOR_EXPOSURE",
    label: "Factor exposures",
    permissionFamily: "risk",
  },
  covariances: { runType: "COVARIANCE", label: "Covariances", permissionFamily: "risk" },
  vars: { runType: "VAR", label: "VaR", permissionFamily: "risk" },
  "active-risk": { runType: "ACTIVE_RISK", label: "Active risk", permissionFamily: "risk" },
  exposure: { runType: "EXPOSURE_AGGREGATE", label: "Exposure", permissionFamily: "exposure" },
  "portfolio-returns": {
    runType: "PORTFOLIO_RETURN",
    label: "Portfolio returns",
    permissionFamily: "perf",
  },
  "benchmark-relative": {
    runType: "BENCHMARK_RELATIVE",
    label: "Benchmark-relative",
    permissionFamily: "perf",
  },
  "var-backtests": {
    runType: "VAR_BACKTEST",
    label: "VaR backtests",
    permissionFamily: "risk",
  },
  scenarios: { runType: "SCENARIO", label: "Scenarios", permissionFamily: "risk" },
  "desmoothed-returns": {
    runType: "DESMOOTHED_RETURN",
    label: "Desmoothed returns",
    permissionFamily: "perf",
  },
  "proxy-weight-estimates": {
    runType: "PROXY_WEIGHT_ESTIMATE",
    label: "Proxy-weight estimates",
    permissionFamily: "risk",
  },
} as const;

export type Family = keyof typeof FAMILIES;

export const RUN_TYPE_TO_FAMILY: Record<string, Family> = {
  SENSITIVITY: "sensitivities",
  FACTOR_EXPOSURE: "factor-exposures",
  COVARIANCE: "covariances",
  VAR: "vars",
  ACTIVE_RISK: "active-risk",
  EXPOSURE_AGGREGATE: "exposure",
  PORTFOLIO_RETURN: "portfolio-returns",
  BENCHMARK_RELATIVE: "benchmark-relative",
  VAR_BACKTEST: "var-backtests",
  SCENARIO: "scenarios",
  DESMOOTHED_RETURN: "desmoothed-returns",
  PROXY_WEIGHT_ESTIMATE: "proxy-weight-estimates",
};

/** The run-detail fetch URL for a family: exposure and the perf families have their own endpoint
 * shapes (``/exposure/runs/{id}``; ``/perf/portfolio-returns/runs/{id}``;
 * ``/perf/benchmark-relative/runs/{id}``), the risk families share ``/risk/{family}/runs/{id}``. */
export function runDetailUrl(family: Family, runId: string): string {
  const id = encodeURIComponent(runId);
  if (family === "exposure") return `/exposure/runs/${id}`;
  if (family === "portfolio-returns") return `/perf/portfolio-returns/runs/${id}`;
  if (family === "benchmark-relative") return `/perf/benchmark-relative/runs/${id}`;
  if (family === "desmoothed-returns") return `/perf/desmoothed-returns/runs/${id}`;
  // Scenario runs are a separate collection (/risk/scenario-runs/{id}) so the run path never
  // collides with /risk/scenarios/{scenario_id} (the definition + its shocks).
  if (family === "scenarios") return `/risk/scenario-runs/${id}`;
  return `/risk/${family}/runs/${id}`;
}

export const RUN_STATUSES = ["CREATED", "RUNNING", "COMPLETED", "FAILED"] as const;

/** Family slug → its generated per-family `*RowOut` type. Hand-authored (the FE knowledge of which
 * family maps to which DTO), but drift-guarded: a renamed/removed backend RowOut is a `tsc` error on
 * the `Schemas[...]` lookup, and a family added to FAMILIES without an entry here errors below. */
type FamilyRowOut = {
  sensitivities: Schemas["SensitivityRowOut"];
  "factor-exposures": Schemas["FactorExposureRowOut"];
  covariances: Schemas["CovarianceRowOut"];
  vars: Schemas["VarRowOut"];
  "active-risk": Schemas["ActiveRiskRowOut"];
  exposure: Schemas["ExposureRowOut"];
  "portfolio-returns": Schemas["PortfolioReturnRowOut"];
  "benchmark-relative": Schemas["BenchmarkRelativeRowOut"];
  "var-backtests": Schemas["VarBacktestRowOut"];
  scenarios: Schemas["ScenarioRowOut"];
  "desmoothed-returns": Schemas["DesmoothedReturnRowOut"];
  "proxy-weight-estimates": Schemas["ProxyWeightRowOut"];
};

/** A display column whose `key` MUST be a field on family F's generated row DTO. This is the FE-2
 * FL-1 kill: a drifted or misspelled column key (the "two missing VaR columns" class) is now a
 * COMPILE error, not a silent blank cell. Labels/ordering stay FE-authored presentation. */
type FamilyColumn<F extends Family> = { key: keyof FamilyRowOut[F] & string; label: string };

/** Per-family result-table columns (keys BOUND to the generated row DTOs, rendered verbatim). */
export const FAMILY_ROW_COLUMNS: { [F in Family]: FamilyColumn<F>[] } = {
  sensitivities: [
    { key: "curve_type", label: "Curve type" },
    { key: "currency_code", label: "Currency" },
    { key: "reference_key", label: "Reference" },
    { key: "value_type", label: "Value type" },
    { key: "tenor_label", label: "Tenor" },
    { key: "tenor_days", label: "Tenor days" },
    { key: "sensitivity_type", label: "Sensitivity" },
    { key: "sensitivity_value", label: "Value" },
    { key: "bump_bps", label: "Bump (bps)" },
  ],
  "factor-exposures": [
    { key: "portfolio_id", label: "Portfolio" },
    { key: "instrument_id", label: "Instrument" },
    { key: "factor_code", label: "Factor" },
    { key: "factor_family", label: "Family" },
    { key: "base_currency", label: "Base ccy" },
    { key: "mark_currency", label: "Mark ccy" },
    { key: "loading", label: "Loading" },
    { key: "exposure_amount", label: "Exposure" },
  ],
  covariances: [
    { key: "factor_code_1", label: "Factor 1" },
    { key: "factor_code_2", label: "Factor 2" },
    { key: "statistic_type", label: "Statistic" },
    { key: "return_type", label: "Return type" },
    { key: "frequency", label: "Frequency" },
    { key: "n_observations", label: "N" },
    { key: "window_start", label: "Window start" },
    { key: "window_end", label: "Window end" },
    { key: "covariance_value", label: "Covariance" },
  ],
  vars: [
    { key: "metric_type", label: "Metric" },
    { key: "base_currency", label: "Base ccy" },
    { key: "confidence_level", label: "Confidence" },
    { key: "horizon_days", label: "Horizon (d)" },
    { key: "z_score", label: "z" },
    { key: "sigma", label: "Sigma" },
    { key: "var_value", label: "VaR" },
    { key: "residual_variance", label: "Residual var" },
    // PPF-3: the UNIFIED number's pure-private block leg (null off VAR_PARAMETRIC_UNIFIED). Its Ω_pp
    // provenance (private_covariance_run_id) rides the API row, not this table — the covariance_run_id
    // / exposure_run_id provenance-id precedent (drill-down, not a column).
    { key: "private_variance", label: "Private var" },
    { key: "estimate_age_days", label: "Est. age (d)" },
    { key: "n_factors", label: "Factors" },
    { key: "n_observations", label: "N" },
    { key: "model_version_id", label: "Model version" },
  ],
  "active-risk": [
    { key: "metric_type", label: "Metric" },
    { key: "base_currency", label: "Base ccy" },
    { key: "te_value", label: "Tracking error" },
    { key: "portfolio_value", label: "Portfolio value" },
    { key: "n_factors", label: "Factors" },
    { key: "n_constituents", label: "Constituents" },
    { key: "benchmark_id", label: "Benchmark" },
    { key: "benchmark_effective_date", label: "Effective date" },
  ],
  exposure: [
    { key: "portfolio_id", label: "Portfolio" },
    { key: "instrument_id", label: "Instrument" },
    { key: "exposure_type", label: "Type" },
    { key: "base_currency", label: "Base ccy" },
    { key: "mark_currency", label: "Mark ccy" },
    { key: "signed_quantity", label: "Quantity" },
    { key: "mark_value", label: "Mark" },
    { key: "fx_rate", label: "FX rate" },
    { key: "exposure_amount", label: "Exposure" },
  ],
  "portfolio-returns": [
    { key: "metric_type", label: "Metric" },
    { key: "period_start", label: "Period start" },
    { key: "period_end", label: "Period end" },
    { key: "begin_mv", label: "Begin MV" },
    { key: "end_mv", label: "End MV" },
    { key: "net_external_flow", label: "Net flow" },
    { key: "return_value", label: "Return" },
    { key: "n_flows", label: "Flows" },
    { key: "n_periods", label: "Periods" },
    { key: "base_currency", label: "Base ccy" },
  ],
  "benchmark-relative": [
    { key: "metric_type", label: "Metric" },
    { key: "period_start", label: "Period start" },
    { key: "period_end", label: "Period end" },
    { key: "metric_value", label: "Value" },
    { key: "portfolio_return_value", label: "Portfolio ret" },
    { key: "benchmark_return_value", label: "Benchmark ret" },
    { key: "return_basis", label: "Basis" },
    { key: "n_benchmark_obs", label: "Bmk obs" },
    { key: "n_periods", label: "Periods" },
    { key: "base_currency", label: "Base ccy" },
  ],
  "var-backtests": [
    { key: "metric_type", label: "Metric" },
    { key: "var_metric_type", label: "VaR method" },
    { key: "period_start", label: "Period start" },
    { key: "period_end", label: "Period end" },
    { key: "metric_value", label: "Value" },
    { key: "realized_pnl", label: "Realized P&L" },
    { key: "var_value", label: "VaR" },
    // BT-3: family-neutral — the column now also renders Christoffersen LR_IND/LR_CC
    // decisions on v2 rows (the Wave-7-close FE-relabel fold).
    { key: "test_decision", label: "Test decision" },
    { key: "basel_zone", label: "Basel zone" },
    { key: "n_pairs", label: "Pairs" },
    { key: "n_exceptions", label: "Exceptions" },
    { key: "base_currency", label: "Base ccy" },
  ],
  "desmoothed-returns": [
    { key: "metric_type", label: "Metric" },
    { key: "period_start", label: "Period start" },
    { key: "period_end", label: "Period end" },
    { key: "metric_value", label: "Value" },
    { key: "observed_return", label: "Observed ret" },
    { key: "observed_stdev", label: "Observed stdev" },
    { key: "alpha", label: "Alpha" },
    { key: "n_periods", label: "Periods" },
    { key: "mark_currency", label: "Mark ccy" },
  ],
  scenarios: [
    { key: "metric_type", label: "Metric" },
    { key: "scenario_code", label: "Scenario" },
    { key: "factor_code", label: "Factor" },
    { key: "factor_family", label: "Family" },
    { key: "shock_value", label: "Shock" },
    { key: "exposure_amount", label: "Exposure" },
    { key: "pnl", label: "P&L" },
    { key: "n_factors_exposed", label: "Exposed" },
    { key: "n_factors_shocked", label: "Shocked" },
    { key: "n_shocks_unmatched", label: "Unmatched" },
    { key: "base_currency", label: "Base ccy" },
  ],
  "proxy-weight-estimates": [
    { key: "metric_type", label: "Metric" },
    { key: "instrument_id", label: "Instrument" },
    { key: "factor_id", label: "Factor" },
    { key: "metric_value", label: "Value" },
    { key: "std_error", label: "Std error" },
    { key: "n_observations", label: "N" },
    { key: "residual_stdev", label: "Residual stdev" },
    { key: "series_currency", label: "Series ccy" },
  ],
};
