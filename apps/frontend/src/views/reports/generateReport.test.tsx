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
import { Reports } from "./Reports";
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

  it("PROOF 5 (second half): after a 201 the LIST shows the new report's report_code", async () => {
    // The audit's HIGH-2: the first version proved only that the callback fired. The record binds
    // "the new report's `report_code` appears in the rendered rows" — the CONSEQUENCE, which is
    // the half that distinguishes "the write returned 201" from "the ledger now shows it". Pass 2
    // had rewritten this proof from `id` to `report_code` precisely to make it implementable, and
    // the implementable half was the half that got dropped.
    const before = {
      id: "r-old",
      portfolio_code: "GLOBAL-EQ",
      as_of_date: "2026-03-31",
      report_code: "RPT-OLD",
      generated_at: "2026-03-31T00:00:00Z",
      content_hash: "a".repeat(64),
    };
    const after = { ...before, id: "r-new", report_code: "RPT-NEW" };
    let generated = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (init?.method === "POST") {
          generated = true;
          return Promise.resolve({
            ok: true,
            status: 201,
            json: () => Promise.resolve(after),
          } as unknown as Response);
        }
        const body = url.includes("/portfolios")
          ? PORTFOLIOS
          : url.includes("/snapshots")
            ? SNAPSHOTS
            : url.includes("/risk/runs")
              ? VAR_RUNS
              : url.includes("/reports")
                ? { items: generated ? [after, before] : [before] }
                : { items: [] };
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(body),
        } as unknown as Response);
      }),
    );

    render(<Reports session={SESSION} />);
    await waitFor(() => expect(screen.getByText("RPT-OLD")).toBeTruthy());
    expect(screen.queryByText("RPT-NEW")).toBeNull(); // the twin: not there before the act

    await fillForm();
    fireEvent.click(screen.getByRole("button", { name: "Generate report" }));
    await waitFor(() => expect(screen.getByText("RPT-NEW")).toBeTruthy());
  });

  it("PROOF 1: the concentration and liquidity dropdowns read their OWN endpoints", async () => {
    // The audit's MEDIUM-4: proof 1 is bound "per family x4" and only two were covered.
    const calls = harness();
    render(<GenerateReport session={SESSION} onGenerated={() => {}} />);
    fireEvent.click(await screen.findByLabelText("Concentration"));
    fireEvent.click(screen.getByLabelText("Liquidity"));
    await waitFor(() => expect(screen.getByLabelText("Liquidity run")).toBeTruthy());
    expect(calls.some((c) => c.url.includes("/concentration/runs"))).toBe(true);
    expect(calls.some((c) => c.url.includes("/liquidity/runs"))).toBe(true);
    // Each carries the status filter the record binds; neither reads another family's listing.
    for (const path of ["/concentration/runs", "/liquidity/runs"]) {
      expect(calls.find((c) => c.url.includes(path))?.url).toContain("status=COMPLETED");
    }
    expect(calls.some((c) => c.url.includes("/risk/runs"))).toBe(false);
  });

  it("the carry-(f) checklist line is bound to the carry still being OPEN", async () => {
    // The ratified staleness binding (audit MEDIUM-1): the FE text names a platform limitation,
    // so it rots the moment the limitation is fixed. A prose reminder would not survive; this
    // reddens when carry (f) is marked paid, forcing the screen's text to move with it.
    const { existsSync, readFileSync } = await import("node:fs");
    const { dirname, resolve } = await import("node:path");
    // Walk UP for the repo root instead of counting `../` from cwd. The repo's other file-reading
    // guards are cwd-sensitive (they assume `apps/frontend`) and the audit caught them failing
    // when the suite is invoked from the root — a guard that cannot find its subject passes by
    // reading nothing, which is the failure mode this binding exists to prevent.
    let dir = process.cwd();
    while (!existsSync(resolve(dir, "10_delivery_backlog")) && dirname(dir) !== dir) {
      dir = dirname(dir);
    }
    const path = resolve(dir, "10_delivery_backlog/rpt_2_slice_record.md");
    expect(
      existsSync(path),
      `could not locate rpt_2_slice_record.md from cwd ${process.cwd()}`,
    ).toBe(true);
    const record = readFileSync(path, "utf8");
    const carryLine = record.split("\n").find((l) => l.includes("(f) VaR is unbindable")) ?? "";
    expect(
      carryLine,
      "carry (f)'s row is not in rpt_2_slice_record.md — the binding reads nothing",
    ).not.toBe("");
    expect(
      carryLine,
      "carry (f) is marked PAID: the unscoped-VaR limitation named in GenerateReport's " +
        "input-class checklist is now stale and the screen's text must move with it",
    ).not.toContain("PAID");
  });
});
