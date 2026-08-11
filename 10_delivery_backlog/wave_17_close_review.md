# Wave-17 close review

**Produced 2026-08-11 by a FRESH-CONTEXT multi-lens review over merged main at `3bccce0`** — six
independent lenses, each lens's findings handed to an adversarial refuter required to EXECUTE a
probe rather than re-read the same code, then a synthesis pass. 13 agents, 35 raw findings, zero
agent errors.

**On the engine, stated first because it bounds everything below.** Wave 16's close was reviewed on
a DIFFERENT engine (Fable), and that is what caught a BLOCKING the mutation battery had certified
green. Fable's usage limit was reached on 2026-08-10 and resets ~2026-08-14, so **this review is
fresh-context Opus — the same engine that built the wave.** RPT-3's gate ratified that substitute
for one slice with a binding condition, and the same condition is applied here: this is recorded as
a same-engine review's findings, not as a different-engine clearance. It found real defects. That
is evidence it is worth running, and it is not evidence it replaces a different engine.

---

## GATE OUTCOME — user decisions, 2026-08-11

All five decisions were ratified **as recommended**.

| # | Decision | Outcome |
|---|---|---|
| **D1** | 13 of 18 carries name a host that does not exist | **Label now, sequence Wave 18 later.** All thirteen become explicitly labelled deferral decisions at this close (P19 clause B); the wave sequence is set at the next planning gate. |
| **D2** | "Exactly ONE platform operator" is uncounted | **Enforce it.** A census plus a rotation path. Shipped as a fail-closed refusal at the seed + `retire_platform_operator` — see the recorded deviation in §4. |
| **D3** | Legacy tenants cannot self-administer | **Backfill migration** (`0069`). Smallest change; no new permission, no new route. |
| **D4** | Provenance columns excluded from CTRL-018 | **Settle by execution, then fix the false reasons.** Executed: the exclusion was a real hole. Three columns now COMPARED. |
| **D5** | The mutation battery is run by no gate | **The cheap anchor check in `make check`.** Full battery stays a per-slice manual run. |

---

## 1. WHAT WAVE 17 DELIVERED

Wave 17 turned the platform from something that had to be started by hand into something an
operator can start and run over HTTP.

**ONBOARD-1a (PR #191) — the ignition.** Before this slice the platform had 251 API paths and no way
to create a tenant. It now has `POST /tenants`, the ENT-074 registry (platform-global by a recorded
design refusal, migration `0067`), a PLATFORM permission catalog whose single verb `tenant.create`
is held only by `platform_operator`, a cross-tenant onboarding transaction that reads the SYSTEM
role templates before re-arming the tenant context, and a fence refusing the operator everywhere
except provisioning. **[ran it]** A recursive dependency-tree walk over the real app found exactly
one SYSTEM-reachable path (`/tenants`) and exactly two unauthenticated routes (`/health`,
`/version`) out of 305.

**ONBOARD-1b (PR #192) — the tenant administers itself.** Four tenant-admin codes, ENT-075
`entitlement_request` with four-eyes (migration `0068`), CTRL-025 and CTRL-037 → Implemented, and
`/admin/users`. **[ran it]** Self-approval is refused at three tiers — unit, endpoint (422) and the
deployed proof — and the actor dataclass canonicalizes, so case variance does not defeat it.

**ALERT-1 (PR #195) — alarm-channel health.** Twelve recomputed fields behind
`GET /reproduction/alarm-health` and the `/ops/alerting` panel, plus a SKIPPED notification outcome.

**REPRO-2 (PRs #197, #198) — the reproduction control becomes real.** Registry-driven tenant
discovery; a schedule write path; then sixteen family adapters taking coverage from **3 registered +
18 unregistered to 19 + 2**. **[ran it]** The census reconciles exactly: 22 `RUN_TYPE_*` constants,
minus REPRODUCTION itself, is 21 = 19 + 2, and the census test asserts set EQUALITY rather than a
subset relation.

**RPT-3 (PRs #199, #200).** `ROLLING_RISK` joined `PERF_RUN_TYPES`; the generate-report form landed
at `/ops/reports`.

---

## 2. WHAT IS TRUE, AND WHAT WAS NOT

### Blocking

**1. Three governed registers described a control the platform no longer has. [ran it]**
The live registry reports `REPRODUCIBLE 19 / UNREPRODUCIBLE 2`. The control matrix, the
requirements backbone and the traceability matrix all still read "exactly three families", and two
of them asserted **"there is no schedule WRITE API"** — a route that ships in the generated OpenAPI
contract (`/schedules` with both `get` and `post`) and that the demo campaign calls through the
real service. `git diff --name-only 80e6b9f..4908b65` filtered to `09_`/`02_` is **empty**: REPRO-2
part 2 shipped sixteen adapters and touched no register at all. Three lenses converged on this
independently. This is the artifact a compliance assessor opens first, and it reported 3/21
coverage for a control that checks 19.

**2. The alarm-health surface read HEALTHY through a sweep failing every night. [ran it]**
`record_failed_dispatch` stamps `fired_at=now, outcome=FAILED, calculation_run_id=NULL` for a
dispatch that RAISED before a run existed. `alarm_channel_health` mentioned `ScheduledRun` three
times and all three were `max(fired_at)` with no outcome predicate — so each night's failure
refreshed the very clock that exists to notice the sweep stopping. `failed_sweeps` counts FAILED
`calculation_run` rows, and on this path there is no run to count. Reproduced at HEAD before the
fix: thirty consecutive FAILED ledger rows gave `healthy=True, sweep_overdue=False,
failed_sweeps=0`, rendering the green HEALTHY chip over "The sweep is running and alarms are getting
through." That is the exact state the `AlarmChannelHealth` docstring names as this surface's reason
to exist, recurring one wave later on the surface built to expose it.

### High

**3. The closure-discipline gate enforced nothing for thirteen days, and exited 0. [ran it]**
`_DONE_MARK` was the literal `✅ **DONE**`; every roadmap row from Wave 14 on writes
`✅ **DONE + CLOSED <date> …**`. The leading-title branch stopped running and `_TICK_SLICE` matched
the prefix, adding the WORD `DONE` to the done-set. Eleven shipped slices went invisible to a
CI-BLOCKING gate rebuilt four times for exactly this purpose. Every guard that should have caught it
was a subset or a count: the unit tests assert `{"API-1","FE-3"} <= done` over a **synthetic**
fixture, and the non-vacuity floor compared 55 parsed against a floor of 38 — a set can lose every
member that matters while staying large.

**4. The committed mutation battery was RED at HEAD, and no gate ran it. [ran it]**
84 mutants, **4 unmatched anchors**, all group `w16-close`, all in `reproduction/service.py`:
ALERT-1 moved bytes in a module it did not own the mutants for. An unmatched anchor is a SURVIVOR by
the harness's own rule, so a full run exited 1 for a day while four Wave-16 alarm controls had no
executable proof — one of them the infinite-paging bug a different review engine caught after the
battery certified the tree green. `grep -rn mutation_battery Makefile .github/workflows/` returned
nothing.

### Medium — the ones that became work

- **`current_state.md`, the file CLAUDE.md orders every session to read second, was not touched
  once in Wave 17** and pointed at "NEXT = the ONBOARD-1a implementation plan" — a slice that merged
  as PR #191 with nine merges after it. P1 ledger (4) went unswept across five consecutive closeouts.
- **The canonical model's next-free-id pointer read ENT-074** while ENT-074 and ENT-075 both had
  realized rows in that same table. It lives inside a narrative row rather than as a declaration.
- **Platform operators were mint-only** — nothing counted them, and no HTTP path could revoke one.
- **Every pre-0067 tenant, including the demo tenant, was 403 on the whole self-administration
  feature**, and the repair code that exists is unreachable.
- **CTRL-018's evidence citation fails its own P16 test** — 51 production files changed since the
  cited SHA.
- **A ratified REPRO-2 disposition claimed it annotated the ALERT-1 register; it did not**, and the
  two records now contradict each other about whether an open carry has fired.
- **13 of 18 carries name a host that does not exist** — there is no Wave 18 anywhere in the roadmap.

### What checked out clean

**Every hard invariant holds, under execution, converged on by three lenses.**
`audit/service.py` has no commit after its two P0.5-era scaffold commits — byte-untouched across
Wave 17. `HYBRID_TABLES` is still exactly **seven**; migration `0067` adds no RLS at all, and ENT-074
is platform-global by a recorded design refusal, not an eighth hybrid table by accident. The
SYSTEM-router fence is total and its census fails on a new route in **both** directions. SOD-04
four-eyes fires at three tiers, person-level and canonicalized. REPRO-2's sixteen adapters each have
a reproduce-green + planted-divergence pair, and the plant is written to the STORED row only — an
adapter that re-read its own answer would report MATCH and fail the test. The sweep's failure
dispositions are structurally correct: the recompute is discarded on a savepoint with no `finally`
and no `is_active` guard.

---

## 3. WHAT NOBODY VERIFIED

This section is load-bearing and is deliberately as specific as the findings.

- **17 of 27 findings were never adversarially probed.** The refuter executed probes for the
  provisioning lens, the carries-and-rules lens and three of five reproduction findings. It ran no
  probe for any operator-surfaces finding, any records-vs-code finding, or five of six ledger
  findings. I independently re-ran three of the biggest — the family census and the three stale
  registers, the battery anchor state, and both halves of the alarm-health mechanism — and those
  are marked **[ran it]**. The rest carry their finder's evidence and nothing more.
- **The entire PostgreSQL tier is unexecuted by this review.** Every lens was barred from touching
  `irp_pg_local` — thirteen agents sharing one database is the P2 hazard. So the RLS boundary
  checks, the `pg_policies` hybrid-set assertion, ENT-075's append-only trigger and the
  18/18-on-the-real-demo-book sweep are read-only inspections here. The gate run below is where the
  PG tier is exercised.
- **Nothing was run against a deployed stack.** `prove_onboarding.sh`, `prove_reproduction.sh` and
  `deploy.sh` were read, never executed. `IGNITION_EXIT=0` and `PROVE_REPRO_EXIT=0` are the records'
  claims, not this review's.
- **CI's conclusion for `3bccce0` was taken from the remit, not measured by a lens.** (It was
  separately verified by the builder before the review began.)
- **Specific gaps worth naming:** the alarm-health failure was reproduced by constructing the
  resulting ledger state directly, not by making `run_reproduction_sweep` raise inside
  `poll_tenant_schedules`; `normalize()` reduces non-Decimal values with `str()`, which makes JSON
  key ORDER significant for `exposure_aggregate.fx_legs` and no re-serialisation case was
  constructed to test for a FALSE DIVERGED; and `_consume_adapter`'s docstring claims a property
  "load-bearing for all eleven" standard binders, of which two were spot-checked and nine were not.

---

## 4. THE CLOSE FOLD

Six commits on `wave-17-close`. Every defect below was made to FIRE before it was fixed (P9), and
every fix is proven load-bearing by a mutant rather than by inspection (P18).

| Fold | What | Proof |
|---|---|---|
| 1 | **BLOCKING 2** — the overdue clock takes an `outcome != FAILED` predicate; `failed_dispatches` counts ticks that fired and did not land, through the wire to the panel | `P9_FIRE_EXIT=1` before the fix; W-A1/W-A2 killed |
| 2 | **HIGH 1 + HIGH 2 + D5** — the done-mark becomes a prefix regex; two records stamped CLOSED; `_MUST_PARSE_AS_DONE` named witnesses replace the count floor; four `w16-close` anchors re-anchored; `make check` gains `mutant-anchors` | gate went RED on the parser fix; W-B1/W-B2 killed; w16-close 13/13 |
| 3 | **BLOCKING 1 + ledgers** — three registers corrected in lockstep; `test_reproduction_register_truth.py`; `current_state.md` swept; the ENT pointer corrected | W-C1/W-C2 killed |
| 4 | **D3** — migration `0069` backfills `tenant_admin` into every registered non-SYSTEM tenant that lacks it | W-D1/W-D2 killed; negative half asserts zero admin codes first |
| 5 | **D2** — the seed fails closed on a second operator; `retire_platform_operator` makes rotation supported | W-E1/W-E2 killed |
| 6 | **D4** — three false exclusions deleted; provenance now COMPARED | W-F1 killed; tamper probe DIVERGED |

### Three things the fold got wrong first, recorded because each PASSED while being unable to fire

1. **My first negative control for the anchor check proved nothing.** It imported a mutated copy of
   `check_docs.py` from `/tmp`, where the module resolved its own repo root and found no roadmap, so
   it "failed" for the wrong reason. Redone in place against the real tree.
2. **The register-truth guard could not fire, twice.** Version 1 exempted a retired claim if a
   retirement marker appeared anywhere on the LINE — and the CTRL-018 row is a single ~9,000
   character line, so unrelated prose satisfied it. Version 2 used a 260-character window, and
   mutant W-C1 showed the AMENDMENT NOTE following the corrected text sat inside the window and
   exempted the very claim it described as retired. Version 3 requires the claim to be QUOTED.
   Writing a guard that cannot fire, twice, inside the fold whose subject is controls that cannot
   fire, is worth the space it takes to record.
3. **Mutant W-B2 survived its first run.** The gate's new witness check had no test behind it, so
   deleting it broke nothing. The twin that exercises it through `_closure_stamp_errors` — the
   function CI actually calls — was added because the battery demanded it, not because the fold
   noticed.

### Recorded deviation

**D2 shipped as a deploy-tier function, not a route.** The ratified wording said "give the
provisioning router a deactivate verb". A route needs its own minted permission — a governed R-07
act carrying a migration, a census entry and an SoD row, which is a slice rather than a close fold —
and it would widen the SYSTEM-fenced surface, a hard invariant, to reach a row a deploy-tier tool
already reaches. The stated reason for choosing enforcement was that "the only fix is SQL" had to
end; it has. The deviation is also recorded in the function's own docstring.

---

## 5. THE HONEST ASSESSMENT

Wave 17 delivered what it claimed. The ignition is real, the reproduction control genuinely went
from three families to nineteen, and every hard invariant survived probing.

What did not keep up is the layer that tells an outside reader what the platform does. Two of the
four most serious findings are documents that were accurate when written and false when read, and
the other two are gates that reported green while enforcing nothing. The pattern across all four is
the same one this project keeps rediscovering: **a control is not implemented until its refusal has
fired, and a claim is not true because it was true once.**

The instrument that found the most this close was execution — probing a guard before trusting it,
running the battery, reproducing a health surface's output against a constructed ledger state. The
instrument that found the least was reading. That ratio is the argument for keeping the
different-engine review when Fable returns, because a same-engine fresh context found these and
still cannot be shown to find what a different engine would.

---

## 6. THE P19 REGISTER SWEEP — thirteen carries, labelled as decisions (D1, ratified)

P19 says a carry must name a **sequenced slice** or a **mechanical trigger**, else it is a DECISION
owed to the user at deferral time. Clause B assigns the backstop sweep to the wave close, and this
is it.

**The structural finding first, because it is not a lapse of care.** The roadmap runs Part 2 through
Part 2.19 (Wave 17) and then Part 3, which is explicitly *"coarse; themes from the RTM map, NOT
sequenced yet"*. `grep -niE 'wave 18|wave-18'` returns no matches. So P19 clause (a) — "a slice that
exists in the roadmap sequence" — was **unsatisfiable for every forward-looking carry the wave
wrote**. Thirteen carries naming "a slice that wants it", "a performance slice",
"CONCENTRATION's next consume-path slice" were not careless; they were the only thing clause (a)
allowed.

Per D1, all thirteen are **labelled DEFERRAL DECISIONS as of 2026-08-11** — visible, owned, and
awaiting a host — and Wave 18 is sequenced at the next planning gate, which is where the ones that
should have a slice will get one.

| # | Carry | Origin | Status at this close |
|---|---|---|---|
| 1 | TS→7 | Wave-16 close | **Trigger-bound, compliant** — pay when BOTH `typescript-eslint` and `openapi-typescript` declare TS 7 support. Monitor, do not force. |
| 2 | Real-browser E2E | RPT-3 (c)/(h) | **DEFERRAL DECISION** — no host. Every UI proof today is a component test. |
| 3 | Generate idempotency | RPT-3 (d) | **DEFERRAL DECISION** — answered with VISIBILITY at RPT-3, not idempotency; the underlying decision stands. |
| 4 | Upstream VaR scope propagation | RPT-3 (f) | **DEFERRAL DECISION** — SURFACED to operators by a test, not paid. |
| 5 | SHARPE's `PERF_RUN_TYPES` entry | RPT-3 | **Trigger-bound, compliant** — the first SHARPE-consuming surface. |
| 6 | CONCENTRATION reproduction | REPRO-2 | **DEFERRAL DECISION** — structural (its binder re-pins current-head classifications); "next consume-path slice" does not exist. |
| 7 | LIQUIDITY reproduction | REPRO-2 | **DEFERRAL DECISION** — structural (a wall clock in its compute); "next model-identity gate" does not exist. |
| 8 | Reject/withdraw verb | ONBOARD-1b | **DEFERRAL DECISION** — already labelled as a decision in its own record; re-confirmed here. |
| 9 | Retention policy for alarm rows | ALERT-1 (k) | **DEFERRAL DECISION** — "a real retention requirement" is an external trigger, not a mechanical one. |
| 10 | Alarm-channel performance work | ALERT-1 | **DEFERRAL DECISION** — "a performance slice" does not exist. PERF-0's four carries are separately BOUND to a real trigger and stay compliant. |
| 11 | `exposure_aggregate.fx_legs` key-order sensitivity | this close, §3 | **NEW, DEFERRAL DECISION** — `normalize()` reduces non-Decimal values with `str()`; no re-serialisation case has been constructed to test for a FALSE DIVERGED. |
| 12 | `_consume_adapter`'s nine unverified binders | this close, §3 | **NEW, DEFERRAL DECISION** — a docstring claims a property "load-bearing for all eleven"; two were spot-checked. |
| 13 | The deployed-proof scripts run in no gate | this close | **DEFERRAL DECISION** — `prove_onboarding.sh` / `prove_reproduction.sh` are manual. The battery's own version of this failure is what HIGH 2 was. |

**What this list is for.** It is not a to-do list — it is the answer to "what did this wave decide
not to do, and does anyone own it?" Ten of the thirteen currently have no owner, and saying so is
the entire point of P19. The Wave-18 planning gate is where they get hosts or get closed.
