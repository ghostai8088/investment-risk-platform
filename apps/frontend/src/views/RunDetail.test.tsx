import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";

import type { RunDetailBase } from "../api/types";
import { RunDetail } from "./RunDetail";

const SESSION = { kind: "dev" as const, userId: "u-1", tenantId: "t-1" };

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
            fx_pivot: null,
            fx_legs: [],
            exposure_amount: "770.000000",
          },
        ],
      } as unknown as Partial<RunDetailBase>),
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

  it("annotates the ES row's z_score as an echo (FL-1 — z×σ is NOT the ES arithmetic)", async () => {
    stubDetail(
      detail({
        rows: [
          {
            id: "row-es",
            metric_type: "ES_PARAMETRIC",
            base_currency: "USD",
            confidence_level: "0.9900",
            horizon_days: 1,
            z_score: "2.326347874041",
            sigma: "1000.000000",
            var_value: "2665.214030",
            n_factors: 2,
            n_observations: 4,
            model_version_id: "m",
          },
        ],
      }),
    );
    renderDetail("vars", "22222222-2222-2222-2222-222222222222");
    // The ES row's z cell renders annotated — the three adjacent columns can no longer invite
    // the wrong z×σ arithmetic (the multiplier k_c lives on the model version, not the row).
    expect(
      await screen.findByText("2.326347874041 (echo — not the ES multiplier; see model version)"),
    ).toBeTruthy();
    expect(screen.getByText("2665.214030")).toBeTruthy();
  });

  it("keeps a plain VAR row's z_score UNANNOTATED (the fix is metric_type-aware, not a header)", async () => {
    stubDetail(
      detail({
        rows: [
          {
            id: "row-var",
            metric_type: "VAR_PARAMETRIC",
            base_currency: "USD",
            confidence_level: "0.9900",
            horizon_days: 1,
            z_score: "2.326347874041",
            sigma: "1000.000000",
            var_value: "2326.347874",
            n_factors: 2,
            n_observations: 4,
            model_version_id: "m",
          },
        ],
      }),
    );
    renderDetail("vars", "22222222-2222-2222-2222-222222222222");
    expect(await screen.findByText("2.326347874041")).toBeTruthy();
    expect(screen.queryByText(/echo — not the ES multiplier/)).toBeNull();
  });

  it("renders a proxy-weight-estimate row (FL-1 — the family the listing showed but the FE could not render)", async () => {
    const mock = stubDetail(
      detail({
        run_type: "PROXY_WEIGHT_ESTIMATE",
        rows: [
          {
            id: "row-w",
            metric_type: "WEIGHT",
            factor_id: "f-1",
            metric_value: "0.612345678901",
            std_error: "0.045678901234",
            n_observations: null,
            n_regressors: null,
            residual_stdev: null,
            min_observations: 4,
            series_currency: "USD",
            source_desmoothed_run_id: "d-1",
            portfolio_id: "p-1",
            instrument_id: "i-1",
          },
        ],
      }),
    );
    renderDetail("proxy-weight-estimates", "22222222-2222-2222-2222-222222222222");
    expect(await screen.findByText("0.612345678901")).toBeTruthy();
    expect(screen.getByText("0.045678901234")).toBeTruthy();
    expect(screen.getByText("WEIGHT")).toBeTruthy();
    expect(String(mock.mock.calls[0]?.[0])).toBe(
      "/risk/proxy-weight-estimates/runs/22222222-2222-2222-2222-222222222222",
    );
  });

  it("renders registered model limitations on the run page (OQ-LQ-1-8 — the ratified surface)", async () => {
    // The Wave-14 close's re-adjudicated MED: the liquidity API returned these and the run-detail
    // screen — the surface the gate ratified — rendered nothing. The governance walk rendering
    // them ELSEWHERE does not satisfy "next to the number". The first limitation is the one that
    // matters: this number must not be read as the Rule 22e-4 15% test.
    stubDetail({
      run_id: "33333333-3333-3333-3333-333333333333",
      status: "COMPLETED",
      failure_reason: null,
      input_snapshot_id: "s-1",
      model_version_id: "m-1",
      code_version: "v",
      environment_id: "e",
      initiated_by: "t",
      created_at: null,
      completed_at: null,
      limitations: [
        "This is NOT the SEC Rule 22e-4 15% test. The denominator is the invested-long book.",
        "Tier assignment is INSTRUMENT-grain.",
      ],
      rows: [],
    } as unknown as RunDetailBase);
    renderDetail("liquidity", "33333333-3333-3333-3333-333333333333");
    expect(await screen.findByText(/NOT the SEC Rule 22e-4 15% test/)).toBeTruthy();
    expect(screen.getByText("Registered model limitations")).toBeTruthy();
    expect(screen.getByText(/INSTRUMENT-grain/)).toBeTruthy();
  });

  // ------- STRUCT-4 (REQ-PPM-010): the conversion-path drill-in -------

  const EXPOSURE_ROW = {
    id: "row-1",
    calculation_run_id: "55555555-5555-5555-5555-555555555555",
    portfolio_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    instrument_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    base_currency: "EUR",
    mark_currency: "GBP",
    signed_quantity: "100",
    mark_value: "40.00",
    fx_rate: "1.157407407407",
    fx_pivot: "USD",
    fx_legs: [
      {
        fx_rate_id: "fx-leg-1",
        base_currency: "GBP",
        quote_currency: "USD",
        rate: "1.25",
        direction: "direct",
        pivot: "USD",
      },
      {
        fx_rate_id: "fx-leg-2",
        base_currency: "EUR",
        quote_currency: "USD",
        rate: "1.08",
        direction: "reciprocal",
        pivot: "USD",
      },
    ],
    exposure_amount: "4629.629630",
    exposure_type: "MARKET_VALUE",
  };

  function stubExposureDetail(rows: unknown[], rollup: unknown[]): ReturnType<typeof vi.fn> {
    // Two fetches now leave this screen (run detail + node rollup) — route by URL.
    const mock = vi.fn().mockImplementation((url: string) => {
      const body = String(url).includes("/rollup") ? rollup : detail({ rows } as never);
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    });
    vi.stubGlobal("fetch", mock);
    return mock;
  }

  it("STRUCT-4: renders the conversion path — legs with travel direction, provenance ids, the stated pivot — and the translated node total", async () => {
    const mock = stubExposureDetail(
      [EXPOSURE_ROW],
      [
        {
          node_id: EXPOSURE_ROW.portfolio_id,
          exposure_type: "MARKET_VALUE",
          total: "5629.629630",
          n_rows: 2,
          base_currency: "EUR",
          reporting_currency: "USD",
          translated_total: "6080.000000",
          translated_currency: "USD",
          translation_fx_rate: "1.080000000000",
          translation_legs: [
            {
              fx_rate_id: "fx-leg-2",
              base_currency: "EUR",
              quote_currency: "USD",
              rate: "1.08",
              direction: "direct",
            },
          ],
          translation_pivot: null,
          missing_fx: null,
        },
      ],
    );
    renderDetail("exposure", "22222222-2222-2222-2222-222222222222");
    expect(await screen.findByText("Conversion paths")).toBeTruthy();
    // The DIRECT leg travels base→quote; the RECIPROCAL leg travels quote→base (stored pair is
    // the published orientation) — rendering it raw would show the path backwards.
    expect(screen.getByText(/GBP → USD \(direct @ 1\.25; fx_rate fx-leg-1\)/)).toBeTruthy();
    expect(
      screen.getByText(/USD → EUR \(reciprocal of EUR\/USD @ 1\.08; fx_rate fx-leg-2\)/),
    ).toBeTruthy();
    // Review fold C13: the pivot cell renders DISTINCTLY ("via USD") — a bare currency-code
    // match was satisfiable by the reporting-currency cell, proving nothing about the pivot.
    expect(screen.getByText("via USD")).toBeTruthy();
    // The translated node total, byte-for-byte with its currency.
    expect(await screen.findByText("6080.000000 USD")).toBeTruthy();
    const urls = mock.mock.calls.map((c) => String(c[0]));
    // Review fold C15: the EXACT rollup URL — run id AND node id pinned, not a substring.
    expect(urls).toContain(
      `/exposure/runs/22222222-2222-2222-2222-222222222222/rollup?node_id=${EXPOSURE_ROW.portfolio_id}`,
    );
  });

  it("STRUCT-4 negative: a NON-exposure family renders no conversion section", async () => {
    stubDetail(detail({ rows: [{ id: "r", metric_type: "VAR_PARAMETRIC", value: "1.0" }] }));
    renderDetail("vars", "22222222-2222-2222-2222-222222222222");
    await screen.findByText("Provenance");
    expect(screen.queryByText("Conversion paths")).toBeNull();
    expect(screen.queryByText(/Node totals/)).toBeNull();
  });

  it("STRUCT-4 honesty: an all-identity run says so, and a missing pinned path renders the gap — never a fabricated rate", async () => {
    stubExposureDetail(
      [{ ...EXPOSURE_ROW, mark_currency: "EUR", fx_rate: "1", fx_pivot: null, fx_legs: [] }],
      [
        {
          node_id: EXPOSURE_ROW.portfolio_id,
          exposure_type: "MARKET_VALUE",
          total: "90.000000",
          n_rows: 1,
          base_currency: "USD",
          reporting_currency: "GBP",
          translated_total: null,
          translated_currency: null,
          translation_fx_rate: null,
          translation_legs: [],
          translation_pivot: null,
          missing_fx: "missing-fx:USD->GBP",
        },
      ],
    );
    renderDetail("exposure", "22222222-2222-2222-2222-222222222222");
    expect(await screen.findByText(/no published-rate legs were used/)).toBeTruthy();
    expect(
      await screen.findByText(/unavailable — missing-fx:USD->GBP \(no pinned path/),
    ).toBeTruthy();
  });

  it("STRUCT-4 (C8): a typed node id re-fetches the rollup for a node the rows never mention", async () => {
    const mock = stubExposureDetail([EXPOSURE_ROW], []);
    renderDetail("exposure", "22222222-2222-2222-2222-222222222222");
    await screen.findByText("Conversion paths");
    const input = screen.getByPlaceholderText("node id");
    const grouping = "cccccccc-cccc-cccc-cccc-cccccccccccc"; // a grouping node with no rows
    fireEvent.change(input, { target: { value: grouping } });
    await waitFor(() => {
      const urls = mock.mock.calls.map((c) => String(c[0]));
      expect(urls).toContain(
        `/exposure/runs/22222222-2222-2222-2222-222222222222/rollup?node_id=${grouping}`,
      );
    });
  });
});
