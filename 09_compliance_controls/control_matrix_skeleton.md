# Control Matrix Skeleton

## Document Control

| Field | Value |
|---|---|
| Document ID | COMPLIANCE-CTRLMTX-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft (skeleton — to be extended per phase) |
| Owner | R-10 Compliance & Controls AI |
| Approver | H-05 Head of Compliance (H-08 Internal Audit consulted) |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | build_rules.md, all 03–07 standards, audit_event_taxonomy.md, entitlement_sod_model.md, model_governance_independence_policy.md |
| Supported Build Rules | BR-1 … BR-16 (traceability layer) |

## 1. Purpose

Provide the control library that links each control to the capability it protects, the build rule(s) it enforces, the owning
role, the test/assurance method, and the evidence artifact. This is the traceability backbone that makes the build rules
auditable. It is a **skeleton**: controls are seeded across every framework and will be expanded per construction phase.

## 2. Schema

| Column | Meaning |
|---|---|
| Control ID | Stable `CTRL-nnn` |
| Control | Name/description |
| Type | Preventive / Detective |
| Mode | Automated / Manual / Hybrid |
| Capability | Capability map ref / bounded context |
| Build Rule | BR-n enforced |
| Owner | Accountable role (R-/H-) |
| Test / Assurance | How the control is verified |
| Evidence | Artifact proving operation |
| Status | Planned / Designed / Implemented |

## 3. Control Library (seed)

| Control ID | Control | Type | Mode | Capability | Build Rule | Owner | Test / Assurance | Evidence | Status |
|---|---|---|---|---|---|---|---|---|---|
| CTRL-001 | Every feature has tests before completion | Preventive | Automated | All | BR-1 | R-09 | CI gate; coverage report | Pipeline run, coverage | Planned |
| CTRL-002 | Every calculation has methodology doc | Preventive | Hybrid | §4–8 | BR-2 | R-06 | Doc-consistency hook | Methodology doc + QS-24 decl. | Planned |
| CTRL-003 | Every model/version inventoried before use | Preventive | Hybrid | §10 | BR-3 | R-08 | Model-inventory hook | Inventory entry (ENT-035) | Planned |
| CTRL-004 | Every field defined in data dictionary | Preventive | Manual | §11 | BR-4 | R-05 | Dictionary review | Data dictionary | Planned |
| CTRL-005 | Data-changing actions emit audit events | Detective | Automated | §11/12 | BR-5, BR-12 | R-07 | Audit completeness test | Audit events (ENT-045) | Implemented (1E, partial: calc-run + entitlement) |
| CTRL-006 | Risk results bind full lineage (source→run) | Preventive | Automated | §4–8 | BR-6, BR-13 | R-05 | Lineage completeness test | Lineage edges, run record | Planned |
| CTRL-007 | Manual overrides carry BR-7 fields + approval | Preventive | Automated | §11 | BR-7 | R-07 | Override schema validation | `OVERRIDE.*` events | Planned |
| CTRL-008 | Scenarios versioned with saved assumptions | Preventive | Automated | §8 | BR-8 | R-06 | Scenario version test | Scenario versions (ENT-029) | Planned |
| CTRL-009 | Reports reproducible from bound runs | Detective | Automated | §12 | BR-9 | R-09 | Report regeneration test | Report version + run ids | Planned |
| CTRL-010 | No secrets in source | Preventive | Automated | §13 | BR-10 | R-12 | Secret-scan hook | Scan results | Planned |
| CTRL-011 | No module bypasses entitlement framework | Preventive | Automated | §13 | BR-11, BR-17 | R-07 | Deny-by-default + tenant-scope tests (app) + Postgres RLS (migration job) | Entitlement test suite, RLS migration | Implemented (1E) |
| CTRL-012 | No module bypasses audit framework | Preventive | Automated | All | BR-12 | R-07 | Unaudited-write detection | Audit coverage report | Planned |
| CTRL-013 | No module bypasses lineage framework | Preventive | Automated | §11 | BR-13 | R-05 | Lineage coverage test | Lineage report | Planned |
| CTRL-014 | Limitations explicitly documented | Detective | Manual | All | BR-14 | R-10 | Limitations register review | Limitations register | Planned |
| CTRL-015 | Human approval gate for restricted change types | Preventive | Manual | §10/11/13 | BR-15 | H-02/H-03/H-05/H-06/H-10 | Approval-record check | `approval_ref` records | Planned |
| CTRL-016 | Material AI agent actions logged | Detective | Automated | All | BR-16 | R-07 | Agent-event completeness test | `AGENT.*` events | Planned |
| CTRL-017 | Temporal-class declared + append-only immutability of audit | Preventive | Automated | §11/12 | BR-6, BR-9, BR-19 | R-05 | Temporal-class + append-only/no-overwrite tests | Append-only test, temporal test | Implemented (1E, audit; FR/EV domain pending) |
| CTRL-018 | Reproduction test re-runs historical runs | Detective | Automated | §4–8 | BR-6, BR-9 | R-09 | Scheduled reproduction job (TR-13) | Reproduction report | Planned |
| CTRL-019 | Decimal-safe money; no float for currency | Preventive | Automated | §4–8 | BR-2 | R-06 | Static/type checks (QS-01) | Lint/test results | Planned |
| CTRL-020 | Deterministic seeds recorded for MC | Preventive | Automated | §4/6/8 | BR-6 | R-06 | Seed-binding test (QS-18) | Run parameters | Planned |
| CTRL-021 | SoD pairs enforced (maker≠checker) | Preventive | Automated | §13 | BR-7, BR-15 | R-07 | SoD conflict test (SOD-01…08) | SoD test results | Planned |
| CTRL-022 | Independent model validation (dev≠validator) | Preventive | Manual | §10 | BR-15 | H-02 | Validation independence review | Validation record (ENT-037) | Planned |
| CTRL-023 | Data classification + MNPI barriers enforced | Preventive | Hybrid | §3/13 | BR-11 | R-07/H-05 | Barrier access tests | Denied-access audit | Planned |
| CTRL-024 | Export controls (DC-4 blocked by default) | Preventive | Automated | §13 | BR-11 | R-07 | Export-control test | `EXPORT.*` events | Planned |
| CTRL-025 | Entitlement changes maker-checked + audited | Preventive | Automated | §13 | BR-7, BR-11 | R-07 | Entitlement-change test | `ENTITLEMENT.*` events | Planned |
| CTRL-026 | Audit store append-only + hash-chain integrity | Preventive | Automated | §12 | BR-12, BR-18 | R-12 | Hash-chain verify + tamper-detection + append-only tests (app + Postgres trigger) | Audit tests, migration trigger | Implemented (1E) |
| CTRL-027 | Data quality rules run on ingest | Detective | Automated | §11 | BR-5 | R-05 | DQ hook execution | DQ results (ENT-039) | Planned |
| CTRL-028 | Reconciliation of sources | Detective | Hybrid | §11 | BR-6 | R-05 | Recon job | Recon results (ENT-040) | Planned |
| CTRL-029 | Stale/missing data flagged, not silently filled | Preventive | Automated | §3/4–8 | BR-2, BR-14 | R-06 | Missing-data handling test (QS-15/16) | Flagged records | Planned |
| CTRL-030 | Production change approval (release gate) | Preventive | Manual | §13 | BR-15 | H-10 | Release-readiness review | Go/no-go record | Planned |
| CTRL-031 | Breach workflow enforces 1L/2L separation | Preventive | Hybrid | §9 | BR-7 | R-01/H-01 | Workflow state test (SOD-02) | `BREACH.*` events | Planned |
| CTRL-032 | Failed audit capture blocks governed change | Preventive | Automated | All | BR-12 | R-07 | Fail-closed test (AUD-04) | Test results | Planned |

## 4. Coverage Note

Every build rule BR-1 … BR-19 is covered by at least one control above. The Step 1C rules map to existing controls: **BR-17**
(tenant isolation) → CTRL-011/CTRL-023; **BR-18** (audit hash-chain integrity) → CTRL-026/CTRL-032; **BR-19** (temporal-class
conformance) → CTRL-017/CTRL-018. As construction phases open, controls will be split to specific bounded contexts and
capabilities (CAP IDs once added to the capability map) and given Test/Evidence detail.

## 5. Open Decisions

| ID | Open Decision |
|---|---|
| OD-036 | Add capability IDs (CAP-x.y) to capability_map.md so controls map 1:1 to capabilities. |
| OD-037 | Confirm regulatory mapping layer (which regimes/controls frameworks, e.g., SOC 2, ISO 27001) for buyer due diligence. |
| OD-038 | Confirm control testing cadence and independent assurance owner (H-08) per control. |

## 6. Dependencies

- build_rules.md (BR-1 … BR-16).
- audit_event_taxonomy.md, entitlement_sod_model.md, model_governance_independence_policy.md, temporal_reproducibility_standard.md, numerical_quant_standards.md (control mechanisms).
- capability_map.md (capability IDs — OD-036).
