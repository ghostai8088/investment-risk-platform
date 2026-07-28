# Methodology — Sharpe Ratio over the Governed Return Series v1

**Model code** `perf.sharpe` · **version label** `v1` · **entity** ENT-065 `sharpe_ratio_result` · **migration** `0055` · **slice** SR-1 (Wave-13 slice 2; the platform's 22nd governed number)

## Purpose & applicability

The number an allocator quotes first: how much return this book earned **per unit of risk taken, above cash**. RM-1 gave the governed return series its risk reading (volatility, drawdown); SR-1 divides the one by the other, over the same trailing windows on the same calendar-month grid.

It is deliberately **not** a benchmark-relative measure — the information ratio is P3-8's, on a different grain against a benchmark rather than a risk-free rate — and it is not a family of risk-adjusted measures. Sortino, Treynor and any downside-deviation denominator are out of scope and are not implied by shipping this one.

Applies to any single-portfolio book carrying a COMPLETED PM-1 run whose boundary grid partitions into whole calendar months, **and** a captured risk-free return series covering every measured month of that span. It does **not** apply to a book whose return series contains a month at or below −100% (a POLICY exclusion — see *Assumptions*, A6).

## Inputs & data policy

Two inputs, both pinned into a `SHARPE_INPUT` snapshot (binding predicate `v1:portfolio-return-run-rows+rf-benchmark-window`):

- **the portfolio leg** — one COMPLETED `PORTFOLIO_RETURN` run, as one `COMPONENT_KIND_PORTFOLIO_RETURN` component per `portfolio_return_result` row. RM-1's substrate unchanged, through the existing `portfolio_return_content` serializer, so **no new pin-key surface and therefore no historical pin drift**;
- **the risk-free leg** — one `COMPONENT_KIND_BENCHMARK_RETURN` series component pinning the in-span `SIMPLE`/`rf_return_basis` rows of an ENT-052 `benchmark_return` head (P3-8's pin flavor, ENT-052's second governed consumer).

**The risk-free series is a CAPTURE, and v1 accepts vendor-published RETURNS only.** ENT-052's twice-ratified constraint — *"captured vendor-published values ONLY — NEVER computed from levels"* — is honored on its face. A source publishing index **levels** cannot be used here: level → return conversion is a registered-model exercise this slice deliberately refuses to smuggle in. A yield curve (ENT-021) would additionally need a registered yield → period-return model plus one curve header and selector per month-end; that path is recorded, costed and **not taken** in v1.

Other input policy, inherited from the family:

- **Computation reads pinned content only** (AD-014 / TR-09). Neither a later PM-1 re-run nor a vendor correction to the risk-free series can move a historical Sharpe number.
- The upstream run id, the book id **and the risk-free benchmark head** are re-resolved out of the pinned content under the acting tenant before any of them is stamped into a hard FK — PostgreSQL FK checks bypass RLS, so the database alone would durably admit a foreign tenant's run, book or benchmark (the P3-5 guard).
- Snapshot `valid_at`/`known_at` are stamped now/now (BT-1's precedent).
- **Nothing is read from RM-1's result rows.** `rolling_risk_result` stores window aggregates, not the monthly series, and its `ROLLING_VOLATILITY` is the wrong denominator (see A1). SR-1 re-derives the monthly series from the same pins through the same kernel helpers.

## Formulas & numerical standards

Over the relinked monthly series `m_j` (RM-1's `relink_to_months`, unchanged) and the captured risk-free series `r_f,j`, per trailing window `W ∈ {12, 36}` ending at each month-end:

```
excess          d_j    = m_j − r_f,j
Sharpe ratio    SR     = mean(d) / σ(d)          σ on the n−1 divisor
annualized      SR_ann = SR_STORED × √12
```

- **The subtraction is EXACT.** Both legs are 12dp fractions and Decimal subtraction at a common exponent is exact at that exponent regardless of context precision — verified across sign and magnitude extremes, not assumed.
- **Single quantization, and the order is load-bearing.** The mean and σ of the excess series are accumulated **UNQUANTIZED** at 50 digits, the division is performed at that precision, and only the **ratio** is quantized HALF_UP to 12dp. The alternative — dividing the quantized operands — was executed and refuted: a NON-constant excess series such as eleven values of `1E-12` and one `0` has a true σ of ≈`2.9E-13`, which quantizes to `0E-12`, so that order raises `DivisionByZero` on a perfectly legal input. This deliberately **contrasts** with RM-1's `annualize_volatility`, which must read its stored σ because RM-1 persists it; ENT-065 persists no mean and no σ, so no reconciliation constraint binds the internals.
- **The annualization DOES read the stored value**, for exactly RM-1's reason: ENT-065 persists both members of that pair, so a consumer must be able to multiply the raw row by √12 and land exactly on the annualized row. Sign is preserved — a negative Sharpe annualizes to a more negative Sharpe.
- **BOTH metrics are emitted at EVERY computable window, including W = 12.** RM-1 suppresses its redundant `ROLLING_RETURN_ANN` at 12 months because the geometric exponent is exactly 1 there; `√12 · SR ≠ SR` at any window, so that rationale does **not** transfer and is not imported.
- **The risk-free leg joins by MONTH KEY** `(year, month)`, never by date. The book's month-end convention is "the calendar month end or the last business day" (GIPS 2.A.23.b) while a vendor may date a monthly return anywhere in its month; joining on the date would refuse a perfectly aligned pair over a weekend.
- All values are `Numeric(20,12)`; the emit envelope is `|value| < 1E7` (see A5).

## Assumptions

**A1 — the denominator is σ of the EXCESS series, not of the portfolio series.** Sharpe (1966) divided by σ of the *total* return series; Sharpe (1994) revised this to the *differential* series, and that revised form is what this model computes. The distinction is not cosmetic: the two coincide only when `r_f` is constant across the window, which is a special case rather than a design. This is precisely why RM-1's persisted `ROLLING_VOLATILITY` rows are **not** reused, and a discriminating test pins a fixture where the two denominators genuinely differ.

**A2 — the divisor DIVERGES from the named paper, and the divergence is DISCLOSED.** Sharpe (1994)'s own endnote 1 uses the **population** standard deviation (divisor `T`). This model uses the platform's uniform `n−1` sample estimator, making σ larger by `√(12/11) ≈ +4.4%` at `n = 12` and the ratio correspondingly **≈4.3% smaller**. That is above this platform's own materiality bar, so the construction is described everywhere — including in the registered `model_assumption` rows — as *"Sharpe (1994)'s differential-return form with OUR n−1 divisor"*, never as "Sharpe (1994)" unqualified. GIPS does not prescribe `n` vs `n−1`; the choice follows the shared `stats_kernel` estimator and GIPS practice.

**A3 — √12 is a DECLARED CONVENTION, not a claim about the books.** Under **iid** returns Lo (2002) gives `SR(q) = √q · SR(1)`, and Sharpe (1994)'s own eqs. 7/8 carry the same operator (mean scales with `T`, σ with `√T` under zero serial correlation). Under **autocorrelation** this misstates; Lo Eq. 20 gives the correction, exact only on log returns, which this platform does not compute. The corrected annualizer is a recorded v2. Carrying iid as a *convention* rather than a *finding* is the honest posture: **this platform's own desmoothing slices exist because iid is false for its books.**

**A4 — the suppression predicate names the SAME σ the division uses.** A row is suppressed iff the **unquantized** σ is exactly zero — a genuinely constant excess series (Decimal equality is exact, so this is a real test rather than a tolerance). Sub-quantum dispersion divides finely and emits a large value, which the magnitude gate then adjudicates. This keeps the reason a consumer reads *true under its own predicate*.

**A5 — the ratio is UNBOUNDED on admitted inputs, so the magnitude gate ships from birth.** Twelve column-legal monthly returns can yield a Sharpe ratio of `10^10`, past both the `Numeric(20,12)` column and the house `1E7` envelope. The gate applies to the **EMITTED value, per row, covering the annualized member of the pair** — a column-fitting SR of `9×10^6` still overflows at ×√12. A breach is a **COMMITTED FAILED run with DQ evidence and zero rows**, never a partial emit and never an uncaught raise with the run stranded in RUNNING.

**A6 — `1 + m > 0` is POLICY, not domain necessity.** The Sharpe arithmetic computes cleanly at −100% and even −150%: there is no wealth index here and no geometric exponent. The grounds are that the monthly series is **shared substrate** with RM-1 — a book RM-1 refuses to carry a drawdown for must not quietly carry a Sharpe ratio — and that a month at or below −100% means the PM-1 series itself is degenerate (the no-cash-ledger pathology). Declared as policy, and labelled as such.

**A7 — risk-free completeness is a REFUSAL, and the asymmetry is the point.** Exactly one current-head risk-free return is required per **measured month** (the months contributing a monthly observation; `d_0`'s month contributes none). A missing month is a **pre-create refusal naming the month**; more than one is a refusal too. There is no imputation and no carry-forward. This is deliberately asymmetric with the per-window suppression convention below: window-insufficiency is structural and time fills it, whereas a missing risk-free month is a **capture gap an operator must fix**, and computing "the windows we can" over a gappy series would ship a partially-poisoned surface whose gaps are invisible to every downstream read.

**A8 — one series per run.** A single `(benchmark_id, return_type=SIMPLE, return_basis)` per run; mixed is refused, and the basis is echoed on **every row** as `rf_return_basis`. One benchmark head can publish three bases, and two Sharpe runs against the same head on different bases are different governed numbers.

## Suppression, not omission

A window the series cannot fill, and a window whose excess series is constant, both emit a governed **suppressed** row: `metric_value` NULL, `suppressed = TRUE`, and a reason, under a total-enumeration DB CHECK. Never omitted and never fabricated.

**Zero is a LEGITIMATE Sharpe ratio** — a book that exactly earns the risk-free rate over the window scores 0 — so a stuffed zero would be indistinguishable from "not computable", and would read as *"earned nothing above cash"* rather than *"we could not compute this"*.

The two suppression states remain distinguishable on the read surface: an unfillable window carries `n_observations` NULL (there is no sample); a zero-dispersion window carries its count (the sample exists, the ratio does not).

**This DIVERGES from P3-8, and the divergence is recorded rather than harmonized.** P3-8's information ratio *omits* the row when TE = 0. RM-1's review established silent omission as an **undisclosed absence** defect, and a consumer keying `(SHARPE_RATIO, 12, NONE)` must be able to tell "not computable" from "not yet emitted". P3-8's shipped rows are governed evidence and are left untouched; retroactive harmonization is explicitly out of scope.

## Validation / reproduction tests

- **Golden values computed by hand**, stated as arithmetic in the test file, for both the ratio and its annualization — and **mutation-tested**: five kernel mutants (`n−1 → n`, `√12 → 12`, the suppression predicate moved to the quantized σ, the risk-free leg dropped, a 1-ulp drift) and ten binder mutants, all executed and all killed. *This is the RM-1 standing lesson as first-class scope: a governed number whose refusal paths are tested and whose positive path is unpinned can ship a material error with every tier green.*
- **The discriminating fixture**: a constant portfolio series against a varying risk-free series, where σ(portfolio) is exactly zero and σ(excess) is not — so an implementation reaching for the portfolio σ fails loudly instead of shipping a plausible wrong number. Both premises are asserted before the claim.
- **The executed refutation** that a non-constant series whose *quantized* σ is `0E-12` still emits.
- The missing-, duplicate- and unconsumed-risk-free-month refusals, each naming the offending month; the month-key join proved against a vendor dating returns on the first of the month.
- Exact SR/SR_ann reconciliation on **persisted** rows (both in the unit tier and on the demo book), consuming the emitted rows rather than re-deriving them.
- The magnitude gate's COMMITTED FAILED run with zero rows.
- A **PostgreSQL enforcement suite from birth**: the suppression CHECK matrix with its dropped-CHECK negative control, the four-column grain collision, the append-only trigger, RLS isolation with a superuser negative control, and a `pg_constraint` read pinning the CHECK's **name** (the RM-1 drift class `alembic check` structurally cannot see).
- A platform-wide GS2 conformance test: no `run_type` value equals any `metric_type` value, for any family.

## Governed-number contract

Every row is **run-bound + snapshot-gated + model-bound** (AD-014 / FW-RUN / TR-15 / CTRL-003) with hard FKs to the consumed PM-1 run, the measured book, and the risk-free benchmark head. IA true append-only (the `irp_prevent_mutation` trigger + the ORM guard); symmetric FORCE RLS; four-column grain `(calculation_run_id, metric_type, window_months, period_start)`. The run reuses `CALC.RUN_*` — **no new audit code, no new permission, no new role**; the `PERF.*` block stays reserved-not-minted, still exactly three reserved codes after a fifth perf family.

## Known limitations (recorded; mirror the `model_limitation` rows)

1. **The ratio is unbounded** on admitted inputs; see A5.
2. **Rolling values are NOT independent** — adjacent 12-month windows share 11 of 12 observations, so a change between consecutive points reflects the single entering and exiting month, not a re-estimate. Inherited from RM-1's grid and equally the most likely misreading here.
3. **GIPS 2020 does not require or define a Sharpe ratio.** Presented, it is an *additional risk measure*: 4.C.43.a (describe it) and 4.C.44 (gross/net) apply. Rows are **gross-of-fees**, inherited from PM-1, and say so rather than inferring it.
4. **The risk-free series is a capture and its quality bounds the number** — vendor-published returns only in v1; see *Inputs & data policy*.
5. **No Sortino, no Treynor, no downside-deviation denominator, no daily grid** (`k = 252` is uncited here). No benchmark-relative variant: that is P3-8's information ratio, on a different grain.
6. `validation_status` **UNVALIDATED** — recorded, non-enforcing until a 2L validator records an outcome (VW-1); a REJECTED latest outcome, or an EXPIRED use-before-validation exception (MG-1), refuses every new bind at the shared seam.

## External benchmarks (roadmap Part 4 rule 6 — sources checked 2026-07-28)

Grades: **[V]** verified against a fetched primary source · **[C]** independently computed · **[U]** unverified, carried as **our** convention and never as a citation.

| Source | Used for | Grade |
|---|---|---|
| Sharpe, "Mutual Fund Performance", *J. Business* 39(1), 1966 | the original reward-to-variability ratio, and the σ(total) contrast this model does **not** implement | **[V]** |
| Sharpe, "The Sharpe Ratio", *JPM* 21(1), 1994 — the differential-return form; eqs. 7/8; **endnote 1** | the construction, the annualization operator, and the population-σ divergence disclosed in A2 | **[V]** |
| Lo, "The Statistics of Sharpe Ratios", *FAJ* 58(4), 2002 — the iid `√q` result; Eq. 20 | the ×√12 annualization and the recorded v2 correction | **[V]** (journal paywalled; published text fetched) |
| GIPS for Firms 2020 (CFA Institute) — 4.C.36, 4.C.43.a, 4.C.44 | additional-risk-measure disclosure, gross/net, and the suppression-disclosure spirit | **[V]** |
| The window set `{12, 36}` | **ours** — RM-1's registered domain reused rather than re-argued | **[U]** |
| The suppress-and-disclose convention beyond GIPS 4.C.36's letter | **ours**, recorded exactly as RM-1 recorded it | **[U]** |
| `k = 252 / 52 / 365` | **not carried.** The grid is monthly, so √12 is the only basis needed | **[U]** |

**Two claims the drafting made and the verifier pass refuted, corrected here rather than quietly dropped.** The draft stated Sharpe (1966)'s numerator as the mean *total* return; it is the mean return **in excess of the riskless rate** — the load-bearing half of that contrast is the denominator, and that half stands. And the draft graded *"implements Sharpe (1994)"* as **[V]**; the paper's own endnote refutes it at the divisor, which is why A2 exists.

**Paywalled primaries are disclosed, not laundered.** No numeric constant is transcribed from any source; only functional forms are carried.

## Reproducibility & governance

Reproducible from the snapshot alone (TR-09). The registered version identity is `code_version` **plus the declared window set** `{12, 36}` **plus the Sharpe-1994 construction and the √12-iid annualization**, all carried in the `model_assumption` rows — including the A2 divergence, which is the one an external reader is most likely to check. Whether an SR-1 read constitutes an "advertisement" under the SEC marketing rule (including its private-fund carve-out) is a **legal determination outside this document**, flagged to compliance — the same posture as RM-1.
