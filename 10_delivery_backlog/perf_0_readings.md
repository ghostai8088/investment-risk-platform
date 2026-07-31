# PERF-0 — measured readings

> **Every number here is a DATED READING under stated conditions, not a pin.** If one is cited
> later it is RE-MEASURED first (the P4 binding clause). A reading without its conditions is not
> evidence (the OPS-H1 "measured beats cited" lesson), so the conditions are recorded beside it.

---

## Reading 1 — capture-rail seed throughput (2026-07-30)

**Conditions.** Apple M1 Max, 10 cores, 64 GB RAM. PostgreSQL 16.14 (Debian) in the local
`irp_pg_local` container. Python 3.13.0. Commit `50bc131`. **Fresh schema per rung** (`DROP SCHEMA` +
`alembic upgrade head`), performed OUTSIDE the timed region — the times below are pure seed cost.
Single process, single connection, no concurrency. Book shape as ratified at OQ-PERF-0-2: 36
month-end marks per position over three years.

| rung (positions) | valuation rows | total rows | seed wall-clock | ms / position | governed rows / s |
|---:|---:|---:|---:|---:|---:|
| 50 | 1,800 | ~1,901 | 34.45 s | 688.9 | 55 |
| 200 | 7,200 | ~7,401 | 138.70 s | 693.5 | 55 |
| 800 | 28,800 | ~29,604 | 535.49 s | 669.4 | 57 |

### What it says

**The capture rail is LINEAR in book size.** Log-log slope between rungs: 1.005 (50→200), 0.974
(200→800), **0.990 overall across a 16× range**. Throughput is flat at **~55–57 governed rows per
second**. This is the single most useful thing the probe has produced so far, and it is *good* news
about the shape: AD-003's deferred worry was that the Python/Decimal/per-row-ORM grain might be
superlinear, in which case a book ten times larger would cost far more than ten times as much. It
does not. **A scale problem here is a throughput-constant problem, not an architecture-shape
problem** — and constants are far cheaper to fix than shapes.

**The constant itself is slow.** ~55 rows/s is ~18 ms per governed write against a local PostgreSQL
on fast hardware. Each governed write is an ORM insert PLUS a co-transactional audit event on a
per-tenant HASH CHAIN, and a hash chain is inherently sequential — each event's hash depends on its
predecessor, so the writes cannot be batched or parallelised without changing that design. This is a
hypothesis consistent with the reading, **not yet a measured attribution**; isolating it needs
per-segment instrumentation, which is the next piece of work.

### Extrapolations (DERIVED, not measured — flagged as such)

At the measured 0.669 s/position and an exponent of ~1.0:

| rung | rows | extrapolated seed time |
|---:|---:|---:|
| 2,000 | 74,000 | 0.37 h |
| 5,000 | 185,000 | 0.93 h |
| 10,000 | 370,000 | **1.86 h** |

**Seeding the ratified 10,000-position book takes roughly two hours.** That is tractable for a
probe, and it is also a real operational answer in its own right (OQ-PERF-0-5): *onboarding* a
10k-position book with three years of month-end history through the governed capture rails is a
~2-hour job as the platform stands.

### What this reading does NOT say

**It says nothing about the ratified 4-hour batch budget.** That budget (OQ-PERF-0-1) applies to the
DAILY RISK BATCH — exposure → factor exposure → covariance → VaR → portfolio return → concentration
— which is compute over an already-seeded book. Seeding is one-time onboarding, not the nightly run,
and its cost does not consume the batch budget. **The batch has not been measured yet.** Nothing
here fires or clears AD-003's revisit trigger.

It also says nothing about memory: `tracemalloc`/RSS instrumentation (OQ-PERF-0-7) is not yet built.

---

## Pending readings

- The 5,000 and 10,000 rungs (Reading 2 covers 500 and 2,000).
- `portfolio_return` and `concentration`, once the harness defect and the classification seed are
  fixed — until then every batch total is a LOWER BOUND.
- The same ladder under the CI runner's shape, for the record (no timing assertion there —
  OQ-PERF-0-4).

---

## Reading 2 — the daily batch, FOUR of six segments (2026-07-30) — SUPERSEDED by Reading 3

> Kept because its degradation analysis stands and Reading 3 relies on it. Its batch
> totals were LOWER BOUNDS (`portfolio_return` and `concentration` did not run) and are
> superseded below.

**Conditions.** As Reading 1 (M1 Max / 10 cores / 64 GB, PostgreSQL 16.14, Python 3.13.0), commit
`2e25958`, fresh schema per rung, resets outside the timed region. 8 factors × 260 daily returns,
held CONSTANT across rungs. Harness: `scripts/perf_probe.py`, driving the SHIPPED binders.

| rung | seed | seed rows | **batch** | exposure | factor_exposure | covariance | var |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 | 746.81 s | 21,090 | **50.75 s** | 31.62 s | 4.77 s | 10.36 s | 4.00 s |
| 2,000 | 2,604.00 s | 78,096 | **172.93 s** | 125.05 s | 22.86 s | 10.79 s | 14.23 s |

Peak `tracemalloc` never exceeded 35 MB; peak RSS 164 MB at the 2,000 rung.

**Only FOUR of six segments are in that batch total.** `portfolio_return` and `concentration` did
not run (below). The batch number is therefore a LOWER BOUND, and is labelled as one wherever it
is used.

### The degradation hypothesis is REFUTED

Reading 1 measured ~55 governed rows/s; this ladder's seed ran at 28.2 (rung 500) and 30.0 (rung
2,000). I flagged the gap and named the possibility that would have mattered: **per-tenant audit
chain appends degrading as the chain lengthens**, which would make the capture rail superlinear and
overturn Reading 1.

**It does not degrade.** Across a 4× increase in book size — and a chain 3.7× longer — throughput
held flat and in fact improved slightly (28.2 → 30.0 rows/s); the seed's growth exponent is
**0.901**, sublinear. The gap against Reading 1 is workload MIX and host conditions, not
degradation: this seed additionally writes factors, factor returns and currencies, and the two
ladders ran under different machine load. **The two ladders' rows/s are therefore NOT directly
comparable** — but the within-ladder comparison, which is the one that tests degradation, is clean.

### Growth exponents (log-log, 500 → 2,000)

| segment | exponent | reading |
|---|---:|---|
| exposure | 0.992 | linear, and the DOMINANT cost (72% of batch at 2,000) |
| factor_exposure | 1.130 | mildly SUPERLINEAR — the one to watch |
| covariance | 0.029 | FLAT — as it should be (see below) |
| var | 0.915 | linear |
| **batch total** | **0.884** | sublinear |

**Covariance being flat is a correctness signal, not an anomaly.** It consumes factor RETURN series,
not position marks, and this ladder holds factors constant at 8 — so its cost must not move with
book size, and it doesn't (10.36 s → 10.79 s). That is the harness demonstrating it measures what
the record says the chain consumes (Part 0 fact 7). A book that also grew its factor count would
move this number; that is a different probe.

### Against the ratified budget (OQ-PERF-0-1: 4 clock-hours @ 10,000 positions)

Linear extrapolation of the four measured segments to 10,000 positions gives **~14.4 minutes** —
roughly 6% of the budget. **DERIVED, not measured**, and a LOWER BOUND on two counts: two segments
are missing, and `factor_exposure`'s 1.130 exponent means it grows faster than the extrapolation
assumes.

**AD-003's revisit trigger has NOT fired.** On the evidence so far the daily batch sits far inside
the ratified window, and the platform's cost is dominated by the one-time SEED (~2 h at 10,000
positions, Reading 1) rather than by the nightly run. Nothing here licenses closing the question:
the 5,000 and 10,000 rungs are unmeasured, and so are two segments.

### The two segments that did not run — recorded, never skipped

- **`portfolio_return`** refuses a multi-portfolio atom set: *"the pinned atoms span 2 portfolios —
  v1 measures a SINGLE portfolio."* A HARNESS defect: it passes every portfolio's exposure runs into
  one call. Invisible at the 20-position smoke, where the whole book fit in one portfolio — the
  ladder is what exposed it. Fix: invoke per portfolio.
- **`concentration`** needs a classification scheme and assignments seeded (CON-1's inputs). Not yet
  built into the scale seed.


---

## Reading 3 — all six segments, but concentration on its FAILURE path (2026-07-30) — SUPERSEDED by Reading 4

> Its concentration row measured a FAILED run (see the correction at the end of this section).
> Reading 4 re-measures the same rungs with every segment COMPLETING. Kept for the record.

**Conditions.** M1 Max / 10 cores / 64 GB; PostgreSQL 16.14; Python 3.13.0; commit `5bf8da9`;
fresh schema per rung, resets outside the timed region; 8 factors × 260 daily returns held constant
across rungs; single process, single connection. Harness `scripts/perf_probe.py` driving the
SHIPPED binders.

| rung | seed | seed rows | **batch (all 6)** |
|---:|---:|---:|---:|
| 500 | 835.14 s | 21,090 | **76.66 s** |
| 2,000 | 2,858.49 s | 78,096 | **269.65 s** |

| segment | 500 | 2,000 | exponent | reading |
|---|---:|---:|---:|---|
| exposure | 32.92 s | 129.53 s | 0.988 | linear; **48% of the batch** — the dominant cost |
| concentration | 15.86 s | 66.81 s | 1.037 | ⚠️ **MEASURED THE FAILURE PATH — see the correction below** |
| factor_exposure | 6.08 s | 22.78 s | 0.953 | linear |
| portfolio_return | 7.06 s | 25.64 s | 0.930 | linear |
| var | 3.09 s | 14.12 s | 1.096 | mildly superlinear |
| covariance | 11.64 s | 10.78 s | −0.055 | FLAT — correct (factors held constant) |
| **batch total** | **76.66 s** | **269.65 s** | **0.907** | **sublinear** |
| seed | 835.14 s | 2,858.49 s | 0.888 | sublinear |

Peak `tracemalloc` never exceeded 12 MB; peak RSS 118 MB at the 2,000 rung. **Memory is not a
constraint at this scale** and shows no growth trend across a 4× book.

### Against the ratified budget (OQ-PERF-0-1: 4 clock-hours @ 10,000 positions)

Extrapolated to 10,000 positions — **DERIVED, not measured**:

- at the measured exponent 0.907: **~19.4 minutes (8% of budget)**
- at a conservative linear 1.000: **~22.5 minutes (9% of budget)**

**AD-003's revisit trigger has NOT fired.** The daily full-portfolio risk batch completes in roughly
a tenth of the ratified window, and every segment is linear or sublinear except `var` (1.096) and
`concentration` (1.037), both close enough to 1.0 that they change nothing at this scale.

**The finding that matters is where the cost actually is.** It is NOT the nightly batch: it is the
one-time SEED, ~2 h at 10,000 positions (Reading 1/2), which is ~6× the entire batch's projected
cost and is dominated by per-row capture writes with co-transactional audit-chain appends. If
anything about this platform's performance deserves engineering attention, the measurement points
at INGESTION, not at risk compute. That is the opposite of what AD-003's "Python batch performance"
risk anticipated, and it is the kind of thing only a measurement could establish.

### What is still NOT measured

The 5,000 and 10,000 rungs (~1 h and ~2 h of seeding respectively) — every 10k number above is an
extrapolation from 2,000, and `var`'s and `concentration`'s slightly-superlinear exponents are
exactly the sort that compound beyond the measured range. The probe has NOT been run under the CI
runner's shape.


### CORRECTION to Reading 3 — the concentration timings measured a FAILED run

Found immediately after Reading 3 was filed, by the CI smoke's second test — the one that reads the
DATABASE rather than trusting the harness's own account of itself.

**The harness reported `concentration` as `ok`, and no COMPLETED concentration run existed.** CON-1's
contract is that a coverage gap commits a **FAILED** run with zero rows rather than raising, so the
harness — which records a segment as failed only when it throws — saw success. The cause: the scale
seed created instruments with **no issuer**, and concentration ALWAYS computes an ISSUER dimension,
so every atom was UNCLASSIFIABLE → `ALL_UNCLASSIFIABLE` gap → FAILED run.

**Consequence for the numbers.** Reading 3's `concentration` figures (15.86 s / 66.81 s, exponent
1.037, "25% of the batch") describe the FAILURE path: bucketing runs, the gap fires, rows are
discarded. That path does real work, so the numbers are not nonsense — but they are NOT the cost of
a completing concentration run and must not be cited as such. **The other five segments are
unaffected**, and the batch total is now a LOWER bound for a different reason than before.

**Fixed** by seeding issuers (one per 5 instruments, so the dimension is both classifiable and
meaningful rather than one bucket per position). Both CI smoke tests now pass with a COMPLETED
concentration run. **Reading 3's batch totals need re-measuring at 500/2,000 before they can be
called complete.**

**Why this survived to be filed at all:** every prior check asked the harness whether the segment
ran. Only a check that asked the DATABASE what was written could see the difference between "did
not throw" and "produced a governed number" — the same distinction that separates a fail-closed
control from a vacuous one.


---

## Reading 4 — the CORRECTED complete batch, all six segments COMPLETING (2026-07-31)

**Supersedes Reading 3.** Same rungs and parameters; the difference is that the seed now creates
issuers, so concentration's always-computed ISSUER dimension is classifiable and the segment mints a
COMPLETED run instead of a gapped FAILED one.

**Conditions.** M1 Max / 10 cores / 64 GB; PostgreSQL 16.14; Python 3.13.0; commit `435bcf8`; fresh
schema per rung, resets outside the timed region; 8 factors × 260 daily returns held constant;
single process, single connection; harness `scripts/perf_probe.py` driving the SHIPPED binders.

| rung | seed | seed rows | **batch (all 6 COMPLETING)** |
|---:|---:|---:|---:|
| 500 | 862.40 s | 21,090 | **77.02 s** |
| 2,000 | 2,642.61 s | 78,096 | **278.70 s** |

| segment | 500 | 2,000 | exponent | share @2,000 |
|---|---:|---:|---:|---:|
| exposure | 32.31 s | 129.58 s | 1.002 | **46.5%** |
| concentration | 16.49 s | 68.94 s | 1.032 | **24.7%** |
| portfolio_return | 7.03 s | 26.92 s | 0.969 | 9.7% |
| factor_exposure | 6.39 s | 25.96 s | 1.011 | 9.3% |
| var | 3.49 s | 15.04 s | 1.054 | 5.4% |
| covariance | 11.31 s | 12.27 s | 0.059 | 4.4% |
| **batch total** | **77.02 s** | **278.70 s** | **0.928** | — |
| seed | 862.40 s | 2,642.61 s | 0.808 | — |

Peak `tracemalloc` ≤ 12 MB; peak RSS 119 MB at 2,000. **Memory is not a constraint** and shows no
growth trend across a 4× book.

### What changed versus Reading 3 — and what did not

Concentration moved 15.86 → 16.49 s (500) and 66.81 → 68.94 s (2,000): **about 3% dearer**. The
failure path was nearly as expensive as the success path because the gap fires only AFTER bucketing
is complete — the work happens, then the rows are discarded. So the correction changes what the
number MEANS far more than what it says, and every conclusion drawn from Reading 3's totals survives.
That is a comfortable outcome, not a vindication of filing it: had the gap fired earlier the error
would have been large, and nothing in the harness would have revealed it.

### Against the ratified budget (OQ-PERF-0-1: 4 clock-hours @ 10,000 positions)

DERIVED, not measured:

- at the measured exponent 0.928: **~20.7 minutes (8.6% of budget)**
- at a conservative linear 1.000: **~23.2 minutes (9.7%)**

**AD-003's revisit trigger has NOT fired.** Every segment is linear or sublinear; the largest
exponent is `var` at 1.054, which changes nothing at this scale.

### The finding, now on corrected numbers

**Ingestion dominates, not risk compute.** Extrapolated to 10,000 positions the seed is ~3.7 h
against a ~20-minute batch — a **9.5× ratio**. AD-003 accepted a "Python batch performance" risk;
the measurement says the batch is a non-issue and the cost sits in the per-row capture rail with its
co-transactional audit-chain appends. **The deferred risk was real but pointed at the wrong half of
the system.**

Note the seed's exponent here is **0.808** — markedly sublinear, i.e. per-row cost IMPROVES with
scale (fixed setup amortising, warm caches). The ~3.7 h figure extrapolates linearly and is
therefore a CONSERVATIVE upper bound; at the measured exponent it would be ~2.6 h.

### Still not measured

The 5,000 and 10,000 rungs. Every 10k figure above is extrapolated from 2,000. The probe has not
run under the CI runner's shape (the CI smoke is a correctness gate with no timing assertion).

---

## Reading 5 — the 10,000-position rung, MEASURED at the ratified budget point (2026-07-31)

The budget in OQ-PERF-0-1 was ratified **at 10,000 positions**, and every prior 10k figure in this
document was extrapolated from 2,000. This is the measurement.

**Conditions.** M1 Max / 10 cores / 64 GB; PostgreSQL 16.14; Python 3.13.0; commit `cd190cf`; fresh
schema; single process, single connection; 8 factors × 260 daily returns; harness
`scripts/perf_probe.py` driving the SHIPPED binders.

**Seed 13,938.26 s (3.87 h), 382,128 governed rows. BATCH 1,281.76 s (21.4 min).**

| segment | 2,000 | 10,000 | exponent | share @10k |
|---|---:|---:|---:|---:|
| exposure | 129.58 s | 621.55 s | 0.974 | **48.5%** |
| concentration | 68.94 s | 316.71 s | 0.947 | **24.7%** |
| portfolio_return | 26.92 s | 126.03 s | 0.959 | 9.8% |
| factor_exposure | 25.96 s | 125.63 s | 0.980 | 9.8% |
| var | 15.04 s | 81.33 s | 1.049 | 6.3% |
| covariance | 12.27 s | 10.52 s | −0.096 | 0.8% |
| **batch total** | **278.70 s** | **1,281.76 s** | **0.948** | — |
| seed | 2,642.61 s | 13,938.26 s | **1.033** | — |

Peak `tracemalloc` 11.8 MB; peak RSS 119.1 MB — **essentially unchanged from the 500 rung** across a
20× book. Memory is definitively not a constraint.

### The verdict, now measured

**The daily full-portfolio risk batch completes in 21.4 minutes at 10,000 positions — 8.90% of the
ratified 4-hour budget. AD-003's revisit trigger has NOT fired**, and that statement no longer rests
on an extrapolation. Every segment is linear or sublinear; the largest exponent is `var` at 1.049.

The batch extrapolation held well: predicted 20.7 min (at the measured exponent) to 23.2 min
(linear); **actual 21.4 min**, between the two.

### Where one of my own projections was WRONG

Reading 4 recorded the seed's exponent as **0.808** over 500→2,000 — markedly sublinear — and I
wrote that the ~3.7 h linear figure was therefore "a CONSERVATIVE upper bound; at the measured
exponent it would be ~2.6 h."

**That was wrong. The seed took 3.87 h.** Over 2,000→10,000 the seed's exponent is **1.033** —
slightly SUPERlinear — and throughput fell from 29.6 to 27.4 governed rows/s (−7.2%). The
sublinearity of the small rungs was fixed-cost amortisation, and it did not survive the 5× extension.
**The conservative linear estimate was nearly exact; the "measured exponent" refinement was
optimistic.**

The transferable lesson: an exponent fitted over a 4× range does not license a 5× extrapolation
beyond it, and when the two estimates disagree the CONSERVATIVE one deserves the weight — which is
the reverse of how the more precise-looking number invites you to read it.

### The finding, on measured numbers

**Ingestion dominates risk compute by 10.9×.** Seeding 10,000 positions costs 3.87 h; running the
entire six-segment daily batch over that book costs 21.4 minutes. AD-003 accepted a "Python batch
performance" risk with a revisit trigger; the batch is comfortably inside budget while the per-row
capture rail — ORM insert plus a co-transactional audit-chain append, ~27 rows/s — is where the
platform's time actually goes. **The deferred risk was real and aimed at the wrong half of the
system.** It does not get cheaper at scale: the rail is now measured as flat-to-slightly-worsening.

**This is PERF-0's answer.** If performance work is ever commissioned here, the measurement points
at ingestion throughput, not at the risk kernels.

### Still not measured

The 5,000 rung (skipped deliberately — the exponent is established from three rungs and 10,000 is
the ratified budget point). The probe under the CI runner's shape. Concurrency: every reading is
single-process, single-connection, so nothing here speaks to parallel ingestion, which is the
obvious first question any ingestion work would ask.
