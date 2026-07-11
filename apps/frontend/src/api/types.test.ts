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

describe("portfolio-returns (PM-1) family wiring", () => {
  it("registers the perf family keyed to PORTFOLIO_RETURN (family, not metric) under perf.view", () => {
    expect(FAMILIES["portfolio-returns"]).toEqual({
      runType: "PORTFOLIO_RETURN",
      label: "Portfolio returns",
      permissionFamily: "perf",
    });
    expect(RUN_TYPE_TO_FAMILY.PORTFOLIO_RETURN).toBe("portfolio-returns");
  });

  it("builds the perf-specific /perf/portfolio-returns/runs/{id} detail URL (own route shape)", () => {
    expect(runDetailUrl("portfolio-returns", "abc-123")).toBe(
      "/perf/portfolio-returns/runs/abc-123",
    );
  });

  it("surfaces the return series columns", () => {
    const keys = FAMILY_ROW_COLUMNS["portfolio-returns"].map((c) => c.key);
    expect(keys).toEqual([
      "metric_type",
      "period_start",
      "period_end",
      "begin_mv",
      "end_mv",
      "net_external_flow",
      "return_value",
      "n_flows",
      "n_periods",
      "base_currency",
    ]);
  });
});

describe("benchmark-relative (P3-8) family wiring", () => {
  it("registers the perf family keyed to BENCHMARK_RELATIVE, REUSING the perf permission family", () => {
    expect(FAMILIES["benchmark-relative"]).toEqual({
      runType: "BENCHMARK_RELATIVE",
      label: "Benchmark-relative",
      permissionFamily: "perf",
    });
    expect(RUN_TYPE_TO_FAMILY.BENCHMARK_RELATIVE).toBe("benchmark-relative");
  });

  it("builds the perf-specific /perf/benchmark-relative/runs/{id} detail URL (own route shape)", () => {
    expect(runDetailUrl("benchmark-relative", "abc-123")).toBe(
      "/perf/benchmark-relative/runs/abc-123",
    );
  });

  it("surfaces the ex-post benchmark-relative columns", () => {
    const keys = FAMILY_ROW_COLUMNS["benchmark-relative"].map((c) => c.key);
    expect(keys).toEqual([
      "metric_type",
      "period_start",
      "period_end",
      "metric_value",
      "portfolio_return_value",
      "benchmark_return_value",
      "return_basis",
      "n_benchmark_obs",
      "n_periods",
      "base_currency",
    ]);
  });
});

describe("var-backtests (BT-1) family wiring", () => {
  it("registers the risk family keyed to VAR_BACKTEST, REUSING the risk permission family", () => {
    expect(FAMILIES["var-backtests"]).toEqual({
      runType: "VAR_BACKTEST",
      label: "VaR backtests",
      permissionFamily: "risk",
    });
    expect(RUN_TYPE_TO_FAMILY.VAR_BACKTEST).toBe("var-backtests");
  });

  it("uses the shared /risk/{family}/runs/{id} detail URL (no special case)", () => {
    expect(runDetailUrl("var-backtests", "abc-123")).toBe("/risk/var-backtests/runs/abc-123");
  });

  it("surfaces the backtest columns", () => {
    const keys = FAMILY_ROW_COLUMNS["var-backtests"].map((c) => c.key);
    expect(keys).toEqual([
      "metric_type",
      "var_metric_type",
      "period_start",
      "period_end",
      "metric_value",
      "realized_pnl",
      "var_value",
      "test_decision",
      "basel_zone",
      "n_pairs",
      "n_exceptions",
      "base_currency",
    ]);
  });
});
