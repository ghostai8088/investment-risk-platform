/**
 * The thin typed API client (FE-1, OD-FE-1-G). One fetch wrapper: injects the dev-session
 * headers, maps HTTP failures to typed errors, and parses JSON. READ-ONLY — this module
 * deliberately exposes no way to make a non-GET request.
 */

import type { DevSession } from "../session";

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

export async function apiGet<T>(path: string, session: DevSession | null): Promise<T> {
  if (!session) {
    throw new ApiError("no-session", "no dev session — start one to make requests");
  }
  let response: Response;
  try {
    response = await fetch(path, {
      method: "GET",
      headers: {
        "X-User-Id": session.userId,
        "X-Tenant-Id": session.tenantId,
      },
    });
  } catch {
    throw new ApiError("network", "the API is unreachable (is the backend running?)");
  }
  if (!response.ok) {
    throw new ApiError(kindFor(response.status), `request failed (${String(response.status)})`);
  }
  return (await response.json()) as T;
}
