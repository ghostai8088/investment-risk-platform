import { type FormEvent, type ReactElement, useCallback, useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { useApiGet } from "../../api/useApiGet";
import { verbatim } from "../../api/format";
import type { components } from "../../api/generated/api-types";
import { generateReport } from "../../api/writes";
import type { Session } from "../../session";
import { explain } from "../ops/Refusal";

type ReportListOut = components["schemas"]["ReportListOut"];
type PortfolioOut = components["schemas"]["PortfolioOut"];
type SnapshotHeaderOut = components["schemas"]["SnapshotHeaderOut"];
/** Both list endpoints return a bare array, not an envelope — checked against the generated
 * contract rather than assumed from the `{items: […]}` shape the runs listings use. */
type PortfolioListOut = PortfolioOut[];
type SnapshotListOut = SnapshotHeaderOut[];

/**
 * Generate a governed report (RPT-3, ratified 2026-08-10).
 *
 * The API has been able to mint a report since RPT-2; nothing in a browser could ask it to. This
 * is that ask — a run picker per report family, and a POST through the audited write surface.
 *
 * **The picker is a CONVENIENCE, not a fence.** It filters to COMPLETED runs of each family's own
 * run type because offering a run the server cannot possibly bind wastes the operator's time — but
 * it does NOT try to predict which runs the server will accept. The service re-validates the
 * family key, the run's existence and status, its tenant, its portfolio scope and its snapshot
 * date; the screen renders whatever it refuses. Any deeper pre-filtering would be a second
 * implementation of the binder's adjudication, and a second implementation is a thing that drifts.
 *
 * **Three wire cases, three renderings** (the ratified OQ-RPT3-4, rewritten twice under review).
 * The route answers a bad portfolio with `404 "portfolio not found"` before any service call, and
 * every service refusal with one of exactly two constants — `"report input refused"` or
 * `"report provenance refused"`. RPT-2 chose those constants deliberately: a service message can
 * embed identifiers, and this slice does not reopen that fence. So the screen renders the constant
 * plus a checklist of causes for THAT class, and says plainly that the server does not disclose
 * which one applied. The two classes get DIFFERENT checklists: every input-class cause is
 * impossible under a provenance refusal, and a list of impossible causes reads authoritative while
 * pointing an operator at nothing.
 */

/** The four report families, in `REPORT_FAMILIES` order (= render order), with their run source. */
const FAMILIES = [
  { key: "var", label: "Value at Risk", path: "/risk/runs?run_type=VAR&status=COMPLETED" },
  {
    key: "concentration",
    label: "Concentration",
    path: "/concentration/runs?status=COMPLETED",
  },
  { key: "liquidity", label: "Liquidity", path: "/liquidity/runs?status=COMPLETED" },
  {
    key: "rolling_risk",
    label: "Rolling risk",
    // Listable only since RPT-3 extended PERF_RUN_TYPES — before that this 422'd, which is why
    // the report could bind a rolling-risk run that no operator could find.
    path: "/perf/runs?run_type=ROLLING_RISK&status=COMPLETED",
  },
] as const;

type RunRow = { run_id: string; input_snapshot_id: string | null };
type RunListing = { items: RunRow[] };

/** What the wire said, turned into what an operator should read and check. */
function refusalGuidance(error: ApiError): { headline: string; causes: string[] } | null {
  if (error.kind === "not-found") {
    return {
      headline: "That portfolio is not visible to this tenant.",
      causes: [],
    };
  }
  if (error.detail === "report provenance refused") {
    return {
      headline: "The server refused this report: report provenance refused.",
      // Deliberately NOT the input-class list. A provenance refusal is about model citation
      // trust; offering the date/scope causes here would point the operator at four things that
      // cannot have caused it.
      causes: ["a bound run's model citation could not be established"],
    };
  }
  if (error.detail === "report input refused") {
    return {
      headline: "The server refused this report: report input refused.",
      causes: [
        "a chosen run's snapshot is dated differently from the report date (see the badge on the run)",
        "a chosen run was computed for a different book than the portfolio named here",
        "a VaR run whose root exposure run carries no portfolio scope, so nothing ties its numbers to a book (a known platform limitation)",
        "no family was selected",
      ],
    };
  }
  return null;
}

export function GenerateReport({
  session,
  onGenerated,
}: {
  session: Session;
  onGenerated: () => void;
}): ReactElement {
  const [portfolioId, setPortfolioId] = useState("");
  const [asOf, setAsOf] = useState("");
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [runFor, setRunFor] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const portfolios = useApiGet<PortfolioListOut>("/portfolios", session);
  // Snapshot headers carry the as-of date a run summary does NOT; the join is presentation only.
  const snapshots = useApiGet<SnapshotListOut>("/snapshots?limit=500", session);
  // The duplicate-generate visibility read (carry (d) answered with visibility, not idempotency).
  const existing = useApiGet<ReportListOut>(
    portfolioId ? `/reports?portfolio_id=${portfolioId}&limit=500` : null,
    session,
  );

  const runsVar = useApiGet<RunListing>(checked.var ? FAMILIES[0].path : null, session);
  const runsConc = useApiGet<RunListing>(checked.concentration ? FAMILIES[1].path : null, session);
  const runsLiq = useApiGet<RunListing>(checked.liquidity ? FAMILIES[2].path : null, session);
  const runsRoll = useApiGet<RunListing>(checked.rolling_risk ? FAMILIES[3].path : null, session);
  const listings: Record<string, RunListing | null> = {
    var: runsVar.data ?? null,
    concentration: runsConc.data ?? null,
    liquidity: runsLiq.data ?? null,
    rolling_risk: runsRoll.data ?? null,
  };

  /** snapshot id -> as-of date, for the run labels.
   *
   * `Array.isArray` rather than `?? []`: these two endpoints return BARE arrays while every
   * listing beside them returns an `{items}` envelope, and the label join is presentation only.
   * A shape that is not what the contract promises must cost the operator a LABEL, never the
   * screen — the form still submits, and the server is still the validator. */
  const snapshotDate = useMemo(() => {
    const map = new Map<string, string>();
    const headers = Array.isArray(snapshots.data) ? snapshots.data : [];
    for (const h of headers) map.set(h.id, h.as_of_valuation_date);
    return map;
  }, [snapshots.data]);

  const portfolioRows: PortfolioOut[] = Array.isArray(portfolios.data) ? portfolios.data : [];

  const anyChecked = FAMILIES.some((f) => checked[f.key] && runFor[f.key]);

  /** The existing-report count, and the honest thing to say when the page bound hides the truth. */
  const existingLine = useMemo(() => {
    const items = existing.data?.items;
    if (!portfolioId || !asOf || !items) return null;
    // The listing is as_of_date DESC with no date filter, so a FULL page holds the newest-dated
    // reports and bounds nothing about an older chosen date: the count for that date could be
    // zero or hundreds. Saying "500+ for this date" would be a wrong LARGE number in place of the
    // wrong small one this control exists to avoid.
    if (items.length >= 500) {
      return "This book has 500+ reports; the count for this date could not be determined.";
    }
    const n = items.filter((r) => r.as_of_date === asOf).length;
    return n === 0
      ? null
      : `${n} report${n === 1 ? "" : "s"} already exist${n === 1 ? "s" : ""} for this book and date.`;
  }, [existing.data, portfolioId, asOf]);

  const submit = useCallback(
    (event: FormEvent) => {
      event.preventDefault();
      if (busy || !anyChecked) return;
      const family_runs: Record<string, string> = {};
      for (const f of FAMILIES) {
        // An UNCHECKED family is ABSENT from the payload, never present-and-null: the API forbids
        // unexpected shapes and the service reads the dict's keys as the family set.
        if (checked[f.key] && runFor[f.key]) family_runs[f.key] = runFor[f.key];
      }
      setBusy(true);
      setError(null);
      void generateReport(session, { portfolioId, asOfDate: asOf, familyRuns: family_runs })
        .then(() => {
          onGenerated();
        })
        .catch((e: unknown) => {
          setError(e instanceof ApiError ? e : new ApiError("network", String(e)));
        })
        .finally(() => setBusy(false));
    },
    [busy, anyChecked, checked, runFor, session, portfolioId, asOf, onGenerated],
  );

  const guidance = error ? refusalGuidance(error) : null;

  return (
    <section className="ops-panel">
      <h2>Generate a report</h2>
      <p className="ops-lede">
        A report BINDS the runs you choose: it re-renders from their pinned snapshots and records a
        content hash. Generating twice is two governed acts, not an overwrite.
      </p>

      {error ? (
        <div className="state error" role="alert">
          {guidance ? (
            <>
              <p>{guidance.headline}</p>
              {guidance.causes.length > 0 ? (
                <>
                  <p>The server does not disclose which of these applied:</p>
                  <ul>
                    {guidance.causes.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                </>
              ) : null}
            </>
          ) : (
            <p>{explain(error, "generate a report")}</p>
          )}
        </div>
      ) : null}

      <form onSubmit={submit}>
        <label htmlFor="rpt-portfolio">Portfolio</label>
        <select
          id="rpt-portfolio"
          value={portfolioId}
          onChange={(e) => setPortfolioId(e.target.value)}
          required
        >
          <option value="">Choose a book…</option>
          {portfolioRows.map((p: PortfolioOut) => (
            <option key={p.id} value={p.id}>
              {verbatim(p.code)}
            </option>
          ))}
        </select>

        <label htmlFor="rpt-asof">As of</label>
        <input
          id="rpt-asof"
          type="date"
          value={asOf}
          onChange={(e) => setAsOf(e.target.value)}
          required
        />
        {existingLine ? <p className="state">{existingLine}</p> : null}

        <fieldset>
          <legend>Families to include</legend>
          {FAMILIES.map((f) => {
            const rows = listings[f.key]?.items ?? [];
            return (
              <div key={f.key}>
                <label>
                  <input
                    type="checkbox"
                    checked={Boolean(checked[f.key])}
                    onChange={(e) => setChecked((c) => ({ ...c, [f.key]: e.target.checked }))}
                  />
                  {f.label}
                </label>
                {checked[f.key] ? (
                  <select
                    aria-label={`${f.label} run`}
                    value={runFor[f.key] ?? ""}
                    onChange={(e) => setRunFor((r) => ({ ...r, [f.key]: e.target.value }))}
                  >
                    <option value="">Choose a completed run…</option>
                    {rows.map((row) => {
                      const dated = row.input_snapshot_id
                        ? snapshotDate.get(row.input_snapshot_id)
                        : undefined;
                      // A run dated off the chosen report date is still OFFERED — the server is
                      // the validator — but badged, so its refusal is unsurprising rather than
                      // mysterious.
                      const mismatch = Boolean(asOf && dated && dated !== asOf);
                      return (
                        <option key={row.run_id} value={row.run_id}>
                          {row.run_id.slice(0, 8)}
                          {dated ? ` · ${dated}` : " · undated"}
                          {mismatch ? ` (dated ${dated}, not ${asOf})` : ""}
                        </option>
                      );
                    })}
                  </select>
                ) : null}
              </div>
            );
          })}
        </fieldset>

        {!anyChecked ? (
          <p className="state">
            Choose at least one family and a completed run for it — a report with no families is
            refused by the server.
          </p>
        ) : null}

        <button type="submit" disabled={busy || !anyChecked}>
          {busy ? "Generating…" : "Generate report"}
        </button>
      </form>
    </section>
  );
}
