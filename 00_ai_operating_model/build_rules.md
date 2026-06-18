# Non-Negotiable Build Rules

This product is not an MVP or proof of concept. It is a full-scope enterprise product built in sequenced layers.

> **Rule identifiers.** The numbered rules below are referenced elsewhere as `BR-1` … `BR-16` (e.g., the control matrix and
> baseline standards cite the rules they enforce). The numbering is stable; do not renumber existing rules when adding new ones.

## General Rules

1. No feature is complete without tests.
2. No calculation is complete without methodology documentation.
3. No model is complete without a model inventory entry.
4. No data field is complete without a data dictionary definition.
5. No user action that changes data, assumptions, models, limits, scenarios, or reports is complete without audit logging.
6. No risk result is complete unless it can be traced to:
   - Source data
   - Data validation checks
   - Model/calculation version
   - Assumptions
   - Scenario, if applicable
   - Calculation run ID
   - Timestamp
   - User or system initiator
7. No manual override is allowed without:
   - User ID
   - Timestamp
   - Justification
   - Prior value
   - New value
   - Approval status
8. No scenario is complete without saved assumptions and versioning.
9. No report is complete unless it is reproducible.
10. No sensitive configuration, credential, API key, or secret may be stored in source code.
11. No module may bypass the entitlement model.
12. No module may bypass the audit event framework.
13. No module may bypass the data lineage framework.
14. All limitations must be explicitly documented.
15. AI-generated code and AI analysis must be reviewed through automated tests and AI review prompts before acceptance. **AI review is necessary but not sufficient as final approval.** The following changes require documented approval by the accountable human role and may not be approved solely by AI:
    - Tier 1 model changes (approver: H-02 Head of Model Risk)
    - Security-critical changes (approver: H-03 CISO)
    - Legal or compliance positions (approver: H-05 Head of Compliance)
    - Entitlement or access-control changes (approver: H-03/H-06 per change type)
    - Audit framework changes (approver: H-06 Engineering Lead, with H-08 Internal Audit consulted)
    - Production deployment changes (approver: H-10 Release Manager / Change Approval Board)
16. All material AI agent actions must be logged to the audit framework. Each logged action must record the agent identity, the model and version used, the action taken, the inputs or justification relied upon, and the human approver where approval was required. Agent actions may not bypass the audit (BR-12), entitlement (BR-11), or lineage (BR-13) frameworks. ("Material" means any action that creates, changes, approves, or recommends a change to data, code, models, limits, scenarios, reports, entitlements, or configuration.)
17. No access to tenant-scoped data is permitted without binding the request to a tenant and an entitled scope. Cross-tenant access is prohibited and is enforced in depth (application entitlement scope and database row-level security per AD-008). Cross-tenant leakage is a critical control failure.
18. Audit events must be hash-chained and independently verifiable (AD-004, audit taxonomy §4A). A chain break or gap is an alertable security incident and a release blocker. Audit records may not be edited or deleted within retention (segregated, append-only store).
19. Every persisted entity must be assigned and conform to its temporal class — FR (full bitemporal), IA (immutable append-only), or EV (effective-dated versioned) per AD-005. FR-class risk-driving inputs must support point-in-time reproduction; IA-class outputs, events, and overrides must be immutable and append-only.

## Build Rule Alignment Note

BR-15 (human approval is required and AI is not sufficient for the listed change types) and BR-16 (material AI agent actions are
logged) remain in force and are unchanged by Step 1C. The Step 1C ratifications were themselves recorded under the BR-15 human
approval model. BR-17/18/19 implement decisions AD-008, AD-004, and AD-005 respectively.

## Design Principle

Build the full enterprise platform structure from day one. Initial analytical methods may be simple, but every capability must be structurally complete, documented, testable, auditable, and extensible.