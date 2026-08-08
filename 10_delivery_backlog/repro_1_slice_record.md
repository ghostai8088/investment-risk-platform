# REPRO-1 slice record — the reproducibility claim became a nightly machine verdict

**Wave 16, slice 2 of 3.** Remit: `repro_1_remit.md`. Branch `repro-1-reproduction-job`.
**Every claim below is cited to an artifact and was checked against the diff before this file was
written** (P1 ledger 7 — REF-1's merged record carried five false claims, found only because the
next slice's recon happened to re-read it).

## 1. What shipped

A nightly, per-tenant **reproduction sweep** that rides the existing scheduler as a third
schedulable family. For each registered governed family it takes the most recent COMPLETED run,
**re-executes that run's binder over the run's OWN pinned `dataset_snapshot`** inside a nested
transaction that is always rolled back, compares the recomputed content against the stored rows,
and writes a verdict (ENT-073 `reproduction_check`: MATCH | DIVERGED | UNREPRODUCIBLE). Divergences
are alarmed in a **separate tick phase**.

| Artifact | Where |
|---|---|
| ENT-073 `reproduction_check` | `packages/shared-python/src/irp_shared/reproduction/models.py`; migration `0065_reproduction_check.py` |
| The engine (sweep, comparison, verdicts, alarm) | `reproduction/service.py` |
| The reproducer registry + coverage census | `reproduction/registry.py` |
| The vocabulary (leaf module) | `reproduction/events.py` |
| `REPRODUCTION` schedulable family | `scheduling/service.py` (`_dispatch_reproduction`, `FAMILY_REGISTRY`) |
| Tick phase 5 (alarm delivery) | `apps/worker/src/irp_worker/reproduction_alarms.py`, wired in `irp_worker/scheduler.py` |
| Deployed proof, both arms | `infra/deploy/prove_reproduction.sh` + `irp_shared/deploy/reproduction_proof.py` |
| Unit + PG suites (64 tests) | `tests/test_reproduction.py`, `tests/test_reproduction_pg.py` |

## 2. Gates, with captured exit codes (P14)

**Measured at the MERGE HEAD, after ALL SIX folds — the review fold, the audit fold, the
re-audit's fold, the fourth pass's fold, the fifth pass's fold, and the SIXTH fold that answered two
independent reviews on a DIFFERENT ENGINE — not carried forward from an earlier commit.**

That sentence has now been wrong once, and the correction is worth more than the sentence. At the
third fold it read "after the review fold and the audit fold", claimed every figure had been
re-taken, and was written in a commit that re-took exactly two of five rows: the mutation count and
the collect counts moved while `CHECK_ALL_EXIT`, the full-PG `PYTEST_EXIT` and the deployed
`PROOF_EXIT` were carried silently forward, under a heading whose entire subject is that carrying
gate numbers forward is the defect ledger 7 exists to prevent. Nobody caught it, across three
scrutiny stages, because a row the diff does not touch does not present itself as something the
diff made false. **Every row below was re-run at this head.**

| Gate | Result |
|---|---|
| `make check-all` (both tiers) | **`CHECK_ALL_EXIT=0`** |
| Full-PG battery, schema reset then migrated to head | **`PG_PYTEST_EXIT=0`** |
| Deployed-stack proof, both arms | CI `stack-proof` job at THIS head — see §2b. **This row previously quoted a LOCAL `PROOF_EXIT=0` measured at an earlier head, carried forward in the one section whose whole subject is not carrying gate numbers forward.** The same defect this record retracted two folds ago, surviving in the row nobody re-derived because the diff never touched it |
| Mutation battery, **14** controls | **`MUTATION_EXIT=0`** — 14/14 |
| CTRL-018's observed evidence | see §2b — re-cited at the final head |

**The mutation claim, stated so it can be checked rather than believed.** Each fold gets its own
battery against the controls IT introduced. The fifth fold's is 10 mutants, `MUTATION_EXIT=0`, all
killed on the first run — including a de-`.distinct()` of `holders_of_permission`, a revert of
per-recipient CONCLUSION to any-success, and removal of the termination backstop.

The fourth fold's was 11, and its first run returned `MUTATION_EXIT=1` with two survivors: the
savepoint could be deleted from the subject-lookup guard, and the per-family verdict flush could be
collapsed back into one shared statement, both with every test still green. Both were real gaps,
both were closed, and the re-run returned 11/11.

One mutant in the fifth battery was reported `SKIP ... ANCHOR NOT UNIQUE — NOT TESTED` after a
reformat moved its anchor, and the harness counts that as a SURVIVOR rather than a pass. That is
deliberate: a mutation that did not run is not a mutation that was killed, and a battery that
reports otherwise is the same false-green this slice keeps finding.

The wording matters because the previous fold replaced a bounded historical claim — "eleven mutations
were each killed by their intended test" — with the present-tense universal "**every** mutation
against the new controls was killed by its intended test", in two governed records. That universal
is false and was falsified in minutes: `MAX_ALARM_ATTEMPTS = 2`, `MAX_ALARM_ATTEMPTS = 500`, deleting
the lookup guard, gutting `poll_tenant_reproduction_alarms` to `return []`, and relaxing the reason
floor to `>= 0` all survived at that commit. A mutation battery is a LIST OF MUTANTS THAT WERE RUN,
never a property of the codebase; a record that upgrades it into one is claiming coverage nobody
measured.

### 2b. The CTRL-018 citation, and the rule that now governs it

This citation has been wrong TWICE, in the same slice, one generation apart, and the second time was
committed by the fold that fixed the first. That is a process defect, not an accident, so it gets a
rule rather than another correction.

* **First**, the row cited run `31204168002` (head `5fafd00`), whose alarm arm was satisfied by a
  no-recipient SUPPRESSED sentinel — the delivery path had never executed — and whose trigger arm
  counted `pg_trigger` rows, which exist for DISABLED triggers. Both arms were incapable of failing.
  The builder's own commit message had already documented that; the control's status rested on
  evidence its author had written down as insufficient. Four audit lenses flagged it.
* **Second**, the correction cited run `31210543828` (head `ef899a6`) — and then two further folds
  changed 486 lines across 13 files, including `reproduction/service.py`, `registry.py`,
  `reproduction_alarms.py` and the proof harness itself. An auditor following the citation from any
  of the four documents that carry it landed on a green run of code that no longer existed.
* **A third near-miss, in the act of fixing the second.** The re-citation was applied by a blanket
  string replacement of the old run id across all four documents — which also rewrote THIS bullet,
  the historical record of the mistake, so the paragraph briefly said the current citation was the
  wrong one. Caught by reading the result rather than trusting the replace. Worth one line because
  it is the same shape as everything else here: a mechanical fix applied to prose that included its
  own history, with no test that could have noticed.

**The rule, bound to a trigger moment (P7).** A control-status citation names a CI run, and *the
last act before opening the PR* is to run `git diff --name-only <cited-sha>..HEAD` and confirm it
names no production file — no source, no migration, no proof harness; records only. Not "is the
cited SHA an ancestor of the tip", which it always will be, and which is why the weak check never
fires. If anything else appears, the proof re-runs on the new head and the citation moves in all
four documents that carry it (this record, `control_matrix_skeleton.md`,
`canonical_data_model_standard.md`'s ENT-073 row, `delivery_roadmap.md`). It is written into
`claude_operating_instructions.md` as P16 rather than left here as a lesson, because "remember to
re-cite" is exactly the bare-instruction shape P7 forbids.

**The rule was wrong on first use, and applying it is what showed that.** P16 was drafted as "the
cited run's head SHA equals the branch tip" — which is unsatisfiable by construction, because the
commit that WRITES the citation moves the tip, so the rule fails on its own act. The property that
matters is that no code the cited step exercises has changed since the evidence was produced, which
is a diff and not an equality. Corrected before the first application rather than after, but only
because it was applied rather than re-read.

**Applied here, with the check quoted — and the quote itself needed a correction.** The command was
run BEFORE the citation commit, so it returned EMPTY at that moment and does NOT reproduce at the
committed head, where it names the five record files the citation commit touched. That is a P14
problem in a record about P14: evidence must be quoted from the state a reader can reproduce, or the
state must be named alongside it. The rule's actual test — records only, no production file — passes
in both readings. `git diff --name-only 0e1de85..<that citation commit>` returned EMPTY.

**Then the fifth pass changed the code again, and the rule fired for the first time in anger.** The
fourth fold's citation (run `31231894079`, head `0e1de85`) named a run of code that the fifth fold
altered in `reproduction/service.py` and `scheduling/service.py`, so P16 forbade it. Rather than
quietly keep it, the control-matrix row was marked **RE-CITE PENDING** in its own evidence column
and the proof was re-run.

**The third citation** was CI run `31237359327` (head `c9df15f`) — superseded when the sixth and
seventh folds (the different-engine reviews' fixes and the confirmation pass's residuals) changed
`reproduction/service.py` and `reproduction_alarms.py` after that head. P16 fired at its trigger
moment both times.

**The citation, fourth and current:** CI run **`31264940869`**, head **`e7ae526`**, `stack-proof`
job → `success`, step *"Prove a scheduled reproduction detects a planted divergence (CTRL-018)"* →
**`success`** — verified at the STEP level rather than inferred from the run-level conclusion. All
8 jobs green. `git diff --name-only e7ae526..HEAD` names no production file; the working tree holds
only this record set.

**The re-citation was applied by TARGETED edit, not by blanket replacement.** The previous one used
a string replace across four documents and rewrote the historical bullet describing the mistake, so
the record briefly claimed the current citation was the wrong one. Three of the four documents hold
the head SHA exactly once, but this one holds it twice — once historically (the sentence above) and
once as the live citation — and a replace-all cannot tell them apart. Noted because it is the
mechanism, not the care, that has to be different next time.

Counts **MEASURED** on a fresh collect at the merge head: **3,156** collected platform-wide;
**64** in this slice's two suites (56 unit + 8 PostgreSQL) — from 34 when the first review pass ran.

**One gate went RED at this head before it went green, and that is worth the line.** The frozen-tree
`make check-all` returned `CHECK_ALL_EXIT=2` on a formatting failure plus four over-long lines in a
comment written minutes earlier. Tests had been re-run after that edit; lint had not. Had the gate
not been run on a frozen tree with its exit code read rather than assumed, a green test count would
have been quoted with a red gate behind it — the six-consecutive-red-CI shape P14 exists for,
reached from inside the process that is supposed to prevent it. The fourth fold added thirteen: the
infrastructure disposition and its ledger consumer, the subject-lookup guard that had none, a forced
verdict-row collision, the retry bound parameterised over 1/2/5 recipients, the departed-recipient
negative control, a mixed FAILED-then-SENT sequence, the NOTIFY vocabulary pin, the REPORT reason
pin, and three on the PostgreSQL tier — including a negative control that demonstrates a bare catch
really does leave the session poisoned, so the reason for the savepoint survives the next edit.

## 3. The Tier-3 forks, and why they existed

Recon found that **three sentences of the ratified OQ-W16P-5 shape could not be built as written**.
Each was verified by hand against the code before being reported, not relayed from an agent.

1. **"Rides the existing scheduler" is not schema-free.** `ck_schedule_model_version_by_family`
   (`0053:101-107`) is a TOTAL ENUMERATION over exactly `VAR` and `EXPOSURE_AGGREGATE`; PostgreSQL
   rejects a third family. 0053's own docstring records this as deliberate. **And SQLite carries no
   CHECK constraints, so the entire unit tier would have gone green on the defect** — only the
   full-PG battery sees it.
2. **"Divergence routes to the webhook notification sink" has no existing path.**
   `BreachNotification.breach_id` is `nullable=False` with an FK to `breach.id`; the queue reads
   only `BREACH.DETECT`/`ESCALATE`; the webhook body hard-coded `"type": "breach-alert"`. Only the
   sink OBJECT is reusable. Writing reproduction rows into that table would also re-open a closed
   HIGH: its cursor filters on `tenant_id` alone, so a repro row with a higher sequence would
   permanently hide every lower-sequence unnotified BREACH alarm.
3. **"Per tenant" has no home** — `scope_portfolio_id` was NOT NULL with a hard FK.

Four forks were put to the user with recommendations; **all four taken as recommended** (remit,
Gate outcome table): relax the column under a family-gated total-enumeration CHECK; mint ENT-073;
three families registered with the rest census-pinned; reuse `breach.review` as the alarm audience.

## 4. What EXECUTION found that reading did not (in-build)

Seven defects found while building, before any review. **Not one was visible to reading, to the
type checker, or to a green test run.** The review's thirteen, the audit's thirty-five and the re-audit's are summarised in §7.

1. **My own planted-divergence test was VACUOUS and reported MATCH.** `make_session_factory` sets
   `expire_on_commit=False`, so after the raw `UPDATE` the session kept serving the pre-plant object
   from its identity map and the comparison never saw the plant. The helper now expires and **reads
   back, asserting the plant landed**. A planted-divergence test that cannot plant is the
   written-believed-inert shape this platform keeps re-finding.
2. **`create_schedule` stringified `scope_portfolio_id` unconditionally**, so the new NULL case
   stored the literal `'None'`. SQLite accepted it happily; PostgreSQL rejects it as `invalid input
   syntax for type uuid`. **The warning about exactly this was already in the file, one line below,
   about the sibling column SCH-2 fixed.**
3. **The deployed proof's first run produced a perfectly green tick over a tenant whose subjects the
   sweep could not see** — the harness minted its own tenant while seeding through the report
   proof's. Zero verdicts, `DISPATCHED`, every operational surface saying fine. **The product-side
   fix is the larger half: a sweep that checked NOTHING is now a FAILED run carrying the reason**,
   because a control that is running, believed and checking nothing is the LQ-1 shape.
4. **Seeding both proof schedules together let the FIRST tick fire both** (`fired=2`), consuming the
   negative arm's tick bucket before there was anything to catch — the arm would have found nothing
   to fire and **passed while proving nothing**.
5. **Tick phase 5 reads `reproduction_check` on every tick**, and the constrained `irp_app` role had
   no grant on it — so under a non-owner role the whole tick fails there. The deployed proof runs as
   the owner and **structurally could not see this**; the full-PG battery did.
6. **`test_scheduler_cadence_pg` reads `calendar_holiday` without granting it** — green only because
   an earlier CI step in the same un-reset database happens to. Pre-existing; fixed here because the
   fresh-schema run exposed it and the file was already being edited.
7. **`mypy` caught two real consequences of the nullability change**: a DTO field narrower than its
   column (which would 500 the whole `/schedules` page on the first tenant-wide schedule) and an
   unguarded scope in `_dispatch_var` (which would have resolved "the latest exposure run for scope
   None"). Both fixed with real guards rather than casts.

## 5. Design decisions worth reviewing

- **Re-execute the BINDER, not the kernel.** Eighteen service modules accept a consume-existing
  `snapshot_id`. A kernel-only re-derivation would prove strictly less — it could not see a change
  in a binder's adjudication — and CTRL-018's wording is "re-runs historical runs". **Verified by
  EXECUTION before adoption** (`PROBE_EXIT=0`): the recompute reproduced the stored values exactly
  and left run/result/audit counts unchanged with `verify_chain` gapless; the positive control (the
  same manoeuvre committed) moved all three.
- **The verdict is control-plane evidence, not a governed number.** ENT-073 binds no snapshot and no
  model of its own — the `breach`/`breach_action` precedent. It DOES bind a `REPRODUCTION`
  `calculation_run`, because OQ-SCH-2-8 requires a schedule's family key to be a real run type.
- **Phase 5 is separate from the sweep**, because phase 1 holds the per-tenant audit advisory lock
  to COMMIT and a sink call there is the API-2b lock-across-I/O anti-pattern. Its queue is an
  per-verdict EVENT QUESTION, not a derived `MAX` cursor — NOTIF-1's lesson that a cursor cannot
  represent a gap. (Bare EXISTENCE was the first rule tried and dropped real alarms; the rule is now
  per-recipient on BOTH halves — an attempt CONCLUDED, or its own FAILED budget spent — with a
  most-tried backstop for termination.) Unlike phase 4 it does **not** head-of-line block: with a
  per-verdict question there
  is no cursor to corrupt, so one poison verdict must not silence the night's other divergences.
- **`first_divergence` names the row key and the field, never the VALUES on the DIVERGED path** (mutation-proven). The UNREPRODUCIBLE path is a stated exception — its reason is a binder's own refusal text, which `_redact` bounds without guaranteeing no identifier appears; carry (n). The moment a read
  surface is added it will be gated by some permission, and the obvious candidate `schedule.view` is
  held by `auditor_3l`, which holds no `valuation.view`/`position.view`/`marketdata.view`. This is
  RPT-2's confirmed disclosure class, pre-empted rather than re-found. Mutation M9 proves the guard.
- **Coverage is a census, not a silence.** Three registered, eighteen excluded with a written reason
  each, union asserted equal to the run-type vocabulary by exact set equality. Two exclusions are
  substantive: CONCENTRATION re-pins current-head classifications; LIQUIDITY has a wall clock in its
  compute.
- **The notification wire format changed, deliberately and not back-compatibly.**
  `NotificationMessage.breach_id` → `subject_id`, plus an `alert_type`; the payload key changed with
  it. The channel has no external consumer (the webhook URL is unset by default and the sink shipped
  one wave ago), and the alternative — a compatibility alias nobody would ever remove — would have
  left a transport that calls every alert a breach.

## 6. Carries

| # | Carry | Trigger |
|---|---|---|
| (a) | **Eighteen families remain unreproduced**, each with a written reason. Sixteen are "not yet adapted" and cheap (a key/field declaration, sometimes a parameter read-back). | The next reproduction-touching slice; or when a family's own slice next opens |
| (b) | **CONCENTRATION needs a consume-existing path** before it can ever be reproduced (its binder rebuilds and re-pins current-head classifications) | A concentration-touching slice |
| (c) | **LIQUIDITY's staleness gate is wall-clock**, so re-anchoring it on pinned content (the `var_service` precedent) is a change to a shipped governed refusal — a model-identity question, not a reproduction decision | A liquidity/model-governance gate |
| (d) | **CTRL-018 is Implemented, not Operational.** The schedule that drives the proof is created by a proof harness; no production deployment exists | A real deployment |
| (e) | **A legitimately-empty tenant now FAILS its nightly sweep** (by design — see §4.3). If an operator surface ever treats a FAILED `scheduled_run` as an incident, this needs a distinct disposition | An operational-alerting slice |
| (f) | **`SCHEDULED_RUN_OUTCOMES` still has zero consumers** and `scheduled_run.outcome` has no DB CHECK — a declaration nothing enforces | The next scheduling slice |
| (g) | **The SoD register is missing §5B rows for eight shipped codes** (`schedule.*`, `limit.manage`, `limit.approve`, `breach.respond`, `breach.review`). P11 debt discovered adjacent to this slice, not caused by it | Recorded for the Wave-16 close |
| (i) | **Phase 1 holds the per-tenant audit advisory lock across the FULL re-execution of every registered family's binder.** The remit named this hazard and it is NOT discharged — it is bounded (three families today) but grows with coverage, and the lock is held to the phases-1-2 commit | Before registering more families, or any parallelization work |
| (j) | **An alarming verdict re-fires every night.** Each sweep mints a fresh verdict row for the same subject, so a genuine DIVERGED alarms nightly until the underlying divergence is resolved. No acknowledgement mechanism exists | An operator-workflow slice |
| (k) | **Phase 5's queue is two unbounded scans per tick** (every alarming verdict + every dispatch event for the tenant), run at the supervisor's 300s cadence. Correct but O(history) | A performance or retention slice |
| (l) | **A sweep that checked NOTHING is invisible to the ALARM channel.** It fails closed in the run ledger (a FAILED run + reason) but writes no verdict row, so phase 5 has nothing to alarm on — an operator watching only notifications cannot tell it from a clean night | An operational-alerting slice |
| (m) | **No demo or deploy path creates a REPRODUCTION schedule** — only the proof harness does. A deployed tenant gets the engine and the family but no nightly sweep until someone creates one, and there is no schedule WRITE API. **This was IN the remit's scope ("a nightly schedule the demo/deploy path creates") and was not built; the deviation is recorded here rather than left silent** | The next scheduling or demo slice |
| (n) | **`first_divergence` can carry governed VALUES on the UNREPRODUCIBLE path.** The DIVERGED path names field+key only (mutation-proven), but an UNREPRODUCIBLE reason embeds a binder's exception text, and some binder messages interpolate row identifiers. `_redact` strips SQL/params but not message bodies | Before any read surface is added over ENT-073 |
| (o) | **A divergence detected while no principal holds `breach.review` is NOT re-alarmed when one is provisioned later.** The ratified trade-off (2026-08-07): a SUPPRESSED attempt is terminal because re-POSTing it every 300s tells nobody anything new. The verdict row and the operational surface remain. **The concrete shape this covers, stated so it is ACCEPTED rather than discovered** (independent review, 2026-08-08): a failed delivery followed by a single transiently-empty holder-set tick CONCLUDES the verdict and cancels the failing recipient's remaining retries — reviewer leaves on the Friday, replacement provisioned on the Monday, and Thursday's owed retries are cancelled by Saturday's empty read. That is the same mechanism that makes SUPPRESSED terminal at all, and it is what fixed the unbounded sentinel loop; it is not a separate defect | A tenant-onboarding/provisioning slice |
| (r) | **An already-delivered recipient is re-paged on retry ticks.** Delivery is per-verdict while the queue is per-attempt, so a tick that retries for the un-reached holders also re-POSTs to the ones already told. Bounded at `MAX_ALARM_ATTEMPTS` and it stops at the first fully-concluded tick (measured: one extra page in the depart-and-recover case), but "retry the wire, not the audience" is not literally what the delivery path does | An operational-alerting slice, with (l) and (q) |
| (s) | **A recipient provisioned mid-outage can be retired at 1 of `MAX_ALARM_ATTEMPTS` attempts.** The termination backstop counts attempts on the verdict, not on the recipient, so someone added on the last attempt gets one. The alternative is the non-terminating rule that this bound exists to prevent | Same host as (r) |
| (p) | **Three ENT-072 columns are OUTSIDE reproduction's reach entirely** — `report_code`, `report_version_label` and `render_format` are stored declarations that `regenerate_report` neither reads nor re-derives, so a tampered value reproduces as MATCH. They cannot be compared (the recompute does not produce them) and are now excluded under `_WHY_NOT_REDERIVED`, which says so. Closing it means regeneration asserting the declaration it re-renders under | The next report slice |
| (t) | **A single permanently-malformed `NOTIFY.DISPATCH` payload makes phase 5 PERMANENTLY INERT for that tenant.** The queue-read guard returns `[]`, which every programmatic consumer reads as "nothing to alarm"; only the log line differs. Every tick then logs and delivers nothing, and no alarm fires about the alarm system. Named here rather than discovered later | An operational-alerting slice, with (l) and (q) |
| (q) | **The alarm retry bound does not cover a failed alarm TRANSACTION.** `MAX_ALARM_ATTEMPTS` counts durably-recorded FAILED attempts; a verdict whose transaction rolls back records nothing, so that path retries every tick indefinitely. Recording a failure inside the transaction that just failed is not available — the honest fix is an operational signal on repeated rollback | An operational-alerting slice, with carry (l) |
| (h) | **RPT-1's claim that `report/service.py` is "recorded on the P8 census exception list" is false as written** — the exception dict contains only `exposure/service.py`, and the census scans for a literal `execute_governed_run(` that `report/service.py` never calls. REPRO-1's binder is in the same position and this record says so plainly rather than repeating the claim | Recorded for the Wave-16 close |

## 7. Scrutiny actually applied, and what each stage found

Written after the fact, not before it. The first draft of this section asserted in the past tense
that a pre-merge audit "ran" — in a file committed two commits before any audit existed. The audit
caught it, which is a fair illustration of why the sentence was wrong.

| Stage | Outcome |
|---|---|
| In-build execution | 7 defects (§4) |
| 5-lens adversarial review, each finding attacked by an independent skeptic | **13 verified findings, 2 BLOCKING** — both reproduced verbatim by the skeptics before anything was changed |
| Fresh-context pre-merge audit, weighted at the review's own fold | **35 findings, 2 of 4 lenses returning DO_NOT_MERGE** — including a regression the review fold itself introduced, and a false evidence citation in four documents |
| Focused re-audit of THAT fold (user-requested) | **33 findings, 4 of 4 lenses returning DO_NOT_MERGE.** The audit fold had introduced a HIGH of its own — filtering the alarm queue on SENT-only turned an un-deliverable verdict into an unbounded 300-second retry loop, ~288 hash-chained audit rows per verdict per day — and two of its stated fixes were false: the census's reason floor was satisfiable by copying an existing constant, and the RTM table fix removed the blockquote but left the blank line, so **44** rows still did not render (the number is measured — this row said 47 for one commit while the RTM's own note three lines away said 44, which is two governed records disagreeing about the same defect) |
| **Fourth focused pass** over the re-audit's fold (user-requested), 5 lenses + a serialised executor + a records verifier + a completeness critic | **TWO BLOCKING, both confirmed by EXECUTION against a real PostgreSQL, plus a HIGH four lenses had all walked past.** (1) The fold's two new `except` guards had no savepoint, so on PostgreSQL they caught the error and left the transaction ABORTED — the sweep built a correct verdict and died on the next flush, `PERSISTED ROWS: 0`, and the fail-closed FAILED write was itself unreachable. Its unit test raised a plain `RuntimeError` and was green with the bug AND with the fix. (2) `MAX_ALARM_ATTEMPTS` counted audit ROWS while one attempt emits one row per RECIPIENT, so at the five holders a 2L desk normally has, a single failed tick retired the alarm forever — v1's dropped-alarm defect re-created by v2's fix, invisible because the test pinned exactly one recipient. (3) Three of the five REPORT exclusions carried a reason that was factually false about what `regenerate_report` reads: a tampered `render_format` produced a durable MATCH. Every existing guard passed over it — the column census, the 40-character reason floor, and a `_MUST_COMPARE` pin holding only the one column that cannot diverge |
| **Fifth focused pass** over the fourth fold (user-requested), same 5-lens + serialised-executor + records + critic shape | **ONE BLOCKING and four HIGHs, and the BLOCKING was introduced BY THE FOURTH FOLD.** (1) A verdict COMPUTED as DIVERGED whose row failed to INSERT was routed into the non-alarming `unresolved` bucket, so the risk desk was never paged — and the governed `failure_reason` then read *"This is NOT a divergence ... which is why no alarm was raised"*, the evidence column asserting the negation of what the sweep had just measured. (2) That same sentence was UNCONDITIONAL, so it also fired on a night where another family genuinely diverged and phase 5 WAS paging: an operator woken at 02:00 had documentary grounds to dismiss the alarm. (3) Giving `unresolved` a consumer made any per-family infrastructure failure fail the WHOLE sweep, so a divergence + one lock timeout reported as an infrastructure failure — violating I3, whose own test predates the change and drives a clean sweep. (4) The `LINE` redaction fix had been applied to the reproduction redactor only; the SIBLING `scheduling.service.redact_failure_reason` — the one with a SHIPPED HTTP reader on `GET /schedules/runs`, gated on `schedule.view`, held by `auditor_3l` — still served verbatim SQL. Fixing the instance, not the class (P10). (5) EXHAUSTION had been rebuilt per-recipient while CONCLUSION stayed per-verdict, so one recipient's success retired the verdict for everyone: five holders, one good address, and four are never told about a live divergence and never retried. |
| **Two independent reviews on a DIFFERENT ENGINE** (Fable), after five passes on one engine had each folded a defect into the next | **The missing ingredient was a different assumption set, not more effort on the same one.** Review 1 found a SIXTH BLOCKING in one pass: v5's per-recipient retirement could not terminate, because a recipient who leaves the holder set at `failed=2` freezes a state no later tick can advance — executed, 25 ticks post-departure still queued and re-paging a live reviewer, and a second ordering appended a SUPPRESSED sentinel every tick forever, falsifying the RATIFIED terminal-SUPPRESSED rule. My own negative control covered only the sub-case the backstop handles. Review 2 proved the state-space simplification behaviour-IDENTICAL by differential execution — both implementations driven through 13 disposition combinations, `ANY_DIFF: False` — which is the first claim in this slice proven rather than argued, and it separately proved the "latest attempt" selection structurally unambiguous from the audit chain's own uniqueness constraint rather than by test. It also caught that I was EDITING THE TREE WHILE IT REVIEWED, making it chase mid-edit artifacts; the re-review ran against pinned hashes. The v6 fix was then sent back to review 1, which found the one defect in it — my `ungrouped-{seq}` fallback resurrected v3 AND v4 at the upgrade boundary, and the comment justifying it asserted the opposite of the truth |

**The audit's decisive finding was about this slice's own records, not its code:** CTRL-018 had been
moved to Implemented citing a CI run of the PRE-FOLD proof harness — the run whose alarm arm and
trigger arm the fold's own commit message documented as unable to fail. The control's status rested
on evidence the builder had already written down as insufficient.

**Each fold introduced a defect the next stage caught — twice, in a row.** The review's fold: the new duplicate-natural-key
refusal was raised OUTSIDE `check_one_family`'s guard, re-creating the exact blast radius the
BLOCKING savepoint fix had just removed — a ValueError escaping the sweep and discarding the
night's other verdicts. Three lenses found it independently. The mutation battery then caught that
my *fix* for it had no test: the direct-call test stayed green with the guard removed.

**Model-diversity disclosure.** Both the review and the audit ran on **fresh-context Opus, not a
second engine** — no Fable allocation was available on 2026-08-07. RPT-2's evidence is that the
lane which pays is fresh CONTEXT (that audit was itself Opus and still found what five hostile
lenses missed), and this slice repeated the pattern: the audit found what the review could not. The
loss is the engine half of P15, stated as a fact rather than left as an implied full-strength claim.

## 8. Explicit no-mint statement (remit I7)

**REPRO-1 mints NO permission code and NO audit code.** The divergence alarm REUSES `breach.review`
as its recipient permission (ratified OQ-REPRO-1-4) and REUSES `NOTIFY.DISPATCH` with a new
`entity_type`, so no catalog-sync migration is owed and `06_security/entitlement_sod_model.md` needs
no new §5B row for this slice. Recorded explicitly because I7 requires it and the first draft of
this record left it to be inferred — which is how the eight-codes-with-no-SoD-row debt in carry (g)
accumulated in the first place.
