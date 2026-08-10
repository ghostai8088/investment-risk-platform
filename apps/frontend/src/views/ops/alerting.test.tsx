/**
 * ALERT-1: the Alerting panel.
 *
 * What makes this a governance surface rather than a status badge is that it distinguishes states
 * an operator would otherwise conflate: a quiet tenant from a broken channel, an accepted bound
 * from a dead channel, and "nothing scheduled" from "scheduled and not running". Those four
 * distinctions are what the tests below pin.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Alerting } from "./Alerting";
import type { Session } from "../../session";

const SESSION: Session = { kind: "dev", userId: "u-1", tenantId: "t-1" };

const HEALTHY = {
  healthy: true,
  unreadable_rows: 0,
  lost_verdicts: 0,
  failed_sweeps: 0,
  sweep_overdue: false,
  dead_channel: false,
  undeliverable_attempts: 0,
  exhausted_verdicts: 0,
  queued: 0,
  no_schedule: false,
  paused_schedules: 0,
  nothing_to_reproduce: 0,
  last_terminal_sweep_at: "2026-08-10T03:00:00Z",
};

function routeHealth(payload: unknown, status = 200) {
  const fn = vi.fn(() =>
    Promise.resolve({
      ok: status === 200,
      status,
      json: () => Promise.resolve(payload),
    } as unknown as Response),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Alerting", () => {
  it("a working channel reads HEALTHY", async () => {
    routeHealth(HEALTHY);
    render(<Alerting session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText("HEALTHY")).toBeTruthy();
    });
    expect(screen.getByText(/The sweep is running and alarms are getting through/)).toBeTruthy();
  });

  it("a STOPPED sweep is NOT healthy — the absence signal reaches the screen", async () => {
    routeHealth({ ...HEALTHY, healthy: false, sweep_overdue: true });
    render(<Alerting session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText("NOT HEALTHY")).toBeTruthy();
    });
    // The row exists AND carries an action, not just a number.
    expect(screen.getByText("Sweep overdue")).toBeTruthy();
    expect(screen.getByText(/Check the worker process/)).toBeTruthy();
  });

  it("no schedule is explained as a gap in setup, not an outage", async () => {
    routeHealth({ ...HEALTHY, no_schedule: true });
    render(<Alerting session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText(/No reproduction schedule is active/)).toBeTruthy();
    });
    expect(screen.getByText("HEALTHY")).toBeTruthy();
  });

  it("the accepted bound is amber while a dead channel is red", async () => {
    routeHealth({ ...HEALTHY, exhausted_verdicts: 2 });
    render(<Alerting session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText("Silenced by the retry bound")).toBeTruthy();
    });
    // Amber: visible, but the channel is still healthy overall.
    expect(screen.getByText("HEALTHY")).toBeTruthy();

    cleanup();
    routeHealth({ ...HEALTHY, healthy: false, dead_channel: true, exhausted_verdicts: 2 });
    render(<Alerting session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText("NOT HEALTHY")).toBeTruthy();
    });
    expect(screen.getByText(/nobody being told anything/)).toBeTruthy();
  });

  it("an empty tenant's failed sweeps are explained as by-design", async () => {
    routeHealth({ ...HEALTHY, nothing_to_reproduce: 3 });
    render(<Alerting session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText("Empty-tenant sweeps")).toBeTruthy();
    });
    expect(screen.getByText(/fails its nightly sweep by design/)).toBeTruthy();
    expect(screen.getByText("HEALTHY")).toBeTruthy();
  });

  it("a refusal is explained in plain language, never as a bare status code", async () => {
    routeHealth({ detail: "permission denied" }, 403);
    render(<Alerting session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
    expect(screen.getByRole("alert").textContent).not.toContain("403");
  });

  it("says plainly that it pages nobody", async () => {
    routeHealth(HEALTHY);
    render(<Alerting session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText(/This screen does not page anyone/)).toBeTruthy();
    });
  });
});
