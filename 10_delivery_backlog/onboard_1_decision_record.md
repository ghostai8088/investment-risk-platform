# ONBOARD-1 decision record — the platform gets an ignition

**Wave 17, slice 0.** Branch `onboard-1-planning`. Ratified as the wave opener at the Wave-16 close
(**D3** — v1 of this record said D1, which was the `report.*` holder-set item; the misattribution
was verifier finding L5-4) on the review's headline finding: **251 API paths — 289 RBAC-protected
operations plus 2 deliberately anonymous (`/health`, `/version`) — and no way to create the
tenant, user, or role any of them requires.** Every deployment that has ever existed was seeded by
a demo or proof script.

**Status: v2 — REWRITTEN after the pre-ratification verifier pass** (5 lanes, 40 agents,
refute-by-default; **11 CONFIRMED BLOCKING, 23 CONFIRMED MATERIAL, 14 minor** against v1 at
`7a61303`). The findings ledger is §7. v1's worst defect was structural and FIVE lanes converged
on it independently: v1's own three recommendations, composed, handed `tenant.create` to every
customer tenant. This version is the fold; nothing here is self-ratified.

---

## 1. The recon facts (re-derived by the verifier pass; v1's errors corrected in place)

| # | Fact | Evidence |
|---|---|---|
| R1 | **No tenant table exists.** `tenant_id` is a free-floating GUID; no migration creates a `tenant` relation | Re-executed: no `create_table("tenant")` in any of 50 migration files; no `class Tenant` |
| R2 | **RLS context is armed from the caller's token claim**, canonicalized then set transaction-locally; `set_tenant_context` already re-arms mid-request today (`deps.py:142` then `:170`), so a route-level re-arm is an existing seam, not new machinery | `deps.py:104–170`; verifier lane 1 EXECUTED the two-arm flow against PG 16 with the exact 0001 policy DDL: check-under-SYSTEM then re-arm-and-write works in ONE transaction, no BYPASSRLS |
| R3 | **The template-cloning code promised since P0.5 does not exist** | `bootstrap.py:6` docstring; no clone code in `entitlement/` |
| R4 | **Only demo/proof scripts create users**; all use `DEMO_TENANT_ID`/`PROOF_TENANT` | Five non-test `AppUser(` sites |
| R5 | **ROLE-ADM is described but unminted**: "User/role admin; **cannot** approve own entitlement requests **or edit audit**" (v1 truncated the quote — L5-10) | `entitlement_sod_model.md:51` |
| R6 | **There are SIX role templates**, not five: `platform_admin`, `ops`, `data_steward`, `risk_analyst_1l`, `risk_manager_2l`, `auditor_3l`. v1 said five throughout — a false load-bearing count (L5-1/L2-2, BLOCKING class) | `ROLE_TEMPLATES` executed listing |
| R7 | **The uuid5 derivations do NOT namespace by tenant**: `role_id(name)` hardcodes `SYSTEM_TENANT_ID`; `role_permission_id(role, code)` has NO tenant component. v1 claimed the opposite (L3-1, BLOCKING) — cloning requires NEW derivations | `bootstrap.py:537–542`, executed |
| R8 | **`platform_admin` is `list(ALL_CODES)`** — any code appended to `PERMISSIONS` enters its template automatically, and `sync_catalog` materializes grants solely from `ROLE_TEMPLATES` | `bootstrap.py:255`; `sync.py` |
| R9 | **The worker's tenant membership is deploy-time env config** (`IRP_TENANT_IDS`, ratified at CAD-1 as "config, NOT a DB sweep") — a created tenant does not TICK until an operator edits the deployment | CAD-1 record; supervisor source |
| R10 | **The deployed stack runs `AUTH_MODE=dev_header`**; Keycloak sits behind an opt-in compose profile the stack-proof job does not enable | compose + CI workflow, lane 2 |
| R11 | **`grant_role` as shipped refuses a cross-tenant actor**, and `audit_event` is FORCE-RLS tenant-scoped with `chain_id == tenant_id` — the onboarding act's audit home is a real design choice, not an afterthought | lane 1/lane 4, executed |
| R12 | **Nothing refuses a SYSTEM-tenant token claim today** — it 401s only because no SYSTEM `app_user` row exists. The day ONBOARD-1 seeds the operator, any IdP-signed token claiming the SYSTEM tenant resolves | lane 1 (L1-3) |

## 2. The shape (v2 — restructured around the verifier's two hard constraints)

The two constraints v1 violated, now load-bearing:

- **C1 (the ALL_CODES trap):** platform-scope authority must live OUTSIDE the tenant catalog.
  Anything minted into `PERMISSIONS` reaches `platform_admin`, the sync, and every clone.
- **C2 (the exists-check must not strand anyone):** a tenant registry that refuses unknown tenants
  must be born already containing the SYSTEM tenant AND every tenant that exists in the deployed
  world — or ONBOARD-1 ships the exact undeliverable-to-live-DBs class P17 was just ratified
  against (L1-2/L4-2/L4-3/L5-8).

Three layers:

1. **ENT-074 `tenant`** — platform-global registry (no `tenant_id`, no RLS — the
   `permission`/`role_permission` class; the canonical standard gains an explicit
   **PLATFORM-GLOBAL tenancy class** naming all three, rather than v1's silent invention, L4-8).
   Columns: `code` (unique), `display_name`, `status` (`ACTIVE`/`SUSPENDED`, total-enumeration
   CHECK, the 0053 pattern), timestamps. EV temporal class (it IS config; "append-lifecycle" was
   not a ratified class — L4-8). **Migration `0067` backfills**: a row for `SYSTEM_TENANT_ID`
   (status `SYSTEM` — a third enum arm so the operator's own context passes the exists-check
   without ever being a customer tenant, L1-2/L5-8) and a row for every DISTINCT `tenant_id` in
   `app_user` (the already-deployed tenants keep working, L4-3), each with a literal `DELIVERS`-
   style declaration in the migration docstring of what was backfilled and why.
2. **The platform catalog + the onboarding act.** A NEW, SEPARATE constant
   `PLATFORM_PERMISSIONS` (first member: `tenant.create`) and a NEW system-only role
   `platform_operator` — **not** in `ROLE_TEMPLATES`, **never** cloned, **excluded from
   `ALL_CODES`** by construction (different constant), with a census test asserting the two
   catalogs are disjoint AND that no tenant-cloned role ever holds a platform code (C1 made
   mechanical). The onboarding act is one transaction: check `tenant.create` under the SYSTEM
   context → insert the `tenant` row → re-arm to the new tenant → clone the templates → seed the
   first admin → grant. Savepoint around the duplicate-code pre-check (L4-6); every audit event
   for SYSTEM-context writes lands in the **SYSTEM chain**, every new-tenant row's event in the
   **new tenant's chain** — the new tenant's audit chain is born WITH the tenant, genesis-anchored
   by the onboarding act itself (L1-4 resolved explicitly).
3. **Tenant-local user/role administration** under the newly minted `tenant_admin` (the SEVENTH
   template — R6), with the SoD design of OQ-4/OQ-9 below.

## 3. The forks (OQ-ONB-1…10) — recommendations attached, none self-ratified

### OQ-ONB-1 — `tenant` as a first-class PLATFORM-GLOBAL entity
As v1, plus the verifier's corrections baked in: **A (recommended)** = ENT-074 platform-global,
EV class, the three-arm status enum (`SYSTEM`/`ACTIVE`/`SUSPENDED`), the 0067 backfill of SYSTEM +
all deployed tenants, and a **new census for the intentionally-global class** (L4-7: a
no-`tenant_id` table is invisible to every shipped tenancy floor — the class census asserts every
no-`tenant_id` table is on an explicit allow-list with a reason: `permission`,
`role_permission`, `role_permission_revocation`, `tenant`). B (implicit tenants) and C (hybrid row)
fail as in v1.

### OQ-ONB-2 — Tenant-creation authority (the crux)
**A (recommended): a SYSTEM-tenant `platform_operator` principal** holding `tenant.create` from
the PLATFORM catalog (C1), checked in its own context; the route re-arms to the new tenant inside
the single onboarding transaction (R2 — executed as buildable by the verifier).
**The invariant amendment, stated whole (L1-5):** option A adds (i) the guarded cross-tenant
onboarding transaction, **(ii) a standing SYSTEM-tenant authenticatable principal — the first
ever** (R12), and (iii) the SYSTEM tenant's registry row. Ratifying A amends the CLAUDE.md
invariant to name all three. **The R12 mitigation ships in-slice:** SYSTEM-tenant principals are
refused on every router EXCEPT the provisioning router (a route-level fence with its own census
test + the P18 positive control), so an IdP-signed SYSTEM claim buys exactly the provisioning
surface and nothing else. The operator seeding is a sub-fork: **(a) recommended** — a
`DELIVERS`-declared migration seeds the operator `app_user` from a deploy-time env var
(subject only; no secret in source, BR-10), refusing to seed when the var is absent (fail-closed,
documented); (b) a documented manual operator step. B (out-of-band CLI) and C (bootstrap token)
fail as in v1.

### OQ-ONB-3 — The first user of a new tenant
As v1: **A (recommended)** — supplied in the create request, seeded as the tenant's admin in the
same transaction; the platform operator is NOT a member. (The cross-tenant grant write happens
inside the onboarding transaction under the NEW tenant's context with the SYSTEM operator as the
audit actor — `grant_role`'s cross-tenant refusal (R11) stays intact for every OTHER path; the
onboarding service writes the seed grant directly, and the refusal's census gains the exception
row with reason, L4-5.)

### OQ-ONB-4 — The tenant admin role, and the ORPHAN-PROOF invariant
**A (recommended): mint `tenant_admin` as the SEVENTH template** — user/role admin verbs only, no
analytics reads, no maker verbs. The last-admin protection is now stated as an INVARIANT over all
paths, not a per-verb rule (L1-8/L3-3/L3-4/L3-5): **a tenant must at all times have ≥1
currently-valid, ACTIVE-user admin** — enforced identically against role revocation, role
END-DATING (`valid_to` counts: the admin count is over grants valid NOW), user DEACTIVATION
(including self), and concurrently (a per-tenant advisory lock around the count-check —
the MG-2 write-lock precedent — so two admins revoking each other serializes and the second
refuses). Each path's refusal is a named test with its P18 positive control.

### OQ-ONB-5 — The mint
**Tenant catalog** (enters `PERMISSIONS`, `ALL_CODES`, the clones): `user.manage` (create/
deactivate users), `role.assign` (grant/revoke roles), `user.view` (list users/roles).
Holder sets: `tenant_admin` + `platform_admin` for all three; **`auditor_3l` is EXCLUDED from
`user.view`** — v1 recommended inclusion on the schedule.view precedent and the verifier
mis-class finding (L3-8) is right: `app_user` rows carry `external_subject` (the OIDC sub) and
`display_name` — person-identifying data, the class every proprietary-identity read has excluded
the 3L auditor from (the CON-1 split-by-what-the-read-exposes doctrine). A redacted roster read
for auditors is NOT minted (the SOD-08 half-mint precedent; trigger: a real 3L access-review
requirement). **Platform catalog** (C1): `tenant.create` only; `tenant.suspend` is NOT minted and
the `SUSPENDED` status arm ships **enforced at the boundary but unreachable by any verb** — the
exists-check refuses suspended tenants' tokens (so the semantics are real and tested, L5-6), and
the setting verb waits with a P19-valid trigger: **the first operator request to suspend a
tenant** (an external human event, loud and datable — the L5-12 class). P11 in full for every
code; migration `0067` carries the literal `DELIVERS` tuple for the tenant-catalog codes and the
platform catalog gets its own parallel delivery census (the P17 test is extended to walk BOTH
constants — L3-9 noted that the gate is AST-only; the extension keeps it so, deliberately, with
the PG-tier grant checks as the execution arm).

### OQ-ONB-6 — Clone semantics (rebuilt: v1's version was unbuildable, R7)
**Clone FROM THE DATABASE's SYSTEM template rows, not from the constant** (L3-6: the constant
would resurrect admin-revoked grants — the exact resurrection class migration `0066` just
closed; the DB rows are the post-revocation truth). NEW deterministic derivations
`tenant_role_id(tenant_id, name)` and `tenant_role_permission_id(tenant_id, name, code)` (R7).
Clone all SEVEN templates. Post-clone drift is tenant configuration; catalog syncs touch SYSTEM
templates only (verified true of `sync_catalog` by the pass). **Pre-existing tenants** (L3-7): the
0067 backfill ALSO clones templates for every backfilled ACTIVE tenant that lacks them — the demo
tenant's three ad-hoc roles are untouched (additive only). **The future-mint catchup** (L5-5 — v1's
trigger was not mechanical): the mint checklist in `entitlement_sod_model.md` gains a required
row — "delivery to EXISTING tenants' clones: named migration or explicit refusal with reason" —
and `sync_catalog`'s report gains a `tenants_missing_code` count so every future sync migration
LOGS the gap at the moment it runs. Mechanical and loud; the carry names it.

### OQ-ONB-7 — Surface
As v1: **A (recommended)** — API for everything; UI for the tenant-local Users & Roles screen
only. Unchanged by the pass.

### OQ-ONB-8 — Sizing and the split line (quantified, L5-7)
**Sized L** (v1 had no sizing section — L5-9; comparators: CAL-1b M/L at ~1 migration + 1 family;
RPT-2 L at ~1 migration + routes + FE). **The split trigger, one condition, measurable:** if at
the end of planning the implementation plan's checklist exceeds **the RPT-2 plan's checklist row
count** (the largest single-slice plan shipped to date), the slice splits at the platform/tenant
line — ONBOARD-1a = OQ-1/2/3 (registry, operator, onboarding act), ONBOARD-1b = OQ-4/5/6/7/9
(tenant-local admin + UI) — under these same ratified forks, no second gate.

### OQ-ONB-9 — SOD-04: four-eyes on entitlement changes (NEW — the pass found v1 contradicted the ratified SoD model, L5-3 BLOCKING)
`entitlement_sod_model.md` §7: "Four-eyes is mandatory for: … entitlement changes (SOD-04)". v1's
direct single-person grant (self-grant refused) contradicts it.
| Option | Consequence |
|---|---|
| **A. Maker-checker grants WHEN POSSIBLE, single-admin bootstrap window (recommended)**: a grant/revoke by an admin in a tenant with **≥2 currently-valid other admins** is born `PENDING` and requires a SECOND admin's approval (the MG-3 person-level pattern: approver ≠ requester by principal id); in a tenant with exactly ONE admin, grants execute directly (the tenant is otherwise stillborn at birth) with the direct-grant fact stamped on the audit event | SOD-04 honored from the first moment it CAN be; the bootstrap window is honest, bounded by the admin count itself, and every direct grant is flagged evidence. The MG-2/MG-3 lifecycle machinery is precedent, not new invention |
| B. Direct grants + self-grant refusal only; SOD-04 recorded as a ratified deviation | The ratified SoD model is amended by exception on day one of real entitlement changes — the matrix's four-eyes clause becomes aspirational exactly where it first binds |
| C. Full four-eyes always (the first admin cannot grant until a second admin exists — seeded by the operator) | The operator must seed TWO admins at onboarding; every tenant pays the ceremony forever; the operator names two humans where the request had one |

### OQ-ONB-10 — The ignition proof's auth mode (NEW — v1's proof was unexecutable as written, L2-4/L2-5)
The deployed stack runs `dev_header`; Keycloak is behind an opt-in profile the stack-proof job
does not enable (R10).
| Option | Consequence |
|---|---|
| **A. The deployed ignition proof runs under `dev_header` end-to-end, PLUS a unit/PG-tier OIDC arm for the exists-check and the SYSTEM-router fence (recommended)** | The deployed proof exercises every layer ONBOARD-1 builds (routes, transaction, clones, RLS) — the auth MODE is the one layer it shares with today's stack-proof, stated as the P15 shared-assumption it is, with the OIDC-specific refusals (unknown-tenant claim, SYSTEM-claim fence, suspended-tenant claim) proven at the tier that can mint tokens |
| B. Enable the Keycloak profile in CI for this slice | The full OIDC path deployed — at the cost of standing up an IdP in the stack-proof job (provisioning realms/users in CI), a real scope expansion the record would have to size |
| **The exists-check scope decision folded in (L2-4):** the exists-check binds BOTH auth modes (it lives behind `get_principal`, not inside the OIDC verifier) — `dev_header` requests with unknown tenants are refused identically, so the deployed proof CAN exercise it; the entire existing test suite's uuid4-tenant fixtures are backfill-exempt because the unit tier has no `tenant` table rows — the exists-check is **PG-tier and boundary-only by design**, stated plainly (SQLite suites are structurally out of its reach, the FK-1 lesson acknowledged, not hidden) | |

## 4. Proofs (P18 bar; every refusal paired with its positive control)

- **The refusal battery, each with its named positive twin**: unknown-tenant claim refused ↔ known
  tenant admitted; SYSTEM claim refused on a data router ↔ admitted on the provisioning router;
  suspended tenant refused ↔ active admitted; `tenant.create` denied to every tenant-catalog role
  ↔ granted to the operator; self-grant refused ↔ second-admin grant lands (OQ-9A); last-admin
  refusals across ALL FOUR paths (revoke, end-date, deactivate, concurrent) ↔ non-last admin
  operations succeed; duplicate tenant code refused with NOTHING persisted (absence asserted) ↔
  fresh code lands everything.
- **The clone equivalence proof**: post-onboard matrix == the DB's SYSTEM template rows at clone
  time (not the constant), exact set equality both directions; a revoked-template-grant tenant
  onboards WITHOUT the revoked grant (the `0066` interplay, executed).
- **The catalog-disjointness census** (C1): `PLATFORM_PERMISSIONS ∩ PERMISSIONS = ∅`; no cloned
  role holds a platform code — asserted against the DATABASE after onboarding, not just the
  constants.
- **The deployed ignition proof** (OQ-10A): fresh deploy → operator creates a tenant over HTTP →
  first admin resolves → creates a second user, grants a role (through the OQ-9 flow) → the second
  user reads one governed surface and is 403'd from another. Rides `stack-proof`.
- **Mutation battery**: group `onboard-1` in `scripts/mutants.toml` (P18), targeting the census,
  the fence, the orphan-proof invariant, and the clone-source choice (mutating DB-source back to
  constant-source must redden the revocation-interplay test).
- **Migration `0067`**: ENT-074 + backfills + the mint + `DELIVERS`; `alembic check`; identifier
  sweep; downgrade honesty (downgrade drops the registry and the exists-check's data — stated: a
  downgraded deployment loses boundary refusal, not tenant data).
- Gates at a frozen tree, exit codes quoted (P14); CI green; P16 at the PR boundary.

## 5. Non-goals (unchanged from v1 except as noted)

- No self-service signup, invitations, email, SCIM, MFA surface.
- No tenant deletion (trigger: the first real offboarding request).
- No billing/quota/plan concepts.
- No change to the OIDC verifier or token shape; the exists-check and SYSTEM-router fence sit
  behind `get_principal`.
- No `tenant.suspend` verb (OQ-5; status semantics enforced, setter deferred on a P19 trigger).
- No auditor roster read (OQ-5; deferred with trigger).
- **The worker still does not tick new tenants** (R9 — v1 was silent, L2-3): `IRP_TENANT_IDS` is
  deploy config by CAD-1's ratified decision, and ONBOARD-1 does not reopen it. The onboarding
  API response and the runbook BOTH state the operator's follow-up step verbatim ("add the tenant
  id to `IRP_TENANT_IDS` and roll the worker"), and the slice record will carry the
  scheduled-work gap with its P19 host: **REPRO-2's schedule write path** is where tenant-driven
  scheduling next gets touched, and the carry rides there by name.

## 6. What ratifying this gate amends elsewhere (named, so the gate sees the blast radius)

1. The CLAUDE.md invariant gains the three-part ONBOARD-1 clause (OQ-2).
2. `canonical_data_model_standard.md` gains the PLATFORM-GLOBAL tenancy class (OQ-1).
3. `entitlement_sod_model.md`: ROLE-ADM → minted as `tenant_admin`; the mint checklist gains the
   delivery-to-clones row (OQ-6); SOD-04's four-eyes clause gets its first enforcement (OQ-9).
4. The intentionally-global-class census becomes a standing guard (OQ-1).

## 7. The verifier-pass ledger (v1 → v2)

**Pass over `7a61303`: 5 lanes, 40 agents, 2.0M tokens; 35 verified findings (11 BLOCKING, 23
MATERIAL after refute-by-default — 1 refuted outright, 2 downgraded), 14 minors.** Full JSON:
session scratchpad `onb1_verifier.json`; lanes also recorded 30+ attacks that FAILED (the record's
transaction mechanics, refusal atomicity, migration numbering, identifier lengths, catalog-sync
ordering, and idempotency all survived execution).

| Cluster | Findings | Fold |
|---|---|---|
| The ALL_CODES trap (5 lanes converged) | L1-1, L2-1, L3-2, L4-1, L5-2 | C1: the separate PLATFORM catalog + `platform_operator` + disjointness census (§2, OQ-2, OQ-5) |
| Exists-check strands SYSTEM/deployed tenants | L1-2, L4-2, L4-3, L5-8 | C2: the three-arm status + 0067 backfill of SYSTEM and all deployed tenants (OQ-1) |
| False facts: five templates; uuid5 namespacing; D1-vs-D3; 291 | L5-1, L2-2, L3-1, L4-4, L5-4, L2-7 + minors | Corrected in place (R6, R7, header) |
| SOD-04 contradiction | L5-3 | NEW OQ-9 with the maker-checker recommendation |
| Audit-chain silence | L1-4 | §2 layer 2: split-chain design, genesis-anchored |
| SYSTEM becomes authenticatable | L1-3, L1-5 | The router fence + the three-part invariant amendment (OQ-2) |
| Orphan paths (deactivate/end-date/TOCTOU) | L1-8, L3-3, L3-4, L3-5 | OQ-4's invariant-over-all-paths + advisory lock |
| Clone source + pre-existing tenants + catchup | L3-6, L3-7, L5-5 | OQ-6 rebuilt: DB-source clones, backfill clones, mechanical catchup |
| Worker never ticks | L2-3 | §5 non-goal stated with the runbook step + P19 carry to REPRO-2 |
| Ignition proof unexecutable | L2-4, L2-5 | NEW OQ-10 |
| auditor `user.view` mis-class | L3-8 | OQ-5 flipped: auditor EXCLUDED |
| Global-class census gap | L4-7 | OQ-1's new census |
| Suspended inert; split trigger; sizing/demo gaps | L5-6, L5-7, L5-9 | OQ-5 boundary-enforced status; OQ-8 quantified; sizing added. Demo-stage disposition: the deployed ignition proof IS this slice's demo (stated, not omitted) |
| Cross-tenant grant refusal vs step 4 | L4-5 | OQ-3: the seed-grant exception, census-rowed |
| Savepoint on duplicate-code refusal | L4-6 | §2 layer 2 |
| Minors (12) | L1-7…L5-12 | Folded in place (counts, quotes, wording) |
