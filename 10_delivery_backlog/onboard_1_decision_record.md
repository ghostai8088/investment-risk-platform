# ONBOARD-1 decision record — the platform gets an ignition

**Wave 17, slice 0.** Branch `onboard-1-planning`. Ratified as the wave opener at the Wave-16 close
(**D3**) on the review's headline finding: **251 API paths — 289 RBAC-protected operations plus 2
deliberately anonymous (`/health`, `/version`) — and no way to create the tenant, user, or role
any of them requires.** Every deployment that has ever existed was seeded by a demo or proof
script.

**Status: CLOSED 2026-08-11 — RATIFIED 2026-08-09 (AskUserQuestion, four questions, ALL as recommended) and SHIPPED as PRs #191 (`888e1ec`, 1a — THE IGNITION) + #192 (`7761cf1`, 1b); ENT-074 + ENT-075; migrations `0067`/`0068`.** *Terminal stamp added at the Wave-17 close; the closure gate could not see this record until its parser was repaired the same day.*
OQ-1A + OQ-2A (registry + operator, the three-part invariant amendment + SYSTEM-router fence);
OQ-9A (four-eyes maker-checker with the bootstrap window — CTRL-025's implementation); OQ-6 as
recommended (DB-sourced clones; customer tenants get the four business templates + `tenant_admin`,
NOT `ops`, NOT `platform_admin`); OQ-8 split (ONBOARD-1a/1b under this one gate) + OQ-3/4/5/7/10
as recommended. The CLAUDE.md invariant amendment executed at this gate (the REF-1 precedent).
**NEXT = the ONBOARD-1a implementation plan.** Two verifier passes ran (P15's different-context bar):
pass 1 (5 lanes, 40 agents) broke v1 at `7a61303` **11-BLOCKING deep** — including a structural
trap FIVE lanes converged on independently (v1's own recommendations, composed, handed
`tenant.create` to every customer tenant). Pass 2 (3 lanes, 23 agents) over v2 at `2b4296b`
confirmed the structural folds HELD under attack (the escalation closure, the backfill, all four
orphan paths, the global-class census — proven exactly complete by an executed 86-table walk) and
found **2 BLOCKING + 13 MATERIAL in v2's own new machinery**, all folded here. The two-pass
ledger is §7. The yield curve: 49 findings → 20, with round 2's blockers confined to machinery
round 1 forced into existence — convergent, and the residual tail is implementation-plan
territory. Nothing here is self-ratified.

---

## 1. The recon facts (verifier-re-derived; both passes' corrections in place)

| # | Fact | Evidence |
|---|---|---|
| R1 | **No tenant table exists.** `tenant_id` is a free-floating GUID | 50 migration files swept; no `class Tenant` |
| R2 | **RLS context is armed from the caller's token claim** and `set_tenant_context` already re-arms mid-request today — the route-level re-arm is an existing seam | `deps.py:104–170`; pass-1 EXECUTED the check-under-SYSTEM-then-re-arm-and-write flow on PG 16 with the real 0001 policy DDL: works in ONE transaction, no BYPASSRLS |
| R3 | **The template-cloning code promised since P0.5 does not exist** | `bootstrap.py:6`; no clone code |
| R4 | **Only demo/proof scripts create users** (`DEMO_TENANT_ID`/`PROOF_TENANT`) | five non-test `AppUser(` sites |
| R5 | **ROLE-ADM is described but unminted**: "User/role admin; **cannot** approve own entitlement requests **or edit audit**" | `entitlement_sod_model.md:51`, quoted whole |
| R6 | **SIX role templates exist** (`platform_admin`, `ops`, `data_steward`, `risk_analyst_1l`, `risk_manager_2l`, `auditor_3l`) | executed listing |
| R7 | **The uuid5 derivations do NOT namespace by tenant** (`role_id` hardcodes `SYSTEM_TENANT_ID`; `role_permission_id` has no tenant component) — cloning requires NEW derivations | `bootstrap.py:537–542`, executed |
| R8 | **`platform_admin` is `list(ALL_CODES)`**; `sync_catalog` materializes grants solely from `ROLE_TEMPLATES` | `bootstrap.py:255`; `sync.py` |
| R9 | **The worker's tenant membership is deploy-time env config** (`IRP_TENANT_IDS`; CAD-1 ratified the config-driven supervisor — paraphrase, not a quote) — a created tenant does not TICK until an operator edits the deployment | CAD-1 record; supervisor source |
| R10 | **The deployed stack runs `AUTH_MODE=dev_header`**; Keycloak is behind an opt-in profile the stack-proof job does not enable | compose + CI workflow |
| R11 | **`grant_role` refuses a cross-tenant actor**; `audit_event` is FORCE-RLS tenant-scoped, `chain_id == tenant_id`; `record_event` selects the chain from its `tenant_id` argument, genesis-anchors an empty chain automatically, and takes a per-chain advisory lock — pass 2 traced two-chains-in-one-transaction as well-defined under the FROZEN audit service, with SYSTEM-first lock order | `audit/service.py:35–136`, executed trace |
| R12 | **Nothing refuses a SYSTEM-tenant token claim today** — it 401s only because no SYSTEM `app_user` exists; the day the operator is seeded, any IdP-signed SYSTEM claim resolves | pass 1 (L1-3) |
| R13 | **The demo tenant already holds roles named with TEMPLATE CODES** (`risk_manager_2l` etc., random ids) under `uq_role_tenant_id` — a backfill-clone collides unless the rule says otherwise; and `PROOF_TENANT` rows exist on any DB the deploy proofs ever touched | pass 2 (B1/B4) |
| R14 | **The shipped P17 delivery gate and P11 route census walk `ALL_CODES` only** — a platform-catalog code silently ESCAPES both unless they are extended in the SAME commit that creates the catalog; and a `DELIVERS` tuple naming a platform code REDDENS the stale-check until the extension lands | pass 2, EXECUTED (B8/B10 + the wf2 probe) |

## 2. The shape (v3)

The two constraints from pass 1, now with pass 2's mechanics folded:

- **C1 (the ALL_CODES trap):** platform-scope authority lives OUTSIDE the tenant catalog — a
  separate `PLATFORM_PERMISSIONS` constant (first member `tenant.create`), a system-only
  `platform_operator` role that is **not** in `ROLE_TEMPLATES` and never cloned, and a
  disjointness census asserted against the DATABASE post-onboarding. **Delivery of the platform
  catalog itself is named** (pass-2 A-2): migration `0067` inserts the platform permission, role
  and grant rows inline, and `sync_catalog` gains a platform arm (kept out of `ROLE_TEMPLATES`
  materialization) so future platform codes have the same sync story as tenant codes. **The P17
  delivery gate and the P11 route census are extended to walk BOTH constants in the SAME commit**
  (R14 — the ordering is pinned: catalog + gate-extension + `DELIVERS` land atomically or the
  gates themselves red).
- **C2 (nobody stranded):** ENT-074 `tenant`, platform-global, EV class, three-arm status
  (`SYSTEM`/`ACTIVE`/`SUSPENDED`, total-enumeration CHECK). Migration `0067` backfills: the
  SYSTEM row, and a row for every DISTINCT `app_user.tenant_id` **except the reserved proof
  literals** (`PROOF_TENANT` and any source-named synthetic ids — pass-2 B4: backfilling proof
  residue as ACTIVE manufactures wrong facts), each backfilled row stamped
  `provenance='0067_backfill'`. **The backfill-clone collision rule** (pass-2 B1, R13): the clone
  step SKIPS any template whose code already exists in that tenant (`uq_role_tenant_id` honored;
  the demo tenant's ad-hoc roles are untouched and NOT upgraded), and the clone-equivalence proof
  is scoped to onboarding-created tenants — stated, not discovered at build time.

Three layers:

1. **ENT-074 `tenant`** (above), plus the **intentionally-global-class census**: every
   no-`tenant_id` table sits on an explicit allow-list with a reason — pass 2 executed the walk:
   the population is exactly {`permission`, `role_permission`, `role_permission_revocation`} + the
   new `tenant`.
2. **The onboarding act**, one transaction, in the ORDER pass 2 corrected (A-3/B7 — the SYSTEM
   template rows are FORCE-RLS and must be read under the SYSTEM arm): check `tenant.create` AND
   materialize the SYSTEM template rows in memory under the SYSTEM context → insert the `tenant`
   row + the SYSTEM-chain audit event → re-arm to the new tenant → write the clones, the first
   admin, the seed grant + the new tenant's genesis-anchored audit events (R11). The
   duplicate-code refusal is a **pre-check, savepoint-wrapped** so the poisoned-transaction path
   never reaches the caller's session (pass-2 A-12: the savepoint's job is the check, not the
   insert). **The audit-code mint is named** (pass-2 A-4): `TENANT.CREATE`, `USER.PROVISION`,
   `ROLE.GRANT_REQUEST`/`ROLE.GRANT_APPROVE` (OQ-9) — an R-07 act inside this same gate, with §4
   proofs asserting both chains' events and `verify_chain` green on each.
3. **Tenant-local user/role administration** under `tenant_admin` (the SEVENTH template), with
   OQ-4's orphan-proof invariant and OQ-9's four-eyes lifecycle.

## 3. The forks (OQ-ONB-1…10) — self-contained (pass-2 C6: every OQ carries its options)

*Dependency note (pass-2 C10): OQ-1 and OQ-2 are a pair — OQ-1's `SYSTEM` status arm exists so
OQ-2A's operator passes the exists-check. Ratifying OQ-2≠A converts that arm to a plain registry
row for the template holder. The rest are independent.*

### OQ-ONB-1 — `tenant` as a first-class entity
| Option | Consequence |
|---|---|
| **A. ENT-074, PLATFORM-GLOBAL, EV, three-arm status, 0067 backfill with proof-literal exclusions + provenance stamps, the global-class census** *(recommended)* | Provisioning has a subject; the boundary can refuse unknown/suspended tenants; deployed tenants keep working; the hybrid 7-table set is untouched |
| B. Tenants stay implicit (a UUID convention) | ONBOARD-1 shrinks to user-seeding; no registry, no boundary refusal, no suspension — the status quo with paperwork |
| C. A SYSTEM-tenant hybrid row | Extends the closed hybrid set (AD-013-R3) for nothing A doesn't do; tenants don't read each other's registry rows |

### OQ-ONB-2 — Tenant-creation authority (the crux)
| Option | Consequence |
|---|---|
| **A. A SYSTEM-tenant `platform_operator` principal holding `tenant.create` from the PLATFORM catalog, checked in its own context; the route re-arms inside the single onboarding transaction** *(recommended)* | Governed, auditable, HTTP-reachable; the two-arm flow is EXECUTED-proven on PG (R2). **The invariant amendment, whole:** (i) the guarded cross-tenant transaction, (ii) the first standing authenticatable SYSTEM principal (R12), (iii) the SYSTEM registry row. **The R12 mitigation ships in-slice:** SYSTEM-tenant principals are refused on every router except provisioning (a fence with its own census over the full 251-path surface — pass 2 confirmed the walker precedent makes this buildable and non-vacuous) |
| B. Out-of-band CLI only | Provisioning stays outside the governed surface — no RBAC, no audit, no refusals; the demo-script status quo |
| C. A signed bootstrap token | A second auth system to build and rotate; BR-10 adjacency; strictly weaker than A |

**Operator seeding sub-fork (pass-2 B5 — a migration is the wrong home: an aborting migration
wedges `upgrade head` for every non-provisioning deploy, and env-var-dependent migration output
breaks reproducibility):** **(a) recommended** — an idempotent, `DELIVERS`-style-documented step
in the deploy prepare path (the `seed_system_reference` pattern `deploy.sh` already proves),
reading the subject from a deploy-time env var; absent var = loud no-op, stated in the deploy
output. (b) a documented manual runbook step.

### OQ-ONB-3 — The first user of a new tenant
| Option | Consequence |
|---|---|
| **A. Supplied in the create request (OIDC subject + display name), seeded as the tenant's admin inside the onboarding transaction; the operator is NOT a member** *(recommended)* | The tenant is born with one admin who provisions everyone else; the seed grant is written directly by the onboarding service under the new tenant's arm with the operator as audit actor — `grant_role`'s cross-tenant refusal (R11) stays intact for every other path, and the refusal's census carries the exception row with reason |
| B. Born empty; a second cross-tenant call adds the first user | Two cross-tenant acts; a window where a tenant exists that nobody can enter |

### OQ-ONB-4 — `tenant_admin` and the ORPHAN-PROOF invariant
**A (recommended): mint `tenant_admin` as the SEVENTH template** — user/role admin verbs only.
The invariant, over ALL paths: **a tenant must at all times have ≥1 currently-valid, ACTIVE-user
admin** — enforced identically against role revocation, role END-DATING (the count is over grants
valid NOW), user DEACTIVATION including self, and concurrently (a per-tenant advisory lock around
the count-check, the MG-2 precedent). Each path's refusal is a named test with its P18 positive
control. B (first user gets the `platform_admin` clone) hands every customer's first user every
verb including 3L reads — rejected as in v1.

### OQ-ONB-5 — The mint
**Tenant catalog** (enters `PERMISSIONS`/clones): `user.manage`, `role.assign`, `user.view`, plus
OQ-9's `role.approve` if OQ-9=A. Holders: `tenant_admin` + `platform_admin` (all); **`auditor_3l`
EXCLUDED from `user.view`** — an entitlement roster carries `external_subject` and
`display_name`, person-identifying data in the class every proprietary-identity read has excluded
the 3L auditor from (a **flip from v1**, which recommended inclusion on the schedule.view
precedent; pass 1 L3-8 showed that mis-classed the read). A redacted auditor roster is NOT minted
(deferred — §5). **Platform catalog** (C1): `tenant.create` only. `tenant.suspend` is NOT minted;
the `SUSPENDED` arm ships boundary-ENFORCED (suspended tenants' tokens refused, tested) but
setter-less (deferred — §5). P11 in full; the audit-code mint rides (§2); migration `0067`
carries `DELIVERS` for tenant-catalog codes and the platform catalog's parallel delivery census
lands in the same commit (R14).

### OQ-ONB-6 — Clone semantics
**A (recommended):** clone **FROM THE DATABASE's SYSTEM template rows** (not the constant — the
constant would resurrect admin-revoked grants, the exact class migration `0066` closed; proven in
§4 by the revoked-grant interplay test). NEW derivations `tenant_role_id(tenant_id, name)` /
`tenant_role_permission_id(tenant_id, name, code)` (R7). **The template-set sub-fork pass 2
demanded (A-7): which templates do customer tenants get?** **Recommended: the four business
templates + `tenant_admin` — `ops` and `platform_admin` are NOT cloned.** `ops` holds only
`ops.audit.verify`, consumed by the BYPASSRLS ops CLI with no HTTP consumer — cloning it hands
tenant admins a grantable code whose only use is a tool tenants never run. `platform_admin`'s
everything-bundle collapses every SoD partition the matrix builds (register/validate,
respond/review, manage/approve) inside a customer tenant; a tenant wanting a super-user grants
multiple roles explicitly and visibly. (The SYSTEM tenant keeps both, unchanged.) Backfill-clone
collision rule per C2. Alternative (clone all seven): maximal continuity with the SYSTEM shape,
carries both objections. **Future-mint catchup:** the "delivery to existing tenants' clones —
named migration or explicit refusal with reason" row is added to the **mint checklist this gate
CREATES in `entitlement_sod_model.md`** (pass-2 C1: no such checklist exists today — this is a
creation, not an amendment; P11's text points at it), and `sync_catalog`'s report gains
`tenants_missing_code` so every future sync LOGS the gap. The log line alone is not claimed to be
mechanical enforcement (pass-2 A-9): the checklist row is the gate, the log is the tell.

### OQ-ONB-7 — Surface
| Option | Consequence |
|---|---|
| **A. API for everything; UI for the tenant-local Users & Roles screen only** *(recommended)* | The rare operator act needs no screen; the daily tenant-admin act gets one (the OPS-1 write-path precedent); bounded FE scope |
| B. API-only | "Reachable" means curl again — the finding this slice exists to close |
| C. Full UI incl. tenant creation | A screen for an audience of ~one; inflates slice 0 |

### OQ-ONB-8 — Sizing and the split (rebuilt: pass-2 C2/C3 — v2's trigger denominator didn't exist and its partition was incoherent)
**Sized L, and the default FLIPS to: plan as ONBOARD-1a/1b from the start, one gate (this one),
two slices.** Pass 2 is right that the OQ-9 lifecycle machinery (a request entity, MG-2-pattern
ordering) pushes the single-slice size past every comparator. The partition, redrawn so
dependencies travel together: **1a = the platform half** (OQ-1 registry + census, OQ-2 operator +
fence, OQ-3 first admin, OQ-6 clones, the `tenant_admin` MINT (OQ-4's role must exist for the
seed grant), migration `0067`, the deployed ignition proof through "first admin resolves") —
**1b = the tenant-local half** (OQ-5's admin verbs + routes, OQ-4's orphan-proof enforcement
paths, OQ-9's four-eyes lifecycle, OQ-7's UI, the remainder of the ignition proof). 1a alone
leaves tenant-local admin API-absent (the first admin exists but manages nobody) — stated so the
gate knows what 1a-without-1b ships. Alternative: one L slice, accepting the size risk.

### OQ-ONB-9 — SOD-04 four-eyes, framed as what it is: CTRL-025's first implementation (pass-2 C4)
`entitlement_sod_model.md` §7: "Four-eyes is mandatory for: … entitlement changes (SOD-04)";
CTRL-025 ("Entitlement changes maker-checked + audited") is Planned with no code. v1 contradicted
both; v2's fix had two holes pass 2 confirmed (the threshold exempted two-admin tenants; admin
DEACTIVATION escaped the flow entirely).
| Option | Consequence |
|---|---|
| **A. Maker-checker with a single-admin bootstrap window, threshold corrected, deactivation included** *(recommended)*: any entitlement-affecting act by an admin — grant, revoke, end-date, AND `user.manage` deactivation of a user currently holding `tenant_admin` (pass-2 B2) — is born `PENDING` when **≥1 currently-valid OTHER admin exists** (pass-2 B3: four-eyes engages the moment an approver exists, i.e. at two admins, not three), and requires a second admin's approval (`role.approve`; approver ≠ requester by principal id, the MG-3 pattern). With NO other admin, the act executes directly, stamped `direct_grant=true` on its audit event. **The machinery, named:** ENT-075 `entitlement_request` (IA append-only, the MG-2 ordering-key + per-item lock pattern, migration `0067`), the `role.approve` verb, the `ROLE.GRANT_REQUEST`/`ROLE.GRANT_APPROVE` audit codes, and CTRL-025 moves Planned → Implemented on the P9 bar (the refusal fires in §4). Ratifying A adds the bootstrap-window clause to `entitlement_sod_model.md` §7 | SOD-04 honored from the first moment an approver exists; every direct act is flagged evidence; CTRL-025 gets its host |
| B. Direct grants + self-grant refusal only; SOD-04 recorded as a ratified deviation | The matrix's four-eyes clause goes aspirational exactly where it first binds |
| C. Full four-eyes always (operator seeds TWO admins) | Every tenant pays double-ceremony forever; the operator names two humans where the request had one |

### OQ-ONB-10 — The ignition proof's auth mode + the exists-check's tier (rebuilt: pass-2 A-1/B6 — v2's tier rationale was backwards)
**The exists-check mechanism, stated as the fork it is:** the check is **dialect-gated** (the
`_lock_chain`/`sync_catalog` precedent: PG executes it, SQLite does not) — so the unit tier is
exempt **by mechanism, not by backfill accident**; the deployed and PG tiers enforce it for BOTH
auth modes (it lives behind `get_principal`, not inside the OIDC verifier). The gate is told
plainly: SQLite suites are structurally outside the boundary check's reach (the FK-1 lesson,
acknowledged). In-slice PG seeding paths (conftest fixtures that mint uuid4 tenants) gain
registry rows via a fixture helper — enumerated in the implementation plan, not discovered.
| Option | Consequence |
|---|---|
| **A. Deployed ignition proof under `dev_header` end-to-end + a token-minting PG/unit arm for the OIDC-specific refusals (unknown tenant, SYSTEM fence, suspended)** *(recommended)* | Every layer ONBOARD-1 builds is deployed-proven; the auth MODE is the one shared assumption with today's stack-proof, named as such (P15) |
| B. Enable the Keycloak profile in CI for this slice | Full OIDC deployed at the cost of standing up an IdP in the stack-proof job — a real scope expansion that would need its own sizing |

## 4. Proofs (P18; each refusal named with its positive twin)

- Unknown-tenant claim refused ↔ known admitted (BOTH auth modes, PG tier). SYSTEM claim refused
  on a data router ↔ admitted on provisioning (the fence census walks all 251 paths). Suspended
  refused ↔ active admitted. `tenant.create` denied to every tenant-catalog role incl. every
  CLONED `platform_admin` ↔ granted to the operator (the C1 census, against the DB). Self-grant
  refused ↔ second-admin approval lands. Four-eyes: PENDING born at ≥1 other admin ↔ direct at
  none, `direct_grant` stamped; deactivation-of-an-admin routes through the flow (B2's exact
  scenario). Last-admin refusals across all four orphan paths ↔ non-last succeed. Duplicate code
  refused with NOTHING persisted (absence asserted) ↔ fresh code lands everything.
- **Audit assertions** (pass-2 A-4): post-onboard, the SYSTEM-chain `TENANT.CREATE` event and the
  new tenant's genesis-anchored events both exist; `verify_chain` green on BOTH chains; the
  upgrade-a-POPULATED-DB test (backfilled tenants still authenticate; proof literals absent;
  provenance stamps present).
- **Clone equivalence**: post-onboard matrix == the DB's SYSTEM template rows at clone time
  (scoped to onboarding-created tenants — the collision rule excludes pre-existing ad-hoc roles);
  a tenant onboarded after a template-grant revocation lacks that grant (the `0066` interplay,
  executed).
- **The catalog-disjointness census** + the extended P17/P11 gates walking both constants (R14,
  same commit).
- **The deployed ignition proof** (OQ-10A) riding `stack-proof`.
- **Mutation battery**: group `onboard-1` in `scripts/mutants.toml` (P18) — the census matchers,
  the fence, the orphan invariant, the four-eyes threshold (mutating `≥1 other` back to `≥2
  other` must redden the two-admin test), and the clone source (constant-vs-DB must redden the
  revocation-interplay test).
- **Migration `0067`**: ENT-074 + ENT-075 + backfills + mint + `DELIVERS`; `alembic check`;
  identifier sweep; downgrade honesty (downgrade drops the registry: boundary refusal is lost,
  tenant data is not; stated).
- Gates at a frozen tree, exit codes quoted (P14); CI green; P16 at the PR boundary.

## 5. Non-goals and deferrals (each labeled with its P19 class — pass-2 C8: an external-human-event trigger is a ratified DEFERRAL DECISION, not a mechanical trigger, and is labeled as such)
- Self-service signup, invitations, email, SCIM, MFA: out of scope (decision, ratified here).
- Tenant deletion: deferred — **decision-class deferral**, revisited on the first real
  offboarding request (external event, loud and datable).
- `tenant.suspend` verb: deferred — decision-class, on the first operator suspension request;
  the status semantics ship enforced (OQ-5).
- Redacted auditor roster: deferred — decision-class, on a real 3L access-review requirement.
- Billing/quota/plans: out of scope.
- OIDC verifier/token shape: untouched.
- **The worker does not tick new tenants** (R9): `IRP_TENANT_IDS` stays config by CAD-1's
  ratified decision. The onboarding API response and the runbook both state the operator step
  verbatim; the scheduled-work gap carries with its P19 SLICE host: **REPRO-2** (the schedule
  write path), by name.

## 6. Blast radius (pass-2 C5: completed)
1. CLAUDE.md invariant: the three-part ONBOARD-1 clause (OQ-2).
2. `canonical_data_model_standard.md`: the PLATFORM-GLOBAL tenancy class; ENT-074 + ENT-075 rows.
3. `entitlement_sod_model.md`: `tenant_admin` minted (ROLE-ADM realized); the mint checklist
   **created** (with the delivery-to-clones row); SOD-04 §7 gains the bootstrap-window clause
   (OQ-9A); the template-clone set decision (OQ-6).
4. `09_compliance_controls/control_matrix_skeleton.md`: **CTRL-025 Planned → Implemented** (OQ-9,
   P9 bar); new rows for the boundary exists-check, the SYSTEM-router fence, and the orphan-proof
   invariant (control mints at the H-05 gate = this gate).
5. `04_data_model/audit_event_taxonomy.md`: the R-07 audit-code mint (`TENANT.CREATE`,
   `USER.PROVISION`, `ROLE.GRANT_REQUEST`, `ROLE.GRANT_APPROVE`).
6. The architecture-decision log: the AD row for the platform catalog + operator principal
   (AD-013 is NOT extended — no hybrid change; a new AD).
7. The intentionally-global-class census becomes standing (OQ-1).
8. Tier labels: OQ-1/2/4/5/6/9 are Tier-3 (this gate); OQ-3/7/10 are design confirmations;
   OQ-8 is sequencing.

## 7. The two-pass verifier ledger

**Pass 1** (over v1 `7a61303`): 5 lanes, 40 agents, 2.0M tokens; **11 BLOCKING + 23 MATERIAL
CONFIRMED after refute-by-default** (1 refuted, 2 downgraded — the headline counts quote the
POST-verification severities; pass-2 A-11 caught the v2 header's arithmetic gloss), 14 minors.
Clusters and folds: v2's §7 table, superseded by this section. Highlights: the five-lane ALL_CODES
convergence; the false uuid5/template-count/D1-vs-D3 facts; the SOD-04 contradiction; the
exists-check stranding SYSTEM and deployed tenants; the audit-chain silence.

**Pass 2** (over v2 `2b4296b`): 3 lanes, 23 agents, 1.5M tokens; **2 BLOCKING + 13 MATERIAL
CONFIRMED**, 2 refuted (whose "refutations" each demanded an explicit rule the record now states:
the backfill-clone collision rule and the proof-literal exclusions, R13), 3 downgraded, 13 minors.
Every confirmed finding's fold is inline above, tagged by id. What HELD under attack, executed:
the C1 escalation closure end-to-end incl. sync semantics; the C2 core; all four orphan paths;
the split-chain audit mechanics under the frozen service (R11); the global-class census's exact
completeness; the route-fence buildability; require_permission's indifference to the catalog
split; CI's fresh-deploy ordering.

**Convergence:** 49 → 20 verified findings, round 2's blockers confined to round-1-mandated new
machinery. The residual tail (fixture enumeration, exact checklist wording) is implementation-plan
territory, gated by the same P14/P16/P18 bars at build time.
