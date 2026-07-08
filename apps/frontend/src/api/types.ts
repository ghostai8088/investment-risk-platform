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

/** The four risk run families and their API path segments (the run detail route carries the
 * family so a deep link needs exactly ONE fetch — OD-FE-1-B). */
export const FAMILIES = {
  sensitivities: { runType: "SENSITIVITY", label: "Sensitivities" },
  "factor-exposures": { runType: "FACTOR_EXPOSURE", label: "Factor exposures" },
  covariances: { runType: "COVARIANCE", label: "Covariances" },
  vars: { runType: "VAR", label: "VaR" },
} as const;

export type Family = keyof typeof FAMILIES;

export const RUN_TYPE_TO_FAMILY: Record<string, Family> = {
  SENSITIVITY: "sensitivities",
  FACTOR_EXPOSURE: "factor-exposures",
  COVARIANCE: "covariances",
  VAR: "vars",
};

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
};
