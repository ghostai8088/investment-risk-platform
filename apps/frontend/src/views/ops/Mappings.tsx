import { useState } from "react";
import type { ReactElement } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../../api/client";
import { useApiGet } from "../../api/useApiGet";
import { verbatim } from "../../api/format";
import { ratifyMappingVersion, withdrawMappingVersion } from "../../api/writes";
import { Pane } from "../../components/Pane";
import type { components } from "../../api/generated/api-types";
import type { Session } from "../../session";

type MappingVersion = components["schemas"]["MappingVersionOut"];
type Batch = components["schemas"]["BatchOut"];
type LineageEdges = components["schemas"]["LineageEdgesOut"];

/** W19-S3a (REQ-INT-001): the ENT-077 mapping read surface — Rule 7's entity/time reads.
 *
 * The screen a human opens to answer "what does this file mean, who said so, and who agreed?"
 * That is the whole INGEST-1 thesis made inspectable: the AI proposes, a human ratifies, the
 * platform executes the ratified version forever.
 *
 * W19-S3b makes it ACTABLE. S3a left this screen read-only on purpose — it minted no permission
 * code, and a ratify button would have been a checker verb sharing an upload permission with the
 * maker path (DS3a-1). S3b's R-07 mint gives the verbs their own codes, so the checker can now act
 * here.
 *
 * The three reads also MOVED off `data.upload` onto `ingest.mapping.view`. That re-gating is the
 * reason the third code exists: every /ingest read was gated on the MAKER's upload permission, so a
 * ratifier-only holder was refused the very screens showing what they were about to approve. A
 * checker who cannot read the artifact is not a checker (DS3b-2). The `requires` strings below name
 * the code the backend actually enforces — a `Pane` naming the wrong one tells a denied operator to
 * request a permission that would not have helped. */
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
        requires="ingest.mapping.view"
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
  const [reload, setReload] = useState(0);
  const version = useApiGet<MappingVersion>(`/ingest/mappings/${mappingId ?? ""}`, session, reload);
  const batches = useApiGet<Batch[]>(
    `/ingest/mappings/${mappingId ?? ""}/batches`,
    session,
    reload,
  );

  return (
    <section>
      <h2>Mapping version</h2>
      <Pane
        state={version}
        requires="ingest.mapping.view"
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

            <Decision
              session={session}
              mappingId={mappingId ?? ""}
              status={row.status}
              onDone={() => {
                setReload((n) => n + 1);
              }}
            />

            <h3>Batches loaded under this version</h3>
            <Pane
              state={batches}
              requires="ingest.mapping.view"
              empty={<p className="state">No file has been loaded under this version.</p>}
            >
              {(loaded) => <BatchTable rows={loaded} session={session} />}
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

function BatchTable({ rows, session }: { rows: Batch[]; session: Session }): ReactElement {
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
          <th>Where it came from</th>
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
            <td>
              <BatchLineage batchId={row.id} session={session} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** The CHECKER's controls — the four-eyes decision, made on the screen that shows the artifact.
 *
 * Only rendered for a PROPOSED version, because those are the only two verbs a proposal admits.
 * There is deliberately no REJECT button: a checker's refusal to ratify is inaction and leaves the
 * version PROPOSED for someone else to look at. WITHDRAW is the PROPOSER's own act of taking a
 * proposal back, gated on the propose code rather than the ratify one — a checker who could
 * withdraw would be rejecting under another name.
 *
 * A 409 here is NOT a permission problem and is worded so: the caller holds the code and is refused
 * on who they are relative to THIS proposal (they proposed it; or they are not the proposer trying
 * to withdraw it). Telling them to request a permission they already hold would send them nowhere.
 */
function Decision({
  session,
  mappingId,
  status,
  onDone,
}: {
  session: Session;
  mappingId: string;
  status: string;
  onDone: () => void;
}): ReactElement | null {
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState<"ratify" | "withdraw" | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  if (status !== "PROPOSED") return null;

  async function run(kind: "ratify" | "withdraw", fn: () => Promise<unknown>): Promise<void> {
    setPending(kind);
    setError(null);
    try {
      await fn();
      setReason("");
      onDone();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e : new ApiError("network", String(e)));
    } finally {
      setPending(null);
    }
  }

  return (
    <>
      <h3>Decision</h3>
      <p className="prov-line">
        A mapping version is ratified by someone other than the person who proposed it. The platform
        refuses a self-ratification rather than relying on anyone to remember the rule.
      </p>
      <label>
        Reason (required to withdraw)
        <input
          type="text"
          value={reason}
          onChange={(e) => {
            setReason(e.target.value);
          }}
        />
      </label>
      <button
        type="button"
        disabled={pending !== null}
        onClick={() => {
          void run("ratify", () => ratifyMappingVersion(session, mappingId, reason || undefined));
        }}
      >
        {pending === "ratify" ? "Ratifying…" : "Ratify this version"}
      </button>
      <button
        type="button"
        disabled={pending !== null || reason.trim() === ""}
        onClick={() => {
          void run("withdraw", () => withdrawMappingVersion(session, mappingId, reason));
        }}
      >
        {pending === "withdraw" ? "Withdrawing…" : "Withdraw my proposal"}
      </button>
      {error !== null && (
        <p className="state error" role="alert">
          {explainDecision(error)}
        </p>
      )}
    </>
  );
}

/** What the refusal MEANT, and therefore what to do about it.
 *
 * `classifyRefusal` is deliberately NOT used here, and a review is why. Its three markers are
 * pinned to the BREACH domain's error map ("separation of duties", "reload and retry", "illegal
 * transition") by `refusal-contract.test.ts`. The mapping router's three conflict details match
 * none of them, so every mapping 409 fell through to "other" and the branch that looked like it
 * was discriminating was doing nothing at all. Borrowing a classifier whose contract is pinned to
 * another domain's strings is how a UI ends up silently generic.
 *
 * A mapping 409 has exactly two causes — you proposed this and may not ratify it, or you did not
 * propose it and may not withdraw it — and both have the SAME remedy. So this says that plainly
 * instead of pretending to discriminate. */
function explainDecision(error: ApiError): string {
  if (error.kind === "forbidden") {
    return "You need the “ingest.mapping.ratify” permission to ratify, or “ingest.mapping.propose” to withdraw.";
  }
  if (error.kind === "conflict") {
    // The caller HAS the code. The act is refused on who they are relative to THIS proposal.
    return `${error.message} — this is not a permission problem, and a retry will not change it. Someone else must act on this proposal.`;
  }
  return error.message;
}

/** The by-target lineage read, hung off the batch that produced the rows.
 *
 * `/lineage` had exactly one endpoint until W19-S3b, keyed on an edge id that no endpoint returned
 * and no listing produced — live, gated, and unreachable. This is the first place in the SPA that
 * fetches it at all. Kept to a count plus the source kinds: the full graph is an audit surface, and
 * the question this cell answers is the ordinary one, "is this batch's origin recorded?".
 */
function BatchLineage({ batchId, session }: { batchId: string; session: Session }): ReactElement {
  const edges = useApiGet<LineageEdges>(`/lineage/targets/ingestion_batch/${batchId}`, session);
  if (edges.loading) return <span className="state">…</span>;
  if (edges.error !== null) {
    return (
      <span className="state denied">
        {edges.error.kind === "forbidden" ? "needs lineage.view" : edges.error.message}
      </span>
    );
  }
  const rows = edges.data?.edges ?? [];
  if (rows.length === 0) {
    // Honest-empty. "No lineage recorded" is a real finding about a loaded batch, not a blank.
    return <span className="state">no lineage recorded</span>;
  }
  const kinds = [...new Set(rows.map((e) => e.source_type))].sort().join(", ");
  return (
    <span className="mono">
      {rows.length} edge{rows.length === 1 ? "" : "s"} · {verbatim(kinds)}
      {edges.data?.truncated === true ? " · truncated" : ""}
    </span>
  );
}
