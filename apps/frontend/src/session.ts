/**
 * The client session (FE-1 / FE-3b). A discriminated union over the two identity mechanisms:
 *
 * - `DevSession` (FE-1, OD-FE-1-D) — the backend's development header shim (`X-User-Id` /
 *   `X-Tenant-Id`, DR-P1A0-3): identity is UNVERIFIED, NOT a security boundary (enforcement lives
 *   server-side). The `DevBanner` says so. Used only when `VITE_AUTH_MODE=dev_header`.
 * - `OidcSession` (FE-3b, OD-FE-3b-B) — a VERIFIED Bearer session from the browser auth-code + PKCE
 *   login. `accessToken` goes on the `Authorization` header; `subject` (the decoded `sub`) is for
 *   the identity chrome ONLY — never the raw token; `expiresAt` (the token `exp`, epoch seconds)
 *   drives re-auth. Used when `VITE_AUTH_MODE=oidc`.
 *
 * `sessionStorage` on purpose: closing the tab drops the identity.
 */

export interface DevSession {
  kind: "dev";
  userId: string;
  tenantId: string;
}

export interface OidcSession {
  kind: "oidc";
  accessToken: string;
  subject: string;
  expiresAt: number;
}

export type Session = DevSession | OidcSession;

const KEY = "irp.session";

/** Printable ASCII only (review fold): any character above U+00FF makes the browser's header
 * constructor throw BEFORE any network I/O, which then masquerades as "API unreachable" on
 * every request until the session is ended. Dev ids are UUIDs/short codes; a JWT is base64url —
 * both are within \x21-\x7e, so this guards the wire-header inputs of BOTH arms. */
export function isValidHeaderValue(value: string): boolean {
  return value.length > 0 && /^[\x21-\x7e]+$/.test(value);
}

export function loadSession(): Session | null {
  const raw = sessionStorage.getItem(KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (
      parsed.kind === "dev" &&
      typeof parsed.userId === "string" &&
      typeof parsed.tenantId === "string" &&
      isValidHeaderValue(parsed.userId) &&
      isValidHeaderValue(parsed.tenantId)
    ) {
      return { kind: "dev", userId: parsed.userId, tenantId: parsed.tenantId };
    }
    if (
      parsed.kind === "oidc" &&
      typeof parsed.accessToken === "string" &&
      isValidHeaderValue(parsed.accessToken) &&
      typeof parsed.subject === "string" &&
      typeof parsed.expiresAt === "number" &&
      Date.now() / 1000 < parsed.expiresAt // an expired token is dropped ⇒ re-auth
    ) {
      return {
        kind: "oidc",
        accessToken: parsed.accessToken,
        subject: parsed.subject,
        expiresAt: parsed.expiresAt,
      };
    }
  } catch {
    // fall through: a corrupt (or legacy-shaped) value is treated as no session
  }
  sessionStorage.removeItem(KEY);
  return null;
}

export function saveSession(session: Session): void {
  sessionStorage.setItem(KEY, JSON.stringify(session));
}

export function clearSession(): void {
  sessionStorage.removeItem(KEY);
}
