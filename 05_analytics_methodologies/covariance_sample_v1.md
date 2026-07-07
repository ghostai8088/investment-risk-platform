# Methodology — Factor Covariance (equal-weighted unbiased sample estimator) v1

> **Model:** `risk.covariance.sample` · **Version:** `v1` · **Referent:** `model_version.methodology_ref` points here.
> **Status:** REGISTERED; `validation_status = UNVALIDATED` (recorded, **non-enforcing until P7**). This doc IS the methodology referent the governed `model_version` binds (P3-4, ENT-051, OD-P3-4-A/F/G).

## Purpose & applicability
The platform's third governed **risk** number: the **factor covariance matrix** — the
equal-weighted, unbiased (N−1) sample covariance of captured factor returns over an aligned
estimation window. This is the P3-5 parametric-VaR substrate (`σ_p² = x'Σx` needs Σ before it
needs x). The diagonal elements ARE the factor variances (no separate variance artifact).
Applicable to ≥ 2 pinned `factor` definitions (`DAILY` frequency, v1) each carrying a pinned
`SIMPLE`-return window of exactly the registered model version's declared `window_observations`
common dates.

**NOT applicable to** (deferred — see Known limitations): asset/instrument covariance;
EWMA/decay-weighted or shrinkage (Ledoit-Wolf) estimation; correlation-matrix output;
annualized covariance; VaR/ES/any consumer of Σ.

## Inputs & data policy
- **Inputs:** the selected `factor` EV definitions + each factor's captured `factor_return` FR
  window, pinned into a `COVARIANCE_INPUT` `dataset_snapshot` as `COMPONENT_KIND_FACTOR` (EV pin)
  + `COMPONENT_KIND_FACTOR_RETURN` (one component per factor: the ordered window rows — the
  curve header+nodes shape over FR rows) components. The compute reads **only** the pinned
  snapshot content — never a live factor/return read — so a result is reproducible under a later
  vendor supersede/correction of a window return (TR-09, test-proven).
- **Data policy (the OD-P3-0-L realization):** the estimation window `N` is **declared at model
  registration** (`window_observations=N` as a `model_assumption`) and is part of the version
  identity — the binder reads the DECLARED window; it is never a free request parameter.
  Alignment = the `N` most recent dates on which **every** selected factor has a current-head
  (or as-known-at) `SIMPLE` return — a set intersection. **Fail-closed: no imputation, no
  pairwise deletion** (pairwise covariance over unequal windows breaks positive
  semi-definiteness). Returns are `DAILY` `SIMPLE` decimal fractions (`0.01` = 1%).
- **Missing data:** fewer than `N` common dates refuses the snapshot build BEFORE any write
  (409); a consumed snapshot whose pinned series are short / misaligned / a different `N` /
  unpaired / non-`SIMPLE`/`DAILY` is a **pre-create refusal** (422) — zero run, zero rows.

## Formulas & numerical standards
For factors `i, j` over the aligned window `t = 1…N` (dates identical across series, verified at
adjudication AND re-verified by the kernel):

```
μ_i     = ( Σ_t r_i,t ) / N
cov_ij  = ( Σ_t (r_i,t − μ_i) · (r_j,t − μ_j) ) / (N − 1)          N ≥ 2
```

- **Grain:** one row per **canonical unordered factor pair** including the diagonal
  (`factor_id_1 ≤ factor_id_2`, lowercase-GUID string order; service-enforced) — `F·(F+1)/2`
  rows per COMPLETED run for `F` factors; the run is the matrix identity. Symmetry is **by
  construction** (each unordered pair is stored once), not by duplicate-row bookkeeping.
- **Units:** covariance of `DAILY` `SIMPLE` decimal-fraction returns — **UNANNUALIZED**
  (annualization is a later, declared transform; naive √252 scaling is a consumer decision that
  must be recorded where applied).
- **Rounding / precision:** computed in `Decimal` at 50-digit context precision;
  `quantize_HALF_UP` to 20 decimal places into `Numeric(38,20)` (a QS-04-style registered
  HALF_UP exception at a covariance-specific scale: second moments of O(1e-2) daily returns are
  O(1e-4)–O(1e-6) with meaningful structure far below the platform's 12dp column ceiling).
- **PSD:** the estimator is a Gram-form matrix ⇒ **positive semi-definite in exact arithmetic**;
  the 20dp quantization perturbs eigenvalues at O(1e-20). The numerical property is
  test-verified (eigenvalue floor `λ_min ≥ −1e-12·trace`), not runtime-enforced.
- **Rank:** the sample estimator has rank ≤ min(F, N−1) — for `F ≥ N` the matrix is singular
  (recorded limitation; use `F < N`).

## Assumptions
Mirrored content-identically into `model_assumption` rows on the registered version (the stored
rows use plain-ASCII spellings — `SUM`/`mu`/`-` for the Σ/μ/− below; plus the
registration-supplied `window_observations=N`):
- Equal-weighted UNBIASED sample covariance: `cov_ij = Σ_t((r_i,t − μ_i)(r_j,t − μ_j)) / (N − 1)`;
  `μ_i = Σ_t(r_i,t) / N`.
- Inputs: captured `SIMPLE` `DAILY` factor returns (decimal fractions); the window = the N most
  recent dates on which EVERY selected factor has a current-head return (set intersection);
  fewer than N common dates fails closed — NO imputation, NO pairwise deletion (pairwise breaks
  PSD).
- Units: DAILY, UNANNUALIZED covariance of SIMPLE returns (annualization is a later, declared
  transform).
- Computed in Decimal at 50-digit context precision; `quantize_HALF_UP` to 20 decimal places
  (the `Numeric(38,20)` column scale).
- PSD by construction (Gram form) in exact arithmetic; numerically verified by eigenvalue
  property tests + an independent `numpy.cov` cross-check (test-only dependency).

## Limitations
Mirrored content-identically into `model_limitation` rows (plain-ASCII spellings stored):
- **Factor-level covariance only** — NOT asset/instrument covariance (instrument return history
  requires adjusted/total-return prices; a named captured-data gap).
- **Equal weights only** — no EWMA/decay; no shrinkage (Ledoit-Wolf); each is a later,
  separately declared `model_version`. The sample estimator is rank-deficient for `F ≥ N` (use
  `F < N`).
- **No correlation-matrix output** (`statistic_type` `CORRELATION` reserved); no annualization.
- **No missing-data imputation:** a factor lacking a return on a window date fails the run
  closed.
- `validation_status = UNVALIDATED` — recorded, non-enforcing until the P7 validation workflow.

## Validation / reproduction tests
The five legs of the dual-path verification standing rule (its first mandatory application):
1. **Hand-computed exact references:** a 3-factor / 4-observation matrix computed by hand
   (ground truth independent of BOTH implementations) reproduced exactly at 20dp.
2. **Independent-implementation cross-check:** `numpy.cov(…, ddof=1)` on synthetic data agrees
   within relative ε = 1e-9 (numpy is a TEST-ONLY dependency; `irp_shared` runtime imports NO
   numpy — fence-tested).
3. **Eigenvalue PSD property test:** `λ_min ≥ −1e-12·trace` on representative + fixed-seed
   random matrices.
4. **Exact re-run reproducibility:** the same snapshot re-run yields byte-identical
   `covariance_value`s; the consume-existing path equals the build-in-request path.
5. **Pin invariance (TR-09):** the result is invariant under a post-pin vendor supersede AND
   correction of a window return (the FR pin captures the version consumed).

## Known limitations
This is the sample-estimator floor of the covariance substrate. Shrinkage, EWMA, correlation
output, annualization, asset-level covariance, a max-lookback bound on the common-date
intersection (sparse mismatched vendor calendars can reach far back — recorded risk), and every
consumer of Σ (parametric VaR at P3-5) are **out of scope for v1** and are taken up by later
slices under their own declared `model_version`s. A future `v2` referent must also carry forward
the standalone-spread CS01 limitation recorded for the sensitivity method family and the
beta-loading seam recorded for the factor-exposure family (the 2026-07-06 retrospective audit's
carry-forward rule); this `v1` referent is immutable.
