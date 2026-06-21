# Phase P1A-1 Implementation Plan — Data Source & Lineage Skeleton

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1A1PLAN-001 |
| Version | 1.0 (Draft for Review) |
| Status | Draft |
| Owner | H-06 Engineering Lead |
| Approver | H-07 Product Owner (H-06 Engineering Lead; H-04 Data Owner consulted on OQ-P1A-1-2; H-03 CISO consulted on RLS/leak vectors) |
| Created | 2026-06-21 |
| Last Reviewed | 2026-06-21 |
| Related Documents | p1a_implementation_plan.md, p1a0_decision_record.md, ../02_requirements/requirements_traceability_matrix.md, ../02_requirements/requirements_backbone.md, ../03_architecture/foundation_slice.md, ../03_architecture/foundational_adrs.md, ../04_data_model/temporal_reproducibility_standard.md, ../04_data_model/audit_event_taxonomy.md, ../04_data_model/canonical_data_model_standard.md, ../06_security/entitlement_sod_model.md, ../09_compliance_controls/control_matrix_skeleton.md, ../11_decision_log/architecture_decision_log.md |
| Supported Build Rules | BR-5, BR-6, BR-11, BR-12, BR-13, BR-17, BR-19 |

## 1. Requirements included

P1A-1 implements **exactly one** Step-2 backbone requirement and **builds** one forward dependency:

- **REQ-LIN-001 — Lineage skeleton & capture** (backbone §7 CAP-14.1/14.2; RTM row 79; Phase **P1**; personas **P-DS** Data Steward + **P-IA** Internal Auditor; LoD **Platform**; controls **CTRL-006 / CTRL-013**; audit **BX-AUD**; entitlement **BX-ENT**; lineage column `-` because this requirement *builds* the rail rather than consuming it).
- **DEP-LIN** — P1A-1 *is* the build of the lineage forward dependency (RTM §4 dependency rollup: first needed in P1; required-by PPM-002/004, SMR-\*, PUB-\*, PRV-\*, MKT-\*, RPT-\*).

**Precise in-scope statement.** Establish the lineage data model (`data_source` node + `lineage_edge`) and the `record_lineage()` capture contract that every later governed write will call, plus retrieve-an-edge-by-id for verification — **capture + retrieve only, no query/graph traversal.** Concretely the slice ships:

1. `data_source` (ENT-038, **EV**, tenant-scoped) with DR-P1-3 nullable, non-enforcing maker-checker hook columns.
2. `lineage_edge` (ENT-042, **IA**, tenant-scoped) — a thin generic join referencing targets polymorphically.
3. `record_lineage(session, *, source, target_entity_type, target_entity_id, run_id=None)` — the BX-LIN capture utility (shared-python).
4. `GET /lineage/edges/{id}` — retrieval/verification read endpoint only.
5. One new entitlement permission `lineage.source.manage` (deny-by-default) plus reuse of the existing `lineage.view`.
6. One new audit event family for `data_source` registration (resolved in §6).
7. One Alembic migration creating both tables with FORCE RLS + tenant-isolation policy.

REQ-AUD-001 is **satisfied cross-cutting** (the `data_source` create path emits a taxonomy event), but is **not** scoped as a P1A-1 requirement of its own — it is verified by the shared audit-coverage enforcement test across P1A-1…4 (plan §7 REQ-AUD-001 note, CTRL-012).

**Backbone-shorthand reconciliation.** Backbone §7 CAP-14 lists both entities as `(IA)` shorthand. P1A-1 intentionally refines this to `data_source = EV` (mutable effective-dated config) and `lineage_edge = IA` (immutable append-only fact). This is a legitimate decomposition, not a conflict — see §10/§17 for the backbone correction.

## 2. Requirements excluded

The following are explicitly **out of scope** for P1A-1 and must not appear in any deliverable, test, or endpoint:

- **REQ-LIN-002 — Lineage query & extract** (CAP-14.3, RTM row 80, **Phase P7**): the "given a result, return the full upstream graph" capability, graph traversal, and any lineage visualization. P1A-1 ships **single-edge retrieve-by-id only**.
- **Field/column-level lineage mapping** and the full source-to-target *mapping* surface of CAP-14.1 (beyond the source-node + entity/run edge). Deferred (see OQ-P1A-1-3).
- **No public lineage write API** (no `POST/PUT /lineage*`) and **no public `data_source` create endpoint** — lineage is recorded only by the in-process `record_lineage()` utility; `data_source` is managed only by an internal/admin utility.
- **Sibling P1A slices**: REQ-MDG-001 model registry (P1A-2), REQ-DQR-001 data quality (P1A-3), REQ-INT-001 ingestion (P1A-4).
- **All domain requirements** (PPM/SMR/PUB/PRV/MKT/CRD/CPT/LIQ/SCN/LIM/BRC) and any domain entity: no instrument, issuer, portfolio, position, valuation, or risk-result entity.
- **Security Master, Reference Data, portfolio, positions, valuations, risk calculations, dashboards, reporting, private-asset ingestion**.
- **Real SSO / verified tenant identity** (P9 — the dev `X-User-Id` / `X-Tenant-Id` header shim remains *unverified* per DR-P1A0-3/AD-007).
- **Maker-checker approval enforcement** (DR-P1-3 → P6): the hook columns are nullable and non-enforcing.

QA scope note: the BX-LIN enforcement test uses a **synthetic governed-write target** precisely so the contract is tested without pulling in any excluded domain. No reproduction/regeneration tests (CTRL-018) — no runs/snapshots exist yet.

## 3. Proposed database entities

Two new tables, one migration. Both are tenant-scoped and carry FORCE RLS + a `tenant_isolation_<table>` policy reusing the migration `0001` pattern verbatim. ORM models follow the established `calc/models.py` pattern: `class X(PrimaryKeyMixin, TenantMixin, <TemporalMixin>, Base)` with an explicit `__temporal_class__`.

### 3.1 `data_source` (ENT-038, EV, tenant-scoped)

```
class DataSource(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base)
    __tablename__ = "data_source"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
```

| Column | Type | Null | Source / Notes |
|---|---|---|---|
| `id` | GUID PK | no | PrimaryKeyMixin |
| `tenant_id` | GUID (indexed) | no | TenantMixin; RLS predicate column; **server-stamped from context, never caller-supplied** |
| `valid_from` | DateTime(tz) | no (default `utcnow`) | EffectiveDatedMixin |
| `valid_to` | DateTime(tz) | yes | EffectiveDatedMixin (null = currently effective) |
| `created_at` / `created_by` / `updated_at` / `updated_by` | — | mixed | TimestampMixin |
| `record_version` | Integer | no (default 1) | **Additive** — satisfies canonical_data_model_standard.md §4 mandatory common column and §2A "system-time versioning" aspect of EV (EffectiveDatedMixin omits it) |
| `code` | String(150) | no | Stable business key (e.g. `BLOOMBERG_PX`, `INTERNAL_UPLOAD`) |
| `name` | String(255) | no | Display name |
| `source_type` | String(50) | no | Controlled vocab (FILE_UPLOAD / VENDOR_FEED / INTERNAL / MANUAL); free-text acceptable for the skeleton, promote to reference data (DM-N-08) before domains rely on it |
| `description` | String(500) | yes | |
| `is_active` | Boolean | no (default true) | |
| `approval_status` | String(20) | yes | **DR-P1-3 hook — non-enforcing** |
| `approval_ref` | String(255) | yes | **DR-P1-3 hook — non-enforcing**; maps to audit event `approval_ref` for future maker-checker linkage |
| `made_by` | String(255) | yes | **DR-P1-3 hook — non-enforcing** |
| `checked_by` | String(255) | yes | **DR-P1-3 hook — non-enforcing** |

Constraints/indexes: `UniqueConstraint('tenant_id','code', name='uq_data_source_tenant_code')` (mirrors `uq_role_tenant_id`); named tenant index in the migration to match the `0001` convention.

### 3.2 `lineage_edge` (ENT-042, IA, tenant-scoped)

```
class LineageEdge(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base)
    __tablename__ = "lineage_edge"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
```

`lineage_edge` is a **thin generic join carrying a polymorphic target reference** — it MUST NOT carry any domain foreign key, mirroring the `audit_event` `entity_type`/`entity_id` pattern. This is what makes the table domain-agnostic and lets a new target entity type be lineage-recorded **without a schema migration**.

| Column | Type | Null | Source / Notes |
|---|---|---|---|
| `id` | GUID PK | no | PrimaryKeyMixin |
| `tenant_id` | GUID (indexed) | no | TenantMixin; RLS predicate column; **server-stamped from context** |
| `system_from` | DateTime(tz) | no (default `utcnow`) | ImmutableAppendOnlyMixin — the only temporal axis for IA (TR-21); no `valid_from`/`valid_to` |
| `source_type` | String(50) | no | Upstream node kind: `data_source` \| `entity` (forward-compat: `data_snapshot` slots in here with no schema change) |
| `source_id` | GUID | no | Id of the `data_source` row or upstream entity |
| `target_entity_type` | String(100) | no | Polymorphic target kind (ENT-id / table name, e.g. `synthetic.governed_output`, `ingestion_batch`); **no FK** |
| `target_entity_id` | GUID | no | Downstream record id; **no FK** (integrity by-convention + BX-LIN test) |
| `edge_kind` | String(50) | no (default `ORIGIN`) | Relationship role, controlled vocab: `ORIGIN` \| `DERIVED_FROM` \| `INPUT_TO` |
| `run_id` | GUID | yes | **Logical (non-FK)** reference to `calculation_run.run_id` (FW-RUN); null for non-run-originated edges (e.g. raw ingestion origin) |

No `created_by`/`updated_by` (IA append-only — actor attribution lives in the governed write's audit event; `system_from` is the record timestamp). No second (valid) time axis (TR-21).

**Forward-compat (no schema change required later):** a future `data_snapshot` (AD-014, `calculation_run.input_snapshot_id` placeholder) becomes an upstream node via `source_type='data_snapshot'`; a risk result records `record_lineage(source=<input data_source>, target_entity_type='risk_result', target_entity_id=<id>, run_id=<calculation_run.run_id>)`, materializing the canonical `source→run→result` chain (canonical_data_model_standard.md §6). Do **not** add a hard FK to `calculation_run` now (most target domains do not yet exist; this matches `CalculationRun`'s own nullable placeholder FKs).

### 3.3 RLS (both tables)

Add both names to the migration's `TENANT_SCOPED_TABLES`-equivalent loop:

```
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <t> FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_<t> ON <t>
  USING (tenant_id::text = current_setting('app.current_tenant', true))
  WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true));
```

The explicit `WITH CHECK` is **mandatory** here (resolved — see §8/§15 OQ-P1A-1-SEC-1): these are new write-bearing tables and the SYSTEM_TENANT_ID global-source resolution (OQ-P1A-1-2) introduces read/write-scope divergence, so relying on `USING`-as-implicit-INSERT-check is not acceptable.

**lineage_edge IA immutability at the DB layer (resolved — see §15 OQ-P1A-1-IMMUT):** add `lineage_edge` to the migration's `APPEND_ONLY_TABLES` so the existing `irp_prevent_mutation()` trigger blocks UPDATE/DELETE, **and** add an ORM `before_update`/`before_delete` guard (mirroring `audit/models.py`) so the IA classification is provable on both SQLite-local and Postgres-CI. `data_source` is EV (mutable) and does **not** get the trigger.

## 4. Proposed API surfaces

Exactly **one** public endpoint; no write API.

| Surface | Method | Auth | Behavior |
|---|---|---|---|
| `GET /lineage/edges/{id}` | read | `require_permission('lineage.view')` under `get_tenant_session` | Retrieval/verification only. Returns the edge by id with source/target fields populated, scoped to the caller's tenant by RLS. |

**Hard guardrails (Scope lens):** reject any `POST/PUT /lineage*`; reject any `/lineage/graph`, `/lineage/trace`, `/lineage/{result}/upstream`, or traversal/query endpoint (REQ-LIN-002/P7); reject any public `POST /data-sources` create endpoint.

**Endpoint requirements (Security lens):**
- MUST depend on `get_tenant_session` (sets `app.current_tenant`), **not** `get_db`, so RLS scopes the lookup to the caller's tenant.
- Entitlement (403) is checked **first**, then the RLS-scoped lookup yields **404** for both "not found" and "exists in another tenant" — the two cases must be **indistinguishable** (no existence/oracle leak). Never 200 for a cross-tenant id.
- Missing principal headers → 401.

`data_source` is managed only via an internal/admin utility gated by `lineage.source.manage`; `record_lineage()` is an in-process utility, not an endpoint.

## 5. Worker / CLI impact

- **No standalone worker or CLI in P1A-1.** No lineage-backfill job, no lineage-export CLI, no graph-builder worker (those are query/reporting concerns, P7/P8).
- **`record_lineage()` MUST live in shared-python** (`irp_shared.lineage`, sibling to `irp_shared.audit` / `irp_shared.calc`), **not** in `apps/backend`. The same single contract is invoked by (a) the FastAPI request path (future domain writes), (b) worker/job paths via `run_in_tenant` (AD-016), and (c) P1A-4 ingestion. Placing it in backend would couple workers to the web app and break the single-contract guarantee.
- `record_lineage()` takes a **caller-managed `Session`** (exactly like `record_event(session, ...)` and `calc` `create_run`) and inserts the edge **in the same transaction** as the governed write it describes — this is what gives BX-LIN its "no governed output without a lineage path" atomicity.
- For now the SQLite unit tests call `record_lineage()` directly with an explicit tenant; P1A-4 will exercise it under `run_in_tenant`. It MUST run under tenant context, never under the AD-015 BYPASSRLS ops role.

## 6. Audit events — resolved

**Decision (resolves OQ-P1A-1-4 / OQ-P1A-1-AUDIT, option C): ADD two new DATA-family taxonomy codes; do NOT overload `CONFIG.CHANGE` or `DATA.INGEST`.**

| Governed write | Event code | EVT id | Notes |
|---|---|---|---|
| `data_source` create | `DATA.SOURCE_REGISTER` | EVT-026 | `record_event(session, event_type='DATA.SOURCE_REGISTER', tenant_id=<ctx>, actor_type='user', actor_id=<admin>, source_module='lineage', entity_type='data_source', entity_id=<source_id>, action='create', after_value={code,name,source_type,approval_status:null}, data_classification='DC-2')` |
| `data_source` update | `DATA.SOURCE_UPDATE` | EVT-027 | `action='update'` with before/after diff. `data_source` is EV, so updates are first-class versioned changes that MUST be audited (TR-06/TR-07). |
| `lineage_edge` write via `record_lineage()` | **none** | — | **No separate audit event by default.** The edge is metadata of the already-audited governed write that produced the target; `record_lineage()` runs in the **same transaction** as that write. A per-edge event would double-count and create lineage-of-lineage recursion risk. |
| Seeding `lineage.source.manage` into the bootstrap catalog | **none** (runtime) | — | Seed is covered by migration provenance, consistent with how `data.upload`/`lineage.view` were seeded — no per-permission runtime event. |

**Reserved-but-unused in P1A-1:** `LINEAGE.RECORD` (EVT-028) is **reserved** in the taxonomy for the **P7 standalone lineage-correction/backfill** case (REQ-LIN-002), where an edge is created/amended *outside* an audited governed write. Documented as reserved so P7 does not re-litigate. Do **not** introduce a broad `LINEAGE.*` family now.

**Rationale.** `data_source` is the provenance **root** bound by CTRL-006/CTRL-013; a dedicated code lets the lineage/audit-coverage controls assert source-registration completeness directly and keeps `DATA.INGEST` scoped to actual ingestion (P1A-4). A generic `CONFIG.CHANGE` would bury provenance among config noise and weaken control evidence. Cost is two taxonomy rows; `event_type` is a free-form string (no code-level allowlist exists), so no existing assertion breaks. The DATA category already begins at EVT-020 (`INGEST/VALIDATE/CORRECTION/RECONCILE/PURGE`); 026/027 extend it cleanly.

**Fail-closed (CTRL-005/CTRL-012/CTRL-032, AUD-04):** the `record_event` write for `data_source` create/update MUST occur in the **same tenant-scoped transaction** as the data row; if the audit insert is rejected (RLS or chain failure) the `data_source` row MUST roll back, not silently persist.

**Correlation:** `record_lineage()` and its producing governed write should share a `correlation_id` so an auditor can join an edge to the producing write's audit event without a per-edge event.

## 7. Entitlement checks

All access is `require_permission`-gated, deny-by-default, tenant-scoped (BX-ENT, CTRL-011), sequenced under `get_tenant_session` so RLS does not false-deny the principal's own `role`/`user_role` rows.

| Permission | Status | Gates | Granted to |
|---|---|---|---|
| `lineage.view` | **Exists** (bootstrap.py line 24) | `GET /lineage/edges/{id}` | data_steward, auditor_3l (and any read role already holding it) |
| `lineage.source.manage` | **NEW** | `data_source` admin/internal create/update utility | **data_steward** (operational owner of data sources) + **platform_admin** (holds `ALL_CODES`) |

**Decision (resolves OQ-P1A-1-SEC-3): grant `lineage.source.manage` to `data_steward` and `platform_admin` only.** Do NOT grant to `risk_analyst_1l`, `risk_manager_2l`, or `auditor_3l` — those are read-only; granting source management would weaken least-privilege (ENT-P-01) and 3L independence.

`lineage.source.manage` MUST be (1) added to `bootstrap.py` `PERMISSIONS` and the `data_steward` template, and (2) covered by a **deny-by-default test** (a principal lacking it is denied; a `lineage.view`-only principal cannot manage `data_source`).

**`record_lineage()` itself is NOT separately permission-gated** — it is an internal contract called inside an already-entitlement-gated governed write; re-gating it would create a second, redundant authorization seam and risk false-denies. The calling governed write carries the entitlement. This matches REQ-LIN-001's "audited at the source level" acceptance. Do **not** add `lineage.write` / `lineage.record` or per-source granular permissions.

## 8. RLS / tenant-context behavior (built on P1A-0)

Both tables are tenant-scoped and rely entirely on the P1A-0 wiring (AD-016): per-session `app.current_tenant` via `set_config(..., is_local=true)` (transaction-local) + durable pool `RESET`; `get_tenant_session` dependency; `run_in_tenant` for workers. All P1A-1 DB surfaces MUST run under this context; missing context **fails closed**.

Confirmed behaviors (replicating the proven `audit_event` behavior in `test_tenant_context_pg.py`):
- **Policy form:** `ENABLE` + `FORCE` ROW LEVEL SECURITY (FORCE so the app role is also subject to RLS) + `tenant_isolation_<t>` with `USING` **and** explicit `WITH CHECK` (§3.3).
- **No-context fail-closed:** with the GUC unset, `current_setting('app.current_tenant', true)` returns NULL → reads return empty (`tenant_id::text = NULL` is never true), INSERTs are rejected with **SQLSTATE 42501**. `record_lineage()` under no context MUST exhibit this rejection.
- **Tenant-mismatch denied:** under context A, inserting `tenant_id=B` is rejected by the `USING`/`WITH CHECK` predicate.
- **Transaction-local auto-clear:** `is_local=true` context clears at COMMIT/ROLLBACK; durable pool RESET on check-in prevents stale-GUC cross-tenant leak.
- **Single-transaction invariant:** `record_lineage()` MUST NOT COMMIT/ROLLBACK mid-call in a request scope — a mid-call commit drops the transaction-local context and the next autobegun transaction runs context-less and writes fail closed.

**Ops-role isolation (AD-015):** the BYPASSRLS `irp_ops` role's grants are scoped to `audit_event`/`audit_checkpoint` only; it MUST NOT be granted SELECT/INSERT on `data_source` or `lineage_edge`. No P1A-1 code path may connect via the ops `DATABASE_URL`. The app DB role stays non-superuser/non-BYPASSRLS. A regression test asserts the ops role has no grant on the new tables.

**Cross-tenant reference leak vector (primary security risk, resolved — OQ-P1A-1-SEC-2):** RLS protects the *edge row* but does NOT validate that a referenced source/target belongs to the same tenant (ids are opaque GUIDs; an FK cannot span the RLS boundary). Therefore `record_lineage()` MUST: (1) **stamp the edge's `tenant_id` server-side** from `current_tenant`/the principal, never from caller input; (2) when `source` is a `data_source`, **resolve it through the RLS-scoped session** so a cross-tenant id resolves to zero rows and fails closed; (3) treat `target_entity_id` as same-tenant-by-construction (it is the tenant's own governed output) and document that cross-tenant references are out of contract.

**SYSTEM_TENANT_ID global sources (OQ-P1A-1-2 resolution):** global/template sources are held under the reserved `SYSTEM_TENANT_ID` (`00000000-0000-0000-0000-000000000001`, already defined in bootstrap.py) with **FORCE RLS retained** (no RLS-exempt table). Only system-tenant context can write those rows, satisfying AD-013's "global must be write-restricted/leak-free." **Cross-tenant READ of system-tenant sources is NOT enabled in P1A-1** (would require widening the `USING` clause to `tenant_id = current OR tenant_id = SYSTEM_TENANT_ID`); the P1A-1 policy stays strict tenant-equality only, and any later widening must be a deliberate, tested RLS change — never a doorway to general global Reference Data (a strict exclusion).

## 9. Lineage behavior — `record_lineage` contract + BX-LIN enforcement

P1A-1 *is* the build of DEP-LIN and establishes the **BX-LIN** contract (backbone §5: "Every governed output binds source→run lineage"; BR-6/BR-13; CTRL-006/CTRL-013) that 40+ downstream requirements will call. DoD D7 ("results bind full lineage source→run→result") becomes executable for downstream slices only after P1A-1.

**Write seam:**
```
record_lineage(session, *, source, target_entity_type, target_entity_id, run_id=None)
```
inserts one or more `lineage_edge` rows linking an upstream `data_source`/entity → target. It maps cleanly onto the schema: `source` → `source_type` + `source_id`; `target_entity_type`/`target_entity_id` verbatim; `run_id` → nullable `run_id` column. It stamps `tenant_id` server-side and resolves `source` through the RLS-scoped session (§8). The contract is **generic and forward-extensible** — Security Master, Portfolio, Market/Credit/Liquidity Risk, and Private Assets each record lineage by calling it with their own `entity_type`/`id` (and `run_id` for derived results) with **no schema change**.

**Verification/enforcement seam:**
```
assert_has_lineage(session, target_entity_type, target_entity_id) -> raises LineageMissingError | returns path
```
raises `LineageMissingError` when no edge path exists, returns the (single-hop, tenant-scoped) `source→target` path otherwise. This operationalizes **CTRL-013** (no-bypass): a governed write lacking a lineage edge fails the check. Because no real domain output exists yet, the enforcement test uses a **synthetic governed-write target** (e.g. `target_entity_type='synthetic.governed_output'`) plus a synthetic `governed_write_with_check()` helper — the same `assert_has_lineage` is what P1A-4 ingestion and all later governed writes will be tested against (the seam must accept arbitrary `target_entity_type` so it transfers).

**Scope fences (in scope = capture + single-edge retrieve only):** OUT of scope and must be fenced — recursive/multi-hop graph traversal or "full upstream graph" assembly (REQ-LIN-002/P7), lineage visualization, field/column-level lineage (entity/run-level only), and **lineage of the lineage tables themselves** (avoid recursion). The completeness test asserts the *presence and retrievability* of an edge for a governed write, not graph traversal.

**Auditability of lineage itself:** the `data_source` root is independently audited at create/update (`DATA.SOURCE_REGISTER`/`UPDATE`), so every edge's source node has hash-chained provenance; `lineage_edge` traceability comes from being co-transactional with an audited governed write and sharing its `correlation_id`.

## 10. Temporal classification

| Entity | Class | Mixin | Authority |
|---|---|---|---|
| `data_source` (ENT-038) | **EV** | `EffectiveDatedMixin` | temporal_reproducibility_standard.md §2A EV list (ENT-038 data_source). Config: steward edits endpoint/status over time → versioned history but not dual-axis as-of. Not risk-driving/reconstructable → **no FR promotion**. |
| `lineage_edge` (ENT-042) | **IA** | `ImmutableAppendOnlyMixin` | temporal_reproducibility_standard.md §2A IA list (lineage edges ENT-042). Immutable fact-of-capture pinned by the write's own time; corrections = new edge, never in-place update (TR-05/TR-06). No second (valid) axis (TR-21). |

Each entity declares `__temporal_class__` (BR-19) and records the class in the data dictionary per §2A.

**Two flagged doc discrepancies to reconcile (not model changes):**
1. Backbone §7 CAP-14 (and the parenthetical near requirements_backbone.md L239) tags both entities `(IA)`. The plan/standard split (`data_source=EV`, `lineage_edge=IA`) is **authoritative**. Update the backbone CAP-14 data column to read `lineage_edge (IA), data_source (EV)` when REQ-LIN-001 moves off Draft (avoids a DoD D5 / docs-check discrepancy and an implementer picking the wrong mixin).
2. `EffectiveDatedMixin` provides only `valid_from`/`valid_to` — it lacks the `system_from`/`record_version` that §2A's "system-time versioning" description and canonical §4 imply for EV. For the skeleton this is acceptable (version history leans on the audit trail) but `data_source` adds an explicit `record_version` column (§3.1). Do **not** modify the shared mixin for one entity; revisit a richer EV mixin in P1A-2/P1A-3 if multiple EV config tables need it. Flag to R-05/H-04 that the mixin is lighter than the §2A EV definition.

## 11. Data dictionary impact

Additions limited to exactly the two new entities and the new vocabulary this slice introduces (per DM-N-06/DM-N-07, every field needs a DC-\* classification tag):

- **`data_source` (ENT-038, EV):** all columns; `code`/`name`/`source_type`/`description`/`is_active` are **DC-1/DC-2** (registry metadata, not client data). DR-P1-3 hook columns documented as "non-enforcing, reserved for P6 maker-checker." Record the temporal class (EV) and `record_version`.
- **`lineage_edge` (ENT-042, IA):** columns `source_type`/`source_id`/`target_entity_type`/`target_entity_id`/`edge_kind`/`run_id`, **DC-1** structural metadata. Flag for H-04 Data Owner: lineage can be *indirectly* sensitive (it reveals which sources feed which records), so **DC-2 is defensible**. Record the temporal class (IA).
- **Event codes** `DATA.SOURCE_REGISTER` (EVT-026), `DATA.SOURCE_UPDATE` (EVT-027) as controlled-vocabulary entries (CTRL-004), with `LINEAGE.RECORD` (EVT-028) marked reserved/unused.
- **Permission code** `lineage.source.manage`.

Design notes (future-table boundaries, not P1A-1 deliverables): the canonical mandatory `source_id` FK (every domain record → `data_source`, BR-13) is a future concern on **domain** tables; it must be added **nullable** on the first domain entities to avoid a chicken-and-egg bootstrap, and an `INTERNAL_UPLOAD` system source should be seeded then. Do NOT register domain/canonical-mapping/model-registry/DQ entities now.

## 12. Tests

Split by harness: **SQLite-local** (fast unit; RLS is a no-op) reuses the in-memory `session` + `seed` fixtures in `packages/shared-python/tests/conftest.py`; **Postgres-CI** (RLS/fail-closed) runs in the CI `migration` job under the **constrained non-superuser `irp_app` role**, reusing the `app_url` fixture + `_is_rls_violation` (SQLSTATE 42501) helper in `test_tenant_context_pg.py`. RLS proofs MUST NOT run as superuser or on SQLite (they pass vacuously). Coverage target: DR-P1-4 advisory ≥85% foundation on the new modules.

**SQLite-local — model/utility (`packages/shared-python/tests/test_lineage.py`):**
1. `DataSource.__temporal_class__ == EV` (valid_from/valid_to present); `LineageEdge.__temporal_class__ == IA` (system_from present, no valid_to).
2. `record_lineage(...)` inserts ≥1 edge linking source→target; row `tenant_id == context tenant`; queryable.
3. Edge retrievable by id with source/target fields populated (service-level proof of the GET read path).
4. `run_id` passed through and persisted.
5. **(negative)** UPDATE/DELETE on a persisted `lineage_edge` raises via the ORM append-only guard.
6. `data_source` create emits exactly one `DATA.SOURCE_REGISTER` event (`entity_type='data_source'`, `entity_id==ds.id`) **and** `verify_chain(session, tenant).ok is True`; `data_source` update emits `DATA.SOURCE_UPDATE` with before/after.
7. `UniqueConstraint(tenant_id, code)` rejects duplicate code within a tenant, allows same code across tenants; DR-P1-3 hooks default NULL.

**SQLite-local — BX-LIN enforcement (headline negative test):**
8. **(negative)** synthetic governed write that does NOT call `record_lineage` → `assert_has_lineage` raises `LineageMissingError` (CTRL-013).
9. (happy companion) same flow with `record_lineage` first → no raise; complete `source→target` path returned (CTRL-006).
10. `assert_has_lineage` filters by `tenant_id` so a B-tenant edge does not satisfy an A-tenant target's check (logic-level).
11. **(negative)** `record_lineage` alone emits **no** audit event (locks the metadata-of-governed-write decision); no self-referential lineage-of-lineage edge is created.

**SQLite-local — entitlement deny matrix (using `seed`):**
12. **(negative)** no grant → `has_permission(...,'lineage.source.manage',...)` is False.
13. **(negative)** missing permission link → manage denied.
14. **(negative)** tenant mismatch → False.
15. **(negative)** `require_permission(...,'lineage.source.manage',...)` raises `PermissionDenied` when ungranted.
16. `lineage.source.manage` in `ALL_CODES`, granted to `platform_admin`/`data_steward`, **not** to read-only roles (extend `test_entitlement_bootstrap.py`).

**Backend HTTP deny (`apps/backend/tests/test_lineage_endpoint.py`, mirror `test_entitlement_dependency.py`):**
17. **(negative)** caller without `lineage.view` → 403.
18. **(negative)** missing principal headers → 401.
19. `lineage.view` granted → 200 returns the edge.

**Postgres-CI (constrained `irp_app`; after `alembic upgrade head`):**
20. `data_source` isolation: context A sees only A's rows; B invisible.
21. `lineage_edge` isolation: same.
22. **(negative, fail-closed)** no `app.current_tenant` → INSERT into both tables raises with `_is_rls_violation` True (42501); SELECT count == 0.
23. **(negative)** context A, insert `tenant_id=B` → rejected (validates `USING` + `WITH CHECK`).
24. **(negative, cross-tenant ref)** `record_lineage` with a `source`/`data_source` id belonging to another tenant resolves to zero under the caller's RLS scope → fails closed (no cross-tenant edge created).
25. `GET /lineage/edges/{id}` for an edge owned by tenant B requested by a tenant-A principal → **404** (RLS-hidden), indistinguishable from non-existent; never 200.
26. **(regression)** `irp_ops` BYPASSRLS role has **no** grant on `data_source`/`lineage_edge`.
27. **(append-only at DB)** `lineage_edge` in `APPEND_ONLY_TABLES`: UPDATE/DELETE raises via `irp_prevent_mutation()`.
28. SYSTEM_TENANT_ID source row writable only under system-tenant context.

No tests for graph traversal/visualization, field-level lineage, or any domain output.

## 13. Acceptance criteria

The slice is **DONE** (capture + retrieve-by-id only) when:

- **AC-1 (edge create + retrieve):** `record_lineage` inserts ≥1 `lineage_edge` with source ref, `target_entity_type`, `target_entity_id`, optional `run_id`, all tenant-tagged; retrievable by id via `GET /lineage/edges/{id}`. (T2/3/4)
- **AC-2 (BX-LIN enforcement / CTRL-013):** a governed write that does NOT record lineage fails `assert_has_lineage`; one that does passes and yields a complete `source→target` path — proven with a synthetic target. (T8/9)
- **AC-3 (lineage completeness / CTRL-006):** for a recorded governed output, `assert_has_lineage` returns a non-empty `source→target` path retrievable by id. (T9)
- **AC-4 (tenant isolation / CTRL-011, BR-17):** under PG RLS with the constrained app role, both tables are visible only to the owning tenant; cross-tenant reads return zero rows. (T20/21)
- **AC-5 (fail-closed):** with no tenant context, writes are rejected (42501) and reads return empty — never an open read. (T22)
- **AC-6 (entitlement deny-by-default / CTRL-011, BR-11):** `lineage.source.manage` and `lineage.view` are deny-by-default; ungranted → PermissionDenied/403; missing principal → 401; the new code is in the bootstrap catalog with a deny test. (T12–19)
- **AC-7 (audit on source create / CTRL-005, BX-AUD):** `data_source` create emits exactly one `DATA.SOURCE_REGISTER` (correct tenant/actor/entity), update emits `DATA.SOURCE_UPDATE` with before/after, the per-tenant hash chain still verifies, and a simulated audit-capture failure rolls back the `data_source` row (fail-closed, AUD-04/CTRL-032). (T6)
- **AC-8 (architecture / extensibility):** `record_lineage()` lives in `irp_shared` (importable by backend AND workers without importing the web app) and records edges via a polymorphic `(target_entity_type, target_entity_id)` reference with NO domain FK, demonstrably allowing a new target entity type to be lineage-recorded without a schema migration; `run_id`, when supplied, is a logical reference to `calculation_run.run_id`.
- **AC-9 (temporal / BR-19, CTRL-017):** `data_source` declares EV, `lineage_edge` declares IA (no second axis); `lineage_edge` is append-only at the DB and ORM layers. (T1/5/27)
- **AC-10 (no recursion):** lineage of the lineage tables is not recorded; `record_lineage` alone emits no audit event. (T11)

**DoR/DoD posture for the slice:** R1–R12 satisfiable now (R5 Calc = N/A — lineage has no calculation; R7 ModelGov = N/A — no model). DoD D6 (audit), D12 (entitlement), D5 (temporal), D13 (no-bypass) are all in force. DoD D7 is **N/A-marked for this slice's own exit** ("builds the rail; no own governed output"), with the synthetic-write test standing in; first real proof is at P1A-4 ingestion. "Done" boundary: capture + retrieve-by-id only — any test needing upstream-graph traversal has crossed into REQ-LIN-002/P7.

## 14. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Scope creep into full lineage graph/query** (REQ-LIN-002/P7) — CAP-14.1's title "source-to-target mapping" invites it. | Capture + retrieve-by-id ONLY; no `/lineage/graph|trace|upstream` endpoint or traversal test; lock granularity at entity/run-level (OQ-P1A-1-3). |
| R2 | **"Governed output" undefined before any domain exists** — the enforcement test may pass vacuously and the real contract is unproven until P1A-4. | Use a synthetic non-domain stand-in now; require P1A-4 acceptance to re-exercise `record_lineage` on the first real governed write; mark REQ-LIN-001 "done" as contract-level with first real proof at P1A-4. |
| R3 | **`record_lineage()` placed in `apps/backend`** would couple workers/CLI/ingestion to the web app and break the single-contract guarantee. | Require `irp_shared.lineage` placement (AC-8). |
| R4 | **Node+edge model** would introduce a generic `lineage_node` table competing with real domain tables (violates ARCH-P-01). | Edge-only with polymorphic `(entity_type, entity_id)` (OQ-P1A-1-1). |
| R5 | **Cross-tenant reference leak** — an edge in tenant A pointing at tenant B's id; RLS protects the row but not reference integrity, and FKs can't cross the RLS boundary. | Server-side `tenant_id` stamping + RLS-scoped source resolution + same-tenant-by-construction documentation (OQ-P1A-1-SEC-2). |
| R6 | **Existence/oracle leak** on `GET /lineage/edges/{id}` via distinguishable 403/404/200. | Entitlement-first then RLS-scoped indistinguishable 404. |
| R7 | **`lineage_edge` immutability untested at DB layer** — the `0001` trigger covers audit tables only. | Add `lineage_edge` to `APPEND_ONLY_TABLES` + ORM guard; test both (OQ-P1A-1-IMMUT). |
| R8 | **Temporal-class ambiguity** — backbone `(IA)` vs implemented `data_source=EV`; implementer could pick the wrong mixin. | Resolve the doc before coding (§10/§17). |
| R9 | **Audit-coverage gap** — `event_type` is free-form (no allowlist), so a typo'd/omitted code passes silently. | Add `data_source` create/update assertions to the cross-cutting audit-coverage test; optional shared event-code constants module. |
| R10 | **Per-edge audit / control over-claim** — a future contributor adds `LINEAGE.RECORD` "for completeness" (noise + recursion), or CTRL-006/013 are marked Implemented on the skeleton. | Document the metadata-of-governed-write decision; keep `LINEAGE.RECORD` reserved-only; mark CTRL-006/013 skeleton-level/partially exercised. |
| R11 | **Permission/audit proliferation** — `lineage.write`/per-source codes or a broad `LINEAGE.*` family. | Exactly ONE new permission (`lineage.source.manage`) and at most two new audit codes. |
| R12 | **SYSTEM_TENANT_ID global source as a backdoor** to general global Reference Data (strict exclusion). | Narrow read-scope divergence only; strict tenant-equality policy in P1A-1; any widening is a deliberate, tested later change. |
| R13 | **Mid-call COMMIT in `record_lineage`** drops transaction-local context → subsequent context-less writes fail closed (availability bug masking isolation). | Honor the single-transaction-request invariant; re-set context after any intentional commit. |

## 15. Open decisions — all resolved

| ID | Question | Decision & rationale |
|---|---|---|
| **OQ-P1A-1-1** | Edge-only (`source_ref→target_ref`) vs node+edge model. | **Edge-only.** `data_source` is the only first-class node the lineage origin needs; instrument/position/calculation_run/risk_result are first-class in their own bounded contexts and are referenced polymorphically, not duplicated as generic nodes. A node table would create a competing second source of truth (violates ARCH-P-01) and a mapping-maintenance burden for zero P1 benefit. Matches canonical §6 and the `audit_event` polymorphic pattern; an optional `edge_kind` column preserves room for richer semantics without a node table. Graph/query nodes are REQ-LIN-002/P7. |
| **OQ-P1A-1-2** | `data_source` tenant-scoped only vs global/system sources (AD-013). | **Tenant-scoped by default; global/template sources under the reserved `SYSTEM_TENANT_ID` with FORCE RLS retained (no RLS-exempt table).** Matches AD-013 (global standard vs tenant-scoped proprietary) and reuses the established bootstrap pattern; only system-tenant context can write those rows (AD-013 "write-restricted/leak-free"). **Do NOT enable cross-tenant READ of system sources in P1A-1** — defer the `USING`-clause widening until a concrete shared-source need, with its own isolation test. Never a doorway to general global Reference Data. |
| **OQ-P1A-1-3** | Lineage granularity: entity/run-level vs field/column-level. | **Entity/run-level only** (`source → target_entity_type+target_entity_id`, optional `run_id`). Field-level mapping is a strict exclusion and the wrong altitude for the skeleton and CTRL-006; the generic shape supports a later nullable `target_field` extension without breaking the contract, so deferring costs nothing. **Single most important product-scope guardrail.** |
| **OQ-P1A-1-4** | Does P1A-1 fully satisfy REQ-LIN-001? | **Declare REQ-LIN-001 Done at entity/run granularity at slice exit.** Record in the RTM that CAP-14.1 *field-level* mapping and CAP-14.3 query are explicitly outside REQ-LIN-001's acceptance (they live in REQ-LIN-002/P7 and later mapping work). The backbone acceptance is path-completeness, which the skeleton meets; keeping it open would block 40+ downstream BX-LIN consumers. Make the boundary explicit so "Done" is honest; first *real* proof lands at P1A-4. |
| **OQ-P1A-1-AUDIT** (= audit-code decision) | Event code for `data_source` create/update; does `record_lineage` emit an event? | **Add `DATA.SOURCE_REGISTER` (EVT-026) + `DATA.SOURCE_UPDATE` (EVT-027); `record_lineage` emits NO event; reserve `LINEAGE.RECORD` (EVT-028) for P7.** Two codes give clean CTRL-005 completeness assertions; per-edge events are noise/recursion. (See §6.) |
| **OQ-P1A-1-SEC-1** | Explicit `WITH CHECK` on the new RLS policies, or `USING`-only (as `0001`)? | **Add explicit `WITH CHECK` on both.** New write-bearing tables; removes reliance on `USING`-as-implicit-INSERT-check, self-documents cross-tenant-write rejection, and future-proofs the SYSTEM_TENANT_ID read/write-scope divergence. One clause per policy. |
| **OQ-P1A-1-SEC-2** | How does `record_lineage()` prevent cross-tenant references (FKs can't span RLS)? | **Never accept caller-supplied `tenant_id`; stamp it from context; resolve `source`/`data_source` through the RLS-scoped session (cross-tenant id → zero rows → fail closed); document `target_entity_id` as same-tenant-by-construction.** Closes R5 without cross-tenant FKs. |
| **OQ-P1A-1-SEC-3** | Which role templates get `lineage.source.manage`? | **`data_steward` + `platform_admin` only.** Not the read-only `risk_*`/`auditor_3l` roles (least-privilege ENT-P-01; 3L independence). Deny-by-default test required. |
| **OQ-P1A-1-IMMUT** | `lineage_edge` (IA) immutability: DB trigger or ORM only? | **Both.** Add `lineage_edge` to the migration's `APPEND_ONLY_TABLES` (`irp_prevent_mutation()` trigger) AND an ORM `before_update`/`before_delete` guard — so IA is provable on Postgres-CI *and* SQLite-local. Otherwise the IA classification is untested at the DB boundary. |
| **OQ-P1A-1-VER** | Add `record_version` to EV `data_source`; is the lighter `EffectiveDatedMixin` acceptable? | **Add a `record_version` Integer column on `data_source` now** (cheap; satisfies canonical §4 and §2A's system-time-versioning aspect). Do NOT change the shared mixin for one entity; revisit a richer EV mixin in P1A-2/P1A-3. Flag to R-05/H-04 that `EffectiveDatedMixin` is lighter than §2A's EV definition. |

No open decision blocks implementation (see §18).

## 16. Controls impacted — exact CTRL row update text

Update `09_compliance_controls/control_matrix_skeleton.md` §3 as follows (status-and-evidence edits only; no new CTRL row is required — existing CTRL-005/006/011/012/013/032 carry P1A-1):

- **CTRL-005** (Data-changing actions emit audit events): Status remains **Implemented (1E + P1A-1)**; add `data_source` create/update to the covered set. Test/Assurance: extend the audit-coverage enforcement test to assert `data_source` create/update emit `DATA.SOURCE_REGISTER`/`DATA.SOURCE_UPDATE`. Evidence: audit events (ENT-045) for `data_source`.
- **CTRL-006** (Risk results bind full lineage (source→run)): Status **Planned → Designed (skeleton)**. Test/Assurance: "Lineage completeness test (skeleton): a recorded governed output has a complete `source→target` path retrievable by id (`record_lineage` + `GET /lineage/edges/{id}`)." Evidence: `lineage_edge` rows + retrieval test. **Note:** full `source→run→result` binding completes when calc runs exist (P2+); P1A-1 establishes the BX-LIN contract only — do NOT mark Implemented.
- **CTRL-011** (No module bypasses entitlement framework; tenant isolation end-to-end): Status remains **Implemented (1E + P1A-0)**. Coverage note: new permission `lineage.source.manage` is deny-by-default with a deny test; `data_source` + `lineage_edge` are FORCE-RLS tenant-scoped under P1A-0 context with explicit `WITH CHECK`; new PG isolation/fail-closed/mismatch tests under the constrained `irp_app` role.
- **CTRL-012** (No module bypasses audit framework): Status remains **Planned/Designed**; add `data_source` create/update to the cross-cutting audit-coverage enforcement test scope ("no governed write without a taxonomy event").
- **CTRL-013** (No module bypasses lineage framework): Status **Planned → Designed (skeleton)**. Test/Assurance: "BX-LIN enforcement test: a governed write lacking a lineage edge fails the lineage-coverage check (skeleton; definition-of-governed-output stubbed via a synthetic target until domains exist)." Evidence: lineage coverage test. This is the load-bearing new control behavior in P1A-1 — do NOT mark Implemented.
- **CTRL-032** (Failed audit capture blocks governed change, AUD-04): no status change; add `data_source` create/update to its scope note as a new governed write that inherits fail-closed semantics (`record_event` in the same transaction; rollback on audit failure).

## 17. Documentation updates (at slice exit, DoD D19)

1. **RTM** (`requirements_traceability_matrix.md`) row 79: REQ-LIN-001 Status Draft → In-Progress → **Done** (entity/run granularity); annotate that CAP-14.1 field-level mapping and CAP-14.3 query are outside its acceptance (REQ-LIN-002/P7).
2. **Backbone** (`requirements_backbone.md`): §7 CAP-14 data column → `lineage_edge (IA), data_source (EV)` (fixes the `(IA)` shorthand / L239 parenthetical); annotate that 14.3 query/viz remains P7; §6 Forward Dependency Registry → flip **DEP-LIN** from "Future (CAP-14)" to "Exists (capture skeleton; query is REQ-LIN-002/P7)."
3. **Control matrix** (`control_matrix_skeleton.md`): CTRL-005/006/011/012/013/032 row edits per §16; add a P1A-1 line to the §4 Coverage Note.
4. **Audit taxonomy** (`audit_event_taxonomy.md`): extend the DATA row with `DATA.SOURCE_REGISTER` (EVT-026), `DATA.SOURCE_UPDATE` (EVT-027); RESERVE `LINEAGE.RECORD` (EVT-028, P7, unused). Keep source events under `DATA.*`; introduce a `LINEAGE.*` family only for the reserved P7 code.
5. **Entitlement / SoD** (`entitlement_sod_model.md` + bootstrap catalog): register `lineage.source.manage` (granted to `data_steward`/`platform_admin`).
6. **Data dictionary / canonical model**: register ENT-038 `data_source` (EV, `record_version`, DR-P1-3 hooks) and ENT-042 `lineage_edge` (IA) with DC-\* tags and temporal classes.
7. **DoD §6 dependency note**: DEP-LIN now available, so downstream D7 is no longer auto-Blocked.
8. **CI enforcement overview** (`08_testing_qa/ci_enforcement_overview.md`): note the new PG RLS tests for `data_source`/`lineage_edge` in the `migration` job.

**Guardrail:** do NOT pre-document REQ-LIN-002 query/visualization design or field-level mapping — those belong to P7 planning. UJ-7 step 3 (P-IA "trace result to source") is only *partially* enabled by P1A-1 (retrieve-by-id, not graph traversal); document that P-IA gets capture-verification now and full upstream-graph trace at P7.

## 18. Is P1A-1 ready to implement?

**YES.** The slice is well-bounded, fully additive (grep confirms zero existing `data_source`/`lineage_edge`/`record_lineage`/`DataSource`/`LineageEdge` artifacts), and its only hard prerequisite — P1A-0 tenant context — is landed (AD-015/AD-016). No new ADR is required: this slice realizes existing AD-005 (temporal), AD-008/AD-013 (tenancy), and canonical §6 lineage hooks.

**No open decision blocks implementation** — every OQ in §15 is resolved with a concrete, scope-preserving recommendation:
- Architecture/data: edge-only (OQ-1), entity/run granularity (OQ-3), `record_version` on `data_source` (OQ-VER).
- Tenancy: tenant-scoped + SYSTEM_TENANT_ID global rows, RLS retained, no cross-tenant read (OQ-2).
- Audit: `DATA.SOURCE_REGISTER`/`UPDATE`, no per-edge event, reserve `LINEAGE.RECORD` (OQ-AUDIT).
- Security: explicit `WITH CHECK` (OQ-SEC-1), server-side tenant stamping + RLS-scoped resolution (OQ-SEC-2), `lineage.source.manage` to steward/admin only (OQ-SEC-3), DB+ORM append-only (OQ-IMMUT).
- Scope: REQ-LIN-001 declared Done at entity/run granularity (OQ-4).

The plan §4 build sequence is correctly ordered: seed `lineage.source.manage` → `data_source` model+migration → `lineage_edge` model+migration → `record_lineage` utility → retrieval + BX-LIN-enforcement + deny-by-default tests. Recommend approval of the slice boundary and proceed to implementation with the §19 kickoff.

## 19. Exact implementation kickoff prompt for P1A-1

> **Begin P1A-1 — Data Source & Lineage Skeleton (REQ-LIN-001, builds DEP-LIN). Implement code.**
>
> **Scope (only this):**
> (1) **`data_source`** model (ENT-038, **EV**, tenant-scoped) following the `calc/models.py` mixin pattern `class DataSource(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base)` with `__temporal_class__ = TemporalClass.EFFECTIVE_DATED`. Columns: `code` (String(150)), `name` (String(255)), `source_type` (String(50)), `description` (String(500) null), `is_active` (Boolean default true), `record_version` (Integer default 1), plus the **DR-P1-3 nullable, non-enforcing** maker-checker hooks `approval_status`/`approval_ref`/`made_by`/`checked_by`. `UniqueConstraint('tenant_id','code')`.
> (2) **`lineage_edge`** model (ENT-042, **IA**, tenant-scoped) `class LineageEdge(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base)` with `__temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY`. Columns: `source_type` (String(50)), `source_id` (GUID), `target_entity_type` (String(100)), `target_entity_id` (GUID), `edge_kind` (String(50) default `ORIGIN`), `run_id` (GUID **nullable**, logical non-FK reference to `calculation_run.run_id`). Use a **polymorphic `(target_entity_type, target_entity_id)` reference with NO domain FK** (the `audit_event` pattern).
> (3) **One Alembic migration** creating both tables; add both to the `TENANT_SCOPED_TABLES` loop with `ENABLE` + `FORCE ROW LEVEL SECURITY` + `CREATE POLICY tenant_isolation_<t> ON <t> USING (tenant_id::text = current_setting('app.current_tenant', true)) WITH CHECK (...)` — **include the explicit `WITH CHECK`**. Add `lineage_edge` to `APPEND_ONLY_TABLES` so the existing `irp_prevent_mutation()` trigger applies; `data_source` does NOT get the trigger.
> (4) **`record_lineage(session, *, source, target_entity_type, target_entity_id, run_id=None)`** in **`irp_shared.lineage`** (shared-python, NOT backend) — takes a caller-managed `Session`, inserts the edge in the caller's transaction, **stamps `tenant_id` server-side from the tenant context (never caller-supplied)**, and resolves a `data_source` `source` through the RLS-scoped session so a cross-tenant id fails closed. Add an `assert_has_lineage(session, target_entity_type, target_entity_id)` verification helper that raises `LineageMissingError` when no edge exists. Add an ORM `before_update`/`before_delete` append-only guard on `lineage_edge` (mirror `audit/models.py`).
> (5) **`data_source` admin/internal utility** (no public create endpoint) that emits **`DATA.SOURCE_REGISTER`** (create) / **`DATA.SOURCE_UPDATE`** (update) via `record_event` **in the same tenant-scoped transaction** as the data row (fail-closed: roll back the row if the audit insert fails). `record_lineage` emits **no** audit event. Reserve `LINEAGE.RECORD` (EVT-028) in the taxonomy doc as unused (P7).
> (6) **`GET /lineage/edges/{id}`** read endpoint only, depending on **`get_tenant_session`** and gated by **`require_permission('lineage.view')`**; entitlement-check first, then an RLS-scoped lookup returning an **indistinguishable 404** for both not-found and cross-tenant ids (no existence leak); 401 on missing principal.
> (7) Add **`lineage.source.manage`** to `bootstrap.py` `PERMISSIONS` and to the `data_steward` template (also held by `platform_admin` via `ALL_CODES`); do NOT grant it to `risk_*`/`auditor_3l`.
> (8) Tests, split SQLite-local vs **Postgres-CI under the constrained non-superuser `irp_app` role** (CI `migration` job, after `alembic upgrade head`, using the `app_url` fixture + `_is_rls_violation` SQLSTATE-42501 helper): temporal-class assertions; `record_lineage` creates a retrievable edge; **BX-LIN enforcement — a synthetic governed write without `record_lineage` fails `assert_has_lineage`** (and one with it passes); `data_source` create emits exactly one `DATA.SOURCE_REGISTER` and `verify_chain.ok`; `record_lineage` emits no audit event; **deny-by-default** for `lineage.source.manage` and `lineage.view` (403/PermissionDenied); PG **tenant isolation**, **no-context fail-closed (42501)**, **cross-tenant write rejected**, **cross-tenant reference fails closed**, **GET cross-tenant id → 404**, **`lineage_edge` UPDATE/DELETE blocked**, and an **ops-role-no-grant regression** test; SYSTEM_TENANT_ID source writable only under system-tenant context.
>
> **Constraints (strict exclusions — none of these):** lineage query/graph/visualization (REQ-LIN-002/P7); field/column-level mapping; any **public lineage write API**; any **public `data_source` create endpoint** (utility/admin-internal only); a `lineage_node` table; model registry (P1A-2); data quality (P1A-3); ingestion endpoint (P1A-4); Security Master; Reference Data; portfolio; positions; valuations; risk calculations; dashboards; reporting; private assets; real SSO; any domain entity. The **only** public endpoint permitted is `GET /lineage/edges/{id}`. The **only** new permission permitted is `lineage.source.manage`. The **only** new audit codes permitted are `DATA.SOURCE_REGISTER` and `DATA.SOURCE_UPDATE` (plus the reserved-unused `LINEAGE.RECORD`). End-state deliverable cap: **2 models + 1 migration + `record_lineage`/`assert_has_lineage` utility + 1 read endpoint + bootstrap/catalog update + the tests above.**
>
> **Honor:** AD-013 (tenant scoping), AD-005 (temporal classes — `data_source=EV`, `lineage_edge=IA`), BR-17 (tenant isolation), BR-19 (declare `__temporal_class__`), the DoR/DoD, and DR-P1-4 coverage targets. Use **`set_config`** / the P1A-0 tenant context for every DB surface; deny-by-default; **no secrets** in code; never use the BYPASSRLS ops role on any normal path and do not grant it on the new tables. Update `04_data_model/audit_event_taxonomy.md`, `06_security/entitlement_sod_model.md`, `09_compliance_controls/control_matrix_skeleton.md` (CTRL-005/006/011/012/013/032), `02_requirements/requirements_traceability_matrix.md` (REQ-LIN-001), `02_requirements/requirements_backbone.md` (CAP-14 temporal shorthand + DEP-LIN), and `08_testing_qa/ci_enforcement_overview.md` for newly-executable controls.
>
> **Return:** files created/updated, DB/migration changes, tests added (SQLite-local + PG-CI), CI impact, controls now executable (note CTRL-006/013 are skeleton/Designed, not Implemented), known placeholders (synthetic governed-output; first real BX-LIN proof at P1A-4), whether P1A-1 is complete, and confirmation that **`make check` passes** and the `migration` job should pass. **Do not commit until approved. Do not start P1A-2.**
