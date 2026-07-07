# P3-4 Implementation Plan — Covariance / Volatility Estimation (sample v1)

## Document Control

| Field | Value |
|---|---|
| Purpose | The build contract for P3-4: an **equal-weighted sample covariance matrix of factor returns** — the third governed risk number and the P3-5 VaR/ES substrate — bound to `dataset_snapshot` + `calculation_run` + a **registered, identity-checked `model_version`** with a **registration-declared estimation window**, IA append-only, dual-path-verified. Companion to `p3_4_decision_record.md` (OD-P3-4-A…P). |
| Status | **Implementation PLAN — PLANNING ONLY; NO code, NO migrations, NO covariance implementation.** |
| HEAD at writing | `362481a` (CI #96 green; P3-3 impl `7c50c43` = #95 green); migration head `0024_factor_exposure`. |
| Predecessors | `p3_4_decision_record.md`; the shipped **hardened P3-3 exemplar** (`risk/factor_service.py` — mirrored step-for-step incl. the review hardenings); `p3_2_factor_return_inputs_implementation_plan.md` (the consumed series); the 2026-07-07 review-deferral register (resolved by the R0 pre-step). |
| Review | Shared with the decision record **Part 5** (disciplined single-pass; folds applied). |

> **Critical invariant (the gate every row passes):** no `covariance_result` row exists unless bound to **`dataset_snapshot` (`COVARIANCE_INPUT`) + `calculation_run` (`COVARIANCE`) + a registered `model_version` OF `risk.covariance.sample` (identity-checked) + `methodology_ref` + `code_version` + `environment_id` + `CALC.RUN_*` audit + `snapshot→run→result` lineage + the fail-closed alignment/window gates**, and is **reproducible** from the snapshot-pinned series alone (no live factor/return read; invariant under later vendor supersede/correction). **PSD by construction; verified by eigenvalue property tests + an independent `numpy.cov` cross-check.** **This plan builds NOTHING.**

---

## Part 0 — The R0 refactor pre-step (OD-P3-4-O; its own commit, BEFORE this slice)
Behavior-preserving extractions resolving the 2026-07-07 duplication findings so P3-4 mints no 4th/5th copies:
1. **`snapshot/service.py` → `_persist_snapshot(session, *, acting_tenant, actor, specs, label, purpose, as_of_valid_at, as_of_known_at, as_of_valuation_date, binding_predicate_version) -> DatasetSnapshot`** — the manifest-hash + header + component-loop + lineage-loop + `record_snapshot_create` tail, consumed by `build_snapshot`, `build_curve_snapshot`, `build_factor_exposure_snapshot` (and P3-4's new builder).
2. **`dq/service.py` (or a small `dq/gates.py`) → `ensure_presence_rule(...)` + `run_presence_gate(session, *, rule_code, rule_name, target_entity_type, gate_target_id, gaps, actor)`** — the resolve-or-register `{'present': None}` NOT_NULL pair, consumed by the snapshot/exposure/sensitivity/factor-exposure call sites (and P3-4's).
Constraints: byte-identical behavior (all 970+ tests green unmodified except import paths); no signature change at any public binder; `make check` + full PG + CI green before P3-4 implementation starts. The run-scaffold extraction is explicitly NOT part of R0 (deferred — failure-timing semantics).

---

## Part 1 — Module map (what the P3-4 implementation slice will touch)

| Area | Change | New/Modified |
|---|---|---|
| `packages/shared-python/src/irp_shared/risk/covariance_kernel.py` | the **pure estimation kernel** — `FactorSeriesPin` (id/code/ordered `(date, value)` rows), `estimate_covariance(series: list[FactorSeriesPin]) -> dict[tuple[str, str], Decimal]` (aligned-input verification; `μ`, `cov_ij` unbiased N−1; Decimal-50; HALF_UP-20; canonical pair ordering) — no DB, no I/O | NEW |
| `…/risk/covariance_service.py` | **`run_covariance(...)`** — the governed binder (the hardened P3-3 shape) + `list_covariance` / `resolve_covariance_run` / `resolve_covariance` readers | NEW |
| `…/risk/models.py` | add `CovarianceResult` (ENT-051; IA append-only ORM guard; the Part-2 columns) | MODIFIED |
| `…/risk/events.py` | add `RUN_TYPE_COVARIANCE = "COVARIANCE"` + `RISK_COVARIANCE_CREATE_EVENT_RESERVED` (reserved, NOT emitted) + `CovarianceActor` | MODIFIED |
| `…/risk/bootstrap.py` | add `register_covariance_model(..., window_observations=N)` (`risk.covariance.sample` v1; window recorded as a `model_assumption` AND part of the version-resolution identity — a mismatch raises the existing `ModelVersionConflictError`); constants + `COVARIANCE_METHODOLOGY_REF` | MODIFIED |
| `…/snapshot/models.py` | add `COMPONENT_KIND_FACTOR_RETURN = "FACTOR_RETURN"` + `PURPOSE_COVARIANCE_INPUT = "COVARIANCE_INPUT"` (app constants — NO migration; the OD-P3-2-G readiness note closes) | MODIFIED |
| `…/snapshot/serialize.py` | `factor_return_series_content(factor, rows)` (ordered window rows; per-row immutable FR fields; values at scale 12) | MODIFIED |
| `…/snapshot/service.py` | `build_covariance_snapshot(session, *, acting_tenant, actor, factor_ids, as_of_valid_at, as_of_known_at=None, window_observations)` — resolves factors (fail-closed), computes the N-most-recent COMMON dates via the bitemporal reads, **fails closed on shortfall BEFORE any write**, pins one `COMPONENT_KIND_FACTOR` + one `COMPONENT_KIND_FACTOR_RETURN` component per factor via the R0 `_persist_snapshot`; truthful `COVARIANCE_BINDING_PREDICATE = "v1:factor-return-window"`; `_reresolve_content` FACTOR_RETURN handler (per-row id re-reads) | MODIFIED |
| `migrations/versions/0025_covariance.py` | `covariance_result` (IA append-only + P0001 + symmetric FORCE RLS); **head `0024` → `0025`** | NEW |
| `apps/backend/src/irp_backend/api/risk.py` | covariance endpoints on the existing router (POST run + run/row reads + POST `/risk/models/covariance` w/ `window_observations`) — gated by the **existing** `risk.run`/`risk.view`/`model.inventory.register`; the existing `_ERROR_MAP` extended for the new pre-create errors only | MODIFIED |
| `05_analytics_methodologies/covariance_sample_v1.md` | the methodology doc (Part 6) | NEW |
| `requirements-dev.txt` | add `numpy` (TEST-ONLY; plus the `irp_shared`-must-not-import-numpy fence test) | MODIFIED |
| `.github/workflows/ci.yml` | the explicit `test_covariance_pg.py` step (the complete-list discipline) | MODIFIED |
| tests | `test_covariance.py` / `_pg.py` / `test_covariance_endpoint.py` (Part 7) + the numpy fence | NEW |
| governance docs | the R-07 amendments of the decision record Part 3 (incl. the **ENT-051 mint** + the no-status-decay flips) | MODIFIED |

**Untouched (hard):** `audit/service.py` (FROZEN); `entitlement/bootstrap.py` (**no new permission**); `marketdata/factor.py` (read-only consumer); the P3-1/P3-3 binders (beyond R0 import-path changes); the DQ `Protocol`; no BYPASSRLS; no hybrid.

---

## Part 2 — `covariance_result` (ENT-051) table design
IA TRUE append-only; run-bound + snapshot-gated + model-bound. Columns:

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` / `tenant_id` / `system_from` | GUID / GUID / DateTime(tz) | NO | the IA mixin trio |
| `calculation_run_id` | GUID FK→`calculation_run.run_id` | NO | indexed |
| `input_snapshot_id` | GUID FK→`dataset_snapshot.id` | NO | indexed |
| `model_version_id` | GUID FK→`model_version.id` | NO | indexed; registered + identity-checked |
| `factor_id_1` / `factor_id_2` | GUID | NO | canonical order `factor_id_1 <= factor_id_2` (binder-enforced, NO CHECK); NOT hard FKs (the pin is authoritative); diagonal ⇒ equal |
| `factor_code_1` / `factor_code_2` | String(150) | NO | carried captured labels |
| `statistic_type` | String(30) | NO | `'COVARIANCE'` v1 (`'CORRELATION'` reserved — extend by value) |
| `return_type` / `frequency` | String(30) / String(20) | NO | carried conventions (`'SIMPLE'` / `'DAILY'`) |
| `n_observations` | Integer | NO | = the version's declared window N |
| `window_start` / `window_end` | Date | NO | the aligned window bounds (self-describing) |
| `covariance_value` | Numeric(38,20) | NO | `quantize_HALF_UP(cov_ij, 20)`; daily, unannualized (declared) |

**Grain / unique:** `(calculation_run_id, factor_id_1, factor_id_2)` — snapshot/model carried NN, out of key. Diagonal rows (`factor_id_1 == factor_id_2`) are the **variances**. For F factors a COMPLETED run writes exactly `F·(F+1)/2` rows (test-asserted). Register in `irp_shared.models`; ORM append-only guard + migration `APPEND_ONLY_TABLES` + P0001; symmetric FORCE RLS.

---

## Part 3 — `run_covariance(...)` binder (the hardened P3-3 shape)
```
run_covariance(session, *, acting_tenant, actor, code_version, environment_id,
               model_version_id, factor_ids=None, as_of_valid_at=None,
               as_of_known_at=None, snapshot_id=None) -> CovarianceRunResult
```
- **(a) pre-create gate** (⇒ ZERO run/rows/run-audit): prerequisites truthy; **`assert_model_version_of(..., expected_model_code=COVARIANCE_MODEL_CODE)`**; resolve the version's declared `window_observations` N (from its assumptions — the binder reads the declared window, never a free parameter). Build path: `factor_ids` ≥ 2, distinct (duplicates refused), each `resolve_factor` own-tenant fail-closed, each `frequency=='DAILY'` (v1); then `build_covariance_snapshot(..., window_observations=N)` — which fail-closes on < N common dates BEFORE any write. Consume path: `resolve_snapshot` + `purpose == PURPOSE_COVARIANCE_INPUT`.
- **(b) pinned-content adjudication — BOTH paths, pre-create** (the P3-3 hardening by construction): parse the pinned components; require ≥2 `FACTOR_RETURN` series; every series exactly N rows; **identical date sets across series**; N == the version's declared window; a paired `COMPONENT_KIND_FACTOR` pin per series. Any defect ⇒ `CovarianceInputError` (422) — a snapshot minted elsewhere cannot smuggle a short/misaligned window past the gate.
- **(c) run** — `create_run(run_type=RUN_TYPE_COVARIANCE, input_snapshot_id, model_version_id, code_version, environment_id)` → RUNNING.
- **(d) DEPENDS_ON before the gate** (FAILED runs keep their input link).
- **(e) compute** — the pure kernel over the parsed pins ONLY (no live read; import-fenced): `μ_i`, then `cov_ij` for the canonical upper triangle; Decimal-50; HALF_UP-20.
- **(f) defensive post-compute gate** — rule `risk.covariance.completeness` (R0 shared helper): non-finite value or negative diagonal ⇒ `DataQualityError` ⇒ **FAILED run (`outcome='failure'`) + ZERO rows** + a defect-naming `failure_reason` (should be unreachable for the sample estimator — recorded defense-in-depth, honestly commented).
- **(g) governed write** — `F·(F+1)/2` rows + flush + per-row `ORIGIN` (`run_id` stamped) + COMPLETED.

---

## Part 4 — Kernel formulas + verification (the dual-path contract)
For factors `i, j` over the aligned window `t = 1…N` (dates identical across series, verified twice):
```
μ_i     = ( Σ_t r_i,t ) / N
cov_ij  = ( Σ_t (r_i,t − μ_i) · (r_j,t − μ_j) ) / (N − 1)          N ≥ 2
```
- Decimal `localcontext(prec=50)`; result `quantize_HALF_UP` to 20dp (`Numeric(38,20)`); units: daily `SIMPLE`-return covariance, **unannualized** (declared).
- **PSD:** Gram-form ⇒ PSD in exact arithmetic; quantization perturbs O(1e-20).
- **Verification (the standing rule, first mandatory application):** (1) hand-computed exact references for a 3-factor/4-observation matrix (ground truth independent of both implementations); (2) **`numpy.cov(…, ddof=1)` cross-check** on synthetic data, `ε_rel = 1e-9`; (3) **eigenvalue property test** `λ_min ≥ −1e-12·trace` on representative + seeded-random matrices (numpy, TEST-ONLY); (4) exact re-run reproducibility; (5) invariance under a post-pin vendor supersede/correction of a window return (the TR-09 proof).

---

## Part 5 — Snapshot extension (the FACTOR_RETURN series pin)
- `COMPONENT_KIND_FACTOR_RETURN` + `PURPOSE_COVARIANCE_INPUT` app constants (no migration).
- `factor_return_series_content(factor, rows)` — `{factor_id, factor_code, return_type, frequency, rows: [{id, return_date, return_value(12dp), valid_from, system_from, record_version}, …]}` ordered by `return_date`; FR row content is immutable ⇒ byte-stable re-verification.
- `build_covariance_snapshot` — per factor: `resolve_factor`, then the window rows via the EXISTING reads only (`list_factor_returns` current-head filtered to `return_date <= as_of_valid_at.date()`; when `as_of_known_at` is supplied, per-date `reconstruct_factor_return_as_of` — `marketdata/factor.py` stays UNTOUCHED); compute the COMMON-date intersection; `< N` ⇒ `CovarianceSnapshotError` (409) BEFORE any write; pin `COMPONENT_KIND_FACTOR` (reused serializer) + `COMPONENT_KIND_FACTOR_RETURN` per factor via the R0 `_persist_snapshot`; binding predicate `"v1:factor-return-window"`.
- `_reresolve_content` FACTOR_RETURN handler: re-read each pinned row by id (tenant-predicated); a gone/cross-tenant row reports as drift (the established verify semantics).

## Part 6 — Methodology doc (`05_analytics_methodologies/covariance_sample_v1.md`)
The OD-P3-0-C §-template: purpose & applicability (factor sample covariance; the P3-5 substrate; diagonal = variances); inputs + **data policy** (the OD-P3-0-L realization: window N declared at registration and identity-bound; DAILY/SIMPLE; alignment = N most recent common dates; **fail-closed, no imputation/pairwise**); formulas + numerical standards (Part 4 verbatim; Numeric(38,20) HALF_UP-20; unannualized); assumptions (→ `model_assumption`, incl. `window_observations=N`); limitations (→ `model_limitation`: equal weights — no decay; no shrinkage ⇒ ill-conditioned for F approaching N (recorded, with the F < N guidance); factor-level only; no annualization; UNVALIDATED until P7); validation/reproduction tests (Part 4's five legs); known limitations + scope-out.

## Part 7 — Tests
1. **Kernel:** hand-computed exact references; N−1 unbiasedness; canonical pair ordering incl. diagonal; N=2 floor; misalignment raises; quantization; **numpy.cov cross-check (ε_rel 1e-9)**; **eigenvalue PSD property test** (representative + seeded-random).
2. **Row-count + symmetry-by-construction:** F factors ⇒ exactly F·(F+1)/2 rows; diagonal = variances ≥ 0.
3. **Reproducibility:** same-snapshot re-run identical; **invariant under a post-pin vendor supersede AND correction** of a window return; consume-existing path identical to build-in-request.
4. **Window/alignment fail-closed:** < N common dates ⇒ pre-create refusal (zero run); a gap date in one factor ⇒ refusal; the consume path refuses a short/misaligned/wrong-N pinned snapshot (build one via the raw builder args to prove the adjudication).
5. **Model governance:** unregistered ⇒ `UnregisteredModelError`; **wrong-family version (the factor-exposure model) ⇒ `WrongModelVersionError`** — both zero-run; registration idempotent; **same-label different `window_observations` OR `code_version` ⇒ `ModelVersionConflictError`**; assumptions include the window; `methodology_ref` matches + doc sections present.
6. **Output contract / IA / RLS / lineage / entitlement / audit:** the P3-3 test-group shapes verbatim (non-null bindings; ORM + P0001 append-only; PG symmetric-RLS + forged-tenant + closed-hybrid-set; DEPENDS_ON-on-FAILED + ORIGIN; **`risk.*` REUSE parity — no new codes**; `CALC.RUN_*` present, zero `RISK.*` emitted).
7. **Scope fences:** no VaR/ES/stress/scenario/benchmark/attribution/shrinkage/EWMA identifiers; no live `resolve_factor`/`reconstruct_factor_return_as_of`/`list_factor_returns` in the compute path (found-the-functions asserted — the P3-3 fence lesson); **`irp_shared` runtime imports NO `numpy`** (the new fence); migration head `0025_covariance` + the five prior head-assertion flips + the synthetic `0026*` glob flip.
8. **Endpoint:** register (incl. 409 conflict) / run / reads; 403 deny-by-default + view-cannot-run; 422/404/409 refusals; FAILED surfaced; no mutating verbs.

## Part 8 — Acceptance criteria
- Covariances reproduce **exactly** on re-run and match `numpy.cov` within ε_rel 1e-9 + hand references (the P3-0 "PSD + reproduces within ε" acceptance — **the dual-path standing rule's first discharge**); eigenvalue-PSD holds.
- The critical invariant holds for every row; window/alignment gates fail closed on both paths; IA + symmetric RLS PG-proven; **no new permission**; `audit/service.py` untouched; head `0025_covariance`; the CI PG list stays complete; the ENT-051 mint + all Part-3 amendments land with the no-status-decay flips.
- **REQ-MKT-001 unchanged** (substrate note only).

## Part 9 — Review log
Shared with `p3_4_decision_record.md` Part 5 (single-pass; folds applied there — the substrate-note explicitness, the R0 resolution, the Numeric(38,20) justification, the named consume-path adjudication checks, the split ε values).

## Part 10 — Risks & open questions
- **Ill-conditioning at F ≈ N** (sample covariance rank ≤ N−1): recorded limitation + methodology guidance (F < N); shrinkage is the designed v2 — NOT silently added.
- **Window semantics under sparse vendor data:** the common-date intersection can reach far back for mismatched calendars — recorded; a max-lookback bound is a candidate v2 registration parameter.
- **R0 sequencing risk:** the refactor touches shipped builders — mitigated by its behavior-preserving contract, the full suite, and the now-complete CI PG coverage; landed + CI-green before P3-4 code starts.
- **Open (settled at build):** exact endpoint DTO shapes; the seeded-random test-matrix generator's seed policy (fixed seeds, recorded — QS-18 spirit).

## Part 11 — Implementation kickoff prompt (when approved)
> "Begin P3-4 implementation only, in TWO separately-committed steps. **STEP R0 (first commit):** the behavior-preserving refactor per `p3_4_covariance_implementation_plan.md` Part 0 — extract `_persist_snapshot` (consumed by all three shipped builders) + the parameterized DQ presence-gate helper (consumed by the four shipped call sites); zero behavior change; all existing tests green; `make check` + full PG + CI green before step 2. **STEP P3-4 (second commit):** build EXACTLY per `p3_4_decision_record.md` (OD-P3-4-A…P) + this plan: `risk/covariance_kernel.py` (sample N−1; Decimal-50; HALF_UP-20; canonical pair order); `risk/covariance_service.py` (`run_covariance` — `assert_model_version_of('risk.covariance.sample')`; the declared-window read; **pinned-content adjudication pre-create on BOTH paths**; DEPENDS_ON-before-gate; defensive post-compute gate; readers); `CovarianceResult` (ENT-051; Part-2 columns; IA append-only); `RUN_TYPE_COVARIANCE` + reserved `RISK.COVARIANCE_CREATE`; `register_covariance_model(window_observations=…)` with the window in the version identity (`ModelVersionConflictError` on mismatch); snapshot `COMPONENT_KIND_FACTOR_RETURN` (series-per-factor) + `PURPOSE_COVARIANCE_INPUT` + `factor_return_series_content` + `build_covariance_snapshot` (fail-closed window) + the verify handler; migration `0025_covariance` (head `0024`→`0025`); the risk-router endpoints on the EXISTING `risk.run`/`risk.view`/`model.inventory.register`; `numpy` into `requirements-dev.txt` ONLY + the no-numpy-in-`irp_shared` fence; the explicit `test_covariance_pg.py` CI step; write `covariance_sample_v1.md`; the Part-7 tests incl. the dual-path cross-check + eigenvalue PSD + the post-pin-correction invariance proof; the R-07 amendments incl. the **ENT-051 canonical mint** + the no-status-decay flips (+ the five migration-head test flips + the synthetic glob). STRICT EXCLUSIONS: NO VaR/ES; NO stress/scenario; NO benchmark-relative/attribution; NO EWMA/decay/shrinkage/correlation output; NO asset/instrument covariance or return computation from prices; NO annualization; NO factor-loading/regression work; NO new permission or audit emitter; NO `audit/service.py` change; NO BYPASSRLS/hybrid; NO frontend; NO P3-5+ work. Independent-context adversarial review before the commit gate (`/code-review ultra` or authorized subagents); `make check` + clean-DB full PG validation. Hold each commit for approval per the gate tiers."

---

*Frontend visibility: none — backend/shared-data + governance only. The covariance substrate enables future risk-model diagnostics UI, but no frontend is built unless explicitly directed.*
