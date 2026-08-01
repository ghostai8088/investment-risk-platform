import { useState } from "react";
import type { ReactElement } from "react";

import { ApiError } from "../../api/client";
import { useApiGet } from "../../api/useApiGet";
import { verbatim } from "../../api/format";
import { approveLimit } from "../../api/writes";
import type { components } from "../../api/generated/api-types";
import type { Session } from "../../session";
import { Refusal, explain } from "./Refusal";

type LimitOut = components["schemas"]["LimitOut"];
type LimitHealthOut = components["schemas"]["LimitHealthOut"];

/** How a limit's row reads, combining its lifecycle status with its evaluation health.
 *
 * The join is deliberately fail-CLOSED (verifier medium fold): `/limits/health` only reports on
 * ACTIVE limits, so a DRAFT or SUSPENDED limit has NO health row. Defaulting an unmatched limit to
 * green would render a suspended limit as healthy — exactly the fail-open dishonesty LIM-1 was
 * built to prevent. A limit that is not in force is shown as NOT IN FORCE, which is neither pass
 * nor fail: nothing is being checked. */
function rowState(
  limit: LimitOut,
  health: LimitHealthOut | undefined,
  healthKnown: boolean,
): string {
  if (limit.status !== "ACTIVE") return "NOT IN FORCE";
  // Review M-3: `limit_health` emits a row for EVERY active limit (NEVER_EVALUABLE when it cannot
  // resolve one), so a missing row while the health read is loading or failed means "we do not
  // know" — NOT "not evaluated". Asserting the latter would state an evaluation fact the UI does
  // not have, on a screen whose whole job is honesty about what has been checked.
  if (!healthKnown) return "UNKNOWN — health unavailable";
  if (!health) return "NOT EVALUATED";
  return health.state;
}

function stateClass(state: string): string {
  if (state === "BREACHED") return "chip chip-hard";
  if (state === "IN_APPETITE") return "chip chip-ok";
  return "chip chip-muted"; // NEVER_EVALUABLE / NOT IN FORCE / NOT EVALUATED — honestly unknown
}

export function LimitHealth({ session }: { session: Session }): ReactElement {
  const [reload, setReload] = useState(0);
  const [approving, setApproving] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<ApiError | null>(null);
  const [approvalRef, setApprovalRef] = useState("");

  const limits = useApiGet<LimitOut[]>("/limits", session, reload);
  const health = useApiGet<LimitHealthOut[]>("/limits/health", session, reload);

  const healthById = new Map((health.data ?? []).map((h) => [h.limit_id, h]));
  const healthKnown = !health.loading && health.error === null;
  const all = limits.data ?? [];
  const drafts = all.filter((l) => l.status === "DRAFT");

  async function approve(limitId: string): Promise<void> {
    setApproving(limitId);
    setWriteError(null);
    try {
      // NO fallback value (review H-3): `approval_ref` is the governed sign-off EVIDENCE and is
      // written verbatim into the immutable LIMIT.APPROVE audit event. The service refuses an empty
      // one on purpose; defaulting it to a placeholder here would neutralize a fail-closed input
      // from the client and fabricate provenance in the ledger. The button is disabled instead.
      await approveLimit(session, limitId, { approvalRef: approvalRef.trim() });
      setApprovalRef("");
      setReload((n) => n + 1);
    } catch (e: unknown) {
      setWriteError(e instanceof ApiError ? e : new ApiError("network", String(e)));
    } finally {
      setApproving(null);
    }
  }

  return (
    <section className="ops-view">
      <header className="ops-header">
        <h2>Limits</h2>
        <p className="ops-lede">
          Every governed limit, its lifecycle status, and — for limits actually in force — whether
          the latest evaluation was within appetite.
        </p>
      </header>

      {limits.error ? (
        <p className="state error" role="alert">
          {explain(limits.error, "view limits")}
        </p>
      ) : null}
      {limits.loading ? <p className="state">Loading limits…</p> : null}

      {/* --- the approval queue: the MG-3 maker-checker gate made visible --- */}
      <div className="ops-panel">
        <h3>Approval queue</h3>
        <p className="ops-lede">
          A DRAFT limit is <strong>not evaluated and cannot breach</strong> — it constrains nothing
          until a second person approves it. The approver may not be one of its makers; that refusal
          is the maker-checker control, and you will see it stated plainly if you are a maker here.
        </p>
        {writeError ? <Refusal error={writeError} action="approve this limit" /> : null}
        {drafts.length === 0 ? (
          <p className="state">Nothing awaiting approval.</p>
        ) : (
          <>
            <label className="ops-field">
              Approval reference
              <input
                type="text"
                value={approvalRef}
                onChange={(e) => setApprovalRef(e.target.value)}
                maxLength={255}
                placeholder="e.g. minutes://RISK-COMMITTEE-2026-07"
                required
              />
              <span className="cell-sub">
                Required — this is written verbatim into the immutable approval record.
              </span>
            </label>
            <table className="ops-table">
              <thead>
                <tr>
                  <th scope="col">Limit</th>
                  <th scope="col">Threshold</th>
                  <th scope="col">Made by</th>
                  <th scope="col" />
                </tr>
              </thead>
              <tbody>
                {drafts.map((l) => (
                  <tr key={l.id}>
                    <th scope="row">
                      {verbatim(l.code)}
                      <span className="cell-sub">{verbatim(l.name)}</span>
                    </th>
                    <td className="mono num">
                      {verbatim(l.threshold_value)} {verbatim(l.threshold_unit)}
                    </td>
                    <td className="mono">{l.created_by ? verbatim(l.created_by) : "—"}</td>
                    <td>
                      <button
                        type="button"
                        disabled={approving !== null || !approvalRef.trim()}
                        onClick={() => void approve(l.id)}
                      >
                        {approving === l.id ? "Approving…" : "Approve"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      {/* --- health across all limits --- */}
      <div className="ops-panel">
        <h3>Limit health</h3>
        {health.error ? (
          <p className="state error" role="alert">
            {explain(health.error, "view limit health")}
          </p>
        ) : null}
        {all.length === 0 && !limits.loading ? (
          <p className="state">No limits are defined in this tenant yet.</p>
        ) : null}
        {all.length > 0 ? (
          <table className="ops-table">
            <thead>
              <tr>
                <th scope="col">Limit</th>
                <th scope="col">Status</th>
                <th scope="col">Threshold</th>
                <th scope="col">Health</th>
                <th scope="col">Latest run</th>
              </tr>
            </thead>
            <tbody>
              {all.map((l) => {
                const h = healthById.get(l.id);
                const state = rowState(l, h, healthKnown);
                return (
                  <tr key={l.id}>
                    <th scope="row">
                      {verbatim(l.code)}
                      <span className="cell-sub">{verbatim(l.metric_type)}</span>
                      {/* Rule 7 + LIM-2 fact 2: `MAX_SHARE_SECTOR_INDUSTRY` alone does not say
                          WHICH taxonomy produced it, and two schemes partition sectors
                          differently. The selector is shown so the number on screen has a
                          determinable meaning. */}
                      {l.dimension_kind ? (
                        <span className="cell-sub">
                          {verbatim(l.dimension_kind)}
                          {l.bucket_code ? ` · ${verbatim(l.bucket_code)}` : ""}
                          {l.scheme_family ? ` · ${verbatim(l.scheme_family)}` : ""}
                        </span>
                      ) : null}
                    </th>
                    <td>{verbatim(l.status)}</td>
                    <td className="mono num">
                      {verbatim(l.threshold_value)} {verbatim(l.threshold_unit)}
                    </td>
                    <td>
                      <span className={stateClass(state)}>{state}</span>
                      {/* ORTHOGONAL signals, rendered ALONGSIDE the verdict rather than replacing
                          it — a limit can be breached AND stale AND drifting at once, and a
                          staleness badge that hid a real breach would be worse than no badge
                          (LIM-2 record 3.5). */}
                      {h?.latest_run_failed ? (
                        <span
                          className="cell-sub"
                          title="The newest run FAILED; this verdict is computed from an older completed one."
                        >
                          stale — newest run failed
                        </span>
                      ) : null}
                      {h?.scheme_drift_from && h?.scheme_drift_to ? (
                        <span
                          className="cell-sub"
                          title={`Authored against ${h.scheme_drift_from}; evaluated against ${h.scheme_drift_to}.`}
                        >
                          scheme version drift
                        </span>
                      ) : null}
                      {h?.refusal_reason ? (
                        <span className="cell-sub" title={h.refusal_reason}>
                          refused — not compared
                        </span>
                      ) : null}
                    </td>
                    <td className="mono">{h?.latest_run_id ? verbatim(h.latest_run_id) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : null}
      </div>
    </section>
  );
}
