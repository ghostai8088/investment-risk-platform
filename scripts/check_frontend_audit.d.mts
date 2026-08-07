/**
 * Typed surface of `check_frontend_audit.mjs` (RPT-2 slice 0, OQ-W16P-4): lets the frontend's
 * `audit-gate.test.ts` typecheck against the real module's contract. TS resolves this SIBLING
 * `.d.mts` for any `import "./check_frontend_audit.mjs"`. The shim cannot silently rot: vitest
 * executes the real .mjs, so a drift between this surface and the implementation fails the guard
 * test at runtime while typecheck stays green — the pair covers both sides.
 */
export declare const LEVELS: Record<
  "info" | "low" | "moderate" | "high" | "critical",
  number
>;
export declare const GATE: number;
export declare function collectAdvisories(
  report: unknown,
): Map<string, Record<string, unknown>>;
export declare function evaluateAudit(
  report: unknown,
  allowlist: unknown,
  today: string,
): {
  failed: boolean;
  errors: string[];
  warnings: string[];
  info: string[];
  summary: string;
};
