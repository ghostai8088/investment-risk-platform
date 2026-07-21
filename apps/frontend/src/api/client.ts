/**
 * The thin typed API client (FE-1, OD-FE-1-G; FE-3b OD-FE-3b-B). One fetch wrapper: injects the
 * session's identity — the dev-header shim OR a verified `Authorization: Bearer` — maps HTTP
 * failures to typed errors, and parses JSON. READ-ONLY — this module deliberately exposes no way
 * to make a non-GET request (the `method: "GET"` below is the fence; the Bearer header is still a
 * read).
 */

import type { Session } from "../session";

export type ApiErrorKind =
  | "no-session"
  | "unauthorized"
  | "forbidden"
  | "not-found"
  | "invalid"
  | "server"
  | "network";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;

  constructor(kind: ApiErrorKind, message: string) {
    super(message);
    this.kind = kind;
  }
}

function kindFor(status: number): ApiErrorKind {
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not-found";
  if (status === 422) return "invalid";
  return "server";
}

export async function apiGet<T>(path: string, session: Session | null): Promise<T> {
  if (!session) {
    throw new ApiError("no-session", "no session — sign in to make requests");
  }
  // The identity injection is the ONLY per-arm difference; `method: "GET"` stays hard-coded (the
  // read-only fence is about the method, not the header — a Bearer GET is still a read).
  const headers: Record<string, string> =
    session.kind === "oidc"
      ? { Authorization: `Bearer ${session.accessToken}` }
      : { "X-User-Id": session.userId, "X-Tenant-Id": session.tenantId };
  let response: Response;
  try {
    response = await fetch(path, { method: "GET", headers });
  } catch {
    throw new ApiError("network", "the API is unreachable (is the backend running?)");
  }
  if (!response.ok) {
    throw new ApiError(kindFor(response.status), `request failed (${String(response.status)})`);
  }
  return (await response.json()) as T;
}
