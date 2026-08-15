# Session Log: 09-08-2026 19:04 - wave16-closed-wave17-gated-onboard1a-merged-onboard1b-built

## Quick Reference (for AI scanning)

**Confidence keywords:** Wave-16 close, Wave-17 planning gate, P18, P19, P15 different-engine
trigger, P14 subagent clause, editorial pass, ONBOARD-1, ONBOARD-1a, ONBOARD-1b, ENT-074 tenant,
ENT-075 entitlement_request, PLATFORM_PERMISSIONS, platform_operator, SYSTEM-router fence,
tenant boundary check, dialect-gated, migration 0066/0067/0068, four-eyes, SOD-04, CTRL-025,
CTRL-035, CTRL-036, CTRL-037, orphan-proof invariant, advisory lock, mutation battery,
needs_pg, zero-tests-ran floor, `-qq` summary suppression, BYPASSRLS superuser, verifier pass,
refute-by-default, PR #187, #188, #189, #190, #191, 9257514, d4e3692, 888e1ec, 85cecc6

**Projects:** investment-risk-platform (multi-tenant governed investment-risk platform)

**Outcome:** Wave 16 closed and Wave 17 opened — ONBOARD-1 ratified after two adversarial verifier
passes (63 agents), ONBOARD-1a merged (the platform can now create tenants over HTTP, proven on the
deployed stack), and ONBOARD-1b built to the gate (four-eyes entitlement changes + the orphan-proof
invariant), with three merges landed (#187, #189, #190, #191) and 1b awaiting its different-engine
review.

---

## Decisions Made

- **Wave-16 close gate (4 questions, all as recommended):** ONBOARD-1 as Wave-17 slice 0; `report.*`
  holder sets ratified as shipped; the mint-reachability rule ratified **with a mechanical gate +
  the revocation fix** (became P17); the alarm fail-open fixed in a close fold.
- **Wave-17 planning gate (3 questions, all as recommended):** sequence ONBOARD-1 → ALERT-1 →
  REPRO-2 → RPT-3 with TS→7 on a mechanical trigger (roadmap Part 2.19); **D5 = P19** (a carry names
  a sequenced slice or a mechanical trigger, else it is a DECISION at deferral time); **D6 = P18**
  (a verification harness is itself a control: positive controls for its preconditions, and any
  harness cited as governed evidence is COMMITTED) plus the **P15 different-engine trigger**, the
  **P14 subagent-admissibility clause**, and the **editorial reconciliation pass**.
- **The editorial pass found two live contradictions:** the Prohibited list still forbade
  "committing/pushing without explicit approval" (pre-grant text) and the operating-model header
  still named "opening + merging every PR" as a USER control point (pre-extension text). Both had
  contradicted the 2026-07-12/14 autonomy grant for months. Reconciled with the contradiction named
  in place, and an index of all standing rules (P1–P19 + 12 conventions) added.
- **ONBOARD-1 gate (4 questions, all as recommended):** ENT-074 registry + platform-operator
  authority with an explicit three-part CLAUDE.md invariant amendment; four-eyes maker-checker with
  a single-admin bootstrap window (= CTRL-025's implementation); DB-sourced clones with customers
  receiving four business templates + `tenant_admin` but NOT `ops`/`platform_admin`; split into
  ONBOARD-1a/1b under one gate.
- **The CLAUDE.md invariant was AMENDED at the ratifying gate** (the REF-1 precedent) rather than
  lawyered around: the three-part ONBOARD-1 clause (the guarded cross-tenant onboarding transaction,
  ONE standing authenticatable SYSTEM principal, the SYSTEM registry row). Hybrid table set
  unchanged at seven; no BYPASSRLS anywhere.
- **Platform authority lives in a SEPARATE catalog** (`PLATFORM_PERMISSIONS` + never-cloned
  `platform_operator`), because minting `tenant.create` normally composes into "every customer
  tenant can create tenants" via ALL_CODES → platform_admin template → clone.
- **`tenant_admin` shipped EMPTY at 1a** (role needed for the seed grant; verbs need routes), on an
  exact exemption list with a stale-entry twin — which forced the exemption's deletion at 1b.
- **`auditor_3l` EXCLUDED from `user.view`** — a flip from the first draft. An entitlement roster
  carries `external_subject`/`display_name` (person-identifying), the class every
  proprietary-identity read withholds from the 3L auditor. The schedule.view precedent does not
  apply (schedule rows carry no identity).
- **Four-eyes threshold is "≥1 OTHER admin"**, not "≥2 other" — four-eyes engages the moment an
  approver exists (two admins), which is where SOD-04 first binds.
- **`role.approve` sits on the SAME role as the maker verbs** (MG-3 pattern): the gate is
  person-level (approver ≠ requester by canonicalized principal id), not role-level.
- **Approval APPENDS a resolution row** (`resolves_request_id`), never mutates — the breach_action
  lifecycle shape, forced by ENT-075's append-only trigger.
- **O-D4 mutant REMOVED with its reason recorded** rather than left as a permanent survivor:
  migration-DDL mutants are unmeasurable by a battery that runs against an already-migrated
  database.

---

## Key Learnings

- **Composed-correct steps produce an incorrect whole.** ONBOARD-1's first design draft was broken
  11-BLOCKING deep, and the finding FIVE independent verifier lanes converged on was three
  individually-correct steps that together handed `tenant.create` to every customer tenant. No
  single review step was wrong; the composition was. Structural separation (a different constant, a
  non-template role, a DB-level census) beats care.
- **A pass that EXECUTES refutes and confirms; a pass that reads only argues.** The verifier passes
  executed PG-16 probes, an 86-table ORM walk, and gate probes — refuting some of their own findings
  and confirming others by execution.
- **Read verifier "refutations" for what they ASK, not just their verdict.** Two pass-2 refutations
  were really demands for explicit rules (the backfill-clone collision rule, proof-literal
  exclusions) — both became ratified design.
- **The different-engine pattern held for the 5th and 6th consecutive time.** At 1a the second
  engine found the build had paid the CODE and skipped the LEDGERS — not a code defect but a claims
  defect, which same-engine review structurally misses.
- **PostgreSQL catches what SQLite cannot, repeatedly and expensively.** At 1b: approval mutating an
  append-only row (25 green SQLite tests, refused outright by the trigger); the two-context GUC
  ordering; the concurrency race.
- **A test's own floor is what catches a wrong-reason pass.** The concurrency test's floor ("neither
  approval was REFUSED ⇒ this proves nothing about the lock") caught both threads erroring rather
  than serializing.
- **Choose the operation the race actually lives in.** Two admins concurrently REQUESTING each
  other's revocation proves nothing — four-eyes already serializes it into a second phase. The race
  is in concurrent APPROVALS.
- **One clock per operation.** `_four_eyes_required` read wall-clock while the orphan check honored
  the caller's `now` — two controls in one module answering "who are the admins?" differently.
- **A migration that live-imports a mutable constant is not stable.** Filling `tenant_admin`'s
  template at 1b retroactively broke migration 0067, which had shipped green.
- **Hand-mirrored global facts recur on schedule.** 21 test-side migration-head pins went stale at
  0066, again at 0067, again at 0068. Recorded as an unhosted DECISION for the Wave-17 close.
- **A green battery is not a green tree** (its baseline is scoped to its mutants' targets), and a
  fully-SKIPPED suite exits 0 — so "exit 0" alone cannot distinguish a kill from a no-run.

---

## Solutions & Fixes

- **The `-qq` root cause (a three-slice-old anomaly).** `pyproject.toml` sets `addopts = "-q"`;
  passing `-q` again makes `-qq`, which **suppresses pytest's summary line entirely**. That is why
  full-PG gate counts had been recovered by hand-counting progress dots since RPT-1. Fix: never pass
  `-q` when capturing gate output.
  ```
  pytest --tb=no <target>      -> "15 passed in 0.83s"
  pytest --tb=no -q <target>   -> progress dots only
  ```
- **Battery harness hardened (P18):** `needs_pg` opt-in (PG-tier mutants keep `IRP_TEST_DATABASE_URL`)
  + a **zero-tests-ran floor** reporting any target that ran nothing as a SURVIVOR.
- **PG suites must run as the constrained role.** The default `irp` login is the container
  **superuser (BYPASSRLS)** — every RLS assertion would pass with RLS switched off. Fix: the
  `irp_app` NOSUPERUSER/NOBYPASSRLS pattern, with a `rolbypassrls IS FALSE` floor.
- **Migration 0067's grant insert existence-guarded** (was colliding on `pk_role_permission`).
- **The proof seeds register their tenant** (`register_proof_tenant`) — the 0067 backfill excludes
  `PROOF_TENANT` by design, and the boundary check refuses unregistered tenants; the fix preserves
  both by making registration an explicit gated act.
- **The deploy proof's migration-head literal → DERIVED** from `alembic heads` with an
  exactly-one-head floor.
- **Constrained-role privilege list extended with `tenant`** (read on every authenticated request).
- **`scripts/mutation_battery.py` + `scripts/mutants.toml`** committed as the artifact four Wave-16
  batteries had lacked.

---

## Files Modified

**Standing rules / governance**
- `docs/project_memory/claude_operating_instructions.md`: P18, P19 added; P15 different-engine
  trigger; P14 subagent-admissibility clause; standing-rules INDEX; Prohibited list and
  operating-model header reconciled to the autonomy grant.
- `CLAUDE.md`: the three-part ONBOARD-1 invariant clause.
- `10_delivery_backlog/delivery_roadmap.md`: Part 2.19 (Wave-17 sequence) + amendment rows.
- `docs/project_memory/current_state.md`: truth blocks for each close/gate/merge.

**Wave-16 close fold (PR #187 = `9257514`)**
- `packages/shared-python/src/irp_shared/reproduction/service.py`: alarm fail-open fixed
  (row-scoped, fails closed toward alarming, `alarm_channel_health`); ceiling checked before the
  poisoned skip (the review's BLOCKING).
- `packages/shared-python/src/irp_shared/entitlement/sync.py` (new): ONE catalog-sync implementation
  consulting the revocation ledger.
- `packages/shared-python/src/irp_shared/entitlement/models.py`: `RolePermissionRevocation`.
- `migrations/versions/0066_entitlement_revocation.py` (new).
- `packages/shared-python/tests/test_entitlement_mint_delivery.py` (new): P17's DELIVERS gate.
- `scripts/mutation_battery.py`, `scripts/mutants.toml` (new).
- `infra/deploy/prove_reproduction.sh`: derived migration head.

**ONBOARD-1a (PR #191 = `888e1ec`)**
- `packages/shared-python/src/irp_shared/tenancy/{models,service,boundary}.py` (new): ENT-074, the
  two-context onboarding act, the dialect-gated boundary check.
- `packages/shared-python/src/irp_shared/entitlement/platform_catalog.py` (new).
- `apps/backend/src/irp_backend/api/tenants.py` (new); `deps.py`: boundary + SYSTEM-router fence.
- `migrations/versions/0067_tenant_registry.py` (new).
- `packages/shared-python/src/irp_shared/deploy/prepare.py`: `seed_platform_operator`.
- `infra/deploy/prove_onboarding.sh` (new) + its `stack-proof` CI step.
- `04_data_model/canonical_data_model_standard.md` (ENT-074 row), `06_security/entitlement_sod_model.md`
  (mint row + §5C mint checklist CREATED), `04_data_model/audit_event_taxonomy.md` (TENANT/USER),
  `09_compliance_controls/control_matrix_skeleton.md` (CTRL-035/036/037).

**ONBOARD-1b (committed `85cecc6`, not yet reviewed/pushed)**
- `packages/shared-python/src/irp_shared/entitlement/request_models.py` (new): ENT-075.
- `packages/shared-python/src/irp_shared/entitlement/admin_service.py` (new): four-eyes + orphan
  invariant + advisory lock.
- `apps/backend/src/irp_backend/api/tenant_admin.py` (new): 8 routes.
- `migrations/versions/0068_entitlement_request.py` (new).
- `packages/shared-python/tests/test_entitlement_admin{,_pg}.py`,
  `apps/backend/tests/test_tenant_admin_endpoint.py` (new).

---

## Setup & Config

- Local PG: container `irp_pg_local`, role **`irp`** (superuser — NOT `postgres`), DB `irp`, port
  5432. URL: `postgresql+psycopg://irp:irp@localhost:5432/irp`.
- Schema reset before each full-PG run must include `GRANT USAGE ON SCHEMA public TO PUBLIC` and
  `GRANT CREATE ON SCHEMA public TO PUBLIC`.
- PG suites needing real RLS create `irp_app` (NOSUPERUSER NOBYPASSRLS, password `ci_app_pw`).
- `gh` at `~/.local/bin/gh`. Deployed stack runs `AUTH_MODE=dev_header`, `app_env=local`.
- New deploy env var: `IRP_PLATFORM_OPERATOR_SUBJECT` (absent = loud no-op). **Pipe characters
  break the dot-sourced env file** — subjects must be pipe-free.
- Battery: `python scripts/mutation_battery.py --group <slice>`; clone at `/tmp/irp-mutation-clone`.

---

## Pending Tasks

1. **ONBOARD-1b different-engine review** over `888e1ec..85cecc6` (Fable) — the immediate next step.
2. **Known unpaid, flagged at the gate:** the Users & Roles **UI** (remit outcome 6); the
   **ledgers** (ENT-075 canonical row, SoD row for the four codes, audit-taxonomy mint for
   `ROLE.GRANT_REQUEST`/`ROLE.GRANT_APPROVE`, CTRL-025 → Implemented, CTRL-037 → Implemented);
   the deployed arm extension in `prove_onboarding.sh`.
3. Then PR → CI-watch-to-green → merge → verify-on-main → memory.
4. **Wave-17 remainder:** ALERT-1 (six homeless carries name it), REPRO-2 (CTRL-018 startable),
   RPT-3, TS→7 on trigger.
5. **Unhosted DECISION for the Wave-17 close:** collapse the 22 hand-mirrored migration-head pins to
   one shared assertion.

---

## Errors & Workarounds

- **`CHECK_ALL_EXIT=2` many times** — formatting, import order, unused variable, stale head pins
  (21 files, three separate migrations), missing CI step for a new PG suite, OpenAPI drift. All
  quoted, never glossed.
- **CI RED twice on ONBOARD-1a.** (1) `prove_reproduction.sh` hand-pinned head `0065` → red in 95s
  when the PR minted 0066 → class-fixed to a derived head. (2) `prove_report_identity` HTTP arm
  "unentitled list was 401, expected 403" → the slice's own two ratified decisions colliding
  (backfill's proof-literal exclusion vs the boundary check) → fixed by the proof's gated seed
  registering its tenant.
- **Battery 9/12 then 9/14** — survivors were harness defects (phantom kills over skipped suites),
  stale anchors after refactors (the harness working as designed), and one unmeasurable mutant.
- **`permission denied for table tenant`** — the constrained app role needed SELECT on the new
  table; second time that privilege list was extended by a failure rather than foresight.
- **Approval refused by the append-only trigger on PG** while 25 SQLite tests passed — the
  BLOCKING defect of 1b, fixed by appending a resolution row.
- **Wrong concurrency scenario** — first draft measured an operation four-eyes already serializes.
- **`psql -U postgres` failed** — the container role is `irp`.
- **Workflow result parsing** — the task output is `{"result": {...}}`, not the bare object.

---

## Key Exchanges

- User ratified the Wave-16 close gate (4 questions) and the Wave-17 planning gate (3 questions),
  all as recommended — which minted P18/P19 and authorized the editorial pass.
- User ratified ONBOARD-1's ten OQs (4 questions, all as recommended), including the invariant
  amendment and the 1a/1b split.
- Model switches at every build/review boundary per the standing pause rule: Opus for building,
  Fable for reviewing — six flips this session, each announced before the work started.
- `/compress` invoked at the end of the ONBOARD-1b build, with 1b gated and awaiting review.

## Custom Notes

None

---

## Quick Resume Context

Wave 16 is closed and Wave 17 is under way on `investment-risk-platform`. ONBOARD-1a is merged
(PR #191 = `888e1ec`) — the platform can now create tenants over HTTP with a fenced SYSTEM operator,
proven on the deployed stack. ONBOARD-1b is **built, gated and committed as `85cecc6` on branch
`onboard-1b-tenant-admin` but NOT pushed**: it awaits a different-engine (Fable) review over
`888e1ec..85cecc6`. Gates at that commit: `CHECK_ALL_EXIT=0` (2629), `PG_PYTEST_EXIT=0` (3,244 at
head 0068), `MUTATION_EXIT=0` (13/13). Three things are knowingly unpaid and were flagged at the
gate: the Users & Roles UI, all the governance ledgers (ENT-075 row, SoD row, audit taxonomy,
CTRL-025/037), and the deployed-proof extension — the 1a review caught exactly this class, so expect
it to be the first finding again.

---

## Raw Session Log

**A deliberate departure, flagged rather than done quietly** — consistent with the four prior logs
in this directory. This section points at the authoritative transcript instead of reproducing it:

`/Users/andrewcox/.claude/projects/-Users-andrewcox-Projects-investment-risk-platform-investment-risk-platform/70b746c9-a66f-4a2f-a168-ed3b64166457.jsonl`

Writing a "full conversation" from memory would fabricate a record, and this session's own subject
matter is that failure class: a docstring that described a design the code did not implement, a
battery that reported kills over suites it never ran, a migration whose behaviour changed when a
constant did, and gate counts that had been hand-recovered for three slices because a flag
suppressed the number. The chronology, decisions, exit codes and commit SHAs above are accurate and
were captured as the work happened; the JSONL is the verbatim record.

### Session chronology (accurate, condensed)

1. **Wave-16 close fold** (5 items) → battery 12/12 after two real survivors → `CHECK_ALL_EXIT=0`
   (2572) → GATED → Fable review found a BLOCKING (poisoned skip preempting `MAX_ALARM_ATTEMPTS` =
   infinite paging) + the multiline-import census evasion → CI found a third (hand-pinned deploy
   head) → **PR #187 = `9257514`**, 20th merge; record **#188 = `4131e1c`**.
2. **Wave-17 planning gate** → P18, P19, P15/P14 amendments, editorial pass → **PR #189 = `d4e3692`**.
3. **ONBOARD-1 planning**: v1 draft → verifier pass 1 (5 lanes, 40 agents, 11 BLOCKING + 23
   MATERIAL) → v2 → verifier pass 2 (3 lanes, 23 agents; structural folds HELD, 2 BLOCKING + 13
   MATERIAL in the new machinery) → v3 → **ratified, PR #190 = `a48a0e7`**.
4. **ONBOARD-1a build** (`9ba9dc5`) → battery 12/12 after 3 harness defects (incl. the `-qq`
   root-cause) → GATED → Fable review fold (`917826d`: the skipped ledgers, operator seed, ignition
   proof executed, fence census) → CI folds (`563d952`, `a6eed1d`) → **merged #191 = `888e1ec`**.
5. **ONBOARD-1b build** (`85cecc6`) → mint + ENT-075 + four-eyes + orphan invariant + 8 routes +
   migration 0068 → battery 13/13 after 5 survivors → gates green → **GATED, awaiting review**.
