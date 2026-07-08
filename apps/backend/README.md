# Backend (`irp-backend`)

Python 3.12+ FastAPI service (AD-003). A **thin router layer** over the `irp_shared` domain library: every domain
endpoint binds to the entitlement (BR-11, deny-by-default via `require_permission`), audit (BR-12), and lineage
(BR-13) frameworks, and runs under the tenant session (`get_tenant_session` sets `app.current_tenant` for
PostgreSQL RLS, AD-016). Governed derived numbers additionally bind `dataset_snapshot` + `calculation_run` + a
registered `model_version` (AD-014 / FW-RUN / CTRL-003).

Current surface (routers under `src/irp_backend/api/`): system probes; lineage; models; data quality; ingestion;
reference data (currencies/calendars/ratings, entities, instruments, corporate actions); portfolios; transactions;
positions; valuations; holdings views; dataset snapshots; market data (FX, prices, curves, benchmarks, factors);
exposure; risk (sensitivities, factor exposures, covariances, VaR — register/run/read + the read-only
`GET /risk/runs` listing).

**Identity is the DEV header shim** (`X-User-Id`/`X-Tenant-Id`, DR-P1A0-3) — unverified, not a security boundary
until SSO (AD-007); the entitlement + RLS enforcement behind it is real.

## Run locally

```bash
make setup
DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \
  .venv/bin/uvicorn irp_backend.main:app --app-dir apps/backend/src --reload
```

Configuration is read from the environment only (no secrets in source — BR-10). See `../../.env.example` and
`../../docs/developer_setup.md`.
