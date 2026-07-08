# P3-C2 Decision Record — Hardening / Consolidation Slice (Wave-1 slice 3, the follow-up paydown)

| Field | Value |
|---|---|
| Status | **PLANNING RATIFIED** — OQ-P3-C2-1…6 approved by the user at the commit gate (2026-07-08, after a plain-language decision briefing); implementation is a SEPARATE approval |
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
| **OD-P3-C2-D** | captured-input `PreciseDecimal` parity | Convert every captured-input decimal column whose declared precision is float53-UNSAFE (≥ 16 significant digits — the EXACT criterion P3-C1 OD-E applied to the result columns, applied consistently) to `PreciseDecimal`: `position.quantity(28,8)` + `.cost_basis(20,6)`; `valuation.mark_value(20,6)`; `fx_rate.rate(28,12)`; `price_point.price(20,6)`; `curve_point.point_value(20,12)`; `benchmark_constituent.weight(20,12)`; `factor_return.return_value(20,12)`; `instrument_terms.face_value(20,4)`; `corporate_action.ratio(18,8)` + `.amount(20,6)`. `instrument_terms.coupon_rate(12,6)` STAYS plain `Numeric` (12 digits — float53-safe by contract). PG DDL is IDENTICAL (`NUMERIC(p,s)`); SQLite/test gains exact fixed-scale TEXT — **NO migration**. This closes the latent SQLite-vs-PG precision divergence on the captured governed data these snapshots pin. |
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

## Part 5 — P3-C2 implementation readiness gate
Implementation-ready once OQ-P3-C2-1…6 are ratified. Build contract = `p3_c2_implementation_plan.md`.
**P3-C2 planning implements nothing.**
