import { cleanup, render, screen } from "@testing-library/react";
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
