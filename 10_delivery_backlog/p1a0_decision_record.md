# Phase P1A-0 Decision Record

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1A0DR-001 |
| Version | 1.0 (Accepted) |
| Status | Accepted |
| Owner | H-06 Engineering Lead |
| Approver | H-06 Engineering Lead (H-03 CISO for OQ-P1A-0-1/-3; H-04 Data Owner consulted) |
| Created | 2026-06-19 |
| Last Reviewed | 2026-06-19 |
| Related Documents | p1a_implementation_plan.md, p1_decision_record.md, ../02_requirements/requirements_traceability_matrix.md, ../03_architecture/foundation_slice.md, ../06_security/entitlement_sod_model.md, ../11_decision_log/architecture_decision_log.md, ../04_data_model/audit_event_taxonomy.md, ../03_architecture/foundational_adrs.md (AD-007, AD-008) |
| Supported Build Rules | BR-10, BR-11, BR-12, BR-16, BR-17 |

## 1. Purpose

Record the four decisions that unblock **P1A-0 (per-session tenant-context wiring for PostgreSQL RLS)**, identified in
[p1a_implementation_plan.md](p1a_implementation_plan.md) §11. These are accepted and binding for P1A-0 implementation. Two are
architecturally significant and are elevated to the decision log as **AD-015** and **AD-016**; the other two are scoping/security
decisions recorded here. No application code is produced or changed.

## 2. Decisions

### DR-P1A0-1 — OQ-P1A-0-1 Cross-tenant ops mechanism → **Accepted (elevated to AD-015)**
**Decision.** Use a **dedicated `BYPASSRLS` ops database role** for controlled cross-tenant operational tasks only. This role may
be used for audit-chain verification, checkpointing, migration verification, and administrative diagnostics. **Normal application
request paths must not use the `BYPASSRLS` role** — normal HTTP/API and worker *business* paths must run under tenant-scoped
context using `app.current_tenant`. BYPASSRLS credentials must be **separate from application credentials**, treated as
**privileged secrets**, and their **usage must be audited**.

**Rationale.** FORCE row-level security (P0.5) applies even to the table owner, so cross-tenant ops (e.g., `verify_all_chains`
over every tenant's audit chain) genuinely require a role that bypasses RLS. Isolating that capability to a separate, audited,
privileged role — never used by the app — preserves tenant isolation (BR-17) while enabling necessary platform operations.

**Implications.** A P1A-0 migration creates the role (`CREATE ROLE … BYPASSRLS`) with explicit grants (`SELECT` on
`audit_event`; `SELECT, INSERT` on `audit_checkpoint`); the audit-verify CLI connects via a **distinct ops `DATABASE_URL`**; the
app DB role is never granted BYPASSRLS; ops-role usage is logged (BR-16/audit). Credential separation is a secrets-management
requirement (BR-10). **Corollary (deployment): the application DB role must be non-superuser and non-BYPASSRLS** — PostgreSQL
superusers/BYPASSRLS roles bypass RLS entirely (even under `FORCE`), so RLS only protects when the app connects as a constrained
role. The RLS tests run under such a constrained role (`irp_app`), not the superuser.

**Status:** Accepted → see **AD-015**.

### DR-P1A0-2 — OQ-P1A-0-2 Tenant-context scope → **Accepted (elevated to AD-016)**
**Decision.** Use `set_config('app.current_tenant', <tenant_id>, true)` for **transaction-local** tenant context. Add an
**explicit pool check-in / reset handler that clears `app.current_tenant`** (`RESET app.current_tenant`) to protect against
connection reuse or unexpected transaction behavior. Tests must prove: (a) tenant context is available within the transaction;
(b) tenant context clears after transaction end; (c) pooled/recycled connections do not retain prior tenant context;
(d) missing tenant context fails closed; (e) tenant mismatch is denied.

**Rationale.** Transaction-local context auto-clears at COMMIT/ROLLBACK, so a connection returned to the pool after a normal
transaction carries no stale tenant — eliminating the primary cross-tenant leak vector. The explicit `RESET` is defense-in-depth
for any code path that mistakenly sets session-scoped context or sets it outside a transaction (SQLAlchemy's default
rollback-on-return does not clear session-level GUCs). This is the canonical end-to-end RLS enforcement mechanism for every
DB-backed request, worker, and CLI.

**Implications.** A `tenant_context()` helper in `irp_shared.db`; the backend `get_tenant_session` dependency sets context via
`set_config`, which **autobegins** the transaction (no explicit BEGIN); the pool check-in listener issues an explicit
`RESET app.current_tenant` **and commits it** so the reset is durable. The proofs above become PG-gated tests run under a
**non-superuser app role** in the CI `migration` job. Missing context yields fail-closed false-deny (availability), not a leak.
A mid-request COMMIT/ROLLBACK drops the transaction-local context (single-transaction request invariant; AD-016 revisit).

**Status:** Accepted → see **AD-016**.

### DR-P1A0-3 — OQ-P1A-0-3 Dev-shim tenant until SSO → **Accepted (scoping/security; covered by AD-007)**
**Decision.** Accept the existing development principal/header shim (`X-User-Id` / `X-Tenant-Id`) until real SSO is implemented in
**P9**. The dev shim is for **local/dev/test only and is not a production security boundary**. **Production deployment must use
OIDC/SAML-based identity and verified tenant claims** before external users or client data are permitted.

**Rationale.** Building SSO now would block P1A; the unverified shim is sufficient to develop and test entitlement + RLS logic
(both remain defense-in-depth regardless of how the tenant is asserted). The production gate makes the security boundary
explicit. This refines, and is covered by, **AD-007** (OIDC/SAML SSO + MFA); no new ADR.

**Implications.** P1A-0 documents the shim as non-production; a production-readiness gate requires verified tenant claims (AD-007)
before any external user / client data. The entitlement `tenant_id` guard + RLS keep the unverified tenant from escalating across
tenants in dev.

**Cutover (SSO-1, 2026-07-21).** The production gate is now enforced in code: `auth_mode` defaults
to `oidc` (verified Bearer JWT → `app_user` resolution), and the `X-User-Id`/`X-Tenant-Id` shim is
permitted **only when `app_env == "local"`** — a fail-closed startup guard (`validate_auth_config`)
raises otherwise, so the unverified shim **cannot** run in a deployed environment. The "P9" horizon
in the original decision was pulled forward to Wave-9 (the UI-is-core premise made real identity the
gate before any non-developer sees the product). Enforcement behind the shim (entitlement + FORCE
RLS) was unchanged — SSO-1 only changed how the `Principal` is minted.

**Status:** Accepted (scoping/security; no new ADR — see AD-007). **Production cutover realized at SSO-1.**

### DR-P1A0-4 — OQ-P1A-0-4 RLS-denied access logging → **Accepted (scoping)**
**Decision.** **Defer** explicit `AUTH.DENIED` audit logging for database-level RLS denials. P1A-0 must **preserve an
error-handling hook** so RLS-denied access can later be mapped to `AUTH.DENIED` or `SECURITY.RLS_DENIED` without redesign.
**Application-layer entitlement denials remain the primary auditable denial event** until the security-event taxonomy is
expanded.

**Rationale.** DB-level RLS denials mostly manifest as empty result sets (fail-closed reads) rather than discrete errors, so a
clean `AUTH.DENIED` mapping needs a small taxonomy extension that is premature now. Preserving a hook avoids a later redesign
(ARCH-P-07). Application-layer entitlement denials (the meaningful, attributable denials) are already auditable.

**Implications.** P1A-0 routes RLS-denial-relevant error handling through a single seam; the audit taxonomy gains
`SECURITY.RLS_DENIED` / `AUTH.DENIED` mapping in a later step (tracked as OQ-P1A-0-4a). No new ADR.

**Status:** Accepted (scoping).

## 3. Open questions closed by this record

| OQ | Resolution | Where reflected |
|---|---|---|
| OQ-P1A-0-1 | Dedicated `BYPASSRLS` ops role; app never uses it; separate audited privileged credentials | AD-015, p1a_implementation_plan §3/§11 |
| OQ-P1A-0-2 | `set_config(..., is_local=true)` transaction-local + explicit pool `RESET`; five proofs as tests | AD-016, p1a_implementation_plan §3/§11 |
| OQ-P1A-0-3 | Accept unverified dev-shim until SSO (P9); production requires verified tenant claims | this record (AD-007), p1a_implementation_plan §3/§11 |
| OQ-P1A-0-4 | Defer `AUTH.DENIED` for RLS denials; preserve mapping hook | this record, p1a_implementation_plan §11 |

## 4. Remaining open questions

**None block P1A-0.** All four P1A-0 decisions are resolved. New follow-up tracked: **OQ-P1A-0-4a** — add
`SECURITY.RLS_DENIED` / `AUTH.DENIED` to the audit taxonomy (later step). Sub-slice questions OQ-P1A-1-x … OQ-P1A-4-x remain open
and are needed before *those* sub-slices, not before P1A-0.

## 5. Dependencies

This record depends on the P0.5 foundation (FORCE RLS, `set_config` mechanism, `FW-AUD`/`FW-ENT`), the P1A implementation plan,
AD-007 (auth), AD-008 (tenancy), and the entitlement/audit standards. It modifies no code and starts no implementation.
