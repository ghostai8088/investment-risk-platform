# ONBOARD-1a remit — the platform half of the ignition

**Wave 17, slice 0a.** Branch `onboard-1a-provisioning`. Ratified at the ONBOARD-1 gate
(2026-08-09, OQ-ONB-1…10 all as recommended); the split into 1a/1b was ratified there too, so this
remit needs no second gate. Its authority is `onboard_1_decision_record.md` v3 + the ratification
stamp — where this remit and that record disagree, the record wins and the disagreement is a
FINDING.

Remits state OUTCOMES and PROOFS (the DEP-1 operating model), not steps.

**Scope line (ratified OQ-8):** 1a is the PLATFORM half — a tenant can be created over HTTP and is
born with its role clones and its first admin, who can authenticate. 1b is the TENANT-LOCAL half
(the admin verbs `user.manage`/`role.assign`/`user.view`, the four-eyes lifecycle, the orphan-proof
enforcement paths, the UI). **1a therefore ships a tenant whose first admin exists and can log in
but cannot yet manage anyone** — stated here so nobody reads the gap as an omission.

---

## Outcomes

1. **ENT-074 `tenant` exists as a PLATFORM-GLOBAL entity** — no `tenant_id`, no RLS (the
   `permission`/`role_permission` class, now a named class in the canonical standard). EV temporal
   class. `code` unique, `display_name`, `status` under a total-enumeration CHECK over exactly
   `SYSTEM` / `ACTIVE` / `SUSPENDED` (the 0053 pattern — an unenumerated arm must fail CLOSED),
   `provenance` recording how the row arrived.

2. **Nobody who works today stops working.** Migration `0067` backfills the SYSTEM row and one row
   per DISTINCT `app_user.tenant_id`, **excluding the reserved proof literals named in source**
   (`PROOF_TENANT` and any synthetic ids), each stamped `provenance='0067_backfill'`. A database
   that had tenants before this slice authenticates identically after it.

3. **The boundary refuses what it cannot vouch for.** Behind `get_principal` (both auth modes, not
   inside the OIDC verifier): a token whose tenant claim names no registry row is refused, and so
   is one naming a `SUSPENDED` tenant. **Dialect-gated** — PostgreSQL executes the check, SQLite
   does not, so the unit tier is exempt BY MECHANISM (the `_lock_chain`/`sync_catalog` precedent),
   which is stated in the code rather than left for a reader to infer from an empty table.

4. **Platform authority cannot leak into a tenant.** A separate `PLATFORM_PERMISSIONS` constant
   (sole member `tenant.create`) and a `platform_operator` role that is **not** in
   `ROLE_TEMPLATES`, never cloned, and absent from `ALL_CODES` by construction. Migration `0067`
   inserts the platform permission/role/grant rows inline; `sync_catalog` gains a platform arm so
   future platform codes have the same delivery story.

5. **The gates that would have missed all of this are extended IN THE SAME COMMIT.** P17's
   delivery test and P11's route census walk `ALL_CODES` only today — proven by execution at
   planning that a platform code escapes both silently, and that a `DELIVERS` tuple naming one
   REDDENS the stale-check until the extension lands. Catalog + gate extension + `DELIVERS` are
   atomic or the gates themselves go red.

6. **The SYSTEM tenant becomes authenticatable exactly once, and fenced.** The platform operator
   is the first standing SYSTEM principal (the CLAUDE.md invariant now says so). A SYSTEM-tenant
   principal is refused on **every router except provisioning** — an allow-list check in the
   dependency chain, with a census over the full 251-path surface so the fence cannot silently
   stop covering a router added later.

7. **A tenant is created over HTTP, in one transaction, or not at all.** `POST /tenants`:
   `tenant.create` checked under the caller's own (SYSTEM) context; the SYSTEM template rows read
   under the SYSTEM arm **before** the re-arm (they are FORCE-RLS — this ordering is ratified and
   is the one an earlier draft got wrong); the `tenant` row + SYSTEM-chain audit event written;
   the context re-armed to the new tenant; clones, first admin and seed grant written with the new
   tenant's genesis-anchored audit events. The duplicate-code refusal is a savepoint-wrapped
   pre-check, so a refusal never hands the caller a poisoned session.

8. **The clones honor revocations and collisions.** Cloned FROM the DATABASE's SYSTEM template
   rows (not the constant — the constant would resurrect admin-revoked grants, the class migration
   `0066` closed), via new derivations `tenant_role_id(tenant_id, name)` /
   `tenant_role_permission_id(tenant_id, name, code)`. **Customer tenants receive the four
   business templates + `tenant_admin`; NOT `ops`, NOT `platform_admin`** (ratified). The clone
   SKIPS any template code the tenant already holds (`uq_role_tenant_id`), so backfilled tenants
   with ad-hoc roles are left exactly as they are.

9. **`tenant_admin` is minted as the seventh template** with its user/role-admin codes reserved —
   the ROLE minted here because the seed grant needs it; its VERBS are 1b's.

10. **The mint is governed end to end (R-07/P11/P17):** the audit codes `TENANT.CREATE` and
    `USER.PROVISION`; holder-set pins; SoD rows; the mint checklist **created** in
    `entitlement_sod_model.md` (it does not exist today) carrying the delivery-to-existing-clones
    row; `DELIVERS` in `0067`.

11. **The operator is seeded outside alembic.** An idempotent step in the deploy prepare path (the
    `seed_system_reference` pattern), reading the subject from a deploy-time env var; absent var =
    a loud no-op in the deploy output, never a wedged `upgrade head`.

## Proofs

**Every refusal ships with the positive control that proves the harness delivered its input (P18).**

- **Boundary:** unknown-tenant claim refused ↔ registered tenant admitted; `SUSPENDED` refused ↔
  `ACTIVE` admitted; both auth modes, PG tier. Plus the dialect gate asserted directly (the check
  is a no-op on SQLite, by mechanism).
- **Fence:** a SYSTEM-tenant principal refused on a data router ↔ admitted on provisioning; the
  census walks all 251 paths and fails if a router escapes classification (non-vacuity floor: the
  census must find the provisioning routes it exempts).
- **Escalation closure (the trap that broke v1):** `tenant.create` denied to every tenant-catalog
  role **including a cloned `platform_admin`, asserted against the DATABASE after an onboarding**
  ↔ granted to the operator. Plus the constant-level disjointness census
  (`PLATFORM_PERMISSIONS ∩ PERMISSIONS = ∅`).
- **Atomicity:** duplicate tenant code refused with NOTHING persisted — the ABSENCE of the tenant
  row, the clones and the user asserted (the DATA-1 hostile-caller shape) ↔ a fresh code lands all
  of it.
- **Clones:** post-onboard matrix == the DB's SYSTEM template rows at clone time, exact set
  equality both directions, scoped to onboarding-created tenants and to the ratified template set
  (a cloned `ops`/`platform_admin` is a FAILURE, asserted); a tenant onboarded after a
  template-grant revocation lacks that grant (the `0066` interplay, executed).
- **Audit:** post-onboard, the SYSTEM chain's `TENANT.CREATE` and the new tenant's
  genesis-anchored events both exist; `verify_chain` green on BOTH chains.
- **Migration on a POPULATED database:** upgrade a DB holding pre-existing tenants → they still
  authenticate, proof literals are ABSENT from the registry, provenance stamps present. Executed
  on the local PG, not reasoned.
- **Both tiers**: `make check-all` and the full-PG battery at a frozen tree, exit codes quoted
  (P14); `alembic check`; the identifier sweep.
- **Deployed ignition proof** (OQ-10A), riding `stack-proof`: fresh deploy → operator creates a
  tenant over HTTP → the first admin's principal resolves against a governed read. Under
  `dev_header`, with the OIDC-specific refusals proven at the token-minting tier — the shared
  assumption named (P15).
- **Mutation battery**, group `onboard-1a` in `scripts/mutants.toml` (P18, committed): the
  disjointness census, the fence, the dialect gate, the clone source (constant-vs-DB must redden
  the revocation-interplay test), the collision rule, and the P17/P11 gate extensions.

## Non-goals

- The tenant-local admin verbs, the four-eyes lifecycle, ENT-075, `role.approve`, the UI — all 1b.
- `tenant.suspend` (the status is enforced at the boundary; no setter — ratified deferral).
- Tenant deletion; self-service signup; SCIM; MFA; billing.
- Any change to the OIDC verifier or token shape.
- Any widening of the hybrid 7-table set (unchanged), and no BYPASSRLS anywhere.
- The worker still does not tick a new tenant (`IRP_TENANT_IDS` stays config; the API response and
  runbook state the operator's follow-up step; the carry rides to REPRO-2 by name).

## If a proof appears to require a production change the record did not ratify

That is a FINDING to report at the gate, not an edit to make (the FK-1 rule).
