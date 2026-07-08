# Worker (`irp-worker`)

Python skeleton for the future calculation-run worker (AD-006). It performs **no calculations**; `run_once()`
returns an idle heartbeat to prove wiring. The one real capability here is the **audit-chain verification ops CLI**
(`python -m irp_worker.audit_verify` — reads the audit chain cross-tenant via the BYPASSRLS ops role, AD-015).

When implemented, every calculation run must produce a reproducible `CalculationRun` record (temporal & numerical standards)
and must not bypass the audit (BR-12) or lineage (BR-13) frameworks.

## Run locally

```bash
make setup
.venv/bin/python -m irp_worker.main
```
