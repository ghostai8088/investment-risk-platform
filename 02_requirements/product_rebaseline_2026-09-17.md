# Product re-baseline — 2026-09-17: a CRO cannot recognise it

**Status: DRAFT, PENDING RATIFICATION.** Authored 2026-09-17 on `product-rebaseline-2026-09-17`
by Claude (Opus 5), from four recon censuses of the repository, after a different-engine
verification pass (Part 7). Nothing in this document is ratified until the owner says so, and the
decision points in Part 5 are the owner's. This record follows `product_rebaseline.md`
(2026-08-12) and is the second re-baseline of the product; it exists because the first one did
not work, and Part 1 says why.

**Why it exists.** On 2026-09-17 the owner opened the deployed demo and said: *"Wow, this is way
off."* Asked to state the purpose of the application, Claude gave the ratified answer (a
multi-tenant risk platform for asset managers spanning public and private assets, serving the
CRO, the risk manager, the portfolio manager and the board). The owner replied: *"I agree with
your interpretation of 'way off'. This is not something a CRO or PM would recognize. How do we
realign?"* and then: *"Should I start over instead of trying to fix this?"* The recommendation was
a partial restart, and the owner said "proceed". This record is the proposal.

**What the owner will see if they open the demo today.** One portfolio named DEMO-GLOBAL holding
three positions (400 shares of a fictional "ACME Corp", 300 of "EURX Industries AG", 50 units of
one private-equity fund). A landing page titled "How you can trust a governed number". A left nav
with seven operations screens, one admin screen, a six-step governance walk and a run ledger.
There is no screen anywhere that shows a portfolio's total risk, its exposures by factor or sector
or currency, or a limit utilisation figure. The only chart in the product is a server-rendered
SVG inside a report, visible through a sandboxed iframe on the Reports operations screen. The
numbers behind all of this are real, governed and reproducible. Nobody can see them.

---

## Part 1 — What happened, and why the 2026-08-12 fix did not fix it

### 1.1 The same complaint, thirty-six days apart

On 2026-08-12 the owner said: *"The math and visualization need to be the star of the show ...
How did we get so off track that the way it was built was antithetical to the original plan?"*
(`product_rebaseline.md:19-23`). The response was a re-baseline that:

- diagnosed the drift mechanism correctly: acceptance criteria satisfiable without delivering the
  stated purpose (`product_rebaseline.md:34-50`);
- minted a new capability domain, CAP-21 Presentation & Exploration, with five requirement rows,
  REQ-PRS-001 to REQ-PRS-005 (`requirements_backbone.md:337-350`);
- built four process gates: G1 capability coverage, G2 human adjudication of acceptance text, G3
  "every presentation requirement needs an acceptance criterion a human can see", G4 the
  wave-close coverage table (`product_rebaseline.md:256-345`).

The first slice built under CAP-21 was Wave-19 S1, PRESENT-1, ratified 2026-09-05 and built
2026-09-05 to 2026-09-17 on `w19-s1-present`. It delivered a presentation contract per result
family, a renderer-version dispatch, and a governed chart: a byte-identical inline SVG emitted
into report HTML and covered by the report content hash. It passed its census, its mutation
battery (13 of 13 killed), full-PG at 3,758 tests, and a 39-finding adversarial review. **No
person can see the chart on any screen of the product except through a sandboxed iframe on an
operations page.** The slice is a faithful execution of REQ-PRS-002, whose acceptance text is
entirely about bytes, hashes, run ids and SVG element names (`requirements_backbone.md:347`).

G3 was supposed to prevent this. Its test is "a HUMAN to see something or a RENDERED artifact to
be asserted on" (`requirements_backbone.md:339`). A rendered artifact asserted on by a test
satisfies it. The chart is a rendered artifact. G3 passed.

### 1.2 The mechanism, precisely

The 2026-08-12 record said: *"An audit whose reference point is the artifact carrying the defect
cannot see the defect"* (`product_rebaseline.md:70-72`). It then repaired the artifact, the
requirements register, and kept it as the reference point. Every gate it built reads the register
or a taxonomy the register cites. None of them asks a person to use the product.

The register can only ever describe what a system does. It cannot describe what a person
experiences, because acceptance text is written by the builder and, as G2's own bake-off proved,
"any word rule is one word away from being switched off by the person it polices"
(`product_rebaseline.md:295-298`). A row that says "a chart is a server-rendered SVG fragment
covered by the content hash" is a true, testable, and complete description of something no CRO
will ever look at.

### 1.3 The yardstick that was never used

A persona and journey document has existed since 2026-06-18:
`02_requirements/personas_and_user_journeys.md` (REQ-PERSONA-001). It names ten personas and eight
journeys. UJ-1, the first-line daily risk review, reads in full: authenticate; view positions and
exposures as-of; run or inspect risk results; see limit utilisation and any breaches; if breached,
initiate a response (`personas_and_user_journeys.md:59-64`). UJ-2 step 1 is "Review
portfolio/aggregate risk and scenario results" (`:67`). Its own text says "Journeys are the basis
for per-phase user stories" (`:57`).

Measured on 2026-09-17: no user story was ever written. No `UJ-` id appears in any document
authored after June 2026 except the four P1A implementation plans. The 2026-08-12 re-baseline does
not cite the journeys document once. Neither does any wave planning record, any wave close review,
the operating instructions, or Parts 1 to 4 of the roadmap. The Definition of Done has no
user-perspective criterion; its only UI clause is a prohibition (`definition_of_ready_done.md:49`).

The one product-UI decision ever taken, FE-3's information architecture (OQ-FE-3-1, ratified
2026-07-21), was offered to the owner as a choice between "the platform's governance story as the
product narrative" and "a generic run browser" (`ui_read_surface_assessment.md:46`). No
persona-shaped option was on the table. The owner chose the better of two engineering options, and
that choice is what the product looks like today. The recommendation was Claude's.

### 1.4 Four measured facts underneath

1. **The read a dashboard needs most was deferred and never swept.** API-1 planning (2026-07-20)
   deferred "metric time-series + cross-family summary" to "a later fast-follow"
   (`api_1_decision_record.md:55`). No later record names it. It is a homeless carry of the P19
   class, written before P19 existed, and P19's clause B (the wave-close backstop) has run twice
   since without finding it because it lives in a decision record's scope line, not in the carry
   register.
2. **The engines exist and the aggregates do not.** 178 GET endpoints serve 25 governed
   calculation families. Per-portfolio latest reads exist for VaR and ES, tracking error,
   exposure total, concentration shares, liquidity shares, rolling risk, Sharpe and returns
   (Part 3). There is no exposure-by-factor, by-sector or by-currency aggregate read: factor
   exposures come back one row per instrument-and-factor (`api/risk.py:982`). There is no limit
   utilisation ratio anywhere in the backend (`api/limits.py:406` returns state, not
   observed-over-threshold). There is no cross-family summary for one portfolio as of a date.
3. **The deployed demo is one three-position book.** The campaign script runs only the base
   campaign (`scripts/run_demo_campaign.py` → `irp_shared/demo/campaign.py`). The 27 extension
   stages that add the multi-currency fund, the structured fund, the private-credit fund, the
   limits and the four open breaches exist only as ordered PostgreSQL test modules; there is no
   orchestrator that seeds them into a deployed stack. The 141-run, 27-model demo position that
   every close review quotes has never been on a deployed database.
4. **The product surface is a ledger.** Of 14 routes, nine are operations or administration
   screens, three are the governance walk, and two are a run list and a run detail page whose
   columns are run ids, snapshot ids and model versions. The single "Value-at-Risk" heading in
   the product says: "VaR has no 'latest for portfolio P' resolver yet ... open one for its
   value" (`views/walk/NumbersStep.tsx:97-107`). That resolver shipped at API-1b (PR #92, merged
   2026-07-22). The screen was never updated.

### 1.5 What this is not

It is not a failure of the engines, the governance or the tests. 107,000 lines of backend and
shared code, 77 migrations, 25 governed families with cited methodology, symmetric row-level
security, a frozen audit service, reproduction on demand and 3,700 PostgreSQL-tier tests are the
hard part of an enterprise risk platform and they are built. It is not a failure of effort on the
front end either: 34,500 lines and 250 tests. It is a failure of the question every gate asks.
Seventeen closes asked "did we build it correctly"; the 2026-08-12 fix added "does the register
cover the taxonomy"; nobody has yet asked "can the CRO use it".

---

## Part 2 — The decision: a partial restart

**Keep** the backend, the shared package, the migrations, the tests, the governance documents,
the standing rules, and the front-end infrastructure that is product-agnostic (Part 4.3).

**Restart the presentation layer** as a persona-first product. The existing screens are reference
material. The operations and administration screens are kept because they serve real journeys
(UJ-4, UJ-5, and the second-line breach review in UJ-2), but they stop being the product's front
door.

**Replace the deployed demo book** with one coherent multi-asset book that a CRO would recognise,
seeded by one orchestrator on deploy.

**Change the yardstick.** A persona journey, walked by a person on the deployed stack, becomes the
acceptance test for every presentation slice. The requirements register stays as the record of
what the system does; it stops being the only judge of whether the product is right.

**Why not start over.** The alternative was raised by the owner and weighed. A fresh repository
would discard the part that is right and, run under the same yardstick, would produce the same
drift later. The front end and the demo book are the parts that are wrong, and together they are
a fraction of the codebase. Part 4 is sized on that basis.

---

## Part 3 — What can be shown today, from reads that already exist

This table is the feasibility floor for the first two slices. Every path was verified against
the router source on 2026-09-17. A row marked MISSING is a new read; every one of those is an
additive aggregate over existing governed results, not a new engine.

| What a CRO or PM expects to see | Read that serves it today | Status |
|---|---|---|
| Portfolio VaR and ES, latest, with confidence and horizon | `GET /risk/vars/latest?portfolio_id=&metric_type=` (`api/risk.py:1749`) | EXISTS |
| Tracking error vs benchmark | `GET /risk/active-risk/latest?portfolio_id=` (`api/risk.py:2208`) | EXISTS |
| Total exposure in base currency | `GET /exposure/latest/sum?portfolio_id=` (`api/exposure.py:372`) | EXISTS |
| Exposure by hierarchy node with currency translation | `GET /exposure/runs/{run_id}/rollup?node_id=` (`api/exposure.py:430`) | EXISTS (run-keyed) |
| Concentration by sector, country, issuer | `GET /concentration/results/latest?portfolio_id=` (`api/concentration.py:322`) | EXISTS (shares) |
| Liquidity tiers | `GET /liquidity/results/latest?portfolio_id=` (`api/liquidity.py:154`) | EXISTS |
| Rolling return, volatility, drawdown | `GET /perf/rolling-risk/latest?portfolio_id=` (`api/perf.py:1227`) | EXISTS |
| Limit status per limit | `GET /limits/health` (`api/limits.py:406`) | EXISTS (state only) |
| Open breaches in scope | `GET /breaches?open=true&portfolio_id=` (`api/breaches.py:532`) | EXISTS |
| Holdings with marks as-of | `GET /portfolios/{id}/holdings?include_marks=true` (`api/holdings.py:138`) | EXISTS |
| Portfolio tree as-of | `GET /portfolios/tree-as-of?at=` (`api/portfolios.py:175`) | EXISTS |
| Reported vs desmoothed return for a private holding | `GET /perf/desmoothed-returns/latest?portfolio_id=&instrument_id=` (`api/perf.py:1134`) | EXISTS (per instrument) |
| Unfunded commitments and projected calls | `GET /pacing/projections/latest?portfolio_id=&instrument_id=` (`api/pacing.py:396`) | EXISTS (per fund) |
| Scenario P&L | `GET /risk/scenario-results/latest` (`api/risk.py:3350`) | EXISTS |
| Exposure by factor, by sector, by currency, by asset class (amounts) | none; factor exposures are per instrument (`api/risk.py:982`), sector exists only as a share | MISSING, additive |
| Limit utilisation (observed over threshold, per limit) | none; only breach rows carry observed and threshold (`api/breaches.py:287`) | MISSING (LIM-3, declined to Wave 20 at DP-19-9) |
| One call: everything above for portfolio P as of date D | none | MISSING, additive (the 2026-07-20 deferral) |
| Contribution to VaR by position or factor | none; contribution-to-risk deferred since P3-3 | MISSING, an ENGINE (the Wave-20 spine already names risk decomposition) |

The private-asset view the differentiation thesis promises, reported risk beside desmoothed risk
for the private sleeve, is buildable from the first, seventh and twelfth rows today. Nothing in the
market shows that plainly. It should be on the first screen.

---

## Part 4 — The proposal

### 4.1 The yardstick: G5, the journey walk

A lesson is a gate, a trigger, or an explicit acceptance of recurrence (P7). The G2 bake-off
established that whether a document means what it says is a question a script cannot answer, and
the same holds one level up: whether a screen serves a persona is a question about meaning. So G5
has the G2 shape, a human act with deterministic bookkeeping that proves the act happened and
never claims to judge quality.

**The act.** At every slice close that claims a journey step, a person on the adjudicator roster
opens the deployed stack, walks the step as the named persona, and records a verdict.

**The bookkeeping.** `02_requirements/journey_walk_ledger.jsonl`, one row per walk:
`{uj, step, persona, walked_by, deployed_head, route, verdict, reasoning, walked_at}`. Verdicts
are WALKABLE or NOT WALKABLE; reasoning is at least 120 characters and must name what was on the
screen. A script, `scripts/check_journey_walks.py`, wired into `make check` and CI, checks
paperwork only:

- every slice remit declares the journey steps it makes walkable, or declares none with a
  written reason; an undeclared remit with no reason exits 2 (the empty-scope vacuity G2 found
  inside itself);
- a slice that declared a step may not merge until a WALKABLE row exists for that step, by a
  roster member, at a `deployed_head` that is an ancestor of the merge commit;
- a wave close review from Wave 20 on carries a `## Journey coverage (G5)` section listing the
  steps that became walkable, each cited to its ledger row; a wave that made nothing walkable
  writes NO NEW JOURNEY COVERAGE plus a sentence, and a close whose slices declared steps but
  whose ledger holds no WALKABLE rows for them fails.

**What G5 does not do.** It does not judge whether the screen is good. That is the walker's job,
and the walker is the owner until the owner names someone else. It never gets cited as a check on
product quality, on the P20 precedent.

**The DoD gains one criterion, D20:** "For a presentation requirement, the journey step it serves
is walked WALKABLE on the deployed stack by a roster member, ledger row cited." This is the first
user-perspective criterion the DoD has had.

### 4.2 The journeys, made concrete

The eight journeys of REQ-PERSONA-001 are the frame. Two are made concrete now, as the yardstick
for Wave 20. Each names the screen, the numbers on it, and the drill. They are written so a
walker can say yes or no to each line.

**J-CRO — "Monday morning" (UJ-2 step 1, PERSONA-01).** The CRO signs in and, without clicking
anything, sees the firm's books ranked by risk. For the selected book:

1. A headline row: total exposure in base currency; VaR and ES at the governed confidence and
   horizon with the as-of date; tracking error vs the benchmark; each a governed value with its
   provenance one click away.
2. Limit posture: how many limits are in force, how many breached, how many near threshold; the
   list of open breaches with owner and response due.
3. Exposure composition: by asset class, by currency, by sector, by factor family; public beside
   private.
4. The private sleeve, plainly: reported (appraisal) volatility beside desmoothed volatility, the
   uncertainty introduced stated in words, unfunded commitments and the next projected call.
5. Trend: the VaR series over the last quarter, the rolling drawdown, as charts on the page.
6. A drill: click the VaR headline and see what makes it up (Wave 20 delivers the first hop, by
   hierarchy node; the position-level hop needs the decomposition engine and is the Wave-20 spine).

**J-PM — "before the trade" (UJ-1 steps 2 to 4, PERSONA-03).** A portfolio manager entitled to one
book opens it and sees:

1. Holdings with marks as-of, sortable, with the mark date and any stale mark flagged.
2. The book's exposures by factor and by currency, and its share of the firm's limits, with
   utilisation as a number (observed over threshold) not a state word.
3. Any open breach in scope, with the first-line response form on the same page.
4. The same headline numbers the CRO sees, so the two never argue about a value.

The other six journeys keep their existing surfaces (the operations and administration screens
serve UJ-4 and UJ-5; the walk's content serves UJ-3 and UJ-7) and are re-walked under G5 as they
are touched, not retro-fitted.

### 4.3 The front-end restart

**Kept, product-agnostic:** the API client and refusal classifier, the staleness-guarded fetch
hook, the generated OpenAPI types and the drift gate, the decimal-as-string compile-time contract,
session and OIDC/PKCE handling, the governed-value primitive with its provenance strip, the pane
and validation-badge components, and the six root guard tests (write fence, router fence,
dependency fence, OpenAPI contract, audit gate, API prefixes). About 1,200 lines of source
plus 860 lines of guard tests.

**Replaced:** the route tree and nav, the walk, the run ledger as a primary surface, the
per-slice stylesheet with no design tokens, and the family registry's row-column views. The run
list and run detail pages survive as the provenance drill behind any governed value, reached from
the value, not from the nav.

**Introduced:** a design token set (one `:root` block, light and dark), a chart component
rendered in the browser from governed reads (the server-side SVG renderer stays for reports,
where byte identity matters), a portfolio selector in the shell, and the two journey screens.

**Not touched:** the write fence stays; no domain logic enters the UI; every number stays a
verbatim string.

### 4.4 The demo book

One tenant, one fund, one coherent book, seeded by one orchestrator that the deploy script runs
after the prepare step. Shape:

- a FUND root with four STRATEGY sleeves: public equity, fixed income, private equity, private
  credit; ACCOUNT leaves under each, in at least two base currencies;
- fifty to eighty instruments with plausible fictional names and real-shaped identifiers
  (fictional, so the demo never invites the question whether it is licensed market data);
- twelve months of daily prices, FX and factor returns, with the calendar the platform already
  ships; quarterly appraisals for the private funds with the desmoothing chain run; commitments,
  calls and distributions for each private fund with pacing projections;
- limits that a CRO would set (VaR ceiling, tracking-error ceiling, sector and issuer
  concentration, illiquid share) with two live breaches and one near-threshold;
- every governed family run at least once against the book, and the reproduction schedule live.

The ten per-stage DEMO-* books stay in the test battery, because their goldens must not move.
They stop being what a deployed stack holds. The test-data realism rule applies in full, and it
gains one line: names, counts and totals must be plausible too, not only values.

### 4.5 The wave sequence

**Wave 19 closes at this gate.** S3a and S3b are delivered. S1 is parked (4.6). S2 is deferred
behind a trigger (P19): "the first journey step that needs a report a fixed family set cannot
produce". S5, the deployed OIDC demo posture, moves to the end of Wave 20, because a CRO walking
the demo will do so over real identity.

**Wave 20 = "A CRO CAN USE IT".** Proposed order, each slice its own remit and gate under the
existing per-slice discipline plus G5:

| # | Slice | What it is | Journey steps | Size |
|---|---|---|---|---|
| 1 | **BOOK-1 — the demo book** | The 4.4 book, the orchestrator, the deploy hook, the realism amendment. No new engine; every family already exists. | none (it is what the others are walked over) | L |
| 2 | **CRO-1 — the CRO overview** | The restarted shell, tokens, portfolio selector, and J-CRO lines 1 to 5 over the reads in Part 3 marked EXISTS, plus the three additive aggregates (exposure by dimension; the one-call summary; utilisation as a number, realising LIM-3). No new governed number. | J-CRO 1-5 | L |
| 3 | **PM-1 — the PM book view** | J-PM lines 1 to 4 over the same reads, entitlement-scoped; the breach response form re-homed. | J-PM 1-4 | M |
| 4 | **DRILL-1 — the first hop** | REQ-PRS-004's first hop: headline VaR to hierarchy-node contributions, over the existing rollup read. The position-level hop waits for the decomposition engine. | J-CRO 6 (first hop) | M |
| 5 | **SHOW-1 — deployed OIDC posture** | Wave 19's S5, unchanged in content, walked by the owner over real identity as the wave's exit. | re-walk J-CRO, J-PM under OIDC | M/L |

Cut line: DRILL-1 first, then SHOW-1. The Wave-20 spine named at DP-19 (pricing → risk
decomposition) is not displaced; it becomes Wave 21, and DRILL-1's second hop is its first
consumer. New calculation families pause until a journey step needs one.

**Rule 7 gains its inverse.** Rule 7 says every governed number ships its entity and time reads
in the same slice. The inverse must be legitimate too: a slice that ships reads and screens over
existing numbers, minting no number, is a valid slice when it makes a journey step walkable. Today
the roadmap has no such slice shape, and that absence is one reason every wave reached for a new
engine.

### 4.6 The S1 branch

`w19-s1-present` holds four commits: the contracts, the dispatch, the chart renderer, proofs, a
review fold and the session log. Recommendation: **park it, unmerged.** The presentation contract
and the server-side renderer are the right substrate for reports and will be picked up when S2's
trigger fires; the outstanding Outcome 4 (a chart on the run-detail screen) builds a screen the
restart retires, so it is dropped rather than finished. REQ-PRS-001 and REQ-PRS-002 keep their
adjudications; their acceptance text is not edited by this record, so nothing lapses.

REQ-PRS-002's acceptance is complete as a description of evidence and silent on whether anyone
sees it. That is exactly the P20 shape ("describe an implementation that passes every clause and
does not deliver the stated purpose": a chart in an iframe on an ops page). It is proposed for
re-adjudication when CRO-1 enters scope, not now, because editing it now lapses a row that is not
in any slice.

### 4.7 The outward-facing check (Part 4 rule 6b)

What a CRO sees on the first screen of the incumbent risk platforms, stated from general
knowledge and not as a citation: a portfolio selector; a risk summary with VaR, ES or volatility
and tracking error; exposure decompositions by asset class, sector, country, currency and factor;
limit utilisation with breaches; scenario P&L; a time series; and a drill from any number to its
contributors. Every line of J-CRO maps to one of those. The platform's differentiator, the
private sleeve rendered honestly beside the public one with the desmoothing uncertainty stated, is
the one line on that list the incumbents do not have. This re-baseline does not change the
destination in the differentiation thesis. It changes what gets built first so the destination
can be seen.

---

## Part 5 — Decision points (Tier 3, the owner's)

| # | Decision | Recommendation |
|---|---|---|
| DP-RB2-1 | Direction: partial restart as Part 2 states, or start over | **Partial restart.** The spine is right and expensive; the surface is wrong and cheap. |
| DP-RB2-2 | Yardstick: adopt G5 (journey walk ledger, script, DoD D20) as a standing gate | **Adopt.** It is the G2 shape applied to the product; a human act with paperwork. Ratifying it is a standing-rule change and cannot be self-enacted. |
| DP-RB2-3 | Lead persona: CRO first, PM second | **CRO first.** The stated primary user is the second line, and the overview is the most reusable screen. |
| DP-RB2-4 | Rule 7 inverse: presentation-only slices are legitimate when they make a journey step walkable | **Adopt.** Without it the sequence has no slice shape for this work. |
| DP-RB2-5 | Demo book: one coherent fictional book replaces the deployed demo; the per-stage test books stay in the battery | **Adopt.** Fictional names, real-shaped identifiers. |
| DP-RB2-6 | S1 branch: park unmerged, drop Outcome 4, reuse the renderer for reports later | **Park.** Finishing it builds a screen the restart retires. |
| DP-RB2-7 | Wave 19: close now; S2 deferred behind a P19 trigger; S5 re-homed to the end of Wave 20 | **Close.** Leaving a half-wave open while the sequence changes underneath it is how carries go homeless. |
| DP-RB2-8 | Wave 20 sequence and cut line as 4.5 | **Adopt as written.** BOOK-1 first, because a screen over three positions cannot be judged. |
| DP-RB2-9 | Who walks: the owner is the sole G5 walker until named otherwise | **Owner.** The roster is `g2_adjudicators.json`; reuse it. |

Sub-questions Claude will decide and flag for reversal if the owner does not object: the design
token palette; the chart library (none, inline SVG in React, on the no-new-runtime-dependency
precedent); the orchestrator's name and CLI shape; the fictional naming scheme for the book.

---

## Part 6 — What the ratification commit must carry

In this order, on the P20 precedent that text lands before the ledger that hashes it:

1. This record's status block flipped to RATIFIED, with the owner's words quoted, and every
   "PENDING" phrase in it reconciled (the 2026-08-12 record still says "None is ratified" under a
   RATIFIED block; that is not repeated here).
2. `delivery_roadmap.md`: a Part 2.22 for Wave 20, the Part 2.21 status lines for S1/S2/S5, a
   Part 4 rule 8 (G5) and the rule 7 inverse, and a Part 5 row dated 2026-09-17. Also the Part 5
   row the 2026-08-12 re-baseline never wrote, dated and marked as written late.
3. `personas_and_user_journeys.md`: J-CRO and J-PM added under UJ-2 and UJ-1 as the concrete
   walks; "Last Reviewed" updated for the first time since 2026-06-18.
4. `definition_of_ready_done.md`: D20.
5. `claude_operating_instructions.md`: the G5 section and its index line; the rule 7 inverse.
6. The G5 script, its ledger file with a header and no rows, its make target, its CI wiring, and
   its controls, including the one that asserts the ledger is empty and instructs its own deletion
   at the first walk (the G4 precedent).
7. `current_state.md` CURRENT TRUTH rewritten: NEXT = BOOK-1.
8. `CLAUDE.md`: one line under the hard invariants pointing at G5.
9. The seven-ledger sweep, with "no control moved" stated explicitly if true.

Nothing in this list writes application code. BOOK-1 starts after the ratification PR merges.

---

## Part 7 — Different-engine verification (Fable 5.1)

*To be appended after the pass runs. Every finding is listed with its disposition; refuted
findings are kept, with the refutation, not deleted.*

---

## Part 8 — What this document does not decide

- Whether the front-end restart uses a component library. Recommendation: no, on the
  no-new-runtime-dependency precedent, but it is a build-time call at CRO-1 planning.
- The decomposition engine's design (the Wave-21 spine). DRILL-1's second hop consumes it; this
  record only sequences it.
- Whether the report family set (RPT-1 to RPT-3, S1's contracts) is re-aimed at the board journey
  UJ-6. That is the S2 trigger's question.
- Credit and counterparty, unchanged from the 2026-08-12 record.
- Any acceptance text. This record edits no requirement row. The rows it names for
  re-adjudication (REQ-PRS-002 and, when they enter scope, REQ-PPM-002 and REQ-LIM-002 for the
  journey clauses) are re-asked at the slice gate that first scopes them, under P20 T1.
