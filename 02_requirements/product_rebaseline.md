# Product re-baseline — 2026-08-12

**Status: §3 RATIFIED 2026-08-12** — the owner accepted all ten recommended answers ("proceed with
your recommended answers to the 10 questions"). §4's requirement set remains PROPOSED and is not
adopted until it is written into the backbone as rows with testable acceptance criteria, which is
the work §5 sequences. §6's first gate is built, proven and merged.

**The three answers that ratify a LOSS, recorded here so they cannot later read as oversights:**

1. **Monte Carlo leaves the governed spine** (Q1). Simulated exposure profiles — EPE, EEPE, peak
   PFE — and path-dependent exotics are permanently out. This CONTRADICTS a ratified requirement
   specifying seeded Monte Carlo; that requirement is superseded by this ratification, and the
   supersession must be annotated at the requirement itself, not only here.
2. **Counterparty risk is declined** behind named triggers (Q6), which follows from (1).
3. **The report sign-off rail is deferred** (Q9), so the platform carries a visible half-mint and
   two ratified documents promising a control it has not built. An assessor reading the segregation
   model will find it. That is accepted, not hidden.

**Why it exists.** After eight weeks and seventeen delivery waves, the owner reviewed the build and
said: *"The math and visualization need to be the star of the show. This needs to be flexible
enough to handle any product type, fund/portfolio/sleeve structure, and across publics and
privates. Best in class on both sides of analytics and control. How did we get so off track that
the way it was built was antithetical to the original plan?"*

This document answers that question, states what the requirement set should have said, and installs
the gates that make the failure mechanically detectable rather than dependent on someone noticing.

**Evidence base.** Three adversarial multi-agent runs (13, 13 and 21 agents), each finding
independently verified by the builder before it appears here. Two questions were answered by
EXECUTED SPIKE rather than argument, and their measured numbers are quoted in §3.

---

## 1. What happened

The delivery process draws work from `requirements_backbone.md`. That register is a disciplined
instrument and it under-specified exactly the two things the owner said were the point.

**The mechanism, precisely: the acceptance criteria were satisfiable without delivering the stated
purpose.** Two rows carry the whole story.

| Requirement | Business purpose | Acceptance criterion |
|---|---|---|
| REQ-PPM-004 | "Roll up exposures across hierarchy" | "Aggregates reproduce within tolerance and bind lineage" |
| REQ-MKT-003 | "Attribute risk to factors" | "Contributions sum to total within ε" |

Neither acceptance criterion mentions the thing its requirement exists for. An aggregation that
rolls up *nothing* reproduces perfectly. An allocation identity sums to total *trivially* —
REQ-MKT-003's own status column admits "contribution-to-risk deferred". **No test consumes a
business-purpose column.** A test-driven process tests acceptance criteria, so it built exactly
what could pass, correctly, for seventeen waves.

Three structural facts underneath it, each measured:

1. **No address.** The register declares twenty domain codes. None is presentation or exploration.
   "Visualisation" occurs twice in the whole file (`:79`, `:248`) and both are lineage diagrams.
   Work with no address in the taxonomy cannot be selected by a process that selects from it.
2. **The acceptance vocabulary is reproducibility-only.** Of 74 rows, **22 mention reproduction or
   identity; 2 mention a human seeing anything.** The Definition of Done has nineteen criteria and
   exactly one mentions the UI — as a prohibition ("no domain logic in the UI layer").
3. **The strategy's own vocabulary is spoken nowhere.** `SCOPE-01`…`SCOPE-05`, including SCOPE-02's
   "public and private, both first-class", are cited in exactly one file: their own. A commitment
   nothing downstream references cannot be traced, gated, or noticed when it goes unbuilt.

**The build is not a departure from its instrument. It is a faithful execution of it.**

And the review process could not have caught it. Seventeen wave closes asked *"did we build this
correctly?"* — mutation batteries, adversarial reviews, quoted exit codes. None asked *"is this the
right thing to build?"* Every audit compared code against requirements or records against code; the
register was the yardstick in all of them, and the register was where the gap was. **An audit whose
reference point is the artifact carrying the defect cannot see the defect.** §6 fixes that
specifically.

---

## 2. Where the platform actually stands

Measured, not asserted. 62,284 backend lines: 40% risk/performance mathematics, 33% data model and
ingestion, 23% governance and control, 1% reporting. Plus 7,311 frontend lines with **zero charts**
(runtime dependencies are exactly `react`, `react-dom`, `react-router`).

The shape of the 40% is the problem: **21 calculation families built one inch deep** rather than
eight families built a foot deep. Each was built to exactly the depth its acceptance criterion
demanded.

### LEADS — genuinely ahead of Aladdin, MSCI/Barra, Axioma, PORT, FactSet, Charles River, SimCorp

- **Reproducibility as an executed control.** 19 of 21 families re-executed nightly through
  production code against stored inputs, inside a rolled-back transaction. No incumbent does this;
  several cannot, because their numbers were never bound to a frozen copy of their inputs.
- **Model governance inside the compute path.** A calculation refuses to start if the model version
  is unregistered, rejected, or on an expired exception. In the industry the model inventory lives
  in a separate governance tool and the engine cannot see it.
- **Exact decimal arithmetic.** 30 kernels, 5,873 lines, zero floating point, zero
  numpy/pandas/scipy in production. Unfashionable, and it is what underwrites the ten-year
  reproducibility claim — see §3 Q1, where it is now evidenced rather than asserted.
- **Append-only by construction.** Of 305 operations: 171 read, 131 append, and exactly one PUT,
  one PATCH, one DELETE — none of which touches a calculated number.
- **Private-asset treatment.** Commitments, calls, distributions, proxy weights, pacing,
  desmoothing. Genuinely differentiated and rare.

### LAGS — and these are the re-baseline

| Gap | Measured state |
|---|---|
| Risk decomposition | **Zero code repo-wide.** No component VaR, marginal VaR or risk contribution. The first question on any risk desk each morning is unanswerable |
| Derivatives | Instrument terms carry seven bond fields. Zero matches for strike, expiry, option type, underlying, notional. **A derivative cannot be expressed**, against SCOPE-02's "first-class" |
| Scenarios | `SHOCK_TYPES = frozenset({RETURN})`; `SUPPORTED_FACTOR_FAMILIES = (CURRENCY,)`. **One of ten declared factor families, one of two shock types** |
| VaR horizon | `VAR_HORIZON_DAYS = 1`, hard-enforced. A fund filing a 10-day number cannot |
| Hierarchy rollup | `parent_portfolio_id` exists; the model says "NO rollup/scope logic". Structure is stored, never computed through |
| Limits | Bind 3 of 21 governed families. An illiquid share is computed and cannot be capped |
| Counterparty risk | Zero code, four prose mentions |
| Presentation | 105+ read endpoints with no screen. Zero search boxes. Zero charts |
| Attribution | Absent entirely — performance and risk |
| Evidence egress | Four of 305 operations serve audit/lineage/reproduction and none of them join. No assembly or export code exists |

---

## 3. The ten questions — researched recommendations, PENDING RATIFICATION

Each was researched against the code and industry practice, then attacked by an independent
adversary. **Q1 and Q2 were answered by executed spike; their numbers are measurements.**

### Q1 — Build a pricing/discounting engine? **Recommend: yes, pure Decimal, closed-form only.** (XL)

A 5,000-position book under 20 scenarios — 3,000 bonds off an interpolated curve, 500 options with
a full greek set, 1,500 equities — measured **4.5s** by the researcher and **6.5s** by the adversary
re-measuring with options pushed off-the-money. Seconds, by three orders of magnitude; under a
second on eight cores. A 40-flow 20-year bond prices in 541µs (adversary: 532µs); Black-Scholes
with six greeks costs 130µs at-the-money rising to 346µs in the tail.

The reproducibility argument is now evidenced: **18,000 Decimal operations across two independent
implementations at three precisions, zero mismatches.** Float transcendentals carry no such
guarantee — they vary at the last bit across platform, libc version and compiler flags — so a
float spine's ten-year reproducibility is a property of a frozen machine image, not of arithmetic.

**The one uncloseable cliff is Monte Carlo:** ~112 hours per core in Decimal versus ~15 seconds
vectorised. Simulated exposure profiles (EPE, EEPE, peak PFE) and path-dependent exotics are
therefore permanently outside the governed spine. **This contradicts a ratified requirement
specifying seeded Monte Carlo and must be briefed as dropping a promise, not as housekeeping.**

Three corrections the adversary forced: (i) the SA-CCR counterparty finding was **wrong** — it sits
under "Future Jurisdictional Overlays (not initial scope)" and targets bank-affiliated clients, not
an SEC-registered adviser; (ii) **choose the error-function algorithm before freezing it** — the
measured penalty for the wrong choice is 4–5× in exactly the shocked regime, and once pinned in a
registered model version it cannot be improved without breaking every historical price; (iii) the
instrument model is missing three pieces nobody listed — index fixing/reset history (no floating leg
can be valued without it), curve bootstrapping from par rates, and curve-set/discount-curve
assignment for multi-curve discounting.

*Honest gap: nobody measured the build. XL is right and "the maths is about a week" is not — this
introduces six to ten governed families at the repo's own cadence.*

### Q2 — Structural factor model in Decimal? **Recommend: yes, and stop re-litigating it per slice.** (XL)

The premise that the solve is the hard part is false. At **117 factors × 10,000 instruments**:
**0.838s per period** (researcher), **0.607s** (adversary, independent sparse implementation).
Against a four-hour daily budget that is a fraction of one percent. Three years of daily history
rebuilds in ten minutes on one core.

Four corrections to ship with the kernel: use a Gaussian solve rather than the existing full matrix
inverse (measured **4.16×** more work at 40 factors); **fix the precision-coupled singularity
guard** — on a degenerate cap-weighted design at Python's default 28 digits it did not refuse, it
returned a factor return of 3×10²³; impose the cap-weighted identification constraint rather than
dropping a reference industry; and budget a new governed entity for estimated factor returns,
because the existing table cannot hold them.

**Do not build the kernel first** — decide where market cap and the style descriptors come from.

### Q3–Q10 — recommendations in brief

| # | Question | Recommendation | Size |
|---|---|---|---|
| **Q3** | Multiple exposure measures per holding? | **Yes — widen the grain now**, while the vocabulary has one member. Relax four not-null columns; make every consumer declare the measure it eats and refuse others. Eight families touched, not four | L |
| **Q4** | Sleeve label vs measured holdings | Ratify three words used everywhere — **Mandate / Measured / Off-mandate** — and declare the portfolio name semantically inert | XL |
| **Q5** | New limit dimensions | **Strategy-node limits already work and have never been demonstrated** — do that first. Add strategy as a concentration dimension (no new captured data). Defer ultimate-parent behind a named trigger | L |
| **Q6** | Credit vs counterparty | **Build credit, decline counterparty** behind three named triggers. Credit as a real Decimal bond-analytics kernel, not a vendor-spread wrapper. Introduces bounded-bisection iteration — a new numerical class here | XL |
| **Q7** | Filer or input supplier | **Input supplier**, written as an explicit supersession of the existing fence. Then build a fund-grain net/gross assets series and a governed export — both pay for themselves with no regulatory argument | M |
| **Q8** | Scheduled report run binding | One as-of date from the tick by declared rule; newest completed run per family within it; **every declared family or nothing**; refuse before writing; make the absence louder than the failure. **Two of four families cannot honour this today** | XL |
| **Q9** | Report sign-off rail | **Not yet** — record the approve half as a deferred carry with a firing trigger (the repo uses this pattern three times). Spend the slice on the renderer, which cannot dispatch on its own version label and is why every future chart would break | M |
| **Q10** | Board-altitude limitations | Board face: provenance line, limitation **count and link**. Board appendix: every limitation of the pinned model version plus its operative validation conditions — **mechanically derived, no human in the loop**. Defer the editorial flag | M |

---

## 4. The requirement set — WRITTEN INTO THE BACKBONE, 2026-08-12/13

Thirty requirements survived adversarial attack out of sixty proposed: **9 analytics, 7 structure,
6 presentation, 6 reporting, 1 governance, 1 operations.**

**They are no longer proposals.** Part 1 (2026-08-12) wrote twelve rows and minted CAP-21; part 2
(2026-08-13) wrote nineteen more. The register went **74 → 105 rows**, and the RTM was brought level
with it — part 1 had updated only one half, which is the P1 ledger-5 omission class and nothing
mechanical was checking it.

**Seven coverage gaps were paid in part 2, and the gate found every one of them itself** by refusing
to pass while the stale exemptions sat in the baseline: capability `13.3` Exception management
(REQ-DQR-004), `16.2` Scenario/breach reports (REQ-RPT-005), and **all five SCOPE commitments** —
discharged the only way that means anything, by requirement rows that CITE the id they serve.
`SCOPE-01` REQ-INT-004 · `SCOPE-02` REQ-PPM-009 and REQ-SMR-007 · `SCOPE-03` REQ-MDG-004 ·
`SCOPE-04` REQ-ADM-005 and REQ-DQR-004 · `SCOPE-05` REQ-ADM-006. Two accepted gaps remain, both
deliberate: `20.2` money-weighted return and `20.4` composites.

> **A cited SCOPE id means a requirement now answers to the commitment. It does not mean the
> commitment is built.** SCOPE-02's derivative half is still the largest gap the re-baseline found —
> instrument terms carry seven bond fields and cannot express an option — and REQ-SMR-007 is
> precisely the row that fails until that is fixed. Discharging a coverage gap makes work visible to
> the process; it does not do the work.

The shape that matters:

- **`REQ-STR-005` — the risk-bearing exposure measure. BUILD THIS FIRST.** Factor allocation and
  every exposure-consuming family must consume a *declared* risk-bearing measure. Everything
  downstream depends on it.
- **`REQ-MKT-003` amended** — risk decomposition as a governed number over an existing parametric
  run, replacing the deferred contribution-to-risk conjunct. No new id: the row's own purpose
  always said this.
- **`REQ-MKT-002` restated** — sensitivities at *position* grain, aggregating to portfolio and to
  any hierarchy node.
- **`REQ-PRES-001` — the presentation contract registry.** Every governed result family declares
  how it is presented. This is the row whose absence caused the drift.
- **`REQ-PRS-001` — the governed chart:** a server-rendered inline-SVG fragment inside the report
  section renderer, so a chart is evidence rather than a picture of it.
- **`REQ-PRS-002` — the value-to-pixel projection fence:** all conversion in one named module per
  tier, Decimal server-side.
- **`REQ-PRS-004` — viewing mints nothing**, with an executed negative control.
- **`REQ-RPT-004` — the report definition entity. BUILD BEFORE THE OTHER REPORTING ROWS.**
- **`REQ-RPT-005` — four audience-tiered renditions from ONE pinned evidence set**, audience class
  as a first-class column. This is how ANALYST/PM/COMMITTEE/BOARD stop being four documents that
  disagree.

Every presentation and reporting row names its audiences explicitly. A row serving all four was
treated as a row nobody had thought about.

---

## 5. Sequencing

Dependencies are real even in a full build with no MVP constraint:

1. **`REQ-STR-005`** (risk-bearing exposure measure) and **`REQ-STR-001`** (per-family aggregation
   contract). Nothing analytic is safe to build before these; Q3's grain widening lands here while
   the vocabulary still has one member.
2. **Pricing engine, linear instruments first** (Q1) plus the three missing instrument pieces —
   fixings, bootstrapping, curve sets. Options and the volatility surface second.
3. **Risk decomposition** (`REQ-MKT-003`) — needs position-grain sensitivities, which need (2).
   This is the highest-value visible capability in the whole re-baseline.
4. **Presentation contract + the governed chart** (`REQ-PRES-001`, `REQ-PRS-001/2/3/4`). Can run in
   parallel with (2) and (3); it is not blocked by the pricing engine.
5. **Node-scoped runs and rollup** (`REQ-PPM-005`), then the Mandate/Measured vocabulary (Q4).
6. **Report definition entity, then audience-tiered renditions** (`REQ-RPT-004`, `-005`).
7. **Factor model** (Q2) once its descriptor inputs are decided.
8. **Credit** (Q6). **Counterparty declined** behind triggers.

---

## 6. The process fix — four gates

A lesson here is a gate, a trigger, or an explicit acceptance of recurrence. That rule should have
applied to itself.

**G1 — capability coverage. BUILT AND PROVEN (2026-08-12).** `scripts/check_capability_coverage.py`
reads the *owner's* capability taxonomy and SCOPE commitments and fails when a leaf has no
requirement behind it. Wired into `make check` and CI. On install: 94 leaves, 89 covered, **5 not**
— one of which is `20.3 Performance attribution`, which it rediscovered without being told to look.
A ratchet, not a wall: today's gaps sit named in `capability_coverage_baseline.json`, only new ones
fail, and an exemption left in place after it is paid also fails.

*Two defects were found in this gate while building it, both the class it exists to catch: a
citation parser producing 47 false positives, and a first negative control that **passed** because
it anchored on text that does not occur in the file. Six controls are committed so it cannot rot
into a green light matching nothing.*

**G2 — acceptance criteria must test the stated purpose. BUILT 2026-08-13, AND NOT AS SPECIFIED:
the automated version does not exist, and that is a measured result rather than a shortfall.**

G2 was specified here as *"flag any row whose acceptance clause does not reference the same object
as its business-purpose clause"*. Six independent detector designs were built to that brief and
scored against a labelled 74-row register with three known-bad rows. **All six catch all three. None
is usable.** Varying only REQ-PPM-004's acceptance cell, on the best performer, verified by hand:

| Acceptance text | Verdict |
|---|---|
| `Aggregates reproduce within tolerance and bind lineage` — the real defect | **FLAG** (correct) |
| `Exposure rollup across the hierarchy is NOT implemented; the endpoint returns 501` | **PASS** |
| the defect plus six words: `; the hierarchy is recorded` | **PASS** |
| the real 2026-08-12 repair, `removing the largest contributor moves total risk by that contributor's stated amount` | **FLAG** |

**The check passes the bug and blocks the patch**, and six words of appended noise disarm it — not
an attack anyone must mount, an edit an author makes while tidying prose. Underneath, all six are
checking which WORDS appear in the acceptance sentence, and no word rule distinguishes a sentence
that promises something from one that merely mentions it. Five of the six flagged criteria of
exactly the shape the 2026-08-12 amendments demonstrate. The model-judged variant understood the
defects properly and failed differently: its verdict flips on 15 of 74 rows between runs, and its
headline 3/3 collapsed to **0/3** once the answers were removed from its own rubric.

The reason is structural and worth stating once: **G2 asks a question about MEANING, about a
document the person being checked can freely reword.** Any word rule is one word away from being
switched off by the person it polices — which is how this drift happened in the first place. The
criteria were written to be passable; a rule reading those criteria gets written around too.

**So G2 is a human act (P20), with deterministic bookkeeping that proves the act happened and lapses
it when the text moves** — `scripts/check_g2_adjudication.py`, `02_requirements/g2_adjudication_ledger.jsonl`,
wired into `make check` and CI, 16 controls committed. **The bookkeeping checks paperwork, never
quality, and must never be cited otherwise.** Ratified by the user at the G2 decision gate,
2026-08-13.

*The bake-off's union of flags is kept as an advisory reading order in `g2_slice_scope.json` — 11
rows flagged by three or more independent designs, several corroborated by the register's own Status
column. A row absent from that list is not thereby fine: the second run measured that **0 of 4**
defective rows written in fresh wording reach three votes.*

**The bake-off ran twice, independently, and the second run earned its keep twice over.** It tested
the one idea the first did not — an ensemble requiring 4 of 5 detectors to agree — which looked
superb on the original 74 rows (3 extra flags, all genuine) and then caught **3 of 10** defective
rows written fresh that morning, scoring the three strongest acceptance criteria identically to the
three most vacuous. The good result was five detectors fitted to the same 74 sentences. **It also
found a defect in the first version of the bookkeeping gate: with an empty slice scope it exited 0
having adjudicated nothing** — the empty-population vacuity, inside the gate written to prevent it,
and this repository's fifth near-miss of that class. Now a refusal (exit 2), with its own control.

**G3 — every presentation requirement needs an acceptance criterion a human can see.** Two of 74
rows qualify today. *Rides the re-baselined register.*

**G4 — the close review cannot close without the capability coverage table. BUILT 2026-08-13.**
A wave close review from the Wave-18 close on must carry a `## Capability coverage (G4)` section
listing the capability leaves the wave's slices newly covered. The gate verifies each listed leaf is
real in the owner's taxonomy and is still cited by a requirement row; a wave that covered nothing
writes `NO NEW CAPABILITY COVERAGE` plus a sentence, because an empty table is not a measurement.

*The table is the wave's OWN contribution rather than the platform's running total — deliberately,
because a "coverage right now" table goes stale the moment the next requirement row lands, and
enforcing it would redden CI until someone edited a historical document. Rewriting a measurement
after the fact is the class of defect this gate exists to prevent.*

*Waves 1–17 are NOT retro-fitted, and a control asserts they carry no G4 section: demanding a
coverage table from seventeen closed waves would mean writing a measurement that was never taken.*

**Its weak point today, named rather than discovered:** no wave has closed since G4 existed, so on
the real tree it is bound to **zero** documents. That is the same vacuity the second G2 bake-off run
found inside the G2 gate, and it is handled the same way — a committed control asserts the count is
zero and instructs its own deletion at the Wave-18 close, and nine further controls prove the gate
fires. A tenth refuses (exit 2) if the discovery glob ever stops finding the seventeen historical
reviews, which is how a gate reports green having checked nothing.

---

## 7. What this document does not decide

- **The ten answers are recommendations.** None is ratified.
- **Monte Carlo displacement** (Q1) contradicts a ratified requirement and needs an explicit
  decision to drop it, not a silent supersession.
- **The error-function algorithm** (Q1) must be chosen before anything is frozen.
- **Where market cap and style descriptors come from** (Q2) — blocks the factor model kernel.
- **The 10 MiB upload cap** — realistic for a few thousand line items, not for a real book.
- **Who wins a restatement** — the one genuinely judgemental inflow question, still open.
- **Credit and counterparty** were not re-baselined in this pass; each needs a run the size of the
  analytics one.
