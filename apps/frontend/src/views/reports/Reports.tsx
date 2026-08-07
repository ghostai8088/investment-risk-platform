/**
 * The report view (RPT-2, remit I4): list governed reports, render one SAFELY, show provenance.
 *
 * **The render is a sandboxed iframe, and the sandbox is the point.** The report body is
 * server-produced HTML whose tenant-influenced strings are escaped server-side (mutation-proven at
 * RPT-1) — but this view is the platform's first rendering of server HTML, and a renderer defect
 * three slices from now must not become an XSS in the ops app. `` (every capability
 * withheld: no scripts, no same-origin, no forms, no popups) puts the markup in a null-origin
 * browsing context where even a hostile `<script>` that survived every server escape executes
 * nowhere and can reach neither the session storage nor the API. The alternative —
 * `dangerouslySetInnerHTML` into our own DOM — would make the app's integrity depend on the
 * server's escaping being perfect forever; the iframe makes it depend on the browser's sandbox,
 * which is the stronger promise. Content arrives via `srcDoc` (no network fetch from the frame —
 * it could not make one anyway; a null-origin frame sends no identity headers).
 *
 * **Every read of the artifact is a reproduction check** (remit I1): the HTML endpoint re-renders
 * from the pinned snapshot and 500s on identity divergence — so a rendered report on this screen
 * IS a fresh proof, and the 500 path renders as the honest integrity failure it is, not as noise.
 */

import { useEffect, useState } from "react";
import type { ReactElement } from "react";

import { ApiError, apiGetHtml } from "../../api/client";
import { useApiGet } from "../../api/useApiGet";
import { verbatim } from "../../api/format";
import type { components } from "../../api/generated/api-types";
import type { Session } from "../../session";
import { explain } from "../ops/Refusal";

type ReportOut = components["schemas"]["ReportOut"];
type ReportListOut = components["schemas"]["ReportListOut"];

/** The rendered artifact, loaded imperatively (the HTML verb is not JSON, so it cannot ride
 * `useApiGet`). Staleness-guarded like the hook: a superseded selection never renders. */
function useReportHtml(
  reportId: string | null,
  session: Session,
  reloadKey: number,
): { html: string | null; error: ApiError | null; loading: boolean } {
  const [state, setState] = useState<{
    html: string | null;
    error: ApiError | null;
    loading: boolean;
  }>({ html: null, error: null, loading: false });

  useEffect(() => {
    if (reportId === null) {
      setState({ html: null, error: null, loading: false });
      return;
    }
    let stale = false;
    setState({ html: null, error: null, loading: true });
    apiGetHtml(`/reports/${reportId}/html`, session)
      .then((html) => {
        if (!stale) setState({ html, error: null, loading: false });
      })
      .catch((err: unknown) => {
        if (!stale) {
          const apiErr =
            err instanceof ApiError ? err : new ApiError("server", "unexpected failure");
          setState({ html: null, error: apiErr, loading: false });
        }
      });
    return () => {
      stale = true;
    };
    // `reloadKey` is in the dependency list because RELOAD MUST RE-FETCH: each read of the
    // artifact re-renders it from the pinned snapshot server-side, so a re-read is a FRESH
    // reproduction proof. Without this the button re-rendered cached state and the screen's
    // central promise was decorative (review finding).
  }, [reportId, session, reloadKey]);

  return state;
}

export function Reports({ session }: { session: Session }): ReactElement {
  const [selected, setSelected] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const reports = useApiGet<ReportListOut>("/reports", session, reload);
  const artifact = useReportHtml(selected, session, reload);

  const items = reports.data?.items ?? [];
  const current = items.find((r) => r.id === selected) ?? null;

  return (
    <div className="ops-view">
      <header className="ops-header">
        <h1>Reports</h1>
        <p className="ops-lede">
          Governed reports, regenerated from their pinned inputs on every read — what renders below
          is re-proven byte-identical to the recorded artifact, not served from a cache.
        </p>
      </header>

      {reports.loading ? <p className="state">Loading reports…</p> : null}
      {reports.error ? (
        <p className="state error" role="alert">
          {explain(reports.error, "view reports")}
        </p>
      ) : null}
      {!reports.loading && !reports.error && items.length === 0 ? (
        <p className="state">No reports have been generated yet.</p>
      ) : null}

      {items.length > 0 ? (
        <section className="ops-panel">
          <table className="ops-table">
            <thead>
              <tr>
                <th>Portfolio</th>
                <th>As of</th>
                <th>Report</th>
                <th>Generated</th>
                <th>Identity (SHA-256)</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((r: ReportOut) => (
                <tr key={r.id}>
                  <td>{verbatim(r.portfolio_code)}</td>
                  <td className="num">{verbatim(r.as_of_date)}</td>
                  <td>
                    {verbatim(r.report_code)}{" "}
                    <span className="cell-sub">{r.report_version_label}</span>
                  </td>
                  <td className="cell-sub">
                    {verbatim(r.generated_at)} by {verbatim(r.generated_by)}
                  </td>
                  {/* The full hash, verbatim — a truncated hash cannot be independently checked,
                      and independent checking is the entire value of showing it. */}
                  <td className="mono">{verbatim(r.content_hash)}</td>
                  <td>
                    <button
                      type="button"
                      onClick={() => {
                        setSelected(r.id);
                        // Bump on re-click: re-selecting the SAME id must still re-fetch, because
                        // the re-fetch IS the proof.
                        if (selected === r.id) setReload((n) => n + 1);
                      }}
                    >
                      {selected === r.id ? "Reload" : "Open"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {selected !== null ? (
        <section className="ops-panel">
          {current ? (
            <p className="cell-sub">
              run <span className="mono">{current.calculation_run_id}</span> · inputs{" "}
              <span className="mono">{current.input_snapshot_id}</span>
            </p>
          ) : null}
          {artifact.loading ? <p className="state">Regenerating from the pinned inputs…</p> : null}
          {artifact.error ? (
            <p className="state error" role="alert">
              {/* Only a REAL identity failure may be announced as one. Any 500 was previously
                  rendered as an integrity alarm, so a transient server error would have told an
                  operator the platform had failed its reproducibility claim when it had not
                  (review finding). The server's detail names this failure explicitly. */}
              {artifact.error.status === 500 && artifact.error.detail.includes("identity failure")
                ? "REPORT IDENTITY FAILURE — regeneration diverged from the recorded artifact. " +
                  "This is the platform failing its own reproducibility claim, not a display " +
                  "problem; the divergence detail has been recorded server-side."
                : explain(artifact.error, "render the report")}
            </p>
          ) : null}
          {artifact.html !== null ? (
            <iframe
              title="Governed report (sandboxed)"
              className="report-frame"
              // Every sandbox capability withheld — see the module docstring. Do NOT add
              // allow-scripts or allow-same-origin here; either one re-opens the exact hole the
              // sandbox exists to close.
              sandbox=""
              srcDoc={artifact.html}
            />
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
