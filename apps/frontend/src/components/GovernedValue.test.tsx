import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { GovernedValue } from "./GovernedValue";

afterEach(cleanup);

function renderGV(ui: React.ReactElement): void {
  render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("GovernedValue", () => {
  it("renders the value VERBATIM — a governed decimal string reaches the DOM unmodified", () => {
    const gov = "0.01234500000000000000";
    renderGV(<GovernedValue label="VaR (95%, 1d)" value={gov} />);
    // Exact string, trailing zeros and all — a Number() would have printed 0.012345.
    expect(screen.getByText(gov)).toBeTruthy();
  });

  it("shows the provenance strip (snapshot / run / model) with the snapshot-verify mark", () => {
    renderGV(
      <GovernedValue
        label="ES"
        value="0.9"
        provenance={{
          snapshotId: "aaaaaaaa-1111-2222-3333-444444444444",
          runId: "bbbbbbbb-1111-2222-3333-444444444444",
          modelVersionId: "cccccccc-1111-2222-3333-444444444444",
          codeVersion: "es-1.0",
        }}
        snapshotVerified={true}
      />,
    );
    expect(screen.getByText("Snapshot")).toBeTruthy();
    expect(screen.getByText("Run")).toBeTruthy();
    expect(screen.getByText("Model version")).toBeTruthy();
    expect(screen.getByText("es-1.0")).toBeTruthy();
    expect(screen.getByText(/reproduces/)).toBeTruthy();
  });

  it("shows a mismatch mark when a snapshot fails to verify", () => {
    renderGV(
      <GovernedValue
        label="X"
        value="1"
        provenance={{ snapshotId: "aaaaaaaa-1111-2222-3333-444444444444" }}
        snapshotVerified={false}
      />,
    );
    expect(screen.getByText(/mismatch/)).toBeTruthy();
  });

  it("renders a lineage/audit link when an audit href is given", () => {
    renderGV(<GovernedValue label="X" value="1" auditHref="/walk/validation" />);
    expect(screen.getByRole("link", { name: /Lineage & audit/ })).toBeTruthy();
  });
});
