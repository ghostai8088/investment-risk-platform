import type { ReactElement } from "react";

import type { Session } from "../../session";
import { useModelIndex } from "../../walk/useModelIndex";

/**
 * Walk step 6 — Disclosed limitations (FE-3, OD-FE-3-A). What each model deliberately cannot see —
 * declared, not discovered. The honesty about the edges of every number (e.g. the currency-only
 * factor model cannot see the equity drawdown captured on 2026-05-22). Reuses the model index.
 */
export function LimitationsStep({ session }: { session: Session }): ReactElement {
  const m = useModelIndex(session);

  if (m.loading) return <p className="state">Loading limitations…</p>;
  if (m.error) {
    return m.error.kind === "forbidden" ? (
      <p className="state denied">
        The disclosed limitations need the “model.inventory.view” permission.
      </p>
    ) : (
      <p className="state error">Could not load limitations: {m.error.message}</p>
    );
  }

  const byModel = new Map<string, { tier: string | null; limitations: string[] }>();
  for (const e of m.entries.values()) {
    if (e.limitations.length > 0 && !byModel.has(e.modelCode)) {
      byModel.set(e.modelCode, { tier: e.tier, limitations: e.limitations });
    }
  }
  const groups = [...byModel.entries()].sort((a, b) => a[0].localeCompare(b[0]));

  return (
    <>
      <p className="muted">
        What each model deliberately cannot see — declared, not discovered. The currency-only factor
        model, for instance, cannot see the equity drawdown captured on 2026-05-22: that is stated
        here, not hidden.
      </p>
      {groups.length === 0 ? (
        <p className="state">No disclosed limitations.</p>
      ) : (
        groups.map(([code, g]) => (
          <div className="limitation-group" key={code}>
            <h3>
              {code}{" "}
              {g.tier ? <span className="badge tier">{g.tier.replace(/_/g, " ")}</span> : null}
            </h3>
            <ul className="limitations-list">
              {g.limitations.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          </div>
        ))
      )}
    </>
  );
}
