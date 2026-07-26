# Worker (`irp-worker`)

The operational worker for the governed risk engine. Two entrypoints drive the **per-tenant
operational tick** (`run_operational_tick_for_tenant` — schedules → breaches → deadlines →
breach-notification), each under the ordinary non-BYPASSRLS app role with forced RLS:

- **`python -m irp_worker.supervisor`** (the container default, CAD-1) — an in-process supervisor
  that ticks every **configured** tenant on a cadence. Config (env): `DATABASE_URL`,
  `IRP_TENANT_IDS` (comma-separated tenant UUIDs), `IRP_TICK_INTERVAL_SECONDS` (default 300),
  `IRP_CODE_VERSION`. Tenant ids are canonicalized before they arm RLS; a malformed entry is skipped
  (the rest keep ticking); an empty list fails closed at startup.
- **`python -m irp_worker.scheduler --tenant <uuid>`** — a single one-shot tick for one tenant, for
  an external scheduler (k8s CronJob / cloud scheduler / host cron) that prefers once-per-tenant
  invocation (OQ-SCH-1-1=B / CAD-1 OQ-1=A). The `--tenant` value is canonicalized; a non-UUID fails
  closed (exit 2).

The tenant list is always **supplied by infra/config** — the app never sweeps the database for
tenants and never uses the BYPASSRLS ops role for a business path (OQ-SCH-1-1=B).

The other capability here is the **audit-chain verification ops CLI** (`python -m
irp_worker.audit_verify` — reads the audit chain cross-tenant via the BYPASSRLS ops role, AD-015).

Every fired run produces a reproducible `CalculationRun` record (temporal & numerical standards) and
never bypasses the audit (BR-12) or lineage (BR-13) frameworks.

## Run locally

```bash
make setup
# one tick for one tenant:
.venv/bin/python -m irp_worker.scheduler --tenant <tenant-uuid> --database-url "$DATABASE_URL"
# or the cadence supervisor (reads IRP_TENANT_IDS / IRP_TICK_INTERVAL_SECONDS from the env):
.venv/bin/python -m irp_worker.supervisor
```
