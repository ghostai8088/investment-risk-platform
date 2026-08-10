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
export type UserOut = Schemas["UserOut"];
export type EntitlementRequestOut = Schemas["EntitlementRequestOut"];
export type ScheduleOut = Schemas["ScheduleWriteOut"];
export type ReproductionCheckOut = Schemas["ReproductionCheckOut"];
export type ReportOut = Schemas["ReportOut"];

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

// --- ONBOARD-1b: tenant administration (Users & Roles, SOD-04 four-eyes) ----------------------
// Every entitlement verb returns `EntitlementRequestOut`, and the caller MUST read `status`:
// PENDING means the act has NOT happened yet (a second admin must approve), DIRECT means it did
// (the bootstrap window, flagged). Rendering the outcome is the screen's job — a 200 alone says
// only that the REQUEST was recorded.

export async function createUser(
  session: Session | null,
  input: { externalSubject: string; displayName: string },
): Promise<UserOut> {
  return request<UserOut>("/users", session, "POST", {
    external_subject: input.externalSubject,
    display_name: input.displayName,
  });
}

export async function grantRole(
  session: Session | null,
  userId: string,
  input: { roleId: string; reason?: string },
): Promise<EntitlementRequestOut> {
  return request<EntitlementRequestOut>(`/users/${userId}/roles`, session, "POST", {
    role_id: input.roleId,
    // Optional governed context — sent only when populated (the DTO is extra-forbidding).
    ...(input.reason ? { reason: input.reason } : {}),
  });
}

export async function revokeRole(
  session: Session | null,
  userId: string,
  roleId: string,
): Promise<EntitlementRequestOut> {
  return request<EntitlementRequestOut>(`/users/${userId}/roles/${roleId}`, session, "DELETE");
}

export async function deactivateUser(
  session: Session | null,
  userId: string,
): Promise<EntitlementRequestOut> {
  return request<EntitlementRequestOut>(`/users/${userId}/deactivate`, session, "POST");
}

export async function approveEntitlementRequest(
  session: Session | null,
  requestId: string,
): Promise<EntitlementRequestOut> {
  return request<EntitlementRequestOut>(
    `/entitlement-requests/${requestId}/approve`,
    session,
    "POST",
  );
}

// --- REPRO-2: the schedule write path (OQ-REP2-2) --------------------------------------------
// The verbs that make CTRL-018 startable from a browser. No `expected_seq`: a schedule is a HEAD
// row, not an append-only lifecycle with an interleaving tick, so there is no stale-write hazard
// of the breach kind for the token to close. Pause/resume are idempotent in effect — the service
// refuses an illegal transition and the screen renders that refusal.
//
// PAUSE deserves its own note, because a reader should not have to go to the API to find it: it
// is a ONE-PERSON, reversible switch-off of the platform's only detective control over governed
// -number drift, and the ratified compensating control is VISIBILITY, not a second approver —
// pausing every reproduction schedule turns the Alerting panel RED (`control_switched_off`).

export async function createSchedule(
  session: Session | null,
  input: {
    code: string;
    name: string;
    targetRunType: string;
    environmentId: string;
    anchorDate: string;
    cadenceKind: string;
    intervalDays?: number | null;
  },
): Promise<ScheduleOut> {
  return request<ScheduleOut>("/schedules", session, "POST", {
    code: input.code,
    name: input.name,
    target_run_type: input.targetRunType,
    environment_id: input.environmentId,
    anchor_date: input.anchorDate,
    cadence_kind: input.cadenceKind,
    ...(input.intervalDays ? { interval_days: input.intervalDays } : {}),
  });
}

export async function pauseSchedule(
  session: Session | null,
  scheduleId: string,
): Promise<ScheduleOut> {
  return request<ScheduleOut>(`/schedules/${scheduleId}/pause`, session, "POST");
}

export async function resumeSchedule(
  session: Session | null,
  scheduleId: string,
): Promise<ScheduleOut> {
  return request<ScheduleOut>(`/schedules/${scheduleId}/resume`, session, "POST");
}

// --- RPT-3: report generation from the UI ----------------------------------------------------
// The one write this slice adds. `family_runs` carries ONLY the families the operator checked —
// an unchecked family is absent from the object, never present with a null, because the service
// reads the dict's KEYS as the family set and the DTO forbids unexpected shapes.
//
// No `expected_seq`: a report is an append-only governed act, not a lifecycle transition with an
// interleaving tick, so there is no stale-write hazard for the token to close. Generating twice
// is deliberately TWO reports (RPT-2 carry (d) — a re-generation is a new governed act); the
// screen makes existing reports visible rather than pretending the second is a mistake.
export async function generateReport(
  session: Session | null,
  input: { portfolioId: string; asOfDate: string; familyRuns: Record<string, string> },
): Promise<ReportOut> {
  return request<ReportOut>("/reports", session, "POST", {
    portfolio_id: input.portfolioId,
    as_of_date: input.asOfDate,
    family_runs: input.familyRuns,
  });
}
