import type { ReactElement, ReactNode } from "react";

import type { ApiError } from "../api/client";
import type { AsyncState } from "../api/useApiGet";

/** Human message for an error, with graceful entitlement handling (OD-FE-3-E): a 403 is a normal,
 * first-class "you lack this permission" state, never a screen-level failure. */
function errorMessage(error: ApiError, requires?: string): string {
  switch (error.kind) {
    case "forbidden":
      return requires
        ? `You need the “${requires}” permission to view this.`
        : "This identity is not entitled to view this (403).";
    case "unauthorized":
      return "The backend rejected the session headers (401).";
    case "not-found":
      return "Not found, or not visible to this identity.";
    case "no-session":
      return "No active session.";
    default:
      return error.message;
  }
}

/**
 * An async region that renders one of: loading / an error (a 403 degrades to a calm "requires the
 * `<requires>` permission" note, so a missing entitlement never blanks the walk) / an empty state /
 * the data. The whole walk composes these, so partial entitlement is legible instead of broken.
 */
export function Pane<T>({
  state,
  requires,
  empty,
  children,
}: {
  state: AsyncState<T>;
  /** The permission code this region needs — shown if the read 403s (OD-E). */
  requires?: string;
  /** Rendered when the read succeeds but returns no data (default: a neutral note). */
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}): ReactElement {
  if (state.loading) return <p className="state">Loading…</p>;
  if (state.error) {
    const denied = state.error.kind === "forbidden";
    return (
      <p className={denied ? "state denied" : "state error"} role={denied ? "note" : "alert"}>
        {errorMessage(state.error, requires)}
      </p>
    );
  }
  if (state.data === null || (Array.isArray(state.data) && state.data.length === 0)) {
    return <>{empty ?? <p className="state">No data for this book yet.</p>}</>;
  }
  return <>{children(state.data)}</>;
}
