# REPRO-2 decision record — the reproduction control becomes STARTABLE

**Status:** DRAFT v2 — post-pass-1, pre-pass-2

**Wave 17, slice 2** (the ratified Part 2.19 sequence). Branch `repro-2-planning`. Design
authority once ratified: THIS record.

## 1. What this slice is

CTRL-018 is real code no deployed tenant can run: the sweep exists, the alarm channel is now
observable (ALERT-1), and yet a real tenant cannot START any of it — no schedule write path, a
worker that ticks only hand-configured tenant ids, and verdicts readable by nobody. REPRO-2 is
the startability slice.

Carries riding in, verbatim sources: ONBOARD-1a ("the worker still does not tick a created
tenant — `IRP_TENANT_IDS` stays deploy config; the carry rides to REPRO-2 by name"); REPRO-1 (m)
("no demo or deploy path creates a REPRODUCTION schedule — only the proof harness does");
REPRO-1 (n) ("`first_divergence` can carry governed VALUES on the UNREPRODUCIBLE path … before
any read surface is added over ENT-073"); SCH-2's reserved question ("a create/pause API is its
own slice with its own maker-checker question").

## 2. Decisions (OQ-REP2-1…7)

### OQ-REP2-1 — Worker tenant discovery: SUPERSEDE **OQ-CAD-1-2=A**, registry-driven — with every disposition stated

*(Pass 1, R15: v1 named the wrong ratified decision. The config-not-DB-sweep choice is
**CAD-1's OQ-2=A** — `IRP_TENANT_IDS` did not exist until CAD-1. And what is explicitly NOT
reopened: **OQ-SCH-1-1=B** — infra-driven per-tenant dispatch, the app 100% non-BYPASSRLS. The
registry read requires no bypass of anything: ENT-074 is deliberately PLATFORM-GLOBAL, read on
every authenticated request since ONBOARD-1a.)*

**The supersession, with CAD-1 FOLD-2's actual rationale quoted and answered** (pass 1, R18).
FOLD-2's recorded reason was not "an empty list is probably a typo"; it was: *"a silently-idle
engine is the exact failure this slice exists to prevent."* That rationale is answered head-on,
disposition by disposition — silence remains impossible; what changes is only WHICH states are
legitimate:

| State | Disposition |
|---|---|
| Restriction filter UNSET, registry has zero ACTIVE tenants | **Idle-and-re-poll, loudly logged each cycle** — the truthful state of a fresh platform; a crash-looping worker would make ONBOARD-1's ignition depend on restart orchestration. NOT silent: the idle line is asserted by the deployed proof |
| Restriction filter SET and any listed id is unknown to the registry — a fortiori an empty intersection | **REFUSE TO START (the CAD-1 FOLD-2 behavior, retained)** — this is a definite misconfiguration, and idling here would be the silently-idle-but-looks-configured state FOLD-2 ratified against (pass 1, R6) |
| The registry READ fails (exception, missing table) | **Never treated as zero tenants.** A transient failure skips the cycle with a distinct logged error and ticks nothing; a consecutive-failure streak escalates through the supervisor's existing `_FAILURE_STREAK` machinery. At startup, an unreadable registry REFUSES to start (pass 1, R8) |
| A tenant onboarded mid-operation | Ticked from the next cycle (the list is re-read per cycle) |
| A tenant SUSPENDED / not ACTIVE / SYSTEM | Never ticked |
| The one-shot `--tenant` entrypoint | Retained as an operator override and now VALIDATED against the registry: an id the registry does not know is refused (pass-1 minor — the old form would tick any id) |

`IRP_TENANT_IDS` becomes an optional RESTRICTION (intersect; it can pin a subset, it can no
longer invent a tenant).

**The blast radius, enumerated in-slice** (pass 1, R19 — the AD-013-R2 mechanics: a supersession
amends every carrier of the old fact, not just its own record): `supervisor.py`'s docstring and
refusal text; **`deploy.sh` step 8 — an EXECUTED CI gate that today REQUIRES exit 2 on zero
tenants and would HANG under idle-and-poll** (pass 1, R4/R7/R16/R23: rewritten to a bounded
idle proof — the worker starts, emits the documented idle line, and exits cleanly under a
bounded-cycles seam; the closing "proven to fail closed" banner and `.env.example`'s
`IRP_TENANT_IDS` comment rewritten with it); `prove_reproduction.sh`'s premise comment; the
onboarding runbook sentence; and a superseded-by annotation ON the CAD-1 record's OQ-2 row.

### OQ-REP2-2 — The schedule WRITE path: three routes, the holder set enumerated, and the maker-checker question SPLIT

`POST /schedules`, `POST /schedules/{id}/pause`, `POST /schedules/{id}/resume` — ordinary
`require_permission("schedule.manage")`, discharging the SCH-1 forward-gate (the census entry is
DELETED; the catalog comment at `entitlement/bootstrap.py` — the BINDING record, per the
liquidity.run precedent — is amended in the same commit; route count +3, conscious). Validation
is the existing `create_schedule` fail-closed rule set, PLUS one transport-level courtesy: the
route pre-checks `(tenant_id, code)` and refuses a duplicate code as a clean 409-class
`ScheduleError` instead of a raw IntegrityError 500 (pass 1, R3). **There is deliberately NO
one-REPRODUCTION-schedule-per-tenant rule** — the deployed proof itself legitimately runs two;
a second schedule double-runs and double-pages, which is legal, visible (the runs ledger and the
alarm-health panel both show it), and the UI warns before creating a second schedule for a
family that already has an ACTIVE one.

**The holder set, recomputed from `ROLE_TEMPLATES` source** (pass 1, R13): `schedule.manage` =
`data_steward`, `risk_analyst_1l`, `platform_admin` — and in a CUSTOMER tenant (platform_admin
never cloned) that means **`data_steward` and `risk_analyst_1l` only**. `tenant_admin` holds
nothing schedule-shaped, consistent with the ALERT-1 doctrine (a tenant admin administers
people), and the onboarding consequence is stated rather than discovered: a fresh tenant's
first admin cannot start the control themselves — they create a user, grant `data_steward` or
`risk_analyst_1l` (four-eyes applies to THAT grant), and that person clicks. Revisit trigger:
the first real tenant that finds this two-step onboarding a blocker.

**The reserved maker-checker question, SPLIT** (pass 1, R9 — v1's blanket NO never confronted
its strongest counter):

- **CREATE and RESUME: no four-eyes.** They only ADD detection; every act a schedule triggers
  is itself fully governed; friction here delays the control this wave exists to start.
- **PAUSE is the strongest counter, adjudicated in the open:** pausing a REPRODUCTION schedule
  is a one-person, reversible switch-off of the platform's only detective control over
  governed-number drift — held by `risk_analyst_1l`, the very population whose runs CTRL-018
  re-checks — and under ALERT-1's ratified dispositions a fully-paused tenant reads
  `paused_schedules` (informational) + `no_schedule` (informational): **silent green during the
  tamper window.** The recommendation is a COMPENSATING DETECTIVE VISIBILITY, not four-eyes:
  **the `control_switched_off` red** — a tenant with ≥1 reproduction schedule and ZERO ACTIVE
  ones joins the ALERT-1 `healthy` fold as red. This AMENDS an ALERT-1-ratified disposition
  (`no_schedule`/`paused_schedules` stay informational only while nothing was ever configured)
  and is put to the gate BY NAME as part of this OQ. Pause itself stays one-person (the
  SCHEDULE.UPDATE audit row + the panel showing who/when are the trail); four-eyes-on-pause is
  the recorded alternative if the residual is unacceptable. Revisit trigger: the first
  suspicious pause in a real tenant's audit review.

### OQ-REP2-3 — The verdict READ surface: carry (n) discharged BY PURE EXCLUSION

`GET /reproduction/checks` (tenant-local; filters family/verdict/since), gated on
`schedule.view` (the ALERT-1 audience). Payload per row: `id`, `family_key`, `verdict`,
`rows_compared`, `rows_diverged`, `subject_run_id`, `calculation_run_id`, `system_from`, and
`first_divergence` **under the following rule** (v1's strict option was UNIMPLEMENTABLE — pass
1's strongest convergence, R1/R10/R12: the exception class name is NOT recoverable from stored
text on the dominant UNREPRODUCIBLE paths, v1's own example class cannot even occur in an
ENT-073 row since the 2026-08-07 disposition ratification, and parsing would EMIT the message
body on exactly the rows that lack a class prefix — the opposite of the intent):

- **DIVERGED rows**: `first_divergence` verbatim — row KEY + field, mutation-proven at REPRO-1,
  and now guarded by the OQ-REP2-4 key-class invariant below.
- **UNREPRODUCIBLE rows**: the payload carries the FIXED LITERAL
  `"UNREPRODUCIBLE — detail withheld; investigate at database grade"` — no parsing, no
  transport of stored text, satisfiable over every existing row, no migration. Carry (n) is
  discharged by exclusion: no read surface transports the bounded-but-unguaranteed text, ever.
- **MATCH rows**: null.

**The key-class invariant** (pass 1, R14): a registered family's `key_fields` — and therefore
every DIVERGED divergence label this surface ships — must contain NO column of an identity
class withheld from any `schedule.view` holder (issuer identity, person identity — the
CON-1/REF-1 exclusions). Proven MECHANICALLY: a census test walks every registered family's
declared key and compared fields against the named identity-column classes, so the sixteen new
declarations (OQ-REP2-4) cannot smuggle one in.

### OQ-REP2-4 — Families: ALL SIXTEEN mechanically-adaptable, each with the exclusion-truth proof

Register all sixteen "not yet adapted" families (the two structural stay out with their
triggers: CONCENTRATION — no snapshot consume path; LIQUIDITY — wall clock inside a shipped
governed refusal, a model-identity question). Coverage census 3+18 → 19+2, reasons preserved.

Two obligations pass 1 added:

- **The exclusion-truth proof, per adapter** (R11): a planted-divergence test proves only the
  DECLARED fields detect plants — the uncaught class is a well-written but FALSE `uncompared`
  reason producing a durable MATCH over a tampered value. Every new adapter's `uncompared`
  column outside the two by-construction classes gets the REPORT treatment: tamper the excluded
  column, assert the sweep still MATCHES, and assert the exclusion REASON names why that is
  correct — sixteen-fold, priced in.
- **Sweep runtime, measured and accepted** (R5): a 19-family sweep re-executes every binder
  sequentially inside the tick's phases-1-2 transaction, which holds the per-tenant audit
  advisory lock to COMMIT. The proof list includes a MEASURED full-sweep wall time on the demo
  book, the acceptance is recorded against that number, and the split trigger is named: a real
  tenant's sweep exceeding five minutes moves sweep phases out of the single transaction (a
  PERF-0-carries-inheriting change, not this slice's).

### OQ-REP2-5 — Carry (m): discharged where the artifacts actually EXIST

*(v1 named a deploy.sh demo seed that does not exist — pass 1's second-strongest convergence,
R2/R17/R22: deploy.sh deliberately deploys ZERO tenants and refuses to manufacture principals,
and the demo tenant is not in ENT-074 on a fresh database, so v1's seeded schedule would have
belonged to a tenant the OQ-REP2-1 worker never ticks — the LQ-1 inert-control shape, in the
very record that cites it.)*

Two legs, against real artifacts:

- **The DEMO half**: `run_demo_campaign.py` gains a stage that REGISTERS the demo tenant in
  ENT-074 (ACTIVE) and creates its nightly REPRODUCTION schedule through the real
  `create_schedule` service — so every demo database has a startable, discoverable control.
- **The DEPLOY half**: `prove_reproduction.sh`'s arm moves to the full ONBOARD-1a + REPRO-2
  path: the tenant is created OVER HTTP (registered ACTIVE by provisioning), the schedule is
  created OVER HTTP by a seeded `schedule.manage` principal, and the proof asserts the worker
  — under registry discovery, with NO config naming that tenant — actually FIRES it. That
  assertion (schedule fires with no hand configuration) IS carry (m)'s discharge sentence.

Tenant ONBOARDING still does not auto-create a schedule: a schedule is a governed act with an
actor and a cadence choice.

### OQ-REP2-6 — The UI: a "Reproduction" operations screen, with its proofs bound

One screen at `/ops/reproduction` (the shadow-trap convention): schedules (list + create +
pause/resume via `writes.ts`; `schedule.manage` refusals rendered plainly; the
second-active-schedule warning), the verdict table (OQ-REP2-3 payload; DIVERGED loud;
UNREPRODUCIBLE showing the fixed literal), and the first reader of `GET /schedules/runs`
(shipped at SCH-2, unconsumed since — verified at pass 1). FE consequence named (pass 1, R24):
`/schedules` and `/reproduction`… `/reproduction` already entered `API_PREFIXES` at ALERT-1;
**`/schedules` joins it now, with the nginx alternation in lockstep** (the parity test forces
the pair once the list moves; the discipline is the lockstep edit). **UI proofs are bound in §3**
(pass 1, R21 — v1 promised "API + UI" and bound zero UI proofs).

### OQ-REP2-7 — Mint census and control disposition

NOTHING minted: no permission (the forward-gate discharge is the opposite of a mint — and the
BINDING catalog comment is amended with the census entry, pass-1 minor), no entity, no event
code, **no migration** (the third no-migration slice; the carry-(n) discharge was chosen
partly so this stays true — the alternative that stored an exception class needed a column).
Route count +3 conscious. **CTRL-018 stays Implemented, annotated STARTABLE**; Operational's
trigger: the first observed scheduled green on a real (non-proof, non-demo) tenant.

## 3. Proofs (the remit binds these; P18 throughout — every negative names its positive twin)

- **Write path**: create over HTTP → the schedule FIRES on the next real supervisor tick ↔ a
  `schedule.view`-only principal 403'd; duplicate code → clean refusal, not a 500 ↔ a fresh code
  succeeds; pause → the tick skips it ↔ resume → it fires; census: the forward-gate entry
  deletion + the catalog-comment amendment.
- **Discovery**: an onboarded (registry-ACTIVE) tenant ticked with NO config ↔ SUSPENDED stops ↔
  SYSTEM never; filter set + unknown id → REFUSES TO START (the retained FOLD-2 behavior, its
  own test) ↔ filter unset + zero tenants → idles with the documented log line, bounded-exit
  under the proof seam; registry read failure → cycle skipped with the distinct error, NOT
  treated as zero ↔ streak escalation fires; one-shot `--tenant` with an unregistered id →
  refused. Mutants: discovery reverts to config-only; the empty-intersection refusal dropped;
  read-failure treated as zero.
- **The `control_switched_off` red** (if ratified): all-paused tenant → red on the panel ↔ one
  ACTIVE schedule → not red ↔ a never-configured tenant stays informational (the ALERT-1
  amendment's own discriminating twin).
- **Verdict read, the carry-(n) discharge with its positive twin** (pass 1, R20): the planted
  binder failure FIRST proven to have produced an UNREPRODUCIBLE row whose STORED
  `first_divergence` contains a distinctive marker (DB-side — the harness delivered its input),
  THEN the marker asserted ABSENT from the HTTP response, which carries the fixed literal;
  DIVERGED rows carry field+key ↔ permission parity (holder / 403 / 401) ↔ tenant-locality with
  a live second tenant. The key-class census (OQ-REP2-3) as its own test.
- **Sixteen adapters**: per family, reproduce-green ↔ planted divergence detected ↔ the
  exclusion-truth tamper test per uncompared column; the coverage census exact-set 19+2; the
  MEASURED full-sweep wall time recorded in the slice record.
- **UI** (pass 1, R21): component tests — create/pause/resume through `writes.ts` with refusal
  rendering; the DIVERGED-loud and fixed-literal verdict rows; the runs-ledger table; the
  second-active-schedule warning.
- **Deployed**: the OQ-REP2-5 deploy leg (HTTP tenant → HTTP schedule → the worker fires it
  under discovery with no config) + deploy.sh step 8 rewritten to the bounded idle proof; both
  refusal twins live (unregistered one-shot id; `schedule.view`-only writer 403).
- Mutation battery group `repro-2` (committed, `needs_pg` where PG-tier); both tiers + full-PG +
  CI-watch-to-green, exit codes quoted (P14).

## 4. Non-goals (each with its trigger, P19)

- **CONCENTRATION / LIQUIDITY registration** — triggers: CONCENTRATION's next consume-path
  slice; LIQUIDITY's next model-identity gate.
- **Schedule DELETE** — pause is the retirement verb; trigger: a real retention requirement.
- **Four-eyes on pause** — the recorded alternative if `control_switched_off` is judged
  insufficient; trigger: the first suspicious pause in a real tenant's audit review.
- **Sweep-transaction splitting / parallelization** — trigger: a real tenant's sweep exceeding
  five minutes (inherits the PERF-0 carries by their ratified trigger).
- **Acknowledgement / re-fire (carry (j))** and **a push alerting leg** — unchanged from
  ALERT-1, their triggers standing.
- **Backfill of missed ticks** — honest gaps stay honest; trigger: a regulatory completeness
  requirement on a scheduled family.

## 5. Verifier ledger

| Pass | Shape | Outcome |
|---|---|---|
| 1 (2026-08-10) | 5 adversarial lanes + refute-by-default; 31 agents, 0 errors | **24 CONFIRMED (7 BLOCKING in 3 convergence groups), 2 REFUTED, 5 minor.** The convergences: the strict carry-(n) discharge unimplementable from stored data (R1/R10/R12 — v1's example exception class cannot even occur in an ENT-073 row); the deploy-seed mechanism nonexistent AND the seeded tenant undiscoverable (R2/R17/R22 — the LQ-1 inert-control shape inside the record that cites it); idle-and-poll inverting an EXECUTED CI gate that would then HANG (R4/R7/R16/R23). Also: the supersession target was the WRONG ratified OQ (R15 — CAD-1's, not SCH-1's); the empty-intersection fail-closed split (R6); pause-before-tamper adjudicated (R9); the sixteen-fold exclusion-truth obligation (R11); the key-class disclosure invariant (R14). The REFUTED worth recording: the split-this-slice sizing claim did not survive its refuter — L stands, with the R11 growth priced in. All folded above; each fold names its finding. |
| 2 | PENDING — attacks the folds | |
