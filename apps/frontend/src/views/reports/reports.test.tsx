/**
 * RPT-2 remit I4: the report view renders the artifact SAFELY and shows provenance verbatim.
 *
 * The load-bearing tests are the SANDBOX ones. The server escapes tenant strings
 * (mutation-proven at RPT-1), but this view is the platform's first rendering of server-produced
 * HTML, and the app's integrity must not depend on the server's escaping being perfect forever.
 * So the tests assert the MECHANISM, not the happy render: the markup goes into an iframe whose
 * `sandbox` attribute withholds EVERY capability, via `srcDoc` — and never into the app's own DOM,
 * where a surviving `<script>` would run with the session in reach.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Reports } from "./Reports";
import type { Session } from "../../session";

const SESSION: Session = {
  kind: "dev",
  userId: "11111111-1111-1111-1111-111111111111",
  tenantId: "22222222-2222-2222-2222-222222222222",
};

/** A hostile artifact: markup that SHOULD have been escaped server-side but — for this test —
 * was not. If the view is safe, this string reaches the iframe's srcDoc inert and never becomes a
 * live element (let alone a running script) in the app's document. */
const HOSTILE_HTML =
  "<h1>Risk summary</h1><script>document.title='owned'</script>" +
  "<img src=x onerror=\"document.title='owned'\">";

const REPORT = {
  id: "33333333-3333-3333-3333-333333333333",
  calculation_run_id: "44444444-4444-4444-4444-444444444444",
  input_snapshot_id: "55555555-5555-5555-5555-555555555555",
  portfolio_id: "66666666-6666-6666-6666-666666666666",
  portfolio_code: "PF-GROWTH",
  report_code: "report.risk_summary",
  report_version_label: "v1",
  render_format: "HTML",
  as_of_date: "2026-06-30",
  content_hash: "a".repeat(64),
  generated_at: "2026-07-01T12:00:00+00:00",
  generated_by: "analyst",
};

function stubFetch(htmlBody: string, htmlStatus = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/html")) {
        return new Response(htmlStatus === 200 ? htmlBody : JSON.stringify({ detail: "boom" }), {
          status: htmlStatus,
          headers: {
            "content-type": htmlStatus === 200 ? "text/html; charset=utf-8" : "application/json",
          },
        });
      }
      if (url.includes("/reports")) {
        return new Response(JSON.stringify({ items: [REPORT] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      throw new Error(`unrouted URL in test: ${url}`);
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderView(): void {
  render(
    <MemoryRouter>
      <Reports session={SESSION} />
    </MemoryRouter>,
  );
}

describe("the report list", () => {
  it("shows the report with its FULL identity hash, verbatim", async () => {
    stubFetch(HOSTILE_HTML);
    renderView();
    expect(await screen.findByText("PF-GROWTH")).toBeTruthy();
    // The full 64-char hash — a truncated hash cannot be independently checked, and independent
    // checking is the entire value of showing it.
    expect(screen.getByText("a".repeat(64))).toBeTruthy();
  });

  it("explains a refusal via role=alert instead of a bare error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "permission denied" }), {
            status: 403,
            headers: { "content-type": "application/json" },
          }),
      ),
    );
    renderView();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("view reports");
  });
});

describe("the sandbox (remit I4 — the mechanism, not the happy render)", () => {
  it("puts the artifact in an iframe with EVERY sandbox capability withheld", async () => {
    stubFetch(HOSTILE_HTML);
    renderView();
    (await screen.findByText("Open")).click();
    const frame = (await screen.findByTitle("Governed report (sandboxed)")) as HTMLIFrameElement;
    // sandbox="" — present AND empty. A missing attribute is no sandbox at all; a non-empty one
    // (allow-scripts, allow-same-origin) re-opens exactly the hole the sandbox exists to close.
    expect(frame.hasAttribute("sandbox")).toBe(true);
    expect(frame.getAttribute("sandbox")).toBe("");
    // The markup travels via srcDoc — not via src (no identity headers exist in a null-origin
    // frame, and a src fetch would just 401) and not via innerHTML.
    expect(frame.getAttribute("srcdoc")).toContain("Risk summary");
    expect(frame.getAttribute("srcdoc")).toContain("<script>");
  });

  it("NEVER materializes the artifact's markup in the app's own document", async () => {
    stubFetch(HOSTILE_HTML);
    renderView();
    (await screen.findByText("Open")).click();
    await screen.findByTitle("Governed report (sandboxed)");
    // The hostile elements must not exist as LIVE DOM nodes in the parent document: no script
    // element carrying the payload, no img with the onerror handler — anywhere.
    const scripts = Array.from(document.querySelectorAll("script")).filter((s) =>
      (s.textContent ?? "").includes("owned"),
    );
    expect(scripts).toHaveLength(0);
    expect(document.querySelectorAll("img[onerror]")).toHaveLength(0);
    expect(document.title).not.toBe("owned");
  });

  it("renders the 500 identity failure as the integrity event it is, not as noise", async () => {
    stubFetch("", 500);
    renderView();
    (await screen.findByText("Open")).click();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("IDENTITY FAILURE");
    expect(alert.textContent).toContain("reproducibility");
  });
});
