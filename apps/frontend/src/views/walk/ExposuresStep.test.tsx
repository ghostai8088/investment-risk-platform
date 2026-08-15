import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExposuresStep } from "./ExposuresStep";
import type { DevSession } from "../../session";

const SESSION: DevSession = { kind: "dev" as const, userId: "u", tenantId: "t" };

function mockRoutes(routes: Record<string, unknown>, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const key = Object.keys(routes).find((k) => url.startsWith(k));
      return Promise.resolve({
        ok: key !== undefined && status < 400,
        status: key === undefined ? 404 : status,
        json: () => Promise.resolve(key === undefined ? {} : routes[key]),
      });
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ExposuresStep", () => {
  it("renders factor exposures (with run provenance) and the aggregate, decimals verbatim", async () => {
    mockRoutes({
      "/risk/factor-exposures/latest": [
        {
          id: "f1",
          calculation_run_id: "run-aaaa-bbbb-cccc-dddd",
          model_version_id: "mv-aaaa-bbbb-cccc-dddd",
          instrument_id: "inst-1",
          factor_code: "FX_EUR",
          factor_family: "CURRENCY",
          loading: "1.00000000",
          exposure_amount: "300.000000",
        },
      ],
      "/exposure/latest": [
        {
          id: "e1",
          instrument_id: "inst-1",
          exposure_type: "MARKET_VALUE",
          mark_value: "300.000000",
          exposure_amount: "300.000000",
        },
      ],
    });
    render(<ExposuresStep session={SESSION} portfolioId="pf-1" />);
    expect(await screen.findByText("FX_EUR")).toBeTruthy();
    expect(screen.getByText("1.00000000")).toBeTruthy(); // loading, trailing zeros intact
    expect(screen.getByText(/From run/)).toBeTruthy();
    expect(screen.getAllByText("MARKET_VALUE").length).toBeGreaterThan(0);
  });

  it("degrades the factor-exposure pane on 403 (requires risk.view)", async () => {
    mockRoutes({ "/risk/factor-exposures/latest": {}, "/exposure/latest": [] }, 403);
    render(<ExposuresStep session={SESSION} portfolioId="pf-1" />);
    expect(await screen.findAllByText(/You need the/)).toBeTruthy();
    expect(screen.getAllByText(/risk\.view/).length).toBeGreaterThan(0);
  });

  it("renders a two-measure holding side by side (STRUCT-1, REQ-PPM-006)", async () => {
    mockRoutes({
      "/risk/factor-exposures/latest": [],
      "/exposure/latest": [
        {
          id: "e1",
          portfolio_id: "pf-1",
          instrument_id: "inst-bond",
          exposure_type: "MARKET_VALUE",
          mark_value: "985.400000",
          exposure_amount: "246350.000000",
        },
        {
          id: "e2",
          portfolio_id: "pf-1",
          instrument_id: "inst-bond",
          exposure_type: "NOTIONAL",
          mark_value: "1000.0000",
          exposure_amount: "250000.000000",
        },
      ],
    });
    render(<ExposuresStep session={SESSION} portfolioId="pf-1" />);
    expect(await screen.findByText("Holdings carrying two measures")).toBeTruthy();
    expect(screen.getAllByText("250000.000000").length).toBeGreaterThan(0);
    expect(screen.getAllByText("246350.000000").length).toBeGreaterThan(0);
    expect(screen.getByText("-3650.000000")).toBeTruthy(); // MV minus notional, off par
    expect(screen.getByText("All measures")).toBeTruthy(); // the filter is on the screen
  });

  it("selecting a measure refetches through the API filter (wiring, not presence)", async () => {
    const seen: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        seen.push(url);
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }),
    );
    const { fireEvent } = await import("@testing-library/react");
    render(<ExposuresStep session={SESSION} portfolioId="pf-1" />);
    await screen.findByText("All measures");
    fireEvent.change(screen.getByDisplayValue("All measures"), {
      target: { value: "NOTIONAL" },
    });
    await screen.findByDisplayValue("NOTIONAL");
    expect(
      seen.some((u) => u.includes("/exposure/latest") && u.includes("exposure_type=NOTIONAL")),
    ).toBe(true);
  });
});
