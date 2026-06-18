# Agent Operating Model

## Purpose

This document defines how AI agents will be used as part of the build, validation, operation, and continuous improvement of the enterprise investment risk platform.

The objective is to use AI wherever appropriate while maintaining enterprise-grade quality, auditability, security, reproducibility, and human accountability for areas requiring independent judgment or formal sign-off.

## Agent Usage Layers

## 1. Build-Time Agents

Build-time agents assist with software delivery, architecture, analytics, testing, documentation, and control design.

Examples:
- Product Manager Agent
- Chief Architect Agent
- Backend Engineering Agent
- Frontend Engineering Agent
- Data Architect Agent
- Quant/Risk Methodology Agent
- Security Review Agent
- Model Governance Agent
- QA/Test Agent
- Documentation Agent
- Compliance and Controls Agent

## 2. BAU Product Operations Agents

BAU agents assist with ongoing operation of the platform once the product is running.

Examples:
- Data Quality Monitoring Agent
- Data Lineage Review Agent
- Model Performance Monitoring Agent
- Limit Breach Triage Agent
- Scenario Commentary Agent
- Report Drafting Agent
- Release Readiness Agent
- Security Monitoring Support Agent
- User Support Agent
- Evidence Pack Maintenance Agent

## 3. Embedded Product Agents

Embedded product agents are capabilities inside the platform that assist end users.

Examples:
- Risk Commentary Assistant
- Data Quality Explanation Assistant
- Model Limitation Explanation Assistant
- Breach Triage Assistant
- Scenario Design Assistant
- Board Reporting Assistant
- Private Asset Data Review Assistant
- Control Evidence Assistant

## Agent Design Principles

1. Agents may assist, draft, review, test, and summarize.
2. Agents may not silently approve material risk, model, security, or compliance decisions.
3. Agent outputs must be traceable to source data, code, documents, or explicit assumptions.
4. Agent recommendations must distinguish facts, assumptions, and judgments.
5. Agent-generated changes must pass automated tests before acceptance.
6. Agents must operate under defined permissions.
7. Agents must not access secrets unless explicitly required and controlled.
8. Agents must not bypass audit logging.
9. Agents must not bypass entitlement rules.
10. Agents must document limitations and uncertainty.

## Human Review Philosophy

The goal is to minimize human dependency, not eliminate accountable review entirely.

AI should prepare:
- Analysis
- Drafts
- Test cases
- Evidence packs
- Methodology documentation
- Security checklists
- Validation support materials
- Control mappings
- Release readiness reports

Humans should be used selectively for:
- Independent model validation
- Security assessment
- Legal review
- Enterprise buyer review
- Commercial decisions
- Final accountability where required