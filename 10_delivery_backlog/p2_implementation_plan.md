# P2 Implementation Plan — Reproducibility-First Market Data, Snapshots & the First Governed Compute

## Document Control

| Field | Value |
|---|---|
| Purpose | The P2 build plan: a **reproducibility-first** subphase structure (P2-1…P2-6) that lands the `dataset_snapshot` primitive + `calculation_run` wiring **before** any official derived number, then the supporting market-data foundation. Companion to `p2_0_decision_record.md` (OD-P2-A…L). |
| Status | **Implementation PLAN — PLANNING ONLY; NO code, NO migrations, NO P2 implementation.** |
| HEAD at writing | `7070dff`; origin/main clean. |
| Predecessors | `p2_0_decision_record.md`; `p1c_closeout_p2_readiness.md`; the P1C per-slice plans. |
| Review | 8-lens UltraCode review — see `p2_0_decision_record.md` Part 5 (covers both artifacts; in-scope findings folded into both). |

> **Reproducibility-first principle.** P2 builds the **reproducibility primitive (`dataset_snapshot`)** and the **run binding (`calculation_run`)** first, so the **first official derived number (basic exposure)** can only exist **bound to a snapshot + a run** (AD-014 + FW-RUN §5/TR-15). Market data is **captured/ingested, FR, never modeled**; the **only governed compute in P2 is the snapshot-bound, run-tracked exposure rollup over captured marks**. No factor/risk/pricing/valuation models; no VaR/ES; no P3+ analytics. Rails reuse is additive: new generic DQ evaluators + **two caller-side DQ gates**, a **new internal lineage writer** (the shipped `record_lineage` is data_source-only), and an additive `calculation_run.environment_id` column — plus the AD-004 repo interface (OD-014 → Postgres-first, **pending ratification**).

---

## Part 1 — Subphase map

| Subphase | Deliverable | Entities (canonical) | Temporal | Gate |
|---|---|---|---|---|
| **P2-1** | `dataset_snapshot` reproducible input snapshot | `dataset_snapshot` + `dataset_snapshot_component` (new canonical ids) | **IA, true append-only** (in `APPEND_ONLY_TABLES`) | the reproducibility primitive (AD-014) |
| **P2-2** | FX rates + currency conversion (published-rate lookup + ratified base-triangulation) | `fx_rate` (ENT-024) | **FR** | the one market input exposure needs |
| **P2-3** | `calculation_run` wiring + basic exposure | `calculation_run` (ENT-026, wired + `environment_id` add) + `exposure_aggregate` (ENT-014, in `APPEND_ONLY_TABLES`) | run = IA status-mutable; result = IA append-only | **the FIRST governed compute** (snapshot+run gated) |
| **P2-4** | Market price history | `price_point` (ENT-020) | **FR** | P3 factor-model on-ramp (off the exposure critical path) |
| **P2-5** | Yield curves / credit spreads | `yield_curve` (ENT-021), `credit_spread` (ENT-023) | **FR** | P3 on-ramp |
| **P2-6** | Benchmark / index — **DELIVERED (migration `0021`)** | `benchmark` (ENT-009, EV definition) + `benchmark_constituent` (ENT-009, FR membership) | EV + FR | **conditionality RESOLVED — P3 dependency CONFIRMED (OD-P2-6-O); levels/returns deferred** |

---

## Part 2 — Subphase definitions (14-field template)

### P2-1 — `dataset_snapshot` / reproducible input snapshot
1. **Requirements included** — the AD-014 snapshot primitive (REQ-PPM-004 prerequisite); TR-09 version-pinning; an immutable reproducible input bind for downstream runs.
2. **Requirements excluded** — any calc that consumes the snapshot (P2-3); market-data binding beyond optional refs; exposure/risk.
3. **Proposed entities/modules** — `dataset_snapshot` (header) + `dataset_snapshot_component` (per-input pin) — **new canonical ENT ids** (Part 3); new `irp_shared/snapshot/` package; a `build_snapshot` binder resolving inputs via `reconstruct_*_as_of` and **pinning the FR physical-version tuple `(surrogate_id, valid_from, system_from)` + the captured value/`content_hash`** (FR prior-version immutability is service-enforced, not trigger-enforced, so the pin captures the value, not just a row pointer); hashes computed in **application code over a fixed canonical serialization** (engine-independent across the AD-011 SQLite/PG split).
4. **Temporal classification** — **IA, TRUE append-only** (both tables in `APPEND_ONLY_TABLES` → P0001 trigger + ORM guard — the TRANSACTION exemplar, **not** the status-mutable calculation_run pattern).
5. **APIs** — `POST /snapshots` (bind the as-of input set) + `GET /snapshots/{id}` + `GET /snapshots/{id}/verify` (re-resolve + hash-check). No mutate/delete.
6. **Audit events** — **reserve `SNAPSHOT.CREATE`** (proposed R-07) caller-side to the FROZEN `record_event`.
7. **Entitlement checks** — mint `snapshot.view`/`snapshot.create` (deny-by-default); maker = **`data_steward`**; risk tiers view; `auditor_3l` excluded; parity-tested.
8. **RLS behavior** — symmetric tenant-scoped (ENABLE+FORCE); **closed hybrid set asserted unchanged**; no BYPASSRLS. **Cross-tenant binding integrity (load-bearing):** the binder resolves **every** component target ONLY through the acting tenant's RLS-scoped session (never BYPASSRLS, never a caller-supplied raw id); a proprietary target resolving to 0 rows under tenant T **fails closed, writes no snapshot**; `verify` runs under the same tenant context. REFERENCE/hybrid components MAY pin a SYSTEM_TENANT row (the AD-013-R1 USING arm); proprietary components (POSITION/VALUATION/FX/PRICE/CURVE) pin **own-tenant versions only**.
9. **Lineage behavior** — snapshot → component → input version edges. **Requires a NEW internal lineage writer** (the shipped `record_lineage` is data_source-only); the writer RLS-stamps `tenant_id` from the RLS-resolved snapshot, never caller input. `lineage_edge` needs no migration; source_type token = `data_snapshot` (update the `lineage/models.py` comment here).
10. **Data quality behavior** — bound-set **completeness = expected-vs-actual coverage** (every bound position/instrument has its required inputs as-of); the binder materializes the `expected_keys` universe and runs it as a **caller-side gate** through `run_quality_check` (the `(params, dataset)` Protocol is untouched); fail-closed via the no-silent-failure gate; reuse `DATA.VALIDATE`.
11. **Tests** — binds + reads + `verify`; **immutable (P0001 trigger + ORM guard)**; **RLS isolation** (other tenant + no-context → 0 rows); **cross-tenant binding-integrity negative** (a foreign proprietary target → fail-closed, no snapshot); **temporal-reproducibility mutation test** (as-known **correct** a bound valuation (new `system_from`) → re-resolving the SAME snapshot returns the originally-pinned tuple + `content_hash` byte-identical; live `reconstruct_*_as_of` returns the corrected value); negative incomplete-bound-set → fail-closed.
12. **Acceptance criteria** — a snapshot reproducibly resolves the **same pinned versions under later mutation**; `manifest_hash` stable; verify passes; the binding-integrity + completeness gates hold fail-closed.
13. **Risks** — binding scope; hash determinism across DB engines (mitigated by the app-side canonical serialization).
14. **Open questions** — OQ-P2-1 (hash algo + canonical serialization spec).

### P2-2 — FX rates + currency conversion foundation
1. **Requirements included** — the market input a multi-currency exposure rollup needs (convert captured marks to a base); market-data capture (FX) per QS-07/08/09.
2. **Requirements excluded** — model/curve-implied rates; return/vol; any compute beyond published-rate lookup + ratified base-triangulation.
3. **Proposed entities/modules** — `fx_rate` (ENT-024); new `irp_shared/marketdata/` package (`fx.py` + a `convert` helper); reuse P1A-4 generic staging + a **new staging→canonical mapping** step.
4. **Temporal classification** — **FR** (`rate_date` = valid-time; ingest = system-time; vendor restatement = as-known correction).
5. **APIs** — `GET /fx/as-of` + `GET /fx` (range) + `convert(amount, from, to, as_of)`; governed ingest (steward).
6. **Audit events** — reserve `MARKET.FX_INGEST`/`.CORRECT` (proposed R-07); DQ runs reuse `DATA.VALIDATE`.
7. **Entitlement checks** — `marketdata.view`/`marketdata.ingest` (maker = **`data_steward`**; reconcile `marketdata.ingest` vs `data.upload` per Part 3); `auditor_3l` excluded.
8. **RLS behavior** — symmetric tenant-scoped; closed-hybrid-set-unchanged fence; no BYPASSRLS.
9. **Lineage behavior** — register a VENDOR `data_source` (`source_type` e.g. `VENDOR_FX`) → one ORIGIN edge per ingested series version (**reuses `record_lineage` unchanged — no new code**).
10. **Data quality behavior** — positive rate, pair coverage (caller-side gate), staleness (caller-side gate with an `as_of`); fail-closed.
11. **Tests** — as-of + range + `convert` (direct-pair + reciprocal + ratified base-triangulation) + FR supersede/correct/reconstruct; RLS isolation; **scope-fence (vocabulary/import): `convert` uses only published-rate arithmetic — no return/vol/curve-implied/model-derived rates**; DQ-reject.
12. **Acceptance criteria** — convert a captured valuation's currency as-of a date (incl. a triangulated cross-rate via the configured base); FR both-axes reconstruct; vendor lineage rooted.
13. **Risks** — base-currency policy; pair-direction inversion (mitigated by explicit `base/quote` direction, QS-08).
14. **Open questions** — OQ-P2-3 (configurable base set + triangulation pivot rule).

### P2-3 — `calculation_run` wiring + basic exposure foundation  *(the FIRST governed compute)*
1. **Requirements included** — **REQ-PPM-004** (exposure aggregation, promoted In-Progress; keep CTRL-006/018 + FW-RUN + DEP-LIN + CAP-1 satisfied); the FW-RUN §5/TR-15 run bind; AD-014 gate realized.
2. **Requirements excluded** — risk; **VaR/Expected Shortfall**; factor/covariance/vol; **sensitivities/Greeks (ENT-028)**; scenarios; attribution; pricing/valuation models; any P3+ analytic.
3. **Proposed entities/modules** — **wire the shipped `calculation_run` (ENT-026)** + **add an additive `environment_id` column** (FW-RUN item 7); produce `exposure_aggregate` (ENT-014, **in `APPEND_ONLY_TABLES`**); new `irp_shared/exposure/` package (binder runs THROUGH a `calculation_run`); reuse `calc/service.py`.
4. **Temporal classification** — `calculation_run` = **IA but status-mutable** (NOT in `APPEND_ONLY_TABLES`; `update_run_status` projects current status; history lives in the audit chain). `exposure_aggregate` = **IA, derived, run-tracked, TRUE append-only** (in `APPEND_ONLY_TABLES`). **ENT-014 ONLY** (not ENT-028).
5. **APIs** — `POST /exposure/runs` (run over a snapshot, via a run) + `GET /exposure/runs/{id}` + `GET /exposure/{id}`. No mutate.
6. **Audit events** — the run reuses the **shipped `CALC.RUN_CREATE` (create) + `CALC.RUN_STATUS_CHANGE` (per transition; `outcome='failure'` on FAILED)** emitters; `audit/service.py` FROZEN. The taxonomy's `RUN_START/.RUN_COMPLETE/.RUN_FAIL` labels are an R-07 doc-vs-code reconciliation item — **not** newly invented here.
7. **Entitlement checks** — **wire the seeded `exposure.aggregate.run`** (maker/admin) + mint `exposure.view`; `auditor_3l` excluded; parity-tested.
8. **RLS behavior** — symmetric; run + result inherit FORCE-RLS; PG-proven as `irp_app`.
9. **Lineage behavior** — result → `calculation_run` (source_type `calculation_run` and/or `lineage_edge.run_id`) → (`dataset_snapshot` + `code_version`) → inputs (§6, BR-6/BR-13) — via the **new internal lineage writer** (P2-1).
10. **Data quality behavior** — the snapshot **completeness-coverage caller-side gate** (P2-1) is the **fail-closed precondition**; reuse `DATA.VALIDATE`.
11. **Tests** — binds the full **FW-RUN §5/TR-15** set with `code_version` as the anchor (`model_version`/`assumption_set`/`scenario`/`seed` recorded **N/A-with-rationale**); **negative: a run missing ANY required FW-RUN item (null snapshot, missing initiator/timestamps/environment) raises + writes ZERO `exposure_aggregate` AND ZERO orphan `calculation_run` rows** (single tenant-scoped transaction, refusal before any INSERT); **negative: the synthetic seed path imports/writes no `exposure_aggregate`/`calculation_run` model** (OD-P2-L); **scope-fence (VOCABULARY/IMPORT — NOT a no-Mult fence):** the exposure module imports/calls **no** risk/factor/covariance/vol/VaR/ES/scenario symbols and **no** P3 package, while `ast.Mult` is **explicitly permitted** (qty × mark × fx); **positive correctness test:** the rollup equals expected Σ(signed_qty × mark × fx) on a fixture; determinism (same snapshot + code_version ⇒ identical result); RLS.
12. **Acceptance criteria** — a reproducible exposure for a snapshot, **fully run-bound**; **no result exists without a complete TR-15 bind** (non-null snapshot + code_version + the §5 metadata incl. the recorded N/A dispositions).
13. **Risks** — scope creep into risk (mitigated by the vocabulary fence); binding-completeness gaps.
14. **Open questions** — OQ-P2-4 (grouping dimensions).

### P2-4 — Market price history  *(P3 factor-model on-ramp; off the exposure critical path)*
1. **Requirements included** — captured price time-series (the P3 pricing/factor substrate; later mark reconciliation).
2. **Requirements excluded** — **NO `return` entity** (returns derived → ENT-025/P3); no vol/pricing/factor math; corp-action adjustment (a raw-vs-adjusted P2-4 decision).
3. **Proposed entities/modules** — `price_point` (ENT-020); `irp_shared/marketdata/price.py`; staging→canonical mapping.
4. **Temporal classification** — **FR** (§2A).
5. **APIs** — governed ingest + `GET /prices/as-of` + range.
6. **Audit events** — `MARKET.PRICE_INGEST`/`.CORRECT` (proposed R-07).
7. **Entitlement checks** — reuse `marketdata.view`/`.ingest`.
8. **RLS behavior** — symmetric; closed-hybrid-set fence.
9. **Lineage behavior** — vendor `data_source` ORIGIN per series version (reuses `record_lineage`).
10. **Data quality behavior** — non-negative (REGISTRY add), staleness (caller-side gate), gap detection (caller-pre-sorted evaluator).
11. **Tests** — ingest + as-of + RLS + DQ-reject + scope-fence (no return/vol math) + **closed-hybrid-set-unchanged**.
12. **Acceptance criteria** — price history queryable as-of for a range.
13. **Risks** — time-series volume → the OD-014 / AD-004 Timescale threshold; raw-vs-adjusted scope.
14. **Open questions** — OQ-P2-7 (adjusted vs raw); Timescale threshold.

### P2-5 — Yield curves / credit spreads
1. **Requirements included** — captured curve/spread term structures (P3 on-ramp).
2. **Requirements excluded** — bootstrapping, interpolation-as-model, discounting/pricing.
3. **Proposed entities/modules** — `yield_curve` (ENT-021) + `credit_spread` (ENT-023); `irp_shared/marketdata/curve.py`.
4. **Temporal classification** — **FR**.
5. **APIs** — `GET /curves/as-of` (+ spreads).
6. **Audit events** — `MARKET.CURVE_INGEST`/`.CORRECT`.
7. **Entitlement checks** — reuse `marketdata.*`.
8. **RLS behavior** — symmetric; closed-hybrid-set fence.
9. **Lineage behavior** — vendor `data_source` ORIGIN per curve version.
10. **Data quality behavior** — tenor monotonicity (caller-pre-sorted evaluator — a **validation**, must not slide into interpolation-as-model), point coverage (caller-side gate), staleness.
11. **Tests** — as-of + RLS + **scope-fence (no bootstrapping/interpolation-as-model — a named negative test)**.
12. **Acceptance criteria** — retrieve an as-of curve/spread.
13. **Risks** — interpolation creep into "capture".
14. **Open questions** — curve identity/versioning; storage.

### P2-6 — Benchmark / index data  *(conditionality RESOLVED — DELIVERED at migration `0021`)*
> **AS-BUILT (P2-6, OD-P2-6-* / OQ-P2-6-1…11):** the conditionality is **RESOLVED — the P3 dependency is CONFIRMED** (the benchmark-relative/active-risk + factor on-ramp consumes captured membership as as-of inputs, OD-P2-6-O). Built **metadata + constituents** only: `benchmark` (EV definition) + `benchmark_constituent` (FR bitemporal membership, set-grained per `(benchmark, effective_date)`). **`benchmark_level`/`benchmark_return` (captured levels/returns) DEFERRED** — a net-new canonical ENT id NOT minted here (OD-P2-6-K). **Audit (OQ-P2-6-11 Option A):** `REFERENCE.CREATE`/`REFERENCE.UPDATE` for the EV definition (honoring step-6) + `MARKET.BENCHMARK_CONSTITUENT_*` (EVT-200) for the FR membership. **Entitlement:** reuse `marketdata.view`/`.ingest` (a narrow, recorded supersession of the sketch's step-7 'reference perms (definition)'). **Lineage:** `VENDOR_BENCHMARK` ORIGIN for both (a recorded supersession of step-9 'MANUAL/reference for definitions'). **DQ:** required-field + weight `RANGE [0,1]` (sum/staleness deferred). Symmetric RLS both tables (NEITHER append-only). The sketch below (steps 1–14) is the pre-build plan; the AS-BUILT above governs.
1. **Requirements included** — benchmark definitions/constituents + levels, **only if a P3 factor dependency is confirmed**.
2. **Requirements excluded** — active-return/attribution/factor math.
3. **Proposed entities/modules** — `benchmark` (**ENT-009, EV reference**) + `benchmark_level` (FR levels; **a net-new canonical ENT id minted via the Part-3 ratification, gated on the confirmed P3 dependency** — not a free P2-6 build choice).
4. **Temporal classification** — definition = **EV**; levels = **FR**.
5. **APIs** — `GET /benchmarks` + `GET /benchmarks/{id}/levels/as-of`.
6. **Audit events** — reuse `REFERENCE.*` for the EV definition; `MARKET.*` for the levels.
7. **Entitlement checks** — reference perms (definition); `marketdata.*` (levels).
8. **RLS behavior** — **benchmark definition defaults to SYMMETRIC tenant-scoped** (per OD-P2-G; a shared-global benchmark definition is an AD-013-R2 governance event, out of scope) + the closed-hybrid-set fence; levels symmetric.
9. **Lineage behavior** — vendor source for levels; MANUAL/reference for definitions.
10. **Data quality behavior** — constituent coverage; level staleness.
11. **Tests** — as-of retrieval + RLS + closed-hybrid-set-unchanged.
12. **Acceptance criteria** — as-of benchmark + levels retrieval.
13. **Risks** — premature build before a real P3 need.
14. **Open questions** — confirm the P3 dependency + mint the `benchmark_level` canonical id before building.

---

## Part 3 — Cross-cutting contracts
- **AD-014 gate (load-bearing):** no `exposure_aggregate` (or any future derived output) without a non-null `input_snapshot_id` on its `calculation_run` + a complete TR-15 bind — enforced at the governed-write path + the full negative test (any-missing-item → raises + zero result rows + no orphan run).
- **FW-RUN §5/TR-15 bind:** **`code_version` (anchor)** + input_snapshot + (model_version/assumption-set/scenario/seed **N/A-with-rationale**) + initiator + run-timestamps/**`environment_id` (additive column)**. Incomplete bind ⇒ not published.
- **Audit reality (R-07):** the run reuses the **shipped `CALC.RUN_CREATE`/`CALC.RUN_STATUS_CHANGE`** (the taxonomy `RUN_START/COMPLETE/FAIL` labels are a doc-vs-code reconciliation item); wire `exposure.aggregate.run`; reuse `DATA.VALIDATE`; reserve `SNAPSHOT.*`/`MARKET.*`. **`audit/service.py` FROZEN.**
- **Storage (OD-P2-H):** Postgres-first behind the AD-004 repo interface — **a proposed AD-004 refinement (deviates from "Timescale initially"), pending ratification** (OD-014/OD-046/OD-005); Timescale on a measured threshold; the future-Timescale tenant-scoping constraint stands.
- **Tenancy (AD-013):** market data + benchmark definition symmetric; hybrid only via a future AD-013-R2.
- **DQ (OD-P2-I):** pure/cross-row rules = REGISTRY adds over `(params, dataset)`; **staleness + snapshot-completeness = caller-side gates** (Protocol untouched); no-regression on the 2 shipped evaluators.
- **Lineage (OD-P2-J):** vendor→series ORIGIN reuses `record_lineage` (no code); **snapshot/component/run edges need a NEW internal writer** (table unchanged; RLS-stamped from the resolved source).
- **Entitlement (R-07):** maker = the existing **`data_steward`** (no new role); reconcile `marketdata.ingest` vs `data.upload` (recommend distinct governed canonical-write).

## Part 4 — Factor-model & real-data readiness (forward; NOT built)
3y pilot / 5y prod / 10y+ strategic / 15–20y stress — **non-binding** estimates (OD-P2-K); estimation window = a `model_version` assumption; no factor model / no risk math in P2.

## Part 5 — Synthetic-data usage (P2)
P1C-6 fixtures for snapshot/run/exposure + synthetic FX/price/curve (SYNTHETIC tenant only); **input-only**. The existing AST fence already blocks compute; P2-3 **adds** a negative test that no synthetic module imports/writes `exposure_aggregate`/`calculation_run` (and the SYNTHETIC tenant has zero such rows post-seed), and adds the new fx/price/curve seed modules to `_SYN_MODULES` (OD-P2-L). No real data; never-auto-run.

## Part 6 — Risks & open questions register
Subphase risks above + OQ-P2-1/3/4/6/7 in `p2_0_decision_record.md` Part 4 (OQ-P2-2 + OQ-P2-5 resolved in the decision record). Headline risks: scope creep into risk analytics (mitigated by the per-slice vocabulary scope-fences); snapshot hash determinism across engines (app-side canonical serialization); cross-tenant snapshot binding (the binding-integrity invariant + test); market-data volume → the OD-014/AD-004 Timescale threshold.

## Part 7 — UltraCode review
See `p2_0_decision_record.md` Part 5 (8 × approve_with_changes, 0 block; in-scope findings folded into both artifacts).

## Part 8 — P2-1 planning prompt (when approved)
> "Begin P2-1 planning only: the `dataset_snapshot` reproducible input snapshot. Do not write application code; do not create migrations; do not implement. Produce the P2-1 implementation plan (mirror the P1C per-slice plans) for an **IA TRUE append-only** `dataset_snapshot` (header) + `dataset_snapshot_component` (per-input physical-version pin) — **new canonical ENT ids** — that binds an as-of input set (positions + valuations + reference; market refs optional) by `(as_of_valid_at, as_of_known_at)` + an app-side canonical content/manifest hash, pinning the FR `(surrogate_id, valid_from, system_from)` tuple + captured value resolved via `reconstruct_*_as_of`. Define: module placement (`irp_shared/snapshot/`); create/read/verify APIs; `SNAPSHOT.CREATE` audit (reserve via R-07; `audit/service.py` FROZEN); `snapshot.view`/`.create` entitlements (deny-by-default; maker `data_steward`; `auditor_3l` excluded); symmetric FORCE-RLS + the closed-hybrid-set fence + the **cross-tenant binding-integrity invariant** (resolve only under the acting tenant's RLS session; proprietary components pin own-tenant only; foreign target → fail closed) with its negative test; the **new internal lineage writer** (snapshot→component→input; `data_snapshot` token; table unchanged); the completeness-coverage **caller-side DQ gate** (fail-closed; reuse `DATA.VALIDATE`; `(params, dataset)` Protocol untouched); the temporal-reproducibility **mutation test** + immutability (P0001 trigger) + RLS-isolation tests; acceptance; risks; and the FW-RUN binding readiness for P2-3. STRICT EXCLUSIONS: NO calc/exposure/risk; NO market-data build; NO migration beyond the snapshot tables (+ the additive `calculation_run.environment_id` if co-located); NO `audit/service.py` change. 8-lens UltraCode review. Do not commit until I approve."
