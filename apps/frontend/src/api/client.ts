/**
 * The thin typed API client (FE-1, OD-FE-1-G; FE-3b OD-FE-3b-B; OPS-1 OQ-2=A).
 *
 * One request core: injects the session's identity — the dev-header shim OR a verified
 * `Authorization: Bearer` — maps HTTP failures to typed errors, and parses JSON.
 *
 * **The read/write split (OPS-1).** Through Wave 12 slice 3 this module was READ-ONLY, and that was
 * enforced by hard-coding `method: "GET"` with no way to pass another verb ("the fence"). OPS-1
 * introduces the platform's first frontend write path (the breach lifecycle + limit approval), so
 * the guarantee is now expressed as a SEPARATION rather than an absence:
 *
 *   - this module exports `apiGet` and remains the ONLY module used by read paths;
 *   - every mutating call lives in `./writes` — one small, auditable surface;
 *   - both share `request()` below, so identity injection has exactly ONE implementation. That
 *     matters more than the old fence did: the SSO-1 lesson is that identity handling duplicated
 *     into a second place is identity handling that silently drifts.
 *
 * `request` is intentionally NOT exported beyond this package's write sibling.
 */

import type { Session } from "../session";

export type ApiErrorKind =
  | "no-session"
  | "unauthorized"
  | "forbidden"
  | "not-found"
  | "invalid"
  | "conflict"
  | "unavailable"
  | "server"
  | "network";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  /** The HTTP status, when the failure came from a response (0 for transport/no-session). */
  readonly status: number;
  /** The server's `detail`, flattened to text. Load-bearing for OPS-1: several distinct refusals
   * share status 409, so the UI discriminates on this string, never on the status alone. */
  readonly detail: string;

  constructor(kind: ApiErrorKind, message: string, status = 0, detail = "") {
    super(message);
    this.kind = kind;
    this.status = status;
    this.detail = detail;
  }
}

function kindFor(status: number): ApiErrorKind {
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not-found";
  if (status === 409) return "conflict";
  if (status === 422) return "invalid";
  if (status === 503) return "unavailable"; // deadlock victim — RETRYABLE, not a platform failure
  return "server";
}

/** FastAPI returns `detail` as a string for HTTPException but as a ValidationError[] for a 422
 * body-validation failure. Rendering the latter directly prints "[object Object]" — on precisely
 * the refusal screens OPS-1 exists to make legible (verifier medium fold). */
function flattenDetail(body: unknown): string {
  if (body === null || typeof body !== "object") return "";
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item === null || typeof item !== "object") return String(item);
        const { loc, msg } = item as { loc?: unknown; msg?: unknown };
        const field = Array.isArray(loc) ? loc.filter((p) => p !== "body").join(".") : "";
        return field ? `${field}: ${String(msg ?? "")}` : String(msg ?? "");
      })
      .filter(Boolean)
      .join("; ");
  }
  return "";
}

function identityHeaders(session: Session): Record<string, string> {
  return session.kind === "oidc"
    ? { Authorization: `Bearer ${session.accessToken}` }
    : { "X-User-Id": session.userId, "X-Tenant-Id": session.tenantId };
}

/** The shared core. `body === undefined` means no request body (a read). */
export async function request<T>(
  path: string,
  session: Session | null,
  method: "GET" | "POST",
  body?: unknown,
): Promise<T> {
  if (!session) {
    throw new ApiError("no-session", "no session — sign in to make requests");
  }
  const headers: Record<string, string> = identityHeaders(session);
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    throw new ApiError("network", "the API is unreachable (is the backend running?)");
  }

  if (!response.ok) {
    // Read the body for `detail` BEFORE throwing: the UI cannot explain a refusal it never saw.
    let detail = "";
    try {
      detail = flattenDetail(await response.json());
    } catch {
      detail = ""; // a non-JSON error body (e.g. a proxy's HTML) — the status still classifies it
    }
    throw new ApiError(
      kindFor(response.status),
      detail || `request failed (${String(response.status)})`,
      response.status,
      detail,
    );
  }
  // Every endpoint on this API returns a JSON body (the write verbs return the updated resource).
  // The parse is guarded (OPS-H1 H1-10 / OPS-1 L-9): a 200 with a NON-JSON body — a proxy or SPA
  // fallback serving HTML with a happy status — previously threw a bare SyntaxError that callers
  // wrapped as "network / the API is unreachable", sending an operator to check a backend that
  // answered. It is a server-shape problem and says so.
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(
      "server",
      "the API returned a 200 with a non-JSON body (a proxy or fallback page?)",
      response.status,
    );
  }
}

export async function apiGet<T>(path: string, session: Session | null): Promise<T> {
  return request<T>(path, session, "GET");
}
