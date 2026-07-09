# P3-C2 Decision Record — Hardening / Consolidation Slice (Wave-1 slice 3, the follow-up paydown)

| Field | Value |
|---|---|
| Status | **IMPLEMENTED + REVIEWED — HOLDING for Tier-2 commit approval.** OQ-P3-C2-1…6 ratified (2026-07-08); Steps 1–4 built; OD-B scaffold relocation (Part 4.5) + OD-C source-switch (Part 4.6) amendments recorded; FULL 6-finder adversarial review complete (Part 6 — 9 findings, all folded, no deferrals); full validation green post-fold. Commit is a SEPARATE approval (not yet given). |
| Date | 2026-07-08 |
| Basis | `delivery_roadmap.md` Wave 1, slice 3: the four recorded follow-ups accumulated across FE-1 / P3-C1 / P3-5 (the P3-C1 pattern — sweep the deferral register in one consolidation slice). NOT a methodology slice → roadmap Part 4 rule 6 (cited external-benchmark section) does NOT apply (no new math, no new number). |
| Grounding | Verified against shipped HEAD `440f868` (CI #118): `run_exposure` (exposure/service.py) has its OWN hand-rolled lifecycle tail (NOT the P3-C1 `execute_governed_run` scaffold) — it does NOT persist `failure_reason` (line 342 omits it; the returned dataclass carries it but the DB row + GET show None) and records the snapshot→run DEPENDS_ON edge AFTER the DQ gate (line 350 — a FAILED exposure run loses its input-lineage link). `list_risk_runs` fences to `RISK_RUN_TYPES` and REFUSES `EXPOSURE_AGGREGATE`; there is a `GET /exposure/runs/{run_id}` + `GET /exposure/{id}` but NO `GET /exposure/runs` LISTING; `exposure.view` permission exists. `exposure_aggregate`'s four RESULT columns are already `PreciseDecimal` (P3-C1); the captured-INPUT tables still carry plain `Numeric`. `ensure_presence_rule` (dq/gates.py) is SELECT-then-INSERT with no savepoint; `data_quality_rule` has `uq_data_quality_rule_tenant_code`. `PreciseDecimal` renders `NUMERIC(precision, scale)` on PG (db/types.py:58) — DDL-identical, NO migration. |
| Sign-off | **OQ-P3-C2-1…6 — APPROVED / RATIFIED by the user (2026-07-08: "Proceed" on the full package, all six as recommended, incl. keeping the exposure-listing item in this slice).** |

---

## Part 1 — Decisions at a glance

| ID | Topic | Decision |
|---|---|---|
| **OD-P3-C2-A** | slice character | A **hardening/consolidation slice**: NO new governed number, NO new entity/canonical id, NO new permission, NO new audit code, **NO migration** (all four items are type-only, refactor, additive-read, or concurrency-logic). Three items are behavior-preserving OR explicit tested TIGHTENINGS; the exposure-listing item is a small additive read surface. |
| **OD-P3-C2-B** | exposure scaffold + `failure_reason` adoption | Refactor `run_exposure` onto the P3-C1 `execute_governed_run` scaffold (the "exposure's fifth variant" recorded follow-up). The scaffold accepts `model_version_id=None` (exposure is model-less); the compute closure wraps `_read_components` + `_build_rows`; the reason format is preserved VERBATIM (`format_reason=lambda gate, gaps: str(gate)` — the P3-1 bare format exposure already uses). TWO **intended** behavior improvements come with adoption (NOT preserved — this is the point): (1) `failure_reason` is now PERSISTED on FAILED exposure runs (`update_run_status(failure_reason=…)`; the `GET /exposure/runs/{id}` endpoint surfaces it instead of the hardcoded None); (2) the snapshot→run DEPENDS_ON edge is recorded BEFORE the DQ gate, so a committed FAILED exposure run keeps its input-lineage link (the P3-1 lineage fold, now extended to the exposure family). Everything ELSE (audit-event sequence, ORIGIN edges, COMPLETED-path rows, pre-create refusals) is byte-preserved — proven by a golden capture written green PRE-refactor (the P3-C1 R0 method). |
| **OD-P3-C2-C** | exposure runs in the FE listing | A NEW read-only `list_exposure_runs` (a sibling of `list_risk_runs` in `irp_shared/exposure/queries.py`, fenced to `EXPOSURE_AGGREGATE` ONLY — the mirror fence) + `GET /exposure/runs` gated `exposure.view` (fail-closed filters; `created_at DESC, run_id`; items-only — the `GET /risk/runs` shape). The FE-1 runs view gains exposure as a FIFTH listed family: it queries `/exposure/runs` IN ADDITION to `/risk/runs` and merges, and the run-detail route gains an `exposure` family (model-less; `exposure_type=MARKET_VALUE` result rows). A session without `exposure.view` simply gets a 403 on that fetch, rendered as the honest not-entitled state — the risk listing is unaffected (the permission-family separation the FE-1 review insisted on is preserved: `risk.view` NEVER surfaces exposure runs). |
| **OD-P3-C2-D** | captured-input `PreciseDecimal` parity | Convert every captured-input decimal column whose declared precision is float53-UNSAFE (≥ 16 significant digits — the EXACT criterion P3-C1 OD-E applied to the result columns, applied consistently) to `PreciseDecimal`: `position.quantity(28,8)` + `.cost_basis(20,6)`; `valuation.mark_value(20,6)`; `fx_rate.rate(28,12)`; `price_point.price(20,6)`; `curve_point.point_value(20,12)`; `benchmark_constituent.weight(20,12)`; `factor_return.return_value(20,12)`; `instrument_terms.face_value(20,4)`; `corporate_action.ratio(18,8)` + `.amount(20,6)`; **and (review fold) `transaction.quantity(28,8)` + `.price(20,6)` + `.gross_amount(20,6)`** — the P3-C2 review (Finder C/F) found the `transaction` captured/inert decimals were the one remaining ≥16-precision captured table left plain; converting them makes the criterion TRULY mechanical (a repo-wide `grep` confirms these three were the only ≥16 plain `Numeric` columns remaining). `instrument_terms.coupon_rate(12,6)` STAYS plain `Numeric` (12 digits — float53-safe by contract); `bump_bps(10,4)`/`confidence_level(6,4)` likewise (<16). PG DDL is IDENTICAL (`NUMERIC(p,s)`); SQLite/test gains exact fixed-scale TEXT — **NO migration**. This closes the latent SQLite-vs-PG precision divergence on the captured governed data (the criterion is now the invariant "every captured decimal column with precision ≥16 is `PreciseDecimal`", enforced by `test_p3c2_precision_parity._CONVERTED` — 14 columns). |
| **OD-P3-C2-E** | DQ-rule first-registration race | `ensure_presence_rule` (SELECT-then-INSERT) races: two concurrent first governed runs of a tenant both SELECT-miss then both INSERT the same `(tenant_id, code)` → one hits `uq_data_quality_rule_tenant_code` → an IntegrityError that ABORTS the whole co-transactional run (a 500 + rollback). Fix: wrap the `register_dq_rule` INSERT in a `session.begin_nested()` SAVEPOINT; on IntegrityError roll back to the savepoint (NOT the whole transaction) and re-SELECT the now-committed peer rule. The "small deliberate behavior change" the P3-C1 review recorded (500-on-race → clean resolve). The audit event `register_dq_rule` emits is inside the savepoint and unwinds with it on the losing branch — verified in review that no dangling audit row survives. |
| **OD-P3-C2-F** | proportionate review | A FULL **6-finder** adversarial review: the slice touches the governed run lifecycle (exposure), a type change across NINE captured tables, a concurrency fix in a shared DQ helper, and a frontend surface — breadth warrants the full review, not a reduced one. Validation gates unreduced (make check + full-PG + downgrade smoke + the frontend suite). |

## Part 2 — Rationale highlights

### OD-P3-C2-B — why adopt the scaffold now (and what changes)
P3-C1 extracted the scaffold from the four RISK binders and explicitly LEFT exposure out ("its model-less shape
differs; not forced into this mold"). Recon confirms the shape fits: the scaffold's `model_version_id: str | None`
and `compute(run)` callback accommodate exposure's model-less, run-first build cleanly. Adopting it deletes
exposure's ~30-line hand-rolled tail (the last copy of the lifecycle the scaffold owns) AND brings exposure to
parity with the risk families on the two governance behaviors it was silently missing — persisted failure reasons
and FAILED-run input lineage. Both are strict improvements a FAILED exposure run should already have had.

### OD-P3-C2-D — why the ≥16-digit criterion and why no migration
The float53 safe-integer boundary is 2^53 ≈ 9.0e15 (≈ 15–16 significant digits). Any `Numeric(p,s)` with p ≥ 16
can hold a value SQLite's `Numeric` roundtrip (through binary float) corrupts at the 17th digit — the exact bug
`PreciseDecimal` exists to prevent, and the exact criterion P3-C1 used for the result columns. Applying it
mechanically (not per-column judgement) gives a defensible, drift-proof scope. These captured columns are pinned
verbatim into `dataset_snapshot` components and drive reproducible governed numbers, so a test-engine precision
divergence is a latent correctness gap even though PG (production) is already exact. `PreciseDecimal` is
type-decorator-only: `NUMERIC(p,s)` on PG is byte-identical to today, so `alembic check` stays a no-op.

## Part 3 — Out of scope (recorded)
The DQ-rule race fix is the ONLY concurrency change (the analogous model-registrar resolve-or-register races are a
separate recorded item — NOT pulled in here unless review shows the same helper); NO new governed number/entity/
permission/audit code; NO migration; NO methodology (rule 6 N/A); NO exposure-model introduction (exposure stays
model-less); the captured tables' NON-decimal columns and `coupon_rate(12,6)` are untouched; no frontend change
beyond surfacing the exposure family in the existing runs view.

## Part 4 — Open decisions (OQ-P3-C2-1…6) — **APPROVED / RATIFIED by the user (2026-07-08, the plan-commit gate)**
**Status: RATIFIED.** The six defaults below are fixed inputs to the P3-C2 implementation.
- **OQ-P3-C2-1 — recommend APPROVE.** The slice scope = the four recorded follow-ups; no migration; no new number/entity/permission/audit code. (OD-A.)
- **OQ-P3-C2-2 — recommend APPROVE.** The exposure scaffold adoption with its two intended behavior improvements (persisted `failure_reason`; DEPENDS_ON-before-gate), else golden-capture behavior-preserving; the exposure GET surfaces `failure_reason`. (OD-B.)
- **OQ-P3-C2-3 — recommend APPROVE.** Exposure runs in the FE listing via a new `exposure.view`-gated `GET /exposure/runs` + the FE view merging it as a fifth family (the permission-family separation preserved). *(This is the largest sub-item; the alternative is to defer just this to its own slice — but the roadmap placed it here and it completes the FE-1 view honestly.)* (OD-C.)
- **OQ-P3-C2-4 — recommend APPROVE.** `PreciseDecimal` parity for every captured-input decimal column with precision ≥ 16 (the P3-C1 criterion, applied consistently); `coupon_rate(12,6)` stays plain; NO migration. (OD-D.)
- **OQ-P3-C2-5 — recommend APPROVE.** The savepoint-based resolve-or-register fix for the DQ-rule first-registration race. (OD-E.)
- **OQ-P3-C2-6 — recommend APPROVE.** The full 6-finder review + unreduced validation gates. (OD-F.)

## Part 4.5 — OD-B amendment (recorded at implementation, user-approved 2026-07-08)

**Scaffold RELOCATED, not imported across the layering fence.** OD-B assumed adopting the shared
scaffold in `run_exposure` was a local refactor. Implementation surfaced a ratified, TESTED
invariant — `test_scope_fence_no_risk_imports_or_identifiers` forbids `exposure` importing
`risk` (the layering is one-way: risk consumes exposure, never the reverse). Since the scaffold
lived under `risk`, exposure could not adopt it without breaking that boundary. The user was
brought the decision (relocate-and-adopt vs. improve-exposure-in-place) and chose **relocate**
(the best answer for the larger plan). Executed: `git mv risk/scaffold.py → calc/scaffold.py` (a
neutral home below both risk and exposure — a generic governed-run lifecycle is not
risk-specific; cycle-safe: `dq`/`lineage` do not import `calc`); the FIVE risk binders +
`exposure` now import `from irp_shared.calc.scaffold`; the P3-C1 golden suite is unaffected (it
tests the binders' public behavior, not the module path). This makes the layering permanently
clean rather than papering over it with a function-local import.

## Part 4.6 — OD-C amendment (recorded at implementation, review-confirmed 2026-07-08)

**FE listing SOURCE-SWITCHES; it does NOT client-merge.** OD-C's prose (and plan step 7) said the
FE "queries `/exposure/runs` IN ADDITION to `/risk/runs` and MERGES." Implementation instead makes
the family selector pick the ENDPOINT (Exposure → `/exposure/runs`; the four risk families and the
"All risk families" default → `/risk/runs`). A client-side merge of two independently-paginated
endpoints would recreate the exact FE-1 `has-more` pagination trap the FE-1 review fixed (a merged
page cannot compute a correct server-side `has-more`), so the source-switch is the sound choice —
server-side pagination stays correct per source. Accepted trade-offs, recorded: (1) the default
"All risk families" view lists the four risk families only — exposure is reached by selecting the
Exposure family (consistent with the permission-family separation: `risk.view` never surfaces
exposure); an `exposure.view`-only identity lands on a 403 on the default view until it selects
Exposure. (2) The list heading was changed from "Risk runs" to the family-neutral "Runs" (the copy
elsewhere was already made family-neutral). Backend row contract is byte-identical across the two
endpoints (`ExposureRunSummaryOut` now carries `model_version_id: str | None` — always None for the
model-less family — so the shared FE `RiskRunSummary` type is satisfied for BOTH sources; review
Finder A).

## Part 5 — P3-C2 implementation readiness gate
Implementation-ready once OQ-P3-C2-1…6 are ratified. Build contract = `p3_c2_implementation_plan.md`.
**P3-C2 planning implements nothing.**

## Part 6 — Adversarial review log (2026-07-08, FULL 6-finder per OD-F)

Six independent finders ran against the staged change set (line-scan, governance/tenancy/layering,
cross-file tracer, concurrency+precision, test-quality, plan/record conformance). **Finders B and D
returned clean** (all house invariants and every FE↔backend / scaffold-relocation seam verified
against code, no defects). Nine actionable findings across A/C/E/F — **all folded** (no deferrals);
all are additive hardening, DDL-neutral, and consistent with the ratified scope (they tighten the
same criteria OD-D/OD-C already committed to). Full validation re-run green after folding.

| # | Finder | Finding | Disposition |
|---|---|---|---|
| A | line-scan | `ExposureRunSummaryOut` omitted `model_version_id` while the shared FE `RiskRunSummary` type (parsing BOTH endpoints) declares it required — latent contract mismatch (harmless today; never rendered). | **FOLDED** — added `model_version_id: str \| None` (always None; model-less family), populated from `r.model_version_id`, byte-for-byte with the risk sibling. |
| C/F1 | precision / conformance | `transaction.quantity(28,8)`/`.price(20,6)`/`.gross_amount(20,6)` — captured/inert decimals with precision ≥16 — were the one remaining ≥16 table left plain `Numeric`, contradicting OD-D's "mechanical, not per-column" criterion. | **FOLDED** — converted to `PreciseDecimal` (a repo-wide `grep` confirmed these were the ONLY ≥16 plain `Numeric` columns left); added to `test_p3c2_precision_parity._CONVERTED` (14 cols); OD-D text updated. DDL-identical on PG; no migration. |
| E1 | test-quality | The exposure scaffold test claimed COMPLETED-path "audit sequence" preservation but asserted only edge/row counts — not the ordered `CALC.*` sequence or the DQ-rule identity the P3-C1 golden pins for the risk binders. | **FOLDED** — added the ordered `_COMPLETED_SEQUENCE`/`_FAILED_SEQUENCE` assertions and a DQ-rule identity check (code/name/target verbatim) to `test_p3c2_exposure_scaffold.py`, matching the golden bar. |
| E2/E3 | test-quality | No PG coverage for `list_exposure_runs` (RLS isolation, the EXPOSURE_AGGREGATE fence, the `created_at DESC, run_id` tie-break — never exercised since SQLite rows had distinct timestamps) nor for FAILED `failure_reason` persistence on PG — diverging from the risk sibling's `test_risk_runs_pg.py` house pattern. | **FOLDED** — new `test_exposure_runs_pg.py` (mirrors `test_risk_runs_pg.py`): FORCE-RLS tenant isolation + no-context-zero-rows, the fence (a VAR run never appears), the equal-`created_at` tie-break, FAILED `failure_reason` round-trip under the NOBYPASSRLS `irp_app` role, and the fail-closed status refusal. |
| F2 | conformance | Plan step 9 said "ten columns"; OD-D named eleven (position/corporate_action each have two). | **FOLDED** — plan corrected to eleven + three `transaction` = fourteen. |
| F3 | conformance | FE uses a SOURCE-SWITCH, not the record's "merges" wording — an unrecorded (sound) deviation. | **FOLDED** — recorded as Part 4.6; the stale "merge" comment in `exposure/queries.py` was corrected. |
| F4 | conformance | The "All risk families" default excludes exposure; an `exposure.view`-only identity lands on a 403 by default. | **FOLDED (recorded)** — accepted trade-off documented in Part 4.6 (consistent with the permission-family separation). |
| F5 | conformance | List header hard-coded "Risk runs" while the view now also renders exposure. | **FOLDED** — heading changed to the family-neutral "Runs"; `App.test.tsx` negative assertion re-anchored by role. |
| F6 | conformance | `docs/project_memory/current_state.md` still carries a LIVE `risk/scaffold.py::execute_governed_run` pointer (the scaffold was git-mv'd to `calc/scaffold.py`). Other doc hits are P3-C1 history (correctly left). | **CLOSEOUT OBLIGATION** (not a blocker for this staged set) — update the live pointer to `calc/scaffold.py` at P3-C2 closeout. |
