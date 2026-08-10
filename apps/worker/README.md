# Worker (`irp-worker`)

The operational worker for the governed risk engine. Two entrypoints drive the **per-tenant
operational tick** (`run_operational_tick_for_tenant` — schedules → breaches → deadlines →
breach-notification), each under the ordinary non-BYPASSRLS app role with forced RLS:

- **`python -m irp_worker.supervisor`** (the container default; CAD-1, discovery superseded at
  REPRO-2) — an in-process supervisor that ticks every **ACTIVE registry tenant** on a cadence.
  Config (env): `DATABASE_URL`, `IRP_TENANT_IDS` (OPTIONAL restriction filter since REPRO-2 — the
  tenant list itself comes from the ENT-074 registry, ACTIVE only, re-read every cycle),
  `IRP_TICK_INTERVAL_SECONDS` (default 300), `IRP_CODE_VERSION`, `IRP_MAX_CYCLES` (default
  unbounded). Tenant ids are canonicalized before they arm RLS; a malformed restriction entry
  REFUSES at startup (skip-and-continue would silently widen the filter to every tenant); a
  restriction naming a tenant the registry does not know refuses; an EMPTY registry idles LOUDLY
  every cycle and keeps polling.
- **`python -m irp_worker.scheduler --tenant <uuid>`** — a single one-shot tick for one tenant, for
  an external scheduler (k8s CronJob / cloud scheduler / host cron) that prefers once-per-tenant
  invocation (OQ-SCH-1-1=B / CAD-1 OQ-1=A). The `--tenant` value is canonicalized; a non-UUID fails
  closed (exit 2).

The tenant list comes from the **ENT-074 tenant registry** (REPRO-2) — a deliberately
platform-global table read on every authenticated request, so the discovery read needs no
BYPASSRLS and no RLS bypass of any kind. Dispatch stays strictly per-tenant and the app never
uses the BYPASSRLS ops role for a business path (OQ-SCH-1-1=B, unchanged).

The other capability here is the **audit-chain verification ops CLI** (`python -m
irp_worker.audit_verify` — reads the audit chain cross-tenant via the BYPASSRLS ops role, AD-015).

Every fired run produces a reproducible `CalculationRun` record (temporal & numerical standards) and
never bypasses the audit (BR-12) or lineage (BR-13) frameworks.

## Run locally

```bash
make setup
# one tick for one tenant:
.venv/bin/python -m irp_worker.scheduler --tenant <tenant-uuid> --database-url "$DATABASE_URL"
# or the cadence supervisor (discovers ACTIVE tenants from the registry; reads the optional
# IRP_TENANT_IDS restriction / IRP_TICK_INTERVAL_SECONDS from the env):
.venv/bin/python -m irp_worker.supervisor
```
