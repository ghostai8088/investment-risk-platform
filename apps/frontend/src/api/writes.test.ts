/**
 * OPS-1: the write surface — identity injection, the expected_seq token, and refusal decoding.
 *
 * These are the first mutating calls the SPA has ever made, so the invariants proven here are the
 * ones a read-only client never needed: the right verb and body reach the wire, the session's
 * identity is injected identically to reads (one implementation — the SSO-1 drift lesson), and a
 * refusal body is actually READ rather than discarded (the UI cannot explain what it never saw).
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./client";
import { approveLimit, closeBreach, respondToBreach, reviewBreach } from "./writes";
import type { Session } from "../session";

const DEV: Session = { kind: "dev", userId: "u-1", tenantId: "t-1" };
const OIDC: Session = { kind: "oidc", accessToken: "tok", subject: "sub", expiresAt: 9e12 };

function stubFetch(response: Partial<Response> & { jsonBody?: unknown }): ReturnType<typeof vi.fn> {
  const fn = vi.fn(() =>
    Promise.resolve({
      ok: response.ok ?? true,
      status: response.status ?? 200,
      json: () => Promise.resolve(response.jsonBody ?? {}),
    } as unknown as Response),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the write surface", () => {
  it("POSTs the respond verb with the expected_seq token and the dev identity", async () => {
    const fetchMock = stubFetch({ jsonBody: { id: "b1" } });
    await respondToBreach(DEV, "b1", { narrative: "hedged", expectedSeq: 3 });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/breaches/b1/respond");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({
      "X-User-Id": "u-1",
      "X-Tenant-Id": "t-1",
      "Content-Type": "application/json",
    });
    expect(JSON.parse(String(init.body))).toEqual({ narrative: "hedged", expected_seq: 3 });
  });

  it("injects a Bearer token for an OIDC session (same core as reads)", async () => {
    const fetchMock = stubFetch({ jsonBody: {} });
    await approveLimit(OIDC, "l1", { approvalRef: "minutes://x" });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toMatchObject({ Authorization: "Bearer tok" });
    expect(init.headers).not.toHaveProperty("X-User-Id");
  });

  it("omits an empty narrative so an ACCEPT body stays minimal (the DTOs forbid extras)", async () => {
    const fetchMock = stubFetch({ jsonBody: {} });
    await reviewBreach(DEV, "b1", { outcome: "ACCEPT", expectedSeq: 1 });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ outcome: "ACCEPT", expected_seq: 1 });
  });

  it("sends the narrative on a REJECT", async () => {
    const fetchMock = stubFetch({ jsonBody: {} });
    await reviewBreach(DEV, "b1", { outcome: "REJECT", narrative: "redo", expectedSeq: 2 });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toMatchObject({ outcome: "REJECT", narrative: "redo" });
  });

  it("carries the refusal detail off a 409 so the UI can explain WHICH control fired", async () => {
    stubFetch({
      ok: false,
      status: 409,
      jsonBody: { detail: "separation of duties: the actor responded to this breach" },
    });
    await expect(
      closeBreach(DEV, "b1", { evidenceRef: "t://1", expectedSeq: 1 }),
    ).rejects.toMatchObject({
      kind: "conflict",
      status: 409,
      detail: "separation of duties: the actor responded to this breach",
    });
  });

  it("flattens a 422 ValidationError[] instead of rendering [object Object]", async () => {
    stubFetch({
      ok: false,
      status: 422,
      jsonBody: { detail: [{ loc: ["body", "narrative"], msg: "field required" }] },
    });
    let err: ApiError | null = null;
    try {
      await closeBreach(DEV, "b1", { evidenceRef: "", expectedSeq: 1 });
    } catch (e: unknown) {
      err = e as ApiError;
    }
    expect(err?.kind).toBe("invalid");
    expect(err?.detail).toBe("narrative: field required");
    expect(err?.detail).not.toContain("[object Object]");
  });

  it("maps a 503 deadlock victim to a RETRYABLE kind, not a server failure", async () => {
    stubFetch({ ok: false, status: 503, jsonBody: { detail: "transient lock contention; retry" } });
    await expect(
      respondToBreach(DEV, "b1", { narrative: "x", expectedSeq: 1 }),
    ).rejects.toMatchObject({ kind: "unavailable" });
  });

  it("refuses to send without a session", async () => {
    const fetchMock = stubFetch({ jsonBody: {} });
    await expect(
      respondToBreach(null, "b1", { narrative: "x", expectedSeq: 1 }),
    ).rejects.toMatchObject({ kind: "no-session" });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
