# P3-5 Implementation Plan — Parametric VaR (`var_result`, ENT-027)

> **Status: PLAN RATIFIED (OQ-P3-5-1…10 approved 2026-07-07); implementation is a SEPARATE approval.**
> Decision basis: `p3_5_decision_record.md` (OD-P3-5-A…N). Exemplars: the P3-4 covariance slice
> (`c2bd126`) for the binder/adjudication/review shape; P3-3 for the IA-row pin flavor.

## Part 0 — Preconditions (all satisfied at plan time)
- P3-3 (`7c50c43`) + P3-4 (`c2bd126`) CLOSED and CI-green — the exposure vector and Σ substrate exist as
  governed, snapshot-pinned, IA numbers. Head `0025_covariance`. No refactor pre-step required (the R0 helpers
  from P3-4 are the shared substrate; the run-scaffold extraction stays consciously deferred — a THIRD scaffold
  copy accrues here, recorded).

## Part 1 — Module map (what the implementation slice will touch)
- NEW `packages/shared-python/src/irp_shared/risk/var_kernel.py` — the pure kernel (no DB/IO/numpy).
- NEW `packages/shared-python/src/irp_shared/risk/var_service.py` — `run_var(...)` binder + readers.
- `risk/models.py` — `VarResult` (ENT-027; IA; event guards). `risk/events.py` — `RUN_TYPE_VAR`,
  `RISK_VAR_CREATE_EVENT_RESERVED`, `METRIC_TYPE_VAR_PARAMETRIC` (+ `ES` reserved), `VarActor`.
- `risk/bootstrap.py` — `VAR_MODEL_CODE="risk.var.parametric"`, declaration constants/prefixes
  (`confidence_level=` / `horizon_days=` / `z_score=`), `declared_var_parameters(session, version)` (strict
  parse → `WrongModelVersionError`), `register_var_model(..., confidence_level, horizon_days=1)` (vocabulary
  {0.95, 0.99} → the recorded z constants; identity conflicts 409).
- `snapshot/models.py|serialize.py|service.py` — `PURPOSE_VAR_INPUT`, `COMPONENT_KIND_FACTOR_EXPOSURE`,
  `COMPONENT_KIND_COVARIANCE`, `factor_exposure_content(row)` + `covariance_content(row)` serializers,
  `build_var_snapshot(exposure_run_id, covariance_run_id)` + `VarSnapshotError` +
  `VAR_BINDING_PREDICATE="v1:exposure-run-rows+covariance-run-rows"`, `_reresolve_content` handlers
  (tenant-predicated row re-reads; models-only function-local import of the RISK models — the P3-3
  exposure-atom precedent; the risk SERVICE is never imported).
- `migrations/versions/0026_var.py`; `apps/backend/src/irp_backend/api/risk.py` (register/run/read endpoints);
  `05_analytics_methodologies/var_parametric_v1.md`; `.github/workflows/ci.yml` (Var PG step); head flips
  0025→0026 + synthetic glob 0026→0027; tests `test_var.py` / `test_var_pg.py` / `test_var_endpoint.py`.

## Part 2 — `var_result` (ENT-027) table design
Columns: `id`/`tenant_id`/`system_from` (IA mixins) + NOT-NULL `calculation_run_id`/`input_snapshot_id`/
`model_version_id` (FKs; indexed) + `exposure_run_id`/`covariance_run_id` (NOT-NULL FKs →
`calculation_run.run_id`) + `metric_type String(30)` + `base_currency String(3)` +
`confidence_level Numeric(6,4)` + `horizon_days Integer` + `z_score Numeric(20,12)` +
`sigma Numeric(28,6)` + `var_value Numeric(28,6)` + `n_factors Integer` + `n_observations Integer` +
`window_start/window_end Date`. UNIQUE `(calculation_run_id, metric_type)`. IA TRUE append-only
(`APPEND_ONLY_TABLES` + P0001 + ORM guards); symmetric FORCE RLS; NEVER hybrid.

## Part 3 — `run_var(...)` binder (the hardened P3-4 shape)
```
run_var(session, *, acting_tenant, actor, code_version, environment_id, model_version_id,
        exposure_run_id=None, covariance_run_id=None, snapshot_id=None) -> VarRunResult
```
- **(a) pre-create gate** (⇒ ZERO run/rows/run-audit): prereqs truthy; `assert_model_version_of(...,
  VAR_MODEL_CODE)`; `declared_var_parameters` (strict digits/decimal parse; malformed/absent/ambiguous ⇒
  `WrongModelVersionError`). Build path: resolve BOTH runs own-tenant (`resolve_factor_exposure_run` /
  `resolve_covariance_run` — REUSED), each COMPLETED; then `build_var_snapshot(...)`. Consume path:
  `resolve_snapshot` + `purpose == PURPOSE_VAR_INPUT`.
- **(b) pinned-content adjudication — BOTH paths, pre-create**: parse pins; ≥1 FACTOR_EXPOSURE row; ≥1
  COVARIANCE row; uniform `base_currency` across exposure rows; covariance rows uniform
  `statistic_type='COVARIANCE'`/`return_type='SIMPLE'`/`frequency='DAILY'`/window; all exposure rows from ONE
  run and all covariance rows from ONE run (no mixed-run smuggle); **coverage**: every exposure `factor_id`
  (lowercased) ∈ the covariance factor set, and every needed canonical pair present. Any defect ⇒
  `VarInputError` (422).
- **(c) run** — `create_run(run_type=RUN_TYPE_VAR, ...)` → RUNNING; **(d)** DEPENDS_ON before the gate.
- **(e) compute** — the pure kernel over parsed pins ONLY: `x_i = Σ exposure_amount` per factor;
  `radicand = xᵀΣx` (Decimal-50); the OD-P3-5-G tolerance (`[−tol,0) → 0`; `< −tol` → gate defect);
  `σ_p = radicand.sqrt()`; `var = z·σ_p`; both `quantize_HALF_UP(…, 6)`.
- **(f) defensive post-compute gate** — rule `risk.var.completeness`: non-finite σ/VaR or radicand < −tol ⇒
  `DataQualityError` ⇒ FAILED run + evidence + zero rows (reason names the radicand).
- **(g) governed write** — ONE row + flush + ORIGIN + COMPLETED.

## Part 4 — Kernel formulas + verification (the dual-path contract)
```
x_i       = Σ_rows(factor i) exposure_amount              (base currency, signed)
radicand  = Σ_i Σ_j x_i·σ_ij·x_j                          (σ_ij symmetric from canonical pairs)
σ_p       = sqrt(radicand)      VaR_α = z_α · σ_p         (h = 1; zero mean)
```
- Decimal `localcontext(prec=50)`; outputs HALF_UP-6 (`Numeric(28,6)`).
- **Verification legs:** (1) hand-computed exact rational reference (2-factor + 3-factor cases, incl. an
  offsetting-x near-null case exercising the tolerance); (2) `numpy` float cross-check
  (`z*sqrt(x@S@x)`, ε_rel 1e-9, TEST-ONLY); (3) properties: positive homogeneity `VaR(λx)=λ·VaR(x)` (exact
  unrounded/for σ; within (λ+1)/2 quanta after rounding), confidence monotonicity (z₉₉ > z₉₅ ⇒ VaR₉₉ > VaR₉₅ for σ>0), σ_p invariant under exposure-row
  ORDER; (4) z-constant verification: `Φ(z)=(1+erf(z/√2))/2` reproduces α to 1e-12 (stdlib `math.erf`) +
  the literature values quoted in the methodology; (5) exact re-run + consume≡build + pin invariance under an
  upstream exposure/covariance RE-RUN (new upstream runs must not move a pinned VaR).

## Part 5 — Snapshot extension
- `factor_exposure_content(row)` / `covariance_content(row)`: the full immutable column sets (id, tenant, run
  ids, factor identities, amounts/values at column scale, window fields) — IA rows ⇒ byte-stable re-verification.
- `build_var_snapshot`: list both runs' rows via the EXISTING readers (`list_factor_exposures` /
  `list_covariances` — tenant-predicated), refuse empty sets pre-write, pin one component per row
  (`target_entity_type` = the source table name; IA pin coords: `pinned_system_from` only).
- `_reresolve_content` handlers re-read rows by id (tenant-predicated, function-local models-only import);
  gone/cross-tenant ⇒ drift.

## Part 6 — Methodology doc (`var_parametric_v1.md`)
The §-template: purpose (parametric delta-normal 1-day VaR; the first composed governed number); inputs + data
policy (two COMPLETED governed runs; coverage subset rule; NO imputation); formulas + numerical standards (Part 4;
the radicand tolerance DECLARED); assumptions (mirrored + the registration declarations); limitations
(**specific risk = 0** — first-class; normality; 1-day; parametric-only; sample-Σ estimation error inherited;
UNVALIDATED until P7); validation legs (Part 4's five); known limitations + scope-out (ES/historical/MC/√h/
component-VaR/backtesting/quantile-function).

## Part 7 — Tests
1. Kernel: hand references (incl. near-null tolerance case); homogeneity; monotonicity; order-invariance;
   numpy cross-check; erf round-trip of z constants; radicand-below-tolerance defect signal.
2. Governance: unregistered/wrong-family refused; malformed/absent/ambiguous declarations refused (via the
   generic registration path — the P3-4 lesson); registration idempotent + 409 on identity drift; vocabulary
   floor (confidence ∉ {0.95,0.99} refused at registration).
3. Full stack: hand-reference VaR through `run_var`; bindings; single row; window echo columns match the
   covariance run.
4. Adjudication fail-closed (both paths; hand-minted snapshots for what the builder can't produce): coverage
   gap; mixed-run rows; non-uniform base_currency; wrong vocab; wrong purpose; unknown/cross-tenant ids.
5. Reproducibility: exact re-run; consume≡build; invariance under upstream re-runs + a factor amend.
6. IA/RLS/lineage/audit/entitlement parity (the P3-4 group verbatim); `RISK.*` zero-emission; no new permission.
7. Fences: no live readers in the compute path (found-set asserted); no runtime numpy/scipy (population-asserted);
   no historical/monte_carlo/simulation/es/backtest identifiers; head `0026_var` + flips.
8. Endpoint: register (409/422 arms)/run/read; 403 deny + view-cannot-run; FAILED surfaced; fixed-point
   serialization; no mutating verbs (all route families).

## Part 8 — Acceptance criteria (REQ-MKT-001 partial)
- VaR reproduces the hand references exactly at 6dp and matches numpy within ε_rel 1e-9; re-run identical;
  methodology doc + inventory entry ship with the slice (the REQ's own acceptance text).
- The critical invariant holds; coverage/consistency gates fail closed on both paths; IA + RLS PG-proven;
  no new permission; `audit/service.py` untouched; head `0026_var`; ENT-027 realization + amendments land with
  the no-status-decay flips. REQ-MKT-001 → In-Progress (partial); historical/MC/ES legs stay named-open.

## Part 9 — Review log
Shared with `p3_5_decision_record.md` Part 5 (single-pass; folds applied there). The implementation slice gets
the independent-context adversarial review (the plan-Part-11 gate, the P3-4 precedent).

## Part 10 — Risks & open questions
- **The specific-risk hole is the big honesty risk** — a CURRENCY-factor-only linear model has zero
  idiosyncratic variance; the methodology states it in the first limitation and the API docstring carries it.
- **Near-null radicand** — bounded + declared (OD-P3-5-G); the tolerance derivation is itself reviewed.
- **Third run-scaffold copy** accrues (recorded; the extraction is a standing deferral — revisit at P3-6).
- **Open (settled at build):** exact endpoint DTO shapes; whether `sigma` gets its own read filter.

## Part 11 — Implementation kickoff prompt (when approved)
STEP P3-5: build EXACTLY per `p3_5_decision_record.md` (OD-P3-5-A…N) + this plan. Validate (full suite + full-PG
+ migration cycle + drift + downgrade smoke), run the independent-context adversarial review (/code-review ultra
or authorized subagents), fold, HOLD the commit for explicit approval (Tier 2). Then push + CI-watch + the
Tier-0 closeout (memory refresh + record stamp + decay flips).
