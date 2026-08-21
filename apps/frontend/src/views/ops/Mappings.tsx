import type { ReactElement } from "react";
import { Link, useParams } from "react-router";

import { useApiGet } from "../../api/useApiGet";
import { verbatim } from "../../api/format";
import { Pane } from "../../components/Pane";
import type { components } from "../../api/generated/api-types";
import type { Session } from "../../session";

type MappingVersion = components["schemas"]["MappingVersionOut"];
type Batch = components["schemas"]["BatchOut"];

/** W19-S3a (REQ-INT-001): the ENT-077 mapping read surface — Rule 7's entity/time reads.
 *
 * The screen a human opens to answer "what does this file mean, who said so, and who agreed?"
 * That is the whole INGEST-1 thesis made inspectable: the AI proposes, a human ratifies, the
 * platform executes the ratified version forever.
 *
 * READ ONLY, and deliberately: S3a mints no permission code, so the propose/ratify verbs stay at
 * the service tier until S3b's governed R-07 mint gives them their own (DS3a-1). A ratify button
 * here would be a checker verb sharing an upload permission with the maker path. */
export function Mappings({ session }: { session: Session }): ReactElement {
  const versions = useApiGet<MappingVersion[]>("/ingest/mappings", session);

  return (
    <section>
      <h2>Source mappings</h2>
      <p className="prov-line">
        A positions file loads into canonical holdings only through a RATIFIED mapping version.
        Editing a mapping never edits it — a change mints a NEW version that supersedes the old one,
        and every loaded batch records which version interpreted it.
      </p>
      <Pane
        state={versions}
        requires="data.upload"
        empty={
          <p className="state">
            No mapping version has been proposed for this tenant. Until one is ratified, a positions
            file cannot load.
          </p>
        }
      >
        {(rows) => <VersionTable rows={rows} />}
      </Pane>
    </section>
  );
}

function VersionTable({ rows }: { rows: MappingVersion[] }): ReactElement {
  if (rows.length === 0) {
    // Honest-empty: an empty list is NOT an all-clear. Nothing can load in this state.
    return (
      <p className="state">
        No mapping version has been proposed for this tenant. Until one is ratified, a positions
        file cannot load.
      </p>
    );
  }
  return (
    <table>
      <thead>
        <tr>
          <th>Version</th>
          <th>Source type</th>
          <th>State</th>
          <th>Drafted by</th>
          <th>Proposed by</th>
          <th>Ratified by</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>
              <Link to={`/ops/mappings/${row.id}`}>{verbatim(row.version_label)}</Link>
            </td>
            <td className="mono">{verbatim(row.source_type)}</td>
            <td>
              <StatusCell status={row.status} />
            </td>
            <td>{authorshipLabel(row)}</td>
            <td className="mono">{verbatim(row.proposed_by_actor_id)}</td>
            {/* An un-ratified mapping must NOT render as though it were ratified — the blank cell
                would read as "nobody recorded", not as "nobody has agreed yet". */}
            <td className="mono">
              {row.ratified_by_actor_id === null ? (
                <span className="state">awaiting ratification</span>
              ) : (
                verbatim(row.ratified_by_actor_id)
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** The lifecycle state, spelled so PROPOSED never looks like a finished thing. */
function StatusCell({ status }: { status: string }): ReactElement {
  if (status === "RATIFIED") return <span>RATIFIED — files load through this version</span>;
  if (status === "PROPOSED") return <span className="state">PROPOSED — not yet in force</span>;
  if (status === "SUPERSEDED") return <span className="state">SUPERSEDED — historical</span>;
  return <span className="state">{verbatim(status)}</span>;
}

function authorshipLabel(row: MappingVersion): string {
  return row.authorship === "MODEL_PROPOSED" ? "a registered model" : "hand-authored";
}

/** The detail view: the operations a non-engineer can read, and the provenance behind them. */
export function MappingDetail({ session }: { session: Session }): ReactElement {
  const { mappingId } = useParams();
  const version = useApiGet<MappingVersion>(`/ingest/mappings/${mappingId ?? ""}`, session);
  const batches = useApiGet<Batch[]>(`/ingest/mappings/${mappingId ?? ""}/batches`, session);

  return (
    <section>
      <h2>Mapping version</h2>
      <Pane
        state={version}
        requires="data.upload"
        empty={<p className="state">No such mapping version is visible to you.</p>}
      >
        {(row) => (
          <>
            <table>
              <tbody>
                <tr>
                  <th>Version</th>
                  <td className="mono">{verbatim(row.version_label)}</td>
                </tr>
                <tr>
                  <th>State</th>
                  <td>
                    <StatusCell status={row.status} />
                  </td>
                </tr>
                <tr>
                  <th>Source type</th>
                  <td className="mono">{verbatim(row.source_type)}</td>
                </tr>
                <tr>
                  <th>Drafted by</th>
                  <td>{authorshipLabel(row)}</td>
                </tr>
                <tr>
                  <th>Proposing model version</th>
                  <td className="mono">
                    {row.proposer_model_version_id === null ? (
                      <span className="state">none — hand-authored</span>
                    ) : (
                      verbatim(row.proposer_model_version_id)
                    )}
                  </td>
                </tr>
                <tr>
                  {/* The hash is what makes the recorded provenance CHECKABLE rather than
                      asserted: it is the sha256 of the committed prompt artifact. */}
                  <th>Prompt identity</th>
                  <td className="mono">
                    {row.proposal_prompt_hash === null ? (
                      <span className="state">none — hand-authored</span>
                    ) : (
                      verbatim(row.proposal_prompt_hash)
                    )}
                  </td>
                </tr>
                <tr>
                  <th>Prompt artifact</th>
                  <td className="mono">{verbatim(row.proposal_prompt_ref)}</td>
                </tr>
                <tr>
                  <th>Proposed</th>
                  <td className="mono">
                    {verbatim(row.proposed_by_actor_id)} · {row.proposed_at}
                  </td>
                </tr>
                <tr>
                  <th>Ratified</th>
                  <td className="mono">
                    {row.ratified_by_actor_id === null ? (
                      <span className="state">not ratified — this version cannot load a file</span>
                    ) : (
                      `${row.ratified_by_actor_id} · ${row.ratified_at ?? ""}`
                    )}
                  </td>
                </tr>
                <tr>
                  <th>Operations hash</th>
                  <td className="mono">{verbatim(row.operations_hash)}</td>
                </tr>
              </tbody>
            </table>

            <h3>What this mapping does</h3>
            <p className="prov-line">
              A fixed vocabulary of seven operations, so this question always has a short answer. A
              file the vocabulary cannot express is refused by name rather than approximated.
            </p>
            <OperationTable operations={row.operations} />

            <h3>Batches loaded under this version</h3>
            <Pane
              state={batches}
              requires="data.upload"
              empty={<p className="state">No file has been loaded under this version.</p>}
            >
              {(loaded) => <BatchTable rows={loaded} />}
            </Pane>
          </>
        )}
      </Pane>
    </section>
  );
}

function OperationTable({ operations }: { operations: Record<string, unknown>[] }): ReactElement {
  if (operations.length === 0) {
    return <p className="state">This version declares no operations and can load nothing.</p>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Operation</th>
          <th>Canonical field</th>
          <th>Detail</th>
        </tr>
      </thead>
      <tbody>
        {operations.map((op, index) => (
          // ORDER is the identity here: the operations are an ordered list and a later one
          // overwrites an earlier one on the same target, so the index IS the meaningful key.
          <tr key={`${String(op.op ?? "")}-${String(op.target ?? "")}-${index}`}>
            <td className="mono">{index + 1}</td>
            <td className="mono">{verbatim(String(op.op ?? ""))}</td>
            <td className="mono">{verbatim(String(op.target ?? ""))}</td>
            <td className="mono">{describeOperation(op)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** One line a non-engineer can read. Never a JSON dump: "what did this mapping do?" is the
 * question the closed vocabulary exists to keep answerable. */
function describeOperation(op: Record<string, unknown>): string {
  const source = op.source === undefined ? "" : String(op.source);
  switch (op.op) {
    case "rename":
      return `take the "${source}" column as it is`;
    case "cast":
      return `read "${source}" as ${String(op.to ?? "decimal")}`;
    case "scale":
      return `multiply "${source}" by ${String(op.factor ?? "")}`;
    case "parse-date":
      return `read "${source}" as a date in format ${String(op.format ?? "")}`;
    case "code-lookup":
      return `resolve "${source}" as a ${String(op.scheme ?? "")} identifier`;
    case "constant":
      return `always ${JSON.stringify(op.value)}`;
    case "concatenate":
      return `join ${JSON.stringify(op.sources)} with "${String(op.separator ?? "")}"`;
    default:
      return "";
  }
}

function BatchTable({ rows }: { rows: Batch[] }): ReactElement {
  if (rows.length === 0) {
    return <p className="state">No file has been loaded under this version.</p>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>File</th>
          <th>State</th>
          <th>Rows staged</th>
          <th>Lookups resolved as of</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td className="mono">{verbatim(row.filename)}</td>
            <td className="mono">{verbatim(row.status)}</td>
            <td className="mono">{row.staged_count}</td>
            {/* The third input a re-run needs (clause 9). Blank would read as "no lookups", so an
                absent instant says so in words. */}
            <td className="mono">
              {row.lookup_as_of === null ? (
                <span className="state">not recorded</span>
              ) : (
                row.lookup_as_of
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
