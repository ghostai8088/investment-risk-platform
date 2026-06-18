# Backend (`irp-backend`)

Python 3.12+ FastAPI service (AD-003). **Scaffold only** — the only endpoints are system probes:

- `GET /health` → `{"status": "ok"}`
- `GET /version` → `{"version": ..., "env": ...}`

No domain logic, no database access, no governed data. Any future domain endpoint **must** bind to the entitlement (BR-11),
audit (BR-12), and lineage (BR-13) frameworks before it is added.

## Run locally

```bash
make setup
.venv/bin/uvicorn irp_backend.main:app --reload
```

Configuration is read from the environment only (no secrets in source — BR-10). See `../../.env.example`.
