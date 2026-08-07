# Wave-16 planning — the promises become reachable and continuously checked

**Drafted 2026-08-07 on the close-review model (fresh-context relative to the Wave-15 builds),
against `main` at `d904d6c`. Everything in Part 3 is Tier-3 and binds nothing until ratified.**

---

## Part 0 — Organizing facts, recon-verified against `main`

1. **The report exists and cannot be reached.** ENT-072 regenerates byte-identically from its id —
   and no HTTP endpoint serves generation or retrieval; the FE has no report view. Verified: no
   report router registered in `apps/backend/src/irp_backend/main.py`; zero report views in
   `apps/frontend/src`. A board member today needs a developer with a Python session.
2. **`generated_at` is caller-asserted** (the N3 decision, recorded on the ENT-072 column): the
   trust posture for an HTTP caller asserting its own evidence time is explicitly reserved for the
   gate that exposes the verb — this gate.
3. **CTRL-018 has a ratified host and no code.** Wave-15 close §7-A: slice REPRO-1, dated at this
   gate. The scheduler machinery exists (`schedule`/`scheduled_run`, ENT-061/062, ticking since
   CAD-1) and currently dispatches exactly two families (`SCHEDULABLE_RUN_TYPES = {VAR,
   EXPOSURE_AGGREGATE}`, census-pinned in `test_scheduler.py`).
4. **The FK gap is measured, not estimated:** 115 failures across 12 suites with SQLite
   `PRAGMA foreign_keys=ON`; RPT-1's 12 paid; **103 remain** (sharpe 29, rolling_risk 28,
   breach_lifecycle 25, notification 10, private_capital 3, ingestion 2, es_backtest 2, + 4
   singles). Breakdown: `rpt_1_slice_record.md` §6. The pragma stays OFF globally until paid.
5. **The FE toolchain debt is enumerable:** TS→7, eslint→10, jsdom→30, + six untypechecked root
   guard tests. Its ORIGINAL trigger — "first FE feature slice" — fires if RPT-2 ships an FE view.
6. **Standing triggers that do NOT fire here** (stated so silence is visible): cloud deploy (its
   own gate + spend, OQ-W15P-3's reserved option b); SSO/RTM-P9 (nothing internet-facing in this
   wave); credit/counterparty (no genuine curve feed); REQ-LIQ-002 redemption stress (no scenario
   slice, no user ask). Reversible by saying so.
7. **Bound inheritance:** PERF-0's four carries now bind "before any parallelization or
   grain-level performance work" (§7-B). REPRO-1 re-RUNS historical runs — that is re-execution,
   not parallelization or grain work; the carries are NOT inherited by REPRO-1 unless its remit
   turns out to touch kernel grain. Stated here so the non-inheritance is a visible reading, not
   an oversight.

## Part 1 — Scope boundary

Wave 15 made the engine deployable and its first report reproducible. **Wave 16 is: the promises
become reachable (a human can GET the report) and continuously checked (reproducibility is a
nightly machine verdict, not an on-demand ceremony) — and the test floor stops lying about
foreign keys.**

**Explicitly NOT in this wave:** new governed number families; cloud/SSO/internet-facing anything;
vendor adapters; dashboards beyond the report view RPT-2 may ratify; PDF typography.

## Part 2 — Proposed slice order

### RPT-2 (report access) → REPRO-1 (the reproduction job) → FK-1 (the 103). Recommended.

- **RPT-2 first** because it completes Wave 15's own purpose sentence ("a human outside the team")
  and is small: generate + get + list endpoints over a shipped service, the N3 decision, and —
  if OQ-W16P-3 ratifies the FE view — the first FE feature slice since the read surface wave.
- **REPRO-1 second** because it is the platform's thesis made mechanical, four times deferred, and
  it *consumes* RPT-2's regeneration verb as one of its checks (a report family re-verified
  nightly is CTRL-009's path to *Operational*, closing two control gaps with one job).
- **FK-1 third** because it is mechanical, measured, and benefits from landing after the two
  feature slices stop touching fixtures. Its acceptance is exact: the pragma ON globally, 0
  failures, and the per-suite count pinned so regression is loud.
- The FE toolchain majors, if ratified (OQ-W16P-4), ride as **RPT-2's slice 0** — the TC-1
  precedent: do the bump while the FE context is fresh, before the feature lands on it.

## Part 3 — Wave-level decision ledger (Tier-3 — ratify at this gate)

| OQ | Question | Recommendation |
|---|---|---|
| **OQ-W16P-1** | **Slice order** | **RPT-2 → REPRO-1 → FK-1** (Part 2). Flip RPT-2/REPRO-1 only if continuous verification matters more to you than reachability |
| **OQ-W16P-2** | **The N3 `generated_at` trust posture** — may an HTTP caller assert when its report was generated? | **NO for HTTP: server-stamped.** The HTTP verb stamps `generated_at = now()` server-side; the caller may not assert evidence time over the wire. The in-process parameter remains (batch/backfill), per the column's recorded rationale. An HTTP client asserting its own evidence time is a forgeable claim on a governed artifact |
| **OQ-W16P-3** | **Does RPT-2 include the FE report view, or endpoints only?** | **Include the FE view.** The wave purpose is a human REACHING the artifact; an endpoint without a view still needs an intermediary with `curl`. This fires the FE toolchain's original trigger, which OQ-W16P-4 resolves at the same gate rather than by accident |
| **OQ-W16P-4** | **The FE toolchain majors** (TS→7, eslint→10, jsdom→30, six untypechecked guards) — §7-C says decide HERE | **PAY, as RPT-2 slice 0**, executed-dry-run style (the FE-M1 lesson: a migration slice's pre-work is an EXECUTED dry run, not a read of the upgrade guide). Declining is coherent only with OQ-W16P-3 = endpoints-only, and must then be recorded with a NEW trigger, not silence |
| **OQ-W16P-5** | **REPRO-1's shape** | **Ride the existing scheduler** (a new schedulable run family, the census consciously extended), re-running the most recent COMPLETED run per governed family per tenant nightly and diffing result content against the stored rows; divergence → the webhook sink. CTRL-018 moves Planned → Implemented on the FIRST OBSERVED scheduled green (the CTRL-009 evidence bar); the report family's check is `regenerate_report` itself, putting CTRL-009 on the path to Operational |
| **OQ-W16P-6** | **FK-1's acceptance** | **Exact:** `PRAGMA foreign_keys=ON` in the SHARED fixture; 0 failures; the 115→0 count pinned by suite so a new dangling-FK fixture is loud. No sampling, no allowlist |
| **OQ-W16P-7** | **Does anything outward-facing enter this wave?** | **No.** Cloud/SSO stay behind their own gates (Part 0, fact 6). If a demo to an outside party is imminent, say so — that flips this and possibly OQ-W16P-1 |

## Part 4 — Standing-rule application map (P1–P15)

- **P1** (seven-ledger + verify-on-main): all three slices. RPT-2 touches the API surface — the
  OpenAPI/FE-types drift gate and permission mint rules (P11) bind.
- **P7** (lessons as acts): **OQ-W15P-7's failure mode gets a mechanical fix in this wave's
  remits** — every remit carries an explicit "inherited gate commitments" section listing what
  prior gates bound to ITS gate, so a commitment cannot fire silently again. This planning doc's
  Part 0 fact 7 is the first instance.
- **P9** (refusals FIRE): REPRO-1's divergence alarm must be made to fire on a planted divergence
  before the control moves; RPT-2's entitlement refusals fire with real foreign-owned objects.
- **P14** (exit codes quoted): every gate claim, both tiers, per slice.
- **P15** (shared-assumption proofs): REPRO-1 is ITSELF a P15 instrument (a different process,
  nightly, re-deriving what the build asserted). RPT-2's identity claims are already covered by
  the restore-cycle proof; its NEW surface (HTTP) needs at least one proof not sharing the
  service-layer tests' assumptions — the deployed-stack smoke extends to the report endpoints.
- Fresh-context audit BEFORE merge, per slice, unchanged (n=2 verdict: keep; re-ask at n≥4).

## Part 5 — Pre-emption ledger (what this wave deliberately does not decide)

Scheduled report GENERATION (REPRO-1 re-verifies existing reports; generating new ones on a
schedule is a separate act with its own approval semantics); PDF; report distribution (the webhook
sink notifies operators, it does not deliver reports); any new snapshot component kind; the
`limit_utilization` (ENT-032) and `instrument_factor_loading` (ENT-058) paper reservations.

---

*Gate: present Part 3 to the user. Nothing proceeds until ratified.*

---

## Part 6 — Gate outcome (2026-08-07)

The user ratified **"approved. proceed"** against Part 3 without amending any recommendation. Each
OQ is taken **as recommended**, operating assumptions stated per the standing precedent:

| OQ | Outcome | Operating assumption made explicit |
|---|---|---|
| **OQ-W16P-1** | **RPT-2 → REPRO-1 → FK-1** | That reachability outranks continuous verification by days, not months — REPRO-1 follows immediately |
| **OQ-W16P-2** | **Server-stamped `generated_at` for HTTP callers**; the in-process parameter remains for batch | That an HTTP client may never assert evidence time on a governed artifact. If a backfill-over-HTTP need appears, it gets its own gate |
| **OQ-W16P-3** | **RPT-2 includes the FE report view** | That "a human outside the team" means a browser, not `curl` |
| **OQ-W16P-4** | **FE toolchain majors PAID as RPT-2 slice 0** (TS→7, eslint→10, jsdom→30, the six untypechecked root guards) — EXECUTED dry-run style, the FE-M1 lesson | That the debt is paid before the feature lands on it, not after |
| **OQ-W16P-5** | **REPRO-1 rides the existing scheduler**; CTRL-018 moves only on the first OBSERVED scheduled green | That the census extension is a conscious act (the run-type census moves WITH the slice) |
| **OQ-W16P-6** | **FK-1 acceptance exact: 115 → 0, pragma ON globally, per-suite count pinned** | No sampling, no allowlist — the measured number is the contract |
| **OQ-W16P-7** | **Nothing outward-facing this wave** | That no external demo is imminent. Say so if that changes — it flips this and possibly OQ-1 |

**NEXT = the RPT-2 remit** (outcome + proofs, carrying the FIRST "inherited gate commitments"
section per Part 4's P7 fix), then the build.
