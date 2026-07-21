import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CaptureStep } from "./CaptureStep";
import type { DevSession } from "../../session";

const SESSION: DevSession = { userId: "u", tenantId: "t" };

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

describe("CaptureStep", () => {
  it("renders positions and valuation marks with decimals VERBATIM", async () => {
    mockRoutes({
      "/positions": [
        {
          id: "p1",
          instrument_id: "aaaaaaaa-1111-2222-3333-444444444444",
          quantity: "400.00000000",
          valid_from: "2024-06-01T00:00:00Z",
        },
      ],
      "/valuations": [
        {
          id: "v1",
          instrument_id: "bbbbbbbb-1111-2222-3333-444444444444",
          valuation_date: "2024-09-30",
          mark_value: "1000.000000",
          currency_code: "USD",
        },
      ],
    });
    render(<CaptureStep session={SESSION} portfolioId="pf-1" />);
    // Trailing zeros preserved — a Number() would have printed 400 / 1000.
    expect(await screen.findByText("400.00000000")).toBeTruthy();
    expect(await screen.findByText("1000.000000")).toBeTruthy();
    expect(screen.getByText("USD")).toBeTruthy();
  });

  it("degrades the positions pane on a 403 to a requires-permission note", async () => {
    mockRoutes({ "/positions": {}, "/valuations": [] }, 403);
    render(<CaptureStep session={SESSION} portfolioId="pf-1" />);
    expect(await screen.findAllByText(/You need the/)).toBeTruthy();
    expect(screen.getAllByText(/position\.view/).length).toBeGreaterThan(0);
  });
});
