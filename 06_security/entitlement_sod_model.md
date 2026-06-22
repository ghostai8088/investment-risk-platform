# Entitlement & Segregation-of-Duties Model

## Document Control

| Field | Value |
|---|---|
| Document ID | SEC-ENTITLEMENT-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-07 Security Architect AI |
| Approver | H-03 CISO (H-05 Head of Compliance for MNPI sections) |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | reconciled_agent_role_registry.md, audit_event_taxonomy.md, canonical_data_model_standard.md, model_governance_independence_policy.md, foundational_adrs.md (AD-007, AD-008) |
| Supported Build Rules | BR-7, BR-10, BR-11, BR-15, BR-16 |

## 1. Purpose

Define the entitlement (RBAC + ABAC) model, the segregation-of-duties matrix, maker-checker controls, data classification
(including MNPI handling), and export controls. This makes "no module may bypass the entitlement model" (BR-11) and the
human-approval gates (BR-15) enforceable.

## 2. Principles (ENT-P)

| ID | Principle |
|---|---|
| ENT-P-01 | **Deny by default**; access is granted explicitly and is least-privilege. |
| ENT-P-02 | Entitlement checks occur at the API/gateway and again at the data-access layer (defense in depth). |
| ENT-P-03 | Subjects include humans, service accounts, and **AI agents** — all entitled and tiered (registry §2). |
| ENT-P-04 | Every entitlement change is maker-checked and audited (`ENTITLEMENT.*`). |
| ENT-P-05 | Secrets are externalized and never in source (BR-10); access to secrets is Tier-5, human-initiated. |
| ENT-P-06 | Tenancy (`tenant_id`) and portfolio scope are mandatory attributes on every entitled query (AD-008). |

## 3. Model Components

- **Permission (`PERM-*`):** an action on a resource type (e.g., `PERM-OVERRIDE-CREATE` on governed values).
- **Role (`ROLE-*`):** a named bundle of permissions aligned to a business function.
- **Scope (`SCOPE-*`):** ABAC attributes constraining a grant (tenant, portfolio/fund/strategy, asset class, data class).
- **Grant (`entitlement_grant`):** binds subject → role → scope, with validity dates and approver.

## 4. Business Roles (initial)

| Role ID | Role | Line | Indicative permissions |
|---|---|---|---|
| ROLE-PM | Portfolio Manager | 1L | View positions/risk in scope; request scenarios; respond to breaches |
| ROLE-RA | Risk Analyst | 1L | Run calcs, define scenarios (draft), view risk in scope; **register models/versions** (`model.inventory.register`, P1A-2 — 1L developer/owner, the maker side of the future SOD-03; the 2L validator deliberately does not hold register, MG-04) |
| ROLE-RM | Risk Manager | 2L | Review breaches, approve 2L steps, define/approve limits |
| ROLE-MV | Model Validator | 2L (independent) | View models/methodologies, record validation; cannot author methodology |
| ROLE-DS | Data Steward | — | Manage DQ exceptions, approve overrides within remit; **register/manage data sources** (`lineage.source.manage`, P1A-1); **manage data-quality rules** (`dq.rule.manage`, P1A-3 — held by P-DS + platform_admin only, the maker side of the future REQ-DQR-003 override SoD; read roles hold only `dq.result.view`) |
| ROLE-CO | Compliance Officer | 2L | MNPI/restricted-list administration, compliance positions |
| ROLE-ADM | Administrator | — | User/role admin; **cannot** approve own entitlement requests or edit audit |
| ROLE-AUD | Auditor / Internal Audit | 3L | Read-only across controls and audit; no operational actions |
| ROLE-RC | Report Consumer | — | View/export approved reports in scope |
| ROLE-SVC | Service Account | — | Scoped machine access (integration jobs) |
| ROLE-AGENT | AI Agent Principal | — | Tiered (registry §2); cannot hold approval permissions reserved to humans (BR-15) |

## 5. Permission Taxonomy (resource × action)

Resource types map to canonical entities/contexts; actions include: `view`, `create`, `edit`, `approve`, `reject`,
`override`, `run_calc`, `define_limit`, `change_limit`, `close_breach`, `validate_model`, `approve_model`, `manage_entitlement`,
`export`, `deploy`, `admin`. Each (resource, action) is a `PERM-*` and is checked per ENT-P-02.

### 5A. Reference-data permissions (P1B Security Master & Reference Data — ratified P1B-0/OD-P1B-F)

Required `reference.<entity>.<verb>` permissions with **view/edit separation** (a viewer cannot mutate). These are
governance-level definitions; the entitlement bootstrap **code** is updated in the relevant P1B build slice (not here),
deny-by-default, least-privilege (data_steward edit; broader view), with **no role-template change beyond additive grants**.

| Entity | Permissions | Status in catalog (`bootstrap.py`) |
|---|---|---|
| currency | `reference.currency.view`, `reference.currency.edit` | **new** (P1B-1) |
| calendar | `reference.calendar.view`, `reference.calendar.edit` | `.edit` exists; **add `.view`** (P1B-1) |
| rating_scale | `reference.rating_scale.view`, `reference.rating_scale.edit` | **new** (P1B-1) |
| legal_entity | `reference.legal_entity.view`, `reference.legal_entity.edit` | **new** (P1B-2) |
| issuer | `reference.issuer.view`, `reference.issuer.edit` | exists |
| counterparty | `reference.counterparty.view`, `reference.counterparty.edit` | exists |
| instrument | `reference.instrument.view`, `reference.instrument.edit` | exists |
| identifier_xref | `reference.identifier.resolve` (read/lookup) | exists |
| corporate_action | `reference.corporate_action.view`, `reference.corporate_action.edit` | `.edit` exists; **add `.view`** (P1B-4) |

**Reserved (not minted now):** `reference.rating.*` — held for the future **FR rating-assignment** domain (distinct from the
EV `rating_scale` taxonomy), so the verb namespace does not collide when rating assignments land in a later phase.

## 6. Segregation-of-Duties Matrix (SOD)

Incompatible duties — the same subject must not hold both sides of a pair within the same scope.

| SOD ID | Duty A | Duty B (incompatible) | Rationale |
|---|---|---|---|
| SOD-01 | Create override | Approve that override | Maker-checker (BR-7) |
| SOD-02 | 1L breach response (own breach) | Approve breach closure | 1L/2L independence |
| SOD-03 | Author model methodology (ROLE author) | Validate/approve that model | Effective challenge (model gov) |
| SOD-04 | Request entitlement | Approve entitlement | Access-control integrity |
| SOD-05 | Define/change a limit | Approve that limit change | Limit-framework integrity |
| SOD-06 | Deploy to production | Approve the deployment | Change-management integrity |
| SOD-07 | Administer users/roles | Edit/delete audit records | Audit independence (also AUD-01) |
| SOD-08 | Generate a report | Approve/publish a board report | Reporting integrity |

AI agents are treated as the "maker" side only; the "approver/checker" side of every SOD pair is a human role (BR-15).

## 7. Maker-Checker / Four-Eyes Controls

Four-eyes is mandatory for: overrides (SOD-01), limit changes (SOD-05), model approval (SOD-03), entitlement changes (SOD-04),
report publication (SOD-08), production deployment (SOD-06). Each produces an approval record referenced by `approval_ref` in
the audit event (audit_event_taxonomy.md §5/§6).

## 8. Data Classification (DC)

| DC ID | Level | Examples | Handling |
|---|---|---|---|
| DC-1 | Public | Public market prices, benchmarks | Standard controls |
| DC-2 | Internal | Internal risk results, configs | Entitled access |
| DC-3 | Confidential | Client portfolios, positions | Strict entitlement + scope; masked in logs |
| DC-4 | Restricted / MNPI | Private company financials, GP-confidential data | Information barriers, need-to-know, restricted lists, no plaintext in audit, export-blocked by default |

Every field carries a DC tag (DM-N-07). Logs and audit `before/after` for DC-3/DC-4 use references/hashes, not plaintext.

## 9. MNPI & Information Barriers

| ID | Rule |
|---|---|
| MNPI-01 | Private company financials and GP-confidential data (DC-4) are gated by information barriers; access requires explicit need-to-know grant approved by ROLE-CO/H-05. |
| MNPI-02 | Restricted lists are maintained by Compliance; entitlement enforces barrier scopes. |
| MNPI-03 | Cross-barrier access attempts are denied and audited (`AUTH.DENIED`, `EXPORT.DENIED`). |

## 10. Export Controls

| ID | Rule |
|---|---|
| EXP-01 | Data export is a distinct permission, entitlement- and classification-checked; DC-4 export blocked by default. |
| EXP-02 | Every export emits `EXPORT.DATA` (or `EXPORT.DENIED`) with classification and scope. |
| EXP-03 | Bulk/admin export requires four-eyes approval. |

## 11. Open Decisions

| ID | Open Decision |
|---|---|
| OD-024 | Confirm IdP/SSO integration specifics and MFA policy (AD-007). |
| OD-025 | Confirm portfolio-scope granularity for ABAC (position-level vs portfolio-level). |
| OD-026 | Confirm whether team holds multiple human roles and how SoD pairs are preserved at small scale (links OD-001). |
| OD-027 | Confirm MNPI barrier model and restricted-list source of truth with H-05. |

## 12. Dependencies

- reconciled_agent_role_registry.md (subjects, tiers, human approvers).
- audit_event_taxonomy.md (`ENTITLEMENT.*`, `EXPORT.*`, `approval_ref`).
- canonical_data_model_standard.md (ENT-043/044, DC tags).
- model_governance_independence_policy.md (SOD-03 author/validator).
- AD-007 (auth), AD-008 (tenancy).
