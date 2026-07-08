import { beforeEach, describe, expect, it } from "vitest";

import { clearSession, isValidSessionId, loadSession, saveSession } from "./session";

beforeEach(() => {
  sessionStorage.clear();
});

describe("dev session storage", () => {
  it("round-trips a session through sessionStorage", () => {
    saveSession({ userId: "u", tenantId: "t" });
    expect(loadSession()).toEqual({ userId: "u", tenantId: "t" });
    clearSession();
    expect(loadSession()).toBeNull();
  });

  it("treats a corrupt stored value as no session and clears it", () => {
    sessionStorage.setItem("irp.dev.session", "{nope");
    expect(loadSession()).toBeNull();
    expect(sessionStorage.getItem("irp.dev.session")).toBeNull();
    sessionStorage.setItem("irp.dev.session", JSON.stringify({ userId: 5 }));
    expect(loadSession()).toBeNull();
    // The clear-on-corrupt contract holds for shape-invalid values too (review fold: only
    // the parse-failure branch was asserting removal).
    expect(sessionStorage.getItem("irp.dev.session")).toBeNull();
  });

  it("drops a persisted session whose ids cannot be sent as headers (non-ASCII)", () => {
    sessionStorage.setItem(
      "irp.dev.session",
      JSON.stringify({ userId: "u—1", tenantId: "t-1" }), // em-dash: header construction throws
    );
    expect(loadSession()).toBeNull();
    expect(sessionStorage.getItem("irp.dev.session")).toBeNull();
  });

  it("validates session ids as printable ASCII", () => {
    expect(isValidSessionId("a4f0c9e2-1b2c-4d5e-8f90-000000000001")).toBe(true);
    expect(isValidSessionId("tenant-code_1")).toBe(true);
    expect(isValidSessionId("")).toBe(false);
    expect(isValidSessionId("u—1")).toBe(false); // em-dash
    expect(isValidSessionId("café")).toBe(false);
    expect(isValidSessionId("a b")).toBe(false); // no spaces in ids
  });
});
