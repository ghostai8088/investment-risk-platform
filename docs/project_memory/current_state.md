# Current State

> ## ⚠️ CURRENT TRUTH (2026-08-08, latest) — read this block; everything below it is HISTORY
>
> **THE WAVE-16 CLOSE REVIEW HAS RUN AND ITS GATE IS RATIFIED; THE CLOSE FOLD IS BUILT AND AWAITING
> ITS GATES.** Branch `wave-16-close`. The review ran fresh-context over the whole wave and found
> what neither the slices nor their reviews could:
>
> - **A BLOCKING product gap nobody had recorded: the platform has no way to create a tenant, a
>   user or a role.** 251 API paths, 291 RBAC-protected operations, **zero provisioning routes** —
>   every deployment is seeded by a demo script. Spot-checked independently. ⇒ **ONBOARD-1 is
>   ratified as Wave-17 slice 0.**
> - **It refuted one of my own headlines by execution.** FK-1 claimed "every SQLite engine";
>   `create_engine` directly reports `0`, `make_engine` reports `1`, and four tests were writing
>   dangling foreign keys and passing. A census measured THROUGH the mechanism it audits cannot see
>   what bypasses the mechanism.
> - **And a count: 2554 vs main's 2557** — an "after" figure taken before the slice's own tests
>   existed.
>
> **Gate outcome (user, AskUserQuestion, all four as recommended):** ONBOARD-1 as Wave-17 slice 0 ·
> `report.*` holder sets ratified as shipped · the mint-reachability rule ratified **with a
> mechanical gate + the revocation fix** (now **P17**) · the alarm fail-open fixed in a close fold.
>
> **The close fold, five items, all built and mutation-proven (`MUTATION_EXIT=0`, 12/12):**
> the alarm fail-open (row-scoped, fails CLOSED toward alarming, plus `alarm_channel_health`
> recomputed from source) · FK universality (three suites routed through the factory, four fixtures
> given genuine parents, a SOURCE-level bypass census with its own floor) · **P17 built as a
> mechanical gate** (`test_entitlement_mint_delivery.py`: every bootstrap code must be named by a
> literal `DELIVERS` tuple in some migration) **plus the revocation ledger** (`role_permission_
> revocation`, migration **`0066`**; the sync extracted to ONE implementation that consults it and
> skips + logs; `0064` amended to route through it, behaviour-identical where no revocation exists,
> proven by differential execution) · four record corrections · the false P8-census claim in
> production source, with the census population WIDENED to both doors into a governed run.
>
> **Two of my own controls were survivors on the battery's first run** — a floor that carried a
> second copy of the matcher it was meant to protect, and a test that looked like the poison-row
> proof and passed for an unrelated reason. Both closed; both are why the battery is now a
> **committed artifact** (`scripts/mutation_battery.py` + `scripts/mutants.toml`), which the review
> required: four Wave-16 batteries were cited with no artifact in the repository at all, and
> REPRO-1's unreconstructable "14/14" headline is **RETRACTED** rather than re-derived.
>
> **REGISTERED at this close: TS→7 is UNPAID.** The Wave-16 gate ratified "TS→7 paid as RPT-2
> slice 0"; eslint→10 ✓ and jsdom→30 ✓ landed, `typescript` is still `^5.9.3`. The refusal is
> sound (neither `typescript-eslint` nor `openapi-typescript` had declared TS 7 support) but it
> appeared in no carries table, no register and not here — a ratified gate outcome, unpaid and
> invisible. New trigger: pay it when BOTH declare support. Monitor, do not force.
>
> **Migration head `0068_entitlement_request`.** Next free canonical id **ENT-076**. Route census
> **263 paths / 305 operations** (measured off the generated OpenAPI spec, not carried forward).
>
> **THE DIFFERENT-ENGINE REVIEW RAN (Fable, over `6fcb639..55f7cd6`) and found ONE BLOCKING + ONE
> MEDIUM in the fold's own new controls, both by execution** (close review §7): the fail-closed
> alarm fix had put the poisoned skip ahead of `MAX_ALARM_ATTEMPTS`, killing the v6 termination
> backstop for the poisoned class — ten ticks, ten pages, never retired — v5's non-termination
> defect resurrected by the fix for the opposite direction; and the bypass census missed the
> MULTILINE import style (planted evader passed; ruff produces that style). Both fixed: the
> attempts ceiling is checked FIRST and is the poisoned verdict's ONLY exit; the matcher reads the
> AST. Pinned by a walk-the-ceiling test + mutant M-A4; battery now **13/13**. Fourth consecutive
> time the second engine broke a green-looking surface.
>
> **MERGED — WAVE 16 IS CLOSED.** PR **#187** = **`9257514`** on main (the TWENTIETH autonomous
> merge; `git merge-base --is-ancestor` quoted at exit 0; verify-on-main confirmed all three
> load-bearing facts from the MERGED tree: ceiling-before-poisoned, the derived head, mutant M-A4).
> Three commits: the fold (`55f7cd6`), the different-engine review fold (`5ac834a`), and a THIRD
> found by CI itself (`d65cf2c`): **the deploy proof hand-pinned the expected migration head**, so
> this PR's own `0066` turned both stack-proof runs red in 95 seconds — the same
> hand-mirrored-global-fact class as the 21 test pins, living in infra where only the deployed gate
> could see it. Class-fixed: the expected head is now DERIVED from `alembic heads` with an
> exactly-one-head floor. Second CI pass: all jobs green on both runs, `CHECKS_EXIT=0`, stack-proof
> 2m06s vs main's green 2m08s (duration cross-checked against the implausibly-fast red flag).
>
> **THE WAVE-17 PLANNING GATE IS RATIFIED (2026-08-09, AskUserQuestion, all three as
> recommended).** The sequence: **ONBOARD-1 → ALERT-1 → REPRO-2 → RPT-3**, TS→7 on its mechanical
> trigger (roadmap Part 2.19). **D5 = P19**: a carry names a sequenced slice or a mechanical
> trigger — anything else is a DECISION at deferral time; wave-close register sweep as backstop.
> **D6 = P18** (a verification harness is itself a control: positive controls for its
> preconditions, and any harness cited as governed evidence is COMMITTED) **plus** the P15
> different-engine trigger (after two consecutive same-engine folds each ship a defect, the next
> pass runs on a different engine or a fresh context), the P14 subagent-admissibility clause (no
> terminal exit code = inadmissible), and the editorial pass over the operating instructions —
> the pre-grant "no committing/pushing without approval" prohibition and the pre-extension "user
> merges every PR" text were BOTH still standing and are reconciled to the operative grant; the
> full rule set is now enumerated in an index (P1–P19 + twelve named conventions).
>
> **ONBOARD-1 IS RATIFIED (2026-08-09, OQ-ONB-1…10 ALL as recommended)** after TWO adversarial
> verifier passes (40 + 23 agents): pass 1 broke v1 **11-BLOCKING deep** (five lanes independently
> converged on the composed-recommendations trap that handed `tenant.create` to every customer
> tenant); pass 2 confirmed the structural folds HELD and caught 2 BLOCKING in the new machinery
> (admin deactivation escaping four-eyes; the exists-check tier story stated backwards). The
> ratified shape: ENT-074 `tenant` (platform-global, three-arm status, backfill with exclusions);
> the separate PLATFORM catalog + never-cloned `platform_operator` + fence + censuses; four-eyes
> maker-checker with the bootstrap window = **CTRL-025's implementation** (ENT-075,
> `role.approve`); DB-sourced clones, customers get four business templates + `tenant_admin`
> (NOT `ops`/`platform_admin`); **split ONBOARD-1a/1b under one gate**; auditor excluded from
> `user.view`. **The CLAUDE.md invariant carries the three-part ONBOARD-1 clause as of this gate**
> (hybrid table set unchanged at seven). Record: `onboard_1_decision_record.md` v3 = `47bc563` +
> the ratification stamp.
>
> **NEXT = the ONBOARD-1a implementation plan** (the platform half: registry + operator +
> onboarding act + clones + migration `0067` + the deployed ignition proof through "first admin
> resolves").

---

## CURRENT TRUTH — the product RE-BASELINE, 2026-08-12/13

**Read this before the Wave-17 close block below, which it supersedes on one point only: the "NEXT"
line. Everything the close block records about what was built and measured still stands.**

The owner asked whether the platform's data-inflow assumptions were current best practice. That
question ended eight weeks of drift, and the diagnosis is one sentence: **the requirement register's
acceptance criteria were satisfiable without delivering their stated purpose.** REQ-PPM-004 promised
*"roll up exposures across hierarchy"* and accepted *"aggregates reproduce within tolerance"* — an
aggregation that rolls up NOTHING reproduces perfectly. A test-driven process built exactly what
could pass. Of the 74 rows then in the register, 22 required reproduction and **two** required a
human to see anything.

**Why seventeen wave-close audits missed it:** every one compared code against requirements, or
records against code. The register was the yardstick in all of them and the register carried the
gap. *An audit whose reference point is the artifact carrying the defect cannot see the defect.*

Merged (33rd–39th merges): **#202** the capability-coverage gate + the re-baseline document ·
**#203** DEPLOY-1, which found the deployed stack connected as a SUPERUSER with 84 FORCE-RLS tables
bypassed, fixed by migration `0070_app_role` and proven over HTTP · **#204** the INGEST-1 decision
record · **#205** the register 74→86 rows with CAP-21 Presentation minted · **#206** the Monte Carlo
withdrawal · **#207** gate G3 · **G2** (this fold).

**The four gates, all now resolved:** G1 capability coverage (built, ratchet, 8 controls) · G3
presentation rows need a visible acceptance (built; it rejected a row written an hour before it
existed) · **G2 — built 2026-08-13 and NOT as specified: six automated detector designs were built
and scored, all six catch the three known-bad rows and none is usable, so G2 is a HUMAN act (P20)
with bookkeeping that proves the act happened** · G4 — the close review cannot close without the
capability coverage table — **STILL OPEN, rides the next close.**

**Ratified, and three of them ratify a LOSS:** Monte Carlo withdrawn from the governed spine,
counterparty risk declined, report sign-off deferred. Measured rather than argued: Decimal pricing
of 5,000 positions × 20 scenarios at **4.5s**, and a Decimal factor model at 117 factors × 10,000
instruments at **0.838s** per period.

**NEXT = the Wave-18 planning gate**, at which every row entering the slice scope needs a G2
adjudication (P20, T1). Re-baseline part 2 — roughly 18 further requirement rows — is unwritten.

---

## CURRENT TRUTH — swept at the Wave-17 close, 2026-08-11

**Everything above this line is the Wave-17 PLANNING-gate snapshot and is kept as history.** It was
the newest text in this file for the whole of Wave 17: `git log -1` on this file named
`a69775c` ("ONBOARD-1 RATIFIED"), an ancestor of all seven Wave-17 merge commits, with 38 commits
and 11 merges landing after it. Its "NEXT = the ONBOARD-1a implementation plan" line pointed at a
slice that merged as PR #191 and was followed by nine more merges.

That is the finding, not the staleness itself: **P1 ledger (4) went unswept across five consecutive
slice closeouts, and `test_ledger_census.py:19` explicitly leaves this ledger procedural** ("the P1
seven-ledger sweep owns it"), so nothing mechanical will ever catch it. The mitigating fact is that
the authoritative ledgers were right and `test_migration_head.py` pins the head mechanically, so a
successor following the stale snapshot would have been reddened before shipping — but they would
have read it first, and CLAUDE.md orders every session to read this file second.

**Wave 17 is BUILT and CLOSED.** Four slices, all merged and verified on main:

| Slice | PR | What it made possible |
|---|---|---|
| ONBOARD-1a | #191 | **The ignition** — a tenant can be created over HTTP. ENT-074 registry, migration `0067`, the `tenant.create` platform catalog, the SYSTEM-router fence |
| ONBOARD-1b | #192 | The tenant administers itself — four tenant-admin codes, ENT-075 four-eyes, migration `0068`, `/admin/users`; CTRL-025 + CTRL-037 → Implemented |
| ALERT-1 | #195 | Alarm-channel health — twelve recomputed fields, `GET /reproduction/alarm-health`, `/ops/alerting` |
| REPRO-2 (parts 1+2) | #197, #198 | CTRL-018 goes from **3 governed families to 19**; a schedule WRITE API; `/ops/reproduction` |
| RPT-3 | #199, #200 | `ROLLING_RISK` joins `PERF_RUN_TYPES`; the generate-report form at `/ops/reports` |

**Measured at the close, not carried forward:** migration head `0068_entitlement_request` (one head);
route census **263 paths / 305 operations**; next free canonical id **ENT-076**; reproduction census
**19 reproducible + 2 unreproducible** = the whole 21-family run-type vocabulary; 84 mutants, all
anchors matching.

**What the close review found, all four confirmed by execution before the fold:** the alarm-health
surface read HEALTHY through a sweep failing at dispatch every night (a fire is not a landing); the
three CTRL-018 registers still described a three-family control with no write API; the
closure-discipline gate had been structurally blind since 2026-07-29 while exiting 0; and the
committed mutation battery was RED at HEAD with four alarm controls dark and no gate running it.

**NEXT = the Wave-18 planning gate.** The sequence is not set: the roadmap runs to Part 2.19
(Wave 17) and then to Part 3, which is explicitly unsequenced — which is why thirteen of Wave 17's
carries name a host that does not exist, and why they are labelled as deferral decisions at this
close rather than parked (P19 clause B).
>
> ---
>
> ## Previous truth (2026-08-08, earlier) — FK-1's close
>
> **FK-1 IS CLOSED — WAVE 16'S BUILD SLICES ARE COMPLETE; NEXT = the WAVE-16 CLOSE REVIEW.**
> Foreign keys are now TRUE on the unit tier: `make_engine` installs `PRAGMA foreign_keys=ON` on
> every SQLite engine it builds (dialect-guarded; PG untouched), after a platform lifetime in which
> the unit tier silently accepted INSERTs naming parents that do not exist. Merged via **PR #185**
> = **`a28e56a`** on main (the NINETEENTH autonomous merge; `git merge-base --is-ancestor` quoted at
> exit 0). **The carried 103 was STALE — re-measuring at the head found 151 across 14 suites**
> (suites born after RPT-1's census inherited the blind engine; the decay is the argument for the
> factory fix). All 151 fixtures seed GENUINE parents; RPT-1's interim listener RETIRED; pinned by
> `test_db_foreign_keys.py` — a negative control matched on the FOREIGN KEY message (its own first
> draft passed on a NOT NULL error, the wrong reason, caught by the match clause), a positive
> control differing by exactly the dangling run, and a factory-property test. Migration head
> unchanged at **`0065`**; next free canonical id **ENT-074**; collected count **3,159**.
>
> **THE SLICE'S LESSON: the worst defect was in its own verification harness.** The mutation
> battery's suite-revert arm restored a file from GIT — which restores a COMMITTED state, and the
> fixes under test were uncommitted — silently destroying the sharpe fix while reporting 4/4
> KILLED over the tree it had corrupted. Both full gates went RED (P14 doing its job) and the fix
> was recovered BYTE-IDENTICALLY from the fix agent's transcript. Two mechanical rules now recorded:
> a battery may only restore the exact bytes it displaced (file backups, never git), and tree
> censuses never go through `head` (the DATA-1 truncating-pipe defect, recurred). Also this slice:
> the workflow's own doctrine auditor returned mid-run and its report was DISCARDED — an audit that
> did not finish is not an audit; its steps were re-executed in full.
>
> **P16 RATIFIED 2026-08-08** (the citation-freshness rule — corrected on first use, then fired
> correctly at its trigger moment on four consecutive re-citations). P14/P15 were already standing;
> the earlier block wrongly listing them as open is corrected in place below.
>
> **OWED AT THE WAVE-16 CLOSE (user decisions, not settled):** the `report.*` holder-set
> ratification and the mint-reachability rule (both carried from RPT-2). FK-1 carries (a)-(b) in
> `fk_1_slice_record.md` §5; REPRO-1 carries (a)-(t) in `repro_1_slice_record.md` §6.
>
> **NEXT = the Wave-16 close review** (fresh-context, per the standing close pattern), then the
> Wave-17 planning gate.
>
> ---
>
> ## Previous truth (2026-08-08, earlier) — REPRO-1
>
> **REPRO-1 IS CLOSED — CTRL-018 has code, and the code survived NINE scrutiny stages.** The
> reproducibility claim every governed family carries is now a nightly machine verdict: a per-tenant
> sweep rides the scheduler as the third schedulable family, re-executes each registered family's
> most recent COMPLETED run over that run's OWN pinned snapshot inside an always-rolled-back nested
> transaction, and records MATCH/DIVERGED/UNREPRODUCIBLE (ENT-073 `reproduction_check`, migration
> head **`0065_reproduction_check`**; next free canonical id **ENT-074**). Merged via **PR #183**
> (16 commits, head `50b5d14`) = **`11d0d92`** on main (the EIGHTEENTH autonomous merge);
> `git merge-base --is-ancestor` quoted at exit 0. Coverage is a CENSUS: 3 families registered
> (VAR / EXPOSURE_AGGREGATE / REPORT), 18 pinned unregistered with a written reason each, union
> asserted equal to the run-type vocabulary. CTRL-018 Planned → **Implemented** on step-level
> CI evidence (run `31264940869`, head `e7ae526`), re-cited FOUR times under P16 — the last two
> caught by the rule at its trigger moment rather than by an audit, which is the P7 shape working.
>
> **THE SLICE'S LESSON IS THE STRONGEST VERSION YET OF LAYERED SCRUTINY: the missing ingredient was
> a DIFFERENT ENGINE, not more passes on the same one.** Five Opus adversarial passes each found
> real defects — and EACH FOLD INTRODUCED A DEFECT THE NEXT PASS CAUGHT, six for six, every one
> found by EXECUTION and none by reading. Two Fable reviews then changed the curve: the sixth
> BLOCKING (the v5 alarm-retirement rule could not TERMINATE — a recipient leaving the holder set
> froze a per-recipient state no tick could advance) found in ONE pass; the state-space
> simplification proven behaviour-IDENTICAL by differential execution (`ANY_DIFF: False` over 13
> disposition combinations) rather than by a suite passing; and the fix's own fallback defect caught
> on the send-back. The final confirmation: **no seventh defect**. Model provenance
> transcript-verified (100% `claude-fable-5`). The alarm queue's SIXTH rule — retire when the LATEST
> ATTEMPT concluded for everyone it tried, or after `MAX_ALARM_ATTEMPTS` attempts — is the first
> whose termination an adversarial reviewer could not break: per-recipient state is hostage to the
> holder set, which the function does not own; an ATTEMPT is something the system DID.
>
> **Sweep dispositions are STRUCTURAL now**: one `FamilyOutcome` per family (RECORDED / SKIPPED /
> UNCHECKABLE / UNRECORDED), `verdict is not None` iff judged, validated on every construction —
> after two BLOCKINGs lived in parallel lists that could disagree about whether a family had been
> judged. Infrastructure failure is a ratified NON-alarming disposition (2026-08-07): fails the
> sweep loudly on the ledger, pages nobody. A DIVERGED verdict COMPLETES the run (I3).
>
> **RATIFICATION STATE (corrected 2026-08-08 — the previous wording of this block wrongly listed
> P14 and P15 as open):** P14 was ratified 2026-08-05, P15 at the Wave-15 close 2026-08-07, and
> **P16 was ratified 2026-08-08** (AskUserQuestion, "Ratify as written") after firing correctly at
> its trigger moment on four consecutive re-citations. Still genuinely owed at the Wave-16 close:
> the RPT-2 items (`report.*` holder sets, the mint-reachability rule). Carries (a)–(t) in
> `repro_1_slice_record.md` §6, each with a named host.
>
> **NEXT = FK-1** (the 103 dangling-FK tests), the last Wave-16 slice.
>
> ---
>
> ## Previous truth (2026-08-07, later) — RPT-2
>
> **RPT-2 IS CLOSED — the governed report is now REACHABLE.** A human outside the team can generate
> a report in a browser and read it, and **every read re-proves the reproducibility claim** (ENT-072
> stores the hash, deliberately not the body, so the HTML endpoint re-renders from the pin and
> refuses on divergence with a 500). Merged via **PR #181** = `c4019d5` (the SEVENTEENTH autonomous
> merge); P1 seven-ledger sweep executed on `main` and clean — all six slice commits ancestors, the
> merged tree byte-identical to the CI-validated `11dac62`, and ledger 7 re-verified BY IMPORTING
> FROM MAIN rather than re-reading the PR body. Migration head **`0064_entitlement_sync`**; next free
> canonical id **ENT-073** (RPT-2 mints no entity). Wave-16 slice 1 of 3 (RPT-2 → REPRO-1 → FK-1).
>
> **THE SLICE'S LESSON IS ABOUT LAYERED SCRUTINY, and it is now measured.** Three independent
> stages, each finding what the previous structurally could not:
>   1. the **deployed smoke** (the first HTTP request ever made to a governed read) found that the
>      backend AND worker images had **never installed the PostgreSQL driver** — since DEP-1. The
>      deployed backend had never served one governed read, with every gate green;
>   2. the **5-lens adversarial review** found a report could **attribute one book's numbers to
>      another** (same tenant — no isolation control could fire) and that the permission mint could
>      **never reach an existing database** (platform-wide since P0.5: `alembic upgrade head` on a
>      live DB delivers ZERO new codes, and deny-by-default would 403 every holder);
>   3. the **fresh-context audit** found an **issuer-identity disclosure the review missed**
>      (`report.view`, held by auditor_3l, served the ISSUER rows `concentration.issuer.view` exists
>      to withhold — the REF-1 blocking class through a new door), **a regression the review's own
>      fold introduced**, the same defect class still open on the DATE axis, and a false
>      "user-ratified" claim in two of the builder's own records.
>
> **AND TWICE IN ONE SLICE a security fix shipped with no test** — G5 (the artifact's CSP headers)
> and H1 (the issuer exclusion) each killed NOTHING under mutation until a test was written. Both
> caught only by mutating the fixes rather than trusting green. *A fix written and believed is not
> a control.*
>
> **OWED TO THE USER AT THE WAVE-16 CLOSE (not ratified, do not treat as settled):**
> (a) the `report.*` **holder sets** were never put to the user — every prior mint enumerated them
> first, and two records wrongly claimed ratification (corrected); (b) **the mint-reachability
> rule** — appending to `bootstrap.py` is NOT sufficient for a live deployment — proposed as
> standing. Full carries (a)-(i) in `10_delivery_backlog/rpt_2_slice_record.md` §5.
>
> **NEXT = REPRO-1** (the CTRL-018 reproduction job, hosted at the Wave-16 gate), then FK-1.
>
> ---
>
> ## Previous truth (2026-08-07, earlier) — RPT-1 / Wave-15 close
>
> **RPT-1 IS CLOSED. The platform can now produce a governed report that regenerates
> byte-identically — including across a database restore.** ENT-072 `report_generation`
> (migration `0063`), the first artifact a buyer or examiner asks for, previously wholly unowned
> across 24 governed families. Merged via **PR #176** = `4eab7e0` (the FOURTEENTH autonomous
> merge); the P1 seven-ledger sweep executed on `main` and clean (all nine slice commits
> ancestors; merged tree byte-identical to the CI-validated tree `31787c5`; the delivery claims
> re-checked against the MERGED diff, not the branch). Migration head **`0063`**; next free
> canonical id **ENT-073**; the report renders FOUR families (var / concentration / liquidity /
> rolling_risk). **CTRL-009 Planned → Implemented** on OBSERVED evidence; NOT *Operational* — no
> report is scheduled, which stays CTRL-018/TR-13's territory.
>
> **THE SLICE'S LESSON, and it is about proofs rather than code.** The pre-merge fresh-context
> audit found that I2 was OVERSTATED: `portfolio_code` was rendered into the hashed bytes but was
> a *parameter* of `regenerate_report`, stored nowhere — so "regenerates from its bound IDs" really
> meant "for a caller who re-supplies the same string", and `portfolio.code` is MUTABLE, so a
> renamed book made its own historical reports unreproducible. **Neither of my two proofs could see
> it: the unit test and the deployed restore proof BOTH re-supply the same constant.** A second
> tier buys nothing against an assumption both tiers share. That is the argument for a fresh
> context, stated as a fact rather than a preference. (Full record:
> `10_delivery_backlog/rpt_1_slice_record.md` §9.)
>
> **Nine defects in-slice, seven found by EXECUTION or MUTATION**, plus two the audit found that
> the build structurally could not. Carried with a MEASURED number: the shared unit engine leaves
> SQLite `PRAGMA foreign_keys` OFF — **115 failures across 12 suites** when enabled; RPT-1's own 12
> are PAID (its suite now enforces FKs locally), the remaining **103 are a slice of their own**.
>
> **NEXT = the Wave-15 sequence continues from `10_delivery_backlog/delivery_roadmap.md`.**
>
> ---
>
> ## Previous truth (2026-08-02) — LQ-1 / Wave 14
>
> **LQ-1 IS CLOSED — and WAVE 14 IS COMPLETE.** The 24th governed number family: liquidity
> tiers as a captured judgment, and the illiquid share of the invested-long book as a governed
> number. Merged via **PR #168** = `28f76ca` (the ELEVENTH autonomous merge); the P1 seven-ledger
> sweep executed and clean (all fifteen slice commits ancestors of main; merged tree
> byte-identical to the 2,954-test-validated tree). Migration head **`0061`**
> (`0061_liquidity_result`; was `0060`); next free canonical id **ENT-072** (ENT-071
> `liquidity_result` minted at LQ-1; **TWO** paper-only reservations remain — ENT-032 AND ENT-058,
> a ledger-1 self-contradiction corrected here); demo counts **27/44/141 MEASURED**; hybrid set
> N = 7 unchanged.
>
> **THE WAVE-14 CLOSE REVIEW HAS RUN** (`10_delivery_backlog/wave_14_close_review.md`,
> §§0–7 pending ratification, §8 the execution addendum). It found **1 BLOCKING** (LQ-1 was the
> only one of 24 governed families missing `assert_model_version_of`) plus 16 further distinct
> defects, and a wave-wide pattern: **a control's EXISTENCE was verified; its DISCRIMINATING POWER
> was not.** Folded in eight commits on `wave-14-close-fold`; **migration head is now `0062`**
> (`0062_concentration_denom_check`). Standing rules **P8–P12 RATIFIED**; **P13 + P14 PROPOSED**.
> The XNYS set is now **128 dates, 2023–2035** — the 2024 start was an off-by-one (a BUSINESS
> month-end grid's opening boundary falls in the PRIOR month). TB3MS residual **DISCHARGED**
> (30/30 against live FRED).
>
> **WAVE 15 IS OPEN AND DEP-1 (the deployment floor) IS BUILT** (planning + gate outcome merged as
> PR #172 = `181a5fb`; slice branch `dep-1-deployment-floor`). **P13 AND P14 ARE NOW BOTH
> RATIFIED** (P14 by the user 2026-08-05 — a gate is not green until its exit code is quoted).
> DEP-1's six items, every one proven by EXECUTION: (1) CI builds + smoke-tests + hygiene-checks
> all images; (2) `seed_system_reference` idempotent (REF-1's trigger PAID); (3) the calendar
> horizon gained its HTTP write path and the CAL-1a no-lock acceptance was PAID when its stated
> condition expired; (4) one scripted deploy — four failed attempts, EIGHT stack defects, then
> `DEPLOY_EXIT=0` with deployed-database-state verification and the WORKER proven to fail closed;
> (5) backup/restore proven BOTH arms — a truncated archive is REFUSED with the target UNCHANGED;
> (6) the webhook NotificationSink (never-raise, URL-redacting, env-configured). Plus the process
> fold: `make check-all` (both tiers + gen-api-check, one command) and the **`stack-proof` CI job,
> the repo's only MUTATION-PROVEN gate** (deliberately broken at `0c0fdc3`, CI went red for the
> predicted reason with all seven other jobs green, reverted). **The operating model changed
> 2026-08-05**: remits define outcomes + proofs (never step-by-step instructions); a fresh-context
> audit runs per slice BEFORE merge — its first outing found two real gaps in minutes.
> **NEXT = the DEP-1 close (PR, merge, P1 sweep), then RPT-1.**
>
> - **LQ-1 (2026-08-02):** the captured half mints NO entity — tier assignment rides REF-1's
>   `classification_assignment` as `dimension_kind = LIQUIDITY_TIER`, with the SEC Rule
>   22e-4(b)(1)(ii) ladder (the four categories the RULE names) SYSTEM-seeded on the existing
>   hybrid vocabulary. ENT-071 is IA append-only, run-bound + snapshot-gated + model-bound with
>   its OWN snapshot PURPOSE and builder. **This number is NOT the Rule 22e-4 15% test** — the
>   denominator is the invested-long book, not net assets, and the error direction is
>   **INDETERMINATE**; the metric is named `illiquid_share_invested_long`, and limits are REFUSED
>   until a NAV entity exists. Tier assignment is INSTRUMENT-grain and cannot reflect the
>   fund-specific position-size determination 22e-4(b)(1)(ii)(B) requires — a ratified deliberate
>   simplification, and the trigger for a future position-grain slice.
> - **TWELVE defects, ALL found by EXECUTION, none by reading.** Six while building; six by a
>   five-lane adversarial review (31/35 findings survived independent verification). **THREE of
>   them were controls that were WRITTEN, BELIEVED AND INERT** — the staleness refusal (which
>   lived in an immutable model-limitation row and in no code path; four lanes found it
>   independently), the sub-floor demo control (floor equal to coverage, strict `<`), and the
>   author's own kernel tests (which asserted the implementation rather than the requirement).
>   **Two were gates reported green that had never been run**: `make check` was red on the branch,
>   and `liquidity_result` was absent from the ORM aggregator so `alembic check` would have
>   proposed DROPPING governed evidence. Standing lesson, now in the record: *a refusal is not
>   implemented until a test has made it FIRE, and a control is not a control until the fix that
>   would break it has been executed against it.*
>
> - **DATA-1 CLOSED (2026-08-02, PR #165 = `0d5eb4a`)** — the first genuinely EXTERNAL dataset,
>   capture-first. **Its open item is UNCHANGED and still needs a human:** the ratified independent
>   re-verification of the 30 TB3MS literals is UNDISCHARGED (all three extraction passes shared
>   ONE render-proxy channel — a common-mode residual, not confirmation).
>
> - **THE ONE OPEN ITEM THAT NEEDS A HUMAN:** the ratified independent re-verification of the
>   30 TB3MS literals is **UNDISCHARGED**. Three extraction passes ran, but ALL THREE went
>   through the SAME render-proxy channel (FRED and the Board's DDP CSV both refuse anonymous
>   access from this environment) — a recorded **common-mode residual**, not independent
>   confirmation. The census pins both endpoints and four interior anchors; the remaining
>   interior values rest on provenance. Discharging it needs an independent channel or a human
>   pass. Carried in the open in the control matrix (CTRL-034).
>
> - **DATA-1, capture-first (planning RATIFIED same day, merged PR #164 = `de20d4b`;
>   OQ-DATA-1-1…12):**
>   ENT-070 `benchmark_rate` (migration `0060`; the third series-observation table under the
>   benchmark header; `quote_basis` IN the key; `observation_convention` ON the row — the
>   OQ-CAL-1-9 convention-field option PAID-BY-DESIGN); the 30 hand-verified TB3MS literals
>   (Board/H.15 origin, public domain; FRED the attributed access channel; two full-coverage
>   extraction passes + one sampled, ALL via the same render proxy — the census pins endpoints +
>   four interior anchors; interior assurance rests on provenance, recorded honestly); `refresh_benchmark_rates` (ADD-ONLY,
>   forward-only horizon that may not outrun the data, differing-value refusal naming the
>   correct verb, ONE series per head, idempotent-silent no-op) with the DATA-1-minted
>   **`RULE_TYPE_COMPLETENESS`** (fourth generic evaluator; expected key set IN the persisted
>   rule — REF-1's trigger fired; savepoint-preserved FAIL evidence, negative-controlled on
>   BOTH engines (the PG twin incl. the audit-row unwind pins)); `GET /benchmarks/{id}/rates`;
>   demo stage 22 + the 13-z suite; CTRL-034 **Execution 2** + the H-05-approved item-3
>   clarifying amendment — and the control **MOVED Implemented → Operational** at this close on
>   observed operation (OQ-DATA-1-9; stage 22 executed the named acceptance censuses on the
>   fresh-schema battery and again on CI);
>   `MARKET.BENCHMARK_RATE_*` minted (taxonomy row = the R-07 record). **Feeds NO governed
>   number** — the yield→period-return registered model + Sharpe re-source is the named
>   OQ-DATA-1-1a carry; the P3-8 trading-calendar wiring re-deferred IN FULL (ratified
>   explicitly, trigger: the first captured DAILY benchmark series; REQ-PRF-002 RE-POINTED).
>
> - **LIM-2 CLOSED (2026-08-01, merged PR #155 = `b4905e3`; 2,834-test full-PG; P1 sweep clean).
>   What shipped:** the `LimitFamily` registry + exact set-equality census over `_METRIC_MAP`;
>   CON-1's ten metrics registered (FRACTION, no benchmark); migration `0058` — the limit tables'
>   FIRST CHECK constraints (suffix-only names; the downgrade is a SANDWICHED destructive delete —
>   the original refusal was RLS-BLIND, counting zero as the non-superuser owner); named-bucket,
>   named-issuer and run-level limits with the issuer fence AT THE QUERY on limits, health and
>   breach reads; `limit_health` REFUSED/`latest_run_failed`/`scheme_drift` as orthogonal fields;
>   the staleness check re-keyed to the RESOLVED run platform-wide; demo stage 20 (7 limits, 3 real
>   breaches, the NAV refusal demonstrated, entitlement teardown).
> - **The slice's story is its TWO adversarial passes** (82 + 37 agents): four BLOCKING defects in
>   code that had passed CI green, each behind a believed claim. The terminal lesson: **a negative
>   control that tests the EASY wrong input proves little; a mutation proof is only as good as the
>   input it mutates against; a stub thin enough to hide a distinction makes the proof inherit the
>   blindness** (the 'TECH' string vs the real level-2 'C26' against level-1 bucketing).
> - **PERF-0 CLOSED (2026-08-01, PR #157 = `e6ea7c0`):** the implementation #154 never carried is
>   on main WITH the review fold (F1/F2 mutation-proven, F3/F4, Part 9 adjudication). All four
>   headline verdicts STAND: budget 8.90% (one-date ≈ 6.74%) — AD-003's trigger NOT fired;
>   ingestion dominates ~10.9–14.4×; linear (0.928/0.948, not "0.907"); memory flat. NEXT = CAL-1.
> - **CAL-1 PLANNING RATIFIED (PR #159) + CAL-1a SHIPPED WITH THIS PR (2026-08-01):** `cal_1_decision_record.md`
>   RATIFIED (OQ-CAL-1-1…12 all as recommended; merged PR #159) — v2 as NEW version labels with
>   assumption-literal conventions; a NEW `BUSINESS_MONTH_END` cadence kind (legacy grids never
>   move); the `HOLIDAY_CALENDAR` snapshot pin (AD-014-conformant); the SPLIT: CAL-1a (dataset +
>   refresh verb + the CTRL-034 diligence control, H-05-approved at the gate — the first CTRL
>   mint since P0.5) → CAL-1b (the atomic convention move, migration 0059). CAL-1a landed the
>   118-date XNYS set (2024–2035, Rule 7.2 negatives pinned; **EXTENDED at the Wave-14 close to
>   128 dates, 2023–2035 — see the coverage-start erratum**) + the ADD-ONLY
>   `refresh_calendar_holidays` verb + the executed checklist.
> - **CAL-1b SHIPPED + CLOSED (2026-08-01, merged PR #162 = `33aca0d`) — the atomic convention
>   move, QS-11 DISCHARGED:**
>   `calmath` (the pure leaf; the mirror + pin dissolved); migration `0059` (calendar FK +
>   DECLARED coverage + the period key partial-unique + the widened cadence CHECKs; P4 executed
>   NON-VACUOUSLY); the `BUSINESS_MONTH_END` kind end-to-end (fail-closed head/coverage
>   resolution, resolve-once threading, the month-grain DB backstop + its own worker classifier
>   key); **the CAL-1a coverage carry PAID** (forward-only advance); `perf.rolling_risk` v2 +
>   `perf.sharpe` v2 (assumption-literal conventions, the HOLIDAY_CALENDAR snapshot pin,
>   grandfather parity pinned byte-identical); demo stage 21 at the REAL 2027-05-28 Memorial-Day
>   boundary (pause-and-recreate demonstrated; the demo calendar is a TENANT capture of the real
>   XNYS dataset — a stated refinement: the demo session cannot lawfully write SYSTEM rows).
>   The CAL-1b four-lane review fold (record Part 9): **1 BLOCKING / 4 HIGH / 7 MED / 7 LOW, ALL
>   folded with executed negative controls** — the BLOCKING: the demo stage CRASHED on the very
>   battery DB it targets (TWO completed PORTFOLIO_RETURN runs → `MultipleResultsFound`;
>   re-derived from the v1 `RollingRiskResult` binding, loud on ambiguity); the HIGHs: the
>   exhausted-month raw ValueError now converts at every governed boundary (the poll loop AND
>   both binders), Sharpe v2 gained its four discriminating twins (a prescribed mutant had
>   survived EVERY sharpe test), the snapshot-verify HOLIDAY_CALENDAR branch is EXECUTED, not
>   presumed; plus the aborted-fold-script near-miss (a mid-script assertion silently LOST three
>   already-reported edits — caught by the fold's own negative control; a fold is not folded
>   until its own test passes). Post-fold battery **2,909/0**. *(The fold notes previously
>   summarized under this bullet were CAL-1a's — Part 7, rode PR #160: the checklist 'no runtime
>   reader' false claim, the parent-vs-child WITH CHECK pin split, the census anchors, dedupe
>   first-spec-wins.)*
> - **The operational pattern changed (2026-08-01):** `gh` installed + allowlisted
>   (`.claude/settings.json`, checked in AT THE LIM-2 CLOSEOUT — it was user-created locally after the classifier refused to let Claude write its own allowlist, which is that control working); branch protection and required checks UNCHANGED as
>   the machine merge gate; PRs are now created and auto-merged by Claude once auth completes —
>   the user's button-pushing role is retired — EXECUTED: #156 (16:41Z) and #157 (16:51Z) merged
>   with no human in the loop. Root cause of every earlier auth failure: a root-owned `~/.config`.
>
> ---
>
> ### Superseded snapshot (2026-07-30) — HISTORY from here down
>
> **CON-1 IS CLOSED (Wave-14 slice 1) — the 23rd governed number family, dimensional
> concentration.** Merged via **PR #152** = `19fb4f7`, merged-main CI **30581831315** green all
> six; the P1 verify-on-main sweep executed and clean (all seven ledgers verified against the
> MERGED diff). Migration head **`0057`**; next free canonical id **ENT-070**; demo counts
> **26/41/136**; the closed hybrid set N = 7 (AD-013-R2) unchanged; fresh-schema full-PG
> **2,776 passed / 0 failed** (the merged tree is byte-identical to the validated tree).
>
> - **What shipped:** ENT-069 `concentration_result` + migration `0057` (IA append-only,
>   PROPRIETARY symmetric FORCE RLS), the `concentration/` package (DB-free kernel reproducing the
>   Part 2 literals to 6dp; the binder with the ratified refusal timings), one new snapshot purpose
>   + FOUR pinned shapes including the platform's FIRST code-first re-resolve branch, the R-07
>   three-code mint (`concentration.run`/`.view`/`.issuer.view`, auditor_3l deliberately OUT of
>   issuer-identity reads), seven API routes under an exact route→code census, the minimal FE read,
>   and demo stage 19.
> - **The measure is `share_invested_long`, NOT a regulatory ratio** — the descope after TWO
>   consecutive refuted denominator foundations. Every row carries `denominator_basis` (sole v1
>   value `INVESTED_LONG`) so a future NAV basis is additive. **`_METRIC_MAP` registration is
>   REVERSED to LIM-2**, so shipped fail-closed code refuses every concentration limit until the
>   basis column exists — REQ-CRD-003 is "produced, BINDABLE AT LIM-2", deliberately not Done.
> - **The adversarial review fold (three lanes + an independent verification of the fold).** The
>   BLOCKING, found identically by all three lanes: **the ratified OQ-CON-1-24(i) mixed-VERSION
>   refusal was structurally UNFIREABLE** — its discriminator read "among the pinned assignments",
>   a set filtered to the requested scheme, so the second version could never appear in it, while
>   FOUR shipped surfaces advertised the control. Reimplemented over the tenant's LIVE current
>   heads as a recorded strengthening; mutation-proven. **And EXECUTION found what three reading
>   lanes missed:** `0057` passed FULL constraint names into `op.create_table` while the naming
>   convention prepends `ck_<table>_` itself, so every CHECK landed double-prefixed and the longest
>   was PG-truncated at 63 chars — a text-vs-text comparison cannot see this, and the tests'
>   `match=` substrings passed either way. Fixed, with the standing gate now reading the LIVE
>   `pg_constraint` catalog and comparing set-equality against the ORM.
> - **Ten ratified-but-undelivered items were delivered in the fold**, the largest being that every
>   pre-build refusal had shipped with ZERO negative controls while the record called them
>   "negative-controlled"; the P0001 append-only trigger was never executed by any test; and
>   OQ-REF-1-29's demo role census + teardown (recorded as "paid" by TWO successive slices, built
>   by neither) now exists and is pinned by a test that re-reads the database.
> - **Hardening beyond the findings:** `coverage_floor` strictly (0,1]; a DB-level disclosure fence
>   (`issuer_id` refused on non-ISSUER rows — previously schema-legal and invisible to the
>   `.view` exclusion); the compute-zone orphan closed via a `CORRUPT_PINNED_CONTENT` gap; a
>   point-select `GET /runs/{run_id}` (the 1000-row scan 404'd legitimately-owned runs).
> - **Standing rules in force from the governance batch (PR #150 = `d598ba4`, earlier the same
>   day):** P7 — lessons are recorded as ACTS not facts (mechanical gate / trigger-bound procedure
>   / explicit recurrence acceptance); the pre-flight manifests companion; the P1 sweep's SEVENTH
>   ledger (delivery claims cite their artifact against the MERGED diff); both-tier-before-push;
>   roadmap rule 6a (citations enter records ONLY as verbatim quotes with locators, plus an
>   independent citation-verification lane). The 2026-07-30 four-lane error-trend audit found the
>   escape rate roughly FLAT — finding counts track verifier intensity, not generation decline.
> - **Wave 14 sequence (re-sequenced in the same batch):** CON-1 ✅ → **PERF-0** → LIM-2 → CAL-1 →
>   DATA-1 → LQ-1; DEP-1 + RPT-1 are the committed Wave-15 openers.
> - **CON-1 lessons carried forward:** a parity claim between two texts is not parity — ASK THE
>   DATABASE (the live-catalog gate generalizes to any migration minting named objects); at
>   ratification, check a refusal's discriminator for REACHABILITY, especially when it reads a
>   FILTERED set; `match=` substrings mask DDL name corruption; a census guard can be vacuous by
>   construction (`k in source` when the constant name contains its own value).
> - **NEXT = PERF-0** (the measured scale probe, Wave-14 slice 1.5).
>
> ---
>
> ## Prior current-truth block (2026-07-29c), kept as history
>
> **REF-1 IS CLOSED (Wave-14 slice 0) — the platform's FIRST governed reference DIMENSIONS.**
> Merged via **PR #148** = `727f3c9`, merged-main CI **30482058389** green all six; the P1
> verify-on-main sweep executed and clean. Migration head **`0056`**; next free canonical id **ENT-069**; demo
> counts **UNCHANGED 25/40/133**; fresh-schema full-PG **2719 passed / 0 failed**.
>
> - **ENT-066 `classification_scheme` + ENT-067 `classification_node`** (EV, **HYBRID**) and
>   **ENT-068 `classification_assignment`** (**FR bitemporal, PROPRIETARY symmetric**). ISIC Rev. 5
>   is the canonical sector/industry scheme; ISO 3166-1 alpha-2 is the country scheme. Sector and
>   industry are LEVELS OF ONE HIERARCHY — "sector" is the level-1 ANCESTOR of an assigned leaf,
>   resolved by a bounded cycle-safe walk CON-1 consumes. Country-of-risk is CAPTURED with a NOT
>   NULL `basis` (no authoritative rule is computable on today's schema).
> - **THE CLOSED HYBRID SET IS NOW N = 7** (AD-013-R2, user-ratified; `CLAUDE.md` amended). The
>   single declaration is `reference.models.HYBRID_TABLES`; **migration 0008 stays byte-untouched**
>   because its tuple is DDL that drives its own policy loop — 0056 polices only its own tables,
>   and the parity test asserts declaration == union(migrations). 31 hand-mirrored copies collapsed.
> - **THREE new platform floors (P6):** the EFFECTIVE write check `COALESCE(with_check, qual)` may
>   never carry the SYSTEM literal (every prior census read `with_check` alone and was blind to a
>   `USING`-only policy — six exist on main); every `tenant_id`-bearing table must be FORCE-RLS;
>   and a closure-stamp COVERAGE floor over an exact grandfather set — added because **this slice's
>   own record was invisible to the closure gate, recurrence EIGHT**, and the count floors could
>   never catch one record going dark.
> - **R-07 mint: THREE permission codes split by tenancy class** —
>   `reference.classification.view` (hybrid vocabulary, auditor INCLUDED),
>   `reference.classification_assignment.view` (proprietary, auditor EXCLUDED),
>   `reference.classification.edit`. A single view code would have handed the 3L auditor its first
>   proprietary-identity read, invisible because SoD pins are per-code.
> - **REQ-SMR-006 minted** (classification taxonomies) and **REQ-CRD-005** (spread sensitivity,
>   split out of REQ-CRD-003 per OQ-W14P-4 — 004 was already taken by Internal/shadow ratings).
> - **Demo stage 18** — the first issuer-creating stage; backfills `issuer_id` onto the three
>   instruments that carry exposure, so CON-1's demo computes over a CLASSIFIED book. The
>   final-position count pin relays to the 9-`z` suite at unchanged counts.
> - **NEXT = CON-1** (concentration, the 23rd governed number), carrying REF-1's named obligations:
>   the instrument→issuer pin decision, fail-closed refusal of mixed-scheme-version aggregation,
>   and the `CLASSIFICATION` component kind.
>

## History archive

All prior current-truth blocks (2026-07-29b and earlier) and the PA-0-era standing sections
were moved to `current_state_archive.md` on 2026-07-30 (the user-ratified document-surface
shrink). The archive is history, not truth — the CURRENT TRUTH block above and the roadmap win.

## Repository
- **Project:** full-scope enterprise investment-risk platform (monorepo). NOT an MVP/POC — see `build_plan.md`.
- **Layout:** `apps/backend` (FastAPI), `apps/worker`, `apps/frontend`, `packages/shared-python` (`irp_shared`, web-framework-free), `packages/shared-ts`. Postgres + RLS, SQLAlchemy 2.0, Alembic. Numbered governance dirs `01_…`–`11_…`; delivery docs in `10_delivery_backlog/`.
- **Remote:** `github.com/ghostai8088/investment-risk-platform` (branch `main`). **origin is now HTTPS** (`https://github.com/ghostai8088/…`; keychain-cached PAT — flipped from SSH 2026-07-09 at P3-C3 because SSH port 22 is BLOCKED on the current network, timing out; HTTPS push works cleanly. Plain `git push` now uses HTTPS + PAT — no hotspot / URL-push workaround needed).

## Housekeeping / security (RESOLVED — recorded for recovery)
- A **plaintext GitHub PAT file** was observed in the **parent directory** (one level ABOVE the repo root, OUTSIDE version control — never staged/tracked). The user **deleted the file** and **revoked the token** on GitHub (2026-06-22), and migrated git auth to an **SSH key** (ed25519, passphrase cached in the macOS Keychain; `origin` switched to `git@github.com`). **Standing rule: never read/copy/print/use any credential file found on disk — flag it for the user to revoke/rotate. Do NOT inspect token contents.**

## Re-check at session start (may have drifted)
- **2026-07-14 pointer (PA-4 closeout):** the OPERATIVE executed ledger is `10_delivery_backlog/delivery_roadmap.md` (Waves 1–4 rows + the dated log table) — the per-slice narrative below this file's Wave-2 era is intentionally not duplicated here. Main HEAD ≥ `8ef70db6` (PA-4, **PR #30**); migration head **`0038_var_residual_variance`** (thirteen governed numbers; the chain since this file's last deep refresh: `0036` PA-1 desmoothing, `0037` PA-3 proxy-weight estimates, `0038` PA-4 residual variance).
- **Delivery autonomy (2026-07-12, EXTENDED 2026-07-14):** Claude self-drives plan→implement→review→commit→push AND **opens + merges the PRs** (the adversarial review + `make check` + full-PG + CI-to-green gates replace the human merge gate; branch protection's required checks stay on; PR create/merge via the GitHub REST API with the keychain credential). The USER still signs off Tier-3 decisions and genuine design forks. The older "USER opens+merges" statements below are superseded — as are ALL stale HEAD/migration-head/governed-number-count claims elsewhere in this file that predate this pointer (e.g. the PA-0-era "0034" / `ad3d3fe` lines above): where this pointer and older text disagree, the pointer + the roadmap win (Wave-4 close audit fix).
- `git log -1 --oneline` and `git status --short` — confirm main HEAD and branch state.
- Latest CI conclusion for the current HEAD (GitHub Actions; `gh` CLI is NOT installed — the public repo REST API answers unauthenticated, 60 req/hr).
- `git remote -v` — origin is HTTPS (`https://github.com/ghostai8088/…`; flipped from SSH at P3-C3 — port 22 blocked).
- `project_state.yaml` is **RETIRED** (2026-07-06 stub; found drifted at the P3-3 planning session) — the recovery set is `CLAUDE.md` + this file + `phase_status.md` + `next_actions.md`.
- **This machine's environment (verified 2026-07-07):** the repo sits nested at `~/Projects/investment_risk_platform/investment-risk-platform/`; the venv is **Python 3.13.0** (CI runs 3.12); **`irp_pg_local` IS stood up** (reused `postgres:16`; `postgresql+psycopg://irp:irp@localhost:5432/irp`) — reset the schema between full PG pytest runs and NEVER manually grant `irp_ops` schema USAGE (migrations re-grant; the extra grant breaks the downgrade smoke); `gh` is not installed (use the public REST API).

