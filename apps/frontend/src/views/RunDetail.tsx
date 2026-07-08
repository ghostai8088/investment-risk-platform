import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, apiGet } from "../api/client";
import { FAMILIES, FAMILY_ROW_COLUMNS } from "../api/types";
import type { Family, RunDetailBase } from "../api/types";
import type { DevSession } from "../session";

/** Render a cell VERBATIM: values arrive as JSON strings/numbers and are never re-parsed —
 * a `Number()` here would corrupt the exact decimal strings (OQ-FE-1-7). */
function cell(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return typeof value === "number" ? String(value) : value;
}

const PROVENANCE_FIELDS: { key: keyof RunDetailBase; label: string }[] = [
  { key: "run_id", label: "Run id" },
  { key: "run_type", label: "Run type" },
  { key: "input_snapshot_id", label: "Input snapshot" },
  { key: "model_version_id", label: "Model version" },
  { key: "code_version", label: "Code version" },
  { key: "environment_id", label: "Environment" },
  { key: "initiated_by", label: "Initiated by" },
];

export function RunDetail({ session }: { session: DevSession }): ReactElement {
  const { family, runId } = useParams<{ family: string; runId: string }>();
  const [run, setRun] = useState<RunDetailBase | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const validFamily = family && family in FAMILIES ? (family as Family) : null;

  useEffect(() => {
    if (!validFamily || !runId) return;
    // Staleness guard (review fold): navigating run A → run B while A's fetch is in flight
    // must not let A's late response render under B's heading — a silent label/data mismatch.
    let stale = false;
    setRun(null);
    setError(null);
    // encodeURIComponent (review fold): the router DECODES %2F/%3F/%23 in the param, so an
    // unencoded runId in a crafted deep link could rewrite the request path/query — and it
    // would carry the session headers. The family segment is allowlisted above.
    apiGet<RunDetailBase>(`/risk/${validFamily}/runs/${encodeURIComponent(runId)}`, session)
      .then((body) => {
        if (!stale) setRun(body);
      })
      .catch((e: unknown) => {
        if (!stale) setError(e instanceof ApiError ? e : new ApiError("network", String(e)));
      });
    return () => {
      stale = true;
    };
  }, [validFamily, runId, session]);

  if (!validFamily || !runId) {
    return (
      <section>
        <p className="state error">Unknown run family in the URL.</p>
        <Link to="/">Back to runs</Link>
      </section>
    );
  }

  return (
    <section>
      <p>
        <Link to="/">← All runs</Link>
      </p>
      <h2>
        {FAMILIES[validFamily].label} run <span className="mono">{runId}</span>
      </h2>

      {error ? (
        <p className="state error">
          {error.kind === "not-found"
            ? "Run not found (or not visible to this identity)."
            : error.kind === "forbidden"
              ? "This identity is not entitled to view risk runs (403)."
              : error.kind === "unauthorized"
                ? "The backend rejected the session headers (401)."
                : `Could not load the run: ${error.message}`}
        </p>
      ) : null}
      {!error && run === null ? <p className="state">Loading…</p> : null}

      {run ? (
        <>
          <p>
            Status:{" "}
            <span className={`status status-${run.status.toLowerCase()}`}>{run.status}</span>
          </p>
          {run.failure_reason ? (
            <div className="failure" role="alert">
              <strong>Failure reason</strong>
              <pre>{run.failure_reason}</pre>
            </div>
          ) : null}

          <h3>Provenance</h3>
          <table className="provenance">
            <tbody>
              {PROVENANCE_FIELDS.map((f) => (
                <tr key={f.key}>
                  <th>{f.label}</th>
                  <td className="mono">{cell(run[f.key] as string | null)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Results ({run.rows.length})</h3>
          {run.rows.length === 0 ? (
            <p className="state">
              No result rows{run.status === "FAILED" ? " — the run failed closed." : "."}
            </p>
          ) : (
            <table className="results">
              <thead>
                <tr>
                  {FAMILY_ROW_COLUMNS[validFamily].map((c) => (
                    <th key={c.key}>{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {run.rows.map((row, i) => (
                  <tr key={typeof row.id === "string" ? row.id : i}>
                    {FAMILY_ROW_COLUMNS[validFamily].map((c) => (
                      <td key={c.key} className="mono">
                        {cell(row[c.key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : null}
    </section>
  );
}
