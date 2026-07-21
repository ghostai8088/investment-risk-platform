import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, apiGet } from "../api/client";
import { verbatim } from "../api/format";
import { FAMILIES, FAMILY_ROW_COLUMNS, runDetailUrl } from "../api/types";
import type { Family, RunDetailBase } from "../api/types";
import type { DevSession } from "../session";

/** FL-1 (the ES honesty fix, OD-FL-1-F): on an ES row the backend ECHOES the quantile z — it is
 * NOT the ES arithmetic (the multiplier k_c lives on the bound model_version), so `z × σ ≠ value`
 * for ES rows and three adjacent columns would otherwise invite exactly that wrong arithmetic.
 * Per-row metric_type-aware rendering annotates the echo; every other cell renders verbatim.
 * (Surfacing es_multiplier on the row DTO is the recorded backend v2 — not smuggled in here.) */
function resultCell(row: Record<string, string | number | null>, key: string): string {
  const value = verbatim(row[key]);
  if (key === "z_score" && row.metric_type === "ES_PARAMETRIC" && value !== "—") {
    return `${value} (echo — not the ES multiplier; see model version)`;
  }
  return value;
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
    // runDetailUrl encodeURIComponent's the runId (review fold: the router DECODES %2F/%3F/%23,
    // so an unencoded id in a crafted deep link could rewrite the request path/query with the
    // session headers attached) and routes exposure to its own endpoint (P3-C2 OD-C). The
    // family segment is allowlisted above (validFamily).
    apiGet<RunDetailBase>(runDetailUrl(validFamily, runId), session)
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
        <Link to="/runs">Back to runs</Link>
      </section>
    );
  }

  return (
    <section>
      <p>
        <Link to="/runs">← All runs</Link>
      </p>
      <h2>
        {FAMILIES[validFamily].label} run <span className="mono">{runId}</span>
      </h2>

      {error ? (
        <p className="state error">
          {error.kind === "not-found"
            ? "Run not found (or not visible to this identity)."
            : error.kind === "forbidden"
              ? "This identity is not entitled to view this run (403)."
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
                  <td className="mono">{verbatim(run[f.key] as string | null)}</td>
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
                        {resultCell(row, c.key)}
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
