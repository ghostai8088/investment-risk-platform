/**
 * The FRONTEND WRITE SURFACE (OPS-1, OQ-2=A) — the platform's first, and deliberately its only.
 *
 * Every mutating call the SPA can make lives in this one file so the write surface is auditable at
 * a glance. Identity injection and error mapping are NOT reimplemented here: they come from
 * `client.ts`'s shared `request()` (the SSO-1 lesson — a second copy of identity handling is a copy
 * that drifts).
 *
 * ## Refusals are part of the contract, not exceptions to it
 *
 * The governed backend refuses on purpose, and the operations UI exists partly to SHOW those
 * refusals. Three of them arrive as HTTP 409 with different meanings and OPPOSITE remedies, so
 * `classifyRefusal` discriminates on the server's `detail` text, never on the status alone:
 *
 *   - **separation of duties** — you may not review/close a breach you responded to, and an
 *     approver may not be a maker of the limit. The remedy is *a different person*, never a retry.
 *   - **stale `expected_seq`** — the timeline moved while you were reading it (very often the
 *     operational tick escalating underneath you). The remedy is *reload and retry*.
 *   - **illegal transition** — the verb is not legal from the current state. The remedy is neither.
 *
 * Backing the string match: `BreachStaleSeqError` and `BreachSodError` carry their own API
 * error-map keys with distinct details (OPS-1 fold H2 added the former; before it, stale-seq and
 * illegal-transition were wire-identical and the UI could only guess). `refusal-contract.test.ts`
 * pins these strings against the committed OpenAPI so a backend reword cannot silently degrade the
 * UI to a generic "conflict".
 */

import { request } from "./client";
import type { Session } from "../session";
import type { components } from "./generated/api-types";

type Schemas = components["schemas"];
export type BreachOut = Schemas["BreachOut"];
export type LimitOut = Schemas["LimitOut"];

/** What a 409 actually meant, and therefore what to tell the operator to do. */
export type RefusalKind = "separation-of-duties" | "stale" | "illegal-transition" | "other";

/** The substrings the backend's refusal details are pinned to (see `refusal-contract.test.ts`). */
const SOD_MARKER = "separation of duties";
const STALE_MARKER = "reload and retry";

export function classifyRefusal(detail: string): RefusalKind {
  const text = detail.toLowerCase();
  if (text.includes(SOD_MARKER)) return "separation-of-duties";
  if (text.includes(STALE_MARKER)) return "stale";
  if (text.includes("illegal transition")) return "illegal-transition";
  return "other";
}

// --- the breach lifecycle verbs -------------------------------------------------------------
// `expected_seq` is REQUIRED by these wrappers even though the API defaults it to null, because
// the null default is the fail-OPEN path API-2b introduced the token to close: without it a
// gateway-retried write can land after an interleaved tick ESCALATE and silently clear the alarm
// state. Callers get the token free from `BreachOut.seq` (OPS-1 fold H3).

export async function respondToBreach(
  session: Session | null,
  breachId: string,
  input: { narrative: string; expectedSeq: number },
): Promise<BreachOut> {
  return request<BreachOut>(`/breaches/${breachId}/respond`, session, "POST", {
    narrative: input.narrative,
    expected_seq: input.expectedSeq,
  });
}

export async function reviewBreach(
  session: Session | null,
  breachId: string,
  input: { outcome: "ACCEPT" | "REJECT"; narrative?: string; expectedSeq: number },
): Promise<BreachOut> {
  return request<BreachOut>(`/breaches/${breachId}/review`, session, "POST", {
    outcome: input.outcome,
    // A REJECT without a narrative is a 422 by contract — send the key only when populated so an
    // ACCEPT body stays minimal (the DTOs are extra="forbid").
    ...(input.narrative ? { narrative: input.narrative } : {}),
    expected_seq: input.expectedSeq,
  });
}

export async function closeBreach(
  session: Session | null,
  breachId: string,
  input: { evidenceRef: string; narrative?: string; expectedSeq: number },
): Promise<BreachOut> {
  return request<BreachOut>(`/breaches/${breachId}/close`, session, "POST", {
    evidence_ref: input.evidenceRef,
    ...(input.narrative ? { narrative: input.narrative } : {}),
    expected_seq: input.expectedSeq,
  });
}

// --- the limit maker-checker gate -----------------------------------------------------------

export async function approveLimit(
  session: Session | null,
  limitId: string,
  input: { approvalRef: string },
): Promise<LimitOut> {
  return request<LimitOut>(`/limits/${limitId}/approve`, session, "POST", {
    approval_ref: input.approvalRef,
  });
}
