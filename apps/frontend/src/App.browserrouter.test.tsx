import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BrowserRouter } from "react-router";

import { App } from "./App";

/**
 * FE-M1 (M1-6): the one shipped component the suite never mounted.
 *
 * Every other routing test in this suite uses `MemoryRouter`, which drives navigation from an
 * in-memory array and never touches `window.history` or `window.location`. But `main.tsx` ships
 * `BrowserRouter` — the History-API router — and FE-M1 moved that component into a different
 * npm package (`react-router-dom` -> `react-router`) under a raised React peer floor (>= 19.2.7).
 * A migration that broke exactly the router the app deploys with, and nothing else, would have left
 * this suite green.
 *
 * The deep-link case is the one that matters operationally: the deployed nginx serves index.html
 * for any non-API path (`try_files ... /index.html`, FE-3b HIGH-1), so a user who bookmarks
 * /ops/breaches boots the SPA at that URL and BrowserRouter must resolve the route from
 * `window.location` on first render. `api-prefixes.test.ts` pins the nginx half of that contract;
 * this pins the React half. Together they cover the deep link end to end.
 */

function withSession(): void {
  sessionStorage.setItem(
    "irp.session",
    JSON.stringify({ kind: "dev" as const, userId: "u-1", tenantId: "t-1" }),
  );
}

/** Boot the app the way the browser does after nginx's history fallback: the URL is already the
 * deep link before React mounts. */
function bootAt(path: string): void {
  window.history.replaceState({}, "", path);
  render(
    <BrowserRouter>
      <App />
    </BrowserRouter>,
  );
}

beforeEach(() => {
  sessionStorage.clear();
  window.history.replaceState({}, "", "/");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

describe("BrowserRouter (the router main.tsx actually ships)", () => {
  it("resolves the index route from window.location on first render", () => {
    withSession();
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    bootAt("/");
    expect(screen.getByText(/How you can trust a governed number/)).toBeTruthy();
    expect(mock).not.toHaveBeenCalled();
  });

  it("resolves a DEEP LINK on first render — the nginx history-fallback case", async () => {
    withSession();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => [],
        headers: new Headers({ "content-type": "application/json" }),
      }),
    );
    bootAt("/ops/breaches");
    // The breach queue is the operations landing surface (OPS-1, OQ-6=A).
    await waitFor(() => expect(screen.getByRole("heading", { name: "Breach queue" })).toBeTruthy());
    expect(window.location.pathname).toBe("/ops/breaches");
  });

  it("resolves a deep link with a URL PARAMETER (useParams over the History API)", async () => {
    withSession();
    const mock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "not found" }),
      headers: new Headers({ "content-type": "application/json" }),
    });
    vi.stubGlobal("fetch", mock);
    // `vars` must be a real FAMILIES key: RunDetail allowlists the family segment and returns its
    // "Unknown run family" page WITHOUT fetching for anything else — and that page would satisfy a
    // by-absence assertion just as well, leaving a broken useParams green (review fold).
    bootAt("/runs/vars/11111111-1111-4111-8111-111111111111");
    // The param reached the view — proven by the request URL carrying the runId from the URL, and
    // by the view rendering its own honest not-found state rather than the catch-all redirect.
    await waitFor(() =>
      expect(screen.getByText(/Run not found \(or not visible to this identity\)/)).toBeTruthy(),
    );
    expect(mock).toHaveBeenCalledTimes(1);
    expect(mock.mock.calls[0][0]).toBe("/risk/vars/runs/11111111-1111-4111-8111-111111111111");
    expect(window.location.pathname).toBe("/runs/vars/11111111-1111-4111-8111-111111111111");
    expect(screen.queryByText(/How you can trust a governed number/)).toBeNull();
  });

  it("sends an unknown deep link to the catch-all redirect, rewriting window.location", async () => {
    withSession();
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    bootAt("/no/such/page");
    // `<Route path="*" element={<Navigate to="/" replace />} />` must drive the REAL History API
    // here, not just an in-memory entry stack.
    await waitFor(() => expect(window.location.pathname).toBe("/"));
    expect(screen.getByText(/How you can trust a governed number/)).toBeTruthy();
    expect(mock).not.toHaveBeenCalled();
  });

  it("gates a deep link behind the session — an unauthenticated deep link shows the sign-in surface", () => {
    // No session in storage. The deep link must NOT render the operations surface.
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    bootAt("/ops/breaches");
    expect(screen.getByText(/Start a dev session/)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: /Breaches/ })).toBeNull();
    expect(mock).not.toHaveBeenCalled();
  });
});
