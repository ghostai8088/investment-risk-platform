/**
 * Hand-written mirrors of the backend risk DTOs (FE-1, OD-FE-1-G — no codegen; the surface is
 * five endpoints). Decimal-valued fields are `string` ON PURPOSE and must stay strings all the
 * way to the DOM: the backend serializes exact fixed-point decimals, and one `Number()` here
 * would silently destroy the platform's PreciseDecimal contract at the last step (OQ-FE-1-7).
 */

export interface RiskRunSummary {
  run_id: string;
  run_type: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  initiated_by: string;
  input_snapshot_id: string | null;
  model_version_id: string | null;
  code_version: string | null;
  environment_id: string | null;
  failure_reason: string | null;
}

export interface RiskRunList {
  items: RiskRunSummary[];
}

/** The shared run envelope of all four per-family `GET /risk/{family}/runs/{run_id}`. */
export interface RunDetailBase {
  run_id: string;
  status: string;
  run_type: string;
  input_snapshot_id: string | null;
  model_version_id: string | null;
  code_version: string | null;
  environment_id: string | null;
  initiated_by: string;
  failure_reason: string | null;
  rows: Record<string, string | number | null>[];
}

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
};

/** The run-detail fetch URL for a family: exposure and the perf families have their own endpoint
 * shapes (``/exposure/runs/{id}``; ``/perf/portfolio-returns/runs/{id}``;
 * ``/perf/benchmark-relative/runs/{id}``), the risk families share ``/risk/{family}/runs/{id}``. */
export function runDetailUrl(family: Family, runId: string): string {
  const id = encodeURIComponent(runId);
  if (family === "exposure") return `/exposure/runs/${id}`;
  if (family === "portfolio-returns") return `/perf/portfolio-returns/runs/${id}`;
  if (family === "benchmark-relative") return `/perf/benchmark-relative/runs/${id}`;
  return `/risk/${family}/runs/${id}`;
}

export const RUN_STATUSES = ["CREATED", "RUNNING", "COMPLETED", "FAILED"] as const;

/** Per-family result-table columns (keys of the row DTOs, rendered verbatim). */
export const FAMILY_ROW_COLUMNS: Record<Family, { key: string; label: string }[]> = {
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
    { key: "n_factors", label: "Factors" },
    { key: "n_observations", label: "N" },
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
};
