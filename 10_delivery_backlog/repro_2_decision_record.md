# REPRO-2 decision record — the reproduction control becomes STARTABLE

**Status:** **RATIFIED 2026-08-10** (AskUserQuestion, four decision points, ALL as recommended: v3 OQ-REP2-1…7 ratified; the OQ-CAD-1-2=A/OQ-CAD-1-3=A supersession AUTHORIZED (registry-driven discovery, strict parse, the full disposition table, ~12-carrier blast radius incl. the deploy.sh step-8 rewrite); BOTH named ratified-disposition amendments AUTHORIZED (ALERT-1's `control_switched_off` red; OPS-H1's demo-tick default-on); pause = compensating VISIBILITY, not four-eyes, with its revisit trigger. Design authority: THIS record. NEXT: the REPRO-2 implementation.)

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
own slice with its own maker-checker question"); and — added at pass 2, P2-17, because a carry
whose trigger this slice itself constitutes cannot ride as "unchanged" — ALERT-1's carries
verbatim: carry (j) ("acknowledgement / the nightly re-fire — trigger: REPRO-2's verdict reads
making re-fires visible, or the first operator complaint") and the pull-only residual ("trigger
for a push leg: carry (j)'s slice, or the first missed-red incident").

**Carry (j), adjudicated at this gate** (pass 2, P2-17): OQ-REP2-3's payload carries verdict
rows and NO alarm-attempt data — a nightly re-fire is visible only in the dispatch chain, which
this surface deliberately does not read — so the ALERT-1 trigger has NOT literally fired. The
trigger is REWORDED to the surface that would actually show re-fires: an alarm-attempt read
surface, or the first operator complaint about repeat pages. Recorded here, annotated at the
ALERT-1 register.

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
| `IRP_TENANT_IDS` ABSENT **or present-but-blank** (whitespace-only — the shape `.env.example` ships and `deploy.sh` copies verbatim, stated so the executed CI gate's exact input has ONE unambiguous arm — pass 2, P2-1) | **UNSET: unrestricted registry discovery.** With zero ACTIVE tenants: idle-and-re-poll, loudly logged each cycle — the truthful state of a fresh platform. NOT silent: the idle line is asserted by the deployed proof |
| `IRP_TENANT_IDS` SET and **any non-blank entry fails canonicalization** | **REFUSE TO START** (pass 2, P2-1: the parser's ratified skip-and-continue — CAD-1 OQ-3=A — is SUPERSEDED here BY NAME, because under it a malformed filter silently evaporated into tick-everything: the looks-configured-but-isn't state, inverted into over-ticking. Strict parse; a typo is a refusal, not a widening) |
| `IRP_TENANT_IDS` SET (all entries valid) and any listed id is unknown to the registry — a fortiori an empty intersection | **REFUSE TO START (the CAD-1 FOLD-2 behavior, retained)** — a definite misconfiguration (pass 1, R6) |
| The registry READ fails (exception, missing table) | **Never treated as zero tenants.** A transient failure skips the cycle with a distinct logged error and ticks nothing; a **NEW scalar consecutive-registry-failure counter** (reusing the existing `_FAILURE_STREAK_ALERT` threshold constant — pass 2, P2-2: the existing streak machinery is per-tenant and a failed registry read yields no tenant to key it on) escalates on a streak. At startup, an unreadable registry REFUSES to start (pass 1, R8) |
| A tenant onboarded mid-operation | Ticked from the next cycle (the list is re-read per cycle) |
| A tenant SUSPENDED / not ACTIVE / SYSTEM | Never ticked |
| The one-shot `--tenant` entrypoint | Retained as an operator override, validated against the registry AND against status: an unknown id, a SUSPENDED id, or SYSTEM is refused (pass 2, P2-10 — "never ticked" binds the override too; both status twins in §3) |

`IRP_TENANT_IDS` becomes an optional RESTRICTION (intersect; it can pin a subset, it can no
longer invent a tenant).

**The blast radius, enumerated in-slice and INDEPENDENTLY RE-DERIVED at pass 2** (P2-6/P2-12/
P2-13 found v2's list citing a runbook that does not exist — the nonexistent-artifact shape
recurring inside the very fold that fixed it — while missing the only RUNTIME carriers). The
carriers, verbatim-verified against HEAD:

- `supervisor.py` — docstring, refusal text, and `main()` gaining the env-read cycle bound
  (`IRP_MAX_CYCLES`, parsed fail-closed like `_interval_from_env`, default unbounded — pass 2,
  P2-5: the existing `max_cycles` seam is reachable only as a Python kwarg; the container CMD
  path needs the knob or the rewritten CI gate cannot bound the run);
- `tenants.py` — `parse_tenant_ids` (the strict-parse supersession above) and its docstring's
  "an EMPTY result is the caller's to treat as fail-closed" sentence;
- **the tenant-create API's `WORKER_FOLLOWUP` response string and its pin test** (pass 2, P2-12:
  the one carrier a real operator actually reads — rewritten to the registry truth: a
  registered-ACTIVE tenant is ticked automatically; a schedule still needs a governed actor);
- **`deploy.sh` step 8** — the EXECUTED CI gate that today REQUIRES exit 2 on zero tenants and
  would HANG under idle-and-poll (pass 1, R4/R7/R16/R23): rewritten to the bounded idle proof
  (exit 0 + the documented idle line under `IRP_MAX_CYCLES`), its closing "proven to fail
  closed" banner and `.env.example`'s `IRP_TENANT_IDS` comment rewritten with it — the
  supervisor change and the step-8 rewrite land in the SAME commit (pass-2 minor: either alone
  is a red CI);
- `prove_reproduction.sh`'s premise comment; `apps/worker/README.md`; the worker tests that
  assert refuse-to-start semantics (NAMED in the implementation so they are rewritten as the
  new dispositions' twins, never retained vacuous — pass 2, P2-13);
- the **CTRL-031 row** in the control matrix (its description states config-driven dispatch —
  a dated REPRO-2 annotation, pass 2, P2-13); `current_state.md`; the operating-instructions
  demo-tick rule (see OQ-REP2-5);
- superseded-by annotations ON the CAD-1 record: the OQ-2 row AND the FOLD-2 / OQ-3=A lines and
  Status header (pass 2, P2-14: half of what is superseded — empty-list fail-closed and
  skip-and-continue parsing — is ratified under FOLD-2/OQ-3=A, not OQ-2), each stating which
  half is superseded and which retained.

### OQ-REP2-2 — The schedule WRITE path: three routes, the holder set enumerated, and the maker-checker question SPLIT

`POST /schedules`, `POST /schedules/{id}/pause`, `POST /schedules/{id}/resume` — ordinary
`require_permission("schedule.manage")`, discharging the SCH-1 forward-gate (the census entry is
DELETED; the catalog comment at `entitlement/bootstrap.py` — the BINDING record, per the
liquidity.run precedent — is amended in the same commit). Validation
is the existing `create_schedule` fail-closed rule set, PLUS the duplicate-code refusal — whose
HONEST mechanism is stated (pass 2, P2-4: a route-level pre-check alone cannot deliver its own
guarantee under READ COMMITTED; two concurrent creates both pass it and the loser dies at
flush): **the route catches the unique-violation IntegrityError and maps it to the same clean
409-class refusal** (the in-repo precedent), the pre-check retained as the ordinary-path
courtesy with the richer message; the concurrent-duplicate twin is a PG proof (pass 1, R3). **There is deliberately NO
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
  and is put to the gate BY NAME as part of this OQ — **with its carriers enumerated exactly as
  the OQ-REP2-1 supersession's are** (pass 2, P2-3/P2-19): the shipped ALERT-1 test
  `test_a_PAUSED_schedule_is_its_own_disposition` asserts `healthy is True` at the exact state
  this turns red — it is REWRITTEN as the amendment's positive twin, never silently deleted; the
  `healthy` docstring's enumerated RED list gains the field; the `AlarmHealthOut` response model
  and the endpoint test's BY-NAME field-set pin gain it (a DECISION there, by that pin's own
  design); the `/ops/alerting` panel renders it with its operator action. No new status
  vocabulary is needed (`SCHEDULE_STATUSES` is exactly ACTIVE/PAUSED — verified at pass 2). Pause itself stays one-person (the
  SCHEDULE.UPDATE audit row + the panel showing who/when are the trail); four-eyes-on-pause is
  the recorded alternative if the residual is unacceptable. Revisit trigger: the first
  suspicious pause in a real tenant's audit review.

### OQ-REP2-3 — The verdict READ surface: carry (n) discharged BY PURE EXCLUSION

`GET /reproduction/checks` (tenant-local; filters family/verdict/since; ordered
`system_from` DESC with a stated page-size cap — an unbounded list over an append-only table is
carry (k)'s class and this route does not join it; pass-2 minor), gated on `schedule.view` (the
ALERT-1 audience). Payload per row: `id`, `family_key`, `verdict`,
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
CON-1/REF-1 exclusions). Proven MECHANICALLY — and the class list itself is a NEW declaration this slice MINTS (pass 2,
P2-15: the CON-1/REF-1 exclusions live as permission-gated ROUTES, not as any reusable
column-class enumeration): `IDENTITY_EXCLUDED_COLUMNS`, homed beside the reproduction registry,
derived from the two named exclusion classes (issuer identity; person identity) with each
member's route-gate provenance cited. The census walks every registered family's key and
compared fields against it, so the sixteen new declarations (OQ-REP2-4) cannot smuggle one in —
and the list's own stale-entry twin keeps it honest.

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
  `create_schedule` service. The stage mirrors `register_proof_tenant`'s idempotency exactly
  (tolerant of an existing or 0067-backfilled row and of a dirty re-run — pass 2, P2-20), and
  the isolation rule is stated: PG tests exercising registry discovery PIN the restriction
  filter (or use fresh tenants), because a demo-seeded database now contains a discoverable
  ACTIVE tenant. **This AMENDS an OPS-H1-ratified disposition BY NAME and is put to the gate as
  such** (pass 2, P2-7/P2-16): "enrolling DEMO_TENANT_ID in `IRP_TENANT_IDS` is an OPERATOR
  CHOICE" becomes, under registry discovery, default-ON ticking for demo-seeded databases —
  opt-in enrollment becomes opt-out restriction; re-seeding remains the pristine-walk recovery;
  the operating-instructions demo-tick rule and the OPS-H1 register both carry dated
  annotations.
- **The DEPLOY half**: `prove_reproduction.sh` gains a SECOND tenant — created OVER HTTP via
  ONBOARD-1a provisioning (registered ACTIVE), its `schedule.manage` principal provisioned via
  the ONBOARD-1b flows, its schedule created OVER HTTP — and the proof asserts the worker,
  under registry discovery with NO config naming that tenant, actually FIRES it. **The pinned
  `PROOF_TENANT` and every existing arm keyed to it are UNCHANGED** (pass 2, P2-8: v2's
  "the tenant is created over HTTP" read as parameterizing the whole seed/plant chain, which
  the shared-constant premise forbids; the second-tenant shape leaves that machinery alone).
  The fires-with-no-hand-configuration assertion IS carry (m)'s discharge sentence.

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
Route count +4 conscious (pass 2, P2-9). **CTRL-018 stays Implemented, annotated STARTABLE —
and the matrix row's standing sentence "the status move belongs to REPRO-2" is QUOTED and
DISPOSED in the same amendment** (pass 2, P2-18): the annotation IS the promised move's
adjudication — the write-path reason for not-Operational is retired by this slice; the
no-real-deployment reason stands; Operational's trigger restated: the first observed scheduled
green on a real (non-proof, non-demo) tenant.

## 3. Proofs (the remit binds these; P18 throughout — every negative names its positive twin)

- **Write path**: create over HTTP → the schedule FIRES on the next real supervisor tick ↔ a
  `schedule.view`-only principal 403'd; duplicate code → clean refusal, not a 500 ↔ a fresh code
  succeeds; pause → the tick skips it ↔ resume → it fires; census: the forward-gate entry
  deletion + the catalog-comment amendment.
- **Discovery**: an onboarded (registry-ACTIVE) tenant ticked with NO config ↔ SUSPENDED stops ↔
  SYSTEM never; **filter SET to a subset → exactly that subset ticked, an unpinned ACTIVE tenant
  NOT ticked** (pass 2, P2-11 — the intersection's affirmative semantics, restored after the v2
  rewrite dropped it) ↔ filter set + unknown id → REFUSES TO START ↔ filter set + a MALFORMED
  entry → REFUSES TO START (the strict-parse row's own test) ↔ filter unset/blank + zero tenants
  → idles with the documented log line, bounded-exit under `IRP_MAX_CYCLES`; registry read
  failure → cycle skipped with the distinct error, NOT treated as zero ↔ the scalar
  registry-failure streak escalates; one-shot `--tenant`: unregistered id refused ↔ SUSPENDED id
  refused ↔ SYSTEM refused (pass 2, P2-10). Mutants: discovery reverts to config-only; the
  empty-intersection refusal dropped; the malformed-entry refusal dropped (skip-and-continue
  resurrected); read-failure treated as zero; the filter ignored.
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
| 2 (2026-08-10) | 4 lanes attacking the FOLDS + a completeness critic + refute-by-default; 25 agents, 0 errors | **20 CONFIRMED (4 BLOCKING), 1 REFUTED, 2 minor.** The fold-attack pattern held a third time — the strongest finds were defects IN the folds: the disposition table unimplementable over the real parser (P2-1 — malformed filter entries silently evaporate into tick-everything); the blast radius citing a NONEXISTENT runbook while missing the only runtime carriers (P2-6/P2-12 — the nonexistent-artifact shape recurring inside the fold that fixed it); TWO more ratified dispositions colliding unnamed (ALERT-1's paused test asserts healthy at the exact state the fold turns red, P2-3/P2-19; OPS-H1's demo-tick operator-choice inverting under discovery, P2-7/P2-16); the CAD-1 annotation on the wrong row for half the supersession (P2-14); a route-count regression the v2 fold itself introduced (P2-9); carry (j) mis-dispositioned when this slice IS its trigger (P2-17); CTRL-018's row promising a move v2 never disposed (P2-18). All folded above, each named at its fold. |
