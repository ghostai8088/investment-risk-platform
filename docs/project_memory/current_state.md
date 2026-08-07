# Current State

> ## ⚠️ CURRENT TRUTH (2026-08-07) — read this block; everything below it is HISTORY
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

