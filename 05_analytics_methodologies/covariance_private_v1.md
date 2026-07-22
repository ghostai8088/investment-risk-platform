# Methodology — Private-Factor Covariance block Ω_pp (equal-weighted unbiased sample estimator) v1

> **Model:** `risk.covariance.private` · **Version:** `v1` · **Referent:** `model_version.methodology_ref` points here.
> **Status:** REGISTERED; `validation_status = UNVALIDATED` (recorded, **non-enforcing until the P7 validation workflow**). This doc IS the methodology referent the governed `model_version` binds (PPF-2, ENT-051 reused table, OD-PPF-2-A/B/D).

## Purpose & applicability
The **nineteenth** governed number and the **second slice of the §2.1 unification arc**: the
**private-factor covariance block Ω_pp** — the equal-weighted, unbiased (N−1) sample covariance of
the **pure-private return series** produced by PPF-1 (`risk.covariance.private` over
`PURE_PRIVATE_PERIOD` results), across ≥ 2 `PRIVATE`-family **segment factors**, over their common
appraisal-period grid. It is the substrate for the PPF-3 unified number
`√(x'Σx + p'Ω_pp·p + residual)`: Ω_pp is the `p'Ω_pp·p` block.

This is a **fail-closed sibling** of the public sample covariance (`risk.covariance.sample`): it
reuses the **generic** `estimate_covariance` kernel unchanged and the **shared** `covariance_result`
table (`frequency = APPRAISAL`, `run_type = COVARIANCE_PRIVATE`). The two families never mix — the
public reads filter `run_type` (the shared-table contract; PPF-2 step 1), and this family consumes
ONLY governed pure-private results, never captured factor returns.

Applicable to ≥ 2 pinned `PRIVATE` segment `factor` definitions, each carrying a pinned
`PURE_PRIVATE_RETURN` series of exactly the registered version's declared `window_observations`
common appraisal periods.

**NOT applicable to** (deferred — see Known limitations): joint public+private (off-block-diagonal)
estimation; EWMA/decay-weighted or shrinkage (Vasicek/Ledoit-Wolf) estimation; correlation-matrix
output; the appraisal→daily **frequency conversion** (that is PPF-3); annualization; the VaR/ES
consumer of the unified covariance (that is PPF-3).

## Inputs & data policy
- **Inputs:** the selected `PRIVATE` segment `factor` EV definitions + each segment's PPF-1
  pure-private `PURE_PRIVATE_PERIOD` return series, pinned into a `PRIVATE_COVARIANCE_INPUT`
  `dataset_snapshot` as `COMPONENT_KIND_FACTOR` (EV pin of the segment definition) +
  `COMPONENT_KIND_PURE_PRIVATE_RETURN` (one component per pooled appraisal period: the governed-row
  pin over `segment_factor_id`/`metric_type`/`period_start`/`period_end`/`metric_value`) components.
  The compute reads **only** the pinned snapshot content — never a live pure-private/factor read — so
  a result is reproducible under a later PPF-1 re-run (TR-09).
- **Data policy:** the window `N` is **declared at model registration**
  (`window_observations=N` as a `model_assumption`) and is part of the version identity — the binder
  reads the DECLARED window; it is never a free request parameter. Here `N` is the count of **common
  appraisal periods**: the `N` most recent `(period_start, period_end]` intervals on which **every**
  selected segment has a pure-private return — a set intersection on the interval key. **Fail-closed:
  no imputation, no pairwise deletion** (pairwise covariance over unequal windows breaks positive
  semi-definiteness). Pure-private returns are `SIMPLE` decimal fractions (`0.01` = 1%).
- **Missing data:** fewer than `N` common periods refuses the snapshot build BEFORE any write (409);
  a consumed snapshot whose pinned series are short / misaligned / a different `N` / from a
  non-`PRIVATE` segment is a **pre-create refusal** (422) — zero run, zero rows.

## Formulas & numerical standards
For segments `i, j` over the aligned common-period window `t = 1…N` (interval keys identical across
series, verified at adjudication AND re-verified by the kernel):

```
μ_i     = ( Σ_t p_i,t ) / N
Ω_ij    = ( Σ_t (p_i,t − μ_i) · (p_j,t − μ_j) ) / (N − 1)          N ≥ 2
```

where `p_i,t` is segment `i`'s pooled pure-private return for period `t`.

- **Grain:** one row per **canonical unordered segment pair** including the diagonal
  (`factor_id_1 ≤ factor_id_2`, lowercase-GUID string order; service-enforced) — `K·(K+1)/2` rows
  per COMPLETED run for `K` segments; the run is the matrix identity. Symmetry is **by
  construction**, not by duplicate-row bookkeeping.
- **Units:** covariance of `APPRAISAL`-frequency `SIMPLE` pure-private returns — **UNANNUALIZED**.
  The appraisal→daily frequency conversion is DEFERRED to PPF-3; Ω_pp is stored native-APPRAISAL.
- **Rounding / precision:** computed in `Decimal` at 50-digit context precision;
  `quantize_HALF_UP` to the reused `covariance_result` column scale (`Numeric(38,20)`).
- **PSD:** the estimator is a Gram-form matrix ⇒ **positive semi-definite in exact arithmetic**; the
  20dp quantization perturbs eigenvalues at O(1e-20). Test-verified (eigenvalue floor
  `λ_min ≥ −1e-12·trace`), not runtime-enforced.
- **Rank:** rank ≤ min(K, N−1) — for `K ≥ N` the matrix is singular (recorded limitation; N is small
  by nature here, so this is a real thin-window constraint — use `K < N`).

## Assumptions
Mirrored content-identically into `model_assumption` rows on the registered version (plain-ASCII
spellings — `SUM`/`mu`/`-`; plus the registration-supplied `window_observations=N`):
- Equal-weighted UNBIASED sample covariance of pure-private segment returns:
  `Ω_ij = Σ_t((p_i,t − μ_i)(p_j,t − μ_j)) / (N − 1)`; `μ_i = Σ_t(p_i,t) / N`. The SAME generic
  kernel as `risk.covariance.sample` — this family differs only in its input series and frequency.
- Inputs: PPF-1 pure-private APPRAISAL return series (governed `PURE_PRIVATE_PERIOD` results, NOT
  captured factor returns); the window = the N most recent appraisal periods on which EVERY selected
  PRIVATE segment has a pure-private return (set intersection over `(period_start, period_end]`);
  fewer than N common periods fails closed — NO imputation, NO pairwise deletion.
- Units: APPRAISAL-frequency, UNANNUALIZED covariance of SIMPLE pure-private returns; the
  appraisal→daily conversion is deferred to PPF-3.
- Computed in Decimal at 50-digit context precision; `quantize_HALF_UP` to the `covariance_result`
  column scale.
- PSD by construction (Gram form) in exact arithmetic; numerically verified by the shared eigenvalue
  property tests + the `numpy.cov` cross-check (test-only dependency).

## Limitations
Mirrored content-identically into `model_limitation` rows (plain-ASCII spellings stored):
- **Block-diagonal APPROXIMATION** — Ω_pp is the pure-private block ONLY; the unified covariance
  treats it as block-diagonal with the public Σ (zero cross-covariance). This is an
  **approximation, NOT orthogonal-by-construction**: PPF-1 subtracts the **promoted** proxy blend
  (a SUBSET of the OLS fit), so a pure-private series retains a dropped-factor public component and
  has a small non-zero cross-covariance with Σ. Joint public+private estimation is the v2.
- **Equal weights only** — no EWMA/decay; no shrinkage (Vasicek/Ledoit-Wolf); each is a later,
  separately declared `model_version`. The sample estimator is rank-deficient for `K ≥ N` segments.
- **Thin window by nature** — appraisal periods are quarterly, so `N` is small (single-digit); the
  estimate is disclosed-thin, NOT down-weighted; shrinkage is the recorded v2 remedy.
- **Factor-level (segment) covariance only**; `APPRAISAL` frequency, unannualized; no
  correlation-matrix output (`statistic_type` `CORRELATION` reserved).
- `validation_status = UNVALIDATED` — recorded, non-enforcing until the P7 validation workflow.

## Validation / reproduction tests
The verification legs of the dual-path standing rule (PPF-2 REUSES the generic
`estimate_covariance` kernel byte-for-byte, so the kernel-level legs are the *same shipped tests* as
`covariance_sample_v1`, inherited unchanged — this family adds the input-path + isolation legs):
1. **Hand-computed exact references (inherited):** the kernel's hand-computed 2-/3-series references
   at 20dp live in `test_covariance.py` and bind unchanged (same `estimate_covariance`, same
   quantum); this family does not re-derive them.
2. **Independent-implementation cross-check (this family):** `numpy.cov(…, ddof=1)` on the two
   pure-private series agrees within relative ε = 1e-9 — `test_omega_pp_matches_numpy_cov` (numpy is
   a TEST-ONLY dependency; `irp_shared` runtime imports NO numpy — fence-tested).
3. **Eigenvalue PSD property test (inherited):** `λ_min ≥ −1e-12·trace` on the shared covariance
   property battery (`test_covariance.py`).
4. **Exact re-run reproducibility + consume==build (this family):** the same segments re-run yield
   byte-identical `Ω` (`test_omega_pp_is_reproducible`), AND the consume-existing (`snapshot_id`)
   path equals build-in-request byte-for-byte
   (`test_omega_pp_snapshot_verifies_and_consume_equals_build`).
5. **Pin invariance / verify (TR-09, this family):** the pinned `PURE_PRIVATE_RETURN` +
   `COMPONENT_KIND_FACTOR` components re-resolve byte-identically (`verify_snapshot(...).ok`); the
   pins are IA append-only, so a post-pin PPF-1 re-run mints NEW rows and cannot move the pinned
   ones — a gone/tampered pin reports as *drift*, never a raw 500
   (`test_omega_pp_snapshot_verify_reports_drift_not_500`).
6. **Public isolation (this family):** a private-covariance run NEVER surfaces through the public
   `latest_covariances` / `list_covariances` / by-id covariance reads (the `run_type` filter), and a
   public covariance run NEVER surfaces through the private reads — proven both directions.

## Known limitations
This is the sample-estimator, block-diagonal floor of the private-covariance substrate. Joint
public+private estimation, shrinkage, EWMA, correlation output, the appraisal→daily frequency
conversion (PPF-3), annualization, and the unified VaR/ES consumer are **out of scope for v1** and
are taken up by later slices under their own declared `model_version`s. **No statistical-adequacy
floor beyond `N ≥ 2` in v1:** the declared window is the count of common appraisal periods that
actually exist (the "N most recent common periods" set-intersection semantics), so Ω_pp registers +
completes at whatever thin `N` the substrate carries — down to `N = 2` (one degree of freedom) —
and presents it as a governed number with `n_observations` disclosed on every row. This is a
disclosed property (there is no HS-VaR-style `N ≥ 21/41` gate); shrinkage (v2) is the remedy for
thin-window instability, and PPF-3 must carry the thin-`N` disclosure forward. The block-diagonal
approximation and its disclosed-thin `N` are the two recorded v1 seams; the joint-estimation and
shrinkage v2 referents must carry both forward (the carry-forward rule). This `v1` referent is
immutable.
