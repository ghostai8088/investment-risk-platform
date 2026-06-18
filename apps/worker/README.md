# Worker (`irp-worker`)

Python skeleton for the future calculation-run worker (AD-006). **Scaffold only** — it performs no calculations and reads no
data. `run_once()` returns an idle heartbeat to prove wiring.

When implemented, every calculation run must produce a reproducible `CalculationRun` record (temporal & numerical standards)
and must not bypass the audit (BR-12) or lineage (BR-13) frameworks.

## Run locally

```bash
make setup
.venv/bin/python -m irp_worker.main
```
