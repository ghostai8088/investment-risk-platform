# PERF-0 — the scale probe (Wave-14 slice 1.5)

**Status: IMPLEMENTED, PRE-CLOSEOUT (see Part 9 for what actually shipped). OQ-PERF-0-1 and OQ-PERF-0-2 USER-RATIFIED 2026-07-30 (both as recommended);
OQ-3…OQ-10 stand as recommendations taken under the delivery-autonomy grant (engineering calls,
not Tier-3 forks) and are recorded as such. NO VERIFIER PASS HAS RUN ON THIS RECORD YET — the
ES-1 standing lesson says one runs BEFORE ratification, and this is the exception, flagged rather
than hidden.** Wave-14 slice 1.5, inserted and user-ratified 2026-07-30 (roadmap
Part 4 rule 3). Sizing **M**. **No new governed family, no new entity, no migration, no permission,
no audit code.** Every number this slice produces is a **dated reading**, re-measured if cited later
(the P4 binding clause).

The roadmap's charge: *"Generate a synthetic 5–10k-position, multi-year book through the capture
rails in its own tenant; run the exposure → factor → covariance → VaR → perf chain end-to-end;
record MEASURED wall-clock/memory ceilings against OD-046/NFR-05. AD-003 accepted the
Python-batch/Decimal-grain performance risk with a revisit trigger only a measurement can fire —
nothing beyond a 3-instrument demo book has ever executed, and a grain-level fix later touches every
governed family, so the probe lands BEFORE further kernel families ship."*

---

## Part 0 — The facts that shape the slice (measured on `main` at `19fb4f7`, 2026-07-30)

1. **NFR-05 is UNQUANTIFIED on the batch side.** `architecture_baseline.md:133` reads: *"Daily
   full-portfolio risk batch within overnight window; interactive queries < 3s p95."* The read-side
   half carries a number; the batch half does not — "overnight window" is a phrase, not a budget.
   **AD-003's revisit trigger is "Performance NFR-05 not met"** (`foundational_adrs.md:36-37`).
   A measurement cannot fire that trigger while there is no number to miss. **This is the slice's
   central problem, and it is a decision, not an implementation detail** (OQ-PERF-0-1).
2. **No timing instrumentation exists anywhere.** A broad grep
   (`perf_counter|process_time|monotonic()|elapsed|duration_ms|timeit`) over
   `packages/shared-python/src` + `apps/backend/src` returns only two hits, and BOTH are the English
   word "elapsed" in `pacing` docstrings about annual periods — no instrumentation. The harness is
   net-new, and there is no house convention for it to follow.
3. **There is no bulk-write path.** No `executemany` / `bulk_save_objects` / `bulk_insert_mappings`
   anywhere in `irp_shared`. Every capture write is a per-row ORM call, and governed writes emit an
   audit event co-transactionally to the FROZEN `record_event`. **Seeding is therefore itself a
   scale question**, not test scaffolding (OQ-PERF-0-5).
4. **A synthetic package ALREADY EXISTS** (`irp_shared/synthetic`, P1C-6): a reserved
   `SYNTHETIC_TENANT_ID`, deterministic `uuid5` ids + a fixed `SeedClock` (**wall-clock and `random`
   are AST-FENCED out**), an explicit-confirmation + non-production env gate, and a hard refusal to
   write to any other tenant. It is **capture-only by declared contract**: *"it computes nothing (no
   market value / exposure)"*. But `builder.py` is a **FIXED hand-written dataset** (three accounts,
   a handful of transactions and valuations, 400 lines) — **not scale-parameterized**. PERF-0 reuses
   the tenant, the id discipline and the env gate; it must ADD the scale generator (OQ-PERF-0-2).
5. **A shipped fence forbids importing it.** `test_synthetic.py:331` asserts no module imports
   `irp_shared.synthetic` ("it is leaf tooling"). A perf harness that imports it **trips that
   fence** — which must be amended IN PLACE WITH ITS RATIONALE, never silently (the CON-1
   precedent, where three fences were amended with the reason written at the fence).
6. **Nothing beyond a 3-instrument demo book has ever executed.** The largest book in the repo is
   the CON-1 `DEMO-CONCENTRATION` coverage book. The full-PG battery (2,776 tests) runs in minutes
   because every fixture is tiny. **We currently have no evidence of behaviour at any scale.**
7. **The chain's history requirement sits at the FACTOR level, not the position level.** VERIFIED:
   `risk/covariance_service.py` builds a `COVARIANCE_INPUT` snapshot pinning *"the `factor` EV
   definitions + the aligned `factor_return`"* series (its own module docstring), consuming
   `COMPONENT_KIND_FACTOR_RETURN`; position-level `valuation` rows are consumed by exposure at the
   measurement date. This distinction is what makes a multi-year book affordable (OQ-PERF-0-2) — it
   is a methodological fact, not a shortcut.

---

## Part 1 — The decision ledger (ratify at this gate)

### OQ-PERF-0-1 — Quantify NFR-05's batch budget. **THE decision of this slice.**

**RATIFIED 2026-07-30: YES — the number is set BEFORE the probe runs.**

A probe that produces readings against no budget produces numbers nobody can fail, and AD-003's
revisit trigger stays permanently unfirable — which is precisely the state the roadmap inserted
PERF-0 to end. Measuring first and choosing the line afterwards is also the weaker order: the line
becomes whatever we happened to measure.

**THE RATIFIED BUDGET:** for a **10,000-position book**, the daily full-portfolio risk
batch (exposure → factor exposure → covariance → VaR → portfolio return → concentration) completes
within **4 clock-hours** on a single commodity worker, leaving margin inside a conventional
overnight window for retries, ingestion and reporting. The read-side `< 3s p95` already in NFR-05 is
unchanged and out of this slice's scope.

**Consequence, stated plainly:** if the measured batch exceeds the ratified budget, **AD-003's
revisit trigger FIRES** and that is a recorded decision point for the user (OQ-PERF-0-8) — not an
automatic remediation slice.

### OQ-PERF-0-2 — The book's shape (the cost fork)

**RATIFIED 2026-07-30: month-end position marks across the multi-year span + DAILY factor
returns**, over a THREE-year span.

Naive reading of "multi-year, 5–10k positions" implies daily marks: 10,000 × ~750 business days ≈
**7.5M `valuation` rows**, each a per-row ORM write with an audit event (Part 0 fact 3). That seed
would dominate the slice and measure the seeder, not the chain.

The economical shape is also the methodologically correct one (Part 0 fact 7):

- **Positions/valuations:** month-end marks over 3 years ≈ 36 dates → ~360k valuation rows at the
  10k point. Still substantial, and deliberately so — this is the ingestion number we want.
- **Factor returns:** DAILY over the same span, but factors are few (tens of series), so the row
  count is trivial while the kernels get realistic observation counts.
- **The measurement date:** one chosen boundary date, explicitly selected (never "latest COMPLETED"
  — the OQ-CON-1-20 discipline).

### OQ-PERF-0-3 — A LADDER, not a point

**Recommend: measure at 500 / 2,000 / 5,000 / 10,000 positions.**

A single 10k reading cannot distinguish "slow but linear" from "quadratic and fine at 10k, fatal at
50k". The growth exponent is the actionable output — it is what tells us whether the Decimal/ORM
grain is a tuning problem or a design problem, which is exactly what AD-003 deferred. The ladder
costs little beyond the largest point and converts a number into a diagnosis.

### OQ-PERF-0-4 — Where the harness lives, and what runs in CI

**Recommend: a standalone harness that app code never imports, with the SMALLEST rung wired into CI.**

The CON-1 lesson is that unexecuted machinery rots (its P0001 trigger shipped un-executed; three
lanes read past it). A perf harness that only ever runs by hand will be broken the next time anyone
reaches for it. **CI runs the 500-position rung** as a correctness smoke — it proves the harness
still drives the chain end-to-end — and **asserts NO timing budget** (CI runners are noisy shared
hardware; a wall-clock assertion there would be a flaky gate that teaches people to ignore it).
The full ladder runs locally; its numbers are dated readings recorded in the artifact.

### OQ-PERF-0-5 — Seed time is a REPORTED number, not scaffolding

**Recommend: record seed wall-clock separately from compute wall-clock, per rung.**

Given Part 0 fact 3, "how long does it take to onboard a 10k-position book through the governed
capture rails?" is a genuine operational answer this probe gets for free. Reporting it separately
keeps it from contaminating the batch number the budget applies to.

### OQ-PERF-0-6 — Chain segments, timed individually

**Recommend: exposure → factor exposure → covariance → VaR → portfolio return → CONCENTRATION**, each
segment timed and reported on its own line.

Concentration (CON-1, ENT-069) closed 2026-07-30, AFTER the roadmap row naming this chain was
written; including it costs nothing and it is now a shipped governed family. A single end-to-end
number would hide which segment owns the time, and attribution is the point.

### OQ-PERF-0-7 — How memory is measured

**Recommend: `tracemalloc` peak (Python allocations) + peak RSS via `resource.getrusage`, per segment.**

The two answer different questions (interpreter-level growth vs the number an operator provisions
against) and disagreeing readings are themselves informative.

### OQ-PERF-0-8 — What happens when a reading misses the budget

**Recommend: RECORD and ESCALATE; never auto-remediate.**

If a rung exceeds the OQ-PERF-0-1 budget, PERF-0 records the reading, states that AD-003's revisit
trigger has fired, and surfaces it as a decision point. Choosing the response (vectorization, a
grain change, a different execution model) is a new slice and the user's call — and a grain-level
fix touches every governed family, which is exactly why the roadmap put this probe first.

### OQ-PERF-0-9 — Timing must NOT breach the synthetic package's determinism fence

**Recommend: all timing lives OUTSIDE the fenced seed code.**

`irp_shared/synthetic` is AST-fenced against wall-clock and `random` so its output is reproducible.
A naive harness would put `perf_counter()` inside the seeder and break that guarantee. The harness
therefore **wraps** the seed calls and times them from outside; the fenced modules stay
wall-clock-free. This is a real trap, named here so the implementation cannot walk into it.

### OQ-PERF-0-10 — PERF-0 gets its OWN reserved tenant. **REVERSED at first implementation contact.**

**Originally recommended: reuse `SYNTHETIC_TENANT_ID`. REVERSED 2026-07-30 — reuse would corrupt a
shipped guard.**

`test_synthetic_pg.py` connects as the constrained `irp_app` role (NOSUPERUSER, **NOBYPASSRLS**)
with the tenant context set to `SYNTHETIC_TENANT_ID`, then asserts
`count(Position) == 6`. That count is **RLS-SCOPED to the synthetic tenant** — it is not a global
count that happens to be small. Seeding 500–10,000 perf positions into that tenant turns 6 into
506…10,006 and breaks the assertion; "fixing" it by relaxing the number would permanently destroy
the precision of the synthetic dataset's exact-count guards, which are valuable *because* they are
exact.

Reading matters here: the roadmap's own words are *"in its own tenant"*, which I had over-read as
"any non-production tenant". It means what it says.

**RESOLVED: a second reserved tenant, `PERF_TENANT_ID = synthetic_id("tenant:perf-probe")`**, with
the same discipline as the synthetic one — deterministic `uuid5`, the fixed `SeedClock`, an explicit
confirmation argument, a non-production env gate, and an EXACT-tenant refusal so the perf seed can
never write to the synthetic tenant (or any other) and the synthetic seed can never write to the
perf tenant. The two seeds are mutually exclusive by construction, so neither can pollute the
other's counts.

**Consequent contract change, recorded rather than discovered later:** the `synthetic` package's
docstring states it *"can only ever write to the SYNTHETIC tenant"*. Hosting the perf generator
there makes the package **deterministic seed tooling with TWO reserved tenants, each refusing the
other's**. The package docstring and `build_synthetic_dataset`'s docstring are amended to say
exactly that.

### OQ-PERF-0-11 — The AST fences must become a package CENSUS (found in the same pass)

**Recommend: replace the enumerated `_SYN_MODULES` with a census over the package.**

`test_synthetic.py:43` reads `_SYN_MODULES = (ids_mod, builder_mod)` — an ENUMERATED tuple. All
three AST fences (no wall-clock/`random`, no arithmetic, no raw SQL / BYPASSRLS) iterate it, so **a
new module added to `irp_shared/synthetic/` silently escapes every one of them.** PERF-0 is about to
add exactly such a module. Enumerate-vs-census is the CON-1 lesson (`SNAPSHOT_COMPONENT_KINDS`
membership asserts could not see an added kind); the fix is the same shape: glob the package's
modules and fence whatever is found, so the NEXT module cannot escape either.

The scale generator is written to PASS the existing fences unchanged — in particular **no
multiplication**, which the no-compute fence forbids outright. Deterministic quantities and marks
come from fixed value tables indexed by position, never from `i * step`. The fence stays a real
constraint rather than being widened to accommodate new code.

---

## Part 2 — The artifact

A dated readings table, per rung and per segment: seed wall-clock, compute wall-clock, `tracemalloc`
peak, peak RSS, row counts, and the derived growth exponent between rungs. Each reading carries the
date, the host's shape (cores/RAM), the PostgreSQL version, and the commit measured — **a reading
without its conditions is not evidence** (the OPS-H1 "measured beats cited" lesson).

---

## Part 3 — Implementation shape (as PLANNED; Part 9 records what SHIPPED)

- A scale generator extending the synthetic package's deterministic id + seed-clock discipline
  (`uuid5`, `SeedClock`) to N positions — parameterized, never wall-clock or `random`.
- A harness that seeds a rung, then drives each chain segment through its SHIPPED binder (never a
  reimplementation — the number must describe the code that actually runs), timing from outside.
- The `test_synthetic.py:331` import fence AMENDED IN PLACE with its rationale.
- The CI smoke at the smallest rung, with NO timing assertion.
- The readings artifact, dated, with conditions recorded.

## Part 4 — Sizing

**M.** No migration, no entity, no permission, no audit code, no governed family. The weight is in
the generator's determinism and in honest measurement conditions, not in schema.

## Part 5 — Pre-flight manifest consulted (P7 companion)

Change classes touched: **none of** new migration / new governed family / new permission / new
entity. Closest classes are **new demo-stage-like tooling** (stage-ordering and count-pin relays do
NOT apply — this is not a demo stage and adds no demo counts) and **test-fence amendment** (the
synthetic import fence, Part 0 fact 5). Pins verified as NOT applicable: migration-head population,
`HYBRID_TABLES` parity, `APPEND_ONLY_TABLES`, `FAMILY_REGISTRY`, DDL identifier lengths, the
seven-ledger sweep (no ledger-bearing artifact is minted).

> **CORRECTED at the Wave-14 close (2026-08-03).** Dismissing the **whole** seven-ledger sweep on
> the grounds that "no ledger-bearing artifact is minted" is wrong, and the reasoning only ever
> covered ledgers **1–3** (ENT registry, audit taxonomy, control matrix). Ledgers **4–7** are not
> artifact-gated: (4) `current_state.md` CURRENT TRUTH, (5) the requirements backbone + RTM, (6)
> MEASURED counts, and above all **(7) the record's OWN delivery claims — every "shipped /
> enforced / delivered / implemented" claim verified against the MERGED diff and cited to its
> artifact.** Ledger 7 applies to EVERY slice that makes delivery claims, which is every slice.
>
> This is not a technicality: the Wave-14 close found **exactly the defects ledger 7 exists to
> catch** in this slice's own record — the Reading-1 erratum that corrected a number and then
> asserted nothing depended on it (see the erratum-to-the-erratum in `perf_0_readings.md`), and
> F2's fix, whose record sentence quantified over six segments while the fix touched two, the
> erratum's own segment among the four omitted (now standing rule **P10**). A slice that mints no
> entity can still ship a false record, and the sweep was declared inapplicable precisely where it
> would have bitten.

---

## Part 9 — Execution addendum (2026-07-31, written BEFORE the pre-closeout review)

What actually shipped against what was ratified. Written now so the review's record-vs-diff lane
audits real claims rather than staleness.

**Branch `perf-0-planning`, head `e9e5cbd`.** CI green at head — NOT at every commit: impl 4/n
pushed red (the two-layer marketdata fence miss, recorded below), and the earlier phrasing of this
sentence claimed otherwise in the same document that records the red push (caught by the 2026-08-01
review as a self-contradiction). Both tiers run before every push after impl 5/n. No governed family, no entity, no migration, no
permission, no audit code — the sizing held.

### Delivered

| ratified | shipped | artifact |
|---|---|---|
| OQ-1 — 4 h budget @10k, set before measuring | as ratified; **MEASURED at 21.4 min = 8.90%** | Reading 5 |
| OQ-2 — month-end marks + daily factor returns, 3 y | as ratified | `scale.py` |
| OQ-3 — a LADDER, not a point | 500 / 2,000 / 10,000 (**5,000 skipped**, below) | Readings 1–5 |
| OQ-4 — harness outside app code, smallest rung in CI, no timing assertion | **DEVIATED, recorded late (review F1):** the ratified text says "CI runs the 500-position rung"; the shipped smoke runs rung THREE. The shrink was the right call (500 positions seed for minutes in CI) but went unrecorded — and it silently vacated the multi-portfolio guard, because 3 positions at 250-per-portfolio is ONE portfolio. Fixed at the fold: the seed's packing is parameterized, the smoke seeds 2-per-portfolio, and the portfolio count is ASSERTED in-test | `scripts/perf_probe.py`, `test_perf_probe_pg.py`, `ci.yml` |
| OQ-5 — seed time reported separately | as ratified, and it became the headline finding | all readings |
| OQ-6 — six segments, timed individually | as ratified | Reading 4/5 tables |
| OQ-7 — tracemalloc + peak RSS | as ratified (`ru_maxrss` branches on platform — bytes vs KB) | `_peak_rss_mb` |
| OQ-8 — a miss RECORDS and ESCALATES | never exercised: **no miss occurred** | — |
| OQ-9 — timing OUTSIDE the fenced seed | as ratified | harness lives in `scripts/` |

### Deviations, each recorded where it happened

- **OQ-10 REVERSED at first implementation contact** — reuse of the SYNTHETIC tenant would have
  broken `test_synthetic_pg.py`'s RLS-scoped `count(Position) == 6` and destroyed the precision of a
  guard whose value is being exact. PERF-0 got its own reserved `PERF_TENANT_ID`. Recorded in Part 1.
- **OQ-11 ADDED mid-slice** — the AST fences iterated an ENUMERATED module tuple, so a new module
  escaped all three. Replaced with a package census; mutation-proven.
- **5,000 rung SKIPPED, deliberately.** Three rungs establish the exponent and 10,000 is the ratified
  budget point. Stated rather than silently omitted (the no-silent-caps rule).
- **Determinism is NOT universal — and the count is THREE shapes, not two** (widened at the
  2026-08-01 review, F3). `create_legal_entity`/`create_issuer` mint their own ids with no
  `entity_id` hook, and the per-run-random issuer id is then written INTO `instrument.issuer_id`,
  so instrument rows are not byte-identical either (classification rows under `classify=True` also
  sit outside the guarantee). Affects no measurement — issuer grouping MEMBERSHIP is ordinal-keyed —
  but the caveat as first recorded was itself incomplete, which is the exact failure the caveat
  exists to prevent.

### The 2026-08-01 post-review fold (three Fable lanes, 26 findings; all four headline verdicts ADJUDICATED AS STANDING)

The review's full adjudication: budget 8.90% recomputes exactly (one-date daily ≈ 6.74%);
ingestion-dominates 10.87× (→ ~14.4× one-date); capture linear (1.005/0.974/0.990); memory flat.
The defects were in the probe's own guard layer, and the two that mattered are the SAME classes
this slice had already paid for once:

- **F1 (HIGH): the CI smoke's two-portfolio claim was FALSE** — rung 3 at the default packing is
  ONE portfolio, so the multi-portfolio regression guard was vacuous and its comment described a
  protection the test did not provide. Fixed: `positions_per_portfolio` parameterized (sole
  consumer: the smoke, at 2), and `count(portfolio) >= 2` asserted IN CODE. Mutation-proven: the
  old packing fails exactly that assertion.
- **F2 (HIGH): the smoke's "all six COMPLETED" docstring checked 3 of 6 run types** —
  VAR/PORTFOLIO_RETURN/FACTOR_EXPOSURE were never status-checked while their binders document
  commit-FAILED-and-return contracts (the Reading-3 mechanism, recreated in the slice that fixed
  it). Fixed: an EXACT six-family run-type census + a zero-non-COMPLETED assertion, and the
  harness now folds every returned status into `SegmentReading.ok`. Negative control executed: a
  planted FAILED run is caught by the census query.
- F3: the determinism caveat widened to three shapes (above). F4: the Reading-1 totals erratum
  (in the readings). F5: **PR #154 merged only this record's planning version — the implementation
  was never merged**; this fold rides the implementation PR itself, so the review is pre-merge
  after all.

Named PERF-1 carries (designed-in, not rediscovered): measure the audit-chain share of the
~36 ms/row BEFORE parallelizing (within-tenant parallelism may serialize on the chain and yield
~0); define the write-count basis in the harness (the 27.4 rows/s counts six families and excludes
~3.5% of inserted rows); status census, never throw-based ok; every regression guard asserts its
precondition in code.

### Corrections to this slice's own outputs

- **Reading 3's concentration row measured the FAILURE path.** The seed created issuer-less
  instruments, so concentration's always-computed ISSUER dimension gapped and committed a FAILED
  run; CON-1 commits rather than raises, and the harness only notices a throw. Found by the CI
  smoke's database-reading test ~20 minutes after Reading 3 was filed. Fixed (issuers seeded);
  Reading 4 supersedes. Impact was ~3% — the gap fires after bucketing completes — so the
  conclusions survived, which was luck, not method.
- **A seed projection of mine was wrong.** Reading 4 called ~3.7 h "conservative" and ~2.6 h the
  better estimate from the 0.808 exponent. Measured: **3.87 h**, exponent **1.033** over
  2,000→10,000. The conservative figure was nearly exact.

### Process failures in this slice, named

- **The both-tier-before-push rule lapsed once** (impl 4/n → red CI). CI's Backend job runs bare
  `pytest` — the UNIT tier — while every battery I had run set `IRP_TEST_DATABASE_URL`. I was
  verifying a superset and assuming it covered the subset. Countermeasure: a new pre-flight manifest
  change class for cross-package imports, naming BOTH fence layers.
- **Three fences fired on my own code** (raw-SQL `.execute`, the synthetic import direction, the
  repo-wide marketdata leaf fence). Each was answered by conforming to an existing convention or by
  amending in place with the reason AT the fence — none by widening a fence to fit new code.

### What PERF-0 does NOT answer

**Concurrency.** Every reading is single-process, single-connection. The finding points at ingestion
throughput, and the first question any ingestion work would ask is what parallel writers do to
~27 rows/s — a per-tenant hash-chained audit append is exactly the kind of thing that may not
parallelise. That is a NEW slice's question, not a gap in this one, and it is the natural PERF-1.
