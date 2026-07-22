import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { RiskRunSummary } from "../api/types";
import { RunsList } from "./RunsList";

const SESSION = { kind: "dev" as const, userId: "u-1", tenantId: "t-1" };
const PAGE_SIZE = 50;

function run(overrides: Partial<RiskRunSummary>): RiskRunSummary {
  return {
    run_id: "11111111-1111-1111-1111-111111111111",
    run_type: "VAR",
    status: "COMPLETED",
    created_at: "2026-07-07T12:00:00Z",
    completed_at: "2026-07-07T12:00:01Z",
    initiated_by: "analyst",
    input_snapshot_id: null,
    model_version_id: null,
    code_version: "v1",
    environment_id: "dev",
    failure_reason: null,
    ...overrides,
  };
}

function stubItems(items: RiskRunSummary[]): ReturnType<typeof vi.fn> {
  const mock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ items }),
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function renderList(): void {
  render(
    <MemoryRouter>
      <RunsList session={SESSION} />
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RunsList", () => {
  it("fetches /risk/runs and renders rows in the SERVER's order with family detail links", async () => {
    // Server order: VAR first, COVARIANCE second — the DOM must preserve it (review fold:
    // per-link assertions could not catch a client-side re-sort).
    const mock = stubItems([
      run({ run_id: "aaaaaaaa-0000-0000-0000-000000000001", run_type: "VAR" }),
      run({ run_id: "aaaaaaaa-0000-0000-0000-000000000002", run_type: "COVARIANCE" }),
    ]);
    renderList();
    await screen.findByText("aaaaaaaa-0000-0000-0000-000000000001");

    // The full endpoint path is pinned (review fold: query-substring checks alone let a
    // wrong path ship).
    expect(String(mock.mock.calls[0]?.[0]).startsWith("/risk/runs?")).toBe(true);

    const cells = Array.from(document.querySelectorAll("tbody tr td.mono")).map(
      (td) => td.textContent,
    );
    expect(cells).toEqual([
      "aaaaaaaa-0000-0000-0000-000000000001",
      "aaaaaaaa-0000-0000-0000-000000000002",
    ]);
    const link = screen.getByText("aaaaaaaa-0000-0000-0000-000000000001");
    expect(link.closest("a")?.getAttribute("href")).toBe(
      "/runs/vars/aaaaaaaa-0000-0000-0000-000000000001",
    );
    const link2 = screen.getByText("aaaaaaaa-0000-0000-0000-000000000002");
    expect(link2.closest("a")?.getAttribute("href")).toBe(
      "/runs/covariances/aaaaaaaa-0000-0000-0000-000000000002",
    );
  });

  it("navigates to the run detail when the ROW is clicked (not just the id link)", async () => {
    stubItems([run({ run_id: "eeeeeeee-0000-0000-0000-000000000001", run_type: "VAR" })]);
    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<RunsList session={SESSION} />} />
          <Route path="/runs/:family/:runId" element={<p>DETAIL PROBE vars</p>} />
        </Routes>
      </MemoryRouter>,
    );
    // Click a NON-link cell (the run type) — the whole row must navigate.
    fireEvent.click(await screen.findByText("VAR"));
    expect(await screen.findByText("DETAIL PROBE vars")).toBeTruthy();
  });

  it("shows a truncated failure_reason on a FAILED row", async () => {
    const reason = `snapshot gate — ${"x".repeat(200)}`;
    stubItems([run({ status: "FAILED", failure_reason: reason })]);
    renderList();
    const cell = await screen.findByText(/^snapshot gate — x+…$/);
    expect(cell.textContent?.length).toBeLessThan(reason.length);
    const badge = document.querySelector(".status-failed");
    expect(badge?.textContent).toBe("FAILED");
  });

  it("passes the filters into the query string with the has-more probe limit", async () => {
    const mock = stubItems([]);
    renderList();
    await screen.findByText(/No runs yet/);

    fireEvent.change(screen.getByLabelText(/Run type/), { target: { value: "VAR" } });
    await waitFor(() => {
      const calls = mock.mock.calls.map((c) => String(c[0]));
      expect(calls.some((u) => u.includes("run_type=VAR"))).toBe(true);
    });

    fireEvent.change(screen.getByLabelText(/Status/), { target: { value: "FAILED" } });
    await waitFor(() => {
      const calls = mock.mock.calls.map((c) => String(c[0]));
      expect(calls.some((u) => u.includes("run_type=VAR") && u.includes("status=FAILED"))).toBe(
        true,
      );
    });
    const last = String(mock.mock.calls[mock.mock.calls.length - 1]?.[0]);
    expect(last).toContain(`limit=${String(PAGE_SIZE + 1)}`); // PAGE_SIZE + the has-more probe
    expect(last).toContain("offset=0");
  });

  it("routes the Exposure family to /exposure/runs (source-switch, not run_type=)", async () => {
    const mock = stubItems([]);
    renderList();
    await screen.findByText(/No runs yet/);
    // A risk family stays on /risk/runs with a run_type filter.
    fireEvent.change(screen.getByLabelText(/Run type/), { target: { value: "VAR" } });
    await waitFor(() => {
      const calls = mock.mock.calls.map((c) => String(c[0]));
      expect(calls.some((u) => u.startsWith("/risk/runs?") && u.includes("run_type=VAR"))).toBe(
        true,
      );
    });
    // Selecting Exposure switches the SOURCE endpoint and drops run_type (singleton family).
    fireEvent.change(screen.getByLabelText(/Run type/), {
      target: { value: "EXPOSURE_AGGREGATE" },
    });
    await waitFor(() => {
      const last = String(mock.mock.calls[mock.mock.calls.length - 1]?.[0]);
      expect(last.startsWith("/exposure/runs?")).toBe(true);
      expect(last).not.toContain("run_type=");
    });
  });

  it("pages with Older/Newer: 51 rows means has-more, click requests offset=50", async () => {
    const fullPage = Array.from({ length: PAGE_SIZE + 1 }, (_, i) =>
      run({ run_id: `bbbbbbbb-0000-0000-0000-${String(i).padStart(12, "0")}` }),
    );
    const mock = stubItems(fullPage);
    renderList();
    await screen.findByText("bbbbbbbb-0000-0000-0000-000000000000");

    // Only PAGE_SIZE rows render; the probe row is a signal, not content.
    expect(document.querySelectorAll("tbody tr").length).toBe(PAGE_SIZE);
    const newer = screen.getByText("Newer") as HTMLButtonElement;
    const older = screen.getByText("Older") as HTMLButtonElement;
    expect(newer.disabled).toBe(true); // at offset 0
    expect(older.disabled).toBe(false); // 51st row ⇒ more exist

    fireEvent.click(older);
    await waitFor(() => {
      const calls = mock.mock.calls.map((c) => String(c[0]));
      expect(calls.some((u) => u.includes("offset=50"))).toBe(true);
    });
  });

  it("disables Older on an exactly-full last page (50 rows, no probe row)", async () => {
    const exactPage = Array.from({ length: PAGE_SIZE }, (_, i) =>
      run({ run_id: `cccccccc-0000-0000-0000-${String(i).padStart(12, "0")}` }),
    );
    stubItems(exactPage);
    renderList();
    await screen.findByText("cccccccc-0000-0000-0000-000000000000");
    expect((screen.getByText("Older") as HTMLButtonElement).disabled).toBe(true);
  });

  it("ignores a stale slow response after the filter changed (staleness guard)", async () => {
    // Request 1 (unfiltered) resolves LATE with a COVARIANCE row; request 2 (VAR filter)
    // resolves FIRST with a VAR row. The VAR row must win (review fold: without the guard
    // the stale unfiltered rows replaced the filtered ones).
    let resolveFirst: (v: unknown) => void = () => {};
    const first = new Promise((r) => {
      resolveFirst = r;
    });
    const mock = vi
      .fn()
      .mockImplementationOnce(() => first)
      .mockImplementationOnce(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              items: [run({ run_id: "dddddddd-0000-0000-0000-000000000002" })],
            }),
        }),
      );
    vi.stubGlobal("fetch", mock);
    renderList();
    fireEvent.change(screen.getByLabelText(/Run type/), { target: { value: "VAR" } });
    await screen.findByText("dddddddd-0000-0000-0000-000000000002");

    resolveFirst({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          items: [
            run({
              run_id: "dddddddd-0000-0000-0000-000000000001",
              run_type: "COVARIANCE",
            }),
          ],
        }),
    });
    // Give the stale promise chain a chance to (incorrectly) render.
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText("dddddddd-0000-0000-0000-000000000001")).toBeNull();
    expect(screen.getByText("dddddddd-0000-0000-0000-000000000002")).toBeTruthy();
  });

  it("offers the FL-1 proxy-weight-estimates family as a risk-source filter", async () => {
    const mock = stubItems([]);
    renderList();
    await screen.findByText(/No runs yet/);
    // The dropdown is derived from FAMILIES, so the new family is selectable and stays on the
    // shared /risk/runs source with its run_type filter (a risk-permission family).
    fireEvent.change(screen.getByLabelText(/Run type/), {
      target: { value: "PROXY_WEIGHT_ESTIMATE" },
    });
    await waitFor(() => {
      const last = String(mock.mock.calls[mock.mock.calls.length - 1]?.[0]);
      expect(last.startsWith("/risk/runs?")).toBe(true);
      expect(last).toContain("run_type=PROXY_WEIGHT_ESTIMATE");
    });
  });

  it("renders the empty and error states", async () => {
    stubItems([]);
    renderList();
    expect(await screen.findByText(/No runs yet/)).toBeTruthy();
    cleanup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500, json: () => Promise.resolve({}) }),
    );
    renderList();
    expect(await screen.findByText(/Could not load runs/)).toBeTruthy();
  });
});
