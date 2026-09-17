# W20 BOOK-1a remit — the public demo tenant

**Wave 20, slice 1.** Branch `w20-book1a`. Authority: `02_requirements/product_rebaseline_2026-09-17.md`
(RATIFIED 2026-09-17, PR #241) Part 4.4 and Part 7 Lane F, and `delivery_roadmap.md` Part 2.22 row 1.
Where this remit and the record disagree, the record wins and the disagreement is a FINDING.

**Status: DRAFT, PENDING RATIFICATION** (DS-B1a-1 to DS-B1a-8, Part 4).

Planned against main `ed298e7`, tree clean. Migration head `0077_bind_position_to_mapping`, one
head. Next free canonical id **ENT-079**; next free control id CTRL-040. CI green on all nine checks
at `03f1b37` (PR #241's head) and at `952efb9` (PR #242's head), verified per conclusion.

Remits state OUTCOMES and PROOFS, not steps.

**G2 (P20 T1): declared no-scope, with the reason.** BOOK-1a builds demo data and an orchestrator.
No requirement row enters build: the families it runs are all delivered rows, and it mints no
number, no entity, no permission and no route. `g2_slice_scope.json` stays at its declared
emptiness with this slice named in the reason.

**G5 (P21 T1): declared no-scope, with the reason.** BOOK-1a makes no journey line walkable; it is
the tenant the later screens are walked over. `journey_slice_scope.json` stays at its declared
emptiness with this slice named in the reason. CRO-1 is the first slice to declare lines.

**Verification of this document (P15).** *To be appended after the different-engine lane runs
(Part 6).*

---

## Part 0 — Organizing facts (recon-verified; each reshaped the plan)

1. **The portfolio-return engine is single-portfolio.** `perf/return_service.py:295-299` refuses
   pinned atoms spanning more than one `portfolio_id`, and atoms carry the LEAF account. A
   fund-root exposure run over several accounts cannot feed a return run; stage 26 runs the return
   chain at a leaf for this reason (`demo/struct3_stage26.py:258-321`). Rolling risk, Sharpe and
   benchmark-relative all consume the return run. **So each fund's return chain runs at ONE
   designated account** (DS-B1a-4), and the fund-level return across accounts is a Wave-21
   candidate, not a BOOK-1a outcome.
2. **Tracking error and scenarios refuse the loadings factor family.** `risk/active_risk_service.py:475-481`
   refuses any exposure run not produced by the allocation model; `risk/scenario_service.py:165-168`
   refuses any exposed factor whose family is not CURRENCY. **So each fund runs BOTH factor-exposure
   paths**: allocation (currency) for tracking error and scenarios, loadings (the wider model) for
   VaR, ES and historical VaR.
3. **Covariance has no portfolio input** (`risk/covariance_service.py:258`): one matrix per factor
   set per date, shared across the three funds.
4. **Rolling risk and Sharpe need month-end boundaries** (`perf/rolling_kernel.py:95-160`): the
   first and last boundary must be month-ends and every month needs one; a twelve-month window
   needs thirteen. Weekly Fridays alone will not do. **The boundary set is every Friday plus every
   month's last business day** (about 62 in a year).
5. **Two engine gates read the real clock.** Liquidity FAILS a run whose oldest tier assignment is
   older than `tier_max_age_days` measured against `datetime.now()` (`liquidity/service.py:299-307`,
   default 31), and a model EXCEPTION with `next_review_due` in the past refuses binding
   (`model/service.py:563-570`). A demo that is re-seeded or re-run after a month must not trip
   either (DS-B1a-8).
6. **The deploy hook has one legal slot.** `deploy.sh` step 7 asserts `count(*) FROM currency = 4`
   over a tenant-scoped table (`deploy.sh:117-120`; the campaign adds two demo currencies), and
   step 8 asserts the worker prints "no ACTIVE tenants in the registry" (`deploy.sh:161`), which an
   ACTIVE demo tenant would falsify. **Seeding runs after step 8b and before "DEPLOY VERIFIED"**,
   and only with `--keep`, else the exit trap tears the seeded stack down.
7. **Nothing seeds a book today.** `scripts/run_demo_campaign.py` runs the base campaign only;
   nine extension stages have CLIs; eighteen exist only as PG test modules; no deploy, compose,
   Makefile or CI path invokes any of them.
8. **The base campaign's runtime is unmeasured anywhere in the repo.** BOOK-1a's run count is
   about ten times the base campaign's; the seeding time is MEASURED in this slice before its
   boundary set is final (Part 5).
9. **The prove scripts each use their own compose project and volume** (`prove_*.sh`), create
   tenants coded `ignition`, `proof-tenant`, `discovered`, and never see deploy.sh's database. No
   collision with a demo tenant by code or id.

---

## Part 1 — Scope line, stated so the gap is not read as an omission

**IN:** one new tenant with three funds; the hierarchy; 50 to 80 fictional instruments with
issuers; a marked year of weekly-plus-month-end boundaries with every leaf holding marked and
every FX pair captured on each; daily factor returns; the calendar; the loadings factor model with
captured loadings per instrument-factor pair and the currency allocation set; a benchmark per
fund with pinned constituents and monthly returns; a risk-free benchmark; sector, country and
liquidity-tier classification; every PUBLIC family run (Part 2 outcome 7); one orchestrator with a
CLI and a deploy flag; one PG suite with hand-derived goldens; two riders (Part 2 outcomes 10, 11).

**OUT, by design, with the host named:** the private sleeves (appraisal history, desmoothing,
regression and promotion, commitments and pacing, total and unified VaR) → **BOOK-1b**; limits and
breaches → **BOOK-1b**; the daily last quarter → **BOOK-1b**; any screen → **CRO-1**; the
fund-level return across accounts → **Wave-21 candidate** (Part 0.1); a deployed proof script that
seeds and reads back over HTTP → **SHOW-1** (the wave's exit); running the seed inside CI's
`stack-proof` job → not in this slice (runtime unmeasured; the PG suite is the CI proof).

---

## Part 2 — Outcomes

### 1. A tenant a CRO would recognise as a manager, not a fixture

Tenant code `northlight`, "Northlight Capital Partners" (fictional; DS-B1a-1), ACTIVE, admitted to
the ENT-074 registry by the orchestrator (the 2026-08-25 lesson: admission is not a side effect).
Three principals on the roster shape of the base campaign (a risk manager 2L, an analyst 1L, an
auditor 3L) plus a CRO principal and a PM principal, so CRO-1 and PM-1 have someone to sign in as.
Three funds, each a FUND root declaring its base currency, with STRATEGY sleeves and ACCOUNT leaves:

| Fund | Base | Sleeves → accounts | Return account |
|---|---|---|---|
| Northlight Global Multi-Asset Fund | USD | Global Equity → US Core, International; Fixed Income → Government, Credit; Cash | US Core |
| Northlight Euro Fixed Income Fund | EUR | Government → Core Govies; Credit → IG Credit, HY Credit | Core Govies |
| Northlight Private Markets Fund of Funds | USD | Private Equity → PE Primaries; Private Credit → Direct Lending; Liquidity Reserve → Treasury Reserve | Treasury Reserve |

The private-markets fund holds only its liquidity reserve in BOOK-1a; BOOK-1b fills the private
sleeves. **Proof:** the PG suite asserts the tree as-of via the hierarchy read, three roots with
declared base currencies, and the registry row present; the hand-checked names list in the slice
record.

### 2. Fifty to eighty instruments with plausible fictional names and real-shaped identifiers

Listed equities across US, Europe and UK; government bonds in USD and EUR; investment-grade and
high-yield corporates; cash. Every instrument has an issuer (legal entity), a currency, terms where
the exposure binder needs them (bonds: face and coupon, the DP-4 gap otherwise), and identifiers
shaped like the real thing under the user-assigned country prefix (`ZZ…` ISIN-shaped codes), so no
one asks whether it is licensed data. **Proof:** the suite asserts the count is within 50 to 80,
every instrument has an issuer and a currency, every bond has terms, and no name matches the
fixture patterns the realism rule now names (`INSTR-`, `CN-`, "Demo").

### 3. A marked year, fixed and time-bomb-free

The marked year is **2025-07-01 to 2026-06-30** (DS-B1a-2), ending before the deploy date and
never moving. Boundaries: every Friday plus every month's last business day (about 62). On every
boundary: a mark per leaf holding at the exact valuation date (the binder pins exact dates,
`snapshot/service.py:331`), and an FX mid for every pair among USD, EUR and GBP. Daily factor
returns from 2025-05-15 (a 30-observation lead-in for the first month-end covariance) through
2026-06-30. Every `valid_from` and `known_at` is explicit and in the past; no `now()` anywhere in
the seed. **Proof:** the suite asserts the boundary count, that every boundary has a mark for every
leaf holding and every FX leg, and greps the orchestrator package for `now(`, `today(` and any
literal date later than 2026-06-30 (the seed's own time-bomb fence).

### 4. The factor model that sees an equity move

The loadings family (`LOADING_FACTOR_FAMILIES`): MARKET (global equity), RATES (USD, EUR),
CREDIT_SPREAD (IG, HY) and CURRENCY (USD, EUR, GBP), eight DAILY factors, a MANUAL loading captured
per (instrument, factor) pair (`marketdata/proxy_mapping.py:396-409`; every instrument has at least
one loading, because an atom with none refuses, `factor_service.py:414-440`). The allocation
(currency) set for tracking error and scenarios. Covariance windows of 30 daily observations.
**Proof:** the suite asserts that the multi-asset fund's VaR at the June month-end moves when one
equity's MARKET loading is changed and the chain re-run on a scratch copy (the campaign's own
comment names the defect: "an equity move the CURRENCY factor model cannot see").

### 5. Benchmarks and a risk-free series

One benchmark per fund with constituents pinned at every month-end (currency-tagged, weights
summing to one) and a TOTAL-basis monthly return series in the fund's base currency, so tracking
error and benchmark-relative both bind (`active_risk_service.py:407-412`;
`benchmark_relative_service.py:283-287, 319-326`). One risk-free benchmark with one TOTAL return
per measured month for Sharpe. The XNYS calendar captured into the tenant with its 2035 coverage
(`demo/cal1b_stage21.py:250-264`), because v2 rolling and Sharpe refuse without it.

### 6. Classification

The SYSTEM schemes resolved or created (ISIC Rev. 5, ISO 3166-1, SEC 22e-4 tiers; the resolve-or-
create shape of `con1_stage19.py:199-212`, because `ref1` refuses a second creation). One sector
and one country assignment per instrument, one liquidity tier per instrument, so concentration and
liquidity run with full coverage.

### 7. Every public family run, with the counts stated

| Family | Where | When | Runs |
|---|---|---|---|
| Exposure aggregate | each fund root, and each return account | every boundary (≈62) | 3 × 62 × 2 = 372 |
| Factor exposure, allocation + loadings | each fund root | 13 month-ends | 3 × 13 × 2 = 78 |
| Covariance, currency + loadings | shared | 13 month-ends | 26 |
| Parametric VaR 99/1d, parametric ES, historical VaR 95 | each fund root | 13 month-ends | 3 × 13 × 3 = 117 |
| Active risk (tracking error) | each fund root | 13 month-ends | 39 |
| Scenario (one definition, two shocks) | each fund root | 13 month-ends | 39 |
| Concentration, liquidity | each fund root | 13 month-ends | 78 |
| Portfolio return, benchmark-relative, rolling risk v2 (12-month), Sharpe v2 | each return account | once, over the year | 12 |
| Sensitivity (one USD swap curve) | tenant | once | 1 |

About **760 runs** and about **4,000 audited captures** (marks and FX at 62 boundaries for roughly
65 holdings; 8 factors × 410 days of returns; up to 640 loadings). The risk chain at month-ends
gives a thirteen-point monthly VaR series per fund; the daily last quarter is BOOK-1b's
(DS-B1a-5). **Proof:** the suite asserts, per fund, the COMPLETED run count per family and that
the latest reads in the record's Part 3 table each return a row for each fund at 2026-06-30.

### 8. Three hand-derived goldens (MD-H1)

The multi-asset fund's total market-value exposure in USD at 2026-06-30; the euro fund's largest
sector share at the same date; the multi-asset fund's parametric VaR at that date from the pinned
matrix and exposures, derived by hand in the slice record with every intermediate quoted. The suite
pins all three verbatim.

### 9. One orchestrator, one CLI, one deploy flag

A new package `irp_shared/demo_tenant/` (its own tenant id, `uuid5` of `tenant:northlight`, so the
base campaign's `(27, 44, 141)` census, filtered to the demo tenant, does not move). Refuse-not-skip
on the campaign's shape: probe the footprint, raise `DemoTenantAlreadySeededError`, caller owns the
one commit. CLI `scripts/seed_demo_tenant.py` on `run_demo_campaign.py`'s shape. `deploy.sh` gains
`--with-demo` (implies `--keep`), which runs the seed **after step 8b** through the migrate image
(`$COMPOSE run --rm --entrypoint python migrate -m irp_shared.demo_tenant.cli`, the
`prove_report_identity.sh:75` pattern, owner role), and prints the seeded position. **Proof:** the
PG suite runs the orchestrator end to end on a fresh database in CI (its own CI step, because
`test_ci_pg_coverage` requires one per PG suite); a second run refuses; a deployed smoke on the
local stack with `--with-demo` is executed and its output quoted in the slice record, including the
measured seeding time.

### 10. Rider A — the one live time bomb, and the class named

`test_model_validation_pg.py:383` re-grants a model EXCEPTION with `next_review_due = 2027-06-01`
and asserts binding; `model/service.py:563-570` refuses an expired exception against the real
clock, so the test goes red on 2027-06-02 with no diff. Fixed the `d78f3d5` way. The other eleven
files named at the S1 close were each read and are fixed-point fixtures with no clock comparison;
listed in the slice record. **No general guard is built** (DS-B1a-6).

### 11. Rider B — mutant R-D5 made deterministic in its test

R-D5's survival is chance: under the mutant, recovery takes `members[0]`, whose order is a random
`uuid4`, so it equals the true target one time in three. The test names the target so it is never
`members[0]` under the stored ordering; the anchor is kept. Ten runs before and after, quoted.

---

## Part 3 — Fences, enumerated before drafting (P7's pre-flight companion)

1. **The currency assertion** (`deploy.sh:117-120`) and the **idle-worker grep** (`:161`): the seed
   must run after step 8b. A seed before step 7 fails the count; before step 8, the grep.
2. **The aggregation AST census** fires on any `+=`, `sum()` or `x = x + y` in the source trees it
   scans. An orchestrator that sums weights to one, or counts runs, trips it: budget `_ALLOWLIST`
   entries with a taxonomy class, or compute totals in the PG suite, not the package.
3. **The holdings-consumption census** (`test_holdings_consumption_census.py`) discovers modules
   that mint a governed run from the AST; a new package that calls run functions may enter its
   population. Check at the first commit; declare, never widen the sanctioned set.
4. **The GS2 run-type conformance walk** reads `*/events.py` and `*/models.py`; the new package
   declares no run type and must not.
5. **`test_ci_pg_coverage`** requires every PG suite to have its own CI step: add one, in the
   existing shape.
6. **Realism bands** (`test_data_realism.md`): prices 1 to 10^4, FX 0.5 to 200, daily |r| ≲ 0.05,
   weights in [0,1], and now names, counts and totals.
7. **The route census (315) and the migration head (0077) do not move.** No route, no migration.
8. **The liquidity age gate and the exception expiry gate read the real clock** (Part 0.5).
9. **`ref1`'s scheme creation refuses a second ISIC Rev. 5**: resolve-or-create.
10. **The stage-24 reproduction schedule sweeps every ACTIVE tenant** (`campaign.py:1127-1130`):
    the new tenant enters that sweep's population on a database that also holds the base campaign
    (CI's PG battery); its runs must reproduce, which is a proof, not a hazard.
11. **`make fix` before the first gate run**; purge `__pycache__` before trusting any gate; no
    `git add -A` while agents hold the tree.

---

## Part 4 — Decisions this slice cannot make for itself

**DS-B1a-1 — The fictional naming scheme.** Tenant `northlight`, "Northlight Capital Partners";
funds as Part 2.1; instruments named like real issuers of their kind ("Cascadia Semiconductor",
"Meridian Utilities 4.25% 2031"), identifiers ISIN-shaped under the user-assigned `ZZ` prefix.
**Recommend as written**; the owner sees these names on every screen from CRO-1 on.

**DS-B1a-2 — The marked year: fixed or rolling.** (a) fixed 2025-07-01 to 2026-06-30, the as-of
shown on screen as the book's date; (b) rolling, ending at the deploy date. **Recommend (a).** A
rolling year is a time bomb by construction (every re-seed changes every golden) and reproduction
needs fixed inputs; a CRO reading "as of 30 June 2026" is not confused.

**DS-B1a-3 — The deploy hook.** (a) `deploy.sh --with-demo`, implying `--keep`, seeding after step
8b through the migrate image; (b) a separate `seed_demo.sh` only. **Recommend (a), with the same
entry point callable standalone.** The flag is the shape SHOW-1 will exercise.

**DS-B1a-4 — The return chain at one designated account per fund** (Part 0.1). (a) accept: each
fund's return, rolling risk, Sharpe and benchmark-relative are its designated account's, stated on
the screen at CRO-1; the multi-account return goes to the Wave-21 candidate list; (b) build the
multi-account return now. **Recommend (a).** (b) is an engine change in a data slice.

**DS-B1a-5 — Risk-chain cadence.** (a) month-ends only in BOOK-1a (thirteen points; J-CRO-7's
quarter-of-daily VaR is BOOK-1b's); (b) every boundary. **Recommend (a)**: about 760 runs against
about 2,000, with the seeding time unmeasured (Part 0.8).

**DS-B1a-6 — The time-bomb class.** (a) fix the one live bomb (Rider A) and record a P7 clause-c
acceptance: no literal-date guard, because eleven of twelve literals are legitimate fixed-point
fixtures a grep would flag, while the two real bombs (`d78f3d5`'s and this one) were now-based
captures a grep would miss; the recurrence trigger is CI going red on a date, and each such red is
fixed the `d78f3d5` way; (b) build a guard. **Recommend (a).**

**DS-B1a-7 — Mutant R-D5.** (a) fix the test's target selection, keep the anchor (Rider B); (b)
withdraw the mutant with reason. **Recommend (a).** The mutant measures a real defect; only the
test's ability to see it was chance.

**DS-B1a-8 — The liquidity model's `tier_max_age_days`.** The demo registers its liquidity model
with a large age (3,660 days) and records why in the registration's assumptions: the real-clock
gate is correct for a live tenant and wrong for a fixed-year demo. No EXCEPTION validations with an
expiry are seeded. **Recommend as written.**

Sub-questions Claude decides and flags for reversal: the orchestrator's internal stage split; the
scenario definition's two shocks; the swap curve's tenors.

---

## Part 5 — Proofs (what "done" means, and none of it is a reading)

- `make check` exit 0 with the count quoted; full-PG exit 0 with the count quoted on a fresh
  four-part reset; `mutant-anchors` 188/188 plus this slice's new mutants all KILLED (at least: the
  admission step removed → the suite's HTTP read 401s; the time-bomb fence removed → a planted
  `now()` passes; the refuse-not-skip removed → a second seed succeeds; a mark omitted on one
  boundary → the exposure run at that boundary FAILS, asserted by the suite).
- **The seeding time MEASURED** on the local stack and quoted; if it exceeds ten minutes, the
  boundary set is reduced at the slice gate with the owner, not silently.
- The deployed smoke: `deploy.sh --with-demo` on this machine, output quoted, then the three
  latest reads of the record's Part 3 (VaR, exposure total, concentration) called over HTTP as the
  CRO principal and their rows quoted.
- CI green on all nine checks at the PR head, verified per conclusion via
  `gh api …/commits/<sha>/check-runs` and quoted.
- The adversarial review folded before the push; P15: at least one pass on a different engine.
- The seven-ledger sweep, with the verify-on-main clause run AFTER the merge; "no control moved"
  stated if true; both register halves untouched (no row enters build).

---

## Part 6 — Verification of this remit (different engine)

*Appended after the pass.*
