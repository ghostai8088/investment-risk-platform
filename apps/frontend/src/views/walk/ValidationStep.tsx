import type { ReactElement } from "react";

import { shortId, verbatim } from "../../api/format";
import { ValidationBadge } from "../../components/ValidationBadge";
import type { DevSession } from "../../session";
import { useModelValidations } from "../../walk/useModelValidations";
import type { ValidationCard } from "../../walk/useModelValidations";

/**
 * Walk step 5 — Validation status (FE-3, OD-FE-3-A). Independent review of the models behind the
 * numbers, with the findings and evidence made visible — the F2 governance reads that were
 * write-only before API-1. Degrades to a calm note without `model.inventory.view`.
 */
export function ValidationStep({ session }: { session: DevSession }): ReactElement {
  const v = useModelValidations(session);

  if (v.loading) return <p className="state">Loading validations…</p>;
  if (v.error) {
    return v.error.kind === "forbidden" ? (
      <p className="state denied">
        The validation records need the “model.inventory.view” permission.
      </p>
    ) : (
      <p className="state error">Could not load validations: {v.error.message}</p>
    );
  }

  return (
    <>
      <p className="muted">
        Independent review of the models behind the numbers — the findings and the evidence that
        backed each sign-off, first-class.
      </p>
      {v.cards.length === 0 ? (
        <p className="state">No validations filed yet.</p>
      ) : (
        v.cards.map((card) => <ValidationCardView key={card.detail.id} card={card} />)
      )}
    </>
  );
}

function ValidationCardView({ card }: { card: ValidationCard }): ReactElement {
  const d = card.detail;
  return (
    <div className="validation-card">
      <div className="vc-head">
        <h3>{card.modelCode}</h3>
        <ValidationBadge info={{ tier: card.tier, outcome: d.outcome, overdue: null }} />
        <span className="badge muted">{verbatim(d.validation_type)}</span>
      </div>
      {d.scope_summary ? <p className="muted">{verbatim(d.scope_summary)}</p> : null}
      {d.conditions ? (
        <p>
          <strong>Conditions:</strong> {verbatim(d.conditions)}
        </p>
      ) : null}

      <h4>Findings ({d.findings.length})</h4>
      {d.findings.length === 0 ? (
        <p className="state">None recorded.</p>
      ) : (
        <ul className="findings">
          {d.findings.map((f) => (
            <li key={f.id}>
              <span className={`badge sev-${(f.severity ?? "").toLowerCase()}`}>
                {verbatim(f.severity)}
              </span>{" "}
              {verbatim(f.finding_text)} <em>— {verbatim(f.authored_by)}</em>
            </li>
          ))}
        </ul>
      )}

      <h4>Evidence ({d.evidence.length})</h4>
      {d.evidence.length === 0 ? (
        <p className="state">None recorded.</p>
      ) : (
        <ul className="evidence">
          {d.evidence.map((e) => (
            <li key={e.id}>
              <span className="badge muted">{verbatim(e.evidence_type)}</span>{" "}
              {e.run_id ? (
                <>
                  run <span className="mono">{shortId(e.run_id)}</span> —{" "}
                </>
              ) : null}
              {verbatim(e.reference)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
