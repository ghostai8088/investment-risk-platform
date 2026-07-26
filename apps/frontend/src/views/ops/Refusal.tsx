import type { ReactElement } from "react";

import { ApiError } from "../../api/client";
import { classifyRefusal } from "../../api/writes";

/**
 * Renders a governed REFUSAL in plain language (OPS-1, OQ-3=A).
 *
 * This component is the point of the operations UI, not an error-handling afterthought. The
 * platform's controls — 1L/2L separation of duties, the maker-checker approval gate, the
 * optimistic-concurrency precondition — are invisible until something is refused. So a refusal is
 * rendered as an EXPLANATION that names the control and says what to do next, never as a raw status
 * code or a generic "something went wrong".
 *
 * The discrimination is deliberate: three unrelated refusals arrive as HTTP 409 and demand opposite
 * remedies (a different person / reload and retry / neither). Classifying on status alone would let
 * the UI confidently tell an operator "you are not allowed to do this" when the truth is "the tick
 * escalated this breach while you were reading it" — see `writes.ts`.
 */
export function Refusal({ error, action }: { error: ApiError; action: string }): ReactElement {
  return (
    <p className="state error" role="alert">
      {explain(error, action)}
    </p>
  );
}

export function explain(error: ApiError, action: string): string {
  switch (error.kind) {
    case "forbidden":
      // The 403 body carries no permission code, so the UI names the requirement from the action
      // it attempted — the honest phrasing given F3 (the FE has no permission knowledge at all).
      return `You are not entitled to ${action}. This is enforced by the server: your roles do not grant the required permission. Ask a role administrator, or have someone with that role act instead.`;
    case "conflict":
      switch (classifyRefusal(error.detail)) {
        case "separation-of-duties":
          return `${error.detail}. This is the separation-of-duties control working as intended, not an obstacle: the person who acted at the earlier step may not also ratify it. Someone else must ${action}.`;
        case "stale":
          return `This record changed while you were reading it — very often the operational tick escalating it underneath you. Nothing was written. Reload to see the current state, then act again.`;
        case "illegal-transition":
          return `That step is not legal from the current state: ${error.detail}. Reload to see where this record actually is in its lifecycle.`;
        default:
          return `Refused (conflict): ${error.detail}`;
      }
    case "invalid":
      return `The request was rejected as invalid: ${error.detail}`;
    case "unavailable":
      // A deadlock victim is RETRYABLE. Calling it a platform failure would be a lie that trains
      // operators to escalate a transient, self-healing condition.
      return `The platform was briefly busy (transient lock contention) and did not apply the change. This is expected under concurrent activity — retry in a moment.`;
    case "unauthorized":
      return `Your session was rejected (401). Sign in again.`;
    case "not-found":
      return `That record is not visible in your tenant.`;
    case "no-session":
      return `No active session.`;
    case "network":
      return `The API is unreachable. ${error.message}`;
    default:
      return `The request failed: ${error.message}`;
  }
}
