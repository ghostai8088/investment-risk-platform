import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Pane } from "./Pane";
import { ApiError } from "../api/client";
import type { AsyncState } from "../api/useApiGet";

afterEach(cleanup);

function state<T>(partial: Partial<AsyncState<T>>): AsyncState<T> {
  return { data: null, error: null, loading: false, ...partial };
}

describe("Pane", () => {
  it("shows loading", () => {
    render(<Pane state={state({ loading: true })}>{() => <span>data</span>}</Pane>);
    expect(screen.getByText("Loading…")).toBeTruthy();
  });

  it("degrades a 403 to a calm requires-permission note (never a screen failure)", () => {
    render(
      <Pane
        state={state({ error: new ApiError("forbidden", "403") })}
        requires="model.inventory.view"
      >
        {() => <span>secret</span>}
      </Pane>,
    );
    expect(screen.getByText(/You need the .*model\.inventory\.view.* permission/)).toBeTruthy();
    expect(screen.queryByText("secret")).toBeNull();
    // A denied read is a note, not an alert.
    expect(screen.getByRole("note")).toBeTruthy();
  });

  it("shows a real error as an alert", () => {
    render(
      <Pane state={state({ error: new ApiError("network", "the API is unreachable") })}>
        {() => <span>data</span>}
      </Pane>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText(/unreachable/)).toBeTruthy();
  });

  it("renders children with the data", () => {
    render(<Pane state={state({ data: { n: 7 } })}>{(d) => <span>got {d.n}</span>}</Pane>);
    expect(screen.getByText("got 7")).toBeTruthy();
  });

  it("shows an empty state for an empty array", () => {
    render(<Pane state={state<number[]>({ data: [] })}>{() => <span>rows</span>}</Pane>);
    expect(screen.getByText(/No data for this book yet/)).toBeTruthy();
  });
});
