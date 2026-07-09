# P3-7 Implementation Plan — Ex-ante active risk / tracking error (build contract)

> Executes `p3_7_decision_record.md` (OD-P3-7-A…I) once OQ-P3-7-1…10 are ratified. The build
> templates are P3-5's parametric VaR end-to-end (two-upstream-run consumption, single-summary-row
> result, declared-convention model identity, radicand floor) + P3-4's snapshot pinning. **Planning
> implements nothing; implementation starts on separate explicit approval.**

## Step 0 — Pre-checks (no writes)
1. Head is `0029_benchmark_series`; `alembic check` no-op; `0030` free.
2. Verify the seams as recon found them: `var_result`/`var_service`/`var_kernel` shapes;
   `build_var_snapshot`/`build_covariance_snapshot` (the pin builders); `calc/scaffold.py`
   `execute_governed_run`; `RISK_RUN_TYPES`; `benchmark_constituent.constituent_currency` optional.

## Step 1 — Kernel (`risk/active_risk_kernel.py`)
3. `compute_tracking_error(active_weights: dict[factor_id, Decimal], covariance: dict[(f1,f2), Decimal]) -> TeEstimate`:
   radicand = wₐᵀΣwₐ via exact Decimal (context 50); the declared quantization floor
   `tol = F²·max(wᵢ²)·1e-19` (the P3-5 pattern re-derived for weight scale — clamp within, defect
   beyond); `te_value = quantize_HALF_UP(Decimal.sqrt, 12)`. Kernel errors for ill-formed inputs
   (empty weights, missing covariance entries — coverage is re-verified in the kernel, the VaR
   precedent).
4. **Hand references (exact rational constructions, TD-1-plausible):** two uncorrelated factors at
   1% daily vol (var 1e-4) with active weights (0.03, 0.04) — the 3-4-5 triangle in weight space →
   radicand 2.5e-7, TE = **0.000500000000** exactly; fully-correlated pair → 4.9e-7, TE =
   **0.000700000000** exactly (the 7²=49 construction). Plus the TEST-only numpy float cross-check
   + positive-homogeneity (TE(λwₐ)=λ·TE) / symmetry (TE(w_p,w_b)=TE(w_b,w_p)) property tests.

## Step 2 — Model registrar + methodology doc
5. `register_active_risk_model` (`risk/bootstrap.py` constants + the registrar precedent):
   family `risk.active_risk.parametric` v1; `methodology_ref` =
   `05_analytics_methodologies/active_risk_parametric_v1.md` (NEW — the var_parametric_v1 structure:
   definition, formula, conventions, the Part-2 citations, declared assumptions/limitations incl.
   specific-active-risk = 0, daily-unannualized, normalization, the refusal semantics);
   assumptions/limitations recorded; same-label conflict = 409. No free numeric params.

## Step 3 — Snapshot: purpose + the COMPONENT_KIND_BENCHMARK mint
6. `PURPOSE_ACTIVE_RISK_INPUT`; **mint `COMPONENT_KIND_BENCHMARK`** (the FR-row pin flavor — one
   component per pinned constituent row of the declared `(benchmark_id, effective_date)` membership,
   `captured_content` incl. instrument_id/weight/constituent_currency; the benchmark HEADER identity
   goes in the component content, the `factor_return` per-series precedent). `build_active_risk_snapshot`:
   pins FACTOR_EXPOSURE rows (from a COMPLETED factor-exposure run) + COVARIANCE rows (from a
   COMPLETED covariance run) + FACTOR definitions (the covariance factor set) + the BENCHMARK
   membership set (resolved via the tenant-predicated reconstruct — fail-closed on an empty set).
7. Extend `SNAPSHOT_COMPONENT_KINDS` + the verify path additively (tables unchanged — OD-P3-0-G).

## Step 4 — Migration `0030_active_risk` + model
8. `active_risk_result` (IA TRUE append-only: `APPEND_ONLY_TABLES` + `irp_prevent_mutation` trigger
   + ORM guard; symmetric FORCE RLS): grain `UNIQUE(calculation_run_id, metric_type)`;
   `te_value Numeric(20,12)` (PreciseDecimal); hard FKs `factor_exposure_run_id`/`covariance_run_id`
   → `calculation_run.run_id`, `benchmark_id` → `benchmark.id`; `benchmark_effective_date Date`;
   `portfolio_value Numeric(28,6)` (PreciseDecimal); `input_snapshot_id`/`model_version_id` NOT NULL.
   Downgrade drops the table (+ trigger/policies). Per-suite migration-head tests advance → `0030`.

## Step 5 — Binder (`risk/active_risk_service.py`) on the shared scaffold
9. `run_active_risk(...)` via `calc/scaffold.py::execute_governed_run` (its SEVENTH consumer), the
   VaR binder shape: BUILD mode (factor_exposure_run_id + covariance_run_id + benchmark_id +
   benchmark_effective_date → build the snapshot) XOR CONSUME mode (snapshot_id) — the P3-C1
   both-modes ambiguity gate. Pre-create refusals (zero run/rows/audit): unregistered/wrong-family
   model; non-COMPLETED upstream runs; empty membership; **NULL `constituent_currency` on any pinned
   constituent** (named-gap refusal); Σw_b ≤ 0; portfolio value = 0; coverage gaps (portfolio factors
   ⊄ Σ, or a benchmark currency with no Σ factor — NO imputation). Compute: portfolio weights from
   pinned FACTOR_EXPOSURE sums ÷ pinned portfolio value; benchmark weights normalized by Σw_b and
   mapped currency→factor via the pinned FACTOR definitions; wₐ = w_p − w_b over the Σ factor set;
   kernel; post-create FAILED for the radicand-beyond-floor + a result-magnitude envelope (te within
   `Numeric(20,12)`). ONE result row; DEPENDS_ON + ORIGIN lineage via the scaffold; run_type
   `TRACKING_ERROR` (added to `RISK_RUN_TYPES` + the run-type constants).
10. `list_active_risks` + exports; entitlement REUSE parity tests (`risk.run`/`risk.view`).

## Step 6 — API + FE (small, additive)
11. `POST /risk/active-risk/runs` (gated `risk.run`; BUILD/CONSUME bodies, the VaR DTO shapes) +
    `GET /risk/active-risk/runs/{id}` (+ the run listing picks up TRACKING_ERROR automatically via
    `RISK_RUN_TYPES`); error maps per the risk family conventions; decimals as strings.
12. FE: additive `FAMILIES` entry (`TRACKING_ERROR` → label "Active risk", permissionFamily risk) +
    `FAMILY_ROW_COLUMNS`/detail fields (te_value, benchmark, provenance) in `types.ts` (the P3-C2
    exposure-family precedent); tests URL-pinned.

## Step 7 — Docs (same commit)
13. Canonical registry: ENT-027 Notes cell gains the third realization (`active_risk_result` — no
    new id); audit taxonomy: `RISK.ACTIVE_RISK_CREATE` reserved-not-minted (EVT-220, the P3-5
    wording); RTM: advance the benchmark-relative REQ row (verify which REQ at implementation);
    `delivery_roadmap.md`: the OD-G precision amendment ("P2-7 unblocked the benchmark half; the
    portfolio-return series is the ex-post prerequisite") + dated log entry; decision-record status
    stamps. `p3_implementation_plan.md` P3-7 row: mark the ex-ante leg delivered, ex-post deferred.

## Step 8 — Tests (unreduced; TD-1 fixture realism throughout)
14. Kernel: the two exact hand references + numpy cross-check (TEST-only, import-fenced) +
    homogeneity/symmetry/ill-formed properties + the floor boundary.
15. Binder (SQLite): full-stack golden over a realistic seed (e.g. a two-currency portfolio vs a
    two-constituent benchmark, covariance from the P3-4 SERIES windows) with the EXACT expected
    te_value hand-derived; every pre-create refusal (incl. the null-currency and Σw_b gates — zero
    runs/rows/audit); post-create FAILED reachable (the kernel seam poke, the P3-4 pattern); pin
    invariance under post-pin membership supersede/correction (TR-09); audit sequence at the
    P3-C1 golden bar + DQ identity; lineage content; append-only ORM guard; scope fences (no
    benchmark_level/return consumption in v1 — asserted, per OD-G); migration head test.
16. PG (`test_active_risk_pg.py`): FORCE-RLS isolation under `irp_app`; the P0001 trigger proof on
    `active_risk_result`; cross-tenant refusals; a full-width PreciseDecimal roundtrip.
17. Endpoint tests: 401/403/404/409/422 maps; decimal-verbatim; the listing shows TRACKING_ERROR.
18. FE: the new family listed + detail rendering (URL-pinned; decimals byte-for-byte).

## Validation gates (unreduced — OD-P3-7-I)
`make check` → full-PG (fresh schema, the recorded reset recipe) → `alembic check` no-op after
`0030` → downgrade smoke `0030→0029→head` (both directions, real exit codes) → `make fe-check` →
diff fence (audit/service.py + entitlement/bootstrap.py untouched; no new permission; exactly ONE
migration).

## Review
FULL 6-finder adversarial review (the P2-7 angle set + a methodology-correctness lens on the kernel
math and the weight-construction/coverage logic), findings folded, then HOLD for Tier-2 commit
approval.

## Sizing
M/L. The binder/kernel/snapshot legs are templated on P3-5/P3-4; the novel surface is the
benchmark-side weight construction + the COMPONENT_KIND_BENCHMARK mint + the FE family addition.
