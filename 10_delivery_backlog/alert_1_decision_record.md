# ALERT-1 decision record — the alarm about the alarm, visible and bounded

**Wave 17, slice 1** (the ratified Part 2.19 sequence). Status: **DRAFT v2 — post-pass-1,
pre-pass-2**. Branch `alert-1-planning`. Design authority once ratified: THIS record.

## 1. What this slice is, and is not

ALERT-1 is the operational-alerting slice six homeless carries name as their host (P19-mandatory).
Its subject is **the alarm channel itself** — machinery that today can be broken, degraded,
bounded, silenced, or simply STOPPED with no path by which an operator learns any of it. Nothing
here touches governed numbers, the ratified v6 retirement rule, or reproduction verdicts' CONTENT
(REPRO-2's remit).

**The six carries (census CORRECTED at pass 1, finding C13 — v1 dropped (e) and counted the
enabling machinery as a carry):** all from `repro_1_slice_record.md` §6:

| # | Carry | Disposition here |
|---|---|---|
| (e) | A legitimately-empty tenant FAILS its nightly sweep BY DESIGN; an operator surface treating a FAILED run as an incident needs a distinct disposition | PAID — the `nothing_to_reproduce` disposition, recomputed from source, non-red (OQ-ALR-1) |
| (l) | A sweep that checked NOTHING is invisible to the alarm channel | PAID — `failed_sweeps` (OQ-ALR-1) |
| (q) | The retry bound does not cover a failed alarm TRANSACTION; retries every tick indefinitely, no trace | PAID — the sibling-transaction FAILED row joins the EXISTING bound (OQ-ALR-3) |
| (r) | An already-delivered recipient is re-paged on retry ticks | PAID — the courtesy skip, WITH a durable concluded row per skip (OQ-ALR-4) |
| (s) | A recipient provisioned mid-outage can be retired at 1 of `MAX_ALARM_ATTEMPTS` attempts | ACCEPTED, made visible via `exhausted_verdicts` (OQ-ALR-4) |
| (t) | One malformed payload silences the tenant's channel, and no alarm fires about the alarm system | **First half ALREADY PAID at the Wave-16 close** — executed probe at pass 1: a planted bare-string payload for one entity left ANOTHER entity's genuine verdict queued (per-row scoping, mutants M-A1/M-A2 pin it). ALERT-1 pays the VISIBILITY half only |

The enabling machinery (not itself a carry): `AlarmChannelHealth`
(`reproduction/service.py`) — recomputed, correct, and consumed by nothing outside its module.
This slice gives it its missing fields, its route, and its screen.

## 2. The shape (one sentence)

Extend the recomputed per-tenant health object until it answers every question the six carries ask
— including the question v1 forgot, "is the sweep RUNNING AT ALL?" — give it a governed read route
and an ops-UI panel, make failed alarm transactions durable in a sibling transaction so the
EXISTING attempt bound covers them, and make retries stop re-paging the already-told while still
emitting the durable rows the retirement rule counts — with no new entity, no new permission, no
new audit code, and no change to the ratified v6 rule.

## 3. Decisions (OQ-ALR-1…7)

### OQ-ALR-1 — The health surface: fields, windows, and what "healthy" means — all enumerated

Extend `AlarmChannelHealth` (computed, never stored — the LIM-1 rule). Pass 1 broke v1's field set
four ways (absence-blindness C1; the alarm-lost night C7; window incoherence C9/C15/C21; transient
red C10) — v2 enumerates per-field semantics:

| Field | Answers | Window | In `healthy`? |
|---|---|---|---|
| `queued` | verdicts still owed delivery | UNWINDOWED — it IS `unalarmed_verdicts`, which is O(all-history) by the v6 rule's own needs; that cost is carry (k)'s, hosted elsewhere, and this record says so instead of pretending a window fixes it | NO — a nonzero queue is the channel WORKING (a divergence in flight between phases) |
| `unreadable_rows` | the poison floor | UNWINDOWED — standing poison must not age out of sight | YES (red) |
| `last_terminal_sweep_at` + `sweep_overdue` | **the absence-sensing pair (pass-1 BLOCKING C1): a dead supervisor, a never-firing schedule, or a mid-run death (which rolls back to NO row at all — the refuter's sharpening) all read as an overdue sweep.** `sweep_overdue` is true iff a REPRODUCTION schedule EXISTS for the tenant and no terminal (COMPLETED/FAILED) REPRODUCTION run has landed within its cadence plus a grace bound | overdue derives from the schedule's own cadence | YES (red) |
| `no_schedule` | the tenant has NO reproduction schedule — a distinct, honest disposition (REPRO-2's startability gap, not an incident; pointing at it is not owning it) | — | NO (informational; the UI names REPRO-2) |
| `failed_sweeps` | **ALL** FAILED REPRODUCTION runs in the window **except** the `nothing_to_reproduce` class (pass-1 C7 killed v1's "and no verdict rows" qualifier: the alarm-lost night is a FAILED run WITH verdict rows) | 7-day window | YES (red) |
| `nothing_to_reproduce` | carry (e)'s disposition: FAILED sweeps whose tenant has NO completed reproducible-family runs — **recomputed from source** (the LIM-1 rule again), not parsed from prose | 7-day window | NO (informational) |
| `lost_verdicts` | the alarm-LOST signal: sweeps whose failure reason records verdicts that could not be written (`DISPOSITION_UNRECORDED`). The durable trace is the run's `failure_reason` prose, so the marker phrase is HOISTED to a module constant used by BOTH the writer and this reader — one implementation, no drifting grep (the C4 medicine applied here too) | 7-day window | YES (red) |
| `undeliverable_attempts` | durably-recorded FAILED attempt rows — **for verdicts still queued or ceiling-retired only**, so a transient failure whose retry succeeded goes green (pass-1 C10) | 7-day window | NO (amber — retries in flight are the system working; persistent failure ends in `exhausted_verdicts`) |
| `exhausted_verdicts` | verdicts retired BY the ceiling — the bound made VISIBLE. Classification comes from the SAME implementation as the queue (pass-1 C4): `unalarmed_verdicts`' fold is refactored to expose per-verdict classification (queued / delivered / ceiling-retired) and both consumers read it. Semantics stated: a verdict whose final attempt concluded for everyone counts as DELIVERED even at the ceiling; a poisoned verdict at the ceiling counts as ceiling-retired (its history is untrustworthy) | UNWINDOWED — a silenced verdict must not age into invisibility | NO (amber — the ACCEPTED bound, visible; making it red forever would be the cry-wolf class carry (j) warns about) |

`healthy` is therefore **enumerated**: `unreadable_rows == 0 AND lost_verdicts == 0 AND
failed_sweeps == 0 AND NOT sweep_overdue`. Amber fields render distinctly in the UI; nothing else
participates. The existing `AlarmChannelHealth.healthy` docstring is updated to this definition in
the same commit that changes it.

### OQ-ALR-2 — The read route and its permission: REUSE `schedule.view`, counts only

`GET /reproduction/alarm-health`; ordinary `require_permission`; census-visible
(`EXPECTED_ROUTE_COUNT` 300 → 301, a conscious move). Payload = the OQ-ALR-1 fields — counts,
booleans, one timestamp. **No verdict ids, no reason text, no `first_divergence`** (carry (n)'s
redaction residual stays bound to REPRO-2's content reads).

**Permission: REUSE `schedule.view`.** Holder set — corrected at pass 1 (C3/C12/C16: v1 claimed
"all four business roles"; the recomputed truth, from `ROLE_TEMPLATES` source:
**`data_steward`, `risk_analyst_1l`, `risk_manager_2l`, `auditor_3l`, `platform_admin` — five
roles; `tenant_admin` and `ops` do NOT hold it.** Channel health is control-plane oversight
(the CTRL-018 chain) with no proprietary values and no person data — `auditor_3l`'s inclusion is
the point, per the governed-oversight doctrine. **`tenant_admin`'s exclusion is surfaced as part
of this OQ rather than discovered later**: recommendation — keep the five-role set (a tenant
admin administers PEOPLE, not the risk control plane; the roles that operate the control see its
health), revisitable when a real operator asks.

FE consequence, stated: `/reproduction` is a NEW API prefix — `api-prefixes.ts` and the nginx
alternation move in lockstep (the census test forces it).

### OQ-ALR-3 — C2 (repeated rollback): the failure becomes DURABLE in a sibling transaction

Pass 1 (C2/C11/C19) proved v1's mechanism unimplementable as written — `attempt_id` is a local
inside `alarm_for_verdict` and the failure surfaces at the worker's `session.commit()` where only
the exception is in scope. **The plumbing, named:**

- `attempt_id` is minted at the WORKER call boundary and passed into `alarm_for_verdict`
  (consistent with the service's own minted-at-the-call-boundary doctrine); the function's
  one-invocation-one-attempt contract is unchanged.
- On failure, the worker's except arm begins a NEW transaction on the same session after rollback
  — architecturally verified at pass 1: the audit service's advisory locks are
  transaction-scoped (released at ROLLBACK) and the `after_begin` listener re-arms the RLS GUC on
  the next transaction — and records ONE `NOTIFY.DISPATCH` row: `outcome='failure'`, the SAME
  `attempt_id`, a SENTINEL recipient value (excluded by name from OQ-ALR-4's courtesy-skip reads),
  and a bounded reason.
- The EXISTING `MAX_ALARM_ATTEMPTS` bound now covers the rollback path — no new rule; the v6
  grouping pools the sibling row by its `attempt_id` like any other.
- **Commit-ambiguity, stated (pass-1 minor):** if the COMMIT actually landed server-side but the
  poller saw an error, the attempt's success rows AND the sibling failure row coexist under one
  `attempt_id` — they pool into ONE attempt whose rows are mixed, which does not retire the
  verdict (not all-success) and does not double-count the ceiling. Benign, and now said.
- If the sibling write ALSO fails (the database itself is down), nothing durable is possible by
  definition; the supervisor's own tick failure is the outer signal. Stated residual.

### OQ-ALR-4 — C3/C4 (recipient degradation): the courtesy skip EMITS THE ROW IT SKIPS

Pass 1's strongest convergence (C6/C14/C18 — three lanes independently): v1's skip, which POSTed
nothing and recorded nothing for an already-told recipient, made an all-skipped tick emit ZERO
rows — the v6 rule (a pure function of `NOTIFY.DISPATCH` rows) could then never retire the
verdict. v5's non-termination, resurrected through the delivery loop by a slice whose remit is
noise reduction.

**The fold: a courtesy-skipped recipient still emits a durable CONCLUDED row** under the tick's
`attempt_id` — `outcome='success'`, payload detail `skipped: already delivered` — so an
all-skipped attempt is an all-success latest attempt and the verdict retires EXACTLY as it does
today, minus the wire noise. The skip consults the recipient's own prior outcome rows for the
courtesy decision only; **failure direction on ANY doubt (no rows, unreadable rows, shape it does
not recognize, the OQ-ALR-3 sentinel) is PAGE** — shape-blindness degrades to paging, never to
dropping, which is also why the pass-1 claim that the skip resurrects the payload-shape dependency
was REFUTED: a dependency whose failure mode is the status quo is a courtesy, not a load-bearing
read. The retirement rule itself never reads per-recipient state — unchanged, un-reopened.

**C4 (carry (s)) is ACCEPTED, not fixed** — the alternative is the non-terminating rule the bound
exists to prevent. Visible via `exhausted_verdicts`; recorded here.

### OQ-ALR-5 — Scope fence: the REPRODUCTION channel only

Breach-channel health (ENT-063 has its own durable per-recipient rows and semantics) is a NAMED
NON-GOAL; trigger: the first breach-channel delivery incident, or the operator-workflow slice
hosting carry (j).

### OQ-ALR-6 — The UI: an "Alerting" panel on the operations surface

`/ops/alerting` (client route; the API prefix consequence is OQ-ALR-2's). Red fields, amber
fields, and the two informational dispositions rendered with plain-language explanations —
`no_schedule` names REPRO-2 as the payer; `nothing_to_reproduce` says "empty tenant, by design".
FE reads via generated types; no writes; no acknowledgement (carry (j), §5).

### OQ-ALR-7 — Mint census: NOTHING minted

No new entity, no new permission, no new audit code (`NOTIFY.DISPATCH` reused with
`outcome='failure'` — an outcome, not a verb), no model, no migration. §5C is a PER-MINT
checklist (pass-1 correction): a slice minting nothing owes no rows, and this line records that
reading rather than inventing refused-row ceremony. The route-count pin and the FE prefix pair
move consciously. CTRL moves: NONE (CTRL-018 is REPRO-2's to move); this slice's evidence rides
existing rows. *(v1's "first slice ever to ship no migration" boast was false — struck at pass 1,
C17.)*

## 4. Proofs (the remit binds these; P18 throughout)

- Every red/amber field: a test that MAKES its condition true and sees it move, plus the
  discriminating twin (a clean tenant: all-zero, healthy, and `nothing_to_reproduce`
  distinguishable from a real failure). Named additions from pass 1:
  - **absence-sensing**: a tenant with a schedule and NO terminal run within cadence+grace →
    `sweep_overdue` ↔ a fresh terminal run → not overdue; a tenant with no schedule →
    `no_schedule`, NOT overdue, NOT red;
  - **the alarm-lost night**: a FAILED run WITH other families' verdict rows and an UNRECORDED
    verdict → `lost_verdicts` nonzero (the marker constant asserted shared by writer and reader);
  - **all-skipped termination** (the C6/C14/C18 killer): both recipients already told → the tick
    emits concluded rows, the attempt is all-success, the verdict RETIRES; mutant: skip stops
    emitting rows → a named test must redden on non-termination;
  - **sibling row joins the bound**: force a rollback on PG → the FAILED row lands with the
    boundary-minted `attempt_id` → the verdict retires at the EXISTING ceiling; mutant: drop the
    sibling write → indefinite-retry test reddens;
  - **classification single-implementation**: the queue and `exhausted_verdicts` disagree-proof —
    one fold, two consumers, asserted by construction (the refactor) and by a test that would
    catch a second implementation appearing.
- Route: census-visible; permission parity (five-role holder ↔ 403 for `tenant_admin`/stranger ↔
  401 bare); counts-only payload asserted against the response model BY FIELD NAME.
- Deployed arm (pass-1 C20 named the gaps): host = `prove_reproduction.sh`, which gains
  `$COMPOSE up -d backend` and a `schedule.view`-holding seeded principal; asserts the healthy
  all-zero read on the live stack, plus twins: the `breach.review`-only principal → 403; bare →
  401.
- Mutation battery group `alert-1`, committed, `needs_pg` on PG-tier mutants (P18).
- Both tiers + full-PG + CI-watch-to-green, exit codes quoted (P14).

## 5. Non-goals (each with its trigger, P19)

- **Acknowledgement / the nightly re-fire (carry (j))** — trigger: REPRO-2's verdict reads making
  re-fires visible, or the first operator complaint.
- **Breach-channel health** — trigger at OQ-ALR-5.
- **Phase-5 scan performance/retention (carry (k))** — a performance slice; `queued`'s
  O(all-history) cost is THAT carry's, explicitly not paid here.
- **A real paging integration** — the sink Protocol is the boundary; DEP-1's webhook stands.
- **Verdict CONTENT reads** — REPRO-2, where carry (n)'s redaction residual is bound.

## 6. Verifier ledger

| Pass | Shape | Outcome |
|---|---|---|
| 1 (2026-08-09) | 5 adversarial lanes + refute-by-default on every serious finding; 29 agents, 0 errors | **21 CONFIRMED (6 BLOCKING-class in 3 convergence groups), 3 REFUTED, 12 minor.** The three convergences: the courtesy skip's zero-row tick resurrecting v5 non-termination (3 lanes independently); the health surface blind to the sweep's ABSENCE (the LQ-1 inert-control shape applied to the health surface itself); the six-carry census wrong in v1 (carry (e) dropped). All folded above; each fold names its pass-1 finding. |
| 2 | PENDING — attacks the folds | |
