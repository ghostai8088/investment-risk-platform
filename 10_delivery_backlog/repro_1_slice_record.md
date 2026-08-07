# REPRO-1 slice record — the reproducibility claim became a nightly machine verdict

**Wave 16, slice 2 of 3.** Remit: `repro_1_remit.md`. Branch `repro-1-reproduction-job`.
**Every claim below is cited to an artifact and was checked against the diff before this file was
written** (P1 ledger 7 — REF-1's merged record carried five false claims, found only because the
next slice's recon happened to re-read it).

## 1. What shipped

A nightly, per-tenant **reproduction sweep** that rides the existing scheduler as a third
schedulable family. For each registered governed family it takes the most recent COMPLETED run,
**re-executes that run's binder over the run's OWN pinned `dataset_snapshot`** inside a nested
transaction that is always rolled back, compares the recomputed content against the stored rows,
and writes a verdict (ENT-073 `reproduction_check`: MATCH | DIVERGED | UNREPRODUCIBLE). Divergences
are alarmed in a **separate tick phase**.

| Artifact | Where |
|---|---|
| ENT-073 `reproduction_check` | `packages/shared-python/src/irp_shared/reproduction/models.py`; migration `0065_reproduction_check.py` |
| The engine (sweep, comparison, verdicts, alarm) | `reproduction/service.py` |
| The reproducer registry + coverage census | `reproduction/registry.py` |
| The vocabulary (leaf module) | `reproduction/events.py` |
| `REPRODUCTION` schedulable family | `scheduling/service.py` (`_dispatch_reproduction`, `FAMILY_REGISTRY`) |
| Tick phase 5 (alarm delivery) | `apps/worker/src/irp_worker/reproduction_alarms.py`, wired in `irp_worker/scheduler.py` |
| Deployed proof, both arms | `infra/deploy/prove_reproduction.sh` + `irp_shared/deploy/reproduction_proof.py` |
| Unit + PG suites (26 tests) | `tests/test_reproduction.py`, `tests/test_reproduction_pg.py` |

## 2. Gates, with captured exit codes (P14)

| Gate | Result |
|---|---|
| `make check-all` (both tiers) | **`CHECK_ALL_EXIT=0`** |
| Full-PG battery, schema reset then migrated to head | **`PYTEST_EXIT=0`** |
| Deployed-stack proof, both arms | **`PROOF_EXIT=0`** |
| Mutation battery, 11 controls | **`MUTATION_EXIT=0`** — all killed |
| CI on head `5fafd00` | run **`31204168002`**, conclusion **`success`**, all 8 jobs |
| CTRL-018's observed evidence | `stack-proof` step *"Prove a scheduled reproduction detects a planted divergence (CTRL-018)"* → **`success`** |

Battery size **MEASURED** on a fresh collect, not derived: **3,116** collected (was 3,109 before
this slice's suites; +26 new tests, less the arithmetic of suites that also gained tests).

## 3. The Tier-3 forks, and why they existed

Recon found that **three sentences of the ratified OQ-W16P-5 shape could not be built as written**.
Each was verified by hand against the code before being reported, not relayed from an agent.

1. **"Rides the existing scheduler" is not schema-free.** `ck_schedule_model_version_by_family`
   (`0053:101-107`) is a TOTAL ENUMERATION over exactly `VAR` and `EXPOSURE_AGGREGATE`; PostgreSQL
   rejects a third family. 0053's own docstring records this as deliberate. **And SQLite carries no
   CHECK constraints, so the entire unit tier would have gone green on the defect** — only the
   full-PG battery sees it.
2. **"Divergence routes to the webhook notification sink" has no existing path.**
   `BreachNotification.breach_id` is `nullable=False` with an FK to `breach.id`; the queue reads
   only `BREACH.DETECT`/`ESCALATE`; the webhook body hard-coded `"type": "breach-alert"`. Only the
   sink OBJECT is reusable. Writing reproduction rows into that table would also re-open a closed
   HIGH: its cursor filters on `tenant_id` alone, so a repro row with a higher sequence would
   permanently hide every lower-sequence unnotified BREACH alarm.
3. **"Per tenant" has no home** — `scope_portfolio_id` was NOT NULL with a hard FK.

Four forks were put to the user with recommendations; **all four taken as recommended** (remit,
Gate outcome table): relax the column under a family-gated total-enumeration CHECK; mint ENT-073;
three families registered with the rest census-pinned; reuse `breach.review` as the alarm audience.

## 4. What EXECUTION found that reading did not

Seven defects. **Not one was visible to reading, to the type checker, or to a green test run.**

1. **My own planted-divergence test was VACUOUS and reported MATCH.** `make_session_factory` sets
   `expire_on_commit=False`, so after the raw `UPDATE` the session kept serving the pre-plant object
   from its identity map and the comparison never saw the plant. The helper now expires and **reads
   back, asserting the plant landed**. A planted-divergence test that cannot plant is the
   written-believed-inert shape this platform keeps re-finding.
2. **`create_schedule` stringified `scope_portfolio_id` unconditionally**, so the new NULL case
   stored the literal `'None'`. SQLite accepted it happily; PostgreSQL rejects it as `invalid input
   syntax for type uuid`. **The warning about exactly this was already in the file, one line below,
   about the sibling column SCH-2 fixed.**
3. **The deployed proof's first run produced a perfectly green tick over a tenant whose subjects the
   sweep could not see** — the harness minted its own tenant while seeding through the report
   proof's. Zero verdicts, `DISPATCHED`, every operational surface saying fine. **The product-side
   fix is the larger half: a sweep that checked NOTHING is now a FAILED run carrying the reason**,
   because a control that is running, believed and checking nothing is the LQ-1 shape.
4. **Seeding both proof schedules together let the FIRST tick fire both** (`fired=2`), consuming the
   negative arm's tick bucket before there was anything to catch — the arm would have found nothing
   to fire and **passed while proving nothing**.
5. **Tick phase 5 reads `reproduction_check` on every tick**, and the constrained `irp_app` role had
   no grant on it — so under a non-owner role the whole tick fails there. The deployed proof runs as
   the owner and **structurally could not see this**; the full-PG battery did.
6. **`test_scheduler_cadence_pg` reads `calendar_holiday` without granting it** — green only because
   an earlier CI step in the same un-reset database happens to. Pre-existing; fixed here because the
   fresh-schema run exposed it and the file was already being edited.
7. **`mypy` caught two real consequences of the nullability change**: a DTO field narrower than its
   column (which would 500 the whole `/schedules` page on the first tenant-wide schedule) and an
   unguarded scope in `_dispatch_var` (which would have resolved "the latest exposure run for scope
   None"). Both fixed with real guards rather than casts.

## 5. Design decisions worth reviewing

- **Re-execute the BINDER, not the kernel.** Eighteen service modules accept a consume-existing
  `snapshot_id`. A kernel-only re-derivation would prove strictly less — it could not see a change
  in a binder's adjudication — and CTRL-018's wording is "re-runs historical runs". **Verified by
  EXECUTION before adoption** (`PROBE_EXIT=0`): the recompute reproduced the stored values exactly
  and left run/result/audit counts unchanged with `verify_chain` gapless; the positive control (the
  same manoeuvre committed) moved all three.
- **The verdict is control-plane evidence, not a governed number.** ENT-073 binds no snapshot and no
  model of its own — the `breach`/`breach_action` precedent. It DOES bind a `REPRODUCTION`
  `calculation_run`, because OQ-SCH-2-8 requires a schedule's family key to be a real run type.
- **Phase 5 is separate from the sweep**, because phase 1 holds the per-tenant audit advisory lock
  to COMMIT and a sink call there is the API-2b lock-across-I/O anti-pattern. Its queue is an
  EXISTENCE test per verdict, not a derived `MAX` cursor — NOTIF-1's lesson that a cursor cannot
  represent a gap. Unlike phase 4 it does **not** head-of-line block: with an existence queue there
  is no cursor to corrupt, so one poison verdict must not silence the night's other divergences.
- **`first_divergence` names the row key and the field, never the VALUES.** The moment a read
  surface is added it will be gated by some permission, and the obvious candidate `schedule.view` is
  held by `auditor_3l`, which holds no `valuation.view`/`position.view`/`marketdata.view`. This is
  RPT-2's confirmed disclosure class, pre-empted rather than re-found. Mutation M9 proves the guard.
- **Coverage is a census, not a silence.** Three registered, eighteen excluded with a written reason
  each, union asserted equal to the run-type vocabulary by exact set equality. Two exclusions are
  substantive: CONCENTRATION re-pins current-head classifications; LIQUIDITY has a wall clock in its
  compute.
- **The notification wire format changed, deliberately and not back-compatibly.**
  `NotificationMessage.breach_id` → `subject_id`, plus an `alert_type`; the payload key changed with
  it. The channel has no external consumer (the webhook URL is unset by default and the sink shipped
  one wave ago), and the alternative — a compatibility alias nobody would ever remove — would have
  left a transport that calls every alert a breach.

## 6. Carries

| # | Carry | Trigger |
|---|---|---|
| (a) | **Eighteen families remain unreproduced**, each with a written reason. Sixteen are "not yet adapted" and cheap (a key/field declaration, sometimes a parameter read-back). | The next reproduction-touching slice; or when a family's own slice next opens |
| (b) | **CONCENTRATION needs a consume-existing path** before it can ever be reproduced (its binder rebuilds and re-pins current-head classifications) | A concentration-touching slice |
| (c) | **LIQUIDITY's staleness gate is wall-clock**, so re-anchoring it on pinned content (the `var_service` precedent) is a change to a shipped governed refusal — a model-identity question, not a reproduction decision | A liquidity/model-governance gate |
| (d) | **CTRL-018 is Implemented, not Operational.** The schedule that drives the proof is created by a proof harness; no production deployment exists | A real deployment |
| (e) | **A legitimately-empty tenant now FAILS its nightly sweep** (by design — see §4.3). If an operator surface ever treats a FAILED `scheduled_run` as an incident, this needs a distinct disposition | An operational-alerting slice |
| (f) | **`SCHEDULED_RUN_OUTCOMES` still has zero consumers** and `scheduled_run.outcome` has no DB CHECK — a declaration nothing enforces | The next scheduling slice |
| (g) | **The SoD register is missing §5B rows for eight shipped codes** (`schedule.*`, `limit.manage`, `limit.approve`, `breach.respond`, `breach.review`). P11 debt discovered adjacent to this slice, not caused by it | Recorded for the Wave-16 close |
| (h) | **RPT-1's claim that `report/service.py` is "recorded on the P8 census exception list" is false as written** — the exception dict contains only `exposure/service.py`, and the census scans for a literal `execute_governed_run(` that `report/service.py` never calls. REPRO-1's binder is in the same position and this record says so plainly rather than repeating the claim | Recorded for the Wave-16 close |

## 7. Model-diversity disclosure

The pre-merge audit ran on **fresh-context Opus, not a second engine** — no Fable allocation was
available on 2026-08-07. RPT-2's evidence is that the lane which paid was fresh CONTEXT (that audit
was itself Opus and still found the issuer disclosure a five-lens review had missed), so the loss is
the engine half of P15 and not the lane itself. Stated here as a fact rather than left as an implied
full-strength claim.
