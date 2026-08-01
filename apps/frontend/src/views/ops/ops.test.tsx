/**
 * OPS-1: the operations surfaces.
 *
 * The behaviours proven here are the ones that make this a *governance* UI rather than a table:
 * a refusal is explained by which control fired (not by its status code), a limit that is not in
 * force is never rendered as healthy, the expected_seq token is round-tripped on every write, and
 * a completed write actually refreshes the stale reads.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";

import { BreachDetail } from "./BreachDetail";
import { BreachQueue } from "./BreachQueue";
import { LimitHealth } from "./LimitHealth";
import type { Session } from "../../session";

const SESSION: Session = { kind: "dev", userId: "u-1", tenantId: "t-1" };

const BREACH = {
  id: "b-1",
  limit_definition_id: "l-1",
  calculation_run_id: "run-1",
  detected_at: "2026-07-01T00:00:00Z",
  target_run_type: "VAR",
  metric_type: "VAR_PARAMETRIC",
  benchmark_id: null,
  observed_value: "2000000.25",
  threshold_value: "1000000.00",
  threshold_unit: "CURRENCY",
  breach_direction: "ABOVE",
  limit_kind: "HARD",
  severity: "HARD",
  state: "ASSIGNED",
  assigned_to: "u-9",
  response_due: "2026-07-02T00:00:00Z",
  scope_portfolio_id: "pf-1",
  limit_code: "VAR-CEIL",
  seq: 4,
};

/** Route each path to a canned response; unmatched paths reject loudly so a typo'd URL is not
 * mistaken for an empty result. */
function routeFetch(
  routes: Record<string, unknown>,
  onPost?: (url: string, init: RequestInit) => unknown,
) {
  const fn = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const body = onPost ? onPost(url, init) : {};
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

afterEach(() => {
  cleanup(); // this config does not auto-clean; a stale DOM would let one test read another's alert
  vi.unstubAllGlobals();
});

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/ops/breaches/b-1"]}>
      <Routes>
        <Route path="/ops/breaches/:breachId" element={<BreachDetail session={SESSION} />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("BreachQueue", () => {
  it("renders fixed-point values verbatim and flags an overdue breach", async () => {
    routeFetch({ "/breaches?": [BREACH] });
    render(
      <MemoryRouter>
        <BreachQueue session={SESSION} />
      </MemoryRouter>,
    );
    expect(await screen.findByText("2000000.25")).toBeTruthy(); // never parsed to a float
    expect(screen.getByText("1000000.00")).toBeTruthy();
    expect(screen.getByText("overdue")).toBeTruthy(); // response_due is in the past
  });

  it("explains a 403 by naming the control, not the status code", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 403,
          json: () => Promise.resolve({ detail: "permission denied" }),
        } as unknown as Response),
      ),
    );
    render(
      <MemoryRouter>
        <BreachQueue session={SESSION} />
      </MemoryRouter>,
    );
    const msg = await screen.findByRole("alert");
    expect(msg.textContent).toContain("not entitled");
    expect(msg.textContent).toContain("enforced by the server");
  });

  it("does not treat a null response_due as overdue", async () => {
    routeFetch({ "/breaches?": [{ ...BREACH, state: "CLOSED", response_due: null }] });
    render(
      <MemoryRouter>
        <BreachQueue session={SESSION} />
      </MemoryRouter>,
    );
    expect(await screen.findByText("VAR-CEIL")).toBeTruthy();
    expect(screen.queryByText("overdue")).toBeNull();
  });
});

describe("BreachDetail", () => {
  it("sends the breach's own seq as expected_seq and refreshes afterwards", async () => {
    const posts: RequestInit[] = [];
    const fetchMock = routeFetch(
      {
        "/breaches/b-1/actions": [],
        "/breaches/b-1/notifications": [],
        "/breaches/b-1": BREACH,
      },
      (_url, init) => {
        posts.push(init);
        return BREACH;
      },
    );
    renderDetail();
    await screen.findByText("VAR-CEIL");
    const before = fetchMock.mock.calls.filter(
      (c) => (c[1] as RequestInit | undefined)?.method !== "POST",
    ).length;

    fireEvent.change(screen.getByLabelText(/Narrative/i), { target: { value: "hedged" } });
    fireEvent.click(screen.getByRole("button", { name: /File 1L response/i }));

    await waitFor(() => expect(posts.length).toBe(1));
    expect(JSON.parse(String(posts[0].body))).toMatchObject({ expected_seq: 4 });
    // fold H4: the reads re-run after the write (the hook could not refetch an unchanged path)
    await waitFor(() => {
      const after = fetchMock.mock.calls.filter(
        (c) => (c[1] as RequestInit | undefined)?.method !== "POST",
      ).length;
      expect(after).toBeGreaterThan(before);
    });
  });

  it("explains a separation-of-duties refusal as the control working", async () => {
    routeFetch(
      {
        "/breaches/b-1/actions": [],
        "/breaches/b-1/notifications": [],
        "/breaches/b-1": BREACH,
      },
      () => ({
        __status: 409,
        detail: "separation of duties: the actor responded to this breach",
      }),
    );
    renderDetail();
    await screen.findByText("VAR-CEIL");
    fireEvent.click(screen.getByRole("button", { name: /2L accept/i }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("separation of duties");
    expect(alert.textContent).toContain("Someone else must");
  });

  it("tells the operator to RELOAD on a stale-seq conflict, not that the move was illegal", async () => {
    routeFetch(
      {
        "/breaches/b-1/actions": [],
        "/breaches/b-1/notifications": [],
        "/breaches/b-1": BREACH,
      },
      () => ({
        __status: 409,
        detail: "the breach changed while you were reading it; reload and retry",
      }),
    );
    renderDetail();
    await screen.findByText("VAR-CEIL");
    fireEvent.click(screen.getByRole("button", { name: /2L accept/i }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("changed while you were reading it");
    expect(alert.textContent).toContain("Nothing was written");
    // the crucial distinction: it must NOT accuse the operator of an illegal action
    expect(alert.textContent).not.toContain("not legal");
  });

  it("pages the alerts explicitly and SURFACES truncation at a full page (OPS-H1 H1-9)", async () => {
    // The real residual of OPS-1 L-7: the backend pager shipped in NOTIF-1, but this screen
    // fetched the default page, so the 51st alert silently vanished. The fetch must now carry an
    // explicit limit at the API's cap, and a FULL page must render a visible truncation notice
    // instead of silence. (The ratified item said "a load-more affordance"; what shipped is the
    // static notice — the substitution is recorded in the decision record, and THIS test is the
    // truncation-visible control it owed.)
    const fullPage = Array.from({ length: 200 }, (_, i) => ({
      id: `n-${String(i)}`,
      breach_id: "b-1",
      source_event_type: "LIMIT.BREACH_ESCALATE",
      source_sequence_no: i,
      recipient_id: "u-9",
      channel: "LOG",
      outcome: "SENT",
      notified_at: "2026-07-01T00:00:00Z",
    }));
    const fetchMock = routeFetch({
      "/breaches/b-1/actions": [],
      "/breaches/b-1/notifications": fullPage,
      "/breaches/b-1": BREACH,
    });
    renderDetail();
    await screen.findByText("VAR-CEIL");
    const alertCalls = fetchMock.mock.calls.filter((c) => String(c[0]).includes("/notifications"));
    expect(alertCalls.length).toBeGreaterThan(0);
    expect(String(alertCalls[0][0])).toContain("limit=200");
    await screen.findByText(/the list is capped/i);
  });
});

describe("LimitHealth", () => {
  const ACTIVE_LIMIT = {
    id: "l-1",
    code: "VAR-CEIL",
    name: "VaR ceiling",
    status: "ACTIVE",
    threshold_value: "1000000.00",
    threshold_unit: "CURRENCY",
    metric_type: "VAR_PARAMETRIC",
    target_run_type: "VAR",
    breach_direction: "ABOVE",
    limit_kind: "HARD",
    benchmark_id: null,
    scope_portfolio_id: "pf-1",
    record_version: 1,
    created_by: "maker-1",
    updated_by: null,
  };

  const CONCENTRATION_LIMIT = {
    ...ACTIVE_LIMIT,
    id: "l-c",
    code: "TECH-20",
    name: "tech <= 20%",
    target_run_type: "CONCENTRATION",
    metric_type: "SHARE",
    threshold_value: "0.200000",
    threshold_unit: "FRACTION",
    dimension_kind: "SECTOR_INDUSTRY",
    bucket_code: "J",
    issuer_id: null,
    scheme_family: "ISIC",
    authored_scheme_id: "scheme-rev4",
    denominator_basis: "INVESTED_LONG",
  };

  it("shows WHICH taxonomy a concentration limit means (the metric name alone cannot)", async () => {
    // LIM-2 fact 2: `MAX_SHARE_SECTOR_INDUSTRY` / `SHARE` does not say which scheme partitioned the
    // sectors, and two schemes partition them differently. Rule 7 requires the selector on screen.
    routeFetch({
      "/limits/health": [
        {
          limit_id: "l-c",
          code: "TECH-20",
          state: "IN_APPETITE",
          latest_run_id: "run-9",
          latest_breach_id: null,
          latest_run_failed: false,
          scheme_drift_from: null,
          scheme_drift_to: null,
          refusal_reason: null,
        },
      ],
      "/limits": [CONCENTRATION_LIMIT],
    });
    render(
      <MemoryRouter>
        <LimitHealth session={SESSION} />
      </MemoryRouter>,
    );
    expect(await screen.findByText("TECH-20")).toBeTruthy();
    expect(screen.getByText(/SECTOR_INDUSTRY/)).toBeTruthy();
    expect(screen.getByText(/ISIC/)).toBeTruthy();
  });

  it("shows staleness and scheme drift ALONGSIDE a breach, never instead of it", async () => {
    // The reason these are orthogonal fields and not extra enum values (LIM-2 record 3.5): a
    // staleness badge that REPLACED the verdict would hide a real breach. All three must render.
    routeFetch({
      "/limits/health": [
        {
          limit_id: "l-c",
          code: "TECH-20",
          state: "BREACHED",
          latest_run_id: "run-9",
          latest_breach_id: "b-9",
          latest_run_failed: true,
          scheme_drift_from: "scheme-rev4",
          scheme_drift_to: "scheme-rev5",
          refusal_reason: null,
        },
      ],
      "/limits": [CONCENTRATION_LIMIT],
    });
    render(
      <MemoryRouter>
        <LimitHealth session={SESSION} />
      </MemoryRouter>,
    );
    expect(await screen.findByText("BREACHED")).toBeTruthy();
    expect(screen.getByText(/newest run failed/i)).toBeTruthy();
    expect(screen.getByText(/scheme version drift/i)).toBeTruthy();
  });

  it("says a refused limit was NOT compared, rather than showing it as green", async () => {
    routeFetch({
      "/limits/health": [
        {
          limit_id: "l-c",
          code: "TECH-20",
          state: "REFUSED",
          latest_run_id: null,
          latest_breach_id: null,
          latest_run_failed: false,
          scheme_drift_from: null,
          scheme_drift_to: null,
          refusal_reason: "basis mismatch: the limit was written against 'INVESTED_LONG'",
        },
      ],
      "/limits": [CONCENTRATION_LIMIT],
    });
    render(
      <MemoryRouter>
        <LimitHealth session={SESSION} />
      </MemoryRouter>,
    );
    expect(await screen.findByText("REFUSED")).toBeTruthy();
    expect(screen.getByText(/not compared/i)).toBeTruthy();
    expect(screen.queryByText("IN_APPETITE")).toBeNull();
  });

  it("never renders a SUSPENDED limit as healthy (it has no health row at all)", async () => {
    routeFetch({
      "/limits/health": [], // health only covers ACTIVE limits
      "/limits": [{ ...ACTIVE_LIMIT, id: "l-2", code: "SUSP", status: "SUSPENDED" }],
    });
    render(
      <MemoryRouter>
        <LimitHealth session={SESSION} />
      </MemoryRouter>,
    );
    expect(await screen.findByText("SUSP")).toBeTruthy();
    expect(screen.getByText("NOT IN FORCE")).toBeTruthy();
    expect(screen.queryByText("IN_APPETITE")).toBeNull();
  });

  it("lists DRAFT limits in the approval queue and explains they constrain nothing", async () => {
    routeFetch({
      "/limits/health": [],
      "/limits": [{ ...ACTIVE_LIMIT, status: "DRAFT" }],
    });
    render(
      <MemoryRouter>
        <LimitHealth session={SESSION} />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("button", { name: /Approve/i })).toBeTruthy();
    expect(screen.getByText(/not evaluated and cannot breach/i)).toBeTruthy();
  });

  it("explains the maker-checker refusal when the approver is a maker", async () => {
    routeFetch(
      {
        "/limits/health": [],
        "/limits": [{ ...ACTIVE_LIMIT, status: "DRAFT" }],
      },
      () => ({
        __status: 409,
        detail: "separation of duties: the actor shaped this limit", // the SHIPPED limits.py string
      }),
    );
    render(
      <MemoryRouter>
        <LimitHealth session={SESSION} />
      </MemoryRouter>,
    );
    // The approval reference is REQUIRED (it is the sign-off evidence written into the ledger),
    // so it must be supplied before the button is even enabled.
    fireEvent.change(await screen.findByLabelText(/Approval reference/i), {
      target: { value: "minutes://RISK-COMMITTEE-2026-07" },
    });
    fireEvent.click(await screen.findByRole("button", { name: /Approve/i }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("separation of duties");
    expect(alert.textContent).toContain("Someone else must");
  });

  it("refuses to approve without sign-off evidence rather than inventing a placeholder", async () => {
    const fetchMock = routeFetch({
      "/limits/health": [],
      "/limits": [{ ...ACTIVE_LIMIT, status: "DRAFT" }],
    });
    render(
      <MemoryRouter>
        <LimitHealth session={SESSION} />
      </MemoryRouter>,
    );
    // approval_ref is written verbatim into the immutable LIMIT.APPROVE audit event, and the
    // service refuses an empty one on purpose. A client-side default would fabricate provenance,
    // so the button stays disabled and NO write is attempted.
    const button = await screen.findByRole("button", { name: /Approve/i });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(button);
    expect(
      fetchMock.mock.calls.filter((c) => (c[1] as RequestInit | undefined)?.method === "POST"),
    ).toHaveLength(0);
  });
});
