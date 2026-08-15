# G2 adjudication proposals — the 11-row advisory worklist

**Status: PROPOSED. NOTHING HERE IS AN ADJUDICATION.** P20 is explicit: *Claude may PROPOSE, and its
proposal is never the adjudication.* Ledger entries are written under the adjudicator's handle only
after a human decides. Hashes below are the current `(purpose, acceptance)` hashes computed by
`scripts/check_g2_adjudication.py` at main `3ca0271`; editing either cell lapses any verdict.

**Subject:** the `worklist` array in `02_requirements/g2_slice_scope.json` — the 11 rows flagged by
three or more independent detector designs at the 2026-08-13 bake-off. The worklist is advisory and
is not an exemption for rows off it. None of these rows is in a slice scope today, so none of these
adjudications is REQUIRED yet; the reason to work the list now is that four of these rows sit on the
re-baseline §5 critical path and their defects are the same class the re-baseline was called for.

**The question asked of each row, verbatim from P20:**

> *"Describe an implementation that passes EVERY clause of this acceptance criterion and does NOT
> deliver the stated business purpose. Barred: 'they might compute it wrongly' — the implementation
> must be one a competent, lazy team would actually ship."*

**Author caveat, same as last time:** most of these rows are genesis-era, not written at the
re-baseline, but I am still the register's author of record throughout. Read the exploits on their
merits and reject the ones that are theatre.

**Shape of what follows.** Three groups:

- **Group A — two rows superseded by ratified decisions.** The proposal is register reconciliation
  (WITHDRAW), not a G2 verdict. Adjudicating acceptance text for a declined capability is theatre.
- **Group B — one row whose Status cell is false by silence.** Reconcile before adjudicating.
- **Group C — eight rows with the reproduce-shaped defect.** Six proposed AMENDED, one proposed
  NARROW+SPLIT, one AMEND-now-or-defer-to-trigger.

The recurring exploit across Group C is the one the re-baseline named on REQ-PPM-004:
**"reproduces" means run-twice-identical, which any deterministic build passes, including the one
that does none of the work.** Five of the eight acceptance cells contain the word "reproduce" as
their only teeth.

---

## Group A — superseded rows: propose WITHDRAW, not adjudicate

### 1. REQ-CPT-002 — PFE / EPE

`hash c68bf33b…` · purpose: *Potential future exposure* · acceptance: *PFE reproduces with recorded seed*

**Proposed: WITHDRAW (register reconciliation, cites two ratified decisions).**

The row is superseded twice over. Its Method cell mandates *"Deterministic seeded MC (QS-18)"*, and
**Monte Carlo was withdrawn from the governed spine on 2026-08-12** — measured at ~112 hours per
core in exact Decimal, and the withdrawal note in roadmap Part 3 explicitly says it *"carries with
it EPE/EEPE/peak-PFE exposure profiles."* Separately, **counterparty risk was declined behind
triggers at the same gate** (Q6). A register row that mandates a withdrawn method for a declined
capability cannot be amended into health; the honest act is to mark it WITHDRAWN citing both
decisions, with re-entry defined: if a counterparty trigger fires, the method question is re-opened
(MC reconsidered or replaced), fresh rows are written, and THOSE rows enter G2.

For completeness, the exploit on the text as written: a two-path "simulation" with a recorded seed
reproduces perfectly and measures nothing. It will never need fixing because the row should not
survive in this form.

### 2. REQ-CPT-004 — CVA placeholder

`hash 849023c6…` · purpose: *Future credit valuation adjustment* · acceptance: *Capability present,
limitations documented (BX-LIM)*

**Proposed: WITHDRAW.**

This row is the degenerate build BY DESIGN: its acceptance is satisfied by a documentation page.
"Capability present" has no test that could fail — a module containing a docstring is a present
capability under this wording. A register row whose acceptance a document satisfies is the exact
class the re-baseline exists to kill, here institutionalized rather than accidental. With
counterparty declined (Q6), the limitation statement this row wants belongs in BX-LIM directly, not
wearing a requirement id. Same re-entry path as CPT-002.

---

## Group B — a Status cell false by silence: reconcile first

### 3. REQ-LIQ-004 — Capital-call forecasting

`hash 542eb7a2…` · purpose: *Forecast private cash needs* · acceptance: *Forecast reproduces; feeds
CFP indicators*

**Proposed: STATUS RECONCILIATION first, then AMENDED.**

**The status is stale.** The row reads bare "Draft". CC-2 shipped ENT-059
`pacing_projection_result` on 2026-07-20 — the SEVENTEENTH governed number, per-period
`projected_call` / `projected_distribution` computed from captured commitments through a pinned
snapshot. That IS a governed capital-call forecast from commitments; the adjacent rows REQ-PRV-001/
002 cite it in detail. This is the register-silence-in-the-omission-direction class that OQ-LQ-1-12
named on the rows one screen up. The status should read In-Progress citing CC-2, with the open
remainder stated.

**The exploit on the text as written.** A forecast that returns a constant — or zero — for every
period reproduces perfectly, and "feeds CFP indicators" is unfalsifiable because **CFP indicators
are defined nowhere in the register**. A clause naming an undefined artifact is satisfied by wiring
the number to anything and calling it an indicator. Both clauses pass with no forecasting delivered.

> **Proposed amendment.** Status: In-Progress (CC-2, ENT-059). The open remainder, as acceptance:
> (i) the portfolio-level rollup of unfunded and projected calls across pairs — the named CC-2 v2;
> the per-pair kernel is shipped and redefining "aggregated" as per-pair was already ruled an
> overclaim at CC-2; and (ii) *"feeds CFP indicators"* is REPLACED by a named consumer or deleted —
> if a cash-flow-planning surface is intended, name the row that owns it and bind this forecast as
> its input; if none is intended, the liquidity rows own their own inputs and the clause goes.

---

## Group C — the reproduce-shaped rows

### 4. REQ-PPM-001 — Portfolio/fund/strategy/account hierarchy

`hash daff8270…` · purpose: *Organize holdings for aggregation & entitlement scope* · acceptance:
*A node tree persists, is tenant-scoped, and is the portfolio-scope anchor (subtree semantics
recorded; enforcement deferred)*

**Proposed: AMENDED.**

**The exploit.** A table with a `parent_portfolio_id` that nothing traverses passes every clause.
"Persists" is an INSERT; "tenant-scoped" is the RLS every table on this platform gets for free;
"anchor … recorded" is prose; "enforcement deferred" concedes the rest. The requirement cell says
*versioned* hierarchy nodes and the acceptance never mentions versioning — CRUD with no history
passes. The tree organizes nothing: it is two levels deep in practice and no governed run walks it.
That is roughly today's state, which is why the row is thirteen weeks In-Progress with nothing left
that could fail.

**What the lazy build cannot produce: history-stable reads.** Re-parenting a node today silently
re-shapes what every past result meant by "the tree".

> **Proposed clause.** Persistence and tenancy stay as regression guards, not evidence. Added:
> (i) the entity expresses at least THREE levels and TWO node types, and REQ-PPM-008's rollup test
> runs over THIS entity — the dependency is named, not duplicated; (ii) hierarchy edits are
> versioned: a governed result computed before a re-parenting, re-read after it, resolves the tree
> AS IT WAS at the run's as-of — asserted by re-parenting a node between run and read and comparing;
> (iii) the entitlement-anchor half remains DEFERRED to ABAC enforcement (P6+) and is stated as
> deferred, never counted as delivered by this row.

### 5. REQ-PPM-002 — Position master (as-of)

`hash c2664cb4…` · purpose: *Single source of holdings for all risk* · acceptance: *A position is
reconstructable for any past as-of date*

**Proposed: AMENDED.**

**The exploit.** Reconstruction shipped in migration `0014` and its tests pass. Nothing in the
acceptance mentions CONSUMERS. A competent lazy team adds the next analytic with its own holdings
ingestion — a CSV, a side table — and this row stays green while "single source" quietly becomes
"one of several sources". The purpose lives entirely in the word "single" and no clause tests it.

> **Proposed clause.** The reconstruction clause stays as a regression guard. Added: every governed
> family that consumes holdings resolves them THROUGH the position master's as-of reconstruction at
> the run's pinned snapshot, asserted by a census of holdings-consuming code paths — a consumer
> outside the census FAILS, and the census must be exact (subset passes are the RPT-3 defect). The
> ABAC portfolio-scope residual keeps its existing deferral home unchanged.

### 6. REQ-PUB-002 — Curves & volatility surfaces

`hash a31d89ca…` · purpose: *Discounting & options risk* · acceptance: *Curve/surface values
reproduce; method declared*

**Proposed: AMENDED.**

**The exploit is the shipped state plus one table.** Captured curves read back byte-identical —
stored data "reproduces" trivially. `interpolation_method` is already captured as an inert label
with NO engine (OQ-P2-5-9 recorded exactly this). Add a `volatility_surface` table of the same
shape and every clause passes while nothing is ever discounted and no option risk exists. The
Status cell honestly says the REQ does not close, but the acceptance itself would pass — the row is
held open by prose, not by its criterion.

> **Proposed clause.** (i) A curve queried at an OFF-NODE tenor returns a value COMPUTED by the
> declared method, and the demonstrating query asserts the interpolated-read count is NON-ZERO
> before asserting anything about the values; (ii) the value agrees with a HAND-COMPUTED oracle for
> that method; (iii) the declared method is load-bearing: two different declared methods over the
> same nodes give DIFFERENT off-node values, so an inert label fails; (iv) at least one governed
> consumer discounts with it — a discount factor at an off-node date reaches a governed number —
> because an interpolation engine no run calls is a library, not a capability. The surface leg
> carries the same four clauses when built (QS-13).

### 7. REQ-MKT-002 — Sensitivities

`hash 577ede00…` · purpose: *Risk decomposition & hedging* · acceptance: *Greeks reproduce within
ε; conventions declared*

**Proposed: AMENDED — and this is the highest-value row on the list.** Re-baseline §5 puts risk
decomposition (REQ-MKT-003) third, "the highest-value visible capability in the whole re-baseline,"
and it needs position-grain sensitivities. This row is the feeder, and its acceptance is
REQ-PPM-004's defect verbatim: *reproduce within tolerance* with no oracle and no grain.

**The exploit.** "Within ε" against WHAT? If against a re-run, any deterministic code passes at
ε = 0 — including the book-level curve-node DV01 that already shipped at P3-1. "Conventions
declared" is a string in a methodology doc. Every clause passes with no position-grain number in
existence, and no hedge can be derived from a book-level aggregate: the purpose says *hedging* and
nothing tests that a trader could act.

> **Proposed clause.** (i) Sensitivities exist at POSITION grain; (ii) the book-level figure equals
> the composition of the position-grain figures under the family's declared aggregation operator
> (REQ-PPM-007's contract, once built — additive for DV01); (iii) at least one hand-computed
> EXTERNAL oracle per shipped convention — a known bond's DV01 verified by hand, the convention that
> produces it named; (iv) the hedging outcome: bump the pricing inputs of ONE position and re-price —
> the book moves by that position's stated sensitivity within a DECLARED ε, where ε is a number
> written in the methodology doc, never a run-to-run diff; (v) "reproduces" survives only as the
> standard governed-number regression guard.

### 8. REQ-LIM-002 — Utilization computation

`hash 361f93cc…` · purpose: *Measure usage vs limit* · acceptance: *Utilization reproduces and
binds source results*

**Proposed: AMENDED.**

**The exploit.** Shipped `evaluate_limit` compares observed vs threshold at evaluation time and
binds the evaluated run — both clauses pass today. But a comparison is not a MEASURE. Nothing
stores the ratio, nothing serves it, and an operator cannot see 87% and act before the breach.
Utilization-as-a-readable-number is the entire content of this row over and above the shipped
breach machinery, and no clause requires it. The reserved ENT-032 surface can stay reserved forever
under this wording.

> **Proposed clause.** (i) Utilization is a STORED governed number — observed value, threshold,
> ratio — per limit per evaluation (this is the ENT-032 decision, made rather than reserved);
> (ii) readable through the entity/time read surface per the rule-7 house shape: filter by limit
> and portfolio plus a date range, so headroom TREND is visible across at least two evaluations;
> (iii) the demonstrating case shows a utilization STRICTLY BETWEEN zero and the threshold — a
> fixture that only ever sits at 0% or in breach never exercises "usage", which is the one-member-
> population house defect again; (iv) binding the source `calculation_run` stays as shipped.

### 9. REQ-SCN-003 — Combined & private-asset shock

`hash 98c32dd9…` · purpose: *Holistic stress incl. illiquids* · acceptance: *Combined run
reproduces; binds all input versions*

**Proposed: AMENDED.**

**The exploit is REQ-PPM-004 verbatim** — reproduce plus bind-lineage requires no combining. Run
the shipped linear factor shock alone, label the run type COMBINED, bind the inputs it happened to
consume: it reproduces and it binds. Sharper, and specific to "incl. illiquids": private sleeves
carry NO factor exposure rows, so the shipped scenario semantics ("unnamed factor unchanged", with
loud coverage counts) silently pass a private book through UNSHOCKED while every count reads clean.
Holistic in name, public-only in fact.

> **Proposed clause.** (i) The demonstrating book holds at least one PRIVATE holding, and the
> private-NAV leg's contribution is asserted NON-ZERO before any claim about the total; (ii) all
> three legs — market, credit, liquidity — participate, asserted by ablation: removing any one leg
> CHANGES the combined total; (iii) the combination method is DECLARED — if the legs are additive,
> the row says so and the interaction limitation is stated (BX-LIM), so the number is honest about
> what it is not; (iv) reproduce-and-bind survives as the standard regression guard.

### 10. REQ-CRD-005 — Credit spread sensitivity

`hash 53c25a37…` · purpose: *Measure sensitivity to credit-spread moves* · acceptance: *Spread
sensitivities reproduce from a pinned snapshot*

**Proposed: AMENDED now, cheaply — or explicitly DEFERRED to its trigger. Owner's call.**

The row is trigger-parked ("real curve feeds land") and enters no slice, so P20 does not require it
yet. The case for amending now: the exploit is the same reproduce-only shape, the analysis is
already done, and the ledger lapses automatically if the text moves again later.

**The exploit.** Curve-node spread-DV01 shipped at P3-1 and reproduces deterministically — the
acceptance is arguably already passable today, against a FIXTURE curve, with no position-grain CS01
and no external feed, which is everything the row was minted to mean when it was split from
CRD-003.

> **Proposed clause.** (i) Position-grain CS01 composing to the book figure under the declared
> operator; (ii) a hand-computed oracle on a known bond over a known spread curve; (iii) the
> demonstrating spread curve is a CAPTURED EXTERNAL curve, asserted by ORIGIN provenance, not a
> fixture — that is the trigger's own point, written where it can fail.

### 11. REQ-RPT-001 — Risk reports (market/credit/liquidity)

`hash cf2f5510…` · purpose: *Communicate risk* · acceptance: *Report binds run IDs; regenerates
identically (BR-9)*

**Proposed: NARROW + SPLIT.**

**The exploit is already in progress, benignly.** The acceptance is fully satisfied today by the
four built families (var, concentration, liquidity, rolling_risk) — proven end-to-end on the
deployed stack with a byte-identity check and a negative control. The ONLY thing holding the row
open is a sentence in the Status cell saying the credit family is not built. The acceptance names
no family set, so the row closes the moment that prose is edited — the binding scope lives in an
editable comment, which is precisely how REQ-PPM-004 drifted.

> **Proposed restructure.** NARROW this row to the report families of BUILT risk domains, with
> acceptance by EXACT SET EQUALITY against a declared report-family registry (a subset check is the
> RPT-3 defect); and MINT the credit risk report as its own row homed with the Q6 credit build, so
> each row can close honestly when its own scope is delivered. If the owner prefers one row, the
> alternative is to enumerate the required families IN THE ACCEPTANCE and fail while any is
> missing — but then the row stays open for as long as credit does, measuring nothing about the
> four families that are done.

---

## What happens when you decide

Per row: **AMENDED** (I rewrite the acceptance so the exploit fails, commit it, ledger entry records
the commit) · **REBUTTED** (you name the clause that already blocks the exploit) · for Group A,
**WITHDRAWN** is a register edit citing the ratifying decision, not a ledger verdict · for
REQ-RPT-001 the restructure needs your pick between the two shapes. Every AMENDED row gets a new
hash and needs its own future adjudication if it later enters a slice — nothing here pre-clears a
row for Wave 18.

**Not decided here:** the Wave-18 scope. That is unchanged and remains yours at the planning gate.
