# W20 BOOK-1a slice record — the public demo tenant, delivered

**Wave 20, slice 1.** Branch `w20-book1a`. Remit: `w20_book1a_remit.md` (RATIFIED 2026-09-17,
PR #243 = `d00cca8`). This record states what was built against each outcome, what the build
found that the remit did not know, the three hand derivations, and the measured gates.

**Status: BUILT 2026-09-17; review and merge stamps below as they land.**

## 1. What was built, outcome by outcome

| Remit outcome | Delivered | Where |
|---|---|---|
| 1. A tenant a CRO would recognise | Tenant `northlight`, "Northlight Capital Partners", ACTIVE, admitted at ONE site; five principals (CRO, PM, risk manager, analyst, auditor) with read sets from the governed catalog; three FUND roots declaring their base, eight STRATEGY sleeves, eleven ACCOUNT leaves. | `irp_shared/demo_tenant/seed.py` `_create_tenant`, `_seed_principals`, `_seed_funds` |
| 2. Fifty to eighty fictional instruments | **54** instruments across 31 issuers (24 corporates, 6 sovereigns, one custodian): 24 listed equities in USD, EUR and GBP; 4 US Treasuries; 5 euro sovereigns; 6 USD IG, 6 EUR IG and 5 EUR HY corporates with terms; 2 T-bills; 2 cash lines. ISIN-shaped identifiers under the user-assigned `ZZ` prefix. | `book.INSTRUMENTS`, `book.ISSUERS` |
| 3. A marked year, fixed | 2025-06-30 to 2026-06-30, **56 boundaries** (every business-day Friday plus every month's last business day; two Fridays are holidays), **13 month-ends**. 3,024 marks, 112 FX mids, 2,504 factor returns on 313 business days from 2025-04-01. No clock, no future literal, proven by an AST fence. | `book.BOUNDARIES`, `test_demo_tenant_book.py` |
| 4. The factor model that sees an equity move | Eight DAILY factors: FX_USD, FX_EUR, FX_GBP (CURRENCY), MKT_GLOBAL_EQ (MARKET), RATES_USD_10Y, RATES_EUR_10Y (RATES), CREDIT_IG, CREDIT_HY (CREDIT_SPREAD). 123 MANUAL loadings; the home-currency loading is an explicit zero (coverage without exposure, see §2.3). Covariance windows of 30 business days. | `_seed_factors`, `_seed_loadings` |
| 5. Benchmarks and risk-free | One composite benchmark per fund with constituents pinned at every month-end and a TOTAL return per boundary; one risk-free series per base currency (USD, EUR), one return per measured month; the XNYS calendar captured with its 2035 coverage. | `_seed_benchmarks`, `_seed_calendar` |
| 6. Classification | ISIC Rev. 5 (ten sections), ISO 3166-1 (eight countries) and SEC 22e-4 tiers resolved-or-created under SYSTEM; one sector, one country and one liquidity tier per instrument (162 assignments). | `_seed_schemes`, `_seed_instruments` |
| 7. Every public family run | **636 COMPLETED runs, zero FAILED** (table in §3). | `_run_account_boundaries`, `_run_month_end_chain`, `_run_return_chains`, `_run_sensitivity` |
| 8. Three hand-derived goldens | §4. | `test_demo_tenant_book1a_pg.py`, `scripts/derive_northlight_var.py` |
| 9. One orchestrator, one CLI, one deploy flag | `irp_shared.demo_tenant.seed_demo_tenant`; `python -m irp_shared.demo_tenant.cli` armed by `IRP_ALLOW_DEMO_SEED=1`; `deploy.sh --with-demo` (implies `--keep`), seeding after "DEPLOY VERIFIED" through the migrate image as the superuser. | `cli.py`, `infra/deploy/deploy.sh` step 9 |
| 10. Rider A | `test_model_validation_pg.py`'s EXCEPTION due date is now a year ahead of today, never a literal the clock can overtake. | `_DUE` |
| 11. Rider B | `R-D5` killed **10 of 10** runs (was 12 of 30 surviving): the shrinkage test targets the cohort member whose pinned summary row sorts LAST, so a recovery of `members[0]` is wrong every time. Anchor unchanged. | `test_reproduction_families_private.py` |

## 2. What the build found that the remit did not know

1. **The scenario engine is single-portfolio too** (`scenario_service.py`: "the pinned exposure
   run spans 5 portfolios (v1 is single-portfolio)"). The remit knew this of the return engine
   (DS-B1a-4) and not of scenarios. The first seed failed at the first fund's first scenario.
   Scenarios now run over the designated return account's allocation exposure, the same
   limitation as the return chain, and J-CRO-6 is that account's scenario until the multi-account
   engine lands (Wave-21 candidate, alongside the fund-level return).
2. **The boundary count is 56, not 59.** Two of the year's Fridays are exchange holidays
   (2025-07-04, 2026-04-03). The remit's recount assumed every Friday was a business day. The
   month-ends are all thirteen; nothing the rolling window needs is missing.
3. **A currency loading of one on a fund's own base is FX risk against its own numeraire.** The
   first seed loaded every instrument 1.0 on its currency factor, so the euro fund carried
   EUR/USD variance it cannot experience and its VaR was 977,718 EUR. The home-currency loading
   is now an explicit zero (an atom with no loading at all refuses; a zero loading is coverage
   and emits no row), and the euro fund's VaR is 454,549 EUR, entirely rates and spread.
4. **Tracking error is currency-only, by engine.** The active-risk family consumes the allocation
   (currency) exposure only, so a euro fund against a euro benchmark reports a tracking error of
   zero, and the multi-asset fund's is its currency mismatch against its composite. J-CRO-2's
   "tracking error vs the fund's benchmark" is what the engine computes, and CRO-1 must say so
   on the screen rather than let the zero read as precision.
5. **The census the census-writer forgot.** The aggregation-site census reads `x = x + y` as
   well as `+=`; three sites in the seed's own arithmetic (a calendar walk, the generated
   benchmark series, the CLI's run counter) were classified NON_MEASURE by name. The portfolio-
   name census caught six `.name` reads off the seed's spec dataclasses, classified
   OTHER_ENTITY. Four import-direction fences admitted `demo_tenant` by name on `demo`'s grounds.
   Each is an explicit edit someone reads, which is the fences' design.
6. **The seed runs on in-memory SQLite in 33 seconds.** That gave the mutation battery a
   unit-tier host with a fresh database per run (the M-DEMO-1 lesson: a PostgreSQL fixture that
   tolerates an already-seeded tenant cannot see a mutant behind a leftover row). The PostgreSQL
   suite proves the end state under RLS and the real admission gate; the SQLite suite proves
   causality.
7. **The seed's captures are 5,890, not 7,500.** Marks 3,024 (56 × 54), FX 112, factor returns
   2,504 (8 × 313), loadings 123, benchmark rows 127. The remit's estimate assumed 59 boundaries,
   65 holdings and 290 return days.

## 3. The run census (measured, from the seed summary and the PostgreSQL suite)

| Family | Runs | Where |
|---|---|---|
| Exposure aggregate | 207 | 3 return accounts × 56 boundaries + 3 fund roots × 13 month-ends |
| Factor exposure | 117 | per fund per month-end: allocation at root, loadings at root, allocation at the return account (for the scenario) |
| Covariance | 26 | 13 month-ends × (currency set, full set), shared across funds |
| Parametric VaR 99/1d, parametric ES 97.5, historical VaR 95/60 | 39 + 39 + 39 | per fund per month-end |
| Active risk | 39 | per fund per month-end |
| Scenario | 39 | per fund per month-end, at the return account |
| Concentration, liquidity | 39 + 39 | per fund per month-end |
| Portfolio return, benchmark-relative, rolling risk v2, Sharpe v2 | 3 each | per return account over the year |
| Sensitivity | 1 | one USD swap curve |
| **Total** | **636** | all COMPLETED |

Seeding time on the local PostgreSQL: **372.8 s** (CLI, first clean run) and **357 s** (inside the
suite), under DS-B1a-9's ten-minute ceiling with no fallback taken.

## 4. The three goldens, derived by hand (MD-H1)

Every derivation reads the book's own generated inputs and the kernels' published conventions
only; none calls a kernel. `scripts/derive_northlight_var.py` reproduces the third to the last
digit and is committed as the derivation's executable form.

**4.1 The multi-asset fund's market value in USD at 2026-06-30 = 157,800,377.922680.**
Thirty-five holdings; each contributes `quantity × mark × FX(mark currency → USD)`, with FX mids
at that date EUR/USD 1.1014 and GBP/USD 1.2552. Three rows as worked examples: CSDA 42,000 ×
190.3689 × 1 = 7,995,493.80; BWHS 38,000 × 108.5537 = 4,125,040.60; ORRN 21,000 × 438.3719 =
9,205,809.90. The thirty-five rows sum to 157,800,377.92268 USD, which the exposure binder stores
as 157,800,377.922680 (6 dp).

**4.2 The euro fund's largest sector share at 2026-06-30 = O (Public administration), 0.669801.**
The fund's sixteen holdings total 98,520,171.00 EUR (all EUR, FX 1). Its five sovereigns (BUND-30,
BUND-35, OAT-33, BTP-31, BONOS-32) are classified ISIC section O through their issuers and total
65,988,899.20 EUR. 65,988,899.20 / 98,520,171.00 = 0.669801 (6 dp), the row the concentration
run stores as `share_invested_long`.

**4.3 The euro fund's parametric VaR 99/1d at 2026-06-30 = 454,548.838555 EUR.**
Factor exposures are loading × market value, quantized HALF_UP at 20 dp and summed per factor:
RATES_EUR_10Y −523,643,504.02 (every bond's negative duration-like loading); CREDIT_IG
−21,215,656.975; CREDIT_HY −29,809,249.885; the home-currency loading is zero, so FX_EUR carries
no exposure. The covariance is the sample covariance over the 30 most recent business-day returns
ending 2026-06-30 (2026-05-18 to 2026-06-30), n−1 denominator, quantized HALF_UP at 20 dp:

| | RATES_EUR_10Y | CREDIT_IG | CREDIT_HY |
|---|---|---|---|
| RATES_EUR_10Y | 1.3878571954023E-7 | 1.633746436782E-8 | −1.319233563218E-8 |
| CREDIT_IG | 1.633746436782E-8 | 1.731177126437E-8 | 9.714022989E-11 |
| CREDIT_HY | −1.319233563218E-8 | 9.714022989E-11 | 1.8390742988506E-7 |

The quadratic form w′Σw = 38,177,878,239.079483; its square root is 195,391.602274; times the
registered z for 0.99, 2.326347874041 (`risk/bootstrap.py`, `VAR_Z_SCORES`), gives
454,548.838555 EUR after HALF_UP at 6 dp. With the nine-digit z a first pass used, the result was
454,548.838547, eight millionths off: the constant is quoted verbatim for that reason.

## 5. Gates (exit codes captured without pipes)

- `make check` = **0** — 3,124 passed, 680 skipped (`CHECK_EXIT=0`).
- Full-PG battery on a fresh four-part reset: *stamped below when the run completes.*
- Mutation battery: anchors **195/195**; group `w20-book1a` **7/7 killed** (one re-anchored after
  the formatter moved its bytes, an anchor-not-matched survivor and not a real one); group
  `repro-2b` **6/6** across ten consecutive runs (Rider B).
- The three censuses and four fences: aggregation, portfolio-name, holdings-consumption,
  fx/snapshot/risk/exposure import direction, all green with the new package admitted by name.
- The deployed smoke: `deploy.sh --with-demo` on this machine — *stamped below.*
- CI, the adversarial review and the ledger sweep: *stamped below.*

## 6. Carries out of this slice (P19)

1. **The fund-level scenario across accounts** joins the fund-level return on the Wave-21
   candidate list (finding §2.1).
2. **Tracking error is currency-only** (finding §2.4): CRO-1's remit must put that on the screen
   next to the number; a multi-factor active-risk model is a Wave-21 candidate, not a screen fix.
3. **The remit's 59 and 7,500** were wrong by the two holiday Fridays and the instrument count;
   corrected here, not in the remit (a record is not rewritten after ratification).
