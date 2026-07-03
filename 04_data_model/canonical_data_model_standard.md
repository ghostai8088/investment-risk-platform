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
| ENT-009 | `benchmark` | Benchmark definitions and constituents. **REALIZED in P2-6 (migration `0021`)** as `benchmark` (EV definition header — `REFERENCE.*` audited) + `benchmark_constituent` (FR bitemporal membership — `MARKET.BENCHMARK_CONSTITUENT_*` audited; OQ-P2-6-11 Option A). Identity key `(tenant, benchmark_code, benchmark_source)`; constituent current-head partial-unique `(tenant, benchmark_id, instrument_id, effective_date) WHERE valid_to IS NULL AND system_to IS NULL`; `weight` `Numeric(20,12)` (sanity `RANGE [0,1]`); `instrument_id` NOT-NULL FK (`resolve_instrument`); `effective_date` a separate immutable logical key; symmetric tenant-scoped RLS (NEVER hybrid; NEITHER table append-only); VENDOR_BENCHMARK ORIGIN lineage; reuse `marketdata.view`/`.ingest`. **Captured, not computed** (no performance/active-return/active-risk/tracking-error/attribution/factor). `benchmark_level`/`benchmark_return` (captured levels/returns) **DEFERRED** — a net-new canonical ENT id, NOT minted here (OD-P2-6-K). |

### Portfolio & Positions (BC-01)
| ID | Entity | Notes |
|---|---|---|
| ENT-010 | `portfolio` / `fund` / `strategy` / `account` | Hierarchy nodes |
| ENT-011 | `position` | Holdings (bitemporal) — **REALIZED in P1C-3 (migration `0014`)** |
| ENT-012 | `transaction` | Trades/cashflows |
| ENT-013 | `valuation` | Valuation history (bitemporal) — **REALIZED in P1C-4 (migration `0015`)** |
| ENT-014 | `exposure_aggregate` | Derived aggregation (run-tracked). **RATIFIED-IN-PLANNING for P2-3** (2026-06-26; `p2_3_decision_record.md` OD-P2-3-A…L + `p2_3_exposure_implementation_plan.md`) — the platform's **FIRST official governed derived number** (AD-018; AD-014 / FW-RUN §5 / TR-15 gate). **IA, TRUE append-only** (in `APPEND_ONLY_TABLES`; `irp_prevent_mutation` P0001 trigger + ORM guard — the `transaction`/`dataset_snapshot` exemplar; a re-run is a NEW run + new rows, never an edit). **RUN-BOUND + SNAPSHOT-GATED:** no row without a non-null `input_snapshot_id` + a complete `calculation_run` (ENT-026). Grain = the **per-holding atom `(portfolio_id, instrument_id, base_currency)`** (1:1 to one snapshot POSITION + VALUATION + FX component; **NO portfolio/subtree TOTAL rows in P2-3** — a deterministic Σ deferred); **signed market value v1** `exposure_amount = quantize_HALF_UP(signed_quantity × captured mark_value × effective fx_rate, 6)` (`Numeric(28,6)`, base currency), `exposure_type = MARKET_VALUE` only; captured `signed_quantity`/`mark_value`/`fx_rate` (the EFFECTIVE composite multiplier) + `fx_legs` (JSON leg refs — **NOT a hard FK** to the supersedable `fx_rate` FR row; the snapshot `COMPONENT_KIND_FX` is the authoritative version-pin). Symmetric tenant-scoped RLS (NEVER hybrid); cross-tenant fails closed. **BASIC exposure ONLY — NOT risk** (NO VaR/Expected Shortfall/factor/sensitivity/scenario/stress/P&L/performance/pricing/valuation model). Reproducible from the snapshot-pinned captured content (TR-09) — the exposure compute makes NO live market read. **Planned, NOT implemented** (migration `0018` planned: the `exposure_aggregate` table + the additive `calculation_run.environment_id`; head stays `0017_fx_rate`). REQ-PPM-004 advances. |

> **P1C-0 ratification note (AD-017, 2026-06-23 — conforms to §2A temporal classes, no AD-005 amendment):** P1C is a **capture-only** domain block. **ENT-010** (`portfolio`) is **REALIZED in P1C-1 (migration `0012`)** as a **single `portfolio` EV table** with a `node_type` controlled-vocab (`PORTFOLIO`/`FUND`/`STRATEGY`/`ACCOUNT`) + a `parent_portfolio_id` self-FK adjacency — the entitlement portfolio-scope **ANCHOR** (subtree semantics; ABAC enforcement deferred to P6+). **ENT-011** position (**FR**) is **REALIZED in P1C-3 (migration `0014`)** as the captured bitemporal holdings master (reusing the P1B-3 `instrument_terms` FR protocol — create / effective-dated supersede / as-known correction / `reconstruct_position_as_of` on both axes; aggregated `(portfolio, instrument)` grain, signed quantity, opaque `cost_basis`; `POSITION.CREATE`/`.UPDATE`/`.CORRECTION` EVT-170/171/172; **captured directly, NOT derived from transactions**, NOT append-only). **ENT-013** valuation (**FR**) is **REALIZED in P1C-4 (migration `0015`)** as the captured bitemporal mark history (reusing the `position`/`instrument_terms` FR protocol — create / effective-dated supersede / as-known correction / `reconstruct_valuation_as_of` on both axes; grain `(portfolio, instrument, valuation_date)` with `valuation_date` an immutable logical-key column; `mark_value` captured, `mark_source` an inert label; `VALUATION.CREATE`/`.UPDATE`/`.CORRECTION` EVT-180/181/182; **captured marks, NOT modeled / NOT derived from positions**, NOT append-only); **ENT-012** transaction (**IA**, append-only) — **REALIZED in P1C-2 (migration `0013`)** as the `transaction` immutable append-only trade/cashflow event log (keyed to portfolio + instrument; truly immutable via the `irp_prevent_mutation` P0001 trigger + ORM guard; corrections are explicit reversal records — capture-only, no derivation; `TRANSACTION.RECORD`/`.REVERSE` EVT-160/161). **ENT-014** `exposure_aggregate` (IA, derived) and `dataset_snapshot` **stay P2** (AD-014) unless explicitly reopened *(— **REOPENED for P2**: `dataset_snapshot` ratified at P2-0 (ENT-049/050); **`exposure_aggregate` ratified-in-planning at P2-3** as the first governed derived number — see the ENT-014 Notes cell + AD-018)* — P1C performs **no** exposure aggregation / risk / pricing / valuation models / corporate-action application. OD-012 (identifier precedence) and OD-015 (counterparty netting/CSA) remain deferred beyond P1C.

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
| ENT-024 | `fx_rate` | FX (QS triangulation). **REALIZED in P2-2 (migration `0017`, FR)** — captured vendor FX; logical key `(base_currency, quote_currency, rate_date, rate_type)`; `rate` = "1 base = rate quote" (QS-08), `Numeric(28,12)`, MID only (QS-09); `rate_date` a separate immutable logical key (the `valuation_date` precedent); current-head partial-unique `WHERE valid_to IS NULL AND system_to IS NULL`; symmetric tenant-scoped RLS (NEVER hybrid); VENDOR `data_source` ORIGIN lineage; `MARKET.FX_*` audit; a pure published-rate `convert` (direct/reciprocal/triangulation-through-base, fail-closed) — **no analytics, no exposure, no `calculation_run`**. |
| ENT-025 | `factor_return` | Risk-factor returns. **REALIZED-IN-P3-2 (2026-07-02; `p3_2_decision_record.md` OD-P3-2-A…J + `p3_2_factor_return_inputs_implementation_plan.md`; implemented LOCAL-ONLY under degraded connectivity — commit + push/CI PENDING, NOT remote-CI-green)** as a split mirroring `benchmark` (OQ-P2-6-11 Option A): a **net-new `factor` definition = EV** (`EffectiveDatedMixin`; entity-versioned in place via `record_version`; `REFERENCE.CREATE`/`.UPDATE`-audited; identity key `(tenant, factor_code, factor_source)`; `factor_family` controlled vocab STYLE/INDUSTRY/COUNTRY/MACRO/MARKET/CURRENCY/OTHER; optional `factor_type`/`region`/`currency_code`(validated via `resolve_currency`)/`asset_class`; `frequency` DAILY v1) **+ `factor_return` = FR bitemporal captured series** (ENT-025; `FullReproducibleMixin` — the EIGHTH persisted user after `instrument_terms`/`position`/`valuation`/`fx_rate`/`price_point`/`curve`/`benchmark_constituent`; capture / effective-dated supersede / as-known correction / both-axes `reconstruct_factor_return_as_of`; `MARKET.FACTOR_RETURN_CREATE`/`_UPDATE`/`_CORRECTION`-audited). **The `factor` canonical id is MINTED here** (the `benchmark` precedent — a net-new EV definition entity, distinct from ENT-025 which is the FR return series). Grain `(tenant, factor_id, return_date, return_type)`; current-head partial-unique `WHERE valid_to IS NULL AND system_to IS NULL`; `return_value` = captured DECIMAL fraction (`0.01`=1%, NOT percent/bps), `Numeric(20,12)`; `return_type` SIMPLE (LOG reserved); `factor_id` NOT-NULL FK (`resolve_factor`, tenant-filtered); `return_date` a separate immutable logical key. A binder-side **finiteness guard** rejects NaN/±Inf pre-write (the min-only `> -1` economic-sanity DQ RANGE does not catch +Inf); symmetric tenant-scoped RLS (NEVER hybrid; **NEITHER table append-only** — EV mutates in place, FR requires close-out UPDATEs, no `irp_prevent_mutation` trigger — the `benchmark` precedent); VENDOR_FACTOR ORIGIN lineage; reuse `marketdata.view`/`.ingest`. **Captured INPUT, NOT computed** — no price-derived/regressed/factor-model return, no exposure/covariance/VaR/ES, **NO `calculation_run`, NO `model_version`, NO snapshot pin** (an INPUT, not a governed derived number). **Computed factor returns DEFERRED** (would require a registered `model_version` + `methodology_ref`, the ENT-028 `sensitivity_result` precedent). |

### Risk Results & Scenarios (BC-05…BC-09)
| ID | Entity | Notes |
|---|---|---|
| ENT-026 | `calculation_run` | Binds version+snapshot+assumptions+seed+initiator (FW-RUN). **P2-3: binding wired (ratified-in-planning, OD-P2-3-F).** **IA, status-mutable** (`status` mutates in place via `update_run_status`; therefore **NOT** in `APPEND_ONLY_TABLES` / not in any `irp_prevent_mutation` loop — the `ingestion_batch` precedent; lifecycle history lives in the audit chain). For the P2-3 exposure run it binds: `input_snapshot_id` **non-null** at the governed-write path; **`code_version`** the mandatory deterministic anchor; a **NEW additive `environment_id`** column (migration `0018`, a non-breaking add on the status-mutable table); `model_version_id` **N/A-with-recorded-rationale** (no estimation model — deterministic captured-mark rollup; never mint a sham model_version); `assumption_set_id`/`random_seed`/scenario **N/A**; `run_type='EXPOSURE_AGGREGATE'`. Reuses the shipped `CALC.RUN_CREATE` + `CALC.RUN_STATUS_CHANGE` audit emitters (+ ONE additive `outcome` param on `update_run_status` in `calc/service.py` — the sole non-frozen calc change; `audit/service.py` FROZEN). **Failure model split by timing:** a **pre-create refusal** (missing prerequisite) = ZERO run + ZERO exposure + ZERO audit; a **post-create FAILED** run (gate failure after RUNNING) = a committed FAILED run + `CALC.RUN_STATUS_CHANGE(→FAILED, outcome='failure')` audit + ZERO exposure rows. **Planned, NOT implemented** (the additive `environment_id` ships with migration `0018`). |
| ENT-027 | `risk_result` | Immutable result rows linked to a run |
| ENT-028 | `sensitivity` / `exposure_metric` | Greeks/duration/PFE/etc. **REALIZED-IN-P3-1 (2026-06-30; `p3_1_decision_record.md` OD-P3-1-A…O + `p3_1_sensitivities_implementation_plan.md`)** as `sensitivity_result` — the platform's **FIRST reproducible governed RISK number** (analytic curve-node DV01 / spread-DV01; migration `0022_sensitivity`). **IA, TRUE append-only** (in `APPEND_ONLY_TABLES`; `irp_prevent_mutation` P0001 trigger + ORM guard — the `exposure_aggregate` exemplar; a re-run is a NEW run + new rows). **RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND:** no row without a non-null `calculation_run_id` + `input_snapshot_id` + a **registered** `model_version_id` (the model-governance hardening vs the model-less `exposure_aggregate`; `assert_registered_model_version` is load-bearing pre-create — **CTRL-003 now EXECUTABLE**). **Curve-intrinsic v1 grain** `(calculation_run_id, curve_id, value_type, tenor_days, sensitivity_type)`; `sensitivity_value = quantize_HALF_UP(-T·DF·1bp, 12)` (`Numeric(28,12)`, per unit notional; ACT/365F + continuous compounding, OD-P3-1-G); **NO `portfolio_id`/`instrument_id`** (instrument attribution DEFERRED — needs captured cash-flow terms + interpolation + a pricing engine, none in scope). Reads ONLY snapshot-pinned `COMPONENT_KIND_CURVE` content (reproducible under a later curve correction; TR-09). Symmetric tenant-scoped RLS (NEVER hybrid). **Analytic sensitivities ONLY** — no VaR/ES/factor/covariance/scenario/stress. |
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
| ENT-042 | `lineage_edge` | Source-to-target lineage graph edges (BR-13). **P2-3 (ratified-in-planning, OD-P2-3-J):** the P2-1 internal-lineage writer is generalized to root a `calculation_run` source — additive `source_type` token `SOURCE_TYPE_CALCULATION_RUN` (joining `data_source`/`data_snapshot`) + the additive `edge_kind` value **`EDGE_KIND_DEPENDENCY` (`"DEPENDS_ON"`)**. Edges per exposure run: `dataset_snapshot → calculation_run` (`DEPENDS_ON`) + `calculation_run → exposure_aggregate` (`EDGE_KIND_ORIGIN`, with `lineage_edge.run_id` stamped). `edge_kind`/`source_type` are free controlled-vocab strings → additive, **no `lineage_edge` migration, no framework rewrite**. (**"DEP-LIN" is the RTM/control traceability token, NOT an `edge_kind`.**) Tenant stamped from the RLS-resolved source. |

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

### Reproducibility — Input Snapshots (BC-05 / AD-014)
| ID | Entity | Notes |
|---|---|---|
| ENT-049 | `dataset_snapshot` | **Reproducible input snapshot HEADER** (AD-014). IA, **TRUE append-only** (in `APPEND_ONLY_TABLES` — the `transaction` precedent, NOT the status-mutable `calculation_run` flavor). Pins a knowledge-time-cut input set by `(as_of_valid_at, as_of_known_at, as_of_valuation_date)` + a `manifest_hash`. **NO `status` column; NO `model_version` component** (model_version binds at the run, ENT-026). Reproducibility INFRASTRUCTURE — captures input versions, computes **no** derived number. |
| ENT-050 | `dataset_snapshot_component` | Per-input **physical-version pin** of a `dataset_snapshot`. IA, true append-only. Captures `target_entity_type` + `target_entity_id` (surrogate row id) + `valid_from` + `system_from` (FR) + `record_version` + **`captured_content`** + `content_hash`. Component vocabulary (P2-1): **`PORTFOLIO` / `POSITION` / `VALUATION`**; **`FX` reserved for P2-2**, `PRICE`/`CURVE`/`REFERENCE` later. |

> **P2-0 ratification note (AD-014 reproducibility primitive, 2026-06-26):** `dataset_snapshot` (ENT-049) + `dataset_snapshot_component` (ENT-050) are **ratified-in-planning** (`p2_0_decision_record.md` + `p2_1_dataset_snapshot_implementation_plan.md`) — the AD-014 reproducible input snapshot that **precedes any official derived output**. **Planned, NOT implemented** (migration head stays `0015_valuation`; no `snapshot` package). Temporal class **IA TRUE append-only**; **symmetric tenant-scoped RLS** (never hybrid/SYSTEM_TENANT); cross-tenant component binding **fails closed**. Physical-version pin = `target_entity_id` (surrogate row id) + `valid_from` + `system_from` + `record_version` + `captured_content` + `content_hash`; **FR records pin `valid_from`+`system_from`** (each FR version is a distinct immutable row); the **EV `portfolio` component pins NULL `system_from`** (no system axis) with `record_version` the authoritative drift discriminator (`captured_content` makes EV value-captured); the content hash is **SHA-256** over an **app-side canonical serialization** (deterministic field order; Decimal fixed-scale; ISO-8601 UTC-µs date/time; GUID lowercase; explicit null sentinel; **excludes the mutable close-out markers `valid_to`/`system_to`**). `calculation_run` (ENT-026) **binding begins in P2-3** — P2-1 prepares for it but wires nothing and produces **no** derived number. This **reopens** the AD-017 "`dataset_snapshot` stays P2" deferral (the P2 reproducibility-foundation phase, AD-014).

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
| OD-014 | **RESOLVED (P2-0 ratification, 2026-06-26, via AD-004-R1):** **Postgres-first** behind the AD-004 market-data repository interface; TimescaleDB **deferred** to a measured volume/performance threshold (AD-004's own revisit trigger). The relational SoR backs ENT-020…025 (+ the ENT-049/050 snapshots) for P2 initial volumes; the repo interface keeps a future Timescale swap non-breaking. See **AD-004-R1**. *(orig: confirm storage split between relational SoR and time-series store for ENT-020…025, AD-004.)* |
| OD-015 | Confirm netting-set / CSA modeling depth for counterparty (ENT-003 related). |

## 8. Dependencies

- [temporal_reproducibility_standard.md](temporal_reproducibility_standard.md) (bitemporal columns, snapshots).
- [audit_event_taxonomy.md](audit_event_taxonomy.md) (ENT-045 schema).
- [entitlement_sod_model.md](../06_security/entitlement_sod_model.md) (DC tags, ENT-043/044).
- [numerical_quant_standards.md](../05_analytics_methodologies/numerical_quant_standards.md) (monetary/FX/date conventions).
- AD-004 (datastore), AD-005 (temporal), AD-008 (tenancy).
