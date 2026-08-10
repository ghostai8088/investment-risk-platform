/**
 * REPRO-2: the Reproduction screen (OQ-REP2-6).
 *
 * The record bound UI PROOFS to this screen by name, because its predecessor slice promised
 * "API + UI" and bound zero. What is worth pinning is not that the tables render — it is the four
 * places this screen could quietly mislead an operator:
 *
 *  - a tenant with NO schedule must not read as a clean night (the honest-empty rule);
 *  - a tenant whose schedules are ALL PAUSED must be told the control is off, at the screen where
 *    they would go to check it;
 *  - a DIVERGED verdict must be visibly different from a MATCH, and must name what diverged;
 *  - an UNREPRODUCIBLE verdict must show the fixed literal and NEVER stored exception text.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Reproduction } from "./Reproduction";
import type { Session } from "../../session";

const SESSION: Session = { kind: "dev", userId: "u-1", tenantId: "t-1" };

const SCHEDULE = {
  id: "s-1",
  code: "nightly-reproduction",
  name: "Nightly reproduction",
  target_run_type: "REPRODUCTION",
  cadence_kind: "INTERVAL",
  interval_days: 1,
  status: "ACTIVE",
  anchor_date: "2026-01-01",
  environment_id: "prod",
  scope_portfolio_id: null,
  model_version_id: null,
  calendar_id: null,
};

/** Route each GET the screen makes to a canned payload, by path. */
function routeAll(payloads: {
  schedules?: unknown;
  runs?: unknown;
  checks?: unknown;
}): ReturnType<typeof vi.fn> {
  const fn = vi.fn((url: string) => {
    const body = url.includes("/reproduction/checks")
      ? (payloads.checks ?? [])
      : url.includes("/schedules/runs")
        ? (payloads.runs ?? { items: [] })
        : (payloads.schedules ?? { items: [] });
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    } as unknown as Response);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Reproduction", () => {
  it("a tenant with NO schedule is told the control is not running, not that all is well", async () => {
    routeAll({});
    render(<Reproduction session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText(/No reproduction schedule exists/)).toBeTruthy();
    });
    expect(screen.getByText(/makes no claim about your numbers/)).toBeTruthy();
  });

  it("ALL schedules paused says the control is switched OFF and points at Alerting", async () => {
    routeAll({ schedules: { items: [{ ...SCHEDULE, status: "PAUSED" }] } });
    render(<Reproduction session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText(/the detective control is switched OFF/)).toBeTruthy();
    });
    // The operator's next step is named, and it matches what the health surface will actually say.
    expect(screen.getByText(/Alerting panel reads NOT HEALTHY/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Resume" })).toBeTruthy();
  });

  it("an ACTIVE schedule offers Pause, and does NOT claim the control is off", async () => {
    routeAll({ schedules: { items: [SCHEDULE] } });
    render(<Reproduction session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Pause" })).toBeTruthy();
    });
    expect(screen.queryByText(/switched OFF/)).toBeNull();
  });

  it("a DIVERGED verdict is loud and names the field that diverged", async () => {
    routeAll({
      checks: [
        {
          id: "c-1",
          family_key: "VAR",
          verdict: "DIVERGED",
          rows_compared: 4,
          rows_diverged: 1,
          subject_run_id: "r-1",
          calculation_run_id: "r-2",
          system_from: "2026-08-10T03:00:00Z",
          first_divergence: "key=(TOTAL) field=sigma",
        },
      ],
    });
    render(<Reproduction session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText("DIVERGED")).toBeTruthy();
    });
    expect(screen.getByText("key=(TOTAL) field=sigma")).toBeTruthy();
    expect(screen.getByText("1/4")).toBeTruthy();
  });

  it("an UNREPRODUCIBLE verdict shows the fixed literal — never stored exception text", async () => {
    // The API guarantees this (carry (n) discharged by exclusion): the stored text never reaches
    // the wire. This pins the SCREEN's half — it renders whatever came back rather than trying to
    // reconstruct a reason, so there is no second place for the text to reappear.
    routeAll({
      checks: [
        {
          id: "c-2",
          family_key: "REPORT",
          verdict: "UNREPRODUCIBLE",
          rows_compared: 0,
          rows_diverged: 0,
          subject_run_id: "r-3",
          calculation_run_id: "r-4",
          system_from: "2026-08-10T03:00:00Z",
          first_divergence: "UNREPRODUCIBLE — detail withheld; investigate at database grade",
        },
      ],
    });
    render(<Reproduction session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText("UNREPRODUCIBLE")).toBeTruthy();
    });
    expect(screen.getByText(/detail withheld; investigate at database grade/)).toBeTruthy();
  });

  it("an empty verdict list makes NO all-clear claim", async () => {
    routeAll({ schedules: { items: [SCHEDULE] } });
    render(<Reproduction session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText(/That is not an all-clear/)).toBeTruthy();
    });
  });

  it("a FAILED tick is shown as an outage in the control, distinct from a divergence", async () => {
    routeAll({
      schedules: { items: [SCHEDULE] },
      runs: {
        items: [
          {
            id: "sr-1",
            schedule_id: "s-1",
            scheduled_for: "2026-08-10T03:00:00Z",
            fired_at: "2026-08-10T03:00:01Z",
            outcome: "FAILED",
            failure_reason: "could not CHECK VAR: lock timeout",
            calculation_run_id: null,
            resolved_exposure_run_id: null,
            resolved_covariance_run_id: null,
          },
        ],
      },
    });
    render(<Reproduction session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText("FAILED")).toBeTruthy();
    });
    expect(screen.getByText(/could not CHECK VAR/)).toBeTruthy();
    expect(screen.getByText(/outage in the control, not a divergence/)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------------------------
// The §3-bound write proofs, added at the different-engine review. The record binds "component
// tests — create/pause/resume through `writes.ts` with refusal rendering; … the second-active-
// schedule warning" BY NAME, and the first seven tests rendered buttons without ever exercising a
// write, rendering a refusal, or asserting the warning — part 1's F2 class (a ratified proof
// bound in the record, quietly not delivered), caught by the same review pattern.
// ---------------------------------------------------------------------------------------------

/** Route GETs to payloads AND capture writes, answering them with `write` (a Response-shaped stub). */
function routeWithWrites(
  payloads: { schedules?: unknown },
  write: { status: number; body?: unknown },
): ReturnType<typeof vi.fn> {
  const fn = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method && init.method !== "GET") {
      return Promise.resolve({
        ok: write.status < 400,
        status: write.status,
        json: () => Promise.resolve(write.body ?? {}),
      } as unknown as Response);
    }
    const body = url.includes("/reproduction/checks")
      ? []
      : url.includes("/schedules/runs")
        ? { items: [] }
        : (payloads.schedules ?? { items: [] });
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    } as unknown as Response);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("Reproduction — the write path through writes.ts", () => {
  it("Pause actually POSTs to /schedules/{id}/pause", async () => {
    const fetchSpy = routeWithWrites(
      { schedules: { items: [SCHEDULE] } },
      { status: 200, body: { ...SCHEDULE, status: "PAUSED" } },
    );
    render(<Reproduction session={SESSION} />);
    const pause = await screen.findByRole("button", { name: "Pause" });
    pause.click();
    await waitFor(() => {
      const posts = fetchSpy.mock.calls.filter(([, init]) => init?.method === "POST");
      expect(posts.some(([url]) => String(url).includes("/schedules/s-1/pause"))).toBe(true);
    });
  });

  it("a schedule.view-only principal's refused pause is EXPLAINED, not swallowed", async () => {
    // The server's 403 must surface through `explain()`'s plain-language rendering — the OPS-1
    // convention: the FE holds no permission knowledge, so the refusal names the attempted act.
    routeWithWrites(
      { schedules: { items: [SCHEDULE] } },
      { status: 403, body: { detail: "forbidden" } },
    );
    render(<Reproduction session={SESSION} />);
    const pause = await screen.findByRole("button", { name: "Pause" });
    pause.click();
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/not entitled to change this schedule/);
    });
  });

  it("Create submits through createSchedule and a duplicate-code refusal renders plainly", async () => {
    const fetchSpy = routeWithWrites(
      { schedules: { items: [] } },
      {
        status: 422,
        body: {
          detail: "a schedule with code 'nightly-reproduction' already exists in this tenant",
        },
      },
    );
    render(<Reproduction session={SESSION} />);
    const submit = await screen.findByRole("button", {
      name: "Create daily reproduction schedule",
    });
    submit.click();
    await waitFor(() => {
      const posts = fetchSpy.mock.calls.filter(([, init]) => init?.method === "POST");
      expect(posts.some(([url]) => String(url).endsWith("/schedules"))).toBe(true);
    });
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/already exists/);
    });
  });

  it("the SECOND-active-schedule warning shows beside the form exactly when one is ACTIVE", async () => {
    // The ratified sentence: "the UI warns before creating a second schedule for a family that
    // already has an ACTIVE one." Both directions, so the warning cannot become wallpaper.
    routeWithWrites({ schedules: { items: [SCHEDULE] } }, { status: 200 });
    render(<Reproduction session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText(/second active reproduction schedule would sweep/)).toBeTruthy();
    });
    cleanup();
    routeWithWrites({ schedules: { items: [] } }, { status: 200 });
    render(<Reproduction session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText(/No reproduction schedule exists/)).toBeTruthy();
    });
    expect(screen.queryByText(/second active reproduction schedule would sweep/)).toBeNull();
  });
});
