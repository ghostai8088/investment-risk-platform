/**
 * Compile-time guard (FE-2, OQ-FE-1-7 mechanized): every governed RESPONSE decimal MUST generate to
 * TS `string`, never `number`. A `Number()` on a governed value destroys the platform's
 * PreciseDecimal contract, and the ONE historical place a governed number failed to check out was
 * the UI (the FL-1 ES `z×σ` display). If a backend change ever regenerates one of these fields to
 * `number` (or the `number | string` request union), `tsc` fails HERE — so `npm run typecheck` (in
 * `make fe-check` + CI) is the standing enforcement. Types only; nothing runs at runtime.
 */
import type { components } from "./generated/api-types";

type Schemas = components["schemas"];

/** Passes iff `T` is exactly assignable to `string` (a `number` or `number | string` fails). */
type AssertString<T extends string> = T;

// One representative governed decimal per DTO shape (required + nullable, across the class split).
export type GovernedDecimalIsString = [
  AssertString<Schemas["CovarianceRowOut"]["covariance_value"]>,
  AssertString<Schemas["SensitivityRowOut"]["sensitivity_value"]>,
  AssertString<Schemas["VarRowOut"]["var_value"]>,
  AssertString<Schemas["ExposureRowOut"]["exposure_amount"]>,
  AssertString<Schemas["ProxyWeightRowOut"]["metric_value"]>,
  AssertString<NonNullable<Schemas["ScenarioRowOut"]["pnl"]>>,
  AssertString<NonNullable<Schemas["ProxyWeightRowOut"]["std_error"]>>,
  AssertString<Schemas["PortfolioReturnRowOut"]["return_value"]>,
];
