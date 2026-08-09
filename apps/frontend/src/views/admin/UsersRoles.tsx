import { useState } from "react";
import type { ReactElement } from "react";

import { ApiError } from "../../api/client";
import { useApiGet } from "../../api/useApiGet";
import { verbatim } from "../../api/format";
import {
  approveEntitlementRequest,
  createUser,
  deactivateUser,
  grantRole,
  revokeRole,
} from "../../api/writes";
import type { EntitlementRequestOut } from "../../api/writes";
import type { components } from "../../api/generated/api-types";
import type { Session } from "../../session";
import { Refusal, explain } from "../ops/Refusal";

type UserOut = components["schemas"]["UserOut"];
type RoleOut = components["schemas"]["RoleOut"];

/**
 * Users & Roles (ONBOARD-1b, remit outcome 6) — the tenant administers itself.
 *
 * The load-bearing rule of this screen: **the four-eyes outcome is in the RESPONSE BODY, not the
 * status code.** A grant that took effect and a grant that was queued for a second administrator
 * both return 200; `status` says which happened, and this screen renders that verdict every time
 * rather than letting a 200 read as "done". A PENDING act has NOT happened.
 *
 * The screen holds NO permission knowledge (the FE convention since OPS-1): every refusal —
 * self-approval (SOD-04), orphaning the last admin, a duplicate subject — is the server's, and is
 * rendered in plain language rather than pre-empted client-side. The one thing the client refuses
 * to do is default a governed input.
 */

/** What a write's `EntitlementRequestOut` means for the person who clicked the button. */
function outcomeText(row: EntitlementRequestOut): string {
  if (row.status === "PENDING") {
    return "Queued for four-eyes: a second administrator must approve before this takes effect.";
  }
  if (row.status === "DIRECT") {
    return "Applied directly — you are the only administrator, and the act is flagged as such in the audit chain.";
  }
  return "Approved — the requested change has taken effect.";
}

function actionLabel(action: string): string {
  if (action === "GRANT_ROLE") return "grant role";
  if (action === "REVOKE_ROLE") return "revoke role";
  return "deactivate user";
}

export function UsersRoles({ session }: { session: Session }): ReactElement {
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<ApiError | null>(null);
  const [outcome, setOutcome] = useState<string | null>(null);

  const [subject, setSubject] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [roleByUser, setRoleByUser] = useState<Record<string, string>>({});

  const users = useApiGet<UserOut[]>("/users", session, reload);
  const roles = useApiGet<RoleOut[]>("/roles", session, reload);
  const pending = useApiGet<EntitlementRequestOut[]>("/entitlement-requests", session, reload);

  const roster = users.data ?? [];
  const nameById = new Map(roster.map((u) => [u.id, u.display_name]));
  const roleById = new Map((roles.data ?? []).map((r) => [r.id, r.code]));
  const roleIdByCode = new Map((roles.data ?? []).map((r) => [r.code, r.id]));

  async function run(key: string, act: () => Promise<EntitlementRequestOut | null>): Promise<void> {
    setBusy(key);
    setWriteError(null);
    setOutcome(null);
    try {
      const row = await act();
      if (row) setOutcome(outcomeText(row));
      setReload((n) => n + 1);
    } catch (e: unknown) {
      setWriteError(e instanceof ApiError ? e : new ApiError("network", String(e)));
    } finally {
      setBusy(null);
    }
  }

  async function addUser(): Promise<void> {
    setBusy("create");
    setWriteError(null);
    setOutcome(null);
    try {
      await createUser(session, {
        externalSubject: subject.trim(),
        displayName: displayName.trim(),
      });
      setSubject("");
      setDisplayName("");
      setOutcome(
        "User created. They hold no roles — and therefore no authority — until granted one.",
      );
      setReload((n) => n + 1);
    } catch (e: unknown) {
      setWriteError(e instanceof ApiError ? e : new ApiError("network", String(e)));
    } finally {
      setBusy(null);
    }
  }

  const queue = pending.data ?? [];

  return (
    <section className="ops-view">
      <header className="ops-header">
        <h2>Users &amp; Roles</h2>
        <p className="ops-lede">
          Who can act in this tenant, and with what authority. Entitlement changes are maker-checked
          (SOD-04): with a second administrator present, a grant, revocation or admin-deactivation
          only takes effect once <strong>another</strong> administrator approves it.
        </p>
      </header>

      {writeError ? <Refusal error={writeError} action="change entitlements" /> : null}
      {outcome ? (
        <p className="state" role="status">
          {outcome}
        </p>
      ) : null}

      {/* --- the four-eyes queue ------------------------------------------------------------ */}
      <div className="ops-panel">
        <h3>Awaiting a second administrator</h3>
        <p className="ops-lede">
          These requests have <strong>not taken effect</strong>. You cannot approve your own — the
          server refuses it, by principal, and that refusal is the control.
        </p>
        {pending.error ? (
          <p className="state error" role="alert">
            {explain(pending.error, "view the approval queue")}
          </p>
        ) : null}
        {queue.length === 0 && !pending.loading ? (
          <p className="state">Nothing awaiting approval.</p>
        ) : null}
        {queue.length > 0 ? (
          <table className="ops-table">
            <thead>
              <tr>
                <th scope="col">#</th>
                <th scope="col">Requested act</th>
                <th scope="col">Target</th>
                <th scope="col">Requested by</th>
                <th scope="col" />
              </tr>
            </thead>
            <tbody>
              {queue.map((q) => (
                <tr key={q.id}>
                  <td className="mono num">{q.seq}</td>
                  <th scope="row">
                    {actionLabel(q.action)}
                    {q.target_role_id ? (
                      <span className="cell-sub">
                        {verbatim(roleById.get(q.target_role_id) ?? q.target_role_id)}
                      </span>
                    ) : null}
                  </th>
                  <td>{verbatim(nameById.get(q.target_user_id) ?? q.target_user_id)}</td>
                  <td className="mono">{verbatim(q.requested_by)}</td>
                  <td>
                    <button
                      type="button"
                      disabled={busy !== null}
                      onClick={() => void run(q.id, () => approveEntitlementRequest(session, q.id))}
                    >
                      {busy === q.id ? "Approving…" : "Approve"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>

      {/* --- create a user ------------------------------------------------------------------ */}
      <div className="ops-panel">
        <h3>Create a user</h3>
        <p className="ops-lede">
          Creation is not gated: a user with no roles holds no authority. The grant that would give
          them authority is what four-eyes watches.
        </p>
        <label className="ops-field">
          Sign-in subject
          <input
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            maxLength={255}
            placeholder="e.g. jane.doe@yourfirm.com"
            required
          />
          <span className="cell-sub">
            Must match the identity your sign-in provider presents for them.
          </span>
        </label>
        <label className="ops-field">
          Display name
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            maxLength={255}
            required
          />
        </label>
        <button
          type="button"
          disabled={busy !== null || !subject.trim() || !displayName.trim()}
          onClick={() => void addUser()}
        >
          {busy === "create" ? "Creating…" : "Create user"}
        </button>
      </div>

      {/* --- the roster --------------------------------------------------------------------- */}
      <div className="ops-panel">
        <h3>Roster</h3>
        {users.error ? (
          <p className="state error" role="alert">
            {explain(users.error, "view users")}
          </p>
        ) : null}
        {users.loading ? <p className="state">Loading users…</p> : null}
        {roster.length > 0 ? (
          <table className="ops-table">
            <thead>
              <tr>
                <th scope="col">User</th>
                <th scope="col">Status</th>
                <th scope="col">Roles</th>
                <th scope="col">Grant a role</th>
                <th scope="col" />
              </tr>
            </thead>
            <tbody>
              {roster.map((u) => (
                <tr key={u.id}>
                  <th scope="row">
                    {verbatim(u.display_name)}
                    <span className="cell-sub mono">{u.external_subject ?? "—"}</span>
                  </th>
                  <td>
                    <span className={u.is_active ? "chip chip-ok" : "chip chip-muted"}>
                      {u.is_active ? "ACTIVE" : "DEACTIVATED"}
                    </span>
                  </td>
                  <td>
                    {u.roles.length === 0 ? (
                      <span className="cell-sub">no roles — no authority</span>
                    ) : (
                      u.roles.map((code) => {
                        const rid = roleIdByCode.get(code);
                        return (
                          <span key={code} className="chip chip-muted">
                            {verbatim(code)}{" "}
                            {rid ? (
                              <button
                                type="button"
                                className="chip-action"
                                disabled={busy !== null}
                                aria-label={`revoke ${code} from ${u.display_name}`}
                                onClick={() =>
                                  void run(`revoke:${u.id}:${rid}`, () =>
                                    revokeRole(session, u.id, rid),
                                  )
                                }
                              >
                                revoke
                              </button>
                            ) : null}
                          </span>
                        );
                      })
                    )}
                  </td>
                  <td>
                    <span className="ops-grant">
                      <select
                        aria-label={`role to grant to ${u.display_name}`}
                        value={roleByUser[u.id] ?? ""}
                        onChange={(e) => setRoleByUser((m) => ({ ...m, [u.id]: e.target.value }))}
                      >
                        <option value="">choose a role…</option>
                        {(roles.data ?? []).map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.code}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        disabled={busy !== null || !roleByUser[u.id]}
                        onClick={() =>
                          void run(`grant:${u.id}`, () =>
                            grantRole(session, u.id, { roleId: roleByUser[u.id] }),
                          )
                        }
                      >
                        {busy === `grant:${u.id}` ? "Granting…" : "Grant"}
                      </button>
                    </span>
                  </td>
                  <td>
                    {u.is_active ? (
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() =>
                          void run(`deactivate:${u.id}`, () => deactivateUser(session, u.id))
                        }
                      >
                        {busy === `deactivate:${u.id}` ? "Deactivating…" : "Deactivate"}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
        {roster.length === 0 && !users.loading && !users.error ? (
          <p className="state">No users in this tenant.</p>
        ) : null}
      </div>
    </section>
  );
}
