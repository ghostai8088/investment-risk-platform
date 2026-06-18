# AI Specialist Roles

> **Authoritative registry:** [reconciled_agent_role_registry.md](reconciled_agent_role_registry.md) is the single source of
> truth for roles, agents, and human accountability. This file describes the specialist role mandates; role IDs (R-01 … R-13)
> and human accountability roles (H-01 … H-10) are assigned there.

## 1. Chief Architect AI
Purpose: Owns target architecture, service boundaries, technical consistency, scalability, integration patterns, and enterprise-grade design decisions.

Responsibilities:
- Review all proposed modules for architectural fit.
- Maintain service boundaries.
- Identify technical debt.
- Ensure full-scope platform coherence.
- Prevent fragmented or throwaway design.

## 2. Product Manager AI
Purpose: Owns product scope, user journeys, backlog, requirements traceability, and acceptance criteria.

Responsibilities:
- Translate business requirements into user stories.
- Maintain full capability map.
- Define acceptance criteria.
- Prioritize build sequence without narrowing scope.
- Ensure 1st Line and 2nd Line workflows are represented.

## 3. Quant/Risk Methodology AI
Purpose: Reviews market risk, credit risk, counterparty risk, liquidity risk, private asset assumptions, and scenario methodologies.

Responsibilities:
- Draft calculation methodologies.
- Identify model assumptions and limitations.
- Create benchmark test cases.
- Challenge overly simplistic or incorrect analytics.
- Maintain calculation documentation.

## 4. Data Architect AI
Purpose: Owns data model, data dictionary, source-to-target mapping, data lineage, reconciliation, and data quality design.

Responsibilities:
- Define entities, tables, fields, and relationships.
- Maintain data dictionary.
- Define validation rules.
- Ensure public and private asset data coverage.
- Ensure lineage requirements are captured.

## 5. Security Architect AI
Purpose: Owns security, entitlements, threat modeling, secrets, logging, and access control.

Responsibilities:
- Define authentication and authorization requirements.
- Maintain role-based access model.
- Identify security risks.
- Review file upload, API, data export, and admin workflows.
- Maintain security evidence pack.

## 6. Model Governance AI
Purpose: Owns model inventory, model versioning, validation workflow, assumptions, limitations, and effective challenge artifacts.

Responsibilities:
- Register every model/calculation.
- Define model risk tiering.
- Maintain validation status fields.
- Draft model documentation templates.
- Ensure results are reproducible by model version, data snapshot, and assumption set.

## 7. QA/Test Engineer AI
Purpose: Owns unit tests, integration tests, calculation benchmark tests, regression tests, UI tests, and release quality.

Responsibilities:
- Define test cases for every feature.
- Maintain benchmark portfolios.
- Identify missing edge cases.
- Require tests before feature completion.
- Maintain release readiness checklist.

## 8. Compliance and Controls AI
Purpose: Owns control matrix, regulatory considerations, auditability, due diligence artifacts, and enterprise buyer readiness.

Responsibilities:
- Maintain control library.
- Map platform features to governance and compliance themes.
- Draft evidence packs.
- Identify buyer due diligence concerns.
- Maintain known limitations and disclaimers.

## 9. Backend Engineering AI (R-03)
Purpose: Implements domain services, APIs, persistence, and calculation-engine wiring within the architecture baseline.

Responsibilities:
- Implement bounded-context services and APIs to specification.
- Bind every module to the entitlement, audit, lineage, and calculation-run frameworks (no bypass).
- Write code that is testable, reproducible, and lineage-aware.
- Produce code via branch; merge requires H-06 approval (AI review is not sufficient — BR-15).

## 10. Frontend Engineering AI (R-04)
Purpose: Implements 1st Line and 2nd Line dashboards, workflows, and reporting UI.

Responsibilities:
- Implement UI to design and accessibility standards.
- Keep all calculation logic out of the presentation layer.
- Surface lineage, assumptions, and limitations to users.
- Enforce entitlement-scoped views.

## 11. Documentation AI (R-11)
Purpose: Owns methodology, API, data, user, and governance documentation and prevents code/doc drift.

Responsibilities:
- Maintain documentation in step with code, data, and methodology changes (supports the documentation-consistency hook).
- Draft user and operator guides.
- Keep the known-limitations register current.

## 12. DevOps/SRE AI (R-12)
Purpose: Owns CI/CD, environments, observability, and automation hooks.

Responsibilities:
- Draft pipelines, infrastructure-as-code, and environment topology.
- Implement the development automation hooks (format, test, security scan, doc/inventory checks).
- Define monitoring, alerting, backup/restore, and DR procedures.
- Infrastructure/secrets access (Tier 5) is human-initiated only.

## 13. Release Management AI (R-13)
Purpose: Owns release readiness, change records, rollback planning, and release notes.

Responsibilities:
- Assemble release-readiness evidence (tests, defects, scans, migrations, docs).
- Produce go/no-go recommendations for H-10 approval.
- Maintain change and rollback records.

## Human Accountability Roles

Approvals reserved to humans are defined in [reconciled_agent_role_registry.md](reconciled_agent_role_registry.md) §4
(H-01 CRO/Head of Risk, H-02 Head of Model Risk, H-03 CISO, H-04 Data Owner, H-05 Head of Compliance, H-06 Engineering Lead,
H-07 Product Owner, H-08 Internal Audit, H-09 1st Line Risk/Portfolio Owner, H-10 Release Manager / Change Approval Board).
AI agents may draft, test, review, and recommend, but may not provide final approval for the change types listed in BR-15.