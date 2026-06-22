# P1B Implementation Plan — Security Master & Reference Data

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1B-PLAN-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-01 Chief Architect AI (with R-05 Data Architect AI) |
| Approver | H-06 Engineering Lead |
| Created | 2026-06-22 |
| Related Documents | p1b0_decision_record.md, p1a_closeout_p1b_readiness.md, ../02_requirements/requirements_backbone.md, ../02_requirements/requirements_traceability_matrix.md, ../04_data_model/canonical_data_model_standard.md, ../04_data_model/temporal_reproducibility_standard.md, ../04_data_model/audit_event_taxonomy.md, ../06_security/entitlement_sod_model.md, ../09_compliance_controls/control_matrix_skeleton.md |
| Supported Build Rules | BR-3, BR-5, BR-7, BR-11, BR-12, BR-13, BR-17, BR-19 |

**Purpose.** Sequence P1B (Security Master & Reference Data) into build sub-slices, each implementing the
OD-P1B-A…J decisions (see `p1b0_decision_record.md`). **Scope: reference data only.** Every slice follows
the P1A cadence: UltraCode plan → implement → multi-lens review → fix in-scope → `make check` →
commit-on-approval → CI-green. Each slice reuses the P1A rails (RLS, audit, lineage, DQ, entitlement,
temporal mixins, Alembic drift gate, constrained-role PG tests, append-only triggers) and adds **no new
rail**. Migrations continue sequentially from head `0007` (next is `0008`).

**Global build conventions (all slices):**
- New package `irp_shared.reference` (web-framework-free, one-way deps — OD-P1B-H); endpoints in
  `irp_backend/api/reference*`; models registered in `irp_shared.models`.
- Reference CRUD emits the **new `REFERENCE.*` audit codes** (OD-P1B-E, R-07 EVT-140 block) co-transactionally
  (fail-closed, AUD-04).
- Every reference write records an origin lineage edge `data_source(MANUAL) → <entity>` + `assert_has_lineage`
  (OD-P1B-I).
- Deny-by-default `require_permission` on every endpoint; server-stamped `tenant_id`; indistinguishable 404;
  `uuid.UUID` path params → 422.
- DQ at entry uses **only** the generic `not_null` / `allowed_values` evaluators (OD-P1B decision, no
  domain-specific rules).
- PG tests run under the constrained `irp_app` role; SQLite-local logic + endpoint tests; append-only
  asserts the P0001 trigger where an entity is IA/FR-immutable-versioned.

**Slice → REQ-SMR mapping:** P1B-1 = **REQ-SMR-005 (new)** + REQ-SMR-004(calendar); P1B-2 = REQ-SMR-002;
P1B-3 = REQ-SMR-001 + REQ-SMR-003; P1B-4 = REQ-SMR-004(corporate_action); P1B-5 = (conditional) REQ-INT
reuse.

---

## P1B-1 — Currency / Calendar / Rating Scale

1. **Requirements included.** REQ-SMR-005 (new — currency ENT-005, rating_scale ENT-007) + REQ-SMR-004
   calendar (ENT-006). All EV, hybrid global+override (OD-P1B-C). Mint REQ-SMR-005, the REFERENCE audit
   category (EVT-140 block), and the currency/rating_scale/calendar `.view`+`.edit` permissions in this slice.
2. **Requirements excluded.** legal_entity/issuer/counterparty/instrument/identifier_xref/corporate_action;
   **rating ASSIGNMENTS** (ENT-007 FR half — deferred to a credit phase); day-count/roll math (QS-10/11, later).
3. **Entities.** `currency`, `calendar` (+ `calendar_holiday` child), `rating_scale` (+ `rating_grade` child)
   — EV (scale/taxonomy only), tenant-scoped + **hybrid global-readable**.
4. **APIs.** `POST/GET /reference/currencies`, `/calendars`, `/rating-scales` (+ `/{id}`).
5. **Audit events.** `REFERENCE.CREATE` / `REFERENCE.UPDATE` (mint the REFERENCE category, EVT-140 block,
   R-07); reuse `DATA.VALIDATE` only for any DQ run.
6. **Entitlement checks.** New `reference.currency.view/edit`, `reference.rating_scale.view/edit`,
   `reference.calendar.view` (+ existing `reference.calendar.edit`); deny-by-default.
7. **RLS behavior.** Hybrid: `USING (own OR SYSTEM_TENANT)` read; `WITH CHECK` single-tenant; `UNIQUE(tenant_id,
   code)`; tenant override wins; SYSTEM_TENANT writable only under system context.
8. **Lineage behavior.** Origin edge `data_source(MANUAL) → entity` on create; `assert_has_lineage`.
9. **DQ behavior.** `not_null` on `code`; `allowed_values` on controlled vocabs (e.g. currency ISO set).
10. **Tests.** SQLite logic + endpoint; PG RLS (the asymmetric global-read `USING` is **net-new** — no P1A
    test covers it): own+SYSTEM readable, other-tenant invisible, SYSTEM write rejected under tenant context,
    **no-context read returns only global rows**, **override: when a tenant row and a SYSTEM_TENANT row share a
    `code`, both are RLS-visible but the application read returns exactly the tenant row (one row)**; EV
    mutability; deny-by-default; audit `REFERENCE.*` emitted + `verify_chain`.
11. **Acceptance criteria.** Global taxonomies seeded + readable by tenants; tenant overrides shadow globals
    (tenant wins); writes tenant-isolated; audited (REFERENCE.*) + lineage-rooted; REQ-SMR-005 satisfied.
12. **Risks.** First hybrid-RLS implementation — the asymmetric USING/WITH-CHECK + no-context caveat is
    load-bearing (OD-P1B-C). Requirement REQ-SMR-005 + the taxonomy/permission additions must be ratified
    (R-02/R-07) before build.
13. **Open questions.** Currency controlled-vocab source (ISO-4217 seed list scope); rating_scale child
    grade model depth; which tables are hybrid vs pure-tenant if a tenant wants a private calendar only.

---

## P1B-2 — Legal Entity / Issuer / Counterparty

1. **Requirements included.** REQ-SMR-002 (issuer ENT-002, counterparty ENT-003) via a shared `legal_entity`
   core + separate role tables (OD-P1B-D), all EV; LEI + parent/child hierarchy + rollup.
2. **Requirements excluded.** netting set / CSA depth (OD-015, P1C); a unified single-table legal_entity+role
   (the rejected alternative); instrument linkage; ratings assignment.
3. **Entities.** `legal_entity` (core: LEI, name, domicile, `parent_id` self-FK), `issuer` (1:1 profile →
   legal_entity), `counterparty` (1:1 profile → legal_entity). All **tenant-scoped, NEVER hybrid** (proprietary).
4. **APIs.** `POST/GET /reference/legal-entities` (+ `/{id}`, hierarchy read), `/reference/issuers`,
   `/reference/counterparties`.
5. **Audit events.** `REFERENCE.CREATE` / `REFERENCE.UPDATE` for core + profiles.
6. **Entitlement checks.** New `reference.legal_entity.view/edit`; existing `reference.issuer.view/edit`,
   `reference.counterparty.view/edit`.
7. **RLS behavior.** Tenant-scoped + `WITH CHECK`; **no SYSTEM_TENANT rows** (OD-P1B-C invariant); cross-tenant
   issuer/counterparty/legal_entity invisible.
8. **Lineage behavior.** Origin edge `data_source(MANUAL) → entity` per row; `assert_has_lineage`.
9. **DQ behavior.** `not_null` on LEI/name; `allowed_values` on entity_type/role where applicable.
10. **Tests.** Shared-core ↔ profile 1:1 integrity; parent/child hierarchy rollup; issuer vs counterparty role
    separation; cross-tenant invisibility (PG); a legal_entity carrying both profiles; deny-by-default; audited.
11. **Acceptance criteria.** Issuer/counterparty modeled as profiles over a shared legal_entity core; LEI +
    hierarchy present; exposure-relevant rollup resolves to ultimate parent (REQ-SMR-002); tenant-isolated;
    audited + lineage-rooted.
12. **Risks.** Hierarchy correctness (cycles, orphan profiles); the 1:1 core↔profile contract. Mitigation:
    FK + cycle-guard + rollup tests. OD-P1B-D ratification (R-05+H-04) and canonical annotation precede build.
13. **Open questions.** Hierarchy depth/representation (adjacency vs closure table — adjacency for skeleton);
    whether `legal_entity` itself ever needs to be global (recommend no — proprietary).

---

## P1B-3 — Instrument / Instrument Terms / Identifier Cross-Reference

1. **Requirements included.** REQ-SMR-001 (instrument) via the OD-P1B-A split: `instrument` = EV identity,
   `instrument_terms` = **FR** (bitemporal, reconstructable as-of); REQ-SMR-003 (identifier_xref EV) with the
   OD-P1B-G deterministic-or-ambiguity resolver. **First real FR/bitemporal domain usage.**
2. **Requirements excluded.** identifier **authority/precedence engine** (OD-012/P1C — REQ-SMR-003 partially
   met); terms math/pricing; market data; valuation.
3. **Entities.** `instrument` (EV: identifier handle, asset_class, issuer FK, status), `instrument_terms`
   (FR, FullReproducibleMixin: coupon/maturity/call/day-count/denomination ccy, instrument FK),
   `identifier_xref` (EV: entity_type/entity_id/scheme/value/valid_from/valid_to). All tenant-scoped.
4. **APIs.** `POST/GET /reference/instruments` (+ `/{id}`, as-of terms read), `POST/GET /reference/instruments/{id}/terms`,
   `GET /reference/identifiers/resolve?scheme=&value=` (deterministic single result or ambiguity error).
5. **Audit events.** `REFERENCE.CREATE` / `REFERENCE.UPDATE` / `REFERENCE.CORRECTION` (terms restatement).
6. **Entitlement checks.** Existing `reference.instrument.view/edit`, `reference.identifier.resolve`.
7. **RLS behavior.** Tenant-scoped + `WITH CHECK`; no hybrid; native-uuid CI lessons for FR temporal queries.
8. **Lineage behavior.** Origin edge `data_source(MANUAL) → instrument` (+ terms); `assert_has_lineage`.
9. **DQ behavior.** `not_null` on primary identifier / instrument FK; `allowed_values` on asset_class/scheme.
10. **Tests.** **FR "reconstructable as-of" bitemporal proof** (valid-time + system-time) — the headline;
    identifier resolve returns ONE or explicit ambiguity (no silent match); structural uniqueness on active
    `(scheme,value)`; genericity (new scheme by value, no migration); **no precedence engine** (scope-fence);
    EV instrument mutable vs FR terms versioned; PG tenant isolation; deny-by-default; audited.
11. **Acceptance criteria.** Instrument terms reconstructable as-of (REQ-SMR-001); any known identifier
    resolves to one instrument or an explicit ambiguity error (REQ-SMR-003 partial, precedence → P1C);
    tenant-isolated; audited + lineage-rooted.
12. **Risks.** FR bitemporal correctness is the most expensive-to-retrofit pattern; OD-P1B-A must be ratified
    first. Identifier ambiguity semantics must be explicit. Mitigation: bitemporal + ambiguity tests are
    acceptance-gating.
13. **Open questions.** instrument_terms granularity (one wide terms row vs per-term-type rows — recommend one
    versioned terms row for skeleton); xref `entity_type` scope (instrument-only at P1B vs entity-general).

---

## P1B-4 — Corporate Actions & Effective-Dated Reference Updates

1. **Requirements included.** REQ-SMR-004 corporate_action (ENT-008) = **EV** (OD-P1B-B; effective-dated,
   applies on effective date, supersedable before application); demonstrate EV effective-dated update/
   restatement on a P1B-1/3 entity.
2. **Requirements excluded.** position/valuation adjustment from corporate actions (P1C); automatic
   application; a separate immutable announcement-event log (a distinct future entity — do NOT reclass ENT-008
   to IA).
3. **Entities.** `corporate_action` (EV: instrument FK, type controlled vocab, effective/ex-date, terms JSON
   or typed fields).
4. **APIs.** `POST/GET /reference/corporate-actions` (+ `/{id}`).
5. **Audit events.** `REFERENCE.CREATE` / `REFERENCE.UPDATE` / `REFERENCE.CORRECTION` / `REFERENCE.STATUS_CHANGE`
   (announced → confirmed → cancelled as EV status transitions, audited).
6. **Entitlement checks.** Existing `reference.corporate_action.edit` + new `reference.corporate_action.view`.
7. **RLS behavior.** Tenant-scoped + `WITH CHECK`; no hybrid.
8. **Lineage behavior.** Origin edge `data_source(MANUAL) → corporate_action`; `assert_has_lineage`.
9. **DQ behavior.** `not_null` on type/effective-date/instrument FK; `allowed_values` on action type/status.
10. **Tests.** **EV effective-dated supersede** (an amendment supersedes via a new effective version; no
    double-apply) — NOT an append-only/P0001 proof; status-transition audit (`REFERENCE.STATUS_CHANGE`);
    cross-tenant isolation; deny-by-default; audited + lineage-rooted. **Capture-only scope-fence test**
    (parallel to P1B-3's no-precedence-engine fence): assert NO corporate-action effect is computed/applied to
    any instrument_terms / position / valuation (P1B captures the action only; application logic is P1C).
11. **Acceptance criteria.** Actions apply on effective date (REQ-SMR-004); amend/cancel-before-application via
    EV supersede; status transitions audited; tenant-isolated.
12. **Risks.** EV supersede must not double-apply; status lifecycle must stay capture-only (no application
    engine in P1B). Mitigation: supersede + status tests; scope-fence against any application logic.
13. **Open questions.** corporate_action type vocabulary breadth (minimal generic set for skeleton); whether a
    separate immutable announcement log is wanted later (a distinct OD, not P1B).

---

## P1B-5 — Reference-Data Ingestion Mapping (CONDITIONAL — only if bulk loading is needed)

1. **Requirements included.** ONLY if bulk reference loading is required this phase: the **first real
   staging→canonical mapping** — map P1A-4 `ingestion_staged_record` rows → P1B reference entities, reusing
   `stage_upload` + a thin mapping step; bind `ingestion_batch_id`.
2. **Requirements excluded.** vendor/SFTP/API adapters (REQ-INT-002/003, P9); any non-reference mapping; new
   ingestion rails.
3. **Entities.** No new entity — a mapping function/utility over staged rows → P1B-1…4 entities.
4. **APIs.** Reuse `POST /ingest/upload`; optionally `POST /reference/ingest/{batch_id}/map` (gated
   `data.upload`).
5. **Audit events.** Reuse `DATA.INGEST` (batch lifecycle) + `REFERENCE.CREATE` (per mapped entity).
6. **Entitlement checks.** Existing `data.upload` + the relevant `reference.<entity>.edit`.
7. **RLS behavior.** Tenant-scoped; staged rows + mapped entities both tenant-isolated.
8. **Lineage behavior.** The existing rail records only `data_source → target` ORIGIN edges (no
   `ingestion_batch` source-node kind, no DERIVED edge — and P1B adds no rail). So the achievable shape is
   **two ORIGIN edges sharing the vendor source** — `data_source → ingestion_batch` (from P1A-4) **and**
   `data_source → reference_entity` (the mapped row) — plus `ingestion_batch_id` bound on the entity / DQ
   result for batch correlation. **Not** a literal transitive `ingestion_batch → reference_entity` edge.
9. **DQ behavior.** Reuse `run_quality_check` / `assert_passed_quality_checks` gate on the staged rows before
   mapping (generic rules).
10. **Tests.** End-to-end CSV → staged → mapped reference rows with the full lineage chain + DQ gate; mapping
    rejects invalid rows (durable evidence, no partial canonical write).
11. **Acceptance criteria.** A staged CSV maps to reference rows with lineage `data_source → ingestion_batch →
    entity` and DQ gating; **defer entirely if not needed** — direct CRUD (P1B-1…4) already satisfies P1B entry.
12. **Risks.** Over-building ingestion mapping too early; canonical-mapping creep beyond reference. Mitigation:
    conditional/last; scope-fence to reference entities only.
13. **Open questions.** Is bulk reference loading actually needed at P1B, or deferred to when a vendor feed
    lands (P9)? Recommend **defer** unless a concrete bulk-load need exists.

---

## Sequencing & gating

P1B-1 → P1B-2 → P1B-3 → P1B-4, then P1B-5 only if justified. **Gating prerequisites (from P1B-0):** the
AD-013-R1 refinement (OD-P1B-C), REQ-SMR-005 (OD-P1B-J), and the canonical legal_entity-core annotation
(OD-P1B-D) are ratified before the slices that depend on them; the REFERENCE audit category (OD-P1B-E) and
the entitlement additions (OD-P1B-F) are minted in the slice that first needs them (P1B-1). **No P1C/P2+
work** (portfolio, positions, valuation, market data, risk, exposure, limits, breach, reporting, SSO) enters
any P1B slice.
