import type { ReactElement } from "react";

import { shortId, verbatim } from "../../api/format";
import type { ExposureRow, FactorExposureRow } from "../../api/types";
import { useApiGet } from "../../api/useApiGet";
import { Pane } from "../../components/Pane";
import type { DevSession } from "../../session";

/**
 * Walk step 2 — Exposures (FE-3, OD-FE-3-A). What the book is exposed to: the governed factor
 * exposures (the currency-only factor set — the seed of the limitation the walk discloses later)
 * and the exposure aggregate. Factor-exposure rows share one run/model, shown as provenance once.
 */
export function ExposuresStep({
  session,
  portfolioId,
}: {
  session: DevSession;
  portfolioId: string;
}): ReactElement {
  const pf = encodeURIComponent(portfolioId);
  const factors = useApiGet<FactorExposureRow[]>(
    `/risk/factor-exposures/latest?portfolio_id=${pf}`,
    session,
  );
  const exposure = useApiGet<ExposureRow[]>(`/exposure/latest?portfolio_id=${pf}`, session);

  return (
    <>
      <h3>Factor exposures</h3>
      <Pane
        state={factors}
        requires="risk.view"
        empty={<p className="state">No factor exposures.</p>}
      >
        {(rows) => (
          <>
            <p className="prov-line">
              From run{" "}
              <span className="mono" title={rows[0].calculation_run_id}>
                {shortId(rows[0].calculation_run_id)}
              </span>{" "}
              · model version{" "}
              <span className="mono" title={rows[0].model_version_id ?? undefined}>
                {rows[0].model_version_id ? shortId(rows[0].model_version_id) : "—"}
              </span>
            </p>
            <table>
              <thead>
                <tr>
                  <th>Instrument</th>
                  <th>Factor</th>
                  <th>Family</th>
                  <th>Loading</th>
                  <th>Exposure</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="mono" title={r.instrument_id ?? undefined}>
                      {r.instrument_id ? shortId(r.instrument_id) : "—"}
                    </td>
                    <td>{verbatim(r.factor_code)}</td>
                    <td>{verbatim(r.factor_family)}</td>
                    <td className="mono">{verbatim(r.loading)}</td>
                    <td className="mono">{verbatim(r.exposure_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Pane>

      <h3>Exposure aggregate</h3>
      <Pane
        state={exposure}
        requires="exposure.view"
        empty={<p className="state">No exposure rows.</p>}
      >
        {(rows) => (
          <table>
            <thead>
              <tr>
                <th>Instrument</th>
                <th>Type</th>
                <th>Mark</th>
                <th>Exposure</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="mono" title={r.instrument_id ?? undefined}>
                    {r.instrument_id ? shortId(r.instrument_id) : "—"}
                  </td>
                  <td>{verbatim(r.exposure_type)}</td>
                  <td className="mono">{verbatim(r.mark_value)}</td>
                  <td className="mono">{verbatim(r.exposure_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Pane>
    </>
  );
}
