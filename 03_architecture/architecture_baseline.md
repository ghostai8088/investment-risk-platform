# Architecture Baseline

## Document Control

| Field | Value |
|---|---|
| Document ID | ARCH-BASELINE-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-02 Chief Architect AI |
| Approver | H-06 Engineering Lead |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | foundational_adrs.md, canonical_data_model_standard.md, temporal_reproducibility_standard.md, audit_event_taxonomy.md, entitlement_sod_model.md, numerical_quant_standards.md, capability_map.md |
| Supported Build Rules | BR-5, BR-6, BR-9, BR-10, BR-11, BR-12, BR-13 |

## 1. Purpose & Scope

Define the target logical architecture, bounded contexts, mandatory cross-cutting frameworks, calculation-engine pattern,
integration pattern, environment topology, and non-functional baseline that constrain all subsequent implementation. This is a
**full-scope enterprise architecture**; construction is sequenced by phase, but the structure is defined now so no module is
built outside it. No application code is authored here.

## 2. Architecture Principles (ARCH-P)

| ID | Principle |
|---|---|
| ARCH-P-01 | Modular, bounded-context design; no module reaches into another's persistence. |
| ARCH-P-02 | Cross-cutting frameworks (entitlement, audit, lineage, calculation-run) are platform services that **no module may bypass** (BR-11/12/13). |
| ARCH-P-03 | Calculations are deterministic and reproducible from versioned inputs (BR-6, BR-9). |
| ARCH-P-04 | No calculation logic in the presentation layer; UI is a consumer of governed results. |
| ARCH-P-05 | Public and private asset domains are first-class and structurally equal. |
| ARCH-P-06 | Secrets are externalized; never in source (BR-10). |
| ARCH-P-07 | Extensible by configuration: analytics may start simple but must be swappable without structural change. |
| ARCH-P-08 | Separation of duties is enforced architecturally, not only procedurally (e.g., independent audit store). |

## 3. Logical Architecture (layers)

```
+--------------------------------------------------------------+
|  Presentation:  1st Line Dashboard | 2nd Line Dashboard |     |
|                 Reporting UI | Admin Console (entitled views) |
+--------------------------------------------------------------+
|  API / Gateway:  AuthN, request entitlement check, rate limit |
+--------------------------------------------------------------+
|  Domain Services (bounded contexts — Section 4)               |
+--------------------------------------------------------------+
|  Calculation Engine (deterministic, versioned, run-tracked)   |
+--------------------------------------------------------------+
|  Cross-Cutting Platform Frameworks (Section 5)                |
|   Entitlement | Audit | Lineage | Calculation-Run | Workflow  |
|   Model Registry | Reporting | Integration/Adapters           |
+--------------------------------------------------------------+
|  Data Platform: System-of-record | Time-series/market data |  |
|                 Document store | Audit store (segregated)     |
+--------------------------------------------------------------+
```

## 4. Bounded Contexts (Domain Services)

| Ctx ID | Bounded Context | Core responsibility | Capability map ref |
|---|---|---|---|
| BC-01 | Portfolio & Positions | Hierarchies, positions, transactions, valuations, exposure aggregation | §1 |
| BC-02 | Public Market & Reference Data | Prices, curves, vols, spreads, ratings, benchmarks | §2 |
| BC-03 | Security Master & Reference | Instruments, issuers, identifiers/xref, corporate actions, calendars | §2 |
| BC-04 | Private Asset Data | Commitments, calls, distributions, GP NAV, appraisals, proxies | §3 |
| BC-05 | Market Risk | VaR, ES, sensitivities, factor exposure, drawdown, stress | §4 |
| BC-06 | Credit Risk | PD/LGD/EAD/EL, migration, spread, concentration | §5 |
| BC-07 | Counterparty Risk | CE, PFE, EPE, netting, collateral, CSA, wrong-way, CVA (staged) | §6 |
| BC-08 | Liquidity Risk | Classification, redemption/funding stress, waterfall, capital-call forecast | §7 |
| BC-09 | Scenario & Stress | Historical, hypothetical, reverse, macro, combined | §8 |
| BC-10 | Limits & Breach Workflow | Limit framework, utilization, detection, 1L/2L workflow, closure | §9 |
| BC-11 | Model Governance | Inventory, versioning, validation, tiering, approval | §10 |
| BC-12 | Data Quality & Lineage | DQ rules, reconciliation, overrides, source-to-target lineage | §11 |
| BC-13 | Audit | Immutable audit event capture and query | §11/§12 |
| BC-14 | Reporting | Governed, reproducible reports & extracts | §12 |
| BC-15 | Security & Administration | Identity, RBAC/ABAC entitlements, admin, export controls | §13 |
| BC-16 | Integration | Ingestion adapters with anti-corruption layer | §14 |

## 5. Mandatory Cross-Cutting Frameworks

These are shared services every module binds to; bypass is a build-rule violation and a control finding.

| FW ID | Framework | Enforces | Contract reference |
|---|---|---|---|
| FW-ENT | Entitlement | BR-11 | entitlement_sod_model.md |
| FW-AUD | Audit Event | BR-5, BR-12, BR-16 | audit_event_taxonomy.md |
| FW-LIN | Data Lineage | BR-6, BR-13 | canonical_data_model_standard.md, temporal_reproducibility_standard.md |
| FW-RUN | Calculation-Run | BR-6, BR-9 | temporal_reproducibility_standard.md, numerical_quant_standards.md |
| FW-WFL | Workflow/State-Machine | BR-7 (breach/override/approval) | entitlement_sod_model.md (maker-checker) |
| FW-MDL | Model Registry | BR-3 | model_governance_independence_policy.md |

## 6. Calculation Engine Pattern

- Calculations run as **jobs** that produce a `CalculationRun` record binding code/model version, input dataset snapshot,
  assumption set, parameters, RNG seed (where stochastic), initiator, and timestamps (FW-RUN).
- Engine is **separated from UI and from persistence of source data**; it reads governed inputs and writes governed results.
- Results are **immutable**; corrections create new runs/versions (temporal_reproducibility_standard.md), never overwrites.
- Pluggable methodology modules per bounded context so initial simple methods can be replaced without structural change
  (ARCH-P-07); each registered in the Model Registry (FW-MDL).
- Determinism and numerical conventions governed by numerical_quant_standards.md.

## 7. Integration & Adapter Pattern

- All external feeds (CSV, Excel, API, SFTP, vendor, portfolio accounting, market data, GP reports) enter through an
  **anti-corruption layer**: ingest → validate → map to canonical model → record lineage → emit audit event.
- Adapters never write directly to domain stores; they produce canonical records via BC-03/BC-12 validation.

## 8. Environment Topology & Deployment

| Env | Purpose | Data |
|---|---|---|
| dev | Engineering | Synthetic/de-identified |
| test | Automated tests, benchmark portfolios | Synthetic + golden datasets |
| staging | Pre-prod, release validation | De-identified production-like |
| prod | Live | Production (entitled, classified) |

Deployment model, multi-tenancy, and stack are governed by ADRs AD-003, AD-008, AD-010. DR targets (RTO/RPO) are in §9 and
subject to AD-010.

## 9. Non-Functional Baseline (NFR)

Placeholders to be ratified per AD-010 and the (future) NFR document; stated now to constrain design.

| NFR ID | Dimension | Baseline target (to confirm) |
|---|---|---|
| NFR-01 | Calculation reproducibility | 100% — identical run inputs reproduce identical results within QS tolerances |
| NFR-02 | Availability (prod) | 99.5% business-hours initial; revisit for enterprise SLA |
| NFR-03 | RPO / RTO | RPO ≤ 24h, RTO ≤ 8h initial; revisit per buyer requirements |
| NFR-04 | Audit/lineage retention | ≥ 7 years (confirm per jurisdiction) |
| NFR-05 | Performance | Daily full-portfolio risk batch within overnight window; interactive queries < 3s p95 |
| NFR-06 | Scalability | Scale to multi-fund, multi-asset-class portfolios without architectural change |
| NFR-07 | Observability | All FW-* frameworks emit metrics, logs (no sensitive data), traces |

## 10. Technology Stack

The concrete stack is decided in [foundational_adrs.md](foundational_adrs.md) (AD-003 stack, AD-004 datastore). Until ratified,
no module may hard-code stack assumptions beyond the interface contracts in §5.

## 11. Open Decisions

| ID | Open Decision |
|---|---|
| OD-004 | Ratify technology stack (AD-003). |
| OD-005 | Ratify datastore strategy incl. time-series/market-data store (AD-004). |
| OD-006 | Confirm multi-tenancy model — single-tenant vs pooled (AD-008). |
| OD-007 | Confirm deployment model — cloud/on-prem/hybrid and DR targets (AD-010). |
| OD-008 | Confirm whether a dedicated workflow/BPM engine (FW-WFL) is built or adopted. |

## 12. Dependencies

- foundational_adrs.md (AD-003 … AD-010) must be approved before BC services are implemented.
- canonical_data_model_standard.md and temporal_reproducibility_standard.md define the data contracts for all BCs.
- entitlement_sod_model.md and audit_event_taxonomy.md define FW-ENT and FW-AUD contracts.
