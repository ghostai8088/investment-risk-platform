import { describe, expect, it } from "vitest";

import { FAMILIES, FAMILY_ROW_COLUMNS, RUN_TYPE_TO_FAMILY, runDetailUrl } from "./types";

describe("active-risk (P3-7) family wiring", () => {
  it("registers the active-risk family keyed to the ACTIVE_RISK run_type (family, not metric)", () => {
    expect(FAMILIES["active-risk"]).toEqual({
      runType: "ACTIVE_RISK",
      label: "Active risk",
      permissionFamily: "risk",
    });
    expect(RUN_TYPE_TO_FAMILY.ACTIVE_RISK).toBe("active-risk");
  });

  it("builds the shared /risk/{family}/runs/{id} detail URL (matches the backend route)", () => {
    expect(runDetailUrl("active-risk", "abc-123")).toBe("/risk/active-risk/runs/abc-123");
  });

  it("surfaces the tracking-error result columns", () => {
    const keys = FAMILY_ROW_COLUMNS["active-risk"].map((c) => c.key);
    expect(keys).toEqual([
      "metric_type",
      "base_currency",
      "te_value",
      "portfolio_value",
      "n_factors",
      "n_constituents",
      "benchmark_id",
      "benchmark_effective_date",
    ]);
  });

  it("keeps every FAMILIES key represented in FAMILY_ROW_COLUMNS (exhaustive)", () => {
    for (const family of Object.keys(FAMILIES)) {
      expect(FAMILY_ROW_COLUMNS[family as keyof typeof FAMILIES]).toBeDefined();
    }
  });
});
