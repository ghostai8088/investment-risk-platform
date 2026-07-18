# RS-1 Implementation Plan — residual shrinkage + EWMA (the OD-E/OD-G residual-estimator v2s)

Companion to `rs_1_decision_record.md`. Sized **M/L**. NO migration (head stays `0041_es_historical`).
The two estimators enter at DIFFERENT layers: EWMA is a kernel-level weighting; shrinkage is a cohort
transformation over already-computed raw σ_e's. The OLS regression output and every downstream number are
byte-preserved.

## Step sequence

**1 — EWMA in the kernel (OD-A).** In `proxy_weight_kernel.py`, edit the :128-136 region with the `s2`
DECOUPLING (the verifier's load-bearing catch): **KEEP `s2 = ss_res/(n−m)` (:129) — `std_errors` (:134-136)
consumes it and OLS coefficient inference must use the classical variance, never a decayed one.** Add a
SEPARATE `residual_var` that dispatches on an optional `decay_lambda`: `None` ⇒ `residual_var = s2` (the raw
v1 path, `residual_stdev` BYTE-IDENTICAL); a Decimal λ∈(0,1) ⇒ `residual_var = Σ_t w_t·e²_t`,
w_t = (1−λ)λ^{n−t}/(1−λ^n) over the residual vector in time order (most-recent-last). `residual_stdev =
residual_var.sqrt()` (:130). Net: on BOTH paths the design matrix / betas / residual vector (:107-126),
`std_errors` (:134-136), and `r_squared` (:131, on `ss_res/ss_tot`) are byte-identical; only `residual_stdev`
diverges on the EWMA path. Prec-50, the existing terminal quantize. The effective-sample-size 1/Σw_t² is a
limitation-doc quantity, NOT persisted (no `OlsEstimate` shape change).

**2 — The EB shrinkage transformation (OD-B).** New `residual_shrinkage_kernel.py` (pure, prec-50,
deterministic Decimal — no float, no nondeterministic tie-break, the fit must byte-reproduce): given a cohort
of `(instrument, raw_residual_stdev, n_obs, n_reg)` — **SQUARE each stored `residual_stdev` to a variance
s²_i** (the stored quantity is a stdev, `models.py:470` — the verifier's unit catch) — refuse if the cohort
size N < 3 (`ResidualShrinkageCohortError`, the OD-B fail-closed floor); then compute σ²_pool = mean(s²_i),
per-instrument sampling variance v_i = 2·s⁴_i/(n_obs_i − n_reg_i), v̄ = mean(v_i), S²_cross = the
cross-sectional sample variance of the s²_i, τ² = max(0, S²_cross − v̄), per-instrument w_i = v_i/(v_i+τ²)
(guard the τ²=0 → w_i=1 all-shrink and the v_i=0 → w_i=0 no-shrink edges), σ²_e,i(shrunk) = w_i·σ²_pool +
(1−w_i)·s²_i, then **SQRT back** to a per-member shrunk `residual_stdev`; return the per-member shrunk stdevs
+ w_i + the pinned pool/τ². No declared intensity, no OLS, no I/O.

**3 — The declared-identity gate (OD-C).** In `bootstrap.py`, add `PROXY_WEIGHT_EWMA_CONVENTION =
"EWMA_RISKMETRICS"`, `PROXY_WEIGHT_SHRINKAGE_EB_CONVENTION = "SHRINKAGE_CROSS_SECTIONAL_EB"`, the
`decay_lambda=` prefix (EWMA only — the EB shrinkage carries NO numeric literal, method-as-identity), and
`declared_proxy_weight_parameters` (ADAPTS `declared_es_hs_parameters` :1112 — strict well-formedness for a
PRESENT literal, but `estimator_convention` is OPTIONAL with a RAW default: absent ⇒ the implicit `RAW` v1
byte-preserved; malformed ⇒ `WrongModelVersionError`; the deliberate inversion of the es_hs required-literal).
Add the `_ResidualEstimator` registry map (RAW/EWMA_RISKMETRICS/SHRINKAGE_CROSS_SECTIONAL_EB → compute path),
the `_HS_FAMILIES` shape. Two new registrars `register_proxy_weight_ewma_model` (stamps `decay_lambda`) /
`register_proxy_weight_shrinkage_eb_model` (stamps the method only); same-label-different-declaration ⇒ 409
`ModelVersionConflictError`.

**4 — The service + snapshot plumbing (OD-B/OD-D).** `proxy_weight_service.py`: on a bound EWMA version,
parse `decay_lambda` and pass it to `estimate_ols` (the run rides the EXISTING estimate endpoint). New
`residual_shrinkage_service.py::run_residual_shrinkage`: take an explicit cohort of promoted proxy-weight
estimate runs, build + pin a `PURPOSE_RESIDUAL_SHRINKAGE_INPUT` snapshot over each member's raw s²_i AND its
residual df (n_obs, n_reg — the EB fit needs them; the pin must be self-sufficient to recompute w_i) (new
builder + `RESIDUAL_SHRINKAGE_BINDING_PREDICATE = "v1:cohort-residual-variances+dof"` added to the
`_BINDING_PREDICATES` tuple, `snapshot/service.py:2666` — 32 chars ≤ the varchar(50) assert), compute via the
kernel, and persist one shrunk-σ_e `ProxyWeightEstimateResult` (`ESTIMATION_SUMMARY` row) per member,
RUN/SNAPSHOT/MODEL-bound. NO new column; NO new pin serializer key.

**5 — The API (OD-D).** `apps/api` (or the router home): `POST /risk/models/proxy-weight-ewma`,
`POST /risk/models/proxy-weight-shrinkage-eb`, `POST /risk/residual-shrinkage/runs`. The proxy-weight estimate
RUN endpoint is unchanged (dispatches on the bound version). Reads unchanged.

**6 — Constants + docs (OD-F).** The new dossier limitation rows (EWMA: effective-sample-size, declared-λ,
biased/zero-mean; EB SHRINKAGE: comparable-cohort, min-cohort-fail-closed (N≥3), Gaussian-sampling-variance,
equal-weighted-pool-v2) under the HG-1 fence. Reword `VAR_TOTAL_LIMITATIONS`/`ES_TOTAL_LIMITATIONS` "v2s" rows
→ REALIZED (new registrations) — but PRESERVE the still-open calendar-aware clause bundled in the ES_TOTAL row
(split if needed). Dated amendment to `pa_4_decision_record.md` discharging the raw-sample-σ_e limitation. New
referent `05_analytics_methodologies/residual_estimation_v1.md` (Part-2 citations at honest grades — pin the
RiskMetrics §-number against the primary here; L-W explicitly NOT cited; USE4-faithful on the EB intensity,
the cap-weighted-pool + RMSE-fitted-λ forms disclosed as v2s).

**7 — The demo TRIGGERED re-validation (OD-E).** `demo/rs1_stage5.py` + `scripts/run_demo_rs1.py`: register
the two versions for the demo tenant; **grow the equity sleeve additively to N≥3 comparable equities** (one or
two new listed-equity instruments + their per-instrument raw estimation chain — so the EB fit is genuine, not
a floor case); re-estimate under EWMA (declared λ); run the EB shrinkage over the ≥3-equity cohort (the
corporate bond EXCLUDED + asserted-raw — the comparable-group rule); run a fresh total-VaR/ES-total bound to
the flagship downstream versions; file the TRIGGERED re-validations (freshly-drafted closing conditions,
conditions-grep flips) + the INITIAL dossiers for the two new versions. Additive, single-commit,
refuse-not-skip. CI slot after stage 4, before the downgrade smoke; filename `test_demo_stage5_rs1*.py`.

**8 — Tests + battery.** Kernel: the EWMA weight-sum/λ→1⁻-limit/most-recent-orientation goldens + the raw
path byte-regression against the shipped PA-3 goldens; the EB shrinkage — a hand-derived multi-instrument
golden (w_i heterogeneous by df), the τ²=0 all-shrink and v_i=0 no-shrink edges, and the N<3 fail-closed
refusal. Service: the parse-gate (each malformed/absent/ambiguous case), the raw-v1 grandfather, **the EB fit
reproducibility (recompute τ²/v_i/w_i/blend from the pin alone → byte-identical)**, the 409 twin. Demo:
stage-5 conformance (the new dossier fence) + the conditions-grep flip. `make check`, full local-PG fresh,
`alembic check` (expect no-op — no migration), downgrade smoke unaffected.

## Review composition (OD-G)
The ratified 4-finder shape (decision record Part 5): adversarial (dispatch + cohort pin + can the EB fit be
made non-reproducible?) · numeric (both estimators — the EWMA weights AND the EB w_i/τ²/v_i, hand +
exact-rational + fuzz over λ, cohort size, df spread) · doctrine (dossier texts + citation dispositions + the
dated discharge + USE4-faithful claim) · scope-fence (OD-G clause-by-clause). Proportionate to M/L; the
numeric finder warrants Opus/High (the EB fit is the one genuinely new piece of math); other finders all-Fable
acceptable (the MG-1 budget rule; Opus is the fallback).

## Verification appendix (the standing planning pass)
Runs BEFORE ratification (decision record Part 5). Confirms the NO-migration claim, the OLS byte-preservation,
the downstream zero-math-change, the citation grades (esp. L-W-not-used), and the raw-v1 grandfather. Findings
fold into the decision record before "Approve all."
