import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MappingDetail, Mappings } from "./Mappings";
import type { DevSession } from "../../session";

const SESSION: DevSession = { kind: "dev" as const, userId: "u", tenantId: "t" };

const PROPOSED = {
  id: "m1",
  data_source_id: "ds1",
  source_type: "POSITIONS",
  version_label: "custodian-a-positions-v1",
  status: "PROPOSED",
  operations: [
    { op: "rename", target: "portfolio_code", source: "Account Ref" },
    { op: "code-lookup", target: "instrument", source: "SEDOL", scheme: "SEDOL" },
    { op: "scale", target: "quantity", source: "Nominal (000s)", factor: "1000" },
    { op: "parse-date", target: "valid_from", source: "Valuation Date", format: "%d/%m/%Y" },
  ],
  operations_hash: "abc123",
  authorship: "MODEL_PROPOSED",
  proposer_model_version_id: "mv1",
  proposal_prompt_hash: "deadbeef",
  proposal_prompt_ref: "08_testing_qa/ingest_mapping_proposal/prompt.md",
  proposal_response_ref: "08_testing_qa/ingest_mapping_proposal/response.json",
  proposed_by_actor_id: "onboarding.analyst@demo",
  proposed_at: "2026-08-21T09:00:00+00:00",
  ratified_by_actor_id: null,
  ratified_at: null,
  superseded_at: null,
  supersedes_id: null,
};

function stubJson(payload: (url: string) => unknown): string[] {
  const seen: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      seen.push(url);
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(payload(url)),
      });
    }),
  );
  return seen;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Mappings", () => {
  it("lists a PROPOSED version and does NOT render it as ratified", async () => {
    const seen = stubJson(() => [PROPOSED]);
    render(
      <MemoryRouter>
        <Mappings session={SESSION} />
      </MemoryRouter>,
    );

    expect(await screen.findByText("custodian-a-positions-v1")).toBeTruthy();
    // Honest state: an un-ratified mapping must not read as a finished thing, and the ratifier
    // cell must SAY nobody has agreed rather than sit blank.
    expect(screen.getByText(/PROPOSED — not yet in force/)).toBeTruthy();
    expect(screen.getByText(/awaiting ratification/)).toBeTruthy();
    expect(screen.queryByText(/files load through this version/)).toBeNull();
    expect(seen).toContain("/ingest/mappings");
  });

  it("renders honest-empty rather than an all-clear when no mapping exists", async () => {
    stubJson(() => []);
    render(
      <MemoryRouter>
        <Mappings session={SESSION} />
      </MemoryRouter>,
    );

    // An empty list is NOT good news here: nothing can load at all in this state, and the copy
    // has to say so. This is the convention the ops screens are pinned on.
    expect(await screen.findByText(/a positions file cannot load/)).toBeTruthy();
  });
});

describe("MappingDetail", () => {
  function renderDetail(payload: (url: string) => unknown): string[] {
    const seen = stubJson(payload);
    // Mounted under a REAL router with the parameterised path. Rendering the component bare
    // leaves useParams undefined and lets the assertions pass by absence — the R-4 by-absence
    // class this repo has shipped before.
    render(
      <MemoryRouter initialEntries={["/ops/mappings/m1"]}>
        <Routes>
          <Route path="/ops/mappings/:mappingId" element={<MappingDetail session={SESSION} />} />
        </Routes>
      </MemoryRouter>,
    );
    return seen;
  }

  it("reads the id from the route and explains each operation in words", async () => {
    const seen = renderDetail((url) => (url.endsWith("/batches") ? [] : PROPOSED));

    expect(await screen.findByText(/multiply "Nominal \(000s\)" by 1000/)).toBeTruthy();
    expect(screen.getByText(/resolve "SEDOL" as a SEDOL identifier/)).toBeTruthy();
    expect(screen.getByText(/read "Valuation Date" as a date in format %d\/%m\/%Y/)).toBeTruthy();
    expect(screen.getByText(/take the "Account Ref" column as it is/)).toBeTruthy();
    // the id came from the ROUTE, not from a default
    expect(seen).toContain("/ingest/mappings/m1");
    expect(seen).toContain("/ingest/mappings/m1/batches");
  });

  it("shows the prompt identity that makes the provenance checkable", async () => {
    renderDetail((url) => (url.endsWith("/batches") ? [] : PROPOSED));

    expect(await screen.findByText("deadbeef")).toBeTruthy();
    expect(screen.getByText("08_testing_qa/ingest_mapping_proposal/prompt.md")).toBeTruthy();
    expect(screen.getByText(/not ratified — this version cannot load a file/)).toBeTruthy();
  });

  it("says a hand-authored version carries NO model attribution", async () => {
    const hand = {
      ...PROPOSED,
      authorship: "HAND_AUTHORED",
      proposer_model_version_id: null,
      proposal_prompt_hash: null,
      proposal_prompt_ref: null,
    };
    renderDetail((url) => (url.endsWith("/batches") ? [] : hand));

    // The symmetric CHECK's other arm, made visible: absent attribution is stated, not blank.
    expect(await screen.findAllByText(/none — hand-authored/)).toHaveLength(2);
  });

  it("says a batch with no recorded lookup instant has none", async () => {
    renderDetail((url) =>
      url.endsWith("/batches")
        ? [
            {
              id: "b1",
              status: "COMPLETED",
              scan_status: "SKIPPED",
              filename: "custodian_positions_2026-07-31.csv",
              content_type: "text/csv",
              byte_size: 512,
              data_source_id: "ds1",
              row_count: 4,
              staged_count: 4,
              failed_count: 0,
              mapping_version_id: "m1",
              lookup_as_of: null,
            },
          ]
        : PROPOSED,
    );

    expect(await screen.findByText("custodian_positions_2026-07-31.csv")).toBeTruthy();
    // A blank cell would read as "no lookups happened"; clause 9's third input is either recorded
    // or explicitly not.
    expect(screen.getByText(/not recorded/)).toBeTruthy();
  });
});

describe("Mappings — the POSITIVE branches", () => {
  // Every test above covers an absent/negative state: PROPOSED, hand-authored, no lookup, empty
  // list. A slice reviewer pointed out that the states representing the system WORKING — a
  // RATIFIED mapping, a recorded ratifier, a recorded lookup instant — were never rendered at all,
  // so a swapped condition or a blanked cell in any of them would ship undetected.
  const RATIFIED = {
    ...PROPOSED,
    status: "RATIFIED",
    ratified_by_actor_id: "data.steward@demo",
    ratified_at: "2026-08-21T10:30:00+00:00",
  };

  it("renders a RATIFIED mapping as in force, with its ratifier", async () => {
    stubJson(() => [RATIFIED]);
    render(
      <MemoryRouter>
        <Mappings session={SESSION} />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/RATIFIED — files load through this version/)).toBeTruthy();
    expect(screen.getByText("data.steward@demo")).toBeTruthy();
    expect(screen.queryByText(/awaiting ratification/)).toBeNull();
  });

  it("renders the populated ratifier row and lookup instant on the detail view", async () => {
    stubJson((url) =>
      url.endsWith("/batches")
        ? [
            {
              id: "b1",
              status: "COMPLETED",
              scan_status: "SKIPPED",
              filename: "custodian_positions_2026-07-31.csv",
              content_type: "text/csv",
              byte_size: 512,
              data_source_id: "ds1",
              row_count: 4,
              staged_count: 4,
              failed_count: 0,
              mapping_version_id: "m1",
              lookup_as_of: "2026-08-21T10:31:00+00:00",
            },
          ]
        : RATIFIED,
    );
    render(
      <MemoryRouter initialEntries={["/ops/mappings/m1"]}>
        <Routes>
          <Route path="/ops/mappings/:mappingId" element={<MappingDetail session={SESSION} />} />
        </Routes>
      </MemoryRouter>,
    );

    // "who agreed?" — the question the whole INGEST-1 thesis turns on, for the one state that can
    // actually load a file.
    expect(await screen.findByText(/data\.steward@demo · 2026-08-21T10:30:00\+00:00/)).toBeTruthy();
    expect(screen.queryByText(/not ratified — this version cannot load a file/)).toBeNull();
    // clause 9's third input, RECORDED rather than absent
    expect(screen.getByText("2026-08-21T10:31:00+00:00")).toBeTruthy();
    expect(screen.queryByText(/not recorded/)).toBeNull();
  });
});

// --- W19-S3b: the checker's decision, the re-gating, and the by-target lineage cell -------------

const BATCH = {
  id: "b1",
  status: "COMPLETED",
  filename: "custodian_positions_2026-07-31.csv",
  staged_count: 4,
  lookup_as_of: "2026-08-21T09:00:00+00:00",
  mapping_version_id: "m1",
};

const EDGE = {
  id: "e1",
  source_type: "data_source",
  source_id: "ds1",
  target_entity_type: "ingestion_batch",
  target_entity_id: "b1",
  edge_kind: "ORIGIN",
  run_id: null,
};

/** Route a stub by URL shape: the detail, its batches, and the lineage of each batch. */
function detailRoutes(version: unknown, batches: unknown[], lineage: unknown) {
  return (url: string): unknown => {
    if (url.includes("/lineage/targets/")) return lineage;
    if (url.endsWith("/batches")) return batches;
    return version;
  };
}

function renderDetailAt(payload: (url: string) => unknown): string[] {
  const seen = stubJson(payload);
  render(
    <MemoryRouter initialEntries={["/ops/mappings/m1"]}>
      <Routes>
        <Route path="/ops/mappings/:mappingId" element={<MappingDetail session={SESSION} />} />
      </Routes>
    </MemoryRouter>,
  );
  return seen;
}

describe("MappingDetail — the checker's decision (W19-S3b)", () => {
  it("offers ratify and withdraw on a PROPOSED version, and NO reject verb", async () => {
    renderDetailAt(detailRoutes(PROPOSED, [], { edges: [], truncated: false }));

    expect(await screen.findByRole("button", { name: /Ratify this version/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Withdraw my proposal/ })).toBeTruthy();
    // A checker's refusal to ratify is INACTION — there is deliberately no reject verb anywhere,
    // and the ENT-075 review struck exactly this shape when it deleted REJECTED.
    expect(screen.queryByRole("button", { name: /Reject/i })).toBeNull();
  });

  it("hides the decision entirely once the version is no longer PROPOSED", async () => {
    const ratified = {
      ...PROPOSED,
      status: "RATIFIED",
      ratified_by_actor_id: "risk.manager@demo",
      ratified_at: "2026-08-21T10:00:00+00:00",
    };
    renderDetailAt(detailRoutes(ratified, [], { edges: [], truncated: false }));

    expect(await screen.findByText(/RATIFIED — files load through this version/)).toBeTruthy();
    // Both verbs are gone: they are the only two acts a PROPOSED version admits, and offering a
    // button whose only outcome is a 409 teaches an operator to ignore refusals.
    expect(screen.queryByRole("button", { name: /Ratify this version/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Withdraw my proposal/ })).toBeNull();
  });

  it("will not let a withdrawal be submitted without a reason", async () => {
    renderDetailAt(detailRoutes(PROPOSED, [], { edges: [], truncated: false }));

    const withdraw = await screen.findByRole("button", { name: /Withdraw my proposal/ });
    // Disabled with the reason box empty — so the backend's 422 is never an operator's first
    // sight of the rule. Ratify has no such requirement: a reason there is optional metadata.
    expect(withdraw.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByRole("button", { name: /Ratify this version/ }).hasAttribute("disabled"),
    ).toBe(false);
  });
});

describe("MappingDetail — the by-target lineage cell (W19-S3b)", () => {
  it("fetches lineage BY TARGET for each loaded batch and reports what it found", async () => {
    const seen = renderDetailAt(
      detailRoutes(PROPOSED, [BATCH], { edges: [EDGE], truncated: false }),
    );

    expect(await screen.findByText(/1 edge · data_source/)).toBeTruthy();
    // The endpoint that did not exist before this slice, keyed on an id the SPA actually holds.
    // `/lineage` previously had ONE route, taking an edge id nothing produced.
    expect(seen).toContain("/lineage/targets/ingestion_batch/b1");
  });

  it("says 'no lineage recorded' rather than rendering a blank", async () => {
    renderDetailAt(detailRoutes(PROPOSED, [BATCH], { edges: [], truncated: false }));

    // Honest-empty: no recorded origin for a LOADED batch is a real finding about the batch, and a
    // blank cell reads as "nothing to say here".
    expect(await screen.findByText(/no lineage recorded/)).toBeTruthy();
  });
});

// --- W19-S3b: the WRITE PATH, exercised ---------------------------------------------------------
//
// Added after a review found the decision tests asserted only that a button RENDERED. The
// component's whole reason for existing is the write and its refusal handling; `ops.test.tsx` (same
// directory, same class of maker/checker UI) already sets the convention — click, assert the POST
// body, assert the refetch, assert the exact remedy text. This follows it.

/** Route reads by URL and capture writes, so a POST body and a refusal can both be asserted. */
function routeMapping(
  reads: (url: string) => unknown,
  write?: () => { __status?: number; detail?: string } | unknown,
): { posts: RequestInit[]; reads: string[] } {
  const posts: RequestInit[] = [];
  const seen: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posts.push(init);
        const body = write ? write() : {};
        const status = (body as { __status?: number }).__status ?? 200;
        return Promise.resolve({
          ok: status < 400,
          status,
          json: () => Promise.resolve(body),
        });
      }
      seen.push(url);
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(reads(url)) });
    }),
  );
  return { posts, reads: seen };
}

describe("MappingDetail — the write path (W19-S3b)", () => {
  function mount(): void {
    render(
      <MemoryRouter initialEntries={["/ops/mappings/m1"]}>
        <Routes>
          <Route path="/ops/mappings/:mappingId" element={<MappingDetail session={SESSION} />} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("POSTs to the ratify route and REFETCHES what the write changed", async () => {
    const captured = routeMapping(detailRoutes(PROPOSED, [], { edges: [], truncated: false }));
    mount();
    await screen.findByRole("button", { name: /Ratify this version/ });
    const before = captured.reads.length;

    fireEvent.click(screen.getByRole("button", { name: /Ratify this version/ }));

    await waitFor(() => {
      expect(captured.posts.length).toBe(1);
    });
    // The refetch is the point of `onDone`: without it the screen still says PROPOSED and the
    // buttons stay live after a successful ratification.
    await waitFor(() => {
      expect(captured.reads.length).toBeGreaterThan(before);
    });
  });

  it("sends the operator's reason with a withdrawal", async () => {
    const captured = routeMapping(detailRoutes(PROPOSED, [], { edges: [], truncated: false }));
    mount();
    await screen.findByRole("button", { name: /Withdraw my proposal/ });

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "the custodian re-issued the file" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Withdraw my proposal/ }));

    await waitFor(() => {
      expect(captured.posts.length).toBe(1);
    });
    expect(JSON.parse(String(captured.posts[0].body))).toMatchObject({
      reason: "the custodian re-issued the file",
    });
  });

  it("tells a self-ratifier that a DIFFERENT PERSON must act, not to ask for a permission", async () => {
    const captured = routeMapping(
      detailRoutes(PROPOSED, [], { edges: [], truncated: false }),
      () => ({
        __status: 409,
        detail: "the ratifier may not be the proposer of this mapping version",
      }),
    );
    mount();
    await screen.findByRole("button", { name: /Ratify this version/ });
    fireEvent.click(screen.getByRole("button", { name: /Ratify this version/ }));

    const alert = await screen.findByRole("alert");
    // The caller HOLDS the code. Telling them to request a permission would send them nowhere,
    // and a retry cannot help — the remedy is a different person.
    expect(alert.textContent).toContain("Someone else must act on this proposal");
    expect(alert.textContent).not.toContain("You need the");
    expect(captured.posts.length).toBe(1);
  });

  it("tells a caller WITHOUT the code which permission they need", async () => {
    routeMapping(detailRoutes(PROPOSED, [], { edges: [], truncated: false }), () => ({
      __status: 403,
      detail: "permission denied",
    }));
    mount();
    await screen.findByRole("button", { name: /Ratify this version/ });
    fireEvent.click(screen.getByRole("button", { name: /Ratify this version/ }));

    const alert = await screen.findByRole("alert");
    // The opposite case, and it must NOT collapse into the 409 wording.
    expect(alert.textContent).toContain("ingest.mapping.ratify");
    expect(alert.textContent).not.toContain("Someone else must act");
  });
});

describe("MappingDetail — the lineage cap (W19-S3b)", () => {
  it("says TRUNCATED rather than presenting a cut-short lineage answer as complete", async () => {
    const many = Array.from({ length: 200 }, (_, i) => ({ ...EDGE, id: `e${String(i)}` }));
    renderDetailAt(detailRoutes(PROPOSED, [BATCH], { edges: many, truncated: true }));

    // A silently truncated lineage answer is worse than no answer: it looks complete. Every other
    // assertion in this file sees `truncated: false`, so without this the branch never runs.
    expect(await screen.findByText(/200 edges · data_source · truncated/)).toBeTruthy();
  });
});
