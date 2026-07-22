/**
 * FE-3b (OD-FE-3b-C): the browser auth-code + PKCE login flow, hand-rolled over `fetch` + Web Crypto
 * (OQ-FE-3b-1 = A). `beginLogin()` redirects to the IdP; `completeLogin()` runs on the `/callback`
 * route (validate `state` → strip the code from the URL → exchange → store); `logout()` ends the IdP
 * session. The public client carries NO secret — PKCE protects the code exchange.
 *
 * The FE decodes the token's `sub`/`exp` for the identity chrome + re-auth ONLY — it does NOT verify
 * the signature; the backend (SSO-1) is the verifier.
 */

import { oidcConfig } from "../api/authConfig";
import type { OidcSession } from "../session";
import { clearSession, saveSession } from "../session";
import { codeChallengeS256, randomCodeVerifier, randomState } from "./pkce";

const VERIFIER_KEY = "irp.pkce.verifier";
const STATE_KEY = "irp.pkce.state";

/** Kick the auth-code + PKCE flow: stash the verifier+state, redirect to the IdP's authorize endpoint. */
export async function beginLogin(): Promise<void> {
  // Web Crypto (PKCE) requires a secure context (https or localhost). Fail with a clear message
  // rather than an opaque TypeError if this SPA is ever served over plain HTTP (review LOW).
  if (window.isSecureContext === false) {
    throw new Error("OIDC login requires a secure context (https:// or http://localhost)");
  }
  const { issuer, clientId, redirectUri } = oidcConfig();
  const verifier = randomCodeVerifier();
  const state = randomState();
  const challenge = await codeChallengeS256(verifier);
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  sessionStorage.setItem(STATE_KEY, state);
  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: "openid",
    state,
    code_challenge: challenge,
    code_challenge_method: "S256",
  });
  window.location.assign(`${issuer}/protocol/openid-connect/auth?${params.toString()}`);
}

/** Decode a JWT payload WITHOUT verifying (the backend verifies). Reads `sub` + `exp` only. */
function decodeClaims(token: string): { sub: string; exp: number } {
  const parts = token.split(".");
  if (parts.length < 2) return { sub: "", exp: 0 };
  const json = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
  const claims = JSON.parse(json) as { sub?: unknown; exp?: unknown };
  return {
    sub: typeof claims.sub === "string" ? claims.sub : "",
    exp: typeof claims.exp === "number" ? claims.exp : 0,
  };
}

/**
 * Handle the IdP redirect on `/callback`. Order matters for security: validate `state` (CSRF) and
 * strip the `?code` from the URL BEFORE the exchange, and clear the single-use verifier+state
 * regardless of outcome.
 */
export async function completeLogin(search: URLSearchParams): Promise<OidcSession> {
  const code = search.get("code");
  const returnedState = search.get("state");
  const storedState = sessionStorage.getItem(STATE_KEY);
  const verifier = sessionStorage.getItem(VERIFIER_KEY);

  // Strip the code from the URL synchronously, before any exchange/subresource (referrer hygiene).
  window.history.replaceState(null, "", window.location.pathname);
  // Single-use: the verifier + state never survive one callback.
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);

  if (!code) throw new Error("callback: missing authorization code");
  if (!returnedState || returnedState !== storedState) {
    throw new Error("callback: state mismatch (possible CSRF) — login aborted");
  }
  if (!verifier) throw new Error("callback: missing PKCE verifier — restart the login");

  const { issuer, clientId, redirectUri } = oidcConfig();
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: redirectUri,
    client_id: clientId,
    code_verifier: verifier,
  });
  const resp = await fetch(`${issuer}/protocol/openid-connect/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!resp.ok) throw new Error(`callback: token exchange failed (${String(resp.status)})`);
  const token = (await resp.json()) as { access_token?: unknown };
  if (typeof token.access_token !== "string") {
    throw new Error("callback: token response had no access_token");
  }
  const { sub, exp } = decodeClaims(token.access_token);
  const session: OidcSession = {
    kind: "oidc",
    accessToken: token.access_token,
    subject: sub,
    expiresAt: exp,
  };
  saveSession(session);
  return session;
}

/** End the session locally, then redirect to the IdP's end-session endpoint (a real OIDC logout,
 * not just a `sessionStorage` clear). */
export function logout(): void {
  clearSession();
  const { issuer, clientId, redirectUri } = oidcConfig();
  // Trailing slash so the URI matches the realm's registered `.../*` post-logout pattern (review
  // MED: a bare origin does not match `http://localhost:5173/*` and Keycloak rejects the redirect).
  const params = new URLSearchParams({
    client_id: clientId,
    post_logout_redirect_uri: `${new URL(redirectUri).origin}/`,
  });
  window.location.assign(`${issuer}/protocol/openid-connect/logout?${params.toString()}`);
}
