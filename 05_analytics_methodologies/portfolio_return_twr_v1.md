# Methodology — Portfolio Return (time-weighted, Modified-Dietz, gross, 1-period) v1

> **Model:** `perf.return.twr` · **Version:** `v1` · **Referent:** `model_version.methodology_ref` points here.
> **Status:** REGISTERED; `validation_status = UNVALIDATED` (recorded, **non-enforcing until P7**). This doc IS the methodology referent the governed `model_version` binds (PM-1, ENT-053, OD-PM-1-B/D).

## Purpose & applicability
The platform's **seventh** governed number and its **first non-risk** one: a governed **portfolio
return series** — how much the portfolio actually earned over a set of valuation boundaries, with
external cash flows correctly neutralised. This is the **time-weighted return (TWR)**, the measure
that isolates the manager's result from the timing/size of client contributions and withdrawals
(GIPS 2020). It is the prerequisite for ex-post benchmark-relative analytics (realized tracking
error / active return / information ratio — P3-8), VaR backtesting, and the private-asset return
machinery. ENT-053 `portfolio_return_result` is realized as the per-sub-period + linked series.

## Inputs & data policy
An ORDERED list of **N ≥ 2 COMPLETED `exposure_aggregate` runs** of a **SINGLE portfolio** (v1
scope — see Known limitations) and the SAME base currency; their input-snapshot `as_of_valuation_date`s
are the sub-period boundaries. Plus the `transaction` rows whose `trade_date` falls in each half-open
sub-period window `(start, end]`. All pinned into a `RETURN_INPUT` snapshot (`COMPONENT_KIND_EXPOSURE`
atoms + the new `COMPONENT_KIND_TRANSACTION` + `COMPONENT_KIND_FX` legs for non-base flow currencies);
the compute reads ONLY the pinned content (AD-014) — a later upstream re-run OR a transaction append
cannot move a historical return (test-proven, TR-09). NO live valuation/transaction read. The
boundary VALUATION DATES are the one input NOT in the pins: they are read from each boundary run's
**IMMUTABLE** `EXPOSURE_INPUT` snapshot header **pre-create** (drift-free by construction — a
`dataset_snapshot` is IA append-only and never mutated; the `run_active_risk` run-re-resolution
pattern), so the series still reproduces exactly.

## Formulas & numerical standards
```
BMV_i = Σ (pinned exposure_amount of the atoms of boundary run i-1)      (base currency)
EMV_i = Σ (pinned exposure_amount of the atoms of boundary run i)
F_ij  = signed external flow (TRANSFER_IN +, TRANSFER_OUT -), base ccy   (via pinned FX @ trade_date)
w_ij  = (CD_i - D_ij) / CD_i     D_ij = calendar days from start_i to the flow (end-of-day timing)
r_i   = (EMV_i - BMV_i - Σ_j F_ij) / (BMV_i + Σ_j w_ij·F_ij)             (Modified Dietz)
R     = Π_i (1 + r_i) - 1                                                (geometric linking)
```
- **No-flow reduction:** with no in-window flows, `r_i = EMV_i/BMV_i - 1` EXACTLY (a true TWR
  sub-period). **Valuation-at-flow is the caller's lever** — supply a boundary at the flow date and
  Dietz never approximates that flow (the GIPS hierarchy).
- **Precision:** `Decimal` at 50-digit context; `return_value` `quantize_HALF_UP` to **12** decimal
  places (the `Numeric(20,12)` return-fraction scale — a return, NOT a currency amount). Gross of
  fees, **UNANNUALIZED**, in the exposure runs' base currency.
- **Pathology gates (Bacon):** `BMV_i ≤ 0` or the average-capital denominator `≤ 0` → a return over
  zero/negative capital is undefined → **pre-create REFUSAL**, never a signed-garbage number.

## Assumptions
1. **TWR with Modified-Dietz within** caller-supplied boundaries; end-of-day flow timing;
   calendar-day weights; geometric linking — all DECLARED (version identity; not request params).
2. **MV = Σ pinned exposure atoms** of one COMPLETED exposure run per boundary (the established
   platform market-value convention — P3-7's `portfolio_value`).
3. **External-flow set = {TRANSFER_IN, TRANSFER_OUT} ONLY**, as model identity — every other
   `txn_type` is internal; extending the set = a new version label, never a silent re-read.
4. **Snapshot-only compute** (AD-014): invariant under upstream re-runs and transaction appends.
5. **Fail-closed inputs:** <2 runs, mixed scope/base, DUPLICATE boundary dates (the binder ORDERS
   boundaries by valuation date — caller order is irrelevant; only equal dates refuse), a NULL/blank
   flow amount or currency, a missing FX leg, or a Dietz pathology → refused pre-create (no imputation).

## Validation / reproduction tests
- **Hand golden:** BMV 1,000,000 → EMV 1,050,000 with a +20,000 contribution at the sub-period
  midpoint (weight 0.5) → `r = 30,000 / 1,010,000 = 0.029702970297`; a no-flow sub-period of
  1,000,000 → 1,030,000 → exactly `0.030000000000`; a three-period geometric link
  `(1.03)(0.98)(1.01) − 1 = 0.019494000000`.
- **Independent cross-check:** a spreadsheet/float recomputation of the linked series from the
  pinned content agrees within ε (TEST-only).
- **Reproduction:** an identical re-run reproduces the series exactly; a pinned snapshot is
  invariant under a later exposure re-run AND a transaction appended after the snapshot (TR-09).
- **Reachable refusals — pre-create (zero run/rows):** a NULL/blank flow currency or amount, a
  missing FX leg for a flow, fewer than two boundaries, DUPLICATE boundary dates (order-agnostic), a
  multi-portfolio book, a non-positive begin MV, and a non-positive Modified-Dietz denominator all
  refuse BEFORE `create_run` (NO imputation, ever).
- **Reachable refusal — post-create FAILED (committed run, zero rows):** a column-legal-but-extreme
  pin whose per-sub-period OR linked return exceeds the `Numeric(20,12)` column envelope
  (`|value| < 1E8`; gated explicitly by `abs(return) >= _MAX_RESULT_ABS` and the aggregate net-flow
  by `_MAX_EVIDENCE_ABS`, since the kernel's 12dp-quantize guard bounds only the SCALE and trips
  ~1E38 — far above the column) is a committed FAILED run + `DATA.VALIDATE` DQ evidence + a
  magnitude-naming `failure_reason` — never a PG-overflow 500. REACHABLE via a hand-minted snapshot,
  e.g. BMV 1 → EMV 1E10 ⇒ return ~1E10.

## Governed-number contract
RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND; IA TRUE append-only `portfolio_return_result` (one
`DIETZ_PERIOD` row per sub-period + one `TWR_LINKED` summary row; grain `(calculation_run_id,
metric_type, period_start)`); the N-run provenance lives in the snapshot pins (`begin_mv`/`end_mv`/
`net_external_flow` carried as evidence); symmetric tenant RLS (NEVER hybrid); reproducible under
input correction; `CALC.RUN_*` audit (no `PERF.*` code minted — `PERF.RETURN_CREATE` reserved).
**Entitlement is the NEW `perf.run`/`perf.view` pair** (a performance number is not a risk number —
the governed R-07 mint; `auditor_3l` included in `perf.view`); `run_type = 'PORTFOLIO_RETURN'`
(the family, ≠ the metric).

## Known limitations (recorded; mirror the `model_limitation` rows)
1. **CAPTURED-HOLDINGS BOOK — no cash ledger.** Dividend/interest cash not subsequently captured as
   a position (or transferred out) is INVISIBLE to market value; total return is UNDERSTATED by
   uncaptured income. First-class limitation; mitigation is operational (capture the cash), NOT
   imputation. Named again wherever actives (P3-8) consume this series.
2. **Money-weighted / IRR DEFERRED** to the private-asset foundations slice (PA-0) — the GIPS
   measure for committed-capital vehicles; it belongs with commitments/calls/distributions capture.
3. **Gross-of-fees only** — no fee capture exists; net-of-fees is a deferred version.
4. **No large-flow revaluation threshold** (every boundary is caller-supplied); **no composites**
   (firm-level GIPS construct); **no annualization**; **no sub-portfolio/instrument attribution**.
5. **SINGLE-portfolio book (v1).** All pinned atoms must resolve to ONE `portfolio_id`; a
   multi-portfolio / subtree book is REFUSED pre-create. Rationale is not only convenience: an
   intra-subtree transfer between two child portfolios of the measured book is INTERNAL (not an
   external flow), and that classification is its own deferred slice — refusing the case is the
   honest v1 boundary, never a silent mis-measurement.
6. `validation_status = UNVALIDATED` — recorded, non-enforcing until the P7 validation workflow.
