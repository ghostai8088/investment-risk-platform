# Phase P1A Implementation Plan

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1AIMPL-001 |
| Version | 0.1 (Draft) |
| Status | Proposed for approval (planning only — no code) |
| Owner | R-01 Product Manager AI (with R-02 Chief Architect AI, R-05 Data Architect AI) |
| Approver | H-07 Product Owner (H-06 Engineering Lead) |
| Created | 2026-06-19 |
| Last Reviewed | 2026-06-19 |
| Related Documents | p1_scoping_plan.md, p1_decision_record.md, ../02_requirements/requirements_backbone.md, ../02_requirements/requirements_traceability_matrix.md, ../02_requirements/definition_of_ready_done.md, ../03_architecture/foundation_slice.md, ../04_data_model/temporal_reproducibility_standard.md, ../04_data_model/audit_event_taxonomy.md, ../06_security/entitlement_sod_model.md, ../11_decision_log/architecture_decision_log.md |
| Supported Build Rules | BR-1, BR-3, BR-4, BR-5, BR-6, BR-11, BR-12, BR-13, BR-17, BR-19 |

## 1. Purpose & Grounding

Detailed implementation plan for **Phase P1A — the cross-cutting *rails*** (tenant context, lineage, model registry, data
quality, generic ingestion) that every later domain write rides. **Planning only; no code, no migrations.** P1A delivers
DEP-LIN, DEP-MREG, DEP-DQF as skeletons and REQ-INT-001 ingestion, with REQ-AUD-001 audit coverage extended — per
[requirements_backbone.md](../02_requirements/requirements_backbone.md) and [p1_scoping_plan.md](p1_scoping_plan.md) §3.

**Foundation it builds on (P0.5, commit `e7fc61a`, CI green):**
- `FW-TMP` — temporal mixins (`FullReproducibleMixin` FR / `ImmutableAppendOnlyMixin` IA / `EffectiveDatedMixin` EV), `GUID`,
  `TenantMixin`; PostgreSQL **FORCE row-level security** on tenant tables with policy
  `USING (tenant_id::text = current_setting('app.current_tenant', true))`.
- `FW-AUD` — `record_event` (per-tenant SHA-256 hash chain + advisory-lock concurrency), `verify_chain`, `verify_all_chains`,
  `create_checkpoint`; audit-verify ops CLI.
- `FW-ENT` — deny-by-default `has_permission`/`require_permission`; FastAPI `get_db` / `get_principal` (dev `X-User-Id` /
  `X-Tenant-Id` header shim) / `require_permission(code)` in `apps/backend/src/irp_backend/deps.py`; entitlement **bootstrap
  seed** (permission catalog incl. `data.upload`, `lineage.view`, `model.inventory.view/register`, `dq.rule.manage`,
  `dq.result.view`; role templates under `SYSTEM_TENANT_ID`).
- `FW-RUN` — `CalculationRun` with nullable `model_version_id` / `input_snapshot_id` / `assumption_set_id` placeholders.

**The gap P1A-0 closes:** the migration **arms** FORCE RLS but nothing in the app sets `app.current_tenant` per session, so
against real Postgres tenant-scoped reads/writes are blocked until a session sets context. P1A-0 wires this in.

**Decisions already binding (p1_decision_record.md):** AD-013 hybrid tenancy (global system reference vs tenant-scoped); AD-014
no derived output without a bound snapshot (not exercised in P1A — no derived outputs here); DR-P1-3 SoD/maker-checker deferred
to P6 (P1A adds non-enforcing hooks only); DR-P1-4 coverage ≥85% foundation / ≥75% early-domain (advisory until post-P1A).

## 2. Cross-cutting conventions for all P1A sub-slices

- **Tenancy (AD-013):** P1A config tables (`data_source`, `data_quality_rule`, `model`) default **tenant-scoped** (RLS); a
  reserved **system tenant** may hold global/template rows. All new tenant tables carry `tenant_id` + FORCE RLS + policy.
- **Temporal class (BR-19):** every new entity declares `__temporal_class__`. Config = EV; immutable records/results/edges = IA.
- **Audit (BX-AUD) — REQ-AUD-001 coverage:** every create/change across P1A-1…4 emits a taxonomy event via `record_event`.
  REQ-AUD-001 is satisfied **cross-cutting** (not a separate sub-slice): a shared **audit-coverage enforcement test** asserts
  "no governed write without a corresponding taxonomy event" (DoD D6, **CTRL-012**), and each sub-slice's acceptance includes its
  audit events. (See the REQ-AUD-001 note after §7.)
- **Entitlement (BX-ENT):** every access is `require_permission`-gated, deny-by-default, tenant-scoped; **any new permission code
  must be added to the bootstrap catalog *and* covered by a deny-by-default test** (most P1A codes already exist).
- **Lineage (BX-LIN):** once P1A-1 lands, governed outputs/ingests record lineage; the skeleton enforces "no governed output
  without a lineage path" via tests.
- **Maker-checker forward-compat (DR-P1-3):** change-controlled config tables that will later be maker-checked (`model`,
  `data_quality_rule`, `data_source`) reserve **nullable, non-enforcing** hook columns now — `approval_status`, `approval_ref`,
  `made_by`, `checked_by` — so P6 can add approval semantics without redesign. **No approval is enforced in P1A.**
- **No domain entities** (no instrument/issuer/portfolio/position/valuation/risk); staging is generic.

---

## 3. P1A-0 — Tenant Context Wiring (Postgres RLS)

| Dimension | Detail |
|---|---|
| **Requirements included** | Per-request DB-session tenant context; per-worker/job context; per-CLI/ops context; RLS verification tests; tenant-mismatch/failure tests. Enabling infra for BR-17 / FW-ENT / all P1A DB access (no backbone REQ of its own). |
| **Requirements excluded** | Real SSO / *verified* tenant identity (P9 — the dev header shim provides an **unverified** tenant); SoD (P6); domain entities; the lineage/model/DQ/ingestion skeletons (P1A-1…4). |
| **Database impact** | **No new domain tables.** One small migration to create a **`BYPASSRLS` ops DB role** for cross-tenant ops jobs (audit verification). No schema/table changes otherwise (RLS already exists from P0.5). |
| **API impact** | A tenant-scoped session dependency (e.g., `get_tenant_session`) that resolves the principal → sets `app.current_tenant` before any query; `require_permission` re-sequenced to run under that context. No new endpoints (health/version unchanged). |
| **Worker/CLI impact** | A `tenant_context(session, tenant_id)` helper in `irp_shared.db`. Worker jobs set context per tenant. The **audit-verify CLI** runs under a dedicated **`BYPASSRLS` ops role** so `verify_all_chains` can read every chain (and insert checkpoints across tenants). The migration must `CREATE ROLE … BYPASSRLS`, `GRANT SELECT ON audit_event` + `SELECT, INSERT ON audit_checkpoint` to it, and the CLI must connect via **separate ops credentials** (distinct `DATABASE_URL`). The app role is **never** granted BYPASSRLS. |
| **Audit events** | None new for setting context (plumbing). Optionally `AUTH.DENIED` on an RLS-blocked access (defer; minimal). |
| **Entitlement checks** | **Resolve principal → set tenant context → entitlement check.** `has_permission` joins `permission`→`role_permission`→`role`→`user_role`; of these, **`role` and `user_role` are FORCE-RLS tenant-scoped** (`permission`/`role_permission` are global; `app_user` is not joined). The ordering is required for **availability/correctness, not security**: without context the RLS-scoped `role`/`user_role` rows are hidden, so a legitimately-permitted principal is wrongly **denied** (fail-closed). Cross-tenant escalation is already prevented by `has_permission`'s explicit `principal.tenant_id == resource_tenant_id` guard and `UserRole.tenant_id` filter. |
| **RLS / tenant-context behavior** | App request: `set_config('app.current_tenant', <tenant>, true)` inside the request's transaction (**transaction-local**, discarded at COMMIT/ROLLBACK) — so a connection returned to the pool after a normal transaction carries **no** stale context. The pool check-in listener executes an **explicit `RESET app.current_tenant`** (SQLAlchemy's default rollback-on-return clears *transaction-local* but **not** session-level GUCs) as **defense-in-depth** for code paths that mistakenly use session-scoped context or set it outside a transaction. Cross-tenant ops via the BYPASSRLS role. An insert whose `tenant_id` ≠ context is rejected: the policy is **`USING`-only**, and PostgreSQL applies the `USING` predicate as the implicit INSERT check when `WITH CHECK` is omitted. **Optional (in scope for the one P1A-0 migration):** add an explicit `WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))` for clarity and to future-proof read/write-scope divergence (e.g., cross-tenant-readable system rows). |
| **Data lineage behavior** | N/A (no lineage yet). |
| **Tests** | PG-gated (real RLS; SQLite has none — run in the CI `migration` job like the concurrency test): (a) **visibility** — context=A sees only A's rows; (b) **no-context fail-closed** — with the GUC unset, `current_setting(…, true)` returns NULL so reads return empty and inserts are rejected (assert it never raises; optionally assert empty-string context behaves the same); (c) **mismatch** — context=A, insert `tenant_id=B` raises an RLS policy violation (assert on the actual error, **not** a `WITH CHECK` clause); (d) **connection-recycle safety** — must exercise a **session-scoped / no-transaction** path (the case the RESET actually guards) and assert a reused pooled connection retains no prior context — otherwise the test passes vacuously; (e) **is_local=true auto-clear** — set context transaction-locally, query, commit/rollback, assert `current_setting` is NULL on the same connection afterward; (f) **ops role** — BYPASSRLS role reads all chains and (when checkpointing) inserts checkpoints across tenants. |
| **Acceptance criteria** | App sessions are tenant-scoped via `set_config`; FORCE RLS fail-closed without context; cross-tenant write rejected; transaction-local context auto-clears + explicit RESET clears session-scoped context (no leak); entitlement check runs under correct context (authorized principals not falsely denied); ops role verifies all chains. |
| **Risks** | (1) **Stale session-scoped GUC on a pooled connection → cross-tenant leak** — *largely eliminated* by `is_local=true` (auto-clears at txn end); the **explicit `RESET`** listener covers the residual `is_local=false`/no-transaction paths, and test (d) must target exactly those paths to be meaningful. (2) Dev header-shim tenant is **unverified** — not a security boundary until SSO (P9); document prominently. (3) BYPASSRLS ops role is powerful — restrict to ops jobs, never the app role. (4) Forgetting context on a new code path fails *closed* (RLS returns empty → false-deny), not open — mitigate with the `tenant_context` helper + test convention. |
| **Open questions** | OQ-P1A-0-1 cross-tenant ops mechanism (BYPASSRLS role [recommended] vs per-tenant loop); OQ-P1A-0-2 `is_local=true` [recommended] vs session-scoped + reset; OQ-P1A-0-3 accept unverified dev-shim tenant until SSO (recommended: yes, documented). |
| **Build sequence** | (a) `tenant_context` helper + pool check-in reset listener in `irp_shared.db`; (b) backend `get_tenant_session` dependency + re-sequenced `require_permission`; (c) worker/CLI context helpers + BYPASSRLS ops role migration; (d) PG RLS tests in CI. |

---

## 4. P1A-1 — Data Source & Lineage Skeleton (REQ-LIN-001, DEP-LIN)

| Dimension | Detail |
|---|---|
| **Requirements included** | REQ-LIN-001 (lineage skeleton & capture): `data_source`, `lineage_edge`, a `record_lineage()` utility (the BX-LIN hook), and retrieval-by-id for verification. |
| **Requirements excluded** | Lineage query/visualization (REQ-LIN-002 → P7); field/column-level mapping; domain entities; full source-to-target mapping UI. |
| **Database impact** | New tables: `data_source` (ENT-038, **EV**, tenant-scoped, **+ DR-P1-3 nullable maker-checker hooks**; system tenant may hold global sources per AD-013), `lineage_edge` (ENT-042, **IA**, tenant-scoped). FORCE RLS + policy on both. Migration. |
| **API impact** | Minimal: `GET /lineage/edges/{id}` (verification/retrieval). Lineage is **recorded by utilities, not via a public write API**. `data_source` management via an admin/internal utility (no public create endpoint yet). |
| **Worker/CLI impact** | None standalone; `record_lineage()` is called by any process that creates governed data (e.g., ingestion in P1A-4). |
| **Audit events** | `data_source` create → `DATA.*` (create). Lineage edges are metadata of a governed write (no separate audit event by default; the governed write itself is audited). |
| **Entitlement checks** | `lineage.view` (read; already in catalog); a data-source admin permission (new code, e.g., `lineage.source.manage`). |
| **RLS / tenant-context** | Tenant-scoped; relies on P1A-0 context. |
| **Data lineage behavior** | `record_lineage(session, *, source, target_entity_type, target_entity_id, run_id=None)` inserts edge(s) linking a `data_source`/upstream entity → target. Establishes the contract every later governed write calls; a verification test asserts a recorded output has a complete path. |
| **Tests** | Edge created + retrievable by id; **enforcement test** — a governed write lacking a lineage edge fails the BX-LIN check; tenant isolation of lineage; lineage of the lineage tables themselves not required (avoid recursion). |
| **Acceptance criteria** | Every recorded governed output has a complete `source → target` lineage path retrievable by id; lineage is tenant-scoped and audited at the source level. |
| **Risks** | Scope creep into full lineage graph/query (keep capture + retrieve-by-id only); edge **granularity** (start at entity/run level, not field level); defining "governed output" for the enforcement test before domains exist. |
| **Open questions** | OQ-P1A-1-1 edge-only (`source_ref → target_ref`) vs node+edge model; OQ-P1A-1-2 `data_source` tenant-scoped only vs allow global/system sources (AD-013); OQ-P1A-1-3 lineage granularity. |
| **Build sequence** | extend the entitlement bootstrap seed with `lineage.source.manage` (new code) → `data_source` model+migration → `lineage_edge` model+migration → `record_lineage` utility → retrieval + BX-LIN-enforcement + deny-by-default tests. |

---

## 5. P1A-2 — Model Registry Skeleton (REQ-MDG-001, DEP-MREG)

| Dimension | Detail |
|---|---|
| **Requirements included** | REQ-MDG-001 (model inventory & versioning skeleton): `model`, `model_version`, **`model_assumption` + `model_limitation`** (the canonical ENT-036 shape; minimal capture), a `register_model()` utility, inventory tests. Enforces BR-3 (inventoried before use) and BX-LIM (limitations documented, CTRL-014) at skeleton level. |
| **Requirements excluded** | Tiering (REQ-MDG-002 → P7); validation workflow & effective challenge (REQ-MDG-003 → P7); approval *enforcement* gates; restricted-use status workflow. |
| **Database impact** | `model` (ENT-035, **EV**, tenant-scoped, **+ DR-P1-3 nullable maker-checker hooks**), `model_version` (ENT-035, **IA** immutable), `model_assumption` + `model_limitation` (ENT-036, **IA**, minimal). FORCE RLS + policy. Migration. **Decision (OQ-P1A-2-2):** whether to wire a real FK `calculation_run.model_version_id → model_version` now — **only that FK is in scope**; the reproducibility FKs `input_snapshot_id`/`assumption_set_id` stay nullable placeholders, deferred per **AD-014**. |
| **API impact** | `POST /models` (register), `GET /models` + `GET /models/{id}` (inventory). |
| **Worker/CLI impact** | Provides real `model_version` rows that FW-RUN `CalculationRun` can reference; no new worker. |
| **Audit events** | `MODEL.REGISTER`, `MODEL.VERSION`. |
| **Entitlement checks** | `model.inventory.register`, `model.inventory.view` (already in catalog). |
| **RLS / tenant-context** | Tenant-scoped via P1A-0. |
| **Data lineage behavior** | Registration is not a data output; `model_version` is referenced by the lineage/run of future results, not lineage-recorded itself. |
| **Tests** | Register model+version (+assumptions/limitations) → inventory entry + audit; **BR-3 gate** — using an unregistered `model_version` fails; **limitations captured** (BX-LIM/CTRL-014); versioning (multiple immutable versions); tenant isolation. |
| **Acceptance criteria** | Every model/version is inventoried before use; assumptions/limitations recorded; inventory queryable; versions immutable; tenant-scoped. |
| **Risks** | Over-building toward full model governance (keep inventory + versioning + assumptions/limitations only — no tiering/validation); the FW-RUN FK decision (OQ-P1A-2-2). |
| **Open questions** | OQ-P1A-2-1 models tenant-scoped vs global/shared (AD-013); OQ-P1A-2-2 wire only `calculation_run.model_version_id` FK now vs P2 (snapshot FKs deferred, AD-014); OQ-P1A-2-3 minimal `model_assumption`/`model_limitation` shape. |
| **Build sequence** | `model`+`model_version`+`model_assumption`+`model_limitation` models+migration → `register_model` utility → inventory API → tests. |

---

## 6. P1A-3 — Data Quality Skeleton (REQ-DQR-001, DEP-DQF)

| Dimension | Detail |
|---|---|
| **Requirements included** | REQ-DQR-001 (DQ rules engine skeleton): `data_quality_rule`, `data_quality_result`, a pluggable rule-execution interface with 1–2 **generic** rules (e.g., not-null, allowed-values), and exception/no-silent-failure tests. |
| **Requirements excluded** | Reconciliation (REQ-DQR-002 → P7); manual overrides (REQ-DQR-003 → P7); DQ dashboard (P7); domain-specific rules. |
| **Database impact** | `data_quality_rule` (ENT-039, **EV**, tenant-scoped, **+ DR-P1-3 nullable maker-checker hooks**; system tenant may hold global rules per AD-013), `data_quality_result` (ENT-039/related, **IA**, tenant-scoped, with a **nullable/optional** `data_source` reference so P1A-3 stands alone before P1A-1). FORCE RLS + policy. Migration. |
| **API impact** | `POST /dq/rules` (manage), `GET /dq/results`. |
| **Worker/CLI impact** | A rule-execution interface (`DQRule.evaluate(...) -> DQResult`) callable in-process (used by P1A-4 ingestion) and as a job later. |
| **Audit events** | `DATA.VALIDATE` (rule run); rule create → `DATA.*`/`CONFIG.*`. |
| **Entitlement checks** | `dq.rule.manage`, `dq.result.view` (already in catalog). |
| **RLS / tenant-context** | Tenant-scoped via P1A-0. |
| **Data lineage behavior** | DQ results *optionally* reference the `data_source`/ingestion they validated (nullable link, populated once P1A-1 exists). |
| **Tests** | Rule runs → result persisted; **no-silent-failure** — a failing rule surfaces an exception/flagged result, never silently passes (QS-15/BR-14); exception is propagated not swallowed; tenant isolation. |
| **Acceptance criteria** | Rules run on demand/ingest; failures surfaced (exception or flagged result), never silently ignored; results queryable + tenant-scoped. |
| **Risks** | Over-engineering the rule engine (keep a minimal pluggable interface); rule scope (generic only — no domain rules); defining severity + the "raise vs flag" policy. |
| **Open questions** | OQ-P1A-3-1 declarative-config rules vs code-based rules; OQ-P1A-3-2 severity model + raise-vs-flag policy; OQ-P1A-3-3 global vs tenant rules. |
| **Build sequence** | `data_quality_rule`+`data_quality_result` models+migration → rule interface + generic rules → execution+persistence → no-silent-failure tests. |

---

## 7. P1A-4 — Generic Ingestion Staging (REQ-INT-001)

| Dimension | Detail |
|---|---|
| **Requirements included** | REQ-INT-001 (file upload / anti-corruption ingestion): upload + generic **staging**, anti-corruption validation, DQ run (P1A-3), lineage origin (P1A-1), audit events, entitlement gate. The **first real governed-write endpoint**. |
| **Requirements excluded** | API/SFTP/vendor/GP-report adapters (REQ-INT-002/003 → P9); **domain-specific canonical mapping** (P1B/P1C define targets); AV scanning (later-hardening, OD-042). |
| **Database impact** | `ingestion_batch` (**IA**, tenant-scoped: filename, source, status, row counts, timestamps) + a **generic staging** representation (parsed rows as JSON keyed to the batch — no domain target yet). FORCE RLS + policy. Migration. |
| **API impact** | `POST /ingest/upload` (multipart): validate (type/size/sandboxed parse) → stage → DQ (P1A-3) → lineage origin (P1A-1) → audit (`DATA.INGEST`). Entitlement `data.upload`. Runs under P1A-0 tenant context. |
| **Worker/CLI impact** | Synchronous for the skeleton (upload → stage → DQ → lineage → audit). Async batch processing via worker is a later option. |
| **Audit events** | `DATA.INGEST` (upload), `DATA.VALIDATE` (DQ on staged data). |
| **Entitlement checks** | `data.upload` (deny-by-default, tenant-scoped). |
| **RLS / tenant-context** | Tenant-scoped; staged rows + batch tagged with the request tenant; RLS enforced. |
| **Data lineage behavior** | Upload creates/links a `data_source` and records **lineage origin** edges for the staged batch. |
| **Tests** | Upload validation (type/size); **malicious-file / CSV-formula-injection / path-traversal rejection** (THR-05/06); DQ runs and surfaces exceptions; lineage origin recorded; audit emitted; entitlement deny (unauthorized → 403); tenant isolation; oversized rejected. |
| **Acceptance criteria** | End-to-end upload → validate → stage → DQ → lineage → audit on a sample file; bad/malicious files rejected; unauthorized denied; all tenant-scoped and auditable. |
| **Risks** | Upload **security surface** (malicious files — sandboxed parsing + type/size now, AV later); **staging genericity** — no canonical target exists yet, so staging holds raw/parsed rows pending P1B/P1C mapping; file storage location (object store per AD-004 vs DB). |
| **Open questions** | OQ-P1A-4-1 staging representation — **recommend JSON rows in DB for the skeleton** (stays within Postgres RLS); object storage (AD-004) is a later option; OQ-P1A-4-2 sync vs async (recommend sync for skeleton); OQ-P1A-4-3 file size/type limits + storage location. **Note:** if object storage is chosen, tenant isolation of stored artifacts is enforced **outside** Postgres RLS and needs its own test, so the RLS/test rows above would expand. |
| **Build sequence** | `ingestion_batch`+staging models+migration → upload endpoint + anti-corruption validation → wire DQ + lineage + audit → entitlement gate → tests (incl. malicious file). |

---

### REQ-AUD-001 — Audit coverage (cross-cutting, not a separate sub-slice)

REQ-AUD-001 is satisfied **across** P1A-1…4 rather than as its own slice: every governed write (`data_source` create,
model/version register, DQ rule create + run, ingestion upload + validate) emits a taxonomy event via `record_event` (the
per-slice "Audit events" rows). It is **verified once** by a shared **audit-coverage enforcement test** — "a governed write with
no corresponding taxonomy event fails" — mapped to **CTRL-012** (BR-12, no governed write without an audit event) and CTRL-005.
Acceptance: no new P1A governed-write path lacks an audit event. (Per DoD §3, a sub-slice with no governed write marks this N/A.)

## 8. Recommended P1A Implementation Sequence

```
P1A-0 (tenant context — unblocks everything)
   ├─► P1A-1 (data source + lineage)   ┐
   ├─► P1A-2 (model registry)          │  independent skeletons; may overlap after P1A-0
   └─► P1A-3 (data quality)            ┘
            └─► P1A-4 (ingestion — integrates P1A-0 + P1A-1 + P1A-3)
```

- **Hard ordering:** P1A-0 first (every DB-backed surface needs tenant context). P1A-4 last (it composes lineage + DQ + audit +
  entitlement under tenant context).
- **Allowed overlap:** P1A-2 (model registry) is fully independent. P1A-1 and P1A-3 can largely run in parallel, but **P1A-3 has
  a soft dependency on P1A-1** (`data_quality_result.data_source` is a *nullable* reference) — either build P1A-1's `data_source`
  first, or keep that reference null until P1A-1 lands. P1A-4 consumes P1A-1 + P1A-3.
- Each sub-slice exits only on full [DoD](../02_requirements/definition_of_ready_done.md) + its controls + green CI (incl. the
  PG RLS/concurrency tests in the `migration` job) + clean enterprise review.

## 9. Is P1A-0 ready to implement?

**Yes.** The P0.5 foundation is CI-green: FORCE RLS exists; the `set_config('app.current_tenant', …)` **mechanism** is exercised
against real Postgres (the seed migration uses `is_local=true`; the concurrency test uses `is_local=false`); the dev header-shim
principal + entitlement gate exist; and `FW-AUD` is concurrency-safe. **Note:** no existing test yet proves the request-scoped
`is_local=true` auto-clear or the pool `RESET` — P1A-0 adds those (tests d/e). P1A-0 is otherwise pure wiring. Confirm the §11
decisions first (sensible defaults recommended so they do not block).

## 10. Exact kickoff prompt for P1A-0

> **Begin P1A-0 — Per-session tenant context wiring for PostgreSQL RLS. Implement code.**
>
> Scope (only this): (1) A `tenant_context(session, tenant_id)` helper in `irp_shared.db` that sets `app.current_tenant` via
> `set_config(..., is_local=true)` **inside the session's transaction**, plus a SQLAlchemy **pool check-in listener that issues an
> explicit `RESET app.current_tenant`** (defense-in-depth for session-scoped / no-transaction paths). (2) A backend
> `get_tenant_session` FastAPI dependency that resolves the principal (`get_principal`) → opens a transaction → sets tenant
> context → yields the session, and re-sequences `require_permission` to run under it (so authorized principals are not
> false-denied by RLS-hidden `role`/`user_role` rows). (3) Worker/CLI tenant-context helpers, and a **BYPASSRLS ops DB role**
> (one migration: `CREATE ROLE … BYPASSRLS`, `GRANT SELECT ON audit_event` + `SELECT, INSERT ON audit_checkpoint`; CLI connects
> via separate ops credentials) so the audit-verify CLI can read/checkpoint all chains. Optionally add an explicit `WITH CHECK`
> to the RLS policy. (4) PG-gated tests in the CI `migration` job: visibility; **no-context fail-closed** (unset → `current_setting`
> returns NULL, never raises); cross-tenant write rejected (**assert the RLS policy violation, not a `WITH CHECK` clause**);
> **`is_local=true` auto-clear**; **connection-recycle safety exercising a session-scoped / no-transaction path**; and ops-role
> cross-tenant read + checkpoint.
>
> Constraints: **No domain entities/tables** (Security Master, Reference Data, portfolio, position, valuation, risk, dashboards,
> reporting, private assets — none). No real SSO (the header-shim tenant remains **unverified** — document that it is not a
> security boundary until SSO/P9). No new domain endpoints. Only the BYPASSRLS-role migration is permitted. Keep it thin,
> modular, tested. Do not bypass audit/entitlement/temporal frameworks.
>
> Honor: AD-013 (tenant scoping), BR-17 (tenant isolation), the DoR/DoD, and DR-P1-4 coverage targets. Use
> `set_config` (NOT parameterized `SET`). For each item provide DB impact, audit, entitlement, RLS behavior, tests, acceptance,
> and build-rule/control mapping. Update `08_testing_qa/ci_enforcement_overview.md` and `09_compliance_controls/
> control_matrix_skeleton.md` for newly-executable controls (CTRL-011 tenant isolation now end-to-end).
>
> Return: files created/updated, DB/role changes, tests added, CI impact, controls now executable, known placeholders, whether
> P1A-0 is complete, and confirmation that `make check` passes and the migration job should pass. Do not start P1A-1.

## 11. Open decisions that must be resolved before P1A-0 code

| ID | Decision | Recommendation |
|---|---|---|
| OQ-P1A-0-1 | Cross-tenant ops mechanism (audit-verify, platform jobs) | **Dedicated `BYPASSRLS` ops DB role** for ops jobs; app uses per-tenant `set_config`. |
| OQ-P1A-0-2 | Tenant-context scope | **`is_local=true`** (transaction-local; auto-clears at COMMIT/ROLLBACK) **plus** a pool check-in handler issuing an explicit **`RESET app.current_tenant`** (defense-in-depth for session-scoped / no-transaction paths — SQLAlchemy's default rollback-on-return does **not** clear session-level GUCs). |
| OQ-P1A-0-3 | Unverified dev-shim tenant | Accept for dev; **document it is not a security boundary** until SSO (P9). RLS + entitlement remain defense-in-depth. |
| OQ-P1A-0-4 | Log RLS-denied access as `AUTH.DENIED`? | Defer (minimal value pre-domain); revisit in P1A-4. |

(Sub-slice-specific open questions OQ-P1A-1-x … OQ-P1A-4-x are listed per §4–7 and are needed before *those* sub-slices, not
before P1A-0.)

## 12. Dependencies

This plan depends on the P0.5 foundation (`e7fc61a`), the Step 2 backbone/RTM, the P1 scoping plan + decision record, AD-013,
and the audit/entitlement/temporal standards. It introduces no code and no migrations.
