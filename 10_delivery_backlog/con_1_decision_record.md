# CON-1 Decision Record — concentration, the 23rd governed number (Wave-14 slice 1)

| Field | Value |
|---|---|
| Status | **DRAFT v2 — pre-ratification, NOT yet re-verified.** v1 broke 46 findings deep (5 BLOCKING) including its methodology foundation; all folded here, and the folded record warrants its own verifier pass before implementation |
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
  **Mitigation in-slice:** `long_amount` is already a stored column and equals total assets on a
  long-only book, so a total-assets-based share is additionally derivable; store or declare it, and
  record the trigger "the first consumer needing a limit-comparable share" for the NAV entity that
  would make the real ratio computable.
  **Refusal:** a zero gross total is refused as a `gaps` entry, never divided by.
- **OQ-CON-1-2 — the measure set. Recommend share + CR-N + HHI**, with effective-number-of-holdings
  rendered at the read surface rather than stored (it is `1/HHI`, a pure derivation).
  Share-of-total is mandatory — it is the numerator of every cited limit (UCITS Art. 52's 5/10/40,
  IRC §851(b)(3)'s 5%/25%, Solvency II's CT_i × Assets, BCBS's 25% of Tier 1) and it is what makes
  the family limits-ready. CR-N and HHI are the two measures with authoritative external
  definitions and established fund/index application, and both are pure functions of the shares —
  cheap in-slice, and a later slice adding them would have to re-open this table. **Normalized HHI
  (H\*) is excluded from v1** with the trigger "a consumer needs cross-book comparability at
  differing N".
- **OQ-CON-1-3 — HHI scale. Recommend the FRACTION (0–1) form**, and the load-bearing requirement
  is that the scale be **DECLARED in the registered model assumptions**, not which form is picked.
  **CORRECTED from v1:** the stored HHI is **not** "exactly the sum of the stored shares squared" at
  the platform's quantum — quantize-then-square differs from square-then-quantize by up to N ulps
  (Part 2 shows 0.356057 stored from unrounded ratios vs 0.356058 from the quantized shares). A test
  written to v1's identity would FAIL on v1's own reference values. The identity is therefore stated
  with a tolerance: `abs(HHI − Σ stored_shareᵢ²) ≤ N·10⁻ˢᶜᵃˡᵉ`. The fraction-form decision survives on
  the no-magic-constant argument alone: under the 0–10,000 convention every threshold and derivation
  carries a 10⁴ factor a later reader cannot recover from the column. Under the 0–10,000 convention every threshold and derivation carries a 10⁴ factor
  a later reader cannot recover from the column, and a mis-scaled value is silently plausible.
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
  the chain**, which corrects OQ-REF-1-25. Two independent reasons: `resolve_node` prefers a tenant
  override for the same `(scheme_id, code)` and `resolve_ancestors` walks parents **by id**, so a
  later node override changes the sector bucket **with no pinned byte changing** — verify stays
  green while the number becomes unreproducible; and a whole-scheme node-set hash would false-drift
  on any unrelated node ADD, which `create_node` permits and the demo's partial skeleton invites.
  The pin is therefore scoped to **the ancestor closure of the pinned leaf codes**.
- **OQ-CON-1-10 — mixed-scheme-version aggregation: refuse PRE-BUILD, not at compute. Recommend
  pre-build.** Every snapshot table is IA true append-only, so a snapshot built over a mixed-version
  set is immutable governance garbage that cannot be withdrawn — the same reasoning the codebase
  already gives for every pre-write refusal.
- **OQ-CON-1-11 — as-of reconstruct for the pinned assignments. Recommend pinning current heads in
  v1.** Nothing exists to reconstruct against (shared-python has no assignment as-of read), and
  CON-1's input is a now-anchored "latest COMPLETED exposure run" selection, so a backdated
  `valid_at` has no consumer in this slice. Shipping the bitemporal read now would make its only
  exercise its own test — the vacuity pattern P5 exists to prevent. Recorded with the trigger "the
  first consumer needing a backdated concentration".

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
  discriminated by `metric_type` (the `desmoothed_return_result` PERIOD-vs-SUMMARY precedent).
  Detail rows carry `dimension_kind` + the bucket identity + gross/long/short/net + share. Summary
  rows carry the limit-selectable metrics. **The summary `metric_type` ENCODES the dimension**
  (`MAX_SHARE_ISSUER`, `HHI_SECTOR`, …) because `_resolve_latest` picks `matching[0]` and would
  otherwise silently resolve to whichever bucket sorts first (Part 0 fact 8).
- **OQ-CON-1-14 — dimension identity: a SCHEME-QUALIFIED pair (`scheme_id` + `node_code`), not a
  node FK and not a bare code. Recommend the pair.** A node FK is refused on the same principle
  REF-1 applied to assignments — PostgreSQL referential checks bypass RLS, so an FK would let a
  proprietary row reference a hybrid node its own `USING` cannot see. A bare code is ambiguous
  across schemes. This is also LIM-2's frozen selector, so it is fixed here with limits-readiness
  as a named acceptance constraint.
- **OQ-CON-1-15 — register the metrics in `_METRIC_MAP` in-slice. Recommend YES.** REQ-CRD-003's
  acceptance verb is literally "Limits-ready metrics **produced**", so leaving registration to LIM-2
  would mean the REQ cannot honestly advance at CON-1's close. It costs one dict entry plus one
  resolver branch and needs no API/DTO change.
- **OQ-CON-1-16 — the wildcard regulatory rule ("no single issuer > 5%") binds to the run-level MAX
  metric, not to N per-bucket limits. Recommend the MAX form** — close to forced, because
  `uq_breach_limit_run` permits one breach per (limit, run), so a per-bucket wildcard could not
  record the three issuers it breached on.
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

- **OQ-CON-1-23 — the ISSUER bucket identity (NEW; v1 could not represent its own primary
  dimension).** Issuers are **not** classification nodes — they are proprietary `issuer` rows reached
  through `instrument.issuer_id`, and REF-1's `DIMENSION_KINDS` enumerates only SECTOR_INDUSTRY and
  COUNTRY_OF_RISK. v1's `(scheme_id, node_code)`-only identity therefore had **no column, no scheme
  and no vocabulary value for an issuer bucket**, while its own reference values, its pin argument and
  its `MAX_SHARE_ISSUER` metric all presupposed one. **Recommend:** add a nullable `issuer_id` GUID
  (intra-tenant, cross-tenant-guarded) beside the pair, with a **total-enumeration DB CHECK per
  `dimension_kind`** (`ISSUER` ⇒ `issuer_id` NOT NULL and the node pair sentinel-valued;
  `SECTOR_INDUSTRY`/`COUNTRY_OF_RISK` ⇒ the inverse) on the `ck_schedule_model_version_by_family`
  idiom, which fails CLOSED for an unenumerated kind. **`ISSUER` is a CON-1-owned `dimension_kind`
  value and must NOT be added to `classification.DIMENSION_KINDS`** — no assignment row can carry it —
  and that split is pinned by a test.
- **OQ-CON-1-24 — CO-EXISTING schemes (NEW; v1 answered only mixed VERSIONS).** REF-1's current-head
  key includes `scheme_id` precisely so one instrument may carry an ISIC sector AND a NACE sector at
  once — a permanent legal state. **Recommend:** (i) the refusal discriminator is "more than one live
  `scheme_id` within the SAME (`dimension_kind`, `scheme_family`)", so ISIC + ISO-3166 stays legal
  while ISIC Rev. 5 + Rev. 6 refuses; (ii) `scheme_id` is an **explicit run input**, pinned in the
  snapshot and echoed on the result row, so the number records which taxonomy produced it; (iii) a
  book carrying a second live scheme in the same dimension outside the requested one refuses
  fail-closed.
- **OQ-CON-1-25 — the R-07 permission mint (NEW; v1 never asked).** CON-1 ships API reads for a
  governed family that OQ-CON-1-19 deliberately homes in a NEW `concentration/` package, so it cannot
  inherit `risk.view`/`perf.view` the way BT-1/RM-1/SR-1 did — those reuse the pair because their code
  lives in `risk/`/`perf/`. **Recommend minting `concentration.run` + `concentration.view`** on the
  pacing precedent, with the holder set for each named explicitly and **`auditor_3l` INCLUDED in
  `.view`** (the governed-OUTPUT precedent: the 3L auditor reads governed results), plus a
  `_holders(code) == {...}` pin per code in both directions. Silence here is what let REF-1's
  single-code SoD defect nearly ship.

### Demo

- **OQ-CON-1-20 — the demo selects its exposure run EXPLICITLY by boundary, never "latest".
  Recommend explicit selection** — forced by Part 0 fact 10: the latest DEMO-GLOBAL run is SCH-2's,
  which is 99.98% one issuer and would make the flagship demo absurd. The stage resolves the
  portfolio by code, selects the campaign boundary run, and **asserts exactly one match** (the SR-1
  deterministic-discovery pattern).
- **OQ-CON-1-21 — the demo needs a PARTIALLY classified book, not just 100% and 0%.** v1 paired
  DEMO-GLOBAL (100% classified) with DEMO-MULTIASSET (0%) and called that coverage cover. It is not:
  at 100% the gate is inert and at 0% the run refuses before any share is computed, so **neither book
  exercises the thing OQ-CON-1-4 exists for** — a partially-classified book whose shares are computed
  over a visible residual. The stage therefore classifies a SUBSET of a book (or leaves one of the
  DEMO-GLOBAL instruments unclassified in a dedicated portfolio) so the UNCLASSIFIED bucket, the
  `coverage_ratio` field, and the exclusion of the residual from the rankings are all demonstrated on
  real data. DEMO-MULTIASSET stays as the refusal negative control.
  **Also recorded:** CR-N is degenerate on a three-holding book (CR-5 == 100%), so either the demo
  book is widened or CR-N ships explicitly un-demonstrated by the demo with its unit coverage named —
  the P5 vacuity pattern, labelled rather than hidden.
- **OQ-CON-1-22 — counts MOVE, and the expected triple is DECLARED here.** One new model code
  (`risk.concentration` or `concentration.dimensional` — fixed at the gate), one INITIAL validation
  record, and N new COMPLETED runs where N is the demo stage's run count: **25/40/133 →
  26/41/(133+N)**, with N pinned once the demo book set is ratified (OQ-CON-1-21 changes it). v1 said
  only "counts move", which pins nothing and hides the dependency on the demo design. The
  final-position pin relays to CON-1's suite (ten `z`, verified by `ls`, not read off this record).
  **Also relayed:** the machine-enforced EXACT vocabulary censuses (`_METRIC_MAP`, `SNAPSHOT_PURPOSES`,
  `_BINDING_PREDICATES`, the component-kind set) each move by construction — a set-equality census is
  not a count pin and must be updated in the same commit.

## Part 2 — Independently computed reference values

Per the standing rule that expected values must be derived **independently of the implementation**,
these are hand-computed from the demo fixtures (`campaign.py` marks, quantities and FX), for
DEMO-GLOBAL boundary run r0 (`as_of` 2026-05-18, base USD):

| Instrument | Quantity | Mark | FX | Exposure |
|---|---|---|---|---|
| EQ-ACME-US | 400 | 150.00 USD | 1 | 60,000.000000 |
| EQ-EURX-DE | 300 | 95.00 EUR | 1.080000000000 | 30,780.000000 |
| PE-HARBOR-IV | 50 | 1,080.00 USD | 1 | 54,000.000000 |

All three are long, so gross == signed net == **144,780.000000** on this run — which is why the
suite must ALSO cover a short-bearing book, or the gross convention would be untested by the demo.

**Issuer shares:** ACME-CORP 0.414422, HARBOR-GP 0.372980, EURX-AG 0.212598 (sum 1.000000).
**Sector shares** (ISIC level-1 ancestors: C26→C, C28→C, K64→K): **C = 90,780.000000 → 0.627020**;
**K = 54,000.000000 → 0.372980**. Two holdings rolling into one sector is what makes the number
non-trivial — a book with one holding per sector could not demonstrate concentration at all.
**Country shares:** US = 114,000.000000 → 0.787402; DE = 30,780.000000 → 0.212598.
**HHI (issuer, fraction):** 0.414422² + 0.372980² + 0.212598² = **0.356057**.
**Effective number of issuers:** 1/0.356057 = **2.809**.

> **Why these are stated to six decimals and were re-derived by execution.** The first draft of this
> section carried **0.348834** for the HHI (and 2.867 for the effective number) — arithmetic I did in
> prose and got wrong; the sector shares were also off by 3e-6 from carrying rounded intermediates.
> Re-deriving them with `Decimal` at the platform's own quantum caught both. That is the standing
> rule working as intended: a reference value computed the same way as the implementation, or
> computed carelessly, proves nothing. **The implementation must reproduce the table above, and the
> test must carry these literals rather than recomputing them from the fixtures** — otherwise the
> expected value and the code share a single point of failure.

## Part 3 — Implementation shape

**ENT-069 `concentration_result`, migration `0057`** — IA append-only (ORM guard + P0001 trigger).
NOT NULL: `calculation_run_id`, `input_snapshot_id`, `model_version_id`, `portfolio_id`,
`dimension_kind`, `metric_type`, `scheme_id`-or-sentinel, `node_code`-or-sentinel. Nullable and
CHECK-gated: `issuer_id` (OQ-CON-1-23). Values: `gross_amount`, `long_amount`, `short_amount`,
`net_amount`, `metric_value`, `coverage_ratio`.

**Grain constraints — specified, because v1 left them to "a run-grain unique constraint" and that
was VACUOUS where it mattered most.** Every key column is NOT NULL with a declared sentinel (the
`BASIS_NOT_APPLICABLE` / `REFERENCE_KEY_NONE` pattern REF-1 already ratified for this exact problem):
`node_code = 'UNCLASSIFIED'` for the residual bucket and a distinct sentinel for summary rows. On
PostgreSQL a NULL in a UNIQUE constraint constrains **nothing**, so a nullable `node_code` would have
silently disabled the grain for precisely the two row classes that need it — the limit-selectable
summary rows and the coverage-bearing residual — re-creating the `_resolve_latest` `matching[0]`
hazard of Part 0 fact 8 by the record's own hand, one slice after REF-1 ratified the opposite fix.
Two constraints: summary rows `UNIQUE(calculation_run_id, metric_type)`; detail rows
`UNIQUE(calculation_run_id, metric_type, dimension_kind, scheme_id, node_code, issuer_id)`. A row-kind
CHECK prevents a summary row carrying bucket identity or a detail row carrying none. **PG-tier
negative controls** that a duplicate summary row AND a duplicate UNCLASSIFIED row are both refused —
SQLite cannot see the NULL semantics, so a unit-only pin would be structurally blind.

**`metric_type` width:** the dimension-encoded names (`MAX_SHARE_ISSUER`, `HHI_SECTOR_INDUSTRY`, …)
must fit the shipped `String(30)` used across the metric-map families; the longest candidate is
measured and the vocabulary constrained to fit, with an exact-census test.

**New `concentration/` package** — the binder (upstream-run discovery, the pre-build refusals, the
snapshot legs), a DB-free kernel (shares, CR-N, HHI over pinned rows), and the bootstrap registrar
with the declared parameters.

**Snapshot legs** — a new PURPOSE, binding predicate, and three pinned shapes: the exposure atoms,
the narrow instrument→issuer edge, and the classification assignments + ancestor closure. Each with
its serializer, explicit-tenant resolver, `_reresolve_content` branch, and verify except-tuple entry.

**Reads** — `calc/reads.py` typed wrappers + list/latest/entity-time endpoints (rule 7), with
PG-tier pins for every non-String filter.

**Gates** — `make check`; fresh-schema full-PG; `alembic check`; a P4 executed dry run of `0057` up
and down; the new CI PG steps; `make gen-api`; the closure stamp verified by executing
`check_docs._status_lines`.

## Part 4 — Sizing

**M/L.** One entity + migration, a new package with a kernel, THREE snapshot pinned shapes (the
largest single cost — Part 0 fact 7), a registered model with declared parameters and a validation
record, `_METRIC_MAP` registration, rule-7 reads, two demo runs on two books, and the count relay.
**Split candidate if it runs long:** the country dimension (the machinery is identical to sector, so
it is additive data rather than new code) — but NOT the coverage gate, which is a correctness rail.

## Part 5 — Cited external research (rule 6a), RESTATED

Sources dated 2026-07-29. **v1's version of this section did not satisfy rule 6a** — it cited two
texts for the opposite of what they say, which is worse than citing nothing because it launders a
guess as authority. Each source is now cited for what it actually establishes:

- **Regulation 231/2013 Art. 7** — the "sum of the absolute values of all positions" is the AIFMD
  leverage **NUMERATOR**. Art. 6(1) gives the denominator as **net asset value**. Art. 7 further
  excludes base-currency cash and matched cash borrowings and requires derivative→underlying
  conversion (Art. 10), none of which this platform performs — so the platform's gross is not Art. 7
  gross either.
- **CESR/10-788 Box 2 point 2(b)/(c)** — the absolute value is taken **after** netting and hedging
  are identified; the guideline is netting-**permissive**. Box 3 mandates offsetting perfectly
  correlated swaps. Its denominator is NAV throughout (Box 8: "not greater than 100% of NAV").
- **ESMA/2013/1339 ¶84/91/93** — no netting between instruments of the same sub-asset type, reported
  by long and short: this governs the **NUMERATOR** and is what the long/short decomposition
  satisfies. **¶87 gives the denominator: "percentage in terms of total value of assets."** ¶106
  requires currency exposure as separate long and short values.
- **Limit regimes and their denominators** — UCITS Directive 2009/65/EC Art. 52 (5/10/40, with the
  20%/35% variants) against NAV; US IRC §851(b)(3) RIC diversification (5%/25%) against total assets;
  Solvency II market-concentration SCR (CT_i × Assets); BCBS large exposures (25% of Tier 1 capital).
  **None uses a gross absolute-value denominator** — which is precisely why OQ-CON-1-1 now records
  that CON-1's primary share is not any of these ratios.
- **Measures** — HHI as the sum of squared shares (DOJ/OECD, conventionally 0–10,000, deliberately
  not adopted here per OQ-CON-1-3); CR-N as the top-N concentration ratio; effective number of
  holdings as 1/HHI.

## Part 6 — Corrections## Part 6 — Corrections this slice's recon forced on prior RATIFIED records

Folded separately as `3b74a52`, recorded here because CON-1 stands on them:

1. **OQ-REF-1-23's write-freeze was ratified and never implemented** — `issuer.sector` remained
   writable while REF-1's record described the freeze as done. Two live sector representations,
   entering the slice that computes sector buckets. Now delivered.
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
   in a record reading as delivery, for the fourth time in one slice. **To be corrected on the REF-1
   fold branch alongside the other three.**
9. **REF-1's carry #3 was only HALF discharged by v1 of this record.** REF-1 specified the node pin as
   the node-set hash **excluding `name`/`description`**; v1 replaced the set hash with the ancestor
   closure (correctly, OQ-CON-1-9) but dropped the field exclusion without mentioning it. The
   exclusion is restored: the ancestor-closure hash covers `code`/`parent_node_id`/`level` and
   excludes `name`/`description`, so a cosmetic rename cannot redden a historical run.

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
3. **The metric set is broader than "share-of-total"** implied by the roadmap's "share-of-total,
   top-N, HHI-class metrics" phrasing only in that CR-N and HHI are now explicitly governed values
   rather than read-surface derivations — a widening, recorded for symmetry.
4. **"Immediate-issuer grain; ultimate-parent rollup stays deferred"** is honoured unchanged; noted
   here so the gate can see it was checked rather than assumed.

## Part 7 — Pre-ratification verifier pass (findings ledger)

*(Filled before the gate; refute-by-default, fresh-context lanes.)*
