# P3-5 Decision Record — Parametric VaR (ENT-027 `risk_result` realized)

| Field | Value |
|---|---|
| Status | **PLANNING RATIFIED** — OQ-P3-5-1…10 approved by the user at the commit gate (2026-07-07); implementation is a SEPARATE approval |
| Date | 2026-07-07 |
| Basis | `p3_0_decision_record.md` (OD-P3-0-A…N — VaR is LAST of the core numbers, the highest bar) + `p3_implementation_plan.md` P3-5 row + Part 3 contracts; the P3-3/P3-4 hardened exemplars (`7c50c43`, `c2bd126`) |
| Grounding | Verified against shipped HEAD `c2480a4` (CI #99/#100 chain): `factor_exposure_result` (ENT-028 family; per-atom CURRENCY-family allocation rows; `exposure_amount Numeric(28,6)` signed, base currency; run-uniform `base_currency`) + `covariance_result` (ENT-051; canonical-pair sample covariance of SIMPLE/DAILY returns at `Numeric(38,20)`; per-run uniform `n_observations`/`window_start`/`window_end`; PSD by Gram construction) + the window-as-version-identity precedent (OD-P3-4-G) + `PreciseDecimal` + the R0 shared helpers. `Decimal.sqrt()` is exact-to-context (verified prec-50). |
| Sign-off | **OQ-P3-5-1…10 — APPROVED / RATIFIED by the user (2026-07-07: "agree with your recommendation on parametric first … Good with all of your other recommendations. Proceed.").** The user additionally set a **directional roadmap**: factor-based historical simulation AND Monte-Carlo VaR are WANTED later method slices — committed direction, not open deferrals (each still its own registered model family/version + separately planned slice; MC additionally gated on a seeded simulator + revaluation engine). |

---

## Part 1 — Decisions at a glance

| ID | Decision | Summary |
|---|---|---|
| **OD-P3-5-A** | v1 method | **Parametric (delta-normal, zero-mean) 1-day portfolio VaR** under the linear factor model `ΔV = Σ_i x_i·r_i`: `x` = the per-factor CURRENCY-exposure totals of a COMPLETED FACTOR_EXPOSURE run (base currency); `r` covariance = a COMPLETED COVARIANCE run (Σ). **NOT historical** — split honestly: *full-revaluation* historical VaR IS data-blocked (needs position-level return history / adjusted prices — a named gap), but ***factor-based historical simulation* is FEASIBLE today** (`P&L_t = Σ_i x_i·r_i,t` over the pinned windows; empirical quantile) and is deferred by PREFERENCE, not by data: a 99% empirical quantile from an N≈60 window is far noisier than a parametric estimate using all N points through Σ, and it would bypass the P3-4 covariance substrate rather than consume it (the composition thesis). Recorded as the nearest-next method. **NOT Monte-Carlo** (needs seeded simulation + revaluation; binds `random_seed` QS-18 when it arrives), **NOT ES** (closed-form seam recorded, deferred). "Pluggable" (the P3-0 row) = each method is its own registered model family/version — v1 ships ONE. |
| **OD-P3-5-B** | entity | **ENT-027 `risk_result` REALIZED as `var_result`** — the platform's first **single-summary-row** governed result: ONE row per COMPLETED run (grain `(calculation_run_id, metric_type)`); `metric_type='VAR_PARAMETRIC'` (`ES_PARAMETRIC` reserved — extend by value). No new canonical id (ENT-027 exists — "immutable result rows linked to a run"). |
| **OD-P3-5-C** | columns | Run/snapshot/model bindings (the P3-1/3/4 shape) + **`exposure_run_id` + `covariance_run_id` provenance columns (hard FKs → `calculation_run.run_id`)** + self-describing captured descriptors: `base_currency`, `confidence_level Numeric(6,4)` (fraction), `horizon_days Integer` (=1), `z_score Numeric(20,12)` (the declared constant), `sigma Numeric(28,6)` (currency), `var_value Numeric(28,6)` (currency; positive = potential loss), `n_factors Integer`, + the covariance window echo (`n_observations`, `window_start`, `window_end`). |
| **OD-P3-5-D** | confidence/horizon as version identity | The OD-P3-4-G precedent extended: **`confidence_level=`, `horizon_days=`, `z_score=` are registration-declared `model_assumption`s and part of the version identity** (strict parse; a malformed/absent declaration = `WrongModelVersionError`; a same-label re-register with a different declaration = 409). v1 confidence vocabulary = **{0.95, 0.99}** with REGISTERED z constants (dual-sourced from published standard-normal tables, recorded to 12dp: 1.644853626951 / 2.326347874041). **NO runtime inverse-normal-CDF** — implementing one is a separately verified numerical method (capability-is-not-evidence); deferred. |
| **OD-P3-5-E** | statistical assumptions | **Zero-mean** delta-normal (declared); joint normality of factor returns (declared limitation); `horizon_days = 1` FIXED in v1 (the covariance is daily/unannualized — `√h` scaling is a recorded seam, NOT implemented). |
| **OD-P3-5-F** | formula + numerics | `σ_p = sqrt(xᵀΣx)` in Decimal prec-50 (`Decimal.sqrt` is correctly rounded to context); `VaR = z_α · σ_p` (h=1); outputs `quantize_HALF_UP(…, 6)` into `Numeric(28,6)` (the currency scale — no new precision departure). `x_i` = the deterministic Σ of the pinned exposure rows per factor (test-asserted against the pinned atoms). |
| **OD-P3-5-G** | radicand quantization floor | Σ is PSD in exact arithmetic but stored at 20dp — for near-null-space `x` (offsetting exposures on near-perfectly-correlated factors) the quantized radicand can be a TINY negative. **Declared tolerance:** radicand in `[−tol, 0)` with `tol = F² · max_i(x_i²) · 1e-19` (the 20dp-quantum bound) → treated as 0 (σ_p = 0); radicand `< −tol` → the defensive **post-create FAILED** gate (evidence recorded). The clamp bound is a declared assumption, not a silent fix. |
| **OD-P3-5-H** | input adjudication (both paths, pre-create) | Exposure run: own-tenant, `run_type='FACTOR_EXPOSURE'`, COMPLETED, ≥1 row, uniform `base_currency`. Covariance run: own-tenant, `run_type='COVARIANCE'`, COMPLETED, `statistic_type='COVARIANCE'`/`SIMPLE`/`DAILY`, uniform window. **Coverage:** every exposure `factor_id` MUST be in the covariance factor set (subset — the covariance may cover more; a missing factor = pre-create refusal, NO zero-variance imputation). Every needed pair exists by the F·(F+1)/2 construction once the subset holds (adjudicated anyway). |
| **OD-P3-5-I** | snapshot | **Mint `PURPOSE_VAR_INPUT` + `COMPONENT_KIND_FACTOR_EXPOSURE` + `COMPONENT_KIND_COVARIANCE`** (the IA-row pin flavor — both source rows are TRUE append-only; drift impossible by construction). `build_var_snapshot(exposure_run_id, covariance_run_id)` pins every consumed result row; binding predicate `"v1:exposure-run-rows+covariance-run-rows"`. **NO `COMPONENT_KIND_FACTOR` pin** — both result-row types carry `factor_id`+`factor_code` (self-describing; no live factor read exists in the compute). Compute reads ONLY pinned content. |
| **OD-P3-5-J** | failure model | The P3-3/P3-4 shape verbatim: pre-create refusal (prereqs/model-identity/declared-parse/adjudication) = ZERO run/rows/audit, BOTH entry paths (build-in-request `exposure_run_id`+`covariance_run_id`, or consume-existing `snapshot_id`); post-create FAILED = the OD-P3-5-G defensive gate (committed FAILED run + DQ evidence + zero rows); emit-path raises roll back co-transactionally. |
| **OD-P3-5-K** | audit + entitlement | `RISK.VAR_CREATE` **reserved-not-emitted** @ EVT-220 (the row grows a third code); `CALC.RUN_*` + `MODEL.*` reuse; `audit/service.py` FROZEN. **`risk.view`/`risk.run` REUSED** — no new permission; registration reuses `model.inventory.register`. |
| **OD-P3-5-L** | migration + CI | `0026_var` (`var_result` + symmetric FORCE RLS + P0001 trigger; the 0022/0024/0025 template); head-assertion flips 0025→0026 (+ the synthetic glob 0026→0027); `test_var_pg.py` CI step lands WITH the implementation. |
| **OD-P3-5-M** | model + methodology | `risk.var.parametric` v1; `methodology_ref` → `05_analytics_methodologies/var_parametric_v1.md` (the §-template); assumptions mirror the declarations (confidence/horizon/z/zero-mean/linear-model/radicand-tolerance); limitations: **specific/idiosyncratic risk = 0** (the allocation-v1 indicator-loading limitation PROPAGATES — no residual variance term), normality, 1-day-only, parametric-only, single-confidence-per-version, sample-Σ estimation error inherited, UNVALIDATED until P7. |
| **OD-P3-5-N** | requirements | **REQ-MKT-001 → In-Progress (partial) at the implementation slice** (the parametric leg; acceptance "VaR matches reference within ε; re-run identical; methodology doc + inventory entry" — the dual-path discharge). Historical/MC/ES legs stay open; the REQ does NOT close. |

---

## Part 2 — Decision detail (the non-obvious ones)

### OD-P3-5-A — why parametric delta-normal is the honest v1
The methods differ in input depth AND statistical footing. *Full-revaluation* historical VaR is data-blocked
(needs position-level return history / adjusted prices). ***Factor-based* historical simulation is NOT
data-blocked** — it runs on the same pinned windows — and is rejected on the merits, recorded honestly: (1) at
the declared window sizes (N≈60) a 99% empirical quantile sits in the extreme tail of the sample and is
substantially noisier than the parametric estimate, which uses every observation through Σ; (2) it would consume
the raw return windows and BYPASS the P3-4 covariance run — leaving the just-shipped substrate without its
designed consumer and violating compose-don't-rederive. It is the nearest-next deferred method (its quantile
interpolation convention would be a new declared assumption). Monte-Carlo needs a seeded simulator + a
revaluation engine (absent; `random_seed` is the QS-18 seam). Parametric delta-normal needs exactly what
P3-3 + P3-4 shipped: an exposure vector and a covariance matrix — both governed, snapshot-pinned, IA-immutable.
The result is the FIRST derived-of-derived governed number (two upstream governed runs as inputs) — the platform
thesis: composition without re-derivation. The price is the normality assumption, declared as a limitation.

### OD-P3-5-D — why declared z constants, not an inverse CDF
An inverse-normal-CDF (Acklam/BSM/erfinv) is itself a numerical method with its own error bounds — shipping one
"because the model can write it" violates capability-is-not-evidence. v1 declares an enumerated confidence
vocabulary with z constants recorded to 12dp, dual-sourced from published tables and cross-checked in tests
against `scipy`-independent references (numpy has no ppf; the test uses the recorded literature values +
`math.erf` round-trip verification: `Φ(z) = (1+erf(z/√2))/2` must reproduce α to 1e-12). A runtime quantile
function is a later, separately verified slice.

### OD-P3-5-G — why a declared radicand tolerance instead of fail-always or clamp-always
Exact-arithmetic PSD guarantees `xᵀΣx ≥ 0`; the 20dp quantization of Σ perturbs each element by ≤ 5e-21, so the
radicand can dip below zero by at most `F²·max(x_i²)·5e-21` for adversarially offsetting `x`. Failing every tiny
negative would fail honest portfolios on a storage artifact; clamping unboundedly would hide real defects. The
declared bound (`1e-19` headroom over the quantum) separates the two regimes and is itself a mirrored assumption.

### OD-P3-5-I — why no FACTOR definition pin
P3-3/P3-4 pinned `factor` EV definitions because their computes needed definition attributes (family scope,
frequency). The VaR compute needs only the factor IDENTITY to join `x` to Σ — and both pinned row types carry
`factor_id` + `factor_code` verbatim. Pinning definitions would add drift surface without adding reproducibility.

### OD-P3-5-C — why hard-FK provenance run columns
`factor_exposure_result`/`covariance_result` rows already FK their own runs; `var_result` additionally carries
WHICH exposure run and WHICH covariance run fed it. `calculation_run.run_id` is unique and never deleted (IA
status-mutable), so hard FKs are safe and make the provenance queryable without parsing the snapshot.

---

## Part 3 — Governance amendments (folded at the implementation slice, R-07)
- **Canonical model** — ENT-027 `risk_result` row annotated **REALIZED as `var_result`** (single-summary-row; no new id).
- **Audit taxonomy** — the RISK/EVT-220 row gains `RISK.VAR_CREATE` reserved-not-emitted; `audit/service.py` FROZEN.
- **Entitlement** — the `risk.view`/`risk.run` row extended with the VaR REUSE note (no code change).
- **Control matrix** — a P3-5 block: CTRL-003 (fourth model family, identity-checked incl. the declared confidence/horizon/z); CTRL-002/014 (methodology + mirrored declarations); CTRL-009/017/018/TR-13 (governed output; IA; dual-path reproduction); CTRL-006/013 (lineage); CTRL-011/023 (RLS); CTRL-026 (CALC.RUN_*); CTRL-029/032 (fail-closed coverage/consistency adjudication + the radicand gate). No new CTRL.
- **Temporal standard** — a P3-5 realization note: `var_result` IA TRUE append-only (ENT-027).
- **Methodology home** — add `05_analytics_methodologies/var_parametric_v1.md`.
- **RTM** — **REQ-MKT-001 → In-Progress (partial)** (parametric leg; historical/MC/ES named open legs).
- **Snapshot kinds** — `COMPONENT_KIND_FACTOR_EXPOSURE` + `COMPONENT_KIND_COVARIANCE` + `PURPOSE_VAR_INPUT` (app constants).
- **No-status-decay checklist** — at implementation close, flip every planning-era qualifier introduced here.

---

## Part 4 — Open decisions (OQ-P3-5-1…10) — **APPROVED / RATIFIED by the user (2026-07-07, the plan-commit gate)**
**Status: RATIFIED.** The ten defaults below are fixed inputs to the P3-5 implementation; no open question remains for the build. *(The original recommendations are retained verbatim.)*
- **OQ-P3-5-1 — recommend APPROVE (the central one).** v1 = parametric delta-normal 1-day VaR (OD-P3-5-A); historical/MC/ES each a DEFERRED named method (own model family/version); "pluggable" realized as the registry, not three engines.
- **OQ-P3-5-2 — recommend APPROVE.** ENT-027 realized as `var_result` single-summary-row; grain `(calculation_run_id, metric_type)`; `VAR_PARAMETRIC` (+`ES_PARAMETRIC` reserved). (OD-P3-5-B/C.)
- **OQ-P3-5-3 — recommend APPROVE.** Confidence/horizon/z as registration-declared version identity; vocabulary {0.95, 0.99}; NO runtime inverse-CDF; the `math.erf` round-trip + literature dual-check in tests. (OD-P3-5-D.)
- **OQ-P3-5-4 — recommend APPROVE.** Two-completed-governed-runs input; the coverage subset rule (exposure factors ⊆ covariance factors), fail-closed, both paths. (OD-P3-5-H.)
- **OQ-P3-5-5 — recommend APPROVE.** `PURPOSE_VAR_INPUT` + the two IA-row component kinds; NO factor-definition pin; compute from pins only. (OD-P3-5-I.)
- **OQ-P3-5-6 — recommend APPROVE.** Decimal-50 + `Decimal.sqrt`; HALF_UP-6 `Numeric(28,6)` outputs; the DECLARED radicand quantization-floor tolerance (clamp within; FAILED below). (OD-P3-5-F/G.)
- **OQ-P3-5-7 — recommend APPROVE.** Zero-mean + normality declared; **specific-risk = 0 recorded as a first-class limitation** (propagated from allocation v1); h=1 only (√h a recorded seam). (OD-P3-5-E/M.)
- **OQ-P3-5-8 — recommend APPROVE.** `RISK.VAR_CREATE` reserved; `risk.*` REUSED; migration `0026_var` + the Var PG CI step with the implementation. (OD-P3-5-K/L.)
- **OQ-P3-5-9 — recommend APPROVE.** Dual-path verification: hand-computed exact rational references; `numpy` float cross-check (ε_rel 1e-9, TEST-ONLY, fence extended); positive-homogeneity (`VaR(λx) = λ·VaR(x)`) + confidence-monotonicity property tests; exact re-run; pin invariance under upstream re-runs.
- **OQ-P3-5-10 — recommend APPROVE.** The deferral register: ES (closed-form seam `ES = σ·φ(z)/(1−α)` recorded); **factor-based historical simulation (FEASIBLE with current data — deferred by preference, the nearest-next method; RATIFICATION NOTE 2026-07-07: user-directed ROADMAP item, to be planned as its own method slice)**; full-revaluation historical (data-blocked); **MC (+`random_seed`; RATIFICATION NOTE: user-directed ROADMAP item — gated on a seeded simulator + revaluation engine)**; √h multi-horizon; component/marginal VaR; backtesting (P7-adjacent); the specific-risk term; runtime quantile function.

---

## Part 5 — Adversarial review log (8 lenses, disciplined single-pass)
Planning documents take the disciplined single-pass floor (implementation slices get the independent-context
review). Each lens re-verified against shipped HEAD `c2480a4` — symbols, column names/scales, run types, the
canonical-pair storage, and the deferral registers read from the repo, not recalled.

| Lens | Outcome |
|---|---|
| Product/Requirements | REQ-MKT-001's own acceptance text drives the plan (reference-match ε + re-run + doc + inventory); the partial advance is honest (one of four legs); no other REQ moves. **Folded:** the "pluggable" wording reconciled to registry-pluggability so the RTM cannot read three engines into v1. |
| Chief-Architect | The first two-upstream-runs consumer: verified both provenance ids are FK-able (`calculation_run.run_id` unique); verified the binder shape carries over (uniform both-path adjudication; the run-scaffold extraction deferral noted a THIRD copy accrues — accepted consciously, recorded). **Folded:** the consume-path `snapshot_id` mode adjudicates pinned rows identically (no smuggled mixed-run snapshots). |
| Data-Architecture | ENT-027 realization honest (no new id); single-summary-row is a NEW result shape — verified the grain/uniqueness story and the metric_type extend-by-value seam; window echo columns denormalize run-uniform covariance facts (self-describing precedent). No defect. |
| Security/RLS | Symmetric FORCE RLS; never hybrid; tenant-predicated resolution everywhere; the two upstream runs resolve own-tenant fail-closed; opaque errors. No defect. |
| Audit/Controls | Third reserved RISK.* code; CALC.RUN_*/MODEL.* reuse; the declared-parameter identity extends CTRL-003 the same way OD-P3-4-G did. No defect. |
| Lineage/Data-Quality | Coverage subset rule is the fail-closed analogue of P3-4 alignment (no imputation); IA-row pins make drift impossible by construction; DEPENDS_ON-before-gate carried. **Folded:** the radicand tolerance made a DECLARED assumption (OD-P3-5-G) instead of an implementation detail. |
| Model-Governance/Quant | z-constants-not-inverse-CDF is the capability-is-not-evidence discharge; zero-mean and normality declared; specific-risk-=0 elevated to a first-class limitation (it is the LARGEST honesty gap of this number); the σ_p math verified dimensionally (currency × return² × currency = currency²). **Folded:** the erf round-trip test leg added so the z constants are verified, not trusted. |
| Scope | Planning-only; no ES/historical/MC/stress/benchmark/attribution/backtesting pulled forward; no new permission; no frontend; no code. No defect. |

**Not folded / refuted:** none withheld.

---

## Part 6 — P3-5 implementation readiness gate
P3-5 is **implementation-ready** once OQ-P3-5-1…10 are ratified: the v1 method, the ENT-027 realization shape, the
declared-parameter version identity, the coverage adjudication, the VAR_INPUT snapshot design, the numerics incl.
the radicand tolerance, the audit/entitlement reuse, the dual-path verification contract, and migration `0026_var`
are all fixed against the ratified standards and the hardened P3-4 exemplar. The build contract is
`p3_5_var_implementation_plan.md`. **P3-5 planning implements nothing.**

---

## Part 7 — Implementation adversarial review log (2026-07-07, independent-context — the plan Part 11 gate)

> **CLOSEOUT STAMP (2026-07-07):** P3-5 **IMPLEMENTED and CLOSED** — plan `c2c1b4d` (CI **#101** green);
> implementation `5ed8271` (CI **#102** green, REST-verified); user approval given at the Tier-2 gate AFTER the
> review below was folded and re-validated (1091 PG-backed tests; `alembic check` clean; downgrade smoke green).

Six independent finder agents (line-scan / changed-behavior / cross-file / governance-tenancy / numeric-methodology /
test-quality) over the full P3-5 working-tree diff; every candidate verified empirically before folding. The numeric
finder independently confirmed the z constants (incl. the rounding direction — truncation would give …040), all four
hand references, the tolerance derivation (valid majorant, 20× headroom, clamp error economically nil), and the numpy
legs' non-vacuity. **Thirteen findings CONFIRMED and FOLDED** (fixes + regression tests in the same slice); two
recorded deferrals:

1. **Cross-tenant provenance FK stamping (the principal finding).** The `exposure_run_id`/`covariance_run_id` hard-FK
   values come from PINNED CONTENT, and on the consume path were never re-resolved own-tenant — PG FK checks run as
   the table owner and BYPASS RLS, so a hand-minted snapshot could make tenant A's governed row durably reference
   tenant B's runs (plus a run-id existence oracle). → both parsed ids now re-resolve through the tenant-predicated
   run resolvers (run_type + COMPLETED) on BOTH paths before `create_run`; regression-tested with a foreign-tenant
   chain.
2. **`_norm_decimal` default-context crash** — the serializer quantized at 20dp under prec-28 (the exact P3-4
   `PreciseDecimal` bug class, reintroduced): a covariance ≥1e8 crashed `build_var_snapshot`/`verify_snapshot`. →
   quantize inside a prec-60 localcontext (behavior-preserving for all existing hashes).
3. **Non-canonical pinned pair order** let a REVERSED duplicate carry a conflicting value past the duplicate check
   (and falsely refused a reversed-but-complete matrix). → non-canonical order is refused outright (the OD-P3-4-D
   storage contract); probes added.
4. **Duplicate-exposure-content smuggle** — identical captured rows under distinct component targets double-counted
   x. → dedup on the captured row id; probe added (with the target/content-id decoupling shape).
5. **Column-overflow escape** — column-legal extremes (x=1e18, σ_ij=1e12) give σ≈1e24 > Numeric(28,6): a PG
   NumericValueOutOfRange 500 with NO durable evidence. → a magnitude gate in the post-compute DQ (committed FAILED
   run); tested.
6. **Absurd-pin kernel crash** — a pinned `exposure_amount` of 1e50 (beyond its SOURCE column's envelope) crashed the
   kernel quantize POST-create. → source-column magnitude envelopes adjudicated pre-create (exposure <1e22,
   covariance <1e18) + a kernel `InvalidOperation`→`VarKernelError` defense; tested.
7. **Malformed-pinned-content 500s** — missing keys / non-decimal values / bad dates raised raw
   KeyError/InvalidOperation/ValueError instead of the documented 422. → a well-formedness envelope converts the
   parse/adjudication error classes to `VarInputError`; probes added.
8. **Horizon identity hole** — `isdigit()` accepted any digit-string (incl. Unicode digits that then crashed `int()`),
   so a generically-minted version could stamp `horizon_days=250` onto an immutable 1-day number. → the declared
   horizon must equal `1` verbatim (v1 identity); tampered/Unicode cases tested.
9. **Confidence parse escapes + silent coercion** — `Decimal('abc')` raised `InvalidOperation` (NOT a ValueError →
   500), and `0.94995` was silently ROUNDED onto 0.9500 instead of refused. → strict pattern-first parse (exact
   zero-padding only); endpoint 422s tested for both classes.
10. **σ/VaR SQLite float roundtrip** — plain Numeric(28,6) loses the low digits of 16+-significant-digit currency
    values on the dev engine. → `PreciseDecimal(28,6)` (PG DDL unchanged; drift-checked).
11. **Serializer pin-flavor parity** — the new content serializers omitted `input_snapshot_id`/`model_version_id`/
    `system_from`, narrowing verify's tamper-evidence surface vs the P3-3 EXPOSURE flavor. → columns added.
12. **σ-homogeneity overclaim** in the methodology (exactness holds only for perfect-square radicands; the stored
    values satisfy the (λ+1)/2-quanta bound). → wording fixed; the property test asserts BOTH regimes.
13. **Vacuous pin-invariance + coverage gaps** (test-quality): the invariance test's re-seed produced identical
    upstream data (a live-read defect would have passed) → rebuilt with a vendor supersede so the fresh build
    DIFFERS while the pinned consume is invariant; added: the endpoint FAILED-surfacing contract, the endpoint
    `WrongModelVersionError` arm, duplicate-pair / missing-off-diagonal probes, a 3-factor exact reference (σ=700).

**Recorded deferrals (not folded, with rationale):**
- **`assert_registered_model_version` has NO `status=='REGISTERED'` predicate** (pre-existing; newly load-bearing —
  generically-minted versions bind with `status=None` across ALL FOUR risk binders). Tightening it is a cross-slice
  semantic change needing its own decision (what statuses bind; existing-data audit) — a P3-6-planning carry-in. The
  P3-5-specific exposure is materially reduced by the strict declared-parameter identity (folds 8/9).
- **Shipped result-column float parity** — `sensitivity_result`/`factor_exposure_result` (and `exposure_aggregate`)
  carry plain Numeric columns with the same SQLite-roundtrip latency the new columns just escaped; converting shipped
  columns to `PreciseDecimal` is a dedicated parity slice (behavior-preserving on PG), not a P3-5 ride-along.

Post-fold validation: format/lint/mypy/docs/secret-scan clean; **1091 passed** full-PG suite (52 P3-5 tests);
`alembic check` clean; downgrade-base smoke green.
