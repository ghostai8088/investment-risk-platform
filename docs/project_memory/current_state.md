# Current State

> ## ⚠️ CURRENT TRUTH (2026-07-29c) — read this block; everything below it is HISTORY
>
> **REF-1 IS IMPLEMENTED (Wave-14 slice 0) — the platform's FIRST governed reference DIMENSIONS.**
> Branch `ref-1-planning`; migration head **`0056`**; next free canonical id **ENT-069**; demo
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
> ---
>
> ## Prior current-truth block (2026-07-29b), kept as history
>
> **WAVE 14 IS SLICED + RATIFIED (2026-07-29, OQ-W14P-1…8 ALL as recommended) — `wave_14_planning.md`
> (RATIFIED) + roadmap Part 2.18. The sequence: REF-1 (reference dimensions + the
> vendor-classification capture rail, L) → CON-1 (concentration, the 23rd governed family, M/L) →
> LIM-2 (the dimensional limit selector, M) → CAL-1 (ENT-006 holiday resolution + the atomic
> scheduler+perf convention move, M/L) → LQ-1 (liquidity tiers + governed % illiquid, M/L).
> NEXT = REF-1 planning.** Branch `wave-14-planning` (`489c7fd` = the verified draft, CI run
> **30464515268** green all six; the ratification folds follow on the same branch).
>
> - **Key wave-level ratifications:** real data = authoritative external datasets through governed
>   capture, NO live adapters (trigger: a real vendor contract); open taxonomy schemes (`scheme`
>   discriminator; licensed GICS/ICB = user procurement, additive later); REQ-CRD-003 SPLITS
>   (spread REQ minted at REF-1); REQ-LIQ-002 deferred + homed (Part 3 RTM-P4, event trigger);
>   **scheme tenancy = EXTEND THE HYBRID SET via AD-013-R2 + the CLAUDE.md closed-set invariant
>   amendment + 0008/ORM mirror updates — EXECUTING AT REF-1's GATE, not yet done** (assignments
>   stay per-tenant; holiday sets SYSTEM only if the source is public); demo campaign extends
>   (count-pin relay); FE toolchain debt re-deferred with triggers.
> - **Planning method:** 6-lane recon fan-out (P3 register-verification against `2411d00`) +
>   single-threaded draft + 4-lane refute-by-default verifier pass — **24 findings (2 BLOCKING,
>   4 HIGH, 12 MED, 6 LOW), ALL folded**; BLOCKINGs hand re-verified (slice-id collision with the
>   shipped Wave-3 RD-1 → renamed REF-1; the taxonomy-tenancy recommendation contradicted Accepted
>   AD-013 uncited → OQ-W14P-6 rebuilt around the AD-013/AD-013-R1 fork).
> - **The OQ-W14P-7 register re-sync EXECUTED on this branch:** LIM/BRC ×6, SCN-001 (stale ~11
>   waves), ADM-001, DQR-001 (three evaluators), SMR-004 (QS-11 → CAL-1; QS-10 trigger-based),
>   RTM §3 summary re-measured (20 CAP domains, 72 REQ rows, 52 BX-LIN, 27 ModelGov — column-exact
>   2026-07-29); three declared Tier-2 items: the `ingestion/models.py` canonical-mapping
>   docstring, the Wave-13-close ES-multiplier mis-attribution (corrected in place), the SR-1
>   wave-named curve pointers → event triggers.
> - Migration head stays `0055`; counts UNCHANGED **25/40/133**; next free canonical id ENT-066;
>   FE 32 files / 204 tests. No code changed on this branch except the one ingestion docstring.
>
> ---
>
> ## Prior current-truth block (2026-07-29), kept as history
>
> **WAVE 13 IS CLOSED + RATIFIED (2026-07-29) — `wave_13_close_review.md`. P1–P6 ALL APPROVED AS
> RECOMMENDED and WRITTEN into `claude_operating_instructions.md` as standing sections; WAVE 14
> RATIFIED = "REAL DATA THROUGH THE GOVERNED RAILS" (roadmap Part 2.17 — direction only, slicing
> at Wave-14 planning). NEXT = Wave-14 planning.** Branch `wave-13-close`; fold batches `396d513`
> → `b131e89`; CI run **30455596382** observed green all six. Migration head stays `0055`; counts
> UNCHANGED **25/40/133**; FE **32 files / 204 tests** (was 190 at the FE-M1 close).
>
> - **THE RUNTIME-CLEAN STREAK ENDED AT EIGHT.** The close audit (121 agents under ultracode,
>   refute-by-default, 3-lens adversarial refutation; 11 findings survived, 26 killed, 3 of 6
>   thin-margin kills overturned by hand) found ONE shipped runtime HIGH: `calc/reads.py` bound
>   every entity-read filter as text, so RM-1/SR-1's `window_months` — the platform's first
>   Integer filter — reached PostgreSQL as `integer = character varying` and **all four new
>   `/perf/rolling-risk{,/latest}` + `/perf/sharpe{,/latest}` endpoints 500'd on the production
>   database while every gate was green.** SQLite's column affinity converts `'12'`→`12`, so the
>   unit tier is STRUCTURALLY blind to the class — the pin lives in the PG tier, where a unit pin
>   could never fail. Fixed by binding at the column's type; 10-family equivalence proven on live
>   PG; mutant kills the pin with the exact ProgrammingError.
> - **The guard layer took its heaviest close yet, all folded with executed mutants (11/11
>   killed):** the closure-stamp gate was blind to the WHOLE wave (7th recurrence — six unstamped
>   records found, five stale for many waves incl. PM-1; now widened + **NON-VACUITY FLOORS**, the
>   close's new P6 pattern); RM-1's headline alignment fix was deletable suite-green against its
>   own "every new guard is mutation-tested" claim; the FE audit gate failed OPEN on a malformed
>   exception (undefined date comparisons — a CRITICAL advisory could vanish silently); the import
>   fences' THIRD un-enumerated bypass axis (dynamic `import()`) + `.mts`/`.cts`; SR-1's
>   `_persist_snapshot` purpose gate had no negative control; RM-1 accepted a NaN pinned return as
>   a raw InvalidOperation where SR-1 refuses a governed 422 (now shared strict parse, pinned both
>   sides); the R-4 vacuous-assertion class recurred in the file R-4 rewrote AND in the Python
>   suite (the pacing purpose test).
> - **Four false claims in governed records corrected in place** (the registered `sharpe_v1.md`
>   carried refuted overflow arithmetic; "refused at capture" named an enforcement that does not
>   exist; CTRL-002 told three different stories across three documents; FE-M1's lockfile delta
>   was 22 entries, not "exactly 12", and the declared gate never fired).
> - **Wave-14 PROPOSED = real-data onboarding** (reference dimensions, concentration, liquidity
>   tiers, the ENT-006 holiday calendar with its dated 2027-05-31 forcing function, the rf vendor
>   diligence). Ratification at the gate.
>
> ---
>
> ## Prior current-truth block (2026-07-28d), kept as history
>
> ## ⚠️ CURRENT TRUTH (2026-07-28d) — superseded
>
> **HEAD `bd1073b`** = merge of **PR #144** (the FE-M1 R-4 fold), atop **PR #143** = `44ee905` (the
> FE-M1 implementation). **CI green all six jobs on both.** Migration head stays `0055`; counts
> UNCHANGED **25/40/133**.
>
> **WAVE 13 IS FUNCTIONALLY COMPLETE — all five slices shipped and merged. NEXT = the WAVE-13 CLOSE
> REVIEW** (the mandatory Part-4 rule-2 re-baseline).
>
> - **FE-M1 CLOSED 2026-07-28** (PR **#143** = `44ee905` + PR **#144** = `bd1073b`; NO migration;
>   counts UNCHANGED 25/40/133): **React 19.2.8 +
>   react-router 8.3.0**, and with them the `GHSA-qwww-vcr4-c8h2` exception **retired by fix, not by
>   expiry** — `npm audit --omit=dev` 2 High → **0**, ~3 months before the 2026-10-24 cliff;
>   `audit-allowlist.json` is now empty. Three regression fences (eslint ban / manifest pin /
>   single-React pin), each with executed negative **and** positive controls, because `npm audit`'s
>   own `fixAvailable` field recommends the refuted 7.11.0 downgrade. **The pre-ratification pass
>   ran as a full EXECUTED DRY RUN in a throwaway workspace copy and refuted two of the plan's own
>   claims before the gate** — a plain `npm install` leaves a DUPLICATE React that fails 73/150
>   tests while passing `tsc` AND `vite build` (so `npm dedupe` is load-bearing), and the natural
>   fix for that moves 61 packages against a declared scope of 12. Two findings no register held:
>   the shipped container built on **EOL `node:20-slim`**, below react-router 8's `>=22.22.0` floor
>   and invisible to CI because CI never builds the image; and **the fail-closed audit gate this
>   slice exists to satisfy had no test at all**, while about to enter its untested empty-allowlist
>   state. FE 28 files/150 tests → **32/190**.
>
>   **And the reason it took TWO PRs is the slice's most transferable finding.** An independent
>   `/code-review ultra` found **R-4**: the one test FE-M1 wrote to cover `BrowserRouter`'s
>   `useParams` deep link booted at `/runs/risk/{uuid}`, but `risk` is a `permissionFamily` VALUE in
>   `FAMILIES`, not a key — so `RunDetail`'s allowlist bailed out **without fetching** and rendered
>   "Unknown run family", a page that satisfies both of the test's by-absence assertions. **A real
>   break in the exact thing the test exists to pin would have left it green.** Fixed by using a real
>   family key and raising the assertions to by-evidence (the fetch asserted called once with
>   `/risk/vars/runs/{uuid}`). **PR #143 had already merged one commit earlier**, so `main` briefly
>   carried the vacuous test while the branch and the record both said it was fixed — caught only by
>   running the SR-1 *verify-the-fix-is-on-`main`* clause as
>   `git merge-base --is-ancestor <sha> origin/main`. **Third appearance of that class, first on the
>   RACE axis** (not a forgotten commit — a fold that arrived after its own PR was opened). See
>   `fe_m1_decision_record.md` Part 8b: the clause belongs to the **closeout**, must run **after the
>   last merge**, and must cover **review folds**, not only ledger sweeps.
>
> - **OPS-H1 CLOSED 2026-07-28** (PR #141 = `03da139`, CI #669; NO migration; counts UNCHANGED
>   25/40/133): the tick's N+1 retired (ONE statement, count-asserted); **the true M-C1 tick×HTTP
>   40P01 interleave FORCED deterministically** with both recoveries proven on the real error; the
>   demo clock seed-relative + backdated (walk preserved) — **the OQ-W12C-3d demo-tick prohibition
>   is RETIRED and replaced by a documented consequence** (enrolling runs the lifecycle by design;
>   re-seed restores the walk); every RLS-arming boundary canonicalizes; the first demo role census
>   (pinned to MEASURED values); the alerts screen pages visibly; client.ts guards the success
>   parse. 2-finder review 0 HIGH.
>
> **Wave 13 is COMPLETE — all five slices merged** (SCH-2 → RM-1 → SR-1 → OPS-H1 → FE-M1). *(This
> line read "THREE slices in" until the FE-M1 closeout; it had gone stale two slices earlier.)*
> Re-verify HEAD/CI at session start as always.
>
> - **SCH-2 CLOSED 2026-07-27** (PR #133 = `8c8c17b`; migration `0053`): month-end cadence
>   (last weekday, END-of-day tick), `EXPOSURE_AGGREGATE` schedulable, the family dispatch registry,
>   the `schedule.view` read surface. Its record's "counts unchanged" was WRONG — stage 15 adds one
>   COMPLETED run (corrected at RM-1).
> - **RM-1 CLOSED 2026-07-27** (PR #135 = `b6e7ba0`, CI #652; migration `0054`): **the 21st governed
>   number** — ENT-064 `rolling_risk_result`, rolling return/volatility/max-drawdown on a
>   calendar-month relink of the PM-1 series. The 4-finder review was the largest to date
>   (8 HIGH / 10 MED / 6 LOW, all folded). **Counts 24/39/132**, pinned AFTER the last demo stage.
> - **SR-1 CLOSED 2026-07-28** (impl **PR #139** = `b86aa28`, CI #663; planning PR #138; migration
>   `0055`): **the 22nd governed number** — ENT-065 `sharpe_ratio_result`, Sharpe (1994)'s
>   differential-return form with a DISCLOSED n−1 divisor divergence, single-quantization, a
>   magnitude gate + PG suite FROM BIRTH, and a CAPTURED risk-free leg joined by MONTH KEY.
>   **Counts 25/40/133 MEASURED; 20/20 mutants killed.** The 4-finder review's two worst HIGHs were
>   PRODUCT defects in the snapshot builder's rf window (both edges), invisible to the demo because
>   its fixture was derived FROM the book under test — both fixed, both mutation-proved.
>
> **A DOC-DEBT CORRECTION, found while running the SR-1 ledger sweep.** The "systematic omission
> sweep" commit (`c9d0374`, three further ledger-class gaps across three slices) was authored but
> **never merged** — PR #137 carried only the two incidentally-found fixes (`5e46c5a`). So this
> CURRENT TRUTH block sat at 2026-07-26/PR #128 for four merged PRs, the ENT registry was missing
> rows for ENT-061…064, and the CTRL-003 SCH-2 trace was absent from `main`. All of it is carried
> forward on `sr-1-impl`. **The lesson is about the sweep, not the docs: an omission sweep that ends
> in an unmerged commit has the same effect as never running it, and the checklist that found the
> gaps could not tell that its own fix had not landed.** Verify the FIX is on `main`, not merely
> that it was written.
>
> **NEXT = the WAVE-13 CLOSE REVIEW.** Standing proposals for that close: ratify the six-ledger
> omission sweep as a closeout step in `claude_operating_instructions.md` (with its new final
> clause, *verify the fix is on `main`*) — **AMENDED at the FE-M1 closeout: the clause is a
> CLOSEOUT step, not a ledger-sweep step; it runs against `main` AFTER THE LAST MERGE and covers
> every artifact the slice claims to have delivered, review folds included** (FE-M1 ran the sweep
> on its branch and passed, then merged a PR that did not contain its own R-4 fold; the cheap form
> is `git merge-base --is-ancestor <sha> origin/main`); ratify the shared-tree mutation rules; and
> ratify *"a register entry is a claim about the code — verify it at planning recon"*, which FE-M1
> is the third slice to demonstrate. FE-M1 additionally proposes a fourth: **for a migration or
> dependency-floor slice, run the pre-ratification pass as an EXECUTED DRY RUN in a throwaway tree**
> — reading, `grep` and the upstream upgrade guide all missed both of FE-M1's blocking findings,
> and ten minutes of actually running it found them. And a fifth, from R-4: **a test whose failure
> mode is a DIFFERENT render path is vacuous — assert by evidence (the call that proves the path ran)
> rather than by absence.** Wave-14 tee = real-data onboarding.
>
> **FE-toolchain debt recorded at FE-M1, deliberately NOT taken (OQ-FE-M1-6=A):** 11 further
> `npm outdated` drifts including two majors — **TypeScript 5.9 → 7.0** and **eslint 9 → 10** — plus
> `jsdom 29 → 30` and five patch/minor bumps. Bundling a TypeScript major with a React major would
> make a resulting type error unattributable to either. Also deferred, with its cost MEASURED: the
> frontend `tsconfig.json` `include` omits the SIX root-level guard tests (miscounted "four" until the Wave-13 close, while listing six) (write-fence,
> router-fence, api-prefixes, openapi-contract, audit-gate, dependency-fence), so they are linted
> and run but never typechecked — probed at **12 errors, all `@types/node` resolution, no
> substantive defects**, so closing it needs a new dev dependency rather than a fix.
>
> ---
>
> ## Prior current-truth block (2026-07-26), kept as history
>
> ## ⚠️ CURRENT TRUTH (2026-07-26) — superseded
>
> **Audited baseline `6f8d923`** = merge of **PR #128 — CI-parity hardening + the OPS-1 closeout**,
> **CI green all 6 (run #624)**; the Wave-12 close folds ride the `wave-12-close` branch on top.
> **NO migration** (head stays `0052`); **counts UNCHANGED 23/38/109** (census-pinned).
>
> ## WAVE 12 CLOSED + RATIFIED 2026-07-26 (OQ-W12C-1/2/3 approved) — `wave_12_close_review.md`
>
> **Ten close auditors under ultracode (Fable 5)** — five slice verifiers, four cross-cutting
> (integration/adversarial re-probe, security/doctrine, register, docs/CI), one agenda-claims
> verifier — refute-by-default, every HIGH/MED finding attacked by two adversarial refuters.
> **Zero RUNTIME defects: the 8th consecutive clean close on that axis.** Every end-to-end probe
> held (SoD via every route/verb combination; the seq/epoch laundering sequences; canonicalization
> at every RLS-arming entry; the anti-laundering property composing through phase 4; hard
> invariants byte-verified). **But the guard layer took its first two HIGHs** — both OPS-1 review
> folds whose delivered form failed its own claim: the eslint **write fence was bypassable** by the
> natural src-root (`./api/client`) and depth-4+ import forms, and the **refusal-detail pin's SoD
> assertion sat in a provably dead branch** (the dual-hat never responded, so their review legally
> returned 200 — 4-auditor convergence). **Both folded AT the close with executed negative
> controls**: a `patterns`-based fence + `write-fence.test.ts` (proven: 3/9 fail against the old
> rule), and unconditional exact-string wire pins on BOTH routers. Also folded: the phase-2
> FK-KEY-SHARE tick×HTTP 40P01 edge ("phases 1–2 take NO row locks" was FALSE — `deadlock_503`
> hoisted to `deps.py`, applied on all five limit verbs, OpenAPI 503s regenerated, docstring
> corrected); the closure-teeth `**Status:**` prose-shape blindness (broadened + shape-tested —
> the class's 8th appearance, mechanism axis; outcome axis stayed clean); the skipped
> control-matrix sweeps (CTRL-021/031 backfilled with their HTTP/UI legs); CI-pin comment-strip +
> multi-path hardening. **Register: 5 PAID / 15 OPEN-legitimate / 3 TIPPED-and-slotted.** Gates
> re-verified post-fold: `make check` 2036, full-PG **2463/0** fresh-schema, `fe-check` 148,
> downgrade smoke clean.
>
> **Outward (rule 6b):** Wave 11's named gap — "the controls have no consumption surface" — is
> **CLOSED** (reachable, alarmed with durable proof-of-alert, running on an evidenced cadence,
> visible/operable). Honest residuals: LOG-sink alerting (provisioning-coupled), single-replica
> supervisor, no UI assign verb. **The new distance-to-frontier: credibility of the numbers** —
> analytics breadth, then real data through the governed rails.
>
> ## WAVE 13 RATIFIED (Part 2.16, OQ-W12C-2=A): "ANALYTICS BREADTH ON THE GOVERNED RAILS"
>
> **RM-1 rolling metrics → SR-1 Sharpe → OPS-H1 operations hygiene → FE-M1 React-19/router-8**, on
> VERIFIED slotting facts: rolling return/vol + max drawdown need ZERO new capture (the governed
> PM-1 series suffices; carries the Tier-3 day-count fork, the annualization deferral re-open, a
> demo-history extension, and a REQ mint for drawdown); **Sharpe's risk-free series rides the
> EXISTING ENT-052 benchmark capture** (or ENT-021 curve + a registered conversion) — NOT a new
> capture family; **sector exposure is 0% computable today** (no issuer rows, no aggregation
> engine), so sector/industry/geo + concentration ride the **Wave-14 real-data tee** as its
> payoff. FE-M1 lands well before the **2026-10-24** allowlist expiry.
>
> **Process (OQ-W12C-3, all four ratified):** (a) **recommendation-before-verification** is
> STANDING and generalized to review folds — any cheaply-testable ratification option or shipped
> guard carries its EXECUTED test/negative control IN the record; (b) the **conformance-pin
> pattern** is the standing answer to any hand-mirrored contract (+ CI Python 3.12 vs local 3.13
> accepted-as-recorded); (c) every closeout leaves a **control-matrix trace** (touch it or state
> "no control moved"); (d) interim: **`DEMO_TENANT_ID` never enters `IRP_TENANT_IDS`** until
> OPS-H1 pays regenerate-on-seed (the frozen-clock demo breach would escalate + page).
>
> **NEXT = RM-1 planning** (the 21st governed number).
>
> ## WAVE 12 IS FUNCTIONALLY COMPLETE
>
> **API-2/API-2b ✅ → NOTIF-1 ✅ → CAD-1 ✅ → OPS-1 ✅.** The wave's thesis was "Operations,
> Reachable": Wave 11 built a governed engine that computed nothing new but could not be reached,
> alarmed, run, or seen. Wave 12 made it **reachable** (the limit/breach HTTP surface),
> **alarmed** (durable proof-of-alert), **running** (an in-process supervisor turning the per-tenant
> tick on a real cadence) and **visible** (the breach/limits dashboard). Counts never moved — by
> design; not one slice was a governed number.
>
> **What OPS-1 shipped.** The breach queue; breach detail (the identity/arithmetic echo + the
> remediation timeline + the NOTIF-1 proof-of-alert + the lifecycle actions); limit health; the
> approval queue. It is also the platform's **first frontend write path**: `client.ts`'s read-only
> fence became a read/write SEPARATION — one shared `request()` core (so identity injection has
> exactly ONE implementation) with every mutating call confined to `api/writes.ts`, now enforced by
> an eslint `no-restricted-imports` rule rather than a comment. Refusals are first-class UI: three
> unrelated governed refusals arrive as HTTP 409 and demand OPPOSITE remedies, so the UI
> discriminates on the server's `detail` and explains which control fired.
>
> **Ratified:** OQ-2=A (dedicated write module), OQ-3=A (refusals as explanations; no `/me`),
> OQ-4=A (a demo operations extension), OQ-5=A (**Assign dropped** — no user directory exists), and
> the **Tier-3 IA sign-off** OQ-6=A (Operations is the FIRST nav group; the book chip is scoped to
> the walk, since it is false over a tenant-wide queue).
>
> **OQ-1 was ratified as C and REFUTED IN BUILD** — see the decision record §7a. Pinning
> `react-router-dom` below the advisory range clears one *unreachable* advisory but re-exposes SIX
> that later 7.x fixed, including a HIGH unauthenticated DoS and two open redirects in `<Link>` /
> `useNavigate` (used on 15 sites — i.e. REACHABLE). The tree stayed at `^7.18.1`. **Standing
> lesson: never recommend a dependency DOWNGRADE as a security fix without re-running the audit gate
> ON the downgraded tree.** Consequence: the `GHSA-qwww-vcr4-c8h2` allowlist exception **remains
> live with its 2026-10-24 expiry**, and the React-19 + react-router-8 migration is a carried slice.
>
> **Review load:** the pre-ratification verifier folded **6 BLOCKING** holes and the 4-finder folded
> **4 HIGH + 5 MED** — the heaviest review of any slice so far. The two most instructive: the demo's
> SoD showcase was **structurally unreachable** (splitting `limit.manage`/`limit.approve` across two
> roles contradicted the ratified MG-3 doctrine that they share one role because the gate is
> PERSON-level, so self-approval hit the 403 permission guard and the maker-checker 409 could never
> fire — a control that LOOKS enforced while being untested); and `make fe-check` lacked the
> `prettier --check` that CI runs, so five files would have failed the merge gate with every local
> check green.
>
> ## CI-PARITY HARDENING (follow-on, same day)
>
> A five-reader audit run on the user's direction-check question found **systemic harness drift in
> one direction**: CI's PostgreSQL tier is a hand-enumerated per-file allowlist (~65 steps) while the
> local merge gate is a wildcard full battery — so a new `*_pg.py` suite joins the local gate
> automatically and joins CI only if someone remembers. For four consecutive slices nobody did, and
> **six suites were never run by CI**, including `test_scheduler_pg` / `test_limit_pg` /
> `test_breach_lifecycle_pg` / `test_notification_pg` — **the entire RLS / append-only /
> ops-no-grant enforcement layer of the Wave-11/12 governance surface** — plus the PPF-2/PPF-3 demo
> stages. Nothing was broken (all pass, and the local full-PG battery is a merge precondition), but
> the enforcement rested on human discipline. **Fixed:** the six steps added, AND
> `test_ci_pg_coverage.py` — a unit-tier conformance pin that FAILS if any PG-gated suite is absent
> from `ci.yml`, so the drift class cannot recur. Adding the suites also exposed that two of them
> leaked `role_permission` rows that break the downgrade smoke; a shared snapshot-then-delete-new
> fixture (`pg_role_permission_guard`) now cleans exactly what a suite created. Local mirrors added
> for both audit gates (`make dep-audit`, `make fe-audit`), `fe-setup` switched to `npm ci`, and the
> developer recipe gained the downgrade smoke + bare `pytest`.
>
> **NEXT = the WAVE-12 CLOSE REVIEW** (the mandatory Part-4 rule-2 re-baseline). Agenda: the
> harness-parity audit; a **recommendation-before-verification** process rule; the React-19
> migration slice (2026-10-24); and — on the user's 2026-07-26 direction — an **analytics-breadth
> ratification** (rolling vol/returns + drawdown are computable from the existing governed return
> series TODAY; Sharpe needs one captured risk-free series; sector/industry/geography-of-risk
> exposure + concentration need reference dimensions that arrive WITH real data, so they fold into
> the Wave-13 real-data candidate).
>
> **What CAD-1 shipped — THE ENGINE NOW TICKS.** Wave 11 built the per-tenant operational tick and
> Wave-12 slices 1–2 put an HTTP surface and an alarm leg on it, but **nothing invoked it on a
> cadence** — the shipped worker container still ran the `irp_worker/main.py` heartbeat placeholder.
> CAD-1 adds an in-process **supervisor** (`irp_worker/supervisor.py`) that, every
> `IRP_TICK_INTERVAL_SECONDS`, runs `run_operational_tick_for_tenant` (schedules → breach detection
> → deadline escalation → notification) for each **configured** tenant with **per-tenant fault
> isolation** (one tenant's failure never halts the cycle), and retires the placeholder. **OQ-1=A**
> keeps the one-shot `scheduler --tenant` for an external scheduler (k8s CronJob / cron); **OQ-2=A**
> sources the tenant list from config env **`IRP_TENANT_IDS`** — no DB sweep, no BYPASSRLS, so the
> ratified OQ-SCH-1-1=B "app never reads cross-tenant" doctrine is intact; **OQ-3=A** skips a
> malformed tenant id (logged) so the rest keep ticking, while the one-shot fails closed (exit 2)
> and an **EMPTY list fails closed at startup** (a silently-idle engine is the exact failure this
> slice exists to prevent).
>
> **BOTH STANDING CARRIES ARE NOW PAID (and CLOSED).** (1) **OQ-a** — every tenant id is
> canonicalized `str(uuid.UUID(x))` **before it arms the RLS GUC**, at both entry boundaries plus a
> defensive check at the shared tick (`irp_worker/tenants.py`). This was the **SSO-1 bug's second
> instance**: `tenant_id::text` renders lowercase-hyphenated, so a non-canonical UUID matched
> NOTHING and the tick fired/evaluated/escalated/notified nothing while printing a normal summary —
> a fail-OPEN. (2) **OQ-W11C-2** — `create_schedule` re-resolves `scope_portfolio_id` and
> `model_version_id` under the acting tenant before stamping the NOT-NULL FKs (the P3-5 finding: PG
> FK checks BYPASS RLS), via `assert_portfolio_in_tenant` + the NEW
> `model/guards.py::assert_model_version_in_tenant`; `environment_id` is a free `String(100)` label
> (`calculation_run.environment_id`, NOT a security boundary) and is correctly unguarded.
>
> **Review.** Pre-ratification verifier folded 2 (the **BLOCKING** `test_worker.py` `run_once`
> import that would have failed pytest at COLLECTION once `main.py` was retired; the empty-list
> fail-closed). **4-finder: ZERO HIGH** — folded M1 (the `main()` fail-closed/canonicalization exit
> codes were untested), M2 (a permanently-failing tenant was log-only with no durable evidence → a
> consecutive-failure WARN escalation), L3 (the success log sat inside the isolation `try` and could
> misreport a committed success as a failure), L4 (defensive tick canonicalization), L5 (compose
> `db` healthcheck). FROZEN `audit/service.py` byte-untouched. Battery: `make check` **2021 passed /
> 416 skipped** + **full-PG GREEN** (clean single run, `PYTEST_EXIT=0`, 100% pass) + CI green.
>
> **Env lesson (cost 3 wasted PG runs):** the module-scoped `test_demo_campaign_pg.py` fixture
> COMMITS demo-tenant data, so re-running full-PG against `irp_pg_local` **without a schema reset**
> pollutes `DEMO_TENANT_ID` and the governed-number census tests fail with "Extra items" — NOT a
> code regression. Always reset the schema + `alembic upgrade head` before EACH full-PG run, run it
> ONCE, and capture pytest to a plain log with an explicit `echo PYTEST_EXIT=$?` (piping through
> `grep`/`tail` drops the summary line AND masks the real exit code).
>
> **What NOTIF-1 shipped.** The alarm leg — "prove the CRO was alerted" (SR 11-7 / BCBS 239). A
> decoupled audit-stream consumer as tick **phase 4** (`poll_tenant_notifications`, after the
> phases-1–2 commit + phase 3, under the `persistent_tenant_context` re-arm) turns each unnotified
> `BREACH.DETECT`/`BREACH.ESCALATE` audit event into a durable IA **`breach_notification`** (ENT-063)
> attempt row per (event, recipient) + a **`NOTIFY.DISPATCH`** (EVT-270, R-07-minted) hash-chained
> ledger entry. Recipients = the in-tenant `breach.review` holders (a NEW reverse-lookup
> `holders_of_permission` replicating the effective-dated `user_role` window + `is_active`). The
> cursor is the DERIVED `MAX(source_sequence_no)` (OQ-4=B, no watermark table); idempotency =
> `uq(tenant, source_sequence_no, recipient_id)`. Delivery is OQ-1=A **record-first** — a
> `LoggingNotificationSink` behind a `NotificationSink` Protocol (a real EMAIL/WEBHOOK channel is a
> provisioning-coupled v2; `app_user` has no contact field, BR-10 forbids secrets). **NO new
> permission** (the read `GET /breaches/{id}/notifications` reuses `breach.view`); **FROZEN
> `audit/service.py` byte-untouched** (read via `audit/queries.py::list_events_since_sequence`; the
> NOTIFY emit reuses existing `record_event` kwargs).
>
> **THE LOAD-BEARING CORRECTNESS PROPERTY (4-finder HIGH, 3-finder converged, folded):** a DERIVED
> `MAX` cursor cannot represent a gap — so `poll_tenant_notifications` **STOPS the batch on the
> first non-dedup failure** (`break`, fail-CLOSED head-of-line); processing a later event would
> advance `MAX` past an earlier failed one, orphaning the alarm forever (the silent no-notify this
> slice exists to close). Each alarm event is a per-EVENT atomic transaction (all recipients
> committed together; a sink exception is caught → FAILED, never rowless). Deadlock-safe by
> row-lock (FK KEY SHARE) → advisory ordering, uniform with the HTTP verbs (NOT by lock absence —
> the 4-finder corrected that rationale). 4-finder also folded: the sink moved off the advisory
> lock (v2-network-sink safety); ENT-063 registered; the record-vs-code drift. Battery: `make
> check` + `fe-check` + `gen-api-check` drift-clean + **full-PG 2416/0** + CI 6/6.
>
> **The `create_schedule` P3-5 FK guard + the OQ-a worker `--tenant` canonicalization remain
> carried to the cadence-wiring slice (Wave-12 slice 3, NEXT).**
>
> ---
>
> **Prior: HEAD `b3f818a`** = merge of **PR #121 — API-2b, the Breach Lifecycle API** (Wave-12 slice 1b, the
> OQ-1=B fast-follow completing slice 1), **CI green all 6**. **NO migration** (head stays `0051`);
> **counts UNCHANGED 23/38/109** (an API is transport, not a governed number). **NEXT = Wave-12
> slice 2: breach notification.**
>
> **What API-2b shipped.** The HTTP surface over the MG-2 breach remediation machine:
> `POST /breaches/{id}/assign|respond|review|close` + the batched/filtered/paginated queue reads
> (`GET /breaches`, `/{id}`, `/{id}/actions` timeline). Driven by a **3-finder Fable foundation
> audit**; TWO blocking pre-fixes landed FIRST: **P1** — the tick×HTTP **deadlock** (the frozen
> `record_event` takes a per-tenant audit-chain ADVISORY lock held to commit; the single-txn tick
> held it across phase-3 breach ROW locks while HTTP verbs acquire row→advisory → reachable 40P01).
> FIX: `run_operational_tick_for_tenant` commits phases 1–2, runs phase 3 as **per-breach top-level
> transactions** (uniform row→advisory order). `persistent_tenant_context` is LOAD-BEARING — the RLS
> GUC is transaction-local; a naive mid-tick commit would run phase 3 RLS-unarmed → silent
> zero-escalation (the OQ-a fail-open pattern; the verifier's blocking fold). 40P01→503 at the API.
> **P2** — the **epoch-aware review guard**: `reject→escalate→ACCEPT` could ratify a formally-REJECTED
> response; now a 2L review requires a 1L response from the CURRENT epoch (`seq > _governing_assign`).
> Ratified OQ-1=A (REJECT carries the owner) / OQ-2=A (per-observation lifecycle; queue groups
> siblings) / OQ-3=A (tick restructure) / OQ-4=A (optional `expected_seq`, all four verbs). D6:
> `BreachOut.state` recency-derived, frozen `status` never serialized; D8: `assigned_to`
> canonicalized+resolved to an ACTIVE same-tenant `app_user` (router also requires `breach.respond`);
> the fail-closed non-UUID→401 actor constructor HOISTED to `deps.require_uuid_principal_id`
> (shared with limits). **4-finder review: ZERO HIGH** — the epoch guard, person-level SoD,
> assignee resolution, and the P1 lock topology all held; folds: `BreachAssigneeError`→422 (non-UUID
> `assigned_to` was a PG 500), the vacuous single-breach deadlock test rewritten to a real 2-breach
> cycle, terminal-state deadline nulling, `ORDER BY id` phase determinism, and the twice-carried
> **PG-tier case-variance self-review HTTP replay** finally shipped. Battery: `make check` +
> `fe-check` + `gen-api-check` drift-clean + **full-PG 2393 passed / 0 failed** + CI 6/6.
> **The `create_schedule` P3-5 FK guard + audit OQ-a (worker `--tenant` canonicalization) remain
> carried to the cadence-wiring slice (Wave-12 slice 3).**
>
> ---
>
> **HEAD `80d5ad6`** = merge of **PR #118** (the Fable Wave-12 API-boundary audit doc), atop THREE
> same-day merges: **PR #117** (the Wave-11 close review — **WAVE 11 CLOSED + RATIFIED**, OQ-W11C-1/2/3,
> 7th consecutive zero-shipped-code-defect close; **WAVE 12 RATIFIED = "Operations, Reachable"**),
> **PR #119** (CI: the time-bound reachability-justified npm-audit allowlist for the live react-router
> advisory GHSA-qwww-vcr4-c8h2 — `audit-allowlist.json` + `scripts/check_frontend_audit.mjs`,
> review_by 2026-10-24), and **PR #120 = API-2, Wave-12 slice 1 SHIPPED** (`20da275`, CI green all 6).
> **NO migration** (head stays `0051`); **counts UNCHANGED 23/38/109** (an API is transport, not a
> governed number). **NEXT = API-2b (the breach lifecycle API — reuses API-2's auth foundation).**
>
> **What API-2 shipped.** The FIRST HTTP surface over the Wave-11 governed operational controls — the
> **limit half** (OQ-1=B split; breach lifecycle = API-2b): `POST /limits` (born DRAFT), `PATCH`
> (material change auto-demotes), `POST /limits/{id}/approve` (the person-level maker-checker gate over
> HTTP), `/suspend`|`/resume`, reads `GET /limits[?status=DRAFT⇒approval queue]`, `/limits/{id}`,
> `/limits/health` — all thin pass-throughs to the gated service fns (no second write path; `status` is
> not a DTO field, `extra="forbid"`). **The Fable-audit auth foundation:** D1 actor-id canonicalization
> lives in the ACTOR DATACLASSES (`LimitActor`/`BreachActor.__post_init__` → `str(uuid.UUID(x))`,
> lenient) so stamp==compare in EVERY caller — API-2b's breach SoD inherits it for free; the router
> additionally fail-closes a non-UUID `X-User-Id` → 401. Ratified: OQ-2=A (human-only by doctrine +
> entrypoint; `_require_human` backstop), OQ-3=A (**SoD refusal = 409**, distinct from 403=entitlement
> gap and 422=validation), OQ-4=A (one-human-one-row provisioning doctrine; schema tightening = a hard
> provisioning-slice precondition). New service reads `list_limits`/`get_limit` (+ `DuplicateLimitError`,
> `LimitStateError`, `_threshold` guarded parse). **4-finder: ZERO functional HIGH — the SoD held
> against every HTTP probe**; 1 coverage HIGH folded (prove `limit.approve` ≠ `limit.manage`: a
> manage-only principal → 403 while the maker → 409) + MED folds (state-conflict 409s; smuggled-status
> 422; fixed-point `1E-8`). Fable demands: D1/D3/D4/D7/D10 PAID; D2/D5 doctrine; **OQ-a (worker
> `--tenant` silent-fail-open) + D8 `create_schedule` guard CARRIED to cadence-wiring**; D6/D9 +
> `assigned_to` resolution to API-2b.
>
> ---
>
> **Prior: HEAD `96679e2`** = merge of **PR #115** (MG-3: the `LIMIT.APPROVE` maker-checker gate — Wave-11
> slice 4, the FINAL slice, "operationalize"), **CI green** (all 6 checks). **NO migration** (code-only;
> head stays `0051_breach_action`). **Counts UNCHANGED 23/38/109** — MG-3 mints NO new governed number:
> a limit approval is a control-plane state transition binding no snapshot/run/model. **WAVE 11 IS
> FUNCTIONALLY COMPLETE (SCH-1 → LIM-1 → MG-2 → MG-3); NEXT = the mandatory Wave-11 close review.**
>
> **What shipped.** The genesis-reserved `LIMIT.APPROVE` (EVT-060) REALIZED as a DRAFT→ACTIVE
> maker-checker gate: `create_limit` now yields **DRAFT** (never immediately ACTIVE — not evaluated by
> the tick); `approve_limit` transitions DRAFT→ACTIVE, **human-only** (BR-15), approver ∉ the maker SET
> `{created_by, updated_by}` (the author AND the last editor — SOD-02), the from-state re-read under a
> `SELECT … FOR UPDATE` lock (`populate_existing`) so a stale read can't double-approve. **RATIFIED
> OQ-5=A — the gate covers limit CHANGES, not just creation:** a material governing-field edit
> (threshold/kind/direction) to a live limit auto-demotes it to DRAFT for a NON-editor re-approval (the
> full REQ-LIM-001/BX-SOD "limit changes are maker-checked"); a status/governing combo in one edit is
> refused; `evaluate_limit` is fail-closed (only ACTIVE). R-07 mint `limit.approve` on `risk_manager_2l`
> (person-level gate, same role as the maker `limit.manage` — spec-blessed "second 2L"); **code-only
> seeding** (`0002_entitlement_seed` re-seeds from the live `bootstrap.py` catalog — a re-seed migration
> would collide on the deterministic uuid5 PK; verifier B-1).
>
> **Pre-ratification verifier folded 3 BLOCKING holes** (no-migration; stale-read-under-lock;
> create-side ACTIVE bypass). **4-finder: 1 HIGH (THREE finders converged) + 4 MED, all folded** — HIGH:
> a solo 2L could bypass the change-gate via `suspend → edit-while-SUSPENDED → resume` OR by slipping a
> no-op `status=` alongside a governing edit (the ACTIVE-only demote suppressed) → fixed to demote on a
> real governing change to ANY non-DRAFT limit + refuse status/governing combos. MED: `update_limit`
> TOCTOU → read fresh status under a scalar `FOR UPDATE`; a no-op re-save spuriously demoted →
> value-compare; the SoD excluded only the LAST editor (a cosmetic edit let the author self-approve) →
> the approver ∉ `{created_by, updated_by}` SET; `LIMIT.APPROVE` records `checked_makers` for durable
> audit. MED-3 (SoD `actor_id` canonicalization) NOT folded — a forward-gate carry for the future
> limit-API auth boundary (the SSO-1 lesson).
> **Lesson: a "material change to a live control re-enters the gate" rule must fire on the change
> regardless of the current lifecycle state AND regardless of a co-submitted status toggle — an
> ACTIVE-only / not-in-`changes` guard is bypassable by the suspend→edit→resume and no-op-status
> paths.** Gates: `make check` green; clean full PG suite **1912 passed**; `alembic check` zero-drift;
> the new gate + concurrency (double-approve lock) + cross-tenant approve + tick DRAFT-skip tests green.
>
> **A separate additive doctrine landed alongside (docs-only, no code): AD-019** (PR #116 `466999d`) —
> the analytical-plane / Snowflake strategy: **hybrid, additive, read-only** — Postgres stays the
> governed system-of-record (RLS/append-only/locks/lineage), a future analytical plane (Snowflake
> likely) is CDC/ELT-fed and never the enforcement layer; the governed OLTP core never moves. Build the
> plane only when a trigger fires (external SQL consumer / volume threshold per OD-046 / diligence date).
>
> ---
>
> **Prior: HEAD `aa6503f`** = merge of **PR #113** (MG-2: the breach remediation lifecycle — Wave-11
> slice 3 "operationalize"; migration `0051_breach_action`), **CI green** (all 6 checks). **Counts
> UNCHANGED 23/38/109** — MG-2 mints NO new governed number: a breach action is a control-plane
> governance event binding no snapshot/run/model. LIM-1 could DETECT a breach; MG-2 makes it something
> you MANAGE — the FIRST governance-workflow-with-teeth.
>
> **What shipped.** MG-2 REALIZES the genesis-reserved **ENT-034 `breach_action`** (IA TRUE
> append-only) as the **DEP-WFL** state machine `DETECTED → ASSIGNED → RESPONDED(1L) → REVIEWED(2L) →
> CLOSED` with an orthogonal `ESCALATED`. The OPERATIVE current state is the recency-derived latest
> action `to_state` by a per-breach monotonic `seq` (assigned `max+1` under a parent-breach
> `SELECT … FOR UPDATE` lock — NEVER a mutated flag; `breach.status` is deprecated-in-place). Every
> transition is a fail-closed guarded step: `assign_breach` (2L starts the clock), `respond_breach`
> (1L files a remediation, narrative required), `review_breach` (2L, **requires a prior 1L response**,
> ACCEPT→REVIEWED / REJECT→ASSIGNED-with-a-fresh-deadline), `close_breach` (2L, evidence required).
> Auto-escalation is a **THIRD phase of the SCH-1 per-tenant operational tick**
> (`poll_tenant_breach_deadlines`, a plain `response_due < now` check, NOT `current_tick`),
> escalate-once-per-epoch via `uq_breach_escalation(breach_id, epoch_seq)`.
>
> **The platform's FIRST person-level SoD.** R-07 mint `breach.respond` (1L = `risk_analyst_1l`) /
> `breach.review` (2L = `risk_manager_2l`), NEVER co-granted to a non-admin role (the SOD-03 partition
> = the first line); the runtime backstop refuses a reviewer/closer who is in the SET of ALL prior 1L
> responders (SOD-02, "1L cannot approve own closure"). Activates the genesis-reserved
> `BREACH.ASSIGN`/`.1L_RESPONSE`/`.2L_REVIEW`/`.ESCALATE`/`.CLOSE` audit codes (REALIZE, no taxonomy
> mint); the frozen `audit/service.py` is untouched.
>
> **Pre-ratification verifier folded 3 BLOCKING concurrency holes** (nondeterministic recency → a
> monotonic `seq`; escalate TOCTOU → the epoch key + FOR UPDATE lock; SoD latest-responder bypass →
> the all-responders set). **4-finder review: 1 HIGH + 4 MED, all folded** — HIGH: a breach could
> reach CLOSED with ZERO 1L response, making the person-level SoD vacuous (a single 2L
> assign→review→close) → `review_breach` now REFUSES with no prior 1L response. MED: the escalation
> epoch was keyed on the DERIVED `response_due` (a same-due-time collision would silently suppress a
> real re-escalation) → re-keyed to the governing ASSIGN's monotonic `epoch_seq`; no `ORDER BY` in the
> overdue scan → a lock-ordering deadlock under concurrent ticks → `ORDER BY Breach.id`; the FOR UPDATE
> lock was untested → a two-connection `FOR UPDATE NOWAIT` proof; audit-payload + ESCALATED-review
> coverage gaps closed.
> **Lesson: a state machine on an append-only log needs a DB-monotonic ordering key (not a uuid or a
> caller timestamp), a per-item write lock for linearizable transitions, and an idempotency epoch
> keyed on a monotonic id — and a "requires a prior step" control must be enforced explicitly, since
> an empty set-check passes vacuously.** Gates: `make check` **1915 passed**; local PG (0051 up/down
> smoke, `alembic check` zero-drift, breach+limit families green incl. the lock proof + append-only
> trigger + cross-tenant + uq-escalation + ops-no-grant).
>
> **The platform can now carry a breach to term with teeth: owned, responded, independently reviewed,
> auto-escalated, closed with evidence.** *(MG-2's NEXT was MG-3 — DONE + CLOSED 2026-07-24, PR #115
> `96679e2`: the `LIMIT.APPROVE` DRAFT→ACTIVE maker-checker gate. See the CURRENT TRUTH block at the
> top; NEXT is now the mandatory Wave-11 close review.)*
>
> ---
>
> **Prior: HEAD `218afc9`** = merge of **PR #111** (LIM-1: the FIRST governed write-side workflow — the
> governed LIMIT + BREACH control, Wave-11 slice 2 "operationalize"; migration `0050_limit_breach`),
> **CI green** (all 6 jobs). **Counts UNCHANGED 23/38/109** — LIM-1 mints NO new governed number: a
> breach is a control-plane predicate over an already-governed `calculation_run`, binding no new
> snapshot/run/model. The platform computed 20 governed numbers but had NO limit to measure them
> against; LIM-1 realizes the DETECTION half of limit monitoring.
>
> **What shipped.** It REALIZES the genesis-reserved entities **ENT-031 `limit_definition`** (EV,
> entity-versioned-in-place — a threshold + a `(target_run_type, metric_type, benchmark_id?)`
> metric-selector + an exact `scope_portfolio_id` + a `breach_direction` predicate + a `limit_kind`
> HARD/SOFT; `LIMIT.DEFINE`/`.CHANGE` audited) + **ENT-033 `breach`** (IA TRUE append-only,
> SELF-DESCRIBING — echoes the metric IDENTITY AND the comparison arithmetic at detection, FKs the
> evaluated `calculation_run_id`, `uq(limit_definition_id, calculation_run_id)` idempotency) and
> ACTIVATES the genesis-reserved `LIMIT.*` (EVT-060) + `BREACH.*` (EVT-070) audit decades (first
> emission — the SCH-1/SCHEDULE realization precedent). R-07 mint `limit.manage` (**2L-maker SoD** —
> `risk_manager_2l` + `platform_admin` ONLY; author≠limit-setter, DIVERGES from SCH-1's 1L
> `schedule.manage`) / `limit.view` / `breach.view`.
>
> **All FOUR Fable foundation-audit demands discharged.** (1) breach discovery via
> `calculation_run`/`calc/reads.py` (so MANUAL runs are limit-checked too), breach records FK
> `calculation_run_id`, idempotency = the IA `(limit_id, run_id)` key; (2) breach evaluation is a PHASE
> of the ONE per-tenant operational tick — `run_operational_tick_for_tenant` = `poll_tenant_schedules`
> then `poll_tenant_breaches` under one `run_in_tenant` terminal commit (NO second entrypoint, NO
> `Schedule` row); (3) per-tenant assembly inside the tick (OQ-1=B preserved, app 100% non-BYPASSRLS);
> (4) grid-frozen-for-life ratified standing.
>
> **Ratified OQ-LIM-1-1…4:** OQ-1=A (EV header + self-describing echo; threshold history = the
> `LIMIT.CHANGE` trail, NOT FR-bitemporal) / OQ-2=A (exact `scope_portfolio_id`; firm rollup v2) /
> OQ-3=A (v1 metric set VAR/`var_value` + ACTIVE_RISK/`te_value`, hardcoded `_METRIC_MAP` + fail-closed
> `column_unit == threshold_unit` assert + REQUIRED `benchmark_id` for ACTIVE_RISK) / OQ-4=A (DETECT +
> record + read; the formal `LIMIT.APPROVE` maker-checker gate AND the breach
> ASSIGN/1L/2L/ESCALATE/CLOSE lifecycle DEFERRED to MG-2).
>
> **Pre-ratification verifier folded TWO blocking correctness holes BEFORE ratification:** the breach
> predicate's `LTE/GTE` naming was an inversion trap (a mis-code fires on every healthy book, silent on
> real breaches) → `breach_direction` names the BREACH condition directly (ABOVE ⟺ `observed >
> threshold` strict; BELOW ⟺ `observed < threshold`), a two-line total function tested against its table
> from birth; and active-risk was under-specified without a benchmark (`active_risk_result.benchmark_id`
> NOT-NULL; a portfolio computes TE vs MANY benchmarks) → `benchmark_id` added to the selector + echo.
>
> **4-finder impl review: ZERO HIGH, 6 MED folded.** The two load-bearing safety themes: **the
> silent-green fail-open** — `limit_health` now RECOMPUTES its verdict from the source of truth via
> `_breaches(observed, …)`, NEVER inferred from the presence of a breach row; the breach poll uses a
> constraint-SPECIFIC dedup (`_is_breach_dedup` — only `uq_breach_limit_run` is benign) plus `logging`
> on any non-dedup/eval failure — and **the precision overflow** — `threshold_value`/`observed_value`
> widened `(28,6)→PreciseDecimal(34,12)` (22 integer digits cover `var_value`'s `(28,6)` range with no
> loss, 12 scale holds the `te_value` fraction). Plus the **P3-5 cross-tenant FK guard** restored on the
> NEW `create_limit` write path (`assert_portfolio_in_tenant` + a raw-SQL tenant-filtered `benchmark`
> existence check kept OFF the marketdata import fence + a duplicate-code pre-check) and coverage folds
> (active-risk `te_value`/FRACTION + floor-direction e2e). Two conformance-test catches during impl: a
> local `_json_safe` dup → canonical `irp_shared.audit.payload.json_safe`; a
> `from irp_shared.marketdata.benchmark` import → the raw-SQL benchmark check.
> **Lesson: a health/status surface for a fail-open control must RECOMPUTE its verdict from the source
> of truth, never infer it from the presence of an evidence row — and its echo/store columns must carry
> at least the integer-range of every source they copy.** Gates at close: `make check` green; full suite
> exit-0 on a FRESH PG schema; scheduler+limit PG battery
> (RLS/append-only-trigger/ops-no-grant/uq-double-detect/forged-tenant) green; `alembic check` clean
> (single linear head `0050`, chain `…0048→0049→0050`).
>
> **The platform can now enforce a limit and record a breach, auditably, over the numbers SCH-1 keeps
> fresh.** *(LIM-1's NEXT was MG-2 planning — DONE + CLOSED 2026-07-23, PR #113 `aa6503f`; MG-2 split
> the `LIMIT.APPROVE` gate to MG-3. See the CURRENT TRUTH block at the top.)*
>
> ---
>
> **Prior: HEAD `96965cf`** = merge of **PR #108** (SCH-1: the FIRST scheduler — Wave-11 slice 1,
> "operationalize"; migration `0049_scheduling`), **CI green** (all 6 jobs). **Counts UNCHANGED
> 23/38/109** — SCH-1 mints NO new governed number; it is the platform's first genuinely-new
> architectural primitive beyond request/response reuse: cadenced governed background execution that
> makes the *existing* numbers PRODUCIBLE on a cadence. New entities: an EV `schedule` (ENT-061,
> config header, entity-versioned-in-place) + an IA append-only `scheduled_run` (ENT-062, one row per
> fired grid tick, `uq(schedule_id, scheduled_for)` idempotency backstop); an R-07 permission mint
> (`schedule.manage`/`.view`) + an R-07 audit-taxonomy mint (a new `SCHEDULE` category, EVT-260,
> genuinely EMITTED — a control-plane lifecycle, not a CALC run). A fire re-invokes an existing family
> binder (v1 `run_var`) over a FRESH re-pin.
>
> **THE CRUX (OQ-1=B, ratified).** The census proved there is NO tenant registry and the app role
> CANNOT enumerate tenants, so cross-tenant dispatch is inherently an AD-015 ops-role question. Two
> pre-ratification verifiers REFUTED the draft framing of Option A (in-app ops-role cross-tenant read)
> as a settled AD-015 reuse — it is a genuine 3-part doctrine EXPANSION (a first-ever ops grant on
> non-audit tables + inverting the test-enforced no-grant invariant + a cross-tenant read of
> governed-run provenance). **User ratified OQ-1=B (infra-driven per-tenant dispatch): the deploy
> layer invokes the worker once per tenant, the whole poll+dispatch runs inside ONE tenant's
> NON-BYPASSRLS `run_in_tenant` context — the app stays 100% non-BYPASSRLS, the standing
> `test_ops_role_has_no_grant_on_*` isolation invariant is PRESERVED** (SCH-1 ships its own such test
> for the two scheduling tables).
>
> **The no-backfill / coalesce-to-`current_tick` model.** The verifiers also caught TWO blocking
> cadence defects (a backfill that would manufacture a fraudulent daily series of identical re-pins
> wearing different date stamps; a pause/resume backfill storm) — BOTH folded by ONE fix: each poll
> fires at most the CURRENT grid tick and leaves missed grid points as honest ledger gaps (a fresh
> number is inherently as-of-now; the FRTB daily series accrues PROSPECTIVELY). **INV-SCH-1**
> (ratified): `scheduled_for` = the pure `current_tick(anchor, interval, now)` grid value, NEVER a
> wall clock — load-bearing for both idempotency and the pure-function test firewall.
>
> **4-finder impl review: ZERO HIGH, 4 MED + LOWs folded.** The doctrine finder found ZERO HIGH/MED
> (frozen `audit/service.py` empty diff; app 100% non-BYPASSRLS; RLS/append-only/grants correct). The
> substantive findings converged on the worker poll-loop error handling: (1) an over-broad
> `except IntegrityError` masked non-dedup constraint failures → could hot-loop a failing tick forever
> with no FAILED evidence — fixed with a constraint-name check (`_is_tick_dedup`); (2) the
> failure-recording path caught only `IntegrityError` → a non-integrity error there could escape the
> loop, abort `run_in_tenant`'s single commit, and unwind every sibling schedule — fixed by making
> `_record_failed` FULLY catch-all (the starvation guarantee); (3) INV-SCH-1 unenforced at the write
> boundary → `_assert_current_tick` self-enforces `tick == current_tick`; (4) the advertised
> resilience behaviors were untested → 4 new tests. A build-time bug was caught by the recon + fixed
> pre-review (dispatch resolved a plain EXPOSURE run when `run_var` needs a FACTOR_EXPOSURE run).
>
> **Post-merge CI fix (PR #108 re-land).** **PR #107 had merged ONLY the planning DRAFT (`a382b93`)** —
> no implementation reached main. The first push also had a CI-collection bug: the dispatch test
> imported the VaR-chain seed as `from tests.test_var`, which resolves locally (cwd on `sys.path`) but
> NOT under CI's repo-root `python -m pytest` (`ModuleNotFoundError: No module named 'tests'`) —
> switched to the repo's `from test_var` sibling-module convention; the full implementation re-landed
> via **PR #108** (CI green). **Lesson: a cross-test-module import MUST use the bare sibling form
> (`from test_x import`), never `from tests.test_x import`.** Gates at close: `make check` green (ruff,
> mypy 222 files, docs, secret); pytest **1453 passed / 388 skipped** (SQLite); scheduler PG battery
> (RLS/append-only-trigger/ops-no-grant/unique-tick) + affected chain green on a clean schema;
> `alembic check` clean (single linear head `0049`).
>
> **The platform's operational half is opening: a governed number can now RUN on a cadence, auditably.**
> *(SCH-1's NEXT was LIM-1 planning — DONE + CLOSED 2026-07-23, PR #111 `218afc9`; see the CURRENT TRUTH
> block at the top.)*
>
> **Prior: HEAD `633e855`** = merge of **PR #104** (PPF-3: the unified public+private parametric VaR —
> Wave 10 slice 3, §2.1 arc CAPSTONE; migration `0048`; the 20th governed number,
> `risk.var.parametric_unified`, `σ_unified = √(x'Σx + p'(Ω_pp/d_t)·p + residual)`; counts
> 22/37/104 → 23/38/109). A REPARTITION, not a naive add — two verifiers refuted the additive formula
> as a variance double-count; 4-finder folded 1 HIGH (the consume-path double-count, three finders
> converged) + 2 MED. **WAVE 10 CLOSED + RATIFIED 2026-07-23** (PR #106; SIXTH consecutive clean close
> on the code axis; the one HIGH doc/process — the closure-stamp class recurred a sixth time, teeth
> broadened + tested). The §2.1 destination shipped v1 (leverage the one load-bearing v2 gap). **WAVE
> 11 RATIFIED (fork A "OPERATIONALIZE"): SCH-1 (done) → LIM-1 → MG-2.**
>
> **Prior: HEAD `7aefd1c`** = merge of **PR #101** (PPF-2: the private covariance block Ω_pp — Wave 10
> slice 3, §2.1 unification arc slice 2 of 3; **NO migration**; the 19th governed number,
> `risk.covariance.private`, counts 21/36/103 → **22/37/104**), **CI green run #519** (all 6 jobs).
> A fail-closed SIBLING of `risk.covariance.sample` over PPF-1's pure-private return series: REUSES
> the generic `estimate_covariance` kernel **byte-for-byte** + the shared `covariance_result` table
> (`frequency=APPRAISAL`, `run_type=COVARIANCE_PRIVATE`). Equal-weight sample covariance of PPF-1's
> pure-private series across ≥2 PRIVATE segments over their common appraisal grid; block-diagonal
> treatment of Ω_pp against the public Σ is disclosed as an **APPROXIMATION, not
> orthogonal-by-construction** (the promoted proxy weights are a SUBSET of the OLS fit — the Part-5
> verifier's forced honesty correction). Isolation was the load-bearing property (a `run_type` filter
> closed a latent shared-table read bug before any private row could exist). 4-finder review: ZERO
> HIGH, 2 MED + 4 LOW folded. Demo stage 12 ran ONE Ω_pp over the two seeded segments, ZERO new book
> data, N=5 common appraisal periods matching the Part-5 verifier's prediction exactly.
>
> **Prior: HEAD `9d64b49`** = merge of **PR #98** (PPF-1: the pure-private factor return — Wave 10
> slice 3, §2.1 arc slice 1 of 3; migration `0047_private_factor_return`; the 18th governed number,
> counts 20/35/101 → 21/36/103), **CI green** (all 6 jobs). The MSCI PE Factor Model "pure private"
> leg: `pp_i,t = desmoothed_i,t − Σ_f w_i,f·R_f,t` (desmoothed minus the proxy-implied return),
> pooled EQUAL-WEIGHT across members sharing the identical appraisal interval (RETAIN_ALPHA). A new
> `PRIVATE` factor family + `APPRAISAL` frequency, fail-closed OUT of every DAILY covariance/VaR gate
> until PPF-2/3 mint the conversion — three isolation guards forced by the pre-ratification verifier
> (the exposure-builder family filter; the capture-admission split; PRIVATE⇒MANUAL). 4-finder review:
> ZERO HIGH, 1 MED (the `update_factor` back door — froze `factor_family`/`frequency` as
> gate-admission identity) + 2 LOW folded.
>
> **Prior: HEAD `2cbb68c`** = merge of **PR #95** (FE-3b: the SPA OIDC/PKCE browser login — Wave 10
> slice 2; NO migration; counts UNCHANGED 17/20/35/101), **CI green**. Turns SSO-1's real OIDC
> resource server into something a non-developer can actually reach: a hand-rolled browser auth-code
> + PKCE flow (Web Crypto, zero new runtime dep) against the Keycloak `irp-frontend` public client.
> **WAVE 10 SLICES 1+2 COMPLETE** (API-1b + FE-3b, both DONE) — see below for the API-1b summary.
>
> **Prior: HEAD `f1e830f`** = merge of **PR #92** (API-1b: the flagship VaR/active-risk entity reads —
> Wave 10 slice 1; migration `0046_run_scope_portfolio`; counts UNCHANGED 17/20/35/101), **CI green
> run #488**. Pays the ONE read API-1 deferred — "latest VaR / active-risk for portfolio P" — at the
> **write** boundary (API-1's verifier had refuted read-only resolution).
>
> **ONE additive nullable `calculation_run.scope_portfolio_id`** column (the `environment_id`/
> `failure_reason` precedent — no RLS/grant/trigger change) threaded through the SINGLE
> `create_run`/`execute_governed_run` choke point and stamped by all FIVE binders: `run_exposure`
> from its direct `portfolio_id` arg (the subtree ROOT); `run_factor_exposure`/`run_var`/
> `run_var_historical`/`run_active_risk` COPYING it forward from their resolved upstream run — proven
> to hold in BOTH the build and snapshot-consume input paths, the write-boundary crux API-1's
> read-boundary could not resolve. The Class-C reads (`list_var_results`/`latest_var_for_portfolio`,
> `list_active_risk_results`/`latest_active_risk_for_portfolio`) resolve via the EXISTING
> `calc/reads.py` helper (zero helper change — a `scope_portfolio_id == P` equality filter);
> `active_risk`'s native `benchmark_id` filter also lands. **OQ-API-1b-1 = A "honest-NULL"**: a
> snapshot-consume-rooted chain (exposure OR factor) stays NULL and is disclosed-unresolvable — the
> fully build-in-request chain (demo/UI/default-API) always stamps a real root; no data back-fill.
> Both ratified Wave-10 CI riders landed here: a **`pip-audit` gate** (audits the INSTALLED
> ENVIRONMENT — review-corrected from `-r requirements-dev.txt`, which missed the `python-multipart`
> runtime dep) and a **closure-discipline docs-check** (filename-keyed, row-anchored; fails on a
> DONE-in-roadmap record still reading "DRAFT for ratification" — teeth for the 5th-consecutive
> missing-stamp class, unit-tested to actually FIRE).
>
> Pre-ratification verifier pass RAN: the copy-forward crux + TR-09 hash-neutrality + migration
> neutrality + read non-shadowing all HELD; 2 COMPLICATED findings folded pre-implementation (a
> second snapshot-consume NULL-origin at the exposure tier, not just factor; the closure-check's
> mechanic, needed to dodge a demonstrated false-positive trap — "API-1b" appears as prose inside two
> other slices' `✅ DONE` rows). **4-finder review: ZERO HIGH.** Write-path: the copy-forward proven
> correct across all 5 binders + both paths, immutable-after-creation, TR-09-neutral, complete (no
> unstamped run creator). Doctrine/security: all 6 hard invariants held; the cross-tenant probe
> confirmed `scope_portfolio_id` is NOT a security boundary (RLS + an explicit tenant filter
> double-bind it — a foreign `portfolio_id` is silent-empty, no existence oracle). Read-correctness:
> filters/run_type/latest-run-selection correct; `/latest` declared before `/{id}`, zero shadowing;
> OpenAPI regen deterministic. CI-riders+honesty: found and fixed a REAL gate hole (the pip-audit
> target above). Folded **5 MED + 1 LOW**: the pip-audit target fix; the closure-check's own
> failure-path teeth were untested (added a test proving the rule FIRES); the closure-check's
> guarantee was over-claimed in its own comment (rescoped to the go-forward cadence); the record's
> "`/latest` 404" wording was a mis-cite (the shipped list-shaped `/latest` correctly returns `[]`,
> matching the covariance/sensitivity/factor-exposure/var-backtest siblings); the copy-forward
> endpoint tests strengthened from non-null to VALUE-equality against the upstream stamp. Disclosed:
> the one `pip-audit` allowlist entry is `PYSEC-2026-1845` (dev-only pytest, fix is a risky major
> bump) — `pyjwt`/`cryptography` (the identity surface) audit CLEAN, NOT ignored; `pydantic-settings`
> bumped 2.14.1→2.14.2 clearing a real advisory the gate surfaced. Battery: `make check` green;
> `make fe-check` green (97+build); `make gen-api-check` clean; full-PG affected-family battery
> green; `0046` downgrade/upgrade smoke + `alembic check` clean.
>
> **The OPERATIVE sequence doc is `10_delivery_backlog/delivery_roadmap.md`** (wave rows + the dated
> amendment log — it WINS wherever the sections below disagree). The latest decision record is
> `ppf_2_decision_record.md` (**CLOSED 2026-07-22**); prior `ppf_1_decision_record.md` (**CLOSED
> 2026-07-22**), `fe_3b_decision_record.md` (**CLOSED 2026-07-21**), `api_1b_decision_record.md`
> (**CLOSED 2026-07-21**). Prior wave: **WAVE 9 FUNCTIONALLY COMPLETE +
> CLOSED + RATIFIED 2026-07-21** (API-1 → FE-2 → SSO-1 → FE-3, all four slices DONE;
> `wave_9_close_review.md` RATIFIED, the FIFTH consecutive zero-shipped-defect close). Standing
> carries: the BT-3 D-F4 reword (a dedicated ES/var-backtest touch); the FE-2 `@redocly` dev-tree
> advisory (dev-only, no action); the FE-3 `auditor_3l` demo-viewer (demo-scoped). *(Everything from
> the "WAVE 7 IS UNDERWAY" line down is prior HISTORY, superseded by this block — the counts/
> next-pointers below are as-of their own date.)*
>
> **WAVE 7 IS UNDERWAY (roadmap Part 2.10, fork A "deepen the mathematics"): HG-1 → ES-HS-1 → RS-1 →
> DS-2**, riders: SC-2 the named pull-forward, commitment/capital-call the presumptive Wave-8
> headline. **HG-1 (slice 1) DONE** (impl PR #55 = `8260ea6`). **ES-HS-1 (slice 2, the headline)
> DONE** — planning PR #57 = `7568c49`, impl PR #58 = `dc2a494`, CI green: the **15th governed
> number** and the platform's FIRST empirical tail measure — the Acerbi-Tasche Prop-4.1 α-tail-mean
> (floor count + fractional boundary weight, NEVER the TCE) over the shipped HS scenario
> distribution; `metric_type='ES_HISTORICAL'`, the `risk.var.historical_es` v1 family through the
> HS binder's registry-map dispatch; the ONE migration `0041` widening the 0028 CHECK (destructive
> RLS-safe downgrade proven under a non-superuser owner-member role); the Acerbi-Szekely backtest
> TEED as BT-3 (Christoffersen finally homed; pairing via shared `input_snapshot_id`; AS 2014
> verified-via-reproduction — the primary is gated); demo stage 4 = the 18th code (TIER_1, an
> INITIAL AWC dossier, the flagship ES bound to the flagship HS VaR's snapshot). 4-finder review,
> zero HIGH, zero shipped math defects. **RS-1 (slice 3) DONE** — impl PR #61 = `9c15658` (planning
> PR #60): the PA-4 **OD-E/OD-G residual-estimator v2s REALIZED** as two declared conventions on
> `risk.proxy_weight.regression` — `EWMA_RISKMETRICS` (Axioma/RiskMetrics decay-weighted specific
> variance, declared λ; the s2 decoupling keeps OLS std-errors classical; raw v1 grandfathered) and
> `SHRINKAGE_CROSS_SECTIONAL_EB` (Barra USE4 empirical-Bayes cross-sectional shrinkage, data-driven
> per-instrument w_i, method-as-identity, N≥3-distinct-instrument fail-closed) — NO new governed
> number/code/migration; Ledoit-Wolf verified-and-explicitly-NOT-used (it leaves variances
> unshrunk). Demo **stage 5** = the SECOND lifecycle turn: the sleeve grown to 3 equities, MF-EQ-B
> EWMA-re-estimated + MF-EQ-A EB-shrunk (bond excluded, asserted-raw), fresh gated flagship
> total-VaR/ES-total evidence, **2 TRIGGERED re-validations closing the raw-sample-σ_e rider** (the
> `hostage to the PA-3 estimate quality` finding flipped to historical, both directions test-pinned)
> + 2 INITIAL AWC dossiers for the new versions. **DS-2 (slice 4, the LAST) DONE** — planning
> PR #63 = `0f199aa`, impl **PR #64 = `5120baa`** (CI green; migration **`0042`**): the
> declared-α rider REMEDIATED via two declared estimator conventions on
> `perf.return.desmoothed_geltner` — **`AR1_ESTIMATED`** (α̂ = 1−ρ̂₁ in-run; the CONSERVATIVE
> Bartlett band persisted as `alpha_stderr`; the Kendall/Marriott-Pope small-n UPWARD bias of α̂
> a registered limitation) + **`OKUNEV_WHITE_ITERATIVE`** (deterministic lag-i passes, the
> derivation-settled '−' root, the length-vs-order floor; alpha NULL on OW rows) — GLM MA(k)
> stays the named v2 (extraction-verified to equation numbers; the MLE-optimizer determinism
> obstacle recorded). Demo **stage 6** = `PE-HARBORVIEW-IX` (16 marks at known α_true = 0.4),
> the three-way declared/estimated/OW comparison, 2 INITIAL AWCs claiming
> **estimation-with-honest-uncertainty, NOT recovery**; **NO TRIGGERED re-validation, recorded
> honestly** (census-proved: no closable condition names the rider — deliberate contrast with
> the MF-1/RS-1 flywheel). 4-finder review ZERO HIGH/MEDIUM; + the missing-CI-step catch at the
> pre-push battery (the 0042 PG suite had no ci.yml step — the P3-7 class, fixed + recorded).
> **WAVE 7 IS CLOSED AND RATIFIED** (2026-07-19: `wave_7_close_review.md` OQ-W7C-1…6 "Approve
> all", merged as DRAFT via **PR #66** = `cc251b2`, ratified immediately after — the second
> full-ultracode close: 71 agents, all four slices SHIPPED-AS-RATIFIED, **ZERO shipped-code
> defects, the THIRD consecutive clean close**; 14 hygiene fixes applied at the close; the one
> code-behavior finding — the stage-4 flagship-pair uuid4 tie-break — ASSIGNED to BT-3).
> **WAVE 8 IS RATIFIED (roadmap Part 2.11, OQ-W7C-6 fork A "fund the third leg"): BT-3 (the
> Acerbi-Szekely ES backtest) → CC-1 (captured commitments/calls/distributions, ENT-015/016) →
> CC-2 (the Takahashi-Alexander pacing projection — the HEADLINE, the 16th-governed-number
> candidate — SEVENTEENTH after the BT-3 mint adjudication)**, riders: BT-3's Z1/threshold
> re-verification MUST; CC-2's Tier-3 forks named at planning + the TA-fetch fallback; SC-2 the
> named pull-forward (its Wave-7 condition expired unspent); the stage-7 demo obligation; the
> slot-zero opener option. **BT-3 (slice 1) DONE** — planning PR #68 = `b493c78`, impl
> **PR #69 = `109d11d`** (CI green run #399; migration **`0043`**): **`risk.es_backtest` = the
> SIXTEENTH governed number** — the AS Z1/Z2 evidence rows with the verdict **DOMAIN-GATED to
> (paired confidence 0.9750 ∧ n_pairs 250)** (the criticals are α/T/df-dependent — executed MC;
> off-domain runs persist Z evidence + `ES_PAIR_COUNT` and NO verdict; the per-(α,T) table =
> the named v2 under a governed offline MC derivation); the fetch MUSTs discharged (the '+1'
> null-expectation identity + the three-route threshold bar); **the Christoffersen
> `risk.var_backtest` v2** in-slice (`CHRISTOFFERSEN_MARKOV`, LR_IND/LR_CC from stored legs;
> v1 byte-preserved — the twice-re-teed item DISCHARGED); the OD-C sibling-pair gates on
> shared `input_snapshot_id`; the OQ-W7C-2 tie-break fix folded by name; demo **stage 7** =
> the DOMAIN-GATE HONESTY demo (Z2 = −127.09 verdict-WITHHELD; the LR_CC joint-power lesson
> live at n=3), 4 INITIAL AWCs, NO TRIGGERED census-proved, the 19th registered code.
> 4-finder review ZERO HIGH; 2 named D-F4 next-touch deferrals → the Wave-8 close register.
> **CC-1 (slice 2) DONE** — planning PR #71 + the rule-7 amendment PR #73, impl **PR #74 =
> `1cdc95b`** (CI green run #420; migration **`0044`**): ENT-015/016 REALIZED as captured
> inputs on the stable (portfolio, instrument) identity (chain-immutable currency; the
> negation FULL-reversal correction; the provenance-only version echo); the three-code
> `commitment.*` mint; EVT-240 ACTIVATED; REQ-PRV-001/002 → In-Progress (the computed +
> liquidity clauses OPEN → CC-2); demo stage 8 = the capture half of the commitment walk
> (counts pinned UNCHANGED — capture-only honesty); 4-finder ZERO HIGH, all 8 MED folded.
> **NEXT = CC-2 planning** (the SEVENTEENTH-number HEADLINE: Takahashi-Alexander pacing —
> fetch TA to paragraph FIRST, the ratified MUST; ENT-059 + family/permission Tier-3 forks;
> the projection half lands on the stage-8 seeded commitment). **WAVE 6 remains
> CLOSED AND RATIFIED** (2026-07-17: `wave_6_close_review.md` OQ-W6C-1…6 via PR #52 = `9d561bf`).
> The living tenant is **19 registered model codes / 34 validation records (11 EXCEPTION +
> 16 INITIAL + 7 TRIGGERED) / 95 COMPLETED runs — UNCHANGED by CC-1 (capture-only)** + the
> stage-8 captured lifecycle (1 commitment / 5 call rows incl. the reversal / 2
> distributions). `phase_status.md`/`next_actions.md` are pointer stubs (OQ-W6C-4).
>
> **Wave-6 history: Wave 6 was functionally complete 2026-07-16** (MG-1 → FL-1 → MF-1 all CLOSED). MF-1
> demonstrated **the full governance lifecycle**: the living demo tenant went multi-family — an
> additive extension (`scripts/run_demo_multifamily.py`; refuse-not-skip; the base campaign
> byte-untouched) seeded the multi-asset sleeve (2 equities + 1 credit, 3 FRTB-family factors),
> ran marks → α=1 desmooth (`v1-alpha1`) → the k=3 Sharpe-1992 OLS → promoted structural
> loadings → the loadings-family exposure → covariance → one VaR/HS/total/ES/ES-total run each
> **bound to the demo-mg1 flagship versions**, and filed **5 TRIGGERED AWC re-validations closing
> the CURRENCY-only condition** (freshly-drafted conditions, zero 'FL-1' — the conditions-grep
> finds the token in exactly the 5 HISTORICAL rows, test-pinned both directions at the version
> grain) + the loadings INITIAL (TIER_2) + the α=1 EXCEPTION. Demo tenant now: **17 codes / 17
> tiered / 7 validated + 11 excepted / 63 COMPLETED runs**. The mixed-family fence held (the
> legacy proxy family stays runnable). Two standing capabilities RETIRED, disclosed: the campaign
> suite's tolerate-living-tenant mode + the dirty-schema double-run (fresh-schema-only from MF-1
> on; the extension CI step is ordering-pinned after the campaign step).
>
> *(The close review this paragraph used to tee is DONE and RATIFIED — see the banner above; the
> OD-E re-tee was discharged by sequencing RS-1/DS-2 into Wave 7, and the four MF-1-unlocked
> candidates stay sequence-able with SC-2 the named pull-forward.)* The pre-ratification verifier
> pass is standing process.
>
> **Counts (2026-07-20, post-CC-1 — UNCHANGED by design, the capture-only honesty):** **16
> governed numbers** (`risk.es_backtest` = the SIXTEENTH; CC-2's candidate is the
> SEVENTEENTH; CC-1 deliberately mints NONE) / **19 registered model codes** in the demo
> tenant / 19 tiered, 16 validated (the Wave-6 seven + the ES-HS INITIAL + RS-1's two +
> DS-2's two + BT-3's four new INITIALs), 11 excepted, 34 validation records total
> (11 EXCEPTION + 16 INITIAL + 7 TRIGGERED, DB-verified) / **95 COMPLETED runs** — plus the
> NEW captured private-capital substrate (3 tables; the stage-8 lifecycle live). Delivery runs under the
> 2026-07-14 EXTENDED autonomy grant (the USER signs Tier-3 decisions; the USER creates AND merges
> PRs — the auto-mode classifier blocks Claude's REST create + merge on this repo).
>
> **Purpose.** Entry-point snapshot so a fresh Claude Code session can recover context without chat
> history. Read this block, then `10_delivery_backlog/delivery_roadmap.md` (the operative sequence),
> then `claude_operating_instructions.md`. Re-verify HEAD/CI before acting. *(`project_state.yaml` is
> RETIRED — see its stub; the recovery set is `CLAUDE.md` → this file → the roadmap.)*
>
> **⚠️ EVERYTHING BELOW THIS BANNER was last deep-refreshed at the PA-0 era (HEAD `ad3d3fe`,
> 2026-07-11) and UNDERSTATES the current state** — it stops before PA-1/PA-2/PA-3/PA-4, the Wave-4
> close, RD-3 and VW-1. Retained as history (the per-slice detail is accurate for the slices it
> covers). Where it disagrees with the roadmap or this banner, **they win**.

## Repository
- **Project:** full-scope enterprise investment-risk platform (monorepo). NOT an MVP/POC — see `build_plan.md`.
- **Layout:** `apps/backend` (FastAPI), `apps/worker`, `apps/frontend`, `packages/shared-python` (`irp_shared`, web-framework-free), `packages/shared-ts`. Postgres + RLS, SQLAlchemy 2.0, Alembic. Numbered governance dirs `01_…`–`11_…`; delivery docs in `10_delivery_backlog/`.
- **Remote:** `github.com/ghostai8088/investment-risk-platform` (branch `main`). **origin is now HTTPS** (`https://github.com/ghostai8088/…`; keychain-cached PAT — flipped from SSH 2026-07-09 at P3-C3 because SSH port 22 is BLOCKED on the current network, timing out; HTTPS push works cleanly. Plain `git push` now uses HTTPS + PAT — no hotspot / URL-push workaround needed).

## Latest known committed state
- **origin/main HEAD:** `ad3d3fe` — merge of **PR #8** (`c9d41a7`, "PA-0: private-asset foundations — proxy_mapping (ENT-019, captured input)", **CI green**); prior `7a422aa` (PR #7, PA-0 planning) ← `df92a9c` (PR #6, BT-1 closeout) ← `868f892` (PR #5, BT-1 impl). Chain since P3-3: `7c50c43` (**P3-3 implementation**, #95) → `362481a` (P3-3 closeout memory) → `8abe764` (**P3-4 planning**, OQs ratified) → `a9b6567` (**P3-4-R0 refactor**, #98) → `c2bd126` (**P3-4 IMPLEMENTATION + 12 review folds**, #99) → `c2480a4` (P3-4 closeout memory, #100) → `c2c1b4d` (**P3-5 parametric-VaR planning**, OQ-P3-5-1..10 ratified + the historical-sim/MC ROADMAP note, #101) → `5ed8271` (**P3-5 IMPLEMENTATION + 13 review folds**, #102) → `d94e572` (P3-5 closeout memory, #103) → `c2e85ac` (**P3-C1 hardening planning**, OQ-P3-C1-1..8 ratified after a plain-language briefing, #104) → `0599f7f` (**P3-C1 IMPLEMENTATION + 12 review folds**, #105) → `ee3c581` (P3-C1 closeout memory, #106) → `416cb1d` (**FE-1 frontend runs-view planning**, OQ-FE-1-1..8 ratified, #107) → `678a651` (**FE-1 IMPLEMENTATION + 16 review folds — the FIRST VISIBLE UI SLICE**, #108) → `945661d` (FE-1 closeout memory, #109) → `63a1bb8` (**the RATIFIED delivery roadmap + the documentation-alignment audit**, #110) → `76c7942` (**TC-1 planning**, OQ-TC-1-1..5 ratified, #111) → `c34b346` (**TC-1 IMPLEMENTATION — Wave-1 slice 1**, #112) → `df04e1d` (TC-1 closeout memory, #113) → `ec1f582` (**VAR-HS-1 planning**, OQ-VAR-HS-1-1..7 ratified, #116) → `29ae31b` (**VAR-HS-1 IMPLEMENTATION — Wave-1 slice 2 — the FIFTH governed risk number**, **CI #117 green**) → `a4d0f89` (**P3-C2 hardening/consolidation planning**, OQ-P3-C2-1..6 ratified, #118) → `6fb1a13` (**P3-C2 IMPLEMENTATION — Wave-1 slice 3 — the four-follow-up paydown; scaffold relocated risk→calc; full 6-finder review, 9 folds; NO migration**, **CI green**) → `13f71df` (P3-C2 closeout memory) → `a4d0f89`…`04c4135` (**P2-7 planning** — benchmark price/level capture / ENT-052, OQ-P2-7-1..8 ratified, CI green) → `2569151` (**TD-1 planning** — test-data realism audit, Wave-1 slice 3.5 insertion, OQ-TD-1-1..6 ratified) → `ac92e0b` (**TD-1 IMPLEMENTATION — fixture-realism remediation; 4 independent finder passes; test-and-docs only; NO migration**, **CI green**) → `4534a38` (**TD-1 follow-up** — 2 more completeness-sweep folds, **CI green**) → `ea2863d` (**P2-7 IMPLEMENTATION — Wave-1 slice 4 — ENT-052 benchmark_level+benchmark_return; migration `0029`; captured returns only; full 6-finder review, ~10 folds; unblocks P3-7**, **CI green**) → `367f602` (P2-7 closeout memory) → `552b954` (**P3-7 planning** — ex-ante active risk / tracking error, OQ-P3-7-1..10 ratified) → `65e6dbe` (**P3-7 IMPLEMENTATION — Wave-1 slice 5 — the SIXTH governed risk number: `active_risk_result` ENT-027, migration `0030`, `COMPONENT_KIND_BENCHMARK`; the FIRST user-directed FULL max-effort multi-agent review ("ultrareview": 10 finders + 6 empirical verifiers + gap sweep), 21 folds incl. run_type=ACTIVE_RISK + 3 missing CI PG steps; 3 deferred findings in the record Part 6**, **CI green**) → `18d35d5` (P3-7 closeout memory, #131) → `1bf172b` (**P3-C3 — binder adjudication-consistency hardening carry-in; the P3-7 item-A deferral: TypeError + base_currency shape gate across var/var_hs/factor + the factor malformed-pin wrapper it lacked; NO migration; B+C re-deferred**, **CI #132 green**) → `6a864c9` (P3-C3 closeout memory, #133) → `4e4648e` (**WAVE-1 CLOSE review + Wave-2 re-baseline**, #134) → `601bbec` (**PM-1 planning** — governed portfolio-return series, OQ-PM-1-1..10 ratified, #135) → `b2445c7` (**PM-1 IMPLEMENTATION — Wave-2 slice 1 — the SEVENTH governed number + FIRST non-risk (the `perf` family): `portfolio_return_result` ENT-053, migration `0031`, `PURPOSE_RETURN_INPUT`+`COMPONENT_KIND_TRANSACTION`, `perf.run`/`perf.view` R-07 mint, CAP-20+REQ-PRF-001; FULL 5-finder ultrareview, 3 HIGH + 1 MED folds each with a regression test**) → `f5e16b6` (**PM-1 ruff-format CI fix**, **CI #137 green**) → `4880b36` (**P3-8 planning — via PR #1, the FIRST PR under branch protection** — OD-P3-8-A..K + OQ-P3-8-1..10 ratified) → `d769f59` (**merge of PR #2 = `86ef3ec`: P3-8 IMPLEMENTATION — Wave-2 slice 2 — the EIGHTH governed number, the SECOND perf-family one, the FIRST governed consumer of `benchmark_return`/ENT-052 (closes P3-7 OD-G): `benchmark_relative_result` ENT-054 (realized ACTIVE_RETURN/TRACKING_DIFFERENCE/TRACKING_ERROR/INFORMATION_RATIO), migration `0032`, `PURPOSE_BENCHMARK_RELATIVE_INPUT` + `COMPONENT_KIND_PORTFOLIO_RETURN`/`_BENCHMARK_RETURN`, run family `BENCHMARK_RELATIVE` REUSING `perf.run`/`perf.view` (NO mint), exact-linkage + contiguity + currency gates; FULL 4-finder local review (user-authorized in lieu of cloud ultrareview), 5 folds incl. the HIGH evidence-echo magnitude gate; the 68-char FK name caught ONLY by local PG (the 63-char identifier cap)**, **CI #142 green**) → `503a9e2` (**merge of PR #3 = `962974f`: P3-8 CLEANUP+CLOSEOUT — the clean-code standing bar (2026-07-10, "as clean as possible" — proof-of-concept build) reactivated 3 dedup folds: `compound_returns` delegates to `link_periods`; the shared tenant guard relocated to `perf/guards.py`; `_register_perf_model` registrar core**, **CI green**) → `1da87c7` (**merge of PR #4 = `3e81ef4`: BT-1 planning — VaR backtesting, OD-BT-1-A..K + OQ-BT-1-1..9 ratified**) → `868f892` (**merge of PR #5 = `e7b615d`: BT-1 IMPLEMENTATION — Wave-2 slice 3 — the NINTH governed number: SR 11-7 outcomes analysis (Kupiec POF + Basel traffic-light zone) over realized flow-adjusted P&L (PM-1) vs ONE VaR method's pinned forecasts, `var_backtest_result` ENT-055, migration `0033`, run family `VAR_BACKTEST` REUSING `risk.run`/`risk.view` (NO mint), the all-or-nothing alignment + MV-chain integrity + cross-portfolio identity gates; FULL 4-finder local review, 14 findings/13 folded incl. a HIGH NaN-VaR-value detonation and a horizon-blind Basel gate; `portfolio/guards.py` relocation (a risk binder needed the shared P3-5 guard the perf home would have fenced off)**, **CI green**). → `df92a9c` (**merge of PR #6 = `05da04a`: BT-1 CLOSEOUT** — Part 6 dispositions: 13 folds + 2 deferred-with-reasons) → `7a422aa` (**merge of PR #7 = `07e5d6a`: PA-0 planning — the capture-first split ratified (OD-PA-0-A..J + OQ-PA-0-1..8); the Okunev-White citation honestly flagged UNVERIFIED for PA-1**) → `ad3d3fe` (**merge of PR #8 = `c9d41a7`: PA-0 IMPLEMENTATION — Wave-2 slice 4 — the FIRST private-asset foundation (differentiation-thesis destination §2.1): ENT-019 `proxy_mapping` REALIZED — FR bitemporal captured private→public factor proxy weights, migration `0034`, multi-factor blend per instrument, NO sum-to-1 (a partial proxy is honest), the CURRENCY-family v1 scope ENFORCED fail-closed (a review fold — was doc-stated but ungated), `MANUAL_PROXY` ORIGIN lineage, `MARKET.PROXY_MAPPING_*` caller-side audit, `marketdata.view`/`.ingest` REUSED (no mint); a private asset is an ORDINARY instrument+valuation under a documented asset_class convention (NO new NAV schema); merged planning-FIRST after a rebase so main's decision-record citations always resolve; proportionate 2-finder review (OQ-8), 4 folds + 2 family-wide deferrals**, **CI green**). Earlier chain: Chain since P2-6: `ae2be8e` (P2-6 closeout memory, #85) → `bb73211` (**P2 closeout / P3 readiness review**; CI re-trigger `6663452` = #86) → `07607a5` (**P3-0 decision record + P3 implementation plan**, #87) → `1a8b2a4` (**P3-1 plan**, #88) → `e8e2e59` (**P3-1 implementation**, batch-pushed) → `5466a09` (**P3-2 plan**, batch-pushed) → `402cb12` (**P3-2 implementation**, #89) → `c452229` (**P3-2 closeout / P3-3 readiness anchor**, #90) → `f941d50` (**P3-3 plan + memory refresh + governance-qualifier cleanup + model-agnostic trailer rule**, #91) → `b3d3923` (**operating-discipline modernization**, #92) → `5c64cf1` (**retrospective model-upgrade audit + status-decay fixes**, #93) → `bd5ba3c` (**gate tiers + OQ-P3-3 ratification**, #94) → `7c50c43` (**P3-3 IMPLEMENTATION + review folds**, #95).
- **Local == origin:** yes (0 ahead / 0 behind); working tree carries only this closeout-docs refresh (branch `pa-0-closeout`, pending gated commit+push).
- **Latest CI:** **GREEN** — `c9d41a7` (PA-0, PR #8) merged as `ad3d3fe`, GitHub Actions success. Locally `make check` **1191** passed + local-PG (incl. the 7 new proxy-mapping RLS legs) + fe-check 52. Chain #98–PA-0 all green.
- **Migration head:** `0034_proxy_mapping` — advanced `0033_var_backtest` → `0034_proxy_mapping` at **PA-0** (`c9d41a7`): the ENT-019 table `proxy_mapping` (FR bitemporal — `weight` NUMERIC(20,12), `mapping_method` MANUAL v1; FKs `private_instrument_id` + `factor_id` + `supersedes_id`; current-head partial-unique `(tenant, private_instrument_id, factor_id)`); **NOT append-only** (FR close-out UPDATEs — no trigger, the factor_return precedent); symmetric FORCE RLS (NEVER hybrid); downgrade smoke (0034↔0033) cycled clean; every DDL identifier ≤ 63, asserted at import (the P3-8/BT-1 lesson made structural). **Next migration lands at the next separately-approved implementation slice.**
- **Networking note (this machine):** **origin was flipped SSH→HTTPS at P3-C3 (2026-07-09)** — SSH port 22 is BLOCKED on the current network (`ls-remote`/push time out; SSH-over-443 also fails, broken pipe). **HTTPS is the working path** (github.com, REST API, and authenticated push all fast; keychain PAT cached) — plain `git push origin main` now works, no hotspot or URL-push workaround. CI verification via the public REST API always works. A full-repo safety bundle exists at `../irp-p3-3-7c50c43.bundle`.

## Working tree (uncommitted)
- **Branch `pa-0-closeout` — the PA-0 closeout PR** (pending gated commit+push): `pa_0_decision_record.md` Part 6 (proportionate 2-finder review — no HIGH bugs; 4 folds incl. the ENFORCED CURRENCY-family scope + the correction-audit `action` convention; 2 family-wide deferrals: the FR supersede window-coherence guard, the marketdata `IntegrityError`→409 mapping) + this docs refresh (roadmap/phase-ledger/current_state/next_actions). Docs-only — NO migration/permission/audit change.

## Current active gate
**WAVE 1 IS CLOSED — `wave_1_close_review.md` RATIFIED (2026-07-09, OQ-W1C-1…6); the RATIFIED Wave-2 sequence
(`delivery_roadmap.md` Part 2.5: PM-1 → P3-8 → BT-1 → PA-0 → P3-6) is now the operative sequence.** The close:
honest audit (5 slices + 2 insertions, all CI-green; ~90 review findings folded; npm audit 0 at all severities);
deferral register reconciled (P3-3/P3-5/P3-C1 deferrals all PAID in-wave; open items trigger-based incl. P3-7
B+C); outward benchmark review; the thesis destination check answered "forward, in dependency order" — Wave 2 is
organized around the **return-series triple unlock** (ex-post TE/IR + VaR backtesting + the desmoothing substrate
share ONE missing primitive, the governed portfolio-return series → PM-1 first). P3-6 moved to Wave-2 slot 5
(pre-authorized). npm CI gate tightened high→moderate at the close; **branch protection (OD-050) ✅ DONE
2026-07-10 — `enforce_admins=everyone` + 5 required CI checks; no direct pushes to `main`, PR flow binds
everyone (P3-8 onward).** **PM-1 (slice 1) DONE — `b2445c7` + `f5e16b6`, CI #137 green; the SEVENTH governed
number, FIRST non-risk (the `perf` family). P3-8 (slice 2) DONE — planning PR #1 `4880b36`, impl PR #2 `86ef3ec`
(merge `d769f59`, CI #142), cleanup+closeout PR #3 `962974f` (merge `503a9e2`); the EIGHTH governed number
(ex-post benchmark-relative AR/TD/TE/IR, ENT-054, migration 0032). BT-1 (slice 3) DONE — planning PR #4
`3e81ef4` (merge `1da87c7`), impl PR #5 `e7b615d` (merge `868f892`, CI green); the NINTH governed number
(VaR backtesting — Kupiec POF + Basel zone, ENT-055, migration 0033); FULL 4-finder local review, 14
findings/13 folded; closeout PR #6. PA-0 (slice 4) DONE — planning PR #7 `07e5d6a` (merge `7a422aa`;
capture-first split ratified; the Okunev-White citation flagged UNVERIFIED for PA-1), impl PR #8 `c9d41a7`
(merge `ad3d3fe`, CI green); the FIRST private-asset foundation: ENT-019 `proxy_mapping` REALIZED (migration
0034); proportionate 2-finder review, 4 folds + 2 family-wide deferrals. Next: THIS closeout PR (branch
`pa-0-closeout`), then **MD-H1** (slice 4.5 — a user-ratified 2026-07-11 Part-4-rule-3 hardening insertion
paying the three bug-shaped register items: FR supersede window-coherence guard, IntegrityError→409 capture
mapping, registrar first-registration race; NO migration), then P3-6 planning (stress/scenario — the LAST
Wave-2 slice; may defer again at the close, an expected outcome) on explicit direction, then the Wave-2 close
review (incl. the PA-1 sequencing decision).**
Prior state: P3-0 … P3-5 + P3-C1 + FE-1 + TC-1 + VAR-HS-1 + P3-C2 + TD-1 + P2-7 + P3-7 + P3-C3 + PM-1 + P3-8 + BT-1 + PA-0 all complete and CI-green.
Earlier slice detail: **P3-C3**
(`1bf172b`, CI run #132 green) — a hardening CARRY-IN (not a numbered slice) paying the P3-7 ultrareview's item-A deferral: binder
adjudication consistency (`TypeError` + a `base_currency` 3-letter shape gate across var/var_hs/factor so every
binder fails-close identically on malformed pins; factor_service also gained the malformed-pin wrapper it
lacked). Test-and-binder only; NO migration/permission/audit. Items B (shared covariance adjudicator) + C
(lineage batching) formally re-deferred (record OD-E). Before it, **P3-7** (`65e6dbe`,
CI run #130 green; plan `552b954`) closed Wave-1 slice **5** — the **SIXTH governed risk number: ex-ante active risk /
tracking error** `TE = √(wₐᵀΣwₐ)` (Grinold-Kahn/Roll, daily unannualized, EX-ANTE only — ex-post deferred on
the portfolio-return prerequisite, OD-G): `active_risk_result` (ENT-027 third realization, migration `0030`,
IA append-only, 3 hard-FK provenance columns incl. `benchmark_id`); `ACTIVE_RISK_INPUT` snapshot pinning
FACTOR_EXPOSURE + COVARIANCE + FACTOR + the newly minted `COMPONENT_KIND_BENCHMARK` (FR-version pins, TR-09);
registered `risk.active_risk.parametric` v1 (code_version-only identity); run family `ACTIVE_RISK`, metric
`TRACKING_ERROR`; fail-closed adjudication (NO imputation). **The FIRST user-directed FULL max-effort
multi-agent review ("ultrareview"): 10 finder angles + 6 empirical verifiers + a gap sweep — 21 findings
folded** (incl. the run_type family/metric split, kernel-overflow→committed-FAILED, adjudication hardening
each test-pinned, and 3 previously-missing CI PG RLS steps), 3 refuted/rejected-as-designed, **3
recorded-deferred in `p3_7_decision_record.md` Part 6** (var_service V2/V5 twins; shared covariance
adjudicator; lineage batching). **Remaining Wave-1: P3-6 (stress/scenario) then the Wave-1 close review**
(planning on explicit direction). Model/effort recommendation standing rule (2026-07-08): append a
next-step model+effort suggestion to every gate briefing (Sonnet/medium for commit-and-closeout mechanics;
Opus 4.8/high for templated implementation with a shipped exemplar like P3-C2; Fable/high for novel
methodology/planning/review-synthesis — extra-high/max reserved for wave-close benchmark reviews or gnarly
debugging). Strict planning-first cadence + the gate tiers hold. **Frontend visibility: the FE-1 read-only view
EXISTS (dev-shim session, permanent DEV banner) and now ALSO surfaces VAR-HS-1 runs with zero frontend changes;
anything further (dashboards, charts, mutations, more domains) remains explicitly gated.**

## P3-7 key deliverables (closed, `65e6dbe`, CI-green run #130) — Wave-1 slice 5; the SIXTH governed RISK number (record `p3_7_decision_record.md`)
**Ex-ante active risk / parametric tracking error** (OD-P3-7-A…H; plan `552b954`): `TE = √(wₐᵀΣwₐ)` — active
weights `wₐ = w_p − w_b`, BOTH sides mapped through the ONE allocation-v1 currency-factor model
(`build_factor_index` — Barra-style symmetry); daily UNANNUALIZED; EX-ANTE only (ex-post TE / active return /
IR deferred on a governed portfolio-return series — OD-G).
- **`active_risk_result`** (ENT-027, third realization; migration `0030`): single-summary-row grain
  `(calculation_run_id, metric_type='TRACKING_ERROR')`; IA TRUE append-only; symmetric FORCE RLS; hard-FK
  provenance `factor_exposure_run_id`/`covariance_run_id`/`benchmark_id` + `benchmark_effective_date` +
  `portfolio_value` evidence. **Run family `ACTIVE_RISK` ≠ metric `TRACKING_ERROR`** (a review amendment to
  OD-F — the family hosts the reserved ex-post metrics).
- **`ACTIVE_RISK_INPUT`** snapshot: FACTOR_EXPOSURE + COVARIANCE IA-row pins + FACTOR EV pins + the newly
  minted **`COMPONENT_KIND_BENCHMARK`** (FR-version constituent pins — supersede/correction invisible, TR-09;
  pin invariance test-proven under upstream re-runs AND a benchmark restatement). Binding predicate
  `v1:fexp-rows+cov-rows+cov-factors+benchmark-set` (+ an import-time varchar(50) guard over ALL predicates).
- **Registered `risk.active_risk.parametric` v1** — code_version-only identity (NO numeric parameter);
  methodology doc `active_risk_parametric_v1.md`; `risk.view`/`risk.run` REUSED; `RISK.ACTIVE_RISK_CREATE`
  reserved-not-minted; consume-path golden **0.007211102551**; fail-closed adjudication (NO imputation:
  NULL/blank currencies, unmappable currency, zero book, Σw_b ≤ 0, coverage gaps, duplicate pins of EVERY
  kind all refuse pre-create; kernel magnitude overflow → committed FAILED, never a 500).
- **Review (Part 6):** the FIRST user-directed FULL max-effort multi-agent "ultrareview" — 10 finder angles →
  22 deduped candidates → 6 verifiers with empirical probes → gap sweep. **21 folds** (correctness hardening
  each test-pinned; 3 previously-missing CI PG RLS steps incl. two PRE-EXISTING gaps; the run_type split; the
  fexp-rows rename), 3 refuted/rejected-as-designed (kept), **3 recorded-deferred**: the `var_service.py`
  TypeError/base_currency twins, the shared covariance-pin adjudicator extraction, `_persist_snapshot`
  lineage batching. Validation post-fold: make check 1044 / full-PG 230 / downgrade smoke / fe-check 43 +
  build / diff fence clean.

## P3-C2 key deliverables (closed, `6fb1a13`, CI-green) — Wave-1 slice 3; hardening/consolidation (record `p3_c2_decision_record.md`)
The four recorded FE-1/P3-C1/P3-5 follow-ups swept in one slice; NO new governed number/entity/permission/audit code; NO migration.
- **OD-B — exposure on the shared scaffold.** `run_exposure` adopts `execute_governed_run`, RELOCATED `risk/scaffold.py`→`calc/scaffold.py` (neutral home; keeps the ratified `test_scope_fence_no_risk_imports_or_identifiers` exposure↛risk fence clean — Part 4.5). FAILED exposure runs now PERSIST `failure_reason` and keep the snapshot→run DEPENDS_ON edge; COMPLETED-path behavior byte-preserved (golden at `test_p3c2_exposure_scaffold.py`, held to the P3-C1 audit-sequence + DQ-identity bar).
- **OD-C — exposure in the FE listing.** New `exposure.view`-gated `GET /exposure/runs` + `list_exposure_runs` (`irp_shared/exposure/queries.py`, fenced to `EXPOSURE_AGGREGATE`). FE runs view SOURCE-SWITCHES per family (not a client-side merge — Part 4.6); heading is now family-neutral "Runs"; `ExposureRunSummaryOut` carries `model_version_id: str|None` (always None) for byte parity with risk.
- **OD-D — captured-input `PreciseDecimal` parity.** Every captured decimal column with precision ≥16 converted (position/valuation/marketdata/reference + `transaction.{quantity,price,gross_amount}` via the review); `coupon_rate(12,6)`/`bump_bps(10,4)`/`confidence_level(6,4)` stay plain. DDL-identical on PG; invariant pinned by `test_p3c2_precision_parity._CONVERTED` (14 cols).
- **OD-E — DQ-rule first-registration race.** `ensure_presence_rule` wraps the INSERT in `begin_nested()` + `except IntegrityError` re-SELECT — 500-on-race → clean resolve, no dangling audit (`test_p3c2_dq_rule_race.py`).
- **Review (Part 6):** full 6-finder, 9 findings ALL folded (model_version_id parity, transaction completeness, exposure golden-bar proofs, exposure PG coverage `test_exposure_runs_pg.py`, doc conformance); 2 finders clean. Validation: make check 968 / full-PG 1177 / alembic no-op / downgrade clean / fe-check 39 + build / diff fence clean (30 files).

## VAR-HS-1 key deliverables (closed, `29ae31b`, CI-green run #117) — Wave-1 slice 2; the FIFTH governed risk number
**Historical-simulation VaR** (OD-VHS-A…G; plan `ec1f582`, #116): plain equal-weight factor-based historical
simulation — `risk.var.historical` v1 registered model family (declared confidence/horizon/window/quantile-
convention; the empirical lower order statistic `k=⌈N(1−c)⌉` over pinned factor-return windows; NO distributional
assumption). Reuses `var_result` (ENT-027) via `metric_type='VAR_HISTORICAL'`; additive migration
`0028_var_historical` makes `z_score`/`sigma`/`covariance_run_id` nullable, GUARDED by a new metric-conditional
`ck_var_result_parametric_not_null` CHECK constraint (the parametric method's NOT-NULL invariant stays
DB-enforced); the downgrade is DESTRUCTIVE (deletes `VAR_HISTORICAL` rows — unrepresentable pre-0028) and RLS-safe
(disables FORCE RLS + the append-only trigger transactionally around the delete — cycled twice in both directions
with real exit codes over suite-created data). New snapshot purpose `VAR_HS_INPUT` (`SNAPSHOT_PURPOSES` member) +
`build_var_hs_snapshot` (FACTOR_EXPOSURE IA-row pins + aligned per-factor FACTOR_RETURN bitemporal window pins).
Two new endpoints (`POST /risk/models/var-historical`, `POST /risk/vars-historical/runs`); reads flow through the
EXISTING parametric VaR GET family + the FE-1 listing with **zero frontend changes**. Methodology doc
`var_historical_v1.md` carries CITED external benchmarks (BoE WP525, Pritsker 2006, arXiv 2505.05646, BIS
d305/d457 — the ratified roadmap's Part 4 rule 6, its first discharge). **Independent 6-finder review: 30 filings
folded into 16 fixes**, incl. TWO ratification amendments recorded in the record's Part 5: **OD-VHS-E tightened**
(the adequacy floor `N≥⌈1/(1−c)⌉` still permitted `k=1`, the sample minimum, at its own boundary — now
`N·(1−c)>1` strictly, 21@0.95/101@0.99, enforced at BOTH the registrar and the declared-parameter re-check — the
generic-registration floor-bypass is closed too); **OD-VHS-C widened** (the third nullable column + the CHECK
constraint + the destructive/RLS-safe downgrade, above). Kernel/binder precision fixes (the magnitude-FAILED gate
was dead code — now reachable and test-proven on both engines); registry-honesty corrections to the parametric
model's own limitation text (it no longer denies the shipped method exists). 26 backend tests (a hand-minted
adjudication vehicle now drives 16 gate probes, incl. a cross-tenant provenance regression that had silently
survived the original suite). `audit/service.py` FROZEN; zero new permissions. Full-PG **1142 passed** at
implementation time.

## FE-1 key deliverables (closed, `678a651`, CI-green run #108) — the FIRST VISIBLE UI slice; NO migration
The read-only **"risk runs & results" view** (OD-FE-1-A…H; plan `416cb1d`, #107): TWO screens — the **runs list**
(the four RISK families; run_type/status filters; has-more offset pagination via a PAGE_SIZE+1 probe; truncated
`failure_reason`; whole-row click-through) and the deep-linkable **run detail** (`/runs/:family/:runId` — provenance
verbatim in monospace, per-family result tables, a FAILED run's persisted reason rendered prominently — the P3-C1
column's designed first consumer; **decimal strings rendered byte-for-byte, never Number()** — tested with
NON-round-tripping constants). **The ONE backend addition:** `GET /risk/runs` (`irp_shared/risk/queries.py` +
router; `risk.view`; explicit tenant predicate + RLS; the four RISK run_types ONLY — `EXPOSURE_AGGREGATE` fenced
out and its request a 422; fail-closed filters; `created_at DESC, run_id` deterministic order; items-only; NO audit
on reads). **Dev-session posture:** header-shim session (`sessionStorage`; printable-ASCII validation at entry AND
on load) under a permanent non-dismissable "DEV SESSION — identity is unverified" banner; honest 401/403 states on
BOTH screens; enforcement stays server-side; SSO unchanged at P6+. **Dependencies:** runtime = react/react-dom/
react-router-dom ONLY; jsdom + @testing-library/react as dev-only test tooling (disposition recorded in the
record). Vite dev proxy — NO backend CORS. **16 review findings folded** (Part 7): 2 stale-response races; runId
URL-injection (encodeURIComponent + attack-shaped test); the has-more pager; non-ASCII session-id refusal; the
fence test re-pinned to LITERALS with the real `EXPOSURE_AGGREGATE` witness; deterministic tie-break ids; **NEW
`test_risk_runs_pg.py`** (irp_app RLS posture) + its ci.yml step; RunDetail honest 401/403; row-click navigation
(the user caught this live); strengthened proofs (path pins, DOM order, pager click-through, all four families).
`apps/frontend/README.md` = the verified demo run-book (uvicorn + vite + a TESTED seeding snippet). 12 + 2 backend
tests, 37 frontend tests. **Recorded follow-ups:** the vite5/vitest2 toolchain major-bump slice (+ production-deps
`npm audit` in CI); exposure runs in the listing (`exposure.view` family).

## P3-C1 key deliverables (closed, `0599f7f`, CI-green run #105) — the hardening/consolidation slice; NO new governed number
The deferral-register paydown (OD-P3-C1-A…H; plan `c2e85ac`, CI #104): **(B) the REGISTERED-status bind** —
`assert_model_version_of` (the risk-family gate all four binders route through) now requires
`version.status == "REGISTERED"` → `UnregisteredModelError`; AND (the review's principal fold) **all FOUR governed
registrars refuse a non-REGISTERED same-label twin** (`WrongModelVersionError` 422) — register/run consistency (the
generic resolver + P7 validation semantics untouched). **(C) persisted `calculation_run.failure_reason`** (additive
Text; migration `0027_run_failure_reason`; `update_run_status(failure_reason=)` persists on the FAILED transition
ONLY; the audit payload UNCHANGED — DQ rows remain the durable evidence; the four GET-run endpoints surface it; all
four binder reason formats preserved VERBATIM). **(D) the run-scaffold extraction** —
`calc/scaffold.py::execute_governed_run` (**relocated from `risk/scaffold.py` at P3-C2** so exposure could adopt it
without crossing the one-way exposure↛risk fence; create_run → RUNNING → DEPENDS_ON → compute → fail-closed gate →
FAILED+reason | rows+ORIGIN+COMPLETED) consumed by all four risk binders AND exposure under the R0
behavior-preservation bar, **proven
by golden captures written green PRE-extraction** (`test_p3c1_scaffold_preservation.py`: audit sequences + lineage
CONTENT + DQ-rule CONTENT + exact reason formats; one finder re-ran the goldens against the stashed pre-extraction
code). **(E) `PreciseDecimal` parity** for the 8 float53-unsafe result columns (`sensitivity_value(28,12)`,
`loading(20,12)`, `exposure_amount(28,6)`×2, `signed_quantity(28,8)`, `mark_value(20,6)`, `fx_rate(28,12)`,
`z_score(20,12)` — the review fold); PG DDL identical, NO migration. **(F) the MRO-walking `deps.map_refusal`**
shared by the risk/exposure/snapshot routers (a subclass of a mapped refusal no longer 500s). **(G) both-modes
ambiguity refusal ×5 binders** covering EVERY build-mode argument incl. the as-of args (exposure's `base_currency`
deliberately excluded — verified honored on the snapshot path); checks sit BEFORE the model gate (request-shape
first). **(H) the P3-3 mixed-base adjudication check** (`_adjudicate_pins` base-currency uniformity — the latent
hole closed at adjudication, grain unchanged). **12 review findings folded; 1 residual recorded** (the DQ-rule
first-registration race — pre-existing, faithfully preserved; a deliberate-behavior-change slice if wanted).
**Recorded follow-ups:** exposure-family scaffold/`failure_reason` adoption; captured-input-table PreciseDecimal
parity. 1111 PG-backed tests; `audit/service.py` FROZEN; zero new permissions/audit codes/entities.

## P3-5 key deliverables (closed, `5ed8271`, CI-green run #102) — ENT-027 REALIZED; the FIRST derived-of-derived number
**`var_result`** (**ENT-027 `risk_result` REALIZED**; migration `0026_var`; **IA TRUE append-only** + P0001 trigger +
symmetric RLS): zero-mean delta-normal 1-day parametric VaR — `σ_p = √(xᵀΣx)`, `VaR = z·σ_p` — over the pinned
result rows of TWO upstream governed runs (`x` = a COMPLETED FACTOR_EXPOSURE run's per-factor totals; `Σ` = a
COMPLETED COVARIANCE run), the platform's first SINGLE-SUMMARY-ROW result (grain `(calculation_run_id,
metric_type)`; `VAR_PARAMETRIC`, ES reserved) with **hard-FK provenance columns** `exposure_run_id`/
`covariance_run_id` (re-resolved own-tenant on BOTH paths pre-create — PG FK checks bypass RLS; the review's
principal fold). **Declared-parameter version identity** (OD-P3-5-D): confidence/horizon/z are strict-parsed
`model_assumption`s (vocab {0.9500, 0.9900}; dual-verified 12dp z constants; horizon must equal `1` verbatim; NO
runtime inverse-CDF). Fail-closed adjudication on BOTH paths: coverage (exposure factors ⊆ covariance factors, NO
zero-variance imputation), single-run provenance, uniform base currency, canonical-order + duplicate refusals,
source-column magnitude envelopes, structurally-malformed-content 422s. The declared radicand quantization floor
(`tol = F²·max(xᵢ²)·1e-19`; clamp within, committed FAILED below — REACHABLE and test-proven) + a magnitude gate
(σ beyond Numeric(28,6) ⇒ FAILED, never a PG overflow 500). σ/VaR carried as `PreciseDecimal(28,6)`. Dual-path
verification: exact hand references (σ=500/700/7) through the kernel AND the governed consume path; `numpy`
cross-check @1e-9; erf round-trip + bisection of the z constants; NON-VACUOUS pin invariance (upstream supersede
moves a fresh build but not the pin). `RISK.VAR_CREATE` reserved-not-emitted; **`risk.*` REUSED — zero new
permissions**; `var_parametric_v1.md` methodology (**specific-risk = 0 the first-class limitation**); 4 endpoints;
the VaR PG CI step; 52 new tests. **13 review findings folded; 2 recorded deferrals** (the
`assert_registered_model_version` status-bind check — cross-slice, a P3-6-planning carry-in; shipped result-column
float parity — a dedicated PreciseDecimal parity slice) — **both PAID DOWN at P3-C1 (`0599f7f`)**. **REQ-MKT-001 → In-Progress (parametric leg);
historical-sim + MC = user-directed ROADMAP method slices.**

## P3-4 key deliverables (closed, `c2bd126`, CI-green run #99) — the THIRD governed RISK number REALIZED
**`covariance_result`** (**ENT-051 `covariance_matrix` MINTED** — the Part-3 process; migration `0025_covariance`;
**IA TRUE append-only** + P0001 trigger + symmetric RLS): the equal-weighted UNBIASED (N−1) sample covariance of
pinned `SIMPLE`/`DAILY` factor-return windows — one row per canonical unordered pair INCL. the diagonal (the
variances; `F·(F+1)/2` rows per run); grain `(calculation_run_id, factor_id_1, factor_id_2)` with binder-enforced
lowercase-GUID canonical ordering (no CHECK). **Window-as-version-identity** (OD-P3-4-G): `window_observations=N`
is a `model_assumption` on the registered `risk.covariance.sample` v1 (strict-digit parse; a malformed/absent
declaration = `WrongModelVersionError` 422; same-label different window/code_version = 409). Snapshot pins:
`COMPONENT_KIND_FACTOR_RETURN` MINTED (per-date **bitemporal** version pins — the review fix; the frozen header
cutoffs reproduce the pin under backdated/future-effective supersedes) + `PURPOSE_COVARIANCE_INPUT` +
`build_covariance_snapshot` (fail-closed common-date alignment — no imputation/pairwise). `run_covariance` mirrors
the hardened P3-3 shape: uniform pre-create adjudication of PINNED content on BOTH paths (<2 series / wrong-N /
misaligned / unpaired / non-SIMPLE/DAILY / duplicate-series all refuse before any run); defensive post-compute DQ
gate (`risk.covariance.completeness`); DEPENDS_ON-before-gate; per-row ORIGIN. **New portable `PreciseDecimal`
type** (`db/types.py`): PG `NUMERIC(38,20)` / SQLite fixed-scale TEXT (a 20dp value does NOT survive SQLite's
float roundtrip; bind-quantize inside a WIDE localcontext; −0 normalized). Kernel: pure Decimal-50, HALF_UP-20,
PSD by Gram construction; **the dual-path verification rule's first discharge** (hand-derived rational references
= kernel = `numpy.cov(ddof=1)` at ε_rel 1e-9; eigenvalue floor λ_min ≥ −1e-12·trace; numpy TEST-ONLY,
runtime-fenced). `RISK.COVARIANCE_CREATE` reserved-not-emitted @ EVT-220; **`risk.view`/`risk.run` REUSED — zero
new permissions**; `covariance_sample_v1.md` methodology; 4 endpoints; the Covariance PG CI step; 57 new tests.
**12 review findings folded** incl. a cross-slice catch: the P3-3 PG hybrid-set probe was VACUOUS (wrong
SYSTEM_TENANT_ID) — both PG suites now probe the real id + assert set EQUALITY. Deferred (recorded): shrinkage/
EWMA/correlation/annualization (v2 versions); max-lookback bound; asset-level covariance; run-scaffold extraction.
**R0 pre-step** (`a9b6567`, CI #98): behavior-preserving extraction of the shared DQ presence-gate helpers
(`dq/gates.py`) + `_persist_snapshot` — the 3×-snapshot-assembly / 4×-DQ-gate duplication debt paid pre-slice.

## P3-3 key deliverables (closed, `7c50c43`, CI-green run #95) — the SECOND governed RISK number REALIZED
**`factor_exposure_result`** (ENT-028 family — **no new canonical id**; migration `0024_factor_exposure`; **IA TRUE
append-only** + P0001 trigger + symmetric RLS; grain `(calculation_run_id, portfolio_id, instrument_id, factor_id)`;
`factor_id` deliberately NOT a hard FK — the `COMPONENT_KIND_FACTOR` pin is authoritative). **Allocation v1:**
indicator loading (= 1, quantized to the Numeric(20,12) quantum) over the pinned atoms of a COMPLETED
`exposure_aggregate` run × pinned CURRENCY-family `factor` definitions, matched on the atom's captured
`mark_currency`; contributions sum to the pinned total **exactly (ε=0)** — **REQ-MKT-003 → In-Progress (partial)**.
`run_factor_exposure` mirrors the P3-1 exemplar + the review hardenings: **uniform pre-create adjudication of PINNED
content on BOTH entry paths** (zero-atom / zero-factor / wrong-family / NULL-scope / duplicate-currency snapshots
refuse before any run exists); **model-identity assert** `assert_model_version_of` (a sensitivity model_version
cannot drive a factor-exposure run — twin-fixed into `run_sensitivities`); **conflict-safe model registration**
(`ModelVersionConflictError` → 409; twin-fixed); gap-naming `failure_reason` on FAILED runs; snapshot
`COMPONENT_KIND_EXPOSURE` (the first IA pin flavor) + `COMPONENT_KIND_FACTOR` + `PURPOSE_FACTOR_EXPOSURE_INPUT` +
a truthful `FACTOR_EXPOSURE_BINDING_PREDICATE`; `RISK.FACTOR_EXPOSURE_CREATE` reserved-not-emitted @ EVT-220;
**`risk.view`/`risk.run` REUSED — zero new permissions**; `factor_exposure_allocation_v1.md` methodology + governed
`register_factor_exposure_model`. **ci.yml restored to the COMPLETE per-table PG suite set** (benchmark, holdings,
synthetic, sensitivity, factor, factor-exposure — six suites absent from CI since the P2-5-era list; #95 ran all
green). 60 new tests incl. 8 review-regression tests; the snapshot→exposure import boundary fenced (function-local
models-only — module-level is a proven circular import). `COMPONENT_KIND_FACTOR_RETURN` was still unminted at
P3-3 close (MINTED at P3-4, its designed first consumer). `audit/service.py` FROZEN. Deferred (recorded): vendor-beta/regression exposures;
ASSET_CLASS+ dimensions; `_ERROR_MAP` exact-type lookup; both-modes silent snapshot preference; latent mixed-base
grain; GET `failure_reason` persistence; the 3×-snapshot-assembly / 4×-DQ-gate / 3×-run-scaffold extractions
(a dedicated cleanup slice — a P3-4 planning carry-in).

## P3-2 key deliverables (closed, `402cb12`, CI-green run #89) — captured factor-return inputs REALIZED
Net-new **`factor` EV definition** (canonical id MINTED; identity `(tenant, factor_code, factor_source)`; `factor_family`
{STYLE, INDUSTRY, COUNTRY, MACRO, MARKET, CURRENCY, OTHER}; optional `factor_type`/`region`/`currency_code`/`asset_class`
scope; `frequency` DAILY v1; `REFERENCE.CREATE`/`UPDATE`-audited) **+ `factor_return` FR bitemporal captured series**
(ENT-025; grain `(tenant, factor_id, return_date, return_type)` current-head partial-unique; `return_value` decimal
fraction `Numeric(20,12)`; `return_type` SIMPLE (LOG reserved); capture/supersede/correct + both-axes
`reconstruct_factor_return_as_of`; `MARKET.FACTOR_RETURN_CREATE`/`_UPDATE`/`_CORRECTION`-audited). Migration
`0023_factor_return` — symmetric tenant RLS (never hybrid), **NEITHER table append-only**. `marketdata/factor.py` binder;
VENDOR_FACTOR ORIGIN lineage; **`marketdata.view`/`.ingest` REUSED** (no `factor.*` permission); binder-side
`Decimal.is_finite()` guard (NaN/±Inf rejected pre-write) + `> -1` economic-sanity DQ RANGE; 8 endpoints; 39 factor tests.
**Captured INPUT — NO `calculation_run`, NO `model_version`, NO snapshot pin** (computed factor returns DEFERRED — would
need adjusted prices + a registered model_version). `COMPONENT_KIND_FACTOR_RETURN` readiness-noted (MINTED at P3-4).
`audit/service.py` FROZEN. Validated green on Python 3.12 + 3.14 + full PG.

## P3-1 key deliverables (closed, `e8e2e59`, CI-covered at run #89) — the FIRST governed RISK number REALIZED
ENT-028 **`sensitivity_result`** (migration `0022_sensitivity`; **IA TRUE append-only** — `APPEND_ONLY_TABLES` + P0001
trigger + ORM guard; symmetric RLS) — **curve-node analytic DV01 / spread-DV01** (`−T·DF·1bp`; ACT/365F; continuous
compounding; nodes-only/no-interpolation; ZERO_RATE/DISCOUNT_FACTOR/SPREAD; PAR_RATE rejected/deferred;
`quantize_HALF_UP(…,12)`; curve-intrinsic — NO instrument/position attribution). **The model-governance hardening:**
`run_sensitivities` calls **`assert_registered_model_version` in the pre-create gate** (fail-closed ⇒ zero run/rows/audit)
— **CTRL-003 inventory-before-use is EXECUTABLE**; the model registered via governed `register_sensitivity_model`
(`risk.sensitivity.analytic` v1; `methodology_ref` → `05_analytics_methodologies/sensitivities_analytic_v1.md`;
assumptions/limitations mirrored; `validation_status` UNVALIDATED, non-enforcing until P7). New `irp_shared/risk/` package
(`models`/`kernel`/`service`/`events`/`bootstrap`) + `api/risk.py`; snapshot `COMPONENT_KIND_CURVE` +
`PURPOSE_SENSITIVITY_INPUT` + `curve_content` + `build_curve_snapshot`; **`risk.view`/`risk.run` MINTED** (auditor_3l in
`.view`); `RISK.SENSITIVITY_CREATE` **reserved-not-emitted** @ EVT-220; `CALC.RUN_*` reused; lineage `snapshot
--DEPENDS_ON--> run --ORIGIN--> result` (DEPENDS_ON recorded BEFORE the DQ gate); fail-closed
`risk.sensitivity.completeness` DQ; the methodology framework + first methodology doc. `audit/service.py` FROZEN.

## P3-0 key decisions (ratified, `07607a5`, CI-green run #87) — the P3 contract
OD-P3-0-A…N + the OQ-P3-0-1…10 sign-offs: **analytic-sensitivities-first** (NOT VaR/ES); the **derived-number output
contract** (every official risk result binds `dataset_snapshot` + `calculation_run` + a **registered `model_version`**
where a model applies + `code_version` + `environment_id`; IA append-only; snapshot-only compute; reproducible under
correction; pre-create-refusal / post-create-FAILED failure model); **`code_version`-only reserved for convention-free
transforms** (the P2-3 rollup — sole precedent); the methodology home `05_analytics_methodologies/` + the §-template;
`RISK.*` reserved @ EVT-220 + `CALC.RUN_*` reuse; `risk.view`/`risk.run` reservation; component kinds minted additively
per consumer; risk results IA append-only; validation-workflow enforcement deferred to P7; the captured-data gap register
(vol surface / adjusted prices / ratings / benchmark levels — later-subphase prerequisites only). Subphase map P3-1…P3-7
in `p3_implementation_plan.md` (sequencing a recommendation, not a strict chain; VaR/ES last; stress RTM-P5).

## P2 captured market-data foundation — COMPLETE (CI-green)
The full reproducibility-first P2 block is delivered and CI-green: **P2-1** `dataset_snapshot` (`3629baa`, the AD-014 reproducibility
primitive) · **P2-2** `fx_rate` (`c257e5c`, captured FX) · **P2-3** `calculation_run`+`exposure_aggregate` (`da178fc`, the first
governed derived number — MARKET_VALUE only) · **P2-4** `price_point` (`2b63b76`, captured prices) · **P2-5** `curve`+`curve_point`
(`49ca3bd`, captured curves) · **P2-6** `benchmark`+`benchmark_constituent` (`b6284a4`, captured benchmarks). The reproducibility
primitive + the captured market-data inputs (FX, prices, curves, benchmarks) + the first governed derived number (exposure) are all
realized. **NO risk analytics yet** — VaR/ES/factor/covariance/stress/scenario/attribution/tracking-error stay **P3+**.


> **Per-slice deliverable detail for CLOSED phases (P0.5–P2-6, P1B, P1C) was thinned out of this file on
> 2026-07-06** — it lives in `phase_status.md` (the ledger), the `10_delivery_backlog/` decision records /
> plans / closeout docs, and this file's own git history. Only the active-phase (P3) sections are kept here.

## Completed phases
- **P0.5** engineering hygiene & foundation (scaffold, audit framework, RLS foundation, CI).
- **P1A-0…P1A-4** the cross-cutting rails — `7cdc2f9`, `96a1564`, `c9be657`, `cc472be`, `c781bb8` (+ PG fix `0282359`). **P1A milestone CLOSED.**
- **P1A closeout / P1B readiness** — `69afedf`.
- **P1B-0 decision record + plan** — `dbed93e`; **ratifications into governance** — `4fae26b`; **project-memory artifacts** — `b1efc05`.
- **P1B-1 implementation plan** — `05ee5f5`.
- **P1B-1 reference-data implementation** — `6568cb1` (CI-green, run #28). **P1B-1 CLOSED.**
- **P1B-2 implementation plan** — `410cc7e` (CI-green, run #29).
- **P1B-2 reference-data implementation** — `32c7778` (CI-green, run #31). **P1B-2 CLOSED.**
- **P1B-3 implementation plan** — `43c042e` (CI-green).
- **P1B-3 reference-data implementation** — `8545ed6` (CI-green, run #34). **P1B-3 CLOSED.**
- **P1B-4 implementation plan** — `f6d691a` (CI-green).
- **P1B-4 reference-data implementation** — `060b2a4` (CI-green, run #37). **P1B-4 CLOSED → P1B block DELIVERED.**
- **P1B closeout / P1C readiness review** — `e99633a` (CI-green, run #39).
- **P1C-0 decision record + P1C implementation plan** — `705d3ba` (CI-green, run #40).
- **P1C-1 portfolio-hierarchy implementation plan** — `b52ad9e` (CI-green, run #41).
- **P1C-0 ratification into governance** — `dca7bc0` (AD-017 + REQ-PPM-001 + PORTFOLIO.* reserved + OD-013/OD-025 closed; CI-green, run #42).
- **P1C-1 portfolio-hierarchy + ABAC scope anchor implementation** — `bb89c74` (CI-green, run #43). **P1C-1 CLOSED** — the first domain entity.
- **P1C-1 closeout project-memory refresh** — `d1d6829` (CI-green, run #44).
- **P1C-2 transaction implementation plan** — `c398215` (CI-green, run #45).
- **P1C-2 transaction capture (IA append-only) implementation** — `abb230f` (CI-green, run #46). **P1C-2 CLOSED** — the first domain IA / append-only entity.
- **P1C-2 closeout project-memory refresh** — `f3fd7c9` (CI-green, run #47).
- **P1C-3 position implementation plan** — `42cc02c` (CI-green, run #48).
- **P1C-3 position capture (FR bitemporal) implementation** — `4ee124e` (CI-green, run #49). **P1C-3 CLOSED** — the first FR domain entity.
- **P1C-3 closeout project-memory refresh** — `2f7d647` (run #50) + cleanup `b38f182` (run #51).
- **CI hygiene** — `67741fb` (run #52): GitHub Actions bumped to Node-24 majors (`checkout@v5`/`setup-python@v6`/`setup-node@v5`); Node-20 deprecation warning eliminated.
- **P1C-4 valuation implementation plan** — `92a0264` (CI-green, run #53).
- **P1C-4 valuation capture (FR bitemporal, captured marks) implementation** — `c5c5806` (CI-green, run #54). **P1C-4 CLOSED** — the second FR domain entity; **REQ-PPM-003 now Done**.
- **P1C-4 closeout project-memory refresh** — `6e3dcc1` (CI-green, run #55).
- **P1C-5 holdings-views implementation plan** — `8a14173` (CI-green, run #56; OD-P1C5-1..6 signed off).
- **P1C-5 read-only as-of holdings / portfolio views implementation** — `0bef45b` (CI-green, run #57). **P1C-5 CLOSED** — the first read-model / composition package (no entity, no migration).
- **P1C-5 closeout project-memory refresh** — `867e576` (CI-green, run #58).
- **P1C-6 deterministic synthetic dataset implementation plan** — `7dfdb79` (CI-green, run #59; audit conclusions folded; OD-P1C6-1..7 signed off).
- **P1C-6 deterministic synthetic dataset implementation** — `3e9882d` (CI-green, run #60). **P1C-6 CLOSED** — the deterministic synthetic dataset (governed seam + never-auto-run). **The FULL P1C block (P1C-1…P1C-6) is DELIVERED.**
- **P1C-6 closeout project-memory refresh** — `9584ba4` (CI-green, run #61).
- **P1C closeout / P2 readiness review** — `7070dff` (CI-green, run #62; 8-lens). Reproducibility-first P2 sequencing chosen.
- **P2-0 decision record + P2 implementation plan** — `2d19992` (CI-green, run #63; 8-lens, 0 block). OD-P2-A…L; subphases P2-1…P2-6.
- **P2-1 dataset_snapshot implementation plan** — `d7be981` (CI-green, run #64; 8-lens, 0 block). The AD-014 reproducibility-primitive build plan.
- **P2 dataset_snapshot governance ratification** — `63be23a` (CI-green, run #65; 7-lens, 7× approve). ENT-049/050 + SNAPSHOT.CREATE (EVT-190 reserved) + snapshot.* (reserved) + AD-004-R1 + REQ-PPM-004→In-Progress.
- **P2 ratification closeout project-memory refresh** — `d45a31b` (CI-green, run #66; docs-only).
- **P2-1 `dataset_snapshot` implementation** — `3629baa` (CI-green, run #67; 8-lens, 6 in-scope folds). **P2-1 CLOSED** — the AD-014 reproducible input-snapshot primitive (ENT-049/050) realized; **migration head `0015_valuation` → `0016_dataset_snapshot`** (the first migration since P1C-4) + the first new Snapshot symmetric-RLS CI step. NO exposure number, NO `calculation_run` wiring.
- **P2-1 closeout project-memory refresh** — `85ff5b2` (CI-green, run #68; docs-only).
- **P2-2 `fx_rate` implementation plan** — `6020b03` (CI-green, run #69; 8-lens, 6 in-scope folds; build-ready). The 10 specific decisions settled (FR; base/quote direction; MID; USD-base triangulation; `marketdata.*`; etc.).
- **P2-2 `fx_rate` implementation** — `c257e5c` (CI-green, run #70; 8-lens, 6 approve / 2 approve_with_changes / 0 block; 1 in-scope fold). **P2-2 CLOSED** — captured FX market data (ENT-024, FR) realized; **migration head `0016_dataset_snapshot` → `0017_fx_rate`** + the new FX symmetric-RLS CI step. NO exposure number, NO `calculation_run` wiring, NO `dataset_snapshot` change.
- **P2-2 closeout project-memory refresh** — `adf4ac5` (CI-green, run #71; docs-only).
- **P2-3 decision record + implementation plan** — `d10c766` (CI-green, run #72; 8-lens, 10 in-scope folds; the five OQ-P2-3 sign-offs). `calculation_run` wiring + basic exposure; OD-P2-3-A…L.
- **P2-3 exposure + `calculation_run` governance ratification** — `851f976` (CI-green, run #73; AD-018; 7-lens, 6 approve / 1 approve_with_changes). ENT-014 ratified-in-planning; the `CALC.RUN_START/COMPLETE/FAIL` → `CALC.RUN_CREATE/STATUS_CHANGE` doc-vs-code reconciliation; EVT-210 `EXPOSURE.*` reserved; `exposure.*` perms; CTRL-009 executable; HALF_UP canonical-serialization exception. RATIFIED-IN-PLANNING, no code.
- **P2-3 `calculation_run` wiring + basic exposure implementation** — `da178fc` (CI-green, run #74; 8-lens, 5 approve / 3 approve_with_changes / 0 block; 2 in-scope folds). **P2-3 CLOSED** — the **first governed derived number** (`exposure_aggregate`, ENT-014, IA append-only) realized; **migration head `0017_fx_rate` → `0018_exposure_aggregate`** (+ the additive `calculation_run.environment_id`) + the new Exposure symmetric-RLS CI step. The AD-014/FW-RUN/TR-15 gate is now load-bearing. NO risk (MARKET_VALUE only).
- **P2-3 closeout project-memory refresh** — `0b12d85` (CI-green, run #75; docs-only).
- **P2-4 captured price history decision record + implementation plan** — `b73e65f` (CI-green, run #76; 8-lens, 4 in-scope folds; the six OQ-P2-4 sign-offs). `price_point` (ENT-020) FR/bitemporal captured prices; OD-P2-4-A…L.
- **P2-4 captured price history implementation** — `2b63b76` (CI-green, run #77; 8-lens, 7 approve / 1 approve_with_changes / 0 block; 1 in-scope fold). **P2-4 CLOSED** — `price_point` (ENT-020, FR/bitemporal captured vendor prices) realized; **migration head `0018_exposure_aggregate` → `0019_price_point`** + the new Price-point symmetric-RLS CI step. **REQ-PUB-001 → In-Progress (partial).** NO pricing model, NO conversion, NO `calculation_run`/`exposure_aggregate`/`dataset_snapshot`/FX change.
- **P2-4 closeout project-memory refresh** — `419db9d` (CI-green, run #78; docs-only).
- **P2-5 captured yield/spread curves decision record + implementation plan** — `326ad94` (CI-green, run #79; 8-lens, 8 in-scope folds; the ten OQ-P2-5 sign-offs). The unified `curve` + `curve_point`; OD-P2-5-A…N.
- **P2-5 captured yield/spread curves implementation** — `49ca3bd` (CI-green, run #80; 8-lens, 7 approve / 1 approve_with_changes / 0 block; 1 material + 3 low folds). **P2-5 CLOSED** — the unified `curve` (FR header, ENT-021) + `curve_point` (IA append-only nodes) realized; ENT-023 `credit_spread` by value; **migration head `0019_price_point` → `0020_curves`** + the new Curve symmetric-RLS CI step. **REQ-PUB-002 + REQ-PUB-003 → In-Progress (partial).** NO curve construction/interpolation/duration/pricing/risk; NO `calculation_run`/`exposure_aggregate`/`dataset_snapshot`/`fx_rate`/`price_point` change.
- **P2-5 closeout memory** — `0c5c068` (run #81); **P2-6 plan** — `8d2782f` (run #82); **operating rules** — `1e0dc08` (run #83).
- **P2-6 captured benchmark/index data implementation** — `b6284a4` (CI-green, run #84). **P2-6 CLOSED** — `benchmark` (ENT-009, EV definition) + `benchmark_constituent` (FR membership); **migration head `0020_curves` → `0021_benchmark`**. **THE FULL P2 FOUNDATION COMPLETE.** Closeout memory — `ae2be8e` (run #85).
- **P2 closeout / P3 readiness review** — `bb73211` (CI re-trigger `6663452`, run #86).
- **P3-0 decision record + P3 implementation plan** — `07607a5` (CI-green, run #87). **OD-P3-0-A…N RATIFIED** (the P3 contract; analytic-sensitivities-first; subphases P3-1…P3-7).
- **P3-1 analytic sensitivities plan** — `1a8b2a4` (CI-green, run #88; OQ-P3-1-1…6 ratified).
- **P3-1 analytic sensitivities implementation** — `e8e2e59` (batch-pushed; CI-covered at run #89). **P3-1 CLOSED** — the first governed RISK number (`sensitivity_result`, migration `0022_sensitivity`); CTRL-003 executable; `risk.view`/`risk.run` minted; the methodology framework + `sensitivities_analytic_v1.md`.
- **P3-2 factor-return inputs plan** — `5466a09` (batch-pushed; CI-covered at run #89).
- **P3-2 factor-return inputs implementation** — `402cb12` (CI-green, run #89). **P3-2 CLOSED** — the `factor` canonical id minted + ENT-025 `factor_return` realized (migration `0023_factor_return`); captured INPUT (no run/model/snapshot binding).
- **P3-2 closeout / P3-3 readiness handoff** — `c452229` (CI-green, run #90; the resume anchor for the machine move).
- **P3-3 plan / discipline / audit / gate-tier chain** — `f941d50` (#91) → `b3d3923` (#92) → `5c64cf1` (#93) → `bd5ba3c` (#94).
- **P3-3 factor-exposure implementation** — `7c50c43` (CI-green, run #95 — the first run executing ALL per-table PG suites). **P3-3 CLOSED.** Closeout memory — `362481a`.
- **P3-4 covariance planning** — `8abe764` (OQ-P3-4-1…10 RATIFIED at the commit gate).
- **P3-4-R0 refactor pre-step** — `a9b6567` (CI-green, run #98; shared `dq/gates.py` presence helpers + `_persist_snapshot`).
- **P3-4 covariance implementation** — `c2bd126` (CI-green, run #99; 12 review folds). **P3-4 CLOSED** — the third governed risk number (ENT-051; migration `0025_covariance`). Closeout memory — `c2480a4` (#100).
- **P3-5 parametric-VaR planning** — `c2c1b4d` (CI-green, run #101; OQ-P3-5-1…10 RATIFIED + the historical-sim/MC roadmap note).
- **P3-5 parametric-VaR implementation** — `5ed8271` (CI-green, run #102; 13 review folds). **P3-5 CLOSED** — ENT-027 realized (migration `0026_var`); REQ-MKT-001 → In-Progress (parametric leg). Closeout memory — `d94e572` (#103).
- **P3-C1 hardening/consolidation planning** — `c2e85ac` (CI-green, run #104; OQ-P3-C1-1…8 RATIFIED at the commit gate after a plain-language decision briefing).
- **P3-C1 hardening/consolidation implementation** — `0599f7f` (CI-green, run #105; 12 review folds + 1 pre-existing residual recorded). **P3-C1 CLOSED** — the deferral-register paydown (migration `0027_run_failure_reason`; the run-scaffold extraction; the REGISTERED-status bind + register/run consistency; PreciseDecimal parity ×8; `deps.map_refusal`; both-modes refusal ×5; the mixed-base check). Closeout memory — `ee3c581` (#106).
- **FE-1 frontend runs-view planning** — `416cb1d` (CI-green, run #107; OQ-FE-1-1…8 RATIFIED at the commit gate; chosen on the walking-skeleton recommendation with the user explicitly deferring to best practices).
- **FE-1 frontend runs-view implementation** — `678a651` (CI-green, run #108; 16 review folds). **FE-1 CLOSED — the FIRST VISIBLE UI** (two read-only screens + `GET /risk/runs`; NO migration; dev-shim session + permanent DEV banner; user exercised it live pre-approval). Closeout memory — `945661d` (#109).
- **The delivery roadmap ratification + documentation-alignment audit** — `63a1bb8` (CI-green, run #110). Rolling-wave Wave 1 fixed; ten stale genesis-era docs aligned to the true state.
- **TC-1 FE toolchain-bump planning** — `76c7942` (CI-green, run #111; OQ-TC-1-1…5 RATIFIED).
- **TC-1 FE toolchain-bump implementation** — `c34b346` (CI-green, run #112 — the upgraded pipeline's own first run; 3-finder review: 1 fold + 1 evidence-based disposition). **TC-1 CLOSED — Wave-1 slice 1** (vite 8/vitest 4/plugin-react 6; audit 0 vulns; Node 24 CI; the audit + format gates; ZERO source changes). Closeout memory — `df04e1d` (#113).
- **VAR-HS-1 historical-simulation VaR planning** — `ec1f582` (CI-green, run #116; OQ-VAR-HS-1-1…7 RATIFIED; the record's Part 2 carries the FIRST discharge of roadmap rule 6's cited external-benchmark obligation).
- **VAR-HS-1 historical-simulation VaR implementation** — `29ae31b` (CI-green, run #117; 30 filings folded into 16 fixes incl. two ratification amendments). **VAR-HS-1 CLOSED — Wave-1 slice 2 — the FIFTH governed risk number** (`risk.var.historical` v1; migration `0028_var_historical`; the metric-conditional CHECK constraint; the RLS-safe destructive downgrade; zero frontend changes).

## Next required action
**THE RATIFIED ROADMAP SEQUENCE** (`10_delivery_backlog/delivery_roadmap.md`, Wave 1 — the sequence replaces the
per-slice option menu; re-sequencing only via its Part 4 rules): **TC-1 ✅ DONE (`c34b346`, #112)** → **VAR-HS-1 ✅
DONE (`29ae31b`, #117)** → **P3-C2** hardening bundle → **P2-7** benchmark price/level capture → **P3-7**
benchmark-relative → **P3-6** stress/scenario → the Wave-1 close review + re-baseline. Each slice still gets its
own decision record + plan + OQ ratification + adversarial review + Tier-2 commit approval, and starts only on
explicit direction. **Next concrete step: P3-C2 (the hardening bundle) planning, on direction — a templated
consolidation slice (the P3-C1 exemplar); recommend Opus 4.8/high per the model/effort standing rule.** Genuine
ambiguity inside a slice → ask the user with a recommendation attached (their standing rule, 2026-07-08).

## What MUST NOT be started yet
- **No next-slice implementation** — not until its planning is committed + ratified AND the user directs it (the planning itself also awaits explicit direction; see "Next required action").
- **No ES / Monte-Carlo implementation** — ROADMAP method slices (user-directed), each its own registered model family/version + planned slice; the ES closed-form seam (`σ·φ(z)/(1−α)`) stays a recorded seam (now with a hist-sim leg noted too); historical simulation is DONE (VAR-HS-1, `29ae31b`).
- **No multi-horizon √h scaling / component-marginal VaR / backtesting / runtime quantile function** — recorded P3-5 + VAR-HS-1 deferrals (backtesting is also a named later slice, a P7 prerequisite).
- **No FHS/volatility-filtered or BRW/time-weighted historical-VaR variants** — recorded v2 model versions of `risk.var.historical` (need a declared volatility model — EWMA/GARCH), never silent extensions.
- **No shrinkage / EWMA / correlation output / annualization / asset-level covariance** — recorded v2 `model_version`s of the covariance family, never silent extensions.
- **No stress testing / scenario analytics** — P3-6 (ENT-029/030; RTM-P5 — possibly a later phase).
- **No benchmark-relative analytics / active risk / tracking error / performance attribution** — P3-7+ (and `benchmark_level`/`benchmark_return` are themselves DEFERRED captured inputs — a net-new canonical ENT id, not minted).
- **No vendor-beta or regression factor exposures** — deferred v2 (need a captured factor-loading slice / adjusted-price return history + estimation); **no computed factor returns** (need adjusted prices + a registered model_version); `COMPONENT_KIND_FACTOR_RETURN` MINTED at P3-4 for the covariance window pin (regression v2 stays deferred).
- **No instrument/position key-rate DV01 / interpolation / bootstrapping / pricing engine / PAR_RATE / vol surface** — the P3-1 deferrals stand.
- **No frontend EXPANSION** unless explicitly approved — FE-1 shipped the read-only runs/results view (`678a651`); dashboards, charts, exports, mutations from the UI, additional domain screens, and any softening of the DEV-banner posture each gate on their own planned slice. No reporting build.
- **No limits/breach, real SSO, ABAC enforcement** — P6+ (ABAC stays anchored-not-enforced).
- **P1B-5** (reference-data ingestion mapping) — conditional/deferred (only if bulk loading is needed; not now).
- **Never** modify `packages/shared-python/src/irp_shared/audit/service.py` (frozen) or `entitlement/bootstrap.py` outside the governed R-07 mint (P3-3 mints NO new permission — `risk.view`/`risk.run` are REUSED); no new audit code / permission / role / migration without R-07. **No weakening of the P2/P3 snapshot-run-model controls; no BYPASSRLS; no hybrid/SYSTEM_TENANT behavior** beyond the closed 5-table set.

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
