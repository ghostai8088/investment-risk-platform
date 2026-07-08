import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { App } from "./App";

const BANNER = /DEV SESSION — identity is unverified/;

function renderApp(): void {
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
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
    expect(screen.queryByText(/Risk runs/)).toBeNull();
    expect(mock).not.toHaveBeenCalled();
  });

  it("keeps the DEV banner when a session exists (never dismissable)", async () => {
    sessionStorage.setItem("irp.dev.session", JSON.stringify({ userId: "u-1", tenantId: "t-1" }));
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ items: [] }),
      }),
    );
    renderApp();
    expect(screen.getByText(BANNER)).toBeTruthy();
    expect(await screen.findByText(/No runs yet/)).toBeTruthy();
  });

  it("renders the not-entitled state honestly on 403", async () => {
    sessionStorage.setItem("irp.dev.session", JSON.stringify({ userId: "u-1", tenantId: "t-1" }));
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 403, json: () => Promise.resolve({}) }),
    );
    renderApp();
    expect(await screen.findByText(/not entitled to view risk runs \(403\)/)).toBeTruthy();
    expect(screen.getByText(BANNER)).toBeTruthy();
  });
});
