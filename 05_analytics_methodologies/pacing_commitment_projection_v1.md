# Commitment-Pacing Projection v1 (`pacing.commitment_projection`) — CC-2

The platform's **17th governed number and its FIRST private-capital derived output** — and the
first governed **projection**: a deterministic forward path of a private-fund commitment's future
capital calls, distributions, and NAV, discharging the REQ-PRV-001 "computed" leg CC-1 left open (a
persisted per-period unfunded number). Where every prior governed number measures a realized or
current state, this one projects a FUTURE under DECLARED assumptions — so its honesty discipline is
different in kind: it is a projection, NOT a forecast of realized cashflows, and the five declared
parameters propagate one-for-one into every projected value.

## Purpose & applicability

Forward liquidity and commitment-pacing planning for ONE `(portfolio, instrument)` private-fund
commitment over the CC-1 captured substrate. It answers "given what has been called and distributed
and the latest mark, how much more will be called, distributed, and held — year by year — to fund
maturity, under these declared pacing assumptions?" It gates no capital and prices no book; it is a
planning read whose consumers weigh the declared assumptions. The portfolio-level unfunded ROLLUP
across pairs (the REQ-PRV-001 "aggregated" clause) is the named v2 — this number is per-pair.

## The recursion, pinned

Let `L` = fund life (periods), `RC(t)` = the declared rate-of-contribution at fund age `t`, `B` =
bow, `G` = per-period NAV growth, `Y` = the distribution-rate floor. For each future fund age
`t = current_age+1 .. L` (the MID-LIFE re-anchoring seeds the recursion from realized actuals and
projects only forward):

    C(t)   = RC(t) · Unfunded(t−1)                         (the capital call)
    RD(t)  = max( Y, (t / L)^B )                           (the rate of distribution)
    D(t)   = RD(t) · NAV(t−1) · (1 + G)                    (the distribution)
    NAV(t) = NAV(t−1) · (1 + G) + C(t) − D(t)              (the NAV roll)
    Unfunded(t) = Unfunded(t−1) − C(t)

— the **Takahashi & Alexander (2002) deterministic commitment-pacing model** (JPM 28(2):90–100).
`RD(t)` is the bow-shaped fraction of NAV distributed each period: the `(t/L)^B` term grows the
distribution rate toward `1` as the fund matures, and `RD(L)=max(Y,1)=1` so the final age fully
distributes the grown NAV (unfunded exhausted, NAV rolls to its terminal distribution). NO
optimizer, NO randomness — a closed-form deterministic linear system.

## The anchor (mid-life re-anchoring — OUR documented adaptation)

The from-inception recursion (age 0: `Unfunded(0)=committed`, `NAV(0)=0`) is what the sources
attest. For an ALREADY-CALLED commitment we re-anchor from REALIZED actuals — a documented CC-2
extension, not source-attested — read entirely from the pinned snapshot:

- `PaidIn = Σ capital_call.amount` (reversals self-correct — the CC-1 negation Σ).
- `Unfunded(0) = committed − PaidIn + Σ(recallable distribution.amount)` — a recallable
  distribution restores unfunded (the CC-1 `is_recallable` flag interpreted HERE). Coherence gate:
  `Unfunded(0) ∈ [0, committed]` else **pre-create REFUSAL** (an incoherent book is never
  projected).
- `NAV(0)` = the latest pinned current-head `valuation` mark for the pair (max `valuation_date`),
  whose `currency_code` MUST equal the commitment's else **REFUSAL** (never a fabricated anchor). A
  funded book (`PaidIn ≠ 0`) with NO pinned mark **REFUSES**; a new/uncalled commitment anchors
  `NAV(0)=0` (the canonical TA new-commitment case).
- `current_age` = the complete ANNUAL periods (anniversaries) from the vintage to the snapshot's
  `as_of_valuation_date` — a DETERMINISTIC pin-derived age (a wall-clock age would break
  pin-reproducibility, TR-09). A commitment past fund life (`current_age ≥ L`) **REFUSES** (nothing
  to project).

## Declared identity

The **FIVE declared parameters ARE the version identity**: `rc_schedule` (a non-empty list of rates
in [0,1], `len ≤ L`), `fund_life` (positive int `L`), `bow` (signed `B`), `growth` (signed `G`),
`yield_floor` (`Y ∈ [0,1]`) — stored as `model_assumption` rows (canonicalized: rates to fixed 6dp,
signed decimals normalized, so `0.25` and `0.250` cannot mint distinct identities), parsed back
fail-closed by the binder (a generically-minted version can stamp anything → `WrongModelVersionError`).
Identity = (code_version, rc_schedule, fund_life, bow, growth, yield_floor, functional_form);
same-label different-declaration is a governed 409. Domains are validated at registration AND
re-checked at bind by a probe projection (defense-in-depth).

**NO numeric constant is minted from Takahashi-Alexander — only the FUNCTIONAL FORM is TA's**,
recorded as the `functional_form=TAKAHASHI_ALEXANDER` identity marker (a string, not a number). The
declared parameters are OUR PE-shaped choices, never TA's un-routed paper examples.

## Precision & determinism

All money is `Decimal`; the projection runs at `Decimal` precision with a **QUANTIZE-THEN-ROLL at
6dp HALF_UP** discipline — each period's `C`, `D`, `NAV`, `Unfunded` are quantized to 6dp before
they seed the next period (executed proof that quantize-then-roll is value-affecting vs.
round-at-the-end; the quantum is part of the number's identity). The one transcendental step is
`(t/L)^B` — **`Decimal ** Decimal`** power: Python's `Decimal.__pow__` with a non-integer Decimal
exponent is deterministic at a fixed context precision (it is a correctly-rounded contextual
operation, NOT a float `math.pow`), so the projection is bit-reproducible across platforms given the
pinned parameters. NO float touches the recursion. A projected value beyond the reproducible
magnitude envelope (`abs(v) > 1E21` — a declared growth/bow can compound NAV past any sane book) is
a **post-create FAILED** run (a committed FAILED run, zero rows, a naming reason). The envelope sits
strictly below the `PreciseDecimal(28,6)` column capacity (`< 1e22`) so an oversized value FAILs
rather than overflowing the column on insert; a separate kernel ceiling above the envelope stops
runaway geometric compounding before it can exceed the Decimal compute precision.

## Shape

ONE IA true-append-only result table `pacing_projection_result` (ENT-059; migration `0045`): the
run-bound NOT-NULL FK trio (`calculation_run_id`/`input_snapshot_id`/`model_version_id`) + hard-FK
provenance `portfolio_id`/`instrument_id`; grain `(calculation_run_id, period_index)` with
`period_index` = fund age (1..L); `period_start`/`period_end Date` (the ANNUAL anniversary window
from the vintage, Feb-29→Feb-28 clamped); four money `PreciseDecimal(28,6)` columns
(`projected_call`/`projected_distribution`/`projected_nav`/`unfunded_end`) + `currency_code`
echoing the commitment's chain-immutable currency. NO summary row (totals are Σ-derivable — one row
shape, no `metric_type` vocab in v1; a future variant re-opens it additively). Symmetric FORCE RLS
(NEVER hybrid); the `irp_prevent_mutation` P0001 trigger + the ORM guard.

The binder `run_pacing_projection` is **consume-only** (`build_pacing_snapshot` builds the
`PACING_INPUT` snapshot separately — the commitment head + ALL call/distribution events + the latest
mark) and runs through the shared `execute_governed_run` scaffold. The NEW `pacing.run`/`pacing.view`
R-07 mint (a governed-output `.view`, so it INCLUDES `auditor_3l` — the DECISIVE contrast with CC-1's
captured-input `commitment.view` that excluded the auditor); `run_type='PACING_PROJECTION'`;
`CALC.RUN_*`-audited (`PACING.PROJECTION_CREATE`/EVT-250 RESERVED, NOT minted — the PERF/EVT-230
governed-number precedent). `audit/service.py` FROZEN; `private_capital/` and `valuation/`
byte-untouched (read only through the pin).

## Reads — rule 7 in-slice, and the platform's FIRST latest-resolver

Every governed number ships entity/time-centric reads in-slice (roadmap Part-4 rule 7). This slice
delivers ALL THREE legs: the run-centric reads (by run/row id); the entity-filtered
`list_pacing_projections(portfolio, instrument, as_of)` — flat rows each carrying
`calculation_run_id` + `model_version_id`, total ordering (run `system_from` DESC, run_id DESC,
`period_index` ASC), silent-empty on an unknown id; and the platform's **FIRST latest-resolver**
`latest_pacing_projection` — the newest COMPLETED projection run for the pair across ALL model
versions ("current" = the latest run), `as_of`-aware (`as_of=None` = now; ONE code path via
`list_pacing_projections`). **Cross-run aggregation is a CONSUMER ERROR**: a pair may hold several
runs (e.g. successive version labels); a consumer discriminates by `calculation_run_id` and reads one
run's rows, never sums across runs.

## External benchmark (roadmap Part 4 rule 6 — sources checked 2026-07-20)

- **Takahashi & Alexander 2002** ("Illiquid Alternative Asset Fund Modeling", J. Portfolio
  Management 28(2):90–100) — **verified-via-reproduction at per-source grades; the primary is GATED**
  (JPM paywall; PMR form-gate), disclosed rather than laundered:
  - the **call/distribution/NAV recursion verified via two independent equation-level
    reproductions** — Jaeckel's practitioner note and the Tamarix Advisors white paper both quote
    the four update equations in the `RD(t)=max(Y,(t/L)^B)` bow form with `C(t)=RC(t)·Unfunded(t−1)`
    and the `NAV(t)=NAV(t−1)(1+G)+C(t)−D(t)` roll — independently cross-checked against the
    boundary identity `RD(L)=1` (the final age fully distributes).
  - **structural corroboration** — [Luxenberg, Boyd et al., "Portfolio Construction with Private
    Assets" (arXiv)](https://arxiv.org/abs/2503.01218) frames the TA yield/rate-of-contribution
    model structurally (single deterministic path, the bow-shaped distribution rate) without
    re-deriving the equations.
  - **input-list corroboration** — an FRG (Financial Risk Group) practitioner note enumerates the
    five model inputs (rate of contribution, fund life, bow, growth, yield) verbatim, confirming
    the DECLARED-parameter set this family registers.
  - **No numeric constant is transcribed from any of these** — only the functional form is carried;
    the parameters are declared per-version, so the three-route constant bar does not apply (there
    is no constant to register).
- **Mid-life re-anchoring** — NOT source-attested; OUR documented CC-2 adaptation (the R1/R2
  reproductions verify the from-inception recursion; the re-anchoring seeds `Unfunded(0)`/`NAV(0)`
  from realized actuals and is disclosed as an extension).

## Known limitations (first-class; mirrored into `model_limitation` rows)

- **Single deterministic path** — no scenarios, no randomness; a mis-declared growth/bow biases the
  whole series. The stochastic Jeet (SSRN 4819761) enhancement is the recorded v2. A projection under
  declared assumptions, NOT a forecast of realized cashflows.
- **Mid-life re-anchoring is OUR adaptation** — the from-inception recursion is source-attested; the
  realized-actuals re-anchoring is a documented CC-2 extension.
- **ANNUAL periodicity in v1** — quarterly is the recorded v2; all captured call types
  (DRAWDOWN/EQUALIZATION/FEE) consume unfunded (the fees-inside-commitment convention); a recallable
  distribution restores unfunded up to the anchor-coherence bound.
- **NAV anchor** — `NAV(0)` = the latest same-currency pinned mark (else REFUSED pre-create). Mark
  STALENESS is v1-DISCLOSED, not gated (the HG-1-style opt-in age gate is the v2).
- **Per-(portfolio, instrument) pair** — the portfolio-level unfunded ROLLUP (the REQ-PRV-001
  "aggregated" clause) is the named v2; `RD(L)=1` so the final age fully distributes.
- **validation_status UNVALIDATED** — the standing VW-1/MG-1 enforcement posture (a REJECTED latest
  outcome or an EXPIRED use-before-validation exception refuses every new bind at the shared seam).

## Reproducibility & governance

The row reproduces from its pinned snapshot content + declared parameters alone (no registered
constant participates); TR-09 re-run invariance holds through the pinned content and the pin-derived
age (a later supersede/correct/new-event/mark cannot move a historical run). The `0045` downgrade
DROPS `pacing_projection_result` (the recorded honestly-destructive-downgrade precedent), with the
append-only trigger and FORCE RLS transactionally handled around the table drop; demo stage 9
exercises the full projection LIVE on the living tenant (the counts move 19/34/95 → 20/35/96 — the
deliberate contrast with stage 8's capture-only pins is the demo's own story: capture mints nothing,
a governed projection is a real number).
