import { useState } from "react";
import type { ReactElement } from "react";

import { shortId, verbatim } from "../../api/format";
import type { ExposureRow, FactorExposureRow } from "../../api/types";
import { useApiGet } from "../../api/useApiGet";
import { Pane } from "../../components/Pane";
import type { Session } from "../../session";

/**
 * Walk step 2 — Exposures (FE-3, OD-FE-3-A). What the book is exposed to: the governed factor
 * exposures (the currency-only factor set — the seed of the limitation the walk discloses later)
 * and the exposure aggregate. Factor-exposure rows share one run/model, shown as provenance once.
 *
 * STRUCT-1 (REQ-PPM-006): one holding can carry more than one exposure MEASURE. The grid gains a
 * measure filter (served by the API's `exposure_type` param — the same filter a consumer uses),
 * and any holding carrying BOTH measures renders side by side with the difference, so the two
 * numbers for one holding id are a thing a human can SEE, not only an API shape.
 */
const MEASURES = ["ALL", "MARKET_VALUE", "NOTIONAL"] as const;

export function ExposuresStep({
  session,
  portfolioId,
}: {
  session: Session;
  portfolioId: string;
}): ReactElement {
  const pf = encodeURIComponent(portfolioId);
  const [measure, setMeasure] = useState<(typeof MEASURES)[number]>("ALL");
  const factors = useApiGet<FactorExposureRow[]>(
    `/risk/factor-exposures/latest?portfolio_id=${pf}`,
    session,
  );
  const exposure = useApiGet<ExposureRow[]>(
    `/exposure/latest?portfolio_id=${pf}${measure === "ALL" ? "" : `&exposure_type=${measure}`}`,
    session,
  );

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
      <label>
        Measure{" "}
        <select
          value={measure}
          onChange={(e) => setMeasure(e.target.value as (typeof MEASURES)[number])}
        >
          {MEASURES.map((m) => (
            <option key={m} value={m}>
              {m === "ALL" ? "All measures" : m}
            </option>
          ))}
        </select>
      </label>
      <Pane
        state={exposure}
        requires="exposure.view"
        empty={<p className="state">No exposure rows.</p>}
      >
        {(rows) => {
          const byHolding = new Map<string, ExposureRow[]>();
          for (const r of rows) {
            const key = `${r.portfolio_id ?? ""}:${r.instrument_id ?? ""}`;
            byHolding.set(key, [...(byHolding.get(key) ?? []), r]);
          }
          const twoMeasure = [...byHolding.values()].filter((hs) => hs.length > 1);
          return (
            <>
              {measure === "ALL" && twoMeasure.length > 0 && (
                <>
                  <h4>Holdings carrying two measures</h4>
                  <table>
                    <thead>
                      <tr>
                        <th>Instrument</th>
                        <th>Notional</th>
                        <th>Market value</th>
                        <th>Difference</th>
                      </tr>
                    </thead>
                    <tbody>
                      {twoMeasure.map((hs) => {
                        const notional = hs.find((r) => r.exposure_type === "NOTIONAL");
                        const mv = hs.find((r) => r.exposure_type === "MARKET_VALUE");
                        const diff =
                          notional && mv
                            ? (
                                Number(mv.exposure_amount) - Number(notional.exposure_amount)
                              ).toFixed(6)
                            : "—";
                        return (
                          <tr key={hs[0].id}>
                            <td className="mono" title={hs[0].instrument_id ?? undefined}>
                              {hs[0].instrument_id ? shortId(hs[0].instrument_id) : "—"}
                            </td>
                            <td className="mono">
                              {notional ? verbatim(notional.exposure_amount) : "—"}
                            </td>
                            <td className="mono">{mv ? verbatim(mv.exposure_amount) : "—"}</td>
                            {/* Display-only convenience (float arithmetic); the governed values
                                are the verbatim decimal strings in the two columns beside it. */}
                            <td className="mono">{diff}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </>
              )}
              <table>
                <thead>
                  <tr>
                    <th>Instrument</th>
                    <th>Measure</th>
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
            </>
          );
        }}
      </Pane>
    </>
  );
}
