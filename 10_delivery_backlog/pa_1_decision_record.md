# PA-1 Decision Record — private-asset desmoothing (Wave-3 slice 2, the thesis payload)

> **Status: RATIFIED 2026-07-12** — OQ-PA-1-1…7 approved as recommended (user: "Approved").
> Drafted against `main` `82f5f1d` (Wave-2 closed; RD-1 merged PR #17). Scope: the **ELEVENTH governed number** and the differentiation-thesis
> payload (`01_product_strategy/differentiation_thesis.md` §2.1) — **Geltner AR(1) unsmoothing of a
> captured private-asset appraisal mark series** (the model family RATIFIED at OD-PA-0-G /
> OQ-PA-0-7), producing a governed desmoothed return series with the introduced uncertainty stated
> honestly. Realizes a NET-NEW canonical entity (**ENT-056 `desmoothed_return_result`**, subject to
> OQ-2). Implementation follows ratification under the delivery-autonomy grant (Claude self-drives;
> the USER merges PRs); the OQs below are the Tier-3 gate.

## Part 1 — Decisions at a glance (OD-PA-1-A…K)

| # | Decision | Choice (recommended) |
|---|---|---|
| OD-PA-1-A | **v1 input (the headline shape).** | **The instrument-level appraisal mark series**: the current-head `valuation` rows of ONE `(portfolio, instrument)` pair over a caller-declared date window (the PA-0 convention — a private asset's appraised NAV/unit mark IS a `valuation` row). The binder computes the OBSERVED simple return series in-run from consecutive pinned marks (`r_a,t = mark_t/mark_{t−1} − 1`) and desmooths THAT. **NOT a PM-1 portfolio-return run**: the appraisal-smoothing literature operates on the asset's own appraisal series; routing through portfolio TWR would blend flows/other holdings into the very series whose autocorrelation carries the smoothing signal. |
| OD-PA-1-B | ENT-056 realization shape | `desmoothed_return_result` — **IA TRUE append-only** (`APPEND_ONLY_TABLES` + P0001 trigger + ORM guard); symmetric tenant-scoped FORCE RLS (NEVER hybrid). **A MULTI-ROW series** (the ENT-053 precedent): `n−1` per-period **`DESMOOTHED_RETURN`** rows (one per consecutive mark pair, the FIRST pair yielding an observed return only — see OD-D) + ONE **`DESMOOTHING_SUMMARY`** row. Grain `(calculation_run_id, metric_type, period_start)`. Per-period rows ECHO their consumed inputs (`observed_return`, `begin_mark`, `end_mark`, the declared `alpha` — the P3-6/P3-8 echo lesson): the arithmetic is auditable row-by-row. `metric_value` `Numeric(20,12)` FRACTION; marks echoed at `Numeric(28,6)`. Hard-FK PROVENANCE: `portfolio_id`, `instrument_id` (the measured subject — the ENT-053 `portfolio_id` precedent). |
| OD-PA-1-C | **The honest-uncertainty statement (thesis §2.1's "stated honestly").** | The `DESMOOTHING_SUMMARY` row carries `metric_value` = the **desmoothed sample stdev** (n−1) of the per-period desmoothed returns, with `observed_stdev` as an evidence column + `n_periods` — the headline "risk was understated by THIS much" number, computed not implied (the volatility ratio is derivable, not stored). Plus declared `model_assumption`s naming what the transform introduces: the AR(1) single-lag structure is ASSUMED, α is DECLARED (not estimated in-run), and the desmoothed series is a MODEL OUTPUT whose error compounds the α mis-specification — mirrored as first-class `model_limitation`s. |
| OD-PA-1-D | Kernel + math conventions | Geltner inversion per period: `r_t = (r_a,t − (1−α)·r_a,t−1) / α`, `quantize_HALF_UP(…, 12)` per row (`Numeric(20,12)`). The FIRST observed return (t=1) has no prior — it seeds the recursion and gets NO desmoothed row (no imputation; the standard treatment). Observed returns from marks: `r_a,t = mark_t/mark_{t−1} − 1` at 12dp. Sample stdev via the P3-5 Decimal-sqrt convention (Decimal-50 intermediate, `Decimal.sqrt`, quantize 12dp). A PURE kernel module (`desmoothing_kernel.py`, the `var_backtest_kernel` precedent) with property tests: `α=1` ⇒ identity (desmoothed == observed, boundary-labeled); desmoothed stdev ≥ observed stdev for a positively-autocorrelated series. |
| OD-PA-1-E | Model identity (declared-parameter) | Registered **`perf.return.desmoothed_geltner` v1** with **declared `alpha` as a strict-parsed `model_assumption`** (the OD-P3-5-D/BT-1 declared-parameter precedent): identity = `(code_version, alpha)`; a same-label re-register with a different α is a governed 409. Domain-gated at registration AND parsed back by the binder: `0 < α ≤ 1` (α=1 = the no-smoothing boundary; α≤0 or α>1 refuses 422). α is **estimated OFFLINE** (from the observed series' first-order autocorrelation — recorded procedure, NOT a runtime regression; the VAR-z/Kupiec-critical declared-not-computed precedent). Race-safe `resolve_or_register_*` registration. |
| OD-PA-1-F | Permission + run family + audit | **REUSE `perf.run`/`perf.view` — NO mint** (a desmoothed return series is a return-series number; the P3-8 reuse precedent). NEW run family **`DESMOOTHED_RETURN`** (≠ every metric_type). `CALC.RUN_*` audit reused; **`PERF.DESMOOTHED_RETURN_CREATE` RESERVED-not-emitted at EVT-230** (the standing pattern). `audit/service.py` stays FROZEN. |
| OD-PA-1-G | Snapshot + reproducibility | NEW purpose **`DESMOOTHING_INPUT`** pinning the window's current-head `valuation` FR rows (**REUSED `COMPONENT_KIND_VALUATION`** — the exposure-snapshot flavor; no new kind). AD-014 pinned-content-only reads; TR-09 BOTH sides tested (a post-run valuation correction cannot move the historical result; a re-run against the same snapshot reproduces byte-identically). Build-in-request (`portfolio_id` + `instrument_id` + `window_start/end`) XOR consume-existing (`snapshot_id`) — the P3-C1 gate. An empty pinned mark set refuses BEFORE any write. |
| OD-PA-1-H | Series-quality gates (fail-closed; NO imputation) | Pre-create refusals: **fewer than 4 pinned marks** (< 3 observed returns ⇒ < 2 desmoothed returns ⇒ no meaningful summary stdev); a **non-positive mark** (a simple return is undefined); **duplicate `valuation_date`**; a **mixed-currency** mark series (no FX translation in v1 — the series must be single-currency, echoed as `mark_currency`); mixed portfolio/instrument. **Irregular calendar spacing is ACCEPTED but recorded**: the AR(1) step is per-OBSERVATION, and appraisal cadence (quarterly by convention) is not schema-enforced — a calendar-regularity gate is a recorded v2, and the spacing caveat is a first-class `model_limitation`. Post-create FAILED: any persisted `Numeric(20,12)` value with magnitude ≥ 1E8 (the PM-1 envelope gate) — a committed FAILED run + DQ evidence + ZERO rows. |
| OD-PA-1-I | **Money-weighted IRR / capital calls: NOT in PA-1 (a recorded deviation from OD-PA-0-F).** | OD-PA-0-F redirected PM-1's money-weighted/IRR deferral "to PA-1". Folding IRR in would DOUBLE the methodology surface (root-finding + cash-flow conventions — its own numerical-standards work) and dilute the thesis payload; the ratified Wave-3 table scopes PA-1 to desmoothing. The deferral is hereby RE-RECORDED (not silently dropped) as its own trigger-based register item: **a cash-flow/IRR slice (provisionally PA-3)** when commitment/capital-call tracking is demanded. Subject to OQ-5. |
| OD-PA-1-J | Rule-6 research + **the Okunev-White RESOLUTION** | Geltner (1991) *JREFE* 4(3) 327–345 + Geltner (1993) *JRER* 8(3) 325–345 (the v1 filter, HIGH confidence, unchanged). Getmansky-Lo-Makarov (2004) *JFE* 74(3) 529–609 (MA(q) generalization — v2). **Okunev-White VERIFIED (2026-07-12), and the PA-0 tentative substance was WRONG:** the actual method is an **ITERATIVE HIGHER-ORDER EXTENSION of the Geltner filter** (repeated application removing autocorrelation of any order m), NOT a Kalman-filter/switching-regression dynamic-beta approach. Citation: **Okunev, J. & White, D. (Oct 2003), "Hedge Fund Risk Factors and Value at Risk of Credit Trading Strategies", SSRN working paper 460641** (published as Loudon, Okunev & White, *Journal of Fixed Income* 16(2), 2006, 46–61). The v2 register is corrected accordingly (Part 2); the OD-PA-0-I honesty flag is DISCHARGED. |
| OD-PA-1-K | Review + flow | **FULL 4-finder governed-number battery** (it IS the eleventh governed number — the OD-P3-6-J precedent): kernel/math correctness; governance/temporal/RLS/snapshot; API/entitlement/cross-file/FE; cleanup/conventions/sweep. Fixtures TD-1-realistic (a plausible quarterly PE NAV series; extreme values boundary-labeled); the full-stack golden ships its hand derivation; MD-H1 design-completeness checklist at design time (empty/short series refused; both TR-09 sides; α domain enforced in the binder, not doc-stated; no RUNNING orphan on any refusal). Claude self-drives to a pushed branch; the USER merges. |

## Part 2 — External benchmark research (roadmap Part 4 rule 6; sources checked 2026-07-12)

- **Geltner, D. (1991)**, "Smoothing in Appraisal-Based Returns", *J. Real Estate Finance and
  Economics* 4(3), 327–345; **Geltner, D. (1993)**, "Estimating Market Values from Appraised Values
  without Assuming an Efficient Market", *J. Real Estate Research* 8(3), 325–345. The v1 model:
  observed appraisal returns blend the true current return and the prior observed return
  (`r_a,t = α·r_t + (1−α)·r_a,t−1`); inversion recovers the desmoothed series. α ("speed of
  adjustment", the fraction of new information incorporated per period) is conventionally estimated
  from the observed series' first-order autocorrelation (`α ≈ 1 − ρ₁`) — PA-1 declares it offline
  (OD-E) rather than estimating in-run.
- **Getmansky, M., Lo, A. W., & Makarov, I. (2004)**, "An econometric model of serial correlation
  and illiquidity in hedge fund returns", *J. Financial Economics* 74(3), 529–609. The k-lag MA
  smoothing profile (`Σθ_j = 1`) generalization — the recorded v2 once a single lag proves
  insufficient (testable: residual autocorrelation in the v1 desmoothed series).
- **Okunev, J. & White, D. (2003)**, "Hedge Fund Risk Factors and Value at Risk of Credit Trading
  Strategies", SSRN 460641 (Oct 2003); published as **Loudon, Okunev & White (2006)**, *J. Fixed
  Income* 16(2), 46–61. **VERIFIED 2026-07-12** — an iterative procedure extending Geltner's filter
  to remove autocorrelation of ANY order (apply the first-order filter, then re-filter the m-th
  order residual autocorrelations progressively). The literature notes it nullifies first-order
  autocorrelation more completely than one Geltner pass. **Recorded v2 alongside GLM** (they attack
  the same residual-autocorrelation gap from different constructions). The PA-0 tentative
  description ("dynamic/time-varying-exposure, Kalman-style") was INCORRECT and is superseded by
  this entry — the OD-PA-0-I flag worked as designed: the unverified claim was quarantined, never
  ratified into a methodology doc.
- **Supervisory context:** appraisal-smoothing understates volatility and correlation with public
  markets (the thesis §2.1 problem); desmoothing before risk measurement is standard in
  institutional private-market risk practice (e.g. NCREIF-based real-estate risk work descends from
  Geltner/Fisher; "volatility laundering" is the current practitioner label for reporting smoothed
  vols). The honest-uncertainty framing (OD-C) is the differentiator: the transform's own
  assumptions are declared, not hidden.

## Part 3 — Limitations carried forward + out of scope (recorded)

1. **Single-lag AR(1) only** — residual higher-order autocorrelation survives one Geltner pass;
   GLM MA(q) + Okunev-White iterative are the recorded v2s (OD-J).
2. **α is DECLARED, not estimated in-run** — an offline mis-estimated α propagates directly into
   the desmoothed series (first-class limitation; the estimation procedure is recorded in the
   methodology doc).
   > **PARTIALLY DISCHARGED (dated note, additive — ratified history is not rewritten). DS-2
   > (2026-07-19):** items 1 and 2's v2 register is partially REALIZED as declared estimator
   > conventions on this family — **`AR1_ESTIMATED`** (α̂ = 1 − ρ̂₁ in-run + a persisted Bartlett
   > band; the conservative-band direction and the small-sample upward bias of α̂ registered as
   > first-class limitations) and **`OKUNEV_WHITE_ITERATIVE`** (the deterministic higher-order
   > filter; the per-pass formula settled by derivation + executed proof — the SSRN primary
   > remains gated). Referent: `05_analytics_methodologies/desmoothing_estimated_v1.md`;
   > migration `0042`. **Still open:** the GLM MA(q) profile — extraction-verified to equation
   > numbers at DS-2 planning but its MLE requires constrained numerical optimization, a
   > determinism obstacle this runtime has not admitted (the named v2's own prerequisite).
3. **Irregular appraisal spacing accepted** (OD-H) — the AR(1) step is per-observation; a
   calendar-regularity gate is v2.
4. **No FX translation** — single-currency mark series only.
5. **Money-weighted IRR / capital calls / commitments — NOT here** (OD-I; re-recorded as the PA-3
   trigger-based item).
6. **The desmoothed series is not yet CONSUMED downstream** — wiring it into the proxy-risk chain
   is PA-2's scope (the Wave-3 table); PA-1 mints the number.
7. `validation_status` UNVALIDATED (non-enforcing until P7).

## Part 4 — Open decisions (OQ-PA-1-1…7) — pending ratification

- **OQ-1** — v1 input = the instrument-level appraisal mark series (pinned `valuation` rows of one
  (portfolio, instrument) over a declared window); observed returns computed in-run; NOT a PM-1 run.
  *(Recommended: yes — OD-A.)*
- **OQ-2** — **MINT ENT-056 `desmoothed_return_result`** (IA; per-period rows + ONE summary row;
  grain `(run, metric_type, period_start)`; echoes per OD-B/C). *(Recommended: yes — the Part-3 mint
  process; the next free canonical id after ENT-055.)*
- **OQ-3** — Model identity `perf.return.desmoothed_geltner` v1 with declared `alpha ∈ (0, 1]`
  (strict-parsed assumption; offline estimation; the executable shape of the already-ratified
  OQ-PA-0-7). *(Recommended: yes — OD-E.)*
- **OQ-4** — REUSE `perf.run`/`perf.view`; run family `DESMOOTHED_RETURN`;
  `PERF.DESMOOTHED_RETURN_CREATE` reserved-not-emitted. *(Recommended: yes — OD-F.)*
- **OQ-5** — IRR/capital-calls stay OUT of PA-1 (a recorded deviation from OD-PA-0-F's redirect;
  re-recorded as the trigger-based PA-3 item). *(Recommended: yes — OD-I; the alternative doubles
  the slice's methodology surface against the ratified Wave-3 scope.)*
- **OQ-6** — Accept the Okunev-White RESOLUTION (verified citation; the corrected iterative-
  higher-order substance; v2 register updated; the OD-PA-0-I flag discharged). *(Recommended: yes —
  OD-J.)*
- **OQ-7** — Series-quality gates as OD-H (min 4 marks; positive marks; unique dates; uniform
  currency; irregular spacing accepted-and-recorded; magnitude gate 1E8). *(Recommended: yes.)*

**[CORRECTION, 2026-07-12 — implementation-time amendment to OD-PA-1-B (the OD-PA-0-I
resolution-note precedent):** OD-B as ratified named the per-period ``metric_type``
"DESMOOTHED_RETURN" and "``n−1`` per-period rows". As written, that metric name EQUALS the OD-F
run-family name — violating OD-F's own "≠ every metric_type" (GS2) requirement — and the row count
is arithmetically ``n−2`` (``n`` marks → ``n−1`` observed returns → the first seeds the recursion).
The implementation ships ``metric_type = "DESMOOTHED_PERIOD"`` (the ``DIETZ_PERIOD`` naming
precedent) and ``n−2`` per-period rows, honoring the ratified GS2 intent over the ratified literal.
Caught in-build (the metric) + at the 4-finder review (the row count + this missing note).**]**

## Part 5 — Implementation readiness gate

Implementation starts on ratification of OQ-1…7, against `pa_1_implementation_plan.md`. Model/effort
for implementation: **Fable 5 / High** for the kernel + methodology doc (novel math with property
obligations — the first governed TRANSFORM of a captured series), **Opus 4.8 / High** acceptable for
the templated remainder (migration/binder/API/tests mirror the PM-1/P3-6 exemplars). Full 4-finder
review at the end (OD-K).

## Part 6 — Review dispositions + closure

**Review (OD-PA-1-K) — appended 2026-07-12.** A FULL 4-finder local max-effort review (kernel/math
correctness; governance/persistence/snapshot; API/entitlement/cross-file/FE; cleanup/conventions/
sweep) over the complete PR-scope diff. The golden derivation was independently re-derived
digit-exact by TWO finders (incl. the HALF_UP round on the observed stdev's 13th digit); the
Geltner inversion, row indexing, like-for-like stdev alignment, TR-09 determinism, migration/ORM
parity, identifier lengths, alpha regex/identity round-trip, RLS symmetry, and all hard invariants
verified intact. **19 raw findings → 12 distinct; 10 folded, 2 deferred:**

1. **HIGH (API, 4×-confirmed) — unknown/cross-tenant `portfolio_id` on the build path escaped as a
   raw 500.** `build_desmoothing_snapshot → resolve_portfolio` raises `PortfolioNotVisible`, which
   was absent from the endpoint's except tuple AND `_ERROR_MAP` (the instrument leg was wrapped;
   the portfolio leg was not — a cross-tenant prober could even distinguish the two). **Folded:**
   mapped → 404 (the exposure.py precedent) + an endpoint test.
2. **HIGH (FE) — the eleventh governed number was invisible in the UI runs list.** `RunsList`'s
   `isPerf` was a hardcoded run-type list; the new family routed to `/risk/runs` → 422. **Folded at
   altitude:** the source is now DERIVED from the family's own `permissionFamily` (a future perf
   family cannot repeat this class) + the missing per-family FE wiring test block added.
3. **HIGH (kernel) — `decimal.InvalidOperation` escape corridor.** An extreme-but-column-legal
   pin/α combination could push the inversion past the 50-digit context, where quantize RAISES —
   after the run was RUNNING (the P3-6 detonation class). **Folded:** `_compute` wraps the kernel +
   stdev calls in `except ArithmeticError → committed FAILED` (`numeric-envelope:*` reason).
4. **MED (adjudication) — mark echoes were not hardened to their column.** No `quantum=` on the
   mark parse (a hand-minted 1E30 mark → PG DataError 500; a 1E-13 mark persisted a ZERO echo
   contradicting the adjudicated invariant). **Folded:** `quantum=_MARK_QUANTUM` (the BT-1
   pattern), the strictly-positive gate now runs on the QUANTIZED value, a `_MAX_MARK_ABS` (1E21)
   gate in `_compute` → committed FAILED, and a `len(currency)==3` shape gate.
5. **MED (adjudication) — duplicate-date detection keyed on the RAW string.** `date.fromisoformat`
   accepts the ISO BASIC form, so `'20260331'` + `'2026-03-31'` bypassed the gate (grain
   IntegrityError 500 mid-run, or a silently wrong series). **Folded:** dedupe on the PARSED date +
   a malformed-date refusal + a two-representations test.
6. **MED (echo stability) — the `alpha` evidence echo drifted between POST ('0.4') and GET
   ('0.400000000000').** The one row column assigned unquantized. **Folded:** α is quantized to the
   column scale once at the binder; the echo is byte-stable across both reads (test updated).
7. **MED (coverage) — the post-create FAILED magnitude path had ZERO coverage** despite the plan
   promising it. **Folded:** `test_magnitude_overflow_is_committed_failed_not_raised` (a labeled
   boundary fixture) proves committed-FAILED + zero rows + reason + no orphan.
8. **MED (coverage) — the mixed-portfolio/instrument OD-H gates were untested** (unreachable via
   the build path). **Folded:** direct `_adjudicate_pins` unit cases for both.
9. **LOW (dedup) — two NEW instrument tenant-guard copies in one diff.** **Folded:** NEW
   `reference/guards.assert_instrument_in_tenant` (the `portfolio/guards` twin, injectable error
   class); both new call sites converted.
10. **LOW (docs/record) — the model + migration docstrings said `n−1` per-period rows (actual:
    `n−2`), and the RATIFIED OD-B named a metric equal to the run family (violating its own OD-F
    GS2 requirement).** **Folded:** docstrings corrected; a dated CORRECTION note added to this
    record (Part 4 area) documenting the in-build `DESMOOTHED_PERIOD` rename + row count. Plus two
    micro-folds: `getattr(outcome, "failure_reason")` → the direct contractual attribute (here AND
    the P3-6 one-off it copied); kernel `zip(..., strict=True)` (the sibling-kernel convention).

**Deferred (2 — recorded, not silently dropped):**

- **D-1 — the declared-parameter parse-back family is at SIX near-verbatim copies**
  (`declared_desmoothing_alpha` + five in `risk/bootstrap.py`): a shared
  `declared_assumption(session, version, prefix)` accessor in `model/service.py` collapses the
  boilerplate (each caller keeps its own pattern/domain check). Cross-slice (re-opens four merged
  registrars) — the RD-1 precedent says a dedicated dedup pass; **register: RD-2 candidate.**
- **D-2 — the two PRE-EXISTING instrument-guard variants** (`proxy_mapping._resolve_instrument_id`,
  `reference.instrument.resolve_instrument`) could also route through the new shared guard —
  next-touch of those files (PA-2 likely touches proxy_mapping).

**Post-fold validation (2026-07-12):** `make check` 1298 passed / 273 skipped (+3 fold tests) +
secret-scan + docs-check; FE 55 (+3) + typecheck + lint; local-PG clean-schema 273 green;
`alembic check` no drift; downgrade-base smoke + restore clean.

**CLOSED (2026-07-12).** Planning merged via **PR #18** (`366a5c4`); implementation (`af155d2` → `11079c9` → `34e8830`) merged via **PR #19** (merge `f8bc20d`), CI green. Migration `0036`. The ELEVENTH governed number — the thesis payload — ships. Deferred to the register: **RD-2 candidate** (the 6-copy declared-parameter parse-back) + the two pre-existing instrument-guard variants (next-touch, likely PA-2).
