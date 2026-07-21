import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import { shortId, verbatim } from "../api/format";

export interface Provenance {
  runId?: string | null;
  snapshotId?: string | null;
  modelVersionId?: string | null;
  codeVersion?: string | null;
}

/**
 * A governed number rendered with its trust context INLINE (OD-FE-3-C) — the value verbatim (never
 * `Number()`'d) plus a provenance strip (snapshot / run / model version / code) and an optional
 * snapshot-verify mark and lineage affordance. This is "verifiability as the product" in one
 * component: every number shows what it traces to, not behind a click. The validation badge and
 * disclosed limitations are composed alongside by the walk views.
 */
export function GovernedValue({
  label,
  value,
  provenance,
  snapshotVerified,
  auditHref,
  children,
}: {
  label: string;
  value: string | number | null | undefined;
  provenance?: Provenance;
  /** null = not checked / not entitled; true/false = the /verify result. */
  snapshotVerified?: boolean | null;
  auditHref?: string;
  children?: ReactElement | ReactElement[];
}): ReactElement {
  return (
    <div className="governed-value">
      <div className="gv-head">
        <span className="gv-label">{label}</span>
        <span className="gv-number mono">{verbatim(value)}</span>
      </div>

      {provenance ? (
        <dl className="provenance-strip">
          {provenance.snapshotId ? (
            <div className="prov-item">
              <dt>Snapshot</dt>
              <dd className="mono" title={provenance.snapshotId}>
                {shortId(provenance.snapshotId)}
                {snapshotVerified === true ? (
                  <span className="verify ok" role="status">
                    {" "}
                    ✓ reproduces
                  </span>
                ) : null}
                {snapshotVerified === false ? (
                  <span className="verify bad" role="status">
                    {" "}
                    ✗ mismatch
                  </span>
                ) : null}
              </dd>
            </div>
          ) : null}
          {provenance.runId ? (
            <div className="prov-item">
              <dt>Run</dt>
              <dd className="mono" title={provenance.runId}>
                {shortId(provenance.runId)}
              </dd>
            </div>
          ) : null}
          {provenance.modelVersionId ? (
            <div className="prov-item">
              <dt>Model version</dt>
              <dd className="mono" title={provenance.modelVersionId}>
                {shortId(provenance.modelVersionId)}
              </dd>
            </div>
          ) : null}
          {provenance.codeVersion ? (
            <div className="prov-item">
              <dt>Code</dt>
              <dd className="mono">{provenance.codeVersion}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}

      {children}

      {auditHref ? (
        <p className="gv-audit">
          <Link to={auditHref}>Lineage &amp; audit →</Link>
        </p>
      ) : null}
    </div>
  );
}
