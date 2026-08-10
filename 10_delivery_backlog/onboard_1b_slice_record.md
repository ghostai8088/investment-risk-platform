# ONBOARD-1b slice record — the tenant administers itself

**Wave 17, slice 0b.** Branch `onboard-1b-tenant-admin`; build commit `85cecc6` (Opus), review
fold on a different engine (Fable, 2026-08-09) per P15. Design authority:
`onboard_1_decision_record.md` v3 + ratification stamp (OQ-ONB-1…10); remit
`onboard_1b_remit.md`. Ratified at the ONBOARD-1 gate — no second gate.

## 1. What shipped

- **The four tenant-administration codes** — `user.manage`, `role.assign`, `user.view`,
  `role.approve` — filling the `tenant_admin` template 1a minted empty. Holders: `tenant_admin` +
  `platform_admin` only; `auditor_3l` excluded from `user.view` (person-identifying roster).
  The `_DELIBERATELY_EMPTY` exemption was deleted — its stale-entry twin is what required it.
- **ENT-075 `entitlement_request`** (migration `0068`): IA append-only, FORCE RLS, the
  `irp_prevent_mutation` trigger, per-tenant monotonic `seq`, three total-enumeration CHECKs.
  The four-eyes lifecycle: born `PENDING` at ≥1 other admin, `DIRECT` in the bootstrap window,
  resolution as an **appended row** (`resolves_request_id`).
- **CTRL-025 implemented** (SOD-04 four-eyes with the single-admin bootstrap window, OQ-ONB-9A)
  and **CTRL-037 implemented** (the orphan invariant across all four paths — revoke, end-date,
  deactivate incl. self, concurrent under the per-tenant advisory lock).
- **Eight tenant-local routes** with no `{tenant_id}` path parameter (see §5 finding 5), all
  guarded by the ordinary `require_permission`, census-visible (route count 292 → 300), and NOT
  under the SYSTEM fence's allowed prefix.
- **The Users & Roles screen** (`/admin/users`, remit outcome 6) — roster, create-user, grant /
  revoke / deactivate, and the four-eyes queue. The screen's load-bearing behavior, pinned by its
  tests: **the outcome is read from the response body** — a 200 whose body says `PENDING` renders
  as "not yet effective"; a `DIRECT` act renders the flagged bootstrap-window language.
- **The deployed arm** (`prove_onboarding.sh` arm 5): create user → DIRECT grant → second admin
  minted → the very next act born PENDING → self-approval 422 → second admin approves → the
  granted analyst reads `/portfolios` 200 and is 403'd creating a user.
- **Ledgers**: ENT-075 canonical row; SoD §5B mint row + §5C checklist (all five rows executed,
  row 5 as the named 0068 backfill) + §7 bootstrap-window clause; `ROLE.GRANT_REQUEST` /
  `ROLE.GRANT_APPROVE` taxonomy mint row; CTRL-025/CTRL-037 → Implemented.

## 2. Gates, with captured exit codes (P14)

Recorded from the review-fold tree; the fold commit message carries the same figures and is the
artifact (P14: the captured exit code is the claim).

- Full-PG validation, schema reset first: `PG_PYTEST_EXIT=0` — **3,245 passed** at head `0068`;
  the stripped `REJECTED` CHECK verified against `pg_constraint`, not migration text.
- `alembic upgrade head` on the reset PG: `UPGRADE_EXIT=0`; `alembic check`:
  `ALEMBIC_CHECK_EXIT=0`.
- Deployed proof, all five arms: `ONBOARDING_PROOF_EXIT=0` (first run FAILED on the new arm's own
  construction — §3 fold item — then green).
- Mutation battery, group `onboard-1b`, **15 mutants** (13 from build + O-F1/O-F2 pinning the two
  review fixes): `MUTATION_EXIT=0`, **15/15 KILLED**, every line with a nonzero ran-count (the
  phantom-kill floor visible: 18 ran on the unit-tier mutants, 4 on the PG-tier ones).
- `make check-all` (both tiers + API-drift): `CHECK_ALL_EXIT=0` on the committed fold tree —
  2,630 unit-tier passed, 222 FE tests passed, dependency audit clean. The path to green was
  itself three refusals doing their jobs — `ruff format` on the reworked test file, `tsc` on an
  unused parameter, and `gen-api-check`, which by construction compares regenerated output
  against HEAD and therefore only passes post-commit for an API-changing fold.
- CI to green on the PR head; P16 at the PR boundary.

## 3. Defects found, and by what

### At build (Opus), by execution — the ones the summary already records

1. **Approval mutated the append-only row** — accepted by every SQLite test, refused by the
   ENT-075 PG trigger (P0001). Rewritten as an appended resolution row. The trigger, not review,
   caught it.
2. **`_four_eyes_required` read the wall clock while the orphan check honored the caller's
   `now`** — two controls in one module answering "who are the admins?" against different clocks.
   Found while diagnosing the concurrency test's fixture.
3. **The concurrency test measured the wrong operation twice** — concurrent *requests* are both
   born PENDING (harmless by construction); the race lives in concurrent *approvals*. And its own
   wrong-reason floor then caught defect 1 above (both threads erroring is not the lock working).
4. **Migration 0067's unguarded template insert collided** the moment 1b filled the mutable
   constant it live-imports — existence-guarded, class rule recorded in 0067.

### At the different-engine review (Fable) — six findings, two probe-confirmed by execution

1. **BLOCKING — deactivation four-eyes was over-broad, and the test pinning it carried the
   ratified behavior in its NAME while asserting the opposite.** Every deactivation was born
   PENDING when a second admin existed; the record's enumeration (pass-2 B2, exactly) scopes the
   flow to a target *currently holding `tenant_admin`*, and the remit's proof pins "deactivating
   a NON-admin user stays direct" — while `test_deactivating_a_NON_admin_stays_direct` asserted
   `PENDING`. Probe-confirmed, fixed in the service, the test renamed and made to assert what its
   name claims, and the fix carries its own mutant.
2. **HIGH — the target role was never tenant-validated** (the target *user* was — an asymmetry).
   Probe-confirmed: a grant naming another tenant's role id was accepted. On PG the ghost grant
   confers nothing (RLS breaks the `has_permission` join) and is invisible in the roster — an
   unenumerated cross-tenant reference either way. Fixed with the same opaque no-oracle refusal
   as the user check, plus a test and a mutant.
3. **MEDIUM — `REJECTED` was minted with no code path able to produce it** (the LQ-1 inert-state
   class: a CHECK an auditor can read implies a flow that does not exist). The record ratified
   approval and nothing else — the status is STRUCK from the model and 0068 (both unmerged).
   **A reject/withdraw verb is a named open decision** — see §5.
4. **MEDIUM — audit incoherence**: 1b's `create_user` recorded `USER.PROVISION` with
   `action='update'` where 1a's onboarding records the same event with `action='create'`.
   Aligned; the existing create-user test now asserts the pair.
5. **PAPER — the remit's own route paths (`/tenants/{id}/users`…) were never shipped**, and
   shipping them would have been a defect: `/tenants` is the SYSTEM fence's sole allowed prefix,
   so nesting tenant-admin routes under it would have exposed them to the SYSTEM principal. The
   shipped shape (no tenant path parameter — the principal's tenant IS the scope) is recorded in
   the remit as an annotation rather than silently diverging from it.
6. **LOW — `list_roles` returned `list[dict]`**, compiling the FE against `unknown` and voiding
   the FE-2 contract for the one list the grant flow depends on. Typed as `RoleOut`.

Findings 1–4 are production-behavior defects that existed *after* a 9-defect build gauntlet and
2,629 green tests — all four invisible to the suite because the suite pinned the built behavior,
not the ratified one. The different-engine pattern's seventh consecutive catch, and the second
(after 1a) whose biggest finding is a claims defect: an artifact named for a proof it does not
deliver.

### At the fold's own gate run — one defect in the fold's OWN work, caught by execution

1. **The new deployed arm's first draft refuted itself.** It granted `tenant_admin` in the
   four-eyes step (to have a PENDING act) and then demanded the target be 403'd creating a user —
   but the approval it had just proven made the target an admin, so the analyst got 201 where the
   script demanded 403. The run failed, correctly, on the arm's own construction; the PENDING
   grant is now `risk_manager_2l`. A refusal twin only discriminates if the granted role does NOT
   confer the verb the twin denies — the LIM-2 lesson (mutate against the LIKELY input) in proof
   form, and one more entry for "found by execution, invisible to reading".

## 4. The build's own lessons, carried forward

- **A test named for the ratified behavior must assert it** — the name is a claim; the assertion
  is the artifact. This is the seventh-ledger class surfacing inside a test file.
- **Symmetry check at every scope boundary**: when one side of a pair (user) is tenant-validated
  and the other (role) is not, the asymmetry is the finding. Ask "what else crosses this
  boundary?" at every refusal.
- **A minted state with no producer is a false document** — strip it or ship its verb.

## 5. Carries and open decisions (P19)

- **Reject/withdraw for a PENDING entitlement request — a DECISION, surfaced now**: with approval
  the only exit, a wrong request sits in the queue forever (noise, not danger: it never takes
  effect). The record ratified approval only, so the review struck the dead status rather than
  minting an unratified verb. **Trigger: the first operator complaint about queue noise, or the
  next entitlement slice, whichever first — and the verb needs its own ratification (R-07).**
- The worker still does not tick a created tenant (`IRP_TENANT_IDS` stays deploy config) — rides
  to REPRO-2 by name, unchanged from 1a.
- The 22 hand-mirrored migration-head pins → one shared assertion: the Wave-17 close decision,
  unchanged.

## 6. Non-goals honored

No signup/invitations/SCIM/MFA; no `tenant.suspend` setter; no tenant deletion; no new platform
codes; no change to the OIDC verifier, boundary check, or SYSTEM fence (the fence census asserts
the allowed surface did NOT grow with these eight routes).
