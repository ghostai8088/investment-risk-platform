# BT-1 Decision Record — VaR backtesting (Wave-2 slice 3)

> **Status: RATIFIED 2026-07-10** — OQ-BT-1-1…9 approved as recommended (user: "Approved").
> Drafted 2026-07-10 against HEAD `503a9e2`
> (P3-8 fully closed via PRs #1–#3). Scope: the NINTH governed number — **VaR backtesting**
> (exception counting + Kupiec proportion-of-failures + the Basel traffic-light zone) over realized
> flow-adjusted P&L (PM-1) vs the VaR forecasts of ONE shipped method per run (parametric P3-5 or
> historical-sim VAR-HS-1). The P7 model-validation prerequisite (SR 11-7 "outcomes analysis") and
> the Wave-1 close review's named nearest supervisory gap. Implementation gated separately behind
> `bt_1_implementation_plan.md`.

## Part 1 — Decisions at a glance (OD-BT-1-A…K)

| # | Decision | Choice (recommended) |
|---|---|---|
| OD-BT-1-A | Model identity | **`risk.var_backtest` v1** — a REGISTERED `model_version`; `code_version`-only identity PLUS one DECLARED parameter: the test significance level **`alpha`** (the P3-5 declared-parameter precedent). v1 supports exactly `alpha ∈ {0.05, 0.01}` — the Kupiec decision compares LR_POF against the FIXED chi-square(1) critical value (3.841459 / 6.634897), so the whole test is Decimal-pure (NO p-value/erf in v1). |
| OD-BT-1-B | Family home + permission | **The `risk` family** — a backtest VALIDATES a risk number (SR 11-7 outcomes analysis). New run family `run_type='VAR_BACKTEST'` (GS2: distinct from every metric); **REUSES `risk.run`/`risk.view` — NO permission mint** (the P3-8 OD-B precedent). **The perf fence stays INTACT** ("nothing imports perf"): the binder reads ONLY pinned JSON + re-resolves the consumed return run via `calc.CalculationRun` with a fence-kept LOCAL `"PORTFOLIO_RETURN"` constant + a sync test — a REAL fence (cross-package), unlike the P3-8 same-package false fence that was removed. |
| OD-BT-1-C | Inputs | ONE COMPLETED **PORTFOLIO_RETURN** run (PM-1 — realized side) + **N ≥ 1 COMPLETED VAR runs of ONE method** (uniform `metric_type` — VAR_PARAMETRIC xor VAR_HISTORICAL; backtesting both methods = two backtest runs, honestly separate). Uniform `confidence_level`/`horizon_days`/`base_currency` across the pinned VaR rows, and equal to the return run's base currency. |
| OD-BT-1-D | Realized P&L | **Flow-adjusted captured-book P&L per DIETZ sub-period: `P&L_i = end_mv − begin_mv − net_external_flow`** — computed purely from the pinned PM-1 rows (all three columns are pinned by the P3-8 `portfolio_return_content` serializer). This is the "actual P&L excluding external flows" leg; **hypothetical/clean P&L (static-portfolio repricing) is DEFERRED** — recorded, not silently conflated. |
| OD-BT-1-E | Alignment (the correctness heart) | Each pinned VaR forecast applies as of its **`window_end`**; it pairs with EXACTLY the DIETZ sub-period where `period_start == window_end` **and** `period_end == period_start + horizon_days` (calendar-day v1 — consistent with PM-1's calendar-day Dietz weighting). **Any unpaired forecast OR any duplicate/overlapping pairing ⇒ pre-create refusal of the WHOLE run** (NO imputation, no partial silent pairing). |
| OD-BT-1-F | Exception rule | `realized_loss_i = −P&L_i`; **exception iff `realized_loss_i > var_value_i`** (STRICT inequality — a loss exactly at VaR is not an exception; the Basel "loss exceeding VaR" convention). |
| OD-BT-1-G | Outputs (ENT-055) | Per-pair **`EXCEPTION_INDICATOR`** rows (0/1 `metric_value` + `realized_pnl`/`var_value` evidence echoes + the pair's period) + summary rows **`EXCEPTION_COUNT`** and **`KUPIEC_LR`** (the POF likelihood-ratio statistic + `test_decision` = REJECT / FAIL_TO_REJECT at the declared alpha) + **`BASEL_ZONE`** (GREEN/YELLOW/RED in a dedicated string column) emitted **ONLY when `confidence_level == 0.99` AND `n_pairs == 250`** — the domain the Basel table defines; outside it the zone row is OMITTED, never scaled or extrapolated. |
| OD-BT-1-H | Identity gate (cross-series) | Backtesting portfolio A's VaR against portfolio B's returns must REFUSE: each pinned VaR row's `exposure_run_id` is re-resolved under the acting tenant and its `exposure_aggregate.portfolio_id` (a models-only read — the risk→exposure import is precedented in `factor_service`) must equal the PM-1 run's pinned `portfolio_id`. All FK targets re-resolved under the acting tenant pre-create (the P3-5 finding). |
| OD-BT-1-I | Persistence | **ENT-055 `var_backtest_result`**, migration `0033`; IA TRUE append-only (P0001 trigger + ORM guard); symmetric FORCE RLS; grain UNIQUE `(calculation_run_id, metric_type, period_start)`; NOT-NULL FKs: calculation_run / input_snapshot / model_version / portfolio_return_run (→`calculation_run.run_id`) / portfolio. **Every DDL identifier ≤ 63 chars — checked at plan time, not discovered at PG** (the P3-8 lesson). |
| OD-BT-1-J | Snapshot | `PURPOSE_VAR_BACKTEST_INPUT`; **REUSES `COMPONENT_KIND_PORTFOLIO_RETURN`** (minted at P3-8) for the return rows; NEW **`COMPONENT_KIND_VAR`** (IA-row pin flavor) for the `var_result` rows. TR-09: a later VaR re-run or return re-run cannot move a historical backtest. |
| OD-BT-1-K | Review + flow | FULL multi-finder review before push; unreduced local gates (`make check` incl. `ruff format --check`, full local-PG + downgrade smoke, fe-check); the PR flow (Claude pushes the branch; the USER opens+merges). Fixtures TD-1-realistic; dedup findings FOLD by default (the clean-code standing bar). |

## Part 2 — External benchmark research (roadmap Part 4 rule 6; sources checked 2026-07-10)

- **Kupiec (1995)**, "Techniques for Verifying the Accuracy of Risk Measurement Models", *Journal of
  Derivatives* 3(2) — the proportion-of-failures (POF) test: with `N` observations, `x` exceptions,
  coverage `p = 1 − confidence`, `LR_POF = −2 ln[(1−p)^(N−x) p^x] + 2 ln[(1−x/N)^(N−x) (x/N)^x]`,
  asymptotically χ²(1). Well-defined at the `x=0` / `x=N` edges under the `0⁰ = 1` convention.
- **Basel Committee (January 1996)**, "Supervisory framework for the use of backtesting in
  conjunction with the internal models approach" — the traffic-light zones are defined for
  **250 trading-day windows at 99%**: GREEN 0–4 exceptions, YELLOW 5–9, RED ≥ 10 (with multiplier
  add-ons we do NOT compute in v1 — the zone is the recorded output, the capital multiplier is a
  later regulatory-reporting concern). The zone table has NO defined meaning off (99%, 250) — hence
  OD-G's domain-only emission.
- **Basel distinguishes "actual" vs "hypothetical" (clean) P&L** for backtesting; FRTB carries both
  requirements forward. v1 ships the flow-adjusted ACTUAL leg (OD-D); the hypothetical leg needs
  static-portfolio repricing the platform does not yet have — deferred, recorded.
- **Christoffersen (1998)**, "Evaluating Interval Forecasts" — the independence / conditional-
  coverage tests. DEFERRED in v1 (needs exception-sequence modeling; Kupiec-first is the standard
  minimal outcomes-analysis battery). Recorded as the natural BT-2 extension.
- **SR 11-7** (Fed/OCC model risk management) — backtesting is the named "outcomes analysis" leg of
  ongoing monitoring; this slice is the platform's first executable instance of it.

## Part 3 — Limitations carried forward + out of scope (recorded)

1. **Captured-holdings P&L bias propagates** (the PM-1 first-class limitation, named for the third
   time per the OD-K obligation): uncaptured income understates realized P&L, which UNDERSTATES
   exceptions — a backtest over a leaky book is anti-conservative. Mitigation stays operational.
2. **Actual-only P&L** — hypothetical/clean P&L backtesting deferred (no static repricing engine).
3. **Kupiec only** — no Christoffersen independence/conditional coverage (BT-2), no Basel multiplier
   arithmetic, no p-values (critical-value decisions at the declared alpha only).
   > **Cross-note added 2026-07-15 (BT-2, additive — the ratified text above is unchanged):** the
   > "BT-2" label here predates Wave 5 and meant *the Christoffersen extension*. Wave 5's ratified
   > **BT-2 is the total-series admit** (`bt_2_decision_record.md`), which took the name first. The
   > Christoffersen independence/conditional-coverage leg is now a named **BT-3 candidate**, along
   > with the appraisal-frequency pairing. BT-2 also DISCHARGED this record's implicit one-method
   > scope-out for the total family: `VAR_PARAMETRIC_TOTAL` is backtestable, under the recorded
   > honest-pairing doctrine (see `var_backtesting_v1.md`'s BT-2 scope amendment).
4. **Small-N honesty** — Kupiec is asymptotic; `KUPIEC_LR` is emitted for any `N ≥ 1` with `n_pairs`
   recorded on every row so a reader can weigh it; the Basel zone refuses to exist off its domain.
5. **Calendar-day horizon interpretation** (consistent with PM-1's calendar-day Dietz); trading-day
   calendars are the same deferred data-quality slice P3-8 recorded.
6. One backtest run = ONE VaR method; cross-method comparison is two runs side-by-side (no joint test).

## Part 4 — Open decisions (OQ-BT-1-1…9) — pending ratification

- **OQ-1** — Family home + permission REUSE (`risk.run`/`risk.view`, run_type `VAR_BACKTEST`) per OD-B. *(Recommended: yes.)*
- **OQ-2** — STRICT exception inequality (`realized_loss > var_value`) per OD-F. *(Recommended: strict.)*
- **OQ-3** — Whole-run refusal on ANY unpaired forecast/period (vs pair-what-matches) per OD-E. *(Recommended: refuse — silent partial pairing is a mismeasure.)*
- **OQ-4** — Declared `alpha ∈ {0.05, 0.01}` with fixed χ²(1) criticals; recommend **0.05** as the default registration. *(Recommended: yes.)*
- **OQ-5** — Basel zone emitted ONLY on its defined (0.99, 250) domain per OD-G. *(Recommended: yes.)*
- **OQ-6** — `metric_value` scale: **NUMERIC(28,6)** (parity with `var_value`; currency P&L, counts, 0/1 indicators, and an LR statistic where 6dp is decision-adequate vs 3.841459) — vs NUMERIC(28,12). *(Recommended: 28,6; the LR inputs are exactly reproducible from pins, so 6dp presentation loses nothing auditable.)*
- **OQ-7** — Per-pair `EXCEPTION_INDICATOR` evidence rows included (vs summary-only). *(Recommended: include — the exception series IS the audit evidence.)*
- **OQ-8** — The portfolio-identity mechanism: models-only `exposure_aggregate` read per pinned VaR row per OD-H. *(Recommended: yes — the only honest cross-series gate available; `var_result` carries no `portfolio_id`.)*
- **OQ-9** — Review mode: FULL multi-finder local review (the P3-8 protocol) vs cloud ultrareview. *(User's call at implementation time; either satisfies OD-K.)*

## Part 5 — Implementation readiness gate

Implementation starts ONLY on explicit direction after OQ ratification, against
`bt_1_implementation_plan.md` (the 8-step build contract). Model/effort recommendation for the
implementation: **Opus 4.8 / high** — templated on the PM-1/P3-8 exemplars (kernel + binder +
snapshot + migration + API + FE + tests) with one genuinely novel leg (the alignment/pairing
adjudication), which the FULL review covers.

## Part 5.5 — Implementation deviations from the ratified plan (recorded during the build)

1. **Exact-linkage cross-check → MV-CHAIN check.** The plan carried the P3-8 exact-linkage gate
   (`Π(1+r_i)−1 == TWR_LINKED`) into the return-side adjudication, but recomputing the link needs
   perf's compounding kernel and **risk must not import perf** ("nothing imports perf"); duplicating
   the kernel in risk would recreate the exact duplication the P3-8 cleanup removed. The binder
   instead enforces `begin_mv_{i+1} == end_mv_i` across contiguous sub-periods (the SAME boundary
   valuation appears on both sides in a well-formed PM-1 output) — a STRONGER gate for THIS number,
   because it adjudicates exactly the columns the realized P&L consumes (`begin_mv`/`end_mv`/
   `net_external_flow`; `return_value` is not read at all). The one-TWR_LINKED-row and contiguity
   shape checks are kept as planned.
2. **`portfolio.guards` relocation.** The shared `assert_portfolio_in_tenant` guard (created in the
   P3-8 cleanup as `perf/guards.py`) moved to `portfolio/guards.py`: BT-1's risk binder needs the
   same P3-5 cross-tenant-FK check and the perf home violated the fence. Both perf binders + both
   tests updated; one implementation, no wrapper.

## Part 6 — Review dispositions + closure (appended at closeout, 2026-07-11)

**CLOSED.** Planning `3e81ef4` merged via **PR #4** (`1da87c7`); implementation `e7b615d` merged
via **PR #5** (`868f892`), CI green. Migration `0033`; validation: `make check` 1168 / local PG
28/28 / downgrade smoke 0033↔0032 / fe-check 52.

**Review (OD-9):** a FULL 4-finder local max-effort review (kernel+binder math; persistence+
migration+ORM; cross-file+API+FE; cleanup/conventions+test-quality+docs-sync), user-authorized in
lieu of the cloud ultrareview. All hard invariants verified intact. **14 findings, 13 folded:**

1. **HIGH — NaN VaR-value detonation.** A hand-minted `NaN` `var_value` passed adjudication
   unchecked and raised an uncaught `InvalidOperation` inside `_compute` — a raw 500 with the run
   orphaned in `RUNNING` (PG's `numeric` type accepts `NaN`, so this was column-legal). Fixed:
   `var_value` is quantized at parse INSIDE the pre-create wrapper, so `NaN` now raises
   `InvalidOperation` → the governed 422, never a post-create crash. This also fixed finding 3.
2. **MED — Basel zone gate was horizon-blind.** The domain gate checked only
   `(confidence == 0.99, n_pairs == 250)`; the Basel table is defined over 250 ONE-DAY
   observations, and a future multi-day-horizon VaR registration (the recorded sqrt(h) seam) would
   have minted an off-domain zone row. Fixed: `horizon_days == 1` added to the gate
   (`_BASEL_HORIZON_DAYS`).
3. **MED — unquantized `var_value` echo.** Folded into finding 1's fix (one quantize-at-parse
   line kills the NaN hole AND pins the stored echo byte-identical across engines).
4. **MED — snapshot builder accepted an empty `var_run_ids` list.** `build_var_backtest_snapshot`
   would mint a permanent, undeletable "VAR-less" `VAR_BACKTEST_INPUT` snapshot on `[]` — contrary
   to its own docstring and the `build_factor_exposure_snapshot` precedent. Fixed: refuses BEFORE
   any write; a direct-builder test added (`test_builder_refuses_empty_var_run_ids`).
5. **MED — the BASEL_ZONE emission branch had ZERO test coverage.** The only code path that mints
   the flagship supervisory row never executed in any test (only the off-domain negative was
   covered). Fixed: `test_basel_zone_emitted_on_domain` (the `_BASEL_PAIRS` monkeypatch seam,
   mirroring the existing `_MAX_RESULT_ABS` precedent) exercises the mint path end-to-end.
6. **LOW — unnecessary FK-name shortening.** The auto-style FK name
   `fk_var_backtest_result_portfolio_return_run_id_calculation_run` is 62 chars — UNDER the 63-char
   cap — but I shortened it anyway, over-applying the P3-8 lesson (where the analogous name really
   was 68 chars) without re-measuring. Reverted to the naming-convention name; ORM and PG now carry
   identical constraint names (no spurious future schema-diff).
7. **LOW — unused backdatable `as_of` params on the builder.** `build_var_backtest_snapshot`
   accepted `as_of_valid_at`/`as_of_known_at` but performed zero as-of reads (both sides are IA
   rows read as they exist now) — the params bound nothing yet let a caller stamp a permanent,
   pre-content knowledge-time claim onto the immutable header. Dropped (the `build_var_snapshot`
   precedent: an IA-only pin set takes no cutoffs).
8. **LOW — methodology doc contradicted the code.** The doc still promised the exact-linkage check
   Part 5.5 deviation 1 replaced, and claimed "BOTH VaR methods" golden-tested when
   `VAR_HISTORICAL` had zero coverage anywhere. Fixed: the doc now describes the MV-chain gate +
   the 6dp decision-basis + the horizon-gated Basel domain; a full HS-VaR backtest golden
   (`test_build_path_historical_var_method`) makes the "both methods" claim true rather than
   softening it.
9. **LOW — one-sided TR-09 test.** The reproducibility test re-ran only the VaR side; the
   docstring/RTM claimed "either side". Fixed: the test now re-runs BOTH the VaR side and the
   return side (a whole new `portfolio_return_result` run) and proves the pinned snapshot still
   reproduces the ORIGINAL rows.
10. **LOW — misleading registrar error details.** A same-label re-registration with a different
    declared `alpha` mapped to a 409 detail claiming a `code_version` mismatch (factually wrong for
    that case); a malformed/non-REGISTERED twin mapped to a "different model" 422 (also wrong).
    Fixed in both `api/risk.py` and `api/perf.py` (the same pattern) with accurate, uniform detail
    strings; the raw `str(exc)` echo on the alpha-vocabulary `ValueError` replaced with a fixed
    opaque detail (the file's own convention elsewhere).
11. **Docs — stale family-count comments.** "the FOUR/FIVE risk families" bumped to "the SIX" in
    `api/risk.py` and `risk/queries.py` after BT-1 joined the listing.
12. **Docs — Kupiec decision basis undeclared.** The registered assumption text said only "12dp
    internally"; it now states the decision is taken on the STORED 6dp value against the 6dp
    critical (a knife-edge LR within ~5e-7 of a critical follows the stored value, not the
    unquantized statistic) — an intentional, now-documented design choice.
13. **Docs — ENT-055 registry row.** Amended to say "250 ONE-DAY pairs" (the horizon leg of the
    Basel domain), matching finding 2.

**Deferred, with recorded reasons (not silently):**
- **A — the P3-8/BT-1 return-side adjudication-shape duplication.** `_adjudicate_pins`'s DIETZ/
  TWR_LINKED/contiguity/single-run-portfolio-base checks are near-verbatim between
  `benchmark_relative_service.py` and `var_backtest_service.py`. The "nothing imports perf" fence
  justifies not sharing the *adjudicator function*, but not the duplication itself — a neutral-
  homed "well-formed ENT-053 shape" helper is plausible. Per the ratified P3-4-R0 tipping-point
  rule (extract at the THIRD consumer, not the second), this is deferred — BT-1 is ENT-053's
  SECOND downstream consumer (PM-1 → P3-8 → BT-1 is the return-run chain; P3-8 and BT-1 are its
  two consumers so far). Trigger: a third governed number reading `portfolio_return_result` shape.
- **B — concurrent first-registration returns a raw 500.** Two simultaneous first-registrations of
  the SAME `(code, code_version, …)` identity both pass the existence check and race to INSERT;
  the loser's `IntegrityError` at flush is uncaught → 500. This is a PRE-EXISTING pattern shared
  identically by ALL SIX family registrars (sensitivity/factor-exposure/covariance/var/active-risk/
  portfolio-return/benchmark-relative/var-backtest) — not a BT-1 defect, and fixing it properly
  means one shared hardening pass (a savepoint-and-retry or an `IntegrityError` → identity-conflict
  translation) across the whole registrar family, not a ride-along patch to one. Trigger: the next
  slice that touches model registration, or a dedicated hardening slice if concurrent registration
  becomes an observed operational risk.

**Build finding worth the record:** the HS-VaR adequacy floor (`window_observations` must exceed
`1/(1-confidence)`) surfaced during test-writing, not design — the 0.99-confidence test fixture
needed 101 observations where 4 sufficed for the parametric method; the second HS golden used
0.95/21 instead to keep the fixture small while staying realistic (TD-1).
