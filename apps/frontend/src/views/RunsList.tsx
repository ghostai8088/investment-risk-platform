import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, apiGet } from "../api/client";
import { FAMILIES, RUN_STATUSES, RUN_TYPE_TO_FAMILY } from "../api/types";
import type { RiskRunList, RiskRunSummary } from "../api/types";
import type { Session } from "../session";

const PAGE_SIZE = 50;

function truncate(text: string, max = 80): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function ErrorState({ error }: { error: ApiError }): ReactElement {
  if (error.kind === "forbidden") {
    // Family-neutral: exposure runs need exposure.view, risk runs need risk.view, perf runs need
    // perf.view — a session may hold one and not the others (the permission-family separation,
    // P3-C2 OD-C; PM-1).
    return (
      <p className="state error">
        This identity is not entitled to view the selected runs (403 — risk runs need risk.view,
        exposure runs need exposure.view, portfolio-return runs need perf.view).
      </p>
    );
  }
  if (error.kind === "unauthorized") {
    return <p className="state error">The backend rejected the session headers (401).</p>;
  }
  return <p className="state error">Could not load runs: {error.message}</p>;
}

export function RunsList({ session }: { session: Session }): ReactElement {
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
    if (statusFilter) params.set("status", statusFilter);
    // Fetch one extra row as the has-more signal (review fold: `length < PAGE_SIZE` cannot
    // detect the last page when the count is an exact multiple of the page size).
    params.set("limit", String(PAGE_SIZE + 1));
    params.set("offset", String(offset));
    // The family selector chooses the SOURCE (P3-C2 OD-C; PM-1/P3-8): EXPOSURE_AGGREGATE is a
    // separate permission family (exposure.view) listed by /exposure/runs; the perf families
    // (PORTFOLIO_RETURN, BENCHMARK_RELATIVE — perf.view) are listed by /perf/runs; the risk families
    // (and the "All risk" default) are listed by /risk/runs. Selecting a source per family keeps
    // server-side pagination correct — merging independently-paginated endpoints would recreate the
    // FE-1 has-more trap. The run_type filter narrows /risk/runs and /perf/runs to the chosen family.
    // Derive the source from the family's OWN permissionFamily (review fold: a hardcoded
    // run-type list silently dropped each newly added perf family from the listing).
    const family = runType ? RUN_TYPE_TO_FAMILY[runType] : undefined;
    const permissionFamily = family ? FAMILIES[family].permissionFamily : "risk";
    const isExposure = permissionFamily === "exposure";
    const isPerf = permissionFamily === "perf";
    if (runType && !isExposure) params.set("run_type", runType);
    let base = "/risk/runs";
    if (isExposure) base = "/exposure/runs";
    else if (isPerf) base = "/perf/runs";
    const url = `${base}?${params.toString()}`;
    setItems(null);
    setError(null);
    apiGet<RiskRunList>(url, session)
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
      {/* Family-neutral heading: this view now also lists the exposure family (P3-C2 OD-C),
          so it is no longer "Risk runs" — the family selector below scopes the source. */}
      <h2>Runs</h2>
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
            <option value="">All risk families</option>
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
