import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionForm } from "./SessionForm";

afterEach(cleanup);

function fill(user: string, tenant: string): void {
  fireEvent.change(screen.getByLabelText(/User id/), { target: { value: user } });
  fireEvent.change(screen.getByLabelText(/Tenant id/), { target: { value: tenant } });
}

describe("SessionForm", () => {
  it("starts a session with trimmed plain-ASCII ids", () => {
    const onStart = vi.fn();
    render(<SessionForm onStart={onStart} />);
    fill("  u-1  ", "t-1");
    fireEvent.click(screen.getByText("Start dev session"));
    expect(onStart).toHaveBeenCalledWith({ kind: "dev" as const, userId: "u-1", tenantId: "t-1" });
  });

  it("refuses non-ASCII ids with an explanation instead of a doomed session", () => {
    // An em-dash in an id makes the browser's header constructor throw on EVERY request,
    // masquerading as "API unreachable" (review fold) — refuse at entry.
    const onStart = vi.fn();
    render(<SessionForm onStart={onStart} />);
    fill("u—1", "t-1");
    expect(screen.getByText(/must be plain ASCII/)).toBeTruthy();
    expect((screen.getByText("Start dev session") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.submit(screen.getByText("Start dev session").closest("form") as HTMLFormElement);
    expect(onStart).not.toHaveBeenCalled();
  });

  it("keeps the button disabled while empty and shows no error", () => {
    render(<SessionForm onStart={vi.fn()} />);
    expect((screen.getByText("Start dev session") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByText(/must be plain ASCII/)).toBeNull();
  });
});
