# W20 BOOK-1b remit — the private sleeves and the limits

**Wave 20, slice 2.** Branch `w20-book1b`. Authority: `02_requirements/product_rebaseline_2026-09-17.md`
(RATIFIED 2026-09-17, PR #241) Part 4.4 (`:375-383`), `delivery_roadmap.md` Part 2.22 row 2 (`:357`,
with the 2026-09-18 additions), and `purpose_mismatch_remediation_plan.md` §4 Phase 1 (`:65-76`).
Where this remit and the record disagree, the record wins and the disagreement is a FINDING.

**Status: RATIFIED 2026-09-18 by the owner** ("Proceed", after the brief that put nine decisions to the owner and
named seven as routine): every DS-B1b decision as recommended — DS-B1b-1 (a), -2 (a), -3 (B), -4 (b), -5 (B),
-6 (A), -7 (B, B, A), -8 (D), -9 (C), -9a (A), -10 (A), -11 (A), -12 (a), -13 (A), -14 (A, floor seventeen),
-15 (A). The nine decisions BRIEFED to the owner were DS-B1b-1, -3, -4, -5, -7, -8, -9, -10 and -15; the seven
named ROUTINE were DS-B1b-2, -6, -9a, -11, -12, -13 and -14 (each Part 4 header carries its tag; GOV-R-12). The two
clause amendments (DS-B1b-4, DS-B1b-9) were therefore put to the owner, not carried in the routine seven.
Two ratified clauses are AMENDED by this ratification and recorded in the roadmap Part 5 row dated
2026-09-18 (the re-baseline record itself is not rewritten): the chain is "per MATURE private fund" (DS-B1b-4),
and the two backtest families are NOT run in BOOK-1b (DS-B1b-9). DS-B1b-3 (B) is a PRE-SLICE FOLD with its own
gate, before BOOK-1b's seed is written. Part 4 holds the decisions as put; Part 7 holds the fold of the four different-engine lanes (61 findings, 2026-09-18), the second-pass
fold check (10 findings), the round-3 fold check (10 findings, every folded number re-executed), the round-4
fold check (8 findings, every touched number re-executed), the round-5 fold check (6 findings, every touched
number re-executed), the round-6 fold check (6 findings, folded by hand with each site re-read), the round-7 fold check (5 findings, folded by hand), the round-8 fold check (5 findings, none BLOCKING or HIGH, folded by hand; the loop exit), the four claims that stay unverified until the seed exists, and the ratification-diff verification of commit `d676fc4` on a different engine (round 1: 43 findings, 3 BLOCKING; round 2: 7 findings, 1 HIGH; round 3: 4 findings, 1 HIGH; all folded 2026-09-18 in the working tree — the last three tables of Part 7).

Planned on branch `w20-remediation-plan` at `323cedc` ("Phase 0a DONE"); ratified and committed on
`w20-book1b-planning` over main `1c4f64f` (PR #246), together with Phase 0b's benchmark
(`02_requirements/outward_benchmark_cro_overview_2026-09-18.md`, not this slice's deliverable).
Migration head `0077_bind_position_to_mapping`, unchanged by this slice. Next free canonical id ENT-079
(not used: ENT-032 stays reserved, Part 0.14). CI at the PR head to be verified per conclusion at the gate.

Remits state OUTCOMES and PROOFS, not steps. Plain words; short sentences.

**Recon basis.** SIX read-only lanes (Fable 5.1) on 2026-09-18, the roster the roadmap Part 5 row counts
(GOV-R-09, FR-07, CC-10; the first text said "five" and listed six): (1) the private-sleeve chain; (2) commitments
and pacing; (3) total and unified VaR; (4) limits and breaches; (5) seed mechanics for the daily quarter; (6) a
governance lane. Every fact below carries their file:line citations. Where two lanes disagreed, the
disagreement is written as a decision point in Part 4, not smoothed over. Executed evidence is marked
"Executed:" and quoted.

**G2 (P20 T1): declared no-scope, with the reason (DS-B1b-10).** BOOK-1b seeds data and runs delivered
families. It mints no number, no entity, no permission and no route. ENT-032 stays reserved
(`04_data_model/canonical_data_model_standard.md:149`). The G2 script exits 0 today with no slice declared
(Executed: `requirement rows parsed : 103 / adjudicated (any version): 19 / adjudication CURRENT : 11 /
slice scope : 0 / G2_EXIT=0`). An executed probe (2026-09-18, on a scratch copy of the gate's inputs)
scoped to the eight rows DS-B1b-10 (A) names made the gate exit 1 with all eight blocking: seven never
asked (LIM-001, LIM-003, PRV-001/002/003/005, MKT-005) and one lapsed (LIM-002, ledger line 52,
adjudicated 2026-08-15; `slice scope : 8 / blocking : 8 / G2_PROBE_EXIT=1`). The first draft quoted an
eleven-row probe (eight never asked, three lapsed: LIM-002, LIQ-004, SCN-003) that declared rows DS-B1b-10
does not name; the eight-row probe replaces it (N-03). `g2_slice_scope.json` gets a new dated
`no_scope_reason` (at least 60 characters, `scripts/check_g2_adjudication.py:99,293`) that argues the
gate's own test, "rows currently entering build" (`g2_slice_scope.json` `_why`), not the mint test: it
names REQ-LIM-002 clause (3) (`requirements_backbone.md:242`, the strictly-between demonstrating case) and
states that BOOK-1b ships the DATA that makes the clause demonstrable while the STORED utilisation number
the same row demands lands at UTIL-1, so the clause-(3) assertion in the seed is evidence for UTIL-1's
adjudication, not a delivery of the row (GOV-7). It also states why REQ-PRV-003 (Draft, `:173`) can be
served by captures while REQ-LIM-004 (Draft, `:244`) cannot be built: LIM-004's acceptance names the
demo-book demonstration as the deliverable, so building it delivers the row; PRV-003's acceptance also
requires stale-NAV FLAGGING, which BOOK-1b does not build, so its captures serve a row that stays Draft
(GOV-12).

**G5 (P21 T1): declared no-scope, with the reason.** BOOK-1b makes no journey line walkable. It is data
for CRO-1's lines J-CRO-1, J-CRO-5 and J-CRO-7 (the line-to-data map, Part 2.11). `journey_slice_scope.json`
gets a new dated `no_scope_reason` (at least 60 characters, `scripts/check_journey_walks.py:96,269`). The
G5 gate exits 0 today with zero ledger rows (Executed: `journey lines parsed : 12 / ledger rows : 0 /
slice scope : 0 — no slice declared / G5_EXIT=0`).

---

## Part 0 — Organizing facts (recon-verified by the SIX lanes numbered in the Recon basis above; each reshaped the plan)

1. **The desmoothing binder pins every current-head mark in its window. No frequency filter.**
   `snapshot/service.py:2419-2431` selects `Valuation.valuation_date >= window_start` and
   `<= window_end` for the (portfolio, instrument) pair; `:2436-2440` refuses fewer than two marks.
   Any weekly or daily carry mark inside the window becomes an appraisal period. **So the appraisal
   window must end before the first carry mark**, which is the first boundary, 2025-06-30. The
   re-baseline says the same (`product_rebaseline_2026-09-17.md:375-377`). The lanes disagree on the
   end date: 2025-03-31 (strictly before the marked year) or 2025-06-30 (the first boundary, itself a
   quarter end). That is DS-B1b-1.
2. **Twelve quarterly marks clear every observation floor.** Executed on the book's calendar:
   `appraisal grid 2022-06-30 .. 2025-03-31 marks 12 observed 11 desmoothed 10`. Desmoothing needs
   4 marks (`perf/desmoothing_service.py:100` `_MIN_MARKS = 4`); AR1 estimation needs observed
   returns at or above `max(min_periods, 6)` (`:364-369`, `perf/bootstrap.py:458`); regression needs
   `n >= max(min_observations, k+2)` (`risk/proxy_weight_service.py:303`), 10 >= 4 for k = 2.
3. **The regression cannot run on BOOK-1a's factor data. Coverage is zero.** The regression refuses any
   appraisal period with no factor return inside `(period_start, period_end]`, with no zero-fill
   (`proxy_weight_service.py:313-323`; the snapshot builder refuses first at `snapshot/service.py:2760-2765`).
   BOOK-1a's factor returns start 2025-04-01 (`book.py:73` `RETURNS_START = date(2025, 4, 1)`).
   Executed: `any RETURN_DAY <= 2025-03-31: False`; the lane's probe: `periods covered by BOOK-1a factor
   returns ...: 0 of 10`. **So BOOK-1b mints factor returns inside every appraisal period** (DS-B1b-2).
   The shipped shape is HG-1's: one SIMPLE return per desmoothed-period end per candidate factor
   (`demo/hg1_private.py:341-356`). Minted dates on or before 2025-03-31 are invisible to every daily
   covariance window, because a window takes the N most recent common dates
   (`snapshot/service.py:1093` `window_dates = sorted(common)[-window_observations:]`) and the
   earliest daily return is 2025-04-01.
4. **The total and unified VaR staleness gate is strict and its policy is a required parameter.**
   `risk/var_service.py:650-651`: `age = (window_end - estimate_snapshot.as_of_valuation_date).days` /
   `if max_estimate_age_days is not None and age > max_estimate_age_days:` refuses.
   `risk/bootstrap.py:2736-2737` makes `appraisal_days` and `max_estimate_age_days` required at
   registration. Executed: `age at YEAR_END from 2025-03-31: 456 ; from 2025-06-30: 365`. The policy
   value follows from DS-B1b-1. **The gate binds on the TOTAL flavour only** (R4V-02): the age is
   measured over the cited estimates (`var_service.py:567-577`, `_estimate_age_days` returns "the MAX
   estimate age in calendar days across the cited estimates ... or ``None`` when there is nothing to
   measure"); the total builder pins every REGRESSION row on the exposure instruments
   (`snapshot/service.py:3378-3395`), but the unified builder skips a segment member's REGRESSION rows
   (`:3612-3613` `if iid in private_member_instruments: continue`), and under this remit every mature
   private fund is a member, so the unified row's `proxy_weights` is empty (`var_service.py:1253-1293`)
   and its `estimate_age_days` is None. The 548-day policy is declared on the unified model because
   registration requires it (`risk/bootstrap.py:2923`) and is structurally inert there; DS-B1b-1's
   staleness consequence bites on VAR_PARAMETRIC_TOTAL only.
5. **Promotion reads the real clock, but refuses only when a bound is supplied.**
   `proxy_weight_service.py:682` `promotion_age_days = (utcnow().date() - span_end).days`; `:683`
   `if max_promotion_age_days is not None:`. Executed: `promotion age today from 2025-03-31: 536`.
   The seed passes no bound (HG-1 did the same, `hg1_private.py:15-17`). The stored
   `promotion_age_days` on the mapping row (`:709`) differs by seed day. That is the one
   clock-derived field the seed writes; it is named, and the determinism proof excludes it (Part 5).
   A second clock path exists and the seed must not reach it: the pacing snapshot's as-of is the
   pinned mark's date OR the real clock (`snapshot/service.py:2605` `as_of_valuation =
   mark.valuation_date if mark is not None else now.date()`), so a commitment pair with NO mark would
   anchor `current_age` and every projected window on the seed day (FEAS-2). Every pacing pair
   therefore carries a 2026-06-30 mark, position or not (Part 3.7).
6. **The NL-PMF root loadings run refuses an unmapped atom, and it pins current-head mappings.**
   `risk/factor_service.py:507` `gaps.append(f"unmapped-atom:...")`; `snapshot/service.py:905-914`
   pins `ProxyMapping` rows with `valid_to IS NULL AND system_to IS NULL` at build time. **So the
   private chain (appraisal → desmooth → regression → promote) runs BEFORE the first NL-PMF
   month-end**, and one promotion serves all 13 month-ends and the daily quarter. **A second, earlier
   refusal sits in the same run** (R3-01): the loadings snapshot pins only LOADING-family mappings
   (`snapshot/service.py:894-914`, `Factor.factor_family.in_(LOADING_FACTOR_FAMILIES)`;
   `marketdata/models.py:176-186` lists nine families, none PRIVATE), and `_assert_full_coverage`
   (`factor_service.py:414-441`, called at `:650` inside the pre-create block that opens at `:546`)
   refuses before `create_run` when any pinned atom has NO loading row. A PRIVATE segment membership
   is therefore not coverage; every private instrument, young or mature, needs at least one
   LOADING-family row (Part 2.3; the mature funds' REGRESSION rows are that row), and for the unified
   builder that row must be NON-ZERO, because a zero-weight pin emits no exposure row and the builder
   sees only exposure instruments (R4V-01, Part 2.3). Today the seed's
   order is `_register_models` → `_run_account_boundaries` → `_run_month_end_chain` →
   `_run_return_chains` → `_run_sensitivity` (`demo_tenant/seed.py:1234-1239`, re-read at the
   ratification-diff fold). **The BOOK-1b orchestrator order, stated once (FR-01):**
   `_register_models` → **`_run_private_chain`** (new; C-05) → `_run_account_boundaries` →
   **`_run_daily_chain`** (new; the 59 dates of Part 2.7) → `_run_month_end_chain` (unchanged 13
   iterations, with the LIMIT EVALUATION inside the loop at the 2026-04-30, 2026-05-29 and 2026-06-30
   iterations, after that iteration's concentration and liquidity runs, `seed.py:1076-1104`; DS-B1b-8
   (D)) → `_run_return_chains` → `_run_sensitivity`. The daily chain runs BEFORE the month-end chain
   because the limit resolver orders by wall clock, not by as-of (`calc/reads.py:101-103`
   `order_by(CalculationRun.system_from.desc(), ...)`): a daily NL-GMA VAR_PARAMETRIC run created after
   the June evaluation would become "latest", carry no breach row, and break `limit_health` (Part 0.10,
   Part 5 mutant 9). After `_run_month_end_chain` no step creates a run of a limited family (VAR,
   CONCENTRATION, ACTIVE_RISK) for a fund root: `_run_return_chains` creates PORTFOLIO_RETURN,
   BENCHMARK_RELATIVE, ROLLING_RISK and SHARPE runs only (`seed.py:1116-1179`) and `_run_sensitivity`
   creates SENSITIVITY runs.
7. **Unified VaR at the NL-PMF root refuses today, because the builder does not conform to its own
   registered `v1` assumption.** The registered text says the p vector sums "MANUAL-members i of
   segment s" and a repartitioned instrument is "a current-head MANUAL member of a pure-private
   segment" (`risk/bootstrap.py:2852-2853,2863`, inside `VAR_UNIFIED_ASSUMPTIONS_BASE`; version label
   `v1` at `:2840`). The builder ignores the segment restriction: it treats EVERY current-head MANUAL
   proxy_mapping on the exposure instruments as a pure-private segment membership, with no
   factor-family filter (`snapshot/service.py:3556-3568`, `:3574` `held_segments =
   {str(r.factor_id).lower() for r in manual_rows}`, `:3583`). BOOK-1a gives every instrument at least
   one MANUAL loading, including NL-PMF's T-bills and cash (a zero-weight FX_USD row; `seed.py:686-687`),
   so a public factor is read as a held segment. Executed (SQLite probe, 4 passed): `PROBE A (mixed
   fund, MANUAL public loading): ... held pure-private segments [...] are absent from the pinned
   Omega_pp run`; `PROBE D (mixed fund, public instrument with NO manual row): COMPLETED`. The engine
   can price a mixed book; the code is non-conformant with the model version's declared assumption.
   That is DS-B1b-3, it is BLOCKING for "unified VaR" as the roadmap row writes it, and the assumption
   question belongs to model governance — CTRL-003, the model inventory (`register_model` /
   `register_model_version`, `09_compliance_controls/control_matrix_skeleton.md:44`), and CTRL-022,
   independent validation, whose `model.validate` write is 2L-only (`:63`); CTRL-014 (`:55`) is the
   limitations register and is touched only if the `v1` version records a `model_limitation` row
   (GOV-R-04: the first text named CTRL-014 as "the registrar") — not to G2, which
   gates requirement rows (GOV-6; C-10 corrected `:3575` to `:3574`).
8. **Unified VaR is an NL-PMF-only number.** On NL-GMA and NL-EFI the unified builder refuses
   pre-create, but TODAY on the uncovered-held-segment gate (`snapshot/service.py:3574-3584`, Part 0.7's
   hazard), not on the "no MANUAL pure-private membership" gate at `:3569-3573`: `manual_rows` has no
   family filter and BOOK-1a gives every instrument a MANUAL loading (`seed.py:658-660`; the zero-weight home-currency row at `:686-687`), so it is never
   empty. Only after DS-B1b-3 = B does the `:3570` gate become the reason. PROBE B and PROBE C ran on
   the two public funds; which message each produced is re-quoted in the record from a re-run (FEAS-3,
   FEAS-9). Total VaR on NL-GMA and NL-EFI is expected to equal plain VaR (no REGRESSION rows, so an
   empty residual leg); the first draft cited `var_service.py:389-391` for this, which is a docstring
   about pins that ARE present and says nothing about an empty pin set (C-03). The claim is therefore
   PROVED, not cited: the seed runs total VaR on all three funds at the 13 month-ends and the suite
   asserts `total == plain` on NL-GMA and NL-EFI at every month-end. That also keeps the ratified
   clause "every governed family run against each fund" (`product_rebaseline_2026-09-17.md:384-385`)
   without a departure (GOV-11). The remit states the flavour-by-fund matrix (Part 2.5) so the census
   and the CRO screen are honest.
9. **Every VaR flavour shares run_type VAR; `latest` without `metric_type` returns whichever ran
   last** (`var_service.py:1490,1520`; `calc/reads.py:101-103`; `api/risk.py:1752` makes it
   optional). Every BOOK-1b read, limit and golden passes `metric_type`.
10. **Limits: the admitted targets match the roadmap; liquidity is not one.** `limit/service.py:131-169`
    `_METRIC_MAP` admits six VaR flavours, TRACKING_ERROR, and the concentration metrics;
    `LIMIT_FAMILY_REGISTRY` (`:448`) has VAR, ACTIVE_RISK, CONCENTRATION only. Scope is an exact
    `scope_portfolio_id` match (`limit/models.py:125-129`); the seed's month-end root runs are
    root-scoped, so a root limit resolves (Executed: `latest_var_for_portfolio(root,
    metric_type='VAR_PARAMETRIC')` → `NL-GMA VAR_PARAMETRIC 1734274.488757 USD`). Evaluation is the
    tick's, importable with an injected `now` (`service.py:577`); the resolver takes the LATEST
    COMPLETED run by wall clock (`calc/reads.py:101-103`), so **no step after the June evaluation may create a COMPLETED run of a limited family (VAR,
    CONCENTRATION, ACTIVE_RISK) for the three fund roots** (Part 0.6's invariant in Part 0.6's words,
    VF1-05; the first rewrite said the evaluation "must be the last step that creates a COMPLETED run",
    but the evaluation creates no run — it appends a breach row, `limit/service.py:577-598`, and the run
    it reads comes from `_resolve_latest` at `:586`): the daily chain runs BEFORE the month-end chain and each of the three
    evaluations sits inside the month-end loop after its own iteration's runs (Part 0.6, FR-01; the
    first text said "the orchestrator's last step", which would have collapsed the three
    evaluations onto one run under `uq_breach_limit_run`). A
    breach is one row per (limit, run) (`models.py:177` `uq_breach_limit_run`); re-evaluation is
    idempotent (Executed: a second pass returned the same two ids and wrote nothing).
11. **"Exactly one utilisation strictly between" and a CRO-recognisable grid cannot both hold.**
    Executed at 2026-06-30: every admitted observed value in the book is strictly positive except
    tracking error on NL-EFI and NL-PMF (`TE 0E-12`), because the engine is currency-only
    (`w20_book1a_slice_record.md:49-53`; C-01) and both funds are single-currency. A TE limit on either
    fund would show "0 %, in appetite" on the first screen for a number that is structurally zero, so
    NO TE limit is set on NL-EFI or NL-PMF (CRO-R5): ten limits (nine at round 3; a sector limit added at
    round 4, R3-03), not eleven, none at zero. Every
    admitted observed value in the grid is then breached or strictly between. The ratified text says
    "one utilisation strictly between", not "exactly one" (`product_rebaseline_2026-09-17.md:380-383`).
    That is DS-B1b-5.
12. **The daily last quarter is 62 business days, not "about sixty-three".** Executed with the book's
    XNYS calendar: `Q2 business days 62 2026-04-01 2026-06-30 / already boundaries 13 new 49 / union 105
    / Q2 month-ends [2026-04-30, 2026-05-29, 2026-06-30] daily-chain dates excl month-ends 59`. Holidays
    in the span: Good Friday 2026-04-03, Memorial Day 2026-05-25, Juneteenth 2026-06-19
    (`xnys_holidays.py:92-94`). The generator draws its random stream per RETURN_DAY and only RECORDS
    on boundaries (`book.py:1429-1451`), so adding dates moves no existing mark or FX (Executed:
    `marks on every old boundary identical: True`, `fx on old boundaries identical: True`). But the
    benchmark series is CUT at boundaries (`book.py:1490-1496`): extending `BOUNDARIES` itself re-cuts
    it (Executed: `benchmark return at YE old/new -0.001244 0.004666`). That is DS-B1b-7.
13. **The golden selectors break on a duplicate, not on a moved number.** Golden 4.3 uses
    `scalar_one()` over VarResult rows at `window_end == 2026-06-30`
    (`test_demo_tenant_book1a_pg.py:366-381`; `test_demo_tenant_seed.py:91-104`; C-11). A daily chain that
    re-runs the three Q2 month-ends raises `MultipleResultsFound` in both suites. The three goldens
    themselves do not move (Executed: `derive_northlight_var.py` → `VaR 99/1d EUR: 464184.575474`,
    `EXIT=0`, under the extended date set).
14. **Utilisation is not stored; ENT-032 is UTIL-1's.** `evaluate_limit` returns None on a refusal or
    a cold metric and persists nothing (`limit/service.py:587-588`); `limit_health` is derived on
    demand (`:1170`). REQ-LIM-002 clause (1) makes utilisation a STORED number
    (`requirements_backbone.md:242`); clause (3) is the demonstrating case this slice seeds. BOOK-1b
    supplies the case without realising the row. The "two open gaps" of REQ-LIM-002 live at
    `wave_19_planning.md:132`, not in the backbone row; the roadmap (`:359`) restates the two gaps
    inline without a pointer, and the re-baseline cites the backbone (C-13). This remit cites `wave_19_planning.md:132` (carry to UTIL-1, Part 6).
15. **The pacing read is per (portfolio, instrument) pair and its as-of is the latest mark's date.**
    `api/pacing.py:396-399` requires both ids and 404s without a COMPLETED run (`:419`);
    `snapshot/service.py:2590-2605` pins the latest current-head mark for the SAME pair and takes its
    date as the business as-of. `current_age` counts complete anniversaries from `commitment_date`
    (`pacing/service.py:204`) and the first projected window starts at the last anniversary
    (`pacing_kernel.py:117-120,150`). **So commitment and NAV mark share one portfolio id, the pair
    needs a 2026-06-30 mark, and vintages dated 30 June make the "next projected call" window start
    on the as-of** (Executed probe: a 2023-09-15 vintage projects `[2025-09-15, 2026-09-15)`, nine
    months already past). No fund-level unfunded rollup exists (`pacing_commitment_projection_v1.md:17-18`;
    `api/pacing.py:26` calls cross-run aggregation a consumer error).
16. **The Northlight roster holds no `commitment.*` or `pacing.*` code.** `demo_tenant/seed.py:163-186`
    `_READ_PERMS` (22 codes) has none; the routers require them (`api/pacing.py:77-78`). The catalog
    already holds all five (`entitlement/bootstrap.py:142-144,154-155`), so granting them is a roster
    edit, not a P17 mint. The seed writes through services and would not notice; the deployed CRO
    would 403. That is DS-B1b-13.
17. **Two BOOK-1a rules the private sleeves must not break.** The generator is one shared
    `random.Random(SEED)` stream consumed in a fixed order: the factor draws (`book.py:1371,1394,1403`),
    then the public mark noise inside `for inst in INSTRUMENTS` (`:1438` `noise = rng.gauss(0.0, idio)
    if idio > 0 else 0.0`), then the BENCHMARK noise inside `for fund in FUNDS` (`:1481` `noise =
    rng.gauss(0.0, float(m.daily_sigma)) ...`). Appending instruments AFTER the 55 protects the public
    marks but NOT the benchmark series: a private spec that takes even one draw at `:1438` shifts every
    benchmark draw after it, and the three goldens read marks, FX and factor returns only
    (`test_demo_tenant_book1a_pg.py:55-57`), so they would stay green while every BOOK-1a benchmark
    return and tracking-error value moved (FR-02; the verifier's probe, twelve appended specs with
    idio sigma 0.0100: `public marks identical : True / benchmark identical : False`). **So the private
    specs take NO draw from the shared stream** — idio sigma zero in `generate_paths`, and their
    appraisal and step marks come from their own `random.Random(SEED + 2)` (fence 21's pattern;
    `SEED + 1` is the two new factors'). The proof is Part 5's determinism proof: the three goldens
    PLUS a byte-equality assertion on the public mark and benchmark series. The
    time-bomb fence greps the package for `now(`, `today(` and any date literal later than
    2026-06-30 (`test_demo_tenant_book.py:110`); a fixed breach-detection instant must therefore
    be ON or before 2026-06-30, not 2026-07-01 (Part 3.9).
18. **A private fund cannot have three years of appraisals before its own vintage.** The pacing lane
    recommends a vintage ladder 2019 to 2025 for realism; the private-chain lane needs 12 marks from
    2022-06-30 on every risk-bearing instrument; the pure-private family refuses members of one
    segment with different appraisal grids (`private_factor_service.py:277-281`) and the private
    covariance needs exactly `window_observations` common periods (`private_covariance_service.py:176-179`).
    The lanes did not see each other. That is DS-B1b-4.
19. **Engine facts carried from BOOK-1a §2, still true.** Scenario is single-portfolio and
    currency-only (`w20_book1a_slice_record.md:27-38`); tracking error is currency-only (`:49-53`);
    `GET /exposure/latest/sum` is leaf-only, the fund total comes from the run-keyed rollup
    (`:70-76`); the home-currency loading is an explicit zero (`:44-48`); 56 boundaries, 13
    month-ends (`:39-43`); 6,105 captures counted by the seed's own counters (`:65-69`); the seed runs
    on in-memory SQLite in 33 s (`:60-64`). §2.9's Docker carry is DISCHARGED by Phase 0a
    (`purpose_mismatch_remediation_plan.md:51`; roadmap `:355`).
20. **The reproduction census covers every family this slice runs.** Executed:
    `irp_shared.reproduction.REPRODUCIBLE_FAMILIES` holds 19 (ACTIVE_RISK, BENCHMARK_RELATIVE,
    COVARIANCE, COVARIANCE_PRIVATE, DESMOOTHED_RETURN, ES_BACKTEST, EXPOSURE_AGGREGATE, FACTOR_EXPOSURE,
    PACING_PROJECTION, PORTFOLIO_RETURN, PROXY_WEIGHT_ESTIMATE, PURE_PRIVATE_FACTOR, REPORT, ROLLING_RISK,
    SCENARIO, SENSITIVITY, SHARPE, VAR, VAR_BACKTEST) and `UNREPRODUCIBLE_FAMILIES` holds 2
    (CONCENTRATION, LIQUIDITY). Total and unified VaR ride run_type VAR (Part 0.9). Consequence: because
    VAR is reproducible, the DS-B1b-3 (B) fold must not change the unified result of any run already
    stored on a deployed stack; the fold checks that BEFORE it lands, not after (GOV-9; the former
    Part 6 out-carry (6) is deleted).
21. **Two book facts the first draft got wrong, re-measured.** The NL-PMF reserve is 45,598,600 USD at
    START prices only (`book.py:1118-1162`); marked at 2026-06-30 it is **45,678,907.400000 USD**
    (Executed over `book.generate_paths()`: `USTB-3M start 989.60 YE 991.3740 qty 22000 / USTB-6M start
    979.30 YE 981.5933 qty 18000 / NLUSD-CASH-PMF 1.0000 qty 6200000 / NL-PMF reserve marked at YE
    45678907.400000`; the same script reproduces `NL-GMA total 155681069.672680`, the golden). The
    exposure run reads marks, so every hand figure in this remit uses the marked reserve (N-01, CRO-R10).
    And the FX cross series is a THIRD widening site: `book.py:1418-1421` iterates `BOUNDARIES` directly
    (`for d in BOUNDARIES`), not behind an `if d in BOUNDARIES` guard; the seed then does a bare lookup
    `rate=series[on]` (`seed.py:613`). Executed: `FX series key counts: {('EUR','USD'): 56, ('GBP','USD'):
    56, ('GBP','EUR'): 56}` / `cross fx KeyError on first new date: 2026-04-01` (FEAS-1; Part 2.7).

---

## Part 1 — Scope line, stated so the gap is not read as an omission

**IN:** the private sleeves of NL-PMF as holdings with issuers, classification and liquidity tier; a
three-year quarterly appraisal history per mature private fund on one common grid; minted quarterly
factor returns inside every appraisal period; one desmooth → regression → promotion chain per mature
private fund, a PRIVATE segment factor per sleeve with MANUAL memberships, one pure-private run per
segment and one private covariance; commitments, calls, distributions and one pacing projection per
(account, fund) pair; total VaR on all three funds and unified VaR on NL-PMF; the roster's pacing and
commitment codes; ten limits on the three fund roots, approved by the CRO principal, evaluated at the
last three month-ends with fixed instants, with two live breaches; the daily last quarter as a separate date set with a public daily VaR chain; the
census; the goldens; the mutants; the seed-time measurement.

**OUT, by design, with the host named:** any screen → **CRO-1**; utilisation as a stored number,
ENT-032, the REQ-LIM-002 gaps → **UTIL-1**; a strategy-node limit (REQ-LIM-004) → **its own gate**
(DS-B1b-11); the breach response form → **PM-1**; the VaR and ES backtest families → **deferred, as a NAMED DEPARTURE from the ratified "every
governed family run" clause (`product_rebaseline_2026-09-17.md:384-385`) that the owner is asked to
amend at this gate** (DS-B1b-9; DP-RB2-7 reaches new families only, GOV-5); the fund-level return and scenario across accounts → **Wave-21
candidates** (BOOK-1a §6.1); a fund-level unfunded rollup → **not built** (v2 per the methodology);
running the seed inside CI's `stack-proof` job → not in this slice; the unified-builder family filter and the
private-asset-class coverage refusal (DS-B1b-3 (B), ratified) → **its own small pre-slice fold**, not this diff.

---

## Part 2 — Outcomes

### 1. The private sleeves are holdings, not empty nodes

NL-PMF's two private accounts (`NL-PMF-PE-PRIM`, `NL-PMF-PC-DL`; `book.py:241-262`) hold private-fund
interests: one instrument per underlying fund, asset class `PRIVATE_EQUITY` or `PRIVATE_CREDIT` (the
hg1/ds2 precedent), an issuer (the general partner), a sector, a country and the ILLIQUID tier
(`classification/models.py:150-155`), because concentration and liquidity run at the fund root and
`_seed_instruments` (`seed.py:501`) needs them: `InstrumentSpec` carries `issuer` and `liquidity_tier`,
and `IssuerSpec` carries `country` and `sector` (`book.py:268-296`; C-08). Each holds a position of
quantity 1 marked at NAV in USD, the fund's base, because the total and unified residual legs refuse a
series currency other than the base (`var_service.py:447-453`; C-07). **Names and classification are
acceptance, not detail** (`test_data_realism.md:34-41`; CRO-R11): fund instruments are named as LP
interests with vintage and series (the shape "Ridgeline Capital Partners V, L.P."), GP issuers as
management companies ("Ridgeline Capital Management LLC"), issuer country = the GP's domicile, and each
private instrument is classified by its STATED STRATEGY FOCUS (a healthcare buyout fund → ISIC section
Q, a software growth fund → J, a diversified fund → K), so NL-PMF's sector view says something a CRO
uses rather than "82 % financial activities". The suite asserts no private instrument or issuer name
matches a fixture pattern (`^(INSTR|FUND|PE|DL)[-_]?\d`) and that at most two private instruments carry
section K. The count and the vintage ladder follow DS-B1b-4; the
recommended shape is twelve funds (seven PE, five direct lending), eight of them mature (DS-B1b-4's roster). The new
instruments are appended AFTER the 55 public ones in `book.INSTRUMENTS` and take NO draw from the
public random stream (idio sigma zero; their own `random.Random(SEED + 2)`, Part 0.17, FR-02); their marks
come from a private schedule (outcome 2), not the random walk. **ISIN convention** (FR-08): `InstrumentSpec.isin`
has no default (`book.py:280` `isin: str  # ISIN-shaped under the user-assigned ZZ prefix`), so each of the
twelve LP interests carries its own `ZZ` ISIN minted through `book.isin(base)` (`book.py:42-54`, the Luhn
check digit over an 11-character base), and the existing fence `test_demo_tenant_book.py:73-76` (unique
ISINs, `ZZ\d{10}`, check digit valid) is asserted over all 67, not amended (Executed at the fold over the 55:
`isin unique True check ok True`). **Proof:** the suite asserts the three BOOK-1a goldens verbatim and unchanged; asserts
every private instrument has an issuer, a sector, a country, a tier and a position; asserts the
NL-PMF root's 2026-06-30 exposure total equals the MARKED reserve, 45,678,907.400000 USD (Part 0.21, not
the 45,598,600 start-price face), plus the private NAVs, with the derivation shipped beside it (MD-H1;
N-01, CRO-R10).

### 2. The appraisal history, and the window that keeps the marked year out of it

Per mature private fund: **12 quarterly marks on the common grid 2022-06-30 to 2025-03-31** (DS-B1b-1
as recommended), captured with `create_valuation(..., currency_code='USD', valid_from=book.T0)` exactly
as `demo/hg1_private.py:318-328` does, because the desmoothing binder refuses a currency that is not
three characters (`desmoothing_service.py:208-211`; C-04, FEAS-7), the proxy-weight binder re-checks it
on `mark_currency` (`proxy_weight_service.py:240-242`), and the pacing anchor compares it to the
commitment's (`pacing/service.py:159`). Generated by an honest pre-smoothed generator with a known
alpha (the HG-1 shape), so the desmoothed series recovers a known structure and a hand golden exists.
**The mark series is a flow-free VALUE INDEX** (CRO-R2): the kernel differences consecutive marks
(`desmoothing_kernel.py:46-48` `r_a,t = mark_t/mark_{t-1} - 1`) and the binder pins every mark in the
window with no flow adjustment (`snapshot/service.py:2419-2431`), so a 3M call folded into a 20M NAV
would print as a +15 % quarter and desmoothing would amplify it by about 1.67 at alpha 0.4. The
appraisal marks are therefore NAV_t = NAV_{t-1} × (1 + r_t) from the generator, and the calls and
distributions are the separate paid-in / DPI record (outcome 4); the record says the demo's appraisal
series is deliberately flow-free, which is what a GP's gross-of-flows unit-value series is. **Economic
targets are acceptance** (CRO-R7): per sleeve, the annualised desmoothed volatility band (PE 16-24 %,
direct lending 5-10 %) and the smoothing ratio observed stdev / desmoothed stdev in [0.55, 0.80] at
alpha 0.4; the scale reference is `MKT_GLOBAL_EQ`'s daily sigma 0.0090 (`book.py:151`), 14.3 %
annualised. Per quarter, every observed appraisal return sits in [-0.15, +0.20]. **The youngest mature
fund shows a J-curve** (CRO-R14): its first four quarterly returns are negative or near zero, turning
positive from year 2; the suite asserts its cumulative return over the first four appraisal periods is
negative. The measured values are quoted in the record.
In the marked year every private instrument carries a step series: a fresh NAV at each quarter end
(2025-06-30, 09-30, 12-31, 2026-03-31, 06-30) carried forward on every boundary between, so the
exposure binder's exact-date rule is met on all 105 mark dates (`holdings/service.py:210-213`;
`exposure/service.py:304-306` `missing-mark`). None of those marks is inside the desmoothing window.
The young DL fund with vintage 2025-06-30 sits ON the first union date (Executed, round 4:
`BOUNDARIES[0] 2025-06-30`), so its first step-series mark is its own vintage-day NAV: it carries a
same-day first DRAWDOWN of at least 1,000,000 USD and that mark equals the paid-in amount, inside the
private NAV band of Part 3.14 (R3-04; the rule is stated at DS-B1b-4).
**The window proof:** the suite asserts, per mature fund, the desmoothing summary row's `n_periods`
equals 10 and the pinned-mark count equals 12; a mutant moving `window_end` onto or past 2025-06-30
raises the pinned count and is KILLED by that assertion (Part 5). **Line-to-data:** the summary row
(desmoothed stdev beside observed stdev, `desmoothing_service.py:4-9`) is J-CRO-5's "reported vs
desmoothed with the difference".

### 3. Desmooth → regression → promotion, per mature fund, before the first month-end

- Models registered under `book.CODE_VERSION` in `_register_models`, which today registers none of
  these (`seed.py:834-892`): `register_desmoothed_return_model(alpha=...)` (DECLARED convention,
  DS-B1b-12), `register_proxy_weight_regression_model(min_observations=3)`,
  `register_var_parametric_total_model(confidence_level, appraisal_days=91, max_estimate_age_days=548)`,
  `register_pure_private_factor_model`, `register_private_covariance_model(window_observations=10)`,
  `register_var_parametric_unified_model(appraisal_days=91, max_estimate_age_days=548)`
  (`risk/bootstrap.py:2915`; GOV-13; the unified policy is declared because `:2923` requires it and is
  inert while every private instrument is a segment member, Part 0.4, R4V-02), and two pacing labels
  (outcome 4). No EXCEPTION validation with an expiry (DS-B1a-8's rule).
- `run_desmoothed_return(..., window_start=2022-06-30, window_end=2025-03-31)` per mature fund
  (`desmoothing_service.py:236-248`): 10 DESMOOTHED_PERIOD rows plus one DESMOOTHING_SUMMARY row.
- Quarterly factor-return mint: one SIMPLE return per candidate factor per desmoothed-period end, ten
  dates 2022-12-31 to 2025-03-31, all on or before 2025-03-31 (Part 0.3). **The candidate set must be
  unit-homogeneous: PRICE-RETURN factors only** (CRO-R1, CRO-R13; DS-B1b-15). The first draft proposed
  `RATES_USD_10Y` and `CREDIT_HY`, which are yield and spread CHANGES (`book.py:152,157`; the book's own
  loadings on them are durations, `book.py:410,434-435`), so an OLS of a quarterly private return on
  them returns a duration-like coefficient of order 5 to 20, signed negative for a widening. That
  coefficient is multiplied straight into market value (`factor_service.py:481` `raw = pin.weight *
  atom.exposure_amount`) and the unified adjudicator SUMS the rows per instrument into MV_i
  (`var_service.py:1245-1250`), so a direct-lending fund would enter the p vector at something like
  -7 × NAV. With return-type factors the weights are betas near 1 and Σ weights ≈ 1. The book has one
  such factor (`MKT_GLOBAL_EQ`), so BOOK-1b adds two total-return index factors to `book.FACTORS`,
  `CREDIT_HY_TR` (US high-yield total return, daily sigma about 0.0025, family CREDIT_SPREAD like
  `CREDIT_HY`, `book.py:157`) and `RATES_UST_TR` (US Treasury total return, about 0.0018, **family RATES**
  like `RATES_USD_10Y`, `book.py:152`; FR-06), on the same daily grid and minted quarterly like the others.
  Both families are in `LOADING_FACTOR_FAMILIES` (Executed, round 5: `'RATES'` and `'CREDIT_SPREAD'` in the
  nine), so the eight mature funds' REGRESSION rows on either factor are pinned into the root loadings
  snapshot and count for `_assert_full_coverage` (fence 3).
  **Constraint:** `generate_paths` draws factors first and marks after from ONE `random.Random(SEED)`
  (`book.py:1394-1405`, then the mark noise at `:1438`), so two factors appended to `FACTORS` would
  shift every public mark draw and move all three goldens; the new factors draw from their own
  `random.Random(SEED + 1)` stream, and the three goldens unchanged is the proof. The two candidate sets
  differ, so each new factor is fitted to something: PE = `MKT_GLOBAL_EQ` + `CREDIT_HY_TR`, direct
  lending = `CREDIT_HY_TR` + `RATES_UST_TR` (the fold check's option (i), F-01: the first fold wrote
  the same two factors for both sleeves, which made the union two and left `RATES_UST_TR` fitted to
  nothing). A floating-rate loan book has little duration, so the generator gives direct lending a
  SMALL positive loading on `RATES_UST_TR` (the funding-cost leg) and the larger one on `CREDIT_HY_TR`;
  the fitted rate weight is expected small and positive, inside the band below. Union three factors,
  **30 minted returns** (3 × 10 dates). k = 2 gives the floor `max(3, 4) = 4` against n = 10. **Magnitude convention** (CRO-R12):
  each minted quarterly return is drawn at the factor's quarterly scale, sigma = daily_sigma × sqrt(63)
  (`MKT_GLOBAL_EQ` → 0.0714, mean 0.00045 × 63 = 0.028); the suite asserts every minted value within
  3 sigma of that band and no minted date on or after 2025-04-01. The series then carries two
  frequencies with no marker: `factor_return` has `return_date`, `return_type` and `return_value` and
  no periodicity column (`marketdata/models.py:743-746`), and the FACTOR's `frequency` is DAILY (`:197`,
  WEEKLY/MONTHLY reserved). The record states this as a known shape of the demo data. **Acceptance
  band** (CRO-R1): per mature fund every promoted weight is strictly positive and Σ weights ∈ [0.80,
  1.35]; the NL-PMF root's 2026-06-30 factor-exposure total over the EIGHT MATURE private instruments
  (rows selected by instrument id) is within 35 % of the sum of THOSE EIGHT instruments' 2026-06-30 NAV
  marks (both sides pinned to the mature set by name; R3-07 as restated at round 5, R4V-01: the four
  young funds DO emit exposure rows under the sleeve-proxy loading below, so they are kept out of the
  band by selection, not by emitting nothing, and each carries its own exact assertion: exactly ONE
  factor-exposure row at 2026-06-30, equal to 1.0 × its NAV mark, `factor_service.py:481` `raw =
  pin.weight * atom.exposure_amount`); a mutant that sets one promoted weight negative is KILLED by the
  band assertion (Part 5).
- `run_proxy_weight_estimate(..., desmoothed_run_id, factor_ids)` per mature fund
  (`api/risk.py:3517-3518`); then `promote_proxy_weight_estimate(...)` per (fund, factor) with the
  seed reading the estimate's WEIGHT rows and passing the coefficient as the caller's choice — the
  service does NOT read the weight from the run (`proxy_weight_service.py:642-644`; C-14) — and **no
  `max_promotion_age_days`** (DS-B1b-6; `:683`), writing REGRESSION-method `proxy_mapping` rows citing
  the run.
- One PRIVATE-family APPRAISAL factor per sleeve, a weight-1 MANUAL membership per mature member,
  one pure-private run per segment (`private_factor_service.py:13-14,284-287`), one private
  covariance over the two segments with `window_observations = 10` (`private_covariance_service.py:151-154,176-179`).
- Young funds (holdings under DS-B1b-4 (b), ratified): **a weight-1 MANUAL MEMBERSHIP of the sleeve's
  PRIVATE segment factor PLUS one NON-ZERO MANUAL loading on the sleeve's primary return-type factor**
  (PE: `MKT_GLOBAL_EQ`, family MARKET; direct lending: `CREDIT_HY_TR`, declared in family CREDIT_SPREAD
  like `CREDIT_HY`, `book.py:157`), each at weight 1.0, the sleeve proxy at beta 1; no chain, disclosed
  in the record as "proxied until history exists". Two gates shape this row, and the round-4 shape
  satisfied only the first (R3-01, then R4V-01, both BLOCKING). First, the membership alone would fail
  the deploy-path seed (given that `_seed_loadings` skips private specs, V6-01, fence 22): the NL-PMF root loadings run pins only LOADING-family mappings
  (`snapshot/service.py:894-914`; `marketdata/models.py:176-186`, nine families, no PRIVATE) and
  `_assert_full_coverage` (`factor_service.py:414-441`, called at `:650` in the pre-create block)
  refuses when any pinned atom has no loading row, at every month-end and every daily date. Executed
  (round 5, `R5F_FAM_EXIT=0`): `LOADING_FACTOR_FAMILIES ('CURRENCY', 'MARKET', 'RATES', 'CREDIT_SPREAD',
  'COMMODITY', 'STYLE', 'INDUSTRY', 'COUNTRY', 'MACRO') len 9 | MARKET in True | CREDIT_SPREAD in True
  | PRIVATE in False` and `MKT_GLOBAL_EQ family ['MARKET'] | CREDIT_HY family ['CREDIT_SPREAD']`.
  Second, the loading must be NON-ZERO, which round 4's zero-weight `FX_USD` row was not: a zero-weight
  pin emits no exposure row (`factor_service.py:455-456` "zero weights emit no row"; `:470-471` `if
  pin.weight == 0: continue`; and the `continue` at `:504` after the pin loop skips the indicator
  fallback), and the unified builder keys everything off those rows (`snapshot/service.py:3511`
  `exposure_rows = _list_factor_exposure_rows(`, `:3550` `instrument_ids = sorted({str(r.instrument_id)
  for r in exposure_rows})`, `:3559` `ProxyMapping.private_instrument_id.in_(instrument_ids)`). So a
  young fund with only a zero-weight row was absent from `instrument_ids`, its PRIVATE membership was
  never selected into `manual_rows`, it sat in neither `private_member_instruments` (`:3586`) nor
  `by_instrument` (`:3609-3614`), and its MV was 0 (`var_service.py:1245-1250` builds
  `mv_by_instrument` from the pinned exposure rows alone; `:518-555` `_build_p_vector` refuses a
  membership with no pinned MV). That is the invisibility GOV-1 was folded to prevent, re-created by
  the round-4 fix; Part 2.5's coverage control would have read 8 != 12. Under the non-zero loading the
  young fund emits one exposure row, enters `instrument_ids`, its membership is selected, and it enters
  leg 2 at MV_i = 1.0 × NAV (the registered p vector, `risk/bootstrap.py:2863` "p_s = SUM over
  MANUAL-members i of segment s of MV_i (the same pinned factor-exposure MV the residual leg uses)");
  leg 1 carries its exposure on the sleeve index, which is the registered repartition (`:2852-2857`
  removes a member's RESIDUAL leg, not its factor leg), not a double count. The weight is 1.0 and not
  small because the loading weight is also the fraction of NAV that enters Omega_pp; at 1.0 a young
  fund sits on the same footing as a mature fund whose promoted weights sum near 1. Under DS-B1b-3 = B
  the `FACTOR_FAMILY_PRIVATE` filter keeps the public row out of `manual_rows`, and so out of the p vector,
  which sees only the filtered pinned rows (DS-B1b-3 (B), V5-01, V6-03), while
  the PRIVATE membership carries the fund into leg 2, so GOV-1's objection does not return. The first
  draft's shape (a MANUAL loading on the sleeve's market factor with NO segment membership) was
  BLOCKING under DS-B1b-3 = B (GOV-1): the unified builder has no coverage guard — after the MANUAL
  query (`snapshot/service.py:3554-3568`) and the REGRESSION query (`:3594-3612`) it goes straight to
  `_persist_snapshot` (`:3661`) with nothing asserting every exposure instrument landed in one leg —
  so a young fund with a public MANUAL row and no REGRESSION row would carry NO leg-2 and NO leg-3
  term while its MV entered the factor leg, its non-public variance silently zero, and
  `residual_variance == 0` would still hold. Segment membership puts each young fund in leg 2 through
  the segment's Omega_pp; the non-zero loading makes it an exposure instrument the builder can see at
  all. The fold under DS-B1b-3 = B also adds a refusal in `build_var_unified_snapshot` when an exposure
  instrument of asset class PRIVATE_EQUITY or PRIVATE_CREDIT has neither a PRIVATE-family MANUAL
  membership nor a REGRESSION mapping, with its own negative control (Part 3.20). This shape rests on
  DS-B1b-3 (B), ratified 2026-09-18; the commitment-only-pair shape of Part 0.5 is a branch not taken (VF1-04).
- **Order:** all of the above runs in a new `_run_private_chain` step AFTER `_register_models` and
  BEFORE `_run_account_boundaries` (Part 0.6). **Proof:** the suite asserts zero FAILED runs; a mutant
  that reorders the private chain after the month-end chain makes the NL-PMF root loadings run FAIL
  with `unmapped-atom` and is KILLED (Part 5); the suite asserts each mature fund has exactly one open
  REGRESSION mapping per candidate factor citing one COMPLETED PROXY_WEIGHT_ESTIMATE run, and that
  `GET /perf/desmoothed-returns/latest?portfolio_id=&instrument_id=` (`api/perf.py:1134`) returns rows
  for every mature pair.

### 4. Commitments, calls, distributions and one pacing projection per pair

Per underlying fund, under the ACCOUNT leaf that holds it (DS-B1b-4; `snapshot/service.py:2594-2595`
needs commitment and mark on one portfolio id): one commitment in USD (`private_capital/models.py:70-92`;
event currency must equal it, `capital_flow_service.py:148-151`), vintage on a quarter end, mostly 30 June (Part 0.15),
DRAWDOWN calls and INCOME / RETURN_OF_CAPITAL / CAPITAL_GAIN distributions from the fixed vocabulary
(`models.py:56-57`), every event dated on or after the vintage and on or before 2026-06-30 (the code
does not check ordering, `capital_flow_service.py:297`; the seed does), Σcalls never above committed
(`pacing/service.py:182-183`), at most one or two `is_recallable=True` rows. Every funded pair has its
2026-06-30 NAV mark (outcome 2; `pacing/service.py:191-192` refuses a funded pair without one). Two
pacing labels because the five parameters are the version identity (`pacing/bootstrap.py:308-310`):
`v1-pe` (rc **0.25, 0.30, 0.25, 0.15, 0.10, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 1.0**, twelve entries; L 12;
bow 2.5; growth 0.12; Y 0) and `v1-credit` (rc **0.5, 0.5, 0.3, 0.1, 0.05, 0.05, 0.05, 1.0**, eight
entries; L 8; bow 1.5; growth 0.08; Y 0.08). **Each schedule is exactly as long as its fund life**,
because the kernel repeats the LAST rate from t = len(rc_schedule) onward, not from t = L
(`pacing_kernel.py:123-126` `idx = min(age, len(rc_schedule)) - 1`; the kernel refuses a schedule
longer than L, `:192-193`), so a short schedule ending in 1.0 calls 100 % of the remaining unfunded at
every age past its length: the second fold's PE shape (five entries, L 12) made every mature PE fund's
first projected row call everything (S-01, S-02). A short schedule ending below 1.0 leaves a remainder
never called (the first draft's PE shape ending 0.05: `terminal unfunded 7737809.375000 at t 12`,
77.4 % of the remaining unfunded; FEAS-4, N-06). The tail rate 0.05 sits mid-life and 1.0 only at t = L,
so the final period calls the remainder and every earlier row is a partial call. The schedule length
is part of the version identity (`pacing/bootstrap.py:6` "The FIVE declared parameters ARE the version
identity"; `:308-310` a same-label re-register with a changed parameter is a conflict). Executed
(round 3, reproduced line for line at rounds 4 and 5, `project_commitment` on every roster vintage at as-of 2026-06-30 with unfunded 10,000,000
and NAV 20,000,000, `KERNEL_EXIT=0`):
`PE 2019-06-30 age 7 rows 5 t0 8 window 2026-06-30..2027-06-30 call 500000.000000 unfunded_end 9500000.000000 terminal_unfunded 0.000000 at t 12` /
`PE 2019-12-31 age 6 rows 6 t0 7 window 2025-12-31..2026-12-31 call 500000.000000 unfunded_end 9500000.000000` /
`PE 2020-06-30 age 6 ... call 500000.000000 unfunded_end 9500000.000000` /
`PE 2021-06-30 age 5 rows 7 t0 6 ... call 500000.000000 unfunded_end 9500000.000000` /
`PE 2021-12-31 age 4 rows 8 t0 5 window 2025-12-31..2026-12-31 call 1000000.000000 unfunded_end 9000000.000000` /
`DL 2020-06-30 age 6 rows 2 t0 7 ... call 500000.000000 unfunded_end 9500000.000000 terminal_unfunded 0.000000 at t 8` /
`DL 2021-06-30 age 5 rows 3 t0 6 ... call 500000.000000 unfunded_end 9500000.000000` /
`DL 2021-12-31 age 4 rows 4 t0 5 window 2025-12-31..2026-12-31 call 500000.000000 unfunded_end 9500000.000000` /
`PE 2023-06-30 age 3 rows 9 t0 4 ... call 1500000.000000 unfunded_end 8500000.000000` /
`PE 2024-06-30 age 2 rows 10 t0 3 ... call 2500000.000000 unfunded_end 7500000.000000` /
`DL 2024-12-31 age 1 rows 7 t0 2 window 2025-12-31..2026-12-31 call 5000000.000000 unfunded_end 5000000.000000` /
`DL 2025-06-30 age 1 rows 7 t0 2 ... call 5000000.000000 unfunded_end 5000000.000000`; every quoted FIRST row's
identity is 10,000,000.000000 (call + unfunded_end = that row's OPENING unfunded, which decays row by
row: PE 2019-06-30's five rows give `['10000000.000000', '9500000.000000', '9025000.000000',
'8573750.000000', '8145062.500000']`, R3-06) and every pair's `terminal_unfunded 0.000000` at t = L
(Executed, round 4, all twelve pairs, `r4_kernel_EXIT=0`, and again at round 5, `R5F_KERNEL_EXIT=0`, every line identical; `min first-row unfunded_end 5000000.000000`). No roster pair is degenerate, and not only at that anchor: the
first row's rate is below 1.0 for every roster pair (1.0 sits only at t = L, `pacing_kernel.py:123-125`; the
oldest PE opens at t 8 of 12, the oldest DL at t 7 of 8), and `call = _q(rc * unfunded)`, `unfunded = _q(unfunded - call)`
(`:152,162`) give `unfunded_end = (1 - rc) x unfunded > 0` for any positive unfunded. The 10,000,000 anchor is an
illustration, not the seeded size; the build-time guard is the `rows[0].unfunded_end > 0` assertion (V5-06). One `run_pacing_projection` per pair, asserted COMPLETED (the ceilings at
`pacing_kernel.py:56` and `pacing/service.py:224` are unreachable at book scale). Sizing per the
pacing lane, checked against the reserve MARKED at 2026-06-30, 45,678,907.40 USD (start-price face
45,598,600, `book.py:1118-1162`; Part 0.21): about 235M committed, 175M NAV, 75M unfunded, so the
reserve covers about 61 percent of unfunded (45.679 / 75); the final figures are DS-B1b-4's and are
quoted in the record. **Distributions are sized, not left implicit** (CRO-R8): a seven-year-old PE fund
with no distributions is a failed programme. Aggregate distributions about 60-70M, so programme TVPI
lands near 1.45-1.55 and DPI near 0.40; per-fund DPI by age (age 7 about 0.7-0.9, age 5 about 0.3-0.5,
age 4 about 0.1-0.2, young funds 0); cumulative called by age (age 3 about 0.60-0.70, age 5 about 0.85,
age 7 about 0.90-0.95). The record quotes committed / paid-in / distributed / NAV / unfunded / DPI /
TVPI as a seven-column table per fund, and the suite asserts the oldest PE fund's DPI is above 0.5.
Vintages: eight on 30 June and FOUR on 31 December (PE 2019-12, PE 2021-12, DL 2021-12, DL 2024-12;
DS-B1b-4's roster, one number carried everywhere, S-05) so the pacing screen shows two call dates
rather than one cliff (CRO-R16); the record says a 31-December vintage's first projected window opened
six months before the as-of by the engine's anniversary convention, not by a data error (Executed,
round 3: `PE 2019-12-31 age 6 rows 6 t0 7 window 2025-12-31..2026-12-31`).
No teaching reversal (sub-question, flagged: it adds a row a CRO asks about and no line needs it).
**Proof:** the suite asserts one COMPLETED pacing run per pair and that `GET /pacing/projections/latest`
returns a first row whose window starts 2026-06-30; a hand golden: one fund's unfunded = committed −
Σcalls + Σrecallable, equal to `rows[0].projected_call + rows[0].unfunded_end`
(`pacing_kernel.py:13,162`), taken on a fund whose first projected row has a NON-ZERO `unfunded_end`
(FEAS-5, S-01), so the golden never collapses to x + 0 = x. Under the folded schedules above no roster
pair is degenerate (Executed, round 3: the smallest first-row `unfunded_end` is 5,000,000 on the two
age-1 DL pairs; the oldest PE fund's is `call 500000.000000 unfunded_end 9500000.000000 identity
10000000.000000`). The degenerate case exists only under a schedule shorter than L ending in 1.0, which
this remit no longer uses; the suite asserts `rows[0].unfunded_end > 0` on the golden's pair so a
schedule change cannot re-open it silently. Part 2.10 (c) names the fund. The fund-level unfunded shown by CRO-1 is a client-side sum across pairs,
unpersisted; whether CTRL-039 treats a sum across PAIRS (one run each) as an unbound sum is CRO-1's
question (Part 6).

### 5. Total and unified VaR, with the flavour-by-fund matrix stated

| Flavour | NL-GMA | NL-EFI | NL-PMF |
|---|---|---|---|
| VAR_PARAMETRIC 99/1d, ES_PARAMETRIC 97.5 | 13 month-ends + 59 daily | same | same |
| VAR_HISTORICAL 95/60 | 13 month-ends (BOOK-1a) | same | same |
| VAR_PARAMETRIC_TOTAL | 13 month-ends (asserted == plain; Part 0.8) | same | 13 month-ends |
| VAR_PARAMETRIC_UNIFIED | refuses by engine | refuses by engine | 13 month-ends + 59 daily |

Total and unified run through the same exposure and covariance runs the plain VaR consumed: the
`exposure_run_id` / `covariance_run_id` are threaded into both builders at `var_service.py:840-846`
(`build_snapshot_fn = build_var_total_snapshot if is_total else build_var_snapshot` at `:840`, the two
run ids at `:845-846`) and into
the unified path at `:1206-1215` (C-06; `:686-691` is only the 2x2 dispatch table); unified adds the
tenant-wide private covariance run (`var_service.py:1201-1216`). Each builds its own snapshot behind
its own predicate (`var_service.py:802-812,1194`), so NL-PMF gains two extra VAR_INPUT snapshots per
month-end and one per daily date, 13 × 2 + 59 = 85 in all (N-04; the census's "+ 85"). The unified
row's `residual_variance` is exactly 0 when every proxied instrument is a segment member
(`snapshot/service.py:3612-3613`; `test_var_unified_e2e.py:490-492`; C-02), but that value cannot tell
"all repartitioned" from "some invisible" (GOV-1), so the proof is a POSITIVE coverage control: the
suite asserts `set(private_member_instruments) | set(by_instrument) == set(private instrument ids)` on
the 2026-06-30 unified snapshot, naming the instruments each leg covers. MV_i is the SUM of the instrument's
pinned factor exposures (`var_service.py:1245-1250`; `factor_service.py:481`), so a fund whose promoted
weights sum to 0.9 enters at 0.9 × NAV and a young fund enters at 1.0 × NAV through its single
sleeve-proxy loading (Part 2.3, R4V-01); the golden uses the blend-weighted exposure and the record says
so for CRO-1's screen. The coverage control's right-hand set is the seed's roster of twelve private
instrument ids (`SeedSummary`), never a set derived from the snapshot's own exposure rows, so a fund
missing from `instrument_ids` cannot vanish from both sides at once (R4V-01). The staleness policy is
548 days against a measured 456 at 2026-06-30 (Part 0.4; DS-B1b-1), and it binds on
VAR_PARAMETRIC_TOTAL only: the unified row cites no estimate while every private instrument is a
segment member (R4V-02). **The blocker:** unified at the root needs DS-B1b-3 resolved first. **Proof:** the suite
asserts 13 + 72 COMPLETED runs for NL-PMF by metric_type and 13 total runs each on NL-GMA and NL-EFI
with `total == plain` at every month-end, none FAILED; `estimate_age_days` equals 456 on NL-PMF's
2026-06-30 VAR_PARAMETRIC_TOTAL row (the sixteen REGRESSION rows of the eight mature funds are pinned there, one
cited estimation run per fund, `snapshot/service.py:3378-3395,3398-3409` in the TOTAL builder; V5-02, V6-02) and is None on the 2026-06-30 unified row (R4V-02); the hand golden for NL-PMF's unified VaR at 2026-06-30 works the
three legs with the blend-weighted p vector; every new read over `covariance_result` carries the
`run_type` filter (`covariance_service.py:432-441`), and the census counts COVARIANCE and
COVARIANCE_PRIVATE separately (the BOOK-1a CI red, `book-1a-state`).

### 6. Limits a CRO would set, two live breaches, the strictly-between cases named

Ten limits, all ABOVE (ceilings; `limit/service.py:205`, `events.py:61-63`), all scoped to
`summary.fund_ids[code]`, created by `northlight-rm` (`limit.manage`, `seed.py:204-208`) and approved
by `northlight-cro` (`limit.approve`, `:190-194`) with `approval_ref="minutes://RISK-COMMITTEE-2026-06"`,
the only pair the roster allows (Executed: rm-then-rm raised `LimitSodError`; rm-then-cro went ACTIVE;
pm approving through the service also went ACTIVE, so the roster is discipline, not enforcement:
`approve_limit` checks `_require_human`, `approval_ref`, DRAFT status and the maker set only,
`service.py:1033-1048`, with no `limit.approve` role check — that gate lives at the HTTP boundary,
GOV-3). The first draft's grid had three defects a CRO would see on the first screen (CRO-R3, R4, R5),
re-derived here over the book at 2026-06-30 (Executed over `book.generate_paths()`: `NL-GMA issuer UST
0.249188 / sector O 0.249188 / country US 0.822013 / CR5 issuer 0.549503`; `NL-EFI sector O 0.647615 /
issuer BUND 0.254149 / country DE 0.348986, IT 0.158438`; `NL-PMF issuer UST 0.864270`): (i) NL-EFI's
sector breach was on ISIC section O, "Public administration and defence" (`book.py:343`), which every
euro sovereign carries (`book.py:325-329`: BUND, OAT, BTP, BONOS, DSL; S-09), so the headline breach read "over the limit because it holds
65 % government bonds", a cap no CRO sets on a euro-aggregate mandate; (ii) NL-GMA's issuer and sector
rows both reported 0.249188 because the binding issuer is the United States Treasury (`book.py:324`),
the only member of section O, so the flagship near-limit story was a sovereign every framework carves
out and two rows showed one number; (iii) two TE rows sat at exactly 0 (Part 0.11). Thresholds per
DS-B1b-5 (Design B, recommended) against the executed 2026-06-30 values:

| Limit | Kind | Threshold | Observed | Utilisation | State |
|---|---|---|---|---|---|
| NL-GMA VaR 99/1d | HARD | 1,500,000 USD | 1,734,274.488757 | 115.6 % | **BREACH** |
| NL-GMA tracking error, daily (0.0010 ≈ 1.6 % p.a.) | SOFT | 0.0010 | 0.000286895819 | 28.7 % | strictly between |
| NL-GMA top-five issuer share (`CR_5_ISSUER`) | HARD | 0.65 | 0.549503 | **84.5 %** | strictly between; **the ASSERTED case**, above J-CRO-3's 80 % line |
| NL-GMA largest single issuer incl. sovereign (`MAX_SHARE_ISSUER`) | SOFT | 0.35 | 0.249188 | 71.2 % | strictly between |
| NL-GMA manufacturing share (`SHARE` on `bucket_code='C'`, ISIC section C, `scheme_family='ISIC'`, dimension `SECTOR_INDUSTRY`; `NL-GMA-MFG`) | SOFT | 0.20 | 0.147878 | 73.9 % | strictly between; the sector limit the ratified enumeration names (R3-03) |
| NL-EFI VaR 99/1d | HARD | 600,000 EUR | 464,184.575474 | 77.4 % | strictly between |
| NL-EFI Italy share (`SHARE` on `bucket_code='IT'`, country of risk) | SOFT | 0.15 | 0.158438 | 105.6 % | **BREACH** |
| NL-EFI max issuer share | HARD | 0.35 | 0.254149 | 72.6 % | strictly between |
| NL-PMF unified VaR (`VAR_PARAMETRIC_UNIFIED`; DS-B1b-3 (B) ratified) | HARD | derived at seed time, then frozen | BOOK-1b's number | strictly between | quoted in the record |
| NL-PMF largest single issuer incl. the Treasury reserve (`MAX_SHARE_ISSUER`) | HARD | 0.25 (a round committee number) | about 0.18 | about 72 % | strictly between; named as the reserve |

Eight rows are strictly between zero and threshold (GOV-14; seven at round 3, eight from round 4, R3-03); `NL-GMA-CR5` is the one the seed ASSERTS
and the mutants target, and it crosses J-CRO-3's 80 percent line (`personas_and_user_journeys.md:93`).
The Italy row is a detail-row `SHARE` limit bound to a bucket (`limit/models.py:74-79`, the `concentration_shape`
constraint: its CONCENTRATION branch at `:75-76` constrains only `dimension_kind` and
`denominator_basis` and leaves `bucket_code` and `scheme_family` unconstrained, which is what admits
the detail-row shape; `:77-79` is the non-concentration branch, whose `:78` forbids `bucket_code`, `issuer_id` and `scheme_family`, R4V-05, V5-05); `MAX_SHARE_COUNTRY_OF_RISK` would bind on Germany at 0.349, so it is not used.
If the bucket selector cannot express "Italy" in the build, the fallback is `MAX_SHARE_SECTOR_INDUSTRY`
on a CREDIT section, never on O (CRO-R3). **The sector limit** (R3-03): the round-3 grid had no sector
limit at all while the ratified text names "sector and issuer concentration"
(`product_rebaseline_2026-09-17.md:380-381`; roadmap `:357`), so one is added rather than declared a
departure. It sits on NL-GMA's ISIC section C, Manufacturing, the largest corporate section that holds no
cash: section K (0.212638) carries the custodian cash line (`NLUSD-CASH`, issuer Harborside Trust
Company, 0.118833 of the fund, which is 56 % of section K; Executed, round 5, `R5F_CONC_EXIT=0`:
`NLUSD-CASH issuer Harborside Trust Company | share of FUND 0.118833 | share of section K 0.558849 =
55.9 %`, R4V-03), so a financials cap would read as a cap on the fund's own cash, and
`MAX_SHARE_SECTOR_INDUSTRY` would bind on O (0.249188, the Treasury). Executed over
`book.generate_paths()` at 2026-06-30 (round 4, `GMA_K_EXIT=0`): `NL-GMA sector C share 0.147878 ex-cash
0.147878` over five members (CSDA, NSAR, RHWK, HLVP, CSDA-29); `sector K share 0.212638 ex-cash 0.093806`;
`C/0.20 = 73.9 %`. The bucket vocabulary is `CONCENTRATION_DIMENSION_KINDS` (`concentration/models.py:37-41`:
ISSUER, SECTOR_INDUSTRY, COUNTRY_OF_RISK) and `SCHEME_FAMILY_ISIC` (`classification/models.py:129`); the
same `SHARE`-on-bucket shape as the Italy row, so if the selector cannot express a section in the build
the two rows fall back together. NL-PMF's issuer limit is a round number, not derived from the
observed value (CRO-R9): with the private NAV seeded the Treasury bills (39.48M) are about 17.9 % of a
220.7M fund and remain the largest issuer, because the reserve is fixed by BOOK-1a and no plausible GP
holding exceeds 39M; so the limit is NAMED as including the reserve, the record says the maximum-share
DETAIL row is UST, and the GP-level concentration is read from the concentration view, not from a limit.
Tracking error is a DAILY fraction, not annualised (`active_risk_service.py:13`; no `252` in that
file); the unit translation travels in the limit's own `name`, which is free text (`_UPDATABLE` at
`service.py:176`; CRO-R15), so J-CRO-1 shows it without a footnote. The sector and country limits (`NL-GMA-MFG`, `NL-EFI-ITALY`) carry
`denominator_basis='INVESTED_LONG'` (`concentration/models.py:52-53`, the only basis; the share is
`share_invested_long` on the DETAIL row, `limit/service.py:163-170`); `CR_5_ISSUER` and `MAX_SHARE_ISSUER` are in the concentration
vocabulary (`concentration/models.py:59-65`), so no issuer id is resolved (ids differ per seed, Part
3.12). The executed probe used the first draft's grid and thresholds (0.0050 / 0.0100 / 750,000) and
produced two breaches and six in appetite; the table's numbers are re-executed in the build. **The seed's
per-limit guard asserts the RESOLUTION, not the return value** (FR-03): `evaluate_limit` returns None on
three different outcomes — a non-ACTIVE limit (`limit/service.py:585`), an unresolved or REFUSED resolution
(`:593`, "Covers BOTH 'no matching COMPLETED run' and a REFUSAL") and within appetite (`:598`) — so
asserting None on the eight in-appetite rows would pass on a cold metric. For each of the eight the seed
asserts `_resolve_latest(session, limit).is_resolved is True` (`:236-237`: `run_id`, `observed` set and
`refusal` None) and `observed < threshold`, the shape `NL-GMA-CR5` already carries; for the two breach rows
it asserts `evaluate_limit` returned a `Breach`; and it REFUSES otherwise, so a moved number cannot stop
demonstrating silently. The NL-GMA tracking-error limit IS resolvable at all three instants: `run_active_risk`
is called inside `_run_month_end_chain` (`seed.py:1026-1039`), one ACTIVE_RISK run per fund per month-end
(BOOK-1a: 39 runs, `w20_book1a_slice_record.md:94`), so at each evaluation that month-end's run exists;
the verifier's claim that `_run_return_chains` creates them was wrong at its citation (that step creates
PORTFOLIO_RETURN, BENCHMARK_RELATIVE, ROLLING_RISK and SHARPE, `seed.py:1116-1179`).

**Evaluation runs at the last three month-ends, not once** (CRO-R6): inside `_run_month_end_chain`, after
the 2026-04-30, 2026-05-29 and 2026-06-30 iterations' runs (VaR, historical VaR, active risk, concentration,
liquidity; `seed.py:1015-1104`), with injected `now` = 2026-04-30T22:00Z, 2026-05-29T22:00Z and
2026-06-30T22:00Z; the daily chain has already run by then (Part 0.6, FR-01)
(all inside the time-bomb fence, Part 0.17; `detected_at` is the injected instant, `service.py:613`). A
breach is one row per (limit, run) (`models.py:177` `uq_breach_limit_run`) and the resolver takes the
latest COMPLETED run at evaluation time (`calc/reads.py:101-103`), so this mints a genuine breach
series: each open breach has a first-detected date and an age on J-CRO-1, and the record quotes the
first-detected date per limit. Both limits stay DETECTED (DS-B1b-8, re-opened with option (D)): no
owner, no due date, no clock. The deployed tick re-evaluates every 300 s (`supervisor.py:46`) as an
idempotent no-op and its phase 4 writes `breach_notification` rows to the CRO and RM for the
BREACH.DETECT events (`notification/events.py:68`); expected, named. **Proof:** the suite asserts
exactly TWO limits have open breaches (`list_breaches(open_only=True)` grouped by limit, naming
`NL-GMA-VAR` and `NL-EFI-ITALY`), with the earliest `detected_at` per limit asserted; `limit_health`
returns ten rows, two BREACHED with `latest_breach_id` set, eight IN_APPETITE, none REFUSED; and for
`NL-GMA-CR5` the suite asserts `observed > 0` and `observed < threshold` SEPARATELY, never dividing by
the threshold (FEAS-6). "Change since the last close" (J-CRO-1) is not a stored evaluation: it is the
family latest read at two dates against the threshold, which the daily series makes possible; CRO-1
decides the data path (Part 6).

### 7. The daily last quarter, as a separate date set

`book.BOUNDARIES` stays 56; the 50-60 fence (`test_demo_tenant_book.py:38`) holds. New:
`book.DAILY_BOUNDARIES`, the 49 Q2 business days not already boundaries, and `book.DAILY_CHAIN_DATES`,
the 59 Q2 business days that are not month-ends (DS-B1b-7 as recommended). The mark and FX loops iterate
the union (105 dates) at THREE sites, not two: the generator's `if d in BOUNDARIES` guards at
`book.py:1450` (marks) and `:1415` (FX USD legs) widen to the union, and the FX-cross comprehension at
`:1418-1421` (`for d in BOUNDARIES`, a direct iteration with no guard) is re-pointed at the union
constant. Without the third site the GBP/EUR series stays at 56 dates and the seed's bare lookup
`rate=series[on]` (`seed.py:613`) raises `KeyError` on the first new date (Executed, Part 0.21: `cross
fx KeyError on first new date: 2026-04-01`), failing the whole deploy-path seed under refuse-not-skip
(FEAS-1); the benchmark cut (`book.py:1490`) and the return-account exposure loop (`seed.py:924`) keep
`BOUNDARIES`, so no BOOK-1a stored value moves. **Order** (FR-01): `_run_daily_chain` runs AFTER
`_run_account_boundaries` and BEFORE `_run_month_end_chain`, so every daily run is older by wall clock
than the month-end run the three limit evaluations resolve (Part 0.6; `calc/reads.py:101-103`). The daily chain per date: one shared full-set covariance
(`seed.py:953-964` shares `cov_all` today; covariance has no portfolio input, BOOK-1a remit Part 0.3) and,
per fund, one root exposure, one loadings factor exposure, VAR_PARAMETRIC and ES_PARAMETRIC; for NL-PMF
also the unified run. The three Q2 month-ends are NOT re-run (Part 0.13). **Proof:** the suite asserts 59
daily VAR_PARAMETRIC rows per fund in Q2 plus the three month-end rows, 62 distinct `window_end` dates;
the three goldens unchanged; `test_demo_tenant_book.py:91` (`marks per instrument == len(BOUNDARIES)`)
amended to the union with the reason; a mutant dropping one Q2 date is KILLED; a mutant leaving the
cross comprehension on `BOUNDARIES` fails the seed with a NAMED refusal (the seed checks every FX
series spans the union before the capture loop), not a `KeyError`.

### 8. The run census, stated as arithmetic

| Family | Runs | Arithmetic |
|---|---|---|
| BOOK-1a, unchanged | 597 | slice record §3 |
| Covariance (full set), daily | 59 | 1 × 59 daily-chain dates |
| Exposure aggregate at each fund root, daily | 177 | 3 × 59 |
| Factor exposure (loadings) at each root, daily | 177 | 3 × 59 |
| VAR_PARAMETRIC, daily | 177 | 3 × 59 |
| ES_PARAMETRIC, daily | 177 | 3 × 59 |
| VAR_PARAMETRIC_TOTAL, all three funds | 39 | 3 × 13 month-ends (GOV-11) |
| VAR_PARAMETRIC_UNIFIED, NL-PMF | 72 | 13 + 59 |
| Desmoothed return | 8 | one per mature fund (DS-B1b-4 at twelve funds, eight mature) |
| Proxy-weight estimate | 8 | one per mature fund |
| Pure-private factor return | 2 | one per segment |
| Private covariance (COVARIANCE_PRIVATE) | 1 | tenant-wide |
| Pacing projection | 12 | one per pair |
| **New** | **909** | 767 + 111 + 31 |
| **Total** | **1,506** | 597 + 909 |

Not runs, stated so Part 2.5's "+ 85" resolves here: VAR_INPUT snapshots on NL-PMF for the total and
unified flavours, **85** = 13 × 2 (total and unified at each month-end) + 59 (unified on each daily
date). They are snapshots, so neither the run total nor the capture total moves (S-06).

The roadmap's literal "one covariance ... per boundary per metric per fund" would be 2 × 3 × 62 = 372
identical covariance runs; the engine needs 59 and the count is restated in the engine's terms.
Roadmap Part 2.22 row 2 is AMENDED to say so ("sixty-two business days, of which fifty-nine are not
month-ends; one shared full-set covariance per daily date, not one per metric per fund; measured"), because
the roadmap is the document the next gate opens (GOV-10). The planning commit `d676fc4` did NOT carry that
amendment (GOV-R-01, CC-1: `awk 'NR==357'` still read "about sixty-three"); it lands at the ratification-diff
fold, together with "per MATURE private fund" and "ten limits, two breaches, eight strictly between" in the
same row body (CC-5). New captures, about
**5,100** (the list sums to 5,106): public marks 55 × 49 = 2,695; FX 3 × 49 = 147 (the cross series
included, FEAS-1); private marks 12 × 105 = 1,260; appraisal marks 8 × 12 = 96; two new public factors
2 × 313 daily returns = 626 (`RETURN_DAYS` is 313 days, 2025-04-01..2026-06-30; DS-B1b-15); minted
quarterly factor returns 3 factors (`MKT_GLOBAL_EQ`, `CREDIT_HY_TR`, `RATES_UST_TR`) × 10 dates = 30;
REGRESSION mappings 8 × 2 = 16; PRIVATE factors 2; memberships 8 mature + 4 young = 12;
sleeve-proxy MANUAL loadings on the four young funds 4 (R3-01; non-zero from round 5, R4V-01; and NO FX row on any private instrument — the fence-22 `_seed_loadings` skip; without it, +12, V7-03); commitments 12; calls and distributions about
110; model versions 8; limits 10 (R3-03); breach rows up to 6 (two limits, up to three evaluations
each); instruments, issuers, positions and classification for twelve funds about 72. Total
6,105 + 5,106 = 11,211, about **11,200** captures.
Counts are MEASURED on a fresh battery at close, never derived (sweep item 6). DS-B1b-4 (b) is ratified
at twelve funds, eight mature, as holdings; the eight-fund and commitment-only scale-downs the draft
carried here were not taken (FR-04).

### 9. Projected seed time, and which path the ceiling binds

Measured BOOK-1a: 86.7 s in-stack via `deploy.sh --with-demo` (`purpose_mismatch_remediation_plan.md:51`),
295.7 s from the host (`w20_book1a_slice_record.md:101-103`), 33 s on SQLite (`:60`, `:103`; the first
draft's 32.1 s had no source and contradicted the record, N-02). The CI step's time has no committed
measurement: the only number is the stale comment at `ci.yml:779-780` ("~6 minutes measured locally:
636 runs"), so the CI projection below is bracketed, not stated (N-02).
Runs are about 70 percent of seed time on the only per-stage split (SQLite), and each month-end chain
ran slower than the last (1.0 s → 1.9 s), so a linear projection is a floor. At about 0.10 s per run and
0.004 s per capture in-stack, with 909 new runs and 5,106 new captures: 87 + 91 + 20 ≈ **198 s** (about
three minutes). From the host at 0.35 and 0.015: 296 + 318 + 77 ≈ **691 s**, over ten minutes. CI:
between 87 × 1,506 / 597 ≈ 219 s and 360 × 1,506 / 636 ≈ 852 s, measured from the actual run at the PR
head and quoted in the record. The two brackets use different denominators: the 86.7 s was measured
over BOOK-1a's 597 runs in-stack, and the ~360 s at `ci.yml:779-780` is a stale LOCAL measurement
attached to the BOOK-1a step (verbatim: `# The suite seeds the tenant end to end through the real
orchestrator (~6 minutes measured` / `# locally: 636 runs, ~5,800 audited captures)`), quoting 636 runs
and ~5,800 captures, neither matching BOOK-1a's measured 597 runs and 6,105 captures; it is not a CI
timing and not the old campaign's (S-03). The upper bracket is kept, labelled as a stale local figure. Neither
CI nor `deploy.sh` step 9 sets a timeout (`ci.yml` has no `timeout-minutes`, `grep -c` → 0;
`deploy.sh:210-211`, under `set -euo pipefail` at `:29`; C-12). **The
ten-minute ceiling (DS-B1a-9) binds the in-stack path** (DS-B1b-9a); the host figure is quoted for
information. The stale CI comment at `ci.yml:779-780` ("~6 minutes ... 636 runs") is refreshed in
this slice.

### 10. Goldens (MD-H1): the three kept, three added

Kept verbatim: `GOLDEN_GMA_MARKET_VALUE_USD = 155681069.672680`, `GOLDEN_EFI_LARGEST_SECTOR = ('O',
0.647615)`, `GOLDEN_EFI_VAR_PARAMETRIC_EUR = 464184.575474` (`test_demo_tenant_book1a_pg.py:55-57`). They
read marks and FX at 2026-06-30 and the 30 factor returns 2026-05-18..2026-06-30, all unchanged under
the extended date set (Executed). Added, each derived by hand in the record: (a) one mature PE fund's
desmoothed stdev and observed stdev from its 12 generated marks under the declared alpha; (b) NL-PMF's
unified VaR at 2026-06-30, the three legs worked with the blend-weighted p vector; (c) one fund's
unfunded commitment from its commitment and flow rows, taken on the oldest PE fund (vintage 2019-06-30,
age 7 at 2026-06-30), whose first projected row is a 5 % call with a non-zero `unfunded_end` under the
folded `v1-pe` schedule (Executed, round 5, re-run under the folded schedules: `PE 2019-06-30 age 7 rows 5 t0 8 window
2026-06-30..2027-06-30 call 500000.000000 unfunded_end 9500000.000000 first_identity 10000000.000000
terminal_unfunded 0.000000 at t 12 identities ['10000000.000000', '9500000.000000', '9025000.000000',
'8573750.000000', '8145062.500000']` on a 10,000,000 unfunded / 20,000,000 NAV anchor,
`R5F_KERNEL_EXIT=0`, identical to round 4's `r4_kernel_EXIT=0` run;
FEAS-5, S-01, R3-06); the suite also asserts that row's `unfunded_end > 0`. The
suite pins all six.

### 11. The line-to-data map (roadmap row 2, 2026-09-18 addition)

| Line | Needs from BOOK-1b | Served by |
|---|---|---|
| J-CRO-1 funds ranked by headroom, change since last close | limits in force, two breaches with first-detected dates, eight strictly-between | outcome 6; `GET /limits`, `GET /limits/health`, `GET /breaches?open=true`, family latest reads at two dates |
| J-CRO-5 private sleeve: reported vs desmoothed; unfunded and next call | appraisal history, chain, commitments, pacing — under DS-B1b-4 (b) the young funds show "proxied until history exists" in place of a desmoothed volatility, a departure from the line's "for each private fund" the owner is asked to ratify (GOV-2) | outcomes 2, 3, 4; `GET /perf/desmoothed-returns/latest`, `GET /pacing/projections/latest` per pair |
| J-CRO-7 VaR trend over the last quarter | daily covariance and VaR per boundary per fund | outcome 7; `GET /risk/vars/latest` with `metric_type`, and the run-keyed reads over the 62 Q2 dates |
| J-CRO-7, the ROLLING-DRAWDOWN half ("the VaR series over the last quarter **and rolling drawdown**, as charts", `personas_and_user_journeys.md:97`; GOV-R-07) | nothing new from BOOK-1b. What exists: ROLLING_RISK v2 (`perf/rolling_service.py`, ENT-064) emits MAX_DRAWDOWN on a calendar-month grid, one row per (metric, window, period_start), over the PORTFOLIO_RETURN series; BOOK-1a runs it once per fund at its return account over the year (`seed.py:1147-1158`, 3 runs) with `book.ROLLING_WINDOWS = (12,)` (`book.py:1364`) and twelve months of returns, so the kernel emits ONE complete 12-month window per fund (`rolling_kernel.py:404` `for end in range(window_months - 1, len(months))` → one) — a single MDD point, not a series. The registered domain is `(12, 36)` (`perf/bootstrap.py:794`); no shorter window is registrable. BOOK-1b adds no rolling-risk run (the return-account exposure loop keeps `BOUNDARIES`, Part 2.7). | **CRO-1 gate decision (Part 6 out (11)):** show the one 12-month MDD point as a number beside the VaR chart, or amend J-CRO-7's line to "VaR trend, with maximum drawdown over the year as a number", or compute a drawdown series client-side from the PORTFOLIO_RETURN rows (an unbound sum, CTRL-039's question). Not served as a chart by any run family today. |
| J-CRO-2, 4, 6, 8 | nothing | BOOK-1a (`purpose_mismatch_remediation_plan.md:76`) |

### 12. The old campaign tenant's disposition (roadmap row 2, 2026-09-18 addition)

The ten per-stage DEMO-* books stay in the test battery, because their goldens must not move
(`product_rebaseline_2026-09-17.md:387-388`). They are absent from any deployed database: Phase 0a is
DONE, a fresh `deploy.sh --with-demo` printed `DEPLOY VERIFIED` then `DEMO SEEDED`, and "the registry
holds `northlight` and `system` only" (`purpose_mismatch_remediation_plan.md:51`; roadmap `:355`). One
lane read a stale roadmap row during its run; at `323cedc` the row and the plan agree. BOOK-1b changes
nothing here and carries nothing on it. The seed is refuse-not-skip (`seed.py:307-308`; `cli.py:43-49`),
so BOOK-1b cannot be applied over a BOOK-1a database: the deployed stack is re-seeded by a fresh deploy.

### 13. The roster's pacing and commitment codes (DS-B1b-13)

`pacing.view` joins `_READ_PERMS` (CRO, PM, RM, auditor, analyst); `commitment.view` is granted PER
PRINCIPAL to the CRO, PM, RM and analyst and NOT to `northlight-auditor` (`auditor_3l`), because the
catalog excludes the 3L auditor from the captured-INPUT `commitment.*` codes
(`entitlement/bootstrap.py:140-141`: "auditor_3l is EXCLUDED from all three (captured-INPUT read
scope") while including it in `pacing.view` (`:152`); `ROLE_TEMPLATES["auditor_3l"]` holds
`pacing.view` and not `commitment.view` (Executed, round 4: `auditor_3l template: pacing.view True |
commitment.view False`), and the file names a grant of that class as a BLOCKING SoD defect (`:68-72`; the label is at `:69`,
"the verifier pass caught a single `.view` here as a BLOCKING SoD defect", and `:71` carries only the
grant clause, R4V-06).
The ground is the CATALOG's holder set, not the roster's (R3-05): `_READ_PERMS` is applied verbatim to
`northlight-auditor` (`seed.py:236-241`), and that tuple ALREADY grants the auditor nine codes absent
from its template (Executed, round 4: `northlight-auditor role auditor_3l ... grants 22
absent-from-template 9: ['concentration.issuer.view', 'marketdata.view', 'portfolio.view',
'position.view', 'reference.classification_assignment.view', 'reference.instrument.view',
'reference.issuer.view', 'snapshot.view', 'valuation.view']`), three of them the very
"marketdata/valuation precedent" the catalog comment names, so the roster is not a clean boundary this
slice can cite; `cro_2l` and `portfolio_manager_1l` have no template at all (Executed: `in
ROLE_TEMPLATES False` for both), so the CRO's and PM's per-principal grants sit inside no holder set.
BOOK-1b does not widen the crossing: `commitment.view` stays off the auditor, and the pre-existing nine
are carried out as an open SoD question (Part 6 out (10)), not ratified here by silence (GOV-4). `commitment.edit`,
`commitment.record` and `pacing.run` join the analyst. The codes are safe to grant not because they sit
in a Python constant but because migration `0064_entitlement_catalog_sync.py` delivered them to running
databases and `_permission` refuses an unknown code (`seed.py:323-326`); no P17 mint. **Proof:** the PG suite reads
`GET /pacing/projections/latest` and `GET /commitments` as the CRO principal under RLS and gets rows.

---

## Part 3 — Fences, enumerated before drafting (P7's pre-flight companion)

1. **Coverage gate:** a candidate factor with no return in any appraisal period refuses the regression
   before any write (`snapshot/service.py:2760-2765`; `proxy_weight_service.py:313-323`). Mint first.
2. **Window pollution:** any mark inside `[window_start, window_end]` is an appraisal
   (`snapshot/service.py:2419-2431`). The window ends 2025-03-31; the first carry mark is 2025-06-30.
3. **Unmapped atom:** the root loadings run FAILS post-create on a private atom with no mapping
   (`factor_service.py:507`). Promote before the first month-end. **And loadings coverage** (R3-01):
   the same run REFUSES pre-create when any pinned atom has no LOADING-family row
   (`_assert_full_coverage`, `factor_service.py:414-441`, called at `:650`); PRIVATE memberships are
   not pinned (`snapshot/service.py:894-914`), so (given the `_seed_loadings` skip of fence 22, V7-01) every young fund carries one NON-ZERO MANUAL loading on
   its sleeve's primary factor (Part 2.3, fence 22; a zero-weight row satisfies this gate but emits no
   exposure row and hides the fund from the unified builder, R4V-01). The families the coverage rows rely
   on, all in `LOADING_FACTOR_FAMILIES`: MARKET (`MKT_GLOBAL_EQ`), CREDIT_SPREAD (`CREDIT_HY_TR`) and RATES
   (`RATES_UST_TR`; FR-06) — the mature funds' REGRESSION rows sit on those three, the young funds' proxy
   rows on the first two.
4. **Staleness:** `age > max_estimate_age_days` refuses pre-create (`var_service.py:650-651`); 456 at
   2026-06-30 under a 548 policy, on the TOTAL flavour; the unified flavour cites no estimate while every
   private instrument is a segment member, so its age is None (Part 0.4, R4V-02).
5. **Unified MANUAL hazard** (Part 0.7): unresolved, unified at the root refuses. DS-B1b-3 first.
6. **Common grid:** members of one segment need identical appraisal grids
   (`private_factor_service.py:277-281`); the private covariance needs exactly `window_observations`
   common periods (`private_covariance_service.py:176-179`). One grid for every mature fund.
7. **Pacing:** commitment and mark on one portfolio id; a funded pair needs a mark
   (`pacing/service.py:191-194` refuses, and every seeded pair has calls); a pair with NO mark anchors
   on the real clock (`snapshot/service.py:2605`), so EVERY pacing pair carries a 2026-06-30 mark,
   position or not (FEAS-2); mark currency equals commitment currency; as-of before vintage refused;
   age at or past fund_life refused (`pacing/service.py:159,182-199,267`).
8. **Golden selectors:** `scalar_one()` at `window_end == 2026-06-30` (`test_demo_tenant_book1a_pg.py:366-381`).
   Never re-run a month-end in the daily chain.
9. **Time-bomb fence:** no `now(`, `today(`, no literal after 2026-06-30 (`test_demo_tenant_book.py:110`).
   The breach instant is 2026-06-30T22:00Z; the promotion age is the engine's, not the seed's.
10. **Aggregation census:** any `+=`, `sum()` or `x = x + y` in the package trips it (BOOK-1a Part 3.2).
    The allowlist is keyed `(module, function, kind) -> (COUNT, class)` (`test_aggregation_census.py:
    116-120`), so a new site inside an already-listed function (`generate_paths` is pinned at 1
    `plain-assign-add`) needs the COUNT bumped, and `irp_shared.demo_tenant.seed` has no entry at all,
    so any `+=` there is a new key (FEAS-8). Σcalls for the unfunded assertion lives in the suite, not
    the seed.
11. **VaR reads without `metric_type`** return whichever flavour ran last (Part 0.9). Every read and
    golden names it.
12. **Ids are not stable across seeds** (Executed: `northlight-rm` was `f4a8852e-...` then `26ccc2e0-...`).
    Limits reference `_Refs`/`SeedSummary`, never literals; `MAX_SHARE_ISSUER` avoids issuer ids.
13. **Run-type filter on `covariance_result`** (`covariance_service.py:432-441`): every new read and
    the census carry it.
14. **The book fences:** `test_demo_tenant_book.py:38` (50-60 boundaries) holds under a separate daily
    set; `:91` (marks per instrument) and `:102` (benchmark rows) are read before edit and amended
    with a reason where the union changes them. Two more in the same loop (GOV-8): `:90` reads
    `paths.marks[inst.code]` for every `book.INSTRUMENTS` entry (a `KeyError` if the private marks are
    not in `paths.marks`) and `:92` asserts `1.0 <= v <= 10_000` per mark (a NAV of about 21M fails
    it); `:94` asserts `abs(b/a - 1) < 0.15` per consecutive mark (a private quarterly NAV step of up
    to +20 % would fail it); and `:100` asserts marks at or below `face_value` for zero-coupon bills.
    Decision: the private instruments are excluded by an explicit predicate on asset class that covers
    `:90`, `:91`, `:92`, `:94` AND `:100`; the test asserts the excluded set is non-empty so the fence
    cannot go blind; and a separate assertion bands private NAVs (1M to 100M) with NO per-step move
    check, because a quarterly private step is not a weekly public one. The function is read before it
    is edited. **The two SEED suites carry eight more sites that BOOK-1b breaks, plus `:207` which holds and is
    read only** (S-04; nine grep hits, re-run at round 5, R4V-04; read at round 3,
    `grep -n "BOUNDARIES\|len(book.INSTRUMENTS)"`), each amended as follows, read before edit:
    `test_demo_tenant_seed.py:135` `assert summary.marks == len(book.BOUNDARIES) * len(book.INSTRUMENTS)`
    → the sum over three grids, public × union + private × union + mature × appraisal grid (55 × 105 +
    12 × 105 + 8 × 12 = 7,131 at twelve funds, written as an expression over the book constants, never
    the literal); `:143` `assert set(per_date) == set(book.BOUNDARIES)` → `set(book.BOUNDARIES) |
    set(book.DAILY_BOUNDARIES) | set(book.APPRAISAL_GRID)` (105 + 12 dates); `:144`
    `assert set(per_date.values()) == {len(book.INSTRUMENTS)}` → SPLIT: every union date carries
    `len(book.INSTRUMENTS)` (67, the private instruments appended), every appraisal-grid date carries
    exactly the mature private count (8), asserted as two separate set comparisons;
    `test_demo_tenant_book1a_pg.py:232` `assert set(marks_per_date) == set(book.BOUNDARIES)` and `:233`
    `assert all(n == len(book.INSTRUMENTS) for n in marks_per_date.values())` → the same union-or-grid
    set and the same split; `:241` `assert set(fx_per_date) == set(book.BOUNDARIES)` → the union only
    (no FX on appraisal dates); and the two run-count dictionaries `test_demo_tenant_seed.py:47`
    (`"exposure": _FUNDS * len(book.BOUNDARIES) + ...`) and `test_demo_tenant_book1a_pg.py:64`
    (`"EXPOSURE_AGGREGATE": ...`) → each gains the daily terms of Part 2.8 (`_FUNDS *
    len(book.DAILY_CHAIN_DATES)` for exposure and factor exposure, 59 for covariance, and the new
    families' rows). `test_demo_tenant_book1a_pg.py:207` `assert held == len(book.INSTRUMENTS)` keeps
    holding at 67 and its `50 <= held <= 80` band holds; it is read, not amended. **The pre-flight is wider
    than that grep** (FR-08): `grep -n "BOUNDARIES\|len(book.INSTRUMENTS)"` cannot reach the per-instrument
    loops of `test_demo_tenant_book.py` that iterate `book.INSTRUMENTS` without naming its length — `:73-76`
    (ISINs unique, `ZZ\d{10}`, check digit via `book.isin`), `:89-100` (the mark fences above) and the
    fund-holding loops at `:70-78` (every fund holds at least three instruments; no two funds share a holding;
    the benchmark is never a subset of the fund's holdings) — so before the seed is written every function in
    `test_demo_tenant_book.py` that iterates `book.INSTRUMENTS`, `book.FUNDS` or `book.FACTORS` is read
    whole (`grep -n "book.INSTRUMENTS\|book.FUNDS\|book.FACTORS" test_demo_tenant_book.py`), and each site
    is listed in the record as HOLDS or AMENDED with the reason. The ISIN fence holds over 67 by construction
    (Part 2.1); the holding fences hold because the twelve LP interests sit under NL-PMF's two private accounts.
15. **Refuse-not-skip, one commit** (`seed.py:307-308`; `cli.py:50`): a daily date that fails, fails the
    whole deploy-path seed. Every private-chain refusal is designed out above; the suite proves the
    seed completes on a fresh database, twice (SQLite and PG).
16. **`make fix` before the first gate run**; purge `__pycache__`; no `git add -A` while agents hold the
    tree; read a structured file's block schema before appending (`mutants.toml`, the two scope JSONs).
17. **`test_ci_pg_coverage`:** BOOK-1b's PG assertions extend `test_demo_tenant_book1a_pg.py` (one seed
    per suite run); a new PG module would need its own CI step.
18. **Multi-currency marks refuse:** the desmoothing binder refuses pinned marks spanning more than one
    currency (`desmoothing_service.py:221-225`), a second fence beside the three-character check (C-04).
19. **Every FX series spans the union** before the capture loop, or the seed refuses by name (FEAS-1).
20. **Coverage of the unified legs** is asserted positively over the private instrument set (GOV-1),
    and after the DS-B1b-3 (B) fold the builder refuses a PRIVATE_EQUITY / PRIVATE_CREDIT instrument
    with neither a PRIVATE-family membership nor a REGRESSION mapping.
21. **The two new factors draw from their own random stream** (`random.Random(SEED + 1)`), because the
    shared stream feeds the mark noise after the factors (`book.py:1394-1405,1438`); the three goldens
    unchanged is the proof (DS-B1b-15). **And the twelve private specs draw from `random.Random(SEED + 2)`**
    with idio sigma zero at `:1438`, because the benchmark noise follows the mark noise on the same stream
    (`:1481`) and the goldens read no benchmark value; the proof is the series digest of Part 5 (FR-02).
22. **Sleeve-proxy loading per young fund** (R3-01, R4V-01): each young private instrument carries one
    NON-ZERO MANUAL loading (weight 1.0 on `MKT_GLOBAL_EQ` for PE, on `CREDIT_HY_TR` for direct lending)
    beside its PRIVATE membership; the suite asserts at least one LOADING-family mapping per private instrument
    (the gate at `risk/factor_service.py:417-422` refuses only total absence), and exactly one on each of
    the four young funds (the weight-1.0 sleeve proxy; the eight mature ones carry two REGRESSION rows each, V5-03) and
    exactly one 2026-06-30 factor-exposure row per young fund equal to 1.0 × its NAV mark; and `_seed_loadings`
    (`seed.py:681-687`, unconditional over `book.INSTRUMENTS` today, called at `:1230`) gains an explicit
    predicate that SKIPS `PRIVATE_EQUITY` / `PRIVATE_CREDIT` specs — an edited site, read before edit — so no
    private instrument carries the zero-weight FX row; without the skip each USD-marked young fund would carry
    TWO LOADING-family rows (FX_USD at 0 plus the proxy), the census would be short twelve rows, and R3-01's
    coverage premise would be false because a zero-weight row IS coverage (`factor_service.py:420-422`; V6-01);
    the suite asserts that no private instrument carries an `FX_` loading. Mutant (15)
    sets the young weight to zero and mutant (16) drops the row.

---

## Part 4 — Decisions this slice cannot make for itself (Tier 3, with recommendations)

**DS-B1b-1 [briefed] — The appraisal window end, and with it the staleness policy.** The lanes disagree.
(a) Window 2022-06-30 to **2025-03-31**, strictly before the marked year as the ratified text says;
age at 2026-06-30 is 456 days; declare `max_estimate_age_days = 548` (18 months) on the total and
unified models (binding on the total flavour only; the unified declaration is required at registration
and inert, Part 0.4, R4V-02). (b) Window ending **2025-06-30**, the first boundary and a quarter end, so the
2025-06-30 mark is both the last appraisal and the first carry mark; age 365; declare 400 (the campaign
and stage-13 value, `campaign.py:232`, `ppf3_stage13.py:109`). (c) A tight policy with mid-year
re-estimation: impossible, no appraisals may sit inside the marked year. **Recommend (a).** It reads
the ratified row literally ("ending BEFORE the marked year begins"), keeps every appraisal out of the
year the screens show, and an annual re-estimation with an 18-month tolerance is a plausible policy,
disclosed on every row through `estimate_age_days`. (b) puts the whole daily quarter within 35 days of
the cliff and makes one mark carry two meanings. Either way the coverage mint is needed (DS-B1b-2).

**DS-B1b-2 [routine] — Factor coverage for the regression.** (a) Mint one SIMPLE return per candidate factor per
desmoothed-period end, dated on or before 2025-03-31 (30 rows; the HG-1 precedent). (b) Extend the
daily factor series back to 2022 (about 750 business days × k factors; one lane sized it at 780).
(c) Move the appraisals into 2025-04-01..2026-06-30 (breaks the ratified constraint and re-opens the
pollution problem). **Recommend (a).** Measured coverage is 0 of 10 today; (a) is provably invisible to
every daily window (Part 0.3); (b) multiplies captures for no screen value.

**DS-B1b-3 [briefed] — Unified VaR at the NL-PMF root against the MANUAL-loading hazard (BLOCKING).**
(A) Re-seed NL-PMF's Treasury Reserve loadings as REGRESSION rows so no public MANUAL row exists in that
fund. (B) Add a `FACTOR_FAMILY_PRIVATE` filter to `build_var_unified_snapshot`'s MANUAL query (the query at
`snapshot/service.py:3554-3568` selects on `mapping_method` only and joins no factor). That is the ONLY
code site for the filter: `_build_p_vector` (`var_service.py:518-520`, called at `:1265`) receives the pinned
`proxy_mapping_content` rows (`snapshot/serialize.py:392-402`: id, tenant, instrument, factor, weight, method,
dates, version; no factor family) that the filtered query produced; the kernel refuses a held segment with no
Omega_pp diagonal entry on EVERY path (`risk/var_unified_kernel.py:81-89`, `uncovered-segment`, reached at
`var_service.py:1351`), and the builder refuses earlier on the build-in-request path only
(`snapshot/service.py:3580-3585`; the consume-existing path skips the builder, `var_service.py:1266-1270`),
so a second filter in `_build_p_vector` could never fire — the inert-guard class the Wave-17 close named — and is not written
(V5-01, then V6-03). No pinned-content shape changes (GOV-9). Plus the coverage refusal of Part 3.20: a CONFORMANCE REPAIR of the PPF-3 binder to
its own registered `v1` assumption (`risk/bootstrap.py:2852-2853,2863`; Part 0.7), shipped as its own
small pre-slice fold with a negative control and the different-engine review, BEFORE BOOK-1b's seed is
written. The fold's G2 declaration is no-scope (a defect fix, the demo-tenant-fix precedent); the
assumption question is routed through MODEL governance, not G2 (GOV-6): the owner decides at the fold's
gate whether the repair is a code-conformance fix under the same declared assumption and label `v1`
(recommended: the text already says "of segment s"), or needs a new `version_label`. Because VAR is a
reproducible family (Part 0.20), the fold proves before landing that no unified run already stored on
a deployed stack changes value.
(C) Scope the unified run to a private-only node; the run's scope copies the exposure run's
(`var_service.py:1428` `scope_portfolio_id=pinned_exposure_run.scope_portfolio_id`; C-09), so J-CRO-1
cannot rank the fund on it. **Recommend (B).** (A) and (C) both leave the non-conformance shipped, so
neither is a governance answer; the builder's own comment calls the MANUAL rows pure-private
memberships, and PROBE D shows the binder prices a mixed book once the public instrument has no MANUAL
row. (A) also re-seeds a fund around an engine quirk and leaves the trap for the next tenant. Not verified, and worth one probe before the fold: whether a unified run
over the ALLOCATION-family exposure at the root avoids the hazard (PROBE D used that family). If (B) is
declined: unified is not run at the root, NL-PMF's limit and daily series use VAR_PARAMETRIC, the
young funds of DS-B1b-4 become commitment-only, and the record says so. *(Branch not taken: (B) ratified
2026-09-18.)*

**DS-B1b-4 [briefed] — The vintage ladder against the three-year history (the cross-lane conflict, Part 0.18).**
(a) All private funds mature: vintages on 30 June 2019 to 2022 (a 2022 vintage needs a same-day first
DRAWDOWN so its first mark is positive); every fund carries the full chain; smaller unfunded, the
reserve covers all of it. (b) Mature plus young: mature funds carry the chain and the segment memberships; young funds carry
commitments, calls, distributions, pacing, a position marked at NAV, a weight-1 MANUAL MEMBERSHIP of
the sleeve's PRIVATE segment factor and one NON-ZERO weight-1.0 MANUAL loading on the sleeve's primary
return-type factor, for loadings coverage AND visibility to the unified builder (Part 2.3; the membership
is what puts the fund in leg 2, GOV-1; the non-zero loading is what makes it an exposure instrument at
all, R3-01, R4V-01), disclosed as proxied until history exists. Rests on DS-B1b-3 (B), ratified. Any mature vintage on the grid's first date
(2022-06-30) needs the same same-day first DRAWDOWN as (a), because the grid is one for every member
(`private_factor_service.py:279-281`) and a non-positive first mark refuses
(`desmoothing_service.py:203-206`); the ladder therefore puts no mature vintage on 2022-06-30 (N-05,
CRO-R14). The same rule covers the marked year (R3-04): no vintage, mature or young, sits on the
appraisal grid's first date OR on `book.BOUNDARIES[0]` (Executed, round 4: `BOUNDARIES[0] 2025-06-30`)
without a same-day first DRAWDOWN. The young DL 2025-06-30 vintage is exactly on that boundary, so it
keeps its date (the roster number carried everywhere, S-05) and carries a same-day first DRAWDOWN of at
least 1,000,000 USD; its 2025-06-30 mark is that paid-in amount, inside Part 3.14's 1M to 100M band
(Part 2.2). PE 2024-06-30 and DL 2024-12-31 predate the first boundary and need nothing. (c) Mature plus young, the young funds commitment-only (no position). Its two real costs
(FEAS-2): a commitment-only pair WITH calls refuses (`pacing/service.py:191-194`) and fails the seed;
one WITHOUT calls anchors its pacing snapshot on `utcnow().date()` (`snapshot/service.py:2605`) and
breaks Part 5's one-excluded-field determinism claim — so (c) requires every pair to carry a
2026-06-30 mark regardless, and NL-PMF's exposure still omits the young funds' paid-in NAV.
**Recommend (b) — and (b) is a DEPARTURE the owner is asked to ratify** (GOV-2; the fallback to (a) if
DS-B1b-3 were declined is a branch not taken, DS-B1b-3 (B) ratified 2026-09-18): the ratified clause says "one desmooth, regression and promotion chain per
private fund" (`product_rebaseline_2026-09-17.md:377-378`; roadmap `:357` repeats it) and J-CRO-5 reads
"for each private fund, reported (appraisal) volatility beside desmoothed volatility"
(`personas_and_user_journeys.md:95`); under (b) the young funds have no desmoothed volatility to show
and J-CRO-5 shows "proxied until history exists" for them. Ratifying (b) amends that clause to "per
MATURE private fund"; declining it means (a), which is what the record says. (b) is what a fund of
funds looks like: a ladder of vintages, the young ones proxied. (a) is the simplest and has no engine
dependency but shows a programme that stopped committing in 2022 and a reserve larger than its
unfunded — this remit's own judgment; the realism rule's nearest clause is "book TOTALS must sit where
a mid-sized manager's would" (`test_data_realism.md:37-38`), which does not name that ratio (C-15).
Roster size (CRO-R9): the denominator is the 175M PRIVATE SLEEVE (Part 2.4's NAV), not the 220.7M fund
(FR-09). At eight funds the average GP exposure is about 13 % of the sleeve (175 / 8 = 21.9M; 9.9 % of the
220.7M fund), which a CRO queries on a fund of funds; the recommended roster is TWELVE underlying funds
(eight mature — PE 2019-06, 2019-12, 2020-06, 2021-06, 2021-12; DL 2020-06, 2021-06, 2021-12 — and four
young — PE 2023-06, 2024-06; DL 2024-12, 2025-06) so the average GP is 7-9 % of the sleeve (175 / 12 =
14.6M, 8.3 %; 6.6 % of the fund) and the largest about 12 % of the sleeve (about 9.5 % of the fund).
The limits grid is fund-scoped, so `MAX_SHARE_ISSUER` on NL-PMF reads the fund-level figures. The
Treasury reserve stays the largest issuer either way (Part 2.6). Sizing: about 235M committed across
twelve pairs (Part 2.4); the census is stated at twelve (Part 2.8) and restated if the owner keeps
eight; the record quotes the final figures.

**DS-B1b-5 [briefed] — How to read "two live breaches and one utilisation strictly between zero and threshold".**
(A) Literal: five limits, exactly two breached, exactly one strictly between, two at zero (the two
structurally-zero TE values, Part 0.11, which is a broken row on the first screen, CRO-R5); no VaR
ceiling on two funds, no TE ceiling on NL-GMA. (B) Demonstrating case: the grid a CRO expects (ten
limits, Part 2.6; the first draft's eleven included two TE limits on structurally-zero values, and its
"strictly-between case" was a sovereign issuer share that duplicated the sector row, CRO-R4), the same
two breaches, every other limit strictly between, and the record NAMES `NL-GMA-CR5` at 84.5 percent as
the case that exercises REQ-LIM-002 clause (3) and J-CRO-3's 80 percent line
(`personas_and_user_journeys.md:93`), with the other seven strictly-between rows listed as such (GOV-14; R3-03 added the sector row).
**Recommend (B).** The ratified text says "one", not "exactly one"; no limit sits on a
structurally-zero value; J-CRO-1 needs a ranking with a population. Thresholds: hardcoded round numbers
for NL-GMA and NL-EFI (goldens, stable), derived from the measured value for NL-PMF until its numbers
exist, then frozen in the record; the seed asserts the intended outcome per limit either way.

**DS-B1b-6 [routine] — Promotion age bound.** (A) None, the HG-1 precedent; the stored `promotion_age_days`
varies by seed day and the record says so. (B) A bound that passes today (over 536) and fails on a
future date. **Recommend (A).** (B) is a time bomb by construction; a moving bound is a guard that
cannot fire (the Wave-17 close class).

**DS-B1b-7 [briefed] — The daily boundaries.** Three linked choices. Date set: (A) extend `BOUNDARIES` (105;
re-cuts the benchmark series, +147 return-account runs, three book fences amended) or (B) a separate
daily set read by the mark/FX loops and the daily chain only. Dates: (A) all 62 (re-runs three
month-ends; `MultipleResultsFound` in both suites) or (B) the 59 non-month-ends. Covariance: (A) one
shared full-set matrix per date or (B) the roadmap's literal 372. **Recommend B, B, A.** No BOOK-1a
stored value moves; 767 public runs instead of 914 or more.

**DS-B1b-8 [briefed] — Lifecycle state of the two breaches at seed.** (A) Both DETECTED: no owner, no due date,
no clock, nothing escalates. (B) Assign one to the PM with a seed-relative clock (the `ops_stage14.py:114-126`
pattern): the deployed tick escalates it within 1 to 5 days (`events.py:161`) and the book changes by
itself. (C) Assign with a fixed instant: permanently overdue, escalated on the first tick.
(D) Both DETECTED, with REAL detection dates: evaluate after each of the last three month-end chains
with injected instants 2026-04-30T22:00Z, 2026-05-29T22:00Z, 2026-06-30T22:00Z (Part 2.6), so each open
breach has a first-detected date and an age, which is two of the four things J-CRO-1 asks (which limit,
how far over, since when, who owns it); still no owner, no due date, no clock (CRO-R6).
**Recommend (D).** The walks are the acceptance test; a CRO assigning live on J-CRO-3 and the PM
responding on J-PM-3 is the better demonstration, the seed stays clock-free, and a breach born in the
same second as every other breach has no "since when".

**DS-B1b-9 [briefed] — The backtest families.** (A) In scope, feeding only forecasts whose next boundary is the
next calendar day (the 1-day pairing rule, `var_backtest_service.py:369-383`: a Friday forecast cannot
pair with Monday). (B) In scope as a demonstrated refusal. (C) Deferred until a journey line names a
backtest; none of J-CRO-1..8 or J-PM-1..4 does. **Recommend (C), stated as what it is: a NAMED DEPARTURE from the ratified clause "every governed
family run against each fund" (`product_rebaseline_2026-09-17.md:384-385`) that the owner is asked to
amend at this gate** (GOV-5). DP-RB2-7 does not authorise it: it pauses NEW calculation families
(`:465`), and VAR_BACKTEST and ES_BACKTEST are delivered, reproducible families (Part 0.20). The
justification is on the merits: the 1-day pairing rule makes a book whose forecasts are weekly for
nine months and daily for one quarter a poor demonstration of a backtest, and no journey line shows an
overshooting count. REQ-MKT-005 is never adjudicated; running it would be the same "delivered row" case
as BOOK-1a's families, but nothing asks for it. If the owner declines the amendment, (A) runs in this
slice with the pairing rule stated and the census restated. *(Branch not taken: the amendment was
ratified 2026-09-18, (C).)*

**DS-B1b-9a [routine] — Which path the ten-minute ceiling binds.** (A) In-stack via `deploy.sh --with-demo`
(86.7 s today, about 198 s projected). (B) From the host (295.7 s today, about 691 s projected).
(C) Both. **Recommend (A), with the host figure quoted.** The deploy path is the one Phase 0a measured
and G5 uses.

**DS-B1b-10 [briefed] — G2 scope.** (A) Declared no-scope, dated 2026-09-18, naming REQ-LIM-001/002/003 (served
by evaluation; LIM-002 re-asked at UTIL-1, roadmap `:359`), REQ-PRV-001/002/003/005 (served by captures)
and REQ-MKT-005 (not run), each entering build at its own slice. (B) Scope LIM-001/002/003 and
adjudicate all three now (two never asked, one lapsed by the 2026-08-15 pre-amendment hash). **Recommend
(A), with the reason argued on the gate's own test** (rows entering build, not the mint test; the G2
header states it: REQ-LIM-002 clause (3) is served with data, the stored number lands at UTIL-1, and
the seed's clause-(3) assertion is evidence for UTIL-1's adjudication, GOV-7). Executed: the eight-row
probe exits 1 with 7 never asked + 1 lapsed (N-03), so (B) would be a two-commit G2 amendment under P20
(acceptance text first, ledger hash from the post-amendment cells via the gate's own `parse_rows`).
DS-B1b-3 (B) is ratified, so that fold declares its own scope (the demo-tenant-fix precedent: a defect fix, no row
entering build, `g2_slice_scope.json` `_scope_note`).

**DS-B1b-11 [routine] — A strategy-node limit for REQ-LIM-004?** (A) No; fund-root only as ratified; LIM-004 stays
Draft (`requirements_backbone.md:244`). (B) Yes, and adjudicate it here. **Recommend (A).** (B) lets a
Draft row enter build in a no-scope slice. The distinction from REQ-PRV-003, also Draft
(`requirements_backbone.md:173`) and served by this slice's captures (GOV-12): LIM-004's acceptance
names the demo-book demonstration as the deliverable, so building it delivers the row; PRV-003's also
requires stale-NAV FLAGGING, which BOOK-1b does not build, so its captures serve a row that stays Draft.

**DS-B1b-12 [routine] — The alpha convention for the Northlight private funds.** (a) DECLARED alpha (the HG-1
shape; an honest pre-smoothed generator so the OLS recovers a known structure and a hand golden
exists; `perf/bootstrap.py:349-355` default 0.4). (b) AR1_ESTIMATED (observed 11 >= 6; small-sample
biased, as DS-2 discloses). Both fit 12 marks. **Recommend (a).** J-CRO-5 shows "reported vs
desmoothed"; a declared alpha makes the difference a stated assumption a CRO can read, and the golden
is derivable by hand.

**DS-B1b-13 [routine] — The roster's pacing and commitment codes: BOOK-1b or CRO-1?** (A) BOOK-1b (outcome 13).
(B) CRO-1. **Recommend (A).** The data is useless to the persona without the read code; the seed is
where the roster lives; no mint, no P17.

**DS-B1b-14 [routine] — The mutant floor.** (A) Group `w20-book1b` with at least seventeen mutants (Part 5; seventeen from round 8, V7-02; an eighteenth, the series digest, added at the ratification-diff fold, FR-02 — the floor "at least seventeen" holds), kills
run by hand with exit codes quoted. (B) No floor. **Recommend (A)** (P18; the BOOK-1a 7/7 pattern).

**DS-B1b-15 [briefed] — Two total-return index factors added to the public book (CRO-R1, CRO-R13).** The
regression candidates must be price-return factors, or the promoted weights are durations that enter
the unified p vector as multiples of NAV (Part 2.3). (A) Add `CREDIT_HY_TR` and `RATES_UST_TR` to
`book.FACTORS` (eight today, `len(book.FACTORS) == 8`) on their own random stream, so no public mark or
golden moves; PE = `MKT_GLOBAL_EQ` + `CREDIT_HY_TR`, direct lending = `CREDIT_HY_TR` + `RATES_UST_TR`
(option (i) of the fold check, F-01; union three, 30 minted returns). (B) Keep the book's eight factors and
regress on `MKT_GLOBAL_EQ` alone (k = 1; the floor `max(3, 3) = 3` against n = 10), disclosed as a
single-factor proxy. (C) The first draft's change-type candidates (`RATES_USD_10Y`, `CREDIT_HY`;
`book.py:152,157`), with the p-vector consequence disclosed. **Recommend (A).** (B) is honest but gives the direct-lending sleeve an equity beta and
nothing else; (C) ships a number a CRO would read as wrong. This was a sub-question in the first draft;
it is Tier 3 because it adds two captured factor series to the public book.

Sub-questions Claude decides and flags for reversal: total VaR at month-ends only while unified runs
daily (Part 2.5); the pacing parameters and labels (Part 2.4); the call and distribution schedules and
the DPI bands (Part 2.4); which four vintages sit on 31 December (Part 2.4 names them); no teaching reversal; the
three evaluation instants (Part 2.6); the private mark step series' quarter-end values in the marked
year; the strategy-focus classification of each private fund (Part 2.1).

---

## Part 5 — Proofs (what "done" means, and none of it is a reading)

- `make check` exit 0 with the count quoted; full-PG exit 0 with the count quoted on a fresh four-part
  reset (drop+create, `GRANT ALL`, `GRANT USAGE ON SCHEMA public TO PUBLIC`, `alembic upgrade head`);
  `mutant-anchors` 195/195 (re-anchored if `book.py` bytes move under M-B1A-4..7) plus group
  `w20-book1b` all KILLED, at least: (1) one appraisal mark dropped → `n_periods` != 10; (2) `window_end`
  moved onto 2025-06-30 → pinned marks > 12; (3) the private chain reordered after the month-end chain →
  a FAILED `unmapped-atom` run; (4) a threshold moved so a third limit breaches → the two-limit assertion;
  (5) `NL-GMA-CR5`'s threshold moved to exactly the observed 0.549503 → `observed < threshold` fails
  ALONE (the breach count stays two because the predicate is strict, `limit/service.py:205`; the first
  draft's "to breach or to zero" variants were killed by mutant (4)'s oracle or raised a division error
  rather than failing an assertion, GOV-15, FEAS-6); (6) one Q2 date dropped → 59 daily rows; (7) one
  pacing pair's 2026-06-30 mark omitted → pacing refuses, the seed fails; (8) a minted quarterly return
  dated inside the daily window → the euro golden moves, anchored on the MINT site (CRO-R12);
  (9) the daily chain moved AFTER the month-end chain (the order of Part 0.6 inverted, anchored on the
  orchestrator's call sequence at `seed.py:1234-1239`) → the 59 later-created NL-GMA VAR_PARAMETRIC daily
  runs outrank the June month-end run by `system_from`, `limit_health` resolves one of them, and
  `NL-GMA-VAR` reads BREACHED with `latest_breach_id` None (no breach row exists for that run; FR-01);
  (10) the FX-cross comprehension left on `BOUNDARIES` → the named refusal, not a `KeyError` (FEAS-1);
  (11) one promoted weight set negative → the weight-band assertion (CRO-R1); (12) a call folded into an
  appraisal mark → the observed-return band assertion (CRO-R2); (13) the three evaluations collapsed to
  one instant → the earliest-`detected_at` assertion (CRO-R6); (14) a young fund's membership dropped →
  the positive coverage control (GOV-1); (15) a young fund's sleeve-proxy weight set to zero → the fund emits no
  factor-exposure row (`factor_service.py:470-471`) and the per-young-fund assertion "exactly one
  2026-06-30 factor-exposure row equal to 1.0 × NAV" fails (R4V-01; the coverage control of Part 2.5,
  whose right-hand set is the roster, is a second net); (16) a young fund's sleeve-proxy row dropped →
  the NL-PMF root loadings run refuses pre-create with `the loadings family requires every atom to
  carry >= 1 loading row` and the seed fails (R3-01; the oracle is a REFUSAL before `create_run`,
  distinct from mutant 3's post-create FAILED run, mutant 14's coverage control and mutant 15's
  exposure-row assertion; this refusal is the oracle ONLY under the fence-22 skip — without it the
  FX_USD row is coverage, `factor_service.py:420-422`, and (16) collapses into (15), V7-01);
  (17) the fence-22 predicate removed from `_seed_loadings` (`seed.py:681-687`) → the assertions
  "no private instrument carries an `FX_` loading" and "exactly one LOADING-family mapping on each of the
  four young funds" both fail (V7-02); (18) one private spec given a non-zero idio sigma at `book.py:1438`
  (a draw from the shared stream) → the public marks stay identical, the three goldens stay green, and the
  benchmark-series digest of the determinism proof below fails (FR-02; the oracle is the digest ALONE,
  which is what makes the mutant distinct from every golden). Every mutant anchored on the SITE, one test through the real
  entry point, half of them negative, and each mutant's oracle distinct from its neighbours' so a kill
  is attributable to its own site.
- **The deterministic-seed proof:** two seeds on fresh in-memory SQLite produce identical governed
  values row for row, with exactly one field excluded and named: `proxy_mapping.promotion_age_days`
  (Part 0.5). **The shared random stream did not move:** the three BOOK-1a goldens unchanged PLUS an
  explicit assertion that the 55 public instruments' `paths.marks` series and the three funds'
  `paths.benchmark_returns` series are byte-identical to BOOK-1a's — pinned as a fourth golden, a stored
  SHA-256 over the `Decimal` strings of both series in date order, derived once from `book.py` at
  `1c430f9` and quoted in the record. The goldens alone cannot prove it: they read marks, FX and factor
  returns only, and the benchmark noise is drawn AFTER the mark noise on the same stream (Part 0.17,
  FR-02). Mutant (18) is the digest's negative control.
- **The PG suite under RLS through the real admission gate:** the orchestrator runs once end to end on
  a fresh database in CI; a second run refuses and writes nothing; every new read (desmoothed latest,
  pacing latest, limits, limits/health, breaches open, VaR latest by metric_type for the three
  flavours) returns rows for a Northlight principal with the tenant GUC armed and returns nothing for
  the base-campaign tenant on the battery's shared database; the admission gate is the real
  `assert_tenant_admitted` on PostgreSQL, at ONE site.
- **The seeding time MEASURED** in-stack via `deploy.sh --with-demo` on a fresh volume, quoted against
  ten minutes; the host figure quoted for information; DS-B1a-9's fallback order applies if the ceiling
  breaks (drop alternate daily dates first, never the month-ends).
- **The deployed smoke:** after `--with-demo`, as `northlight-cro` over HTTP: `GET /breaches?open=true`
  (two limits), `GET /limits/health` (ten rows), `GET /perf/desmoothed-returns/latest` for one mature
  pair, `GET /pacing/projections/latest` for one pair, `GET /risk/vars/latest?metric_type=VAR_PARAMETRIC_UNIFIED`
  for NL-PMF (DS-B1b-3 (B) ratified), each quoted.
- CI green on all checks at the PR head, verified per conclusion via `gh api …/commits/<sha>/check-runs`.
- The adversarial review folded before the push; P15: at least one pass on a different engine (Part 7).
- The seven-ledger sweep with verify-on-main AFTER the merge: (1) no ENT (ENT-032 reserved);
  (2) no audit code; (3) "no control moved": CTRL-021 is already **Operational** (`09_compliance_controls/control_matrix_skeleton.md:62`, the
  top of the `:36` vocabulary) and its cell already records the demo exercise at OPS-1
  (`ops_stage14.py:316-319` approves on a demo book), so there is no status move and no "first time"
  (GOV-3); if its evidence cell is touched at all it states only what is new — the person-level
  maker≠checker refusal fires inside a deployed demo-tenant SEED at the service layer; the role gate is
  not exercised by the seed (it is exercised over HTTP, recorded at OPS-1); (4) `current_state.md`
  and the scorecard row "Replace the deployed demo book" HALF → DONE; (5) backbone and RTM, "no row
  edited" if true; (6) run, capture and second counts MEASURED; (7) every shipped claim cited to the
  merged diff.

---

## Part 6 — P19 carries

**In (from BOOK-1a §6 and the plan):** (1) the fund-level scenario across accounts → Wave 21, not this
slice's; (2) tracking error currency-only → CRO-1's screen; the TE limits here are written in the
engine's daily unit and the record says so; (3) the corrected counts (56 boundaries, 6,105 captures) are
this remit's baseline; (4) §2.9's deploy carry DISCHARGED by Phase 0a; (5) the two DS-B1a-6/7 decisions
were delivered, nothing is inherited as open; the recurrence acceptance stands (no literal-date guard).

**Out:** (1) the REQ-LIM-002 gaps' true location (`wave_19_planning.md:132`) and a one-line pointer
amendment to the backbone row, a G2 amendment in two commits → **UTIL-1's gate**; (2) the unified-builder
family filter and the private-asset-class coverage refusal (DS-B1b-3 (B), ratified) → **its own pre-slice fold**, before this build; (3) "change since the
last close" for J-CRO-1: two family reads against the threshold, not a stored evaluation → **CRO-1**;
(4) the client-side unfunded sum across pairs and whether CTRL-039 governs it → **CRO-1**; (5) the
call site of `escalate_overdue_breach` on the deployed scheduler and whether Northlight is in its
population: not found by this recon's grep outside its module → **open question, answered in the slice
record**; (6) DELETED — answered by execution in Part 0.20: the census covers all six families, and the
consequence is a pre-fold check (GOV-9; a carry naming no slice and no trigger is not a carry under
P19); (7) whether any reproduction or
golden reads `promotion_age_days` → **open question**, decides the determinism claim's wording; (8) the
backtest families → **the first line that needs one**; (9) roadmap row 2's "about sixty-three" → AMENDED IN THE ROW ("sixty-two
business days, of which fifty-nine are not month-ends; one shared full-set covariance per daily date,
not one per metric per fund; measured"), because the roadmap is the document the next gate opens
(GOV-10; the OPS-H1 stale-register class). The planning commit `d676fc4` did not carry it; the
ratification-diff fold does (GOV-R-01, CC-1). The re-baseline's `:372` "about sixty-three" is ratified text
and stays; the record notes the measured count beside it; (10) the nine codes `_READ_PERMS` already
grants `northlight-auditor` beyond `ROLE_TEMPLATES["auditor_3l"]` (`marketdata.view`, `valuation.view`,
`position.view`, `concentration.issuer.view`, `portfolio.view`, `snapshot.view`,
`reference.instrument.view`, `reference.issuer.view`, `reference.classification_assignment.view`;
executed at round 4, R3-05) → **the seven-ledger sweep or CRO-1's gate**, as an open SoD question the
owner answers, not one this gate ratifies by silence; (11) J-CRO-7's rolling-drawdown half: no run family
serves it as a series today (ROLLING_RISK v2 emits ONE 12-month MAX_DRAWDOWN point per fund over BOOK-1a's
year, Part 2.11) → **CRO-1's gate**, a decision between showing the one point as a number, amending the
line, or a client-side series over PORTFOLIO_RETURN rows under CTRL-039 (GOV-R-07).

---

## Part 7 — Different-engine verification (four Opus 5 lanes, 2026-09-18; folded by Fable 5.1)

Four lanes, 314 claims checked, **61 findings: 8 BLOCKING, 12 HIGH, 24 MED, 17 LOW**. Every finding was
re-read or re-executed here before its disposition; the evidence column names what was run or read. No
finding is deleted and no severity is lowered. **Folded 60, refuted 0, folded-in-part 1** (CRO-R9's
assertion that a 0.15 issuer cap binds on a GP is refuted by arithmetic and the rest of the finding is
folded). FEAS-9 is folded whole: four claims the lane could not execute become the carried-unverified
list below, and a fifth was discharged by execution at the fold. Where a finding changed a number or a decision, the disposition names the part it moved.

| Id | Sev | Lane | Disposition | Evidence |
|---|---|---|---|---|
| GOV-1 | BLOCKING | governance | FOLDED (Parts 2.3, 2.5, 3.20, 5 mutant 14) | Read `snapshot/service.py:3554-3615,3661`: after the MANUAL and REGRESSION queries the builder persists with no coverage assertion; young funds moved to PRIVATE segment memberships; positive coverage control replaces `residual_variance == 0` as the proof. Round 4 (R3-01): the membership alone fails the LOADINGS coverage gate, so a zero-weight public row rides beside it. Round 5 (R4V-01): that zero-weight row re-created the invisibility (no exposure row ⇒ absent from `instrument_ids`, `snapshot/service.py:3550` ⇒ in neither leg, MV 0); replaced by a NON-ZERO weight-1.0 sleeve-proxy loading. |
| GOV-2 | HIGH | governance | FOLDED (DS-B1b-4, Part 2.11) | Read `product_rebaseline_2026-09-17.md:377-378` "one desmooth, regression and promotion chain per private fund" and `personas_and_user_journeys.md:95` "for each private fund"; (b) now stated as a departure the owner ratifies. |
| GOV-3 | HIGH | governance | FOLDED (Part 5 sweep item 3, Part 2.6) | Read `control_matrix_skeleton.md:36,62` (already Operational; OPS-1 demo exercise recorded) and `limit/service.py:1033-1048` (no `limit.approve` check in the service); "no control moved". |
| GOV-4 | HIGH | governance | FOLDED (Part 2.13) | Read `entitlement/bootstrap.py:140-141,152,69` (`:71` corrected to `:69` at round 5, R4V-06) and `seed.py:163-186,236-241,323-326`; `auditor_3l` template holds `pacing.view`, not `commitment.view`; `commitment.view` now per-principal, auditor excluded; P17 reason restated on migration 0064 + the unknown-code refusal. Ground restated at round 4 (R3-05): the catalog's holder set, with the roster's nine pre-existing crossings carried out (Part 6 out (10)). |
| GOV-5 | HIGH | governance | FOLDED (Part 1 OUT, DS-B1b-9) | Read `:465` (DP-RB2-7 = NEW families) and `:384-385`; executed `REPRODUCIBLE_FAMILIES` lists VAR_BACKTEST and ES_BACKTEST; deferral relabelled a named departure needing the owner's amendment. |
| GOV-6 | HIGH | governance | FOLDED (Part 0.7, DS-B1b-3) | Read `risk/bootstrap.py:2840,2852-2853,2863`: the registered `v1` text says "of segment s"; builder non-conformant; fold routed through model governance, G2 stays no-scope. |
| GOV-7 | MED | governance | FOLDED (G2 header, DS-B1b-10) | Read `g2_slice_scope.json` `_why` ("rows currently entering build") and `requirements_backbone.md:242` clause (3); no_scope_reason now argues that test; executed gate `G2_EXIT=0` with the five figures matching. |
| GOV-8 | MED | governance | FOLDED (Part 3.14) | Read `test_demo_tenant_book.py:89-94,:100`: `:90` KeyError path, `:92` `1.0 <= v <= 10_000`, `:94` `abs(b/a - 1) < 0.15` per consecutive mark, `:100` face_value; exclusion predicate over all five with a non-empty check added. |
| GOV-9 | MED | governance | FOLDED (Part 0.20, Part 6 out (6) deleted) | Executed: 19 reproducible incl. DESMOOTHED_RETURN, PROXY_WEIGHT_ESTIMATE, PACING_PROJECTION, PURE_PRIVATE_FACTOR, COVARIANCE_PRIVATE, VAR; 2 unreproducible; P19 read at `claude_operating_instructions.md:602-615`. |
| GOV-10 | MED | governance | FOLDED (Part 2.8, Part 6 out (9); the roadmap edit landed at the ratification-diff fold, not in the planning commit) | Executed `Q2 business days 62 new 49 month-ends 3 non-month-end 59`; roadmap `:357` still read "about sixty-three" at `d676fc4` (GOV-R-01, CC-1 caught the promised-but-unrun edit); amended 2026-09-18 at the fold, re-checked against the working tree: `grep -c "sixty-two business days" delivery_roadmap.md` → 1. |
| GOV-11 | MED | governance | FOLDED (Parts 0.8, 2.5, 2.8) | Read `:384-385`; total VaR now runs on all three funds (+26), asserted `total == plain` on NL-GMA/NL-EFI; no departure. |
| GOV-12 | LOW | governance | FOLDED (G2 header, DS-B1b-11) | Read `requirements_backbone.md:173` REQ-PRV-003 Draft and `:244`; the flagging-vs-demonstration distinction stated. |
| GOV-13 | LOW | governance | FOLDED (Part 2.3) | `grep -rn "def register_var_unified_model"` → nothing; `risk/bootstrap.py:2915 def register_var_parametric_unified_model(`. |
| GOV-14 | LOW | governance | FOLDED (Part 2.6 table) | Arithmetic on the table's own numbers: seven rows strictly between; the asserted case named separately. Eight from round 4 (R3-03, the sector row). |
| GOV-15 | LOW | governance | FOLDED (Part 5 mutant 5) | Read `limit/models.py:129-131` (no positivity constraint) and `limit/service.py:201-206` (strict `>`); single variant at threshold = observed, oracle distinct from mutant 4. |
| FEAS-1 | BLOCKING | feasibility | FOLDED (Parts 0.21, 2.7, 3.19, 5 mutant 10) | Executed: `FX series key counts ... ('GBP','EUR'): 56` / `cross fx KeyError on first new date: 2026-04-01`; read `book.py:1418-1421` `for d in BOUNDARIES` and `seed.py:613` `rate=series[on]`. |
| FEAS-2 | HIGH | feasibility | FOLDED (Parts 0.5, 3.7, DS-B1b-4 (c)) | Read `snapshot/service.py:2590-2605` (`now.date()` fallback) and `pacing/service.py:191-194,204`; every pair carries a 2026-06-30 mark. |
| FEAS-3 | MED | feasibility | FOLDED (Part 0.8) | Read `snapshot/service.py:3554-3584` and `seed.py:658-660`: `manual_rows` never empty today, so the `:3574-3584` gate fires; PROBE B/C messages to be re-quoted from a re-run. |
| FEAS-4 | MED | feasibility | FOLDED (Part 2.4; re-folded at round 3, S-02) | Executed `PE 2019 age 7 ... terminal unfunded 7737809.375000 at t 12` under the draft shape; read `pacing_kernel.py:123-126`. The second fold's short schedule ending in 1.0 over-corrected (every mature first row called 100 %); both schedules are now as long as L with 1.0 only at t = L, executed for all twelve pairs at round 3: `terminal_unfunded 0.000000` and a partial first call on every pair. |
| FEAS-5 | MED | feasibility | FOLDED (Parts 2.4, 2.10; re-folded at round 3, S-01) | The draft-shape transcript (`DL 2021 age 5 ... unfunded_end 0.000000`) is superseded: under the folded schedules the oldest PE fund's first row is `call 500000.000000 unfunded_end 9500000.000000 identity 10000000.000000` (Executed, round 3) and no roster pair is degenerate; the suite asserts `unfunded_end > 0` on the golden's pair. |
| FEAS-6 | MED | feasibility | FOLDED (Part 2.6 proof, Part 5 mutant 5) | Read `limit/service.py:201-206`; the assertion no longer divides by the threshold; the zero variant dropped. |
| FEAS-7 | LOW | feasibility | FOLDED (Part 2.2) | Read `desmoothing_service.py:208-211` (three-char) vs `:221-225` (multi-currency) and `proxy_weight_service.py:240-242`. |
| FEAS-8 | LOW | feasibility | FOLDED (Part 3.10) | Read `test_aggregation_census.py:116-120`: `(module, function, kind): (count, class)`; `generate_paths` pinned at 1; no `demo_tenant.seed` entry. |
| FEAS-9 | LOW | feasibility | FOLDED (the carried-unverified list below) | The lane's executed confirmations (G2/G5 exits, calendar, grid, ages, goldens under the extended date set, time-bomb fence, `alembic heads`, baseline `14 passed`) are accepted; four unexecuted claims are bound to the first moment each becomes executable, and the fifth (CTRL-018's census) was discharged by execution at the fold (Part 0.20). |
| C-01 | BLOCKING | citations | FOLDED (Part 0.11) | Read `w20_book1a_slice_record.md:44-53`: `:44-45` is the home-currency finding, `:49-53` is TE currency-only. |
| C-02 | BLOCKING | citations | FOLDED (Part 2.5) | `grep -n residual_variance test_var_unified_e2e.py` → 23, 492, 525, 545, 546; `:487` is `covariance_run_id`. |
| C-03 | BLOCKING | citations | FOLDED (Part 0.8) | Read `var_service.py:385-395`: a docstring on pins that are present; claim replaced by an executed assertion `total == plain`. |
| C-04 | BLOCKING | citations | FOLDED (Part 2.2, Part 3.18) | Read `desmoothing_service.py:208-211` and `:221-225`. |
| N-01 | HIGH | citations | FOLDED (Parts 0.21, 2.1, 2.4) | Executed `NL-PMF reserve marked at YE 45678907.400000 / start-price face 45598600.00`; the script reproduces the GMA golden `155681069.672680`. |
| N-02 | MED | citations | FOLDED (Part 2.9) | Read record `:60` and `:103` (33 s), `:98-100` (census rows) vs `:101-103` (295.7 s), `ci.yml:779-780` (~6 minutes); 120 s dropped, CI projection bracketed. |
| C-05 | MED | citations | FOLDED (Part 0.6) | Read `seed.py:1228-1240`: `_register_models` at 1234, `_run_return_chains` at 1238. |
| C-06 | MED | citations | FOLDED (Part 2.5) | Read `var_service.py:684-691` (the 2x2 `_VAR_FAMILIES` table), `:840-846` (`build_snapshot_fn` at `:840`, the two run ids at `:845-846`) and `:1206-1216` (the three unified resolves). Cell re-pointed at round 3 (S-08). |
| C-07 | MED | citations | FOLDED (Part 2.1) | Read `var_service.py:445-460`: the refusal is `:447-453`. |
| C-08 | MED | citations | FOLDED (Part 2.1) | Read `book.py:266-296` (both specs; sector/country on `IssuerSpec`); `grep _seed_instruments` → `seed.py:501,1223`. |
| N-03 | MED | citations | FOLDED (G2 header, DS-B1b-10) | Executed the eight-row probe on a scratch copy: `slice scope : 8 / blocking : 8`, 7 never asked + LIM-002 lapsed, `G2_PROBE_EXIT=1`; ledger line 52 read. |
| N-04 | MED | citations | FOLDED (Part 2.5) | Arithmetic from the remit's own matrix: 13 × 2 + 59 = 85. |
| C-09 | MED | citations | FOLDED (DS-B1b-3 (C)) | Read `var_service.py:1426-1434`: `scope_portfolio_id=pinned_exposure_run.scope_portfolio_id` at `:1428`. |
| C-10 | LOW | citations | FOLDED (Part 0.7) | Read `snapshot/service.py:3574-3575`. |
| C-11 | LOW | citations | FOLDED (Part 0.13) | Read `test_demo_tenant_seed.py:86-105`: `_june_var` at `:91`, `.scalar_one()` at `:104`. |
| C-12 | LOW | citations | FOLDED (Part 2.9) | Read `deploy.sh:27-29` (`:28` blank, `:29 set -euo pipefail`); `grep -c timeout-minutes ci.yml` → 0. |
| C-13 | LOW | citations | FOLDED (Part 0.14) | Read `delivery_roadmap.md:359`: the two gaps named inline, no pointer. |
| N-05 | LOW | citations | FOLDED (DS-B1b-4 (b)) | Read `private_factor_service.py:277-281` and `desmoothing_service.py:203-206`; no mature vintage on the grid's first date. Extended at round 4 (R3-04) to `book.BOUNDARIES[0]`. |
| N-06 | LOW | citations | FOLDED (Part 2.4) | Executed hand fraction `0.2220385...`; same fix as FEAS-4. |
| C-14 | LOW | citations | FOLDED (Part 2.3) | Read `proxy_weight_service.py:642-644` "NOT read from the run" and `:683`. |
| C-15 | LOW | citations | FOLDED (DS-B1b-4 (a)) | Read `test_data_realism.md:37-38`: names, counts, totals; no reserve-to-unfunded clause; stated as this remit's judgment. |
| CRO-R1 | BLOCKING | CRO realism | FOLDED (Part 2.3, DS-B1b-15, Part 3.21, Part 5 mutant 11) | Read `book.py:151-157,410,434-435`, `factor_service.py:481`, `var_service.py:1245-1250`; and `book.py:1394-1405` (one rng, factors then marks), which is why the new factors need their own stream. |
| CRO-R2 | BLOCKING | CRO realism | FOLDED (Part 2.2, Part 5 mutant 12) | Read `desmoothing_kernel.py:46-48` and `snapshot/service.py:2419-2431`; flow-free value index stated and banded. |
| CRO-R3 | HIGH | CRO realism | FOLDED (Part 2.6) | Executed `NL-EFI sector O 0.647615 / country IT 0.158438 / DE 0.348986`; read `book.py:325-329,343`; breach moved to an Italy `SHARE` bucket limit (`limit/models.py:74-79`; `:78` corrected at round 5, R4V-05), not `MAX_SHARE_COUNTRY_OF_RISK` (binds on DE). |
| CRO-R4 | HIGH | CRO realism | FOLDED (Part 2.6, DS-B1b-5) | Executed `NL-GMA issuer UST 0.249188 / sector O 0.249188 / CR5 0.549503`; strictly-between case moved to `CR_5_ISSUER` at 0.65 (84.5 %); sovereign issuer cap at 0.35. |
| CRO-R5 | HIGH | CRO realism | FOLDED (Parts 0.11, 2.6, Part 1) | The remit's own `TE 0E-12` on single-currency funds; nine limits at that fold (ten from round 4, R3-03), no TE limit on NL-EFI/NL-PMF. |
| CRO-R6 | HIGH | CRO realism | FOLDED (Part 2.6, DS-B1b-8 (D), Part 5 mutant 13) | Read `models.py:177`, `calc/reads.py:101-103`, `service.py:613`; three month-end evaluations with injected instants on or before 2026-06-30. |
| CRO-R7 | HIGH | CRO realism | FOLDED (Part 2.2) | Read `book.py:151` sigma 0.0090; volatility bands, smoothing ratio and beta band made acceptance. |
| CRO-R8 | MED | CRO realism | FOLDED (Part 2.4) | The sizing triple implied NAV/paid-in 1.09 with no distributions; DPI/TVPI bands and a seven-column table added. |
| CRO-R9 | MED | CRO realism | FOLDED IN PART (DS-B1b-4, Parts 2.1, 2.6) | Roster raised to twelve and a round 0.25 cap; REFUTED sub-claim: executed `NL-PMF issuer UST 0.864270` on the reserve alone and 39.48M / 220.7M = 17.9 % after 175M private NAV, above any plausible GP, so a 0.15 cap binds on UST and the "DETAIL row names a GP" assertion cannot hold with BOOK-1a's reserve fixed; the limit is named as including the reserve instead. |
| CRO-R10 | MED | CRO realism | FOLDED (Parts 0.21, 2.1, 2.4) | Same execution as N-01; both figures quoted and labelled. |
| CRO-R11 | MED | CRO realism | FOLDED (Part 2.1) | Read `test_data_realism.md:34-41`; naming and strategy-focus classification convention plus a fixture-pattern assertion. |
| CRO-R12 | MED | CRO realism | FOLDED (Part 2.3, Part 5 mutant 8) | Read `marketdata/models.py:743-746` (no periodicity column) and `:197` (factor frequency DAILY); magnitude band and the two-frequency fact recorded. |
| CRO-R13 | MED | CRO realism | FOLDED (Part 2.3, DS-B1b-15) | Read `book.py:152` (`RATES_USD_10Y`, a yield change); direct lending regresses on `CREDIT_HY_TR` + `RATES_UST_TR`, both total-return indices (F-01). |
| CRO-R14 | MED | CRO realism | FOLDED (Part 2.2, DS-B1b-4 (b)) | Same reads as N-05; J-curve assertion on the youngest mature fund. |
| CRO-R15 | LOW | CRO realism | FOLDED (Part 2.6) | Read `limit/service.py:150-152,176` (`te_value` FRACTION; `name` in `_UPDATABLE`). |
| CRO-R16 | LOW | CRO realism | FOLDED (Part 2.4) | Read `pacing/service.py:204`, `pacing_kernel.py:117-120`; four vintages on 31 December (S-05), the convention stated. |

**Carried-unverified (FEAS-9), each bound to the first moment it becomes executable; none may be
quoted as "Executed:" at the gate without a re-run:** (a) PROBES A-D and the `held pure-private
segments ... absent from the pinned Omega_pp run` transcript, and (b), split at round 4 (R3-02): (b1) values ALREADY reproduced here and
not carried — `0.254149` (NL-EFI max issuer BUND, a book fact, re-executed at round 4 with the list
below), `464184.575474` (a committed constant, `test_demo_tenant_book1a_pg.py:57`
`GOLDEN_EFI_VAR_PARAMETRIC_EUR`, re-derived by `derive_northlight_var.py` at Part 0.13) and
`1734274.488757` (executed over HTTP on the deployed stack, `purpose_mismatch_remediation_plan.md:51`
and roadmap `:355`, both cited by this remit); (b2) values that genuinely need a seeded database —
`0.000286895819` (NL-GMA tracking error), `TE 0E-12` on NL-EFI and NL-PMF, and NL-PMF's derived VaR
threshold → asserted at the first seed run on SQLite; the root-scoping half is confirmed
by reading (`seed.py:966-967`, `root = refs.fund_ids[fund.code]` / `exp_run = _run_exposure(session, refs, root, ...)`; `:969` is the ALLOCATION factor-exposure call, S-07). (c) `rm-then-rm raised LimitSodError` / `pm approving went ACTIVE` → the
code is confirmed person-level by reading (`limit/service.py:1041-1049`); the transcript is re-run at
the first seed run. (d) The in-stack projection (now about 198 s) → the Part 5 in-stack measurement.
Discharged at the fold, not carried: CTRL-018's census coverage, answered by execution (Part 0.20). The book-level
numbers in this fold (`0.249188`, `0.647615`, `0.549503`, `0.158438`, `0.254149`, `0.348986`, `0.864270`,
`0.147878`, `45678907.400000`) were executed
here over `book.generate_paths()` (re-executed at round 4, `r4_conc_EXIT=0`: `NL-GMA total
155681069.672680 USD` / `issuer max 0.249188 UST CR5 0.549503` / `NL-EFI issuer max 0.254149 BUND`,
sector `O 0.647615`, countries `DE 0.348986 ... IT 0.158438` / `NL-PMF total 45678907.400000 USD`,
`issuer max 0.864270 UST`) and reproduce the GMA golden, so they are book facts, not database
facts; the engine's stored values are re-quoted in the record.

**What the fold changed at Tier 3:** DS-B1b-4 (b) is now a named departure from the ratified
"per private fund" clause; DS-B1b-8 gains and recommends (D); DS-B1b-9 (C) is a named departure needing
the owner's amendment; DS-B1b-15 is new; DS-B1b-14's floor is fourteen (fifteen from round 4, sixteen from round 5, SEVENTEEN from round 8, V7-02 — the ratified floor; an eighteenth mutant added at the ratification-diff fold, FR-02); the limits grid is nine rows (ten from round 4, R3-03). *(Tallies in this paragraph are dated to the round that set them; the current figures are Part 2.6, Part 2.8 and DS-B1b-14 — FR-05.)*

### Fold check (Opus 5, 2026-09-18): 10 findings

A second different-engine pass over the folded text: 1 BLOCKING, 1 HIGH, 5 MED, 3 LOW. All ten folded,
none refuted. Every locator in the FACTORS block was off by one; the five `book.py:` sites F-07 and F-08
name were corrected, and the Treasury-reserve block is `:1118-1162`, not `:1118-1160` (corrected at Parts
0.21 and 2.4). This header first claimed "fifteen sites checked"; the re-walk covered only the sites
F-07 and F-08 name, and the remit's distinct `book.py:` locators are measured at round 3 (S-10, twenty
numbered sites; the C-06 cell was also stale until round 3, S-08).

| Id | Sev | Disposition | Evidence |
|---|---|---|---|
| F-01 | BLOCKING | FOLDED, option (i) (Part 2.3, DS-B1b-15 (A) and (C), Part 2.8, CRO-R13) | The first fold wrote PE and direct lending as the SAME two factors, so the union was two, the mint 20, and `RATES_UST_TR` was fitted to nothing; direct lending is now `CREDIT_HY_TR` + `RATES_UST_TR`, union three, 30 minted returns, which is what CRO-R1's fold intended (a rate leg on the credit sleeve). Executed `len(book.FACTORS) == 8`. |
| F-02 | HIGH | FOLDED (Part 2.1, CRO-R9 disposition) | Part 2.1 said eight funds, five mature; DS-B1b-4 and the Part 2.8 census say twelve, eight mature. Part 2.1 now reads twelve (seven PE, five direct lending). |
| F-03 | MED | FOLDED (Parts 2.8, 2.9, DS-B1b-9a, FEAS-9 (d)) | Re-added after F-01 and F-10: 2,695 + 147 + 1,260 + 96 + 626 + 30 + 16 + 2 + 12 + 12 + 110 + 8 + 9 + 6 + 72 = 5,101; total 11,206 *(the round-2 tally; superseded at round 4 by 5,106 / 11,211, R3-01 and R3-03 — FR-05)*. In-stack 87 + 91 + 20 ≈ 198 s; host 296 + 318 + 77 ≈ 691 s. |
| F-04 | MED | FOLDED (Part 7 header) | The table holds one FOLDED IN PART row (CRO-R9) and 60 FOLDED; header now 60 / 0 / 1 and FEAS-9 is out of the gloss. |
| F-05 | MED | FOLDED (front matter, FEAS-9 list and evidence cell) | Item (e) was discharged in its own paragraph; four claims remain (a)-(d), the fifth is a one-line "discharged at the fold" note. |
| F-06 | MED | FOLDED (Part 3.14, GOV-8 evidence) | Read `test_demo_tenant_book.py:94` `assert abs(b / a - 1) < 0.15` (the per-step fence a +20 % quarterly NAV step would hit) and `:100` `v <= inst.face_value`; the exclusion predicate now names `:90`, `:91`, `:92`, `:94` and `:100`, and the private band carries no per-step check. |
| F-07 | MED | FOLDED (Parts 2.2, 2.3, DS-B1b-15 (C), CRO-R1, CRO-R7, CRO-R13) | `grep -n`: `:150` FX_GBP, `:151` MKT_GLOBAL_EQ, `:152` RATES_USD_10Y, `:157` CREDIT_HY, `:158` is `)`. All FACTORS-block locators moved by one. |
| F-08 | LOW | FOLDED (Parts 0.21, 2.3, 2.4, 2.5, 2.7, 3.21, FEAS-1 evidence) | `grep -n`: `rate=series[on]` is `seed.py:613`; `noise = rng.gauss` is `book.py:1438`; the run ids are `var_service.py:845-846`, so Part 2.5 cites `:840-846`. |
| F-09 | LOW | FOLDED (Part 2.9) | `ci.yml:779-780` "~6 minutes ... 636 runs": 360 × 1,506 / 636 ≈ 852 s, and the denominators of the two brackets are now stated (597 in-stack, 636 in CI). |
| F-10 | LOW | FOLDED (Part 2.8) | Executed `len(book.RETURN_DAYS) == 313` (2025-04-01..2026-06-30); 2 × 313 = 626, folded into F-03's total. |

### Fold check round 3 (Opus 5, 2026-09-18): 10 findings

A third different-engine pass over the second fold: 1 BLOCKING, 3 HIGH, 2 MED, 4 LOW. All ten folded,
none refuted. The rule this round, because the two earlier folds each shipped a claim that was false
under the fold's own change: every behavioural or numeric statement written or changed at this fold was
executed or grep'd under the FOLDED parameters and the transcript is quoted beside the claim; no
draft-shape transcript supports a folded claim. The one sentence that could not be re-executed (the
first draft's "campaign shape leaves 41015.625000 unfunded at age 12"; `grep -rn rc_schedule
demo/campaign.py` → nothing, so its parameters are not recoverable from that file) was deleted from
Part 2.4 rather than carried.

| Id | Sev | Disposition | Evidence (executed at round 3) |
|---|---|---|---|
| S-01 | BLOCKING | FOLDED (Parts 2.4, 2.10 (c), FEAS-5 row) | `project_commitment` on all twelve roster pairs under the folded schedules, `KERNEL_EXIT=0`: oldest PE `call 500000.000000 unfunded_end 9500000.000000 identity 10000000.000000`; no pair has `unfunded_end 0` in its first row; the golden stays on PE 2019-06 with an added `unfunded_end > 0` assertion. |
| S-02 | HIGH | FOLDED (Part 2.4, FEAS-4 row) | Read `pacing_kernel.py:123-126` (repeat from `len(rc_schedule)`) and `:192-193` (schedule longer than L refused); `v1-pe` now twelve entries, `v1-credit` eight, tail 0.05 mid-life, 1.0 only at t = L; every pair `terminal_unfunded 0.000000` at t = L; identity cited to `pacing/bootstrap.py:6,308-310`. |
| S-03 | HIGH | FOLDED (Part 2.9) | `sed -n 775,782p ci.yml`: `:779` `# The suite seeds the tenant end to end through the real orchestrator (~6 minutes measured` / `:780` `# locally: 636 runs, ~5,800 audited captures)`, inside the BOOK-1a step's comment block; the bracket is kept and labelled a stale local figure. |
| S-04 | HIGH | FOLDED (Part 3.14) | `grep -n "BOUNDARIES\|len(book.INSTRUMENTS)"` over the two seed suites: `test_demo_tenant_seed.py:47,135,143,144`, `test_demo_tenant_book1a_pg.py:64,207,232,233,241`; each listed with its amendment (union-or-grid date set; per-date count split 67 / 8; `:207` holds at 67 and is read only). 55 × 105 + 12 × 105 + 8 × 12 = 7,131 marks. |
| S-05 | MED | FOLDED (Parts 2.4, 4 sub-questions, CRO-R16 row) | The roster's twelve vintages counted: eight on 30 June, four on 31 December (PE 2019-12, PE 2021-12, DL 2021-12, DL 2024-12); executed window for one: `PE 2019-12-31 age 6 rows 6 t0 7 window 2025-12-31..2026-12-31`. Part 2.4's first clause now "a quarter end, mostly 30 June". |
| S-06 | MED | FOLDED (Part 2.8) | A snapshot line added under the run table: 85 = 13 × 2 + 59, stated as VAR_INPUT snapshots so the run total 1,506 and the capture total (11,206 at round 3; 11,211 from round 4, R3-01 and R3-03 — FR-05) were left unchanged by the snapshots. |
| S-07 | LOW | FOLDED (FEAS-9 item (b)) | `sed -n 964,970p seed.py`: `:966` `root = refs.fund_ids[fund.code]`, `:967` `exp_run = _run_exposure(session, refs, root, ...)`, `:969` `alloc = run_factor_exposure(`. |
| S-08 | LOW | FOLDED (C-06 row, fold-check header) | `grep -n` in `var_service.py`: `_VAR_FAMILIES` `:686-691` under its comment at `:684-685`; `build_snapshot_fn` `:840`; run ids `:845-846`; unified resolves `:1206-1216`. Header now states the re-walk covered the F-07/F-08 sites only. |
| S-09 | LOW | FOLDED (Part 2.6, CRO-R3 row) | `sed -n 322,330p book.py`: `:324` UST, `:325` BUND, `:326` OAT, `:327` BTP, `:328` BONOS, `:329` DSL, all section O; the euro sovereigns are `:325-329`. |
| S-10 | LOW | FOLDED (fold-check header) | ``grep -o '`book\.py:[0-9-]*' \| sort -u`` → 21 lines, one of them the header's bare `book.py:` token, so **twenty** distinct numbered `book.py:` sites (the verifier's twenty-one counted that token); the header no longer claims fifteen. |

Re-added after the fixes (Executed, round 3; *superseded at round 4 — the current tally is the round-5
block below, FR-05*): captures 2,695 + 147 + 1,260 + 96 + 626 + 30 + 16 + 2 +
12 + 12 + 110 + 8 + 9 + 6 + 72 = 5,101, total 6,105 + 5,101 = 11,206; new runs 767 + 111 + 31 = 909,
total 1,506; Part 2.9: 0.10 × 909 = 90.9 and 0.004 × 5,101 = 20.4, so 86.7 + 90.9 + 20.4 = 198.0 s
in-stack; 0.35 × 909 = 318.15 and 0.015 × 5,101 = 76.5, so 295.7 + 318.15 + 76.5 = 690.35 ≈ 691 s
from the host; CI bracket 87 × 1,506 / 597 = 219.5 s to 360 × 1,506 / 636 = 852.5 s.

### Fold check round 4 (Opus 5, 2026-09-18): 8 findings

A fourth different-engine pass over the round-3 text: 1 BLOCKING, 4 MED, 3 LOW. All eight folded, none
refuted. The round-3 rule held again and every statement written or changed here was executed or
grep'd NOW under the folded parameters, with the transcript quoted beside the claim: the pacing kernel
was re-run on all twelve roster pairs under the folded `v1-pe` / `v1-credit` schedules (every round-3
line reproduced character for character, `r4_kernel_EXIT=0`), the book concentration facts were
re-executed over `book.generate_paths()` (`r4_conc_EXIT=0`, the GMA golden `155681069.672680`
reproduced), and the roster-versus-catalog check ran against `ROLE_TEMPLATES` and `seed._PRINCIPALS`
(`r4_roles_EXIT=0`). One correction to the verifier's own reading: `LOADING_FACTOR_FAMILIES` holds
NINE families (`marketdata/models.py:176-186`), not the six R3-01 lists; the conclusion (no PRIVATE)
stands. Two changes move Tier-3 text: a tenth limit (the sector row the ratified enumeration names) and
a fifteenth mutant.

| Id | Sev | Disposition | Evidence (executed at round 4) |
|---|---|---|---|
| R3-01 | BLOCKING | FOLDED (Parts 0.6, 2.3, 2.8, 3.3, 3.22, DS-B1b-4 (b), DS-B1b-14, Part 5 mutant 15, GOV-1 row) | `grep -n`: `snapshot/service.py:894-914` pins `Factor.factor_family.in_(LOADING_FACTOR_FAMILIES)`; `factor_service.py:414` `def _assert_full_coverage`, `:546` the pre-create block, `:650` the call, `:470-471` `if pin.weight == 0: continue`; `seed.py:686-687` the zero-weight home-currency row. Executed: `LOADING_FACTOR_FAMILIES (...) len 9 PRIVATE in False`. Every young fund now carries a zero-weight `FX_USD` MANUAL row beside its PRIVATE membership; captures +4. SUPERSEDED IN PART at round 5 (R4V-01): the coverage row must be NON-ZERO, or the fund emits no exposure row and is invisible to the unified builder; now a weight-1.0 sleeve-proxy loading, captures still +4. |
| R3-02 | MED | FOLDED (FEAS-9 paragraph, split (b1)/(b2)) | Re-executed over `book.generate_paths()`: `NL-EFI issuer max 0.254149 BUND`; read `test_demo_tenant_book1a_pg.py:57` `GOLDEN_EFI_VAR_PARAMETRIC_EUR = Decimal("464184.575474")`; read `purpose_mismatch_remediation_plan.md:51` and roadmap `:355`, both `var_value 1734274.488757`. Only `0.000286895819`, `TE 0E-12` and NL-PMF's derived threshold stay carried. |
| R3-03 | MED | FOLDED (Parts 0.11, 1, 2.6 grid and prose, 2.8, 2.11, DS-B1b-5, Part 5 smoke, GOV-14 and CRO-R5 rows) | Read `product_rebaseline_2026-09-17.md:380-381` "sector and issuer concentration" and roadmap `:357`. Executed: `NL-GMA sector C share 0.147878 ex-cash 0.147878` / `sector K share 0.212638 ex-cash 0.093806` (the custodian cash line `NLUSD-CASH` is 0.118833 of the FUND, which is 56 % of section K; the denominator corrected at round 5, R4V-03) / `C/0.20 = 73.9 %`. Tenth limit `NL-GMA-MFG`, SOFT 0.20 on section C; ten limits, eight strictly between, health ten rows / eight IN_APPETITE; the "Sector and country limits" sentence now names both rows. |
| R3-04 | MED | FOLDED (DS-B1b-4 (b) N-05 rule, Part 2.2, N-05 row) | Executed: `BOUNDARIES[0] 2025-06-30 | 2025-09-30 in BOUNDARIES True | len 56`. Rule extended to `book.BOUNDARIES[0]`; the DL 2025-06-30 vintage keeps its date and carries a same-day first DRAWDOWN of at least 1,000,000 USD so its first mark is the paid-in amount inside the 1M to 100M band. |
| R3-05 | MED | FOLDED (Part 2.13, Part 6 out (10), GOV-4 row) | Executed against `ROLE_TEMPLATES` and `seed._PRINCIPALS`: `auditor_3l template: pacing.view True | commitment.view False`; `northlight-auditor ... grants 22 absent-from-template 9: ['concentration.issuer.view', 'marketdata.view', 'portfolio.view', 'position.view', 'reference.classification_assignment.view', 'reference.instrument.view', 'reference.issuer.view', 'snapshot.view', 'valuation.view']`; `cro_2l in ROLE_TEMPLATES False`, `portfolio_manager_1l in ROLE_TEMPLATES False`. Decision kept, ground moved to the catalog, the nine carried out. |
| R3-06 | LOW | FOLDED (Part 2.4) | Executed `project_commitment` on PE 2019-06-30 under `v1-pe`: identities `['10000000.000000', '9500000.000000', '9025000.000000', '8573750.000000', '8145062.500000']`, `terminal_unfunded 0.000000 at t 12`; the sentence now says every quoted FIRST row's identity is the opening unfunded. |
| R3-07 | LOW | FOLDED (Part 2.3 acceptance band) | Read `factor_service.py:470-471` (a zero-weight pin emits no row) and `snapshot/service.py:894-914` (PRIVATE rows never pinned): the numerator is mature-only by construction; both sides now pinned to the eight mature instruments by name. RESTATED at round 5 (R4V-01): the young funds now DO emit rows, so the band is mature-only by instrument-id selection and each young fund carries an exact 1.0 × NAV assertion. |
| R3-08 | LOW | FOLDED (Parts 0.18, 3.6, N-05 row) | `sed -n 275,284p private_factor_service.py`: `:277` `elif signature != interval_signature:`, `:278` `raise PurePrivateFactorInputError(`, `:279-280` the message, `:281` `)`, `:282` `members[instrument_id] = tuple(member_periods)`. All three sites now read `:277-281`. |

Re-added after the round-4 fixes (Executed, `r4_edit.py`): captures 2,695 + 147 + 1,260 + 96 + 626 + 30 + 16 +
2 + 12 + 4 + 12 + 110 + 8 + 10 + 6 + 72 = 5,106, total 6,105 + 5,106 = 11,211; new runs 767 + 111 + 31 = 909,
total 1,506 (no run count moved: a coverage row and a limit are captures, not runs); Part 2.9: 0.10 × 909 = 90.9 and
0.004 × 5,106 = 20.424, so 86.7 + 90.9 + 20.424 = 198.0 s in-stack (still ≈ 198 s); 0.35 × 909 = 318.15 and
0.015 × 5,106 = 76.59, so 295.7 + 318.15 + 76.59 = 690.44 s from the host (the rounded addends
296 + 318 + 77 = 691 stay quoted; unrounded 690.4); CI bracket 87 × 1,506 / 597 = 219.5 s to 360 × 1,506 / 636 = 852.5 s, unchanged.

### Fold check round 5 (Opus 5, 2026-09-18): 6 findings

A fifth different-engine pass over the round-4 text: 1 BLOCKING, 1 HIGH, 1 MED, 3 LOW. All six folded,
none refuted. The round-3 rule held again: every statement written or changed here was executed or
grep'd NOW under the folded parameters and the transcript is quoted beside the claim (the pacing kernel
on all twelve roster pairs under the folded `v1-pe` / `v1-credit` schedules, `R5F_KERNEL_EXIT=0`, every
round-4 line reproduced character for character including the per-row identities; the book
concentration facts over `book.generate_paths()`, `R5F_CONC_EXIT=0`, the GMA golden `155681069.672680`
reproduced; the factor families, `R5F_FAM_EXIT=0`; the census arithmetic, `R5F_ARITH_EXIT=0`). One
design change: the young funds' coverage row is a NON-ZERO weight-1.0 sleeve-proxy loading, because the
round-4 zero-weight row re-created the very invisibility GOV-1 was folded to prevent (R4V-01). One
Tier-3 change: DS-B1b-14's floor is sixteen (mutant 16). No count moved: captures 5,106, runs 909.

| Id | Sev | Disposition | Evidence (executed at round 5) |
|---|---|---|---|
| R4V-01 | BLOCKING | FOLDED (Parts 0.6, 2.3, 2.5, 2.8, 3.3, 3.22, DS-B1b-4 (b), DS-B1b-14, Part 5 mutants 15-16, GOV-1, R3-01 and R3-07 rows) | Read `factor_service.py:455-456,470-471,504` (a zero-weight pin emits no row and the post-loop `continue` skips the indicator fallback); `snapshot/service.py:3511,3550,3559,3586,3609-3614` (everything keyed off `exposure_rows`); `var_service.py:518-555,1245-1250`; `risk/bootstrap.py:2852-2857,2863`. Executed (`R5F_FAM_EXIT=0`): `MARKET in True | CREDIT_SPREAD in True | PRIVATE in False`; `MKT_GLOBAL_EQ family ['MARKET'] | CREDIT_HY family ['CREDIT_SPREAD']`. The young row is now a weight-1.0 MANUAL loading on the sleeve's primary factor; mutant 15 = weight to zero, mutant 16 = row dropped; floor sixteen; captures unchanged at 4 for the four rows. |
| R4V-02 | HIGH | FOLDED (Parts 0.4, 2.3, 2.5, 3.4, DS-B1b-1) | Read `var_service.py:567-577` ("or ``None`` when there is nothing to measure") and `:1253-1293` (`proxy_weights` from `regression_mapping_raw`); `snapshot/service.py:3378-3395` (the total builder pins every REGRESSION row) against `:3612-3613` (the unified builder skips a member's); `risk/bootstrap.py:2856-2857,2923`. The `= 456` assertion moved to NL-PMF's VAR_PARAMETRIC_TOTAL row; the unified row asserts `estimate_age_days is None`; the unified policy is declared as required and inert. |
| R4V-03 | MED | FOLDED (Part 2.6, R3-03 row) | Executed over `book.generate_paths()` (`R5F_CONC_EXIT=0`): `NL-GMA total 155681069.672680 USD` / `NL-GMA sector K share 0.212638 ex-cash 0.093806` / `NLUSD-CASH issuer Harborside Trust Company | share of FUND 0.118833 | share of section K 0.558849 = 55.9 %` / `check 0.118833/0.212638 = 0.5589`. Both sentences now read "0.118833 of the fund, which is 56 % of section K". |
| R4V-04 | LOW | FOLDED (Part 3.14) | Re-ran `grep -n "BOUNDARIES\|len(book.INSTRUMENTS)"` over both suites: nine hits, `test_demo_tenant_seed.py:47,135,143,144` and `test_demo_tenant_book1a_pg.py:64,207,232,233,241`; eight amended, `:207` read only; the headline now says eight plus `:207`. |
| R4V-05 | LOW | FOLDED (Part 2.6, CRO-R3 row) | `sed -n 72,82p limit/models.py`: `:74` `CheckConstraint(`, `:75-76` the CONCENTRATION branch (`dimension_kind IS NOT NULL AND denominator_basis IS NOT NULL` only), `:77-79` the non-concentration branch with `AND bucket_code IS NULL AND issuer_id IS NULL AND scheme_family IS NULL` at `:78`, `:80` `name="concentration_shape"`. Cited as `:74-79` with the admitting branch named. |
| R4V-06 | LOW | FOLDED (Part 2.13, GOV-4 row) | `grep -n "BLOCKING SoD defect"` → `entitlement/bootstrap.py:69`; `:71` is `and granting it to auditor_3l (which the demo does) would have handed the 3L`. Cited as `:68-72`, label at `:69`. |

Re-added after the round-5 fixes (Executed, `r5f_arith.py`, `R5F_ARITH_EXIT=0`): captures 2,695 + 147 +
1,260 + 96 + 626 + 30 + 16 + 2 + 12 + 4 + 12 + 110 + 8 + 10 + 6 + 72 = 5,106, total 6,105 + 5,106 =
11,211 (the four young-fund rows change shape, not count); new runs 767 + 111 + 31 = 909 (59 + 177 × 4 =
767; 39 + 72 = 111; 8 + 8 + 2 + 1 + 12 = 31), total 1,506; marks 55 × 105 + 12 × 105 + 8 × 12 = 7,131;
Part 2.9: 0.10 × 909 = 90.9 and 0.004 × 5,106 = 20.424, so 86.7 + 90.9 + 20.424 = 198.024 s in-stack
(≈ 198 s); 0.35 × 909 = 318.15 and 0.015 × 5,106 = 76.59, so 295.7 + 318.15 + 76.59 = 690.44 s from the
host (the rounded addends 296 + 318 + 77 = 691 stay quoted); CI bracket 87 × 1,506 / 597 = 219.5 s to
360 × 1,506 / 636 = 852.5 s, unchanged.

### Fold check round 6 (Opus 5, 2026-09-18): 6 findings — folded by hand (Fable 5.1), each site re-read

| Id | Severity | Disposition | Evidence |
|---|---|---|---|
| V5-01 | HIGH | FOLDED (DS-B1b-3 (B); Part 2.3) | `_build_p_vector(manual_mapping_raw, mv_by_instrument)` at `var_service.py:518-520` sees only `proxy_mapping_content` (`serialize.py:392-402`, no family). The second site was restated at round 6 as an Omega_pp-diagonal filter, then DROPPED at round 7 (V6-03): the filtered query is the only source of the p vector's rows and `:3580-3585` already refuses off-diagonal segments, so it could never fire. |
| V5-02 | MED | FOLDED (Part 2.5) | Part 2.8 says `8 x 2 = 16`; the sentence now says sixteen rows, one cited run per fund; the one-cited-run refusal is the TOTAL builder's `:3398-3409` (`:3622-3627` is the unified builder's and never runs for a segment member, V6-02). |
| V5-03 | MED | FOLDED (Part 3 fence 22) | `factor_service.py:417-422`: "only the total ABSENCE of rows is the refusal". Exact-one is asserted on the four young funds only. |
| V5-04 | LOW | FOLDED (Parts 0.7, 0.8) | `seed.py:658-660` is the signature and docstring; the zero-weight row is `:686-687` (`Decimal("1") if foreign else Decimal("0")`). |
| V5-05 | LOW | FOLDED (Part 2.6) | `limit/models.py:77-79` is the non-concentration branch; `:78` is the line that forbids the bucket, issuer and scheme columns. |
| V5-06 | LOW | FOLDED (Part 2.4) | `pacing_kernel.py:125` `idx = min(age, len(rc_schedule)) - 1`; `:152` `call = _q(rc * unfunded)`; `:162` `unfunded = _q(unfunded - call)`. The scale-free sentence added; the anchor labelled an illustration. |

### Fold check round 7 (Opus 5, 2026-09-18): 5 findings — folded by hand (Fable 5.1), each site re-read

| Id | Severity | Disposition | Evidence |
|---|---|---|---|
| V6-01 | HIGH | FOLDED (Part 2.3; Part 3 fence 22) | `seed.py:681-687` loops every `book.INSTRUMENTS` spec and writes `FX_{currency}` at weight 0 for a base-currency instrument; `_seed_loadings` is called unconditionally at `:1230`. Decided: an explicit predicate skips private specs; "exactly one" on the young funds stands; the suite asserts no private instrument carries an `FX_` loading; R3-01's premise restated as conditional on the skip. |
| V6-02 | MED | FOLDED (Part 2.5; round-6 table) | `build_var_total_snapshot` at `snapshot/service.py:3317`, its one-cited-run refusal `:3398-3409` (`if len(cited_run_ids) != 1:` at `:3404`); `:3622-3627` is inside `build_var_unified_snapshot` (`:3471`). |
| V6-03 | MED | FOLDED (DS-B1b-3 (B); Part 2.3) | The p-vector diagonal filter I added at round 6 was inert by construction (`:3580-3585` already refuses; the filtered query is the p vector's only source). Dropped, and the reason written into the option. |
| V6-04 | LOW | FOLDED (Part 1 OUT; Part 6 out (2)) | Both carries now name the family filter AND the coverage refusal. |
| V6-05 | LOW | FOLDED (Part 2.3) | The flush-left continuation line was rewritten inside the bullet by V6-03's edit. |

### Fold check round 8 (Opus 5, 2026-09-18): 5 findings, none BLOCKING or HIGH — folded by hand (Fable 5.1); the loop exit

| Id | Severity | Disposition | Evidence |
|---|---|---|---|
| V7-01 | MED | FOLDED (Part 3 fence 3; Part 5 mutant 16) | Both now conditional on the fence-22 skip; `factor_service.py:420-422` quoted for why (16) would otherwise collapse into (15). |
| V7-02 | MED | FOLDED (Part 5 mutant 17; DS-B1b-14) | New mutant anchored at `seed.py:681-687` (predicate removed); floor seventeen. |
| V7-03 | LOW | FOLDED (Part 2.8) | The census's private-loadings line names the skip and the +12 it prevents; totals unchanged (5,106 / 11,211). |
| V7-04 | LOW | FOLDED (round-6 table) | V5-01's home is DS-B1b-3 (B) and Part 2.3. |
| V7-05 | LOW | FOLDED (DS-B1b-3 (B)) | `var_unified_kernel.py:81-89` `uncovered = held - diagonal_segments` / `raise VarUnifiedKernelError("uncovered-segment", ...)`, called at `var_service.py:1351`; `:1266-1270` names the adjudicator as the snapshot_id trust boundary. |

The round-8 folds are not re-checked by a further round; the ratification diff's own different-engine
verification (the standing rule) reads them.

### Ratification-diff verification, round 1 (Opus 5, 2026-09-18): 43 findings (41 rows at the fold, two re-id'd at round 2)

The standing rule: a different engine verifies every ratification diff. Four lanes read commit `d676fc4`
(the planning commit) — a citation lane over the outward benchmark, a governance lane, a citations-and-counts
lane and a fresh-reader lane — and a fifth, sources-only citation lane then re-fetched the sources behind
the seven quotes the first benchmark fold had added without a check. **43 findings in 43 rows: 3 BLOCKING (GOV-R-01,
CC-1, FR-01), 7 HIGH, 19 MED, 14 LOW; all 43 folded, 0 refuted** (41 rows at the fold, counted with `Counter`
over the four-lane findings file and re-counted over this table by `awk`; two of those rows each folded two
lanes' findings on one id — the sources-only lane's own CITE-6 and CITE-7 beside the citation lane's — so
41 rows carried 43 findings; at round 2 the sources-only pair were re-id'd CITE-6b and CITE-7b with their own
rows (VF1-03) and the table re-counted by `awk` → 43 rows, 3 / 7 / 19 / 14; the folder is Fable 5.1 — and the folder's first draft of this
sentence said "2 BLOCKING, 6 HIGH, 20 MED, 13 LOW" from memory, which the count refuted). Every
number and locator in this table was executed or grep'd at the fold; nothing is recalled. Eight rows are
dispositioned "same edit as" another id (`grep -cE 'same edit( )as'` → 9: those eight rows and this sentence; the `( )` group keeps the cells that quote this command from matching it, so the count holds when a later round quotes it, R2F-04): the same defect seen by two lanes,
folded once with both ids kept. Where the fix moved another file, the Disposition column names it.

| Id | Sev | Lane | Disposition | Executed evidence at the fold |
|---|---|---|---|---|
| CITE-1 | HIGH | citation | FOLDED (benchmark status row, section 1, section 6; roadmap `:355` and `:534`; plan `:57`; `current_state.md:25`, the scorecard's benchmark row — `:21` at the fold, re-pointed at round 3, R2F-03) | `grep -c '^> ' outward_benchmark_cro_overview_2026-09-18.md` → 40 at `d676fc4`, 41 after S4-b; five of the seven fold-added passages were lane-checked in the second pass (S1-d, S3-c twice, S3-d, S6-f: verbatim) and the two from sources pass two did not fetch (S5-e, S7-f) were checked at round 2 against a fresh fetch (VF1-01; this cell first said pass two checked all seven), so every record says 41 of 41 with that split named. |
| CITE-2 | MED | citation | FOLDED (benchmark `:55`, the S1-d locator) | Lane transcript: text VERBATIM on PDF page 34, paragraph 74; section is 3.8.1 under 3.8, not 3.6. Locator rewritten to "section 3.8 ... sub-section 3.8.1 ... paragraph 74; PDF page 34". No other prose in the file said 3.6 for S1-d: `grep -n '3\.6'` → `:35` (S1-a, 3.6.4), `:45` (S1-b, 3.6.5), `:55` (the corrected S1-d line, which now records the old value) and `:263` (the pass-two note). |
| CITE-3 | MED | citation | FOLDED (benchmark J-CRO-2 note, section 3 tail, section 5) | Lane transcript over the re-fetched CESR text: `grep -oi 'expected shortfall' s1.txt \| wc -l` → 0; `CVaR` → 1. Both sentences now separate the source's word (S3-c names expected shortfall; S1-d names CVaR) from this file's gloss. |
| CITE-4 | MED | citation | FOLDED (plan `:57`; roadmap `:355` 0b cell; `current_state.md:25` — `:21` at the fold, re-pointed at round 3) | Half of 0b's stated exit was unmet (`ls 10_delivery_backlog \| grep -i cro` → nothing); 0b now reads "DONE (section written and lane-checked); carried: cited from the CRO-1 planning record at its gate". |
| CITE-5 | LOW | citation | FOLDED (benchmark: Quote S4-b inserted after S4-a; section 4 liquidity bullet cites S4-b) | The lane supplied COLL 6.12.11 R (1) and (2) verbatim from its own fetch (HTTP 200, 251,243 bytes); copied with the same joined-sub-paragraphs note as S4-a; quote count 41. |
| CITE-6 | LOW | citation | FOLDED (benchmark `:13` method sentence) | Executed over the 41 quote lines: `grep -cP '^> .*[\x{2014}\x{2013}]'` → 3 (the whole file → 17, R3V-05) (S5-c, S6-c, S7-b keep their dashes); non-ASCII lines 6 (those three plus the bullet glyphs of S5-b, S5-c, S5-e). Sentence narrowed: quotes and apostrophes folded, dashes kept as printed; "eleven of the 33" labelled the first lane's own tally. |
| CITE-6b | LOW | citation (sources-only) | FOLDED (benchmark `:187` — `:181` at the fold, before S4-b's inserted lines, R3V-03; the S6-f locator; re-id'd at round 2 from the merged CITE-6 row, VF1-03; severity carried as the merged row's LOW, the lane's own label was not kept apart at the fold) | S6-f re-located under "FACTOR-BASED PERFORMANCE ATTRIBUTION" per the lane's layout-aware extraction. |
| CITE-7 | LOW | citation | FOLDED (benchmark section 6 pass-one paragraph; the Citation rule row at `:6`) | Isolation restated in rule 6a's words (`delivery_roadmap.md:448-449` "reads ONLY the cited source (never the draft's framing)"): the lane got the passages, the line texts and the claims, not the argument. |
| CITE-7b | LOW | citation (sources-only) | FOLDED (benchmark `:91` and `:97`, the S3-c / S3-d annotations; the S3 `curl` route at `:23`; re-id'd at round 2 from the merged CITE-7 row, VF1-03; severity carried as above) | S3-c now says marker 302 dropped from passage one only; S3-d says no marker inside the span; the `/files/` path with a contact user agent recorded. |
| GOV-R-01 | BLOCKING | governance | FOLDED (roadmap `:357` body; remit Part 2.8, Part 6 out (9), GOV-10 row) | Executed before: `grep -c "sixty-two" delivery_roadmap.md` → 0. The row body now carries "sixty-two business days, of which fifty-nine are not month-ends; one shared full-set covariance per daily date, not one per metric per fund; measured", "per MATURE private fund" and "ten limits with two live breaches and eight utilisations strictly between". Executed after: `grep -c "sixty-two business days" delivery_roadmap.md` → 1; GOV-10's disposition re-checked against the working tree and rewritten to say the planning commit did NOT carry the edit. |
| GOV-R-02 | HIGH | governance | FOLDED (roadmap `:534`) | Counted with `awk` over Part 7 (`^\| <id> \| (BLOCKING\|HIGH\|MED\|LOW) \|`): 61 + 10 + 10 + 8 + 6 + 6 + 5 + 5 = **111** rows, 111 distinct ids; severities 12 BLOCKING / 19 HIGH / 42 MED / 38 LOW; dispositions 109 `FOLDED` + 1 `FOLDED, option (i)` (F-01) + 1 `FOLDED IN PART` (CRO-R9) = 110 folded, 1 in part, 0 refuted. `git show d676fc4:10_delivery_backlog/w20_book1b_remit.md \| grep -c "96 finding"` → 0 (the number matched no subtotal). Row rewritten to those figures. |
| GOV-R-03 | HIGH | governance | FOLDED (`g2_slice_scope.json` `no_scope_reason`) | Rewritten to the G2 header's ratified argument; executed: 1,792 characters at this fold (1,815 after VF1-06 re-quoted clause (3) at round 2, R3V-02); `'clause (3)' in reason → True`, `'requirements_backbone.md:242' → True`, `'REQ-LIM-004' → True`; `python3 scripts/check_g2_adjudication.py` → `slice scope : 0 / blocking : 0`, `G2_EXIT=0`; `json.load` OK. |
| GOV-R-04 | MED | governance | FOLDED (remit Part 0.7; Part 5 sweep item (3) path) | Read `09_compliance_controls/control_matrix_skeleton.md:44` (CTRL-003, `register_model`/`register_model_version`), `:55` (CTRL-014, limitations register), `:63` (CTRL-022, `model.validate` 2L-only). Routing re-cited to CTRL-003 and CTRL-022 with CTRL-014's actual relevance stated; the bare `control_matrix_skeleton.md:62` citation gained its directory. |
| GOV-R-05 | MED | governance | FOLDED (plan `:49` header; roadmap `:355` row header; `current_state.md:24`, the Wave-20 slices row — `:20` at the fold, re-pointed at round 3) | One sentence in all three: 0a and 0b close before CRO-1's planning gate; 0c (the CRO-1 walk slot) and 0d close by CRO-1's exit; the outside walker by PM-1's gate. |
| GOV-R-06 | MED | governance | FOLDED (`current_state.md:3-13` CURRENT TRUTH block; `:3-9` at the fold) | Executed: `git rev-parse --short main` → `1c4f64f`; `gh pr view 246 --json headRefOid,mergeCommit` → head `323cedc`, merge `1c4f64f`, merged 2026-09-18T13:18:43Z; `gh api .../commits/323cedc.../check-runs` → 18 check-runs, `{"success":18}`, nine distinct names. Block now dated 2026-09-18, main `1c4f64f` (PR #246, the 49th autonomous merge), the planning commit named as on its branch pending merge. |
| GOV-R-07 | MED | governance | FOLDED (remit Part 2.11 new row and Part 6 out (11); plan `:75`; roadmap `:357` map clause) | Read `personas_and_user_journeys.md:97` ("and rolling drawdown, as charts"); `seed.py:1147-1158` (one ROLLING_RISK run per fund, 3 in BOOK-1a); `book.py:1364` `ROLLING_WINDOWS = (12,)`; `perf/bootstrap.py:794` `ROLLING_RISK_WINDOWS = (12, 36)`; `rolling_kernel.py:404` `for end in range(window_months - 1, len(months))` → ONE complete window over twelve months. So the drawdown half is one MAX_DRAWDOWN point per fund, not a series; recorded as a CRO-1 gate decision with the three options named. |
| GOV-R-08 | MED | governance | FOLDED (same edit as CITE-4 and CC-8) | See CITE-4. |
| GOV-R-09 | LOW | governance | FOLDED (remit Recon basis, Part 0 heading) | "Five" → "SIX", the six lanes numbered as the roster the roadmap counts. |
| GOV-R-10 | LOW | governance | FOLDED (`g2_slice_scope.json` `_scope_note`) | The sentence "The scope declared here is W19-S1 ..." removed; the S1 park and the verify-by-subject lesson kept; executed at round 2 (VF1-02; the first form of this cell quoted a `False` that the expression does not produce): `note.count('The scope declared here is W19-S1')` → 1, and the fifteen characters before that one hit are `(The sentence '`, so the only occurrence is inside the removal parenthetical → True. |
| GOV-R-11 | LOW | governance | FOLDED (`g2_slice_scope.json` `no_scope_reason`) | Split into rows served with data (LIM-001/002/003, PRV-001/002/003/005) and REQ-MKT-005 "neither served nor entering build" under DS-B1b-9 (C); executed substring check → True. |
| GOV-R-12 | LOW | governance | FOLDED (remit status block; every Part 4 header) | Status block names the nine briefed (DS-B1b-1, 3, 4, 5, 7, 8, 9, 10, 15) and the seven routine (2, 6, 9a, 11, 12, 13, 14); executed after tagging: `grep -c "\[briefed\]"` → 9, `grep -c "\[routine\]"` → 7. Both clause amendments (DS-B1b-4, -9) are in the briefed nine. |
| CC-1 | BLOCKING | counts | FOLDED (same edit as GOV-R-01) | The lane re-derived 62 business days (65 weekdays minus Good Friday, Memorial Day, Juneteenth); re-executed here with the book's `XNYS_HOLIDAYS`: `Q2 business days 62 / already boundaries 13 new 49 / month-ends [04-30, 05-29, 06-30] / daily-chain dates excl month-ends 59`, `Q2_EXIT=0`. |
| CC-2 | HIGH | counts | FOLDED (same edit as GOV-R-02) | 61 + 50 = 111; the lane's severity split 8/12/24/17 for the lane pass reproduced by the same `awk` (first section 61 rows). |
| CC-3 | HIGH | counts | FOLDED (same edit as CITE-1) | 40 − 7 = 33 confirmed as the pre-fold denominator; now 41 of 41 with both passes named. |
| CC-4 | MED | counts | FOLDED (roadmap `:534`) | Executed `awk '/^### Fold check/{p=1} p && /^\| [A-Z0-9-]+ \| BLOCKING \|/'` → F-01, S-01, R3-01, R4V-01 (four, at remit lines 1337, 1361, 1394, 1425 before this fold). The row names all four by id; "a guard I added that could never fire" (V6-03, MED) is out of the BLOCKING sentence. |
| CC-5 | MED | counts | FOLDED (roadmap `:357` body) | "per MATURE private fund" and "ten limits with two live breaches and eight utilisations strictly between" written into the row. The re-baseline record `:377-378` and `:384-385` stay untouched by the remit's own rule (`:11-13`, "the re-baseline record itself is not rewritten"); the roadmap row, the document the next gate opens, now carries the amendment. |
| CC-6 | MED | counts | FOLDED (same edit as GOV-R-06) | See GOV-R-06. |
| CC-7 | MED | counts | FOLDED (roadmap `:355` 0a cell) | The "could not pull" clause deleted as a live statement and kept as "the earlier diagnosis ... REFUTED by this run"; the plan's `:51` already carried only the true clause. |
| CC-8 | MED | counts | FOLDED (same edit as CITE-4) | See CITE-4. |
| CC-9 | MED | counts | FOLDED (same edit as GOV-R-05) | See GOV-R-05; CRO-1 declares six lines (roadmap `:358`), so its walk slot is bound to CRO-1's exit and the outside walker to PM-1's gate, as the plan's original text says. |
| CC-10 | MED | counts | FOLDED (remit Recon basis and Part 0 heading) | The six-lane roster is now enumerated in the remit, so roadmap `:534`'s "six recon lanes" derives from a committed artifact (`grep -c "SIX read-only lanes" w20_book1b_remit.md` → 2: the Recon basis paragraph and this cell). |
| CC-11 | MED | counts | FOLDED (roadmap `:355`; plan `:51`; `current_state.md:21`, the deployed-stack row — `:17` at the fold, re-pointed at round 3) | Executed: `git rev-parse --short d1c9161^` → `e17b904`; `git diff --stat e17b904 d1c9161` → three `.md` files, 152 insertions, no code path; `git diff --stat e17b904 d1c9161 -- packages apps scripts migrations deploy.sh .github` → empty. All three records now say the 0a stack was built from `w20-remediation-plan` at `d1c9161`, docs-only over `main` `e17b904`; the scorecard's "built from `main`" softened. |
| CC-12 | LOW | counts | FOLDED (roadmap `:534`) | Part 7 holds seven fold-check sections after the lane pass (`grep -c "^### Fold check" w20_book1b_remit.md` → 7); the row now says "SEVEN rounds (the remit numbers them 2 to 8)". |
| CC-13 | LOW | counts | FOLDED (benchmark section 3 rows J-CRO-3 and J-CRO-4, the section-3 tail, section 5, section 6 F-6 wording; roadmap `:355` 0b cell) | Executed after the edit: `grep -c "PARTIAL —"` → 5 (J-CRO-1, 3, 4, 5, 7). Roadmap 0b cell now reads "J-CRO-2, 6, 8 rest on outward evidence; J-CRO-3 and 4 in part; J-CRO-1, 5, 7 are the platform's own design". |
| FR-01 | BLOCKING | fresh-reader | FOLDED (remit Part 0.6, Part 0.10, Part 2.6 evaluation paragraph, Part 2.7 order sentence, Part 5 mutant 9) | Read `seed.py:1234-1239` (today: `_register_models` → `_run_account_boundaries` → `_run_month_end_chain` → `_run_return_chains` → `_run_sensitivity`), `seed.py:932-1106` (`_run_month_end_chain`, one iteration per `book.MONTH_ENDS`, VaR at `:1015`, active risk at `:1026`, concentration at `:1076`, liquidity at `:1091`), `seed.py:1109-1181` (`_run_return_chains` creates no limited family), `calc/reads.py:101-103` (`order_by(CalculationRun.system_from.desc(), ...)`). The order is stated once: `_register_models` → `_run_private_chain` → `_run_account_boundaries` → `_run_daily_chain` → `_run_month_end_chain` (evaluation inside the loop at the three Q2 iterations) → `_run_return_chains` → `_run_sensitivity`; Part 0.10's "last step" sentence and mutant (9) rewritten to that invariant. |
| FR-02 | HIGH | fresh-reader | FOLDED (remit Part 0.17, Part 2.1, fence 21, Part 5 determinism proof and mutant 18, DS-B1b-14 note) | Read `book.py:1394` (`rng = random.Random(SEED)`), `:1403` (factor draw), `:1438` (mark noise inside `for inst in INSTRUMENTS`), `:1481` (benchmark noise inside `for fund in FUNDS`): the benchmark draws follow the mark draws on one stream, so a private spec's draw shifts them. The verifier's probe transcript is quoted as the verifier's (not re-run here). Private specs now draw from `random.Random(SEED + 2)` with idio sigma zero; the proof is a SHA-256 digest over the public mark and benchmark series pinned as a fourth golden; mutant (18) is its negative control; the mutant floor stays "at least seventeen". |
| FR-03 | HIGH | fresh-reader | FOLDED (remit Part 2.6 guard paragraph) | Read `limit/service.py:577-598`: `return None` at `:585` (non-ACTIVE), `:593` (unresolved or REFUSED) and `:598` (within appetite); `:213-237` `Resolution.is_resolved` = `run_id` and `observed` set and `refusal` None; `:458` `_resolve_latest(session, limit)`. Guard now asserts `is_resolved is True` and `observed < threshold` per in-appetite row. The lane's premise that ACTIVE_RISK runs come from `_run_return_chains` is FALSE at its citation: `run_active_risk` is at `seed.py:1026` inside `_run_month_end_chain` (BOOK-1a: 39 runs, `w20_book1a_slice_record.md:94`), so the NL-GMA TE limit resolves at all three instants; stated in Part 2.6. |
| FR-04 | MED | fresh-reader | FOLDED (remit `:281`, `:412`, `:612`, `:731`, `:1003`, `:1070`, `:1179`, `:1205` at their pre-fold line numbers) | Each build-text fork resolved to the ratified option (the grid cell now reads "NL-PMF unified VaR (`VAR_PARAMETRIC_UNIFIED`; DS-B1b-3 (B) ratified)"); the two Part 4 fallbacks (DS-B1b-3 declined; DS-B1b-9 amendment declined) marked "Branch not taken". Executed after: `grep -n "if DS-B1b-3" w20_book1b_remit.md` → one hit, this cell; `grep -c "if DS-B1b-4 keeps\|falling back to (a) if\|If DS-B1b-4 lands"` → 0. |
| FR-05 | MED | fresh-reader | FOLDED (remit "What the fold changed at Tier 3" paragraph; F-03 row; S-06 row; the round-3 re-add block) | Each superseded tally now carries the round that superseded it (5,101 / 11,206 → 5,106 / 11,211 at round 4; floor fourteen → seventeen at round 8); S-06's "are unchanged" rewritten as history. Current figures re-summed from Part 2.8: 2,695 + 147 + 1,260 + 96 + 626 + 30 + 16 + 2 + 12 + 4 + 12 + 110 + 8 + 10 + 6 + 72 = 5,106. |
| FR-06 | MED | fresh-reader | FOLDED (remit Part 2.3; fence 3) | Read `book.py:152` `FactorSpec("RATES_USD_10Y", "RATES", ...)` and `:157` `CREDIT_HY ... "CREDIT_SPREAD"`; `RATES_UST_TR` declared in family RATES beside `CREDIT_HY_TR`'s CREDIT_SPREAD; both in the nine `LOADING_FACTOR_FAMILIES` (round-5 transcript); fence 3 lists the three families the coverage rows rely on. |
| FR-07 | LOW | fresh-reader | FOLDED (same edit as GOV-R-09) | See GOV-R-09. |
| FR-08 | LOW | fresh-reader | FOLDED (remit Part 2.1 ISIN convention; Part 3.14 pre-flight) | Read `book.py:42-54` (`def isin(base)`, Luhn check digit over 11 characters), `:280` (`isin: str`, no default), `test_demo_tenant_book.py:73-76`; executed over the 55: `isin unique True check ok True`. Twelve new `ZZ` ISINs through `book.isin`, uniqueness asserted over 67; the pre-flight now reads every `book.INSTRUMENTS` / `book.FUNDS` / `book.FACTORS` loop in that suite, not only the `BOUNDARIES` grep. |
| FR-09 | LOW | fresh-reader | FOLDED (remit DS-B1b-4 roster paragraph) | Arithmetic named: 175M sleeve / 8 = 21.875M = 12.5 % of the sleeve, 9.9 % of the 220.7M fund; 175 / 12 = 14.58M = 8.3 % of the sleeve, 6.6 % of the fund; "largest about 12 %" of the sleeve is about 9.5 % of the fund. The sentence names the sleeve as denominator and quotes the fund-level figure beside it. |

Not applied, and why: nothing. Two things this fold did NOT do, stated so they are not read as done: the
verifier's stream probe (FR-02) and the citation lane's fetches (CITE-2, -3, -5, -6, -7) are quoted as those
lanes' transcripts, not re-executed here; and the re-baseline record (`product_rebaseline_2026-09-17.md:377-378,
384-385`) is still not annotated with the two amendments, by the rule at the top of this remit (CC-5 asked for
one or the other; the roadmap row carries them).

### Ratification-diff verification, round 2 (Opus 5, 2026-09-18): 7 findings

The second different-engine pass read the round-1 fold (working tree over `d676fc4`). **7 findings: 0 BLOCKING,
1 HIGH (VF1-01), 3 MED, 3 LOW; all 7 folded, 0 refuted** (counted over this table by `awk` → 7 rows, 7 distinct
ids; the folder is Fable 5.1). Every number below was executed at this fold; nothing is recalled. Where the fix
moved another file, the Disposition column names it.

| Id | Sev | Lane | Disposition | Executed evidence at the fold |
|---|---|---|---|---|
| VF1-01 | HIGH | citation | FOLDED (benchmark Status row `:9` and section 6 pass-two paragraph; roadmap `:355` 0b cell and `:534`; plan `:57`; the round-1 CITE-1 cell above) | No record shows pass two fetching S5 or S7, so the "seven checked" claim is withdrawn: pass two's five (S1-d, S3-c x2, S3-d, S6-f) stay pass two's. S5-e and S7-f checked HERE against a fresh `curl` fetch: msci.com HTTP 200, 391,844 bytes, SHA-256 `c397ff88…`; blackrock.com HTTP 200, 528,114 bytes, SHA-256 `15fd3f13…`; both byte-identical to pass one's `cite/s5.pdf` and `cite/s7.html` (same digests). `norm(quote) in norm(text)` → True for S5-e (PDF page 2) and S7-f (first sentence under "Scenario analysis and portfolio modeling"), against the fresh fetch and against pass one's extraction; `CHK_EXIT=0`. So 41 of 41 stands, split 33 / 5 + S4-b / 2, and every record says so. `grep -c '^> '` → 41 after the fold. |
| VF1-02 | MED | governance | FOLDED (the round-1 GOV-R-10 cell above) | Re-executed: `'The scope declared here is W19-S1' in note` → True (the cell's quoted False did not reproduce); `note.count(...)` → 1; the 15 characters before the hit → `(The sentence '`, inside the removal parenthetical → True. The cell now quotes the reproducing check. `_scope_note` itself unchanged. |
| VF1-03 | MED | counts | FOLDED (round-1 heading, header sentence, CITE-6 / CITE-7 rows split into CITE-6, CITE-6b, CITE-7, CITE-7b; `current_state.md:13`) | Before: `awk` over the round-1 table → 41 rows, 41 distinct ids, 3/7/19/12; the two merged rows at the CITE-6 and CITE-7 lines each named "the lane's own" second finding. After: `awk` → 43 rows, 43 distinct ids, 3 BLOCKING / 7 HIGH / 19 MED / 14 LOW; `grep -cE 'same edit( )as'` → 9, unchanged (this cell's first form quoted the plain phrase and so made a tenth hit, R2F-04). The b-rows carry the merged rows' LOW and say so. |
| VF1-04 | MED | fresh-reader | FOLDED (remit `:502-503` and `:1167-1168` at their pre-fold numbers; and the Part 4 DS-B1b-4 (b) option text "Needs DS-B1b-3 = B", rewritten "Rests on DS-B1b-3 (B), ratified") | Before, over wrapped lines and case-insensitive: `tr '\n' ' ' \| grep -oiE 'if *DS-B1b-3 (=) B'` → 1, `'needs *DS-B1b-3 (=) B'` → 2. After: `if` → 0; `needs` → 1, the quotation of the withdrawn text in this cell. `grep -cE 'DS-B1b-3 (=) B'` → 5: the four descriptive uses (Part 0.7 "Only after ... does the `:3570` gate become the reason", Part 2.3 "Under ...", "BLOCKING under ... (GOV-1)", "The fold under ... also adds a refusal", which describe what holds under the ratified option and are not forks) plus this cell's quotation (the first form of this cell said 0 and 4, counting before it was written, R2F-04). |
| VF1-05 | LOW | fresh-reader | FOLDED (remit Part 0.10 bolded clause) | Restated in Part 0.6's words: "no step after the June evaluation may create a COMPLETED run of a limited family (VAR, CONCENTRATION, ACTIVE_RISK) for the three fund roots", with the reason the old form was wrong (the evaluation appends a breach row, `limit/service.py:577-598`, run from `_resolve_latest` at `:586`, re-read by the verifier; not re-read here). `grep -cE 'must be the( )last'` → 1, the sentence that records the old wording (the first form of this cell quoted the plain phrase and so was itself a second hit, R2F-04). |
| VF1-06 | LOW | governance | FOLDED (`g2_slice_scope.json` `no_scope_reason`) | `sed -n 242p requirements_backbone.md \| grep -oi 'utili[sz]ation'` → `utilization` x4, `Utilization` x4, no `utilisation`. Clause (3) now quoted verbatim inside quotation marks with the source's spelling; JSON round-trip byte-identical before the edit (`json.dumps(indent=1)` == file), `json.load` OK after, reason 1,815 characters; `python3 scripts/check_g2_adjudication.py` → `slice scope : 0 / blocking : 0`, `G2_EXIT=0`. |
| VF1-07 | LOW | citation | FOLDED (benchmark S5 block order) | Before: `grep -n '^Quote S5'` → a `:127`, b `:133`, c `:141`, e `:145`, d `:149`. After: a `:127`, b `:133`, c `:141`, d `:145`, e `:149`. Over the quote lines after the move: `grep -c '^> '` → 41; dash lines → 3; non-ASCII lines → 6, as section 1 says. |

Not applied, and why: nothing. Two things this fold did NOT do, stated so they are not read as done: it did not
find a transcript of pass two's fetches, so the S5 / S7 coverage claim is replaced by this fold's own fetch
rather than confirmed; and the `limit/service.py` lines under VF1-05 are the verifier's re-read, quoted as such.

### Ratification-diff verification, round 3 (Opus 5, 2026-09-18): 4 findings

The third different-engine pass read the round-2 fold (working tree over `d676fc4`). **4 findings: 0 BLOCKING,
1 HIGH (R2F-01), 3 MED, 0 LOW; all 4 folded, 0 refuted** (counted over this table by `awk` → 4 rows, 4 distinct
ids; the folder is Fable 5.1). Every number below was executed at this fold; nothing is recalled. All four (R2F-02 included, R3V-06) are the same class: a record written at one fold that a later fold's own edits refuted (a count that
included the cell counting it; a line number that moved when rows were inserted above it). Each re-quoted
count now uses a `( )` regex group, so the cell that quotes the command does not match it. Where the fix
moved another file, the Disposition column names it.

| Id | Sev | Lane | Disposition | Executed evidence at the fold |
|---|---|---|---|---|
| R2F-01 | HIGH | counts | FOLDED (roadmap `:534`, the Part 5 row's final bolded sentence) | Before: the sentence said "41 findings ... 3 BLOCKING, 7 HIGH, 19 MED, 12 LOW" and named no round 2. Re-executed: `awk` over the round-1 table (remit `:1575-1642`) → 43 rows, 43 distinct ids, 3 BLOCKING / 7 HIGH / 19 MED / 14 LOW; over the round-2 table → 7 rows. Sentence rewritten to "43 findings on this commit (41 rows at the fold, two re-id'd at round 2; 3 / 7 / 19 / 14 — counted over the table by `awk`), all folded; a second pass (round 2) raised 7 more (1 HIGH, VF1-01) and a third (round 3) 4 more (1 HIGH, R2F-01 ...)". After: `grep -cE '41 findings( )on this commit'` over the roadmap, the remit and `current_state.md` → 0, 0, 0 (group form, so this cell is not a hit). `current_state.md:13` gained "round 3 = 4 findings, 1 HIGH, all folded" in the same edit. |
| R2F-02 | MED | counts | FOLDED (remit `:20`, the front-matter Part 7 inventory clause) | Before: "round 1: 41 findings, 3 BLOCKING ... the last table of Part 7". After: "round 1: 43 findings, 3 BLOCKING; round 2: 7 findings, 1 HIGH; round 3: 4 findings, 1 HIGH; all folded 2026-09-18 in the working tree — the last three tables of Part 7". `grep -cE 'the last table( )of Part 7'` → 1, the quotation of the old text at the start of this cell; `grep -n '^### Ratification-diff'` → `:1575` (round 1), `:1643` (round 2) and this section's heading. |
| R2F-03 | MED | citation | FOLDED (`current_state.md:25`, the scorecard's benchmark row; the round-1 CITE-1 and CITE-4 cells' locators; and the same drift in GOV-R-05, CC-11 and GOV-R-06) | The cell now reads "41/41 verbatim: 33 in pass one, five plus S4-b in pass two, S5-e and S7-f at the round-2 fold against a fresh fetch, VF1-01"; `grep -c '41/41 verbatim over two lane passes' current_state.md` → 0. Locators re-executed with `sed -n Np current_state.md`: `:25` = the benchmark row (CITE-1, CITE-4 said `:21`), `:24` = the Wave-20 slices row (GOV-R-05 said `:20`), `:21` = the deployed-stack row (CC-11 said `:17`), the CURRENT TRUTH block spans `:3-13` (GOV-R-06 said `:3-9`), `:13` = the round tally (VF1-03, unchanged). Each cell keeps the old number beside the new one. |
| R2F-04 | MED | counts | FOLDED (remit round-1 header sentence `:1588`; the VF1-03, VF1-04 and VF1-05 cells) | Before, plain phrases: same-edit → 10 (eight cells, the header, VF1-03's cell), needs-form → 1 (VF1-04's own quotation), the ratified-option phrase → 5, must-be-last → 2 (`:193` plus VF1-05's cell): each cell had added the hit it counted. After, with the group form: `grep -cE 'same edit( )as'` → 9 (eight disposition cells and the header sentence; VF1-03's cell no longer matches); `tr '\n' ' ' \| grep -oiE 'if *DS-B1b-3 (=) B'` → 0; `'needs *DS-B1b-3 (=) B'` → 1 (the withdrawn text quoted in VF1-04's cell, now said there); `grep -cE 'DS-B1b-3 (=) B'` → 5 at `:171`, `:490`, `:495`, `:502`, `:1655` (four descriptive uses plus VF1-04's quotation, now said there); `grep -cE 'must be the( )last'` → 1 at `:193`. This table's cells use only the group forms, so none of these counts moves when it is read. |

Not applied, and why: nothing. Two things this fold did NOT do, stated so they are not read as done: it did not
re-fetch any benchmark source (R2F-03 is about the record of VF1-01's fetch, not the fetch); and it re-pointed
the five drifted `current_state.md` line numbers but did not re-verify the other files' locators in the
round-1 and round-2 tables (roadmap `:355`, `:534`; plan `:49`, `:51`, `:57`; benchmark lines), which those
tables quote at their own fold's line numbers.

### Ratification-diff verification, round 4 (Opus 5, 2026-09-18): 6 findings, all LOW — folded by hand (Fable 5.1); the loop exit

| Id | Severity | Disposition | Evidence |
|---|---|---|---|
| R3V-01 | LOW | FOLDED (round-1 CITE-4 cell) | `:21` at the fold recorded beside `:25`. |
| R3V-02 | LOW | FOLDED (round-1 GOV-R-03 cell) | 1,792 at the fold; 1,815 after VF1-06 (executed by the round-3 check). |
| R3V-03 | LOW | FOLDED (round-1 CITE-6b cell) | `grep -n '^Quote S6-f'` → 187; `:181` kept as the at-fold number. |
| R3V-04 | LOW | FOLDED (benchmark `:23`, `:91`, `:97`, `:187`, J-CRO-4 note) | The sources-only lane's ids are CITE-6b / CITE-7b since VF1-03; the benchmark's credits now say so. |
| R3V-05 | LOW | FOLDED (benchmark `:13`; round-1 CITE-6 cell) | The command is published with its `^> ` scope; whole-file count 17 stated beside it. |
| R3V-06 | LOW | FOLDED (round-3 header) | "All four", R2F-02 named. |
