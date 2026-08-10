/**
 * RPT-3: the generate flow (ratified OQ-RPT3-5 — the proof list, bound BY NAME at the gate).
 *
 * This file is the checklist the review will diff against the record's §3, because REPRO-2 part 2
 * shipped with two §3-bound UI proofs quietly undelivered and the review caught it one part later.
 * Each test below names the proof number it discharges.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GenerateReport } from "./GenerateReport";
import type { Session } from "../../session";

const SESSION: Session = { kind: "dev", userId: "u-1", tenantId: "t-1" };

const PORTFOLIOS = [{ id: "pf-1", code: "GLOBAL-EQ", name: "Global Equity" }];
const SNAPSHOTS = [
  { id: "snap-match", as_of_valuation_date: "2026-03-31" },
  { id: "snap-off", as_of_valuation_date: "2026-06-30" },
];
const VAR_RUNS = {
  items: [
    { run_id: "aaaaaaaa-0000-4000-8000-000000000001", input_snapshot_id: "snap-match" },
    { run_id: "bbbbbbbb-0000-4000-8000-000000000002", input_snapshot_id: "snap-off" },
  ],
};
const ROLL_RUNS = {
  items: [{ run_id: "cccccccc-0000-4000-8000-000000000003", input_snapshot_id: "snap-match" }],
};

type Route = { reports?: unknown; write?: { status: number; detail?: string } };

/** Route every GET by path; answer the POST from `write`. Records the calls for assertions. */
function harness(route: Route = {}) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fn = vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (init?.method && init.method !== "GET") {
      const w = route.write ?? { status: 201 };
      return Promise.resolve({
        ok: w.status < 400,
        status: w.status,
        json: () => Promise.resolve(w.detail ? { detail: w.detail } : { id: "rep-new" }),
      } as unknown as Response);
    }
    const body = url.includes("/portfolios")
      ? PORTFOLIOS
      : url.includes("/snapshots")
        ? SNAPSHOTS
        : url.includes("/reports")
          ? (route.reports ?? { items: [] })
          : url.includes("/risk/runs")
            ? VAR_RUNS
            : url.includes("/perf/runs")
              ? ROLL_RUNS
              : { items: [] };
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    } as unknown as Response);
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}

const posts = (calls: { url: string; init?: RequestInit }[]) =>
  calls.filter((c) => c.init?.method === "POST");

/** Fill the form to a submittable state: book, date, one family + its run. */
async function fillForm(family = "Value at Risk", runIndex = 1): Promise<void> {
  fireEvent.change(await screen.findByLabelText("Portfolio"), { target: { value: "pf-1" } });
  fireEvent.change(screen.getByLabelText("As of"), { target: { value: "2026-03-31" } });
  fireEvent.click(screen.getByLabelText(family));
  const dropdown = await screen.findByLabelText(`${family} run`);
  const option = (dropdown as HTMLSelectElement).options[runIndex];
  fireEvent.change(dropdown, { target: { value: option.value } });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("GenerateReport — the ratified proof list", () => {
  it("PROOF 1: a family's dropdown lists only ITS run type, from its own endpoint", async () => {
    const calls = harness();
    render(<GenerateReport session={SESSION} onGenerated={() => {}} />);
    fireEvent.click(await screen.findByLabelText("Value at Risk"));

    await waitFor(() => expect(screen.getByLabelText("Value at Risk run")).toBeTruthy());
    // The positive: the VaR dropdown is fed from the VaR-typed listing.
    const varCall = calls.find((c) => c.url.includes("/risk/runs"));
    expect(varCall?.url).toContain("run_type=VAR");
    expect(varCall?.url).toContain("status=COMPLETED");
    // The negative twin: an UNCHECKED family issues no read at all, so a run of another type
    // cannot reach this dropdown — the multi-type-listing hazard the record names.
    expect(calls.some((c) => c.url.includes("/perf/runs"))).toBe(false);
  });

  it("PROOF 1 (rolling_risk): the family unreachable before this slice is now listable", async () => {
    const calls = harness();
    render(<GenerateReport session={SESSION} onGenerated={() => {}} />);
    fireEvent.click(await screen.findByLabelText("Rolling risk"));
    await waitFor(() => expect(screen.getByLabelText("Rolling risk run")).toBeTruthy());
    const call = calls.find((c) => c.url.includes("/perf/runs"));
    expect(call?.url).toContain("run_type=ROLLING_RISK");
  });

  it("PROOF 2: a run dated off the report date is BADGED — and a matching one is not", async () => {
    harness();
    render(<GenerateReport session={SESSION} onGenerated={() => {}} />);
    fireEvent.change(await screen.findByLabelText("As of"), { target: { value: "2026-03-31" } });
    fireEvent.click(screen.getByLabelText("Value at Risk"));

    const dropdown = (await screen.findByLabelText("Value at Risk run")) as HTMLSelectElement;
    const labels = Array.from(dropdown.options).map((o) => o.textContent ?? "");
    // The off-date run carries the badge...
    expect(labels.some((l) => l.includes("dated 2026-06-30, not 2026-03-31"))).toBe(true);
    // ...and the matching one does not (the twin — otherwise the badge is wallpaper).
    expect(labels.filter((l) => l.includes("not 2026-03-31"))).toHaveLength(1);
  });

  it("PROOF 3: submit POSTs only the CHECKED families; unchecked are ABSENT, not null", async () => {
    const calls = harness();
    render(<GenerateReport session={SESSION} onGenerated={() => {}} />);
    await fillForm();
    fireEvent.click(screen.getByRole("button", { name: "Generate report" }));

    await waitFor(() => expect(posts(calls)).toHaveLength(1));
    const body = JSON.parse(String(posts(calls)[0].init?.body));
    expect(body.portfolio_id).toBe("pf-1");
    expect(body.as_of_date).toBe("2026-03-31");
    expect(Object.keys(body.family_runs)).toEqual(["var"]);
    expect("concentration" in body.family_runs).toBe(false);
  });

  it("PROOF 3 (negative): with no family chosen there is no POST, and the reason renders", async () => {
    const calls = harness();
    render(<GenerateReport session={SESSION} onGenerated={() => {}} />);
    fireEvent.change(await screen.findByLabelText("Portfolio"), { target: { value: "pf-1" } });
    fireEvent.change(screen.getByLabelText("As of"), { target: { value: "2026-03-31" } });

    expect(screen.getByText(/Choose at least one family/)).toBeTruthy();
    const button = screen.getByRole("button", { name: "Generate report" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(posts(calls)).toHaveLength(0);
  });

  it("PROOF 4: an INPUT refusal renders the constant + the input-class causes only", async () => {
    harness({ write: { status: 422, detail: "report input refused" } });
    render(<GenerateReport session={SESSION} onGenerated={() => {}} />);
    await fillForm();
    fireEvent.click(screen.getByRole("button", { name: "Generate report" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    const alert = screen.getByRole("alert").textContent ?? "";
    expect(alert).toContain("report input refused");
    expect(alert).toContain("does not disclose which");
    // Carry (f) is SURFACED to the operator — this assertion IS the surfacing, not an intention.
    expect(alert).toContain("root exposure run carries no portfolio scope");
    expect(alert).toContain("dated differently from the report date");
    // ...and the provenance cause is NOT offered here.
    expect(alert).not.toContain("model citation");
  });

  it("PROOF 4: a PROVENANCE refusal shows its OWN cause and NONE of the input-class ones", async () => {
    // The pass-2 BLOCKING, pinned: one shared checklist would hand an operator four causes that
    // cannot produce this refusal, authoritatively.
    harness({ write: { status: 422, detail: "report provenance refused" } });
    render(<GenerateReport session={SESSION} onGenerated={() => {}} />);
    await fillForm();
    fireEvent.click(screen.getByRole("button", { name: "Generate report" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    const alert = screen.getByRole("alert").textContent ?? "";
    expect(alert).toContain("report provenance refused");
    expect(alert).toContain("model citation");
    expect(alert).not.toContain("root exposure run carries no portfolio scope");
    expect(alert).not.toContain("dated differently from the report date");
  });

  it("PROOF 4: the 404 portfolio case is its own rendering, not a generic refusal", async () => {
    harness({ write: { status: 404, detail: "portfolio not found" } });
    render(<GenerateReport session={SESSION} onGenerated={() => {}} />);
    await fillForm();
    fireEvent.click(screen.getByRole("button", { name: "Generate report" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByRole("alert").textContent).toContain("not visible to this tenant");
  });

  it("PROOF 4: a 403 renders the plain-language entitlement text", async () => {
    harness({ write: { status: 403, detail: "forbidden" } });
    render(<GenerateReport session={SESSION} onGenerated={() => {}} />);
    await fillForm();
    fireEvent.click(screen.getByRole("button", { name: "Generate report" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByRole("alert").textContent).toMatch(/not entitled to generate a report/);
  });

  it("PROOF 5: a 201 tells the parent to refetch; a 422 does NOT", async () => {
    let refetched = 0;
    harness();
    render(<GenerateReport session={SESSION} onGenerated={() => refetched++} />);
    await fillForm();
    fireEvent.click(screen.getByRole("button", { name: "Generate report" }));
    await waitFor(() => expect(refetched).toBe(1));

    cleanup();
    harness({ write: { status: 422, detail: "report input refused" } });
    render(<GenerateReport session={SESSION} onGenerated={() => refetched++} />);
    await fillForm();
    fireEvent.click(screen.getByRole("button", { name: "Generate report" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(refetched).toBe(1); // unchanged — a refusal is not a consequence
  });

  it("PROOF 6: the existing-report count shows for a matching date and is absent otherwise", async () => {
    harness({
      reports: {
        items: [
          { id: "r1", as_of_date: "2026-03-31", portfolio_code: "GLOBAL-EQ" },
          { id: "r2", as_of_date: "2026-03-31", portfolio_code: "GLOBAL-EQ" },
          { id: "r3", as_of_date: "2025-12-31", portfolio_code: "GLOBAL-EQ" },
        ],
      },
    });
    render(<GenerateReport session={SESSION} onGenerated={() => {}} />);
    fireEvent.change(await screen.findByLabelText("Portfolio"), { target: { value: "pf-1" } });
    fireEvent.change(screen.getByLabelText("As of"), { target: { value: "2026-03-31" } });
    await waitFor(() =>
      expect(screen.getByText(/2 reports already exist for this book and date/)).toBeTruthy(),
    );

    // The twin: a date with no reports says nothing rather than "0 reports exist".
    fireEvent.change(screen.getByLabelText("As of"), { target: { value: "2024-01-31" } });
    await waitFor(() => expect(screen.queryByText(/already exist/)).toBeNull());
  });

  it("PROOF 6: at the page bound the per-date count is declared UNDETERMINED, never '500+'", async () => {
    // The pass-2 finding, pinned: the listing is as_of_date DESC with no date filter, so a FULL
    // page bounds NOTHING about an older chosen date. Rendering "500+ for this date" would assert
    // ≥500 where there may be zero — a wrong LARGE number replacing the wrong small one.
    harness({
      reports: {
        items: Array.from({ length: 500 }, (_, i) => ({
          id: `r${i}`,
          as_of_date: "2026-12-31",
          portfolio_code: "GLOBAL-EQ",
        })),
      },
    });
    render(<GenerateReport session={SESSION} onGenerated={() => {}} />);
    fireEvent.change(await screen.findByLabelText("Portfolio"), { target: { value: "pf-1" } });
    fireEvent.change(screen.getByLabelText("As of"), { target: { value: "2026-03-31" } });

    await waitFor(() =>
      expect(screen.getByText(/count for this date could not be determined/)).toBeTruthy(),
    );
    expect(screen.queryByText(/500\+ reports already exist/)).toBeNull();
  });

  it("PROOF 7: a second click while the POST is in flight issues no second POST", async () => {
    let release: (v: unknown) => void = () => {};
    const gate = new Promise((r) => (release = r));
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        calls.push({ url, init });
        if (init?.method === "POST") {
          return gate.then(
            () => ({ ok: true, status: 201, json: () => Promise.resolve({ id: "x" }) }) as unknown,
          );
        }
        const body = url.includes("/portfolios")
          ? PORTFOLIOS
          : url.includes("/snapshots")
            ? SNAPSHOTS
            : url.includes("/risk/runs")
              ? VAR_RUNS
              : { items: [] };
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(body),
        } as unknown as Response);
      }),
    );

    render(<GenerateReport session={SESSION} onGenerated={() => {}} />);
    await fillForm();
    const button = screen.getByRole("button", { name: "Generate report" });
    fireEvent.click(button);
    await waitFor(() => expect(posts(calls)).toHaveLength(1));
    fireEvent.click(button); // the double-click
    expect(posts(calls)).toHaveLength(1);

    release(null); // and the twin: after it resolves the button re-arms
    await waitFor(() =>
      expect(
        (screen.getByRole("button", { name: "Generate report" }) as HTMLButtonElement).disabled,
      ).toBe(false),
    );
  });
});
