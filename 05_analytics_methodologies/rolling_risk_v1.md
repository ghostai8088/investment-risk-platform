# Methodology — Rolling Risk over the Governed Return Series (rolling return / rolling volatility / maximum drawdown) v1

**Model code** `perf.rolling_risk` · **version label** `v1` · **entity** ENT-064 `rolling_risk_result` · **migration** `0054` · **slice** RM-1 (Wave-13 slice 1; the platform's 21st governed number)

## Purpose & applicability

The trailing-window statistics a supervisor reads *next to* a return: how much the book made over the last twelve months, how volatile that path was, and how far it fell from its own high-water mark. PM-1 (ENT-053) has persisted a governed dated per-period time-weighted return series since Wave 5; nothing consumed it for **risk of the return series**. RM-1 is that consumer.

It is deliberately **not** the Sharpe ratio (SR-1, the next slice) and not a re-litigation of PM-1's scope. PM-1's registered assumptions already name √T/^T scaling as "a later declared transform"; RM-1 is that slice, and discharges the deferral **explicitly, partially and narrowly** — volatility only, on a monthly grid, by ×√12.

Applies to any single-portfolio book carrying a COMPLETED PM-1 run whose boundary grid partitions into whole calendar months. It does **not** apply to a book whose return series contains a month at or below −100% (see *Known limitations*).

## Inputs & data policy

The sole input is **one** COMPLETED `PORTFOLIO_RETURN` run, pinned into a `ROLLING_RISK_INPUT` snapshot as one `COMPONENT_KIND_PORTFOLIO_RETURN` component per `portfolio_return_result` row.

- **No new pin-key surface.** The existing `portfolio_return_content` serializer already carries `metric_type`, `period_start`, `period_end`, `return_value` and `n_periods` — everything the month partition, the relink, the volatility, the rolling return and the compounded-index drawdown require. Reusing it verbatim means **no historical pin drifts**.
- **Computation reads pinned content only** (AD-014 / TR-09). A later re-run of the upstream PM-1 run cannot move a historical rolling number.
- The upstream run id and the book id are **re-resolved out of the pinned content** under the acting tenant before either is stamped into a hard FK — PostgreSQL FK checks bypass RLS, so the database alone would durably admit a foreign tenant's run (the P3-5 guard).
- Snapshot `valid_at`/`known_at` are stamped now/now (BT-1's precedent): both sides are immutable append-only rows with no valid/known axis to reconstruct, so a caller-supplied cutoff would be a backdatable knowledge-time claim binding nothing.

## Formulas & numerical standards

Let the pinned `DIETZ_PERIOD` sub-period returns be `r_1 … r_n` over boundary dates `d_0 … d_n`.

**1 — Relink to calendar months.** For each calendar month `M`, `m_M = Π_{i ∈ M}(1 + r_i) − 1` (GIPS 2.A.24.f). Every statistic below is computed on the resulting **monthly** series `m_1 … m_N`.

**2 — Rolling return.** For a window of `W` months ending at index `k`: `R = Π_{j=k−W+1}^{k}(1 + m_j) − 1`, annualized as `R_ann = (1 + R)^(12/W) − 1`.

**3 — Rolling volatility.** `σ = sample_stdev_{n−1}(m_j)`, centred on the arithmetic mean, annualized as `σ_ann = quantize(σ_stored × √12)`.

**4 — Maximum drawdown.** On the compounded wealth index `V`, rebased to `1` at the window's opening boundary: `MDD = max_k[(peak_k − V_k)/peak_k]` with `peak_k = max_{j ≤ k} V_j`, running peak, no look-ahead.

All arithmetic in `Decimal` at 50-digit precision; results `quantize_HALF_UP` to 12dp (the `Numeric(20,12)` fraction scale — **not** currency). The magnitude envelope (`1E7`) is applied to the **emitted, post-annualization** value: annualizing amplifies, so gating the pre-transform number would let an out-of-range row reach the flush.

**The quantize ORDER for volatility is declared and load-bearing.** `σ_ann` multiplies the already-quantized 12dp **stored** value, not a higher-precision intermediate, so the emitted pair reconciles **exactly**: a reader can multiply the unannualized row by √12 and land on the annualized row. This costs ≤2 ulp at 12dp against a single-quantization path, accepted because it is what makes emitting both rows honest rather than merely redundant.

## Assumptions

**A1 — The monthly grid, and why sub-periods are not the sample.** GIPS defines the ex-post risk statistic **only** on the monthly series (4.A.1.j) over inputs valued *"at least monthly"*, *"as of the calendar month end or the last business day of the month"* (2.A.23.a/b). Sub-period returns are, by construction, inputs: the *Guidance Statement on Calculation Methodology* defines the sub-period as "the period between external cash flows". RM-1 therefore refuses the sub-period alternative on the **standards** ground.

The estimator-theory corroboration is carried but **explicitly demoted**: Lo (2002) Eq. 19, `Var[R_t(q)] = qσ² + 2σ²Σ_{k=1}^{q−1}(q−k)ρ_k`, gives `qσ²` at `ρ=0`, so variance scales with interval length and unequal sub-periods are heteroskedastic by construction. Three honest caveats: Eq. 16 defines the q-period return as a **sum**, "ignoring the effects of compounding for computational convenience"; applying Eq. 19 to a Dietz series posits a latent daily stationary process; and the `ρ=0` step is an i.i.d. assumption this platform's own desmoothing slices exist because it is false for its books. **And the honest limit of the fix:** calendar months are 28–31 days, so the monthly grid is itself heteroskedastic by ≈5.2% (≈7.6% on trading days). The grid is **conventionalized by the standard, not made homogeneous by mathematics** — a difference of degree, not kind.

**A2 — Month-end means calendar month end OR the last business day.** GIPS 2.A.23.b, in full. This matters: 2026-01-31 is a Saturday and 2026-05-31 a Sunday, so a firm valuing on the preceding Friday is fully conforming, and a strict calendar-month-end gate would **refuse a compliant book while citing GIPS as its authority**. v1 implements the allowance holiday-free (last calendar day, or the last weekday when that falls on a weekend).

**A3 — Alignment is a FIVE-condition conjunction.** `d_0` is a month-end; `d_n` is a month-end; every interior calendar month contributes a month-end boundary; **`d_0` is the LAST boundary in its own month**; and **every measured month closes on a month-end**. Extra intra-month boundaries are fine — they relink. A partial leading or trailing month is a **refusal, never a truncation**: truncating would silently change the caller's requested span, and imputing a valuation is prohibited.

Conditions 4 and 5 were added after review. Three conditions are **not** sufficient, because `is_month_end` accepts *both* the last weekday and the weekend calendar end, so one month can hold two of them: `2026-01-30` (Friday) followed by `2026-01-31` (Saturday) passes conditions 1–3 and yields a **one-day "January"** pooled into σ, ×√12, the drawdown and the 12-month return — a dispersion ratio of √31 ≈ 5.6× against a whole month, four times worse than the 1.32× partial-edge case conditions 1–2 exist to prevent.

**A4 — n−1, arithmetic centring, and no c4 correction.** GIPS does not prescribe `n` vs `n−1`, and the choice is material: `√(n/(n−1))−1` is **+4.45% at n=12** and +1.42% at n=36. The square root of an unbiased variance is itself a **downward-biased** estimator of σ by `1−c4(n)` ≈ **2.24% at n=12** — GIPS and CFA Institute both use it and neither applies a c4 correction, and RM-1 follows them. Centring is arithmetic although returns link geometrically: an internal tension in the standard, documented rather than silently resolved.

**A5 — Annualization, per metric.** Volatility ×√12 [V]. Returns geometrically, never below a 12-month window (GIPS 2.A.12: *"Returns for periods of less than one year must not be annualized"*) — **enforced at the registered parameter domain** `{12, 36}`, not at the kernel guard, which is honest defense-in-depth. At `W=12` the exponent is exactly 1, so the annualized return is definitionally the cumulative return and the redundant row is **suppressed**. Maximum drawdown is **never** annualized: a bounded, saturating, horizon-monotone statistic has no horizon-scaling law at all.

**A6 — Drawdown construction.** Window-**local** rebasing (a run-global peak would import a high-water mark from outside the window and report a "12-month maximum drawdown" for a drawdown that did not occur in it). Note `MDD_36 ≥ MDD_12` holds under **both** conventions and therefore does not evidence this choice — corrected after review. The base point `V_0 = 1` **is an observation** with drawdown zero — omitting it makes a window that opens on a loss report **0.00 instead of 0.10**, a 10pp error converting a real drawdown into something indistinguishable from "no drawdown". Computed on the linked **TWR** index, not a NAV path: a NAV path includes external flows, so a redemption would register as a "drawdown" that is not a performance event.

**A7 — The `1 + m > 0` precondition.** Enforced pre-create, naming the offending month. PM-1 admits `EMV = 0` (yielding exactly `−1`) and `link_periods` has no such guard, so the wealth index would be absorbing, the ratio-to-peak could exceed 1 or invert sign, and the geometric annualization would raise on a negative base.

## Validation / reproduction tests

- The three-condition criterion: a within-month series refuses (the defect that made the first draft self-contradictory); a partial leading month refuses; a partial trailing month refuses; a missing interior month refuses **and is named**; extra intra-month boundaries are accepted.
- `V_0` as an observation: `−10%` then eleven `+1%` months yields `0.10`, not `0.00`.
- `MDD_36 ≥ MDD_12` at a common end date (to within 1 ulp at 12dp — a half-way rounding point can invert the last digit). **This does NOT prove window-local rebasing**: the inequality holds under a run-global peak too. The discriminating test opens a window while the book sits below an earlier run peak.
- Every emitted σ/σ_ann pair reconciles exactly, checked on rows **persisted through PostgreSQL**.
- The mirrored month-end rule is **conformance-pinned** against `scheduling.service`'s implementation across twelve years.
- The demo stage (16) proves the fixture's controls are reachable: 19 sub-periods over **18** distinct months (one month genuinely relinked two), a worst 12-month drawdown of `0.2321`, and four suppressed rows beside legitimate zeros from the same run.
- Guards are **mutation-tested** — the source is broken and the test must fail. **Stated honestly after the 4-finder review, which falsified the earlier unqualified claim:** the refusal and alignment edges were mutation-tested, the POSITIVE computational path was not, and four mutants survived the whole suite (the geometric link replaced by an arithmetic sum; volatility over the wrong slice; a run-global drawdown peak; an alignment filter). All four are now killed by golden-value tests. The lesson recorded rather than buried: mutation-testing the guards you thought of is not the same as mutation-testing the number.

## Governed-number contract

Run-bound + snapshot-gated + model-bound (AD-014 / FW-RUN / TR-15 / CTRL-003), immutable append-only, symmetric tenant RLS, never hybrid. `run_type = ROLLING_RISK`; no new audit code (the run reuses `CALC.RUN_*`; the `PERF.*` block stays RESERVED-not-minted); no new permission (reuses `perf.run`/`perf.view`).

Grain is **four columns** — `(calculation_run_id, metric_type, window_months, period_start)` — because the same statistic is emitted at two windows and the sibling three-column grain collides. Suppression is a **first-class state**: nullable `metric_value` + a NOT NULL `suppressed` flag + a reason, under a total-enumeration DB CHECK. A stuffed zero is forbidden because **`0` is a legitimate value for all three metrics**, and a consumer would read "not computable" as "no drawdown, excellent".

**Consumer contract:** the disambiguation key is `(metric_type, window_months, annualization_basis)`. Rows are gross-of-fees, inherited from PM-1 (GIPS 4.C.44), and carry that basis rather than inferring it.

## Known limitations (recorded; mirror the `model_limitation` rows)

1. **Two-stage linking is not bit-identical to PM-1's.** The same `link_periods` implementation is used, so the *convention* is shared — but it quantizes to 12dp on return, so sub-periods → month → window aggregation is **not associative** with PM-1's one-stage link. A supervisor comparing RM-1's 12-month rolling return with PM-1's `TWR_LINKED` over the same span will find a 12th-decimal difference. A test pins the **non**-equality direction so nobody later "fixes" it with an equality assert.
2. **Rolling values are not independent.** Adjacent 12-month windows share 11 of 12 observations (≈92% overlap), so a change between consecutive windows reflects the single entering and exiting month, **not** a re-estimate. This is the most likely misreading of the surface.
3. **The month-end convention is holiday-free in v1.** A month-end landing on a market holiday is a recorded residual — no holiday substrate exists (the ENT-006 calendar tables carry no business-day logic). A holiday-aware convention is a recorded v2.
4. **Discretisation bias.** `sup(subset) ≤ sup(superset)`, so monthly MDD ≤ daily MDD ≤ continuous MDD, always. Every row carries its sampling frequency; never compare across frequencies.
5. **Captured-holdings book propagation.** PM-1 measures a book with no cash ledger, so uncaptured income understates the return series, and that understatement flows into every RM-1 statistic. Mitigation is operational (capture the cash), never mathematical imputation.
6. **No benchmark leg in v1**, so GIPS 2.A.18.a (same-grid, same-methodology comparison) does not bind here — it binds the v2 benchmark leg, where it is the more demanding constraint.
7. `validation_status` **UNVALIDATED** — recorded, non-enforcing until a 2L validator records an outcome (VW-1); a REJECTED latest outcome, or an EXPIRED use-before-validation exception (MG-1), refuses every new bind at the shared seam.

## External benchmarks (roadmap Part 4 rule 6 — sources checked 2026-07-26)

Grades: **[V]** verified against a fetched primary source · **[C]** independently computed · **[U]** unverified, carried as **our** convention and never as a citation.

| Source | Used for | Grade |
|---|---|---|
| GIPS for Firms 2020 (CFA Institute) — 2.A.12, 2.A.23.a/b, 2.A.24.f, 4.A.1.j, 4.C.36, 4.C.43.a, 4.C.44 | the monthly grid, the business-day allowance, geometric linking, ×√12, suppression disclosure, gross/net | **[V]** |
| GIPS *Guidance Statement on Calculation Methodology* (2010) | the sub-period definition ("between external cash flows") | **[V]** |
| Lo, "The Statistics of Sharpe Ratios", *FAJ* 58(4), 2002 — Eq. 16, Eq. 19, n. 7 | the demoted heteroskedasticity corroboration | **[V]** (journal paywalled; published text fetched) |
| Magdon-Ismail et al., "On the Maximum Drawdown of a Brownian Motion", *J. Appl. Prob.* 41(1), 2004 — Eq. 1 | the running-peak, no-look-ahead structure on a level path | **[V]** (paywalled; preprint fetched) |
| Chekhlov, Uryasev & Zabarankin, "Drawdown Measure in Portfolio Optimization", *IJTAF* 8(1), 2005 — Def. 3.1/3.2, Prop. 3.1/3.4 | the discrete drawdown form and the `w_0`/`ξ_0` base-point treatment | **[V]** (paywalled; author manuscript fetched) |
| 17 CFR §275.206(4)-1(d)(2) via Cornell LII | the 1/5/10-year anti-cherry-picking provision and its private-fund carve-out | **[V]** |
| ×√12 reproduced from CFA Institute's four published 3-year figures to 16 significant digits | the operator, arithmetic-mean centring, and that GIPS does not prescribe n vs n−1 | **[C]** |
| The ratio-to-peak normalisation `f = 1 − e^{−D}` | **ours** — the source is unit-agnostic; "log" does not appear in it | **[U]** |
| `k = 252 / 52 / 365` | **not carried.** RM-1's grid is monthly, so √12 is the only basis needed | **[U]** |

**Paywalled primaries are disclosed, not laundered.** No numeric constant is transcribed from any source; only functional forms are carried. CFA Institute's *Explanation of Provisions §4* workbook is cited **as corroboration only, never as a provision** — a spreadsheet cell is not reader-verifiable.

**Two scope limits the drafting over-claimed, corrected at the verifier pass.** Chekhlov Prop. 3.1's non-negativity is proved for the **absolute** drawdown on an **uncompounded** cumulative return, and the paper explicitly disclaims the relative form — which is what RM-1 emits, on a compounded base. Non-negativity and boundedness are therefore **RM-1's own asserted invariants**, provable only under A7. And Magdon-Ismail's log/√T/linear asymptotics describe the unbounded arithmetic drawdown `D̄`, not the bounded fraction-of-peak RM-1 emits; the "never annualize" conclusion survives on the stronger ground that a bounded, saturating statistic has no horizon-scaling law, which needs no citation.

## Reproducibility & governance

Reproducible from the snapshot alone (TR-09). The registered version identity is `code_version` **plus the declared window set** `{12, 36}` — the parameter domain is part of the identity precisely because it is where GIPS 2.A.12 is enforced. Whether an RM-1 read constitutes an "advertisement" under the SEC marketing rule (including its private-fund carve-out) is a **legal determination outside this document**, flagged to compliance.
