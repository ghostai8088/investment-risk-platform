# Canonical Data Model Standard

## Document Control

| Field | Value |
|---|---|
| Document ID | DATA-CANON-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-05 Data Architect AI |
| Approver | H-04 Data Owner |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | temporal_reproducibility_standard.md, audit_event_taxonomy.md, entitlement_sod_model.md, numerical_quant_standards.md, architecture_baseline.md |
| Supported Build Rules | BR-4, BR-6, BR-7, BR-13 |

## 1. Purpose

Define naming standards, identifier strategy, mandatory common columns, and the canonical entity set so that every module
shares one consistent, lineage-aware, auditable data foundation. This is the contract the data dictionary (future, per-field)
will elaborate; it is not full DDL.

## 2. Naming & Modeling Standards (DM-N)

| ID | Standard |
|---|---|
| DM-N-01 | Tables and columns in `snake_case`; table names singular (e.g., `position`, `calculation_run`). |
| DM-N-02 | Surrogate primary key `id` (UUID); business/natural keys stored explicitly and uniquely constrained. |
| DM-N-03 | Foreign keys named `<referenced_entity>_id`. |
| DM-N-04 | Monetary amounts stored as decimal with explicit `*_currency` (ISO 4217) — never binary float (QS standards). |
| DM-N-05 | All timestamps stored in UTC; business dates stored as date with explicit calendar reference where relevant. |
| DM-N-06 | Every entity carries the mandatory common columns (§4) and, where stateful, bitemporal columns (§4 / temporal standard). |
| DM-N-07 | Every field has a data classification tag (DC-*, see entitlement_sod_model.md) recorded in the data dictionary. |
| DM-N-08 | Enumerations are reference data, not free text; controlled vocabularies live in reference tables. |
| DM-N-09 | No module persists into another bounded context's tables (ARCH-P-01); cross-context access via service/API only. |

## 3. Identifier Strategy

| Concern | Standard |
|---|---|
| Internal IDs | UUID surrogate keys; immutable. |
| Instruments | Maintain cross-reference (`identifier_xref`) across vendor and standard identifiers (ISIN/CUSIP/SEDOL/FIGI/internal). |
| Issuers / Counterparties | Prefer LEI where available; maintain internal entity ID and hierarchy (parent/ultimate-parent). |
| Private assets | Internal private-asset ID with proxy/mapping to public risk factors (`proxy_mapping`). |
| Tenancy | `tenant_id` on every tenant-scoped entity (AD-008); enforced by FW-ENT. |

## 4. Mandatory Common Columns

Every persisted entity includes:

- `id` (UUID, PK)
- `tenant_id` (where tenant-scoped)
- `created_at` / `created_by`, `updated_at` / `updated_by`
- `source_id` (FK to `data_source`; lineage origin — BR-13)
- `record_version` (monotonic version)
- Bitemporal (stateful business entities): `valid_from`, `valid_to`, `system_from`, `system_to`
  (see [temporal_reproducibility_standard.md](temporal_reproducibility_standard.md))
- Classification tag reference (DM-N-07)

Result and audit entities are **append-only/immutable** (no in-place update; corrections via new versions).

## 5. Canonical Entities (ENT)

Grouped by bounded context. IDs are stable; attributes listed are indicative (the per-field dictionary will expand them).

### Reference / Security Master (BC-02/BC-03)
| ID | Entity | Notes |
|---|---|---|
| ENT-001 | `instrument` | Security master; asset class, identifiers via xref. **P1B-0 ratified (OD-P1B-A):** realized as `instrument` (**EV** identity) + `instrument_terms` (**FR** effective-dated economic/legal terms) — no entity removed/renamed. **P1B-3: REALIZED** (migration `0010`) — `instrument` (EV, identity-only; nullable `issuer_id` → issuer profile) + `instrument_terms` (FR, the **first persisted bitemporal** entity: create / effective-dated supersede / as-known correction + `reconstruct_terms_as_of`); tenant-scoped SYMMETRIC RLS (NEVER hybrid); terms math deferred to P2+ |
| ENT-002 | `issuer` | Issuer/obligor with LEI and hierarchy. **P1B-0 (OD-P1B-D):** an `issuer` role/profile table over an **implementation-only `legal_entity` core** (shared LEI/hierarchy; **no canonical ENT id** unless later approved). **P1B-2: REALIZED** — `issuer` (EV) is a 1:1 profile over the `legal_entity` core (migration `0009`); tenant-scoped SYMMETRIC RLS (NEVER hybrid); LEI + `parent_legal_entity_id` adjacency on the core; rollup *calc* deferred |
| ENT-003 | `counterparty` | Trading/credit counterparty; links to netting/CSA. **P1B-0 (OD-P1B-D):** a `counterparty` role/profile table over the same implementation-only `legal_entity` core; remains distinct from ENT-002. **P1B-2: REALIZED** — `counterparty` (EV) 1:1 profile over the `legal_entity` core (migration `0009`); tenant-scoped SYMMETRIC RLS; **ZERO netting/CSA/collateral columns** (OD-015 deferred to P1C) |
| ENT-004 | `identifier_xref` | Instrument/entity identifier cross-reference (EV). **P1B-0 (OD-P1B-G):** deterministic resolve-to-one-or-AmbiguousIdentifier; precedence (OD-012) deferred to P1C. **P1B-3: REALIZED** (migration `0010`) — EV, polymorphic `(entity_type, entity_id)` scoped to `entity_type='instrument'`; active partial-unique `(tenant_id, scheme, value) WHERE valid_to IS NULL`; `resolve_identifier` returns one / `None` / `AmbiguousIdentifier`; no precedence engine, no external validation |
| ENT-005 | `currency` | ISO 4217 reference (EV). **P1B-0:** REQ-SMR-005; hybrid global+tenant-override (AD-013-R1). **P1B-1: REALIZED** — table `currency` (migration 0008), asymmetric hybrid RLS, `UNIQUE(tenant_id, code)` |
| ENT-006 | `calendar` | Holiday calendars per market (QS day-count/roll) (EV). **P1B-0:** REQ-SMR-004; calendar entity only, roll math deferred; hybrid (AD-013-R1). **P1B-1: REALIZED (partial)** — tables `calendar` + `calendar_holiday` (migration 0008); roll/day-count math still deferred |
| ENT-007 | `rating_scale` / `rating` | External and internal/shadow ratings. **P1B-0 split:** `rating_scale`/grade **taxonomy = EV** (REQ-SMR-005, P1B-1); rating **assignments = FR** (ENT-007 per AD-005 §2A, deferred to a credit phase). **P1B-1: EV taxonomy REALIZED** — tables `rating_scale` + `rating_grade` (migration 0008), zero assignment columns; FR assignments NOT built |
| ENT-008 | `corporate_action` | Splits, coupons, calls, restructurings. **P1B-0 ratified (OD-P1B-B):** **EV** effective-dated (applies on effective date, supersedable); status/reason history via the `REFERENCE.*` audit trail, not an IA table. **P1B-4: REALIZED** (migration `0011`) — `corporate_action` (EV, **capture-only**): `instrument_id` NOT-NULL FK; single `status` lifecycle (ANNOUNCED→CONFIRMED→CANCELLED, no `is_active`); inert business dates (announcement/ex/record/pay/effective) + `ratio`/`amount`/`currency_code`; amend = EV in-place supersede (`REFERENCE.UPDATE`), status transition = `REFERENCE.STATUS_CHANGE` (EVT-143); tenant-scoped SYMMETRIC RLS (NEVER hybrid). **NO application engine / position adjustment / roll math** (application → P1C) |
| ENT-009 | `benchmark` | Benchmark definitions and constituents |

### Portfolio & Positions (BC-01)
| ID | Entity | Notes |
|---|---|---|
| ENT-010 | `portfolio` / `fund` / `strategy` / `account` | Hierarchy nodes |
| ENT-011 | `position` | Holdings (bitemporal) |
| ENT-012 | `transaction` | Trades/cashflows |
| ENT-013 | `valuation` | Valuation history (bitemporal) |
| ENT-014 | `exposure_aggregate` | Derived aggregation (run-tracked) |

> **P1C-0 ratification note (AD-017, 2026-06-23 — conforms to §2A temporal classes, no AD-005 amendment):** P1C is a **capture-only** domain block. **ENT-010** (`portfolio`) is **REALIZED in P1C-1 (migration `0012`)** as a **single `portfolio` EV table** with a `node_type` controlled-vocab (`PORTFOLIO`/`FUND`/`STRATEGY`/`ACCOUNT`) + a `parent_portfolio_id` self-FK adjacency — the entitlement portfolio-scope **ANCHOR** (subtree semantics; ABAC enforcement deferred to P6+). **ENT-011** position (**FR**) + **ENT-013** valuation (**FR**) are **CAPTURED / as-of-reconstructable** (reusing the P1B-3 `instrument_terms` FR protocol), **not** derived analytics; **ENT-012** transaction (**IA**, append-only) — **REALIZED in P1C-2 (migration `0013`)** as the `transaction` immutable append-only trade/cashflow event log (keyed to portfolio + instrument; truly immutable via the `irp_prevent_mutation` P0001 trigger + ORM guard; corrections are explicit reversal records — capture-only, no derivation; `TRANSACTION.RECORD`/`.REVERSE` EVT-160/161). **ENT-014** `exposure_aggregate` (IA, derived) and `dataset_snapshot` **stay P2** (AD-014) unless explicitly reopened — P1C performs **no** exposure aggregation / risk / pricing / valuation models / corporate-action application. OD-012 (identifier precedence) and OD-015 (counterparty netting/CSA) remain deferred beyond P1C.

### Private Assets (BC-04)
| ID | Entity | Notes |
|---|---|---|
| ENT-015 | `commitment` | Funded/unfunded |
| ENT-016 | `capital_call` / `distribution` | Cashflow events |
| ENT-017 | `gp_report` / `appraisal` | NAV/valuation sources, valuation dates, stale flags |
| ENT-018 | `private_company_financials` | Restricted/MNPI classification |
| ENT-019 | `proxy_mapping` | Private-to-public risk-factor proxies |

### Market Data (BC-02)
| ID | Entity | Notes |
|---|---|---|
| ENT-020 | `price_point` | Time-series prices |
| ENT-021 | `yield_curve` | Curve nodes |
| ENT-022 | `volatility_surface` | Vol points |
| ENT-023 | `credit_spread` | Spread time-series |
| ENT-024 | `fx_rate` | FX (QS triangulation) |
| ENT-025 | `factor_return` | Risk-factor returns |

### Risk Results & Scenarios (BC-05…BC-09)
| ID | Entity | Notes |
|---|---|---|
| ENT-026 | `calculation_run` | Binds version+snapshot+assumptions+seed+initiator (FW-RUN) |
| ENT-027 | `risk_result` | Immutable result rows linked to a run |
| ENT-028 | `sensitivity` / `exposure_metric` | Greeks/duration/PFE/etc. |
| ENT-029 | `scenario_definition` | Versioned, saved assumptions (BR-8) |
| ENT-030 | `scenario_result` | Run-tracked scenario outputs |

### Limits & Breach (BC-10)
| ID | Entity | Notes |
|---|---|---|
| ENT-031 | `limit_definition` | Soft/hard limits, scope |
| ENT-032 | `limit_utilization` | Run-tracked utilization |
| ENT-033 | `breach` | Breach record + workflow state |
| ENT-034 | `breach_action` | 1L/2L actions, remediation, closure evidence |

### Model Governance (BC-11)
| ID | Entity | Notes |
|---|---|---|
| ENT-035 | `model` / `model_version` | Inventory + versioning |
| ENT-036 | `model_assumption` / `model_limitation` | Declared per version |
| ENT-037 | `model_validation` | Validation status, tier, approval |

### Data Governance (BC-12)
| ID | Entity | Notes |
|---|---|---|
| ENT-038 | `data_source` | Source registry (lineage origin) |
| ENT-039 | `data_quality_rule` / `dq_result` | DQ rules and outcomes |
| ENT-040 | `reconciliation_result` | Recon outcomes |
| ENT-041 | `manual_override` | Prior/new value, justification, approval (BR-7) |
| ENT-042 | `lineage_edge` | Source-to-target lineage graph edges (BR-13) |

### Security / Admin / Audit (BC-13/BC-15)
| ID | Entity | Notes |
|---|---|---|
| ENT-043 | `user` / `service_account` / `agent_principal` | Subjects (incl. AI agents) |
| ENT-044 | `role` / `permission` / `entitlement_grant` / `scope` | RBAC/ABAC model |
| ENT-045 | `audit_event` | Immutable; schema in audit_event_taxonomy.md |
| ENT-046 | `report` / `report_version` | Reproducible reports (BR-9) |

### Integration (BC-16)
| ID | Entity | Notes |
|---|---|---|
| ENT-047 | `ingestion_batch` | One upload's run record (P1A-4, REQ-INT-001). IA-classed but **status-mutable** (the `calculation_run` precedent — not in `APPEND_ONLY_TABLES`; every transition audited via `DATA.INGEST`). Real FK to `data_source` (provenance root); no FK to any domain/canonical table. |
| ENT-048 | `ingestion_staged_record` | Immutable parsed/neutralized raw row (P1A-4). IA, append-only (ORM guard + DB trigger). `payload` is a single **generic JSON** column — no domain shape, no domain FK; **not canonical data** (canonical mapping is deferred to P1B/P1C). |

## 6. Lineage & Audit Hooks (mandatory)

- Every record references its `source_id`; every derived record (results, aggregates, reports) records the upstream
  `calculation_run` and input snapshot, materialized as `lineage_edge` rows (BR-6, BR-13).
- Every create/update/override/approve emits an audit event (BR-5, BR-12) per audit_event_taxonomy.md.
- `manual_override` (ENT-041) is the only sanctioned path to change governed values and must carry the BR-7 fields.

## 7. Open Decisions

| ID | Open Decision |
|---|---|
| OD-012 | Confirm primary instrument/entity identifier authority and vendor xref precedence. |
| OD-013 | **CLOSED (P1C-0, 2026-06-23):** arbitrary adjacency tree — `parent_portfolio_id` self-FK, depth-capped at `MAX_HIERARCHY_DEPTH=32`, default-permissive `node_type` pairs (single `portfolio` EV table; AD-017 / REQ-PPM-001). |
| OD-014 | Confirm storage split between relational SoR and time-series store for ENT-020…025 (AD-004). |
| OD-015 | Confirm netting-set / CSA modeling depth for counterparty (ENT-003 related). |

## 8. Dependencies

- [temporal_reproducibility_standard.md](temporal_reproducibility_standard.md) (bitemporal columns, snapshots).
- [audit_event_taxonomy.md](audit_event_taxonomy.md) (ENT-045 schema).
- [entitlement_sod_model.md](../06_security/entitlement_sod_model.md) (DC tags, ENT-043/044).
- [numerical_quant_standards.md](../05_analytics_methodologies/numerical_quant_standards.md) (monetary/FX/date conventions).
- AD-004 (datastore), AD-005 (temporal), AD-008 (tenancy).
