import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { App } from "./App";

const BANNER = /DEV SESSION — identity is unverified/;

function renderApp(path = "/"): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

function withSession(): void {
  sessionStorage.setItem(
    "irp.session",
    JSON.stringify({ kind: "dev" as const, userId: "u-1", tenantId: "t-1" }),
  );
}

beforeEach(() => {
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("shows the permanent DEV banner and the session form when no session exists — and fetches NOTHING", () => {
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    renderApp();
    expect(screen.getByText(BANNER)).toBeTruthy();
    expect(screen.getByText(/Start a dev session/)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Runs (all calculations)" })).toBeNull();
    expect(mock).not.toHaveBeenCalled();
  });

  it("lands on the governance walk (static) when a session exists — and still fetches NOTHING", () => {
    withSession();
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    renderApp("/");
    expect(screen.getByText(BANNER)).toBeTruthy();
    expect(screen.getByText(/How you can trust a governed number/)).toBeTruthy();
    // The walk landing is static — the read-only client only fires when you enter a data step.
    expect(mock).not.toHaveBeenCalled();
  });

  it("keeps the DEV banner and shows the run browser at /runs", async () => {
    withSession();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ items: [] }),
      }),
    );
    renderApp("/runs");
    expect(screen.getByText(BANNER)).toBeTruthy();
    expect(await screen.findByText(/No runs yet/)).toBeTruthy();
  });

  it("renders the not-entitled state honestly on 403 (run browser)", async () => {
    withSession();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 403, json: () => Promise.resolve({}) }),
    );
    renderApp("/runs");
    expect(await screen.findByText(/not entitled to view the selected runs/)).toBeTruthy();
    expect(screen.getByText(BANNER)).toBeTruthy();
  });

  it("provides a keyboard skip-link and marks the active nav step (WCAG)", () => {
    withSession();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve([]) }),
    );
    renderApp("/walk/exposures");
    const skip = screen.getByRole("link", { name: /Skip to main content/ });
    expect(skip.getAttribute("href")).toBe("#walk-main");
    const active = screen.getByRole("link", { current: "page" });
    expect(active.textContent).toMatch(/Exposures/);
  });

  it("routes a walk step and shows its heading + the walk nav", () => {
    withSession();
    // The step resolves the demo book first; a clean empty portfolios list keeps the chrome tidy.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve([]) }),
    );
    renderApp("/walk/capture");
    expect(screen.getByRole("heading", { name: /1 · Capture/ })).toBeTruthy();
    // OPS-1 (OQ-6=A): the nav is no longer walk-only — it leads with Operations and keeps the walk
    // and the run browser below, so it is labelled "Main".
    expect(screen.getByRole("navigation", { name: "Main" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Breach queue" })).toBeTruthy();
  });

  it("routes the operations surfaces and scopes the book chip to the walk", () => {
    withSession();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve([]) }),
    );
    renderApp("/ops/breaches");
    expect(screen.getByRole("heading", { name: "Breach queue" })).toBeTruthy();
    // The header's book chip claims "the walk is scoped to this book" — over a TENANT-WIDE queue
    // that claim is false, so it must not render here (OPS-1 verifier fold).
    expect(screen.queryByTitle(/scoped to this book/i)).toBeNull();
  });
});
