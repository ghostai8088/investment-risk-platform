# ALERT-1 decision record — the alarm about the alarm, visible and bounded

**Wave 17, slice 1** (the ratified Part 2.19 sequence). Status: **DRAFT v1 — pre-verifier**.
Branch `alert-1-planning`. Design authority once ratified: THIS record; the remit derives from it.

## 1. What this slice is, and is not

ALERT-1 is the host that six homeless carries already name (P19-mandatory): the operational
alerting slice. Its subject is **the alarm channel itself** — the machinery REPRO-1 built and the
Wave-16 close hardened, which today can be broken, degraded, bounded, or silenced with **no path
by which an operator learns any of it**. Nothing in this slice touches governed numbers, the
delivery rule (v6, ratified), or the reproduction verdicts' CONTENT (REPRO-2's remit).

The six carries, verbatim from their registers (`repro_1_slice_record.md` §6 unless noted):

| # | Carry | Source |
|---|---|---|
| C1 | (l) A sweep that checked NOTHING is invisible to the ALARM channel — fails closed in the run ledger (FAILED run + reason) but writes no verdict row, so phase 5 has nothing to alarm on | REPRO-1 |
| C2 | (q) The alarm retry bound does not cover a failed alarm TRANSACTION — a rolled-back attempt records nothing, so that path retries every tick indefinitely; "the honest fix is an operational signal on repeated rollback" | REPRO-1 |
| C3 | (r) An already-delivered recipient is re-paged on retry ticks — delivery is per-verdict while the queue is per-attempt; bounded, measured at one extra page in the depart-and-recover case | REPRO-1 |
| C4 | (s) A recipient provisioned mid-outage can be retired at 1 of `MAX_ALARM_ATTEMPTS` attempts — the backstop counts attempts on the verdict, not the recipient | REPRO-1 |
| C5 | (t) A single permanently-malformed `NOTIFY.DISPATCH` payload makes phase 5 inert for the tenant, and **no alarm fires about the alarm system** | REPRO-1 |
| C6 | `AlarmChannelHealth` exists (`reproduction/service.py`, the Wave-16 close fold) and is consumed by NOTHING outside its own module and tests — a health surface that reaches no operator | Wave-16 close |

**Ground-truth caveat the verifier pass must check:** C5's first half looks ALREADY PAID — the
Wave-16 close fold re-scoped poison to the ROW (`unreadable_rows` + per-row `continue`; the
poisoned verdict stays queued, bounded by the ceiling, and the tenant channel keeps flowing;
mutants M-A1/M-A2 pin it). If confirmed, C5's residue is the VISIBILITY half only, and this record
scopes to that. A carry paid by a later fold and re-paid by a new slice would be waste; a carry
BELIEVED paid on a stale reading would be the LQ-1 class. Verify against HEAD, by execution.

## 2. The shape (one sentence)

Extend the RECOMPUTED per-tenant health object to answer every question the six carries ask, give
it a governed read route and a small ops-UI panel, make failed alarm TRANSACTIONS join the
existing attempt bound by recording their failure in a SIBLING transaction, and add a
delivery-side courtesy skip so retries stop re-paging the already-told — with **no new entity, no
new permission, no new audit code, and no change to the ratified v6 retirement rule**.

## 3. Decisions (OQ-ALR-1…7)

### OQ-ALR-1 — The health surface: recomputed fields, one per carry-question

Extend `AlarmChannelHealth` (computed, never stored — the LIM-1 rule: a health surface RECOMPUTES
from source, never infers from evidence rows):

| Field | Answers | Carry |
|---|---|---|
| `queued` | verdicts still owed delivery (exists today) | — |
| `unreadable_rows` | the poison floor (exists today) | C5 |
| `failed_sweeps` | REPRODUCTION `calculation_run` rows with status FAILED and **no verdict rows** in the window — a checked-nothing night, distinguishable from a clean one | C1 |
| `exhausted_verdicts` | verdicts retired BY THE CEILING (`MAX_ALARM_ATTEMPTS` reached without a concluded delivery) — what the bound silenced, counted instead of inferred | bounded-noise ceiling |
| `undeliverable_attempts` | durably-recorded FAILED attempt rows in the window (incl. OQ-ALR-3's sibling-transaction rows) — repeated rollback surfaces HERE | C2 |
| `healthy` | false iff any degradation field is nonzero | all |

*Window*: a bounded lookback (recommend 7 days, a constant) — the health read must not be
O(all-history) (REPRO-1 carry (k) is a *performance* carry hosted elsewhere; this slice must not
worsen it, and a bounded window also keeps `failed_sweeps` from permanently reddening on ancient
history).

**Recommendation:** as above. **Alternative considered:** a stored health/alert table (rejected:
an IA store for a recomputable fact invites the inference LIM-1 forbids, and invites carry-(j)
style acknowledgement state this slice deliberately does not own).

### OQ-ALR-2 — The read route and its permission: REUSE `schedule.view`, counts only

`GET /reproduction/alarm-health` (backend router; census-visible; ordinary `require_permission`).
Payload = the health fields — **COUNTS AND BOOLEANS ONLY, no verdict ids, no reason text, no
`first_divergence`**. Carry (n) binds a redaction residual to "before any read surface is added
over ENT-073"; this route reads AGGREGATES of ENT-073 and the audit chain, and the counts-only
payload is the discharge of that boundary — the (n) residual itself stays with REPRO-2's verdict
read surface, where content appears.

**Permission: REUSE `schedule.view`** — the control-plane oversight read (holders: all four
business roles + `auditor_3l` + `platform_admin`). Rationale: channel health is control-plane
evidence about whether a detective control is working — precisely the class `auditor_3l` oversees
(the CTRL-018 chain); the payload carries no proprietary values and no person data. **No new code
is minted** (P11: reuse when semantics fit; a `alerting.view` mint would demand its own holder
ratification for an identical set).

### OQ-ALR-3 — C2 (repeated rollback): the failure becomes DURABLE in a sibling transaction

Today a rolled-back alarm transaction records nothing, so the verdict retries every tick with no
bound and no trace. **Fix: when `alarm_for_verdict`'s transaction fails, open a NEW short-lived
transaction and record the FAILED attempt row** (`NOTIFY.DISPATCH`, `outcome='failure'`, the same
`attempt_id` the failed call stamped, a bounded `_redact`-style reason). Consequences, which are
the point:

- the EXISTING `MAX_ALARM_ATTEMPTS` bound now covers the rollback path — no new rule, no new
  counter, the v6 retirement machinery unchanged;
- the failure is visible on the health surface (`undeliverable_attempts`) and in the chain;
- if the sibling write ALSO fails (the database itself is down), nothing durable can be recorded
  by definition — that residual is stated, logged, and accepted; the supervisor's own tick failure
  is the outer signal for a down database.

**Alternative considered:** an in-process rollback counter surfaced via worker logs/metrics
(rejected: the worker has no operator-facing surface, restarts zero the counter, and "an
operational signal" that only a log reader sees is the exact class this slice exists to end).

### OQ-ALR-4 — C3/C4 (recipient degradation): a delivery-side courtesy skip; the RULE untouched

The v6 retirement rule is ratified and its six-version history is the strongest negative-evidence
file in the project — **nothing here re-opens it**. C3's fix lives one layer down, in the delivery
loop: before POSTing to a recipient, consult that recipient's OWN durable outcome rows for THIS
verdict; a recipient whose latest readable outcome is success is skipped ("retry the wire, not the
audience"). Failure direction: any doubt (no rows, unreadable rows) → PAGE — fail toward alarming,
the detective-control direction. The skip consults per-recipient state for a COURTESY decision
only; it can never freeze retirement (the rule never reads it), so the v5 hostage mechanism cannot
return.

**C4 is ACCEPTED, not fixed** — the alternative is the non-terminating rule the bound exists to
prevent (the carry says so itself). The acceptance is recorded here, and the ceiling's effect is
visible via `exhausted_verdicts` rather than silent.

### OQ-ALR-5 — Scope fence: the REPRODUCTION channel only

The breach-notification channel (NOTIF-1, ENT-063) shares the sink but has its own durable
per-recipient rows and its own semantics. Extending health over it is a NAMED NON-GOAL with a
trigger: the first breach-channel delivery incident, or the operator-workflow slice that hosts
carry (j). One channel, done honestly, sized M.

### OQ-ALR-6 — The UI: an "Alerting" card on the operations surface

A compact panel (route `/ops/alerting` or a card on the existing ops landing — implementation's
choice within OPS-1 conventions): the health fields with plain-language explanations, red state
iff `healthy` is false. FE reads via the generated types (FE-2 contract). No writes, no
acknowledgement (carry (j) is NOT this slice — see §5).

### OQ-ALR-7 — Mint census: NOTHING minted, and the absence is the discipline

No new entity (recomputed health), no new permission (`schedule.view` reused), no new audit code
(`NOTIFY.DISPATCH` reused with `outcome='failure'` — an outcome, not a verb), no model, no
migration (**the first slice since the migration chain began that ships none** — the verifier pass
should confirm no schema need hides in the design). §5C checklist rows therefore all read
"explicitly refused with reason: nothing minted". CTRL moves: NONE — CTRL-018's status is
REPRO-2's to move; this slice's controls ride existing rows' evidence columns.

## 4. Proofs (the remit will bind these; P18 throughout)

- Every health field: a test that MAKES the condition true and sees the count move, plus its
  discriminating twin (a clean tenant reads all-zero/healthy). `failed_sweeps`: a FAILED
  REPRODUCTION run with no verdicts → nonzero ↔ a completed sweep → zero.
- The sibling-transaction attempt row: force a rollback (the PG tier can poison the alarm
  transaction), see the FAILED row land, see the verdict retire at the EXISTING ceiling — the
  no-new-rule claim proven by the old rule doing the work. Mutant: drop the sibling write → the
  indefinite-retry behavior returns → a test must redden.
- The courtesy skip: depart-and-recover scenario — the already-told recipient is NOT re-POSTed,
  the un-reached one IS; mutant: skip-on-doubt inverted → page-on-doubt test reddens.
- The route: census-visible, permission parity (holder ↔ 403 stranger ↔ 401 bare), counts-only
  payload asserted against the response model by name (no verdict id, no reason text fields).
- Deployed arm: extend the reproduction/onboarding proof with a health read on the live stack.
- Mutation battery group `alert-1` (P18: committed, `needs_pg` where PG-tier).
- Both tiers + full-PG + CI-to-green, exit codes quoted (P14).

## 5. Non-goals (each with its trigger, P19)

- **Acknowledgement / the nightly re-fire (carry (j))** — an operator-workflow slice; trigger:
  REPRO-2's verdict read surface making re-fires visible, or the first operator complaint.
- **Breach-channel health** — trigger above (OQ-ALR-5).
- **Retention/performance of the phase-5 scans (carry (k))** — a performance slice; the bounded
  health window here must not be silently treated as paying it.
- **A real paging integration (email/PagerDuty)** — the sink Protocol is the boundary; DEP-1's
  webhook stands.
- **Verdict CONTENT reads** — REPRO-2, where carry (n)'s redaction residual is bound.

## 6. Verifier ledger

Pass 1 (adversarial, five lanes): PENDING.
