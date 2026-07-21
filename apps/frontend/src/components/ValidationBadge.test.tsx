import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ValidationBadge } from "./ValidationBadge";

afterEach(cleanup);

describe("ValidationBadge", () => {
  it("renders tier + outcome + overdue", () => {
    render(
      <ValidationBadge
        info={{ tier: "TIER_1", outcome: "APPROVED_WITH_CONDITIONS", overdue: true }}
      />,
    );
    expect(screen.getByText("TIER 1")).toBeTruthy();
    expect(screen.getByText("APPROVED WITH CONDITIONS")).toBeTruthy();
    expect(screen.getByText("review overdue")).toBeTruthy();
  });

  it("shows UNVALIDATED honestly when there is no outcome", () => {
    render(<ValidationBadge info={{ tier: "TIER_3" }} />);
    expect(screen.getByText("UNVALIDATED")).toBeTruthy();
    expect(screen.queryByText("review overdue")).toBeNull();
  });
});
