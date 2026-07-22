import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/authConfig", () => ({
  oidcConfig: () => ({
    issuer: "http://kc:8080/realms/irp-local",
    clientId: "irp-frontend",
    redirectUri: "http://localhost:5173/callback",
  }),
}));

import { beginLogin, completeLogin } from "./oidc";
import { loadSession } from "../session";

/** A base64url JWT payload (unsigned — the FE only decodes sub/exp). */
function fakeJwt(sub: string, exp: number): string {
  const b64url = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${b64url({ alg: "RS256" })}.${b64url({ sub, exp })}.sig`;
}

beforeEach(() => {
  sessionStorage.clear();
  window.history.replaceState(null, "", "/callback?code=abc&state=xyz");
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("beginLogin (the /authorize redirect assembler)", () => {
  it("stashes the single-use verifier + state and redirects with S256 PKCE", async () => {
    Object.defineProperty(window, "isSecureContext", { value: true, configurable: true });
    const assign = vi.fn();
    vi.stubGlobal("location", { origin: "http://localhost:5173", pathname: "/", assign });

    await beginLogin();

    // the single-use PKCE values are stashed for the later CSRF check + code exchange
    const verifier = sessionStorage.getItem("irp.pkce.verifier");
    const state = sessionStorage.getItem("irp.pkce.state");
    expect(verifier).toMatch(/^[A-Za-z0-9\-_]{43}$/);
    expect(state).toMatch(/^[A-Za-z0-9\-_]{43}$/);

    // the authorize redirect carries the S256 challenge + the SAME state (a plain/omitted method
    // would be a silent PKCE downgrade — this catches it)
    const url = new URL(assign.mock.calls[0][0] as string);
    expect(url.pathname).toBe("/realms/irp-local/protocol/openid-connect/auth");
    const q = url.searchParams;
    expect(q.get("response_type")).toBe("code");
    expect(q.get("client_id")).toBe("irp-frontend");
    expect(q.get("redirect_uri")).toBe("http://localhost:5173/callback");
    expect(q.get("code_challenge_method")).toBe("S256");
    expect(q.get("code_challenge")).toMatch(/^[A-Za-z0-9\-_]{43}$/);
    expect(q.get("state")).toBe(state);
  });

  it("refuses on a non-secure context (clear error, not an opaque crash)", async () => {
    Object.defineProperty(window, "isSecureContext", { value: false, configurable: true });
    await expect(beginLogin()).rejects.toThrow(/secure context/);
    Object.defineProperty(window, "isSecureContext", { value: true, configurable: true });
  });
});

describe("completeLogin (the /callback handler)", () => {
  it("exchanges the code, stores the OidcSession, strips the URL, clears the verifier", async () => {
    sessionStorage.setItem("irp.pkce.state", "xyz");
    sessionStorage.setItem("irp.pkce.verifier", "the-verifier");
    const exp = Math.floor(Date.now() / 1000) + 3600;
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ access_token: fakeJwt("demo-auditor", exp) }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const session = await completeLogin(new URLSearchParams("code=abc&state=xyz"));

    expect(session).toEqual({
      kind: "oidc",
      accessToken: expect.any(String),
      subject: "demo-auditor",
      expiresAt: exp,
    });
    // stored + loadable
    expect(loadSession()).toMatchObject({ kind: "oidc", subject: "demo-auditor" });
    // single-use verifier + state cleared
    expect(sessionStorage.getItem("irp.pkce.verifier")).toBeNull();
    expect(sessionStorage.getItem("irp.pkce.state")).toBeNull();
    // the ?code was stripped from the URL
    expect(window.location.search).toBe("");
    // the token exchange was a POST form-encode to the token endpoint (public client, no secret)
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://kc:8080/realms/irp-local/protocol/openid-connect/token");
    expect(init.method).toBe("POST");
    expect(init.body).toContain("grant_type=authorization_code");
    expect(init.body).toContain("code_verifier=the-verifier");
    expect(init.body).not.toContain("client_secret");
  });

  it("rejects a state mismatch (CSRF) WITHOUT exchanging", async () => {
    sessionStorage.setItem("irp.pkce.state", "xyz");
    sessionStorage.setItem("irp.pkce.verifier", "the-verifier");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(completeLogin(new URLSearchParams("code=abc&state=EVIL"))).rejects.toThrow(
      /state mismatch/,
    );
    expect(fetchMock).not.toHaveBeenCalled();
    // even on failure the single-use values are cleared + the URL stripped
    expect(sessionStorage.getItem("irp.pkce.verifier")).toBeNull();
    expect(window.location.search).toBe("");
  });

  it("rejects a missing authorization code", async () => {
    sessionStorage.setItem("irp.pkce.state", "xyz");
    sessionStorage.setItem("irp.pkce.verifier", "v");
    await expect(completeLogin(new URLSearchParams("state=xyz"))).rejects.toThrow(/missing.*code/);
  });
});
