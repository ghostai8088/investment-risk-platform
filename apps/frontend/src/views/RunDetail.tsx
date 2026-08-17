import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { Link, useParams } from "react-router";

import { ApiError, apiGet } from "../api/client";
import { verbatim } from "../api/format";
import { FAMILIES, FAMILY_ROW_COLUMNS, runDetailUrl } from "../api/types";
import type { ExposureRow, Family, NodeRollup, RunDetailBase } from "../api/types";
import type { Session } from "../session";

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

/** STRUCT-4 (DP-12): a stored leg's base/quote are the PUBLISHED row's orientation — a
 * reciprocal leg travels quote → base, and rendering the stored pair raw would show the path
 * BACKWARDS. The displayed rate is the published one; the reciprocal's multiplier is 1/rate. */
function legPath(leg: Record<string, unknown>): string {
  const base = String(leg.base_currency ?? "?");
  const quote = String(leg.quote_currency ?? "?");
  const travel = leg.direction === "reciprocal" ? `${quote} → ${base}` : `${base} → ${quote}`;
  const rate = String(leg.rate ?? "?");
  const label =
    leg.direction === "reciprocal"
      ? `reciprocal of ${base}/${quote} @ ${rate}`
      : `direct @ ${rate}`;
  return `${travel} (${label}; fx_rate ${String(leg.fx_rate_id ?? "?")})`;
}

/** The pivot cell (review fold C13): a DISTINCT rendering ("via USD") so a test asserting the
 * pivot cannot be satisfied by a currency code appearing in any other cell. */
function pivotCell(pivot: string | null): string {
  return pivot ? `via ${pivot}` : "—";
}

/** The conversion-path drill-in (STRUCT-4, REQ-PPM-010 — "a reader can SEE the conversion path
 * on a screen": fx_legs reached the API in P2-3 and no screen ever rendered it, the exact
 * read-endpoint-without-screen pattern the re-baseline exists to stop). Exposure family only.
 * Shows each row's published-rate path (legs, direction, per-tenant fx_rate_id provenance, the
 * DP-12 pivot — stated on new rows, derived for shipped ones) and the node-total drill-in with
 * the translated total in the node's declared reporting currency. */
function ExposureConversionSection({
  session,
  runId,
  rows,
}: {
  session: Session;
  runId: string;
  rows: ExposureRow[];
}): ReactElement {
  const nodes = [...new Set(rows.map((r) => r.portfolio_id))];
  const [nodeId, setNodeId] = useState<string>(nodes[0]);
  const [rollup, setRollup] = useState<NodeRollup[] | null>(null);
  const [rollupError, setRollupError] = useState<ApiError | null>(null);

  useEffect(() => {
    let stale = false;
    setRollup(null);
    setRollupError(null);
    apiGet<NodeRollup[]>(
      `/exposure/runs/${encodeURIComponent(runId)}/rollup?node_id=${encodeURIComponent(nodeId)}`,
      session,
    )
      .then((body) => {
        // Defensive: an unexpected non-array body renders as empty rather than crashing the
        // whole run page under the section (the rollup contract is an array).
        if (!stale) setRollup(Array.isArray(body) ? body : []);
      })
      .catch((e: unknown) => {
        if (!stale) setRollupError(e instanceof ApiError ? e : new ApiError("network", String(e)));
      });
    return () => {
      stale = true;
    };
  }, [runId, nodeId, session]);

  const translated = rows.filter((r) => (r.fx_legs ?? []).length > 0);
  return (
    <>
      <h3>Conversion paths</h3>
      {translated.length === 0 ? (
        <p className="state">
          Every row converts identically (mark currency = reporting currency) — no published-rate
          legs were used.
        </p>
      ) : (
        <table className="results">
          <thead>
            <tr>
              <th>Instrument</th>
              <th>Measure</th>
              <th>Conversion</th>
              <th>Effective rate</th>
              <th>Pivot</th>
              <th>Published legs</th>
            </tr>
          </thead>
          <tbody>
            {translated.map((r) => (
              <tr key={r.id}>
                <td className="mono">{r.instrument_id}</td>
                <td className="mono">{r.exposure_type}</td>
                <td className="mono">
                  {r.mark_currency} → {r.base_currency}
                </td>
                <td className="mono">{r.fx_rate}</td>
                <td className="mono">{pivotCell(r.fx_pivot)}</td>
                <td className="mono">
                  {r.fx_legs.map((leg, i) => (
                    <div key={i}>{legPath(leg)}</div>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>Node totals (declared reporting currency)</h3>
      <p>
        <label>
          Node{" "}
          <select value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
            {nodes.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>{" "}
        <label>
          {/* Review fold C8: the select lists only ROW-bearing nodes — the DP-11 declarations
              live on grouping nodes too, so any pinned node id can be rolled up directly. */}
          or any pinned node id{" "}
          <input
            type="text"
            placeholder="node id"
            onChange={(e) => {
              const value = e.target.value.trim();
              if (value) setNodeId(value);
            }}
          />
        </label>
      </p>
      {rollupError ? (
        <p className="state error">Could not load the node rollup: {rollupError.message}</p>
      ) : null}
      {!rollupError && rollup === null ? <p className="state">Loading…</p> : null}
      {rollup ? (
        <table className="results">
          <thead>
            <tr>
              <th>Measure</th>
              <th>Total</th>
              <th>Reporting ccy</th>
              <th>Translated</th>
              <th>Rate</th>
              <th>Pivot</th>
              <th>Translation legs</th>
            </tr>
          </thead>
          <tbody>
            {rollup.map((r) => (
              <tr key={r.exposure_type}>
                <td className="mono">{r.exposure_type}</td>
                <td className="mono">
                  {r.total} {r.base_currency}
                </td>
                <td className="mono">{verbatim(r.reporting_currency)}</td>
                <td className="mono">
                  {r.missing_fx
                    ? // The honesty clause: a pre-PPM-010 snapshot without the leg says SO —
                      // never a fabricated 1.0, never a retroactive refusal.
                      `unavailable — ${r.missing_fx} (no pinned path in this run's snapshot)`
                    : r.translated_total !== null
                      ? `${r.translated_total} ${verbatim(r.translated_currency)}`
                      : "—"}
                </td>
                <td className="mono">{verbatim(r.translation_fx_rate)}</td>
                <td className="mono">{pivotCell(r.translation_pivot)}</td>
                <td className="mono">
                  {r.translation_legs.length === 0
                    ? "—"
                    : r.translation_legs.map((leg, i) => <div key={i}>{legPath(leg)}</div>)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </>
  );
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

export function RunDetail({ session }: { session: Session }): ReactElement {
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

          {run.limitations && run.limitations.length > 0 ? (
            <div className="limitations" role="note">
              {/* The Wave-14 close (re-adjudicated MED): the API returned these and NO screen on
                  the ratified surface rendered them. The first one is the one that matters — this
                  number is NOT the Rule 22e-4 15% test, and a reader of the run page must see
                  that NEXT TO the number, not in a registry pane elsewhere. */}
              <strong>Registered model limitations</strong>
              <ul>
                {run.limitations.map((text, i) => (
                  <li key={i}>{text}</li>
                ))}
              </ul>
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

          {validFamily === "exposure" && run.rows.length > 0 ? (
            <ExposureConversionSection
              session={session}
              runId={runId}
              rows={run.rows as unknown as ExposureRow[]}
            />
          ) : null}
        </>
      ) : null}
    </section>
  );
}
