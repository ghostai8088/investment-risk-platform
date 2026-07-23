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

  it("labels test_decision family-neutrally (BT-3: the column also renders LR_IND/LR_CC)", () => {
    const col = FAMILY_ROW_COLUMNS["var-backtests"].find((c) => c.key === "test_decision");
    expect(col?.label).toBe("Test decision");
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

describe("desmoothed-returns (PA-1) family wiring", () => {
  it("registers the perf family keyed to DESMOOTHED_RETURN, REUSING the perf permission family", () => {
    expect(FAMILIES["desmoothed-returns"]).toEqual({
      runType: "DESMOOTHED_RETURN",
      label: "Desmoothed returns",
      permissionFamily: "perf",
    });
    expect(RUN_TYPE_TO_FAMILY.DESMOOTHED_RETURN).toBe("desmoothed-returns");
  });

  it("uses the perf-family detail URL special case", () => {
    expect(runDetailUrl("desmoothed-returns", "abc-123")).toBe(
      "/perf/desmoothed-returns/runs/abc-123",
    );
  });

  it("surfaces the desmoothing columns", () => {
    const keys = FAMILY_ROW_COLUMNS["desmoothed-returns"].map((c) => c.key);
    expect(keys).toEqual([
      "metric_type",
      "period_start",
      "period_end",
      "metric_value",
      "observed_return",
      "observed_stdev",
      "alpha",
      "n_periods",
      "mark_currency",
    ]);
  });
});

describe("proxy-weight-estimates (FL-1) family wiring", () => {
  it("registers the risk family keyed to PROXY_WEIGHT_ESTIMATE, REUSING the risk permission family", () => {
    expect(FAMILIES["proxy-weight-estimates"]).toEqual({
      runType: "PROXY_WEIGHT_ESTIMATE",
      label: "Proxy-weight estimates",
      permissionFamily: "risk",
    });
    // NOT forced by the exhaustiveness net (the verifier-pass correction) — pinned explicitly.
    expect(RUN_TYPE_TO_FAMILY.PROXY_WEIGHT_ESTIMATE).toBe("proxy-weight-estimates");
  });

  it("uses the shared /risk/{family}/runs/{id} detail URL (the default fallthrough is correct — verified, no special case added)", () => {
    expect(runDetailUrl("proxy-weight-estimates", "abc-123")).toBe(
      "/risk/proxy-weight-estimates/runs/abc-123",
    );
  });

  it("surfaces the estimate columns (the heterogeneous WEIGHT/INTERCEPT/ESTIMATION_SUMMARY rows share them)", () => {
    const keys = FAMILY_ROW_COLUMNS["proxy-weight-estimates"].map((c) => c.key);
    expect(keys).toEqual([
      "metric_type",
      "instrument_id",
      "factor_id",
      "metric_value",
      "std_error",
      "n_observations",
      "residual_stdev",
      "series_currency",
    ]);
  });
});

describe("vars columns (FL-1 ride-along): the PA-4/BT-2/PPF-3 fields surface", () => {
  it("renders residual_variance, private_variance, estimate_age_days and model_version_id", () => {
    const keys = FAMILY_ROW_COLUMNS.vars.map((c) => c.key);
    expect(keys).toContain("residual_variance");
    expect(keys).toContain("private_variance"); // PPF-3: the unified pure-private block leg
    expect(keys).toContain("estimate_age_days");
    expect(keys).toContain("model_version_id");
  });
});

describe("every RUN_TYPE_TO_FAMILY entry round-trips (FL-1 — the reverse map is NOT forced by the net)", () => {
  it("maps each family's runType back to itself", () => {
    for (const [family, def] of Object.entries(FAMILIES)) {
      expect(RUN_TYPE_TO_FAMILY[def.runType]).toBe(family);
    }
  });
});
