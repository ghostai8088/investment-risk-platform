/**
 * The DEV session (FE-1, OD-FE-1-D). This is the backend's documented development header shim
 * (`X-User-Id` / `X-Tenant-Id`, DR-P1A0-3): the identity is UNVERIFIED and this is NOT a
 * security boundary — enforcement (entitlement + RLS) lives server-side. Vocabulary is
 * "session", never "login". `sessionStorage` on purpose: closing the tab drops the identity.
 */

export interface DevSession {
  userId: string;
  tenantId: string;
}

const KEY = "irp.dev.session";

/** Printable ASCII only (review fold): any character above U+00FF makes the browser's header
 * constructor throw BEFORE any network I/O, which then masquerades as "API unreachable" on
 * every request until the session is ended. Ids here are UUIDs/short codes — refuse early. */
export function isValidSessionId(value: string): boolean {
  return value.length > 0 && /^[\x21-\x7e]+$/.test(value);
}

export function loadSession(): DevSession | null {
  const raw = sessionStorage.getItem(KEY);
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      typeof (parsed as DevSession).userId === "string" &&
      typeof (parsed as DevSession).tenantId === "string" &&
      isValidSessionId((parsed as DevSession).userId) &&
      isValidSessionId((parsed as DevSession).tenantId)
    ) {
      return parsed as DevSession;
    }
  } catch {
    // fall through: a corrupt value is treated as no session
  }
  sessionStorage.removeItem(KEY);
  return null;
}

export function saveSession(session: DevSession): void {
  sessionStorage.setItem(KEY, JSON.stringify(session));
}

export function clearSession(): void {
  sessionStorage.removeItem(KEY);
}
