# PPF-2 Decision Record — the private covariance block Ω_pp, slice 2 of the §2.1 unification arc (Wave-10 slice 3)

| | |
|---|---|
| **Status** | **CLOSED 2026-07-22 — impl PR #101 (merge `7aefd1c`), CI green run #519 (all 6 jobs: Backend/Frontend/DB-migration/API-type-drift/docs/secret-scan). Ratified 2026-07-22 (OQ-PPF-2-1…4, all as recommended: equal-weight sample covariance, thin-N disclosed; block-diagonal Ω_pp, approx-orthogonal disclosed; the frequency conversion lives in PPF-3; reuse `covariance_result` + the three run_type read-filters — NO migration). Pre-ratification verifier pass RAN 2026-07-22 (Part 5: CLAIM 4 REFUTED "orthogonal-by-construction" → reworded as an approximation; CLAIM 2 COMPLICATED → three run_type read-filters named; CLAIMs 1/3/5 HOLD; no redesign). 4-finder adversarial review RAN 2026-07-22 (Part 6: ZERO HIGH, 2 MED + 4 LOW folded — `verify_snapshot`'s except-tuple hardened + the methodology doc's validation-legs claims reconciled to shipped tests). See the delivery roadmap's dated 2026-07-22 PPF-2 DONE log entry for the full closeout record.** |
| **Premise** | PPF-1 (CLOSED 2026-07-22, the 18th governed number) shipped the pure-private factor **return series** — per PRIVATE segment factor, `private_factor_return_result` holds the pooled `PURE_PRIVATE_PERIOD` returns at **APPRAISAL** frequency. PPF-2 estimates the **covariance Ω_pp over those segment return series** — the systematic co-movement of pure-private risk across segments (the MSCI PE/Private-Credit Factor Model's pure-private factor covariance; Shepard 2014/2025). It is the second of the 3-slice arc: **PPF-1 (return) → PPF-2 (covariance Ω_pp) → PPF-3 (the unified number `√(x'Σx + p'Ω_pp·p + residual)`)**. |

## Part 1 — Grounding (file:line; the PPF-2 census 2026-07-22)

**The reuse surface is unusually clean** (verified):
- **The covariance KERNEL is fully estimator/frequency-agnostic.** `risk/covariance_kernel.py:55-107` `estimate_covariance` consumes ANY `list[FactorSeriesPin]` (`id`, `factor_code`, `(date, Decimal)` rows) sharing an identical date vector, N≥2 → one `covariance_value` per canonical unordered pair incl. the diagonal (`F·(F+1)/2`), equal-weight unbiased `Σ(demeaned_i·demeaned_j)/(N−1)`. **NO change needed** — it does not know "daily" or "factor_return."
- **The DAILY wall is ONLY in the ADJUDICATOR + the pin-shape.** `covariance_service.py:189-193` refuses `frequency != DAILY` on BOTH build+consume paths (+ `:325` on the build-path live factor). Everything else (kernel, result table) is frequency-neutral.
- **The result-table-as-series pinning is doubly proven.** `build_proxy_weight_snapshot` (`snapshot/service.py:2218-2318`) AND PPF-1's own `build_private_factor_return_snapshot` pin governed IA-result rows as a `(period_start, period_end, metric_value)` series (`_list_desmoothed_period_rows` + `desmoothed_return_content`, the no-valid-axis governed-row pin flavor). PPF-2 mirrors it against `private_factor_return_result` (`metric_type == PURE_PRIVATE_PERIOD`, ordered by `period_start`).
- **The declared-parameter slot follows `window_observations=` verbatim** (`bootstrap.py:501-513` + `model/assumptions.py`) — mint a parser if a new declared parameter is needed.
- **Cross-series alignment already exists** in the DAILY builder: `build_covariance_snapshot` pins "the N most-recent COMMON dates" fail-closed on short overlap (`:914-921`) — PPF-2's builder mirrors it, intersecting the segments' **appraisal periods**.
- **The `CovarianceResult` table is frequency-carrying** (`risk/models.py:144-193`: `frequency`, `statistic_type`, `factor_id_1/2`, `covariance_value PreciseDecimal(38,20)`, grain `(run, factor_id_1, factor_id_2)`) — it already fits an APPRAISAL private covariance; distinguished from the public one by `run_type` + `frequency`.
- **The downstream VaR gates stay DAILY-only** (`var_service.py:265-273`, `var_hs_service.py:250-253`, `active_risk_service.py:227-234`) — they matter only when Ω_pp is CONSUMED (PPF-3), so PPF-2 is self-contained.

## Part 2 — Design decisions

### OD-PPF-2-A — A SIBLING covariance family, reusing the kernel (isolation-first)
Mint **`risk.covariance.private`** — its own binder (`run_private_covariance`), APPRAISAL-aware adjudicator (the `covariance_service.py:184-193` DAILY/SIMPLE checks become APPRAISAL/SIMPLE), builder, `PURPOSE_PRIVATE_COVARIANCE_INPUT`, `COMPONENT_KIND_PURE_PRIVATE_RETURN` + serializer, and `RUN_TYPE_COVARIANCE_PRIVATE`. **Reuses the generic `estimate_covariance` kernel unchanged** (verifier CLAIM 1: the kernel needs only aligned `(date, Decimal)` series, N≥2 — no daily/factor-return coupling; but the existing covariance *service* is NOT reusable — the new binder MUST intersect the segments to a common grid + re-key each series row on `period_end` + pass `date` objects, OD-F). The existing `risk.covariance.sample` binder + its DAILY gates are **BYTE-UNTOUCHED** — the PPF-1 isolation doctrine (never widen a shipped public gate; add a fail-closed sibling).

### OD-PPF-2-B — Reuse the `covariance_result` table (fork → OQ-PPF-2-4; NO migration; verifier CLAIM 2 fold)
**Recommendation: reuse `CovarianceResult`** (frequency=`APPRAISAL`, `statistic_type=COVARIANCE`, the segment `factor_id`s as the pair keys), distinguished by the new `RUN_TYPE_COVARIANCE_PRIVATE` — the var-backtest/RS-1 "reuse a result table, distinguish by run_type" precedent. **NO migration, NO new ENT.** **The verifier surfaced the real cost (CLAIM 2 partial-refutation):** reusing the table ACTIVATES a *latent* shared-table bug — two public reads have NO `run_type` filter, so a private APPRAISAL run would leak as "the latest/by-id public covariance": `latest_covariances` (`covariance_service.py:415-433`, calls `list_governed_results` without `run_type=` — exactly what the `calc/reads.py:49-54` docstring warns about for shared tables) and `resolve_covariance`/`GET /covariances/{id}` (by-id, tenant-only). **The fold: reuse REQUIRES adding `run_type=RUN_TYPE_COVARIANCE` to those two public reads + `GET /covariances/latest`** — a change that is **behavior-identical for ALL existing data** (no private rows exist pre-PPF-2, so the filter returns the same rows) and is a **correct latent-bug hardening** the reads.py contract already demands. The run-resolved reads + the VaR/active-risk consumers are already SAFE (doubly fail-closed: `resolve_covariance_run` is `RUN_TYPE_COVARIANCE`-filtered → 404, and the DAILY frequency gate is the backstop). Also add `COVARIANCE_PRIVATE` to `RISK_RUN_TYPES` (the generic run browser, honest-by-`run_type`). **Alternative (OQ-4=B): a dedicated `private_covariance_result` table** (+migration, +ENT) — heavier, but the public covariance path stays BYTE-UNTOUCHED (the purest isolation). The recommendation stays **A**: the two filter additions are provably behavior-identical + a genuine bug fix, and reuse avoids a migration+ENT for an identical schema.

### OD-PPF-2-C — Block-diagonal Ω_pp (fork → OQ-PPF-2-2; verifier CLAIM 4 REFUTED "orthogonal-by-construction" → APPROXIMATELY orthogonal)
**Recommendation: block-diagonal** — estimate Ω_pp over the pure-private segment returns ALONE, treating the cross-covariance with the public factors Σ as **zero (a v1 modeling assumption, disclosed as an APPROXIMATION — not an exact identity)**. The MSCI decomposition treats pure-private as a DISTINCT systematic risk source, and PPF-3 sums the two blocks (`x'Σx + p'Ω_pp·p`). **The verifier REFUTED the stronger "orthogonal-by-construction" claim** (folded): only the RAW OLS residual is exactly orthogonal to the regressors by the normal equations; PPF-1's `pp = desmoothed − Σ_f w_i,f·R_f` uses the **PROMOTED** REGRESSION weights, which are analyst-mediated and — in BOTH demo segments — a **strict SUBSET** of the fitted factors (PE promotes 1 of 2 fitted, PC 2 of 3), so `pp` retains a dropped-factor public component `Σ_f(β̂_f − w_f)·R_f` and has a small NON-ZERO cross-covariance with Σ. (RETAIN_ALPHA is a NON-issue here — a constant intercept contributes zero covariance.) So block-diagonal is an honest v1 that slightly UNDERSTATES the public↔private cross term; **joint public+private estimation (capturing that residual cross-correlation) is the recorded v2** — additionally bias-prone from the appraisal/daily frequency mismatch (the mixed-frequency literature), so v1's block-diagonal is the defensible first cut.

### OD-PPF-2-D — Equal-weight sample covariance, thin-data honest (fork → OQ-PPF-2-1)
**Recommendation: reuse the shipped equal-weight sample covariance** (the `estimate_covariance` kernel, window identity = the number of common appraisal periods, floor N≥2). Appraisal series are SHORT (a handful of periods), so a small-N covariance is noisy — disclosed as a first-class limitation. **Bayesian/Vasicek (1973) shrinkage-toward-a-prior + thin-factor corrections (the MSCI PE-model appendix) and Ledoit-Wolf (2004) shrinkage are the recorded v2s** — the platform already has RS-1 empirical-Bayes machinery for residual variances to draw on. NOT minted here (the PPF-1 two-step-vs-Bayesian-single-step precedent: ship the honest v1, record the sophisticated frontier).

### OD-PPF-2-E — The frequency conversion belongs to PPF-3 (fork → OQ-PPF-2-3)
**Recommendation: PPF-2 stores Ω_pp at NATIVE appraisal grain** (`frequency=APPRAISAL`), a faithful estimate; the **appraisal→daily/annual conversion is PPF-3's declared parameter** (it is a property of COMBINING Ω_pp with the daily Σ at a common horizon — the combiner's concern). PPF-2 needs NO conversion parser (simpler + Ω_pp stays a pure estimate). *(This refines the PPF-1 planning note that "PPF-2 needs the frequency-conversion parser" — the grounding shows the conversion is genuinely a PPF-3 concern.)* Alternative: PPF-2 declares `periods_per_year=` as self-describing identity metadata (echoed, not applied) so Ω_pp is self-documenting — a small addition, but declaring-a-parameter-you-don't-apply is unusual.

### OD-PPF-2-F — Cross-segment appraisal-grid alignment (verifier CLAIM 3 confirmed: N=5 common, zero new seeding)
The covariance kernel requires an IDENTICAL date vector across the paired series. PPF-2's builder intersects the segments' `(period_start, period_end)` appraisal intervals to the common grid + re-keys each row on `period_end` (the kernel's alignment precondition), fail-closed below the N≥2 floor — the cross-segment analogue of PPF-1's identical-interval pooling; a segment whose grid does not overlap sufficiently is a named-gap refusal, never zero-filled. **Verifier CLAIM 3 (confirmed on the actual seed):** the two demo segments' pure-private series sit on the identical calendar quarter-end grid — PE-HARBOR-IV's 5 periods = PC-BRIDGEWATER-II's periods 2..6, so the intersection is **exactly 5 common quarterly intervals (2024-12-31 → 2026-03-31)**, N=5 ≥ 2, **ZERO new seeding**; PC's earliest period (2024-09-30 start) has no PE counterpart and is dropped in alignment. **Honest disclosure (OD-F):** N=5 is a THIN appraisal-grain covariance window — a first-class limitation (the shrinkage v2, OD-D), stated in the summary and the demo, not hidden.

### OD-PPF-2-G — Scope fence
NEW: the `risk.covariance.private` family (binder/adjudicator/builder/registrar + `RUN_TYPE_COVARIANCE_PRIVATE` + `PURPOSE_PRIVATE_COVARIANCE_INPUT` + `COMPONENT_KIND_PURE_PRIVATE_RETURN` + serializer), the rule-7 reads (list + latest by segment-pair / run), a demo stage extension, tests. REUSES: the `estimate_covariance` kernel + (OQ-4=A) the `covariance_result` table (NO migration) + `risk.run`/`risk.view` (no permission mint) + `CALC.RUN_*` (a reserved `RISK.COVARIANCE_PRIVATE_CREATE`, not emitted). NOT touched: `audit/service.py` (FROZEN), the `risk.covariance.sample` public path (byte-identical — regression-proven), the DAILY VaR gates (they stay DAILY-only; PPF-3 pays the conversion), the 5-table hybrid set. Counts: 18→**19** governed numbers.

## Part 3 — Open decisions (OQ-PPF-2-1…4) — the ratification gate

- **OQ-PPF-2-1 — The Ω_pp estimator.** **(A, recommended)** equal-weight sample covariance (reuse the shipped kernel; window floor N≥2; thin-data disclosed) — Vasicek/Ledoit-Wolf shrinkage = the recorded v2. **(B)** shrinkage now (Ledoit-Wolf, riding RS-1's EB machinery) — more robust on thin data, a larger build + a different estimator identity. Rec **A** (matches the covariance v1; shrinkage is the honest v2).
- **OQ-PPF-2-2 — Block-diagonal vs joint.** **(A, recommended)** block-diagonal (Ω_pp over pure-private alone; the cross-covariance with Σ treated as zero — a v1 **approximation**, verifier-corrected from "orthogonal-by-construction": the promoted weights are a strict SUBSET of the OLS fit, so a small dropped-factor public component leaks into `pp`; disclosed). **(B)** joint public+private estimation (captures that residual cross-correlation) — a recorded v2, additionally mixed-frequency-biased. Rec **A** (the honest first cut; joint needs the mixed-frequency machinery).
- **OQ-PPF-2-3 — The frequency conversion's home.** **(A, recommended)** PPF-3 owns it — PPF-2 stores native-APPRAISAL Ω_pp, no conversion parser. **(B)** PPF-2 declares `periods_per_year=` as self-describing metadata (echoed, not applied). Rec **A** (simpler; the conversion is the combiner's concern).
- **OQ-PPF-2-4 — Result storage.** **(A, recommended)** reuse `covariance_result` (frequency=APPRAISAL + `RUN_TYPE_COVARIANCE_PRIVATE`; NO migration, NO ENT) — the reuse-a-table-distinguish-by-run_type precedent — **WITH the verifier-mandated run_type filters** added to `latest_covariances` + `resolve_covariance` + `GET /covariances/latest` (behavior-identical for existing data, a latent shared-table-bug hardening). **(B)** a dedicated `private_covariance_result` table (+migration, +ENT) — the public covariance reads stay BYTE-UNTOUCHED (purest isolation), at the cost of duplicated schema. Rec **A** (the filter additions are provably safe + a genuine fix; reuse avoids a migration for an identical shape). *This is the one fork where the isolation-purist (B) and the minimal-footprint (A) answers genuinely diverge — the user's call.*

## Part 4 — Invariants & gates
`make check` + full-PG affected-family battery + (if OQ-4=B) migration smoke + `alembic check`; `make fe-check` + `make gen-api-check` (new read endpoints regenerate OpenAPI deterministically); **byte-identical regression proof on the `risk.covariance.sample` public path** (the private family must be invisible to it — the PPF-1 isolation lesson); the closure-discipline docs-check enforces this record's closeout stamp; 4-finder adversarial review (covariance correctness vs the cited construction + the block-diagonal orthogonality claim; doctrine/security + public-covariance isolation; read-correctness; demo/count integrity). Rule-6 citations: Shepard (MSCI PE Factor Model 2014/2025) + the MSCI Private Credit Factor Model (Sept 2025); Vasicek (1973); Ledoit-Wolf (2004); Geltner (1993); Getmansky-Lo-Makarov (2004); Ang-Nabar-Wald (2013); the mixed-frequency covariance literature.

## Part 5 — Pre-ratification verifier pass — RAN 2026-07-22 (two adversarial verifiers; 1 REFUTED → folded-as-honesty, 1 COMPLICATED → 3 filters named, 3 HOLD; NO redesign)

- **CLAIM 1 — kernel reusable for APPRAISAL: HOLDS with a precondition.** `estimate_covariance` needs only aligned `(date, Decimal)` series, N≥2, no daily/factor-return coupling — a 2×2 over the two segments' series computes correctly. **Precondition folded (OD-A/OD-F):** the existing covariance *service* is NOT reusable (it hardwires the DAILY window + the `factor_return` pin shape); the new binder must intersect to the common grid + re-key on `period_end` + pass `date` objects.
- **CLAIM 2 — public-covariance isolation: COMPLICATED → folded (OD-B).** The run-resolved reads + the VaR/active-risk consumers are SAFE (doubly fail-closed: `RUN_TYPE_COVARIANCE`-resolve → 404, DAILY-gate backstop; grain never collides). BUT `latest_covariances`/`GET /covariances/latest` + `resolve_covariance`/`GET /covariances/{id}` have NO `run_type` filter — reuse would leak a private APPRAISAL matrix as "the latest/by-id public covariance." **Folded:** OQ-4=A now names the three run_type-filter additions (behavior-identical for existing data; a latent shared-table-bug fix the `calc/reads.py` contract already demands).
- **CLAIM 3 — demo common data: HOLDS (confirmed on the seed).** The two segments sit on the identical quarter-end grid; the intersection is **exactly 5 common quarterly intervals (2024-12-31 → 2026-03-31)**, N=5 ≥ 2, ZERO new seeding (PC's earliest period drops in alignment). Folded (OD-F): disclose N=5 as a thin window.
- **CLAIM 4 — block-diagonal orthogonality: REFUTED "orthogonal-by-construction" → folded as honesty (OD-C).** Only the RAW OLS residual is exactly orthogonal; PPF-1 uses PROMOTED weights that are a strict SUBSET of the fitted factors in BOTH demo segments (PE 1/2, PC 2/3), so `pp` retains a dropped-factor public component and has a small non-zero cross-covariance with Σ. (RETAIN_ALPHA is a non-issue — a constant adds zero covariance.) Reworded to "APPROXIMATELY orthogonal, disclosed"; joint estimation = the recorded v2.
- **CLAIM 5 — no-migration correctness: HOLDS.** No CHECK/enum on `frequency`/`statistic_type`/`run_type`; grain is per-run-unique; a new run_type string + a new model code need no schema change; `alembic check` stays clean.

**Net: the design stands — a sibling family reusing the generic kernel + the shared result table. The one refutation (CLAIM 4) is an honesty correction that STRENGTHENS the recorded v2 case, not a redesign; CLAIM 2's leak is three named, provably-safe read-filters. The record is ready for the ratification gate.**

## Part 6 — 4-finder adversarial review (RAN 2026-07-22) — 2 MED + 4 LOW, ALL folded; ZERO HIGH

Four cross-cutting finders over the impl diff (`main...HEAD`, 7 commits): covariance correctness +
numerical honesty; public/private isolation over the shared `covariance_result` table + governance
doctrine; snapshot/pin reproducibility + read correctness + run-resolution plumbing; demo/count
integrity + dossier honesty. Every material finding independently re-verified before folding.

**The number is CORRECT (finder 1): ZERO HIGH/independently confirmed.** The finder ran the shipped
`numpy.cov(ddof=1)` cross-check itself — it passes. Cross-segment `period_end` re-keying is safe
(the adjudicator asserts the FULL `(period_start, period_end)` interval vector identical across
segments before the kernel ever sees a bare `period_end`); `n_observations`/`window_start`/
`window_end`/vocabulary fields are all honest; the "approximately orthogonal, disclosed" claim
(CLAIM 4 above) is substantively accurate against the promoted-weights mechanism; the PSD/defensive
gate is correctly wired through `execute_governed_run`.

**Isolation HOLDS on every read + both downstream consumers (finder 2): ZERO HIGH/MED.** The
step-1 `run_type` filters on `latest_covariances`/`resolve_covariance` are correct and complete;
VaR/active-risk are DOUBLY guarded against consuming a private run (`resolve_covariance_run`'s
`run_type` gate on both the build AND consume-existing paths, backstopped by the DAILY-frequency
adjudication check even if the first gate were bypassed); the PRIVATE/APPRAISAL family guard in
`_adjudicate_pins` is real (triple-checked: pin data, snapshot builder, and — after the fold below —
self-defending reads); `RISK_RUN_TYPES` consistently excludes both private run families from the
generic run browser; all frozen invariants (audit/service.py, no BYPASSRLS, no new
audit/permission/role, no secrets) respected.

**Snapshot/pin plumbing correct, ONE gap (finder 3):** the builder pins exactly what's needed and
fails closed on every malformed-input class (window<2, duplicate/multi-segment/shared-segment runs,
non-PRIVATE segment, short common-interval overlap); the snapshot fence holds (no `calc` import, no
multiplication); run-resolution (latest-COMPLETED-per-segment, the ambiguous-input gate) is correct;
the API surface + regenerated OpenAPI/FE types are drift-free. The one gap: `verify_snapshot`'s
except-tuple omitted the new component kind's resolver exception (below).

**Demo/counts/dossier CLEAN (finder 4): ZERO HIGH/MED.** The stage-12 runner fabricates nothing,
seeds zero new book data, and computes its window (register-N and run-N are the SAME value by
construction, both reads of the identical common-interval intersection in one transaction); counts
move by exactly +1 code / +1 record / +1 COMPLETED run to 22/37/104 (PG-confirmed); `stage9zzz`
correctly sorts last; every dossier finding key matches exactly one registered limitation; thin-N is
disclosed everywhere, never hidden.

**Folds applied (this review):**
- **MED-1 (finder 3) — `verify_snapshot`'s except-tuple omitted `PrivateCovarianceSnapshotError`.**
  Every other governed-row component kind's resolver exception is listed (mirroring
  `CovarianceSnapshotError`, `ProxyWeightSnapshotError`, etc.); the new
  `COMPONENT_KIND_PURE_PRIVATE_RETURN` branch's was the sole omission, so a gone pinned pure-private
  row would raise an UNCAUGHT exception (a raw 500) instead of reporting `drifted=True` — breaking
  the file's own documented invariant. **Fix:** added to the except-tuple; a new drift-not-500 test
  proves it (deletes a pinned row via a Core statement, since SQLite carries no append-only trigger,
  and asserts `verify_snapshot(...).ok is False`).
- **MED-2 (finder 1) — the methodology doc's "Validation / reproduction tests" section overclaimed.**
  It said "the five legs" and listed six; three of the six had NO shipped test (a hand-computed
  2-segment reference; the consume-existing `snapshot_id` path — genuinely UNTESTED, all 5 prior
  `run_private_covariance` calls in the suite used `segment_factor_ids`; TR-09 post-pin invariance).
  **Fix:** reconciled the doc to claim only what ships (the kernel-level legs are correctly labeled
  INHERITED unchanged from `covariance_sample_v1`, since PPF-2 reuses `estimate_covariance`
  byte-for-byte) and added the two missing tests — a consume-existing==build-in-request
  byte-equality assertion AND a `verify_snapshot(...).ok` round-trip — closing the reachable
  untested branch, not just the doc.
- **LOW-1 (finder 2) — the by-run-id `list_covariances`/`list_private_covariances` lacked a
  `run_type` filter.** Not currently exploitable (both callers pre-validate via a `run_type`-gated
  `resolve_*_run` before reaching the list read), but this is exactly the latent-shared-table-read
  class the record's own CLAIM 2 fold warns about. **Fix:** added the `CalculationRun` join +
  `run_type` predicate to BOTH — self-defending now, not merely caller-ordered; behavior-identical
  for existing data.
- **LOW-2 (finder 4) — no statistical-adequacy floor beyond `N≥2` in v1.** The declared window is
  data-derived (the count of common appraisal periods that exist), so Ω_pp will register and
  complete at whatever thin N the substrate carries, down to N=2. Already thoroughly disclosed
  (`n_observations` on every row, the dossier condition, the registered limitation) — not concealed,
  just unrecorded as an explicit scope-out. **Fix:** added the one-line "no adequacy floor beyond
  N≥2 in v1" disclosure to the methodology's Known limitations, with the PPF-3 carry-forward note.
- **LOW-3 (finder 1) — the methodology doc miscounted "five legs" as six items.** Fixed alongside
  MED-2's reconciliation.

**Gates after folds:** `make check` green (**1826 passed**); the affected-family full-PG battery
re-run GREEN after the folds — `test_covariance_pg.py` (8, incl. the step-1 byte-identical read-filter
regression under the new join) + the full demo PG chain in CI order (`stage9zzz` correctly last,
counts 21/36/103 → **22/37/104**; the live demo segments share **N=5** common quarterly intervals,
2024-12-31 → 2026-03-31 — matching CLAIM 3's Part-5 prediction exactly); `make fe-check` green
(build); `make gen-api-check` clean; `alembic check` clean (**NO migration**, as designed);
`pip-audit` clean. **Counts: 18→19 governed numbers; the demo tenant moves 21/36/103 → 22/37/104.**
