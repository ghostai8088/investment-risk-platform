# ONBOARD-1b remit — the tenant administers itself, four-eyes from the first moment it can

**Wave 17, slice 0b.** Branch `onboard-1b-tenant-admin`. Ratified at the ONBOARD-1 gate
(2026-08-09, OQ-ONB-1…10 all as recommended) — the 1a/1b split was ratified there, so **this
needs no second gate**. Design authority: `onboard_1_decision_record.md` v3 + the ratification
stamp; where this remit and that record disagree, the record wins and the disagreement is a
FINDING.

Remits state OUTCOMES and PROOFS, not steps.

**What 1a left, precisely:** a tenant exists, is registered, has role clones, and has a first
administrator who authenticates and **manages nobody**. `tenant_admin` is a template with no
codes, carried on an exact exemption list whose stale-entry twin fires the moment codes arrive.
This slice fills it.

---

## Outcomes

1. **The tenant catalog gains four codes** (P11 + P17 + the §5C mint checklist created at 1a, all
   five rows executed or explicitly refused with reason): `user.manage` (create/deactivate),
   `role.assign` (grant/revoke), `user.view` (list users and their roles), `role.approve` (the
   four-eyes checker verb). Holders: `tenant_admin` + `platform_admin`. **`auditor_3l` is EXCLUDED
   from `user.view`** — ratified, because `app_user` carries `external_subject` and
   `display_name`, person-identifying data in the class every proprietary-identity read has
   excluded the 3L auditor from. Migration `0068` carries the literal `DELIVERS` tuple, and the
   `_DELIBERATELY_EMPTY` exemption in `test_entitlement_bootstrap.py` is **DELETED** — its
   stale-entry test is the mechanism that says so.

2. **SOD-04 is honored from the first moment it can be (OQ-ONB-9A).** Any entitlement-affecting
   act by an admin — grant, revoke, end-date, **and `user.manage` deactivation of a user who
   currently holds `tenant_admin`** — is born `PENDING` when **≥1 currently-valid OTHER admin
   exists**, and needs a second admin's approval (`role.approve`; approver ≠ requester by
   principal id, the MG-3 person-level pattern). With no other admin the act executes directly and
   is stamped `direct_grant=true` on its audit event: the bootstrap window is bounded by the admin
   count itself and every use of it is flagged evidence, not silence.

3. **ENT-075 `entitlement_request`** — IA append-only, the MG-2 pattern (DB-monotonic ordering key,
   per-item write lock, monotonic-id epoch), symmetric tenant-scoped FORCE RLS. It stores the
   pending act, its requester, its target, and its resolution. **Deactivation requests ride the
   same table** — an entitlement change is an entitlement change regardless of which verb spells
   it, which is the whole content of finding B2.

4. **The orphan-proof invariant holds across ALL FOUR paths (OQ-ONB-4A).** A tenant always has
   **≥1 currently-valid, ACTIVE-user admin** — enforced identically against role revocation, role
   END-DATING (`user_role.valid_to`; the count is over grants valid NOW), user DEACTIVATION
   including self, and **concurrently**, via a per-tenant advisory lock around the count-check so
   two admins revoking each other serialize and the second refuses.

5. **The routes exist and are census-visible**: `POST/GET /tenants/{id}/users`,
   `POST/DELETE /tenants/{id}/users/{uid}/roles`, `GET /tenants/{id}/roles`,
   `POST /entitlement-requests/{id}/approve`. Every one guarded by the ordinary
   `require_permission` (an inline check would make them invisible to the P11 census — 1a's
   recorded near-miss), and every one tenant-local: a tenant admin acts only inside their own
   tenant, never across.

6. **The Users & Roles screen (OQ-ONB-7A)** — list users and their roles, create a user, grant and
   revoke, and see PENDING requests awaiting a second admin. The FE's read path is the generated
   OpenAPI types (FE-2's contract), and the write path follows OPS-1's precedent.

7. **CTRL-025 moves Planned → Implemented on the P9 bar** (the refusal fires before the status
   moves), and **CTRL-037** — minted Planned at 1a and hosted here by name — moves with the
   orphan invariant's four paths. `entitlement_sod_model.md` §7 gains the bootstrap-window clause,
   as the ratification requires.

## Proofs

**Every refusal ships the positive control that proves the harness delivered its input (P18).**

- **Four-eyes, both branches, and the boundary between them**: with ≥1 other admin a grant is born
  PENDING and does NOT take effect ↔ the second admin's approval makes it effective; with no other
  admin the act is direct ↔ and stamped. **The threshold itself is a named test** — at exactly two
  admins four-eyes ENGAGES (the pass-2 B3 defect was a threshold that exempted two-admin tenants;
  a mutant moving `≥1 other` to `≥2 other` must redden it).
- **Self-approval refused** (approver ≠ requester by principal id) ↔ a different admin's approval
  lands. **Deactivation routed through the flow** (the B2 bypass: deactivate-instead-of-revoke)
  ↔ deactivating a NON-admin user stays direct.
- **The orphan invariant, one named test per path** — revoke, end-date, deactivate, self-deactivate
  — each with its positive twin (the same operation against a non-last admin succeeds). The
  **concurrent** path is proven on PostgreSQL with two real sessions: both count-checks pass under
  no lock, so the test must show the lock serializing them and the second refusing.
- **Cross-tenant refusal**: a tenant admin cannot manage another tenant's users, proven at the
  route with a live second tenant.
- **`auditor_3l` cannot read the roster** ↔ `tenant_admin` can (the exclusion is a decision, so it
  gets a test that would fail if someone "fixed" it).
- **Migration `0068`**: ENT-075 + the four codes + `DELIVERS`; `alembic check`; the identifier
  sweep; the IA trigger asserted on the new table; downgrade honesty.
- **The deployed arm extends `prove_onboarding.sh`**: after the first admin resolves, that admin
  creates a second user and grants a role through the four-eyes flow, and the second user reads a
  governed surface their role permits and is refused one it does not — the remit sentence 1a could
  not finish.
- **Mutation battery**, group `onboard-1b` in `scripts/mutants.toml` (P18, committed, `needs_pg`
  set on every PG-tier mutant — 1a's phantom-kill lesson).
- Both tiers at a frozen tree with exit codes quoted (P14); CI to green; P16 at the PR boundary.

## Non-goals

- No self-service signup, invitations, email, SCIM, MFA.
- No `tenant.suspend` verb (status stays boundary-enforced, setter deferred — 1a's ratified
  deferral, unchanged).
- No tenant deletion; no billing/quota.
- No new platform-catalog codes (the platform half is closed at 1a; `tenant.create` remains the
  sole platform code).
- No change to the OIDC verifier, the boundary check, or the SYSTEM-router fence.
- The worker still does not tick a created tenant (`IRP_TENANT_IDS` stays deploy config; the carry
  rides to REPRO-2 by name, unchanged from 1a).

## If a proof appears to require a production change the record did not ratify

That is a FINDING to report at the gate, not an edit to make (the FK-1 rule).
