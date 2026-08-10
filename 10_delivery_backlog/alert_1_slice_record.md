# ALERT-1 slice record — the alarm about the alarm

**Status:** BUILT + REVIEW-FOLDED (different engine, 2026-08-10); awaiting PR/CI/merge

**Wave 17, slice 1.** Branch `alert-1-impl`. Design authority: `alert_1_decision_record.md` v3 +
the ratification stamp (2026-08-09, four decision points, all as recommended).

## 1. What shipped

- **The health surface, twelve recomputed fields** (`AlarmChannelHealth`, never stored — the LIM-1
  rule). RED: `unreadable_rows` (scoped to live verdicts), `lost_verdicts`, `failed_sweeps`,
  `sweep_overdue`, `dead_channel`. AMBER: `undeliverable_attempts`, `exhausted_verdicts`.
  INFORMATIONAL: `queued`, `no_schedule`, `paused_schedules`, `nothing_to_reproduce`,
  `last_terminal_sweep_at`.
- **ONE classification fold** (`_classify_alarm_states`) consumed by BOTH the delivery queue and
  the health surface. The retirement rule had six versions, five wrong; a second implementation
  living in a health read was the drift hazard the ratification named, so there is not one.
- **`GET /reproduction/alarm-health`** on reused `schedule.view` (five-role holder set;
  `tenant_admin` excluded by decision), counts-and-booleans-only payload, route census 300 → 301.
- **`/ops/alerting`** — the panel, with a plain-language meaning AND an operator action per red
  field.
- **Carry (q) PAID**: `attempt_id` now minted at the WORKER boundary and passed in, so a
  rolled-back alarm transaction records ONE `NOTIFY.DISPATCH` failure row in a sibling transaction
  under the same attempt id — the EXISTING `MAX_ALARM_ATTEMPTS` bound covers a path that
  previously recorded nothing and retried every tick forever.
- **Carry (r) PAID**: the courtesy skip. A recipient already told about THIS verdict is not
  re-POSTed, and the skip emits a durable CONCLUDING row (`SKIPPED`).
- **The `SKIPPED` NOTIFY outcome minted** (the slice's one ratified vocabulary amendment), added
  to `NOTIFY_CONCLUDING_OUTCOMES` — which `_emit_dispatch`'s total mapping now reads instead of
  re-enumerating, so vocabulary and consequence cannot drift and a FIFTH value still fails closed.
- Ledgers: the `NOTIFY.DISPATCH` taxonomy row amended (the mint record for `SKIPPED` + the second
  sentinel); CTRL-018 annotated with its new observability evidence and explicitly NOT moved.

## 2. Gates, with captured exit codes (P14)

- Unit: `test_alarm_health.py` 25 passed; reproduction + worker suites 110 passed.
- Endpoint + censuses: 11 passed.
- Frontend: `alerting.test.tsx` 7 passed; prefix-parity green.
- Mutation battery, group `alert-1`: **15/15 KILLED**, `MUTATION_EXIT=0`.
- Deployed: `prove_reproduction.sh` including the new arm 5.
- `make check-all`, full-PG, CI-to-green: recorded in the fold commit.

## 3. Defects found during the build, and by what

### By this slice's own tests, before any review

1. **`queued` counted only verdicts that already had dispatch rows.** The refactor moved the count
   onto the classification, which only knows verdicts that have been *attempted* — so a divergence
   recorded minutes ago, the most ordinary state in the system, read as an empty queue. Caught by
   `test_a_queue_in_flight_is_NOT_a_degradation`. Worth naming because it is the SAME shape as the
   defect the whole slice exists to fix: counting rows that exist, and being blind to what has not
   happened yet.
2. **`sweep_overdue` could never fire.** The first implementation asked the scheduler for its
   CURRENT grid tick and compared it to now — but the current tick is by definition ~now, so the
   comparison was always false. Rewritten to measure elapsed time since the schedule's own last
   fire (or its anchor, if it has never fired), per schedule, against two of its declared periods.
3. **`event_time` is a canonical ISO-8601 STRING, not a datetime** (the audit chain hashes the
   serialized form). The window comparison raised `TypeError` on the first run; now parsed
   explicitly, with an unparseable timestamp treated as out-of-window rather than raising.

### By the mutation battery — a real gap, not a harness artifact

4. **The worker's sibling-transaction call had no test.** Mutant A-B1 deleted it and everything
   stayed green, because the proof for carry (q) exercised the SERVICE function directly. A fix
   whose only proof is a unit test of the helper it calls has an unproven seam — and that seam is
   where the carry actually lived. `test_the_WORKER_records_the_failure_when_the_alarm_transaction_blows_up`
   closes it; the battery then read 15/15.

### By an existing tripwire — the one worth keeping

5. **REPRO-1's totality test refused the mint.** `test_the_audit_outcome_mapping_is_TOTAL_over_the_notify_vocabulary`
   pinned the outcome vocabulary as an EXACT set with a docstring saying "minting a fourth outcome
   fails HERE until someone decides which way it maps". It did exactly that. The mint had to come
   to that test and state the mapping; the test is now re-armed for a fifth, and pins the
   concluding SUBSET separately, because "a new outcome exists" and "a new outcome retires a
   divergence" are different decisions.

## 4. Deviations from the record — CORRECTED at the review fold

The build's version of this section said "none material", and the review refuted it by execution:

- **The never-fired clock deviated from a RATIFIED sentence.** The record: "a never-fired
  schedule's clock starts at its first due tick after creation". The build measured from the
  ANCHOR — and the deployed proof's own seed (anchor 2026-01-01, deliberately past) made a
  schedule created seconds ago read instantly red. The proof masked it, because its sweep fires
  before its health read. Fixed: `max(anchor, created_at)`; test + mutant A-F2. The honest note:
  a deviation from ratified text recorded as "an implementation choice the record left open" is
  itself the claims-defect class — the record had NOT left it open.
- `sweep_overdue`'s mechanism (elapsed-time-since-last-fire rather than `select_active_due`)
  remains a genuine open-choice deviation, documented in §3 defect 2 — the record's suggested
  mechanism could not express lateness at all.
- The rollback sentinel is a new named constant, per the record's distinctness requirement.

## 4a. The review fold (different engine, 2026-08-10)

Two probe-confirmed findings, both in the newest logic, both fixed with test + mutant:

1. **Phantom-entity poison was PERMANENT RED.** The ratified scope is "red only while a
   STILL-QUEUED verdict's history contains poison"; the build implemented "not retired" — a
   different set. A poison row about an entity matching NO verdict (a buggy writer spraying rows
   about nothing — the exact shape the Wave-16 close probe planted) was neither queued nor
   retired, and stayed red for a probe-simulated YEAR with no remediation path: the P2-14
   cry-wolf state, back through a side door. Fixed to the ratified sentence exactly (mutant
   A-F1; A-C8 re-anchored). **Recorded residual:** a phantom poison row is now invisible to red —
   a red nobody can ever clear costs more than the phantom's visibility; trigger to revisit:
   the first real buggy-writer incident.
2. **The past-anchored fresh schedule** (above, §4 first bullet; mutant A-F2).
3. **The register:** this slice's roadmap row was missing — the shipped-without-a-row class at
   its third possible recurrence — and is now written AT the fold, riding the PR it describes.

Battery after the fold: **17/17** (15 build + A-F1/A-F2; A-C8 re-anchored to the tightened line).
Probes P3 (pre-attempt-id pooling) and P4 (mixed-attempt semantics) confirmed the build green.

## 5. Carries (P19)

- Everything the record listed as a non-goal stands unchanged, each with its trigger:
  acknowledgement / the nightly re-fire (carry (j)); breach-channel health; phase-5 scan
  performance (carry (k)); a real paging integration; verdict CONTENT reads (REPRO-2).
- **The regress, stated:** the surface is PULL-only. A red field pages nobody, so carry (t)'s
  sentence "no alarm fires about the alarm system" remains literally true one level up. The
  regress stops at the operator's eyes, and a broken health ROUTE shows an error rather than a
  false green — which is the property that makes pull-only acceptable. Trigger for a push leg:
  carry (j)'s slice, or the first missed-red incident.
