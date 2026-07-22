/**
 * FE-3b (OD-FE-3b-C): hand-rolled PKCE helpers over the Web Crypto API — ZERO runtime dependency
 * (OQ-FE-3b-1 = A, honouring OD-FE-1-F). `crypto.getRandomValues` and `crypto.subtle` are baseline
 * in every browser this SPA targets; both require a secure context (`https://` or `http://localhost`,
 * which the dev server and any real deploy satisfy).
 */

/** base64url (RFC 7636 §A): base64 with `+/`→`-_` and no `=` padding. */
export function base64UrlEncode(bytes: Uint8Array): string {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** A cryptographically-random PKCE `code_verifier`: 32 random bytes → 43-char base64url. */
export function randomCodeVerifier(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

/** A random opaque `state` (CSRF token) — same generator as the verifier. */
export function randomState(): string {
  return randomCodeVerifier();
}

/** The S256 `code_challenge` for a verifier: `base64url(SHA-256(verifier))`. */
export async function codeChallengeS256(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64UrlEncode(new Uint8Array(digest));
}
