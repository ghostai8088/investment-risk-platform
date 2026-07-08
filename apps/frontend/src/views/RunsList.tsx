import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, apiGet } from "../api/client";
import { FAMILIES, RUN_STATUSES, RUN_TYPE_TO_FAMILY } from "../api/types";
import type { RiskRunList, RiskRunSummary } from "../api/types";
import type { DevSession } from "../session";

const PAGE_SIZE = 50;

function truncate(text: string, max = 80): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function ErrorState({ error }: { error: ApiError }): ReactElement {
  if (error.kind === "forbidden") {
    return <p className="state error">This identity is not entitled to view risk runs (403).</p>;
  }
  if (error.kind === "unauthorized") {
    return <p className="state error">The backend rejected the session headers (401).</p>;
  }
  return <p className="state error">Could not load runs: {error.message}</p>;
}

export function RunsList({ session }: { session: DevSession }): ReactElement {
  const navigate = useNavigate();
  const [runType, setRunType] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<RiskRunSummary[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    // Staleness guard (review fold): without it a slow older response overwrites a newer
    // filter's results — the table would show non-matching rows under the selected filter.
    let stale = false;
    const params = new URLSearchParams();
    if (runType) params.set("run_type", runType);
    if (statusFilter) params.set("status", statusFilter);
    // Fetch one extra row as the has-more signal (review fold: `length < PAGE_SIZE` cannot
    // detect the last page when the count is an exact multiple of the page size).
    params.set("limit", String(PAGE_SIZE + 1));
    params.set("offset", String(offset));
    setItems(null);
    setError(null);
    apiGet<RiskRunList>(`/risk/runs?${params.toString()}`, session)
      .then((list) => {
        if (stale) return;
        setHasMore(list.items.length > PAGE_SIZE);
        setItems(list.items.slice(0, PAGE_SIZE));
      })
      .catch((e: unknown) => {
        if (stale) return;
        setError(e instanceof ApiError ? e : new ApiError("network", String(e)));
      });
    return () => {
      stale = true;
    };
  }, [runType, statusFilter, offset, session]);

  return (
    <section>
      <h2>Risk runs</h2>
      <div className="filters">
        <label>
          Run type
          <select
            value={runType}
            onChange={(e) => {
              setOffset(0);
              setRunType(e.target.value);
            }}
          >
            <option value="">All</option>
            {Object.values(FAMILIES).map((f) => (
              <option key={f.runType} value={f.runType}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select
            value={statusFilter}
            onChange={(e) => {
              setOffset(0);
              setStatusFilter(e.target.value);
            }}
          >
            <option value="">All</option>
            {RUN_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error ? <ErrorState error={error} /> : null}
      {!error && items === null ? <p className="state">Loading…</p> : null}
      {!error && items !== null && items.length === 0 ? (
        <p className="state">No runs {offset > 0 ? "on this page" : "yet"}.</p>
      ) : null}

      {!error && items !== null && items.length > 0 ? (
        <table className="runs">
          <thead>
            <tr>
              <th>Type</th>
              <th>Status</th>
              <th>Created</th>
              <th>Completed</th>
              <th>Initiated by</th>
              <th>Failure reason</th>
              <th>Run id</th>
            </tr>
          </thead>
          <tbody>
            {items.map((run) => {
              const family = RUN_TYPE_TO_FAMILY[run.run_type];
              return (
                <tr
                  key={run.run_id}
                  className={family ? "clickable" : undefined}
                  onClick={() => {
                    if (family) void navigate(`/runs/${family}/${run.run_id}`);
                  }}
                >
                  <td>{run.run_type}</td>
                  <td>
                    <span className={`status status-${run.status.toLowerCase()}`}>
                      {run.status}
                    </span>
                  </td>
                  <td>{run.created_at}</td>
                  <td>{run.completed_at ?? "—"}</td>
                  <td>{run.initiated_by}</td>
                  <td className="reason">
                    {run.failure_reason ? truncate(run.failure_reason) : "—"}
                  </td>
                  <td className="mono">
                    {family ? (
                      <Link to={`/runs/${family}/${run.run_id}`}>{run.run_id}</Link>
                    ) : (
                      run.run_id
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : null}

      <div className="pager">
        <button
          disabled={offset === 0}
          onClick={() => {
            setOffset(Math.max(0, offset - PAGE_SIZE));
          }}
        >
          Newer
        </button>
        <span>offset {offset}</span>
        <button
          disabled={items === null || !hasMore}
          onClick={() => {
            setOffset(offset + PAGE_SIZE);
          }}
        >
          Older
        </button>
      </div>
    </section>
  );
}
