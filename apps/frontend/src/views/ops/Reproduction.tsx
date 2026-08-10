import { type FormEvent, type ReactElement, useCallback, useState } from "react";

import { ApiError } from "../../api/client";
import { useApiGet } from "../../api/useApiGet";
import type { components } from "../../api/generated/api-types";
import {
  createSchedule,
  pauseSchedule,
  type ReproductionCheckOut,
  resumeSchedule,
  type ScheduleOut,
} from "../../api/writes";
import type { Session } from "../../session";
import { explain } from "./Refusal";

type ScheduleListOut = components["schemas"]["ScheduleListOut"];
type ScheduledRunListOut = components["schemas"]["ScheduledRunListOut"];

/**
 * Reproduction (REPRO-2, OQ-REP2-6) — the detective control, operable from a browser.
 *
 * CTRL-018 re-runs historical governed calculations against their own pinned inputs and says
 * whether the numbers came back the same. Until this screen the control could only be STARTED by
 * a proof harness or a demo script writing a schedule row directly, and its verdicts could only be
 * read at database grade. Three things are here because an operator needs all three to act:
 *
 * 1. **the schedules** — including creating one, which is what "startable" means;
 * 2. **the fired-tick ledger** (`GET /schedules/runs`, shipped at SCH-2 and unconsumed until now
 *    — a read surface nobody reads is a claim nobody checks);
 * 3. **the verdicts**, where DIVERGED is loud and UNREPRODUCIBLE is honest about what it withholds.
 *
 * **Why pausing is offered at all, given what it does.** Pausing every reproduction schedule
 * switches the control off, one person, no second approver. That was adjudicated rather than waved
 * through: the compensating control is visibility, not friction — the Alerting panel reads RED
 * (`control_switched_off`) for exactly this state, and this screen says so at the point of the
 * click rather than leaving the operator to discover it.
 */

/** The verdict's tone. DIVERGED is the one that means the platform's promise broke. */
function verdictTone(verdict: string): string {
  if (verdict === "DIVERGED") return "chip chip-hard";
  if (verdict === "UNREPRODUCIBLE") return "chip chip-muted";
  return "chip chip-ok";
}

export function Reproduction({ session }: { session: Session }): ReactElement {
  const [nonce, setNonce] = useState(0);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [code, setCode] = useState("nightly-reproduction");
  const [name, setName] = useState("Nightly reproduction sweep");

  const schedules = useApiGet<ScheduleListOut>(`/schedules?_=${nonce}`, session);
  const runs = useApiGet<ScheduledRunListOut>(`/schedules/runs?limit=20&_=${nonce}`, session);
  const checks = useApiGet<ReproductionCheckOut[]>(
    `/reproduction/checks?limit=50&_=${nonce}`,
    session,
  );

  const items = schedules.data?.items ?? [];
  const reproductionSchedules = items.filter((s) => s.target_run_type === "REPRODUCTION");
  const activeCount = reproductionSchedules.filter((s) => s.status === "ACTIVE").length;

  const act = useCallback(async (fn: () => Promise<ScheduleOut>) => {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
      setNonce((n) => n + 1);
    } catch (err) {
      // Narrowed the same way every other write view does it: `explain` renders a governed
      // refusal in plain language, and a non-ApiError throw (a network drop) must not lose that
      // treatment by arriving as a bare string.
      setActionError(
        explain(
          err instanceof ApiError ? err : new ApiError("network", String(err)),
          "change this schedule",
        ),
      );
    } finally {
      setBusy(false);
    }
  }, []);

  const onCreate = useCallback(
    (event: FormEvent) => {
      event.preventDefault();
      void act(() =>
        createSchedule(session, {
          code,
          name,
          targetRunType: "REPRODUCTION",
          environmentId: "prod",
          anchorDate: new Date().toISOString().slice(0, 10),
          cadenceKind: "INTERVAL",
          intervalDays: 1,
        }),
      );
    },
    [act, session, code, name],
  );

  return (
    <section className="ops-view">
      <header className="ops-header">
        <h2>Reproduction</h2>
        <p className="ops-lede">
          The nightly check that re-runs governed calculations against their own pinned inputs and
          reports whether they still produce the same numbers. A DIVERGED verdict means a stored
          governed value no longer reproduces — that is the platform&rsquo;s promise breaking, not a
          system outage.
        </p>
      </header>

      {actionError ? (
        <p className="state error" role="alert">
          {actionError}
        </p>
      ) : null}

      <div className="ops-panel">
        <h3>Schedules</h3>
        {schedules.error ? (
          <p className="state error" role="alert">
            {explain(schedules.error, "view schedules")}
          </p>
        ) : null}
        {schedules.loading ? <p className="state">Loading schedules&hellip;</p> : null}

        {schedules.data && reproductionSchedules.length === 0 ? (
          <p className="ops-lede">
            No reproduction schedule exists for this tenant, so the control is not running. It makes
            no claim about your numbers until one does.
          </p>
        ) : null}

        {reproductionSchedules.length > 0 && activeCount === 0 ? (
          <p className="state error" role="alert">
            Every reproduction schedule here is paused — the detective control is switched OFF, and
            the Alerting panel reads NOT HEALTHY for exactly this reason. Resume one to turn it back
            on.
          </p>
        ) : null}

        {reproductionSchedules.length > 0 ? (
          <table className="ops-table">
            <thead>
              <tr>
                <th scope="col">Code</th>
                <th scope="col">Cadence</th>
                <th scope="col">Status</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {reproductionSchedules.map((s) => (
                <tr key={s.id}>
                  <th scope="row">{s.code}</th>
                  <td>
                    {s.cadence_kind}
                    {s.interval_days ? ` / ${s.interval_days}d` : ""}
                  </td>
                  <td>
                    <span className={s.status === "ACTIVE" ? "chip chip-ok" : "chip chip-muted"}>
                      {s.status}
                    </span>
                  </td>
                  <td>
                    {s.status === "ACTIVE" ? (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void act(() => pauseSchedule(session, s.id))}
                      >
                        Pause
                      </button>
                    ) : (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void act(() => resumeSchedule(session, s.id))}
                      >
                        Resume
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}

        {activeCount >= 1 ? (
          <p className="ops-lede">
            A second active reproduction schedule would sweep the same families twice a night and
            double the verdict rows without checking anything new.
          </p>
        ) : null}

        <form onSubmit={onCreate} className="ops-form">
          <h4>Start the control</h4>
          <label htmlFor="repro-code">Code</label>
          <input id="repro-code" value={code} onChange={(e) => setCode(e.target.value)} required />
          <label htmlFor="repro-name">Name</label>
          <input id="repro-name" value={name} onChange={(e) => setName(e.target.value)} required />
          <button type="submit" disabled={busy}>
            Create daily reproduction schedule
          </button>
        </form>
      </div>

      <div className="ops-panel">
        <h3>Recent verdicts</h3>
        {checks.error ? (
          <p className="state error" role="alert">
            {explain(checks.error, "view reproduction verdicts")}
          </p>
        ) : null}
        {checks.data && checks.data.length === 0 ? (
          <p className="ops-lede">
            No verdicts in the window. That is not an all-clear: it means the sweep has not recorded
            a judgement here yet.
          </p>
        ) : null}
        {checks.data && checks.data.length > 0 ? (
          <table className="ops-table">
            <thead>
              <tr>
                <th scope="col">Family</th>
                <th scope="col">Verdict</th>
                <th scope="col">Rows</th>
                <th scope="col">What diverged</th>
              </tr>
            </thead>
            <tbody>
              {checks.data.map((c) => (
                <tr key={c.id}>
                  <th scope="row">{c.family_key}</th>
                  <td>
                    <span className={verdictTone(c.verdict)}>{c.verdict}</span>
                  </td>
                  <td className="mono">
                    {c.rows_diverged}/{c.rows_compared}
                  </td>
                  <td>{c.first_divergence ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>

      <div className="ops-panel">
        <h3>Fired ticks</h3>
        <p className="ops-lede">
          What the scheduler actually did. A FAILED tick means the sweep could not complete — which
          is an outage in the control, not a divergence in the numbers.
        </p>
        {runs.error ? (
          <p className="state error" role="alert">
            {explain(runs.error, "view the scheduled-run ledger")}
          </p>
        ) : null}
        {runs.data && runs.data.items.length === 0 ? (
          <p className="ops-lede">No tick has fired yet.</p>
        ) : null}
        {runs.data && runs.data.items.length > 0 ? (
          <table className="ops-table">
            <thead>
              <tr>
                <th scope="col">Scheduled for</th>
                <th scope="col">Outcome</th>
                <th scope="col">Reason</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.items.map((r) => (
                <tr key={r.id}>
                  <th scope="row" className="mono">
                    {r.scheduled_for}
                  </th>
                  <td>
                    <span className={r.outcome === "FAILED" ? "chip chip-hard" : "chip chip-ok"}>
                      {r.outcome}
                    </span>
                  </td>
                  <td>{r.failure_reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </section>
  );
}
