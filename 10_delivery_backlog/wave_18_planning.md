# Wave-18 planning record — the structure block (REQ-PPM-006 … REQ-PPM-010)

| | |
|---|---|
| Status | **RATIFIED by the user 2026-08-15 ("Proceed with your recommendations") — all 14 decision points adopted as recommended (Part 3)** |
| Authored | 2026-08-15, against main `aac1759` (tree clean, CI green on all nine checks, migration head `0070_app_role`) |
| Method | Ultracode planning workflow `wf_f0ef96d8-350`: 5 subsystem readers → 3 independent slice-plan drafts (dependency-first / demonstrable-first / risk-first) → 2-judge panel → 5 per-row refute-by-default verifiers. Winner: dependency-first (16.5/20 combined), with 12 judge grafts and 8 verifier gap-fixes folded below. This satisfies the pre-ratification adversarial review; findings are in Part 6. |
| P20 (T1) | All five rows carry a current G2 adjudication (`g2_adjudication_ledger.jsonl`, 2026-08-13 entries). REQ-PPM-001's two clauses consumed by STRUCT-3 carry the 2026-08-15 worklist adjudication. T2 standing: any acceptance-cell edit during this wave lapses the row and re-blocks the gate. |

## Part 0 — Organizing facts (recon-verified against main by the workflow readers)

1. **The exposure grain is single-measure today, and the row's collision claim is TRUE.** `ExposureAggregate` carries `exposure_type` (String(30), NOT NULL, ORM default MARKET_VALUE) but `uq_exposure_aggregate_run_grain` = (calculation_run_id, portfolio_id, instrument_id, base_currency) — the type is excluded (`exposure/models.py:56-62`, migration `0018:79-85`; defined in TWO places that must change in lockstep). Exactly ONE producer exists (`exposure/service.py:186-202`, hard-coded MARKET_VALUE).
2. **A second measure in the same run silently double-counts in FOUR governed families today.** Factor exposure, perf returns, concentration, and liquidity all pin EVERY atom of the consumed exposure run with no `exposure_type` predicate (`snapshot/service.py:651-663`, `perf/return_service.py:200-214`, `concentration/service.py:240-246`, `liquidity/service.py:76-80`) and sum `exposure_amount`. The reproduction adapter's comparison key also omits the type (`reproduction/registry.py:317-329`). **The widened key, the second producer, and the consumer measure declarations + refusals must therefore land in ONE slice.**
3. **NOTIONAL is buildable from shipped schema, but not lawfully computable yet.** `InstrumentTerms.face_value` exists (Numeric(20,4), nullable; `reference/models.py:371-395`). No snapshot component kind pins instrument terms, and AD-014 forbids live reads in the compute — a NOTIONAL producer needs a new pinned-terms component. The FR-row pin precedent is CLASSIFICATION (`ClassificationAssignment`, FULL_REPRODUCIBLE); FACTOR is the EV-pin flavor, not FR — corrected from the draft, verifier finding V-006-3.
4. **No rollup code exists.** No hierarchy versioning exists (single EV table, `node_type` + `parent_portfolio_id`, mutable head — deliberate design). Runs carry `scope_portfolio_id` but the snapshot-consume path accepts NULL. Demo data is two-level.
5. **FX**: the governed exposure compute uses `compose_effective_rate` (identity path returns `(Decimal(1), [])`) — NOT `convert()`; regression guards must target the path the family actually executes (verifier finding V-010-2). `fx_legs` reaches the API; zero screens render it. `portfolio.base_currency_code` exists with a silent USD default.
6. **The PPM-009 name census has exactly three production read classes today** (verified by repo-wide sweep): display (`api/portfolios.py:105`), audit payload (dynamic `getattr` over `_AMENDABLE`, `portfolio/portfolio.py:284,293` — invisible to literal grep), and provenance capture (`snapshot/serialize.py:115` pin + `snapshot/service.py:3871` drift re-read; recorded and byte-compared, never interpreted). Computation reads: NONE. Frontend: zero.
7. **Process bindings**: G3 does not mechanically bind (no 21.x rows), but PPM-010's own acceptance carries the visible-screen clause. G4 binds the Wave-18 CLOSE — its first live run; the zero-bindings control must be deleted at that close per its own instruction (recorded in Part 5 so it is not homeless, P19).

## Part 1 — Scope boundary

IN: REQ-PPM-006, -007, -008, -009 (name-inertness half only — mandate comparison is DECLINED, ratified 2026-08-13), -010, plus REQ-PPM-001 clauses (1) and (2) as PPM-008's named dependency. OUT (each with its named trigger, P19): commitment funded/unfunded pair (trigger: unfunded enters the exposure grain); swap notional/market-value pair (trigger: instrument terms can express a swap); duration contract row (trigger: a duration producer lands — a contract row for a non-existent family breaks the exact-set census, judge caution); PPM-001 clause (3) entitlement anchor (deferred to ABAC P6+, stated, never counted); mandate-comparison triggers as recorded on the row.

## Part 2 — Proposed slice order

### STRUCT-1 — Exposure grain: `exposure_type` into the key, the NOTIONAL producer, consumer declarations + refusals (PPM-006 complete) — **XL** (re-sized from L; both judges), migration `0071`

- Migration `0071` widens `uq_exposure_aggregate_run_grain` to include `exposure_type` (models.py + migration in lockstep; collision-free — all shipped rows are MARKET_VALUE) and removes the ORM default so an unset type fails NOT NULL rather than mislabeling. P17: exercised against a POPULATED database, not only empty-schema full-PG.
- New pinned component kind `COMPONENT_KIND_INSTRUMENT_TERMS` (FR-row pin, CLASSIFICATION precedent), wired into PURPOSE_EXPOSURE_INPUT builds, so NOTIONAL stays AD-014-pure.
- Second producer in the SAME governed run (DP-2): NOTIONAL = face_value × signed_quantity × FX per the DP-4 failure model. **Producer census defined** (closes V-006-2): a per-measure producer registry in the exposure service (measure → producing callable); the census asserts EXACT SET EQUALITY between registry keys and the distinct `exposure_type` values emitted by an EXECUTED demonstrating run — never an assertion over the `EXPOSURE_TYPES` tuple. The demonstrating bond: terms seeded with face_value, non-par mark, both measures readable from ONE holding id, values differing off par, both from the valuation path.
- **Consumer declarations live in their FINAL home from day one**: `irp_shared/aggregation/contracts.py` (neutral module, NOT under `reproduction/` — PPM-004/008 and read views consume it too; both judges' graft, deletes the fold-in rework). Mechanism (closes V-006-1, the pin-builder inconsistency): each consuming family's PIN BUILDER filters atoms by the family's declared measure by CONSULTING the contract module; the compute's pin PARSER refuses any atom of an undeclared measure as defense-in-depth. **Anti-inert-declaration control** (closes the V-006 exploit): a mutation test flips a family's declared measure in the contract and asserts the built pin set CHANGES and the parser refusal FIRES — the declaration is proven load-bearing, not decorative.
- P9 pre-fold negatives: synthetic NOTIONAL rows (plain String, no DB CHECK — trivially insertable before the producer exists). PLUS real-row positive controls (risk-first graft): each consumer refusal re-fired against an actually produced NOTIONAL row within this slice's battery.
- Reproduction adapter `_EXPOSURE_KEY` + stored-row ORDER BY gain `exposure_type`. `/exposure` reads gain a type filter (latest/list no longer return silently mixed sums); OpenAPI regen through gen-api-check.
- **Rule 7 screen** (demonstrable-first graft): a Holding view showing NOTIONAL and MARKET_VALUE side by side for one holding id, plus a measure column/filter on the exposure grid.

### STRUCT-2 — Aggregation contracts + two censuses (PPM-007 complete, PPM-009 census + rename guard) — **L**, no migration

- The contract module (already homed in STRUCT-1) gains per family: emitted grain + aggregation operator at DP-5's granularity. Census 1: exact set equality against the run-type registry under DP-13's universe. Subset checks forbidden (RPT-3).
- **Census 2 discovery is mechanical, not marker-only and never a hand list** (closes V-007-1): a committed sweep script discovers aggregation constructs themselves (`func.sum`/`sum(`/`SUM(` over governed result rows, repo-wide) and re-derives the site inventory at test time; every discovered site must contain the contract lookup; a site without one FAILS. **Result-obedience control** (closes the V-007 exploit): a mutation test flips a family's operator to NOT_AGGREGATABLE in the contract and asserts the site's behavior changes (refusal fires) — presence of the lookup is not enough, its RESULT must govern.
- NOT-AGGREGATABLE refusal fired THROUGH HTTP via a summed-read param on family reads, subjects per DP-6. IRR stays the documented canonical example (no producer exists — not the fired subject).
- **Mixed-measure refusal has a NAMED firing test** (closes V-007-2): two atoms of different measures presented at the aggregation boundary → refusal fires; plus the HTTP summed read across measures refused. Never a silent conversion.
- Negative control: a contract permitting every operator on every family FAILS the census.
- PPM-009: repo-wide mechanical name-read census (closes V-009-1 — discovery, not just classification): sweep the whole `packages` + `apps` tree, handle the dynamic `getattr` read by enumerating `_AMENDABLE` explicitly, classify under DP-8's three-way taxonomy, pin the allowlist by exact set equality — a NEW name read anywhere fails the census. Rename regression test per DP-8's output definition.

### STRUCT-3 — Versioned hierarchy + node-scoped rollup (PPM-001 clauses 1-2, PPM-008 complete) — **XL**, migration `0072`

- Hierarchy versioning per DP-1 (recommended: append-only history table beside the mutable EV head — a NEW governed entity). **Re-planning clause** (judge graft): if the owner ratifies EV→FR conversion instead, STRUCT-3 is re-sized and re-planned before any code.
- Snapshot pin extended to the FULL scope subtree including position-less grouping nodes; the run's stored tree view is authoritative at its as-of. Test re-parents a MIDDLE grouping node between run and read — the run's stored view must not change (leaf-only re-parent explicitly insufficient).
- Node-scoped runs per DP-7; **the stamped node id is VALIDATED against the pinned subtree** (closes the V-008 exploit — a verbatim-stamped arbitrary id would pass "distinguishable from run rows alone" while breaking the scope label).
- Rollup per DP-9 (recommended: read-time composition consulting the STRUCT-2 contract; additive only by contract, not by hand). Rollup identity on a tree ≥3 levels, TWO node types (FUND → STRATEGY → ACCOUNTs), built in DEMO data, not only fixtures (judge graft): top == sum(level below) == sum(level below that), per exposure_type; middle-node insertion changes no contract-declared-additive total. Shallow trees run normally — minimum depth is a property of the TEST, never a data rule.
- Empty-subtree and positions-without-marks semantics per DP-10, each pinned by its own test so neither branch can regress to a silent zero (risk-first graft).
- **Clause-7 census is EXECUTION evidence, not declaration** (closes V-008-1): every family in the run-type registry is EXECUTED at a non-root node in the battery (or refuses with its contract-declared reason); a `requires_portfolio_scope`-style registry check is explicitly insufficient — that is the RPT-3/LQ-1 declaration-without-firing class.
- **Rule 7 screen**: the Portfolio Structure tree screen with an as-of toggle — the portfolio entity's first read surface.

### STRUCT-4 — Reporting currency + governed FX translation made visible (PPM-010 complete) — **L**, migration `0073` (conditional on DP-11)

- Per-node reporting currency per DP-11; silent USD default removed. Snapshot FX-completeness redefined against the set of node reporting currencies in scope.
- Demo/test book: THREE currencies, one triangulated pair, at least one node reporting in a currency its holdings are not held in. Translated-leg count asserted > 0 BEFORE any translated-leg assertion (P18 clause 1).
- **The governed read executes AT the foreign-reporting node and the oracle pins THAT node's total** (closes V-010-1 and its exploit): the by-hand oracle is a HAND-DERIVED LITERAL CONSTANT in the test (worked in the test-spec doc), never test code replaying the shipped formula; a root-scoped USD run satisfying the leg-count and refusal clauses is explicitly NOT acceptance. The `base_currency` override conflicting with a node's declaration on a node-scoped read is refused.
- Triangulation recorded per DP-12; conversion-path drill-in screen on RunDetail (rate, legs, pivot, per-tenant fx_rate_id provenance) — the read-endpoint-without-screen gap this row exists to close.
- Missing-rate refusal fired. Old-snapshot-under-new-declaration test REQUIRED (risk-first graft): a read over a pre-PPM-010 snapshot lacking node-currency legs surfaces missing-fx honestly — never refuses retroactively, never fabricates. Same-currency no-op guard kept as a regression guard, targeted at `compose_effective_rate`'s identity path — the path the family actually executes.
- Rule 6(a) citation section per DP-14.

## Part 3 — Wave-level decision ledger (Tier-3 — ratify at this gate)

| # | Decision | Recommendation |
|---|---|---|
| DP-1 | PPM-001 versioning mechanism: (a) convert portfolio EV→FR bitemporal; (b) append-only history table beside the mutable head; (c) snapshot-pin-as-authority only | **(b) + the full-subtree pin from (c)**. (a) breaks UNIQUE(tenant_id,code) and the deliberate EV design; (c) alone gives no tree-as-of outside a run. New governed entity → owner sign-off regardless |
| DP-2 | PPM-006 run shape: both measures in ONE run under the widened key, or one run per measure | **One run**. The row's text points there; per-measure runs leave the key widening untested and double the surface |
| DP-3 | New snapshot component kind pinning InstrumentTerms | **Yes** — AD-014 forbids live reads; no other lawful path. FR-row pin, CLASSIFICATION precedent. Extends the snapshot grain → sign-off |
| DP-4 | NOTIONAL failure model | **Skip when face_value is absent by nature; fail-closed gap when asset_class is BOND and face_value is null; convert via denomination_currency** |
| DP-5 | PPM-007 contract granularity | **Per-field** (family → {field: operator}) — one operator per family is provably wrong for CONCENTRATION/LIQUIDITY's mixed amounts + ratios |
| DP-6 | Fired NOT-AGGREGATABLE HTTP subject | **Both SHARPE and VAR** — a summed VaR is the request desks actually make (draft-B rationale); IRR stays the documented example |
| DP-7 | Consume-path NULL `scope_portfolio_id` | **Require an explicit node; refuse otherwise.** No schema change to the IA header; the shipped path fails PPM-008's node-id clause silently today |
| DP-8 | PPM-009 census taxonomy + rename-output definition | **Three-way taxonomy** (display / provenance-capture / computation; only computation forbidden; provenance sites pinned by exact set equality). Rename test compares computed VALUES, excluding snapshot content hashes — byte-identical snapshots after a rename would fail BY DESIGN (TR-09 amend detection) |
| DP-9 | PPM-008 rollup form | **Read-time composition; parent-scoped runs stay the governed number.** Persisted parent rows mint a new grain and risk re-rounding that breaks the to-the-last-decimal identity |
| DP-10 | Empty-subtree vs positions-without-marks semantics (hidden in the draft; surfaced per judge 2) | **Empty subtree = refusal at run submission** (the row: "REFUSES rather than returning zero"). **Positions present but marks missing = committed FAILED run via the shipped gap mechanism** (fail-closed, auditable) |
| DP-11 | Reporting-currency declaration | **Keep `portfolio.base_currency_code`, backfill, remove the silent USD default; undeclared node inherits its parent; undeclared ROOT refuses** |
| DP-12 | Pivot recording | **State the pivot in NEW rows' fx_legs + derive at read time for shipped rows.** Never rewrite shipped pinned bytes — reproduction hashes are load-bearing |
| DP-13 | PPM-007 census universe (surfaced per verifier V-007-3) | **Registry minus an explicit named RUN_TYPE_REPRODUCTION exclusion**, mirroring the shipped reproduction-census precedent — ratified here, not assumed |
| DP-14 | Rule 6(a) for PPM-010's FX conventions | **Yes, narrow scope** — triangulation pivot, reciprocal legs, minor-unit rounding enter the record as verbatim-quoted citations with the citation lane in the verifier pass (CAL-1/CON-1 precedent) |

## Part 4 — Standing-rule application map

- **P9**: every refusal minted this wave (measure refusal, mixed-measure refusal, NOT-AGGREGATABLE HTTP refusal, empty-subtree refusal, missing-rate refusal, undeclared-root refusal) is named in a test that makes it FIRE; negative controls executed against pre-fold code.
- **P15**: the implementation reviews use a different-assumptions proof per slice (fresh-context or different-engine); this record's own verification was 5 refute-by-default verifiers over an independently drafted plan.
- **P17**: migration `0071` (unique-key widen on a shipped IA table) exercised against a populated DB, not only empty-schema full-PG.
- **P18**: every negative control ships its positive control (translated-leg count > 0 before translated-leg assertions is the named instance); all cited harnesses committed.
- **P19**: every deferral in Part 1 names its trigger; the G4 first-close obligation is recorded in Part 5 so it is not homeless.
- **P20**: scope rows adjudication-current at entry (verified, Part 0 header); T2 lapse rule standing during the wave.
- **Rule 7 / UI-as-core**: STRUCT-1 ships the Holding view; STRUCT-3 ships the Portfolio Structure tree screen; STRUCT-4 ships the conversion-path drill-in. No governed number ships endpoint-only.

## Part 5 — Pre-emption ledger (what the Wave-18 close must carry)

1. **G4 fires for the first time**: the close review carries `## Capability coverage (G4)` naming the leaves newly covered, AND the zero-bindings control is deleted per its own instruction.
2. The ledger-class omission sweep (seven ledgers), verified on main AFTER the last merge.
3. Roadmap rows stamped with merge identities in the FIRST commit of the following slice (the REPRO-2 carry pattern).
4. Deferred triggers from Part 1 re-checked: none should have fired mid-wave; if one did, it is a decision, not a carry.

## Part 6 — Verifier findings ledger (all folded)

| id | Finding | Fold |
|---|---|---|
| V-006-1 | Pin-parse refusal inconsistent with one-run-both-measures (builders pin EVERY atom) | Builder filters by declared measure consulting the contract; parser refuses as defense-in-depth; mutation proves the declaration load-bearing (STRUCT-1) |
| V-006-2 | "Checked against the producers" had no defined mechanism; lazy form = the forbidden vocabulary-list assert | Producer registry + exact set equality against an EXECUTED run's emitted types (STRUCT-1) |
| V-006-3 | FALSE claim: "FR-pin pattern used for FACTOR" — FACTOR is EV-pin; CLASSIFICATION is the FR precedent | Corrected (Part 0.3, DP-3) |
| V-007-1 | Marker-based census only sees sites already consulting; six-module inventory is a hand list | Mechanical construct-discovery sweep, re-derived at test time (STRUCT-2) |
| V-007-2 | Mixed-measure refusal was prose with no named firing test | Named boundary + HTTP firing tests (STRUCT-2) |
| V-007-3 | REPRODUCTION exclusion from the census universe asserted, not ratified | Surfaced as DP-13 |
| V-008-1 | Top-of-tree census satisfiable by the shipped `requires_portfolio_scope` declaration — declaration-without-firing | Execution-evidence census: every family runs at a non-root node (STRUCT-3) |
| V-008-x | Exploit: verbatim-stamped arbitrary node id | Node id validated against the pinned subtree (STRUCT-3) |
| V-009-1 | Classification specified, DISCOVERY of new name reads unspecified | Repo-wide mechanical sweep + `_AMENDABLE` enumeration + exact-set allowlist (STRUCT-2) |
| V-010-1 | No mechanism executed a governed read AT the foreign-reporting node; oracle didn't pin WHICH total | Node-scoped read at that node; hand-derived literal oracle; root-USD run explicitly not acceptance (STRUCT-4) |
| V-010-2 | FALSE claim: guard aimed at `convert()`; the exposure family executes `compose_effective_rate` | Guard re-targeted (STRUCT-4, Part 0.5) |
| J-1/J-2 | Judge defects: declaration re-homing rework; STRUCT-1 undersized; SHARPE chosen without a gate; Rule-7 thinness; hidden DP-10 | Contract module final-home day one; XL; DP-6; screens per slice; DP-10 surfaced |
