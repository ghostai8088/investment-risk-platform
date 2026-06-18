# Initial Threat Model (First Pass)

## Document Control

| Field | Value |
|---|---|
| Document ID | SEC-THREATMODEL-001 |
| Version | 0.1 (First Pass) |
| Status | Accepted as first-pass baseline (to mature per surface during build) |
| Owner | R-07 Security Architect AI |
| Approver | H-03 CISO |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | entitlement_sod_model.md, audit_event_taxonomy.md, architecture_baseline.md, foundational_adrs.md, control_matrix_skeleton.md |
| Supported Build Rules | BR-5, BR-7, BR-10, BR-11, BR-12, BR-15, BR-16 |

## 1. Purpose & Method

First-pass threat model over the security-relevant surfaces, using a STRIDE lens (Spoofing, Tampering, Repudiation,
Information disclosure, Denial of service, Elevation of privilege). Each threat is timed as:

- **pre-code** — design decision/standard already in place; verify before building.
- **foundation-build** — must be implemented as part of the cross-cutting foundation.
- **later-hardening** — production-hardening, scheduled before the relevant surface goes to production but not blocking first build.

This is a living document; each bounded context extends it when built.

## 2. Threat Register

| ID | Surface | Threat (STRIDE) | Risk | Impacted capability / BC | Likely control | Timing |
|---|---|---|---|---|---|---|
| THR-01 | Authentication | Credential theft / weak auth / no MFA (S) | High | BC-15 Security | OIDC/SAML SSO + enforced MFA (AD-007); short-lived tokens | foundation-build |
| THR-02 | Authentication | Session hijacking / token replay (S/T) | High | BC-15 | Short-lived signed tokens, rotation, TLS-only, audience binding | foundation-build |
| THR-03 | Authorization | Broken access control / IDOR / privilege escalation (E/I) | High | All BCs | Deny-by-default; checks at API + data layer (ENT-P-02); SoD | pre-code + foundation-build |
| THR-04 | Authorization | Cross-tenant data access (I/E) | High | All (multi-tenant) | tenant_id scoping + row-level security; tenant tests (BR-17) | foundation-build |
| THR-05 | File upload | Malicious file / malware / oversized (T/DoS) | High | BC-16 Integration | Type/size validation, sandboxed parsing, AV scan, quarantine | foundation-build + later-hardening (AV) |
| THR-06 | File upload | CSV/Excel formula injection, path traversal (T) | Medium | BC-16 | No formula execution, safe parsers, filename sanitization, ACL | foundation-build |
| THR-07 | Data ingestion | Poisoned / malformed / schema-drift data (T) | Medium | BC-12 DQ, BC-16 | Anti-corruption layer, DQ rules, reconciliation, lineage (CTRL-027/028) | foundation-build |
| THR-08 | Data ingestion | Injection via mapped fields (T/E) | Medium | BC-16 | Parameterized access, input validation, canonical mapping | foundation-build |
| THR-09 | Manual overrides | Unauthorized / unjustified override (E/R) | High | BC-12 | Maker-checker (SOD-01), BR-7 fields, audit `OVERRIDE.*` | pre-code (policy) + foundation-build |
| THR-10 | Manual overrides | Repudiation of who changed a value (R) | Medium | BC-12/13 | Immutable override record + hash-chained audit | foundation-build |
| THR-11 | Audit events | Tampering / deletion of audit records (T/R) | High | BC-13 Audit | Segregated append-only store + hash chain (AUD-01/02); fail-closed (AUD-04) | foundation-build |
| THR-12 | Audit events | Audit admin acting outside SoD (E) | Medium | BC-13/15 | SOD-07 (admin ≠ audit edit); RLS on audit store | foundation-build |
| THR-13 | AI agent actions | Agent over-reach / unauthorized change (E) | High | All | Tiered access (registry §2); BR-15 human gates; deny-by-default | pre-code + foundation-build |
| THR-14 | AI agent actions | Prompt injection / data exfiltration (I/T) | High | Embedded agents | Input/output filtering, entitlement-scoped context, no secrets, output citation | foundation-build + later-hardening |
| THR-15 | AI agent actions | Hallucinated/invented numbers in commentary (I) | Medium | Reporting/Embedded | Must cite governed sources; no free-form numbers; human review (AD-009) | pre-code + foundation-build |
| THR-16 | AI agent actions | Unlogged agent action (R) | Medium | All | `AGENT.*` logging mandatory (BR-16); cannot suppress audit | foundation-build |
| THR-17 | Data export | Exfiltration of confidential / DC-4 MNPI (I) | High | BC-14/15 | Export permission + classification check; DC-4 blocked by default (EXP-01) | foundation-build |
| THR-18 | Data export | Bulk export abuse (I/DoS) | Medium | BC-14/15 | Four-eyes for bulk export; rate limits; `EXPORT.*` audit | foundation-build + later-hardening |
| THR-19 | Model/scenario assumption changes | Unauthorized change to assumptions skewing results (T/E) | High | BC-09/11 | Versioned assumptions (BR-8); SOD-03 maker-checker; audit | foundation-build |
| THR-20 | Model/scenario assumption changes | Untracked change → non-reproducible result (R) | High | BC-05–09/11 | Run binds assumption version (TR-12); immutable history | foundation-build |
| THR-21 | Report generation | Report exposes out-of-scope data (I) | High | BC-14 | Entitlement-scoped data access; classification on render/export | foundation-build |
| THR-22 | Report generation | Falsified / non-reproducible report (T/R) | High | BC-14 | Reproducibility binding (BR-9, TR-16); publish maker-checker (SOD-08) | foundation-build |
| THR-23 | Secrets / config | Secret leakage in source or logs (I) | High | BC-15 / DevOps | No secrets in source (BR-10); secret-scan hook; masked logs (DC-3/4) | pre-code + foundation-build |

## 3. Cross-Cutting Notes

- The four non-bypassable frameworks (entitlement, audit, lineage, calculation-run) are the primary mitigations for the majority
  of high-risk threats; building them first reduces residual risk across all later modules.
- Later-hardening items (AV scanning, advanced prompt-injection defense, rate limiting, WORM audit storage) must be scheduled
  before the relevant surface reaches production, tracked in the control matrix.

## 4. Open Decisions

| ID | Open Decision |
|---|---|
| OD-042 | Select AV/malware-scanning approach for uploads (THR-05). |
| OD-043 | Define prompt-injection / output-filtering controls for embedded agents (THR-14). |
| OD-044 | Define rate-limiting and bulk-export thresholds (THR-18). |
| OD-045 | Confirm DC-3/DC-4 log-masking implementation approach (THR-23). |

## 5. Dependencies

- entitlement_sod_model.md (SoD, classification, export controls).
- audit_event_taxonomy.md (hash-chain, fail-closed, `AGENT.*`/`OVERRIDE.*`/`EXPORT.*`).
- foundational_adrs.md (AD-007 auth, AD-008 tenancy, AD-009 AI boundary).
- control_matrix_skeleton.md (control timing/evidence).
