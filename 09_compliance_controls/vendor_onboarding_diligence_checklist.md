# Vendor / external-dataset onboarding diligence checklist (CTRL-034)

**Minted at CAL-1a (2026-08-01) as an R-10 act with H-05 approval, given at the CAL-1 ratification
gate** (`cal_1_decision_record.md` OQ-CAL-1-9; the deliverable pair ratified at Wave-14 planning —
this checklist artifact + the control-matrix row). The control exists because some dataset defects
are **undetectable in-data by design** (the SR-1 finding: a uniformly one-month-late risk-free
series joins one month late with matching row counts and nothing in the data can distinguish it) —
so acceptance is a procedural act executed BEFORE governed use, recorded here per execution.
This control is **procedural**; nothing in it claims code-side enforcement of what code cannot see.

## The checklist (executed once per dataset, before governed use)

| # | Item | What must be recorded |
|---|---|---|
| 1 | Dataset identity & consumer | What series/set it is, its key, and the exact join/read that consumes it (file:line). |
| 2 | Source & authority | The publisher; whether it is the authoritative origin; publication cadence and horizon. |
| 3 | Licensing & tenancy | Open/public ⇒ SYSTEM rows **where the landing table is hybrid-capable (an AD-013-R1/R2 reference vocabulary); a time SERIES lands per-tenant regardless of license openness, with the license recorded** — the DATA-1 clarifying amendment (H-05-approved at the DATA-1 ratification gate, 2026-08-02, OQ-DATA-1-2: the original arm presumed a hybrid-capable table, and a market-data series is not a curated shared vocabulary; the closed hybrid set and the MARKET per-tenant chain stay byte-unchanged). Licensed ⇒ per-tenant captures (the ratified OQ-W14P-6(iii) conditional; the `fx_rate` precedent). The reasoning, not just the verdict. |
| 4 | Dating/keying convention | The convention the CONSUMER declares, verbatim; every convention defect that is undetectable in-data enumerated, with the acknowledgment that this checklist — not code — is its control. |
| 5 | Completeness & horizon | The covered span; published vs PROJECTED portions labeled; the re-verification trigger for projections. |
| 6 | Encoding rules & known traps | Whether values are transcribed from the published source or derived from a rule — derivation traps named (for calendars: NYSE Rule 7.2 — a naive Saturday⇒Friday observance rule fabricates holidays on real trading days). |
| 7 | Delivery path & idempotence | The governed rail (verb) it enters through; re-run behavior; the audit event(s) emitted. |
| 8 | Acceptance censuses | The exact POSITIVE pins (set-equality/counts/anchors) and NEGATIVE pins (dates/values that must be ABSENT), with the test names that enforce them. |
| 9 | Maintenance obligation | Who re-executes this checklist, on what trigger. |

---

## Execution 1 — the XNYS holiday set (CAL-1a, 2026-08-01)

| # | Answer |
|---|---|
| 1 | The XNYS (NYSE) full-day scheduled-closure set, 2024–2035, keyed `(calendar, holiday_date)`. Consuming reads at `8637b67`: the read-only display endpoint `GET /calendars/{calendar_id}` (`apps/backend/src/irp_backend/api/reference.py:214`), which serves the refreshed set to tenants the moment the seed lands. No business-day / date-math CONSUMER exists yet — those are the CAL-1b predicates (scheduler tick + RM-1/SR-1 v2 acceptance). *(Review fold: the original wording claimed no runtime reader at all — refuted by the display endpoint; corrected, kept as history.)* |
| 2 | NYSE, the exchange itself ("Holidays and Trading Hours") — the authoritative origin; publishes ~3 years ahead. |
| 3 | **Public** — exchange-published holiday dates are published public facts ⇒ **SYSTEM rows** per the ratified conditional (`wave_14_planning.md` OQ-W14P-6(iii), lines 216–221; *citation re-pointed at DATA-1 — the original `delivery_roadmap.md:369` locator went stale when the roadmap grew*); a licensed vendor calendar product would instead land as tenant captures. Consistent with the DATA-1 item-3 amendment: `calendar_holiday` IS hybrid-capable, so the SYSTEM arm applies here. |
| 4 | Full-day scheduled closures only; early-close half-days are trading days (deliberately absent); unscheduled event closures out of scope. No join-key convention risk at this grain (a date set, not a dated series). |
| 5 | 2024–2028 from the published schedule; **2029–2035 PROJECTED** from the holiday definitions + observance rules incl. Rule 7.2 — labeled in `xnys_holidays.py`; re-verified against the published schedule as the exchange extends it (item 9). |
| 6 | Hand-encoded literals, never runtime-derived. The named trap: **NYSE Rule 7.2's year-end exception** — Saturday New Year's Days are NOT observed on the preceding Friday when it is a month-end, so 2028/2033 carry NINE holidays and **2027-12-31 / 2032-12-31 are trading days**; a naive observance encoding fabricates both AND corrupts the recorded month-end collision census from 4 to 6. |
| 7 | `refresh_calendar_holidays` (ADD-ONLY diff, intra-call duplicates dedupe first-spec-wins; one parent `REFERENCE.UPDATE` per effective refresh; idempotent no-op emits nothing), executed by `seed_system_reference` under SYSTEM context — its first execution. No removal path exists. **The CAL-1b carry, PAID (2026-08-01, migration 0059):** the verb now takes `complete_through` — a FORWARD-ONLY declared-coverage advance (a regression refuses; an advance alone is an effective refresh), negative-controlled in `test_reference.py`. *(Original wording: "this verb MUST be retrofitted at CAL-1b" — kept as history.)* |
| 8 | POSITIVE: per-year counts (10×10 years, 9 in 2028/2033), total 118, the four month-end collisions present (2024-03-29, 2027-05-31, 2029-03-30, 2032-05-31), published-calendar anchors, weekday-only, independent in-test rule re-derivation must agree — `test_the_xnys_dataset_census`, `test_the_xnys_dataset_agrees_with_an_independent_rule_derivation`. NEGATIVE: 2027-12-31 and 2032-12-31 ABSENT — same census test, plus the `XNYS_RULE_72_OPEN_FRIDAYS` module pin. |
| 9 | Re-execute at each dataset extension (new years appended) and when the exchange publishes a year currently PROJECTED; owner R-10. |

---

## Execution 2 — the TB3MS risk-free-rate series (DATA-1, 2026-08-02)

The first genuinely EXTERNAL dataset — the checklist executed IN FULL, as the rf walk-through
below obligated by name.

| # | Answer |
|---|---|
| 1 | The 3-Month Treasury Bill Secondary Market Rate, Discount Basis (H.15 monthly series; FRED id TB3MS), keyed `(benchmark, rate_date, rate_type, quote_basis)` on ENT-070 `benchmark_rate` under the `US-TBILL-3M`/`US-FRB-H15` head. Consuming reads AS SHIPPED: the completeness gate (`marketdata/benchmark_rates.py::refresh_benchmark_rates`) and the tenant read `GET /benchmarks/{benchmark_id}/rates` (`apps/backend/src/irp_backend/api/marketdata.py::list_benchmark_rates_endpoint`). The INTENDED governed consumer — the Sharpe month-key rf join (`perf/sharpe_kernel.py`) — sits behind the ratified OQ-DATA-1-1a carry (a registered yield→period-return model + new version labels); v1 deliberately feeds NO governed number. |
| 2 | Origin: the Board of Governors of the Federal Reserve System, H.15 Selected Interest Rates (posted each business day 4:15pm ET). FRED (Federal Reserve Bank of St. Louis) is the ACCESS/verification channel, not the owner. Monthly observations post ~1 business day after month end. Horizon: published monthly back to 1934; encoded span 2024-01..2026-06. |
| 3 | **Public domain at origin** (17 U.S.C. §105 + the Board's disclaimer: "information on Board's website is in the public domain… Please cite to the Board" — cited). FRED's ToU permit internal commercial use with attribution (given) and prohibit mining/mirroring — the values were read from proxy-rendered single-page views (fred.stlouisfed.org refuses this environment's direct fetcher), hand-encoded, and verified by THREE independent extraction passes agreeing on all 30 values; any FUTURE programmatic refresh targets the Board's own Data Download Program, not FRED. **Tenancy: per-tenant capture despite the open license — the amended item-3 conditional above** (`benchmark_rate` is a market-data series, not a hybrid-capable vocabulary; the demo tenant captures its own copy, a real tenant captures its own; public-domain duplication is costless). H-05-approved at the ratification gate (BR-15). |
| 4 | Declared consumer convention (verbatim, `sharpe_kernel.py`): *"the rf `return_date` must fall INSIDE the month its return is for."* The vendor dates each monthly observation the FIRST of its OBSERVATION month — **conforming AT THE RATE-OBSERVATION grain** (an observation dated inside the month it averages); the RETURN-month mapping (contemporaneous vs ex-ante — a June-observed yield may be the rate FOR July) is expressly assigned to the conversion-model carry, where a re-dating rule may yet be required. Undetectable-in-data defects, enumerated: (a) a UNIFORM re-dating shift (the SR-1 class — matching row counts, nothing in-data distinguishes it); (b) a BASIS mislabel (discount vs investment basis differ by ~15bp on the same date — June 2026: 3.66 vs 3.81 — which is why `quote_basis` is IN the key and the coherence map refuses incoherent pairs); (c) the H.15 averaging-footnote ambiguity ("averages of business days" vs "monthly figures include each calendar day" — pinned: FRED's TB3MS aggregation note says Averages of Business Days, carried as `observation_convention=MONTHLY_AVG_BUSINESS_DAYS`). This checklist — not code — is the control for all three. |
| 5 | 2024-01..2026-06 encoded (30 observations), ALL published values — nothing projected. 2026-07 was UNPUBLISHED at encoding (posts ~1 business day after month end) and ships ABSENT; the declared horizon `TB3MS_COMPLETE_THROUGH = 2026-06-30` ends at the last published month, and the add-only refresh verb is the paid path for later months. |
| 6 | Hand-encoded literals (`marketdata/tb3ms_rates.py`), transcribed — never derived. The ONLY transformation is the pure units change percent→fraction (5.22 → 0.0522). The named traps NOT taken: the three annualized→monthly treatments (/12, geometric, discount-honoring de-annualization — methodology, not units; the registered-model carry) and the discount→investment basis conversion. The series is REVISABLE (the Board's historical-correction page, selected 2002–2005 dates): a published correction goes through `correct_benchmark_rate` with a restatement reason, never a re-encode. |
| 7 | `refresh_benchmark_rates` (ADD-ONLY, intra-call dedupe first-spec-wins; a differing value for a captured date REFUSES naming `correct_benchmark_rate`; FORWARD-ONLY `rates_complete_through` advance that may not outrun the data; ONE `(rate_type, quote_basis)` series per head in v1). Events: per-row `MARKET.BENCHMARK_RATE_CREATE` + ONE head `REFERENCE.UPDATE` per effective refresh + the DQ-rule params-advance event. Re-run behavior: an identical re-supply is a TRUE silent no-op (nothing written, nothing emitted, no DQ leg) — executed live in demo stage 22. Completeness fires only on an EFFECTIVE refresh; a FAIL rolls the batch back in a savepoint while the FAIL evidence COMMITS. |
| 8 | POSITIVE: exactly 30 observations, unique, ascending, first-of-month dated; the exact month set 2024-01..2026-06; endpoint anchors (2024-01 = 0.0522, 2026-06 = 0.0366); the fraction units band (0.03..0.055 — a percent-scale slip cannot pass); the easing-path shape — `test_the_tb3ms_dataset_census` (unit) + `test_the_demo_tenant_captured_the_real_tb3ms_dataset` (PG, verbatim row set). NEGATIVE: NO 2026-07 row (same census); **NO derived monthly-return row anywhere for the real series** (`test_no_derived_monthly_return_row_exists_for_the_real_series` — the capture-first doctrine's own pin); the count pin 26/43/139 UNCHANGED (`test_the_final_position_count_pin`, 13-z). |
| 9 | Re-execute item 8's census at each `complete_through` advance (the refresh verb's completeness rule re-runs it structurally); a SOURCE or CONVENTION change (new basis, new maturity, a publisher methodology change) re-executes this checklist in full; **owner R-10**. |

---

## Walk-through — the rf (risk-free) series dating convention (the carried SR-1 obligation)

The obligation this control was minted to discharge (`ref_1_decision_record.md` OQ-REF-1-22;
`wave_14_planning.md` fact 8): `capture_benchmark_return` accepts ANY `return_date`; the Sharpe
binder joins by MONTH KEY and catches a partial shift but **never a uniform one** — a uniformly
one-month-late series is undetectable in-data. The declared convention (verbatim, from
`sharpe_kernel.py`): *"the rf `return_date` must fall INSIDE the month its return is for."*

Checklist items 1/4/8 applied to the rf series as it exists today: the only rf data in the
platform is the demo-captured 18-row series (`demo/sr1_stage17.py`), authored in-repo — items
2/3/5/6/7 have no external vendor to interrogate yet. **The first REAL rf/benchmark vendor
dataset (DATA-1) executes this checklist in full**, with item 4 asking the vendor's dating
convention against the declared one and recording the re-dating rule if they differ. This
walk-through discharges the carry as ratified: the control EXISTS, is EXECUTED against the
dataset onboarded in-slice (Execution 1), and names the rf convention as its standing item-4
exemplar — with no claim of code-side enforcement.
