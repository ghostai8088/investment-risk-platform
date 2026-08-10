# RPT-3 — Report generation from the UI (Wave-17 slice 3) — decision record

**Status:** DRAFT v3, GATE-READY (pass 1: 6 lenses, 37 findings survived refutation, broke v1's
central consequence chain in three places. pass 2: 4 lenses, 29 findings against the FOLDS — the
established pattern held a fourth time, and pass 2's strongest findings are all in text pass 1
forced. §7 is the honesty ledger for both.) Ratified remit
(the Wave-16 close gate, D1 sequence): *"The FE can read reports but not create one; a run picker
+ generate flow over RPT-2's endpoints."* Size M.

## 1. What exists, verified against HEAD — with v1's three false claims corrected

- **`POST /reports` (RPT-2)** takes `portfolio_id`, `as_of_date`, `family_runs: dict[family_key →
  run_id]` (typed `uuid.UUID`, `extra="forbid"`), gated `report.generate` — held by
  `data_steward`, `risk_analyst_1l` **and `platform_admin`** (v1 omitted the third; it holds
  `ALL_CODES` and is never cloned into a customer tenant, so the customer-tenant holder set is the
  two makers). The rendered `portfolio_code` comes from the tenant-fenced portfolio ROW;
  `generated_at` is SERVER-stamped.
- **The family vocabulary** is `REPORT_FAMILIES` = `var`, `concentration`, `liquidity`,
  `rolling_risk` (registry order = render order; any non-empty subset valid; empty refused).
- **Refusals cross the wire as CONSTANTS, not service messages** — v1's "render the service's
  message un-translated" was IMPOSSIBLE at HEAD and three lenses converged on it. `reports.py:68-71`
  maps `ReportInputError → (422, "report input refused")` and `ReportProvenanceError → (422,
  "report provenance refused")`; `raise_mapped_write` discards the service text. That is a
  DELIBERATE RPT-2 disclosure fence (a service message can embed identifiers), and this slice does
  NOT reopen it.
  **Three wire cases, not two** (pass 2): the generate route ALSO raises a bare
  `404 "portfolio not found"` (`reports.py:163`) before any service call — a cause-disclosing
  detail v2 wrongly excluded when it said "the two constants and nothing else". The FE therefore
  discriminates THREE cases, and the constants DO distinguish input-class from provenance-class:
  v2's "the FE cannot distinguish refusal causes" was itself an overstatement (it cannot
  distinguish WITHIN a class). OQ-RPT3-4 is rewritten again on that correction.
- **Three of the four families have a runs listing; `rolling_risk` DOES NOT** — v1's "every read
  the picker needs exists" was FALSE for one family. `PERF_RUN_TYPES` is pinned to
  {PORTFOLIO_RETURN, BENCHMARK_RELATIVE, DESMOOTHED_RETURN}; `run_type=ROLLING_RISK` is a
  fail-closed 422 at `/perf/runs`, and the unfiltered listing excludes it. ROLLING_RISK (and
  SHARPE) postdate the allowlist and were never added — drift, not a recorded decision (the
  comment says "the perf families", which they are). OQ-RPT3-0 decides the fix.
- **Run summaries carry NO as-of date** (all four shapes are the same 11 fields). The as-of is
  reachable by joining `input_snapshot_id` against `GET /snapshots` headers
  (`as_of_valuation_date`); `snapshot.view` is held by all three generate holders, so the join is
  permitted. Snapshot headers carry NO portfolio id, so a portfolio label is NOT buildable —
  stated so nobody promises it later.
- **`GET /reports` filters by `portfolio_id` only** (no date filter), ordered `as_of_date`
  DESC, paged with `limit ≤ 500`.
- **The FE surfaces exist**: `views/reports/Reports.tsx` at `/ops/reports`; the write convention
  is `writes.ts`; refusal rendering is `explain()` in `views/ops/Refusal.tsx` (one pass-1 LOW
  claimed the function does not exist — REJECTED, `Refusal.tsx:28`).
- **Contract fact, recorded**: `POST /reports` declares only 201/422 in OpenAPI; 403/404 are
  runtime behavior. Accepted as-is (the platform-wide convention); no contract change here.

**Consequence chain, v2**: ZERO new routes and NO migration hold; **"FE-only" does NOT** — the
`rolling_risk` fix (OQ-RPT3-0-A) is a one-line Python allowlist change plus its tests and a
mutant. The census stays a positive claim; the battery is no longer expected-empty (§6).

## 2. Open questions

**Which of these are DECISIONS and which are DESIGNS** (pass 2: v2 presented four designs in
decision-shaped headings with no alternatives, which is how a hidden decision gets rubber-stamped).
**Gate decisions — genuine forks, each with alternatives: OQ-RPT3-0, OQ-RPT3-1, and the
REQ-RPT-001 status in §5.** OQ-RPT3-2/-3/-4/-5 are DESIGNS derived from code facts, recorded here
so the gate can refuse one if it disagrees, but they carry no alternative I can honestly recommend
against — where a genuine fork existed inside them (the visibility bound's rendering; the
per-constant checklists) the fork is stated in place.

### OQ-RPT3-0 — The `rolling_risk` listing gap (NEW at pass 1; BLOCKING-sourced)

**A (recommended)** — add `RUN_TYPE_ROLLING_RISK` to `PERF_RUN_TYPES`: rolling-risk IS a perf
family; the exclusion is dated drift, the change is one allowlist line, the existing
filter/paging/permission machinery applies unchanged, and zero routes are minted. The fail-closed
422 for a still-unlisted type is retained and re-proven. **SHARPE is deliberately NOT added** —
nothing consumes it and this slice must not widen a listing on symmetry alone; recorded as drift
with trigger (the first SHARPE-consuming surface). **B** — a dedicated rolling-risk runs route
(+1 route, a census move, more surface for the same read). **C** — drive the picker off
`/perf/rolling-risk` result rows (an existence-dependent read: a COMPLETED run with suppressed
rows would be invisible — a correctness hole, refused).

### OQ-RPT3-1 — Where the flow lives

**A (recommended)** — extend `/ops/reports`: the generate form joins the screen that lists and
renders what it mints (the `/ops/reproduction` precedent). **B** — a separate screen; buys
nothing at this size.

### OQ-RPT3-2 — The picker: per-family run_type + status, labeled by the snapshot join

Each checked family's dropdown lists **`status=COMPLETED` runs of that family's RUN TYPE** from
its own endpoint (`/risk/runs?run_type=VAR&…`, `/concentration/runs`, `/liquidity/runs`,
`/perf/runs?run_type=ROLLING_RISK&…` after OQ-RPT3-0-A), newest first. *(v1 said "filters only on
status", which self-contradicts on the multi-type listings — corrected.)*

**Labels**: run id short-form + the run's snapshot `as_of_valuation_date`, joined client-side
from `GET /snapshots` headers — presentation, not a fence. Runs whose snapshot date ≠ the chosen
report date are BADGED ("dated 2026-06-30, not 2026-03-31") and still offered: the server is the
validator, and the badge is what makes its date-mismatch refusal unsurprising. NO portfolio
badge — the reads to build one do not exist (§1), stated as a limitation on the screen's help
text rather than silently absent.

**The picker is a CONVENIENCE, not a fence** (unchanged from v1): the server re-validates
everything; the one client-side gate is submit-disabled-until-≥1-family, with the reason rendered.

### OQ-RPT3-3 — Carry (d): duplicate generate from a browser

**VISIBILITY, not idempotency** (substance unchanged; the mechanism and its BOUND now stated
truthfully — pass 2 caught v2 shipping a wrong number in the other direction): the form reads
`GET /reports?portfolio_id=…&limit=500` and client-filters to the chosen `as_of_date`.

**The page bound makes the per-date count UNKNOWABLE, not merely large.** The listing orders
`as_of_date` DESC with no date filter, so a full 500-row page holds the NEWEST-dated reports and
bounds nothing about an older chosen date: the true count for that date may be zero or hundreds.
v2 rendered "500+" into the per-date sentence, which asserts ≥500 for a date that may have none —
its own bar ("never a silently-wrong small number") met by a silently-wrong LARGE one. So:

* page not full → "N report(s) already exist for this book and date" (N exact, including zero);
* page full → "this book has 500+ reports; **the count for this date could not be determined**".

Submit disables while a POST is in flight (the double-click guard). The carry's idempotency
trigger is explicitly NOT pulled.

### OQ-RPT3-4 — Refusal rendering, PER WIRE CASE (rewritten twice: pass 1, then pass 2)

Pass 1 killed v1's "render the service's message". Pass 2 killed v2's replacement: ONE static
checklist under BOTH constants, when every cause it lists is input-class. An operator seeing
`"report provenance refused"` would be handed four causes that CANNOT produce it — worse than no
guidance, because it reads authoritative. The wire discriminates three cases; the FE renders three:

| Wire | What the FE renders |
|---|---|
| `404 "portfolio not found"` | "That portfolio is not visible to this tenant." (route-level, before any service call) |
| `422 "report input refused"` | The constant + the INPUT-class checklist: the run's snapshot is dated differently from the report date (see the badge); the run was computed for a different book; a VaR run whose ROOT EXPOSURE RUN carries no portfolio scope, so nothing ties its numbers to a book (carry (f) — a known platform limitation); no family was selected |
| `422 "report provenance refused"` | The constant + the PROVENANCE-class line: a bound run's model citation could not be established. **No input-class causes are shown** |
| `403` | `explain()`'s entitlement text |

The checklists are GUIDANCE, and each says so ("the server does not disclose which of these"). The
VaR line's wording is corrected to carry (f)'s actual mechanism — the RUN is unscoped
(`scope_portfolio_id` NULL, propagated from the root exposure run), not "a snapshot without
portfolio scope", which is a property no snapshot has (`report/service.py:209-216`).

**Staleness binding** (pass 2): the checklists enumerate causes the SERVICE owns, so they rot when
it changes. Bound mechanically — the input-class checklist's carry-(f) line is asserted by a test
that also asserts carry (f) is still OPEN in `rpt_2_slice_record.md`; when the carry is paid, that
test reddens and the FE text must move with it. A prose reminder would not have survived.

Carry (f)'s fix stays with its own trigger, **quoted exactly**: *"The next slice touching the
exposure/factor/VaR binders — or a report that needs VaR over a consumed snapshot."* RPT-3 touches
neither binder and needs no VaR-over-consumed-snapshot report, so the trigger is untouched — v1's
paraphrase dropped the second arm, which is the one nearest this slice.

### OQ-RPT3-5 — as_of_date entry (unbound in v1)

A plain date input, defaulting to the most recent snapshot date seen among COMPLETED runs (a
convenience default, recomputed from the same join the labels use — never a fence). The proofs
bind it: the POST carries exactly the entered date, and the date-mismatch badge derives from it.

## 3. The proof list (bound HERE, by name — the checklist the review diffs against)

P18 applies: every negative names its positive twin inline.

1. **Picker population, per family ×4**: the dropdown lists the stubbed endpoint's COMPLETED runs
   of the family's run type, newest first (positive) ↔ a run of ANOTHER type on the same listing
   never appears in the family's dropdown (negative — the multi-type-listing hazard).
2. **The snapshot-date label**: a run whose snapshot header dates it off the chosen date shows
   the badge (positive) ↔ a matching-date run shows no badge (twin).
3. **The write**: submit POSTs `/reports` via `writes.ts` with exactly the checked families' run
   ids; unchecked families ABSENT from `family_runs` (positive) ↔ with zero families checked, no
   POST is issuable and the reason renders (negative + its rendering).
4. **Refusal rendering ×3**: 403 → the entitlement text (twin: a 201 renders no refusal); 422
   `"report input refused"` → the constant + the static cause checklist; 422
   `"report provenance refused"` → likewise. The checklist text asserts the VaR scope line — the
   carry-(f) surfacing is a PROOF, not an intention.
5. **Success is a consequence**: after a 201 the list REFETCHES and the new report's
   **`report_code`** appears in the rendered rows ↔ on a 422 the list does NOT refetch.
   *(Pass 2: v2 said "the new report id is present in the rendered rows" — unimplementable.
   `Reports.tsx` uses `r.id` only as a React key and selection token; the text it renders is
   `report_code` (`Reports.tsx:121-144`). A proof that asserts on text the component never
   renders fails for the wrong reason, which is how a real regression later gets dismissed as
   "that test is flaky".)*
6. **The visibility count** (OQ-RPT3-3): shows N for seeded (portfolio, date) matches ↔ absent
   when none ↔ reads "500+" at the page bound (the bound's own test). Freshness is stated, not
   proven: the count is as-of page load + post-generate refetch — recorded as a limitation.
7. **The double-click guard**: while a POST is unresolved a second submit issues no POST (twin:
   after resolution the button re-arms).
8. **`PERF_RUN_TYPES` extension** (OQ-RPT3-0-A, Python): `/perf/runs?run_type=ROLLING_RISK`
   returns rolling-risk runs (positive) ↔ a still-unlisted type (SHARPE) stays a fail-closed 422
   (the retained refusal, re-proven) ↔ **the UNFILTERED listing now also returns ROLLING_RISK
   rows** — a real behavior change for every existing `/perf/runs` consumer, pinned by its own
   assertion rather than discovered (pass 2, three lenses; `RunsList.tsx` filters by family so it
   is unaffected, but the change is stated) ↔ mutant R-E1: reverting the allowlist starves the
   picker and MUST redden the endpoint test. The mutant anchors on the post-`make fix` multi-line
   frozenset form — the REPRO-2 lesson, applied before the fact: an anchor is a claim about
   bytes, so it is written against the formatted bytes.
9. **No deployed arm is added, stated**: RPT-2's smoke already generates over HTTP and
   byte-verifies; RPT-3 adds browser behavior jsdom can exercise; carries (c)/(h) record what it
   cannot. The deployed surface is unchanged.

## 4. Topology and separation of duties (absent from v1; pass-1 MEDIUM)

The picker wires per-family RUN reads to a REPORT write. Pass 1's disclosure lens walked the
topology and reports it CLEAN, adopted here as a positive claim the implementation must not
regress: every runs listing the picker reads is gated by a view code every `report.generate`
holder also holds (no empty-picker-for-a-legitimate-generator, no read the generate verb does not
already imply); the generate flow adds no read surface (`report.view` output disclosure is
RPT-2's audited fence, untouched); `auditor_3l` does NOT hold `report.generate` and therefore
cannot reach the form's write. *(v2 also claimed it holds "no schedule-shaped verb" — FALSE, and
two lenses caught it: `auditor_3l` holds `schedule.view`, deliberately, as 3L oversight scope. The
clause was borrowed from REPRO-2's ALERT-1 reasoning where it was about a DIFFERENT verb set. A
claim adopted from a neighbouring slice is still this record's claim.)* A run id a caller could not READ still
binds only via the service's own tenant-fenced resolution — unchanged by this slice, which adds
no server code path.

## 5. Ledgers (v1 had none — pass-1 HIGH; the seven-ledger sweep applied)

- **REQ-RPT-001 is STALE at "Draft"** in `requirements_backbone.md:262` AND
  `requirements_traceability_matrix.md:94` — its acceptance clause ("Report binds run IDs;
  regenerates identically, BR-9") has been PROVEN since RPT-1/RPT-2
  (`infra/deploy/prove_report_identity.sh` byte-verifies a regenerated artifact with a negative
  control; `apps/backend/tests/test_reports_endpoint.py`).
  **The target status is a GATE DECISION, not an editorial act** (pass 2 — v2 said "advances it"
  and named no destination, hiding a substantive choice as prose). The house vocabulary makes the
  two candidates mean different things, and the naive one OVERCLAIMS: the row's title is *"Risk
  reports (market/credit/liquidity)"* while `REPORT_FAMILIES` is var/concentration/liquidity/
  rolling_risk — **there is no credit-family report**. So `Implemented (RPT-n, date)` would
  falsify the row's own title even though its acceptance clause is fully proven; the backbone has
  exactly one `Implemented` row against 38 `In-Progress (…)` rows that each NAME the open leg.
  **Recommended: `In-Progress (RPT-1/RPT-2 2026-08-07; RPT-3 2026-08-10) — the acceptance clause
  is proven end-to-end; the CREDIT report family is not built`**, moved in LOCKSTEP in both
  ledgers. The alternative (ratify that the acceptance clause alone governs, and mark Implemented)
  is a real option the gate may prefer; it is not mine to take silently.
- **CTRL-009** (report reproduction): RPT-3 changes no disposition; the row's citations are
  re-checked at the implementation, not rewritten.
- `current_state.md` + the roadmap row at the fold, per standing practice. No control matrix,
  SoD, entity, or audit-taxonomy rows move (nothing minted).

## 6. Mint census and battery

**Minted: NOTHING** — no permission, no route (census 305 at planning HEAD, unchanged BY THIS
SLICE), no entity, no event code, no migration (head `0068` at planning HEAD, unchanged BY THIS
SLICE). The gate ratifies the empty census as a positive claim. *(Phrased as "unchanged by this
slice" per pass 1: absolute pins in a planning record rot when slices re-sequence.)*

**Battery**: group `rpt-3`, no longer expected-empty (v1's claim fell with "FE-only"): R-E1 (the
`PERF_RUN_TYPES` reversion, §3.8). FE assurance is the §3 component-proof list.

## 7. The honesty ledger — what each pass changed

**Pass 1 (6 lenses, 37 findings surviving refutation)** broke v1's central consequence chain:
"zero new routes, FE-only, empty battery" was one-third false (the `rolling_risk` listing gap
forces a Python change); the refusal-rendering design was impossible at HEAD (wire constants —
three lenses converged); the proof list omitted the two refusal classes the picker makes MOST
likely and bound an unimplementable jsdom scroll. Also: the holder pin gained `platform_admin`,
carry (f)'s trigger was quoted in full, the as-of label join was specified with its permission
checked, P18 twins added throughout. One finding REJECTED with evidence (`explain()` exists,
`Refusal.tsx:28`) — and it slipped in because pass 1 refute-checked only serious findings.

**Pass 2 (4 lenses, 29 findings) attacked the FOLDS, and that is where its best work was** — the
fourth consecutive cycle where this held:

- **The rewritten OQ-RPT3-4 was wrong again**, in a new way: ONE checklist under BOTH constants,
  when every listed cause is input-class. Under `"report provenance refused"` an operator would
  have been handed four impossible causes, authoritatively. Now per-wire-case, and the VaR line
  corrected to carry (f)'s actual mechanism (an unscoped RUN, not "a snapshot without scope" — a
  property no snapshot has).
- **v2's "the wire carries the two constants and nothing else" was false**: the route's
  `404 "portfolio not found"` is a third, cause-disclosing case.
- **v2's "500+" fix shipped a wrong number in the opposite direction**: the listing is
  `as_of_date` DESC with no date filter, so a full page bounds NOTHING about an older chosen date.
  "500+ for this date" asserts ≥500 where there may be zero. Now: the count is declared
  UNDETERMINED at the bound.
- **Proof 5 was unimplementable**: `Reports.tsx` renders `report_code`, never the id.
- **§4's adopted-clean SoD claim carried a false conjunct**: `auditor_3l` DOES hold
  `schedule.view`. The clause was borrowed from a neighbouring slice's reasoning about a different
  verb set — an adopted claim is still this record's claim.
- **§5 hid a decision as prose** (no target status named) and the naive destination overclaims a
  requirement whose title spans a family the platform does not build.
- Recorded, not folded: OQ-RPT3-0-A's unfiltered-listing side effect is now pinned by its own
  assertion; the checklists gained a mechanical staleness binding; the mutant anchor is written
  against formatted bytes.

**Still open, stated rather than closed**: the portfolio ENTRY mechanism (picker vs typed id) is
unbound — pass 2 caught it as the one form input neither pass reached. It is left to the
implementation with a constraint the gate can see: whatever it is, the 404 case above must render,
because a portfolio the tenant cannot see is a reachable state.

## 7b. A standing-rule consequence the gate must see: P15 has no Fable for four days

P15 requires the implementation's review to run on a DIFFERENT ENGINE than the build. Every
Wave-17 slice has used Opus to build and Fable to review, and that pattern has now caught a
BLOCKING or HIGH ten consecutive times. **The Fable usage limit was reached during this planning
cycle and resets in four days** — pass 2's verification fleet lost 22 of 33 agents to it, and
their findings were recovered from the journal and verified by hand instead.

The RPT-3 implementation therefore cannot be reviewed by Fable on the current schedule. The
options, none of which I should pick silently:

* **Fresh-context Opus audit** — the RPT-2 precedent (a fresh-context pre-merge audit found a
  real disclosure the review missed). Different context, same engine: weaker than P15's intent,
  but it has a track record HERE.
* **Sonnet as the different engine** — genuinely different, unproven in this role on this repo.
* **Wait** — hold the implementation until Fable returns. Honest, and costs four days.

Recorded here because P15 is a ratified standing rule and this is the first time the platform
cannot satisfy it as written.

## 8. Non-goals (P19: each with a trigger)

- **Generate idempotency** — carry (d) unpulled; trigger: a slice that wants it.
- **VaR bindability** — carry (f); trigger quoted in §OQ-RPT3-4.
- **SHARPE in `PERF_RUN_TYPES`** — trigger: the first SHARPE-consuming surface.
- **Report deletion/retention** — trigger: a real retention requirement.
- **Scheduled report generation** — v1 claimed `target_run_type=REPORT` "already exists
  server-side"; that claim was FALSE and is withdrawn. Trigger: a slice wiring a REPORT run type
  through the scheduler's validated vocabulary, with its own cadence questions.
- **Real-browser E2E** — carries (c)/(h); trigger: a browser harness.
