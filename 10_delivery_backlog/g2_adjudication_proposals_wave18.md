# G2 adjudication proposals — the Wave-18 structure block

**Status: PROPOSED. NOTHING HERE IS AN ADJUDICATION.** P20 is explicit: *Claude may PROPOSE, and its
proposal is never the adjudication.* The ledger stays empty until a human on the roster decides.

**Subject:** the five structure rows `product_rebaseline.md` §5 puts first — nothing analytic is safe
to build before them. **The slice scope itself is still the user's to set at the planning gate;**
these are the rows that would enter it if §5 is followed.

**The question asked of each row, verbatim from P20:**

> *"Describe an implementation that passes EVERY clause of this acceptance criterion and does NOT
> deliver the stated business purpose. Barred: 'they might compute it wrongly' — the implementation
> must be one a competent, lazy team would actually ship."*

---

## Read this before the five

**All five came back AMENDED, and that should be treated as a warning about the proposer, not as a
score.** Two readings are available and I cannot distinguish them from the inside:

1. the rows are genuinely thin — I wrote them yesterday, quickly, to the P20 *shapes* without ever
   attacking them, and attacking is a different act from writing; or
2. I am pattern-matching to look diligent, because a proposal that found nothing would look lazy.

The honest position is that **I am the author of all five rows**, which is exactly the situation the
roster rule exists to prevent, and it makes this the least trustworthy adjudication the process will
ever produce. A REBUTTED verdict from me on my own row would be worth even less than an AMENDED one.
Please read the exploits on their merits and reject the ones that are theatre.

**Recurring theme, worth naming once:** four of the five exploits are the **empty or one-member
population** — a vocabulary with a single member, a book with a single currency, a tree with a single
level, a mandate derived from what is already held. This repository has shipped that failure at
least five times (`SUPPORTED_FACTOR_FAMILIES = (CURRENCY,)`, the vacuous identity census, the
`cohort[0]` break-in test, the empty-scope G2 gate, the subset-not-equality RPT-3 defect). It is the
house defect, and criteria that quantify over a set are where it lands.

---

## 1. REQ-PPM-006 — Declared risk-bearing exposure measure

`hash 5f6920e4…` · purpose: *One holding can carry more than one exposure*

**Proposed: AMENDED.**

**The exploit.** Register exactly ONE measure — `NOTIONAL` — and have every consuming family declare
it. Every clause passes: the exposure key includes the measure type; each family declares what it
eats and refuses another (the refusal fires against a synthetic second value in a test); the census
finds no undeclared consumer. The "one holding may carry both a notional and a delta-equivalent row
without collision" clause is satisfiable by inserting two synthetic rows in a test — **no production
path ever produces a second measure.** The purpose is not delivered: no holding carries more than
one exposure anywhere outside the test.

This is not hypothetical. It is what `SUPPORTED_FACTOR_FAMILIES = (CURRENCY,)` already is, one row
over, and REQ-MKT-004a was amended for precisely it.

**Proposed amendment** — add a differential clause the one-member version provably fails:

> A single derivative holding emits BOTH a notional row and a delta-equivalent row **from the
> ingestion and valuation path, not from a test fixture**, asserted by reading back two rows for one
> holding id; and the two carry different values, so a delta-equivalent that silently equals notional
> fails. The measure vocabulary has at least two members with a producer each, asserted against the
> producers rather than against the vocabulary.

---

## 2. REQ-PPM-007 — Per-family aggregation contract

`hash 122443b4…` · purpose: *Every family says what it aggregates, and refuses the rest*

**Proposed: AMENDED.**

**The exploit.** Declare a contract for every family, mark one token family `NOT AGGREGATABLE`, and
implement the refusal inside an aggregation helper. Every clause passes — exact set equality holds,
the refusal fires when the test calls the helper, mixed measures are refused there too. **In
production, aggregation happens somewhere else**: a `SUM()` in a read view, a total computed in the
report renderer, a rollup in the API layer — none of which consults a contract. The families do not
in fact refuse anything; a helper does, and nothing calls it.

This is the LQ-1 finding exactly: *three controls written, believed and INERT.*

**Proposed amendment** — bind the contract to the path:

> Aggregation has ONE enforcement point, asserted by a census of aggregation sites that fails when a
> second path exists; and the `NOT AGGREGATABLE` refusal is made to fire **through the public read
> surface** (an HTTP request for a summed yield is refused), not only against the helper.

**Separately, a content correction I believe the row gets wrong.** It offers *"a yield, a ratio, a
duration"* as examples of `NOT AGGREGATABLE`. **Duration is aggregatable** — by market-value
weighting, and portfolio duration is a number every fixed-income desk quotes. Classifying it as
un-aggregatable would be a real defect shipped into the vocabulary. It belongs in `WEIGHTED`, and the
example should be replaced (an internal rate of return is the honest `NOT AGGREGATABLE` case).

---

## 3. REQ-PPM-008 — Node-scoped runs and rollup

`hash 71cfc0cd…` · purpose: *Run risk at any node of the structure, not only at the top*

**Proposed: AMENDED.**

**The exploit.** Implement node-scoping on a **two-level** tree — portfolio over positions, which is
the only shape that exists today. Every clause passes: the parent equals the composition of its
children to the last decimal; a childless node returns its own positions; an empty subtree refuses;
the node id is on the run. And *"any node — fund, portfolio, sleeve, strategy"* is not delivered,
because a fund of sleeves of strategies is never exercised and may not even be representable. The
associativity that actually breaks — grandparent against grandchildren — is untested.

**Proposed amendment** — name the population:

> The rollup identity holds on a tree of at least THREE levels and is asserted at the grandparent
> against BOTH its children and its grandchildren; at least two distinct node types participate
> (a fund containing sleeves, not one portfolio containing positions); and a node's result is
> unchanged by inserting an intermediate node that regroups its children without changing the
> holdings — a regrouping that moves the total fails.

---

## 4. REQ-PPM-009 — Mandate, Measured and Off-mandate

`hash 5edd27c4…` · purpose: *A sleeve's label is not evidence of what it holds*

**Proposed: AMENDED.** This one has two independent exploits, which is usually a sign the row is
carrying two requirements.

**Exploit A — the renaming clause costs nothing.** *"Renaming a portfolio changes NO computed
result"* is **already true of the system today**, because nothing reads the name. The clause can be
satisfied by writing the test and changing no code. It is a regression guard dressed as a
requirement.

**Exploit B — seed the mandate from the holdings.** Declare each node's mandate at creation as
"whatever it currently holds". Off-mandate is then permanently empty; every clause passes — the
comparison is genuinely performed, `UNDECLARED` is reported for nodes with no mandate, public and
private sleeves are the same kind of node — and the row delivers nothing, because no holding is ever
outside its mandate.

**Proposed amendment** — a falsifying case, with the mandate authored independently:

> A node whose DECLARED mandate excludes an instrument it holds reports exactly that instrument as
> OFF-MANDATE, on a fixture where the mandate is declared BEFORE the position is added; the mandate
> is a structured declaration with at least two expressible dimensions (an instrument-class rule and
> a concentration rule), not free text; and a mandate derived from current holdings is refused at
> declaration, because a mandate that cannot be violated is not a mandate.

*Exploit A is worth keeping as a clause, just not as evidence — suggest marking it explicitly as a
regression guard so nobody mistakes it for the work.*

---

## 5. REQ-PPM-010 — Reporting currency and governed FX translation

`hash 9bc800ec…` · purpose: *One book, several currencies, one honest total*

**Proposed: AMENDED.**

**The exploit.** Ship it against a **single-currency book**. Every clause passes *vacuously*: "carries
the FX rate id for EVERY translated leg" is true of an empty set of translated legs; same-currency
translation is the exact identity (trivially — it is the only case); the missing-rate refusal fires
in a unit test. Nothing is ever translated, and *one book, several currencies, one honest total* is
not delivered.

**Proposed amendment** — assert the population is non-empty, then assert against an external oracle:

> The test book holds at least THREE currencies, at least one node's reporting currency differs from
> its holdings' currencies, and the count of translated legs is asserted NON-ZERO before any claim is
> made about them; the translated total agrees with a HAND-COMPUTED value (an external oracle, never
> a re-run of the same code); and translating a node to currency A and then A to B agrees with
> translating directly to B, or the result states which convention broke the chain.

---

## What happens when you decide

For each row: **AMENDED** (accept an exploit — I rewrite the acceptance so the exploit fails, commit
it, and the ledger entry records that commit) or **REBUTTED** (you name the clause that already
blocks the obvious exploit, in a sentence). Rejecting a proposal outright is a REBUTTED with your
reason, and is the outcome I would expect on at least one of these.

The ledger entry is written under your handle only after you decide. Editing either cell of a row
lapses its adjudication automatically, so an amendment does not quietly inherit the verdict on the
text it replaced — the new text gets a new hash and needs its own.

**Not decided here:** whether the Wave-18 scope is this structure block at all. The wave's earlier
ratified thesis was *"Show it to someone"* (DEMO-1, DEMO-2, ONBOARD-2, RUN-UI, PRESENT-1) and
INGEST-1 was recommended into it at its own gate. §5 says structure comes first because nothing
analytic is safe before it. **That is a sequencing decision, and it is yours.**
