# Wave 11 Close Review — "Operationalize" (the mandatory Part-4 rule-2 re-baseline)

| | |
|---|---|
| Status | **RATIFIED 2026-07-24** — OQ-W11C-1/2/3 approved (all as recommended) |
| Wave | 11 (fork A "OPERATIONALIZE", from the Wave-10 close OQ-W10C-4) — SCH-1 → LIM-1 → MG-2 → MG-3 |
| Method | Four cross-cutting close auditors (parallel, read-only, refute-by-default, every claim verified against code/migrations/tests/git/CI) on top of each slice's own pre-ratification verifier + 4-finder review; Opus-only, proportionate. |
| Counts | **23/38/109 UNCHANGED** across the wave — no slice minted a governed number (all control-plane primitives, correct). |

## 1. Slice verification — ALL FOUR SHIPPED-AS-RATIFIED (zero shipped-code defects — the 7th consecutive clean close on the code axis)

- **SCH-1** (PR #108 `96965cf`, migration `0049`) — the first scheduler. VERIFIED: EV `schedule`/IA `scheduled_run`; OQ-1=B app 100% non-BYPASSRLS (zero ops grant; standing regression test); INV-SCH-1 self-enforced at both write boundaries; no-backfill/coalesce-to-`current_tick`. Record CLOSED on main.
- **LIM-1** (PR #111 `218afc9`, migration `0050`) — governed LIMIT + BREACH detection. VERIFIED: all four Fable demands discharged in code (discovery via `calculation_run`; eval a tick phase; `limit_health` recomputes from source; precision `(34,12)`); `breach_direction` names the breach condition directly; 2L-maker SoD. Record CLOSED on main.
- **MG-2** (PR #113 `aa6503f`, migration `0051`) — the breach remediation lifecycle. VERIFIED: DEP-WFL state machine; monotonic `seq` under `FOR UPDATE`; auto-escalation the 3rd tick phase (`deadlines.py`) with once-per-epoch `uq_breach_escalation`; the first person-level SoD (reviewer/closer ∉ prior-1L-responder SET); the folded HIGH (review refuses with no prior 1L response) present with a test. Record CLOSED on main.
- **MG-3** (PR #115 `96679e2`, NO migration, head `0051`) — the LIMIT.APPROVE maker-checker gate. VERIFIED: `create_limit`→DRAFT; `approve_limit` approver ∉ `{created_by, updated_by}` under a `FOR UPDATE` lock; OQ-5=A change-gate (demote on a governing change to ANY non-DRAFT limit + refuse status/governing combos); `evaluate_limit` fail-closed; code-only seeding. **Adversarial re-probe (Auditor B) found NO surviving bypass** — suspend→edit→resume, no-op-status, DRAFT-self-approve, cosmetic-edit-reset, and raw paths are all blocked; a distinct second `risk_manager_2l` (∉ makers) is structurally required to reactivate a loosened limit. **Record CLOSED via the `mg-3-closeout` PR (this close's companion) — merge it so main reads CLOSED.**

## 2. Deferral / carry register — 1 PAID, 11 OPEN-and-legitimate, 0 TIPPED

PAID: `create_limit` P3-5 cross-tenant FK guard (verified). OPEN-and-legitimate (no trigger fired): the `create_schedule` FK guard (**OQ-W11C-2=A: pay in the Wave-12 API slice**, endpoint + guard together); the `*.manage`/`breach.*`/`limit.approve` API forward-gate (no endpoints exist yet); `select_overdue_breaches` N+1 (now a standing per-tick cost — bound in Wave 12); MG-3's `actor_id` canonicalization (MED-3, **pay at the Wave-12 API auth boundary — the SSO-1 lesson**); SCH-1's schema family-agnostic deferrals (trigger = the first second-family slice); notifications/egress; `limit_utilization` (ENT-032); `reviewer ≠ closer`; manual-2L-ESCALATE + per-limit SLA; calendar cadence + subtree scope; the OQ-W10C standing riders. **Nothing is TIPPED.**

## 3. Cross-slice integration — COHERENT / SOUND

The per-tenant operational tick runs three ordered, isolated phases in one transaction: schedules (SCH-1) → breach-eval (LIM-1) → deadline-escalation (MG-2). Ordering is load-bearing (a schedule-fired run is breach-checked same tick) and correct; a failure in any phase cannot unwind siblings. The full `create→approve→evaluate→breach→assign→respond→review→close`(+escalate) lifecycle is coherent: a DRAFT/demoted/suspended limit correctly drops out of evaluation (both `select_active_limits` and the `evaluate_limit` fail-closed backstop filter strictly ACTIVE); `_GOVERNING_FIELDS` is disjoint from LIM-1's frozen identity set; person-level SoD is consistent across MG-2 (∉ responders) and MG-3 (∉ makers); the `limit.approve`+`limit.manage` co-grant on `risk_manager_2l` is intentional and trips no conformance test. **Emergent anti-laundering property confirmed:** an in-flight breach on a *since-demoted/suspended* limit keeps escalating (`select_overdue_breaches` filters on breach state, not parent-limit status) — so suspend→wait cannot launder a missed 1L deadline. This was untested; **OQ-W11C-3 added the regression test** (`test_a_breach_on_a_since_demoted_limit_still_escalates`).

## 4. Outward benchmark + destination (rule 6b)

**Premise delivered at the mechanism layer, with one honest residual:** Wave 11 built the operational *engine block* — scheduler, limits, breach lifecycle, person-level maker-checker — but left off **the ignition, the dashboard, and the alarm**. Nothing deployed turns the tick (`apps/worker/.../main.py` is still a scaffold placeholder; zero infra cadence wiring); there is **no API/UI** for schedule/limit/breach/approve (22 routers, none governance-operational); and **no notification path** exists. Enforcement is detective (record + escalate), not preventive — appropriate for v1.

Against cited standards: **SoD/maker-checker is AHEAD of typical** (person-level, DB-linearizable, vacuous-hole closed — stronger than the "two named roles" most vendors ship); **lineage/reproducibility AT/AHEAD**; the SR 11-7 ongoing-monitoring *framework* now exists. **BEHIND the frontier:** BCBS 239 timeliness/aggregation and the SR 11-7 *alert* leg — a control that detects a breach but tells no one, through no interface, is not yet "operational" to an examiner. **The single biggest distance-to-frontier: the Wave-11 controls have no consumption surface.**

## 5. Re-baseline — WAVE 12 RATIFIED: "OPERATIONS, REACHABLE" (OQ-W11C-1=A)

Make the Wave-11 engine reachable, self-driving, and demonstrable **before adding new math** (the §2.1 math destination shipped at Wave 10; more numbers no human can act on widen the gap Wave 11 exposed). Sequenced:

1. **Limit/Breach/Approve API** — the governed read+write surface over the Wave-11 controls; **pays MG-3's MED-3 `actor_id` canonicalization at the auth boundary** (the SSO-1 lesson) and the `create_schedule` FK guard (OQ-W11C-2).
2. **Breach notification / alerting** — the pre-specified in-tick, per-tenant, IA-evidenced egress leg (Fable demand #3; never a cross-tenant sweep). Turns "detect" into "monitor" for SR 11-7 / BCBS 239.
3. **Cadence wiring** — infra actually invokes the per-tenant tick (retire the `worker/main.py` placeholder) — the literal ignition.
4. **Operations UI** — the breach/limits dashboard (the RTM-P8 opener; a Tier-3 FE information-architecture sign-off), the honest demo of the whole wave.

**Named now for later:** the standing "real-data after the build" note has strong pull — with the math destination and (pending Wave 12) the operational surface built, running on real data becomes the natural **Wave-13** candidate. Credit/liquidity/counterparty families and the PPF-3 v2 leverage seams remain later/real-data-gated.

## 6. Process observations (OQ-W11C-3 ratified)

- **Closure-stamp class: STOPPED and mechanically prevented** (OQ-W10C-5 broadened + unit-tested the CI teeth). No seventh recurrence within a slice; MG-3's record CLOSED rides its closeout PR (the established two-PR flow).
- **Pre-ratification verifier earned its keep every slice** (folded blocking holes before ratification on all four) — keep it mandatory.
- **New standing review angles (added to `claude_operating_instructions.md`):** (a) **vacuous / bypassable controls** — both MG-2's and MG-3's sole HIGH were this class (a control that passes on an empty precondition set, or is reachable via an alternate lifecycle path / co-submitted field); (b) **≥3-finder convergence = CONFIRMED-blocking** (MG-3 and PPF-3 both surfaced their HIGH this way).
- **New closeout step:** sweep the control matrix for any CTRL a slice moved *Planned→Operational* (this close fixed **CTRL-021** maker≠checker SoD and **CTRL-031** breach 1L/2L separation, both stale at "Planned" though MG-2/MG-3 shipped them).

## 7. Ratified outcomes

- **OQ-W11C-1 = A** — Wave 12 = "Operations, Reachable" (API → notification → cadence → UI); defer new risk families / real-data / PPF-3 v2.
- **OQ-W11C-2 = A** — pay the `create_schedule` P3-5 FK guard in the Wave-12 API slice (endpoint + guard together), not now.
- **OQ-W11C-3 = A** — adopt the process/hygiene batch: the two review angles + the closeout control-matrix sweep + the CTRL-021/031 fixes + the cross-slice anti-laundering regression test (all in this close).

Wave 11 delivered the operational engine convincingly and cleanly. Its engine is built; Wave 12 gives it ignition, a dashboard, and an alarm.
