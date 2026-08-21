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
  // ONBOARD-1b: the tenant-administration surface (Users & Roles + the four-eyes queue). NOTE:
  // these are also why the SCREEN lives at /admin/users — a client route at bare /users would be
  // shadowed by this very list (the ops/reports precedent).
  "/users",
  "/roles",
  "/entitlement-requests",
  // ALERT-1: the alarm channel's health read. NOTE the same trap as /users — the SCREEN lives at
  // /ops/alerting, not at /reproduction, because a client route under this prefix is shadowed.
  "/reproduction",
  // REPRO-2: the schedule WRITE path (create/pause/resume) and the scheduled-run ledger, which the
  // /ops/reproduction screen drives. Same shadow trap, third instance: the SCREEN is at
  // /ops/reproduction, never at bare /schedules.
  "/schedules",
  // W19-S3a: the ENT-077 mapping reads the /ops/mappings screen drives. The shadow trap for the
  // FOURTH time: the SCREEN is at /ops/mappings, never at bare /ingest — a client route under a
  // prefix in this list is answered by nginx as 200 + index.html and reports as a phantom outage.
  // NOTE this prefix was ALREADY missing while /ingest/upload and /ingest/batches shipped at
  // P1A-4: those routes existed in the backend and in the committed OpenAPI, and the SPA simply
  // never called them, so nothing noticed.
  "/ingest",
] as const;
