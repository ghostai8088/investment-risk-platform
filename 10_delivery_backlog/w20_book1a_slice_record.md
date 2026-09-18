# W20 BOOK-1a slice record — the public demo tenant, delivered

**Wave 20, slice 1.** Branch `w20-book1a`. Remit: `w20_book1a_remit.md` (RATIFIED 2026-09-17,
PR #243 = `d00cca8`). This record states what was built against each outcome, what the build
found that the remit did not know, the three hand derivations, and the measured gates.

**Status: MERGED 2026-09-17 — PR #244 = `1c430f9` (the 48th autonomous merge), CI nine-for-nine at head `8b61b45` per conclusion; full-PG 3,808 passed, exit 0, on a fresh reset; verified on `main`.**

## 1. What was built, outcome by outcome

| Remit outcome | Delivered | Where |
|---|---|---|
| 1. A tenant a CRO would recognise | Tenant `northlight`, "Northlight Capital Partners", ACTIVE, admitted at ONE site; five principals (CRO, PM, risk manager, analyst, auditor) with read sets from the governed catalog; three FUND roots declaring their base, eight STRATEGY sleeves, eleven ACCOUNT leaves. | `irp_shared/demo_tenant/seed.py` `_create_tenant`, `_seed_principals`, `_seed_funds` |
| 2. Fifty to eighty fictional instruments | **55** instruments across 32 issuers (25 corporates, 6 sovereigns, one custodian bank): 24 listed equities in USD, EUR and GBP; 4 US Treasuries; 6 euro sovereigns; 6 USD IG, 6 EUR IG and 5 EUR HY corporates with terms and spread loadings of 0.9 × duration; 2 rolling T-bill positions that never trade above par; 2 cash lines. ISIN-shaped identifiers under the user-assigned `ZZ` prefix **with valid check digits** (the algorithm is asserted against a real ISIN). | `book.INSTRUMENTS`, `book.ISSUERS`, `book.isin` |
| 3. A marked year, fixed | 2025-06-30 to 2026-06-30, **56 boundaries** (52 Fridays of which three are exchange holidays: Independence Day 2025-07-04, Good Friday 2026-04-03, Juneteenth 2026-06-19; plus 13 month-ends, 6 of them Fridays: 49 + 13 − 6), **13 month-ends**. 3,080 marks, 168 FX mids (three pairs, the GBP/EUR cross derived so the triangle is consistent), 2,504 factor returns on 313 business days from 2025-04-01. No clock, no future literal, proven by an AST fence. | `book.BOUNDARIES`, `test_demo_tenant_book.py` |
| 4. The factor model that sees an equity move | Eight DAILY factors: FX_USD, FX_EUR, FX_GBP (CURRENCY), MKT_GLOBAL_EQ (MARKET), RATES_USD_10Y, RATES_EUR_10Y (RATES), CREDIT_IG, CREDIT_HY (CREDIT_SPREAD). 125 MANUAL loadings; the home-currency loading is an explicit zero (coverage without exposure, see §2.3). Covariance windows of 30 business days. **Proven as the remit asked:** doubling one equity's MARKET loading and re-seeding a scratch database moves the multi-asset fund's June VaR and leaves the euro fund's unchanged (`test_the_factor_model_SEES_an_equity_move`). | `_seed_factors`, `_seed_loadings` |
| 5. Benchmarks and risk-free | One composite benchmark per fund made of **index baskets the fund does not hold** (nine unheld instruments with their own factor loadings), constituents pinned at every month-end, a TOTAL return per boundary compounded from the baskets' factor-implied paths and translated into the fund's base; one risk-free series per base currency (USD, EUR), one return per measured month; the XNYS calendar captured with its 2035 coverage. The first build used a subset of the fund's own holdings as its benchmark, which makes benchmark-relative a tautology; the reviewer caught it. | `_seed_benchmarks`, `_seed_calendar` |
| 6. Classification | ISIC Rev. 5 (ten sections), ISO 3166-1 (nine countries) and SEC 22e-4 tiers resolved-or-created under SYSTEM; one sector, one country and one liquidity tier per instrument (165 assignments). Created exactly once on a fresh database (SQLite suite) and RESOLVED, not duplicated, on the battery's database that already holds the base campaign (PG suite). | `_seed_schemes`, `_seed_instruments` |
| 7. Every public family run | **597 COMPLETED runs, zero FAILED** (table in §3; the first build's 636 ran a currency scenario on two funds for which it has no meaning, §2.1). | `_run_account_boundaries`, `_run_month_end_chain`, `_run_return_chains`, `_run_sensitivity` |
| 8. Three hand-derived goldens | §4. | `test_demo_tenant_book1a_pg.py`, `scripts/derive_northlight_var.py` |
| 9. One orchestrator, one CLI, one deploy flag | `irp_shared.demo_tenant.seed_demo_tenant`; `python -m irp_shared.demo_tenant.cli` armed by `IRP_ALLOW_DEMO_SEED=1`, and the remit's `scripts/seed_demo_tenant.py` as a thin wrapper over it; `deploy.sh --with-demo` (implies `--keep`), seeding after "DEPLOY VERIFIED" through the migrate image as the superuser. | `cli.py`, `scripts/seed_demo_tenant.py`, `infra/deploy/deploy.sh` step 9 |
| 10. Rider A | `test_model_validation_pg.py`'s EXCEPTION due date is now a year ahead of today, never a literal the clock can overtake. | `_DUE` |
| 11. Rider B | `R-D5` killed **10 of 10** runs (was 12 of 30 surviving): the shrinkage test targets the cohort member whose pinned summary row sorts LAST, so a recovery of `members[0]` is wrong every time. Anchor unchanged. | `test_reproduction_families_private.py` |

## 2. What the build found that the remit did not know

1. **The scenario engine is single-portfolio AND currency-only** (`scenario_service.py:184`:
   "the pinned exposure run spans 5 portfolios (v1 is single-portfolio)"; `:165-167` refuses any
   non-CURRENCY factor). The remit knew the first of the return engine (DS-B1a-4) and neither of
   scenarios. The first seed failed at the first fund's first scenario; the first fold ran it at
   each fund's return account, and the reviewer read the stored rows: the euro fund's "dollar
   strength" scenario lost 4.8M EUR on euro bonds, FX risk against its own numeraire, and the
   multi-asset fund's was zero because its return account holds only USD equities. **Now:** the
   FX scenario runs over the ONE account holding currencies other than the fund's base (the
   multi-asset fund's International account, `FundSpec.scenario_account`), and a fund with no such
   account runs none (the euro fund, the private-markets fund). J-CRO-6 shows a scenario for one
   fund and "no FX scenario applies" for two, honestly, until a scenario over the loadings family
   exists (Wave-21 candidate, alongside the fund-level return and scenario across accounts).
2. **The boundary count is 56, not 59.** Three of the year's Fridays are exchange holidays
   (Independence Day 2025-07-04, Good Friday 2026-04-03, Juneteenth 2026-06-19): 49 business
   Fridays plus 13 month-ends less 6 coincident. The remit's recount assumed every Friday was a
   business day; the first draft of this record said two holidays, and the reviewer counted three.
   The month-ends are all thirteen; nothing the rolling window needs is missing.
3. **A currency loading of one on a fund's own base is FX risk against its own numeraire.** The
   first seed loaded every instrument 1.0 on its currency factor, so the euro fund carried
   EUR/USD variance it cannot experience and its VaR was 977,718 EUR. The home-currency loading
   is now an explicit zero (an atom with no loading at all refuses; a zero loading is coverage
   and emits no row), and the euro fund's VaR is 464,185 EUR, entirely rates and spread.
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
7. **The seed's captures are 6,105, not 7,500**, counted by the orchestrator's own counters: marks
   3,080 (56 × 55), FX 168 (3 pairs × 56), factor returns 2,504 (8 × 313), loadings 125, benchmark
   rows 228 (three composites × (13 memberships + 55 returns) + 24 risk-free returns). The
   remit's estimate assumed 59 boundaries, 65 holdings and 290 return days; the first draft of
   this record miscounted the benchmark rows.
8. **`GET /exposure/latest/sum` is leaf-only.** Its resolver returns "the portfolio's own" rows
   (`exposure/service.py:795-797`), and a fund root's rows belong to its leaves, so the read
   refuses a fund with "no COMPLETED exposure run carries measure 'MARKET_VALUE' for this
   portfolio". The record's Part 3 marked it EXISTS for a fund total; it exists for an account.
   The fund total is served today by the run-keyed rollup read
   (`GET /exposure/runs/{run_id}/rollup?node_id=`), quoted in §5's smoke. CRO-1's one-call
   summary must resolve the root's latest run and roll it up, not call the leaf sum.
9. **The Docker daemon on this machine cannot pull base images** (Docker Desktop 4.7.1 behind a
   proxy; `docker pull node:24-slim` and `nginx:1.27-alpine` both timed out at 150 s), so
   `deploy.sh --with-demo` could not be executed end to end: step 1 builds images and hangs on
   the pull. The smoke in §5 was run by hand on the same stack with the three-week-old images
   (database, migrate, backend), the new seed run from the host into the deployed database, and
   the reads called over HTTP as the CRO principal. The flag's shell is syntax-checked; its
   execution is a **carry with a mechanical trigger**: the first `stack-proof` CI run on the
   merged branch builds the images, and SHOW-1 exercises the flag on a rebuilt stack.

## 3. The run census (measured, from the seed summary and the PostgreSQL suite)

| Family | Runs | Where |
|---|---|---|
| Exposure aggregate | 220 | 3 return accounts × 56 boundaries + 3 fund roots × 13 month-ends + 1 scenario account × 13 |
| Factor exposure | 91 | per fund per month-end: allocation and loadings at the root; allocation at the scenario account (one fund) |
| Covariance | 26 | 13 month-ends × (currency set, full set), shared across funds |
| Parametric VaR 99/1d, parametric ES 97.5, historical VaR 95/60 | 39 + 39 + 39 | per fund per month-end |
| Active risk | 39 | per fund per month-end |
| Scenario | 13 | the multi-asset fund's International account per month-end (§2.1) |
| Concentration, liquidity | 39 + 39 | per fund per month-end |
| Portfolio return, benchmark-relative, rolling risk v2, Sharpe v2 | 3 each | per return account over the year |
| Sensitivity | 1 | one USD swap curve |
| **Total** | **597** | all COMPLETED |

Seeding time: **295.7 s** into the deployed PostgreSQL from the host (CLI, the folded book) and
**372.8 s** on the first clean local run of the first build; under DS-B1a-9's ten-minute ceiling
with no fallback taken. On in-memory SQLite the same seed takes 33 s.

## 4. The three goldens, derived by hand (MD-H1)

Every derivation reads the book's own generated inputs and the kernels' published conventions
only; none calls a kernel. `scripts/derive_northlight_var.py` reproduces the third to the last
digit and is committed as the derivation's executable form.

**4.1 The multi-asset fund's market value in USD at 2026-06-30 = 155,681,069.672680.**
Thirty-five holdings; each contributes `quantity × mark × FX(mark currency → USD)`, with FX mids
at that date EUR/USD 1.1014 and GBP/USD 1.2552. The thirty-five rows sum to 155,681,069.67268
USD, which the exposure binder stores as 155,681,069.672680 (6 dp); the rollup read returns the
same bytes over HTTP (§5).

**4.2 The euro fund's largest sector share at 2026-06-30 = O (Public administration), 0.647615.**
The fund's sixteen holdings total 98,801,392.55 EUR (all EUR, FX 1). Its six sovereigns (BUND-30
15,697,161.60; BUND-35 9,413,134.00; OAT-33 11,493,306.00; BTP-31 12,744,383.60; BONOS-32
8,826,836.40; DSL-31 5,810,393.40) are classified ISIC section O through their issuers and total
63,985,215.00 EUR. 63,985,215.00 / 98,801,392.55 = 0.647615 (6 dp), the row the concentration
run stores as `share_invested_long`. (The first draft named five sovereigns and a total that
included a sixth it did not name; the reviewer caught it, and the sixth is now a government bond
in the government sleeve, where it belongs.)

**4.3 The euro fund's parametric VaR 99/1d at 2026-06-30 = 464,184.575474 EUR.**
Factor exposures are loading × market value, quantized HALF_UP at 20 dp and summed per factor:
RATES_EUR_10Y −524,871,987.06 (every bond's negative duration loading), CREDIT_IG
−97,631,444.988 and CREDIT_HY −38,264,644.53 (−0.9 × duration × value for the corporates), the
home-currency loading zero so FX_EUR carries no exposure. The covariance is the sample covariance
over the 30 most recent business-day returns ending 2026-06-30 (2026-05-18 to 2026-06-30), n−1
denominator, quantized HALF_UP at 20 dp:

| | RATES_EUR_10Y | CREDIT_IG | CREDIT_HY |
|---|---|---|---|
| RATES_EUR_10Y | 1.3878571954023E-7 | 1.633746436782E-8 | −1.319233563218E-8 |
| CREDIT_IG | 1.633746436782E-8 | 1.731177126437E-8 | 9.714022989E-11 |
| CREDIT_HY | −1.319233563218E-8 | 9.714022989E-11 | 1.8390742988506E-7 |

The quadratic form w′Σw = 39,813,659,126.748886; its square root is 199,533.604004; times the
registered z for 0.99, 2.326347874041 (`risk/bootstrap.py`, `VAR_Z_SCORES`), gives
464,184.575474 EUR after HALF_UP at 6 dp. With the nine-digit z a first pass used, the result was
eight millionths off: the constant is quoted verbatim for that reason.

## 5. Gates (exit codes captured without pipes) and the deployed smoke

**The smoke, by hand on the deployed stack** (§2.9 says why not through the flag): the deployed
PostgreSQL brought up on port 55432 and migrated through the existing migrate image
(`alembic_version` 0077, four currencies, one tenant); the folded seed run from the host into it
(`SEED_EXIT=0`, 597 runs, 295.7 s); the existing backend image started against it as `irp_app`;
then, as the `northlight-cro` principal over HTTP in dev-header mode:

| Read | Response |
|---|---|
| `GET /risk/vars/latest?portfolio_id=<NL-GMA>&metric_type=VAR_PARAMETRIC` | `var_value 1734274.488757 USD`, `confidence_level 0.9900`, `horizon_days 1`, `window_end 2026-06-30`, `n_factors 5`, `n_observations 30`, with the exposure and covariance run ids |
| `GET /exposure/runs/<latest NL-GMA root run>/rollup?node_id=<NL-GMA>` | `MARKET_VALUE total 155681069.672680 USD` over 35 rows, `NOTIONAL 57000000.000000` over 10 (the same bytes as golden 4.1) |
| `GET /exposure/latest/sum?portfolio_id=<NL-GMA>&exposure_type=MARKET_VALUE` | an honest refusal: "no COMPLETED exposure run carries measure 'MARKET_VALUE' for this portfolio — nothing to sum" (§2.8: the read is leaf-only) |
| `GET /concentration/results/latest?portfolio_id=<NL-EFI>` | sector detail rows led by `O 0.647615`, then `H 0.073618`, `C 0.073126` (golden 4.2) |
| the same read with an unknown tenant id | **401** |



- `make check` = **0** — 3,127 passed, 681 skipped (`CHECK_EXIT=0`), after the fold.
- Full-PG battery on a fresh four-part reset: **3,808 passed, exit 0** on the merged head's tree
  (`PYTEST_EXIT=0`); 3,804 before the fold. One control went red on the first post-fold battery
  and on CI (§7 M-11's note): it counted every ISIC version under SYSTEM; narrowed and re-measured.
- The Northlight PostgreSQL suite alone: **12 passed**, the three goldens confirmed on stored
  rows under RLS.
- Mutation battery: anchors **195/195**; group `w20-book1a` **7/7 killed** (one re-anchored twice
  as the book's bytes moved, an anchor-not-matched survivor each time and never a real one);
  group `repro-2b` **6/6** across ten consecutive runs (Rider B).
- The three censuses and four fences: aggregation, portfolio-name, holdings-consumption,
  fx/snapshot/risk/exposure import direction, all green with the new package admitted by name.
- The deployed smoke: by hand on the existing images, quoted above; the flag's end-to-end run is
  carried (§2.9).
- CI: all nine checks `completed | success` at `8b61b45`, verified per conclusion via the check-runs
  API. The adversarial review: §7. The ledger sweep: `current_state.md`.

## 6. Carries out of this slice (P19)

1. **The fund-level scenario across accounts** joins the fund-level return on the Wave-21
   candidate list (finding §2.1).
2. **Tracking error is currency-only** (finding §2.4): CRO-1's remit must put that on the screen
   next to the number; a multi-factor active-risk model is a Wave-21 candidate, not a screen fix.
3. **The remit's 59 and 7,500** were wrong by the two holiday Fridays and the instrument count;
   corrected here, not in the remit (a record is not rewritten after ratification).

## 7. The different-engine review (Fable 5.1): 61 claims checked, 17 findings, all folded

| # | Finding | Disposition |
|---|---|---|
| H-1 | The scenario shipped nonsense for two funds: −4.8M EUR on euro bonds from "dollar strength" (FX risk against the fund's own numeraire) and zero for the multi-asset fund (its return account holds only USD). | FOLDED: `FundSpec.scenario_account`; the scenario runs over the International account for the multi-asset fund and not at all for the two funds with no foreign-currency account (§2.1). |
| H-2 | Remit 2.4's proof (the model sees an equity move) was not delivered. | FOLDED: `test_the_factor_model_SEES_an_equity_move` re-seeds a scratch database with one MARKET loading doubled; the multi-asset VaR moves, the euro fund's does not. |
| M-3 | The name fence was case-sensitive and narrow ("Test Holding", "Sample", "Placeholder", "Dummy", "Instrument 1" all passed); identical funds and one-price books passed. | FOLDED: case-insensitive vocabulary; disjoint holdings per fund; at least twenty distinct equity prices and twenty distinct quantities; benchmarks never a subset of the holdings. |
| M-4 | "Two holiday Fridays" was wrong; Juneteenth 2026-06-19 is the third. | FOLDED: §1 row 3, §2.2. |
| M-5 | The capture count did not match the seed's own counter. | FOLDED: 6,105 from the counters, itemised (§2.7). |
| M-6 | Golden 4.2's prose named five sovereigns and a total that included a sixth. | FOLDED: six named, with values (§4.2). |
| M-7 | A Dutch government bond booked as IG credit with a spread loading. | FOLDED: DSL-31 is a GOVERNMENT_BOND in Core Govies; Kalmar Marine Oyj 3.30% 2031 takes the IG slot (Finland added to the country scheme). |
| M-8 | Every benchmark was a subset of the fund's own holdings, price-only, untranslated, labelled TOTAL. | FOLDED: unheld index baskets with their own loadings, compounded from factors and translated into base (`IndexMemberSpec`). |
| M-9 | T-bills above par; every bond's clean price drifted up by its carry. | FOLDED: bond drift zero (coupon is income); bills as rolling positions with negligible noise, never above par, asserted. |
| M-10 | Spread loadings above modified duration. | FOLDED: 0.9 × duration. |
| M-11 | Remit 2.6's create-once/resolve-once proof was not asserted. | FOLDED: the SQLite suite asserts one ISIC Rev. 5 scheme on a fresh database; the PG suite asserts one on the battery's database that already holds the campaign's. The first version of the control counted every ISIC version under SYSTEM (other suites seed eight others) and went red on CI and on the local battery with "6 == 1"; narrowed to the version this seed resolves. |
| L-12 | `scripts/seed_demo_tenant.py` did not exist. | FOLDED: a thin wrapper over the module CLI. |
| L-13 | Two FX pairs delivered for "every pair among USD, EUR and GBP". | FOLDED: the GBP/EUR cross, derived from the two USD legs. |
| L-14 | No ISIN carried a valid check digit. | FOLDED: `book.isin` computes it; asserted against a real ISIN. |
| L-15 | The missing-mark mutant killed by a fixture error, with no test asserting the failure. | FOLDED: `test_a_missing_mark_STOPS_the_seed_at_that_boundary` (the completeness rule refuses the snapshot, a DataQualityError, and the seed stops). |
| L-16 | "Northlight cash custodian" as an issuer. | FOLDED: Harborside Trust Company. |
| L-17 | Remit 2.1's "tree as-of via the hierarchy read" was a table read. | FOLDED: `resolve_tree_as_of`. |

Found by the build after the review, not by it: `GET /exposure/latest/sum` is leaf-only (§2.8);
the Docker daemon on this machine cannot pull base images, so the flag's execution is carried to
the first CI stack-proof and SHOW-1 (§2.9).
