import type { ReactElement } from "react";

import { useApiGet } from "../../api/useApiGet";
import type { components } from "../../api/generated/api-types";
import type { Session } from "../../session";
import { explain } from "./Refusal";

type AlarmHealthOut = components["schemas"]["AlarmHealthOut"];

/**
 * Alerting (ALERT-1, OQ-ALR-6) — is the reproduction alarm channel actually working?
 *
 * The platform's nightly reproduction sweep is a DETECTIVE control: it re-runs governed
 * calculations against their own pinned inputs and pages a reviewer when the numbers no longer
 * reproduce. Everything about that machinery was invisible until this screen — it could be broken,
 * degraded, bounded, silenced, or simply STOPPED, and the only way to find out was to read audit
 * rows by hand.
 *
 * **Every number here is recomputed from source on each read.** None of it is a stored status
 * field, because a stored one can be stale in exactly the moment it matters (the LIM-1 rule: a
 * fail-open control's health surface must recompute, never infer from an evidence row's presence).
 *
 * **This surface is PULL-only, and that is a recorded limitation rather than an oversight.** A red
 * field here pages nobody; somebody has to look. The regress stops at the operator's eyes — and a
 * broken health route shows an error rather than a false green, which is what makes pull-only
 * acceptable for now.
 */

/** One row of the health table: what it is, what it means, and what to DO about it at 02:00. */
type Signal = {
  label: string;
  value: string;
  tone: "red" | "amber" | "info";
  bad: boolean;
  meaning: string;
  action: string;
};

function signals(h: AlarmHealthOut): Signal[] {
  return [
    {
      label: "Sweep overdue",
      value: h.sweep_overdue ? "YES" : "no",
      tone: "red",
      bad: h.sweep_overdue,
      meaning:
        "A reproduction schedule exists but has not produced a run for more than two of its own cadence periods. The control may not be running at all.",
      action: "Check the worker process and the schedule's status.",
    },
    {
      label: "Lost alarms",
      value: String(h.lost_verdicts),
      tone: "red",
      bad: h.lost_verdicts > 0,
      meaning:
        "A sweep computed an alarming verdict and could not record it, so nobody was ever told. The judgement was made and did not survive the write.",
      action: "Open the FAILED sweep in the run ledger and read its reason first.",
    },
    {
      label: "Failed sweeps",
      value: String(h.failed_sweeps),
      tone: "red",
      bad: h.failed_sweeps > 0,
      meaning:
        "Sweeps in the last 7 days that failed for a real reason — a family that could not be checked, or a verdict that could not be written.",
      action: "Read the run ledger for the failing families.",
    },
    {
      label: "Unreadable delivery rows",
      value: String(h.unreadable_rows),
      tone: "red",
      bad: h.unreadable_rows > 0,
      meaning:
        "Delivery evidence for a verdict still awaiting an alarm cannot be parsed, so the platform cannot tell whether that alarm was delivered. It stays queued deliberately.",
      action: "Treat the affected verdicts as un-delivered and check them by hand.",
    },
    {
      label: "Channel dead",
      value: h.dead_channel ? "YES" : "no",
      tone: "red",
      bad: h.dead_channel,
      meaning:
        "Alarms hit their retry ceiling in the last 7 days and NOT ONE delivery succeeded in that time. This is not a bounded retry working; it is nobody being told anything.",
      action: "Check the notification sink and the reviewer role assignments.",
    },
    {
      label: "Control switched off",
      value: h.control_switched_off ? "YES" : "no",
      tone: "red",
      bad: h.control_switched_off,
      meaning:
        "This tenant configured reproduction schedules and every one of them is now paused. Pausing is a one-person, reversible act — this row is the ratified compensating visibility (REPRO-2): a switched-off detective control must never read as a quiet night.",
      action:
        "Resume a schedule, or confirm the pause was intended — the SCHEDULE.UPDATE audit rows say who paused it and when.",
    },
    {
      label: "Silenced by the retry bound",
      value: String(h.exhausted_verdicts),
      tone: "amber",
      bad: h.exhausted_verdicts > 0,
      meaning:
        "Verdicts whose delivery attempts were exhausted without ever concluding. The bound is deliberate — unbounded retry wrote hundreds of audit rows a day — but these divergences were never acknowledged by anyone.",
      action: "Review these verdicts directly; no further alarm will be raised for them.",
    },
    {
      label: "Failing deliveries",
      value: String(h.undeliverable_attempts),
      tone: "amber",
      bad: h.undeliverable_attempts > 0,
      meaning:
        "Delivery attempts recorded as failed for verdicts still queued or silenced. Retries in flight are the system working; a number that keeps climbing is not.",
      action: "If this is climbing, check the sink before the bound retires the verdicts.",
    },
    {
      label: "Awaiting delivery",
      value: String(h.queued),
      tone: "info",
      bad: false,
      meaning:
        "Alarming verdicts still owed a delivery attempt. A non-zero queue between the sweep and the alarm phase is normal.",
      action: "No action — this is the channel working.",
    },
    {
      label: "Empty-tenant sweeps",
      value: String(h.nothing_to_reproduce),
      tone: "info",
      bad: false,
      meaning:
        "Sweeps that failed only because there was nothing to reproduce. A tenant with no completed governed runs fails its nightly sweep by design — a sweep with zero verdicts proves nothing and is not recorded as a pass.",
      action: "No action — this is expected on a quiet tenant.",
    },
    {
      label: "Paused schedules",
      value: String(h.paused_schedules),
      tone: "info",
      bad: false,
      meaning:
        "Reproduction schedules that exist but are paused — a decision somebody made. Informational only while at least one schedule is still running; ALL of them paused is the red 'Control switched off' signal above.",
      action: "No action unless the pause was not intended.",
    },
  ];
}

export function Alerting({ session }: { session: Session }): ReactElement {
  const health = useApiGet<AlarmHealthOut>("/reproduction/alarm-health", session);
  const data = health.data;

  return (
    <section className="ops-view">
      <header className="ops-header">
        <h2>Alerting</h2>
        <p className="ops-lede">
          Whether the reproduction alarm channel is working — the control that re-runs governed
          calculations against their own pinned inputs and pages a reviewer when they no longer
          reproduce. Every figure is recomputed on this read; none of it is a stored status.
        </p>
      </header>

      {health.error ? (
        <p className="state error" role="alert">
          {explain(health.error, "view alarm-channel health")}
        </p>
      ) : null}
      {health.loading ? <p className="state">Loading channel health…</p> : null}

      {data ? (
        <>
          <div className="ops-panel">
            <h3>
              Channel status:{" "}
              <span className={data.healthy ? "chip chip-ok" : "chip chip-hard"}>
                {data.healthy ? "HEALTHY" : "NOT HEALTHY"}
              </span>
            </h3>
            <p className="ops-lede">
              {data.control_switched_off
                ? "Reproduction schedules exist for this tenant and every one of them is paused — the detective control is switched off. This is not a set-up gap; somebody turned it off."
                : data.no_schedule
                  ? "No reproduction schedule is active for this tenant, so no sweep will run. That is a gap in what has been set up, not a fault in the channel."
                  : data.healthy
                    ? "The sweep is running and alarms are getting through."
                    : "At least one red signal below needs attention."}
            </p>
            <dl className="ops-facts">
              <dt>Last completed sweep</dt>
              <dd className="mono">{data.last_terminal_sweep_at ?? "never"}</dd>
            </dl>
          </div>

          <div className="ops-panel">
            <h3>Signals</h3>
            <table className="ops-table">
              <thead>
                <tr>
                  <th scope="col">Signal</th>
                  <th scope="col">Value</th>
                  <th scope="col">What it means, and what to do</th>
                </tr>
              </thead>
              <tbody>
                {signals(data).map((s) => (
                  <tr key={s.label}>
                    <th scope="row">{s.label}</th>
                    <td>
                      <span
                        className={
                          s.bad
                            ? s.tone === "red"
                              ? "chip chip-hard"
                              : "chip chip-muted"
                            : "chip chip-ok"
                        }
                      >
                        {s.value}
                      </span>
                    </td>
                    <td>
                      {s.meaning}
                      <span className="cell-sub">{s.action}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="ops-panel">
            <p className="ops-lede">
              This screen does not page anyone. A red signal here is seen only when somebody looks
              at it — a limitation recorded deliberately rather than left to be discovered.
            </p>
          </div>
        </>
      ) : null}
    </section>
  );
}
