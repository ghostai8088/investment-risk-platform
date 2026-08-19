# Wave-18 close review

**Produced 2026-08-17 over merged main `7dcb3a3`** (the wave's four slices: STRUCT-1 PR #220 =
`c0bc90b`, STRUCT-2 PR #223 = `42095d2`, STRUCT-3 PR #225 = `f74d207`, STRUCT-4 PR #227 =
`d465b6b`; each with its current_state stamp PR). The close sweep ran as a ten-lane multi-agent
audit — the seven-ledger omission sweep plus three wave-level lenses — 45 agents, every finding
handed to an independent refute-by-default verifier: **34 confirmed, 1 rejected.**

**On the engine, stated first because it bounds everything below.** This wave was built by
Fable and this close review is ALSO Fable — a fresh-context, adversarially-verified pass, not a
different-engine clearance (the RPT-3/Wave-17 condition applies verbatim: worth running, found
real defects, and not evidence it replaces a different engine).

---

## GATE OUTCOME — user decisions, 2026-08-17 (all three ratified AS RECOMMENDED — "proceed")

| # | Decision | Outcome |
|---|---|---|
| **D1** | Rename-carry residual (P19, planning Part 5 item 5): the RETURN chain was discharged at STRUCT-4 stage 27 (fresh post-rename, values identical); backtest/desmoothing/pacing chains remain, and their fresh inputs live on the SHARED flat demo books where a rename re-run moves pinned goldens. | **RATIFIED 2026-08-17: ACCEPT RECURRENCE** on the strength of the mechanical name census (repo-wide, literal-dynamic keys, exact-set) + five fresh-executed families (STRUCT-2 ×2, stage 26 ×2, stage 27 return chain) — with the standing trigger that any slice touching one of the three chains adds its fresh post-rename re-run in-slice. |
| **D2** | The ratified clause-7 sentence (planning line 52; repeated on the STRUCT-3 roadmap row) claims "every family in the run-type registry is EXECUTED at a non-root node"; main delivers non-root EXECUTION for 4 of 21 families (EXPOSURE_AGGREGATE, FACTOR_EXPOSURE, VAR, PORTFOLIO_RETURN) — the rest are covered by the NODE_SCOPES exact-set declaration census + the mechanical scope-stamp census, which is the declaration-without-firing shape the sentence itself forbids (close finding K21, HIGH). | **RATIFIED 2026-08-17: AMEND the two records** — done in this close commit — to the delivered form as a dated close decision — "declaration exact-set census + executed evidence per NODE-SCOPE CLASS (one representative per class) + the mechanical stamp census" — with the standing trigger that any slice touching a family's chain adds that family's non-root execution. The alternative (extend the batteries to execute all 17 remaining chains below root) is a slice-sized build, not a close fold. |
| **D3** | The ledger-5 sweep annotated three present-tense defect claims in the PPM-006/PPM-010 acceptance cells as of-the-amendment history (the wave made them false). The G2 hash mechanism correctly LAPSED both rows' adjudications — it cannot tell annotation from amendment, by design. | **RATIFIED 2026-08-17: leave lapsed** — the ledger's normal path re-asks at the row's next slice entry, and both rows are Done. (Alternative: re-adjudicate now against the annotated text.) |

---

## 1. WHAT WAVE 18 DELIVERED

Wave 18 gave the platform real portfolio STRUCTURE: more than one exposure measure on a
declared grain, machine-readable aggregation contracts with mechanical censuses, a hierarchy
with its own memory and node-scoped governed reads, and honest multi-currency totals with the
conversion path visible.

**STRUCT-1 (PR #220 = `c0bc90b`) — the exposure grain.** REQ-PPM-006: migration `0071` put
`exposure_type` into the uniqueness key; the NOTIONAL producer landed beside MARKET_VALUE via
the `EXPOSURE_PRODUCERS` registry with an executed-run census (exact set, never the vocabulary
tuple); all four consuming families filter by declaration and REFUSE foreign measures
(mutation-proven); demo stage 25's bond carries both measures off one holding id (250,000 vs
246,350). The DP-4 fail-closed containment predicate found three real data defects the demo
book had carried for waves.

**STRUCT-2 (PR #223 = `42095d2`) — the contracts + the censuses.** REQ-PPM-007/-009: per-field
operator contracts + the machine-readable EMITTED GRAIN in `irp_shared/aggregation/contracts.py`;
census 1 exact-set against the registry (minus the ratified REPRODUCTION exclusion, DP-13);
census 2 discovers aggregation constructs mechanically by AST across three source trees;
NOT-AGGREGATABLE fired over HTTP on SHARPE and VAR; the repo-wide name census under the
three-way taxonomy with the fresh rename guard.

**STRUCT-3 (PR #225 = `f74d207`) — the hierarchy's memory.** REQ-PPM-008 + PPM-001 clauses 1-2:
ENT-076 `portfolio_hierarchy_version` (migration `0072`, IA append-only, backfilled with
source-honesty) — the tree resolves as-of a past timestamp with NO run or snapshot in scope;
exposure snapshots pin the FULL subtree (v2 predicate); consume runs REQUIRE a validated node;
the read-time rollup identity holds per measure to the last decimal across three levels;
`GET /portfolios/tree-as-of` + the Portfolio Structure screen.

**STRUCT-4 (PR #227 = `d465b6b`) — FX made visible.** REQ-PPM-010: the silent USD default is
DEAD on both paths (DP-11 — declarations inherit; an undeclared root REFUSES; migration `0073`
states 'USD' on legacy roots); triangulated legs STATE their pivot on v3-predicate runs and
shipped rows derive it at read time (DP-12, bytes never rewritten); the three-currency book
with hand-derived literal oracles (6,080.000000 USD at the foreign-reporting node; 432.000000
GBP through the two-leg node translation); the conversion-path drill-in on RunDetail; missing-fx
honesty on pre-PPM-010 snapshots; DP-14 verbatim citations in `fx_translation_v1.md`. The
slice review's BLOCKING: an asymmetric refusal would have minted irreproducible runs — the
conflict refusal is now symmetric.

Slice-review totals across the wave: **16 + 20 + 23 + 19 = 78 confirmed findings, every one
folded before its merge.** The batteries: struct-1 9/9, struct-2 8/8, struct-3 4/4, struct-4
11/11 mutants killed.

## 2. THE CLOSE SWEEP — what the ten lanes found and what was repaired

**34 confirmed findings (2 BLOCKING, 7 HIGH), all dispositioned in the close commit:**

- **The registers (BLOCKING ×2, repaired):** all six wave-delivered requirement rows still read
  Draft/In-Progress in BOTH backbone and RTM — the register-status class recurring. Advanced
  with merge identities; PPM-001 stays In-Progress by its own terms (clause 3 = ABAC P6+).
  Three present-tense defect claims inside acceptance cells were annotated as of-the-amendment
  history (→ decision D3).
- **A real re-opened exploit (HIGH, FIXED + mutation-pinned):** the legacy v1-snapshot consume
  branch accepted ANY `scope_node_id` — a nonexistent or foreign-tenant UUID minted a COMPLETED
  run stamped with a scope no one owns (the V-008 shape the planning record declares closed),
  reachable over HTTP, the false label propagating through the SCOPE_INHERITED chain. The stamp
  must now resolve as a tenant-visible portfolio (pre-create refusal; the reproduction
  adapter's replay resolves by construction — positive control in the test; mutant M-W18C-1).
- **A confirmed finding REFUTED by measurement (HIGH → resolved, recorded because the
  resolution is the lesson):** two lanes + their verifiers held that the stamped full-PG figure
  3,499 was "arithmetically unreachable" (whole-repo collection 3,539). Executed at the close:
  the battery's own selection (`packages/shared-python/tests apps/backend/tests`, the form
  every slice has run) collects and passes **3,500 with zero skips** (3,499 at the STRUCT-4
  tree + this close's one added test) — the stamp was CORRECT for the battery as defined, and
  the auditors' number was a DIFFERENT selection: the whole-repo collection adds the ~40
  root-`tests/` gate tests, which run in `make check`, are not PG-gated, and have never been
  part of the full-PG battery. Reading-lane consensus (two lanes + two verifiers) lost to one
  execution — the CON-1 lesson again. The battery's selection is now stated here so the next
  auditor doesn't re-derive it.
- **Control matrix (HIGH + 2 MED, dispositioned in-row):** CTRL-018 gained its Wave-18 EXTENDED
  disposition (three touchpoints to its own machinery) and its FOURTH P16 citation re-take
  (CI run `32056226029` on head `7dcb3a3`); CTRL-009's citation re-taken (STRUCT-3 edited the
  cited harness itself); CTRL-029 records the DP-11 kill as a material exercise. **Mint
  candidate flagged for the Wave-19 planning gate (the DEP-1 precedent): the STRUCT-2
  aggregation-contract enforcement layer has no host control row.**
- **Ledgers 1/2 (HIGH + 3 MED/LOW, repaired):** the ENT-014 registry row still claimed the
  pre-STRUCT-1 grain and "MARKET_VALUE only" (extended, dated); three stale present-tense
  next-free-id footers retired; the ENT-076 row and ORM docstring now name `0073_BACKFILL`;
  the audit taxonomy carries its dated Wave-18 minted-nothing sentence (the ENT-076 fold
  convention recorded); `exposure/models.py`'s own docstring corrected.
- **Ratified-vs-delivered (HIGH ×2 → decisions):** clause-7 execution breadth (→ D2) and the
  G4 wording trap (→ §Capability coverage below, worded accurately).
- **Deferred triggers (Part 5 item 4): NONE FIRED** — verified against the whole wave diff:
  unfunded is not in the exposure grain, instrument terms still cannot express a swap, no
  duration producer landed, PPM-001 clause 3 stays deferred, and nothing on the OUT list was
  silently built.
- **Smaller repairs:** the reproduction registry's docstring no longer asserts the killed USD
  fallback in present tense; the route-census comment's arithmetic is complete again
  (+1 STRUCT-2); `build_snapshot` documents that a true v1 EXPOSURE_INPUT artifact can no
  longer be re-minted; the Portfolio Structure screen now shows each node's DECLARED reporting
  currency (the declaration that governs refusals had no screen); the STRUCT-1/STRUCT-2/STRUCT-4
  roadmap rows carry their merge identities (Part 5 item 3 — the close sweep caught the
  STRUCT-1/2 stamps missed by the following slices' first commits).
- **Recorded, no change:** `fx_translation_v1.md` sits outside the CTRL-002 model-methodology
  census BY DESIGN (the exposure family is model-less; the doc is convention documentation
  under DP-14, not a registered model's methodology). NodeRollup translated totals are a READ
  projection outside the aggregation-contract vocabulary — the contracts govern row-space
  aggregation; the translation is per-node scalar conversion with its own evidence fields
  (noted here so a future consumer does not sum translated totals across nodes without reading
  the contract).

## Capability coverage (G4)

First live run of G4 (the zero-bindings control in `test_capability_coverage.py` is DELETED in
this close's commit, per its own instruction — the gate now has teeth in production). Wording
note, recorded deliberately: all three leaves below were already requirement-COVERED (cited)
before Wave 18 opened — the PPM rows were minted at the 2026-08-12/13 re-baseline. Wave 18's
contribution is DELIVERED SUBSTANCE against those cited leaves, which is what this table
records; no leaf moved out of the uncovered set (that set was and stays the four accepted
baseline gaps).

| Leaf | Taxonomy label (verbatim) | What the wave delivered against it |
|---|---|---|
| 1.1 | Portfolio/Fund/Strategy hierarchy | STRUCT-3: ENT-076 version history + as-of-by-timestamp resolution (PPM-001 cl. 1-2); node-scoped runs + the rollup identity (PPM-008); the name-inertness census + rename guards (PPM-009). |
| 1.4 | Valuation history | STRUCT-4 (via the ratified PPM-010→1.4 binding, re-baseline part 2): reporting-currency declarations, governed FX translation visible (stated/derived pivot, drill-in screen, missing-fx honesty). The valuation-HISTORY half was delivered long before (PPM-003, P1C-4); this row records the wave's FX-visibility substance under the row's own ratified capability binding, not a claim that the wave built valuation history. |
| 1.5 | Exposure aggregation | STRUCT-1: the declared two-measure grain (PPM-006); STRUCT-2: per-field operator contracts + emitted grains + the mechanical censuses (PPM-007). |

## 3. Counts and gates at the close (MEASURED, exit codes captured without pipes)

- `make check` = 0 — **2,909** unit-tier tests (incl. the censuses and the G2/G4/docs gates).
- fe-check = 0; gen-api-check = 0.
- Full-PG battery on fresh reset PG at this close: **exit 0, **3,500** passed (zero skips; `PG_PYTEST_EXIT=0`)** (the corrected ledger number).
- Mutation battery: **130 mutants** (struct-4 11/11 + w18-close 1/1 re-run at this close); anchors **130/130**.
- Route census: **308** (STRUCT-2 +1, STRUCT-3 +2, STRUCT-4 +0 — arithmetic repaired).
- Migrations: **73** files, single head `0073_declare_root_currency`.
- Canonical ids: contiguous through ENT-076; next free **ENT-077**.
- Run-type registry: unchanged at **19 registered + 2 pinned-unregistered = 21** families; the
  aggregation contracts declare exactly 21.
- Demo stages: **27**, each PG suite with its own CI step (test_ci_pg_coverage green).
- G2: no slice in flight (declared emptiness at the wave boundary); G4: this section.
- Verify-on-main: every close-fold artifact is in the close commit itself; the four slice
  merges verified per-conclusion green on their heads and on main (`d465b6b`, `7dcb3a3` — CI
  run `32056226029` all nine green).

## 4. Carries out of Wave 18 (P19 — each names a host or trigger)

1. Rename-residual chains (backtest/desmoothing/pacing) — **decision D1 above.**
2. Clause-7 execution breadth — **decision D2 above** (per-family non-root execution rides the
   next slice that touches each family's chain, if D2 ratifies as recommended).
3. PPM-001 clause 3 (entitlement-anchor ENFORCEMENT) — deferred to ABAC P6+, stated on the row.
4. The Part-1 OUT-list triggers (commitment funded/unfunded pair; swap notional/MV pair;
   duration contract row; mandate-comparison) — none fired; each keeps its named trigger.
5. Control-mint candidates for the Wave-19 planning gate: backup/DR (standing since DEP-1);
   the aggregation-contract enforcement layer (this close, K8).
6. The pin-bounded-resolution asymmetry (a scope root inheriting its currency from above the
   pin reports no declared currency on its own rollup) — documented in `fx_translation_v1.md`
   §4; converts to work only on a user-visible trigger.

## 5. NEXT

The Wave-19 planning gate: sequence the next slices from the roadmap (Part 4 rules), mint or
decline the two control candidates, and re-adjudicate any G2 rows entering scope (PPM-006 and
PPM-010 will re-ask if they re-enter — see D3).
