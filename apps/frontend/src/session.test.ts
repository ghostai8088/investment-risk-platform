import { beforeEach, describe, expect, it } from "vitest";

import { clearSession, isValidHeaderValue, loadSession, saveSession } from "./session";

const KEY = "irp.session";

beforeEach(() => {
  sessionStorage.clear();
});

describe("session storage", () => {
  it("round-trips a dev session through sessionStorage", () => {
    saveSession({ kind: "dev" as const, userId: "u", tenantId: "t" });
    expect(loadSession()).toEqual({ kind: "dev" as const, userId: "u", tenantId: "t" });
    clearSession();
    expect(loadSession()).toBeNull();
  });

  it("round-trips an unexpired oidc session", () => {
    const future = Math.floor(Date.now() / 1000) + 3600;
    saveSession({
      kind: "oidc",
      accessToken: "aaa.bbb.ccc",
      subject: "demo-auditor",
      expiresAt: future,
    });
    expect(loadSession()).toEqual({
      kind: "oidc",
      accessToken: "aaa.bbb.ccc",
      subject: "demo-auditor",
      expiresAt: future,
    });
  });

  it("drops an EXPIRED oidc session (⇒ re-auth)", () => {
    const past = Math.floor(Date.now() / 1000) - 1;
    sessionStorage.setItem(
      KEY,
      JSON.stringify({ kind: "oidc", accessToken: "aaa.bbb.ccc", subject: "x", expiresAt: past }),
    );
    expect(loadSession()).toBeNull();
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it("treats a corrupt or kind-less stored value as no session and clears it", () => {
    sessionStorage.setItem(KEY, "{nope");
    expect(loadSession()).toBeNull();
    expect(sessionStorage.getItem(KEY)).toBeNull();
    // A legacy (pre-FE-3b) value with no `kind` is rejected — the discriminant is required.
    sessionStorage.setItem(KEY, JSON.stringify({ userId: "u", tenantId: "t" }));
    expect(loadSession()).toBeNull();
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it("drops a persisted dev session whose ids cannot be sent as headers (non-ASCII)", () => {
    sessionStorage.setItem(
      KEY,
      JSON.stringify({ kind: "dev" as const, userId: "u—1", tenantId: "t-1" }), // em-dash: header ctor throws
    );
    expect(loadSession()).toBeNull();
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it("validates header values as printable ASCII", () => {
    expect(isValidHeaderValue("a4f0c9e2-1b2c-4d5e-8f90-000000000001")).toBe(true);
    expect(isValidHeaderValue("aaa.bbb-ccc_ddd")).toBe(true); // JWT-shaped
    expect(isValidHeaderValue("")).toBe(false);
    expect(isValidHeaderValue("u—1")).toBe(false); // em-dash
    expect(isValidHeaderValue("café")).toBe(false);
    expect(isValidHeaderValue("a b")).toBe(false); // no spaces
  });
});
