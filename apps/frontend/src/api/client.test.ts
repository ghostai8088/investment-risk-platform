import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiGet } from "./client";

const SESSION = { kind: "dev" as const, userId: "u-1", tenantId: "t-1" };

function stubFetch(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const mock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiGet", () => {
  it("injects the two dev-session headers and parses JSON", async () => {
    const mock = stubFetch(200, { items: [] });
    const result = await apiGet<{ items: unknown[] }>("/risk/runs", SESSION);
    expect(result.items).toEqual([]);
    expect(mock).toHaveBeenCalledWith("/risk/runs", {
      method: "GET",
      headers: { "X-User-Id": "u-1", "X-Tenant-Id": "t-1" },
    });
  });

  it("injects the Bearer token (and NO dev headers) for an oidc session — still a GET", async () => {
    const mock = stubFetch(200, { items: [] });
    const oidc = {
      kind: "oidc" as const,
      accessToken: "aaa.bbb.ccc",
      subject: "demo-auditor",
      expiresAt: Math.floor(Date.now() / 1000) + 3600,
    };
    await apiGet("/risk/runs", oidc);
    expect(mock).toHaveBeenCalledWith("/risk/runs", {
      method: "GET",
      headers: { Authorization: "Bearer aaa.bbb.ccc" },
    });
    const sentHeaders = mock.mock.calls[0][1].headers as Record<string, string>;
    expect(sentHeaders["X-User-Id"]).toBeUndefined();
    expect(sentHeaders["X-Tenant-Id"]).toBeUndefined();
  });

  it("refuses to fetch without a session", async () => {
    const mock = stubFetch(200, {});
    await expect(apiGet("/risk/runs", null)).rejects.toMatchObject({ kind: "no-session" });
    expect(mock).not.toHaveBeenCalled();
  });

  it.each([
    [401, "unauthorized"],
    [403, "forbidden"],
    [404, "not-found"],
    [422, "invalid"],
    [500, "server"],
  ])("maps HTTP %i to kind %s", async (status, kind) => {
    stubFetch(status, {});
    await expect(apiGet("/risk/runs", SESSION)).rejects.toMatchObject({ kind });
  });

  it("maps a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("boom")));
    const err = await apiGet("/risk/runs", SESSION).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).kind).toBe("network");
  });

  it("maps a 200 with a NON-JSON body to 'server', never 'unreachable' (OPS-H1 H1-10)", async () => {
    // A proxy error page or SPA history-fallback serving HTML with a happy status: the success
    // parse previously threw a bare SyntaxError outside the try, which callers wrapped as
    // "network / the API is unreachable" — sending an operator to check a backend that ANSWERED.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.reject(new SyntaxError("Unexpected token '<'")),
      }),
    );
    const err = await apiGet("/risk/runs", SESSION).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).kind).toBe("server");
    expect((err as ApiError).message).toContain("non-JSON");
  });
});
