# REPRO-1 remit — the reproducibility claim becomes a nightly machine verdict

**Slice of:** Wave 16 (ratified 2026-08-07, OQ-W16P-1…7 all as recommended), slice 2 of 3.
**Operating model:** this remit defines OUTCOMES and PROOFS. The build has freedom of method;
deviations are recorded in the slice record; a fresh-context audit checks the proofs BEFORE merge.

## Inherited gate commitments (the P7 fix — nothing here may fire silently)

| Source | Commitment | Discharged by |
|---|---|---|
| Wave-15 close §7-A | CTRL-018 is HOSTED here after four citations-without-host. Citation-without-host is **no longer an available disposition** for that row | Invariant I6 |
| OQ-W16P-5 | Ride the EXISTING scheduler as a new schedulable family; the run-type census extension is a **conscious act**; divergence → the webhook sink; CTRL-018 moves only on the **first OBSERVED scheduled green** | I1, I3, I4, I6 |
| OQ-W16P-5 | The report family's check is `regenerate_report` itself, putting **CTRL-009 on the path to Operational** | I2 |
| Wave-15 close §7-B (PERF-0's four carries) | Bound to "before any parallelization or grain-level performance work". REPRO-1 **re-executes existing binders unchanged** and touches no kernel grain ⇒ **NOT inherited**. Stated so the non-inheritance is a visible reading, not an oversight | — |
| P9 | The divergence alarm must be **made to FIRE** on a planted divergence before the control moves | I4 |
| P11 + the RPT-2 mint-reachability finding | Any permission mint carries holder-set pin + route census + SoD row **and a sync migration** — appending to `bootstrap.py` does not reach a live database | I7 |
| P15 | REPRO-1 is itself a P15 instrument; its own claims still need a proof not sharing the unit tier's assumptions | I6 |
| RPT-2 §5 carries (a)–(i) | Reviewed at this remit; none blocks this slice. Any that this slice's surface touches is discharged or restated in the slice record | Slice record §5 |

## Goal

The platform's central promise — *the same inputs and the same code produce the same governed
numbers* — stops being something a human demonstrates on demand and becomes something a machine
asserts every night, per tenant, with a durable verdict and an alarm when it fails.

## Scope boundary

- **IN:** a `REPRODUCTION` schedulable family riding the existing scheduler; a per-family
  reproducer registry with a census; re-execution of covered families' binders over each
  historical run's OWN pinned snapshot; a governed verdict record (ENT-073); divergence routed to
  the notification sink; a nightly schedule the demo/deploy path creates; a deployed-stack proof
  with a **negative arm**.
- **OUT (explicitly):** scheduled report GENERATION (Wave-16 Part 5 pre-emption — its own approval
  semantics); any new governed number family; any change to a family's kernel, binder, or result
  schema; FK-1 (the next slice); remediation workflow for a divergence (the alarm notifies; what an
  operator then does is breach-lifecycle territory and is not minted here).

## The two checks this slice deliberately does NOT conflate

A reproduction job can ask two different questions, and answering them with one verdict would make
the alarm useless:

1. **Computation reproduction (this slice, CTRL-018).** Re-execute the family binder over the
   run's OWN pinned `dataset_snapshot` and compare the recomputed result content against the
   stored rows. Because the snapshot pins content (AD-014), this is **invariant under later
   corrections to live data** — a divergence therefore means the CODE changed what it computes.
   That is the alarm worth waking someone for.
2. **Input drift** — `verify_snapshot` re-resolves a snapshot's components against live data. A
   drift there is usually an *expected* consequence of a legitimate correction. It is a different
   question with a different response, it already exists, and REPRO-1 does not fold it into the
   CTRL-018 verdict.

If the build records input drift at all it is a **separate, separately-named** field, never a
divergence.

## Invariants (each becomes at least one named proof)

| # | Invariant | The proof that makes it real |
|---|---|---|
| I1 | **A reproduction check persists NOTHING of what it recomputes.** Re-execution runs in a nested transaction that is always rolled back: no `calculation_run`, no result rows, no audit events, no lineage survive it. Reusing a shipped result table under a new run would activate every read that omits a run filter (the PPF-2 blocking class) | A test re-runs a covered family and asserts, after the check, that the family's row count, the `calculation_run` count and the tenant's audit-chain head are **unchanged** — plus `verify_chain` still reports gapless |
| I2 | **The verdict is computed, not assumed.** A MATCH verdict is produced by an actual value-by-value comparison against the stored rows; a planted change to a single stored value produces DIVERGED | Mutation: alter one stored result value → the check must report DIVERGED and name the field. A test that only exercises the happy path does not satisfy this |
| I3 | **A divergence is a successful check with a negative verdict, never a failed dispatch.** `scheduled_run.outcome` stays `DISPATCHED` when the check RAN; infrastructure failure is `FAILED`. Collapsing the two makes the platform's most important alarm indistinguishable from a database hiccup (the RPT-2 identity-vs-ordinary-500 lesson) | Two tests: a planted divergence leaves `outcome=DISPATCHED` + a `DIVERGED` verdict; an induced infrastructure error leaves `outcome=FAILED` + no false verdict |
| I4 | **The alarm FIRES** (P9). A divergence reaches the notification sink; the sink's failure does not silently swallow it | A planted divergence drives a real sink call, asserted at the sink; a sink that raises leaves durable evidence rather than a lost alarm |
| I5 | **Coverage is a census, not a silence.** Every governed family is either REGISTERED with a reproducer or listed as UNREGISTERED **with a reason**; the two sets together must equal the full family set, by exact equality | A census test enumerates the families from their canonical source and asserts registered ∪ unregistered == all, with no overlap — the RPT-2 route-census shape. A new family that lands in neither set fails the suite |
| I6 | **CTRL-018 moves only on an OBSERVED scheduled green** — the deployed stack, the real worker, a real tick, a durable verdict row. And the negative arm: a planted divergence on the deployed stack must produce the alarm | A `stack-proof` CI step runs both arms against the running stack; the run conclusion for the head SHA is quoted. Absent that observation the control row stays Planned and the slice record says so |
| I7 | **Anything minted is deliverable.** If this slice mints a permission code, it ships bootstrap + **sync migration** + holder-set pin + route/consumer census + SoD row. If it mints none, the record says so explicitly | The mint checklist, or the explicit "no code minted" sentence in the slice record and the SoD doc |
| I8 | **RLS and the no-BYPASSRLS doctrine are untouched.** The reproduction runs inside the tenant's own non-BYPASSRLS session, like every other tick; ENT-073 is PROPRIETARY, tenant-scoped, symmetric FORCE RLS, IA append-only, never hybrid | The PG RLS suite covers ENT-073 in both directions (own-tenant visible, foreign-tenant invisible) and the append-only trigger refuses an UPDATE |

## Design forks this remit closes (recorded because they change what CTRL-018 PROVES)

1. **Re-execute the binder, not just the kernel.** Eighteen service modules already accept a
   consume-existing `snapshot_id`, so the historical run's own snapshot can be fed back through the
   real production path. A kernel-only re-derivation would prove less — it could not see a change
   in a binder's adjudication — and the control's wording is "re-runs historical runs". The cost is
   the nested-transaction discipline of I1, which the scheduler already uses for its own phantom
   runs.

   **Verified by EXECUTION before the design was adopted, not reasoned (P12).** A throwaway probe
   re-ran `run_var` over an existing run's own `input_snapshot_id` inside `session.begin_nested()`
   and rolled back: the recomputed `sigma`/`var_value` equalled the stored values exactly, and
   afterwards the `VAR` run count, the `var_result` count and the tenant's audit-event count were
   all unchanged with `verify_chain` still `ok` (gapless). Its **positive control** — the same
   manoeuvre with `sp.commit()` instead — moved all three counts, so the three "unchanged"
   assertions are load-bearing rather than vacuous (P5). `PROBE_EXIT=0`. The probe becomes I1's
   real test rather than being thrown away.
2. **The verdict is control-plane evidence, not a governed number.** ENT-073 binds no snapshot and
   no model of its own; it references the already-`CALC.RUN_*`-audited run it checked. This is the
   `breach` / `breach_action` precedent verbatim, and it is why this slice mints no `calculation_run`
   of its own and no new audit code.
3. **Coverage starts partial and says so.** The engine, the census, the alarm and the proof are the
   deliverable; the registered family set is whatever the build can cover honestly. I5 makes the
   remainder enumerated rather than implied, and the CTRL-018 row states the coverage in the same
   sentence as the status.

## Known hazards the build must address explicitly

- **The audit advisory lock is transaction-scoped.** `record_event` takes `pg_advisory_xact_lock`
  per tenant chain; a SAVEPOINT rollback does **not** release it. The tick already holds it, so
  reproduction lengthens an existing hold rather than creating a new class — but the build states
  the expected duration and the slice record carries it. If a covered family's re-execution is slow
  enough to matter, that is a finding, not a footnote.
- **`Schedule.scope_portfolio_id` is NOT NULL.** A tenant-wide reproduction family either names a
  portfolio or the column gains the SCH-2 treatment (per-family declaration + DB CHECK, exactly as
  `model_version_id` did). Whichever is chosen is declared in the registry, never inferred from
  whether a caller supplied a value — that shape is a CTRL-003 fail-open.
- **`ScheduledRun.calculation_run_id` NULL currently means "dispatch failed before the run was
  created".** A reproduction fire mints no run, so it widens that column's meaning. Every consumer
  (including `ScheduledRunOut` on the schedules API) is checked, and the model docstring is
  corrected — a stale docstring on a widened column is the register-entry class (P3).
- **The import fence is set-equality.** `_RISK_IMPORTERS` / `_EXPOSURE_IMPORTERS` in
  `test_scheduler.py` admit importers by explicit reviewed edit. A reproduction package that
  imports family binders joins by that edit, visibly, on the CON-1 posture — never by widening the
  fence.
- **Comparison must exclude the non-deterministic.** Row ids, timestamps and the recomputed run id
  differ by construction. Each registry entry declares the natural key and the value columns it
  compares; a comparison that silently ignored a column would be a control that cannot fail.

## Named proofs (P14 applies to every one — captured exit code quoted, no pipes in the capture path)

1. `make check-all` — exit code quoted, both tiers, per commit claiming green.
2. Full-PG fresh-schema battery — `PYTEST_EXIT` quoted, schema reset before the run.
3. The I1–I5 tests, **mutation-proven**: every new refusal and every new fix is made to FIRE
   (P9 + the RPT-2 companion lesson — twice a security fix shipped with no test).
4. The deployed-stack proof, both arms (I6), with the CI run conclusion for the head SHA quoted.
5. **Fresh-context audit BEFORE merge**, pointed at the review's own fold as well as the build;
   P1 seven-ledger sweep AFTER the last merge, verified on `main`.

## Recon findings that CONTRADICT the ratified shape (verified against the code, not relayed)

Seven independent readers were run against `main` at `88ccbed`; each claim below was then re-read
by hand before it was written down.

1. **"Rides the existing scheduler" is NOT schema-free.**
   `ck_schedule_model_version_by_family` (`0053_schedule_cadence_family.py:101-107`) is a **TOTAL
   ENUMERATION** — `(VAR AND model_version_id IS NOT NULL) OR (EXPOSURE_AGGREGATE AND
   model_version_id IS NULL)`. PostgreSQL **rejects** a third family. 0053's own docstring records
   this as deliberate: "the exclusive-exhaustive form below fails CLOSED, which makes admitting
   family 3 require a migration." **And SQLite carries no CHECKs, so the entire unit tier —
   `make check` — goes GREEN with the registry widened and no migration.** Only
   `test_scheduler_cadence_pg.py:190-198` catches it, and only when the PG battery is actually run.
   Migration `0065` is therefore mandatory, not optional.
2. **"Divergence routes to the webhook notification sink" has no existing path.**
   `BreachNotification.breach_id` is `nullable=False` with an FK to `breach.id`
   (`notification/models.py:64`); `notify_for_event` reads only `BREACH.DETECT`/`BREACH.ESCALATE`;
   `NotificationMessage` requires a `breach_id`; `WebhookNotificationSink` hard-codes
   `"type": "breach-alert"`. **Only the sink OBJECT is reusable**, never the notification
   subsystem or its table. Writing reproduction rows into `breach_notification` would also
   re-open a closed HIGH: `_current_high_water` filters on `tenant_id` alone, so a repro row with
   a higher `source_sequence_no` permanently hides every lower-sequence unnotified BREACH alarm.
3. **"Per tenant" has no home on the schedule table.** `scope_portfolio_id` is NOT NULL with a hard
   FK, re-resolved in-tenant at `create_schedule`. Settled at this slice's gate (below).
4. **Two families cannot be reproduced at all today.** `run_concentration` and `run_liquidity` take
   **no `snapshot_id`** — both unconditionally rebuild their snapshot, and
   `build_concentration_snapshot` pins **current-head** classification assignments, so any
   classification edit since the original run yields a FALSE divergence.
5. **Liquidity has a wall clock inside its compute path** (`liquidity/service.py:295`:
   `age = datetime.now(UTC) - pinned.oldest_assignment_at`, appending `GAP_STALE_TIERS` past the
   declared bound). It is the ONE family whose result is not a function of pinned content alone —
   a nightly reproduction of a once-fresh run will FAIL, with zero rows, as the ladder ages.
   Contrast `var_service.py:585-589`, which anchors its age gate on pinned content precisely so
   re-runs stay stable.
6. **`run_type` does not identify the binder.** VAR has three entry points and seven registered
   models; `var_backtest_result` is shared by `VAR_BACKTEST` and `ES_BACKTEST`; `covariance_result`
   by `COVARIANCE` and `COVARIANCE_PRIVATE`. Dispatching a reproduction on `run_type` alone runs
   the WRONG kernel. RPT-1 already solved this — resolve the bound `model_code` from the run's own
   rows against a declared allowlist (`report/families.py`) — and this slice reuses it rather than
   re-deriving it.
7. **Six binder parameters are not on the run row** — `window_months` (ROLLING_RISK, SHARPE),
   `scheme_by_dimension` (CONCENTRATION), `scheme_id` (LIQUIDITY), `base_currency`
   (EXPOSURE_AGGREGATE), `return_basis`/`benchmark_id` (BENCHMARK_RELATIVE). Each is recoverable
   only by reading it back off the stored RESULT rows. **Supplying any of them from a config
   default is RPT-1's B1 defect verbatim** and is forbidden here.
8. **`run_exposure`'s consume path silently defaults `base_currency` to `DEFAULT_BASE`** and stamps
   `scope_portfolio_id` NULL. A reproducer passing only `snapshot_id` would recompute a EUR book in
   USD and report every row divergent.
9. **The deployed worker has never connected to a database.** `IRP_TENANT_IDS=` is empty in
   `.env.example:21`; `deploy.sh:132` deliberately deploys it empty because no tenant exists yet;
   the supervisor **fails closed at startup** on an empty list. CTRL-018's evidence bar is an
   OBSERVED scheduled green, so this slice must seed a tenant into the deployed stack and prove
   the worker's DB path — RPT-2's carry (b), which named REPRO-1 as its natural host. Without it
   the control stays Planned for a FIFTH time, which its own row says is not available.
10. **`SCHEDULED_RUN_OUTCOMES` has zero consumers** and `scheduled_run.outcome` carries no DB
    CHECK — so a new `DIVERGED` outcome value would be enforced by nothing. That is the
    `produces_run_on_failure` shape this project deleted ("a false declaration with no consumer is
    worse than no declaration"). It is another reason the verdict lives on ENT-073, not on the
    ledger's outcome column.

**Two P11/ledger debts found on `main`, adjacent to this slice and not caused by it** (recorded now
so they cannot be discovered twice): `06_security/entitlement_sod_model.md` has **zero** §5B rows
for `schedule.*`, `limit.manage`, `limit.approve`, `breach.respond`, `breach.review` — eight minted
codes with no SoD row; and RPT-1's claim that `report/service.py` is "recorded on the P8 census
exception list" is **false as written** — the exception dict contains only `exposure/service.py`,
and the census scans for a literal `execute_governed_run(` that `report/service.py` never calls.
Disposition is recorded in the slice record; neither is silently carried.

## Gate outcome (2026-08-07) — four Tier-3 forks the Wave-16 gate did not reach

The forks above are entity mints, a shipped-constraint relaxation, a coverage grain and an
audience — all Tier-3. Put to the user with recommendations; **all four taken as recommended.**

| OQ | Outcome | Operating assumption made explicit |
|---|---|---|
| **OQ-REPRO-1-1** | **Relax `schedule.scope_portfolio_id` under a family-gated TOTAL-ENUMERATION CHECK** (the 0053 pattern, applied to a second column) | That "per tenant" was meant literally, and that a sentinel portfolio stamped into a governed config row the ops UI renders would be a lie |
| **OQ-REPRO-1-2** | **Mint ENT-073 `reproduction_check`** — IA append-only, tenant-scoped, symmetric FORCE RLS; one row per (tick, subject run) carrying family, verdict, rows compared, rows diverged, first divergence | That CTRL-018's "Reproduction report" evidence column means something an auditor can read later, not a log line |
| **OQ-REPRO-1-3** | **Three shapes + census:** VAR (model-bound), EXPOSURE_AGGREGATE (model-less), REPORT (artifact). Every other family pinned UNREGISTERED **with a reason**, by exact set equality | That honest partial coverage with an enumerated remainder beats broad coverage whose parameter read-back makes the check share an assumption with what it checks (P15) |
| **OQ-REPRO-1-4** | **Reuse `breach.review` as the divergence audience**; `recipient_reason` records which permission addressed it | That an alarm which demonstrably reaches a human beats a semantically tidier code held by nobody — the LQ-1 written-believed-inert class |

## Decisions taken without a gate (routine, precedent-backed — stated so they are reviewable)

- Migration `0065` carries all three DDL acts: the REPRODUCTION arm on the family CHECK
  (**model-less ⇒ the `model_version_id IS NULL` arm**), the `scope_portfolio_id` relaxation, and
  ENT-073. The 0059 precedent is followed for the widened CHECKs — capture the 0053 bodies verbatim
  as constants so `downgrade` restores what actually existed.
- The divergence uses `NotificationSink` / `default_sink()` directly, with the message shape
  generalized so a reproduction alarm does not POST a payload calling itself a breach. Nothing is
  written to `breach_notification`.
- The recompute resolves its binder via the RPT-1 model-code allowlist, reads `base_currency` back
  off `exposure_aggregate`, and never supplies a parameter from a default.
- A divergence leaves `scheduled_run.outcome = DISPATCHED`. Infrastructure failure is `FAILED`.
- LIQUIDITY and CONCENTRATION are UNREGISTERED with the reasons at findings 4 and 5, stated on the
  CTRL-018 row in the same sentence as the status.

## Model-diversity disclosure (standing, this slice)

The pre-merge audit runs on **fresh-context Opus**, not a second engine — no Fable allocation was
available on 2026-08-07. The RPT-2 evidence is that the lane which paid was fresh CONTEXT (that
audit was itself Opus and still found the issuer disclosure a five-lens review missed), so the loss
is the engine half of P15 and not the lane itself. This is recorded here and repeated in the slice
record so the gap is a stated fact rather than an implied full-strength claim.
