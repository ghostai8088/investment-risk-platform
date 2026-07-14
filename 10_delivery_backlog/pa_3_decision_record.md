# PA-3 Decision Record — regression-estimated proxy weights (Wave-4 slice 2, the headline payload)

> **Status: RATIFIED 2026-07-13** (OQ-PA-3-1…6 all approved as recommended). The TWELFTH governed number and the
> Wave-4 loop-closer: estimate private→public proxy factor weights by regressing the **desmoothed**
> appraisal return series (PA-1's governed output — its FIRST downstream consumer) on captured public
> factor returns, replacing judgment-only captured weights with evidence + stated uncertainty. The
> thesis §2.2 best-in-class move, ratified as Wave-4 fork option A at the Wave-3 close. Delivered
> under the delivery-autonomy grant (Claude self-drives; the USER merges the PR).

## Part 1 — Problem

PA-2 proved the end-to-end chain (capture → desmooth → proxy → factor risk → VaR, byte-exact), but the
proxy **weights** themselves are captured-only (`MANUAL` mapping method, PA-0/OD-PA-2-D): an analyst's
judgment, entered by hand, with no evidence trail. PA-1's desmoothed return series — built precisely to
reveal a private asset's TRUE factor sensitivity — feeds nothing downstream. The loop is open: the
platform desmooths honestly, then ignores the result when assigning factor loadings.

The recognized methodology closes it: **regress the (desmoothed) illiquid-asset return series on public
factor returns** and read the loadings off the coefficients. PA-0 anticipated exactly this — it RESERVED
`MAPPING_METHOD_REGRESSION` in the proxy-mapping vocabulary (`marketdata/models.py:176`) while accepting
only `MANUAL`, and PA-2 recorded "regression-estimated weights" as the named v2.

## Part 2 — External benchmarks (rule 6; citations verified 2026-07-13)

- **Sharpe (1992), "Asset Allocation: Management Style and Performance Measurement," *JPM* 18(2), 7–19**
  — returns-based style analysis: a fund's effective factor mix estimated by regressing its returns on
  factor/asset-class returns; the "strong" form adds sum-to-1 + non-negativity constraints. The
  grandfather of estimating exposures from returns. *Disposition:* the v1 regression is UNCONSTRAINED
  (see OD-C — proxy weights deliberately have no sum-to-1, PA-0; currency loadings can be legitimately
  negative); Sharpe-style constrained variants = a recorded v2.
- **Scholes & Williams (1977, *JFE*) and Dimson (1979), "Risk measurement when shares are subject to
  infrequent trading," *JFE*** — lagged/lead-beta corrections (aggregated coefficients) for
  infrequently-observed return series. **Asness, Krail & Liew (2001), "Do Hedge Funds Hedge?," *JPM*
  27(3), 6–19** — summed contemporaneous+lagged betas expose the understated market exposure of SMOOTHED
  monthly series. *Disposition:* these correct for smoothing/staleness INSIDE the regression on RAW
  series; the platform instead desmooths FIRST (PA-1 Geltner) and regresses the corrected series —
  the two are recognized alternatives, and desmooth-then-regress composes with what we already ship.
  A summed-lag variant on the raw series = a recorded v2 (cross-check value).
- **Getmansky, Lo & Makarov (2004)** (already cited at PA-0/PA-1) — the smoothed-returns process that
  motivates both legs. *Disposition:* unchanged; PA-3 is the consumption leg.

## Part 3 — Decisions

- **OD-PA-3-A — a GOVERNED estimation number, never an auto-write.** New run family
  `PROXY_WEIGHT_ESTIMATE`; new model `risk.proxy_weight.regression` v1; new IA result table
  `proxy_weight_estimate_result` (**ENT-057**, migration **0037**), grain
  `(calculation_run_id, metric_type, factor_id-nullable)`: one `WEIGHT` row per candidate factor
  (estimated coefficient + its standard error), one `INTERCEPT` row, one `ESTIMATION_SUMMARY` row
  (R², n_observations, residual stdev). Estimated weights are MODEL OUTPUT — snapshot-gated,
  run-bound, model-bound, IA append-only — and are **never written into `proxy_mapping` by the run**.
  The capture/derived boundary the platform is built on stays intact.
- **OD-PA-3-B — inputs: consume PA-1, pin both sides.** New snapshot purpose `PROXY_WEIGHT_INPUT`
  pinning (i) the consumed COMPLETED `DESMOOTHED_RETURN` run's `DESMOOTHED_PERIOD` rows — new
  **`COMPONENT_KIND_DESMOOTHED_RETURN`** (the BT-1 pin-a-prior-governed-run precedent), the consumed-run
  guard on the RD-1/RD-2 `resolve_completed_run_of_type` rails; and (ii) the candidate factors'
  `factor_return` rows covering the desmoothed period span (existing `COMPONENT_KIND_FACTOR_RETURN`,
  the covariance precedent). Build-in-request XOR consume-existing; TR-09 both sides; pre-create
  refusals leave zero orphans.
- **OD-PA-3-C — the v1 regression form: unconstrained OLS with intercept, desmoothed-then-regress.**
  Per appraisal period, the factor regressor is the captured factor-return series **compounded over
  `[period_start, period_end]`** from pinned rows (deterministic; a period with missing factor coverage
  is a named-gap pre-create refusal — the P3-7 precedent, never silent zero-fill). Normal-equations
  solve in fixed-point Decimal (prec-50 working context; outputs quantized 12dp; magnitude envelopes
  gate RAW values before quantize — the P3-6/PA-1/PA-2 bug class guarded from birth); singular/collinear
  design matrix = pre-create refusal. Constrained (Sharpe) and summed-lag (Dimson/AKL) variants =
  recorded v2s.
- **OD-PA-3-D — identity + gates.** Declared parameter `min_observations` (identity via the NEW RD-2
  `model/assumptions.py` rails — `(code_version, min_observations)`), floor
  `max(declared, k + 2)` where k = candidate-factor count (intercept included ⇒ ≥1 residual df,
  so a standard error always exists — the honest-uncertainty analogue of PA-1's stdev pair). The
  candidate factor LIST is a run-request input (pinned into the snapshot; NOT identity — the same
  model estimates any candidate set, like VaR's portfolio). Fail-closed refusals: short series,
  singular matrix, factor-coverage gap, non-CURRENCY candidate factor, mixed-currency series.
- **OD-PA-3-E — the promotion leg (human-mediated, evidence-cited).** Activate the PA-0-reserved
  `MAPPING_METHOD_REGRESSION` vocab value. A REGRESSION-method `capture_proxy_mapping` call MUST cite
  its evidence: new nullable `source_calculation_run_id` column on `proxy_mapping` (additive; rides
  migration 0037), validated tenant-resolved + COMPLETED + `PROXY_WEIGHT_ESTIMATE` run-type (the
  consumed-run guard a third time); `MANUAL` captures leave it NULL (a MANUAL capture citing a run is
  refused — methods don't blur). Promotion stays a DELIBERATE second step (estimate → analyst reviews
  R²/std-errors → capture), preserving maker-checker posture; PA-2's runs then consume the promoted
  rows unchanged.
- **OD-PA-3-F — reuse everything else.** `risk.run`/`risk.view` reused (estimation is a risk-model
  activity — no permission mint); `RISK.PROXY_WEIGHT_ESTIMATE_CREATE` RESERVED-not-emitted (the PA-1
  EVT-230 convention); promotion reuses `marketdata.ingest` + the existing `MARKET.PROXY_MAPPING_*`
  audit codes; the run surfaces in the FE runs view automatically (the PA-1 `permissionFamily` fix);
  `audit/service.py` untouched.

**Recorded v1 limitations (honest):** appraisal series are SHORT (quarterly marks ⇒ wide standard
errors — reported per coefficient, never hidden); estimates regress one MODEL OUTPUT on captured data
(desmoothing model risk propagates into the weights — stated, the declared-α lineage is pinned);
CURRENCY-only candidates (the factor-universe boundary, unchanged); unconstrained OLS can produce
weights an analyst should reject — which is exactly WHY promotion is human-mediated; irregular
appraisal spacing inherited from PA-1 (per-period compounding is spacing-aware, but the AR(1)
per-step caveat rides along).

## Part 4 — Verification plan

Full battery (a governed-number slice): hand-derived OLS golden (normal equations solved
first-principles in-test, digit-exact vs the kernel); the honest-uncertainty check (std errors match a
hand derivation); refusal gates (short series / singular matrix / coverage gap / wrong-family factor);
magnitude-envelope boundary (committed FAILED, no orphan); TR-09 both sides under a factor-return
supersede; the promotion leg (REGRESSION requires a valid run citation; MANUAL refuses one; PA-2
consumes promoted rows end-to-end — closing the loop in one integration test); PG RLS/append-only
suite + its CI step in-slice; endpoint tests (register 201/idempotent/409; run; estimate GET).
`make check` + full local-PG clean-schema + `alembic check` + downgrade smoke + **the full 4-finder
review with a Fable-class numeric finder** (methodology slice — the VAR-HS-1 precedent).

## Part 5 — Open questions for ratification

- **OQ-PA-3-1 — The governed-estimate-then-promote shape (OD-A + OD-E): estimation is a governed
  number; promotion into `proxy_mapping` is a deliberate, evidence-citing second step.** *Recommend
  APPROVE — auto-writing model output into a captured FR table would blur the capture/derived boundary
  every prior slice defends; the two-step keeps the analyst in the loop exactly where judgment belongs.*
- **OQ-PA-3-2 — ENT-057 `proxy_weight_estimate_result` (IA) + migration 0037, incl. the additive
  nullable `proxy_mapping.source_calculation_run_id` provenance column riding the same migration.**
  *Recommend APPROVE — no existing result table has (run × factor → coefficient + std error) grain;
  row-level provenance beats audit-payload-only lineage for the promoted weights.*
- **OQ-PA-3-3 — v1 regression form: unconstrained OLS with intercept on the DESMOOTHED series, factor
  returns compounded per appraisal period from pinned rows; Sharpe-constrained + Dimson/AKL summed-lag
  variants = recorded v2s.** *Recommend APPROVE — desmooth-then-regress composes with what we ship;
  constraints contradict PA-0's deliberate no-sum-to-1; boring-base with honest diagnostics.*
- **OQ-PA-3-4 — Identity: declared `min_observations` (the RD-2 `model/assumptions.py` rails) with the
  `k+2` floor; candidate factors = pinned request input, NOT identity.** *Recommend APPROVE — mirrors
  the covariance window / Geltner-α precedents; k+2 guarantees a standard error always exists.*
- **OQ-PA-3-5 — Promotion validation: REGRESSION method REQUIRES a tenant-resolved COMPLETED
  `PROXY_WEIGHT_ESTIMATE` run citation; MANUAL refuses one.** *Recommend APPROVE — fail-closed in both
  directions; methods never blur.*
- **OQ-PA-3-6 — Permission/audit reuse per OD-F (no mint; EVT reserved-not-emitted).** *Recommend
  APPROVE — nothing about estimation warrants a new permission family.*

## Part 6 — Review dispositions + closure

**Implemented 2026-07-13** (all OQs ratified). The twelfth governed number + the Wave-4 loop-closer:
`proxy_weight_estimate_result` (ENT-057, migration 0037) + the estimate→promote leg activating PA-0's
reserved `MAPPING_METHOD_REGRESSION`. Full stack: OLS kernel, snapshot pins (COMPONENT_KIND_
DESMOOTHED_RETURN), the run service, `risk.promote_proxy_weight_estimate`, the API (register/run/GET
+ the `/proxy-mappings/promote-estimate` endpoint), docs (methodology + ENT-057 + RTM), and the test
battery (integration golden vs an independent OLS recompute; refusal battery; TR-09 both sides;
singular; magnitude-FAILED; coverage-gap; constant-target; the PG RLS/append-only leg).

**FULL 4-finder adversarial review (a governed number) — 3 finders CLEAN, 1 real defect, all folded:**
- *Numerical/OLS finder (Fable-class, the VAR-HS-1 precedent) — CLEAN, math CONFIRMED.* Independently
  re-derived the regression via an exact-rational (`Fraction`) solver across the fixture, a
  hand-derived case, and 60 randomized fuzz cases: coefficients, standard errors, R², the singular
  tolerance, the per-period compounding/alignment, and the magnitude gate all verified correct. Two
  non-defect notes recorded as deferrals (below).
- *Governance/snapshot finder — ONE real defect, FOLDED (the review's single most valuable finding):*
  `supersede_proxy_mapping`/`correct_proxy_mapping` accepted `mapping_method=REGRESSION` (now in the
  vocab) but carry no `source_calculation_run_id` and never called `_validate_promotion` → they could
  mint a live REGRESSION weight with a NULL citation, violating OD-PA-3-E. Everything else verified
  clean (migration↔ORM match, TR-09 no drift, the estimate→promote fence, declared identity, the
  provenance echoes).

  **Fold, as refined by the Fable fold-synthesis pass (2026-07-13):** the first (Opus-session) fold
  hard-refused REGRESSION on BOTH revision paths — safe, but empirically OVER-closed: the one-open-
  head constraint makes a second `promote` on an existing key 409, so the guard's own "re-promote"
  advice could never succeed and the loop-closer could not LOOP (re-estimate → re-promote is the
  steady-state use case). The Fable pass (per the standing fold-synthesis-on-Fable rule) caught this
  and implemented the finder's own recommended direction: `supersede_proxy_mapping` now carries an
  optional `source_calculation_run_id` under the SAME fence-safe blur guard as capture (REGRESSION
  requires a citation; MANUAL forbids one), and `risk.promote_proxy_weight_estimate` is
  promote-or-REpromote (capture on a fresh key; a citation-carrying supersede on an open head — the
  run-TYPE gate still resolved in `risk` first). The HTTP supersede body deliberately gains NO
  citation field (an API-level REGRESSION supersede always refuses — the original bypass stays
  closed); a CORRECTION can never mint REGRESSION (`_reject_regression_correction`, a v1 recorded
  limitation — re-promote instead). Tests: re-promotion succeeds (version 2, method preserved,
  citation updated, supersedes link); REGRESSION-supersede-without-citation, MANUAL-with-citation,
  and REGRESSION-correction all refuse; wrong-run-type on the revision path refuses.
- *Cross-file/API finder — CLEAN + one fold.* All routes/schemas/error-maps/exports/response-before-
  commit sound. Fold: `RISK_RUN_TYPES` had not gained `PROXY_WEIGHT_ESTIMATE` (the runs were invisible
  to `GET /risk/runs`) — added, with the ratified-set guard test updated (a deliberate addition).
- *Cleanup/sweep finder — CLEAN + three folds.* (a) the two doc-claimed-but-untested refusals
  (per-period coverage-gap + constant-target) now have tests; (b) the stale `proxy_weight_service`
  one-way-imports docstring gained `marketdata` (the fence-fix had added it); (c) the dead
  `ProxyMappingValueError` `_ERROR_MAP` entry + import in `api/risk.py` removed. Plus the numeric
  finder's parse-harmonization (factor `return_value` → `parse_strict_decimal`, defensive).

**Deferrals (recorded, not folded):** a partial unique index `WHERE factor_id IS NULL` for the
INTERCEPT/ESTIMATION_SUMMARY singletons (their one-per-run is a `_compute` + append-only guarantee,
not the UNIQUE constraint since PG treats NULLs as distinct — not reachable through the governed run;
the grain comments were corrected to stop overstating the DB guarantee); and the pre-existing
platform-wide `[1E8−½ulp, 1E8)` quantize-up edge shared with `perf/desmoothing_service.py` (a global
envelope-pattern question, not a PA-3 regression).

**Post-fold validation (2026-07-13):** `make check` **1330 passed / 274 skipped** + secret-scan +
docs-check clean; ruff (check + format) clean; the PG RLS/append-only leg collects+skips locally
(docker unavailable; verified via the CI step). NO drift (migration 0037 is the head; `alembic check`
expected clean).

**CLOSED (2026-07-14).** Implementation `15ba13f`→`77149d6` (12 commits: 5 WIP foundation → API →
docs → battery → the 4-finder folds → the Fable fold-synthesis correction `b078396` → the
schema-drift index-name fix `77149d6`) merged via **PR #28** (merge `a98d380`), CI green — including
the FIRST live execution of the ENT-057 PG RLS/append-only leg + downgrade smoke. Migration head →
`0037_proxy_weight_estimate`. The Wave-4 loop-closer ships: PA-1's desmoothed series now drives the
proxy weights PA-2 consumes, with per-coefficient honest uncertainty and the re-promotion loop
working end-to-end. Next = the Wave-4 v2 companion (PA-4).
