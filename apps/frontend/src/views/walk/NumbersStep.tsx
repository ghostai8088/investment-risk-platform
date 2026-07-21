import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import { shortId, verbatim } from "../../api/format";
import type { CovarianceRow, PortfolioReturnRow, RiskRunList } from "../../api/types";
import { useApiGet } from "../../api/useApiGet";
import { GovernedValue } from "../../components/GovernedValue";
import { Pane } from "../../components/Pane";
import { ValidationBadge } from "../../components/ValidationBadge";
import type { DevSession } from "../../session";
import { useModelIndex } from "../../walk/useModelIndex";
import type { ModelIndex } from "../../walk/useModelIndex";

/**
 * Walk step 3 — Governed numbers (FE-3, OD-FE-3-A/C), the heart of the walk. Each number renders
 * with its trust context inline: value verbatim + provenance (run/model) + the model's validation
 * badge and disclosed limitations (from the model index). VaR is shown HONESTLY as the seeded run
 * series with the API-1b gap stated — no faked "latest for portfolio" (OD-F).
 */
export function NumbersStep({
  session,
  portfolioId,
}: {
  session: DevSession;
  portfolioId: string;
}): ReactElement {
  const pf = encodeURIComponent(portfolioId);
  const ret = useApiGet<PortfolioReturnRow[]>(
    `/perf/portfolio-returns/latest?portfolio_id=${pf}`,
    session,
  );
  const cov = useApiGet<CovarianceRow[]>("/risk/covariances/latest", session);
  const vars = useApiGet<RiskRunList>("/risk/runs?run_type=VAR&status=COMPLETED&limit=50", session);
  const models = useModelIndex(session);

  return (
    <>
      <p className="muted">
        Each governed number shows what it traces to — its run and model version — with the model’s
        validation status and disclosed limitations inline. Nothing is asserted without provenance.
      </p>

      <h3>Portfolio return</h3>
      <Pane state={ret} requires="perf.view">
        {(rows) => {
          const r = rows[0];
          return (
            <GovernedValue
              label={`Return · ${verbatim(r.metric_type)} · ${verbatim(r.period_start)} → ${verbatim(r.period_end)}`}
              value={r.return_value}
              provenance={{ runId: r.calculation_run_id, modelVersionId: r.model_version_id }}
            >
              <Governance versionId={r.model_version_id} index={models} />
            </GovernedValue>
          );
        }}
      </Pane>

      <h3>Factor covariance matrix</h3>
      <Pane state={cov} requires="risk.view">
        {(rows) => (
          <>
            <GovernedValue
              label="Factor covariance matrix"
              value={`${String(rows.length)} factor pairs`}
              provenance={{
                runId: rows[0].calculation_run_id,
                modelVersionId: rows[0].model_version_id,
              }}
            >
              <Governance versionId={rows[0].model_version_id} index={models} />
            </GovernedValue>
            <table>
              <thead>
                <tr>
                  <th>Factor</th>
                  <th>Factor</th>
                  <th>Covariance</th>
                  <th>Obs</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id}>
                    <td>{verbatim(c.factor_code_1)}</td>
                    <td>{verbatim(c.factor_code_2)}</td>
                    <td className="mono">{verbatim(c.covariance_value)}</td>
                    <td className="mono">{verbatim(c.n_observations)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Pane>

      <h3>Value-at-Risk</h3>
      <Pane state={vars} requires="risk.view">
        {(list) => (
          <>
            <p className="muted">
              VaR has no “latest for portfolio P” resolver yet — that lands with <strong>API-1b</strong>{" "}
              (it needs a run-to-portfolio scope column). Below is the seeded <em>series</em> of VaR
              runs <strong>across all books — not filtered to this one</strong>; open one for its
              value and full provenance.
            </p>
            {list.items.length === 0 ? (
              <p className="state">No VaR runs.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {list.items.map((run) => (
                    <tr key={run.run_id}>
                      <td className="mono">
                        <Link to={`/runs/vars/${encodeURIComponent(run.run_id)}`}>
                          {shortId(run.run_id)}
                        </Link>
                      </td>
                      <td>
                        <span className={`status status-${run.status.toLowerCase()}`}>
                          {run.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </Pane>
    </>
  );
}

/** The model's governance context under a governed number (OD-FE-3-C): validation badge + disclosed
 * limitations, degrading to a calm note if `model.inventory.view` is absent. */
function Governance({
  versionId,
  index,
}: {
  versionId: string | null | undefined;
  index: ModelIndex;
}): ReactElement | null {
  if (!versionId) return null;
  if (index.loading) return <p className="gv-gov-note">Loading validation…</p>;
  if (index.error) {
    return index.error.kind === "forbidden" ? (
      <p className="state denied">
        Validation &amp; limitations need the “model.inventory.view” permission.
      </p>
    ) : null;
  }
  const entry = index.entries.get(versionId);
  if (!entry) return null;
  return (
    <div className="gv-governance">
      <ValidationBadge info={{ tier: entry.tier, outcome: entry.outcome, overdue: entry.overdue }} />
      {entry.limitations.length > 0 ? (
        <details className="limitations">
          <summary>
            {entry.limitations.length} disclosed limitation
            {entry.limitations.length === 1 ? "" : "s"}
          </summary>
          <ul>
            {entry.limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
