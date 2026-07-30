# CON-1 Decision Record — concentration, the 23rd governed number (Wave-14 slice 1)

| Field | Value |
|---|---|
| Status | **DRAFT v4 (2026-07-30) — the DESCOPED form, all 47 second-pass findings folded; awaiting the descoped-form verifier pass (incl. the NEW rule-6a citation lane) before the ratification gate.** History: v1 broke 46 findings deep (5 BLOCKING) including its methodology foundation; the 2026-07-29 dual-share repair was itself REFUTED by the second pass (47 findings, 8 BLOCKING), triggering the user-ratified stopping rule: descope to the `share_invested_long` core with a `denominator_basis` vocabulary (OQ-CON-1-1) rather than fold a third time |
| Slice | Wave-14 slice 1 (roadmap Part 2.18) |
| Realizes | REQ-CRD-003's **concentration half** (CAP-6.4); the spread half split to REQ-CRD-005 at REF-1 |
| Entity | ENT-069 `concentration_result` (IA append-only, run + snapshot + model bound) |
| Migration | `0057` |
| Sizing | M/L |

> **Method.** 6-lane recon fan-out in fresh contexts, instructed to treat REF-1's three recorded
> "carries to CON-1" as unverified claims authored by the same agent now planning this slice (P3).
> It returned 174 verified facts, **64 corrections to the prior records**, 47 costed forks — and
> caught three claims REF-1's MERGED record asserted that were not true (folded separately as
> `3b74a52`; summarized in Part 6). The pre-ratification verifier pass runs before the gate.

## Part 0 — The facts that shape the slice

1. **The scaffold makes a snapshot non-optional.** `execute_governed_run` types `snapshot_id: str`
   while `create_run` types `input_snapshot_id: str | None` — the seam is STRICTER than the model,
   so AD-014 is structurally enforced. There is no "compute concentration live over the latest
   exposure run" path: the exposure atoms and every classification input must be pinned first.
2. **The scaffold catches ONLY `DataQualityError`,** and `compute(run)` is called outside its try
   block. Any other exception leaves the run in RUNNING — the named BT-1 orphan class, with a
   shipped shared assertion (`assert_no_running_orphan`). Every reachable failure must become a
   `gaps` entry before the compute returns.
3. **An exposure row can be negative, and a run's total can be negative.** `quantity` is signed
   with no CHECK; the platform's own first exposure test ships a short leg producing a negative row
   and a negative run sum. This is what makes the denominator a real decision rather than a
   formality.
4. **`instrument.issuer_id` is mutated in place** with only a `record_version` bump and no version
   row — but the prior value IS reconstructable from the audit log, because `update_instrument`
   emits `REFERENCE.UPDATE` with symmetric before/after payloads. *(REF-1's record omitted the
   audit-log half.)*
5. **"Drift-prone" is a property of the SERIALIZER, not of the temporal class.** `verify_snapshot`
   compares only `content_hash` and never `pinned_record_version`, and the field-exclusion
   precedent is shipped and test-pinned (`var_result_content`). A pin over `{id, tenant_id,
   issuer_id}` drifts iff the issuer edge moves and is inert to the other four `_UPDATABLE` fields.
   **REF-1's "EV-flavored, drift-prone" framing foreclosed a design it never evaluated.**
6. **The strongest form of REF-1's own argument, which REF-1 failed to state:** with the edge
   unpinned, `verify_snapshot` returns **ok=True** on a snapshot whose issuer mapping has since
   moved — the governance walk would AFFIRM the reproducibility of a per-issuer number that no
   longer reproduces. A false-positive verify, not a generic gap.
7. **A component-kind mint is not one thing.** It requires a new `SNAPSHOT_PURPOSES` entry
   (omitting it fails every build), a `*_BINDING_PREDICATE` ≤50 chars plus its `_BINDING_PREDICATES`
   entry (import-time assert), a serializer per pinned shape, an explicit-tenant-predicate resolver
   per shape, a `_reresolve_content` branch per kind (**omission = silent permanent drift**), and
   the resolver's exception in verify's except-tuple. *(The wave plan and roadmap both say "a new
   COMPONENT_KIND", singular — understated.)*
8. **`_resolve_latest` picks `matching[0]`,** so a `(run_type, metric_type)` pair that is not unique
   within a run silently resolves to whichever row sorts first — a wrong observed value with no
   error. Every currently registered family preserves per-run uniqueness of its metric rows.
9. **`uq_breach_limit_run` permits at most ONE breach per (limit, run),** so a single wildcard limit
   ("no issuer > 5%") could never record the three issuers it breached on in one run.
10. **The demo's "latest COMPLETED exposure run" is a trap.** DEMO-GLOBAL's latest is not a campaign
    boundary run — it is SCH-2 stage 15's dispatched run, whose book is **99.98% one issuer**
    because that stage marks PE-HARBOR-IV at 10,250,000.00 against the campaign's 1,080.00 for the
    same instrument. DEMO-MULTIASSET is **0% classified** across three completed runs;
    DEMO-ROLLING-RISK is fully classified only by accident and is degenerate (one mark exactly 2×
    the other). **The demo must select its run explicitly** (the SR-1 deterministic-discovery
    lesson), and the coverage policy is forced by these facts rather than chosen freely.
11. **`resolve_ancestors` is FAIL-OPEN on an invisible parent** *(second-pass finding)*: the walk
    `break`s out when a parent row is not visible to the acting tenant and returns a SHORT chain
    rather than refusing — so "the level-1 ancestor" can silently be a nearer node, and a pinned
    closure would hash the truncated chain with `verify_snapshot` staying green. The same
    false-positive-verify harm as fact 6, arriving by a different door. CON-1's sector bucket rests
    on this walk, so the hardening is mandatory in-slice (OQ-CON-1-28).

## Part 1 — The decision ledger (Tier-3, ratify at this gate)

### The methodology (rule 6a research in Part 5)

- **OQ-CON-1-1 — THE DENOMINATOR. Recommend GROSS (sum of absolute values) — but the v1 argument
  for it was WRONG and is withdrawn.** This is the slice's crux and the verifier refuted it at the
  foundation. What v1 claimed, and why each claim fails:
  - v1 cited Regulation 231/2013 Art. 7's "sum of the absolute values of all positions" as a
    concentration denominator. **Art. 7 is the leverage NUMERATOR**; Art. 6(1) of the same regulation
    says leverage is "the ratio between the exposure of an AIF and its **net asset value**". Wrong in
    both role and scope — and Art. 7 also excludes base-currency cash and matched cash borrowings and
    requires derivative→underlying conversion, none of which this platform does.
  - v1 cited CESR/10-788 as mandating absolute values. **The absolute value there is applied AFTER
    netting** (the guideline is netting-*permissive*), and its denominator is NAV throughout
    ("not greater than 100% of NAV").
  - v1 cited ESMA/2013/1339 ¶84/91/93 for no-netting long/short. Those paragraphs are accurate and
    govern the **numerator** — which the long/short decomposition already satisfies. **¶87, sitting
    between the two paragraphs v1 cited, gives the denominator as "percentage in terms of total value
    of assets."**
  **The honest argument, which v1 omitted:** this platform has **no cash, liability or NAV entity**,
  so neither a NAV nor a total-assets denominator is computable today. Gross is the only denominator
  that can be derived from what the platform actually holds and audited from the stored row
  (`gross == long + |short|`). A signed-net denominator additionally explodes on a market-neutral
  book, and Part 0 fact 3 proves negative totals are reachable here.
  **The consequence, recorded as a first-class limitation rather than buried:** because
  gross ≥ |net|, and gross exceeds total assets whenever shorts exist, **a gross-based share
  UNDERSTATES every regulatory ratio** — the FAIL-OPEN direction, on exactly the long/short books
  reason (iii) invokes. So **CON-1's primary share is NOT the UCITS Art. 52, IRC §851(b)(3),
  Solvency II or BCBS ratio**, and the registered model assumptions must say so in those words.
  **RE-RATIFIED 2026-07-30 — the DESCOPE (the stopping rule applied; supersedes the 2026-07-29
  dual-share ratification, which the second verifier pass REFUTED).** The refutation: `sum(long_amount)`
  does NOT equal total assets even on a long-only book — total assets additionally include **cash, cash
  items and receivables** (IRC §851(b)(3)(A)(i) enumerates them; the UCITS "total value of assets" basis
  is the same class), none of which the platform holds as entities — so `share_total_assets` OVERSTATES
  every share and LIM-2 would have written **false breaches into an append-only, non-withdrawable
  lifecycle**. The 2026-07-29 fold RELOCATED the fail-open defect rather than removing it; recorded here
  AT the gate (the SCH-2 reversal rule). Two consecutive refuted foundations triggered the 2026-07-30
  stopping rule (user-ratified): descope to the defensible core rather than a third fold. The core:
  - CON-1 ships ONE share: **`share_invested_long(bucket) = bucket long_amount ÷ Σ long_amount`** —
    numerator = the bucket's LONG exposure (no netting; the bucket's shorts are evidence, not
    numerator), denominator = the run's invested-long total, **named for what it IS** (share of the
    invested long book), always computable from stored rows, auditable from the evidence columns.
    Shares sum to 1 across the classified buckets plus the residual buckets (OQ-CON-1-4).
  - Every share row carries **`denominator_basis`**, a controlled-vocabulary column with the single v1
    value `INVESTED_LONG` — so a future NAV or total-assets denominator is an ADDITIVE vocabulary value
    on new rows, never a reinterpretation of shipped ones.
  - The registered model assumptions state, in these words: **this share is NOT the UCITS Art. 52,
    IRC §851(b)(3), Solvency II or BCBS ratio; no denominator those regimes require is computable on
    this schema.** The limitation stays first-class, exactly as the paragraph above records it.
  - **The LIM-2 named acceptance constraint (replaces the refuted flag-binding):** a limit may bind ONLY
    to a `denominator_basis` whose semantics its threshold was written against; regulatory-shaped
    thresholds are therefore **REFUSED fail-closed AT LIMIT DEFINITION** until a basis matching a
    regulatory denominator exists. Definition-time refusal is load-bearing: it means NO evaluation-time
    suppression path exists, so the second pass's NEVER_EVALUABLE hazard (a regulatory limit silently
    ceasing to evaluate when a book takes a short, indistinguishable from never-ran) is structurally
    unreachable — `_resolve_latest` never sees a NULL share. **Trigger for the real ratio:** a
    cash/liability/NAV entity — the first consumer needing a NAV-denominated share (unchanged).
  - **The long-only identity, stated so the tests can use it honestly:** on an all-long book
    `gross == long` for every bucket, so `share_invested_long` coincides with the withdrawn gross
    share there — which means the DEMO (long-only) cannot distinguish the two denominators. The
    distinguishing case is therefore pinned in the unit + PG tiers on a short-bearing book: the
    denominator must EXCLUDE the short leg (`Σ long`, not `Σ long + |short|`) and the numerator must
    exclude the bucket's own shorts. A suite without that book would leave the descope untested.
  **Refusal:** a zero invested-long total is refused as a `gaps` entry, never divided by (gross/long/
  short/net evidence columns are unchanged by the descope).
- **OQ-CON-1-2 — the measure set. Recommend share + CR-N + HHI**, with effective-number-of-holdings
  rendered at the read surface rather than stored (it is `1/HHI`, a pure derivation).
  Share-of-total is mandatory — it is the numerator shape every cited regime thresholds (UCITS
  Art. 52's 5/10/40 against NAV; IRC §851(b)(3)'s diversification tests against total assets;
  Solvency II's CT_i × Assets; BCBS's 25% of Tier 1) even though, per OQ-CON-1-1, NONE of their
  denominators is computable here. CR-N and HHI are the two measures with authoritative external
  definitions and established fund/index application, and **both are pure functions of
  `share_invested_long` — the SINGLE basis; with the descope there is no which-share ambiguity to
  record**. CR-N's cardinality is part of the metric identity (`CR_5_ISSUER`, OQ-CON-1-13), so a
  CR-5 threshold can never be silently compared against a CR-10 observation after a model bump —
  the RM-1 grain hazard, answered in the vocabulary rather than with extra columns. Cheap in-slice,
  and a later slice adding them would have to re-open this table. **Normalized HHI (H\*) is
  excluded from v1** with the trigger "a consumer needs cross-book comparability at differing N".
- **OQ-CON-1-3 — HHI scale and the residual. Recommend the FRACTION (0–1) form**, and the
  load-bearing requirement is that the scale be **DECLARED in the registered model assumptions**,
  not which form is picked.
  **CORRECTED from v1:** the stored HHI is **not** "exactly the sum of the stored shares squared" at
  the platform's quantum — quantize-then-square differs from square-then-quantize by up to N ulps
  (Part 2 shows 0.356057 stored from unrounded ratios vs 0.356058 from the quantized shares). A test
  written to v1's identity would FAIL on v1's own reference values.
  **FOLDED (second pass): HHI excludes the residual buckets, and the identity says so.** The same
  principle OQ-CON-1-4 applies to CR-N and MAX — a residual is not a concentration, and including
  `share_UNCLASSIFIED²` would fail the identity by up to 0.09 on a 30%-unclassified book (five
  orders above tolerance) while treating "the part we could not classify" as one concentrated
  holding. The identity is therefore stated over the CLASSIFIED buckets with a tolerance:
  `abs(HHI − Σ_classified stored_shareᵢ²) ≤ N_classified·10⁻ˢᶜᵃˡᵉ`. The known consequence is
  declared as a model assumption: on a partially-covered book HHI is downward-biased by coverage —
  which is exactly what the OQ-CON-1-4 coverage floor bounds, and why `coverage_ratio` rides every
  summary row. The fraction-form decision survives on the no-magic-constant argument alone: under
  the 0–10,000 convention every threshold and derivation carries a 10⁴ factor a later reader cannot
  recover from the column, and a mis-scaled value is silently plausible.
- **OQ-CON-1-4 — unclassified exposure. Recommend an explicit UNCLASSIFIED bucket carried IN the
  denominator, plus a first-class coverage field — AND a declared minimum-coverage refusal.** Both,
  in that order. Dropping unclassified exposure shrinks the denominator so every reported share is
  overstated *while still summing to 1* — self-consistent and systematically wrong, invisible at the
  read surface. But the bucket alone produces a false green: a max-issuer-share limit over a
  40%-unclassified book reads as in-appetite. So coverage is also gated by a **declared model
  parameter** with a fail-closed refusal below it. `instrument.issuer_id` is nullable by design, so
  a gap is the normal state of a real book, not an error — which is exactly why it must be
  *visible* rather than either silently dropped or fatally refused.
  **Also ratified (v1 omitted it):** the UNCLASSIFIED bucket is **excluded from the CR-N and MAX
  rankings**. It is a residual, not a concentration; leaving it rankable would let "the largest
  bucket" be "the part we could not classify", and `MAX_SHARE_ISSUER` — the metric a wildcard limit
  binds to — would breach on ignorance rather than on concentration.
  **FOLDED (second pass): "unclassifiable by design" is split from "unclassified by omission", so
  the refusal cannot fail-closed on a correct book.** `instrument.issuer_id` is nullable BY DESIGN
  (cash/FX/index carry no issuer), so a 30%-cash book has coverage 0.70 through no data-quality
  fault — a floor over raw coverage would refuse a correct book. TWO residual buckets, both
  computable from stored columns: **`UNCLASSIFIABLE`** (`issuer_id IS NULL` — no issuer edge exists
  by design) and **`UNCLASSIFIED`** (an issuer edge exists but no assignment covers the dimension).
  Both stay IN the share denominator and OUT of the rankings and HHI. The declared coverage floor
  gates **classifiable coverage** = `classified ÷ (classified + UNCLASSIFIED)` — the omission rate
  among instruments that COULD be classified — while raw `coverage_ratio` (classified ÷ total) is
  stored alongside so the read surface shows both facts.
- **OQ-CON-1-5 — dimension uniformity. Recommend the IDENTICAL measure set for every dimension**,
  with the dimension differing only in its bucketing rule and its scheme pin. The measures are
  dimension-agnostic in every source surveyed, and per-dimension sets would make a new dimension
  *code* rather than *data* — defeating the MG-01 genericity REF-1 deliberately built into
  `dimension_kind`.

### The AD-014 pin (REF-1's carry, re-argued)

- **OQ-CON-1-6 — pin the instrument→issuer edge. Recommend YES** — but note this replaces REF-1's
  binary framing, which the recon refuted. The operative doctrine is "the snapshot binds exactly the
  inputs its consumer uses (TR-09)", and the issuer edge is unambiguously such an input. Refusing
  the per-issuer half instead would abandon REQ-CRD-003's literal acceptance.
- **OQ-CON-1-7 — pin content: a MINIMAL key set `{id, tenant_id, issuer_id}`, not the full EV
  identity. Recommend the narrow pin.** Under a full-identity serializer an ordinary rename,
  `instrument_type` edit, currency fix or `is_active` flip — all in `_UPDATABLE` — would redden
  every historical concentration snapshot: the exact drift harm REF-1 rejected EV assignments to
  avoid, reintroduced by CON-1's own hand, and a live path since demo stage 18 already runs
  `update_instrument`. Two mandatory guards: a test that the narrow pin **does** drift when the
  issuer moves, and a test that it does **not** drift on each excluded field.
- **OQ-CON-1-8 — also denormalize the resolved issuer into the result row. Recommend YES, in
  addition to the pin — never instead of it.** `exposure_aggregate` is the platform's own precedent:
  it captures its inputs in the result row for self-auditing *and* pins them as components. A
  denormalized value alone does not satisfy AD-014.
- **OQ-CON-1-9 — classification pin: assignment rows PLUS the resolved ancestor chain. Recommend
  the chain**, which corrects OQ-REF-1-25. **The causal mechanics, CORRECTED by the second pass
  (v3 stated them inverted):** because `resolve_ancestors` walks parents **by id**, an ANCESTOR
  override row (a new row with a new id) is never reached — it is INERT and cannot move the bucket.
  The live drift door is the **LEAF**: `resolve_node` prefers the tenant's own row for the same
  `(scheme_id, code)`, so a later LEAF override changes the resolved node — and with it the whole
  chain — **with no pinned byte changing** if only assignments were pinned; verify would stay green
  while the number became unreproducible. The conclusion (pin the ancestor closure) survives via
  the leaf path, and the mandatory negative control is a LEAF override that must redden the pin.
  The second reason stands unchanged: a whole-scheme node-set hash would false-drift on any
  unrelated node ADD, which `create_node` permits and the demo's partial skeleton invites. The pin
  is therefore scoped to **the ancestor closure of the pinned leaf codes**.
- **OQ-CON-1-10 — mixed-scheme-version aggregation: refuse PRE-BUILD, not at compute. Recommend
  pre-build.** Every snapshot table is IA true append-only, so a snapshot built over a mixed-version
  set is immutable governance garbage that cannot be withdrawn — the same reasoning the codebase
  already gives for every pre-write refusal.
- **OQ-CON-1-11 — as-of reconstruct for the pinned assignments. Recommend pinning current heads in
  v1 — with the honest premise the second pass forced.** v3 justified this with "CON-1's input is a
  now-anchored 'latest COMPLETED' selection, so a backdated `valid_at` has no consumer" — which
  OQ-CON-1-20 CONTRADICTS: the demo selects a BOUNDARY run explicitly, never "latest", so the
  backdated consumer exists in this very record. The real justification is narrower and stands
  without the false premise: nothing exists to reconstruct against (shared-python has no assignment
  as-of read), and shipping the bitemporal read now would make its only exercise its own test — the
  P5 vacuity pattern. The consequence is therefore DECLARED as a registered model assumption rather
  than argued away: **classification is as-of-BUILD, not as-of-run — a concentration run over a
  backdated exposure run buckets by the classification heads current when the snapshot was built**,
  and the pin records exactly which heads those were. Trigger unchanged: "the first consumer
  needing an as-of-run classification".

### Shape, limits-readiness, and scope

- **OQ-CON-1-12 — model-bound, not model-less. Recommend registering a `model_version`.** Three
  code reasons: all three surveyed result tables carry NOT-NULL `model_version_id` while the sole
  model-less family has no such column at all, so model-less changes the table spine rather than a
  flag; and the denominator convention, the top-N cardinality and the HHI scale are **methodology**
  — precisely what a registered model version exists to pin. Declared parameters ride
  `model_assumption` rows behind a `declared_concentration_parameters()` with an exact-identity
  refusal (the `declared_var_parameters` precedent) — **never** `assumption_set_id`, which has zero
  writers in the repo and would make CON-1 the first writer of a dead column.
- **OQ-CON-1-13 — result shape: per-bucket detail rows AND run-level summary rows in ONE table**,
  discriminated by an explicit **`row_kind`** column (`DETAIL` | `SUMMARY`, NOT NULL — the second
  pass proved `metric_type` alone cannot discriminate: the two grain constraints were jointly
  unsatisfiable without it; see Part 3). Detail rows carry `metric_type = 'SHARE'`,
  `dimension_kind` + the bucket identity + gross/long/short/net + `share_invested_long`. Summary
  rows carry the limit-selectable metrics in `metric_value`. **The summary `metric_type` ENCODES
  the dimension AND, for CR-N, the cardinality** — the EXACT census, with lengths measured against
  the shipped `String(30)`: `MAX_SHARE_ISSUER` (16), `MAX_SHARE_SECTOR_INDUSTRY` (25),
  `MAX_SHARE_COUNTRY_OF_RISK` (25), `HHI_ISSUER` (10), `HHI_SECTOR_INDUSTRY` (19),
  `HHI_COUNTRY_OF_RISK` (19), `CR_5_ISSUER` (11), `CR_5_SECTOR_INDUSTRY` (20),
  `CR_5_COUNTRY_OF_RISK` (20), `SHARE` (5) — longest 25 ≤ 30, and the census test pins the set
  exactly (v3 wrote `HHI_SECTOR` in one part and `HHI_SECTOR_INDUSTRY` in another; the shipped
  dimension value is `SECTOR_INDUSTRY`, so the LONG forms are canonical). Encoding the dimension is
  forced because `_resolve_latest` picks `matching[0]` and would otherwise silently resolve to
  whichever bucket sorts first (Part 0 fact 8).
- **OQ-CON-1-14 — dimension identity: a SCHEME-QUALIFIED pair (`scheme_id` + `node_code`), not a
  node FK and not a bare code. Recommend the pair.** A node FK is refused on the same principle
  REF-1 applied to assignments — PostgreSQL referential checks bypass RLS, so an FK would let a
  proprietary row reference a hybrid node its own `USING` cannot see. A bare code is ambiguous
  across schemes. This is also LIM-2's frozen selector, so it is fixed here with limits-readiness
  as a named acceptance constraint.
- **OQ-CON-1-15 — register the metrics in `_METRIC_MAP` in-slice. Recommend YES.** REQ-CRD-003's
  acceptance verb is literally "Limits-ready metrics **produced**", so leaving registration to LIM-2
  would mean the REQ cannot honestly advance at CON-1's close. With the descope each summary
  `metric_type` maps to the single `MetricSpec.result_attr = metric_value` — the one-attr shape
  `_METRIC_MAP` can represent; no basis selection rides the map (`denominator_basis` is an ECHO on
  the row, not a selector, until a second basis exists). **The resolver fold (second pass):** the
  family dispatch's current `if …VAR… else: # ACTIVE_RISK` becomes `elif` per family plus a
  **fail-closed `else` raise** — a third family must never silently route into another family's
  latest-read and surface as NEVER_EVALUABLE. **And `_METRIC_MAP` gains its FIRST exact
  set-equality census in this slice** (P6): v3 claimed the census existed to be updated; grep shows
  NO census over `_METRIC_MAP` exists anywhere, and `SNAPSHOT_COMPONENT_KINDS` carries only
  membership asserts — CON-1 upgrades that to set-equality too, and the reflective
  `SNAPSHOT_PURPOSES`/`_BINDING_PREDICATES` censuses are self-deriving and need no edit (stated
  accurately this time).
- **OQ-CON-1-16 — the wildcard appetite rule binds to the run-level MAX metric, not to N
  per-bucket limits. Recommend the MAX form** — close to forced, because `uq_breach_limit_run`
  permits one breach per (limit, run), so a per-bucket wildcard could not record the three issuers
  it breached on. **REFRAMED by the second pass + the descope:** the example is an INTERNAL
  concentration appetite ("flag any issuer above 5% of the invested long book"), NOT the IRC test —
  §851(b)(3)'s 5% is a condition inside the 50%-of-total-assets basket, applies only to "other
  securities" (Government securities, other RICs' securities and cash items are expressly outside
  it), and a flat MAX-over-all-buckets wildcard would breach on a Treasury-heavy book that is fully
  compliant. Under the descope no IRC-shaped limit is bindable at all (OQ-CON-1-1); the MAX metric
  serves the internal-appetite form, which is what LIM-2 can honestly offer.
- **OQ-CON-1-17 — NOT schedulable in CON-1. Recommend deferring.** It buys zero limits-readiness
  (`evaluate_limit` discovers via `calculation_run`, not `scheduled_run`, so a MANUAL run is already
  limit-checked) and costs a migration amending the total-enumeration
  `ck_schedule_model_version_by_family` CHECK. Trigger: the first operator ask for an unattended
  concentration cadence.
- **OQ-CON-1-18 — ENT-032 `limit_utilization` stays RESERVED.** Out of CON-1's scope entirely:
  utilization is a pure function of two values `_resolve_latest` already returns plus the frozen
  threshold, over a run id `LimitHealth` already carries.
- **OQ-CON-1-19 — host package: a new `concentration/`, not inside `risk/`. Recommend the new
  package.** Concentration is neither a risk model nor a performance measure, and burying it in
  `risk/` would inherit the snapshot-import exemption silently. Amending the allow-list is the
  visible act that keeps the fence honest.

- **OQ-CON-1-23 — the bucket identity and the grain, REDESIGNED (the second pass proved v3's two
  CHECKs jointly unsatisfiable and its detail UNIQUE vacuous).** The v3 defects, so the gate can see
  what forced this: (a) the summary `MAX_SHARE_ISSUER` row had to carry `dimension_kind='ISSUER'`,
  which the per-kind CHECK forced to `issuer_id NOT NULL`, while the row-kind CHECK forbade bucket
  identity — no row could satisfy both; (b) nullable `issuer_id` sat INSIDE the detail UNIQUE, and
  PostgreSQL's NULLS-DISTINCT semantics made the grain constrain NOTHING for every sector and
  country row — vacuous for both dimensions REF-1 actually shipped. **The redesign:**
  - **`row_kind`** (`DETAIL` | `SUMMARY`), NOT NULL, total-enumeration CHECK — the discriminator the
    v3 constraints were missing (OQ-CON-1-13).
  - **`bucket_code`**, TEXT NOT NULL — the single keyed bucket identity: the node code for
    classification kinds; the issuer id's canonical string for `ISSUER`; the declared sentinels
    `UNCLASSIFIED` / `UNCLASSIFIABLE` for the residuals; `SUMMARY` for summary rows. Every key
    column NOT NULL — the NULL-vacuity class is structurally gone.
  - **`issuer_id`** stays a nullable GUID FK convenience column OUTSIDE every unique key
    (intra-tenant; FK legal here — `issuer` is same-tenant proprietary, so no RLS-bypass concern),
    with row-kind-qualified CHECKs: `row_kind='DETAIL' AND dimension_kind='ISSUER' AND bucket_code
    NOT IN (sentinels)` ⇒ `issuer_id IS NOT NULL`; `row_kind='SUMMARY'` ⇒ `issuer_id IS NULL`.
    `bucket_code == str(issuer_id)` is a service invariant with a PG-tier test (a cross-column cast
    CHECK is not portable to the SQLite tier).
  - **`scheme_id`** becomes a nullable ECHOED column outside the keys (NOT NULL for classification
    detail rows via CHECK, NULL for ISSUER/summary rows) — within one run OQ-CON-1-24 admits ONE
    live scheme per dimension, so `(dimension_kind, bucket_code)` is unique without scheme
    qualification and no GUID sentinel is needed (v3's "scheme_id-or-sentinel" in a uuid column had
    no declared literal, no FK story, and PG/SQLite divergence).
  - The two grain constraints become **PARTIAL unique indexes with their predicates STATED**:
    summary `UNIQUE(calculation_run_id, metric_type) WHERE row_kind = 'SUMMARY'`; detail
    `UNIQUE(calculation_run_id, dimension_kind, bucket_code) WHERE row_kind = 'DETAIL'`. Partial
    indexes are PG-only semantics — the PG tier carries the duplicate-refusal negative controls for
    BOTH row kinds including a duplicate `UNCLASSIFIED` row (SQLite is structurally blind here).
  **`ISSUER` remains a CON-1-owned `dimension_kind` value, NOT added to
  `classification.DIMENSION_KINDS`** — no assignment row can carry it — and that split is pinned by
  a test. The per-kind CHECK census + the row_kind census + the metric_type census each ship WITH
  their P6 floor.
- **OQ-CON-1-24 — CO-EXISTING schemes (REPAIRED: the second pass proved v3's clauses (i) and (iii)
  contradicted each other and its discriminator was not computable from the pinned set).**
  REF-1's current-head key includes `scheme_id` precisely so one instrument may carry an ISIC
  sector AND a NACE sector at once — a permanent legal state. **Recommend:** (i) the refusal
  discriminator is "more than one live `scheme_id` within the SAME (`dimension_kind`,
  `scheme_family`) among the pinned assignments" — ISIC Rev. 5 + Rev. 6 refuses (mixed VERSIONS of
  one family), while ISIC + NACE co-existing stays legal exactly as clause (i)'s own rationale
  requires; (ii) `scheme_id` is an **explicit run input**, pinned in the snapshot and echoed on the
  result row, so the number records which taxonomy produced it — and to make BOTH clauses
  computable from pinned bytes, **the referenced `classification_scheme` rows (`id`,
  `scheme_family`, `version_label`) become a FOURTH pinned shape** (v3's discriminator needed
  `scheme_family`, which lives only on the scheme row and was pinned nowhere); (iii) *(REPLACES
  v3's contradictory refusal)* assignments in the same dimension under a DIFFERENT family than the
  requested scheme are simply **not consumed** — the instrument reads as UNCLASSIFIED for this
  run's dimension, visible in coverage, refusing nothing that clause (i) declared legal.
- **OQ-CON-1-25 — the R-07 permission mint, RE-DECIDED (the second pass proved v3 re-committed
  REF-1's SoD defect in the identical shape while citing the lesson).** The refutation: CON-1
  denormalizes the resolved proprietary issuer into the result row (OQ-CON-1-8) and ships reads
  over it, and the bootstrap DELIBERATELY excludes `auditor_3l` from `reference.issuer.view`,
  `reference.legal_entity.view` AND `reference.classification_assignment.view` — the comment says
  the split codes "exist precisely so this line can differ from the others". One auditor-included
  `concentration.view` over rows carrying `issuer_id` (and the issuer's name at the read surface)
  hands the 3L auditor exactly the proprietary-identity read three prior mints refused it — and the
  per-code `_holders` pin would PASS on the defective set, because SoD pins are per code.
  **Recommend a THREE-code mint split by what the read exposes** (the REF-1 pattern):
  - **`concentration.run`** — execute runs; operators/2L, named holder set pinned both directions.
  - **`concentration.view`** — summary metrics + sector/country detail buckets (no issuer identity
    anywhere in the payload): **`auditor_3l` INCLUDED** — the governed-output remit.
  - **`concentration.issuer.view`** — the ISSUER-dimension detail reads and any payload carrying
    `issuer_id`/issuer name: **`auditor_3l` EXCLUDED**, consistent with the three prior
    issuer-identity refusals.
  Every code's holder set is NAMED in the implementation plan and pinned `_holders(code) == {...}`
  in both directions, and a route-level test asserts the issuer-bearing endpoints demand the
  `.issuer.view` code (the pin alone cannot catch a mis-scoped route — REF-1's own finding).
  *(Tier-3: the split and the auditor's exclusion from issuer-identity reads are the gate's call.)*

- **OQ-CON-1-26 — the `basis` discipline (NEW; the second pass found `basis` — the mechanism REF-1
  built expressly to protect concentration numbers — absent from CON-1 entirely).**
  `BASIS_BY_DIMENSION_KIND` admits FOUR bases for COUNTRY_OF_RISK, the current-head uniqueness
  index deliberately EXCLUDES `basis`, and two instruments in the same book may legitimately carry
  different bases — so "the country buckets" of a mixed-basis book aggregate judgments made on
  different definitions of country, silently. **Recommend, fail-closed:** (i) `basis` rides the
  pinned assignment shape (it is a column on the row; pinning the row without it would be a
  deliberate exclusion); (ii) a PRE-BUILD refusal when the pinned assignments for one
  `dimension_kind` carry MORE THAN ONE basis — mixed-basis aggregation is refused exactly as
  mixed-scheme-version aggregation is (OQ-CON-1-10, same immutable-garbage rationale); (iii) the
  single surviving basis is ECHOED on that dimension's detail and summary rows, so the number
  records which definition of country produced it. Trigger for per-basis bucketing: a consumer
  needing two bases side by side.
- **OQ-CON-1-27 — REF-1's ratified-but-unbuilt capture guard, PAID HERE (the FIFTH undelivered
  REF-1 ratification, found by the second pass).** OQ-REF-1-1 ratified: a vendor row whose asserted
  sector contradicts its industry's ancestor is **refused fail-closed, naming both codes** —
  `capture_assignment` performs no such check today, and under the OQ-REF-1-8 current-head key the
  contradiction is a reachable stored state. CON-1's sector bucket rests on ancestor consistency,
  so the guard is IN-SLICE mandatory scope: a small `capture_assignment` extension (compare the
  asserted node's ancestor chain against the same capture's sibling assertion where both dimensions
  arrive together), negative-controlled with the contradicting pair. Recorded in Part 6 as REF-1
  debt, paid rather than re-deferred, because deferring it would leave the guard's absence
  invisible for another slice.
- **OQ-CON-1-28 — `resolve_ancestors` becomes FAIL-CLOSED on an invisible parent (Part 0 fact 11).**
  The walk currently `break`s and returns a SHORT chain when a parent row is not visible to the
  acting tenant — CON-1 would bucket on a nearer node and pin a truncated closure with verify
  green. **Recommend:** the walk RAISES (a `gaps`-mapped refusal in the binder) when a parent id
  resolves to no visible row, with a positive control (a reachable chain still resolves) and a
  negative control (an orphaned parent id refuses). This is a REF-1 resolver hardening shipped in
  CON-1 because CON-1 is its first governed consumer; the demo's SYSTEM chain is unaffected.

### Demo

- **OQ-CON-1-20 — the demo selects its exposure run EXPLICITLY by boundary, never "latest".
  Recommend explicit selection** — forced by Part 0 fact 10: the latest DEMO-GLOBAL run is SCH-2's,
  which is 99.98% one issuer and would make the flagship demo absurd. The stage resolves the
  portfolio by code, selects the campaign boundary run, and **asserts exactly one match** (the SR-1
  deterministic-discovery pattern).
- **OQ-CON-1-21 — the demo needs a PARTIALLY classified book, and the second pass proved v3's two
  options were BOTH unrealizable, so the book is now designed explicitly.** v3 proposed "classify a
  subset" (impossible: assignments are at INSTRUMENT grain and every exposure-bearing instrument is
  already classified by stage 18 — no portfolio can un-classify them) or "a dedicated portfolio
  with one DEMO-GLOBAL instrument unclassified" (same impossibility). **The fold: a NEW dedicated
  portfolio `DEMO-CONCENTRATION` with THREE NEW instruments**, one per coverage class — CN-ALPHA
  (issuer-bearing, classified on both dimensions), CN-BETA (issuer-bearing, deliberately
  UNCLASSIFIED), CN-CASH (no issuer by design → UNCLASSIFIABLE) — plus its own exposure run and
  concentration run, so the UNCLASSIFIED and UNCLASSIFIABLE buckets, both coverage fields, and the
  residual-exclusion from rankings/HHI are all demonstrated on reachable data (reference values in
  Part 2). DEMO-GLOBAL's boundary run stays the flagship 100% book; DEMO-MULTIASSET stays the 0%
  refusal negative control. Priced in Part 4; it moves the counts (OQ-CON-1-22).
  **Also recorded:** CR-N is degenerate on these small books (CR-5 == the classified total), so
  CR-N ships demonstrated-degenerate in the demo with its REAL coverage in the unit tier on a
  seven-bucket fixture — the P5 pattern, labelled rather than hidden.
- **OQ-CON-1-22 — counts MOVE, and the expected triple is PINNED here (v3 left N unpinned — "the
  same 'pins nothing' defect the OQ accuses v1 of, one level down").** One new model code
  (`concentration.dimensional` — fixed at the gate), one INITIAL validation record, and THREE new
  COMPLETED runs: DEMO-GLOBAL's concentration run, DEMO-CONCENTRATION's exposure run, and
  DEMO-CONCENTRATION's concentration run. DEMO-MULTIASSET's refusal is PRE-BUILD (OQ-CON-1-10/24
  semantics): the stage exercises it and asserts NO run row is created — a refusal that leaves a
  FAILED run would count, and the stage pins that it does not. **The declared triple: 25/40/133 →
  26/41/136.** Per P4's binding clause this is a dated planning-time reading, RE-MEASURED against
  the merged artifact at closeout, never carried forward as a pin. The final-position pin relays to
  CON-1's suite (ten `z`, verified by `ls`, not read off this record). **Census obligations,
  restated accurately (v3 claimed censuses that do not exist):** `_METRIC_MAP` has NO census today —
  CON-1 CREATES its first exact set-equality census (P6); `SNAPSHOT_COMPONENT_KINDS` has only
  membership asserts — upgraded to set-equality here; the `SNAPSHOT_PURPOSES`/`_BINDING_PREDICATES`
  censuses are reflective (self-deriving) and need no edit when the new constants land.

## Part 2 — Independently computed reference values

Per the standing rule that expected values must be derived **independently of the implementation**,
these are hand-computed from the demo fixtures (`campaign.py` marks, quantities and FX), for
DEMO-GLOBAL boundary run r0 (`as_of` 2026-05-18, base USD):

| Instrument | Quantity | Mark | FX | Exposure |
|---|---|---|---|---|
| EQ-ACME-US | 400 | 150.00 USD | 1 | 60,000.000000 |
| EQ-EURX-DE | 300 | 95.00 EUR | 1.080000000000 | 30,780.000000 |
| PE-HARBOR-IV | 50 | 1,080.00 USD | 1 | 54,000.000000 |

All three are long, so gross == long == signed net == **144,780.000000** on this run — meaning
`share_invested_long` (denominator Σ long) coincides with every share below, `coverage_ratio` =
**1.000000**, classifiable coverage = **1.000000**, and there is no residual bucket. This is why
the suite must ALSO cover a short-bearing book (the OQ-CON-1-1 identity note): the demo cannot
distinguish the invested-long denominator from the withdrawn gross one.

**Issuer shares:** ACME-CORP 0.414422, HARBOR-GP 0.372980, EURX-AG 0.212598 (sum 1.000000).
**Sector shares** (ISIC level-1 ancestors: C26→C, C28→C, K64→K): **C = 90,780.000000 → 0.627020**;
**K = 54,000.000000 → 0.372980**. Two holdings rolling into one sector is what makes the number
non-trivial — a book with one holding per sector could not demonstrate concentration at all.
**Country shares:** US = 114,000.000000 → 0.787402; DE = 30,780.000000 → 0.212598.
**HHI (issuer, fraction):** 0.414422² + 0.372980² + 0.212598² = **0.356057**.
**Effective number of issuers:** 1/0.356057 = **2.809**.

**The DEMO-CONCENTRATION book (OQ-CON-1-21), reference values.** The fixture values are chosen
deliberately trivial so the hand-derivation is at-sight — the lesson of this section's own history
(below) is that clever fixture arithmetic is a defect generator:

| Instrument | Coverage class | Exposure (long, USD) |
|---|---|---|
| CN-ALPHA | classified (issuer ALPHA-CORP; sector C26→C; country US) | 60,000.000000 |
| CN-BETA | UNCLASSIFIED (issuer BETA-LLC, no assignments) | 30,000.000000 |
| CN-CASH | UNCLASSIFIABLE (`issuer_id` NULL by design) | 10,000.000000 |

Denominator Σ long = **100,000.000000**. Issuer dimension: ALPHA-CORP **0.600000**, UNCLASSIFIED
**0.300000**, UNCLASSIFIABLE **0.100000** (sum 1.000000). `coverage_ratio` = **0.600000**;
classifiable coverage = 0.6 ÷ (0.6 + 0.3) = **0.666667** — above a demo floor set at 0.5, so the
run COMPLETES with visible residuals. `HHI_ISSUER` (classified only) = 0.6² = **0.360000**;
`MAX_SHARE_ISSUER` = `CR_5_ISSUER` = **0.600000**. Sector and country dimensions mirror the same
triple (C / US at 0.600000, both residuals identical) since the single classified instrument
carries one node per dimension.

> **Why these are stated to six decimals and were re-derived by execution.** The first draft of this
> section carried **0.348834** for the HHI (and 2.867 for the effective number) — arithmetic I did in
> prose and got wrong; the sector shares were also off by 3e-6 from carrying rounded intermediates.
> Re-deriving them with `Decimal` at the platform's own quantum caught both. That is the standing
> rule working as intended: a reference value computed the same way as the implementation, or
> computed carelessly, proves nothing. **The implementation must reproduce the tables above, and the
> test must carry these literals rather than recomputing them from the fixtures** — otherwise the
> expected value and the code share a single point of failure.

## Part 3 — Implementation shape

**ENT-069 `concentration_result`, migration `0057`** — IA append-only (ORM guard + P0001 trigger).
NOT NULL: `calculation_run_id`, `input_snapshot_id`, `model_version_id`, `portfolio_id`,
`row_kind` (`DETAIL`|`SUMMARY`, total-enumeration CHECK), `dimension_kind`, `metric_type`,
`bucket_code` (TEXT — node code / issuer-id string / `UNCLASSIFIED` / `UNCLASSIFIABLE` /
`SUMMARY`), `denominator_basis` (controlled vocabulary; sole v1 value `INVESTED_LONG`), `basis`
echo for classification dimensions (OQ-CON-1-26; sentinel `NOT_APPLICABLE` elsewhere). Nullable,
NON-KEY, CHECK-gated: `issuer_id` (FK, DETAIL+ISSUER real buckets only), `scheme_id` (echo,
classification DETAIL rows only — no FK, the RLS-bypass refusal of OQ-CON-1-14). Values:
`gross_amount`, `long_amount`, `short_amount`, `net_amount`, `share_invested_long`,
`metric_value`, `coverage_ratio`, `coverage_classifiable`.

**Grain constraints — the OQ-CON-1-23 redesign, restated here as DDL so the migration is written
from this paragraph.** Every KEY column is NOT NULL (the NULL-vacuity class is structurally gone —
the second pass proved v3's nullable-`issuer_id`-in-UNIQUE grain constrained NOTHING for the two
dimensions REF-1 actually shipped). Two **PARTIAL unique indexes, predicates stated**:
`uq_concentration_summary` = `UNIQUE(calculation_run_id, metric_type) WHERE row_kind = 'SUMMARY'`;
`uq_concentration_detail` = `UNIQUE(calculation_run_id, dimension_kind, bucket_code) WHERE
row_kind = 'DETAIL'`. Row-kind-qualified CHECKs per OQ-CON-1-23 (summary ⇒ no bucket identity, no
issuer_id, no scheme_id; detail ISSUER real buckets ⇒ issuer_id NOT NULL; classification detail ⇒
scheme_id NOT NULL). Partial-index semantics are PG-only, so the **PG tier carries the
duplicate-refusal negative controls for BOTH row kinds including a duplicate `UNCLASSIFIED` row**
— SQLite is structurally blind here, and `bucket_code == str(issuer_id)` is a service invariant
with its own PG-tier test.

**`metric_type` vocabulary:** the exact ten-name census of OQ-CON-1-13, longest measured 25 ≤ the
shipped `String(30)`, with the set-equality census test and its P6 floor.

**New `concentration/` package** — the binder (explicit upstream-run selection, the pre-build
refusals: mixed-scheme-version, mixed-basis, zero-denominator, sub-floor classifiable coverage),
a DB-free kernel (shares, CR-N, HHI over pinned rows), and the bootstrap registrar with the
declared parameters (`declared_concentration_parameters()`, exact-identity refusal).

**Snapshot legs** — a new PURPOSE, binding predicate, and FOUR pinned shapes: the exposure atoms,
the narrow instrument→issuer edge, the classification assignments (incl. `basis`) + ancestor
closure (hash over `code`/`parent_node_id`/`level`, excluding `name`/`description`), and the
referenced `classification_scheme` rows (`id`, `scheme_family`, `version_label` — OQ-CON-1-24's
discriminator inputs). Each with its serializer, explicit-tenant resolver, `_reresolve_content`
branch, and verify except-tuple entry.

**Reads** — `calc/reads.py` typed wrappers + list/latest/entity-time endpoints (rule 7), with
PG-tier pins for every non-String filter; the issuer-identity-bearing endpoints demand
`concentration.issuer.view` (OQ-CON-1-25) with a route-level assertion.

**Migration `0057` DOWNGRADE, specified (the second pass: "never specified" + the SCH-2 zero-rows
lesson):** drop the partial indexes, the RLS policy, then the table (the P0001 trigger rides the
table drop); children before parents; NO demo-permission deletions ride 0057 (the R-07 rows land
via bootstrap, not this migration). The P4 dry run stages rows FIRST and proves the drop
destructive — a smoke deleting zero rows tests nothing — and every dry-run number is a dated
reading re-measured at closeout.

**Gates** — `make check`; fresh-schema full-PG; `alembic check`; the P4 executed dry run of `0057`
up and down (destructive-proven); the new CI PG steps; `make gen-api`; the closure stamp verified
by executing `check_docs._status_lines`. **P6 floors shipped WITH their guards:** the
`metric_type` census, the `dimension_kind` per-kind CHECK census, the `row_kind` census, the NEW
`_METRIC_MAP` exact census, the `SNAPSHOT_COMPONENT_KINDS` set-equality upgrade.

**The P1 SEVEN-ledger closeout obligations, named now so the closeout cannot omit them (the second
pass found the record silent on four of six):** (1) ENT-069 registry row + next-free-id → ENT-070;
(2) audit-event taxonomy — the R-07 mint's three permission codes recorded (or the
"deliberately minted nothing" sentence updated — CON-1 mints permissions, not audit codes: say
exactly that); (3) control matrix — REQ-CRD-003 maps to CTRL-002/018: extend their evidence or
state "no control moved" explicitly; (4) `current_state.md` CURRENT TRUTH block; (5) requirements
backbone + BOTH RTM halves — REQ-CRD-003 advances from Draft with the concentration half realized
and the open clauses named; (6) counts MEASURED on a fresh battery against the declared
26/41/136; (7) every delivery claim in this record cited to its merged artifact at close (the
2026-07-30 seventh ledger).

## Part 4 — Sizing

**M/L.** One entity + migration, a new package with a kernel, FOUR snapshot pinned shapes (the
largest single cost — Part 0 fact 7, plus the scheme rows of OQ-CON-1-24), a registered model with
declared parameters and a validation record, `_METRIC_MAP` registration + its first census, rule-7
reads behind the three-code mint, the DEMO-CONCENTRATION book (three instruments, two issuers, an
exposure run + a concentration run) alongside DEMO-GLOBAL's run, the two REF-1 hardenings paid
in-slice (OQ-CON-1-27 capture-consistency guard, OQ-CON-1-28 fail-closed ancestor walk — both
small, both negative-controlled), and the count relay at 26/41/136.
**Split candidate if it runs long:** the country dimension (the machinery is identical to sector,
so it is additive data rather than new code) — but NOT the coverage gate, the basis discipline, or
either REF-1 hardening, which are correctness rails.

## Part 5 — Cited external research (rule 6a), RESTATED under the 2026-07-30 verbatim-quote rule

Sources dated 2026-07-29; **restated 2026-07-30 after the second pass found the RESTATEMENT itself
misattributed its two load-bearing citations** (¶87 quoted with its operative qualifier dropped;
two CESR box numbers wrong) — in the section whose stated purpose was citing each source for what
it actually establishes. Per the amended rule 6a, every citation below is a VERBATIM quote with a
locator, and the pre-ratification pass includes a citation lane that reads ONLY the sources and
answers "does it say what the record claims?". Nothing below enters the methodology on my reading
alone.

- **Regulation (EU) 231/2013, Art. 7** — the gross method computes "*the sum of the absolute
  values of all positions*" — this is the AIFMD leverage **NUMERATOR**; Art. 6(1) defines leverage
  as "*the ratio between the exposure of an AIF and its net asset value*". Art. 7 further excludes
  cash and cash equivalents in the base currency and requires derivative conversion per Art. 10 —
  none of which this platform performs, so the platform's gross is not Art. 7 gross either.
- **CESR/10-788, Box 2** — the absolute value is applied **after** netting and hedging arrangements
  are taken into account (the guideline is netting-permissive). **Box 3** *excludes* from the
  commitment calculation a derivative that "*totally offsets the market risk of the swapped
  assets*" (v3 wrote "mandates offsetting" — inverted). The 100%-of-NAV global-exposure bound is
  **Box 9 point 3**, not Box 8 (Box 8 is hedging criteria): "*global exposure … not greater than
  100% of NAV*" (verbatim confirmation is the citation lane's to make).
- **ESMA/2013/1339, ¶84/91/93** — no netting between instruments of the same sub-asset type,
  reported by long and short: the **NUMERATOR** discipline the long/short decomposition satisfies.
  **¶87 gives the denominator WITH ITS QUALIFIER, which v3 dropped:** "*its percentage in terms of
  total value of assets **under management of the AIF***" — AuM as calculated under Articles 2 and
  10 of the Regulation, a DEFINED regulatory quantity (including derivative conversion), NOT a naive
  balance-sheet total and NOT anything computable on this schema. This strengthens, not weakens,
  OQ-CON-1-1's conclusion that no cited regime's denominator is computable here.
- **Limit regimes and their denominators** — UCITS Directive 2009/65/EC Art. 52 (5/10/40 with the
  20%/35% variants) against NAV. **US IRC §851(b)(3), stated structurally (v3's flat "5%/25%" was
  wrong):** the 5% test — "*not greater than 5 percent of the value of the total assets*" — is a
  condition **inside the 50%-of-total-assets basket of §851(b)(3)(A)(ii)** and applies to "*other
  securities*" only; Government securities, securities of other RICs and "*cash and cash items
  (including receivables)*" (§851(b)(3)(A)(i)) sit outside it; the 25% leg is §851(b)(3)(B).
  Solvency II market-concentration SCR (CT_i × Assets); BCBS large exposures (25% of Tier 1).
  **None uses an invested-long or gross denominator** — which is precisely why OQ-CON-1-1 records
  that CON-1's share is not any of these ratios and LIM-2 refuses regulatory-shaped thresholds.
- **Measures** — HHI as the sum of squared shares (DOJ/OECD merger-guidelines convention 0–10,000,
  deliberately not adopted per OQ-CON-1-3); CR-N as the top-N concentration ratio; effective number
  of holdings as 1/HHI.

## Part 6 — Corrections this slice's recon forced on prior RATIFIED records

Folded separately as `3b74a52`, recorded here because CON-1 stands on them. **Delivery evidence
(the seventh ledger, verified 2026-07-30): `3b74a52` and `dfe0591` are on `main` via PR #150
(merge `d598ba4`); `git merge-base --is-ancestor 3b74a52 origin/main` passes** — the second pass
flagged this section for asserting delivery while the branch was unmerged; the merge has since
made the claims true, and this line cites the evidence rather than the intent.

1. **OQ-REF-1-23's write-freeze was ratified and never implemented** — `issuer.sector` remained
   writable while REF-1's record described the freeze as done. Two live sector representations,
   entering the slice that computes sector buckets. Delivered at `3b74a52`, on `main` per the
   evidence line above.
2. **The `snapshotVerified` user-visibility claim was false** — no production view passes the prop.
   REF-1's FR decision stands on the drift mechanics; the user-visibility clause is withdrawn.
3. **REF-1's node fence is vacuous as shipped** — there is no `update_node`/`update_scheme` for it
   to constrain. Now labelled as intent-pending-a-writer.
4. **REF-1's "EV-flavored, drift-prone" pin framing was imprecise and its binary was wrong**
   (Part 0 facts 5–6, OQ-CON-1-6/7).
5. **OQ-REF-1-25's pin content was under-specified** — it omits the ancestor chain and would
   false-drift on an unrelated node add (OQ-CON-1-9).
6. **"A new COMPONENT_KIND" (singular) understates the mint** (Part 0 fact 7).
7. **The demo-backfill claim was overstated** — only DEMO-GLOBAL's three instruments; two other
   books in the same tenant run exposure over unclassified instruments (Part 0 fact 10).
8. **A FOURTH false claim, found while drafting this record rather than by the recon.** OQ-REF-1-19
   states that REF-1's rail "computes its own expected-set diff and calls `run_presence_gate`
   explicitly, becoming the **first capture-path caller**". Executed grep: `classification/service.py`
   never calls `run_presence_gate` or `ensure_presence_rule` at all — it runs a required-fields
   NOT_NULL gate through `run_quality_check` and computes no expected-set diff. Forward-looking prose
   in a record reading as delivery, for the fourth time in one slice. **CORRECTED (second-pass
   self-accuracy fix): the correction was ALREADY in `ref_1_decision_record.md` via `dfe0591` — the
   commit that wrote this record — so v3's "to be corrected alongside the other three" was itself a
   stale claim about its own commit; now on `main` per the evidence line above.**
9. **REF-1's carry #3 was only HALF discharged by v1 of this record.** REF-1 specified the node pin as
   the node-set hash **excluding `name`/`description`**; v1 replaced the set hash with the ancestor
   closure (correctly, OQ-CON-1-9) but dropped the field exclusion without mentioning it. The
   exclusion is restored: the ancestor-closure hash covers `code`/`parent_node_id`/`level` and
   excludes `name`/`description`, so a cosmetic rename cannot redden a historical run.
10. **A FIFTH ratified-but-undelivered REF-1 item, found by the second pass — and CON-1's sector
    bucket rests on it.** OQ-REF-1-1's fail-closed sector-vs-industry ancestor-consistency refusal
    was ratified and never built (`capture_assignment` has no such check; the contradiction is a
    reachable stored state under the OQ-REF-1-8 key). **Disposition: PAID IN THIS SLICE as
    OQ-CON-1-27**, not re-deferred.
11. **SIXTH: OQ-REF-1-29's demo-stage role census, read-access demonstration and mandatory
    `role_permission` teardown are all unbuilt** — `ref1_stage18.py` contains no Role/Permission
    code at all. **Disposition: paid in CON-1's demo stage**, which extends the same campaign and
    must add its own three-code grants anyway; the stage adds the census + teardown for both
    slices' rows, negative-controlled by the downgrade smoke.
12. **SEVENTH: OQ-REF-1-15's "idempotent, context-guarded seeder" was never built** —
    `seed_system_reference` remains non-idempotent by its own docstring. **Disposition: recorded as
    REF-1 debt with the trigger** "the first second consumer of the SYSTEM seed outside the demo
    campaign" — CON-1's stage consumes the seed through the existing already-seeded guard and does
    not need the rewrite; building it now would be P5 vacuity (its only exercise its own test).

## Part 6b — Amendments this slice forces on the RATIFIED wave plan and roadmap

Recorded per the SCH-2 record-reversals-at-the-gate rule. v1 narrowed ratified deliverables silently
— the exact defect REF-1 named and folded one slice earlier — and had no section to record them in.
**These are briefed at the gate as decisions, not presented as inherited.**

1. **`FAMILY_REGISTRY` entry + the `ck_schedule_model_version_by_family` CHECK amendment are DROPPED**
   because OQ-CON-1-17 defers schedulability. The roadmap row ratified both. `FAMILY_REGISTRY` *is*
   the schedulability registry, so deferring one drops the other. Trigger: the first operator ask for
   an unattended concentration cadence.
2. **"Rule-7 reads + FE in-slice" is narrowed to backend-only.** REF-1 established that **rule 7 has
   no FE clause** — but the FE obligation here comes from the **roadmap row**, not from rule 7, so it
   **cannot be inherited away** by citing REF-1. Dropping it is a reversal of a ratified deliverable
   and needs the user's approval; if approved, the slice that owns the concentration view must be
   named.
3. **CR-N and HHI become GOVERNED stored values rather than read-surface derivations** — that is
   the genuine content here, and it is what makes the metric table hard to re-open later. *(The
   second pass refuted v3's framing of this as a widening OF THE ROADMAP: the roadmap explicitly
   names top-N and HHI-class and defers the exact set to this gate, so there is no roadmap
   amendment to record — only this design consequence, stated plainly.)*
4. **"Immediate-issuer grain; ultimate-parent rollup stays deferred"** is honoured unchanged, and
   the TRIGGER the wave plan requires is now RECORDED (the second pass found it missing): the
   ultimate-parent rollup activates on "the first consumer needing group-level concentration — a
   group-exposure limit ask, or REQ-SMR-002's parent-traversal slice, whichever lands first."
5. **REVERSAL, previously unrecorded (the second pass):** both the roadmap row and the wave plan
   ratify "derived-of-derived over the **latest COMPLETED exposure run**". Part 0 fact 10 refutes
   "latest" as a safe selection anywhere a dispatched run can interleave (the demo's latest is a
   99.98%-one-issuer book), and OQ-CON-1-20 reverses it for the demo: **the binder takes an
   EXPLICIT exposure-run selection; "latest COMPLETED" survives only as the API convenience
   default, never the demo's or any pinned test's selection.** A change to a ratified
   specification, recorded here for the gate.

**On ratification, `wave_14_planning.md`, roadmap Part 2.18 and `current_state.md` are amended in
place** (the REF-1 closing clause, which the second pass found missing here — without it the
ratified registers stay false on completion).

## Part 7 — Pre-ratification verifier pass (findings ledger)

*(Filled before the gate; refute-by-default, fresh-context lanes.)*
