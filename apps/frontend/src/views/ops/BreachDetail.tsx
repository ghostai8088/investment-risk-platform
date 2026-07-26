import { useState } from "react";
import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { useApiGet } from "../../api/useApiGet";
import { verbatim } from "../../api/format";
import { closeBreach, respondToBreach, reviewBreach } from "../../api/writes";
import type { components } from "../../api/generated/api-types";
import type { Session } from "../../session";
import { Refusal, explain } from "./Refusal";

type BreachOut = components["schemas"]["BreachOut"];
type BreachActionOut = components["schemas"]["BreachActionOut"];
type BreachNotificationOut = components["schemas"]["BreachNotificationOut"];

type Pending = "respond" | "review-accept" | "review-reject" | "close" | null;

/**
 * One breach, end to end: what was measured, how the remediation has proceeded, who was alerted,
 * and the actions available now.
 *
 * Every write sends `expected_seq` taken from the breach's own `seq` (OPS-1 fold H3). That is the
 * optimistic-concurrency precondition: if the operational tick escalates this breach between the
 * read and the submit, the write is refused rather than silently clearing an alarm state that no
 * longer exists. After any successful write we bump `reload`, which re-fetches the breach, the
 * timeline and the alerts (fold H4 — the hook could not otherwise re-request an unchanged path).
 */
export function BreachDetail({ session }: { session: Session }): ReactElement {
  const { breachId = "" } = useParams();
  const [reload, setReload] = useState(0);
  const [pending, setPending] = useState<Pending>(null);
  const [writeError, setWriteError] = useState<ApiError | null>(null);
  const [narrative, setNarrative] = useState("");
  const [evidenceRef, setEvidenceRef] = useState("");

  const breach = useApiGet<BreachOut>(`/breaches/${breachId}`, session, reload);
  const actions = useApiGet<BreachActionOut[]>(`/breaches/${breachId}/actions`, session, reload);
  const alerts = useApiGet<BreachNotificationOut[]>(
    `/breaches/${breachId}/notifications`,
    session,
    reload,
  );

  const b = breach.data;

  async function run(kind: Exclude<Pending, null>, fn: () => Promise<unknown>): Promise<void> {
    setPending(kind);
    setWriteError(null);
    try {
      await fn();
      setNarrative("");
      setEvidenceRef("");
      setReload((n) => n + 1); // refetch breach + timeline + alerts
    } catch (e: unknown) {
      const err = e instanceof ApiError ? e : new ApiError("network", String(e));
      setWriteError(err);
      // Review M-2: a CONFLICT means our `expected_seq` no longer matches the server. Without a
      // refetch the stale token is re-sent on every retry, so the operator is told to "reload"
      // while every button is guaranteed to fail forever. Refetch so the explanation and a fresh
      // token arrive together.
      if (err.kind === "conflict") setReload((n) => n + 1);
    } finally {
      setPending(null);
    }
  }

  if (breach.loading) return <p className="state">Loading breach…</p>;
  if (breach.error) {
    return (
      <p className="state error" role="alert">
        {explain(breach.error, "view this breach")}
      </p>
    );
  }
  if (!b) return <p className="state">No such breach.</p>;

  const busy = pending !== null;

  return (
    <section className="ops-view">
      <header className="ops-header">
        <p className="crumb">
          <Link to="/ops/breaches">← Breach queue</Link>
        </p>
        <h2>
          {verbatim(b.limit_code)} <span className="chip">{verbatim(b.state)}</span>
        </h2>
      </header>

      {/* --- what was measured (the self-describing echo the breach row carries) --- */}
      <dl className="ops-facts">
        <div>
          <dt>Observed</dt>
          <dd className="mono num">{verbatim(b.observed_value)}</dd>
        </div>
        <div>
          <dt>Threshold</dt>
          <dd className="mono num">
            {verbatim(b.threshold_value)} ({verbatim(b.breach_direction)})
          </dd>
        </div>
        <div>
          <dt>Unit</dt>
          <dd>{verbatim(b.threshold_unit)}</dd>
        </div>
        <div>
          <dt>Severity</dt>
          <dd>{verbatim(b.severity)}</dd>
        </div>
        <div>
          <dt>Metric</dt>
          <dd>{verbatim(b.metric_type)}</dd>
        </div>
        <div>
          <dt>Detected</dt>
          <dd>{new Date(b.detected_at).toISOString().replace("T", " ").slice(0, 19)}</dd>
        </div>
        <div>
          <dt>Owner</dt>
          <dd className="mono">{b.assigned_to ? verbatim(b.assigned_to) : "unassigned"}</dd>
        </div>
        <div>
          <dt>Evaluated run</dt>
          <dd className="mono">{verbatim(b.calculation_run_id)}</dd>
        </div>
      </dl>

      {/* --- the actions --- */}
      <div className="ops-actions">
        <h3>Act on this breach</h3>
        <p className="ops-lede">
          The workflow enforces 1L/2L separation: the analyst who files a response may not be the
          manager who reviews or closes it. Refusals below are the controls working, not faults.
        </p>
        {writeError ? <Refusal error={writeError} action="take this action" /> : null}

        <label className="ops-field">
          Narrative
          <textarea
            value={narrative}
            onChange={(e) => setNarrative(e.target.value)}
            maxLength={2000}
            rows={3}
            placeholder="What was done, or why the response is accepted / rejected"
          />
        </label>

        <div className="ops-buttons">
          <button
            type="button"
            disabled={busy || !narrative}
            onClick={() =>
              void run("respond", () =>
                respondToBreach(session, b.id, { narrative, expectedSeq: b.seq }),
              )
            }
          >
            {pending === "respond" ? "Filing…" : "File 1L response"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run("review-accept", () =>
                reviewBreach(session, b.id, {
                  outcome: "ACCEPT",
                  narrative: narrative || undefined,
                  expectedSeq: b.seq,
                }),
              )
            }
          >
            {pending === "review-accept" ? "Accepting…" : "2L accept"}
          </button>
          <button
            type="button"
            // A REJECT without a narrative is refused 422 by contract — require it client-side so
            // the operator is told before the round-trip, not by a validation error after it.
            disabled={busy || !narrative}
            onClick={() =>
              void run("review-reject", () =>
                reviewBreach(session, b.id, {
                  outcome: "REJECT",
                  narrative,
                  expectedSeq: b.seq,
                }),
              )
            }
          >
            {pending === "review-reject" ? "Rejecting…" : "2L reject"}
          </button>
        </div>

        <label className="ops-field">
          Closure evidence reference
          <input
            type="text"
            value={evidenceRef}
            onChange={(e) => setEvidenceRef(e.target.value)}
            maxLength={255}
            placeholder="e.g. ticket://RISK-42"
          />
        </label>
        <div className="ops-buttons">
          <button
            type="button"
            disabled={busy || !evidenceRef}
            onClick={() =>
              void run("close", () =>
                closeBreach(session, b.id, {
                  evidenceRef,
                  narrative: narrative || undefined,
                  expectedSeq: b.seq,
                }),
              )
            }
          >
            {pending === "close" ? "Closing…" : "Close breach"}
          </button>
        </div>
      </div>

      {/* --- the remediation timeline --- */}
      <div className="ops-panel">
        <h3>Remediation timeline</h3>
        {actions.error ? (
          <p className="state error">{explain(actions.error, "view the timeline")}</p>
        ) : null}
        {actions.data && actions.data.length === 0 ? (
          <p className="state">No actions filed yet — this breach is awaiting assignment.</p>
        ) : null}
        {actions.data && actions.data.length > 0 ? (
          <ol className="ops-timeline">
            {actions.data.map((a) => (
              <li key={a.id}>
                <span className="chip">{verbatim(a.action_type)}</span>{" "}
                <strong>
                  {verbatim(a.from_state)} → {verbatim(a.to_state)}
                </strong>{" "}
                <span className="cell-sub">
                  by <span className="mono">{verbatim(a.actor_id)}</span> ({verbatim(a.actor_line)})
                  {a.review_outcome ? ` · ${verbatim(a.review_outcome)}` : ""}
                </span>
                {a.narrative ? <p className="ops-narrative">{verbatim(a.narrative)}</p> : null}
              </li>
            ))}
          </ol>
        ) : null}
      </div>

      {/* --- proof of alert (the NOTIF-1 evidence leg) --- */}
      <div className="ops-panel">
        <h3>Alerts sent</h3>
        <p className="ops-lede">
          Durable evidence that this breach was escalated to a human — the record a supervisor asks
          for when they ask &quot;how do you know the risk officer was told?&quot;
        </p>
        {alerts.error ? (
          <p className="state error">{explain(alerts.error, "view alerts")}</p>
        ) : null}
        {alerts.data && alerts.data.length === 0 ? (
          <p className="state">No alert records for this breach yet.</p>
        ) : null}
        {alerts.data && alerts.data.length > 0 ? (
          <table className="ops-table">
            <thead>
              <tr>
                <th scope="col">Event</th>
                <th scope="col">Recipient</th>
                <th scope="col">Channel</th>
                <th scope="col">Outcome</th>
                <th scope="col">At</th>
              </tr>
            </thead>
            <tbody>
              {alerts.data.map((n) => (
                <tr key={n.id}>
                  <td>{verbatim(n.source_event_type)}</td>
                  <td className="mono">{verbatim(n.recipient_id)}</td>
                  <td>{verbatim(n.channel)}</td>
                  <td>{verbatim(n.outcome)}</td>
                  <td>{new Date(n.notified_at).toISOString().replace("T", " ").slice(0, 19)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </section>
  );
}
