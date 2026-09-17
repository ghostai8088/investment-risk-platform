# Product re-baseline — 2026-09-17: a CRO cannot recognise it

**Status: RATIFIED 2026-09-17 by the owner** — "Proceed", all nine decision points in Part 5 as
recommended, after the brief that closed with the four decisions the owner was asked to read rather
than accept on trust (direction; the journey lines; the Wave-20 sequence; an outside walker).
Authored 2026-09-17 on `product-rebaseline-2026-09-17` by Claude (Opus 5) from four recon censuses
of the repository. Verified on a different engine before ratification (Fable 5.1, three fresh-context
lanes on the draft and a fourth on the fold) and folded; the full ledger is Part 7. No hash moves in
this record: it edits no acceptance text, and the G5 ledger it proposes is born empty. This is the
second re-baseline of the product; it exists because the first one, `product_rebaseline.md`
(2026-08-12), did not work, and Part 1 says why. **What the ratification commit carried is Part 6,
each item done; the close review is `10_delivery_backlog/wave_19_close_review.md`.**

**Why it exists.** On 2026-09-17 the owner opened the deployed demo and said: *"Wow, this is way
off."* Asked to state the purpose of the application, Claude gave the ratified answer (a
multi-tenant risk platform for asset managers spanning public and private assets, serving the
CRO, the risk manager, the portfolio manager and the board). The owner replied: *"I agree with
your interpretation of 'way off'. This is not something a CRO or PM would recognize. How do we
realign?"* and then: *"Should I start over instead of trying to fix this?"* The recommendation was
a partial restart, and the owner said "proceed". This record is the proposal.

**What the owner sees if they open the demo today.** One portfolio named DEMO-GLOBAL holding
three positions (400 shares of a fictional "ACME Corp", 300 of "EURX Industries AG", 50 units of
one private-equity fund), seeded by hand on 2026-08-25 because nothing in the deploy path seeds a
book at all. A landing page titled "How you can trust a governed number". A left nav with seven
operations screens, one admin screen, a six-step governance walk and a run ledger. There is no
screen anywhere that shows a portfolio's total risk, its exposures by factor or sector or
currency, or a limit utilisation figure. There is no chart in the deployed product. The only
chart that exists anywhere is a server-rendered SVG on the unmerged S1 branch, and there it is
visible only through a sandboxed iframe on the Reports operations screen. The numbers behind all
of this are real, governed and reproducible. Nobody can see them.

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

The first slice built under CAP-21 was Wave-19 S1, PRESENT-1, ratified 2026-09-05 (PR #240) and
built 2026-09-05 to 2026-09-17 on `w19-s1-present`. It delivered a presentation contract per
result family, a renderer-version dispatch, and a governed chart: a byte-identical inline SVG
emitted into report HTML and covered by the report content hash. It passed its census, its
mutation battery (13 of 13 killed), full-PG at 3,758 tests, and an adversarial review (39 raised,
38 confirmed, 2 BLOCKING: one folded, one left outstanding, Outcome 4, which this record drops). **No person can see the chart on any screen of the product
except through a sandboxed iframe on an operations page.** The slice is a faithful execution of
REQ-PRS-002, whose acceptance text is entirely about bytes, hashes, run ids and SVG element names
(`requirements_backbone.md:347`).

G3 was supposed to prevent this. Its test is "a HUMAN to see something or a RENDERED artifact to
be asserted on" (`requirements_backbone.md:339-340`). A rendered artifact asserted on by a test
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
`02_requirements/personas_and_user_journeys.md` (REQ-PERSONA-001). It names eleven persona rows
over ten PERSONA ids and eight journeys. UJ-1, the first-line daily risk review, reads in full:
authenticate; view positions and exposures as-of; run or inspect risk results; see limit
utilisation and any breaches; if breached, initiate a response (`personas_and_user_journeys.md:59-64`).
UJ-2 step 1 is "Review portfolio/aggregate risk and scenario results" (`:67`). Its own text says
"Journeys are the basis for per-phase user stories" (`:57`).

Measured on 2026-09-17: no user story was ever written. No document authored after June 2026
carries a `UJ-` id; outside the register and the RTM, the only citers of the journeys document are
the four June P1A plans and two slice records that cite its segregation-of-duties table. The 2026-08-12 re-baseline does not cite
it once. Neither does any wave planning record, any wave close review, the operating instructions,
or Parts 1 to 4 of the roadmap. The Definition of Done has one user-perspective criterion, D18
("Acceptance criteria demonstrably met; PO/2L sign-off where required",
`definition_of_ready_done.md:67`), which is bound to no trigger and has never fired; its only UI
clause is a prohibition (`:50`).

The one product-UI decision ever taken, FE-3's information architecture (OQ-FE-3-1, ratified
2026-07-21), was offered to the owner as a choice between "the platform's governance story as the
product narrative" and "a generic run browser" (`ui_read_surface_assessment.md:46`). No
persona-shaped option was on the table. The owner chose the better of two engineering options, and
that choice is what the product looks like today. The recommendation was Claude's.

### 1.4 Four measured facts underneath

1. **The read a dashboard needs most was deferred and never swept.** API-1 planning (2026-07-20)
   deferred "metric time-series + cross-family summary" to "a later fast-follow"
   (`api_1_decision_record.md:55`). No later record names it. It is a homeless carry of the P19
   class, written before P19 existed, and P19's clause B (the wave-close backstop) has run at the
   Wave 17 and 18 closes without finding it, because it lives in a decision record's scope line,
   not in a carry register.
2. **The engines exist and the aggregates do not.** 178 GET endpoints serve 20 calculation
   families across 22 run types; the test campaign registers 27 model codes against them. Per-portfolio latest reads exist
   for VaR, ES, tracking error, exposure total, concentration amounts and shares by sector,
   country and issuer, liquidity shares, rolling risk, Sharpe and returns (Part 3). There is no
   exposure aggregate by asset class, by currency or by factor family: factor exposures come back
   one row per instrument-and-factor (`api/risk.py:982`). There is no limit utilisation ratio
   anywhere in the backend (`api/limits.py:406` returns state, not observed-over-threshold, and
   carries no portfolio scope). There is no cross-family summary for one portfolio as of a date.
3. **Nothing deploys a demo book, and the position every close quotes has never been deployed.**
   `deploy.sh` migrates and seeds SYSTEM reference data only (`infra/deploy/deploy.sh:75`); no
   deploy, compose, Makefile or CI path invokes `scripts/run_demo_campaign.py`. That script runs
   only the base campaign (one three-position book). Nine extension stages have standalone CLI
   scripts; the remaining eighteen exist only as ordered PostgreSQL test modules, and no single
   orchestrator runs all twenty-seven. The 27/44/141 codes/validations/runs census, last measured
   at the Wave-15 close, has never been on a deployed database.
4. **The product surface is a ledger.** Of 15 routes, ten are operations or administration
   screens, three are the governance walk, and two are a run list and a run detail page whose
   columns are run ids, snapshot ids and model versions. The single "Value-at-Risk" heading in
   the product says: "VaR has no 'latest for portfolio P' resolver yet ... open one for its
   value" (`views/walk/NumbersStep.tsx:97-107`). That resolver shipped at API-1b (PR #92, merged
   2026-07-21). The screen was never updated.

### 1.5 What this is not

It is not a failure of the engines, the governance or the tests. About 105,000 lines of backend
and shared source, 77 migrations, 20 calculation families with cited methodology, symmetric
row-level security, a frozen audit service, reproduction on demand and 3,700 PostgreSQL-tier
tests are the hard part of an enterprise risk platform and they are built. It is not a failure of
effort on the front end either: 34,500 lines and 284 tests. It is a failure of the question every
gate asks. Eighteen closes asked "did we build it correctly"; the 2026-08-12 fix added "does the
register cover the taxonomy"; nobody has yet asked "can the CRO use it".

---

## Part 2 — The decision: a partial restart

**Keep** the backend, the shared package, the migrations, the tests, the governance documents,
the standing rules, and the front-end infrastructure that is product-agnostic (Part 4.3).

**Restart the presentation layer** as a persona-first product. The existing screens are reference
material. The operations and administration screens are kept because they serve real journeys
(UJ-4, UJ-5, and the second-line breach review in UJ-2), but they stop being the product's front
door.

**Replace the deployed demo book** with a coherent multi-fund tenant that a CRO would recognise,
seeded by one orchestrator as a deploy step.

**Change the yardstick.** A persona journey, walked line by line by a person on the deployed stack
and recorded with the decision it supports, becomes the acceptance test for every presentation
slice. The requirements register stays as the record of what the system does; it stops being the
only judge of whether the product is right.

**Why not start over.** The alternative was raised by the owner and weighed. A fresh repository
would discard the part that is right and, run under the same yardstick, would produce the same
drift later. The front end and the demo book are the parts that are wrong, and together they are
a fraction of the codebase. Part 4 is sized on that basis.

---

## Part 3 — What can be shown today, from reads that already exist

This table is the feasibility floor for the Wave-20 screens. Every path and every parameter was
verified against the router source on 2026-09-17, twice (author and verifier). A row marked
MISSING is a new read; every one of those is an additive aggregate over existing governed results
or a scoping of an existing read, not a new engine, except the last row.

| What a CRO or PM expects to see | Read that serves it today | Status |
|---|---|---|
| Portfolio VaR, latest, with confidence and horizon | `GET /risk/vars/latest?portfolio_id=&metric_type=VAR_PARAMETRIC` (`api/risk.py:1749`) | EXISTS |
| Portfolio ES | same read with `metric_type=ES_PARAMETRIC`; ES is a separate run, so one call per metric | EXISTS |
| Tracking error vs benchmark | `GET /risk/active-risk/latest?portfolio_id=` (`api/risk.py:2208`); refuses without pinned benchmark constituents | EXISTS |
| Total exposure in base currency | `GET /exposure/latest/sum?portfolio_id=&exposure_type=MARKET_VALUE` (`api/exposure.py:372`); 422 without the type, 409 on an empty book | EXISTS |
| Exposure by hierarchy node with currency translation | `GET /exposure/runs/{run_id}/rollup?node_id=` (`api/exposure.py:430`) | EXISTS (run-keyed) |
| Concentration by sector, country, issuer, as amounts and shares | `GET /concentration/results/latest?portfolio_id=` (`api/concentration.py:322`); rows carry gross, long, short and net amounts per bucket | EXISTS |
| Liquidity tiers | `GET /liquidity/results/latest?portfolio_id=` (`api/liquidity.py:154`) | EXISTS |
| Rolling return, volatility, drawdown | `GET /perf/rolling-risk/latest?portfolio_id=` (`api/perf.py:1227`) | EXISTS |
| Limit status per limit | `GET /limits/health` (`api/limits.py:406`), tenant-wide; scope by joining `GET /limits` on `scope_portfolio_id` | EXISTS (state only) |
| Open breaches in scope, with observed and threshold | `GET /breaches?open=true&portfolio_id=` (`api/breaches.py:532`) | EXISTS |
| Holdings with marks as-of | `GET /portfolios/{id}/holdings?valid_at=&include_marks=true&valuation_date=` (`api/holdings.py:138`); no staleness field | EXISTS |
| Portfolio tree as-of | `GET /portfolios/tree-as-of?at=` (`api/portfolios.py:175`) | EXISTS |
| Reported vs desmoothed volatility for a private holding | `GET /perf/desmoothed-returns/latest?portfolio_id=&instrument_id=` (`api/perf.py:1134`); the summary row carries `observed_stdev` and the desmoothed value; one call per fund | EXISTS (per instrument) |
| Unfunded commitments and projected calls | `GET /pacing/projections/latest?portfolio_id=&instrument_id=` (`api/pacing.py:396`); one call per fund | EXISTS (per fund) |
| Scenario P&L for portfolio P | `GET /risk/scenario-results/latest` (`api/risk.py:3350`) takes a scenario id and as-of only; no portfolio scope | PARTIAL, needs a scoped read |
| Exposure by asset class, by currency, by factor family (amounts) | none; `FACTOR_EXPOSURE.exposure_amount` is declared ADDITIVE (`aggregation/contracts.py:135-137`), so a server-side sum is contract-legal | MISSING, additive |
| Limit utilisation (observed over threshold, per limit, with trend) | none; REQ-LIM-002 (amended 2026-08-15) makes it a STORED governed number realising ENT-032 | MISSING, a governed number with a migration (LIM-3) |
| One call: everything above for portfolio P as of date D | none | MISSING, a composition (the 2026-07-20 deferral) |
| Contribution to VaR by node or position | none; `var_value` is declared NOT_AGGREGATABLE (`aggregation/contracts.py:161`) and `summed=true` is refused | MISSING, an ENGINE (the decomposition spine) |

The private-asset view the differentiation thesis promises, reported volatility beside desmoothed
volatility for the private sleeve, is buildable from the thirteenth row today, one call per fund.
Nothing in the market shows that plainly. It should be on the first screen.

---

## Part 4 — The proposal

### 4.1 The yardstick: G5, the journey walk

A lesson is a gate, a trigger, or an explicit acceptance of recurrence (P7). The G2 bake-off
established that whether a document means what it says is a question a script cannot answer, and
the same holds one level up: whether a screen serves a persona is a question about meaning. So G5
has the G2 shape: a human act with deterministic bookkeeping that proves the act happened and
never claims to judge quality.

The first draft of G5 had a P20 exploit, found by the verifier and recorded in Part 7 (A-B1): a
walker could describe five stacked tables of verbatim strings in 120 characters and pass. The
repair is that the walker does not describe the screen; the walker constructs a decision.

**The unit.** One verdict per numbered journey line (J-CRO-1, J-PM-3), never per journey or per
step.

**The act.** At every slice close that declares journey lines, a person on the roster opens the
deployed stack, walks each declared line as the named persona, and answers, in this form:

> *"Name the decision the persona would take from this screen today, and the value on the screen
> that drove it. If no decision follows from what is shown, the verdict is NOT WALKABLE."*

**The bookkeeping.** `02_requirements/journey_walk_ledger.jsonl`, one row per walked line:
`{line, line_hash, persona, walked_by, deployed_head, route, verdict, decision, driving_value,
reasoning, walked_at}`. WALKABLE requires non-empty `decision` and `driving_value` and reasoning
of at least 120 characters. `line_hash` is the hash of the journey line's text, computed with the
script's own `line_hash` (the writer computes it against the COMMITTED blob, never the working
tree, on the G2 rule; the script hashes the tree it runs in, which in CI is the commit), so
editing the line lapses every walk of it (the P20 T2 analogue). `scripts/check_journey_walks.py`,
a `make check` member and a CI step of its own (as G1 and G2 are: `ci.yml:909, 919`), checks
paperwork only:

- `02_requirements/journey_slice_scope.json` declares, at the slice gate, the journey lines the
  slice makes walkable and the front-end source directories that serve them, or declares none with
  a written reason; an empty declaration with no reason exits 2 (the vacuity G2 found inside
  itself);
- a slice that declared a line may not merge until a WALKABLE row exists for that line, by a
  roster member, whose `deployed_head` is an ancestor of the PR head and whose `line_hash` matches
  the committed text;
- a row is STALE, and the line must be re-walked, when any file under the declared source
  directories changed after `deployed_head`;
- a wave close review from Wave 20 on carries a `## Journey coverage (G5)` section listing the
  lines that became walkable; every listed line must have a WALKABLE ledger row on this lineage,
  or the close fails; a wave that made nothing walkable writes NO NEW JOURNEY COVERAGE plus a
  sentence. **What the script does not check, said plainly:** a close that OMITS a declared but
  unwalked line from its table passes, because the scope file is single-slice and overwritten and
  the gate cannot know what a whole wave declared. The close review's verifier lane checks the
  table against the roadmap's Journey-lines column for that wave (a P7 clause-b act, bound to
  the close);
- every WALKABLE row also carries a decision of at least forty characters, a driving value with a
  number in it, reasoning that is not filler, the persona the line belongs to, and an ISO date;
  and every declared source directory sits under the front end and exists at the commit being
  checked, because a directory that is not there makes the stale rule watch nothing (the
  ratification-diff verifier's attack, folded).

**What G5 does not do.** It does not judge whether the decision the walker named is a good one.
That is the walker's job. It never gets cited as a check on product quality, on the P20 precedent.
A gate script, its ledger and its controls are written in the ratification commit; that is the G2
and G4 precedent, and P18 applies (an entry-point test, and a control that asserts the ledger is
empty and instructs its own deletion at the first walk).

**The DoD's D18 is amended, not duplicated:** "for a presentation requirement, sign-off is a
WALKABLE G5 ledger row per journey line the slice declared". D18 was the user-perspective
criterion the DoD already had, bound to nothing.

### 4.2 The journeys, made concrete (RATIFIED as written, DP-RB2-3; the owner's text now lives in `personas_and_user_journeys.md`)

The eight journeys of REQ-PERSONA-001 are the frame. Two are made concrete now, as the yardstick
for Wave 20. Each line names what is on the screen and the decision it supports, so a walker can
answer the G5 question per line. **These lines are Claude's proposals.** The builder must not
author its own yardstick and then be measured against it, which is the P20 reason in one
sentence, so each line goes to the owner for ratification or rewriting (DP-RB2-3), and lands in
the personas document as the owner's text.

**J-CRO, "Monday morning" (UJ-2 step 1; P-CRO and P-RM, who share this screen per the persona
table).** The CRO signs in and sees the firm's funds, then one fund:

1. **Funds ranked by headroom**, tightest limit first, with the change since the last close beside
   each. Decision: which fund to open first.
2. **Headline row for the selected fund:** total exposure in base currency; VaR and ES at the
   governed confidence and horizon with the as-of date; tracking error vs the fund's benchmark;
   each a governed value with provenance one click away. Decision: is today's risk inside
   appetite.
3. **Limit posture:** limits in force, breached, and near threshold (utilisation at or above 80
   percent), with the open breaches, their owners and response due dates. Decision: which breach
   to chase. *Until UTIL-1 lands, this line shows state words, not a number, and is walked NOT
   WALKABLE by design.*
4. **Exposure composition:** by asset class, by currency, by sector, by factor family; public
   beside private on the same axis. Decision: where the concentration is.
5. **The private sleeve, plainly:** for each private fund, reported (appraisal) volatility beside
   desmoothed volatility with the difference as a number; unfunded commitment and the next
   projected call. Decision: whether the private book's risk is understated, and by how much.
6. **Scenario P&L** for the fund under the tenant's scenarios. Decision: which scenario hurts.
7. **Trend:** the VaR series over the last quarter and rolling drawdown, as charts. Decision: is
   risk rising.
8. **Drill:** click total exposure and see the hierarchy nodes and holdings that make it up, with
   the sum holding. Decision: which sleeve drives it. *The VaR drill waits for the decomposition
   engine (Wave 21) and is not a Wave-20 line.*

**J-PM, "daily review" (UJ-1 steps 2 to 4; P-PM).** A portfolio manager entitled to one fund
opens it and sees:

1. **Holdings with marks as-of**, sortable, with the mark date, and a mark flagged stale when
   older than the asset class's tolerance (one business day for listed instruments, one hundred
   for private funds; the tolerance is a server-side read, not a browser rule). Decision: which
   position needs a fresh mark.
2. **The fund's exposures** by factor family and by currency, and its utilisation of each limit
   that scopes it, as a number. Decision: how much room is left. *Same UTIL-1 dependency as
   J-CRO-3.*
3. **Any open breach in scope**, with the first-line response form on the same page. Decision:
   respond now or escalate.
4. **The same headline numbers the CRO sees** for this fund, walked by opening both screens.
   Decision: escalate if the two screens disagree on any value; the driving value is the pair
   compared.

Pre-trade what-if is not in UJ-1 and is not proposed; a CRO reading J-CRO will look for it and it
is named here as out of scope for Wave 20.

The other six journeys keep their existing surfaces (the operations and administration screens
serve UJ-4 and UJ-5; validation status and disclosed limitations, today the walk's steps 5 and 6,
are re-homed under the model inventory and the governed-value provenance drawer, serving UJ-3 and
UJ-7) and are re-walked under G5 as they are touched, not retro-fitted.

### 4.3 The front-end restart

**Kept, product-agnostic:** the API client and refusal classifier, the staleness-guarded fetch
hook, the generated OpenAPI types and the drift gate, the decimal-as-string compile-time contract,
session and OIDC/PKCE handling, the governed-value primitive with its provenance strip, the pane
and validation-badge components, and the six root guard tests (write fence, router fence,
dependency fence, OpenAPI contract, audit gate, API prefixes). About 1,300 lines of source plus
806 lines of guard tests.

**Retired:** the walk as a navigation surface and its three routes (ten front-end source files
reference them; no deployed proof does, verified in Part 7 F-17), the run ledger as a primary
surface, the per-slice stylesheet with no design tokens, and the family registry's row-column
views. The run list and run detail pages survive as the provenance drill reached from any governed
value, not from the nav; S1's Outcome 4 is dropped because the chart belongs on the journey
screens, not because the run-detail page goes.

**Introduced:** a design token set (one `:root` block, light and dark), a chart component
rendered in the browser from governed reads (the server-side SVG renderer on the S1 branch stays
the right tool for reports, where byte identity matters), a fund selector in the shell, and the
two journey screens.

**Not touched:** the write fence stays; no domain logic enters the UI (every threshold, tolerance
and sum in 4.2 is a server-side read); every number stays a verbatim string.

### 4.4 The demo tenant

One tenant, three funds, seeded by one orchestrator run as a separate deploy step **after** the
deploy verification (the verification asserts four seeded currencies and an empty tenant registry,
`deploy.sh:120, 161`, and the campaign would fail both). Shape, with every constraint the
feasibility lane found (Part 7 F-2, F-8, F-9, F-12, F-14, F-16, F-20) designed in:

- **three funds of different mandate** (a global multi-asset fund, a fixed-income fund, a
  private-markets fund of funds), so a ranking has a population, each a FUND root with STRATEGY
  sleeves and ACCOUNT leaves, in at least two base currencies, each root declaring its base
  currency;
- **fifty to eighty instruments** with plausible fictional names and real-shaped identifiers
  (fictional, so the demo never invites the question whether it is licensed market data);
- **a benchmark per fund with pinned constituents**, without which tracking error refuses;
- **a factor model with more than currency factors**, through the loadings family: captured
  loadings for every instrument-factor pair, so the flagship VaR sees an equity move; the
  currency-only path stays for the regression chain;
- **twelve months of market data**: weekly exposure boundaries across the year and daily
  boundaries for the last quarter (about sixty-three), each boundary with every instrument marked
  and every FX pair captured on that exact date, because one missing mark fails the run; the
  calendar captured into the tenant;
- **private funds with three years of quarterly appraisals ending before the marked year
  begins**, because the desmoothing binder pins every mark in its window with no frequency
  filter, so daily carry inside the window would pollute the appraisal series; one desmooth,
  regression and promotion chain per private fund; commitments, calls and distributions with a
  pacing projection per fund;
- **limits a CRO would set** on admitted targets only (VaR ceiling, tracking-error ceiling, sector
  and issuer concentration; liquidity is not an admitted limit target and is shown as a measure),
  scoped to the fund root, with two live breaches and one utilisation strictly between zero and
  threshold;
- **every governed family run** against each fund, with the run counts stated in the slice remit
  (the VaR trend alone is one covariance and one VaR run per boundary per metric per fund).

The ten per-stage DEMO-* books stay in the test battery, because their goldens must not move.
They stop being what a deployed stack holds. `08_testing_qa/test_data_realism.md` gains one line:
names, position counts and book totals must be plausible too, not only values.

### 4.5 The wave sequence

**Wave 19 closes at this gate, with a close review** (`wave_19_close_review.md`, Part 6 item 0)
carrying its G4 table for S3a and S3b, the P19 clause-B carry sweep, measured counts, and the rule
6b outward section. Its dispositions: S3a and S3b delivered; S1 parked (4.6); **S2 and ING-2 go
to the Wave-21 candidate list**, a sequenced host, because "the first journey that needs a report
a fixed family set cannot produce" is a judgement and P19 says a judgement is a decision, not a
trigger; S5 becomes SHOW-1 at the end of Wave 20; the ratified Wave-20 spine of DP-19-1 (pricing, risk
decomposition and derivative expressibility, `wave_19_planning.md:35`) becomes the Wave-21 spine, and DP-19-2's commissioned algorithm decision
stands unchanged.

**Wave 20 = "A CRO CAN USE IT".** Each slice has its own remit and gate under the existing
per-slice discipline plus G5. The XL was split on the ONBOARD-1 precedent.

| # | Slice | What it is | Journey lines | Size |
|---|---|---|---|---|
| 1 | **BOOK-1a — the public book** | The 4.4 tenant without its private sleeves: three funds, hierarchy, instruments, benchmarks, calendar, the loadings-family factor model, weekly boundaries, and every public family run; the orchestrator and the post-verification deploy step. No new engine. | none; it is what the others are walked over | L |
| 2 | **BOOK-1b — the private sleeves and the limits** | Appraisal history, desmoothing and regression chains, commitments and pacing, total and unified VaR, the limits with their breaches, and the daily last quarter. | none | M/L |
| 3 | **CRO-1 — the CRO overview** | The restarted shell, tokens, fund selector; J-CRO lines 1, 2, 4, 5, 6, 7 over the Part-3 reads; three additive reads: exposure by dimension, a portfolio-scoped scenario read, and the one-call summary. Line 3 shows state words until UTIL-1. No new governed number. | J-CRO-1, 2, 4, 5, 6, 7 | L |
| 4 | **UTIL-1 — utilisation as a governed number** | LIM-3 as its own slice: ENT-032 realised, migration, P17; every utilisation row carries portfolio scope, observed value and threshold, and the read carries a date range so the trend is visible; REQ-LIM-002's two open gaps (direction semantics; what a refused evaluation stores) resolved at its gate under P20 T1. | J-CRO-3, J-PM-2 | M |
| 5 | **PM-1 — the PM daily review** | J-PM lines 1 to 4, entitlement-scoped, including the stale-mark tolerance read and the breach response form re-homed. | J-PM-1 to 4 | M |
| 6 | **DRILL-1 — the exposure drill** | REQ-PRS-004's first realisation on the one measure that is additive: total exposure to nodes to holdings over the existing rollup read, sums holding. | J-CRO-8 | S/M |
| 7 | **SHOW-1 — deployed OIDC posture** | Wave 19's S5, unchanged in content; the wave's exit: J-CRO and J-PM re-walked over real identity. Not cuttable. | re-walk all | M/L |

Cut line: DRILL-1 only. New calculation families pause until a journey line needs one; that is a
sequencing rule and part of DP-RB2-7.

**On slice shape.** The first draft claimed the roadmap had no shape for a read-and-screen-only
slice. That was false: API-1, API-1b, FE-2, FE-3, OPS-1 and RPT-3 were exactly that. The gap was
never slice shape; it was that no such slice ever had a journey-shaped acceptance. Rule 7 stands
unamended.

### 4.6 The S1 branch

`w19-s1-present` holds four commits: the contracts, the dispatch, the chart renderer, proofs, a
review fold (which fixed a live injection) and the session log. **Park it, unmerged.** The
presentation contract and the server-side renderer are the right substrate for reports and are
picked up if and when the Wave-21 planning gate sequences S2 (that gate is the decision moment;
S2 is a candidate, not a sequenced slice); by then the route census and the migration head will
have moved, so resuming is a rebase of a full slice. That is accepted here explicitly (a P7 clause-c
acceptance) rather than left to be discovered. REQ-PRS-001 and REQ-PRS-002 keep their
adjudications; their acceptance text is not edited by this record.

`g2_slice_scope.json` still declares `WAVE-19-S1` as the slice entering build. The ratification
commit flips it to a declared no-scope with the reason "the declared slice was parked unmerged at
the 2026-09-17 re-baseline", on the demo-fix precedent; BOOK-1a declares its own scope at its
gate.

REQ-PRS-002's acceptance is complete as a description of evidence and silent on whether anyone
sees it. That is exactly the P20 shape. It is proposed for re-adjudication when CRO-1 scopes it,
not now, because editing it now lapses a row that is in no slice.

### 4.7 The outward-facing check (Part 4 rule 6b)

The first draft wrote this section "from general knowledge and not as a citation", which
sidesteps rule 6a's verbatim-quote requirement by declaring itself exempt. That is not acceptable
and it is not repaired here, because it cannot be repaired honestly in this session. **Recorded as
a P7 clause-b act with a trigger:** before CRO-1's planning gate, an outward benchmark section is
written with at least two publicly available vendor or regulatory sources quoted verbatim with
locators, read by a citation lane that sees only the sources, on the rule 6a pattern. Until then,
the J-CRO lines rest on the owner's ratification (DP-RB2-3), not on an outward claim.

---

## Part 5 — Decision points (Tier 3, the owner's — ALL RATIFIED AS RECOMMENDED 2026-09-17)

| # | Decision | Recommendation |
|---|---|---|
| DP-RB2-1 | Direction: partial restart as Part 2 states, or start over | **Partial restart.** The spine is right and expensive; the surface is wrong and cheap. |
| DP-RB2-2 | Yardstick: adopt G5 as in 4.1 (per-line verdicts, the decision-and-value question, the lapse hash, the stale rule, D18 amended) as a standing gate | **Adopt.** A standing-rule change; it cannot be self-enacted. |
| DP-RB2-3 | The journey lines J-CRO-1 to 8 and J-PM-1 to 4: ratify each as written, rewrite it, or strike it | **Ratify as written, or rewrite in your own words.** They are proposals; the owner authors the yardstick, not the builder. |
| DP-RB2-4 | The demo tenant as in 4.4: three fictional funds, appraisal history before the daily year, post-verification seeding; per-stage books stay in the battery | **Adopt.** |
| DP-RB2-5 | S1: park unmerged, drop Outcome 4, accept that resumption is a rebase; flip the G2 scope to a declared no-scope | **Park.** Finishing it builds a chart on a screen no journey line reaches. |
| DP-RB2-6 | Wave 19: close now with a close review; S2 and ING-2 to the Wave-21 candidate list; S5 becomes SHOW-1; the DP-19-1 spine becomes Wave 21's | **Close.** A judgement-shaped trigger is a decision under P19, so S2 gets a sequenced host, not a trigger. |
| DP-RB2-7 | Wave 20 sequence, sizes and cut line as 4.5, and the pause on new calculation families until a journey line needs one | **Adopt as written.** BOOK-1a first, because a screen over three positions cannot be judged. |
| DP-RB2-8 | The grain of the three CRO-1 aggregate reads (exposure by dimension, scoped scenario, one-call summary): unbound reads or governed derived numbers | **Unbound reads**, each a server-side sum over a measure the aggregation contract declares ADDITIVE, each response carrying the run ids it summed, never persisted, never citable, fenced by CTRL-039. A stored aggregate would be a new governed number per dimension and would repeat the pattern this record exists to stop. |
| DP-RB2-9 | Walkers: the owner is the roster today; and the P15 question, whether one walk by a practising risk manager or portfolio manager who did not build the product happens before SHOW-1 closes | **Owner walks every line; add one outside walk before SHOW-1 closes**, or record an explicit recurrence acceptance that the sole walker shares the builder's assumptions. |

Sub-questions Claude will decide and flag for reversal if the owner does not object: the design
token palette; the chart approach (inline SVG in React, no new runtime dependency); the
orchestrator's name and CLI shape; the fictional naming scheme for the tenant.

---

## Part 6 — What the ratification commit carries (DONE 2026-09-17, on this branch)

No hash moves in this record, so the two-commit rule does not apply; the order below is the
dependency order.

0. `10_delivery_backlog/wave_19_close_review.md`: the G4 table (S3a, S3b), the P19 clause-B carry
   sweep naming S1, S2, S5, ING-2 and the DP-19-1 spine with their hosts, counts measured on a
   fresh battery, and the rule 6b section pointing at 4.7's trigger.
1. This record's status block flipped to RATIFIED with the owner's words quoted, and every
   "pending" phrase in it reconciled. (The 2026-08-12 record's §7 was never reconciled with its
   §3 ratification; that is not repeated.)
2. `delivery_roadmap.md`: Part 2.21 status lines for S1, S2, S5, and the PR stamps S3a and S3b
   never received (PR #234, PR #236); a Part 2.22 for Wave 20; a Part 4 rule 8 for G5; a Part 5
   row dated 2026-09-17; and the Part 5 row the 2026-08-12 re-baseline never wrote, dated and
   marked as written late.
3. `personas_and_user_journeys.md`: J-CRO and J-PM as ratified under UJ-2 and UJ-1; "Last
   Reviewed" updated for the first time since 2026-06-18.
4. `definition_of_ready_done.md`: D18 amended.
5. `08_testing_qa/test_data_realism.md`: the names-counts-totals line.
6. `claude_operating_instructions.md`: the G5 section and its index line.
7. The G5 script, the empty ledger with its header, `journey_slice_scope.json` with a declared
   no-scope, the make target, the CI step, and the controls (entry-point test; the empty-ledger
   control that instructs its own deletion; the empty-scope refusal), plus one control added to
   the G4 gate: refuse when the roadmap's latest closed wave has no close review, the vacuity the
   verifier found in it.
8. `g2_slice_scope.json` flipped to a declared no-scope (4.6).
9. `current_state.md` CURRENT TRUTH rewritten: NEXT = BOOK-1a.
10. `CLAUDE.md`: one line under the hard invariants pointing at G5.
11. The seven-ledger sweep, with "no control moved" stated explicitly if true.

Application code in this list: the G5 script and its controls, and one control on the G4 script.
Nothing else. BOOK-1a starts after the ratification PR merges.

---

## Part 7 — Different-engine verification (Fable 5.1, three lanes, 2026-09-17)

Four fresh-context lanes: three on the first draft (`5ab0dab`), a fourth on the fold (`8fe5578`; its ten findings are folded in this text and listed as Lane G), and a fifth on the RATIFICATION DIFF (`06acc39`; Lane R at the end): A, an adversarial governance read; F, a
feasibility read of Part 3 and Part 4 against the code; C, a citation-and-count check. Totals:
**6 BLOCKING, 23 HIGH, 19 MED, 13 LOW, 61 in all.** Every finding is listed; the disposition names where the
fold landed. Two findings were refuted in part and are kept with the refutation.

### Lane A — adversarial governance (4 BLOCKING, 9 HIGH, 7 MED, 3 LOW)

| # | Finding | Disposition |
|---|---|---|
| A-B1 | G5 had a P20 exploit: five stacked tables of verbatim strings, a 120-character description, WALKABLE. | FOLDED: per-line verdicts; the decision-and-value question; `decision` and `driving_value` required (4.1). |
| A-B2 | DRILL-1 was false at its own citation: no VaR-by-node read exists; VaR is NOT_AGGREGATABLE. | FOLDED: DRILL-1 is the exposure drill; VaR drill is a Wave-21 line (4.2 line 8, 4.5). |
| A-B3 | CRO-1 claimed "no new governed number" while realising LIM-3, which REQ-LIM-002 makes a stored number with a migration. | FOLDED: UTIL-1 is its own slice; CRO-1 line 3 shows state until it lands (4.5). |
| A-B4 | "Wave 19 closes" with no close review; G4 goes green by omission; P19-B never runs; carries minted homeless. | FOLDED: Part 6 item 0; a G4 control for the missing-review vacuity; S2/ING-2/spine given hosts (4.5). |
| A-H1 | The builder authored the journeys and would be measured against them; the outward check cited nothing. | FOLDED: DP-RB2-3; 4.7 is a trigger-bound act, not a claim. |
| A-H2 | P15 in the sole walker. | FOLDED: DP-RB2-9. |
| A-H3 | G5 had no lapse. | FOLDED: `line_hash` and the stale rule (4.1). |
| A-H4 | "Ancestor of the merge commit" is unimplementable at check time; no scope file. | FOLDED: ancestor of the PR head; `journey_slice_scope.json` (4.1). |
| A-H5 | DP-RB2-4's premise was false: read-only and screen-only slices exist. | FOLDED: DP removed; stated in 4.5. |
| A-H6 | Three internal contradictions (walk retired vs kept; run-detail survives vs retired; SHOW-1 as exit while cuttable). | FOLDED: 4.2 last paragraph, 4.3, 4.5 (SHOW-1 not cuttable). |
| A-H7 | J-CRO unwalkable over a one-fund tenant with no benchmark, no factor model, one VaR point. | FOLDED: 4.4 three funds, benchmarks, loadings model, daily last quarter. |
| A-H8 | Six decisions silently made (aggregate grain; spine displaced; ING-2 dropped; realism amendment homeless; family pause; S2 trigger a judgement). | FOLDED: DP-RB2-6, 7, 8; Part 6 item 5. |
| A-H9 | A CRO would object: rank by headroom and change, not raw VaR; scenario missing; uncertainty as a number; "primary user is second line" unsourced. | FOLDED: J-CRO lines 1, 5, 6; the unsourced claim removed. |
| A-M1 | `g2_slice_scope.json` left pointing at a parked slice. | FOLDED: 4.6, Part 6 item 8. |
| A-M2 | S3a and S3b carry no PR stamp in Part 2.21. | FOLDED: Part 6 item 2. |
| A-M3 | Status block claimed a verification that had not run; two-commit rule invoked with no hash. | FOLDED: status block and Part 6 preamble. |
| A-M4 | D18 already exists as a user-perspective criterion; cited line was the table header. | FOLDED: 1.3, D18 amended not duplicated. |
| A-M5 | Vague journey lines any screen passes. | FOLDED: thresholds and decisions per line (4.2). |
| A-M6 | Parking S1 leaves a fold and a future rebase with no host. | FOLDED: explicit acceptance (4.6). |
| A-M7 | DP-RB2-3 and DP-RB2-9 were not decisions. | FOLDED: old DP-3 merged into DP-7; DP-9 rebuilt around P15. |
| A-L1 | "Writes no application code" was false (a gate script). | FOLDED: Part 6 closing line. |
| A-L2 | LIM-3 "declined" vs "folded into CRO-1". | FOLDED: UTIL-1. |
| A-L3 | Could not find g2-check in CI. | REFUTED IN PART: CI runs the scripts directly (`ci.yml:904, 914`), not the make targets; G5 is wired the same way (4.1). |

### Lane F — feasibility (2 BLOCKING, 11 HIGH including the sizing finding, 4 MED, 4 LOW)

| # | Finding | Disposition |
|---|---|---|
| F-1 | No read decomposes VaR by node (`contracts.py:161`; `risk.py:1749-1770`). | FOLDED with A-B2. |
| F-2 | Daily marks on a private fund pollute its own desmoothing window (`snapshot/service.py:2426-2431`); the campaign avoids it only by ending the window early. | FOLDED: appraisal history ends before the daily year (4.4). |
| F-3 | `/risk/vars/latest` returns one metric per call. | FOLDED: Part 3 rows 1 and 2. |
| F-4 | `/exposure/latest/sum` needs `exposure_type`; 409 on empty. | FOLDED: Part 3. |
| F-5 | `/limits/health` is tenant-wide, no observed or threshold. | FOLDED: Part 3; UTIL-1 must carry scope, observed, threshold. |
| F-6 | Scenario latest has no portfolio scope. | FOLDED: Part 3 PARTIAL; CRO-1's scoped read. |
| F-7 | Holdings read misdescribed; no staleness field; "stale" in the browser would breach the UI fence. | FOLDED: Part 3; J-PM-1 tolerance is a server read. |
| F-8 | Illiquid-share limit cannot be created (limit targets are VaR, tracking error, concentration). | FOLDED: 4.4. |
| F-9 | Flagship factor model is currency-only; wider path needs captured loadings per pair and one regression chain per private fund. | FOLDED: 4.4. |
| F-10 | Seeding before deploy verification breaks `deploy.sh:120, 161` and `prove_backup_restore.sh:56`. | FOLDED: post-verification step (4.4). |
| F-11 | "No orchestrator" overstated (nine per-stage CLIs); the stronger fact: nothing in the deploy path seeds any book. | REFUTED IN PART, then FOLDED: preamble and 1.4(3). |
| F-12 | Tracking error refuses without pinned benchmark constituents. | FOLDED: 4.4. |
| F-13 | Sector and country amounts DO exist in concentration rows; by-factor-family is contract-legal to sum. | FOLDED: Part 3 and 1.4(2) corrected; sums server-side (DP-RB2-8). |
| F-14 | The VaR trend is one covariance and one VaR run per boundary per metric per fund. | FOLDED: 4.4 run counts in the remit. |
| F-15 | Desmoothed and pacing reads are one call per fund. | FOLDED: Part 3. |
| F-16 | Calendar is a per-tenant capture; v2 rolling and Sharpe refuse without it. | FOLDED: 4.4. |
| F-17 | No deployed proof or CI stack-proof touches the walk or the nav; ten FE files reference `/walk`. | NOTED: 4.3; safe to retire. |
| F-18 | Flat books not required; multi-currency leaves fine; stage 26 already builds FUND→STRATEGY→ACCOUNT. | NOTED. |
| F-19 | The 10 MiB cap is irrelevant to an in-process orchestrator. | NOTED. |
| F-20 | A limit on the fund root sees only runs scoped to the root. | FOLDED: 4.4 "scoped to the fund root". |
| F-size | BOOK-1 "L" optimistic (exact-date pin: thousands of audited marks, hundreds of runs); CRO-1 "L" hides LIM-3 and scope mismatches. | FOLDED: BOOK-1 split; UTIL-1 separate; weekly plus daily last quarter. |

### Lane C — citations and counts (0 BLOCKING, 3 HIGH, 8 MED, 6 LOW; 92 claims checked)

| # | Finding | Disposition |
|---|---|---|
| C-H1 | The SVG chart is not in the deployed product at all; it exists only on the S1 branch. | FOLDED: preamble. |
| C-H2 | "25 governed families" has no registry source: 22 run types, 20 calculation families, 27 model codes. | FOLDED: 1.4(2), 1.5. |
| C-H3 | The 27/44/141 census is quoted at the Wave 14 and 15 closes only, not "every close"; "27-model" means model codes. | FOLDED: 1.4(3). |
| C-M1 | Nine per-stage CLIs exist. | FOLDED with F-11. |
| C-M2 | 15 routes, ten ops and admin. | FOLDED: 1.4(4). |
| C-M3 | API-1b merged 2026-07-21. | FOLDED. |
| C-M4 | The test count was wrong. | FOLDED: 284 (measured at HEAD by the fold-check lane; the citation lane's 274 was itself wrong). |
| C-M5 | Eighteen close reviews, not seventeen. | FOLDED: 1.5. |
| C-M6 | Eleven persona rows over ten ids. | FOLDED: 1.3. |
| C-M7 | DoD D1 is line 50. | FOLDED. |
| C-M8 | Kept source about 1,300 lines; guard tests 806. | FOLDED: 4.3. |
| C-L1 | Backend source about 105,000 lines. | FOLDED: 1.5. |
| C-L2 | `UJ-` citers: the four June P1A plans and two SoD citations. | FOLDED: 1.3. |
| C-L3 | Holdings call as written returns 422. | FOLDED with F-7. |
| C-L4 | G3 quote spans lines 339-340. | FOLDED. |
| C-L5 | "39-finding review" is 39 raised, 38 confirmed, 2 BLOCKING. | FOLDED: 1.1. |
| C-L6 | The 2026-08-12 status block scopes RATIFIED to §3; §7 was never reconciled rather than contradictory. | FOLDED: Part 6 item 1 wording. |

**What the pass did that reading could not.** Every BLOCKING was a claim the argument depended on
that the code refuted: a drill over a read that does not exist, a slice labelled "no new number"
that realises an entity, a wave closed with no close review, a gate with the exploit it was built
to catch, a demo book whose private sleeve would corrupt its own desmoothing, and a screen that
could not be walked over the tenant proposed for it. None was visible from the draft. The
draft's author had the same recon the verifiers had.

---

### Lane G — the fold check (0 BLOCKING, 1 HIGH, 5 MED, 4 LOW; 61 dispositions and 41 new claims checked)

| # | Finding | Disposition |
|---|---|---|
| G-H1 | J-PM-4 had "Decision: none" and so could never be WALKABLE, yet PM-1 declared it. | FOLDED: J-PM-4 now names its decision (4.2). |
| G-M1 | Part 7's totals did not sum to its rows (F-size had no severity; 61 rows against "60"). | FOLDED: F-size is HIGH; totals re-summed to 61. |
| G-M2 | "274 tests" wrong; HEAD runs 284, and the roadmap already said so. | FOLDED: 1.5 and C-M4. The citation lane's own correction was wrong; a re-measurement is not right because it is a re-measurement. |
| G-M3 | S1's review described as fully folded; its fold commit left one BLOCKING outstanding. | FOLDED: 1.1. |
| G-M4 | F-5's disposition claimed a UTIL-1 requirement 4.5 did not carry. | FOLDED: the UTIL-1 row. |
| G-M5 | "Two findings refuted in part" but one row said so. | FOLDED: F-11 marked. |
| G-L1 | "27 registered model codes" has no registry; it is the test campaign's census. | FOLDED: 1.4(2). |
| G-L2 | The register and the RTM also cite the journeys document. | FOLDED: 1.3. |
| G-L3 | "daily-marked year" contradicted the weekly-plus-daily bullet. | FOLDED: 4.4. |
| G-L4 | The DP-19-1 spine was abbreviated. | FOLDED: 4.5. |

**Verified by the fold lane and not listed:** every other FOLDED disposition lands where it says;
all forty-one new numbers and locators hold; the cut line, the slice numbering and the journey
line ids are consistent across 4.2, 4.5, Part 5 and Part 7.

---

### Lane R — the ratification diff (0 BLOCKING, 1 HIGH, 5 MED, 7 LOW; 19 P20 attacks executed against the gate, 7 passed when they should not)

| # | Finding | Disposition |
|---|---|---|
| R-H1 | A declared `source_dirs` entry that does not exist (or is blank, or is elsewhere) defeats the STALE rule: `git diff -- <nothing>` exits 0 empty. | FOLDED: refused under the front end only, no `..`, and must exist at the commit being checked (Structural); three controls; mutants M-G5-9, M-G5-10. |
| R-M1 | `decision: "."`, `driving_value: "n/a"`, filler reasoning pass. | FOLDED: floors (forty characters; a digit; twenty distinct characters); three controls; mutants M-G5-11, M-G5-12. |
| R-M2 | The G5 heading was found by substring; a prose mention hijacked the check. G4 had the same pattern. | FOLDED in both gates: line-anchored, exactly one; controls in both suites; mutants M-G5-14, M-G4-6. |
| R-M3 | The record claimed the hash is computed "against the committed blob"; the script reads the working tree. | FOLDED: the claim now says who computes what against what (4.1); the script is unchanged, CI runs on the commit. |
| R-M4 | 4.1 overstated the close check (omission of a declared line is not detected; no citation is checked). | FOLDED: 4.1 says what the script does and does not do; the omission check is a P7 clause-b act on the close review's verifier lane. |
| R-M5 | PR #240 stamped with its head SHA in three places; every other stamp is the merge commit. | FOLDED: `f3bfbee` (head `e992861`) in all three. |
| R-L1 | The G4 roadmap regex would miss an unnumbered Part-2 header. | FOLDED: an unnumbered Part-2 header is a Structural refusal; control; mutant M-G4-7. |
| R-L2 | `persona`, `walked_at`, `route` unvalidated. | FOLDED: vocabulary, line-prefix agreement, ISO date, leading slash; three controls; mutant M-G5-13 (re-anchored once: the vocabulary check alone was subsumed by the prefix chain). |
| R-L3 | A bolded id in a G5 table false-failed. | FOLDED: matcher aligned; control. |
| R-L4 | Close claims bound to `walked_any`, which admitted walks outside the lineage. | FOLDED: the ancestor check precedes `walked_any`; control. |
| R-L5 | `ci.yml:904, 914` moved to 909, 919 after the `fetch-depth` insert. | FOLDED. |
| R-L6 | Part 7's heading said three lanes; four were listed. | FOLDED. |
| R-L7 | Carry 1 (S1) chained to a candidate, not a sequenced host. | FOLDED: the Wave-21 planning gate is named as the decision moment (4.6; close review carry 1). |

Two mutants written for this fold were EQUIVALENT on first run and re-anchored, both recorded in
`mutants.toml`: M-G5-1 (the floors subsumed the emptiness check) and M-G5-13 (the prefix chain
subsumed the vocabulary check). A mutant that survives because another line catches the same
attack is not a survivor; it is a mutant aimed at the wrong site, and the site was moved.

---

## Part 8 — What this document does not decide

- Whether the front-end restart uses a component library. Recommendation: no, on the
  no-new-runtime-dependency precedent, but it is a build-time call at CRO-1 planning.
- The decomposition engine's design (the Wave-21 spine). J-CRO's VaR drill consumes it; this
  record only sequences it.
- Whether the report family set (RPT-1 to RPT-3, S1's contracts) is re-aimed at the board journey
  UJ-6. That is S2's question when it enters Wave 21.
- The outward benchmark content (4.7), which lands before CRO-1's gate under its trigger.
- Credit and counterparty, unchanged from the 2026-08-12 record.
- Any acceptance text. This record edits no requirement row. The rows named for re-adjudication
  (REQ-PRS-002 at CRO-1; REQ-LIM-002 at UTIL-1; REQ-PPM-002 and REQ-PRS-004 when scoped) are
  re-asked at the slice gate that first scopes them, under P20 T1.
