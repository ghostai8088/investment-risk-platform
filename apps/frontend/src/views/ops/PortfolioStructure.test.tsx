import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PortfolioStructure } from "./PortfolioStructure";
import type { DevSession } from "../../session";

const SESSION: DevSession = { kind: "dev" as const, userId: "u", tenantId: "t" };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PortfolioStructure", () => {
  it("renders the as-of tree with indentation by depth and hits the tree-as-of read", async () => {
    const seen: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        seen.push(url);
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve([
              {
                portfolio_id: "f1",
                parent_portfolio_id: null,
                node_type: "FUND",
                name: "Demo structured multi-sleeve fund",
                base_currency_code: "EUR",
                status: "ACTIVE",
                record_version: 1,
                effective_at: "2026-05-27T00:00:00+00:00",
              },
              {
                portfolio_id: "s1",
                parent_portfolio_id: "f1",
                node_type: "STRATEGY",
                name: "Demo fixed-income sleeve",
                base_currency_code: null,
                status: "ACTIVE",
                record_version: 1,
                effective_at: "2026-05-27T00:00:00+00:00",
              },
            ]),
        });
      }),
    );
    render(<PortfolioStructure session={SESSION} />);
    expect(await screen.findByText("Demo structured multi-sleeve fund")).toBeTruthy();
    expect(screen.getByText("Demo fixed-income sleeve")).toBeTruthy();
    // Wave-18 close (K27): the DP-11 declaration column — declared shows the code, undeclared
    // renders the dash (INHERIT), so a reader can see which node a refusal would anchor on.
    expect(screen.getByText("Reporting ccy")).toBeTruthy();
    expect(screen.getByText("EUR")).toBeTruthy();
    expect(screen.getByText("STRATEGY")).toBeTruthy();
    expect(seen.some((u) => u.includes("/portfolios/tree-as-of?at="))).toBe(true);
  });
});
