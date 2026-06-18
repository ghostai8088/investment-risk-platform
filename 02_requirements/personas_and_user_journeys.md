# Personas & User Journeys

## Document Control

| Field | Value |
|---|---|
| Document ID | REQ-PERSONA-001 |
| Version | 0.1 (Draft baseline) |
| Status | Accepted as baseline |
| Owner | R-01 Product Manager AI |
| Approver | H-07 Product Owner |
| Created | 2026-06-18 |
| Last Reviewed | 2026-06-18 |
| Related Documents | requirements_backbone.md, requirements_traceability_matrix.md, ../01_product_strategy/regulatory_product_scope.md, ../00_ai_operating_model/reconciled_agent_role_registry.md |
| Supported Build Rules | BR-7, BR-11, BR-15, BR-17 |

## 1. Purpose

Define the personas referenced by the RTM and the end-to-end user journeys that the requirements must support. Persona codes
(`P-*`) alias the `PERSONA-0x` IDs in [regulatory_product_scope.md](../01_product_strategy/regulatory_product_scope.md) and the
human accountability roles (`H-*`) in the
[reconciled agent & role registry](../00_ai_operating_model/reconciled_agent_role_registry.md). Personas drive entitlement
design and segregation of duties (1L/2L/3L).

## 2. Personas

| Code | Persona | Alias | LoD | Primary goals | Key capabilities |
|---|---|---|---|---|---|
| P-CRO | Chief Risk Officer / Head of Risk | PERSONA-01 / H-01 | 2L (head) | Risk appetite, board oversight, sign-off limit framework | CAP-10, CAP-16, CAP-9 |
| P-RM | Risk Manager | PERSONA-02 / H-01 | 2L | Oversee risk, review breaches, own limits & 2L review | CAP-5–11, CAP-16 |
| P-RA | Risk Analyst | PERSONA-02 / H-09 | 1L | Run analytics, investigate drivers, prepare packages | CAP-5–9, CAP-1 |
| P-PM | Portfolio Manager | PERSONA-03 / H-09 | 1L | See exposure/risk in scope, respond to breaches | CAP-1, CAP-5–8, CAP-11 |
| P-MV | Model Validator (independent) | PERSONA-04 / H-02 | 2L | Validate models, effective challenge, approve tiers | CAP-12 |
| P-DS | Data Steward | PERSONA-05 / H-04 | Platform | Data quality, reconciliation, overrides, reference data | CAP-2–4, CAP-13, CAP-14, CAP-18 |
| P-CO | Compliance Officer | PERSONA-06 / H-05 | 2L | Controls, MNPI/restricted lists, regulatory themes | CAP-15, CAP-17, CAP-4 |
| P-IA | Internal Auditor | PERSONA-07 / H-08 | 3L | Independent assurance, audit extracts (read-only) | CAP-15, CAP-14 |
| P-ADM | Platform Administrator | PERSONA-08 | Platform | Users, entitlements, configuration | CAP-17, CAP-18 |
| P-BRD | Board / Investment Committee | PERSONA-09 | — | Consume governed summary reporting | CAP-16 |
| P-OPS | Buyer / Operations (COO/CTO) | PERSONA-10 | — | Security, due-diligence, deployment fit | CAP-15, CAP-17 |

**System actor:** BAU AI agents (CAP-19) operate under defined tool tiers (registry §2); they assist these personas but never
hold the approver side of any SoD pair (BR-15) and are always logged (BR-16).

## 3. Segregation-of-Duties anchors (drive entitlement design)

| SoD pair | Maker | Checker | Requirement |
|---|---|---|---|
| Override | P-DS / P-RA | P-RM / P-DS (different person) | REQ-DQR-003 |
| Breach closure | P-PM (1L) | P-RM (2L) | REQ-BRC-002 |
| Model approval | P-RA (developer) | P-MV / H-02 | REQ-MDG-003 |
| Limit change | P-RM | P-CRO / second 2L | REQ-LIM-001 |
| Entitlement change | requester | P-ADM (different) | REQ-ADM-002 |
| Board report publish | P-RM (drafts) | P-CRO | REQ-RPT-002 |

## 4. User Journeys

Each journey lists the steps and the requirements/capabilities exercised. Journeys are the basis for per-phase user stories.

### UJ-1 — 1st Line daily risk review (P-RA, P-PM)
1. Authenticate (SSO; today dev shim) → entitled to specific portfolios (REQ-ADM-001/002, BX-ENT).
2. View positions & exposures as-of (REQ-PPM-002/004).
3. Run/inspect market & credit risk results (REQ-MKT-001/002, REQ-CRD-001) — reproducible, lineage-bound.
4. See limit utilization and any breaches (REQ-LIM-002/003).
5. If breached, initiate 1L response (REQ-BRC-002). *All actions audited (BX-AUD).*

### UJ-2 — 2nd Line oversight & breach review (P-RM, P-CRO)
1. Review portfolio/aggregate risk and scenario results (REQ-MKT-004, REQ-SCN-003).
2. Define/approve limits via maker-checker (REQ-LIM-001, SoD).
3. Review 1L breach responses independently; approve/decline closure with evidence (REQ-BRC-002/003).
4. Approve board report for publication (REQ-RPT-002).

### UJ-3 — Independent model validation (P-MV)
1. Open model inventory; select model/version (REQ-MDG-001).
2. Review methodology, assumptions, limitations, benchmark results (BX-DOC).
3. Record validation & effective challenge; cannot have authored the model (REQ-MDG-003, SOD-03).
4. Set approval/restricted-use status; Tier-1 requires H-02 sign-off (BR-15).

### UJ-4 — Data steward data-quality cycle (P-DS)
1. Ingest data via upload/adapter (REQ-INT-001/002) → DQ rules run (REQ-DQR-001).
2. Triage exceptions; reconcile across sources (REQ-DQR-002).
3. Apply a controlled override with justification + approval (REQ-DQR-003, BR-7).
4. Confirm lineage captured for corrected data (REQ-LIN-001).

### UJ-5 — Administration & entitlement management (P-ADM)
1. Create users; assign roles/permissions with tenant scope (REQ-ADM-002).
2. Entitlement changes are maker-checked and audited (BX-SOD).
3. Configure data classification / export controls incl. MNPI barriers (REQ-ADM-003).

### UJ-6 — Board reporting (P-RM → P-CRO → P-BRD)
1. Generate board risk report from approved metrics (REQ-RPT-002) — reproducible (BR-9).
2. P-CRO reviews & approves publication (SoD).
3. P-BRD consumes the governed report; data is entitlement-scoped.

### UJ-7 — Internal audit / due diligence (P-IA, P-OPS)
1. Query the audit trail for a period/entity (REQ-AUD-003) — entitled, read-only.
2. Verify chain integrity (REQ-AUD-002) and pull a signed extract.
3. Trace a specific result to source via lineage (REQ-LIN-002).

### UJ-8 — Private markets onboarding (P-DS, P-CO)
1. Ingest GP NAV / capital calls / commitments (REQ-PRV-001/002/003 via REQ-INT-003).
2. Flag stale valuations; record proxy mappings (REQ-PRV-003).
3. Restrict private company financials behind MNPI barriers (REQ-PRV-004, REQ-ADM-003).

## 5. Open Questions

See [RTM §5](requirements_traceability_matrix.md) (OQ-007 covers persona consolidation at small-team scale).

## 6. Dependencies

Persona-driven entitlement and SoD design depend on REQ-ADM-002 (SoD/maker-checker) and DEP-SSO (real identity); until SSO lands,
journeys use the dev header-shim principal (foundation placeholder).
