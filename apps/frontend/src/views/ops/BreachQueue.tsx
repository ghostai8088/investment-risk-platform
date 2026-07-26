import { useState } from "react";
import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import { useApiGet } from "../../api/useApiGet";
import { verbatim } from "../../api/format";
import type { components } from "../../api/generated/api-types";
import type { Session } from "../../session";
import { explain } from "./Refusal";

type BreachOut = components["schemas"]["BreachOut"];

const PAGE_SIZE = 50;

/** The lifecycle states, in workflow order — the filter chips double as a legend for the machine. */
const STATES = ["DETECTED", "ASSIGNED", "RESPONDED", "REVIEWED", "ESCALATED", "CLOSED"] as const;

/** Is this breach past its response deadline?
 *
 * `response_due` is deliberately NULLed once a breach reaches REVIEWED/CLOSED (the deadline no
 * longer governs), so a null must read as "no deadline applies" — never as "overdue" and never as
 * an implicit OK (verifier medium fold). */
function isOverdue(breach: BreachOut, now: number): boolean {
  if (!breach.response_due) return false;
  return new Date(breach.response_due).getTime() < now;
}

export function BreachQueue({ session }: { session: Session }): ReactElement {
  const [state, setState] = useState<string>("");
  const [openOnly, setOpenOnly] = useState(true);
  const [offset, setOffset] = useState(0);

  const params = new URLSearchParams();
  if (state) params.set("state", state);
  if (openOnly) params.set("open", "true");
  params.set("limit", String(PAGE_SIZE + 1)); // one extra row = the has-more signal
  params.set("offset", String(offset));

  const { data, error, loading } = useApiGet<BreachOut[]>(
    `/breaches?${params.toString()}`,
    session,
  );
  const rows = data ? data.slice(0, PAGE_SIZE) : null;
  const hasMore = data !== null && data.length > PAGE_SIZE;
  const now = Date.now();

  return (
    <section className="ops-view">
      <header className="ops-header">
        <h2>Breach queue</h2>
        <p className="ops-lede">
          Limit breaches detected by the operational tick, with their remediation state and owner.
          This is the tenant-wide worklist — every portfolio, not just the walk&apos;s book.
        </p>
      </header>

      <div className="ops-filters">
        <label>
          State
          <select
            value={state}
            onChange={(e) => {
              setState(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All</option>
            {STATES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="ops-check">
          <input
            type="checkbox"
            checked={openOnly}
            onChange={(e) => {
              setOpenOnly(e.target.checked);
              setOffset(0);
            }}
          />
          Needs attention (hide CLOSED)
        </label>
      </div>

      {loading ? <p className="state">Loading breaches…</p> : null}
      {error ? (
        <p className="state error" role="alert">
          {explain(error, "view breaches")}
        </p>
      ) : null}

      {rows && rows.length === 0 ? (
        /* Review H-4: an empty queue is NOT evidence that everything is within appetite. It is
           equally consistent with: no limits defined, every limit DRAFT/SUSPENDED (never
           evaluated), ACTIVE limits that are NEVER_EVALUABLE, or simply these filters. Asserting
           the reassuring reading would be the empty-state-as-passing-state failure this slice's
           own limit-health handling was written to avoid — so point at the surface that CAN
           answer the question instead of answering it here. */
        <p className="state">
          No breaches match these filters. This is not by itself an all-clear:{" "}
          <Link to="/ops/limits">check limit health</Link> to see which limits are actually in force
          and evaluated.
        </p>
      ) : null}

      {rows && rows.length > 0 ? (
        <table className="ops-table">
          <caption className="sr-only">Open limit breaches</caption>
          <thead>
            <tr>
              <th scope="col">Limit</th>
              <th scope="col">Severity</th>
              <th scope="col">Observed</th>
              <th scope="col">Threshold</th>
              <th scope="col">State</th>
              <th scope="col">Owner</th>
              <th scope="col">Response due</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => (
              <tr key={b.id} className={isOverdue(b, now) ? "row-overdue" : undefined}>
                <th scope="row">
                  <Link to={`/ops/breaches/${b.id}`}>{verbatim(b.limit_code)}</Link>
                  <span className="cell-sub">{verbatim(b.metric_type)}</span>
                </th>
                <td>
                  <span className={b.severity === "HARD" ? "chip chip-hard" : "chip chip-soft"}>
                    {verbatim(b.severity)}
                  </span>
                </td>
                {/* Fixed-point strings straight from the API — never parsed to a float. */}
                <td className="mono num">{verbatim(b.observed_value)}</td>
                <td className="mono num">{verbatim(b.threshold_value)}</td>
                <td>{verbatim(b.state)}</td>
                <td className="mono">{b.assigned_to ? verbatim(b.assigned_to) : "—"}</td>
                <td>
                  {b.response_due ? (
                    <>
                      {new Date(b.response_due).toISOString().slice(0, 16).replace("T", " ")}
                      {isOverdue(b, now) ? (
                        <span className="chip chip-overdue">overdue</span>
                      ) : null}
                    </>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      <div className="ops-pager">
        <button
          type="button"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        >
          Previous
        </button>
        <button type="button" disabled={!hasMore} onClick={() => setOffset(offset + PAGE_SIZE)}>
          Next
        </button>
      </div>
    </section>
  );
}
