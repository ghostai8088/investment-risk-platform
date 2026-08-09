/**
 * ONBOARD-1b: the Users & Roles screen.
 *
 * The behaviour that makes this a GOVERNANCE screen rather than a CRUD table is that the
 * four-eyes outcome lives in the response body — so the tests here pin exactly that: a 200 whose
 * body says PENDING must render as "not yet effective", a 200 whose body says DIRECT must render
 * the flagged bootstrap-window language, and a server refusal (self-approval, SOD-04) must reach
 * the operator as the server's own sentence, not a status code.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UsersRoles } from "./UsersRoles";
import type { Session } from "../../session";

const SESSION: Session = { kind: "dev", userId: "admin-1", tenantId: "t-1" };

const ADMIN = {
  id: "admin-1",
  display_name: "First Admin",
  external_subject: "first@acme",
  is_active: true,
  roles: ["tenant_admin"],
};
const PLAIN = {
  id: "user-2",
  display_name: "New Joiner",
  external_subject: "new@acme",
  is_active: true,
  roles: [],
};
const ROLES = [
  { id: "role-ta", code: "tenant_admin", name: "Tenant Admin" },
  { id: "role-an", code: "risk_analyst_1l", name: "Analyst (1L)" },
];
const PENDING_ROW = {
  id: "req-1",
  seq: 3,
  action: "GRANT_ROLE",
  status: "PENDING",
  requested_by: "admin-2",
  target_user_id: "user-2",
  target_role_id: "role-an",
  resolved_by: null,
  direct: false,
};

/** Route GETs to canned payloads; hand writes (POST/DELETE) to `onWrite`. Unmatched paths reject
 * loudly so a typo'd URL is not mistaken for an empty result (the ops.test.tsx idiom). */
function routeFetch(
  routes: Record<string, unknown>,
  onWrite?: (url: string, init: RequestInit) => unknown,
) {
  const fn = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST" || init?.method === "DELETE") {
      const body = onWrite ? onWrite(url, init) : {};
      const failure = body as { __status?: number; detail?: string };
      if (failure.__status) {
        return Promise.resolve({
          ok: false,
          status: failure.__status,
          json: () => Promise.resolve({ detail: failure.detail }),
        } as unknown as Response);
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(body),
      } as unknown as Response);
    }
    const key = Object.keys(routes).find((k) => url.startsWith(k));
    if (key === undefined) return Promise.reject(new Error(`unrouted ${url}`));
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(routes[key]),
    } as unknown as Response);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const READS = {
  "/users": [ADMIN, PLAIN],
  "/roles": ROLES,
  "/entitlement-requests": [PENDING_ROW],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("UsersRoles", () => {
  it("renders the roster, role chips, and the four-eyes queue with names resolved", async () => {
    routeFetch(READS);
    render(<UsersRoles session={SESSION} />);

    await waitFor(() => {
      expect(screen.getByText("First Admin")).toBeTruthy();
    });
    // "New Joiner" appears twice by design: the roster row AND the queue's target cell.
    expect(screen.getAllByText("New Joiner").length).toBe(2);
    // Role codes appear in chips AND in the grant <option> list — count, don't getBy.
    expect(screen.getAllByText("tenant_admin").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("no roles — no authority")).toBeTruthy();
    // The queue row resolves its target-user and role ids to human labels.
    expect(screen.getByText("grant role")).toBeTruthy();
    expect(screen.getAllByText("risk_analyst_1l").length).toBeGreaterThanOrEqual(2);
  });

  it("a 200 whose body says PENDING renders as NOT yet effective", async () => {
    routeFetch(READS, () => ({ ...PENDING_ROW, id: "req-9" }));
    render(<UsersRoles session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByLabelText("role to grant to New Joiner")).toBeTruthy();
    });

    fireEvent.change(screen.getByLabelText("role to grant to New Joiner"), {
      target: { value: "role-an" },
    });
    fireEvent.click(screen.getAllByText("Grant")[1]);

    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toContain("Queued for four-eyes");
    });
  });

  it("a 200 whose body says DIRECT renders the flagged bootstrap-window language", async () => {
    routeFetch(READS, () => ({ ...PENDING_ROW, id: "req-9", status: "DIRECT", direct: true }));
    render(<UsersRoles session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByLabelText("role to grant to New Joiner")).toBeTruthy();
    });

    fireEvent.change(screen.getByLabelText("role to grant to New Joiner"), {
      target: { value: "role-an" },
    });
    fireEvent.click(screen.getAllByText("Grant")[1]);

    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toContain("Applied directly");
    });
  });

  it("a self-approval refusal reaches the operator as the server's own sentence", async () => {
    routeFetch(READS, () => ({
      __status: 422,
      detail: "refused: an administrator cannot approve their own entitlement request (SOD-04)",
    }));
    render(<UsersRoles session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText("Approve")).toBeTruthy();
    });

    fireEvent.click(screen.getByText("Approve"));
    await waitFor(() => {
      expect(screen.getByText(/cannot approve their own entitlement request/)).toBeTruthy();
    });
  });

  it("revoking a role chip issues DELETE to the grant's own URL", async () => {
    const writes: Array<[string, string]> = [];
    const fetchFn = routeFetch(READS, (url, init) => {
      writes.push([init.method ?? "", url]);
      return { ...PENDING_ROW, id: "req-9", action: "REVOKE_ROLE" };
    });
    render(<UsersRoles session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByLabelText("revoke tenant_admin from First Admin")).toBeTruthy();
    });

    fireEvent.click(screen.getByLabelText("revoke tenant_admin from First Admin"));
    await waitFor(() => {
      expect(writes).toContainEqual(["DELETE", "/users/admin-1/roles/role-ta"]);
    });
    expect(fetchFn).toHaveBeenCalled();
  });

  it("creating a user sends the wire-shape body and refreshes the reads", async () => {
    let posted: unknown = null;
    const fetchFn = routeFetch(READS, (_url, init) => {
      posted = JSON.parse(String(init.body));
      return {
        id: "user-3",
        display_name: "Jane",
        external_subject: "jane@acme",
        is_active: true,
        roles: [],
      };
    });
    render(<UsersRoles session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByText("Create user")).toBeTruthy();
    });

    fireEvent.change(screen.getByPlaceholderText("e.g. jane.doe@yourfirm.com"), {
      target: { value: "jane@acme" },
    });
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Jane" } });
    fireEvent.click(screen.getByText("Create user"));

    await waitFor(() => {
      expect(posted).toEqual({ external_subject: "jane@acme", display_name: "Jane" });
    });
    // The reload counter bumped: the roster read ran again after the write.
    await waitFor(() => {
      const userReads = fetchFn.mock.calls.filter(
        ([u, init]) =>
          String(u) === "/users" && (init as RequestInit | undefined)?.method !== "POST",
      );
      expect(userReads.length).toBeGreaterThanOrEqual(2);
    });
  });
});
