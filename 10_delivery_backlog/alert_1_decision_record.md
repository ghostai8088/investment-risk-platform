# ALERT-1 decision record — the alarm about the alarm, visible and bounded

**Status:** v3 — post-pass-2, READY FOR RATIFICATION (not yet ratified)

**Wave 17, slice 1** (the ratified Part 2.19 sequence). Branch `alert-1-planning`. Design
authority once ratified: THIS record.

## 1. What this slice is, and is not

ALERT-1 is the operational-alerting slice six homeless carries name as their host (P19-mandatory).
Its subject is **the alarm channel itself** — machinery that today can be broken, degraded,
bounded, silenced, or simply STOPPED with no path by which an operator learns any of it. Nothing
here touches governed numbers, the ratified v6 retirement rule, or reproduction verdicts' CONTENT
(REPRO-2's remit).

**The six carries** (census corrected at pass 1, C13 — v1 dropped (e)); all from
`repro_1_slice_record.md` §6:

| # | Carry | Disposition here |
|---|---|---|
| (e) | A legitimately-empty tenant FAILS its nightly sweep BY DESIGN; an operator surface treating that as an incident needs a distinct disposition | PAID — `nothing_to_reproduce`, classified per-RUN from the run's own durable trace (OQ-ALR-1) |
| (l) | A sweep that checked NOTHING is invisible to the alarm channel | PAID — `failed_sweeps` (OQ-ALR-1) |
| (q) | The retry bound does not cover a failed alarm TRANSACTION; retries every tick indefinitely, no trace | PAID — the sibling-transaction FAILED row joins the EXISTING bound (OQ-ALR-3) |
| (r) | An already-delivered recipient is re-paged on retry ticks | PAID — the courtesy skip, emitting a durable `SKIPPED` row per skip (OQ-ALR-4) |
| (s) | A recipient provisioned mid-outage can be retired at 1 of `MAX_ALARM_ATTEMPTS` attempts | ACCEPTED, made visible via `exhausted_verdicts` (OQ-ALR-4) |
| (t) | One malformed payload silences the tenant's channel, and no alarm fires about the alarm system | **First half ALREADY PAID at the Wave-16 close** — executed probe at pass 1 (C5): a planted bare-string payload for one entity left ANOTHER entity's genuine verdict queued (per-row scoping; mutants M-A1/M-A2). ALERT-1 pays the VISIBILITY half; the residual regress is stated in §5 |

The roadmap's five phrases, mapped (pass-2 P2-13 demanded the map be explicit): *alarm-channel
health surface reaching an operator* = OQ-ALR-1/2/6; *recipient-degradation* = OQ-ALR-4;
*the repeated-rollback signal* = OQ-ALR-3 + `undeliverable_attempts` + the persistent-total-failure
red clause; *the bounded-noise ceiling made visible* = `exhausted_verdicts`; *the poison-row noise
floor* = `unreadable_rows` with its terminal disposition.

The enabling machinery (not itself a carry): `AlarmChannelHealth` — recomputed, correct, consumed
by nothing. This slice gives it its missing fields, its route, and its screen.

## 2. The shape (one sentence)

Extend the recomputed per-tenant health object until it answers every question the six carries ask
— including "is the sweep RUNNING AT ALL?" — give it a governed read route and an ops panel, make
failed alarm transactions durable so the EXISTING attempt bound covers them, and make retries stop
re-paging the already-told while still emitting the durable rows the retirement rule counts — with
no new entity, no new permission, no new audit event code, no migration, and no change to the
ratified v6 rule. **One vocabulary amendment IS made and named: a fourth NOTIFY outcome,
`SKIPPED`** (OQ-ALR-4/7).

## 3. Decisions (OQ-ALR-1…7)

### OQ-ALR-1 — The health surface: fields, windows, and what "healthy" means — all enumerated

Extend `AlarmChannelHealth` (computed, never stored — the LIM-1 rule). Per-field semantics, each
sharpened by a named pass finding:

| Field | Semantics | Window | In `healthy`? |
|---|---|---|---|
| `queued` | verdicts still owed delivery | UNWINDOWED (it IS `unalarmed_verdicts`; the O(all-history) cost is carry (k)'s, said plainly) | NO — a nonzero queue is the channel working |
| `unreadable_rows` | the poison floor — **red only while a STILL-QUEUED verdict's history contains poison** (P2-14: an IA audit row can never be repaired, so unconditional-unwindowed red is permanent red — the cry-wolf class; a poison row whose verdict has ceiling-retired stops reddening and stays visible via `exhausted_verdicts`; there is NO remediation path and this record says so) | classification-scoped | YES (red, per the stated scope) |
| `last_terminal_sweep_at` + `sweep_overdue` | absence-sensing (pass-1 C1; a mid-run death rolls back to NO row — the refuter's sharpening). **Evaluated per ACTIVE REPRODUCTION schedule** (P2-4/P2-10): overdue iff ANY active reproduction schedule has no terminal run within its own cadence + grace, where due-ness comes from **the scheduler's own next-fire computation** (the single-implementation medicine — no reimplemented cadence math), grace = one full cadence period, and a never-fired schedule's clock starts at its first due tick after creation. A PAUSED/disabled schedule (if the model has the state) is a distinct informational disposition — not overdue, not `no_schedule` | schedule-derived | YES (red) |
| `no_schedule` | NO active reproduction schedule exists — REPRO-2's startability gap named, not owned | — | NO (informational) |
| `failed_sweeps` | **ALL** FAILED REPRODUCTION runs in the window **except** those classified `nothing_to_reproduce` (pass-1 C7: the alarm-lost night is a FAILED run WITH verdict rows) | 7 days | YES (red) |
| `nothing_to_reproduce` | carry (e). **Classified per-RUN from the run's own durable trace** (P2-5/P2-12 killed the tenant-state recompute — it misread in both directions): the sweep's "checked NOTHING" sentence is HOISTED to a module constant shared by writer and reader; a FAILED run whose reason is exactly the pure nothing-checked class counts here; every other FAILED run is `failed_sweeps` | 7 days | NO (informational) |
| `lost_verdicts` | the alarm-LOST signal, **bound to the `lost_alarms` writer clause specifically** (P2-6 — not `DISPOSITION_UNRECORDED` broadly), via a distinctive prefixed sentinel token hoisted to a shared constant; **unit: SWEEPS with lost alarms** (an unwritten row cannot be counted from prose) | 7 days | YES (red) |
| `undeliverable_attempts` | durably-recorded FAILED attempt rows for verdicts still queued or ceiling-retired (a self-healed transient goes green — pass-1 C10); expected aged shape stated: an old failure whose verdict has retired leaves this field | 7 days | NO (amber) |
| `exhausted_verdicts` | the bound made VISIBLE. Classification from the SAME fold as the queue (pass-1 C4), with the derivation STATED (P2-3, executed): **ceiling-retired iff attempts ≥ MAX AND (poisoned OR latest attempt not all-success); delivered iff latest attempt all-success AND not poisoned** — the retirement SET is provably unchanged (both branches retire); only the label differs from the fold's branch order. The refactor also absorbs `alarm_channel_health`'s second, independent poison-detection loop (pass-2 minor): ONE implementation, all consumers | UNWINDOWED | NO (amber) |

**`healthy`, enumerated** (pass-1 C8, named here as its fold): `unreadable_rows == 0 AND
lost_verdicts == 0 AND failed_sweeps == 0 AND NOT sweep_overdue AND NOT dead_channel`, where
**`dead_channel`** (P2-13 — the totally-dead channel must not stay amber): true iff
`exhausted_verdicts` GREW in-window while ZERO successful deliveries landed in-window — the
persistent-total-failure clause that gives the repeated-rollback class a red of its own. Amber
fields render distinctly; nothing else participates. The existing `healthy` docstring is updated
in the same commit.

### OQ-ALR-2 — The read route and its permission: REUSE `schedule.view`

`GET /reproduction/alarm-health`; ordinary `require_permission`; census-visible
(`EXPECTED_ROUTE_COUNT` 300 → 301, conscious). Payload = the OQ-ALR-1 fields — counts, booleans,
and the `last_terminal_sweep_at` timestamp; **no verdict ids, no reason text, no
`first_divergence`** (carry (n)'s residual stays bound to REPRO-2).

**Permission: REUSE `schedule.view`.** Holder set recomputed from `ROLE_TEMPLATES` source
(pass-1 C3/C12/C16 corrected v1's miscount): **`data_steward`, `risk_analyst_1l`,
`risk_manager_2l`, `auditor_3l`, `platform_admin` — five roles; `tenant_admin` and `ops` do NOT
hold it.** `auditor_3l`'s inclusion is the point (control-plane oversight, no proprietary values,
no person data). **`tenant_admin`'s exclusion is a decision made here, not an accident**:
recommendation — keep the five-role set (a tenant admin administers people, not the risk control
plane); revisit on a real operator ask.

FE consequence: `/reproduction` is a NEW API prefix — `api-prefixes.ts` and the nginx alternation
move together (the prefix-parity test pins them to each other once the list moves; the discipline
is the lockstep edit — pass-2 minor, attribution corrected).

### OQ-ALR-3 — Carry (q): the failure becomes DURABLE in a sibling transaction

Plumbing named (pass-1 C2/C11/C19): `attempt_id` is minted at the WORKER call boundary and passed
into `alarm_for_verdict` (its one-invocation-one-attempt contract unchanged; the doctrine wording
per the code's own comment). On failure, the worker's except arm begins a NEW transaction on the
same session after rollback (verified: advisory locks are transaction-scoped, released at
ROLLBACK; the `after_begin` listener re-arms the RLS GUC) and records ONE `NOTIFY.DISPATCH` row:
`outcome='failure'`, the SAME boundary-minted `attempt_id`, a **NEW named sentinel recipient
value** (pass-2 minor: NOT `NO_RECIPIENT_SENTINEL`, whose SUPPRESSED semantics this row would
falsify) excluded by name from OQ-ALR-4's courtesy reads, and a bounded reason. The EXISTING
`MAX_ALARM_ATTEMPTS` bound then covers the rollback path — no new rule. Commit-ambiguity stated:
success rows and a sibling failure row under one `attempt_id` pool into ONE mixed attempt — not
retired, not double-counted. If the sibling write also fails (database down), nothing durable is
possible; the supervisor's tick failure is the outer signal. Stated residual.

### OQ-ALR-4 — Carries (r)/(s): the courtesy skip EMITS THE ROW IT SKIPS — fully pinned

Pass 1's strongest convergence (C6/C14/C18: a skip that records nothing makes an all-skipped tick
emit zero rows). Pass 2 then broke the fold's own specification twice (P2-1/P2-9: the row's
outcome value undetermined, with SENT a false record, SUPPRESSED a contradicted semantic, and an
unmapped new value landing as audit `failure`; P2-2: the courtesy read's scope unstated). **The
mechanism, fully pinned:**

- **A fourth NOTIFY outcome is MINTED: `SKIPPED`** — "delivery deliberately not attempted: this
  recipient's latest state for THIS verdict is already-delivered". It joins `NOTIFY_OUTCOMES` and
  the ratified `_emit_dispatch` total mapping **in the same commit**, mapping to audit
  `'success'`; the mapping stays total and fail-closed on any FIFTH value. The `NOTIFY.DISPATCH`
  taxonomy row gains the outcome (a vocabulary amendment, not a new event code — the R-07 note
  rides this ratification). **A skip row's payload outcome is NEVER `SENT`** — the wave-12
  honesty doctrine (SENT = the sink accepted a real call) is preserved for auditors counting
  deliveries.
- **The courtesy read is scoped**: THIS verdict's rows (`entity_id = check.id`) for THIS
  recipient; "already delivered" = any prior row whose payload outcome is `SENT` (or `SKIPPED`).
  Failure direction on ANY doubt — no rows, unreadable rows, unrecognized shape, the OQ-ALR-3
  sentinel — is PAGE.
- An all-skipped attempt is therefore an all-success latest attempt and the verdict retires
  exactly as today. (Pass-2's refuter sharpened the stake: even the broken variant terminates at
  the unconditional ceiling — the harm was five false `failure` rows, a burned retry budget, and
  a delivered verdict misclassified as exhausted on the very surface this slice builds. The pin
  removes all three.)

**Carry (s) is ACCEPTED, not fixed** — the alternative is the non-terminating rule the bound
exists to prevent. Visible via `exhausted_verdicts`.

### OQ-ALR-5 — Scope fence: the REPRODUCTION channel only

Breach-channel health is a NAMED NON-GOAL; trigger: the first breach-channel delivery incident,
or the operator-workflow slice hosting carry (j).

### OQ-ALR-6 — The UI: an "Alerting" panel on the operations surface

`/ops/alerting`. Red, amber, and informational fields rendered with plain-language explanations
**and one operator-action line per red field** (pass-2 minor: at 02:00, `lost_verdicts` red says
"read the FAILED sweep's reason in the run ledger", `sweep_overdue` says "check the worker
process/schedule") — runbook strings in the panel, not a runbook document. `no_schedule` names
REPRO-2; `nothing_to_reproduce` says "empty tenant, by design". FE via generated types; no
writes; no acknowledgement (carry (j), §5).

### OQ-ALR-7 — Mint census: no entity, no permission, no event code, no migration — ONE vocabulary amendment, named

No new entity, no new permission, no new audit **event code**, no model, no migration. §5C is a
per-MINT checklist; a slice minting no permission owes no rows (pass-1 correction). **What IS
amended, ratified here by name (pass-2 P2-1): the NOTIFY outcome vocabulary gains `SKIPPED`, and
the ratified `_emit_dispatch` total mapping gains its third success-mapping member — each with its
own mutant.** The route-count pin (300 → 301) and the FE prefix pair move consciously. CTRL
moves: NONE (CTRL-018 is REPRO-2's). *(v1's false "first slice with no migration" boast was
struck at pass 1, C17.)*

## 4. Proofs (the remit binds these; P18 throughout)

- Every red/amber field: make its condition true, see it move; the discriminating twin (clean
  tenant: all-zero, healthy). Named additions:
  - **absence-sensing**: schedule with no terminal run past cadence+grace → `sweep_overdue` ↔
    fresh terminal run → not overdue; no schedule → `no_schedule`, not red; fresh never-fired
    schedule inside its first period → NOT overdue (P2-4); two schedules, one silent → overdue
    (P2-10, per-schedule grain).
  - **the alarm-lost night**: FAILED run WITH other verdict rows + a lost alarm →
    `lost_verdicts` nonzero; the sentinel token asserted shared writer/reader.
  - **carry (e)'s twin pair** (P2-5/P2-12): an empty tenant's FAILED sweep →
    `nothing_to_reproduce`, healthy; an infrastructure-failed sweep on the SAME empty tenant →
    `failed_sweeps`, red.
  - **all-skipped termination**: both recipients already told → SKIPPED rows land → attempt
    all-success → verdict RETIRES; mutants: skip stops emitting rows → redden; `SKIPPED` dropped
    from the success mapping → redden (the P2-1 probe as a permanent test).
  - **the scoped courtesy read** (P2-2): two queued verdicts, recipient told about verdict 1
    only → tick PAGES for verdict 2; mutant: drop the `entity_id` predicate → redden.
  - **sibling row joins the bound**: force a PG rollback → FAILED row with the boundary-minted
    `attempt_id` → verdict retires at the EXISTING ceiling; mutant: drop the sibling write →
    indefinite-retry test reddens.
  - **classification** (P2-3): delivered-at-ceiling labels DELIVERED; poisoned-at-ceiling labels
    ceiling-retired; retirement set unchanged (asserted equal before/after the refactor);
    `dead_channel` fires on grown-exhausted + zero-success (P2-13) ↔ one successful delivery →
    not dead.
- Route: census-visible; permission parity (five-role holder ↔ 403 `tenant_admin`/stranger ↔ 401
  bare); the payload's field set asserted BY NAME against the response model (counts, booleans,
  one timestamp — nothing else).
- Deployed arm (pass-1 C20): host = `prove_reproduction.sh` + `$COMPOSE up -d backend` + a
  seeded `schedule.view`-holding principal (`risk_manager_2l`); asserts the healthy read on the
  live stack ↔ the `breach.review`-only principal 403 ↔ bare 401.
- Mutation battery group `alert-1`, committed, `needs_pg` where PG-tier (P18). Both tiers +
  full-PG + CI-watch-to-green, exit codes quoted (P14).

## 5. Non-goals and stated residuals (each with its trigger, P19)

- **Acknowledgement / the nightly re-fire (carry (j))** — trigger: REPRO-2's verdict reads
  making re-fires visible, or the first operator complaint.
- **Breach-channel health** — trigger at OQ-ALR-5.
- **Phase-5 scan performance/retention (carry (k))** — a performance slice; `queued`'s
  O(all-history) cost is that carry's, not paid here.
- **A real paging integration** — trigger (P2-11): the first production tenant with a real
  on-call rotation, or DEP-1's webhook failing an actual incident.
- **Verdict CONTENT reads** — REPRO-2, where carry (n)'s residual is bound.
- **The regress, terminated honestly (P2-15):** the health surface is PULL-only — a red field
  pages nobody, and carry (t)'s sentence "no alarm fires about the alarm system" remains
  literally true one level up. The regress stops at the operator's eyes: a broken health ROUTE
  is visibly broken (an error, never a false green), which is the property that makes pull-only
  acceptable. Trigger for a push leg: carry (j)'s slice, or the first missed-red incident.

## 6. Verifier ledger

| Pass | Shape | Outcome |
|---|---|---|
| 1 (2026-08-09) | 5 adversarial lanes + refute-by-default; 29 agents, 0 errors | **21 CONFIRMED (6 BLOCKING-class, 3 convergence groups: the zero-row skip tick — C6/C14/C18; absence-blindness — C1; the census wrong — C13), 3 REFUTED, 12 minor.** All folded in v2; pass-2 P2-7 then found C5 and C8 folded but UNCITED — C5 = the carries-table (t) row; C8 = the `healthy` enumeration — now named at their folds. |
| 2 (2026-08-09) | 3 lanes attacking the FOLDS + a completeness critic + refute-by-default; 21 agents, 0 errors | **15 CONFIRMED (5 BLOCKING-class), 2 REFUTED, 8 minor.** The pattern the passes exist for: pass-2's strongest findings were specification gaps in pass-1's own fixes — the skip row's outcome value undetermined with every existing value defective (P2-1); the empty-tenant recompute keyed on read-time state instead of the run's trace (P2-5/P2-12); the absence-sensing pair blind to paused/fresh/multiple schedules (P2-4/P2-10); the dead channel that never turns red (P2-13); permanent-red poison (P2-14). All folded in v3, each named at its fold. |
