import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LimitationsStep } from "./LimitationsStep";
import type { DevSession } from "../../session";

const SESSION: DevSession = { userId: "u", tenantId: "t" };

function mockRoutes(routes: Record<string, { status?: number; body: unknown }>): void {
  const keys = Object.keys(routes).sort((a, b) => b.length - a.length);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const key = keys.find((k) => url.startsWith(k));
      const r = key ? routes[key] : undefined;
      const status = r?.status ?? (r ? 200 : 404);
      return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(r ? r.body : {}) });
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LimitationsStep", () => {
  it("groups disclosed limitations by model", async () => {
    mockRoutes({
      "/models/m1": {
        body: {
          id: "m1",
          code: "risk.var.parametric",
          tier: "TIER_1",
          versions: [
            {
              id: "mv1",
              limitations: ["CURRENCY-ONLY factor set: cannot see the equity drawdown on 2026-05-22."],
              latest_validation: null,
            },
          ],
        },
      },
      "/models": { body: [{ id: "m1" }] },
    });
    render(<LimitationsStep session={SESSION} />);
    expect(await screen.findByText("risk.var.parametric")).toBeTruthy();
    // Assert the unique limitation text (the lede also mentions the drawdown).
    expect(screen.getByText(/CURRENCY-ONLY factor set/)).toBeTruthy();
  });

  it("degrades to a calm note without model.inventory.view", async () => {
    mockRoutes({ "/models": { status: 403, body: {} } });
    render(<LimitationsStep session={SESSION} />);
    expect(await screen.findByText(/model\.inventory\.view/)).toBeTruthy();
  });
});
