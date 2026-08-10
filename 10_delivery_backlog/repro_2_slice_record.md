# REPRO-2 slice record — the reproduction control becomes startable

**Status:** **PART 1 MERGED** (PR #197 = `80e6b9f`, the 28th autonomous merge — OQ-REP2-1/2/3).
**PART 2 BUILT + gated** (OQ-REP2-4/5/6) — the finding in §5 is DISCHARGED; see §8.

**Wave 17, slice 2.** Branch `repro-2-impl`. Design authority:
`repro_2_decision_record.md` v3 + the ratification stamp (2026-08-10, four decision points, all
as recommended).

## 1. What shipped in part 1

### OQ-REP2-1 — registry-driven discovery (the ONBOARD-1a carry, PAID)

`apps/worker/src/irp_worker/discovery.py` + `run_supervisor_discovering`. An ACTIVE tenant in the
ENT-074 registry is ticked within one cycle of onboarding: no config edit, no restart. Every
ratified disposition is implemented and tested — unset/blank filter → unrestricted; malformed
entry → REFUSE (the strict-parse supersession); unknown id → REFUSE (FOLD-2 retained); unreadable
registry → cycle skipped, never mistaken for zero tenants, scalar streak escalation; zero ACTIVE
tenants → idle LOUDLY every cycle; one-shot `--tenant` validated against registry AND status.

**The blast radius, all twelve carriers amended in-slice**: `parse_tenant_ids` (strict);
`supervisor.py` docstring/refusals/`IRP_MAX_CYCLES`; the tenant-create API's `WORKER_FOLLOWUP`
string **and its pin test** (rewritten, not deleted — the response now states the true follow-up);
`deploy.sh` step 8 INVERTED to a bounded idle proof **plus a new step 8b holding the retained
fail-closed arm**; `.env.example`; `docker-compose.yml`; `apps/worker/README.md`; the CI comment;
CTRL-031's row; the CAD-1 record at four sites (Status, OQ-2, OQ-3, FOLD-2), each stating which
half is superseded and which retained; `prove_reproduction.sh`'s premise.

### OQ-REP2-2 — the schedule WRITE path (SCH-1's forward gate, DISCHARGED)

`POST /schedules`, `/{id}/pause`, `/{id}/resume` on `schedule.manage`. The
`UNROUTED_FORWARD_GATES` entry is DELETED (the census forced it — "a resolved entry means the
route landed: DELETE the entry (and celebrate)") and the BINDING catalog comment at
`bootstrap.py` is amended. Route census 301 → 304, conscious. Duplicate codes refuse cleanly by
catching the unique violation, not by a pre-check alone.

**The pause adjudication, made real**: `control_switched_off` joins ALERT-1's `healthy` fold — a
tenant that CONFIGURED the control and then paused every schedule reads RED. The shipped ALERT-1
test asserting `healthy is True` at that state was REWRITTEN as the amendment's twin (never
deleted), with two informational neighbours (never-configured; partially-paused) keeping it from
being a blunt instrument.

### OQ-REP2-3 — the verdict read (carry (n), DISCHARGED BY EXCLUSION)

`GET /reproduction/checks` on `schedule.view`, ordered, windowed, page-capped. DIVERGED rows
carry their field+key label; **UNREPRODUCIBLE rows carry a fixed literal and the stored text
never reaches the wire** — no parsing, nothing defeatable by an exception message shaped unlike
the ones we imagined. Proven with its positive twin first (the marker is asserted present in the
STORED row, then absent from the entire response).

`IDENTITY_EXCLUDED_COLUMNS` MINTED with `identity_offenders` — the rule in production code beside
the list it enforces — so the sixteen adapters still to come cannot key on an identity class the
verdict read's audience is excluded from.

## 2. Gates (P14)

- Unit/worker/endpoint suites for the built work: green (worker 38; alarm-health 29;
  schedule-admin 13; reproduction endpoint 10; identity census 5).
- Mutation battery group `repro-2`: **14/14 KILLED**, `MUTATION_EXIT=0`.
- `make check-all`, full-PG: recorded in the commit message.

## 3. Defects found, and by what

### By the mutation battery — two survivors, two real gaps

1. **The `IntegrityError` catch had no test.** Every duplicate-code test took the pre-check path,
   so deleting the catch — the only mechanism that closes the concurrent race the record names —
   left the suite green. A direct mapping test now covers it.
2. **The identity census was VACUOUS.** Its rule lived inside the test, and there are no
   offenders in the current registry, so emptying the walk was indistinguishable from a clean
   walk. This is the hollow-guard class this project has shipped three times. The rule moved into
   production code (`identity_offenders`), both the census and its planted-offender negative
   control now exercise the same path, and the mutant re-anchored there.

### By the mechanical gates, working as designed

3. The route census refused the slice until the forward-gate entry was deleted AND the count
   moved consciously — both in the same run.
4. ALERT-1's paused-disposition test refused the amendment until it was rewritten as the
   amendment's twin — exactly the collision verifier pass 2 predicted by name.

## 4. Deviations from the record

None in the built scope.

## 5. THE FINDING: this slice needs a second build pass

**OQ-REP2-4 (sixteen family adapters), OQ-REP2-5 (demo stage + the deployed second-tenant arm),
and OQ-REP2-6 (the `/ops/reproduction` screen) are NOT in this commit.**

This is reported as a finding at the gate rather than absorbed silently, because the alternative
was worse in a way this project has already paid for: sixteen adapters means sixteen unfamiliar
binders, each needing a key/field declaration, a binder resolution, a reproduce-green test, a
planted-divergence test, and — per the ratified proof shape — an exclusion-truth tamper test per
uncompared column. Rushing them produces exactly the defect class the exclusion-truth obligation
exists to catch: a well-written but FALSE `uncompared` reason producing a durable MATCH over a
tampered governed value. A shallow adapter is worse than an absent one, because an absent family
is visible in the coverage census and a wrong one is not.

What part 1 delivers standalone: the control is STARTABLE (a real tenant can create a schedule
over HTTP and the worker will tick it), its verdicts are READABLE, and switching it off is
VISIBLE. What part 2 owes: more families under that control, the demo/deploy seeding, and the
screen.

The coverage census still reads 3+18 and says so honestly — no claim about sixteen families has
been made anywhere in the code or the ledgers.

## 6. The different-engine review fold (Fable, 2026-08-10, over `e56d9b0..60c4f2d`)

Six findings, two blocking — every one verified by execution or against the ratified record's own
sentences before it was folded (P15 held for the ninth consecutive time: the other engine found
what the builder certified).

1. **BLOCKING — the committed battery claim was false of the committed tree.** The commit said
   14/14 KILLED; re-running the battery at HEAD reported **R-C3: ANCHOR NOT MATCHED — a
   SURVIVOR**. `ruff format` had reformatted `identity_offenders`' single-line return into three
   lines AFTER the battery ran, so the 14/14 was true of bytes that were never committed. Same
   class as FK-1's displaced-bytes lesson, reached by the formatter instead of the battery.
   R-C3 re-anchored; **and the fold's own supervisor edit displaced R-A6's anchor the same way,
   caught by the same re-run discipline before commit.** The battery run that counts is the one
   against the bytes being committed, after the formatter.
2. **BLOCKING — a ratified carrier was omitted.** The record ratifies BY NAME (OQ-REP2-2): *"the
   `/ops/alerting` panel renders it with its operator action."* The build shipped
   `control_switched_off` in the API, the healthy fold and the field pin — and never touched
   `Alerting.tsx`. An all-paused tenant read NOT HEALTHY with ZERO red rows, under a lede calling
   the state "a gap in what has been set up, not a fault" (`no_schedule` is also true there), with
   the paused-schedules row advising "No action". The panel now renders the red row with its
   action, the lede gives switch-off precedence over the gap text, and the paused row points at
   the red signal — with the FE test asserting all three.
3. **HIGH — two ratified dispositions conflated.** The record's refusal row reads "any listed id
   is **unknown to the registry**"; the built code refused anything **not listed as ACTIVE**. On
   the collision input — a pinned tenant SUSPENDED mid-run beside a live one — the conflation
   raised out of discovery and killed the engine for every other pinned tenant: a crash-loop
   bought with a legitimate governed act, contradicting the ratified "SUSPENDED → Never ticked"
   (honored gracefully in the unrestricted case). Now: unknown-to-registry refuses (FOLD-2
   retained, verbatim); a known-but-inactive pinned tenant drops out of the tick set with a
   per-cycle WARNING and resumes within one cycle of reactivation; a restriction pinning ONLY
   inactive tenants idles loudly with its own restricted-idle announcement (saying "no ACTIVE
   tenants in the registry" there would be false — other tenants may exist). Mutant R-A7 pins the
   conflation; `deploy.sh` step 8b's grep moved in lockstep with the refusal message.
4. **MEDIUM — the worker README still stated the superseded facts** ("a malformed entry is
   skipped (the rest keep ticking); an empty list fails closed at startup", and "the app never
   sweeps the database for tenants") one sentence after the amended one. The twelve-carrier sweep
   amended the bullet's first half and stopped reading. Rewritten.
5. **LOW — `prove_reproduction.sh`'s amended premise mixed tenses**: the inserted parenthetical
   left "the supervisor fails closed on an empty list — so deploy.sh's worker step proves only
   that the REFUSAL fires" standing as present-tense fact. Rewritten as history.
6. **LOW — the create route's `except IntegrityError` mapped EVERY constraint violation to
   "a schedule with code X already exists"** — a false statement in a governed refusal whenever
   the violation was a foreign key (a calendar id, say). The route now asks the database which
   case it is (after rollback the racing winner's committed row is visible); both arms tested.
7. **HIGH — found by CI after the fold, missed by the review AND the blast-radius sweep:**
   `test_supervisor_main_empty_tenant_ids_fails_closed` still asserted the SUPERSEDED FOLD-2
   empty-list refusal — and kept passing locally through a completely different refusal that
   shares exit code 2 (the fake DB URL made the startup REGISTRY read refuse). CI's backend job
   has no `psycopg`, so the test errored at the engine creation the behavior it claimed to pin
   never reached — surfacing that it had been vacuous since the supersession. Both `main()`-level
   tests rewritten to pin the refusal MESSAGE, not just the exit code: an exit code shared
   between two refusals is exactly how a superseded test stays green.

## 7. Carries

Unchanged from the record's §4 non-goals, each with its trigger.

## 8. PART 2 — the sixteen families, the seeding, and the screen (OQ-REP2-4/5/6)

Part 1 reported at its gate that this work was owed rather than absorbing it silently. This is it.

### OQ-REP2-4 — sixteen adapters; the coverage census moves 3+18 → 19+2

`reproduction/families.py`. Eleven families share one shape (read the run's rows in key order;
call one binder with the run's own pinned `snapshot_id` and `model_version_id`; project) and are
built by one factory; five needed more and say so at their own definitions — two backtests, the
two window-recovering families, and PROXY_WEIGHT_ESTIMATE.

**`compared_fields` is now DERIVED, not hand-listed** — the model's columns minus what was
explicitly excused. This inverts REPRO-1's convention deliberately: there, a hand-written list
silently omitted six governed columns and a planted change to `n_factors` produced a durable
MATCH. Deriving makes that omission unrepresentable — a new column joins the comparison by
default, and leaving it out requires writing a reason down.

**Every one of the sixteen was made to say YES and then made to say NO**: a real subject run built
through that family's own production binder reproduces MATCH over a non-zero row count, then one
governed value column is tampered (raw SQL, because IA append-only refuses the UPDATE — that
control working) and the same machinery must report DIVERGED naming the field. Both proxy-weight
binder arms are covered, including the empirical-Bayes path whose target has no stored column.

**FOUR of the sixteen "not yet adapted" reasons were FACTUALLY WRONG about the binders they
described** — the `_WHY_RENDER_INPUT` class, one level up, and none of them could have been caught
by reading prose:
- **BENCHMARK_RELATIVE**: "read `return_basis` + `benchmark_id` back off the stored rows" — the
  binder REFUSES both alongside `snapshot_id` and adjudicates them out of the pin itself. An
  adapter written to that instruction raises on every run.
- **PROXY_WEIGHT_ESTIMATE**: "binder resolution by model code" — unimplementable. Both binders
  assert the SAME code; the resolver returns one string for both. The discriminator is the
  version's declared estimator convention, which is also how production dispatches.
- **VAR_BACKTEST** and **COVARIANCE_PRIVATE**: the same "shared result table needs binder
  resolution" reading, when both pairs are disjoint by RUN TYPE and the sweep resolves per run
  type. A shared table was read as implying a shared dispatch problem; it does not.

**The exclusion-truth obligation is discharged by CONSTRUCTION.** It asked for a tamper proof per
`uncompared` column outside the two by-construction classes; these sixteen have none — every
exclusion is a mixin column or a governed-run FK. `test_no_new_family_has_a_DISCRETIONARY_exclusion`
is what keeps that true and states what is owed the day one appears.

*(A defect of exactly that class was caught in this build, in my own code: four upstream-run FK
columns were excused as "differs by construction" by analogy with VAR's columns of the same NAME.
The writers set them from `parsed.*` — the adjudicated pin — so they reproduce exactly. They are
compared now, and ACTIVE_RISK's green sweep is the executed proof.)*

### OQ-REP2-5 — carry (m), discharged against artifacts that exist

- **Demo**: `run_demo_campaign` registers the demo tenant in ENT-074 (ACTIVE, idempotent, tolerant
  of a 0067 backfill) and creates its nightly reproduction schedule **through the real
  `create_schedule` service** — a demo that seeds around its own service demonstrates nothing about
  the service, and the audit event is the tell. **This AMENDS an OPS-H1-ratified disposition**
  (enrolment was opt-IN; under discovery it is opt-OUT), annotated at BOTH carriers with the
  isolation rule it creates for PG tests.
- **Deploy**: `prove_reproduction.sh` gains a SECOND tenant created over HTTP through ONBOARD-1a,
  its `schedule.manage` principal provisioned through ONBOARD-1b, its schedule created over HTTP
  through REPRO-2's own write path — and then the SUPERVISOR runs with **nothing naming that
  tenant**. It fires. `PROOF_TENANT` and every arm keyed to it are untouched.

### OQ-REP2-6 — the `/ops/reproduction` screen

Schedules (list/create/pause/resume), the verdict table, and the first consumer of
`GET /schedules/runs` (shipped at SCH-2, unread since). `/schedules` joined `API_PREFIXES` with the
nginx alternation in lockstep. Seven FE tests pin the four ways this screen could mislead: no
schedule ≠ clean night; all-paused says the control is OFF and points at Alerting; DIVERGED is
loud and names the field; UNREPRODUCIBLE shows the fixed literal.

### The sweep, MEASURED (ratified R5)

Run against the **real seeded demo book** — a book twenty-three earlier stages built for unrelated
reasons, not fixtures written to make these adapters pass:

```
SWEEP_SECONDS=1.99      SWEEP_FAMILIES_REGISTERED=19
SWEEP_VERDICTS=18       SWEEP_UNRESOLVED=0        SWEEP_STATUS=COMPLETED
```

**All eighteen families with a subject returned MATCH**, over 149 compared rows
(ROLLING_RISK 33, PORTFOLIO_RETURN 20, SHARPE 16, DESMOOTHED_RETURN 13, BENCHMARK_RELATIVE and
PACING_PROJECTION 11 each, and so on). The acceptance is recorded against 1.99s; the ratified
split trigger — a real tenant's sweep exceeding FIVE MINUTES moves the sweep phases out of the
tick's single transaction — is untouched by two orders of magnitude. `scripts/measure_sweep.py` is
the committed instrument (it refuses to report a time for a sweep that judged nothing), and demo
stage 24 carries a deliberately loose 60s regression tripwire rather than a tight benchmark that a
loaded CI runner would teach everyone to ignore.

### Defects found in part 2, and by what

| # | Found by | What |
|---|---|---|
| 1 | **The deployed proof, executed** | The proof never rebuilt the **backend** image, so every HTTP arm ran against an arbitrarily old build. Invisible until an arm asserted on a response BODY: the API returned part 1's superseded `operator_followup` text. |
| 2 | The deployed proof, executed | A guessed SYSTEM-tenant literal (v4-shaped) — the real one is all-zeros-with-1. Reading would never have caught it. |
| 3 | The deployed proof, executed | An `ANCHOR_DATE` variable this script never defined, caught by `set -u`. |
| 4 | **The mutation battery** | FIVE survivors on the first run — the refusal mapping, the window recovery, both proxy-weight guards, and the install itself all had NO test. |
| 5 | The battery, again | Two of my *replacement* tests passed without killing their mutants: the guards they targeted were **unreachable by contract** (`declared_proxy_weight_parameters` fails closed before the `else` arm; `source_desmoothed_run_id` is NOT NULL). The guard moved to where it can fire; the unreachable arm is documented as a backstop, not presented as protection. |
| 6 | The battery, a third time | The shrinkage test targeted `cohort[0]`, so "pick the first member" and "pick the right member" were the same run. Retargeted to the last member. |
| 7 | The import-direction fence | `reproduction` importing `irp_shared.snapshot`. The cohort parse moved to the service that OWNS the pinned format rather than widening a fence whose value is that each member was argued for. |
| 8 | mypy | A `**kwargs` splat erased two binders' differing signatures. |
| 10 | **The full-PG battery** | The demo seeding was written into `run_demo_campaign`'s BODY, which put an extra ACTIVE schedule into the shared demo tenant before stage 15 — whose tick then dispatched TWO schedules where it asserts exactly one. Seven count pins came up one COMPLETED run short and twelve tests errored. Moved to demo stage 24, seeded LAST; no existing assertion was relaxed. **Adding a schedule to a shared demo tenant is not a local act: it changes what every subsequent tick does.** |
| 9 | The OpenAPI generator | Part 1's `ScheduleOut` collided with the read path's, mangling BOTH into `irp_backend__api__<module>__ScheduleOut` in the generated FE types. Renamed `ScheduleWriteOut`. |

**Anchors moved FOUR times in this slice** (the formatter, a dedupe, a refactor across modules).
Part 1's F1 lesson holds and generalises: a mutant anchor is a claim about bytes, and the battery
run that counts is the one against the bytes being committed.

## 9. The different-engine review fold, part 2 (Fable, 2026-08-10, over `80e6b9f..3281923`)

Three findings, all folded — P15's tenth consecutive hold, and the first one where the strongest
finding was the build's own prose about prose:

1. **The `families.py` module header was FALSE twice, in the module whose subject is false
   prose.** It said "THREE of the sixteen reasons were factually wrong" (it was FOUR — the
   header contradicted the `_backtest_families` docstring forty lines below it, which correctly
   calls the backtests "a FOURTH reason"), and it claimed the backtests "need binder resolution
   by model code (the genuine VAR-shaped case)" — asserting the exact falsehood the code beneath
   it corrects: the backtests use the STANDARD factory shape precisely because they need no
   resolution. The header was drafted before the backtest investigation concluded and never
   updated. Rewritten, with the error recorded in place: a module that documents the
   reads-well-but-false class must not ship an instance of it as its own summary.
2. **Two §3-bound UI proofs were not delivered** — the record binds "component tests —
   create/pause/resume through `writes.ts` with refusal rendering; … the second-active-schedule
   warning" BY NAME, and the shipped suite rendered the buttons without ever exercising a write,
   rendering a refusal, or asserting the warning. Part 1's F2 class (a ratified carrier quietly
   omitted), caught by the same review pattern one part later. Four tests added: Pause POSTs to
   the real path; a 403'd pause renders `explain()`'s plain-language refusal; Create submits and
   a duplicate-code refusal renders; the second-active-schedule warning shows exactly when one
   schedule is ACTIVE and not otherwise. FE suite 7 → 11.
3. **LOW**: the deployed proof's new section was numbered "8" in a script whose sections run
   0–5 (the number was copied from deploy.sh's step 8, a different file). Renumbered 6.

Recorded deviations, checked and accepted rather than folded: the part-2 battery group is named
`repro-2b` where the record's proof list says "group `repro-2`" (both groups run at every gate;
the split keeps part 1's 15 anchors and part 2's 7 independently re-runnable); and the
exclusion-truth obligation's per-column tamper tests are vacuously satisfied (zero discretionary
exclusions exist) with the census demanding the ratified proof shape the day one appears — the
review verified the census fails with that exact instruction rather than silently.

One property the review checked and confirms rather than assumes: `compare_rows` matches by KEY
(dict), not by position, so the stored-side SQL ordering and the recompute-side writer ordering
cannot produce a false divergence — and its duplicate-key guard covers the eight new multi-row
grains this slice registered.
