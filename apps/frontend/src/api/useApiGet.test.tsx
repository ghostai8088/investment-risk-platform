import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useApiGet } from "./useApiGet";
import type { DevSession } from "../session";

const SESSION: DevSession = { userId: "u", tenantId: "t" };

function Probe({ path }: { path: string | null }): React.ReactElement {
  const { data, error, loading } = useApiGet<{ v: string }>(path, SESSION);
  if (loading) return <span>loading</span>;
  if (error) return <span>error:{error.kind}</span>;
  if (data) return <span>data:{data.v}</span>;
  return <span>idle</span>;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("useApiGet", () => {
  it("fetches and exposes the parsed body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({ v: "x" }) }),
    );
    render(<Probe path="/models" />);
    expect(await screen.findByText("data:x")).toBeTruthy();
  });

  it("surfaces a 403 as a typed forbidden error (for graceful degradation)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 403, json: () => Promise.resolve({}) }),
    );
    render(<Probe path="/models" />);
    expect(await screen.findByText("error:forbidden")).toBeTruthy();
  });

  it("stays idle and fetches NOTHING when the path is null", async () => {
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    render(<Probe path={null} />);
    await waitFor(() => expect(screen.getByText("idle")).toBeTruthy());
    expect(mock).not.toHaveBeenCalled();
  });
});
