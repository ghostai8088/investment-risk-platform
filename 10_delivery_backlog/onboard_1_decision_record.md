# ONBOARD-1 decision record — the platform gets an ignition

**Wave 17, slice 0.** Branch `onboard-1-planning`. Ratified as the wave opener at the Wave-16 close
(D1) on the review's headline finding: **251 API paths, 291 RBAC-protected operations, and no way
to create the tenant, user, or role any of them requires.** Every deployment that has ever existed
was seeded by a demo or proof script. The records describe a deployable multi-tenant product; the
code describes a very well-governed engine with no ignition.

Status: **DRAFT — awaiting the pre-ratification verifier pass, then the OQ gate.**

---

## 1. The recon facts this design stands on (verified at `d4e3692`, commands quoted)

| # | Fact | Evidence |
|---|---|---|
| R1 | **There is no tenant table.** `tenant_id` is a free-floating GUID on every tenant-scoped table; no migration creates a `tenant` relation; a "tenant" exists only as the set of rows that carry its id | `grep -rn '"tenant"' migrations/versions/0001_foundation_tables.py` → nothing; no `class Tenant` anywhere in `irp_shared` |
| R2 | **RLS context is armed from the caller's token claim.** `get_principal` (oidc mode) canonicalizes the JWT's tenant claim and `set_tenant_context` arms `app.current_tenant` transaction-locally; the RLS policies compare `tenant_id::text` to that GUC | `apps/backend/src/irp_backend/deps.py:104–152`; `irp_shared/db/tenant.py` |
| R3 | **The template-cloning code promised since P0.5 does not exist.** `bootstrap.py`'s docstring: "tenant onboarding later clones them into tenant-scoped roles" — no clone function anywhere in `entitlement/` | `grep -rn "clone" entitlement/service.py` → nothing |
| R4 | **Only demo/proof scripts create users.** Every `AppUser(` construction site outside tests is a demo stage or a deploy-proof harness | `grep -rln "AppUser(" src…` → `demo/ops_stage14.py`, `demo/lim2_stage20.py`, `demo/campaign.py`, two `deploy/*_proof.py` |
| R5 | **ROLE-ADM is described but unminted** — "User/role admin; **cannot** approve own entitlement requests" (`entitlement_sod_model.md` §4) has no template counterpart, the ROLE-RC shape | `06_security/entitlement_sod_model.md:51` |
| R6 | **Entitlement checks resolve in the caller's own tenant context** — `require_permission` walks `user_role` → `role_permission` → `permission` under the caller's armed GUC; `role`/`user_role`/`app_user` are tenant-scoped FORCE RLS; `permission`/`role_permission` are global | `entitlement/service.py:106`; migration `0001` |
| R7 | **P17 is standing**: any new permission code must ship a migration with a literal `DELIVERS` tuple, and the catalog sync consults the revocation ledger | `test_entitlement_mint_delivery.py`; `entitlement/sync.py`; migration `0066` |

The mechanical consequence of R1+R2 together, stated because the whole design hangs on it: creating
a tenant's first rows requires **arming a GUC for a tenant that has no users yet** — no BYPASSRLS
is mechanically needed (RLS admits whatever tenant the GUC names), so the entire question is
**what AUTHORIZES a caller to arm a context different from their own token's claim.** That is an
authority-model decision, not a plumbing one, which is why this slice is fork-heavy.

## 2. The shape (what ONBOARD-1 builds, assuming the forks resolve as recommended)

One governed onboarding surface, three layers:

1. **ENT-074 `tenant`** — the platform's first PLATFORM-GLOBAL registry entity (no `tenant_id`, no
   RLS — the `permission` class, NOT the hybrid class; see OQ-1). A tenant becomes a row with a
   lifecycle (`ACTIVE`/`SUSPENDED`), a code, a display name — something provisioning can point at,
   audit can anchor to, and R2's canonicalization can VALIDATE against (today any well-formed UUID
   in a token claim arms a context; after ONBOARD-1 an unknown tenant is refused at the boundary).
2. **The onboarding act** — one transaction: insert the `tenant` row → clone the five role
   templates into tenant-scoped roles (deterministic ids, `role:{tenant_id}:{name}`) → create the
   first admin user from a caller-supplied OIDC subject → grant that user the tenant's admin role.
   All four steps or none (the DATA-1 refusal-ordering lesson).
3. **Tenant-local user/role administration** — create/deactivate users, grant/revoke roles, list
   both — the ROLE-ADM verbs, inside the tenant's own RLS context, with the SoD refusal that an
   admin cannot grant themselves (R5's "cannot approve own entitlement requests", finally enforced
   rather than described).

## 3. The forks (OQ-ONB-1…8) — each with a recommendation, none self-ratified

### OQ-ONB-1 — Does `tenant` become a first-class entity, and in which tenancy class?
| Option | Consequence |
|---|---|
| **A. ENT-074 `tenant`, PLATFORM-GLOBAL (no tenant_id, no RLS — the `permission`/`role_permission` class)** *(recommended)* | Provisioning has a subject; audit has an anchor; the token-claim canonicalization gains an exists-check; the closed 7-table hybrid set is UNTOUCHED (a tenant row is not a shared vocabulary — it is platform config, the class `permission` already occupies). Chicken-and-egg dissolves: the row cannot be tenant-scoped to the tenant it defines |
| B. Keep tenants implicit (a UUID convention) | ONBOARD-1 shrinks to user-seeding; "create a tenant" stays "use a new UUID", unlisted, unauditable, unsuspendable — the current state with better paperwork |
| C. ENT-074 as a SYSTEM-tenant hybrid row | Requires extending the closed hybrid set (AD-013-R3) for no reason A doesn't satisfy — hybrid exists for *globally shared vocabularies read by every tenant*, and tenants don't read each other's registry rows |

Note under A: the `tenant` table is append-lifecycle (status transitions, no deletes) but NOT
IA-triggered — it is platform config, not governed evidence (the same reasoning as the revocation
ledger, migration `0066`).

### OQ-ONB-2 — Tenant-creation authority (the crux fork)
| Option | Consequence |
|---|---|
| **A. A platform-scope operator: a SYSTEM-tenant principal holding a new `tenant.create` code, checked in the caller's OWN context; the route then arms the NEW tenant's GUC inside the single onboarding transaction** *(recommended, with the invariant note below)* | Governed, auditable, deny-by-default, HTTP-reachable. The cross-tenant GUC arming is scoped to one transaction whose every write is the onboarding act itself |
| B. Out-of-band only (a CLI/script against the DB, like `alembic`) | Honest but keeps provisioning outside the governed surface — no RBAC, no audit event, no 403s; the demo-script status quo with a nicer wrapper |
| C. A signed bootstrap token (no SYSTEM principal; a deployment secret authorizes creation) | A second authentication system to build, rotate and audit; BR-10 adjacency; weaker than A on every axis once A exists |

**The invariant note, stated so the gate sees it whole:** the CLAUDE.md invariant is "no
BYPASSRLS app path; no hybrid/SYSTEM_TENANT **behavior** beyond the closed 7-table set". Option A
adds **no BYPASSRLS** (the GUC mechanism is unchanged) and **no hybrid table** — but it does give
a SYSTEM-tenant *principal* an app path that arms another tenant's context, which is NEW
SYSTEM-tenant behavior in the plain-English sense. The verifier pass must attack this reading;
ratifying OQ-ONB-2=A explicitly amends the invariant's scope ("…beyond the 7-table set **plus the
ONBOARD-1 onboarding transaction, `tenant.create`-guarded**") rather than lawyering around it.
SYSTEM-tenant users do not otherwise exist today; A requires seeding ONE platform-operator user in
the SYSTEM tenant at deploy time (the deployment's own act, via a DELIVERS-declared migration or a
documented operator step — sub-fork at the gate).

### OQ-ONB-3 — The first user of a new tenant (the bootstrap identity)
| Option | Consequence |
|---|---|
| **A. Supplied in the create-tenant request: OIDC subject + display name; seeded as the tenant's ADMIN-role holder in the same transaction** *(recommended)* | The tenant is born with exactly one admin who can then provision everyone else tenant-locally. The platform operator names the first admin but is NOT a user in the new tenant (SoD: creating a container ≠ membership) |
| B. The tenant is born empty; the platform operator makes a second cross-tenant call to add the first user | Two cross-tenant acts instead of one; a window where a tenant exists that nobody can ever log into |

### OQ-ONB-4 — What the admin role of a new tenant IS
| Option | Consequence |
|---|---|
| **A. Mint ROLE-ADM as the SIXTH template (`tenant_admin`): user/role administration verbs ONLY — no analytics reads, no maker verbs; cloned to every tenant like the other five** *(recommended)* | The first user of a tenant can provision but cannot silently read the book or run the numbers — they grant themselves nothing (the SoD refusal below). R5's described-but-unminted role becomes real under this gate's R-07 authority |
| B. First user gets the tenant's `platform_admin` clone (ALL_CODES) | No new role, but every customer's first user holds every verb including 3L oversight reads — an SoD hole the matrix would carry forever |

Under A, the SoD refusal (person-level, the MG-3 pattern): **no admin may grant a role to
themselves** — `actor_id != target user_id` on every grant, platform_admin included (the dual-hat
backstop). Revocation is also self-excluded (an admin cannot revoke their own admin role and
orphan the tenant — the MG-2 empty-set lesson inverted: the LAST admin's role is irrevocable).

### OQ-ONB-5 — The mint (new codes; P11 + P17 discipline in full)
**Recommended set, minimal:** `tenant.create` (platform-scope; SYSTEM-tenant operator + nothing
else), `user.manage` (create/deactivate users; tenant_admin + platform_admin), `role.assign`
(grant/revoke roles; tenant_admin + platform_admin), `user.view` (list users/roles; tenant_admin +
platform_admin + auditor_3l — an entitlement roster is governed-oversight scope, the
schedule.view precedent). Deliberately NOT minted: `tenant.suspend`/`tenant.view` platform verbs
beyond create (suspension ships the status column but the operating verb waits for a real
lifecycle need — the SOD-08 half-mint precedent); any self-service/invitation flow. Each code
ships holder-set pins, the route census rides `test_route_permission_census.py`, the SoD row lands
in `entitlement_sod_model.md`, and migration `0067` carries the literal `DELIVERS` tuple (P17 —
this is the FIRST mint born under that gate).

### OQ-ONB-6 — Template cloning semantics
**Recommended:** clone all six templates (five + `tenant_admin`) at onboarding; deterministic ids
(`role:{tenant_id}:{name}` — the existing uuid5 derivation already namespaces by tenant, R3's
promise kept literally); grants copied row-by-row. **After cloning, tenant roles are the tenant's
own**: catalog syncs (the `0064` pattern) touch SYSTEM templates only — post-clone drift is tenant
configuration, not staleness. A NEW code minted after a tenant onboards therefore reaches the
tenant's clones only by an explicit decision — recorded as a named limitation with its trigger (a
future `tenant role catchup` operation, P19-compliant: trigger = the first post-ONBOARD mint that
must reach existing tenants' role clones; the DELIVERS gate makes that moment loud).

### OQ-ONB-7 — Surface: API-only, or API + UI?
| Option | Consequence |
|---|---|
| **A. API for everything; UI for the TENANT-LOCAL half only (a Users & Roles screen on the ops surface — list, create, grant, revoke); tenant creation stays API-only** *(recommended)* | The operator act (rare, platform-scope) needs no screen to be real; the daily act (tenant admins managing users) gets one, on the OPS-1 write-path precedent. Bounded FE scope |
| B. API-only | "Reachable" again means curl; the review's finding was about REACHABILITY for real users |
| C. Full UI including tenant creation | The platform-operator screen serves an audience of ~one and inflates slice 0 |

### OQ-ONB-8 — Sizing and the split trigger
**L as one slice, with a pre-agreed split line** (P19-compliant): if the verifier pass or the build
finds the platform-scope half (OQ-1+2, ENT-074 + `tenant.create` + the onboarding transaction) and
the tenant-local half (OQ-4+5+7, users/roles admin + UI) each carrying a full proof battery, the
slice splits at that line into ONBOARD-1a/1b — the trigger is the build exceeding the CAL-1
two-convention-slice size in practice, and the split needs no new gate (the same ratified forks
govern both halves).

## 4. Proofs (the P18 bar, named before the build)

- **Every refusal FIRES (P9), with the P18 positive control beside it**: unknown-tenant token claim
  refused at the boundary; `tenant.create` denied to every non-operator role; self-grant refused
  for the admin who tries; last-admin revocation refused; duplicate tenant code refused; the
  onboarding transaction leaves NOTHING behind on any refusal (asserting the ABSENCE of the
  tenant row, the clones, and the user — the DATA-1 hostile-caller shape).
- **The clone is proven equivalent, not assumed**: post-onboard, the tenant's role/grant matrix is
  compared row-for-row against the SYSTEM templates (exact set equality, both directions).
- **The end-to-end ignition proof, on the deployed stack**: a fresh deploy → operator creates a
  tenant via HTTP → the first admin's token resolves → that admin creates a second user and grants
  a role → the second user reads a governed surface their role permits and is 403'd from one it
  does not. The whole reason this slice exists, executed where P15 demands it (different
  assumptions than the unit tier); rides the existing `stack-proof` job.
- **Mutation battery in `scripts/mutants.toml` group `onboard-1`** (P18: committed, declared).
- **Migration `0067`**: ENT-074 + the mint, literal `DELIVERS`, `alembic check` clean, the
  identifier-length sweep, downgrade honesty.
- Gates at a frozen tree, exit codes quoted (P14); CI to green; P16 at the PR boundary.

## 5. Non-goals

- No self-service signup, invitations, or email; no SCIM/directory sync; no MFA policy surface.
- No tenant deletion (a governed-evidence question — every IA table cascades — deferred with
  trigger: the first real offboarding request).
- No billing/quota/plan concepts.
- No change to the OIDC verifier or token shape (SSO-1's boundary is untouched; ONBOARD-1 adds an
  exists-check behind it).
- The SYSTEM tenant gains exactly ONE new thing: the operator principal (OQ-2 sub-fork). No new
  hybrid tables; the 7-table set is closed and stays closed.
