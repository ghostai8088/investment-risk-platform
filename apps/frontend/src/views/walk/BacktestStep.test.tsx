import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BacktestStep } from "./BacktestStep";
import type { DevSession } from "../../session";

const SESSION: DevSession = { kind: "dev" as const, userId: "u", tenantId: "t" };

function mockRoutes(routes: Record<string, { status?: number; body: unknown }>): void {
  const keys = Object.keys(routes).sort((a, b) => b.length - a.length);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const key = keys.find((k) => url.startsWith(k));
      const r = key ? routes[key] : undefined;
      const status = r?.status ?? (r ? 200 : 404);
      return Promise.resolve({
        ok: status < 400,
        status,
        json: () => Promise.resolve(r ? r.body : {}),
      });
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BacktestStep", () => {
  it("renders a VaR backtest verdict with provenance + facts, and the ES domain-gate note when empty", async () => {
    mockRoutes({
      "/risk/var-backtests/latest": {
        body: [
          {
            id: "bt1",
            calculation_run_id: "run-1",
            model_version_id: "mv-1",
            metric_type: "KUPIEC_LR",
            var_metric_type: "VAR_PARAMETRIC_TOTAL",
            period_start: "2026-05-18",
            period_end: "2026-05-26",
            metric_value: "3.322722",
            test_decision: "PASS",
            n_exceptions: 2,
            n_pairs: 250,
            basel_zone: "GREEN",
            confidence_level: "0.9900",
            horizon_days: 1,
          },
        ],
      },
      "/risk/es-backtests/latest": { body: [] },
    });
    render(<BacktestStep session={SESSION} portfolioId="pf-1" />);
    expect(await screen.findByText("PASS")).toBeTruthy();
    expect(screen.getByText("2 / 250")).toBeTruthy();
    expect(screen.getByText("GREEN")).toBeTruthy();
    // ES pane empty → the honest domain-gate note, not a fabricated verdict.
    expect(screen.getByText(/domain-gated/)).toBeTruthy();
  });

  it("degrades on 403 to a requires-permission note", async () => {
    mockRoutes({
      "/risk/var-backtests/latest": { status: 403, body: {} },
      "/risk/es-backtests/latest": { status: 403, body: {} },
    });
    render(<BacktestStep session={SESSION} portfolioId="pf-1" />);
    expect(await screen.findAllByText(/risk\.view/)).toBeTruthy();
  });
});
