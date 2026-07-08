# Shared Python library (`irp-shared`)

**The domain library** — web-framework-free, shared by the backend and worker. All domain logic, persistence
models, and governance frameworks live here; `apps/backend` is a thin router layer over it.

Packages: `audit` (**FROZEN** hash-chained audit service), `entitlement` (deny-by-default permissions + bootstrap),
`lineage`, `dq` (data-quality rules/gates), `db` (engine/session/tenant context/`PreciseDecimal`), `calc`
(`calculation_run` lifecycle), `snapshot` (the AD-014 reproducibility primitive), `reference`, `portfolio`,
`transaction`, `position`, `valuation`, `holdings`, `marketdata` (FX/prices/curves/benchmarks/factors), `exposure`,
`risk` (sensitivity/factor-exposure/covariance/VaR binders + kernels + the governed-run scaffold + read-only
queries), `synthetic` (the deterministic test dataset, never-auto-run).

Temporal classes (AD-005/BR-19): FR (bitemporal), IA (append-only), EV (versioned reference) — declared per entity
and enforced (append-only via DB triggers + ORM guards; proprietary data under symmetric FORCE RLS, BR-17).

Tests in `tests/` run on SQLite by default; the `*_pg.py` suites need `IRP_TEST_DATABASE_URL` (PostgreSQL) and
carry the RLS/append-only proofs.
