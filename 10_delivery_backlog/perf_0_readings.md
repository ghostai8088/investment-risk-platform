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

- The daily batch, per segment, at each rung — the reading the 4-hour budget is actually about.
- Peak `tracemalloc` and peak RSS per segment.
- The same ladder under the CI runner's shape, for the record (no timing assertion there —
  OQ-PERF-0-4).
