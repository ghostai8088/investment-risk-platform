# LQ-1 — liquidity tiers: decision record

**Slice:** Wave-14 slice 4 — the LAST Wave-14 slice.
**Requirement:** REQ-LIQ-001 (REQ-LIQ-002 does NOT ride).
**Planned at:** HEAD `62c917f` on `main`; migration head `0060_benchmark_rate`; next free canonical id ENT-071.
**Method:** six-lane grounded recon (308 cited facts) → adversarial completeness critic → synthesis →
single-threaded draft → **four-lane refute-by-default verifier, which REFUTED the draft (6 BLOCKING,
10 HIGH, 11 MED, 5 LOW — all folded, Part 8)** → this record → ratification gate.

**Status: PENDING RATIFICATION. Nothing below is decided.**

> **Read Part 8 first if you are auditing this record.** The first draft's two central justifications
> were both refuted by the primary source it cited. The *shape* survived; the *reasoning* did not.
> What follows is the rebuilt version.

---

## Part 0 — grounding facts

### A. The requirement and its registers

**G7 — the backbone row, verbatim** (`02_requirements/requirements_backbone.md:198`):
`| REQ-LIQ-001 | Liquidity classification | 8.1 | Bucket assets by liquidity | Classify positions into liquidity tiers | positions, instrument attrs | Classification | Classification test | Each position has a liquidity tier; % illiquid computed | Draft |`

**G8** — the RTM row carries **ModelGov = Y** (`requirements_traceability_matrix.md:70`); status is mirrored
from the backbone, canonical there (`:22`).

**G9 — REQ-LIQ-002, verbatim, in BOTH registers:** a bare `Draft`
(`requirements_backbone.md:199`; `requirements_traceability_matrix.md:71`) — for a requirement that was
formally adjudicated, deferred and given an event trigger at the Wave-14 planning gate
(`delivery_roadmap.md:260,289`). **Register silence in the omission direction.**

**G10 — CAP-8.1 carries THREE sub-capabilities** (`01_product_strategy/capability_map.md:120-123`):
"Liquidity classification", "Illiquid asset percentage", **"Highly liquid asset coverage"**. The
backbone's CAP-8 taxonomy line compresses 8.1 to just the first (`requirements_backbone.md:73`), which
hides the gap.

### B. The primary source — SEC Rule 22e-4, re-fetched and re-verified at the fold

Source of record: **govinfo, `CFR-2024-title17-vol5-sec270-22e-4.xml`** (HTTP 200, 19,240 bytes),
fetched independently twice — once by the verifier, once by me at the fold. The first draft cited
Cornell and **truncated (a)(8) in a way that deleted the operative clause**; that is corrected here and
recorded as B1 in Part 8.

**G12 — (a)(8), IN FULL, no ellipsis:**
> "Illiquid investment means any investment that the fund reasonably expects cannot be sold or
> disposed of in current market conditions in seven calendar days or less without the sale or
> disposition significantly changing the market value of the investment, **as determined pursuant to
> the provisions of paragraph (b)(1)(ii) of this section.**"

**G12a — (b)(1)(ii), the classification mandate — this NAMES the vocabulary:**
> "Each fund must, using information obtained after reasonable inquiry and taking into account
> relevant market, trading, and investment-specific considerations, classify each of the fund's
> portfolio investments (including each of the fund's derivatives transactions) as a **highly liquid
> investment, moderately liquid investment, less liquid investment, or illiquid investment.**"

**Four categories, named, ordinal.** The tier vocabulary is not an open design question — the rule
supplies it.

**G12b — (b)(1)(ii)(B), the position-size mandate:**
> "In classifying and reviewing its portfolio investments or asset classes (as applicable), the fund
> **must determine whether trading varying portions of a position** in a particular portfolio
> investment or asset class, in sizes that the fund would reasonably anticipate trading, is reasonably
> expected to significantly affect its liquidity, **and if so, the fund must take this determination
> into account when classifying** the liquidity of that investment or asset class."

**Consequence, stated plainly because the first draft got it backwards:** under the rule, liquidity
classification is **fund-relative and position-size-sensitive**. The same instrument held by a large
fund and a small fund can — and where the size test bites, **must** — carry different classifications.
Any instrument-grain design is therefore a *deliberate simplification*, not a fidelity argument.

**G12c — (b)(1)(iv), the 15% limit:**
> "No fund or In-Kind ETF may acquire any illiquid investment if, immediately after the acquisition,
> the fund or In-Kind ETF would have invested more than 15% of its **net assets** in illiquid
> investments **that are assets**."

**G12d — (a)(7):** the "highly liquid investment minimum" is likewise **net-assets-denominated**, and
(b)(1)(iii) surrounds it with board-approval, review and shortfall-reporting machinery. LQ-1 ships the
coverage **number**, never that regime.

**G12e — AIFMD Annex IV (the recorded alternative ladder).** The first draft abstained, wrongly: the
abstention came from two failed hosts, not from the source being unreachable.
`legislation.gov.uk/eur/2013/231/annex/IV/adopted?view=plain` (HTTP 200, 172,224 bytes), Question 19
"Portfolio Liquidity Profile", column header *"Percentage of portfolio capable of being liquidated
within:"*, rows verbatim: *"1 day or less / 2-7 days / 8-30 days / 31-90 days / 91-180 days /
181-365 days / more than 365 days"*. **Honest caveat: this host serves the UK-assimilated rendering of
the EU text.** Seven day-buckets, not four ordinal categories — a real alternative, posed at OQ-15.

### C. The rail that already exists

**G14.** `classification_assignment` is FR bitemporal, PROPRIETARY symmetric RLS, never hybrid; current
head `UNIQUE(tenant_id, entity_type, entity_id, scheme_id, dimension_kind) WHERE valid_to IS NULL AND
system_to IS NULL`; polymorphic `(entity_type, entity_id)` with **no domain FK**
(`classification/models.py:193-196,206-234`).

**G15 (CORRECTED at the fold — the first draft overstated this).** The runtime fence is
`ASSIGNMENT_ENTITY_TYPES = (ENTITY_TYPE_INSTRUMENT,)` (`classification/models.py:109`) enforced by
`validate_entity_type` (`classification/service.py:139-143`). **Blast radius of widening it is three
lines, all inside `classification/`.** The snapshot pinner is *unaffected* because it hard-codes the
string literal rather than importing the tuple — which is also what insulates CON-1 from any widening.
The first draft claimed widening "changes the pinner's documented contract"; that is false, and the
correction makes arm (B) of OQ-1 materially cheaper than the draft implied.

**G16.** New dimension kinds are data, not a migration (`classification/models.py:71-78`); migration
`0056` declares `dimension_kind` as bare `sa.String(30)` and emits zero CheckConstraints.

**G17.** …but a kind added to `DIMENSION_KINDS` alone **refuses every capture at runtime** —
`validate_basis` raises "no basis policy declared for dimension_kind … — refusing"
(`classification/service.py:146-163`). **Two declaration sites.**

**G19.** `list_`/`reconstruct_as_of` verbs are **absent** from `classification/service.py` (the verb list
ends at `correct_assignment:778`) — REF-1's gap, which LQ-1 pays rather than copies.

**G21 (CORRECTED at the fold).** `position` carries no market value — `cost_basis` is annotated "Opaque
captured reference value only (OD-P1C-3) — never recomputed; **NOT a market value**"
(`position/models.py:72-77`) — **but position-grain money DOES exist**, as
`exposure_aggregate.exposure_amount`. The first draft's Collision 1 asserted otherwise and was wrong.
`position` has no date column, so "position grain" means `(tenant, portfolio_id, instrument_id)`.

### D. The architecture decisions that BIND (absent from the first draft — B4)

| AD | Binds? | How |
|---|---|---|
| **AD-014** (reproducibility) | **BINDS** | The warrant for pinning tier assignments into every governed run. CAL-1 recorded the cross-slice mandate naming LQ-1 (`cal_1_decision_record.md:437`). |
| **AD-018** (IA charter) | **BINDS** | The result table is true append-only: `APPEND_ONLY_TABLES`, `irp_prevent_mutation`, run-bound + snapshot-gated. |
| **AD-013 / R1 / R2** (hybrid set) | **BINDS** | `classification_scheme` + `classification_node` are members of the **closed 7-table hybrid set**. The tier ladder's tenancy is an AD-013 decision — OQ-16. |
| **AD-005** (`__temporal_class__`) | **BINDS** | Declaration required on the result table. |
| **AD-011** (SQLite/PG tier split) | **BINDS** | The reason T8's non-String filter defect is structurally invisible to the unit tier. |
| AD-003, AD-019 | adjacent | No LQ-1 obligation. |

---

## Part 1 — the collisions, stated before any decision

### Collision 1 — the requirement's grain vs the shipped rail (RESTATED at the fold)

REQ-LIQ-001 says **"Each position has a liquidity tier"** (G7). The assignment rail is instrument-only
at runtime (G15).

That is the *whole* obstacle. The first draft added a second horn — that positions carry no money —
and it was **false**: `exposure_aggregate.exposure_amount` is position-grain money (G21). Arm (B) of
OQ-1 is therefore cheaper than the first draft made it look, and the gate should be told so plainly.

### Collision 2 — the denominator, and a direction that is NOT what the first draft claimed

Rule 22e-4's ratio is against **net assets** (G12c). The denominator computable from stored rows today
is Σ `long_amount`.

The first draft said this **overstates** the regulatory ratio. **That is true only on a cash-holding,
unlevered long-only book.** Write `platform = I/L` and `regulatory = I/N`: the platform number exceeds
the regulatory one **iff L < N**. But `L` is a *gross long* market value, while net assets are total
assets minus liabilities — so on any levered or long/short book **L > N and the platform number
UNDERSTATES**. The recon's underlying fact was correctly scoped ("on a cash-holding book"); the draft
dropped the qualifier and then proposed committing the unconditional claim to an append-only registered
limitation. Verified by executing the shipped kernel.

**The honest statement, which is what the registered limitation must say: the direction of the error is
INDETERMINATE without a net-assets figure.** That is a stronger reason to refuse limit-bindability than
the draft's original one, and it is the premise OQ-5 and OQ-7 are now rebuilt on.

---

## Part 2 — the open questions

**Tier-3 (explicit sign-off required): OQ-1, 2, 4, 5, 6, 9, 13, 14, 15, 16, 17, 19.**
The rest are Claude's call with the reasoning recorded.

### OQ-LQ-1-1 — GRAIN: instrument or position? **TIER-3** *(REBUILT — B1, H1, H2, M8)*

- **(A) Instrument grain**, riding the rail. No table, no migration, no ENT for the captured half.
- **(B) Position grain** `(tenant, portfolio_id, instrument_id)`. Matches the requirement; joins the
  exposure atoms 1:1; money already exists at that grain (G21). Cost, **corrected**: one tuple value, a
  comment correction, and LQ-1's own builder — three lines in `classification/`, not a contract change.

**RECOMMENDATION: (A), on ENGINEERING grounds only, with a registered limitation and an amended
acceptance clause.**

*The legal rationale from the first draft is withdrawn.* It claimed liquidity is a property of the
investment rather than the holder; **(b)(1)(ii)(B) says the opposite** (G12b). Instrument grain is a
deliberate simplification, and the record must say so.

Why (A) still wins: the tier is a *curated assessment* sourced per security, and the platform has one
shipped rail for exactly that shape; position-grain assignment would require an assessment per
`(portfolio, instrument)` pair that no vendor supplies and no operator would maintain. (B) remains
genuinely cheap, and if the gate prefers fidelity to the requirement text over operational realism,
**(B) is a defensible choice and this record does not argue strongly against it.**

**Mandatory if (A):** amend REQ-LIQ-001's acceptance clause in the backbone (mirrored to the RTM), and
register the limitation verbatim — *"tier assignment is instrument-grain and therefore does not reflect
the fund-specific position-size determination that 22e-4(b)(1)(ii)(B) requires."* That limitation is
also the honest trigger for a future position-grain slice.

### OQ-LQ-1-2 — RAIL: ride `classification_assignment`, or mint a new table? **TIER-3 (entity mint)** *(H6)*

- **(A) Ride the rail.** `LIQUIDITY_TIER` into `DIMENSION_KINDS` **and** `BASIS_BY_DIMENSION_KIND` (G17).
  **Costs the first draft omitted:** it inherits REF-1's **mixed-VERSION fail-closed refusal** — which
  this project has already shipped structurally unfireable once, so it must be computed over LIVE heads
  and **mutation-proven** (CON-1's negative control is the template) — plus the mixed-basis refusal.
- **(B) Mint ENT-071.** Independent vocabulary; costs migration, RLS + CI step, audit family, permission
  mint, DQ rule, lineage source, a new COMPONENT_KIND, and a second parallel assignment mechanism.

**RECOMMENDATION: (A), with `list_`/`reconstruct_as_of` added in-slice** (paying REF-1's gap, G19) and
both inherited refusals implemented with executed negative controls. State explicitly whether ladder
revisions fire REF-1's bulk-re-classification trigger.

### OQ-LQ-1-15 — the TIER VOCABULARY **TIER-3** *(NEW — B3; the first draft had no OQ for this at all)*

- **(A) The four 22e-4(b)(1)(ii) codes:** `HIGHLY_LIQUID / MODERATELY_LIQUID / LESS_LIQUID / ILLIQUID`,
  ordinal, day thresholds recorded as the scheme's declared semantics. Illiquid partition = `{ILLIQUID}`
  — a *single named category*, not a configurable subset.
- **(B) AIFMD Annex IV's seven day-buckets** (G12e).

**RECOMMENDATION: (A).** The rule names it, REG-US-04 is the recorded regulatory anchor, and it makes
CAP-8.1's third sub-item (`HIGHLY_LIQUID` coverage) fall out of the same vector. **(B) recorded as an
additive `scheme_family` behind a trigger** — *the first EU/AIFMD-reporting tenant* — not as a rejection.

### OQ-LQ-1-16 — the LADDER'S TENANCY **TIER-3** *(NEW — B6)*

A `scheme_family` is **rows** in `classification_scheme` and `classification_node`, both members of the
**closed 7-table hybrid set** under AD-013-R2. So: SYSTEM-tenant curated global vocabulary, or
tenant-scoped rows?

**RECOMMENDATION: SYSTEM-seeded**, because the 22e-4 ladder is a regulatory standard, not a house
convention — which is precisely what the hybrid arm exists for. **The 7-table set is UNCHANGED**
(these are existing members; nothing joins the set). Evaluate REF-1's seeder-debt trigger and say so.

### OQ-LQ-1-17 — the SNAPSHOT PURPOSE **TIER-3** *(NEW — B5; replaces the first draft's OQ-3)*

Reusing `COMPONENT_KIND_CLASSIFICATION` gets LQ-1 **no snapshot at all.** The only code pinning
CLASSIFICATION components is `build_concentration_snapshot`, hard-bound to
`PURPOSE_CONCENTRATION_INPUT` + `CONCENTRATION_BINDING_PREDICATE`; `_persist_snapshot` refuses any
purpose outside the allow-list (`snapshot/service.py:299`); and **two exact set-equality censuses**
(`test_snapshot.py:1011`, `:1029`) go red the moment either is added.

**RECOMMENDATION: mint `PURPOSE_LIQUIDITY_INPUT` + `LIQUIDITY_BINDING_PREDICATE` +
`build_liquidity_snapshot`**, pinning CLASSIFICATION + CLASSIFICATION_SCHEME + the exposure atoms. Both
censuses are **in-slice amendments with negative controls**. This is the real discharge of CAL-1's
mandate (`cal_1_decision_record.md:437`) — a ratified cross-slice mandate cannot be dissolved by silence.
**Re-scoped OQ-3:** whether the new PURPOSE reuses the CLASSIFICATION serializer content shape
*unchanged* — which is also how T12 gets discharged rather than merely listed. **Recommend: unchanged.**

### OQ-LQ-1-4 — the MODEL fork **TIER-3**

**RECOMMENDATION: model-bound, decisively.** % illiquid embeds at least four methodology choices
(vocabulary version, illiquid partition, as-of convention, coverage floor) and only a registered
`model_version` gives them a versioned, parse-back-enforced declaration site. It also resolves the RTM's
existing `ModelGov = Y` in the direction already recorded, leaving no register to re-sync.

*Precision on arm (B):* the first draft said model-less leaves "nowhere to declare" the partition. More
exactly — the only conceivable site is a node-level attribute on `classification_scheme`/
`classification_node`, which are **hybrid** (OQ-16), so declaring it without a `model_version` costs a
migration on a hybrid table: the very cost arm (B) exists to avoid.

### OQ-LQ-1-5 — the DENOMINATOR **TIER-3** *(REBUILT — B2, H4, H5, M3, M4, M7)*

- **(A) Adopt `INVESTED_LONG`.** The only arm computable from stored rows today. **Error direction is
  sign-INDETERMINATE** (Collision 2). *The first draft's "cross-family basis match stays meaningful"
  benefit is withdrawn — it does not survive scrutiny.*
- **(B) Add a value to CON-1's shared `DENOMINATOR_BASES`** — silently widens what a CONCENTRATION limit
  may declare; needs a migration; re-opens CON-1's ratified single-value guarantee.
- **(C) Wire the dead per-family hook.** `LimitFamily.requires_basis` and `_validate_dimensional_config`
  exist but have **no production consumer**, and the basis vocabulary is hard-coded at
  `limit/service.py:723`. Arm (C) = make the hook real. **This also PAYS LIM-2's `requires_basis`
  inconsistency** rather than recording it.

**RECOMMENDATION: (A) + name the metric `illiquid_share_invested_long`.** The name is the control: a
number called `illiquid_share_invested_long` cannot be silently read as the 22e-4 test, whereas
`pct_illiquid` invites exactly that. **Registered limitation, verbatim:** *"This is NOT the Rule 22e-4
15% test. The denominator is the invested-long book, not net assets; the resulting share may OVERSTATE
or UNDERSTATE the regulatory ratio depending on the book's cash, leverage and short exposure, and the
direction is not determinable without a net-assets figure."*

### OQ-LQ-1-6 — RESULT ROW SHAPE **TIER-3 (grain)**

**RECOMMENDATION: bucket vector** on CON-1's DETAIL/SUMMARY `row_kind` grain, with residual sentinels,
`coverage_ratio`/`coverage_classifiable`, and the illiquid share as a SUMMARY metric. CON-1's kernel
already proves the residual semantics (all residuals stay in the total so shares sum to 1), and
`HIGHLY_LIQUID` coverage falls out of the same vector (OQ-11).

### OQ-LQ-1-19 — the RESIDUAL KIND and the COVERAGE FLOOR **TIER-3** *(NEW — H10; OQ-6 named this question and never answered it)*

An instrument in the pinned exposure set with **no** current-head `LIQUIDITY_TIER` assignment is
**UNCLASSIFIED, not UNCLASSIFIABLE** — so it counts in the classifiable-coverage denominator and **can
trip the floor**. Choosing UNCLASSIFIABLE would make the floor structurally unfireable, which is the
vacuous-guard class this project has shipped twice.

**RECOMMENDATION: UNCLASSIFIED; v1 floor declared as a parse-back-enforced model parameter.**
Consequence stated in one sentence: **below the floor the run commits FAILED with zero rows.**

### OQ-LQ-1-9 — TIER RESOLUTION AS-OF **TIER-3** *(REBUILT — H3)*

*Correction:* the first draft said "this fork only exists on the model-bound arm." **False in both
directions** — the binder must choose a head either way; the model-bound arm is only the one that gives
the choice a *declaration site*.

- **(A) BUILD-time heads** (CON-1's convention).
- **(B) As-of the run's date.**
- **(C) BUILD + a staleness/max-age refusal** — omitted entirely by the first draft.

**RECOMMENDATION: (C).** (A) alone is a non-sequitur for a dataset whose entire point is downgrades:
22e-4 requires review **at least monthly**, so a tier head older than that is a defect the platform
should refuse rather than silently pin. (C) keeps CON-1's platform-wide convention *and* makes staleness
fail-closed. Limitation phrased against the at-least-monthly clause.

### OQ-LQ-1-18 — RESTATEMENT: what happens when a downgrade lands? **TIER-3-adjacent** *(NEW — H9)*

The first draft called downgrades "the whole point of the dataset" and never said what happens to a
committed result when one arrives.

**RECOMMENDATION:** (a) prior COMPLETED runs are **never** mutated (AD-014/IA); (b) the remedy is a NEW
run whose snapshot pins the new head; (c) v1 surfaces no restatement trail — explicit deferral, trigger
*"the first operator ask for a restatement trail"*; (d) a correction arriving **between** snapshot build
and compute is **refused fail-closed**, not absorbed.

### OQ-LQ-1-7 — LIMIT-BINDABILITY **Claude's call** *(REBUILT — H4, M2)*

*Both hidden premises of the first draft's argument were false.* CON-1's deferral has **already fired**;
and "nothing binds" is not a safety argument, because a governed number is read by humans on a screen
(OQ-8). The refusal is re-cited to `limit/service.py:797-799` and `:481-487`.

**RECOMMENDATION: DEFER — grounded in the sign-indeterminate denominator (B2), which is a much stronger
reason.** Trigger: *"a NAV/net-assets entity exists, OR an operator asks for a liquidity threshold."*
Record explicitly that CON-1's deferral has already fired, so the register is not left stale.

### OQ-LQ-1-8 — the FE clause **Claude's call, dispositioned explicitly** *(H5)*

**RECOMMENDATION: ship it**, CON-1's four-file shape plus `make gen-api`. **And make OQ-5's mitigation
structural**: surface the registered limitation on the run-detail screen, bound to the run's
`model_version`. A limitation in a registration table that no shipped screen renders next to the number
**is not a control**. Do not pass `snapshotVerified` unless a real verify call is wired.

### OQ-LQ-1-10 — SPLIT **Claude's call**

**RECOMMENDATION: one slice with a declared split line at the captured-half merge.** The captured half
moves **no** count pin (the triple counts distinct `Model.code` / `ModelValidation` / COMPLETED
`CalculationRun`), so it merges cleanly alone; the governed half then lands with the pin move isolated
and MEASURED.

### OQ-LQ-1-11 — CAP-8.1's third sub-item **Claude's call** *(B3)*

**RECOMMENDATION: ride it** as a second SUMMARY metric — with OQ-15(A) it is the ladder's first
category, so the cost really is near zero. **Scope stated explicitly: LQ-1 ships the coverage NUMBER
only**, never (b)(1)(iii)'s minimum-determination, board-approval or shortfall-reporting regime. Note it
inherits the same denominator caveat (G12d is net-assets-denominated too).

### OQ-LQ-1-12 — REQ-LIQ-002's ratified deferral **Claude's call**

**RECOMMENDATION: write it into both registers** — backbone first, mirrored. LQ-1 is the last Wave-14
slice; if not recorded here the silence becomes permanent.

### OQ-LQ-1-13 — PERMISSIONS **TIER-3 (R-07 mint)**

The captured read and the governed read sit on **opposite sides of the auditor_3l line**.
**RECOMMENDATION: reuse `reference.classification_assignment.view` for the captured read; mint
`liquidity.run` / `liquidity.view` with auditor_3l INCLUDED.** Do not span both with one code — that was
REF-1's BLOCKING defect and the SoD pins are per-code, so no shipped test would catch it. Confirm the
demo principal holds whatever is minted.

### OQ-LQ-1-14 — ENT ids consumed **TIER-3** *(M6)*

**OQ-2 = A ⇒ one** (ENT-071, the result table). **OQ-2 = B ⇒ two.** There are **two** paper-only
reservations, not one. `canonical_data_model_standard.md:97` is self-contradictory on this and the fix
rides in-slice as a ledger-1 correction. **Re-measure the namespace at drafting** — id collisions hit
twice in one day at REF-1.

### OQ-LQ-1-20 — the WAVE-14 CLOSE **Claude's call** *(NEW — L5)*

LQ-1 is the last Wave-14 slice. **RECOMMENDATION: a separate `wave_14_close_review.md` activity after
LQ-1 closes**, following the Wave-13 pattern that produced P1–P7 — not folded into LQ-1.

---

## Part 3 — implementation shape *(NEW — H7; the first draft had no section saying what the slice DOES)*

1. **Captured half.** `LIQUIDITY_TIER` into both declaration sites; the SYSTEM-seeded 22e-4
   `scheme_family` + four `classification_node` rows with ordinals; `list_assignments` +
   `reconstruct_assignment_as_of`; the mixed-VERSION (live-heads, mutation-proven) and mixed-basis
   refusals; the captured read.
2. **Governed half.** New `irp_shared/liquidity/` package (kernel / service / bootstrap / reads).
   **Migration `0061`**: result table, `__temporal_class__`, the three-layer append-only fence
   (`APPEND_ONLY_TABLES`, the `irp_prevent_mutation` trigger, the ORM guard), symmetric FORCE RLS,
   three NOT NULL AD-014 FKs, DETAIL/SUMMARY partial uniques declared for **both** dialects,
   **suffix-only CHECK names**, all DDL identifiers ≤63 in ORM *and* migration.
3. **Snapshot.** `PURPOSE_LIQUIDITY_INPUT` + `LIQUIDITY_BINDING_PREDICATE` + `build_liquidity_snapshot`;
   both set-equality censuses amended with negative controls.
4. **Model.** Registrar + `assert_model_version_of` in the pre-create gate; assumption literals for
   vocabulary version, illiquid partition, as-of convention + staleness bound, coverage floor,
   denominator basis — each parse-back-enforced.
5. **Rule 7 reads (named by name, so the closeout sweep can check it):** `/results`, `/results/latest`,
   `/runs`, `/runs/{id}`, module-level permission singletons, router mounted in `main.py`, **PG-tier pins
   on every non-String filter**.
6. **FE** (OQ-8) + the limitation surfaced on run detail.
7. **Demo stage 23** + the 14-z PG suite + **CI step in the same commit as the suite** + the count-pin
   relay (13-z demoted to positional). **The new triple is MEASURED on a fresh battery, never derived** —
   all arithmetic candidates are inferred and must not be written into a suite.
8. **Registers + the seven-ledger sweep on main after the last merge**, with ledgers 3 (CTRL-002/018
   dispositioned explicitly), 4, 6 and 7 named now.

### The carry sweep *(M11)*

| Slice | Carry | Fires? |
|---|---|---|
| REF-1 | scheme-revision bulk re-capture | **Evaluate at OQ-2** — ladder revisions may fire it |
| REF-1 | seeder debt | **Evaluate at OQ-16** |
| CON-1 | limit registration deferral | **ALREADY FIRED** — record it |
| CON-1 | issuer-edge unpinned hop | Adjacent |
| LIM-2 | classification-basis selector | **Possibly** — first two-basis tenant |
| LIM-2 | `requires_basis` dead hook | **NOT PAID — (C) was NOT taken.** OQ-5 ratified **(A)**, so the hook stays dead. See the correction below |
| CAL-1 | COMPONENT_KIND for pinned tiers | **FIRES — discharged at OQ-17** |
| DATA-1 | yield→return model | Does not fire |
| DATA-1 | trading-calendar wiring | Does not fire (no daily series) |
| RM-1 / SR-1 / SCH-2 / OPS-H1 | — | Do not fire |

> **CORRECTION — the LIM-2 `requires_basis` carry LAPSED (Wave-14 close, 2026-08-03).** The row above
> was written as a conditional and then never resolved: OQ-LQ-1-5 ratified **(A)**, not (C), so the
> hook was NOT wired and the "else recorded" branch was never actually executed. Measured on the
> tree at the Wave-14 close: `grep -n "requires_basis" packages/shared-python/src/irp_shared/limit/`
> returns **exactly one hit** — `service.py:439`, the `LimitFamily` dataclass field declaration.
> **No production consumer, no test, no reader.** The basis vocabulary remains hard-coded at the
> validation site, which is precisely the inconsistency LIM-2 recorded and LQ-1 offered to pay.
>
> **Re-recorded as a live carry with a trigger** (P7 form (b), replacing the conditional that
> silently lapsed): *wire `LimitFamily.requires_basis` to a real consumer, or delete the field.*
> **Trigger: the next slice that adds a `denominator_basis` value or a second basis-bearing limit
> family** — i.e. the same trigger as LIM-2's classification-basis selector, which is the honest
> pairing since both wait on the first two-basis tenant. Until then this is an accepted dead field,
> stated as such rather than left as a promise. **A carry written as "X if Y else Z" is not a carry
> — nobody ever comes back to evaluate the condition**; that is the lesson this row now carries.

**Sizing: L.** P4 commitment: migration `0061` gets an **executed non-vacuous up/down dry run** in a
throwaway workspace before ratification is acted on.

---

## Part 4 — recorded limitations

- **Not the Rule 22e-4 15% test.** Denominator is the invested-long book; direction of error
  **indeterminate** (OQ-5).
- **Instrument grain does not reflect (b)(1)(ii)(B)'s fund-specific position-size determination** (OQ-1)
  — the honest trigger for a future position-grain slice.
- Ships the highly-liquid coverage **number** only, not (b)(1)(iii)'s regime (OQ-11).
- No limit-bindability (OQ-7, triggered); no restatement trail (OQ-18, triggered).
- Does not carry REQ-LIQ-002.

### Still open, carried to the gate

- **The demo coverage question.** How many DEMO-tenant instruments must carry a tier for the flagship run
  to clear the floor and COMPLETE? Below it the run commits FAILED with zero rows. **Unanswered; the count
  pin depends on it; it must be MEASURED, not derived.**
- **ILPA and GIPS were never opened** — "no industry standard applies" would be absence-of-evidence.
- The open LIM-2 anomaly remains unexplained.

---

## Part 5 — the trap inventory

**T1/T2/T3 — the CHECK-name double-prefix.** `migrations/env.py` passes `target_metadata`, so
`op.create_table` **applies** the naming convention: a full name mints `ck_<table>_ck_<table>_<suffix>`,
PG-truncated at 63. `alembic check` does not compare CHECKs; `test_migration_identifiers.py` walks string
*literals* so it structurally cannot catch a name built at DDL time; and `match=` substring assertions
pass against **both** names. Only a live-catalog `pg_constraint` set-equality assertion catches it.

**T4+T5 — one red test, two distinct causes** *(merged at the fold, M1)*. Adding `LIQUIDITY_TIER` turns
`test_concentration_kernel.py:397` red (amend with a stated reason; do **not** "fix" it by adding the kind
to CON-1's tuple). Separately, omitting `BASIS_BY_DIMENSION_KIND` refuses every capture at runtime —
**only an executed capture reaches that one.**

**T7** — `compute(run)` sits outside `execute_governed_run`'s only try; the except tuple must include
`KeyError`/`TypeError`.
**T8** — SQLite affinity makes the non-String filter 500 structurally invisible to the unit tier.
**T9** — nullable columns inside a UNIQUE key are vacuous on PostgreSQL (NULLS DISTINCT).
**T10** — partial uniques must declare both dialects in the ORM.
**T11** — a new COMPONENT_KIND without a `_reresolve_content` branch **always reports drift**, silently.
**T12** — adding a key to an existing serializer falsifies every already-pinned component of that kind.
**T13** *(NEW — H2)* — `entity_type == "instrument"` is **hard-coded** at `snapshot/service.py:4252,4282`.
Any widening of the assignment grain needs an executed pin-then-verify over a non-instrument row.

---

## Part 8 — the verifier fold (2026-08-02)

Four refute-by-default lanes over the draft. Verdicts: **all four REFUTED_IN_PART or REFUTED**;
**6 BLOCKING, 10 HIGH, 11 MED, 5 LOW — all folded**; one finding KILLED as unsupported.

**The two that matter, both in my own reasoning, both found where I aimed the lanes:**

- **B1 (three lanes, independently).** My (a)(8) quote's ellipsis deleted *", as determined pursuant to
  the provisions of paragraph (b)(1)(ii) of this section"* — and (b)(1)(ii)(B) makes position size a
  **mandatory** classification input. So OQ-1's entire legal warrant was contradicted by the paragraph it
  cited, in a recommendation asking the gate to **amend a ratified requirement**. Re-verified by me at the
  fold against the govinfo CFR XML. Same class as RM-1's truncated GIPS quote: *an ellipsis that removes
  the clause that would have refuted the argument.*
- **B2 (two lanes).** "OVERSTATES" was stated unconditionally at four sites and proposed for an
  append-only registered limitation. It **reverses sign** on levered or long/short books. The recon's fact
  was correctly scoped; **I dropped the qualifier.** Proven by executing the shipped kernel.

**B3** — 22e-4(b)(1)(ii) *names* the vocabulary and fixes it at four categories; the draft planned a
"tier ladder" with **no OQ for it**, while declaring the source unsourced — from a document already
fetched. **B4** — zero ADs cited, the twice-repeated BLOCKING class here. **B5** — reusing
`COMPONENT_KIND_CLASSIFICATION` yields no snapshot; the PURPOSE/predicate/builder are the binding
artifacts. **B6** — the `scheme_family` is an invisible AD-013 tenancy decision on hybrid tables.

**What survived attack:** the slice's shape — capture the tier rather than compute it, ride the
classification rail, bucket-vector result, defer limit-bindability. Also independently confirmed: ENT-071
is the next free id; `list_`/`reconstruct_as_of` really are absent; `0056` emits zero CHECKs on
`dimension_kind`; and the captured half really does move no count pin.

**KILLED (recorded so it is not re-folded):** one finding attacked a paraphrase rather than the draft's
words; it survives only as a precision note inside OQ-4.

**The lesson, as an act (P7):** the first draft's fatal quote was *correct where it was quoted and wrong
where it was elided*. The mechanical form — **every primary-source quotation in a decision record is
pasted from a fetched authoritative edition with its locator, and any ellipsis states what was omitted;
a quotation with an unexplained ellipsis is treated as unverified.**

---

## Part 9 — the ratification record (2026-08-02)

**RATIFIED by the user at the Tier-3 gate — "proceed" on the briefed gate, ALL as recommended.**
The briefing named twelve decisions and invited pushback specifically on the two sharpest (grain and
denominator); none was given, and the record was briefed with its own refutation in the open rather
than as a clean plan.

| OQ | Decision | Tier |
|---|---|---|
| OQ-LQ-1-1 | **Instrument grain**, on ENGINEERING grounds only. REQ-LIQ-001's acceptance clause is AMENDED in-slice (backbone → RTM); the (b)(1)(ii)(B) position-size gap is a REGISTERED LIMITATION and the named trigger for a future position-grain slice | 3 |
| OQ-LQ-1-2 | **Ride `classification_assignment`**; `list_`/`reconstruct_as_of` added in-slice (REF-1's gap PAID); the inherited mixed-VERSION refusal computed over LIVE heads and **mutation-proven**, plus the mixed-basis refusal | 3 |
| OQ-LQ-1-15 | **The four 22e-4(b)(1)(ii) codes** — `HIGHLY_LIQUID / MODERATELY_LIQUID / LESS_LIQUID / ILLIQUID`, ordinal, day thresholds as declared scheme semantics; illiquid partition = `{ILLIQUID}`. AIFMD Annex IV's seven day-buckets recorded as an additive `scheme_family` behind the trigger *"the first EU/AIFMD-reporting tenant"* | 3 |
| OQ-LQ-1-16 | **SYSTEM-seeded ladder.** The closed 7-table hybrid set is UNCHANGED — `classification_scheme`/`classification_node` are existing members; nothing joins the set | 3 |
| OQ-LQ-1-17 | **Mint `PURPOSE_LIQUIDITY_INPUT` + `LIQUIDITY_BINDING_PREDICATE` + `build_liquidity_snapshot`**; both set-equality censuses amended in-slice WITH negative controls. This is the discharge of CAL-1's mandate (`cal_1_decision_record.md:437`). Re-scoped OQ-3: the serializer content shape is reused **unchanged** | 3 |
| OQ-LQ-1-4 | **Model-bound** — registered `model_version`, assumption literals parse-back-enforced. Resolves the RTM's existing `ModelGov = Y`; no register goes stale | 3 |
| OQ-LQ-1-5 | **Adopt `INVESTED_LONG`**, metric named **`illiquid_share_invested_long`** — the name IS the control. Registered limitation states the error direction is **INDETERMINATE** | 3 |
| OQ-LQ-1-6 | **Bucket vector** on DETAIL/SUMMARY `row_kind` | 3 |
| OQ-LQ-1-19 | **UNCLASSIFIED**, not UNCLASSIFIABLE — the residual counts in the classifiable-coverage denominator and CAN trip the floor. Floor is a declared parse-back-enforced parameter; below it the run commits **FAILED with zero rows** | 3 |
| OQ-LQ-1-9 | **BUILD-time heads + a staleness refusal** (arm C), phrased against 22e-4's at-least-monthly review clause | 3 |
| OQ-LQ-1-18 | **Never mutate a COMPLETED run**; remedy is a NEW run pinning the new head; no restatement trail in v1 (trigger: *first operator ask*); a correction arriving between snapshot build and compute is **refused fail-closed** | 3-adj |
| OQ-LQ-1-13 | **Reuse `reference.classification_assignment.view`** for the captured read; **mint `liquidity.run` / `liquidity.view`** with auditor_3l INCLUDED. No code spans both sides of the auditor line | 3 |
| OQ-LQ-1-7 | **Defer limit-bindability**, grounded in the sign-indeterminate denominator. Trigger: *a NAV/net-assets entity exists, OR an operator asks for a liquidity threshold*. CON-1's already-fired deferral recorded | C |
| OQ-LQ-1-8 | **Ship the FE entry**; the limitation is surfaced on run detail bound to the run's `model_version` — a limitation no screen renders is not a control | C |
| OQ-LQ-1-10 | **One slice, declared split line** at the captured-half merge | C |
| OQ-LQ-1-11 | **Ride** CAP-8.1's third sub-item as a second SUMMARY metric; LQ-1 ships the coverage NUMBER only, never (b)(1)(iii)'s regime | C |
| OQ-LQ-1-12 | **Write REQ-LIQ-002's ratified deferral into both registers** | C |
| OQ-LQ-1-14 | **One ENT id** (ENT-071, the result table). Two paper-only reservations, not one; `canonical_data_model_standard.md:97`'s self-contradiction fixed in-slice as a ledger-1 correction. Namespace re-measured at drafting | 3 |
| OQ-LQ-1-20 | **Wave-14 close is a SEPARATE activity** after LQ-1 closes, on the Wave-13 pattern | C |

### Binding at the gate

- The **P4 commitment**: migration `0061` gets an executed non-vacuous up/down dry run before
  implementation is trusted.
- The **count triple is MEASURED on a fresh battery, never derived** — every arithmetic candidate in the
  recon is inferred and must not reach a suite.
- The **demo coverage question stays OPEN** and is the count pin's largest uncertainty: below the floor
  the flagship run commits FAILED with zero rows, which moves the pin the other way from every estimate.
- **ILPA and GIPS were never opened.** No "no industry standard applies" claim may be recorded.

---

## Part 10 — the implementation log (2026-08-02, branch `lq-1`)

Fourteen commits. What is worth recording is not the inventory — that is the diff — but the
defects, because every one of them was found by EXECUTION and none by reading.

### Six found while building (commits 1–12)

The binder had never run until the demo stage ran it. In order of how badly each would have shipped:

1. **Untiered instruments were returned as a GAP**, and the binder refuses on any gap — so EVERY
   book containing a single unassessed holding would have FAILED. That inverts the ratified
   OQ-LQ-1-19 semantics entirely: the residual exists so untiered exposure stays in the denominator
   and trips a DECLARED floor, and instead the family refused unconditionally on a hidden absolute.
   **My own kernel tests asserted the buggy behaviour** — written against the implementation rather
   than the requirement, which is why the unit tier was green while the behaviour was wrong.
2. **The refusal control did not refuse.** Floor 0.9 against coverage of exactly 0.9, tested with a
   strict `<`. A control that passes without exercising what it controls proves the opposite of
   what it claims, and it would have shipped as evidence of fail-closed behaviour.
3. **The stage claimed "+1 INITIAL validation" and recorded none** — exposed by the measured
   `(1, 0, 2)`. A governed family with no recorded validation leaves CTRL-003's evidence chain
   broken for the one number the slice exists to produce.
4. `snapshot.components` — an attribute I invented. Every run crashed on it.
5. `TimestampMixin` where the shipped families use `ImmutableAppendOnlyMixin`.
6. `run_liquidity` took a pre-built snapshot instead of an exposure run, breaking the "one call
   builds and computes" contract every other family holds.

### Six more found by the adversarial review (commits 13–14)

Five lanes over the 57-file diff, every finding adversarially verified before it could survive:
**31 of 35 stood; 3 BLOCKING, 3 HIGH.**

**B1 — the staleness refusal was STRUCTURALLY UNFIREABLE.** Found INDEPENDENTLY BY FOUR LANES.
`_parse_pins` read `content["system_from"]`; the assignment serializer emits nine keys and that is
not one. So the guard never entered its body — while `register_liquidity_model` writes an
**immutable model_limitation row** telling every reader the platform refuses a stale ladder, and
OQ-LQ-1-8 requires that text be rendered beside the number. A verifier ran a 3,650-day-old ladder
against a declared 31-day bound: COMPLETED, seven rows. **This is the platform's recorded failure
class exactly — a refusal that exists in prose and in a limitation row and in no code path.** No
test anywhere referenced `GAP_STALE_TIERS`, `tier_max_age_days` or `oldest_assignment_at`.
Fixed by reading `pinned_system_from` (a COLUMN, not an input to the content hash, so no historical
pin moves — widening the serializer would have falsified every already-pinned CON-1 component).
An undateable component now refuses: unknown age is not freshness.

**B2 — `liquidity_result` was never registered in the ORM aggregator**, so `alembic check` emitted
`remove_table` plus seven `remove_index` operations. Autogenerate would have proposed DROPPING an
append-only governed-evidence table. Second omission of its kind ⇒ now a mutation-proven census.

**B3 — `make check` was RED on this branch and I had reported it green.** Nine ruff errors, mostly
my own lines, off a clean `main`. I had been running individual pytest invocations and calling that
the gate. **A gate you did not run is not a gate you passed.**

**H1 — the run's portfolio scope was caller-supplied and never verified**, stamped onto immutable
rows and onto `scope_portfolio_id` while the upstream run was never resolved. Fixed by deriving it;
the parameter is gone from the signature, because a scope that cannot be supplied cannot be
supplied wrongly.

**H2 — an off-vocabulary tier code silently DELETED long money** from the vector: the shares no
longer summed to 1 and the illiquid share was UNDERSTATED — wrong in the unsafe direction, in an
append-only table. Now folded into UNCLASSIFIED with a refusal, plus a structural post-condition
that every long unit is in exactly one bucket.

**H3 — `list_assignments(as_of=…)` returned silent empty for any superseded entity.** The filter
asked a question about NOW while claiming to ask one about THEN. Branch corrected, parameter
renamed `known_at`.

### The lesson, as an act (P7)

Three separate controls in this slice were **written, believed, and inert**: the staleness refusal,
the sub-floor demo control, and my own kernel tests. Each looked like evidence and was not.

**The mechanical form: a refusal is not implemented until a test has made it FIRE, and a control is
not a control until the fix that would break it has been executed against it.**

**CORRECTED at the Wave-14 close (2026-08-03).** This paragraph originally read: *"Every refusal
path in LQ-1 now carries a control that has been mutation-proven — reverting the defect fails the
test."* **That sentence was false when written**, and it is the same defect class the section is
about — a claim ABOUT verification standing in for verification. The close review found the
`build_liquidity_snapshot` builder declaring four refusals (wrong-dimension scheme, mixed live
scheme VERSIONS, mixed basis, empty atoms) with **no test anywhere referencing any of them**, plus
`GAP_STALE_TIERS` and `GAP_CORRUPT_PINNED_CONTENT` likewise unreferenced. "Every refusal path"
quantified over the paths I had fixed, not over the paths that exist — which is exactly what P10
now forbids.

The honest statement: the refusal paths repaired DURING the slice carry mutation-proven controls.
The refusal paths the slice SHIPPED UNTESTED were found by the close review and are now covered by
`test_liquidity_snapshot.py`, each executed against real staged state and each asserting that
NOTHING was persisted. This entry is the grounding evidence for **P9** (a refusal is not shipped
until a test has made it fire) and for **P10** (a fold applies to the class, not the site).

### Gates

`make check` green end to end (2,394 passed); P4 migration dry run executed non-vacuously with rows
STAGED; FE typecheck clean and 207 FE tests green; the count triple **MEASURED at 27/44/141** on a
fresh-schema full-PG battery, never derived.

---

## Part 11 — the close (2026-08-02)

**Merged: PR #168 = `28f76ca`** (the eleventh autonomous merge). **Wave 14 is COMPLETE.**

### The P1 seven-ledger sweep, run AFTER the merge against `origin/main`

| # | Ledger | Result |
|---|---|---|
| 1 | `canonical_data_model_standard.md` | ENT-071 row present; next-free **ENT-072**; the "sole reservation" self-contradiction corrected (TWO paper-only: ENT-032 AND ENT-058) |
| 2 | `audit_event_taxonomy.md` | **Deliberately mints nothing — recorded as a sentence, not left as silence.** The captured half rides REF-1's `REFERENCE.*` events; the governed half rides the standard governed-run chain. A liquidity tier is a classification assignment, not a new audit subject |
| 3 | `control_matrix_skeleton.md` | CTRL-018 dispositioned **NO CONTROL MOVED**, explicitly — REQ-LIQ-001 maps to CTRL-002/018, so silence would be the omission this sweep exists to catch. Third consecutive non-movement, itself the signal it needs a slice. CTRL-002 EXERCISED, not moved |
| 4 | `current_state.md` | CURRENT TRUTH rewritten; head `0061`; NEXT = the Wave-14 close review |
| 5 | `02_requirements/` backbone + RTM | REQ-LIQ-001 acceptance AMENDED with the reason; REQ-LIQ-002's ratified deferral written into both; ModelGov = Y HELD and the §3 count re-measured at 28 |
| 6 | Counts | **27/44/141 MEASURED** on a fresh-schema battery; exactly one file carries FINAL-POSITION (three stale claims swept) |
| 7 | The record's own delivery claims | verified against the merged diff |

**Verify-on-main:** all fifteen slice commits confirmed ancestors of `origin/main`; the merged tree
is **byte-identical** to the tree the 2,954-test battery validated.

### What LQ-1 delivered

The platform can now say what fraction of a book is illiquid, as a governed number: reproducible,
snapshot-pinned, model-bound, and refusable. The captured half mints no entity — a liquidity tier is
a curated code on an instrument, which is structurally what REF-1's rail already carries. The
vocabulary is the regulation's own four categories, transcribed.

It deliberately does **not** claim to be the Rule 22e-4 15% test, and the machinery to prevent that
misreading is the slice's most deliberate work: the metric is named `illiquid_share_invested_long`,
the denominator basis is stamped on every row and every FE column, the limitation rides the
run-detail payload, and limits are refused entirely until a NAV entity exists.

### The close's own finding

**Three separate controls in this slice were written, believed, and inert.** The staleness refusal
existed in an immutable `model_limitation` row promising readers the platform refuses a stale ladder
— and in no code path at all. The sub-floor demo control had a floor exactly equal to the book's
coverage under a strict `<`, so it never refused while standing as evidence of fail-closed
behaviour. And the kernel tests asserted the implementation rather than the requirement, which is
why the unit tier stayed green while the residual semantics were inverted.

**Two gates were reported green having never been run**: `make check` was red on the branch (nine
lint errors off a clean `main`), and `liquidity_result` was absent from the ORM aggregator, so
`alembic check` would have proposed `DROP TABLE` on an append-only governed-evidence table.

Both classes are the same failure: **an artifact that looks like evidence, accepted without being
exercised.** That is what the standing lesson now addresses mechanically.

### Open at the close

1. **Limit-bindability** — deferred. Trigger: *a NAV/net-assets entity exists, OR an operator asks
   for a liquidity threshold.* The sign-indeterminate denominator is the reason.
2. **The restatement trail** — deferred. Trigger: *the first operator ask.*
3. **Position-grain tiers** — deferred. Trigger: the 22e-4(b)(1)(ii)(B) gap becoming operationally
   material. Recorded in the requirement, the model limitations and the entity row.
4. **AIFMD's seven day-buckets** as an additive `scheme_family`. Trigger: *the first
   EU/AIFMD-reporting tenant.*
5. **CTRL-018's scheduled reproduction job** — three consecutive non-movements.
6. **Carried from DATA-1, and belonging to the user:** the independent re-verification of the 30
   TB3MS literals is UNDISCHARGED.

---

*LQ-1 CLOSED. Wave 14 COMPLETE. Next: the Wave-14 close review (ratified OQ-LQ-1-20).*
