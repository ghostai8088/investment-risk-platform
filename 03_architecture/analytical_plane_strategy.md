# Analytical Plane / Warehouse Strategy (AD-019)

## Document Control

| | |
|---|---|
| Status | Accepted — AD-019, 2026-07-24 (H-06 / H-04) |
| Scope | Where governed data lives vs. where analytics/BI/DS/external reads are served |
| Supersedes | Extends AD-004 / AD-004-R1; broadens OD-046 |
| Drivers | A client/investor/compliance (diligence) ask; infra consolidation/cost; data-science/ML; BI/reporting & external access |

## Decision

**Hybrid, additive, read-only.** PostgreSQL remains the **governed system-of-record**. A future
**analytical plane** — Snowflake the likely target — is added **later** as an *additive, read-only*
serving layer, fed by CDC/ELT from Postgres. **The governed OLTP core never moves.** Consolidation is
achieved by making the analytical plane the single *serving/analytics* layer downstream of governed
writes — **not** by relocating the writes.

We do **not** build the plane now (no volume justifies it, and it is post-build work). We **do** now:
capture this doctrine (diligence needs a written answer), protect the one seam that keeps the future
move cheap, and set concrete triggers for when to build it.

## Why the governed core stays on Postgres (the load-bearing fact)

The platform's governance guarantees — what make it *governed* rather than a spreadsheet — are
enforced by four PostgreSQL-native primitives a columnar analytical warehouse does **not** replicate.
A move of the core would convert each from *engine-enforced invariant* to *application convention*:

| Guarantee | Enforced today (Postgres) | On a columnar warehouse (e.g. Snowflake) |
|---|---|---|
| Tenant isolation | RLS + `FORCE ROW LEVEL SECURITY` + transaction-local GUC `app.current_tenant` (AD-008/AD-016), ~43 tables, on a `NOBYPASSRLS` role | No `FORCE` RLS / no equivalent auto-clearing GUC → app-convention `WHERE tenant_id = ?` on every query |
| Immutability (audit + IA results) | `BEFORE UPDATE OR DELETE` trigger `irp_prevent_mutation()` (AUD-01, AD-012) on ~35 append-only tables | **No row triggers** → immutability reduces to "the app promises not to UPDATE/DELETE" |
| Lifecycle linearizability | `SELECT … FOR UPDATE` row locks (breach lifecycle, limit approval) + `pg_advisory_xact_lock` (audit hash-chain sequence) | **No row-level pessimistic locks** → redesign to optimistic-retry / external lock service |
| Referential + idempotency backstops | Enforced FK + UNIQUE constraints (e.g. `uq_breach_limit_run`, once-per-epoch escalation index) | FK / UNIQUE are **informational, not enforced** → duplicate/orphan rows pass silently |

This is an **OLTP governance kernel** — many small, individually-governed transactional writes (runs,
audit events, breaches, limit approvals) — with analytical *result* rows layered on top. The result
rows and their lineage port cleanly to a warehouse; the enforcement primitives do not. Hence: keep
the kernel on Postgres, mirror the results outward.

## Governed-number replication contract

If governed results are copied to the analytical plane, reproducibility (FW-RUN, TR-13/TR-15/TR-16 —
`04_data_model/temporal_reproducibility_standard.md` §5) must be preserved. The plane must replicate,
**together and lineage-intact**, for every governed number:

- the **result** rows (`var_result`, `covariance_result`, `factor_exposure_result`,
  `active_risk_result`, `sensitivity_result`, `exposure_aggregate`, and the rest of the append-only
  result family), **plus**
- `calculation_run` (the run-bind: `input_snapshot_id`, `model_version_id`, `assumption_set_id`,
  `random_seed`, `code_version`, `environment_id`), **plus**
- `dataset_snapshot` + `dataset_snapshot_component` (the immutable input pins), **plus**
- `model_version` (and its assumptions/limitations where a model applies).

**Invariant (TR-15 in the warehouse):** a result row surfaced without its `calculation_run` +
snapshot lineage is *incomplete* and must not be published or used for limits/reports. This is a
**data contract** the CDC/ELT pipeline (deferred) implements; it is not code today. The binding is
already carried as columns that port cleanly — `NUMBER(38, s)` ≈ `PreciseDecimal`, `uuid5` and the
SHA-256 hash canonicalization are engine-independent — so no schema change is needed now to keep the
option open.

## The re-pointable read seam (why the future move is cheap)

Governed reads take **two shapes**, and both are centralized — so re-pointing them at a warehouse is a
small, enumerable change, not a scattered rewrite:

1. **"Latest/list governed number" reads** (the run-selection semantics — *which* completed run is
   current) funnel through **one module**:
   `packages/shared-python/src/irp_shared/calc/reads.py` (`list_governed_results` / `latest_run_rows`),
   consumed by the typed wrappers (`latest_var_for_portfolio`, `latest_sensitivities`,
   `latest_factor_exposure`, `latest_active_risk_for_portfolio`, …) and the read API. This is the
   primary seam.
2. **By-run-id matrix reads** (fetch a *known* run's full result set), used where a result is a matrix
   rather than a scalar — covariance / private-covariance (`risk/covariance_service.py`,
   `risk/private_covariance_service.py`). These join `CalculationRun` for a `run_type` self-defense
   filter (the shared-table contract, PPF-2), **not** for latest-run selection, so they legitimately do
   not go through `calc/reads.py`; they are their own centralized readers.

Re-pointing governed reads is therefore "the `calc/reads.py` seam **plus** the covariance by-run-id
readers" — a handful of modules, all already centralized. The discipline that keeps it that way (a
standing engineering convention, `docs/project_memory/claude_operating_instructions.md`): a new
**latest/list** governed-result read routes through `calc/reads.py` — never an ad-hoc
`select(<ResultModel>)…join(CalculationRun)` scattered in a service or router; a new by-run-id matrix
read stays centralized in its result's service, like covariance. (Demo scripts under `demo/` are
exempt — they are illustrative, not the product read path.)

## Trigger criteria (build the plane when the FIRST fires)

- A concrete external / data-science / BI consumer needs SQL access to risk data (the
  diligence / DS / BI drivers); **or**
- market-data or governed-result volume crosses a stated threshold (attach to OD-046's Timescale
  ceiling); **or**
- a diligence commitment names a date.

Until a trigger fires: **no** Snowpipe / CDC / dbt / warehouse modeling / ELT build.

## Deferred build outline (only after a trigger — not for now)

1. **Replication:** CDC (Postgres logical replication / Debezium) or scheduled batch ELT → the
   warehouse, carrying the replication-contract set as **insert-only** loads that preserve
   `tenant_id`, `system_from`, and append-only semantics.
2. **Governed reads (optional re-point):** serve heavy / external / DS queries from the warehouse by
   re-pointing the `calc/reads.py`-backed wrappers behind a config flag; interactive OLTP reads stay
   on Postgres.
3. **External isolation:** re-express tenant isolation for warehouse readers via **row-access
   policies + secure views** (the RLS analog for read-only external access), while governed *writes*
   keep Postgres FORCE RLS.
4. **Reproducibility gate:** a warehouse-side check that no result surfaces without its lineage
   (TR-15) — the replication contract made executable.
5. **Governance stays on Postgres:** audit hash-chain, append-only enforcement, FOR-UPDATE
   lifecycles, maker-checker, RLS FORCE — unchanged.

## What we explicitly reject

- **Full consolidation** (moving the governed OLTP core, audit ledger, RLS, triggers, and lock-based
  lifecycles onto Snowflake). It converts engine-enforced guarantees into conventions — dissolving the
  product's governance thesis.
- **Coupling correctness to the read engine.** A result row's validity is a property of its (Postgres)
  write path, never of which store it is read from.
- **Premature schema work.** No denormalization / star-schema "preparation" now; the binding columns
  already port.

## References

- AD-004 / AD-004-R1 (datastore strategy; Postgres-first behind the market-data repo interface),
  AD-008/AD-013-R1/AD-015/AD-016 (tenancy + RLS), AD-012 (audit hash-chain) — `foundational_adrs.md`,
  `11_decision_log/architecture_decision_log.md`.
- OD-046 (columnar/time-series store trigger) — broadened to reference this AD.
- FW-RUN §5 reproducibility contract — `04_data_model/temporal_reproducibility_standard.md`.
- The read seam — `packages/shared-python/src/irp_shared/calc/reads.py`.
