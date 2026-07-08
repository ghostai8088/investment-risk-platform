# Methodology — Historical-Simulation Portfolio VaR (plain equal-weight, 1-day) v1

> **Model:** `risk.var.historical` · **Version:** `v1` · **Referent:** `model_version.methodology_ref` points here.
> **Status:** REGISTERED; `validation_status = UNVALIDATED` (recorded, **non-enforcing until P7**). This doc IS the methodology referent the governed `model_version` binds (VAR-HS-1, ENT-027, OD-VHS-A/B/D/E).

## Purpose & applicability
The platform's fifth governed **risk** number and its second VaR method: plain equal-weight
**factor-based historical simulation** under the same linear factor model as the parametric
method — for each date `t` in the pinned window, the scenario P&L is `ΔV_t = Σᵢ xᵢ·r_{t,i}`
(the exposure vector `x` from ONE COMPLETED factor-exposure run; `r_t` from pinned captured
factor-return windows), and `VaR_c = −(k-th smallest ΔV_t)` with `k = ⌈N·(1−c)⌉`. **No
distributional assumption** — the empirical scenario distribution speaks for itself (the
method's point versus delta-normal). Results land on the SAME `var_result` grain with
`metric_type='VAR_HISTORICAL'`; `z_score`/`sigma`/`covariance_run_id` are honestly NULL
(migration `0028` — this method produces no normal quantile, no volatility estimate, and
consumes no covariance run).

**NOT applicable to** (deferred — see Known limitations): filtered (FHS) and time-weighted
(BRW) variants; Expected Shortfall; Monte-Carlo; multi-horizon/overlapping windows;
component/marginal VaR; backtesting.

## Inputs & data policy
- **Inputs:** the `factor_exposure_result` rows of one COMPLETED FACTOR_EXPOSURE run
  (`COMPONENT_KIND_FACTOR_EXPOSURE` IA-row pins) + one aligned per-factor RETURN WINDOW
  (`COMPONENT_KIND_FACTOR_RETURN` bitemporal per-date pins — the P3-4 flavor), pinned into a
  `VAR_HS_INPUT` `dataset_snapshot`. The compute reads **only** the pinned content — never a
  live read — so later vendor supersedes or upstream re-runs cannot move a historical number
  (TR-09/AD-014).
- **Data policy:** confidence, horizon, window length, and the quantile convention are
  **declared at model registration** and are version identity (OD-VHS-B); never request
  parameters. Windows must be SIMPLE/DAILY, mutually aligned (identical date sets), duplicate-
  free, and EXACTLY the declared length; every exposure factor must have a pinned window —
  **no imputation, ever** (OD-P3-0-L). The declared window must satisfy the adequacy floor
  `N ≥ ⌈1/(1−c)⌉` (OD-VHS-E; at 99%, N ≥ 100).

## Method
1. Scenario P&Ls: `ΔV_t = Σᵢ xᵢ·r_{t,i}` per pinned window date, computed in `Decimal` at
   50-digit context precision (per-factor totals aggregated from the pinned exposure rows).
2. Order statistic: `k = ⌈N·(1−c)⌉` in exact integer/Decimal arithmetic (no float).
3. `var_value = −(k-th smallest ΔV_t)`, `quantize_HALF_UP` to 6dp (the `Numeric(28,6)` currency
   scale — parametric parity). The value MAY be negative (every k-th-tail scenario was a gain);
   it is reported honestly, never clamped.
4. The **quantile convention** (`LOWER_ORDER_STATISTIC`, declared) is the conservative discrete
   reading behind the Basel-era "3rd worst of 250 at 99%" rule; interpolated estimators
   (Hyndman–Fan variants) are RECORDED v2 declarations, never silent drift.

## External benchmark (roadmap Part 4 rule 6 — sources checked 2026-07-08)
Plain historical simulation is the industry workhorse but reacts slowly to volatility shifts;
filtered historical simulation (Barone-Adesi et al., 1999) and BRW time-weighting
(Boudoukh–Richardson–Whitelaw, 1998) consistently outperform it —
[Bank of England WP 525](https://www.bankofengland.co.uk/-/media/boe/files/working-paper/2015/filtered-historical-simulation-value-at-risk-models-and-their-competitors.pdf),
[Pritsker 2006](https://www.sciencedirect.com/science/article/abs/pii/S037842660500083X),
[arXiv 2505.05646](https://arxiv.org/pdf/2505.05646). v1 ships the plain method DELIBERATELY as
the deterministic, assumption-free, auditable baseline; FHS/BRW are v2 model versions requiring
a DECLARED volatility model. Regulatory direction (Basel FRTB) prefers 97.5% Expected Shortfall
on stressed windows with ~253 scenarios —
[BIS d457 note](https://www.bis.org/bcbs/publ/d457_note.pdf),
[BIS d305](https://www.bis.org/bcbs/publ/d305.pdf) — VaR remains the backtesting measure; this
platform makes NO capital-model claim, and ES is a recorded seam for this family.

## Known limitations (first-class; mirrored into `model_limitation` rows)
- **Specific/idiosyncratic risk = 0** — `x` spans registered factors only (identical to the
  parametric method; the allocation-v1 limitation propagates).
- **Slow volatility reaction** — equal weights; the cited literature prefers FHS/BRW (v2s).
- **Window-bounded tails** — the estimate cannot exceed the worst scenario IN the window;
  regimes outside the pinned window are invisible. The adequacy floor is a statistical minimum,
  not a sufficiency guarantee (the regulatory convention of ≥ 1 year ≈ 250–253 observations is
  recorded as guidance).
- **1-day horizon only**; ES/√h/component-VaR/backtesting are recorded seams.
- `validation_status = UNVALIDATED` until the P7 validation workflow.

## Reproducibility & governance
Snapshot-only compute (`VAR_HS_INPUT`); run-bound + REGISTERED-model-bound (CTRL-003); IA TRUE
append-only results; per-row ORIGIN + snapshot DEPENDS_ON lineage; pre-create refusal vs
post-create FAILED (the P3-5 failure model, incl. the result-magnitude gate); `risk.*`
permissions REUSED; `RISK.VAR_CREATE` reserved-not-emitted; `audit/service.py` FROZEN.
