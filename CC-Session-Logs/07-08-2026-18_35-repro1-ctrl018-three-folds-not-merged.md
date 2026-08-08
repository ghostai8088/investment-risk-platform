# Session Log: 07-08-2026 18:35 - repro1-ctrl018-three-folds-not-merged

## Quick Reference (for AI scanning)

**Confidence keywords:** REPRO-1, CTRL-018, ENT-073, reproduction_check, migration 0065,
reproduction sweep, nightly reproduction, scheduled reproduction, third schedulable family,
REPRODUCTION run_type, phase 5, alarm delivery, unalarmed_verdicts, MAX_ALARM_ATTEMPTS,
retry-the-wire-not-the-audience, compared_fields, _MUST_COMPARE, census shrinkage, savepoint
rollback, PendingRollbackError, _Discard, begin_nested, duplicate natural key, advisory lock,
prove_reproduction.sh, reproduction_proof.py, deployed proof, PROOF_EXIT, MUTATION_EXIT,
five-lens review, fresh-context audit, re-audit, DO_NOT_MERGE, PR #183, RPT-2 carry b,
IRP_TENANT_IDS, worker database path, seven-ledger sweep, P1, P9, P14, P15, Wave 16, FK-1

**Projects:** investment-risk-platform (multi-tenant governed investment-risk platform)

**Outcome:** REPRO-1 built end to end and proven on the deployed stack (CTRL-018's observed
scheduled green, both arms), then subjected to three successive scrutiny stages — a five-lens
adversarial review (13 findings, 2 BLOCKING), a fresh-context pre-merge audit (35 findings,
2/4 DO_NOT_MERGE) and a focused re-audit of that fold (33 findings, 4/4 DO_NOT_MERGE). Each fold
introduced a defect the next stage caught. **NOT MERGED** — PR #183 is green on `03faa6c` and
awaiting a decision on a third focused pass.

---

## Decisions Made

- **Four Tier-3 forks put to the user and all taken as recommended** (OQ-REPRO-1-1…4), because recon
  proved three sentences of the ratified OQ-W16P-5 shape unbuildable as written:
  - relax `schedule.scope_portfolio_id` under a family-gated TOTAL-ENUMERATION CHECK (the 0053
    pattern applied to a second column) rather than nominating a sentinel portfolio, which would
    stamp a false scope into a governed config row the ops UI renders;
  - mint **ENT-073 `reproduction_check`** rather than ledger-only evidence — CTRL-018's evidence
    column says "Reproduction report", which must mean something an auditor can read later;
  - **three families registered + eighteen census-pinned with written reasons**, over broad coverage
    whose parameter read-back would make the check share an assumption with what it checks (P15);
  - **reuse `breach.review`** as the divergence audience over minting `repro.review`, which would be
    held by nobody in any real tenant (no tenant-onboarding clone of `ROLE_TEMPLATES` exists).
- **Re-execute the BINDER, not the kernel.** Eighteen service modules accept a consume-existing
  `snapshot_id`; a kernel-only re-derivation could not see a change in a binder's adjudication, and
  CTRL-018's wording is "re-runs historical runs". Verified by execution before adoption.
- **The verdict is control-plane evidence, not a governed number** — binds no snapshot and no model
  of its own (the `breach`/`breach_action` precedent). It DOES bind a `REPRODUCTION`
  `calculation_run`, because OQ-SCH-2-8 requires a schedule's family key to be a real run type.
- **Alarm delivery is a separate tick phase (phase 5)**, because phase 1 holds the per-tenant audit
  advisory lock to COMMIT and a sink call there is the API-2b lock-across-I/O anti-pattern.
- **A sweep that checked NOTHING fails closed** (a FAILED run carrying the reason) — added after the
  deployed proof produced a perfectly green tick over a tenant whose subjects it could not see.
- **A divergence is NOT a failed dispatch.** `scheduled_run.outcome` stays DISPATCHED when the check
  ran; infrastructure failure is FAILED. Collapsing them makes the platform's most important alarm
  indistinguishable from a database hiccup.
- **RATIFIED BY USER 2026-08-07 — "retry the wire, not the audience."** A SUPPRESSED alarm is
  TERMINAL (it concluded correctly: nobody holds the permission, and re-POSTing tells nobody
  anything new). A FAILED delivery gets a bounded retry (`MAX_ALARM_ATTEMPTS = 5`). Accepted
  trade-off recorded as carry (o): a divergence found before provisioning is not re-alarmed after.
- **`first_divergence` names the row key and the field, never the VALUES** on the DIVERGED path —
  pre-empting RPT-2's confirmed issuer-disclosure class. The UNREPRODUCIBLE path is a stated
  exception (binder exception text), bounded by `_redact`, recorded as carry (n).
- **The notification wire format changed deliberately and NOT back-compatibly**
  (`NotificationMessage.breach_id` → `subject_id`, plus `alert_type`), because the transport now
  carries two alert classes and a compatibility alias nobody would remove is worse.
- **Did not merge.** Three folds, each caught by the next stage. Merging on my own assessment that
  my own fold is clean is the move this session repeatedly showed to be wrong.

---

## Key Learnings

- **Each fold introduced a defect the next stage caught — twice in a row.** The review's fold
  re-created the exact blast radius the BLOCKING savepoint fix had removed. The audit's fold turned
  a dropped-alarm fix into an unbounded 300-second retry loop. This is the strongest evidence yet
  for the layered-scrutiny rule, and it applies to the *fold*, not just the build.
- **A census that only checks ADDITIONS is a floor wearing a census's name.** The field census
  passed while five governed columns could be moved OUT of the comparison. A `len(reason) >= 40`
  floor was satisfiable by copying an existing module constant. Only a by-name pin (`_MUST_COMPARE`)
  closes removal.
- **`savepoint.is_active` is the wrong guard.** When a `session.flush()` raises, SQLAlchemy
  deactivates the savepoint AND poisons the session; skipping the rollback then raises
  `PendingRollbackError` on the next statement. `with session.begin_nested():` rolls back
  unconditionally on exit — which is why `dq/gates` and `db/integrity` never had this bug.
- **A fix that addresses the reported call site is not a class fix.** `compare_rows` was guarded;
  `read_stored` and `latest_completed_run` were not, and would have destroyed the night's sweep the
  same way.
- **Markdown edits to ledgers can render as NOTHING.** A blank line terminates a GFM table exactly
  as a blockquote does; cells beyond the header count are silently discarded. Three ledger edits in
  this slice rendered as raw text or vanished. `docs-check` catches none of it — only rendering both
  revisions does.
- **A gate claim must cite the run for the CURRENT head.** CTRL-018 was moved citing a CI run of the
  PRE-fold harness — the run whose arms my own commit message had documented as unable to fail. The
  same stale citation propagated into four documents.
- **`expire_on_commit=False` makes a planted-divergence test vacuous.** The session serves the
  pre-plant object from its identity map; the plant must read back and assert it landed.
- **`docker exec` without `-i` silently forwards no stdin.** A seeded precondition that never ran
  made a downgrade proof pass over an empty table.
- **A proof harness that runs unqualified DML as a superuser can destroy other tenants' governed
  evidence** — RLS does not fence a BYPASSRLS role, and the append-only trigger was disabled at the
  time.
- **`pg_trigger` has a row for a DISABLED trigger**, so a `count(*)` assertion cannot fail for the
  condition it exists to detect. `tgenabled = 'O'` is the real check.
- **A mutation can be badly chosen.** M15 perturbed an exhaustion count that a single failed attempt
  cannot detect, and survived. A surviving mutant sometimes means the mutation is wrong, not the
  control — but it must be re-pointed, never dropped.

---

## Solutions & Fixes

- **The nested-transaction manoeuvre**, proven by execution before adoption: re-run a binder over the
  subject run's own `input_snapshot_id` inside `session.begin_nested()`, project results to plain
  values, then discard. Positive control (`sp.commit()`) moves every count, so the "unchanged"
  assertions are load-bearing.
- `check_one_family` now uses `with session.begin_nested():` + a `_Discard` exception so the discard
  is structural; there is no code path out of the block that commits.
- Every per-family call (`read_stored`, `recompute`, `compare_rows`) is inside a guard that turns a
  family's failure into that family's UNREPRODUCIBLE verdict; `latest_completed_run` failures append
  to a new `unresolved` list (no verdict row — `subject_run_id` is a NOT NULL FK).
- `compare_rows` refuses duplicate natural keys rather than collapsing them into one dict entry.
- Alarm queue: a verdict is retired when its attempt CONCLUDED (`outcome == "success"`, i.e. SENT or
  SUPPRESSED) **or** when its FAILED retries reach `MAX_ALARM_ATTEMPTS`.
- `_emit_dispatch` writes `outcome="failure"` only for NOTIFY_OUTCOME_FAILED; SENT and SUPPRESSED
  are both "success" (the attempt concluded correctly).
- Migration `0065` downgrade gained the 0059 trigger/RLS sandwich. Negative control executed:
  without it `MUTANT_DOWNGRADE_EXIT=1` with the exact `AUD-01` error; with it, exit 0.
- `create_schedule` no longer stringifies a NULL `scope_portfolio_id` into the literal `'None'`, and
  `_schedule_metadata` emits JSON null rather than `"None"` into the hash-chained audit ledger.
- Deployed proof hardened: tenant-qualified plant with a `RETURNING` row count, a seeded
  `breach.review` recipient so the DELIVERY path executes (`ALARM_OUTCOMES=SENT`), and
  `tgenabled='O'` for the trigger check.
- `_MUST_COMPARE` pins the governed columns per family by name so a removal fails loudly.

**Commands that worked:**
```bash
make check-all                                     # CHECK_ALL_EXIT=0
bash infra/deploy/prove_reproduction.sh            # PROOF_EXIT=0, both arms
docker exec irp_pg_local psql -U irp -d irp -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; \
  GRANT USAGE ON SCHEMA public TO PUBLIC; GRANT CREATE ON SCHEMA public TO irp;"
DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp .venv/bin/alembic upgrade head
docker exec -i irp_pg_local psql ... <<'SQL'      # -i is REQUIRED for stdin
gh run view <id> --json jobs                       # verify the STEP, not the roll-up
```

---

## Files Modified

**New:**
- `packages/shared-python/src/irp_shared/reproduction/{__init__,events,models,registry,service}.py`
  — ENT-073, the vocabulary, the reproducer registry + coverage census, and the engine.
- `packages/shared-python/src/irp_shared/deploy/reproduction_proof.py` — the deployed harness
  (`seed` / `plant` / `report`), armed by `IRP_ALLOW_PROOF_SEED`.
- `apps/worker/src/irp_worker/reproduction_alarms.py` — tick phase 5.
- `infra/deploy/prove_reproduction.sh` — both arms through the real worker.
- `migrations/versions/0065_reproduction_check.py` — the REPRODUCTION arm on the family CHECK, the
  `scope_portfolio_id` relaxation under a new total-enumeration CHECK, and ENT-073.
- `packages/shared-python/tests/test_reproduction.py`, `tests/test_reproduction_pg.py` (37 tests).
- `10_delivery_backlog/repro_1_remit.md`, `10_delivery_backlog/repro_1_slice_record.md`.

**Modified:**
- `packages/shared-python/src/irp_shared/scheduling/{models,service}.py` — third family,
  `requires_portfolio_scope`, nullable scope, the None-stringification fixes.
- `packages/shared-python/src/irp_shared/notification/{sink,service}.py` — `subject_id` +
  `alert_type` generalisation.
- `apps/worker/src/irp_worker/{scheduler,supervisor}.py` — phase 5 wiring and logging.
- `apps/backend/src/irp_backend/api/schedules.py` — `scope_portfolio_id: str | None`.
- `.github/workflows/ci.yml` — the ENT-073 PG suite step and the `stack-proof` reproduction step.
- Ledgers: `04_data_model/{canonical_data_model_standard,audit_event_taxonomy}.md`,
  `09_compliance_controls/control_matrix_skeleton.md`,
  `02_requirements/{requirements_backbone,requirements_traceability_matrix}.md`,
  `10_delivery_backlog/delivery_roadmap.md` (REPRO-1 row + a BACKFILLED RPT-2 row).
- `packages/shared-python/tests/{test_scheduler,test_scheduler_cadence_pg,test_breach_lifecycle_pg,
  test_sharpe,test_notification_sink_webhook,test_active_risk}.py` + 20 migration-head pins.

---

## Setup & Config

- Repo: `/Users/andrewcox/Projects/investment_risk_platform/investment-risk-platform`, branch
  `repro-1-reproduction-job`, base `main` at `88ccbed`.
- Local PG: container `irp_pg_local`, user/db `irp`/`irp` (SUPERUSER + BYPASSRLS), port 5432.
- Migration head: `0065_reproduction_check`. Next free canonical id: **ENT-074**.
- `gh` at `~/.local/bin/gh`. PR **#183**.
- Deployed-proof compose project `irp-repro1`, host port **55436** (55432 deploy.sh, 55433
  backup/restore, 55435 report-identity).
- Proof tenant `9f000000-0000-4000-8000-000000000001` — SHARED with `report_identity_proof`, because
  this proof reuses its seeded governed report as the subject.
- Mutation harness: `<scratchpad>/mutate.py`, 19 mutants.

---

## Pending Tasks

- **DECIDE: run a third focused pass over `d88e719..03faa6c`, or merge on green CI.** My
  recommendation is the third pass — the two previous rounds each found something real in exactly
  that position.
- **Merge PR #183**, then the P1 verify-on-main (`git merge-base --is-ancestor <sha> origin/main`
  for every claimed artifact, including fold commits).
- **Ledger 4 (`docs/project_memory/current_state.md`) deliberately NOT updated** — held until after
  the merge so it records the real SHA.
- **Carries (a)–(o)** in `repro_1_slice_record.md` §6, including: eighteen unreproduced families;
  CONCENTRATION needs a consume path; LIQUIDITY's wall-clock staleness gate; CTRL-018 is Implemented
  NOT Operational; **carry (m) — the remit's in-scope "a nightly schedule the demo/deploy path
  creates" was NOT built** (only the proof harness creates one); carry (i) — phase 1 holds the audit
  advisory lock across the full re-execution.
- **Two debts found adjacent to this slice, not caused by it:** eight shipped permission codes with
  no SoD §5B row; RPT-1's P8-census exception claim is false as written.
- **NEXT SLICE = FK-1** (115 → 0 SQLite dangling-FK failures; 103 remain).
- **OWED at the Wave-16 close:** `report.*` holder-set ratification; the mint-reachability rule.
- ~120 stale remote branches on origin.

---

## Errors & Workarounds

- **My planted-divergence test was VACUOUS and reported MATCH** — `expire_on_commit=False`. Fixed by
  `expire_all()` + a read-back asserting the plant landed.
- **`create_schedule` stored the literal `'None'`** for a NULL scope. SQLite accepted it; PG rejects
  it as invalid uuid syntax. The warning was already in the file, one line below, about the sibling
  column SCH-2 fixed.
- **The deployed proof's first run was green over the wrong tenant** — the harness minted its own
  tenant while seeding through the report proof's. Zero verdicts, DISPATCHED, everything looking
  fine. Fixed by importing `PROOF_TENANT`; produced the fail-closed-on-empty-sweep control.
- **Both proof schedules fired on the first tick** (`fired=2`) because `interval_days=1` puts every
  schedule on the same UTC-midnight grid, consuming the negative arm's bucket. Fixed by creating the
  second schedule at plant time.
- **Phase 5 read a table the constrained `irp_app` role had no grant on** — invisible to the deployed
  proof (runs as owner), caught by the full-PG battery.
- **`test_scheduler_cadence_pg` reads `calendar_holiday` without granting it** — green only because
  an earlier CI step in the same un-reset database happens to. Pre-existing; fixed.
- **`docker exec` without `-i`** made a downgrade proof pass over an empty table. Re-run with the
  precondition ASSERTED (`schedules=1 scheduled_runs=1`).
- **zsh command substitution in a commit message** — backticks inside a double-quoted `printf`
  argument. Fixed by a quoted heredoc (`<<'MSGEOF'`). This is the standing
  commit-message-shell-safety rule, hit again.
- **Demo-campaign PG failures** after a timed-out battery left the schema polluted — reset before
  each full-PG run (standing rule).
- **`timeout` is not available on this shell** (exit 127).
- **M14 and M15 SURVIVED** on first run: M14 because the test called `compare_rows` directly and
  never exercised the guard; M15 because the mutation perturbed an exhaustion count a single attempt
  cannot detect. Both re-pointed; M14 also gained a sweep-level test.
- **`mypy`: `Result[Any]` has no `rowcount`** — replaced with `RETURNING id` + `len(fetchall())`.
- **`gen-api-check` diffs regenerated artifacts against COMMITTED ones**, so `make gen-api` output
  must be committed before `check-all` passes.

---

## Key Exchanges

- User asked what to do next given no Fable allocation; recommended REPRO-1 on Opus because its
  central proof is an observation, not a reading, and because RPT-2's evidence showed the lane that
  paid was fresh CONTEXT (that audit was itself Opus), not a second engine.
- Surfaced the two owed Wave-16-close decisions (`report.*` holder sets; the mint-reachability rule)
  unprompted, since they were never actually put to the user.
- Four Tier-3 forks presented with recommendations after recon refuted the ratified shape; all four
  taken as recommended.
- User asked "Can you proceed?" → build, review fold, audit fold.
- User: "Run the focused re-audit" → four lenses, all DO_NOT_MERGE, catching a HIGH the previous
  fold had introduced.
- Ratified "retry the wire, not the audience" for the alarm-retry bound.

---

## Custom Notes

None

---

## Quick Resume Context

REPRO-1 is BUILT, PROVEN and PUSHED but **deliberately NOT MERGED**. PR #183, branch
`repro-1-reproduction-job`, head `03faa6c`, ten commits, CI green (run `31219185440`, all 8 jobs,
including the `stack-proof` step *"Prove a scheduled reproduction detects a planted divergence
(CTRL-018)"*). Gates at the head: `CHECK_ALL_EXIT=0`, full-PG `PG_PYTEST_EXIT=0`, `PROOF_EXIT=0`
with `ALARM_OUTCOMES=SENT`, `MUTATION_EXIT=0` 19/19, 3,128 collected.

The open decision is whether to run a **third focused pass over `d88e719..03faa6c`** before merging.
Three scrutiny stages ran and each fold introduced a defect the next stage caught — so the case for
one more pass over the newest fold is strong, and that is the recommendation on the table. After the
merge: update `current_state.md` (ledger 4, held so it records the real SHA), run the P1
verify-on-main, then move to **FK-1**.

---

## Raw Session Log

**This section deliberately points at the authoritative transcript rather than reproducing it.**

The complete, verbatim conversation for this session lives at:

```
/Users/andrewcox/.claude/projects/-Users-andrewcox-Projects-investment-risk-platform-investment-risk-platform/70b746c9-a66f-4a2f-a168-ed3b64166457.jsonl
```

Writing a "full conversation" from memory would fabricate a record — and this session's entire
subject was that failure class: a planted-divergence test that could not plant, a census that could
not detect removal, an assertion that could not fail for the condition it existed to detect, a
control-matrix row citing evidence its own author had documented as insufficient. Inventing a
transcript to close it out would be incoherent. What follows is an accurate chronological skeleton
with the gate values quoted exactly as captured.

### Chronological skeleton

1. **Session opened** post-`/compact` with the user asking what to do next given no Fable
   allocation. Verified repo state (`main` at `88ccbed`, clean); found the plan-mode plan already
   complete (P14 ratified, `check-all` exists, `stack-proof` job present). Recommended REPRO-1.
2. **Surfaced the two owed Wave-16-close decisions** (`report.*` holder sets; the mint-reachability
   rule), neither of which had been put to the user.
3. **User: "proceed."** Confirmed REPRO-1's ratified shape (OQ-W16P-5). Created branch
   `repro-1-reproduction-job`; committed two untracked session logs.
4. **Seven-agent recon fan-out** (`wf_0156d4b1-d62`, 7/7, 0 errors). Five load-bearing findings
   re-verified by hand — including that 0053's family CHECK is a TOTAL ENUMERATION (PG rejects a
   third family while the whole SQLite tier stays green), that the notification transport is
   breach-shaped end to end, and that `IRP_TENANT_IDS` ships empty so the deployed worker's database
   path had never executed.
5. **Design crux settled by EXECUTION**, not reasoning: a probe re-ran `run_var` over an existing
   run's own snapshot inside `begin_nested()`, matched exactly, and left run/result/audit counts
   unchanged with `verify_chain` gapless. Positive control moved all three. `PROBE_EXIT=0`.
6. **Four Tier-3 forks put to the user; all four taken as recommended.**
7. **Build** (commits 2/n–5/n): the engine, ENT-073, migration 0065, the third schedulable family,
   phase 5, the deployed proof. Three guards fired and were moved consciously (the schedulable-set
   census 2→3, the risk/exposure import fence, the run-type census 21→22).
8. **Five defects found by execution during the build**, listed in §4 of the slice record.
9. **First deployed-proof successes:** `irp-worker: tenant=9f000000-… fired=1 … repro_alarmed=1`,
   `VERDICTS=REPORT:MATCH,REPORT:DIVERGED`, `ALARM_EVENTS=1`. CI run `31204168002` on `5fafd00`,
   all 8 jobs `success`.
10. **Five-lens adversarial review** (`wf_322eec77-4c9`, 28 agents): 13 verified findings, 2
    BLOCKING — the `savepoint.is_active` guard and migration 0065's unrunnable downgrade, both
    reproduced verbatim by the skeptics. Folded at `ef899a6`; 12/12 mutants killed; negative control
    executed for the migration (`MUTANT_DOWNGRADE_EXIT=1` without the sandwich, 0 with it).
11. **Fresh-context pre-merge audit** (`wf_43c9bfb5-313`, 4 lenses): 35 findings, **2/4
    DO_NOT_MERGE**. Decisive finding: CTRL-018 had been moved citing a CI run of the pre-fold
    harness. Also: the fold had re-created the BLOCKING blast radius one line over. Folded at
    `d88e719`; CI green (run `31213328622`).
12. **User requested the focused re-audit** (`wf_61c5b8f3-680`, 4 lenses): 33 findings, **4/4
    DO_NOT_MERGE**. The audit fold had introduced a HIGH — SENT-only queue filtering = an unbounded
    300s retry loop; two of its claims were executably false; the RTM fix had not landed.
13. **User ratified "retry the wire, not the audience."** Folded at `03faa6c`. Final gates:
    `CHECK_ALL_EXIT=0`, `PG_PYTEST_EXIT=0`, `PROOF_EXIT=0`, `MUTATION_EXIT=0` (19/19), 3,128
    collected, 37 slice tests. CI run `31219185440` on `03faa6c`: `success`.
14. **NOT MERGED.** Awaiting the decision on a third focused pass.

### Quoted gate evidence (as captured)

```
PROBE_EXIT=0                     the nested-rollback design, before adoption
CHECK_ALL_EXIT=0                 both tiers, at the final head
PG_PYTEST_EXIT=0                 full-PG, freshly reset schema
PROOF_EXIT=0                     deployed proof, both arms
                                 ALARM_OUTCOMES=SENT   PLANTED_ROWS=1   TRIGGER_ENABLED=1
                                 VERDICTS=REPORT:MATCH,REPORT:DIVERGED
MUTATION_EXIT=0                  19/19 killed
MUTANT_DOWNGRADE_EXIT=1          negative control: 0065 downgrade without the sandwich (AUD-01)
DOWNGRADE_EXIT=0                 with the sandwich, precondition asserted (schedules=1, runs=1)
COLLECTED_TOTAL=3128
CI run 31219185440 on 03faa6c -> success (8/8 jobs)
  step "Prove a scheduled reproduction detects a planted divergence (CTRL-018)" -> success
```
