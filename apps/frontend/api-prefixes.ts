/**
 * The API path prefixes the SPA fetches, as ONE source of truth (OPS-1, verifier fold H1).
 *
 * The SPA fetches path-relative, so every prefix must be routed to the backend in BOTH places:
 *   - dev:      `vite.config.ts`'s server.proxy (imports this list)
 *   - deployed: `infra/docker/frontend-nginx.conf`'s location regex (hand-written, PINNED by
 *               `api-prefixes.test.ts` to this list)
 *
 * WHY THIS EXISTS: the two lists were hand-mirrored, and OPS-1 found both were missing `/limits`
 * and `/breaches`. The failure mode is worse than a 404 — nginx's `try_files … /index.html`
 * fallback answers an unrouted API path with **200 + the SPA's HTML**, which the client then fails
 * to parse as JSON and reports as "the API is unreachable" while the backend is perfectly healthy.
 * That is the FE-3b deployed-nginx defect class, and `make check` cannot see it. Adding a prefix
 * here and forgetting nginx now fails a test instead of shipping a phantom outage.
 */
export const API_PREFIXES = [
  "/risk",
  "/perf",
  "/exposure",
  "/portfolios",
  "/positions",
  "/valuations",
  "/holdings",
  "/models",
  "/snapshots",
  "/audit",
  "/lineage",
  "/pacing",
  "/commitments",
  // OPS-1: the operations UI reads/writes the limit + breach surfaces (API-2 / API-2b / NOTIF-1).
  "/limits",
  "/breaches",
  // RPT-2: the report read/generate surface (ENT-072 reachable).
  "/reports",
] as const;
