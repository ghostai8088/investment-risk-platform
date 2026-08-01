# Session Log: 31-07-2026 15:34 — con1-fold-merged-perf0-scale-probe

## Quick Reference (for AI scanning)

**Confidence keywords:** CON-1, concentration, review fold, three-lane adversarial review, Fable
verification, OQ-CON-1-24, unfireable refusal, vacuous guard, mixed scheme version, live current
heads, mutation-proven, migration 0057, double-prefixed constraint names, PG truncation 63 chars,
pg_constraint live catalog, ENT-069, PR #152, PR #153, verify-on-main sweep, seven ledgers,
PERF-0, scale probe, NFR-05, AD-003, revisit trigger, 4-hour budget, 10000 rung, ladder,
growth exponent, log-log, capture rail, audit hash chain, ingestion dominates, seed vs batch,
synthetic package, SYNTHETIC_TENANT_ID, PERF_TENANT_ID, AST fence, no-compute fence, ast.Mult,
pkgutil census, import direction fence, test_nothing_imports_marketdata, pre-flight manifest,
both-tier-before-push, red CI, portfolio_return single portfolio, classification seeding, issuers,
tracemalloc, ru_maxrss, CI smoke, no timing assertion, Reading 5, PERF-1 concurrency

**Projects:** investment-risk-platform (Wave 14 — CON-1 slice 1, PERF-0 slice 1.5)

**Outcome:** CON-1 closed and merged (PR #152 + closeout #153) after a three-lane review found a
ratified control that could never fire; PERF-0 built a scale probe from nothing and MEASURED the
answer at 10,000 positions — the daily batch is 21.4 min (8.90% of the ratified 4h budget, AD-003's
trigger NOT fired) while ingestion costs 10.9× more, i.e. the deferred performance risk was aimed at
the wrong half of the system.

---

## Decisions Made

### CON-1

- **Fold the review's BLOCKING as a deliberate STRENGTHENING, not a literal implementation.**
  OQ-CON-1-24(i)'s discriminator was ratified as "among the pinned assignments" — a set filtered to
  the requested `scheme_id`, so it could never hold the second version. Reimplemented over the
  tenant's **LIVE current heads** (`_list_current_assignment_scheme_ids`, no scheme filter). Recorded
  as a deviation from ratified wording rather than silently "fixed".
- **Pinned scheme rows re-recorded as EVIDENCE, not discriminator inputs** — they were ratified to
  make the refusal computable from pinned bytes; that turned out impossible, so the honest role is
  "which taxonomy version produced this number".
- **`coverage_floor` tightened to strictly (0,1]** — a zero floor lets an all-UNCLASSIFIED dimension
  COMPLETE and write immutable 0.000000 summary rows over an empty classified set.
- **DB-level disclosure fence added** (`issuer_id IS NULL OR dimension_kind = 'ISSUER'`) — a
  non-ISSUER row carrying issuer identity was schema-legal and invisible to the `.view` exclusion.
- **CTRL-018 explicitly dispositioned "NO CONTROL MOVED"** rather than left silent (P1 seventh
  ledger requires extend-or-disposition).
- **1/HHI DEFERRED with a trigger** (the first concentration detail view) — v1's FE is a generic runs
  list with no honest home for a derived column.

### PERF-0

- **Quantify NFR-05's batch budget BEFORE measuring — RATIFIED 4 clock-hours @ 10,000 positions.**
  NFR-05's batch half read "within overnight window" (a phrase), so AD-003's "revisit if NFR-05
  unmet" trigger could never fire. Setting the line first prevents it becoming whatever we happened
  to observe.
- **Book shape RATIFIED: month-end position marks over 3 years + DAILY factor returns.** Read
  literally, "5–10k positions, multi-year" means ~7.5M valuation rows and the seed would dominate.
  The economical shape is also the methodologically correct one: covariance/VaR pin FACTOR series
  (verified in `risk/covariance_service.py`), so daily history belongs at the factor level.
- **OQ-PERF-0-10 REVERSED at first implementation contact.** Reuse of the SYNTHETIC tenant would
  break `test_synthetic_pg.py`'s RLS-scoped `count(Position) == 6` and destroy a guard whose value is
  being exact. PERF-0 got its own `PERF_TENANT_ID`, with exact-tenant refusals both directions.
- **A LADDER, not a point** (500/2,000/10,000) — one reading cannot distinguish "slow but linear"
  from "quadratic and fatal later". **5,000 skipped deliberately** and stated (no silent caps).
- **CI smoke = correctness only, NO timing assertion** — CI hardware is noisy; a wall-clock gate
  there would be flaky and teach people to ignore it.
- **A budget miss RECORDS and ESCALATES; never auto-remediate** — a grain-level fix touches every
  governed family, so it is the user's call.
- **Workflows are NOT appropriate for measurement runs** — parallel rungs contend for CPU/IO/DB and
  the numbers become contention artifacts. Reviews of finished artifacts are the workflow case.
- **Two new standing rules added (user request):** every response's last sentence now carries model +
  effort, a **workflows yes/no verdict**, and a **flag for background processes gating the next step**
  (asymmetric — only when there are any).

---

## Key Learnings

### The dominant pattern — three instances in one session

**Asking the artifact (or the component) whether it worked is not verification. Ask the SYSTEM what
is actually there.** Each of these was invisible to careful reading and obvious the moment something
queried the real state:

1. **CON-1's ratified refusal could never fire.** Advertised on four shipped surfaces (builder
   docstring, exception docstring, a pin comment, an API 409 message) while the pinned set it read
   was filtered to exclude the discriminating case. Three independent review lanes converged on it.
2. **Migration 0057's constraint names were corrupt in the database** while both source files read
   correctly. `op.create_table` received FULL names, but the metadata naming convention prepends
   `ck_<table>_` itself → every CHECK landed double-prefixed and the longest was PG-truncated at 63
   chars. All three lanes byte-compared migration text against ORM text and reported parity. Only
   `SELECT conname FROM pg_constraint` exposed it. The tests' `match="summary_shape"` substring
   passed either way, which is what hid it.
3. **The perf harness reported `concentration` healthy while no COMPLETED run existed.** CON-1
   commits a FAILED run on a coverage gap rather than raising; the harness records failure only on a
   throw. So a filed reading had measured the FAILURE path. Caught ~20 min later by the CI smoke's
   database-reading test.

**Countermeasures are now mechanical, not notes:** a live-`pg_constraint`-vs-ORM set-equality test; a
CI smoke that reads `calculation_run` rather than trusting the harness; a pre-flight manifest entry.

### Other transferable learnings

- **An enumerated guard cannot see a new member.** `_SYN_MODULES = (ids, builder)` meant a new
  `scale.py` escaped all three AST fences. Replaced with a `pkgutil` package census and
  **mutation-proven** (a planted `*` now fails the no-compute fence by name). Same shape as CON-1's
  `SNAPSHOT_COMPONENT_KINDS` membership-vs-census lesson.
- **A guard can be vacuous by construction.** My first re-resolve-branch census used `k in source`,
  which every constant name satisfies (it contains its own value). Word-bounding it immediately
  exposed that `PORTFOLIO` dispatches by FALLTHROUGH — now an explicit, grounded exemption.
- **Cross-package imports have TWO fence layers in DIFFERENT files:** the importer's own direction
  test, and the IMPORTED package's repo-wide leaf fence (which lives in the imported package's test
  file). Amending only the first left CI red.
- **A single small smoke hides shape-dependent defects.** `portfolio_return` refuses a
  multi-portfolio atom set; at 20 positions the book fit in ONE portfolio so it passed. The ladder
  exposed it. The CI smoke's rung is now sized to span TWO portfolios deliberately.
- **Do not extrapolate 5× from an exponent fitted over 4×.** Reading 4 measured the seed exponent at
  0.808 (sublinear) and I called ~3.7 h "conservative" and ~2.6 h the better estimate. Measured:
  **3.87 h**, exponent **1.033** over 2,000→10,000. The small rungs' sublinearity was fixed-cost
  amortisation. **When the conservative and refined estimates disagree, weight the conservative one**
  — the reverse of how the sharper number invites you to read it.
- **A fix's blast radius can exceed its apparent size and still be harmless — verify, don't assume.**
  Reading 3's concentration correction moved the numbers only ~3% because the gap fires AFTER
  bucketing completes. That was luck, not method: had it fired earlier the error would have been
  large and nothing in the harness would have shown it.
- **Parallelism destroys a measurement.** Rungs must run sequentially on a quiet machine — which is
  precisely why PERF-0 was not a workflow candidate while its review is.

---

## Solutions & Fixes

### CON-1 review fold (16 files; both tiers green; merged PR #152)

- **The BLOCKING:** implemented the mixed same-family scheme-VERSION refusal over LIVE current heads;
  corrected all four surfaces that had advertised it. **Mutation-proven** — widening the threshold to
  `> 99` reddens exactly the new control and nothing else, confirming it would have been RED against
  the shipped code.
- **The execution-only defect:** migration `0057` switched to SUFFIX-ONLY constraint names (matching
  `0055`'s documented convention); added a PG test reading the live `pg_constraint` catalog and
  asserting set-equality against the ORM plus a ≤63-char check; **re-executed the P4 staged-rows
  destructive proof** on the amended migration.
- **Ten ratified-but-undelivered items delivered**, incl. negative controls for every pre-build
  refusal (they had shipped with none while the record called them "negative-controlled"), the P0001
  append-only trigger executed for the first time, the `SNAPSHOT_COMPONENT_KINDS` set-equality census
  (claimed 3× and never written), the `row_kind` census, and **OQ-REF-1-29's demo role census +
  teardown** (recorded as "paid" by TWO successive slices, built by neither).
- **Fable verification of the fold** confirmed all ten items and REFUTED one sub-claim: the
  compute-zone except tuple omitted `KeyError`/`TypeError`, the archetypal corrupt-JSON shapes.
  Widened before push.
- **P1 verify-on-main sweep** after the merge: all seven ledgers verified against the MERGED diff;
  found one staleness (`current_state.md` still read head `0056` / next-free ENT-069). Merged tree
  proven **byte-identical** to the validated tree (`git diff aa9bdd8 19fb4f7` empty).

### PERF-0 (12 impl commits on `perf-0-planning`)

- `irp_shared/synthetic/scale.py` — deterministic size-parameterized seed: own reserved tenant,
  three-part gate, exact-tenant refusal both ways, **no multiplication** (the no-compute fence forbids
  `ast.Mult`, so quantities/marks come from fixed value TABLES indexed by ordinal).
- `scripts/perf_probe.py` — drives all six segments through the SHIPPED binders; timing lives OUTSIDE
  the wall-clock-fenced package. `ok=False` records a failing segment **with its reason** and keeps
  going, which surfaced every prerequisite in one pass each.
- Prerequisites discovered from the binders' own refusal messages: VaR needs its own registered model
  AND the factor-exposure run id; `portfolio_return` needs two boundary runs and one portfolio;
  `factor_exposure` admits only CURRENCY-family factors each with a DISTINCT currency scope (and a
  fresh tenant owns no currencies); concentration needs a classification scheme; the ISSUER dimension
  needs issuers or it gaps to a FAILED run.
- `test_perf_probe_pg.py` — CI correctness gate importing the REAL harness by path (a copy would pass
  while the harness rotted); registers it in `sys.modules` before exec so dataclass field-type
  resolution works.
- Fence amendments, each **in place with the reason AT the fence**: `marketdata` and `classification`
  added to the synthetic allowed-set; `synthetic` added to the repo-wide marketdata leaf fence riding
  `demo`'s existing precedent ("an ORCHESTRATOR above every domain… nothing imports it").
- `ru_maxrss` branches on platform — **BYTES on macOS, KILOBYTES on Linux** (a silent 1024× error).
- Model registrations excluded from segment timing so they aren't charged to whichever segment runs
  first.

### The measured result (Reading 5, commit `cd190cf`, 10,000 positions)

| | |
|---|---:|
| seed | 13,938.26 s (3.87 h), 382,128 rows |
| **BATCH** | **1,281.76 s (21.4 min) = 8.90% of the ratified 4 h** |
| exposure | 621.55 s (48.5%), exp 0.974 |
| concentration | 316.71 s (24.7%), exp 0.947 |
| portfolio_return | 126.03 s, exp 0.959 |
| factor_exposure | 125.63 s, exp 0.980 |
| var | 81.33 s, exp 1.049 |
| covariance | 10.52 s (0.8%), exp −0.096 (flat by design) |
| batch total exponent | 0.948 |
| seed exponent (2k→10k) | 1.033 |
| peak RSS | 119 MB — unchanged from the 500 rung across a **20× book** |

**AD-003's revisit trigger has NOT fired.** **Ingestion dominates risk compute by 10.9×** — the
per-row capture rail (ORM insert + co-transactional audit-chain append, ~27 rows/s) is where the time
goes, and it does not get cheaper at scale.

---

## Key Exchanges

- **"Is there anything we can do with Opus in the meantime?"** → wrote the PERF-0 execution addendum
  (Part 9) BEFORE the review, so the record-vs-diff lane audits real claims rather than staleness.
  Declined to run the review on Opus: it would duplicate Saturday's work and, worse, replicate the
  very reasoning that produced the defects Fable and execution have been catching.
- **"Can you add two rules?"** → the workflows clause already existed (added 2026-07-13, re-affirmed
  2026-07-14) and I had let it lapse a THIRD time. Recorded as a known recurring failure mode rather
  than restated. The background-process flag is genuinely new and asymmetric by instruction.
- **"CI is showing red"** → root-caused to the second import-fence layer; disclosed plainly that I had
  skipped the full battery and assumed a PG-enabled superset covered the unit tier CI actually runs.
- **"Whether or not workflows should be used"** → no for building interdependent code or for
  measurement runs (parallelism corrupts the numbers); yes for adversarial review of finished
  artifacts, which is where they have demonstrably paid in this repo.

---

## Custom Notes

None

---

## Quick Resume Context

CON-1 is CLOSED and merged (PR #152 + closeout #153); `main` is at migration head `0057`, ENT-070 is
the next free canonical id, demo counts 26/41/136. PERF-0 is IMPLEMENTED and pre-closeout on branch
`perf-0-planning` (head `104a880`, CI green): the scale seed, the six-segment harness, the CI smoke,
five dated readings and a Part 9 execution addendum are all committed. **The slice's answer is
complete and measured** — batch 21.4 min at 10k (8.90% of budget, AD-003 trigger NOT fired), ingestion
10.9× dearer than compute.

**Next:** the three-lane pre-closeout review (measurement validity / determinism + fences /
readings-vs-code) — held for **Fable on Saturday** so lane blind spots differ from mine — then PERF-0
closeout, then LIM-2 (which carries three named CON-1 obligations: the `limit_definition` basis
column, the basis-match refusal, and the refusal-after-success staleness state in `limit_health`).
PERF-1 (ingestion CONCURRENCY — every reading here is single-process/single-connection) is the natural
follow-on the measurement argues for.

---

## Raw Session Log

> **Fidelity note.** This is a faithful phase-by-phase record rather than a verbatim transcript: the
> session ran ~60 turns and included multi-hundred-KB subagent payloads and multi-hour measurement
> logs that would be unusable inline. Every decision, finding, correction, command class and measured
> number is captured. Retained raw artifacts on disk:
> `…/scratchpad/{ladder.log,ladder2.log,ladder3.log,rung10k.log,fold_final*.log,pg_h.log,unit_*.log}`
> and the review payload at `…/tasks/w9xwc4ssc.output`.

### Phase 1 — CON-1 review fold (opened mid-flight from a compacted session)

The three-lane adversarial review (`wf_ab30eefe-bc2`: quant/correctness, security/RLS,
record-vs-diff) returned. **All three lanes independently returned the SAME BLOCKING**: OQ-CON-1-24(i)
mixed same-family scheme-VERSION refusal was structurally unfireable. Verified independently before
folding (`grep scheme_family` → present only at the serializer that pins it and the docstring that
claims a refusal). Implemented over LIVE heads; mutation-proven; all four advertising surfaces
corrected. Ten further ratified-but-undelivered items delivered. Hardening beyond findings:
`coverage_floor` (0,1], the DB disclosure fence, the compute-zone orphan → `CORRUPT_PINNED_CONTENT`
gap, `GET /runs/{run_id}` point-select, `ConcentrationModelParameterError`, `_norm_guid` join keys.

**Discovered by EXECUTION, missed by all three reading lanes:** migration 0057's constraint names were
double-prefixed and PG-truncated. Fixed; live-catalog gate added; P4 destructive proof re-executed.

Fable verification of the fold confirmed all ten numbered items and refuted one sub-claim
(`KeyError`/`TypeError` missing from the compute-zone except tuple) — widened before push.

Committed `aa9bdd8`; both tiers green (make check; full-PG 2,776/0); pushed; CI green all six; user
merged PR #152.

### Phase 2 — P1 verify-on-main sweep + CON-1 closeout

Ran AFTER the last merge per the standing rule, against the MERGED diff. All seven ledgers verified.
Two of my own reads were wrong before checking (truncated greps hid content inside 3,000-char table
rows). One real staleness found: `current_state.md`'s truth block. Proved the merged tree
byte-identical to the validated tree. Closeout stamped (`caa7726`), CI green, user merged PR #153.

### Phase 3 — PERF-0 planning to the gate

Research established three facts that reshaped the slice: NFR-05's batch half has NO number; a
synthetic package with a reserved tenant and determinism fencing already exists; there is no
bulk-write path and no timing instrumentation anywhere. Record drafted with OQ-1…10 + recommendations;
**user ratified OQ-1 (4 h @ 10k) and OQ-2 (month-end + daily factors)**, both as recommended.
Committed `938bccc`. Flagged honestly that no verifier pass had run on the record (ES-1 says one
should precede ratification).

### Phase 4 — PERF-0 implementation (12 commits)

1/n scale seed + fence census (OQ-10 REVERSED by execution; OQ-11 added). 2/n first reading —
capture rail LINEAR (0.990 over 16×). 3/n the generalized fence caught its own author
(`session.execute` → `session.get`). 4/n factor seeding + a summary that described its arguments
rather than its writes. **5/n RED CI** — the second marketdata import fence; both-tier-before-push
lapse disclosed; pre-flight manifest gained the change class. 6/n the harness, five of six segments.
7/n the batch ladder — my audit-chain degradation hypothesis REFUTED by measurement. 8/n all six
segments (portfolio_return per portfolio; classification seeding). 9/n Reading 3 + the finding that
cost is not where AD-003 expected. **10/n the CI smoke — which invalidated Reading 3's concentration
row within 20 minutes.** 11/n Reading 4 (corrected; ~3% delta). 12/n **Reading 5 — the 10,000 rung
MEASURED**, correcting my own optimistic seed projection.

### Phase 5 — standing rules + pre-review record work

Two rules added to memory (workflows verdict — a third lapse, recorded as a known failure mode; and
the asymmetric background-process flag). PERF-0 Part 9 execution addendum written BEFORE the review
so the record-vs-diff lane audits real claims. Pushed `104a880`.
