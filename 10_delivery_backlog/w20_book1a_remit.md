# W20 BOOK-1a remit — the public demo tenant

**Wave 20, slice 1.** Branch `w20-book1a`. Authority: `02_requirements/product_rebaseline_2026-09-17.md`
(RATIFIED 2026-09-17, PR #241) Part 4.4 and Part 7 Lane F, and `delivery_roadmap.md` Part 2.22 row 1.
Where this remit and the record disagree, the record wins and the disagreement is a FINDING.

**Status: RATIFIED by the owner 2026-09-17** ("proceed"; DS-B1a-1 to DS-B1a-9 all as recommended, Part 4). Planning gate merged as its own PR; the build follows on `w20-book1a`.

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

**Verification of this document (P15).** One refute-by-default lane on a different engine
(Fable 5.1), four sub-lanes in one pass: **58 claims checked, 15 findings, 1 BLOCKING, 4 HIGH,
6 MED, 4 LOW**, all folded (Part 6). The BLOCKING was arithmetic: the draft's marked year held
twelve month-ends and claimed thirteen, under which the twelve-month rolling window would have
produced no number for any fund.

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
   month's last business day, opening on 2025-06-30** so the year holds thirteen month-ends: 52
   Fridays, 13 month-ends, 6 coincide, **59 boundaries**. The first draft said "about 62" and
   "13 month-ends" over a year that holds twelve, under which `rolling_kernel.py:404` iterates an
   empty range and every rolling row is SUPPRESSED with a NULL value; the return series must also
   OPEN on a month-end (`rolling_kernel.py:130-134`), not on the first Friday.
5. **Two engine gates read the real clock.** Liquidity FAILS a run whose oldest tier assignment is
   older than `tier_max_age_days` measured against `datetime.now()` (`liquidity/service.py:299-307`,
   default 31), and a model EXCEPTION with `next_review_due` in the past refuses binding
   (`model/service.py:563-570`). A demo that is re-seeded or re-run after a month must not trip
   either (DS-B1a-8).
6. **The deploy hook has one legal slot.** `deploy.sh` step 7 asserts `count(*) FROM currency = 4`
   over a tenant-scoped table (`deploy.sh:117-120`; the campaign adds two demo currencies), and
   step 8 asserts the worker prints "no ACTIVE tenants in the registry" (`deploy.sh:161`), which an
   ACTIVE demo tenant would falsify. **Seeding runs after "DEPLOY VERIFIED"** (`:187-190`), and
   only with `--keep`, else the exit trap tears the seeded stack down. The seed runs as the
   SUPERUSER (Part 2.9).
7. **Nothing seeds a book today.** `scripts/run_demo_campaign.py` runs the base campaign only;
   nine extension stages have CLIs; eighteen exist only as PG test modules; no deploy, compose,
   Makefile or CI path invokes any of them.
8. **The base campaign's runtime is unmeasured anywhere in the repo.** BOOK-1a's run count is
   about twelve times the base campaign's and its audited captures about ninety times; the seeding
   time is MEASURED in this slice against a ceiling decided now (DS-B1a-9).
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
breaches → **BOOK-1b**; the daily last quarter, and with it the VaR and ES backtest families →
**BOOK-1b**; any screen → **CRO-1**; the
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
fixture patterns the realism rule now names (`INSTR-`, `CN-`, "Demo"). (The ISO 3166-1
user-assigned range covers `ZZ`, and no numbering agency issues under it.)

### 3. A marked year, fixed and time-bomb-free

The marked year is **2025-06-30 to 2026-06-30** (DS-B1a-2), opening on a month-end, ending
before the deploy date and never moving. Boundaries: every Friday plus every month's last business
day, 59 in all, thirteen of them month-ends (Part 0.4). On every
boundary: a mark per leaf holding at the exact valuation date (the binder pins exact dates,
`snapshot/service.py:331`), and an FX mid for every pair among USD, EUR and GBP. Daily factor
returns on XNYS business days only (weekend equity-factor returns fail the realism rule this
slice amends; the base campaign's calendar-day shape is not repeated) from 2025-05-16, a
30-business-day lead-in for the first month-end covariance, through 2026-06-30: about 290 days.
Every `valid_from` and `known_at` is explicit and in the past; no `now()` anywhere in the seed. **Proof:** the suite asserts the boundary count, that every boundary has a mark for every
leaf holding and every FX leg, and greps the orchestrator package for `now(`, `today(` and any
literal date later than 2026-06-30 (the seed's own time-bomb fence).

### 4. The factor model that sees an equity move

The loadings family (`LOADING_FACTOR_FAMILIES`): MARKET (global equity), RATES (USD, EUR),
CREDIT_SPREAD (IG, HY) and CURRENCY (USD, EUR, GBP), eight DAILY factors, a MANUAL loading captured
per (instrument, factor) pair (`marketdata/proxy_mapping.py:396-409`; every instrument has at least
one loading, because an atom with none refuses, `factor_service.py:414-440`). The allocation
(currency) set for tracking error and scenarios. Covariance windows of 30 business-day observations
(about six weeks).
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

The SYSTEM schemes resolved or created: ISIC Rev. 5 and ISO 3166-1 on the create arm of
`ref1_stage18.py:142-181` and SEC 22e-4 tiers on `lq1_stage23.py:123-163`, resolved first because
the unique constraint (`0056_classification.py:107`) refuses a second creation; `con1_stage19.py:199-212`
is resolve-or-REFUSE and is the wrong template. The create arm is a SYSTEM-tenant write from the
seed, inside the seven-table hybrid clause (classification schemes are hybrid by AD-013-R2), and
the suite proves it happens once on a fresh database and is skipped on one that holds the base
campaign. One sector
and one country assignment per instrument, one liquidity tier per instrument, so concentration and
liquidity run with full coverage.

### 7. Every public family run, with the counts stated

| Family | Where | When | Runs |
|---|---|---|---|
| Exposure aggregate | each fund root, and each return account | every boundary (59) | 3 × 59 × 2 = 354 |
| Factor exposure, allocation + loadings | each fund root | 13 month-ends | 3 × 13 × 2 = 78 |
| Covariance, currency + loadings | shared | 13 month-ends | 26 |
| Parametric VaR 99/1d, parametric ES, historical VaR 95 | each fund root | 13 month-ends | 3 × 13 × 3 = 117 |
| Active risk (tracking error) | each fund root | 13 month-ends | 39 |
| Scenario (one definition, two shocks) | each fund root | 13 month-ends | 39 |
| Concentration, liquidity | each fund root | 13 month-ends | 78 |
| Portfolio return, benchmark-relative, rolling risk v2 (12-month), Sharpe v2 | each return account | once, over the year, opening 2025-06-30 | 12 |
| Sensitivity (one USD swap curve) | tenant | once | 1 |

About **744 runs** and about **7,500 audited captures**: marks 59 × 65 ≈ 3,835; FX three pairs
at 59 boundaries ≈ 180; factor returns 8 × 290 ≈ 2,320; loadings up to 640; benchmark
constituents at 13 month-ends and monthly returns ≈ 250. (The first draft said 4,000; its own
parenthetical summed past that.) The risk chain at month-ends gives a thirteen-point monthly VaR
series per fund; the daily last quarter is BOOK-1b's (DS-B1a-5). **Not run, and named:** the VaR
and ES BACKTEST families, which pair each VaR window end with a Dietz sub-period of exactly the
horizon (`var_backtest_service.py:30-31`) and so need the daily boundaries that are BOOK-1b's. **Proof:** the suite asserts, per fund, the COMPLETED run count per family and that
the latest reads in the record's Part 3 table each return a row for each fund at 2026-06-30.

### 8. Three hand-derived goldens (MD-H1)

The multi-asset fund's total market-value exposure in USD at 2026-06-30; the euro fund's largest
sector share at the same date; and the **euro fund's** parametric VaR at that date, chosen because
its factor set is small (RATES EUR, CREDIT IG, CREDIT HY, CURRENCY EUR): at least one covariance
cell is derived by hand from its 30 observations and the quadratic form is worked in full, so the
golden does not pin the kernel's own matrix. Every intermediate quoted in the slice record; the
suite pins all three verbatim.

### 9. One orchestrator, one CLI, one deploy flag

A new package `irp_shared/demo_tenant/` (its own tenant id, `uuid5` of `tenant:northlight`, so the
base campaign's `(27, 44, 141)` census, filtered to the demo tenant, does not move). Refuse-not-skip
on the campaign's shape: probe the footprint, raise `DemoTenantAlreadySeededError`, caller owns the
one commit. CLI `scripts/seed_demo_tenant.py` on `run_demo_campaign.py`'s shape. `deploy.sh` gains
`--with-demo` (implies `--keep`), which runs the seed **after "DEPLOY VERIFIED"** (`deploy.sh:187-190`,
so the VERIFIED claim never quantifies over the seed; the record's "after the deploy verification"
read literally) through the migrate image (`$COMPOSE run --rm -e IRP_ALLOW_DEMO_SEED=1
--entrypoint python migrate -m irp_shared.demo_tenant.cli`, the `prove_report_identity.sh:77-78`
shape including its arming switch, which the module refuses without), and prints the seeded
position. **The seed runs as the database SUPERUSER**, `POSTGRES_USER`, exactly as the prepare
step's SYSTEM seed does (`docker-compose.yml:27, 44-48`): it writes the `tenant` row and SYSTEM
classification schemes, which no `irp_app` path may. It is the second superuser seeding path
beside `alembic upgrade head` and it never becomes an application path; the CLAUDE.md
no-BYPASSRLS invariant is about the application, and this remit says so rather than calling the
role "owner". **Proof:** the
PG suite runs the orchestrator end to end on a fresh database in CI (its own CI step, because
`test_ci_pg_coverage` requires one per PG suite); a second run refuses; a deployed smoke on the
local stack with `--with-demo` is executed and its output quoted in the slice record, including the
measured seeding time.

### 10. Rider A — the one live time bomb, and the class named

`test_model_validation_pg.py:383` re-grants a model EXCEPTION with `next_review_due = 2027-06-01`
and asserts binding; `model/service.py:563-570` refuses an expired exception against the real
clock, so the test goes red on 2027-06-02 with no diff. Fixed the `d78f3d5` way. The other eleven
files named at the S1 close were each read: none compares its literal against the real clock
(`test_scheduler.py:351` compares against now, but with an injected instant), and the furthest
fuse is `test_scheduler_cadence_pg.py:629`'s 2035 coverage horizon; listed in the slice record. **No general guard is built** (DS-B1a-6).

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
3. **The holdings-consumption census** (`test_holdings_consumption_census.py:93-112`) discovers
   READERS of the position and holdings tables, not callers of run functions (a demo stage that
   calls `run_exposure` is a caller, `:22-23`). The hazard is the orchestrator or its suite reading
   `position` rows directly as an oracle, which `ingest1_stage28` had to be exempted for (`:216`).
   Read holdings through the sanctioned as-of reconstruction only.
4. **The GS2 run-type conformance walk** reads `*/events.py` and `*/models.py`; the new package
   declares no run type and must not.
5. **`test_ci_pg_coverage`** requires every PG suite to have its own CI step: add one, in the
   existing shape.
6. **Realism bands** (`test_data_realism.md`): prices 1 to 10^4, FX 0.5 to 200, daily |r| ≲ 0.05,
   weights in [0,1], and now names, counts and totals.
7. **The route census (315) and the migration head (0077) do not move.** No route, no migration.
8. **The liquidity age gate and the exception expiry gate read the real clock** (Part 0.5).
9. **`ref1`'s scheme creation refuses a second ISIC Rev. 5**: resolve-or-create.
10. **The stage-24 reproduction schedule sweeps every ACTIVE tenant** (`demo/repro2_stage24.py`;
    the isolation rule is the docstring at `campaign.py:1127-1130`):
    the new tenant enters that sweep's population on a database that also holds the base campaign
    (CI's PG battery); its runs must reproduce, which is a proof, not a hazard.
11. **`make fix` before the first gate run**; purge `__pycache__` before trusting any gate; no
    `git add -A` while agents hold the tree.

---

## Part 4 — Decisions this slice cannot make for itself (ALL RATIFIED AS RECOMMENDED, 2026-09-17)

**DS-B1a-1 — The fictional naming scheme.** Tenant `northlight`, "Northlight Capital Partners";
funds as Part 2.1; instruments named like real issuers of their kind ("Cascadia Semiconductor",
"Meridian Utilities 4.25% 2031"), identifiers ISIN-shaped under the user-assigned `ZZ` prefix.
**Recommend as written**; the owner sees these names on every screen from CRO-1 on.

**DS-B1a-2 — The marked year: fixed or rolling.** (a) fixed 2025-07-01 to 2026-06-30, the as-of
shown on screen as the book's date; (b) rolling, ending at the deploy date. **Recommend (a).** A
rolling year is a time bomb by construction (every re-seed changes every golden) and reproduction
needs fixed inputs; a CRO reading "as of 30 June 2026" is not confused.

**DS-B1a-3 — The deploy hook.** (a) `deploy.sh --with-demo`, implying `--keep`, seeding after
"DEPLOY VERIFIED" through the migrate image as the superuser, armed by `IRP_ALLOW_DEMO_SEED=1`;
(b) a separate `seed_demo.sh` only. **Recommend (a), with the same
entry point callable standalone.** The flag is the shape SHOW-1 will exercise.

**DS-B1a-4 — The return chain at one designated account per fund** (Part 0.1). (a) accept: each
fund's return, rolling risk, Sharpe and benchmark-relative are its designated account's, stated on
the screen at CRO-1; the multi-account return goes to the Wave-21 candidate list; (b) build the
multi-account return now. **Recommend (a).** (b) is an engine change in a data slice.

**DS-B1a-5 — Risk-chain cadence.** (a) month-ends only in BOOK-1a (thirteen points; J-CRO-7's
quarter-of-daily VaR is BOOK-1b's); (b) every boundary. **Recommend (a)**: about 744 runs against
about 2,000, with the seeding time unmeasured (Part 0.8). **(a) amends the record's 4.4 as folded
from F-14** ("one covariance and one VaR run per boundary per metric per fund") for BOOK-1a; the
per-boundary trend is BOOK-1b's daily quarter. Surfaced as an amendment, not taken.

**DS-B1a-9 — The seeding-time ceiling and its fallback, decided now.** The seed must complete in
under **ten minutes** on the local stack, or the boundary set is reduced in this order: (1) drop
alternate Fridays (59 → about 34 boundaries); (2) only then, reduce the loadings factor set. The
month-ends are never touched (the rolling window needs all thirteen). Any reduction is an amendment
of the record's 4.4 and is recorded in the slice record as one. **Recommend as written.**

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
  admission step removed → the suite calls the real gate, `assert_tenant_admitted`, on PostgreSQL
  and asserts it RAISES (the suite has no HTTP client, so a "401" mutant would be green in CI; the
  401 is the deployed smoke's proof), and the orchestrator admits at ONE site, because the base
  campaign admits at two and a mutant anchored on one of two sites was green while its defect
  shipped; the time-bomb fence removed → a planted
  `now()` passes; the refuse-not-skip removed → a second seed succeeds; a mark omitted on one
  boundary → the exposure run at that boundary FAILS, asserted by the suite).
- **The seeding time MEASURED** on the local stack and quoted against DS-B1a-9's ceiling; any
  reduction taken is the ratified fallback, recorded as a record amendment.
- The deployed smoke: `deploy.sh --with-demo` on this machine, output quoted, then the three
  latest reads of the record's Part 3 (VaR, exposure total, concentration) called over HTTP as the
  CRO principal and their rows quoted.
- CI green on all nine checks at the PR head, verified per conclusion via
  `gh api …/commits/<sha>/check-runs` and quoted.
- The adversarial review folded before the push; P15: at least one pass on a different engine.
- The seven-ledger sweep, with the verify-on-main clause run AFTER the merge; "no control moved"
  stated if true; both register halves untouched (no row enters build).

---

## Part 6 — Verification of this remit (different engine, Fable 5.1; 58 claims, 15 findings)

| # | Finding | Disposition |
|---|---|---|
| B-1 | 2025-07-01..2026-06-30 holds 12 month-ends, not 13; the 12-month rolling window iterates an empty range and writes SUPPRESSED rows; the return series must open on a month-end; boundary union is 58 not 62. | FOLDED: the year opens 2025-06-30; 59 boundaries, 13 month-ends; the run table recounted (744). |
| H-1 | "Owner role" is the SUPERUSER; the campaign never arms tenant context and writes `tenant` rows. | FOLDED: named as the second superuser seeding path beside the SYSTEM seed, never an app path (Part 2.9, Part 0.6). |
| H-2 | VAR_BACKTEST and ES_BACKTEST neither run nor declared OUT; a 1-day VaR backtest needs daily boundaries. | FOLDED: OUT with host BOOK-1b (Part 1, Part 2.7). |
| H-3 | The capture estimate was about half the real count. | FOLDED: about 7,500, itemised (Part 2.7). |
| H-4 | The admission mutant would be GREEN in CI (no HTTP client in the PG suite); the campaign admits at two sites. | FOLDED: the suite calls the real gate; one admission site (Part 5). |
| M-1 | `con1_stage19.py:199-212` is resolve-or-REFUSE; the create arm is stage 18's SYSTEM write. | FOLDED: Part 2.6. |
| M-2 | Fence 3 misdescribed the holdings census (readers of position tables, not run callers). | FOLDED: Part 3.3. |
| M-3 | The VaR golden would pin the kernel's own 8×8 matrix. | FOLDED: the euro fund, one covariance cell by hand (Part 2.8). |
| M-4 | Calendar-day factor returns repeat the base campaign's unrealistic shape; "30 daily" spans 30 calendar days. | FOLDED: business days per the captured calendar, 30 business-day windows (Part 2.3, 2.4). |
| M-5 | The seeding-time clause deferred an owner decision. | FOLDED: DS-B1a-9, ceiling and ordered fallback. |
| M-6 | DS-B1a-5 amends 4.4's F-14 fold without saying so. | FOLDED: named as an amendment. |
| L-1 | The cited line is a comment; the pattern carries an arming switch. | FOLDED: `IRP_ALLOW_DEMO_SEED=1`, `:77-78`. |
| L-2 | The record says after verification; the remit said before "DEPLOY VERIFIED". | FOLDED: after `:187-190`. |
| L-3 | "No clock comparison" overstated; a 2035 horizon exists. | FOLDED: Part 2.10. |
| L-4 | Wrong site for the reproduction sweep. | FOLDED: Part 3.10. |

**Checked and holding, per the lane:** the single-portfolio return refusal and its propagation;
both loadings-family refusals; covariance's absence of a portfolio input; the liquidity and
exception clock gates; the real time bomb at `test_model_validation_pg.py:383`; the deploy.sh
lines; the prove-script codes; R-D5's uuid4 ordering; `ZZ` as user-assigned; the time-bomb fence
not false-firing on the imported 2035 constant; the aggregation census scanning the new package;
the (27, 44, 141) census filtered to the base tenant; a cash-only fund tripping no refusal.
