import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { NumbersStep } from "./NumbersStep";
import type { DevSession } from "../../session";

const SESSION: DevSession = { userId: "u", tenantId: "t" };

/** Mock fetch with LONGEST-prefix routing so `/models/m1` wins over `/models`. */
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

const RETURN = {
  id: "pr1",
  calculation_run_id: "run-1",
  model_version_id: "mv1",
  metric_type: "TWR_LINKED",
  period_start: "2026-05-18",
  period_end: "2026-05-26",
  return_value: "0.01234500000000000000",
};
const COV = {
  id: "cov1",
  calculation_run_id: "run-2",
  model_version_id: "mv2",
  factor_code_1: "FX_EUR",
  factor_code_2: "FX_USD",
  covariance_value: "-0.00000482689655172414",
  n_observations: 30,
};
const MODEL_DETAIL = {
  id: "m1",
  code: "perf.return.twr",
  tier: "TIER_1",
  versions: [
    {
      id: "mv1",
      limitations: ["CAPTURED-HOLDINGS BOOK: uncaptured cash income understates the return."],
      latest_validation: { outcome: "APPROVED_WITH_CONDITIONS", validation_type: "EXCEPTION", overdue: false },
    },
  ],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderStep(): void {
  render(
    <MemoryRouter>
      <NumbersStep session={SESSION} portfolioId="pf-1" />
    </MemoryRouter>,
  );
}

describe("NumbersStep", () => {
  it("renders numbers with verbatim values, provenance, validation + limitations, and the honest VaR series", async () => {
    mockRoutes({
      "/perf/portfolio-returns/latest": { body: [RETURN] },
      "/risk/covariances/latest": { body: [COV] },
      "/risk/runs": { body: { items: [{ run_id: "var-run-1", status: "COMPLETED" }] } },
      "/models/m1": { body: MODEL_DETAIL },
      "/models": { body: [{ id: "m1" }] },
    });
    renderStep();
    // Value verbatim (trailing zeros survive).
    expect(await screen.findByText("0.01234500000000000000")).toBeTruthy();
    expect(screen.getByText("-0.00000482689655172414")).toBeTruthy();
    // Validation badge (from the model index) + a disclosed limitation.
    expect(await screen.findByText("APPROVED WITH CONDITIONS")).toBeTruthy();
    expect(screen.getByText(/1 disclosed limitation/)).toBeTruthy();
    // The VaR gap is stated honestly, not faked.
    expect(screen.getByText(/API-1b/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /var-run/ })).toBeTruthy();
  });

  it("still shows the numbers when the model inventory is forbidden (validation degrades only)", async () => {
    mockRoutes({
      "/perf/portfolio-returns/latest": { body: [RETURN] },
      "/risk/covariances/latest": { body: [COV] },
      "/risk/runs": { body: { items: [] } },
      "/models": { status: 403, body: {} },
    });
    renderStep();
    // The governed value is still shown...
    expect(await screen.findByText("0.01234500000000000000")).toBeTruthy();
    // ...but validation/limitations degrade to a calm requires-permission note.
    expect(await screen.findAllByText(/model\.inventory\.view/)).toBeTruthy();
  });
});
