# ONBOARD-1a slice record — the platform got an ignition

**Wave 17, slice 0a.** Remit: `onboard_1a_remit.md`. Branch `onboard-1a-provisioning`.
Design authority: `onboard_1_decision_record.md` v3 + the 2026-08-09 ratification (OQ-ONB-1…10 all
as recommended).

**Every claim below was checked against the diff before this file was written** (P1 ledger 7).

## 1. What shipped

A tenant can now be created over HTTP, and it is born with its role clones and a first
administrator who can authenticate. Before this slice the platform had 251 API paths, 289
RBAC-protected operations, and no way to create the tenant, user or role any of them requires.

| Artifact | Where |
|---|---|
| ENT-074 `tenant` (PLATFORM-GLOBAL, three-arm status) | `irp_shared/tenancy/models.py`; migration `0067_tenant_registry.py` |
| The PLATFORM entitlement catalog + `platform_operator` | `irp_shared/entitlement/platform_catalog.py` |
| The onboarding act (two RLS contexts, one transaction) | `irp_shared/tenancy/service.py` |
| The boundary exists-check (dialect-gated) | `irp_shared/tenancy/boundary.py`, wired in `deps.py` |
| The SYSTEM-router fence | `deps.py` (`SYSTEM_TENANT_ALLOWED_PREFIXES` + `_assert_system_principal_is_fenced`) |
| `POST /tenants` | `irp_backend/api/tenants.py` |
| Clone derivations + `CLONED_TEMPLATES` + `tenant_admin` | `irp_shared/entitlement/bootstrap.py` |
| Suites (30 tests) | `test_tenancy.py` (15), `test_tenancy_pg.py` (9), `test_tenants_endpoint.py` (6) |

## 2. Gates, with captured exit codes (P14)

Measured at the frozen tree, after the head-pin fold — not carried forward.

| Gate | Result |
|---|---|
| `make check-all` (both tiers) | **`CHECK_ALL_EXIT=0`** |
| Full-PG battery (schema reset → head `0067`) | **`PG_PYTEST_EXIT=0`** |
| `alembic upgrade head` / `alembic check` | **`UPGRADE_EXIT=0`** / **`ALEMBIC_CHECK_EXIT=0`** |
| Mutation battery, group `onboard-1a` | **`MUTATION_EXIT=0`** — 12/12, each kill reporting the test count that ran |

**`CHECK_ALL_EXIT=2` twice before it was 0**, both quoted: once on formatting, once on **23
failures** — 21 hand-mirrored migration-head pins plus two gates correctly refusing this slice's
own novelties (see §4). The head-pin recurrence is the hazard recorded at the Wave-16 close as a
slice candidate, firing on the very next migration exactly as predicted.

## 3. The design's load-bearing choices, and what proves each

- **Platform authority lives in a separate catalog.** `tenant.create` is in
  `PLATFORM_PERMISSIONS`, held by a `platform_operator` role that is not in `ROLE_TEMPLATES` and
  never cloned. Proven by `test_no_cloned_role_holds_a_PLATFORM_code` — asserted against the
  DATABASE after an onboarding, because the constants were never what leaked — and by mutant
  **N-A1**, which mints the code into the tenant catalog and is KILLED.
- **The clone reads the DATABASE, not the constant.** A revoked SYSTEM template grant must not
  reappear in a new tenant (the class migration `0066` closed, arriving through a second door).
  Proven with its discriminating pair: the same code lands for a tenant onboarded BEFORE the
  revocation. Mutant **N-A3** restores constant-sourcing and is KILLED.
- **The SYSTEM templates are read BEFORE the re-arm.** `role` is FORCE-RLS, so reading after would
  return nothing on PostgreSQL and produce a tenant with no roles — while every SQLite test stayed
  green. Mutant **N-B3** does exactly that and is KILLED *by the PG suite only*.
- **The fence.** A SYSTEM principal reaches provisioning and nothing else, proven with the
  positive control that the same principal IS admitted on `/tenants` (without which "refused
  everywhere" is equally consistent with a principal that cannot authenticate at all).
- **Nobody is stranded.** `0067` backfills the SYSTEM row and every existing `app_user.tenant_id`
  except the reserved proof literals, each stamped with provenance.
- **Both gates that would have missed the platform catalog were extended in the same commit** —
  the P17 delivery test and the P11 route census both walked `ALL_CODES` only, and a platform code
  was proven by execution to escape both silently.

## 4. Defects found, and by what

### By the mutation battery — in the HARNESS, not the slice

The first battery run reported **9/12 with three survivors**, and all three were defects in the
harness itself:

1. **PG-tier mutants were phantom-green.** The harness strips `IRP_TEST_DATABASE_URL` (so a
   battery is runnable mid-fold without a database), which made `test_tenancy_pg.py` **skip
   entirely** — and pytest exits 0 for a fully-skipped run, which the harness read as a kill. The
   same false-green class the harness was built to prevent. Fixed two ways: a `needs_pg` opt-in,
   and a **zero-tests-ran floor** that reports any target running nothing as a SURVIVOR.
2. **The floor could not work, because the count was unreadable** — which led to (3).

### By that floor — a three-slice-old anomaly, root-caused

`pyproject.toml` sets `addopts = "-q"`. Passing `-q` again makes it **`-qq`, which suppresses
pytest's summary line entirely.** That is the "pytest's final summary line is missing from the
full-PG logs" anomaly carried open since RPT-1 and re-recorded at REPRO-1 and the Wave-16 close,
where gate counts had to be recovered by counting progress characters **by hand, three times**.
Diagnosed in one command once something needed the number for a decision rather than a report.
The harness no longer passes `-q`; the finding is recorded in memory as a repo-wide capture rule,
because hand-counting is exactly the step where a number stops being evidence (P14).

### By `make check-all` — two gates refusing this slice's novelties, both correctly

- **`tenant_admin` is a template with no codes** (its verbs are 1b's), which
  `test_role_templates_reference_known_codes` rejects — rightly: an assignable role that grants
  nothing reads as authority. Now an EXACT exemption list with the reason and the slice that
  fills it, plus a **stale-entry test** that fails when ONBOARD-1b lands and the entry is not
  deleted.
- **`test_tenancy_pg.py` ran in no CI step**, which `test_ci_pg_coverage` refused. A CI step was
  added — and its comment records why the suite creates its own constrained role.

### By the suite's own floor — the PG suite was testing with RLS switched off

`test_tenancy_pg.py`'s first draft connected as the default `irp` login, which is the container
**superuser: BYPASSRLS**. Every RLS assertion in it would have passed with row-level security
disabled — the control bypassed by the connection testing it. Caught only because one test
asserted `rolbypassrls IS FALSE` about its own connection and went red. The suite now runs as the
constrained `irp_app` role, and that assertion stays as the floor.

## 5. Carries, with triggers (P19: a slice or a mechanical condition, else a decision)

| Carry | Detail | Trigger |
|---|---|---|
| **(a) The tenant-local admin surface** | 1a ships a tenant whose first admin exists and can authenticate but manages nobody: `user.manage`/`role.assign`/`user.view`/`role.approve`, the four-eyes lifecycle (ENT-075), the orphan-proof enforcement paths and the UI are all 1b | **ONBOARD-1b** — sequenced under the same gate, no re-ratification |
| **(b) A created tenant does not TICK** | `IRP_TENANT_IDS` is deploy config by CAD-1's ratified decision. The API response and the runbook both state the operator step verbatim | **REPRO-2** (the schedule write path), by name |
| **(c) 22 hand-mirrored migration-head pins** | 21 test-side + 1 infra, stale on every migration. Recorded at the Wave-16 close as a candidate; it fired again here on the very next migration | A slice that collapses them to ONE shared assertion — **unhosted, and therefore a DECISION at the Wave-17 close** rather than a carry (P19) |
| **(d) The deployed ignition proof** | The remit's stack-proof arm (operator creates a tenant over HTTP on the deployed stack → the first admin resolves) is NOT in this commit — the PG and endpoint tiers prove the layers, the deployed arm proves them composed | **This slice's own PR**, before merge — or explicitly re-hosted at the ONBOARD-1b gate if it does not land here |

## 6. Non-goals honored

No tenant-local admin verbs; no `tenant.suspend` setter (status enforced, setter deferred); no
tenant deletion; no self-service signup/SCIM/MFA; no OIDC verifier change; the hybrid 7-table set
unchanged; **no BYPASSRLS anywhere** — asserted by a test that fails if the connection has it.


## 7. The different-engine review fold (Fable, 2026-08-09)

The build was gated, committed (`9ba9dc5`) and STOPPED per the standing pattern. The review found
**one BLOCKING-class record gap and three unpaid promises**, all folded here:

1. **BLOCKING — the build paid the code and skipped the LEDGERS.** The commit minted ENT-074, two
   audit codes, a platform permission and a role, and touched ZERO governance documents: no
   canonical-registry row (the exact RPT-1 pre-merge BLOCKING — "ENT-072 had no canonical registry
   row" — recurring one entity later), no SoD row (P11 requires it AT the mint), no audit-taxonomy
   mint record, no control-matrix rows, and the mint checklist the gate ratified into existence
   did not exist. All landed in this fold: the ENT-074 row (+ ENT-075 reserved), the SoD mint row
   + ROLE-ADM realization + §5C the mint checklist (CREATED), the `TENANT`/`USER` taxonomy family
   row with the split-chain design stated, CTRL-035/036 **Implemented** on OBSERVED evidence and
   CTRL-037 **Planned, hosted at ONBOARD-1b**, CTRL-025 hosted note.
2. **Remit outcome 11 was unpaid**: operator seeding. Now in the deploy PREPARE step
   (`seed_platform_operator`, idempotent, env-driven, loud no-op when unset) with its unit test.
3. **Carry (d) was unpaid**: the deployed ignition proof. Now `infra/deploy/prove_onboarding.sh`
   + a `stack-proof` CI step — **executed locally first: `IGNITION_EXIT=0`**, every arm green:
   tenant created over HTTP by the env-seeded operator; the first admin RESOLVES (403 =
   permission-refused, not boundary-refused — the correct 1a expectation, asserted as such);
   unregistered-tenant 401; the SYSTEM fence 401; the tenant-admin escalation 403; five roles
   cloned in the DATABASE with `ops`/`platform_admin` absent.
4. **The promised fence CENSUS did not exist** (the remit's proof list named it; only two
   example-based tests shipped). Now `test_system_fence_census.py`: the allowed surface is
   EXACTLY the provisioning router, every prefix matches a real route (dead scope fails), and the
   walker carries its P6 floor.

One incidental: the proof's first run failed on `auth0|`-style subjects — the `|` breaks the
dot-sourced env file. Subjects in deploy env vars are pipe-free by convention now, noted in the
proof script.
