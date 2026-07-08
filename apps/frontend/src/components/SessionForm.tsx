import { useState } from "react";
import type { ReactElement } from "react";

import { isValidSessionId } from "../session";
import type { DevSession } from "../session";

/** The dev-session form (OD-FE-1-D): plain ids, no password field, "session" vocabulary. */
export function SessionForm({ onStart }: { onStart: (session: DevSession) => void }): ReactElement {
  const [userId, setUserId] = useState("");
  const [tenantId, setTenantId] = useState("");
  const trimmedUser = userId.trim();
  const trimmedTenant = tenantId.trim();
  const filled = trimmedUser !== "" && trimmedTenant !== "";
  const ready = isValidSessionId(trimmedUser) && isValidSessionId(trimmedTenant);

  return (
    <form
      className="session-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (ready) onStart({ userId: trimmedUser, tenantId: trimmedTenant });
      }}
    >
      <h2>Start a dev session</h2>
      <p>
        Enter the user id and tenant id to send as the development headers. The backend decides what
        this identity may see.
      </p>
      {filled && !ready ? (
        <p className="state error">
          Ids must be plain ASCII (letters, digits, hyphens — a pasted em-dash or curly quote cannot
          be sent as a header).
        </p>
      ) : null}
      <label>
        User id
        <input
          value={userId}
          onChange={(e) => {
            setUserId(e.target.value);
          }}
          placeholder="user id"
        />
      </label>
      <label>
        Tenant id
        <input
          value={tenantId}
          onChange={(e) => {
            setTenantId(e.target.value);
          }}
          placeholder="tenant id"
        />
      </label>
      <button type="submit" disabled={!ready}>
        Start dev session
      </button>
    </form>
  );
}
