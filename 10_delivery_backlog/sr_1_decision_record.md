# SR-1 Decision Record — the Sharpe ratio over the governed return series (Wave-13 slice 2; the 22nd governed number)

| | |
|---|---|
| Status | **DRAFT — pre-ratification verifier pass pending** |
| Slice | Wave-13 slice 2, per the ratified sequence (Wave-12 close OQ-W12C-2=A); follows RM-1 |
| Kind | A **governed number** — new result family, new registered model, ONE new captured data series (through an EXISTING capture family); no permission, no audit code |
| Counts | 24/39/132 → **25/40/133** (+1 model code, +1 INITIAL validation record filed EXPLICITLY in the demo stage — the RM-1 lesson — and +1 COMPLETED run) |
| Entity / migration | **ENT-065** `sharpe_ratio_result` (fork at OQ-SR-1-3) / migration **`0055`** |
| Demo | stage **17**, suite `test_demo_stage9zzzzzzzz_sr1_pg.py` (**EIGHT `z`** — verified by `ls`, not from a record; the RM-1 trap) |
| Sizing | **M — revised UP from the roadmap's S/M** (§0.1 item 2) |

## Part 0 — What SR-1 is

RM-1 gave the governed return series its risk reading — volatility and drawdown per trailing window. SR-1 is the **risk-adjusted return**: the Sharpe ratio, `SR = mean(excess) / σ(excess)`, per trailing window on the same calendar-month grid, where `excess_j = m_j − r_f,j` against a **captured risk-free return series**. It is the number an allocator quotes first and the one every prior slice deferred.

It deliberately reuses RM-1's machinery — the month relink, the alignment gate, the `stats_kernel` estimators, the window shape, the four-column grain pattern, the suppression encoding — and adds exactly two new things: the risk-free leg, and the ratio.

## Part 0.1 — Claims corrected before they became premises (OQ-W12C-3a)

1. **"Rides existing ENT-052/ENT-021 capture" is true of SCHEMA, misleading about WORK.** The ratified sentence was *"no new capture **family**"* — correct: `benchmark_return` (ENT-052) exists, is FR-bitemporal, carries fraction returns at the shared 12dp scale, has an open `(code, source)` identity, has **no frequency column** (so a monthly series is capturable today with zero vocabulary change), and already has a governed pin flavor (`COMPONENT_KIND_BENCHMARK_RETURN`, P3-8). But **no risk-free data exists anywhere** (`risk-free` appears in no code and no requirements doc), and **no captured series overlaps the only book SR-1 can run on**: RM-1's stage-16 book spans 2023-12 → 2025-06 monthly; every captured index/curve/factor series sits in 2026-05/06, daily. SR-1 must capture a ~19-row monthly risk-free series and ship the demo stage that seeds it, regardless of fork.
2. **The S/M sizing is not defensible.** The two preceding slices were both under-sized on the same optimism ("a small cadence slice" → M/L; "computable today, a cheap slice" → M with the largest review in project history). SR-1 carries: a new entity + migration, a new capture series + demo stage, a new snapshot purpose + builder, a kernel + binder + reads, a REQ mint, a methodology doc with rule-6 grounding, a PG enforcement suite from birth, and the count-pin relocation (item 4). That is **M**.
3. **RM-1's `ROLLING_VOLATILITY` is σ(portfolio), NOT the Sharpe denominator.** Sharpe (1994) divides by the standard deviation of the **excess** series. Reusing RM-1's persisted volatility rows is only correct when `r_f` is constant over the window — a special case, not a design. And the monthly return series itself is **not persisted** (`rolling_risk_result` stores window aggregates only), so SR-1 re-derives it from the same pins via the same kernel helpers. Nothing is read from RM-1's result rows.
4. **The stage-16 "final-position" count pin stops being final the moment stage 17 lands.** `test_demo_stage9zzzzzzz_rm1_pg.py` pins 24/39/132 "where the counts are actually FINAL" — true until the next stage. SR-1 must (a) demote that pin to an explicitly-intermediate one (asserting the post-stage-16 totals it can still see) and (b) carry the final-position pin forward into its own suite at 25/40/133. **The final-position pin is a RELAY BATON, not a monument** — recorded here so the next slice inherits the rule instead of rediscovering it.

## Part 1 — The inputs, file:line grounded (`8de96f4`)

- **The portfolio leg** = RM-1's substrate unchanged: one COMPLETED `PORTFOLIO_RETURN` run's `DIETZ_PERIOD` rows, pinned via `portfolio_return_content` (carries `metric_type`/`period_start`/`period_end`/`return_value` — sufficient, no new pin keys). Relink + alignment + `1+m>0` via `perf/rolling_kernel.py` (`relink_to_months`, `assert_month_aligned` — now five conditions — and `assert_above_total_loss`); estimators via `perf/stats_kernel.py` (lifted at RM-1 to be domain-neutral for exactly this consumer).
- **The risk-free leg (fork OQ-SR-1-2).** Preferred: ENT-052 `benchmark_return` (`marketdata/models.py:793-839`) — grain `(tenant, benchmark_id, return_date, return_type, return_basis)`, `return_value` `PreciseDecimal(20,12)` fraction, FR bitemporal. **Binding constraint, twice-ratified:** *"captured vendor-published values ONLY — NEVER computed from levels"* (`models.py:796-798`; `p2_6_decision_record.md:125`; restated `p2_7_decision_record.md:9`). SR-1 honors it by capturing vendor-published monthly **returns** directly; if a chosen source publishes only index **levels**, level→return conversion is a registered-model exercise this slice refuses to smuggle in. Alternative: ENT-021 `curve`/`curve_point` — yields, not returns (`value_type ∈ {ZERO_RATE, PAR_RATE, DISCOUNT_FACTOR, SPREAD}`); a registered yield→period-return `model_version` (a second Tier-3 methodology decision) plus **one curve header and one `CurveSelector` per month-end** (19 of each — there is no curve-series pin primitive). Materially more expensive; recorded, not recommended.
- **The snapshot shape** = P3-8's, reused: `build_benchmark_relative_snapshot` (`snapshot/service.py:1604-1643`) already pins one PM-1 run's rows PLUS the in-window `benchmark_return` rows. SR-1's builder is that shape under a new purpose (`SHARPE_INPUT`) with the window = the return run's span.
- **The ratio precedent is SPLIT, and SR-1 must pick (fork OQ-SR-1-4).** P3-8's information ratio **omits** the row when TE = 0 (`benchmark_relative_kernel.py:125-133` — "the binder OMITS the IR row, never fabricates a value"). RM-1 **suppresses-and-discloses** (nullable value + flag + reason under a CHECK), and its 4-finder review found that even one silently-omitted row was a defect ("an UNDISCLOSED absence"). The conventions contradict; the newer one has review teeth behind it.

## Part 2 — Rule-6 external grounding (sources checked 2026-07-28)

Grades: **[V]** verified against a fetched primary source · **[C]** independently computed · **[U]** ours, never cited.

- **Sharpe (1966), "Mutual Fund Performance"** — the original "reward-to-variability" ratio: mean return over σ of the **total** return series. **[V]**
- **Sharpe (1994), "The Sharpe Ratio"** — the revised, now-canonical form: the **differential return** `d_t = R_Ft − R_Bt` (fund minus benchmark, here the risk-free), `SR = mean(d)/σ(d)`. **The denominator is σ of the EXCESS series.** SR-1 v1 implements Sharpe-1994; the 1966 σ(portfolio) form is exactly the "reuse RM-1's volatility" shortcut, and it is refused as a *silent* choice — if ever wanted, it is a second declared metric, not a substitution. **[V]**
- **Lo (2002), "The Statistics of Sharpe Ratios"** — under **iid** returns `SR(q) = √q · SR(1)` (the ×√12 monthly→annual operator); under autocorrelation this misstates, with the correction in Eq. 20 (exact only on log returns). SR-1 carries **√12 as the DECLARED iid convention** — the same demotion honesty as RM-1's Lo usage, and consistent with RM-1 carrying k=12 as its only grounded basis. The autocorrelation-corrected annualizer is a recorded v2 (this platform's own desmoothing slices exist because iid is false for its books — stated, not hidden). **[V]**
- **GIPS 2020** — does NOT require or define a Sharpe ratio. If presented, it is an "additional risk measure": **4.C.43.a** (describe it) and **4.C.44** (gross/net disclosure) apply; rows are gross-of-fees inherited from PM-1 and say so. **[V]**
- **The window set `{12, 36}`** is RM-1's registered domain reused **[U — ours]**; the suppression-disclosure stance extends GIPS 4.C.36's spirit beyond its letter, recorded as OUR convention exactly as RM-1 did.
- **SEC marketing rule** exposure: same posture as RM-1 (flagged to compliance; a legal determination outside this record).

## Part 3 — Design decisions

### OD-SR-1-A — The construction (Tier-3)
Per trailing window `W ∈ {12, 36}` ending at each month-end, over the relinked monthly series `m_j` and the captured risk-free series `r_f,j`:
- `excess_j = m_j − r_f,j` (both 12dp fractions on the same month grid; the subtraction is exact at 12dp — no quantize step is introduced);
- `SHARPE_RATIO = mean_return(excess) / sample_stdev(excess)` — both from `stats_kernel` (n−1, arithmetic mean, the disclosed c4 caveat carries over verbatim), the division at 50-digit context then `quantize_HALF_UP` 12dp;
- `SHARPE_RATIO_ANN = quantize(SR_stored × √12)` — **from the STORED 12dp value** (RM-1's declared-order precedent, so the emitted pair reconciles exactly), basis label `SQRT_12`, the iid caveat in the methodology doc AND the registered assumptions.
- **Preconditions, binder-side (the kernel raises stay defense-in-depth):** the five-condition month alignment on the portfolio leg (reused); `1+m>0` (reused — the wealth index is not needed for Sharpe, but a −100% month means the SERIES is broken and every RM-1 argument applies); **risk-free completeness** — a captured `r_f` return for EVERY month of the span, missing month = pre-create refusal naming it (NO imputation, no carry-forward); **uniform basis** — one `(benchmark_id, return_type=SIMPLE, return_basis)` series (mixed bases refused); a duplicate-month `r_f` capture refused (the current-head read makes this structural, asserted anyway).
- A negative or zero `r_f` is **legal input** (2020s Europe was negative; refusing it would refuse history).

### OD-SR-1-B — The risk-free source (Tier-3, the lead fork)
**Recommend ENT-052:** a risk-free series is captured as an ordinary benchmark — head `(code, source)` e.g. `("USD-CASH-1M", vendor)`, monthly `benchmark_return` rows, `return_type=SIMPLE`, `return_basis=TOTAL`, vendor-published returns (the twice-ratified never-derive-from-levels constraint honored on its face). Zero schema change; the P3-8 pin flavor reused. The rf head is a **request parameter** (`risk_free_benchmark_id`), re-resolved under the acting tenant pre-stamp (P3-5), echoed on every row as provenance. The ENT-021 alternative (registered yield→return model + 19 per-date curve headers/selectors) is recorded with its costs and NOT recommended for v1; it becomes attractive only when Wave-14 real-data onboarding lands genuine curve feeds.

### OD-SR-1-C — Entity: NEW ENT-065, not an ENT-064 extension (Tier-3)
Sharpe rows need `risk_free_benchmark_id` provenance that ENT-064 lacks. Extending ENT-064 means a NULLABLE provenance column on every existing row — a stuffed placeholder by another name (the 0028 doctrine), and a family whose rows have different provenance shapes behind one table. **Mint ENT-065 `sharpe_ratio_result`** carrying the RM-1 pattern verbatim: run/snapshot/model bound + `portfolio_return_run_id` hard FK + `risk_free_benchmark_id` hard FK (NOT NULL — every Sharpe row has one); four-column grain `(calculation_run_id, metric_type, window_months, period_start)`; nullable `metric_value` + `suppressed` + reason + the total-enumeration CHECK **declared in ORM and migration both** (the RM-1 name-drift lesson: suffix-only in both, pinned equal); `annualization_basis`, `sampling_frequency`, `n_observations`; IA append-only; symmetric FORCE RLS. Precedent: every perf family got its own entity when provenance differs (ENT-053/054/056/064).

### OD-SR-1-D — The undefined ratio: RM-1's convention, divergence from P3-8 RECORDED
`σ(excess) = 0` (a constant excess series — reachable: a constant-return book against a constant rf) makes the ratio undefined. **Emit a SUPPRESSED row** (`metric_value NULL`, `suppressed=TRUE`, reason "zero dispersion — the ratio is undefined"), never omit (P3-8's convention) and never fabricate. Rationale: RM-1's review established silent omission as an UNDISCLOSED ABSENCE defect, and a Sharpe consumer keying `(SHARPE_RATIO, 12, NONE)` must be able to distinguish "not computable" from "not yet emitted". The P3-8 divergence is recorded here and in the methodology doc; harmonizing P3-8 retroactively is explicitly OUT of scope (its rows are shipped governed evidence). Unfillable windows suppress identically (RM-1 verbatim, including `_ANN` above 12 months).

### OD-SR-1-E — Run, model, permissions, audit
`RUN_TYPE_SHARPE_RATIO` (family ≠ metric, GS2); registered model `perf.sharpe` v1 — identity = `code_version` + the window domain `{12, 36}` + the Sharpe-1994 construction + the √12-iid annualization, all in the assumptions; window domain enforced pre-create (the RM-1 fold, inherited on day one). **No permission mint** (`perf.run`/`perf.view`); **no audit mint** (`CALC.RUN_*`; the PERF taxonomy row gets its "reserved set still three after a FIFTH family" sentence); zero-`PERF.*`-emissions test from birth. `PURPOSE_SHARPE_INPUT` joins the enforced allow-list; binding predicate `v1:portfolio-return-run-rows+rf-benchmark-window`.

### OD-SR-1-F — Reads, requirements, docs, controls
Rule-7 reads in-slice through `calc/reads.py` (`/perf/sharpe{,/latest,/{id}}`, `/latest` first, decimals as strings, NULL survives as NULL); the new `*RowOut` is covered by the derived FE guard automatically (verified at implementation, not assumed). **REQ-PRF-004** mint (CAP-20.6) backbone+RTM same commit, test-enforced both halves. Methodology doc `sharpe_v1.md` with the ten sections + per-source grades. **Control-matrix trace at closeout** (no mechanism moves — CTRL-002/003/018 instantiation; stated in this record's closeout section when written) + the **ledger-class omission sweep** as a closeout step (all six ledgers).

### OD-SR-1-G — Demo stage 17 + the tests the slice owes
Stage 17 (EIGHT `z`): captures the rf series (~19 monthly vendor-style rows overlapping stage-16's book exactly — realistic magnitudes per the test-data rule: ~0.30–0.45%/mo USD-cash-like, DECLINING through 2024-25), reuses stage-16's book and its EXISTING PM-1 run (no new return run), runs Sharpe at `{12, 36}` — 12 fills (7 windows), 36 suppresses; files the tier + INITIAL validation EXPLICITLY (the RM-1 omission not repeated); relocates the final-position count pin (§0.1 item 4). Owed tests, each with its executed control: **golden Sharpe values on a hand-computable series** (mutation-test the NUMBER — the RM-1 standing lesson, first-class scope here, not review-added); excess-not-portfolio σ (a fixture where the two denominators DIFFER, pinning the excess one — the discriminating test, designed before code); the missing-rf-month refusal naming the month; the zero-dispersion suppression; the σ/annualized reconciliation on persisted rows; the PG suite (CHECK matrix + negative control, grain collision, append-only, RLS with belt and suspenders separate) **from birth**; the FAILED-run path; cross-tenant rf-benchmark refusal (P3-5).

## Part 4 — Open questions for the ratification gate

- **OQ-SR-1-1 (Tier-3) — the construction.** Sharpe-1994 (σ of EXCESS) on the monthly grid, windows `{12, 36}`, with binder-side rf-completeness/uniform-basis preconditions? *Recommend APPROVE.* The 1966 σ(portfolio) form is available only as a future SECOND declared metric, never a silent substitution.
- **OQ-SR-1-2 (Tier-3) — the risk-free source.** ENT-052 vendor-published monthly returns as an ordinary benchmark head (zero schema change; never-derive-from-levels honored), rf head a per-run request parameter? *Recommend APPROVE.* ENT-021 + a registered yield→return model is the recorded, costed alternative.
- **OQ-SR-1-3 (Tier-3) — the entity.** NEW ENT-065 `sharpe_ratio_result` (rf provenance NOT NULL) vs extending ENT-064 with a nullable column? *Recommend NEW ENTITY* — no nullable-placeholder provenance, per-family entities are the precedent.
- **OQ-SR-1-4 — the undefined ratio.** RM-1's suppress-and-disclose, with the P3-8 divergence recorded and P3-8 left untouched? *Recommend APPROVE.*
- **OQ-SR-1-5 — annualization.** `√12 × SR_stored` as the DECLARED iid convention (Lo), reconciling exactly from the stored value; the autocorrelation-corrected annualizer a recorded v2? *Recommend APPROVE.*
- **OQ-SR-1-6 — sizing + scope.** M (not S/M), explicitly including the rf capture, demo stage 17, the PG suite from birth, and the count-pin relay? *Recommend APPROVE.*

## Part 5 — Pre-ratification verifier pass

*To be run before the gate (the ES-1 standing lesson) — two lanes: mathematics/methodology and engineering/governance.*

## Part 6 — Implementation plan

*To be written after ratification.*
