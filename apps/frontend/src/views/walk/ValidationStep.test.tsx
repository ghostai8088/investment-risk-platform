import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ValidationStep } from "./ValidationStep";
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

describe("ValidationStep", () => {
  it("shows the validation records with findings AND evidence (the F2 read made visible)", async () => {
    mockRoutes({
      "/models/m1/validations/val1": {
        body: {
          id: "val1",
          outcome: "APPROVED_WITH_CONDITIONS",
          validation_type: "EXCEPTION",
          scope_summary: "Initial review of the TWR model.",
          conditions: "Capture the cash ledger.",
          findings: [
            { id: "f1", severity: "LOW", finding_text: "Uncaptured cash income understates return.", authored_by: "Andrew Cox" },
          ],
          evidence: [
            { id: "e1", evidence_type: "DOCUMENT", run_id: null, reference: "mg_1_decision_record.md" },
          ],
        },
      },
      "/models/m1/versions/mv1/validations": { body: [{ id: "val1" }] },
      "/models/m1": {
        body: {
          id: "m1",
          code: "perf.return.twr",
          tier: "TIER_1",
          versions: [{ id: "mv1", version_label: "v1", latest_validation: { outcome: "APPROVED_WITH_CONDITIONS" } }],
        },
      },
      "/models": { body: [{ id: "m1" }] },
    });
    render(<ValidationStep session={SESSION} />);
    expect(await screen.findByText("perf.return.twr")).toBeTruthy();
    expect(screen.getByText(/Uncaptured cash income/)).toBeTruthy();
    expect(screen.getByText(/mg_1_decision_record/)).toBeTruthy();
    expect(screen.getByText("APPROVED WITH CONDITIONS")).toBeTruthy();
  });

  it("degrades to a calm note when the model inventory is forbidden", async () => {
    mockRoutes({ "/models": { status: 403, body: {} } });
    render(<ValidationStep session={SESSION} />);
    expect(await screen.findByText(/model\.inventory\.view/)).toBeTruthy();
  });
});
