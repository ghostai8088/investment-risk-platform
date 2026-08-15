# Session Log: 10-08-2026 11:09 - onboard1b-merged-process-fold-alert1-shipped-repro2-part1

## Quick Reference (for AI scanning)

**Confidence keywords:** ONBOARD-1b, ENT-075, entitlement_request, four-eyes, SOD-04, CTRL-025,
CTRL-037, orphan invariant, process fold, make fix, gen-api-check, migration-head pin,
test_migration_head, test_ledger_census, ALERT-1, AlarmChannelHealth, sweep_overdue, dead_channel,
SKIPPED outcome, NOTIFY_CONCLUDING_OUTCOMES, courtesy skip, sibling transaction, carry (q),
carry (r), carry (n), REPRO-2, registry discovery, ENT-074, OQ-CAD-1-2, IRP_TENANT_IDS,
IRP_MAX_CYCLES, schedule.manage, forward gate, control_switched_off, IDENTITY_EXCLUDED_COLUMNS,
identity_offenders, mutation battery, different-engine review, P15, P18, P14, ultracode, workflows,
PRs #192 #193 #194 #195 #196

**Projects:** investment-risk-platform (Wave 17 — "an operator can start it")

**Outcome:** Five merges (#192–#196, the 23rd–27th autonomous) closing ONBOARD-1b, a
user-ratified efficiency/process fold, ALERT-1 end to end, and two ratified planning gates;
REPRO-2 part 1 built and gated at `60c4f2d`, awaiting the different-engine review, with the
remaining three OQs reported as a finding rather than absorbed.

## Decisions Made

- **ONBOARD-1b review (Fable):** deactivation four-eyes was scoped wrongly against the ratified
  record and its pinning test was NAMED for the ratified behaviour while asserting the opposite —
  fixed rather than re-ratified, because the record had not left it open.
- **`REJECTED` struck from ENT-075.** The record ratified approval and nothing else; a status no
  code path can produce is the LQ-1 inert-state class. A reject/withdraw verb is a named future
  decision, not a pre-minted state.
- **Four efficiency changes ratified by the user and built as one process fold** (`make fix`,
  `gen-api-check` re-founded, the 21 migration-head pins collapsed, the mechanical ledger census).
  Rejected as false economies: dropping local full-PG, single-engine build+review, thinner
  verifier passes.
- **ALERT-1 pause/visibility questions:** `SKIPPED` NOTIFY outcome MINTED (the only honest value —
  SENT would be a false record); five-role `schedule.view` set KEPT (tenant_admin excluded, with a
  revisit trigger); carry (s) and the pull-only surface ACCEPTED as recorded residuals.
- **REPRO-2 gate, four ratifications:** registry-driven discovery superseding CAD-1's OQ-2 (and
  OQ-3's parse half); BOTH colliding ratified dispositions amended by name (ALERT-1's
  `control_switched_off` red; OPS-H1's demo-tick default-on); pause = compensating VISIBILITY, not
  four-eyes.
- **REPRO-2 split into two build passes** — a finding reported at the gate, not a silent omission.
  Sixteen adapters rushed would produce exactly the defect the exclusion-truth obligation exists to
  catch; an absent family is visible in the coverage census, a wrong one is not.

## Key Learnings

- **A fix written under review pressure is the most defect-prone text in the file.** Pass 2 broke
  pass 1's own folds in all three planning cycles this session (ALERT-1, REPRO-2, and again in
  REPRO-2's blast radius). Enumerating collisions with ratified text deserves its own verifier lane.
- **A test named for the ratified behaviour must assert it.** The name is a claim; the assertion is
  the artifact. Found inside a test file at ONBOARD-1b.
- **A fix whose only proof is a unit test of the helper it calls has an unproven seam** — and the
  seam is usually where the carry actually lived (ALERT-1 mutant A-B1, the worker's
  sibling-transaction call).
- **A census whose rule lives inside the test can be vacuous.** With no offenders to find, an empty
  walk and a clean walk are indistinguishable. Move the rule into production code so the census and
  its negative control exercise the same path (REPRO-2 mutant R-C3).
- **Deployed proofs can mask state-dependent deviations** by exercising a fixed happy-path order
  (ALERT-1's past-anchored schedule read red only before its first fire — which the proof always
  did first).
- **Old tripwires pay off.** REPRO-1's totality test refused ALERT-1's fourth-outcome mint until the
  mapping decision was stated explicitly, exactly as its docstring promised two waves earlier.
- **Mechanical gates beat prose.** The route census demanded the forward-gate deletion "and
  celebrate"; ALERT-1's paused test refused REPRO-2's amendment until rewritten as its twin.

## Solutions & Fixes

- `make fix` (both-tier formatters, write mode) before the first gate; `-` prefix so an unfixable
  lint doesn't stop the gate run it prepares.
- `gen-api-check` re-founded: snapshot → regenerate → diff against the WORKTREE (the old git-diff
  form could never pass pre-commit for an API-changing branch).
- 21 hand-mirrored migration-head pins → `packages/shared-python/tests/test_migration_head.py`
  (single-head + declared-head; a new migration edits one line).
- `packages/shared-python/tests/test_ledger_census.py` — ORM tables → canonical rows, permission
  codes → SoD, audit event types → taxonomy (honouring the doc's wildcard AND abbreviation
  conventions). First run found 4 undocumented tables + 9 SoD-less codes; all backfilled.
- ALERT-1: `_classify_alarm_states` (one fold, two consumers), `record_alarm_transaction_failure`
  (sibling transaction under the worker-minted `attempt_id`), `already_delivered_recipients`
  (entity-scoped, doubt → PAGE).
- REPRO-2: `apps/worker/src/irp_worker/discovery.py` + `run_supervisor_discovering`;
  `IRP_MAX_CYCLES`; `apps/backend/src/irp_backend/api/schedule_admin.py`;
  `GET /reproduction/checks` with `UNREPRODUCIBLE_WIRE_DETAIL`; `identity_offenders`.

## Files Modified

Representative (full detail in each slice record):

- `packages/shared-python/src/irp_shared/reproduction/service.py`: the classification fold, 13
  health fields, courtesy skip, sibling-transaction recorder, `control_switched_off`.
- `packages/shared-python/src/irp_shared/notification/events.py`: `NOTIFY_OUTCOME_SKIPPED` +
  `NOTIFY_CONCLUDING_OUTCOMES`.
- `packages/shared-python/src/irp_shared/reproduction/registry.py`: `IDENTITY_EXCLUDED_COLUMNS`,
  `identity_offenders`.
- `apps/worker/src/irp_worker/{discovery.py,supervisor.py,tenants.py}`: registry discovery, strict
  parse, bounded cycles.
- `apps/backend/src/irp_backend/api/{reproduction.py,schedule_admin.py,tenants.py}`: health read,
  verdict read, three schedule writes, rewritten `WORKER_FOLLOWUP`.
- `Makefile`, `apps/frontend/package.json`: `fix` target, `format` script.
- `infra/deploy/{deploy.sh,prove_onboarding.sh,prove_reproduction.sh}`: step 8 inverted + 8b,
  onboarding arm 5, reproduction arm 5.
- `scripts/mutants.toml`: groups `onboard-1b` (17), `alert-1` (17), `repro-2` (14).
- Ledgers: canonical model, SoD model, audit taxonomy, control matrix (CTRL-018/025/031/037),
  delivery roadmap, CAD-1 record (4 sites), slice records for 1b/ALERT-1/REPRO-2.

## Setup & Config

- `IRP_MAX_CYCLES` — new optional worker bound (unset = forever); required by the deployed idle
  proof since the supervisor no longer exits on an empty tenant list.
- `IRP_TENANT_IDS` — semantics CHANGED: an optional restriction filter, not the tenant set.
- Local PG `irp_pg_local` at head `0068`; schema reset before every full-PG run (standing rule).
- FE API prefixes gained `/users`, `/roles`, `/entitlement-requests`, `/reproduction`; `/schedules`
  still owed in part 2 (with the nginx alternation in lockstep).

## Pending Tasks

1. **Different-engine review of REPRO-2 part 1** over `e56d9b0..60c4f2d` (Fable) — the immediate
   next step; nothing pushed, no PR.
2. **REPRO-2 part 2:** OQ-REP2-4 (sixteen family adapters + exclusion-truth tamper tests + coverage
   census 19+2 + measured sweep wall time), OQ-REP2-5 (demo stage + deployed second-tenant arm),
   OQ-REP2-6 (`/ops/reproduction` screen + `/schedules` prefix lockstep).
3. Then RPT-3, and TS→7 on its mechanical trigger; then the Wave-17 close.

## Errors & Workarounds

- **`queued` counted only verdicts with dispatch rows** (ALERT-1) — a fresh divergence read as an
  empty queue; the same shape as the defect the slice existed to fix.
- **`sweep_overdue` could never fire** — compared the scheduler's CURRENT grid tick to now.
  Rewritten to elapsed-time-since-last-fire per schedule.
- **`event_time` is a canonical ISO-8601 STRING**, not a datetime (the chain hashes the serialized
  form) — window comparisons must parse.
- **Phantom-entity poison held a tenant red for a simulated year** — the ratified "still-queued"
  scope had been implemented as "not retired".
- **FK-1's real foreign keys** rejected test fixtures pointing at `calculation_run.id` instead of
  `.run_id`.
- **Route census arithmetic**: +3 counted where +4 was ratified (the verdict read is a route too).
- **mypy**: `_refuse()` untyped as `NoReturn` made every guard read as "maybe fell through".
- Tooling: `cd` in a backgrounded command doesn't persist; `[[mutant]]` headers and `id` are
  required in `mutants.toml`; a battery must have the tree to itself.

## Key Exchanges

- User ratified all ONBOARD-1b/ALERT-1/REPRO-2 gate questions as recommended (four AskUserQuestion
  rounds across the session).
- User asked for an objective efficiency assessment, then "make all of your suggested changes" —
  producing the process fold (#193).
- User invoked ultracode twice for planning; both runs used two adversarial verifier passes with
  refute-by-default (ALERT-1: 50 agents/36 findings; REPRO-2: 56 agents/44 findings).

## Custom Notes

None

---

## Quick Resume Context

REPRO-2 part 1 is committed at `60c4f2d` on `repro-2-impl` (not pushed) and is waiting on its
different-engine review over `e56d9b0..60c4f2d` — run that on Fable before any PR. Part 1 delivers
registry-driven worker discovery, the schedule write path, and the verdict read; part 2 owes the
sixteen family adapters, the demo/deploy seeding and the ops screen, which was reported as a
finding at the gate rather than quietly dropped. Local `main` is at `e56d9b0` plus the merges
through #196; PG sits at head `0068` with no migration in this slice.

---

## Raw Session Log

The complete turn-by-turn transcript for this session lives in the authoritative JSONL at:

`/Users/andrewcox/.claude/projects/-Users-andrewcox-Projects-investment-risk-platform-investment-risk-platform/70b746c9-a66f-4a2f-a168-ed3b64166457.jsonl`

**This log deliberately points at that file rather than reproducing the conversation**, as the five
previous logs in this directory do. Reconstructing a verbatim transcript from memory would fabricate
a record — and this session's subject matter was precisely that failure class: a test named for a
proof it did not deliver, a census whose rule made it vacuous, a fix proven only at the helper it
calls, and a record citing a runbook that does not exist. The condensed chronology above is
accurate; the JSONL is complete.

**Chronology (merges in order):**

1. **#192 = `7761cf1`** (23rd) — ONBOARD-1b: four-eyes/ENT-075, orphan invariant, Users & Roles UI.
   Review found the BLOCKING deactivation-scope deviation and a probe-confirmed cross-tenant role
   gap.
2. **#193 = `b1fc70c`** (24th) — the process fold: `make fix`, pre-commit `gen-api-check`, one
   migration-head pin, the mechanical ledger census (whose first run paid real P0–Wave-12 debt).
3. **#194 = `9ac331b`** (25th) — ALERT-1 planning ratified after two passes (29 + 21 agents).
4. **#195 = `b7e7b888`** (26th) — ALERT-1 shipped: twelve health fields, the sibling-transaction
   bound, the courtesy skip with its `SKIPPED` mint, the ops panel. Seven defects, all by execution.
5. **#196 = `e56d9b0`** (27th) — REPRO-2 planning ratified after two passes (31 + 25 agents).
6. **`60c4f2d`** — REPRO-2 part 1, built and gated, awaiting review.
