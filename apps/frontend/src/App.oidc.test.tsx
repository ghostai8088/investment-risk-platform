import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

// FE-3b (OD-FE-3b-F): the honesty invariant — in oidc mode the "unverified DEV SESSION" banner must
// NEVER render (a verified Bearer session IS a security boundary). Mock authConfig into oidc mode.
vi.mock("./api/authConfig", () => ({
  authMode: "oidc",
  oidcConfig: () => ({
    issuer: "http://kc:8080/realms/irp-local",
    clientId: "irp-frontend",
    redirectUri: "http://localhost:5173/callback",
  }),
}));

import { App } from "./App";

const BANNER = /DEV SESSION — identity is unverified/;

function renderApp(path = "/"): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  sessionStorage.clear();
});
afterEach(() => {
  cleanup();
});

describe("App in oidc mode", () => {
  it("shows a Sign in button and NO dev banner when logged out", () => {
    renderApp("/");
    expect(screen.getByRole("button", { name: /Sign in/ })).toBeTruthy();
    expect(screen.queryByText(BANNER)).toBeNull(); // honesty: no 'unverified' claim in oidc mode
    expect(screen.queryByText(/Start a dev session/)).toBeNull();
  });

  it("renders the app WITHOUT the dev banner over a verified oidc session", () => {
    sessionStorage.setItem(
      "irp.session",
      JSON.stringify({
        kind: "oidc",
        accessToken: "aaa.bbb.ccc",
        subject: "demo-auditor",
        expiresAt: Math.floor(Date.now() / 1000) + 3600,
      }),
    );
    renderApp("/");
    // the governance walk landing renders (static)…
    expect(screen.getByText(/How you can trust a governed number/)).toBeTruthy();
    // …with the decoded subject in the chrome and a Sign out control, and NO dev banner.
    expect(screen.getByText("demo-auditor")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Sign out/ })).toBeTruthy();
    expect(screen.queryByText(BANNER)).toBeNull();
  });
});
