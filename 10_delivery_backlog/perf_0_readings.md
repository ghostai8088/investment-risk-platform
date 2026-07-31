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

## Reading 2 — the DAILY BATCH, per segment (2026-07-30)

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
