# REPRO-2 slice record — the reproduction control becomes startable

**Status:** PART 1 BUILT + gated (OQ-REP2-1/2/3); **OQ-REP2-4/5/6 REMAIN — a stated finding, not
an omission (see §5)**

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

## 7. Carries

Unchanged from the record's §4 non-goals, each with its trigger.
