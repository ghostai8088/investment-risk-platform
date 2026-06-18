# Reconciled Agent & Role Registry

> **Authoritative source of truth.** This registry reconciles and supersedes the role/agent lists previously held in
> [ai_specialist_roles.md](ai_specialist_roles.md), [agent_operating_model.md](agent_operating_model.md), and
> [agent_registry.md](agent_registry.md). Where any of those documents disagrees with this registry, this registry governs.

## Document Control

| Field | Value |
|---|---|
| Document ID | OPMODEL-REGISTRY-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | H-07 Product Owner (with H-06 Engineering Lead) |
| Approver | H-07 Product Owner |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | ai_specialist_roles.md, agent_registry.md, agent_operating_model.md, build_rules.md, entitlement_sod_model.md, model_governance_independence_policy.md |
| Supported Build Rules | BR-11, BR-12, BR-13, BR-15, BR-16 |

## 1. Purpose

Provide a single authoritative list of (a) AI specialist roles, (b) the concrete AI agents that perform work under those
roles, and (c) the **human accountability roles** that hold non-delegable approval authority. This eliminates the prior
inconsistency where three documents listed different roles/agents and no implementer or DevOps role existed.

## 2. Tool-Access Tiers

Every agent operates under a declared access tier (referenced by [entitlement_sod_model.md](../06_security/entitlement_sod_model.md)).
Deny-by-default applies; an agent receives the minimum tier required.

| Tier | Name | Scope |
|---|---|---|
| T0 | Read-only docs | Read repository docs only |
| T1 | Read/write docs | Read/write documentation artifacts |
| T2 | Read/write code+tests | Read/write source and tests in a branch; no merge, no deploy |
| T3 | Read-only data | Read non-production or de-identified data; never secrets |
| T4 | Controlled app/data | Scoped, entitled access to application data through the app's own entitlement layer |
| T5 | Infrastructure/secrets | Restricted; human-initiated only; never granted to autonomous agents |

## 3. AI Specialist Roles (authoritative)

| Role ID | Role | Mandate | Status |
|---|---|---|---|
| R-01 | Product Manager AI | Requirements, user stories, acceptance criteria, traceability, build sequencing | Existing |
| R-02 | Chief Architect AI | Target architecture, service boundaries, technical consistency, ADRs | Existing |
| R-03 | Backend Engineering AI | Implement domain services, APIs, calculation-engine wiring, persistence | **New** |
| R-04 | Frontend Engineering AI | Implement UI, dashboards (1L/2L), accessibility | **New** |
| R-05 | Data Architect AI | Canonical data model, dictionary, lineage, reconciliation | Existing |
| R-06 | Quant/Risk Methodology AI | Draft risk methodologies, benchmark cases, assumptions/limitations | Existing |
| R-07 | Security Architect AI | Entitlements, threat modeling, secrets, security evidence | Existing |
| R-08 | Model Governance AI | Model inventory, versioning, validation-support artifacts | Existing |
| R-09 | QA/Test Engineer AI | Unit/integration/benchmark/regression/UI tests, release-quality gates | Existing |
| R-10 | Compliance & Controls AI | Control matrix, regulatory mapping, evidence packs, limitations register | Existing |
| R-11 | Documentation AI | Methodology, API, data, user, and governance documentation; drift prevention | **New** |
| R-12 | DevOps/SRE AI | CI/CD, environments, observability, automation hooks, IaC drafting | **New** |
| R-13 | Release Management AI | Release readiness, change records, rollback planning, release notes | **New** |

## 4. Human Accountability Roles (non-delegable approvals)

AI may draft, test, review, and recommend; the approvals below are reserved to humans (see BR-15 amended).

| Human Role ID | Role | Non-delegable approval authority |
|---|---|---|
| H-01 | Chief Risk Officer / Head of Risk (2nd Line head) | Risk appetite, limit framework sign-off |
| H-02 | Head of Model Risk / Independent Model Validation | Tier-1 model approval, validation sign-off |
| H-03 | Chief Information Security Officer (CISO) | Security-critical changes, threat-model acceptance |
| H-04 | Data Owner / Head of Data Governance | Canonical data model & lineage acceptance, data quality standards |
| H-05 | Head of Compliance | Legal/compliance positions, MNPI/information-barrier rulings |
| H-06 | Engineering Lead / Tech Lead | Architecture acceptance, production deployment approval |
| H-07 | Product Owner | Scope, prioritization, acceptance of business requirements |
| H-08 | Internal Audit (3rd Line) | Independent assurance over controls (no operational approvals) |
| H-09 | 1st Line Risk / Portfolio Owner | First-line breach response, business risk ownership |
| H-10 | Release Manager / Change Approval Board | Production change approval, go/no-go |

## 5. Agent Registry (concrete agents → roles)

| Agent ID | Agent | Category | Owning Role | Tier | Human Approval Required |
|---|---|---|---|---|---|
| AG-01 | Product Manager Agent | Build-Time | R-01 | T1 | H-07 for scope |
| AG-02 | Chief Architect Agent | Build-Time | R-02 | T2 | H-06 for major decisions |
| AG-03 | Backend Engineering Agent | Build-Time | R-03 | T2 | H-06 to merge |
| AG-04 | Frontend Engineering Agent | Build-Time | R-04 | T2 | H-06 to merge |
| AG-05 | Data Architect Agent | Build-Time | R-05 | T1/T2 | H-04 for core model changes |
| AG-06 | Quant/Risk Methodology Agent | Build-Time | R-06 | T2 | H-02 for model sign-off |
| AG-07 | Security Review Agent | Build-Time/BAU | R-07 | T3 (read-only preferred) | H-03 for critical findings |
| AG-08 | QA/Test Agent | Build-Time | R-09 | T2 | H-06 if release-critical |
| AG-09 | Model Governance Agent | Build-Time/BAU | R-08 | T1 | H-02 for approvals |
| AG-10 | Documentation Agent | Build-Time | R-11 | T1 | No (advisory) |
| AG-11 | DevOps/SRE Agent | Build-Time/BAU | R-12 | T2 (T5 human-initiated only) | H-06/H-10 for prod |
| AG-12 | Release Readiness Agent | Build-Time/BAU | R-13 | T3 | H-10 go/no-go |
| AG-13 | Data Quality Monitoring Agent | BAU | R-05 | T3 | H-04 for material issues |
| AG-14 | Private Asset Data Review Agent | BAU | R-05 | T3 | H-04 for material issues |
| AG-15 | Limit Breach Triage Agent | BAU | R-01/R-06 | T3 | H-09/H-01 for closure |
| AG-16 | Scenario Commentary Agent | BAU | R-06 | T3 | H-09 before official use |
| AG-17 | Model Performance Monitoring Agent | BAU | R-08 | T3 | H-02 for review actions |
| AG-18 | Board Reporting Assistant | BAU/Embedded | R-01/R-10 | T4 (approved outputs only) | H-01 before publication |
| AG-19 | Regulatory/Due-Diligence Evidence Agent | BAU | R-10 | T3 | H-05/H-08 |
| AG-20 | Security Review Support Agent | BAU | R-07 | T3 | H-03 |
| AG-21 | Risk Commentary Assistant (embedded) | Embedded | R-06 | T4 | Advisory; no auto-approval |
| AG-22 | Data Quality Explanation Assistant (embedded) | Embedded | R-05 | T4 | Advisory |
| AG-23 | Model Limitation Explanation Assistant (embedded) | Embedded | R-08 | T4 | Advisory |
| AG-24 | Breach Triage Assistant (embedded) | Embedded | R-01 | T4 | H-09 to action |
| AG-25 | Scenario Design Assistant (embedded) | Embedded | R-06 | T4 | H-09 before official use |
| AG-26 | Private Asset Data Review Assistant (embedded) | Embedded | R-05 | T4 | H-04 to action |
| AG-27 | Control Evidence Assistant (embedded) | Embedded | R-10 | T4 | H-05/H-08 |
| AG-28 | User Support Agent | BAU/Embedded | R-11 | T0/T4 | No, unless advisory |

## 6. Independence & Segregation Constraints

- **Methodology vs validation:** R-06/AG-06 may not validate its own methodology. Independent validation is performed under
  R-08 with H-02 sign-off (see [model_governance_independence_policy.md](../07_model_governance/model_governance_independence_policy.md)).
- **Author vs approver of code:** AG-03/AG-04 produce code; merge/deploy approval is H-06/H-10. AI review (AG-07/AG-08) is
  necessary but not sufficient (BR-15).
- **Entitlement changes:** requested by an agent/user, approved by a human per SoD (no self-approval).
- **No agent** may bypass the entitlement (BR-11), audit (BR-12), or lineage (BR-13) frameworks; all material agent actions
  are logged (BR-16).

## 7. Open Decisions

| ID | Open Decision |
|---|---|
| OD-001 | Confirm whether human roles H-01..H-10 map to distinct individuals or a smaller startup team holding multiple hats (must still preserve SoD pairs). |
| OD-002 | Decide which embedded agents (AG-21..AG-28) are in-scope for the first construction phases vs deferred. |
| OD-003 | Confirm AI provider/model governance for embedded agents (data residency, PII) — links to AD-009. |

## 8. Dependencies

- [entitlement_sod_model.md](../06_security/entitlement_sod_model.md) — defines the permissions/tiers agents bind to.
- [model_governance_independence_policy.md](../07_model_governance/model_governance_independence_policy.md) — independence rules.
- [audit_event_taxonomy.md](../04_data_model/audit_event_taxonomy.md) — `AGENT.*` events for BR-16.
- AD-009 (AI-usage boundary) in [foundational_adrs.md](../03_architecture/foundational_adrs.md).
