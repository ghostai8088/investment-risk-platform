# CON-1 Decision Record — concentration, the 23rd governed number (Wave-14 slice 1)

| Field | Value |
|---|---|
| Status | **RATIFIED 2026-07-30 (v6) — OQ-CON-1-1…28 ALL approved as recommended at the user gate ("proceed", no exceptions), including the OQ-CON-1-15 reversal and decision point 8 (the minimal FE read KEPT in-slice). The Part 6b in-place amendments to `wave_14_planning.md`, roadmap Part 2.18 and `current_state.md` are EXECUTED. Implementation next.** Four verifier passes (Part 7): the descoped form survived the full 4-lane pass (registers CLEAN 12/12; the citation lane's first execution CLEAN at the core; the OQ-CON-1-15 reversal resolved its BLOCKING structurally), and the v5 targeted pass then caught the record's own mis-measured holder sets (`ops` for `data_steward`) plus four narrow contradictions — all folded here at v6, every holder set recomputed from source. History: v1 broke 46 findings deep (5 BLOCKING, the methodology foundation refuted); the 2026-07-29 dual-share repair was itself REFUTED (47 findings, 8 BLOCKING), triggering the user-ratified stopping rule → the `share_invested_long` descope with the `denominator_basis` vocabulary (OQ-CON-1-1) |
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
  - **The LONG predicate, pinned (the v4 pass: "the word the whole descope hangs on is never given
    a predicate", and no long/short decomposition exists anywhere in shared-python):**
    `exposure_aggregate` stores ONE SIGNED `exposure_amount` per atom — so CON-1's kernel COMPUTES
    the decomposition itself: **long = atoms with `exposure_amount > 0`; short = atoms with
    `exposure_amount < 0`; zero atoms contribute nothing.** `Σ long ≥ 0` by construction, making
    the zero-denominator refusal complete. The gross/long/short/net evidence columns on ENT-069 are
    kernel-computed from the signed atoms, not read from upstream. Recorded consequence: a
    negative captured mark (storable — no sign guard exists on capture) makes an economically-long
    position read as short by value sign; the assumptions state the decomposition is BY VALUE SIGN,
    not by position direction.
  - **The denominator's SCOPE, ratified (the second-pass subtree finding, previously unfolded):**
    an exposure run's rows span the portfolio SUBTREE of its `scope_portfolio_id` (each row carries
    the CHILD's portfolio id). **The run's subtree IS the book**: ENT-069's `portfolio_id` = the
    run's `scope_portfolio_id`, the denominator = Σ long over ALL rows of the run, and the model
    assumptions state "concentration is measured over the exposure run's aggregation scope — the
    subtree rooted at `scope_portfolio_id`". A fund-level (single-book) number is obtained by
    running exposure at that portfolio; no per-child decomposition ships in v1 (trigger: the first
    consumer needing child-level concentration inside one run). **The pin is not total (v6):**
    `scope_portfolio_id` is NULLABLE and genuinely NULL for snapshot-consume-path exposure runs
    (the OD-API-1b-D honest NULL) — a NULL-scope upstream run is **REFUSED PRE-BUILD** (computable
    from the run head), never guessed at.
  - Every share row carries **`denominator_basis`**, a controlled-vocabulary column with the single v1
    value `INVESTED_LONG` — so a future NAV or total-assets denominator is an ADDITIVE vocabulary value
    on new rows, never a reinterpretation of shipped ones.
  - The registered model assumptions state, in these words: **this share is NOT the UCITS Art. 52,
    IRC §851(b)(3), Solvency II or BCBS ratio; no denominator those regimes require is computable on
    this schema.** The limitation stays first-class, exactly as the paragraph above records it.
  - **The LIM-2 named acceptance constraint (replaces the refuted flag-binding; NARROWED and made
    implementable by the v4 pass, which found the definition-time refusal had no predicate and no
    in-slice enforcement point):** LIM-2 adds a **basis declaration column on `limit_definition`**
    (mandatory LIM-2 scope, named here as the acceptance constraint) and a limit may bind ONLY to a
    `denominator_basis` its declared basis matches — regulatory-shaped thresholds are REFUSED
    fail-closed at limit definition BY THAT MACHINERY, which does not exist until LIM-2. **The
    in-slice closure is therefore structural, not textual: `_METRIC_MAP` registration is DEFERRED
    to LIM-2 (the OQ-CON-1-15 reversal)** — with no registered metric, the shipped
    `_validate_config` membership check refuses ANY limit on the concentration family today, so no
    window exists in which a threshold binds this share without a basis discipline. What the
    definition-time design closes is the REGULATORY-limit hazard; two consequences are recorded
    rather than claimed away: (a) when a previously-long book goes zero-long, new runs refuse and
    `_resolve_latest` keeps resolving the LAST COMPLETED run — an internal-appetite limit evaluates
    a stale pre-refusal book with no staleness signal; LIM-2 routes a refusal-after-success into
    `limit_health` as a distinct staleness state (named LIM-2 scope), and until then this is a
    recorded limitation; (b) the NEVER_EVALUABLE hazard is closed for the regulatory path only —
    that is the narrowed claim. **Trigger for the real ratio:** a cash/liability/NAV entity — the
    first consumer needing a NAV-denominated share (unchanged).
  - **The long-only identity, stated so the tests can use it honestly:** on an all-long book
    `gross == long` for every bucket, so `share_invested_long` coincides with the withdrawn gross
    share there — which means the DEMO (long-only) cannot distinguish the two denominators. The
    distinguishing case is therefore pinned in the unit + PG tiers on a short-bearing book: the
    denominator must EXCLUDE the short leg (`Σ long`, not `Σ long + |short|`) and the numerator must
    exclude the bucket's own shorts. A suite without that book would leave the descope untested.
  **Refusal timings, stated once and used consistently (the v4 pass found OQ-1 and Part 3
  contradicting each other):** refusals computable from CURRENT HEADS — mixed scheme version
  (OQ-CON-1-10), co-existing same-family schemes (OQ-CON-1-24), mixed basis (OQ-CON-1-26) — are
  **PRE-BUILD**: no run row is created. Refusals needing the PINNED ATOMS — the zero
  invested-long total, the classifiable-coverage floor, the all-UNCLASSIFIABLE (0/0) book — are
  **POST-BUILD `gaps` entries**: the run commits as FAILED (Part 0 fact 2's orphan discipline),
  never divided by. Gross/long/short/net evidence columns are unchanged by the descope.
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
  fault — a floor over raw coverage would refuse a correct book. TWO residual buckets:
  **`UNCLASSIFIABLE`** and **`UNCLASSIFIED`**, both IN the share denominator and OUT of the
  rankings and HHI. **The predicates are PER-DIMENSION (the v4 pass found the global issuer-NULL
  proxy double-assigns a reachable row — `capture_assignment` never requires an issuer, so an
  issuerless instrument WITH a sector assignment exists):** for the ISSUER dimension,
  `issuer_id IS NULL` ⇒ UNCLASSIFIABLE; for the classification dimensions, **an existing
  assignment ALWAYS classifies regardless of issuer** — UNCLASSIFIABLE there means "no assignment
  AND no issuer edge to inherit one through", and an issuerless-but-assigned instrument buckets by
  its assignment. The declared coverage floor gates **classifiable coverage** =
  `classified ÷ (classified + UNCLASSIFIED)` — the omission rate among instruments that COULD be
  classified — while raw `coverage_ratio` (classified ÷ total) is stored alongside so the read
  surface shows both facts. **The 0/0 edge (v4 pass): an all-UNCLASSIFIABLE book (classified =
  UNCLASSIFIED = 0, Σ long > 0) REFUSES as a `gaps` entry** — a book with nothing classifiable has
  no concentration to govern, and summary metrics over an empty classified set (MAX of nothing,
  HHI of no terms) have no defined value; negative-controlled on an all-cash fixture.
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
- **OQ-CON-1-15 — `_METRIC_MAP` registration: REVERSED at v5 — DEFERRED TO LIM-2 (a Tier-3
  reversal of this record's own v4 position, forced by the descoped-form pass's BLOCKING).** The
  v4 position (register in-slice, so REQ-CRD-003's "limits-ready metrics produced" advances)
  opened a one-slice window: the shipped `create_limit`/`_validate_config` checks only
  `_METRIC_MAP` membership and unit — no basis machinery exists until LIM-2 — so an in-slice
  registration would let a UCITS-shaped threshold bind to `share_invested_long` with zero refusal:
  **the v2 false-breach harm, relocated a third time.** The structural fix: CON-1 produces the
  metrics in exactly the shape LIM-2's selector needs (the ten-name census, the summary grain,
  `result_attr = metric_value`, `SHARE` explicitly EXCLUDED from any future registration) but
  registers NOTHING — the shipped membership check therefore refuses every concentration limit
  today, fail-closed by existing code. LIM-2 registers the metrics IN THE SAME SLICE as the
  `limit_definition` basis column and the basis-match refusal. **The honest REQ consequence,
  recorded:** REQ-CRD-003's concentration half advances at CON-1's close to "metrics produced,
  limits-ready in shape; BINDABLE at LIM-2" — the RTM row says exactly that, not "Done".
  **The resolver fold stands from v4:** when LIM-2 adds the family, the dispatch's `if/else`
  becomes `elif` per family plus a fail-closed `else` raise. **Census obligations stand:**
  `_METRIC_MAP` gains its FIRST exact set-equality census (at LIM-2's registration);
  `SNAPSHOT_COMPONENT_KINDS` upgrades to set-equality HERE; the reflective
  `SNAPSHOT_PURPOSES`/`_BINDING_PREDICATES` censuses are self-deriving and need no edit.
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
    **`__UNCLASSIFIED__` / `__UNCLASSIFIABLE__`** for the residuals and **`__SUMMARY__`** for
    summary rows — dunder-delimited BECAUSE the column shares its namespace with taxonomy node
    codes (the v4 pass: a vendor scheme could legally carry a node literally coded `UNCLASSIFIED`),
    with a capture-side guard in `create_node` refusing any node code matching `__*__` (small,
    negative-controlled — the collision is closed at both ends). Every key column NOT NULL — the
    NULL-vacuity class is structurally gone.
  - **`issuer_id`** stays a nullable GUID FK convenience column OUTSIDE every unique key
    (intra-tenant; FK legal here — `issuer` is same-tenant proprietary, so no RLS-bypass concern),
    with row-kind-qualified CHECKs: `row_kind='DETAIL' AND dimension_kind='ISSUER' AND bucket_code
    NOT IN (sentinels)` ⇒ `issuer_id IS NOT NULL`; `row_kind='SUMMARY'` ⇒ `issuer_id IS NULL`.
    `bucket_code == str(issuer_id)` is a service invariant with a PG-tier test (a cross-column cast
    CHECK is not portable to the SQLite tier).
  - **`scheme_id`** becomes a nullable ECHOED column outside the keys — NOT NULL via CHECK for
    classification DETAIL rows **AND for classification-dimension SUMMARY rows** (the v4 pass found
    v4's summary-⇒-no-scheme CHECK contradicted OQ-CON-1-24(ii): the limit-selectable
    classification numbers ARE summary rows, and "the number records which taxonomy produced it"
    must hold for them; the CHECK is a total enumeration over the ten metric names — issuer trio ⇒
    scheme_id NULL, classification six ⇒ NOT NULL, `SHARE` per its dimension). NULL for
    ISSUER-dimension rows; within one run OQ-CON-1-24 admits ONE live scheme per dimension, so
    `(dimension_kind, bucket_code)` is unique without scheme qualification and no GUID sentinel is
    needed (v3's "scheme_id-or-sentinel" in a uuid column had no declared literal, no FK story,
    and PG/SQLite divergence).
  - The two grain constraints become **PARTIAL unique indexes with their predicates STATED**:
    summary `UNIQUE(calculation_run_id, metric_type) WHERE row_kind = 'SUMMARY'`; detail
    `UNIQUE(calculation_run_id, dimension_kind, bucket_code) WHERE row_kind = 'DETAIL'` —
    **declared with BOTH `postgresql_where` AND `sqlite_where`** (the v4 pass REFUTED v4's
    "SQLite is structurally blind" claim: the repo's own dominant convention declares partial
    indexes for both dialects — REF-1's current-head index, `position`, `limit` and ~8 marketdata
    indexes all do — and the unit tier builds schema via `create_all`, so both tiers enforce).
    The duplicate-refusal negative controls for BOTH row kinds including a duplicate
    `__UNCLASSIFIED__` row run in BOTH tiers, with PG the authoritative gate.
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
  **The holder sets, ENUMERATED HERE so the gate ratifies them and the pins are written FROM this
  record (the v4 pass: deferring enumeration to a not-yet-written plan is the same silence one
  document over). Measured from `ROLE_TEMPLATES` — SIX roles; `platform_admin` holds ALL_CODES by
  construction. *(v6 correction: v5 enumerated these sets with `ops` where the bootstrap has
  `data_steward` and claimed seven roles — a faulty extraction presented as "measured exactly";
  the targeted pass recomputed every set from the source. `ops` holds ONLY `ops.audit.verify`.)*:**
  - `concentration.run` = **{platform_admin, data_steward, risk_analyst_1l}** — the recomputed
    `risk.run`/`pacing.run` precedent exactly.
  - `concentration.view` = **{platform_admin, data_steward, risk_analyst_1l, risk_manager_2l,
    auditor_3l}** — the recomputed `risk.view`/`pacing.view` governed-output precedent exactly.
  - `concentration.issuer.view` = **{platform_admin, data_steward, risk_analyst_1l,
    risk_manager_2l}** — the recomputed `reference.issuer.view` precedent exactly (auditor_3l
    excluded).
  Each pinned `_holders(code) == {...}` in both directions, and a route-level test asserts the
  issuer-bearing endpoints demand the `.issuer.view` code (the pin alone cannot catch a mis-scoped
  route — REF-1's own finding).
  *(Tier-3: the split, the sets above, and the auditor's exclusion from issuer-identity reads are
  the gate's call.)*

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
  DEMO-CONCENTRATION's concentration run. DEMO-MULTIASSET's refusal is the **all-UNCLASSIFIABLE
  0/0 gap** (the v6 targeted pass measured the fixture: its instruments carry NO issuer and NO
  assignments, so classified = UNCLASSIFIED = 0 in every dimension — the OQ-CON-1-4 0/0 refusal,
  not the coverage floor v5 named) — amount-weighted, so **POST-BUILD** per OQ-CON-1-1's timing
  rule: the stage asserts the run row EXISTS, is **FAILED** with the named 0/0 gap, and that the
  COMPLETED count is unmoved by it. **The declared triple: 25/40/133 →
  26/41/136** (COMPLETED runs only; the FAILED refusal run is additionally pinned by status). Per P4's binding clause this is a dated planning-time reading, RE-MEASURED against
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

Denominator Σ long = **100,000.000000**. Coverage is **PER-DIMENSION** (each dimension's summary
rows carry that dimension's pair), and the v6 targeted pass caught the v5 literals contradicting
the per-dimension predicates — CN-BETA carries an issuer, so in the ISSUER dimension it is
CLASSIFIED, not residual. Re-derived under the ratified predicates:
- **ISSUER dimension:** ALPHA-CORP **0.600000**, BETA-LLC **0.300000**, UNCLASSIFIABLE (CN-CASH)
  **0.100000** — an UNCLASSIFIED bucket cannot exist here by construction. `coverage_ratio` =
  **0.900000**; classifiable coverage = 0.9 ÷ (0.9 + 0) = **1.000000**. `HHI_ISSUER` = 0.36 + 0.09
  = **0.450000**; `MAX_SHARE_ISSUER` = **0.600000**; `CR_5_ISSUER` = **0.900000**.
- **SECTOR_INDUSTRY and COUNTRY_OF_RISK dimensions** (where the residual demonstration lives):
  classified C / US **0.600000** (CN-ALPHA); UNCLASSIFIED **0.300000** (CN-BETA — issuer present,
  no assignment); UNCLASSIFIABLE **0.100000** (CN-CASH — no assignment and no issuer edge).
  `coverage_ratio` = **0.600000**; classifiable coverage = 0.6 ÷ (0.6 + 0.3) = **0.666667** —
  above the demo floor of 0.5, so the run COMPLETES with visible residuals. `HHI` = **0.360000**;
  `MAX_SHARE` = `CR_5` = **0.600000** per dimension.

**The SHORT-BEARING distinguishing fixture (unit + PG tiers, not the demo), reference values —
the v4 pass found the ONLY test that distinguishes the descoped denominator had no independently
derived literals anywhere.** Four signed atoms across two issuers:

| Atom | Issuer | Signed exposure |
|---|---|---|
| SB-A | X-CORP | +80,000.000000 |
| SB-B long | X-CORP | +20,000.000000 |
| SB-B short | X-CORP | −25,000.000000 |
| SB-D | Y-CORP | −15,000.000000 |

By the pinned LONG predicate (`exposure_amount > 0`): **Σ long = 100,000.000000**. Issuer shares:
X-CORP = 100,000 ÷ 100,000 = **1.000000** (its −25,000 short is `short_amount` evidence, not
numerator); Y-CORP has no long atom, so `share_invested_long` = **0.000000** with `short_amount`
−15,000.000000 as evidence. The withdrawn gross share would have read X-CORP as 125,000 ÷
140,000 = **0.892857** — the distinguishing literal pair **1.000000 ≠ 0.892857** fails any kernel
that uses gross in either numerator or denominator. Run-level evidence totals: gross =
140,000.000000; long = 100,000.000000; short = −40,000.000000; net = 60,000.000000.

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
`bucket_code` (TEXT — node code / issuer-id string / `__UNCLASSIFIED__` / `__UNCLASSIFIABLE__` /
`__SUMMARY__`, the dunder sentinels of OQ-CON-1-23 with the `create_node` collision guard),
`denominator_basis` (controlled vocabulary; sole v1 value `INVESTED_LONG`), `basis`
echo for classification dimensions (OQ-CON-1-26; sentinel `NOT_APPLICABLE` elsewhere). Nullable,
NON-KEY, CHECK-gated: `issuer_id` (FK, DETAIL+ISSUER real buckets only), `scheme_id` (echo — no
FK, the RLS-bypass refusal of OQ-CON-1-14 — NOT NULL for classification DETAIL rows **and
classification-dimension SUMMARY rows** via the ten-name total-enumeration CHECK, the
OQ-CON-1-24(ii) echo repair). Values:
`gross_amount`, `long_amount`, `short_amount`, `net_amount`, `share_invested_long`,
`metric_value`, `coverage_ratio`, `coverage_classifiable`.

**Grain constraints — the OQ-CON-1-23 redesign, restated here as DDL so the migration is written
from this paragraph.** Every KEY column is NOT NULL (the NULL-vacuity class is structurally gone —
the second pass proved v3's nullable-`issuer_id`-in-UNIQUE grain constrained NOTHING for the two
dimensions REF-1 actually shipped). Two **PARTIAL unique indexes, predicates stated**:
`uq_concentration_summary` = `UNIQUE(calculation_run_id, metric_type) WHERE row_kind = 'SUMMARY'`;
`uq_concentration_detail` = `UNIQUE(calculation_run_id, dimension_kind, bucket_code) WHERE
row_kind = 'DETAIL'` — **declared with BOTH `postgresql_where` and `sqlite_where`** (the shipped
convention: REF-1's current-head index, `position`, `limit`, ~8 marketdata indexes; the v4 pass
refuted the "SQLite is structurally blind" claim — `create_all` builds these in the unit tier
too). Row-kind-qualified CHECKs per OQ-CON-1-23, stated as a **name-AND-dimension enumeration
(v6 precision):** summary ⇒ `bucket_code = '__SUMMARY__'`, no issuer_id, **`metric_type` IN the
NINE summary names** (`SHARE` is refused on summary rows — v6 closed the junk-SHARE-summary hole),
with scheme_id NOT NULL for the classification six and NULL for the issuer trio; detail ⇒
`metric_type = 'SHARE'` with scheme_id decided BY `dimension_kind` (ISSUER ⇒ NULL, classification
kinds ⇒ NOT NULL) and ISSUER real buckets ⇒ issuer_id NOT NULL. The **duplicate-refusal negative
controls for BOTH row kinds including a duplicate `__UNCLASSIFIED__` row run in BOTH tiers with
PG authoritative**, and `bucket_code == str(issuer_id)` is a service invariant with its own
PG-tier test.

**`metric_type` vocabulary:** the exact ten-name census of OQ-CON-1-13, longest measured 25 ≤ the
shipped `String(30)`, with the set-equality census test and its P6 floor.

**New `concentration/` package** — the binder (explicit upstream-run selection; **PRE-BUILD
refusals** = mixed scheme version / co-existing same-family schemes (OQ-10/24), mixed basis
(OQ-26), and a **NULL-scope upstream run** (the v6 targeted pass: a snapshot-consume-path
exposure run carries `scope_portfolio_id = NULL` by the OD-API-1b-D honest-NULL rule, so the
ENT-069 `portfolio_id = scope_portfolio_id` identity is uncomputable — refused from the run head,
negative-controlled; the OQ-CON-1-1 scope pin carries the same clause); **POST-BUILD `gaps`
refusals** = zero invested-long, sub-floor classifiable coverage, the all-UNCLASSIFIABLE 0/0
book — the OQ-CON-1-1 timing rule, now used consistently at both ends), a DB-free kernel (shares,
CR-N, HHI over pinned rows), and the bootstrap registrar with the declared parameters
(`declared_concentration_parameters()`, exact-identity refusal).

**Snapshot legs** — ONE new PURPOSE + ONE binding predicate for the snapshot, and FOUR pinned
shapes (the mint accounting stated precisely — per-SHAPE: serializer, resolver,
`_reresolve_content` branch, verify except-tuple entry): the exposure atoms, the narrow
instrument→issuer edge, the classification assignments (incl. `basis`) + ancestor closure (hash
over `code`/`parent_node_id`/`level`, excluding `name`/`description`), and the referenced
`classification_scheme` rows (`id`, `scheme_family`, `version_label` — OQ-CON-1-24's discriminator
inputs). **Two resolver patterns, not one (the v4 pass: a plain explicit-tenant resolver finds NO
SYSTEM row):** the exposure-atom and issuer-edge shapes use the plain explicit-acting-tenant
predicate every shipped resolver uses; the two HYBRID vocabulary shapes (assignments' closure +
scheme rows) use the two-tenant `tenant_id IN (tenant, SYSTEM)` predicate with tenant-override
precedence — the `resolve_node` idiom. **And the closure branch re-resolves CODE-FIRST (the v4
pass: every one of the ~18 shipped `_reresolve_content` branches re-resolves by pinned surrogate
id, under which a leaf override is INVISIBLE and OQ-CON-1-9's mandatory negative control could
never fire):** re-run `resolve_node` on each pinned `(scheme_id, node_code)` with tenant
precedence, then re-walk `resolve_ancestors` — the platform's FIRST re-derive-flavored branch,
named as such so the review knows it deviates from the shipped idiom deliberately.

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
`metric_type` census, the `dimension_kind` per-kind CHECK census, the `row_kind` census, the
`SNAPSHOT_COMPONENT_KINDS` set-equality upgrade. *(The `_METRIC_MAP` exact census was listed
here in v5 and is STRUCK: it contradicts this record's own OQ-CON-1-15 reversal, which defers
`_METRIC_MAP` registration — and therefore its census — to LIM-2. The code correctly ships
neither. Corrected at the 2026-07-30 review fold, Part 8.)*

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
it actually establishes. Per the amended rule 6a, **every LOAD-BEARING citation below carries a
VERBATIM quote with a locator** (the citation lane's v4 run found the earlier blanket
"every citation" claim false for three regime cites that carried none — scoped honestly now), and
the citation lane reads ONLY the sources. **Citation-lane verdict on this section (first
execution, 2026-07-30): zero BLOCKING/HIGH — Art. 6(1)/Art. 7, CESR Boxes 2/3/8/9, ESMA
¶84/87/91/93 and the IRC §851(b)(3) STRUCTURE all verified verbatim-exact or correct; the
remaining fidelity nits are folded below.** Nothing here enters the methodology on my reading
alone.

- **Regulation (EU) 231/2013, Art. 7** — the gross method computes "*the sum of the absolute
  values of all positions*" — this is the AIFMD leverage **NUMERATOR**; Art. 6(1) defines leverage
  as "*the ratio between the exposure of an AIF and its net asset value*". Art. 7 further excludes
  cash and cash equivalents in the base currency and requires derivative conversion per Art. 10 —
  none of which this platform performs, so the platform's gross is not Art. 7 gross either.
- **CESR/10-788, Box 2 point 2(b)** — after netting and hedging arrangements are identified,
  "*The absolute value of the resulting calculation is equal to net commitment*" — the absolute
  value applies AFTER netting (the guideline is netting-permissive). **Box 3** *excludes* from the
  commitment calculation a derivative that "*totally offsets the market risk of the swapped assets
  held in the UCITS portfolio*" — Box 3 point 1: such a derivative "*is not taken into account*"
  (v3 wrote "mandates offsetting" — inverted). The 100%-of-NAV bound is **Box 9 point 3**, not
  Box 8 (Box 8 is titled "Hedging"): "*the total of these must not be greater than 100% of NAV*" —
  stated in the EPM context (derivatives + EPM-generated exposure combined).
- **ESMA/2013/1339, ¶84/91/93** — "*AIFMs should not net the positions between instruments that
  are part of the same sub-asset type*" (¶84; ¶91 the same at asset-type level; ¶93 long/short
  indicated): the **NUMERATOR** discipline the long/short decomposition satisfies.
  **¶87 gives the denominator WITH ITS QUALIFIER, which v3 dropped:** "*its percentage in terms of
  total value of assets **under management of the AIF***" (verbatim-exact per the citation lane) —
  AuM as calculated under Articles 2 and 10 of the Regulation (the tie stated at ¶51 and ¶103 of
  the same guidelines), a DEFINED regulatory quantity (including derivative conversion), NOT a
  naive balance-sheet total and NOT anything computable on this schema. This strengthens, not
  weakens, OQ-CON-1-1's conclusion that no cited regime's denominator is computable here.
- **Limit regimes and their denominators** — **UCITS Directive 2009/65/EC Art. 52: the operative
  denominator words are "its assets", verbatim** — "*no more than … 5 % of its assets in
  transferable securities or money market instruments issued by the same body*", with the 40%
  aggregate as "*40 % of the value of its assets*" (the citation lane: the directive never says
  NAV; the NAV reading is CESR/ESMA supervisory convention, cited here as convention, separately
  from the text). **US IRC §851(b)(3), stated structurally (v3's flat "5%/25%" was wrong):** the
  5% test — "*not greater in value than 5 percent of the value of the total assets of the
  taxpayer*" (verbatim; the v4 quote silently dropped "in value" and the lane caught it) — is a
  condition **inside the 50%-of-total-assets basket of §851(b)(3)(A)(ii)** and applies to "*other
  securities*" only; Government securities, securities of other RICs and "*cash and cash items
  (including receivables)*" (§851(b)(3)(A)(i)) sit outside it; the 25% leg is §851(b)(3)(B).
  Solvency II market-risk concentration sub-module and BCBS large exposures (25% of Tier 1) are
  cited as REGIME SHAPES ONLY — no verbatim quote is carried for them here, and pinning their
  exact articles (Delegated Regulation 2015/35; the Basel LEX standard) is a NAMED citation-lane
  obligation for the implementation-phase check, not satisfied by this record.
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
13. **REF-1's record and Part-9 sweep verdict SCOPED on this branch (the v4 pass: the sweep's
    "clean" read as covering ratifications it never checked).** `ref_1_decision_record.md`'s
    Status cell and Part 9 now carry the 2026-07-30 scope amendment naming the five undelivered
    ratifications and pointing at this Part's dispositions — the register surface no longer asserts
    the superseded truth.

## Part 6b — Amendments this slice forces on the RATIFIED wave plan and roadmap

Recorded per the SCH-2 record-reversals-at-the-gate rule. v1 narrowed ratified deliverables silently
— the exact defect REF-1 named and folded one slice earlier — and had no section to record them in.
**These are briefed at the gate as decisions, not presented as inherited.**

1. **`FAMILY_REGISTRY` entry + the `ck_schedule_model_version_by_family` CHECK amendment are DROPPED**
   because OQ-CON-1-17 defers schedulability. The roadmap row ratified both. `FAMILY_REGISTRY` *is*
   the schedulability registry, so deferring one drops the other. Trigger: the first operator ask for
   an unattended concentration cadence.
2. **"Rule-7 reads + FE in-slice" — DECIDED AT THE GATE (2026-07-30, decision point 8): the FE
   read is KEPT, minimal.** A concentration list/detail read on the existing runs surface (the
   FE-3 runs view pattern), summary metrics + the classification-dimension buckets; the
   issuer-identity detail rides only behind `concentration.issuer.view`. If the slice runs long,
   the SPLIT ORDER is fixed: the country dimension splits first (Part 4), the FE read second —
   never the coverage gate, the basis discipline, or the REF-1 hardenings. (The earlier
   narrowed-to-backend proposal is withdrawn; the roadmap row's FE clause stands satisfied by the
   minimal read.)
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

## Part 7 — Pre-ratification verifier passes (findings ledger)

**Three passes across three record versions; every finding dispositioned:**

1. **v1 pass (2026-07-29, 4 lanes): 46 findings, 5 BLOCKING** — including the refuted
   gross-denominator methodology (all three rule-6a citations misread). All folded into v2/v3;
   the folded denominator (dual-share) was itself the next pass's subject.
2. **v2/v3 pass (2026-07-29, 3 lanes): 47 findings, 8 BLOCKING** — the dual-share denominator
   REFUTED (`sum(long_amount)` ≠ total assets; false breaches into a non-withdrawable lifecycle);
   the jointly-unsatisfiable grain CHECKs; the NULL-vacuous detail UNIQUE; the single-code SoD
   re-commit; the misread ¶87 requalification. Triggered the user-ratified stopping rule → the
   v4 DESCOPE, all 47 folded (raw ledger retained at the session task dir, `wojjugwka`).
3. **v4 descoped-form pass (2026-07-30, 4 lanes incl. the FIRST citation-lane execution):
   1 BLOCKING, 3 HIGH, 14 MED, 8 LOW; the registers lane fully CLEAN (12/12 code-state claims
   true) and the citation lane's core CLEAN (¶87/IRC/CESR/ESMA verified verbatim or correct).**
   The BLOCKING (in-slice `_METRIC_MAP` registration would open a one-slice unbased-limit window)
   is resolved STRUCTURALLY by the OQ-CON-1-15 reversal (registration deferred to LIM-2). The
   HIGHs: the LONG predicate pinned (`exposure_amount > 0`); the subtree denominator scope
   ratified; the "SQLite structurally blind" claim corrected to the both-dialect
   `sqlite_where` idiom. All 26 findings folded at v5 (this version); the fold quality measured
   by the pass itself: 40/47 of the prior ledger resolved with substance, and the descope's core
   — the share, the grain redesign, the three-code mint, the basis discipline — SURVIVED
   refutation for the first time in three passes.

4. **v5 targeted pass (2026-07-30, single refuter over ONLY the v5 fold diff): 1 BLOCKING, 3 HIGH,
   2 LOW — all folded at v6 (this version).** The BLOCKING was the record's own claimed
   measurement: the v5 holder sets substituted `ops` for the bootstrap's `data_steward` in all
   three codes and claimed seven roles where there are six — a faulty extraction presented as
   "measured exactly", caught by recomputation from source (the seventh-ledger discipline applied
   to this record's own text). The HIGHs: the DEMO-CONCENTRATION issuer-dimension literals
   contradicted the v5 per-dimension predicates (re-derived: BETA-LLC is CLASSIFIED by its issuer
   edge; HHI_ISSUER 0.450000, CR_5 0.900000, coverage per-dimension); DEMO-MULTIASSET's refusal is
   the 0/0 all-UNCLASSIFIABLE gap, not the coverage floor; Part 3's binder line still listed two
   post-build refusals as pre-build; and the `portfolio_id = scope_portfolio_id` pin was not total
   (NULL-scope snapshot-consume runs exist — now a pre-build refusal). Verified-clean by the same
   pass: the short-bearing fixture arithmetic exact to 6dp; the OQ-CON-1-15 reversal's fail-closed
   premise quoted from `limit/service.py`; the both-dialect index convention; the dunder-sentinel
   non-collision; the 26/41/136 consistency.

*(Four passes total; the v6 deltas are pure record edits verified against measured code state.)*

**Execution addendum (2026-07-30, the seventh ledger — delivery claims cited to executed
artifacts):** the P4 dry run EXECUTED on `0057` (upgrade clean; `alembic check` no-drift; the
STAGED-ROWS destructive proof: 3 rows staged → downgrade → table GONE → upgrade → 0 rows, trigger
restored — never a zero-row smoke). FIRST LIVE BATTERY: 143/144 — every stage-19 assertion green
on first execution, including the Part 2 literals to six decimals on both books, the counts pin
26/41/136 MEASURED, and the MULTIASSET 0/0 FAILED-run control. **The single failure
(`test_demo_stage9zzzzz_ops_pg.py::test_the_demo_tenant_role_census_after_stage_14`, 13 vs 2)
REPRODUCES IDENTICALLY ON UNTOUCHED MAIN under the same local single-database layout** (isolation
pair, fresh schemas, main via worktree): the census's expected value encodes its CI execution
layout (a teardown between steps clears the campaign's 11 auditor role rows before the census
reads), so it is a PRE-EXISTING environment-layout sensitivity in that OPS-1-era census, NOT a
CON-1 defect — recorded here for the review pass and for OPS hygiene; CI (the authoritative
layout) adjudicates on push.*

## Part 8 — The adversarial review fold (2026-07-30, POST-implementation)

Three refute-by-default lanes (quant/correctness, security/RLS, record-vs-diff) ran in fresh
contexts against `git diff b89601e..HEAD`. All three independently returned the SAME BLOCKING, and
the fold below is what changed as a result. Two of these entries CORRECT claims made earlier in
this record; they are written here rather than silently edited in place so the record shows what
was ratified, what shipped, and why they differ.

### The BLOCKING — OQ-CON-1-24 (i) was ratified in an unfireable form

**As ratified**, the mixed-VERSION discriminator was "more than one live `scheme_id` within the
SAME (`dimension_kind`, `scheme_family`) **among the pinned assignments**". The pinned assignment
set is filtered to the REQUESTED `scheme_id` (`_list_current_assignments`), so it can never contain
a second version — the refusal could not fire under any input. The FOURTH pinned shape was
ratified specifically to make that discriminator computable from pinned bytes, and nothing consumed
it. Meanwhile FOUR shipped surfaces advertised the control (the builder docstring, the
`ConcentrationSnapshotError` docstring, `concentration/service.py`'s pin comment, and the API's 409
detail string). This is the vacuous-guard class the SCH-2 and MG-2 lessons name: a documented
fail-closed control with no reachable firing path.

**Folded as a deliberate STRENGTHENING of the ratified wording:** the discriminator now reads the
tenant's **LIVE current-head assignments** for the pinned instruments, WITHOUT the scheme filter
(`_list_current_assignment_scheme_ids`), and refuses when more than one live `scheme_id` shares the
requested scheme's family in that dimension. Clause (iii) is untouched — a different FAMILY
co-existing stays legal and simply is not consumed. The pinned scheme rows are **re-recorded as
EVIDENCE** (which taxonomy version produced the number, re-verifiable from pinned bytes), not as
the discriminator, and all four advertising surfaces now describe what the code does.

Controls: an ISIC Rev.5 + Rev.6 book REFUSES; an ISIC + NACE book still BUILDS (the positive
control clause (i)'s own rationale demands, without which the refusal could be a blanket
over-refusal). Both are PG-tier. The refusal is **mutation-proven**: widening the threshold to
`> 99` reddens exactly the new control and nothing else — which also confirms the test would have
been RED against the shipped code, i.e. the lanes' finding was correct.

### What EXECUTION found that three reading lanes missed

The security lane byte-compared the migration's CHECK text against the ORM's and reported them
identical, "names align via the `ck_` convention". **They did not.** `0057` passed FULL constraint
names into `op.create_table`, but the metadata naming convention prepends `ck_<table>_` itself, so
every CHECK landed **double-prefixed** — `ck_concentration_result_ck_concentration_result_row_kind`
— and the longest was TRUNCATED by PostgreSQL to 63 characters
(`..._ck_concentration_result_issuer__a1f4`). `0055` gets this right and says so in a comment;
`0057` did not follow it. The existing tests' `match="summary_shape"` passed either way, because
the ratified name is a SUBSTRING of the double-prefixed one.

Nothing found this by reading. It surfaced the moment a fresh schema was migrated and the live
catalog was queried. **Mechanical gate added** (P7 — a lesson is an act): a PG test that reads
`pg_constraint` for `concentration_result` and asserts set-equality against the ORM's declared
CHECK names, plus a ≤63 length assert so a truncation can never again present as a passing
substring match. The six names are now correct in the database, and the P4 destructive dry run was
**RE-EXECUTED** on the amended migration (6 rows staged → downgrade → table GONE → upgrade → 0
rows, trigger restored, FORCE RLS on, 6 CHECKs present).

### Ratified-but-undelivered items, now delivered

1. **The pre-build refusals shipped with ZERO negative controls** while Part 3 called them
   "negative-controlled". All now have executed PG-tier controls: mixed VERSIONS (+ the
   co-existing-families positive control), mixed BASIS, scheme/dimension MISMATCH, EMPTY atoms, and
   the NULL-scope upstream run — the last asserting **zero `calculation_run` and zero
   `dataset_snapshot` rows** survive the refusal, which is the actual claim ("refused from the run
   head", a run being unwithdrawable).
2. **The `0057` P0001 append-only trigger was never executed by any test.** UPDATE and DELETE
   controls added, asserting the SQLSTATE itself.
3. **`SNAPSHOT_COMPONENT_KINDS` set-equality**, claimed three times as landing "HERE", was never
   written — every prior guard was a membership assert, which cannot notice an added, removed or
   renamed kind. Added, plus a companion asserting every kind has a `_reresolve_content` branch (a
   pinned shape without one verifies VACUOUSLY). The companion's first draft was itself vacuous —
   `k in source` is satisfied by every constant name containing its own value — and tightening it
   to a word-bounded match immediately exposed that `PORTFOLIO` is dispatched by FALLTHROUGH; that
   exemption is now explicit and grounded by an assertion on the fallthrough itself.
4. **The `row_kind` census** (a ratified P6 floor) had no test. Added, cross-checked against the
   DDL CHECK text so a third kind added in Python without the migration is loud in the unit tier.
5. **OQ-REF-1-29's demo role census + teardown**, recorded HERE as "paid in CON-1's demo stage",
   was not built — stage 19 contained no Role/Permission code at all, exactly as REF-1's stage 18
   had not. Now built: the stage grants the six REF-1 + CON-1 read codes to a demo role, censuses
   them exactly, then TEARS THE GRANTS DOWN and proves none survive (a demo that only ever grants
   leaves rows a later entitlement census misreads as production access). Pinned by a test that
   re-reads the database rather than trusting the stage's return value.
6. **Both-tier obligations that shipped in one tier.** The duplicate-refusal controls (including
   the ratified duplicate-`__UNCLASSIFIED__` case) now run in the UNIT tier too, so the
   `sqlite_where` half of the v4 repair is exercised rather than merely declared; the short-bearing
   book now runs END-TO-END in the PG tier, not only in the unit kernel.
7. **CR-N's real coverage.** OQ-CON-1-21's labelled P5 mitigation promised a seven-bucket unit
   fixture; every shipped fixture had at most three classified buckets, where `CR_5` equals the
   classified total identically and the top-5 truncation is never executed. Added with
   hand-derived literals (CR-5 = 0.900000 ≠ 1.000000, HHI = 0.201000).
8. **The `str(issuer_id)` bucket-code invariant** ("a service invariant with its own PG-tier test")
   and **the non-String read filter pins** (`portfolio_id`, `as_of`) had no tests; both added
   against a real governed run.
9. **OQ-CON-1-7's "no drift on EACH excluded field"** tested one of four. Now loops all four, with
   a census assert so a new `_UPDATABLE` field forces a decision rather than silently widening.
10. **OQ-CON-1-9 through the REAL verify path.** The existing control computed closure content
    directly, so the CLASSIFICATION `_reresolve_content` branch — the platform's first code-first
    re-derive and this slice's headline deviation — was executed by NO test. Now proven through
    `verify_snapshot`, with a positive control (a fresh snapshot verifies clean) before the
    negative (a leaf override reddens it).

### Hardening taken beyond the findings

- **`coverage_floor` must now be strictly positive.** A zero floor is not permissive but broken:
  an all-UNCLASSIFIED dimension has classifiable coverage 0, clears a zero floor, and COMPLETES —
  writing immutable MAX/HHI/CR-5 rows of `0.000000` over an EMPTY classified set.
- **A DB-level disclosure fence.** `issuer_id` is now refused on any non-ISSUER row. The prior
  CHECKs required an issuer on real ISSUER buckets but never forbade one elsewhere, so a
  `SECTOR_INDUSTRY` DETAIL row carrying `issuer_id` was schema-legal and would have passed the
  `concentration.view` exclusion (which keys on `(ISSUER, DETAIL)`) carrying proprietary issuer
  identity to a caller holding no `concentration.issuer.view`. Only binder discipline stood in the
  way; now the engine does. Negative-controlled.
- **The compute-zone orphan closed.** `_level1_code` raised from INSIDE `_compute`, and the
  scaffold calls `compute()` outside its only `try` — so corrupt pinned content would have orphaned
  a run in RUNNING with a committed snapshot (Part 0 fact 2's own BT-1 class). Such breaches now
  return a `CORRUPT_PINNED_CONTENT` gap: a committed FAILED run with a named reason. The
  `ConcentrationInputError` docstring, which claimed "raised BEFORE any run/snapshot write", is now
  true again.
- **`GET /concentration/runs/{run_id}` point-selects.** It had listed the newest 1000 runs and
  filtered in Python, so a tenant past its 1000th run got a spurious 404 on every older run — and
  the scheduler ticks these monthly per tenant per portfolio, so the ceiling is reachable.
- **`ConcentrationModelParameterError`** replaces bare `ValueError` in the API error map, which had
  relabelled ANY server-side bug inside registration as a client 422 and re-armed the API-2 MRO
  trap (isinstance-caught, exact-type-mapped → `KeyError` 500).
- **Join-key normalization.** The issuer-edge and assignment serializers used raw `str()` while the
  atoms are `_norm_guid`-normalized, so an uppercase-stored id would have silently read
  UNCLASSIFIABLE instead of failing loudly. Both sides now normalize.

### Deviations from the ratified wording, recorded rather than hidden

- **OQ-CON-1-24 (i)** now reads LIVE heads, not the pinned set — see above. This is a
  strengthening; the ratified form was unfireable.
- **OQ-CON-1-28** shipped as a RAISE at build/verify time (`resolve_ancestors` raises
  `ClassificationNotVisible`), not the ratified "gaps-mapped refusal in the binder". Fail-closed
  either way, and arguably the stronger form (it refuses PRE-BUILD rather than committing a FAILED
  run), but it is a timing deviation and is recorded as one.
- **`0057`'s downgrade body** drops the trigger and policy explicitly and lets the partial indexes
  ride the table drop; the ratified wording said the reverse. Functionally equivalent, executed
  destructively in both directions.
- **Effective-number-of-holdings (`1/HHI`)** is NOT rendered. OQ-CON-1-2 ratified it "at the read
  surface rather than stored", but v1's FE surface for concentration is the generic runs list with
  no dimension detail table, so there is no honest home for a derived column yet. **DEFERRED with
  a trigger: the first concentration detail view.** It remains a pure derivation over a shipped
  number — nothing is lost by not storing it.
- **The Part 3 gates line** listed "the NEW `_METRIC_MAP` exact census" among P6 floors shipped
  with their guards. That contradicts this record's own OQ-CON-1-15 reversal, which defers
  `_METRIC_MAP` registration to LIM-2. The CODE is correct (no census, no entry); the gates line
  was stale from v5. Corrected in place.
- **CTRL-018** (scheduled reproduction job) — **no control moved.** CON-1 ships per-snapshot
  `verify_snapshot` coverage for `CONCENTRATION_INPUT`, which is not the scheduled reproduction job
  CTRL-018 describes; it stays Planned. Stated explicitly per the P1 seventh-ledger obligation,
  which the closeout had half-delivered (CTRL-002 extended, CTRL-018 silent).

### Correction to this record's own execution addendum

The addendum above reports the stage-14 ops role census failing 13-vs-2 locally and reproducing on
untouched `main`. That diagnosis was right about the cause and incomplete about the consequence:
in a **single fresh-schema battery over all three testpaths** — the layout CI uses — the census
**passes**. The sensitivity is real but is a property of running partial subsets against a reused
database, not of the census's expected value being wrong. No OPS follow-up is owed.

### The fold's own verification pass (2026-07-30, fresh context)

The fold itself was then adversarially verified by an independent fresh-context pass over the
uncommitted diff, instructed to refute every claim above. It CONFIRMED all ten numbered items —
including recomputing the seven-bucket CR-5/HHI/MAX literals by hand, reading the six constraint
names back from the live `pg_catalog`, and establishing that the serializer normalization cannot
false-drift previously pinned content (every id generator in the codepath already emits lowercase,
and the three serializers are CON-1-new) — and REFUTED one sub-claim: the compute-zone except
tuple omitted `KeyError`/`TypeError`, the archetypal shapes corrupt pinned JSON actually takes (a
missing content field; `Decimal(None)`), so that residue of the orphan path was still open while
the comment claimed it closed. **Folded before push:** the tuple now covers both, and the kernel
comment states the covered shapes precisely. Two informational notes stand without code change:
a book live-classified under only ONE version, requested under another, degrades to
all-UNCLASSIFIED and fail-closes via the coverage floor rather than the mixed-version refusal
(fail-closed either way, by a different gate); and the closure's `parent_node_id` was normalized
for consistency though it could not false-drift (build and verify share the serializer).
