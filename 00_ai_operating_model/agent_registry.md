# Agent Registry

> **Superseded for authority by [reconciled_agent_role_registry.md](reconciled_agent_role_registry.md).** That registry is the
> single source of truth (with stable agent IDs AG-01 … AG-28, role IDs, tool-access tiers, and human approvers). This table is
> retained as a working summary and must not diverge from the reconciled registry. New engineering, DevOps, documentation, and
> release agents are included below for continuity.

| Agent Name | Category | Purpose | Primary Inputs | Primary Outputs | Tool Access | Human Review Required? |
|---|---|---|---|---|---|---|
| Product Manager Agent | Build-Time | Convert requirements into user stories and acceptance criteria | Requirements, capability map | User stories, backlog | Read/write docs | Yes, for scope decisions |
| Chief Architect Agent | Build-Time | Review architecture and service boundaries | Architecture docs, codebase | Architecture recommendations | Read/write docs and code | Yes, for major decisions |
| Backend Engineering Agent | Build-Time | Implement domain services, APIs, persistence | Specs, architecture baseline | Service/API code | Read/write code+tests (T2) | Yes, H-06 to merge |
| Frontend Engineering Agent | Build-Time | Implement 1L/2L dashboards and workflow UI | Designs, specs | UI code | Read/write code+tests (T2) | Yes, H-06 to merge |
| Documentation Agent | Build-Time | Maintain methodology, API, data, user, governance docs | Code/doc changes | Updated docs | Read/write docs (T1) | No (advisory) |
| DevOps/SRE Agent | Build-Time/BAU | CI/CD, environments, observability, hooks | Repo, pipeline config | Pipelines, IaC, monitoring | Read/write code (T2); T5 human-initiated | Yes, H-06/H-10 for prod |
| Release Readiness Agent | Build-Time/BAU | Assemble release evidence, go/no-go | Tests, scans, migrations | Readiness checklist | Read-only (T3) | Yes, H-10 go/no-go |
| Quant/Risk Methodology Agent | Build-Time | Draft and review risk methodologies | Calculation specs, test portfolios | Methodology docs, test cases | Read/write analytics docs/code | Yes, for model sign-off |
| Data Architect Agent | Build-Time | Design data model, dictionary, lineage | Requirements, schema | Data model, dictionary | Read/write schema/docs | Yes, for core model changes |
| Security Review Agent | Build-Time / BAU | Review security design and findings | Code, config, logs | Security findings | Read-only preferred | Yes, for critical findings |
| QA/Test Agent | Build-Time | Generate and run tests | Code, requirements | Test cases, defects | Read/write tests | No, unless release critical |
| Model Governance Agent | Build-Time / BAU | Maintain model inventory and validation artifacts | Model specs, results | Inventory, validation docs | Read/write docs | Yes, for approvals |
| Data Quality Agent | BAU | Review data quality results and exceptions | DQ results, reconciliations | Exception summaries | Read-only data | Yes, for material issues |
| Breach Triage Agent | BAU | Analyze limit breaches and draft narratives | Breach data, risk results | Breach summaries | Read-only risk data | Yes, for closure |
| Board Reporting Agent | BAU / Embedded | Draft risk commentary | Approved metrics, reports | Draft board narrative | Read-only approved outputs | Yes, before publication |
| Scenario Design Agent | Embedded | Help users design stress scenarios | Scenario library, portfolio data | Scenario drafts | Controlled app access | Yes, before official use |
| User Support Agent | BAU / Embedded | Explain platform functions and metrics | Documentation, user query | Help responses | Read-only docs | No, unless advisory |