import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { RunDetailBase } from "../api/types";
import { RunDetail } from "./RunDetail";

const SESSION = { userId: "u-1", tenantId: "t-1" };

// A value float64 CANNOT represent: Number(...) would print "9007199254740993.12345679"
// or similar. The screen must show it byte-for-byte (OQ-FE-1-7).
const EXACT = "9007199254740993.123456789012";

function detail(overrides: Partial<RunDetailBase>): RunDetailBase {
  return {
    run_id: "22222222-2222-2222-2222-222222222222",
    status: "COMPLETED",
    run_type: "VAR",
    input_snapshot_id: "33333333-3333-3333-3333-333333333333",
    model_version_id: "44444444-4444-4444-4444-444444444444",
    code_version: "v1",
    environment_id: "dev",
    initiated_by: "analyst",
    failure_reason: null,
    rows: [],
    ...overrides,
  };
}

function stubDetail(body: RunDetailBase): ReturnType<typeof vi.fn> {
  const mock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function renderDetail(family: string, runId: string): void {
  render(
    <MemoryRouter initialEntries={[`/runs/${family}/${runId}`]}>
      <Routes>
        <Route path="/runs/:family/:runId" element={<RunDetail session={SESSION} />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RunDetail", () => {
  it("fetches the family endpoint ONCE and renders provenance verbatim", async () => {
    const body = detail({});
    const mock = stubDetail(body);
    renderDetail("vars", body.run_id);
    expect(await screen.findByText(body.input_snapshot_id as string)).toBeTruthy();
    expect(screen.getByText(body.model_version_id as string)).toBeTruthy();
    expect(mock).toHaveBeenCalledTimes(1);
    expect(String(mock.mock.calls[0]?.[0])).toBe(`/risk/vars/runs/${body.run_id}`);
  });

  it("renders a VaR result row with decimal strings byte-for-byte", async () => {
    stubDetail(
      detail({
        rows: [
          {
            id: "row-1",
            metric_type: "VAR_PARAMETRIC",
            base_currency: "USD",
            confidence_level: "0.9500",
            horizon_days: 1,
            z_score: "1.644853626951",
            sigma: EXACT,
            var_value: "700.000000",
            n_factors: 2,
            n_observations: 4,
            window_start: "2026-05-26",
            window_end: "2026-05-29",
            exposure_run_id: "e",
            covariance_run_id: "c",
            model_version_id: "m",
          },
        ],
      }),
    );
    renderDetail("vars", "22222222-2222-2222-2222-222222222222");
    expect(await screen.findByText(EXACT)).toBeTruthy();
    expect(screen.getByText("1.644853626951")).toBeTruthy();
    expect(screen.getByText("700.000000")).toBeTruthy();
    expect(screen.getByText(/Results \(1\)/)).toBeTruthy();
  });

  it("renders a sensitivity row with NON-round-tripping decimal fences", async () => {
    // Both constants change under String(Number(...)): "-0.000098765430" → "-0.00009876543"
    // and "1.0000" → "1" (verified with node) — a real anti-Number() fence (review fold: the
    // previous constant survived a float64 round-trip, proving nothing).
    const mock = stubDetail(
      detail({
        run_type: "SENSITIVITY",
        rows: [
          {
            id: "row-1",
            curve_id: "c-1",
            curve_type: "TREASURY",
            currency_code: "USD",
            reference_key: "NONE",
            value_type: "ZERO_RATE",
            tenor_days: 365,
            tenor_label: "1Y",
            sensitivity_type: "DV01",
            sensitivity_value: "-0.000098765430",
            bump_bps: "1.0000",
            model_version_id: "m",
          },
        ],
      }),
    );
    renderDetail("sensitivities", "22222222-2222-2222-2222-222222222222");
    expect(await screen.findByText("-0.000098765430")).toBeTruthy();
    expect(screen.getByText("1.0000")).toBeTruthy();
    expect(screen.getByText("DV01")).toBeTruthy();
    expect(String(mock.mock.calls[0]?.[0])).toBe(
      "/risk/sensitivities/runs/22222222-2222-2222-2222-222222222222",
    );
  });

  it("renders a covariance row (columns wired to the real DTO keys)", async () => {
    const mock = stubDetail(
      detail({
        run_type: "COVARIANCE",
        rows: [
          {
            id: "row-1",
            factor_id_1: "f1",
            factor_id_2: "f2",
            factor_code_1: "USD",
            factor_code_2: "EUR",
            statistic_type: "COVARIANCE",
            return_type: "SIMPLE",
            frequency: "DAILY",
            n_observations: 4,
            window_start: "2026-05-26",
            window_end: "2026-05-29",
            covariance_value: "0.00012345000000000000", // → 0.00012345 under Number()
            model_version_id: "m",
          },
        ],
      }),
    );
    renderDetail("covariances", "22222222-2222-2222-2222-222222222222");
    expect(await screen.findByText("0.00012345000000000000")).toBeTruthy();
    expect(screen.getByText("EUR")).toBeTruthy();
    expect(screen.getByText("2026-05-29")).toBeTruthy();
    expect(String(mock.mock.calls[0]?.[0])).toBe(
      "/risk/covariances/runs/22222222-2222-2222-2222-222222222222",
    );
  });

  it("renders a factor-exposure row (columns wired to the real DTO keys)", async () => {
    const mock = stubDetail(
      detail({
        run_type: "FACTOR_EXPOSURE",
        rows: [
          {
            id: "row-1",
            portfolio_id: "pf-1",
            instrument_id: "in-1",
            factor_id: "f-1",
            factor_code: "CCY_USD",
            factor_family: "CURRENCY",
            base_currency: "USD",
            mark_currency: "EUR",
            loading: "1.000000000000", // → "1" under Number()
            exposure_amount: "400.000000", // → "400" under Number()
            model_version_id: "m",
          },
        ],
      }),
    );
    renderDetail("factor-exposures", "22222222-2222-2222-2222-222222222222");
    expect(await screen.findByText("1.000000000000")).toBeTruthy();
    expect(screen.getByText("400.000000")).toBeTruthy();
    expect(screen.getByText("CCY_USD")).toBeTruthy();
    expect(String(mock.mock.calls[0]?.[0])).toBe(
      "/risk/factor-exposures/runs/22222222-2222-2222-2222-222222222222",
    );
  });

  it("routes the exposure family to its OWN endpoint (/exposure/runs/{id}), not /risk", async () => {
    const mock = stubDetail(
      detail({
        run_type: "EXPOSURE_AGGREGATE",
        model_version_id: null, // exposure is model-less
        rows: [
          {
            id: "row-1",
            portfolio_id: "pf-1",
            instrument_id: "in-1",
            exposure_type: "MARKET_VALUE",
            base_currency: "USD",
            mark_currency: "EUR",
            signed_quantity: "100.00000000",
            mark_value: "7.000000",
            fx_rate: "1.100000000000",
            exposure_amount: "770.000000",
          },
        ],
      }),
    );
    renderDetail("exposure", "55555555-5555-5555-5555-555555555555");
    expect(await screen.findByText("770.000000")).toBeTruthy();
    expect(screen.getByText("MARKET_VALUE")).toBeTruthy();
    expect(String(mock.mock.calls[0]?.[0])).toBe(
      "/exposure/runs/55555555-5555-5555-5555-555555555555",
    );
  });

  it("URL-encodes the runId so a crafted deep link cannot escape the /risk path", async () => {
    const mock = stubDetail(detail({}));
    // The attack shape: percent-encoded traversal in the deep link — the router DECODES it
    // into the runId param ("../../admin?x=1"); the fetch must re-encode it.
    renderDetail("vars", "..%2F..%2Fadmin%3Fx%3D1");
    await waitFor(() => {
      expect(mock).toHaveBeenCalledTimes(1);
    });
    const url = String(mock.mock.calls[0]?.[0]);
    expect(url).toBe("/risk/vars/runs/..%2F..%2Fadmin%3Fx%3D1");
    expect(url).not.toContain("../");
  });

  it("renders the not-entitled state honestly on 403", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 403, json: () => Promise.resolve({}) }),
    );
    renderDetail("vars", "22222222-2222-2222-2222-222222222222");
    expect(await screen.findByText(/not entitled to view this run \(403\)/)).toBeTruthy();
  });

  it("renders a FAILED run's persisted reason prominently with zero rows", async () => {
    stubDetail(
      detail({
        status: "FAILED",
        failure_reason: "coverage gate — missing covariance for factor 'EUR'",
        rows: [],
      }),
    );
    renderDetail("vars", "22222222-2222-2222-2222-222222222222");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("coverage gate — missing covariance for factor 'EUR'");
    expect(screen.getByText(/failed closed/)).toBeTruthy();
  });

  it("rejects an unknown family without fetching", () => {
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    renderDetail("nonsense", "22222222-2222-2222-2222-222222222222");
    expect(screen.getByText(/Unknown run family/)).toBeTruthy();
    expect(mock).not.toHaveBeenCalled();
  });

  it("renders not-found honestly", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404, json: () => Promise.resolve({}) }),
    );
    renderDetail("vars", "22222222-2222-2222-2222-222222222222");
    expect(await screen.findByText(/Run not found/)).toBeTruthy();
  });
});
