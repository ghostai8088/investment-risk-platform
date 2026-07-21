import type { ReactElement } from "react";

import { shortId, verbatim } from "../../api/format";
import type { Position, Valuation } from "../../api/types";
import { useApiGet } from "../../api/useApiGet";
import { Pane } from "../../components/Pane";
import type { DevSession } from "../../session";

/**
 * Walk step 1 — Capture (FE-3, OD-FE-3-A). The book's raw inputs: the captured positions and the
 * valuation marks every downstream governed number binds to. Each region degrades independently on
 * a missing `position.view` / `valuation.view` grant (OD-E). Decimals render verbatim.
 */
export function CaptureStep({
  session,
  portfolioId,
}: {
  session: DevSession;
  portfolioId: string;
}): ReactElement {
  const pf = encodeURIComponent(portfolioId);
  const positions = useApiGet<Position[]>(`/positions?portfolio_id=${pf}`, session);
  const valuations = useApiGet<Valuation[]>(`/valuations?portfolio_id=${pf}`, session);

  return (
    <>
      <p className="muted">
        Everything downstream binds to what was captured here. These are the inputs, not a
        calculation — no model has run yet.
      </p>

      <h3>Positions</h3>
      <Pane state={positions} requires="position.view" empty={<p className="state">No positions.</p>}>
        {(rows) => (
          <table>
            <thead>
              <tr>
                <th>Instrument</th>
                <th>Quantity</th>
                <th>As of</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="mono" title={r.instrument_id}>
                    {shortId(r.instrument_id)}
                  </td>
                  <td className="mono">{verbatim(r.quantity)}</td>
                  <td>{verbatim(r.valid_from)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Pane>

      <h3>Valuation marks</h3>
      <Pane
        state={valuations}
        requires="valuation.view"
        empty={<p className="state">No valuation marks.</p>}
      >
        {(rows) => (
          <table>
            <thead>
              <tr>
                <th>Instrument</th>
                <th>Valued</th>
                <th>Mark</th>
                <th>Ccy</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="mono" title={r.instrument_id}>
                    {shortId(r.instrument_id)}
                  </td>
                  <td>{verbatim(r.valuation_date)}</td>
                  <td className="mono">{verbatim(r.mark_value)}</td>
                  <td>{verbatim(r.currency_code)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Pane>
    </>
  );
}
