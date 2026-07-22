import type { ReactElement } from "react";

import { verbatim } from "../../api/format";
import type { EsBacktestRow, VarBacktestRow } from "../../api/types";
import { useApiGet } from "../../api/useApiGet";
import { GovernedValue } from "../../components/GovernedValue";
import { Pane } from "../../components/Pane";
import type { Session } from "../../session";

type Fact = [string, string | number | null | undefined];

function BacktestFacts({ facts }: { facts: Fact[] }): ReactElement {
  return (
    <dl className="backtest-facts">
      {facts.map(([label, value]) => (
        <div key={label} className="prov-item">
          <dt>{label}</dt>
          <dd className="mono">{verbatim(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Walk step 4 — Backtest evidence (FE-3, OD-FE-3-A). Did the risk numbers hold up against
 * outcomes? Each backtest is itself a governed result with its own provenance. The ES backtest's
 * verdict is DOMAIN-GATED (Acerbi–Székely criticals depend on α/T/df) — shown honestly as evidence
 * without an off-domain verdict, never a fabricated pass/fail (OD-F).
 */
export function BacktestStep({
  session,
  portfolioId,
}: {
  session: Session;
  portfolioId: string;
}): ReactElement {
  const pf = encodeURIComponent(portfolioId);
  const varBt = useApiGet<VarBacktestRow[]>(
    `/risk/var-backtests/latest?portfolio_id=${pf}`,
    session,
  );
  const esBt = useApiGet<EsBacktestRow[]>(`/risk/es-backtests/latest?portfolio_id=${pf}`, session);

  return (
    <>
      <p className="muted">
        Each backtest below is a governed result in its own right — it traces to its own run and
        model version.
      </p>

      <h3>VaR backtests</h3>
      <Pane state={varBt} requires="risk.view">
        {(rows) => (
          <>
            {rows.map((r) => (
              <GovernedValue
                key={r.id}
                label={`${verbatim(r.metric_type)} · ${verbatim(r.var_metric_type)} · ${verbatim(r.period_start)} → ${verbatim(r.period_end)}`}
                value={verbatim(r.test_decision) === "—" ? r.metric_value : r.test_decision}
                provenance={{ runId: r.calculation_run_id, modelVersionId: r.model_version_id }}
              >
                <BacktestFacts
                  facts={[
                    ["Exceptions", `${verbatim(r.n_exceptions)} / ${verbatim(r.n_pairs)}`],
                    ["Basel zone", r.basel_zone],
                    ["Confidence", r.confidence_level],
                    ["Horizon (d)", r.horizon_days],
                  ]}
                />
              </GovernedValue>
            ))}
          </>
        )}
      </Pane>

      <h3>ES backtests</h3>
      <Pane
        state={esBt}
        requires="risk.view"
        empty={
          <p className="state">
            No ES backtest for this book in this seed (a later demo stage seeds it). When present,
            the Acerbi–Székely verdict is <strong>domain-gated</strong> — evidence with no verdict
            off the (α, T) domain.
          </p>
        }
      >
        {(rows) => (
          <>
            {rows.map((r) => (
              <GovernedValue
                key={r.id}
                label={`ES backtest · ${verbatim(r.metric_type)} · ${verbatim(r.period_start)} → ${verbatim(r.period_end)}`}
                value={
                  verbatim(r.test_decision) === "—"
                    ? "evidence only — no off-domain verdict"
                    : r.test_decision
                }
                provenance={{ runId: r.calculation_run_id, modelVersionId: r.model_version_id }}
              >
                <BacktestFacts
                  facts={[
                    ["Exceptions", `${verbatim(r.n_exceptions)} / ${verbatim(r.n_pairs)}`],
                    ["ES value", r.es_value],
                    ["Confidence", r.confidence_level],
                  ]}
                />
              </GovernedValue>
            ))}
          </>
        )}
      </Pane>
    </>
  );
}
