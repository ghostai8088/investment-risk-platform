import type { ReactElement } from "react";

export interface ValidationInfo {
  tier?: string | null;
  outcome?: string | null;
  overdue?: boolean | null;
}

/** Outcome → severity class (deny-by-default: anything unrecognized reads as neutral/muted). */
const OUTCOME_CLASS: Record<string, string> = {
  APPROVED: "ok",
  APPROVED_WITH_CONDITIONS: "warn",
  REJECTED: "bad",
  IN_PROGRESS: "info",
};

/**
 * A model's governance status as a compact badge (OD-FE-3-C): tier, the latest validation outcome,
 * and an overdue-review flag. `UNVALIDATED` is shown honestly (the SR 26-2 posture — a number can
 * run before validation), never hidden.
 */
export function ValidationBadge({ info }: { info: ValidationInfo }): ReactElement {
  const outcome = info.outcome ?? "UNVALIDATED";
  const cls = OUTCOME_CLASS[outcome] ?? "muted";
  return (
    <span className="validation-badge">
      {info.tier ? <span className="badge tier">{info.tier.replace(/_/g, " ")}</span> : null}
      <span className={`badge outcome ${cls}`}>{outcome.replace(/_/g, " ")}</span>
      {info.overdue ? <span className="badge bad">review overdue</span> : null}
    </span>
  );
}
