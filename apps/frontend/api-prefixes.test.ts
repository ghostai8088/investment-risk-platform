/**
 * OPS-1 fold H1: the deployed nginx location regex MUST route exactly the prefixes the SPA fetches.
 *
 * The dev proxy imports `API_PREFIXES` directly, so it cannot drift. The nginx config is a
 * hand-written regex in a different language and a different file, so it CAN — and did: both lists
 * were missing `/limits` and `/breaches` until this slice. That drift is invisible to `make check`
 * and to every unit test, because nginx answers an unrouted API path with the SPA's own HTML
 * (`try_files … /index.html`) — a 200, not a 404 — which the client then fails to parse as JSON and
 * reports as "the API is unreachable". This test is the only thing standing between a new prefix and
 * a phantom production outage.
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { API_PREFIXES } from "./api-prefixes";

const CONF_RELATIVE = "infra/docker/frontend-nginx.conf";

/** Walk up from the working directory to the repo root that holds the nginx config. (Resolving via
 * `import.meta.url` does NOT work here: under vitest that is an http:// URL, not a file one.) */
function nginxConfPath(): string {
  let dir = process.cwd();
  for (;;) {
    const candidate = resolve(dir, CONF_RELATIVE);
    if (existsSync(candidate)) return candidate;
    const parent = dirname(dir);
    if (parent === dir) throw new Error(`could not locate ${CONF_RELATIVE} above ${process.cwd()}`);
    dir = parent;
  }
}

/** Extract the alternation group from the proxy `location ~ ^/(a|b|c)(/|$)` directive. */
function nginxProxiedPrefixes(): string[] {
  const conf = readFileSync(nginxConfPath(), "utf8");
  const match = conf.match(/location\s+~\s+\^\/\(([^)]+)\)\(\/\|\$\)/);
  if (!match) throw new Error("could not find the nginx proxy location regex");
  return match[1].split("|").map((name) => `/${name}`);
}

describe("API prefix routing", () => {
  it("nginx proxies exactly the prefixes the SPA fetches", () => {
    // Set equality both directions: a missing prefix is a phantom outage; an extra one silently
    // proxies a path the SPA never calls (and shadows a would-be client route).
    expect([...nginxProxiedPrefixes()].sort()).toEqual([...API_PREFIXES].sort());
  });

  it("covers the operations surfaces this slice adds", () => {
    expect(API_PREFIXES).toContain("/limits");
    expect(API_PREFIXES).toContain("/breaches");
  });

  it("lists no duplicates", () => {
    expect(new Set(API_PREFIXES).size).toBe(API_PREFIXES.length);
  });
});
