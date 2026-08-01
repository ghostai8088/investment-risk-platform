# Current State

> ## ⚠️ CURRENT TRUTH (2026-08-01) — read this block; everything below it is HISTORY
>
> **LIM-2 IS CLOSED (Wave-14 slice 2) — concentration limits, the dimensional selector.** Merged
> via **PR #155** = `b4905e3`, merged-main CI observed green; the P1 sweep executed and clean
> (seven ledgers, merged tree byte-identical to the 2,834-test-validated tree). Migration head
> **`0058`**; next free canonical id **ENT-070** (ENT-032 stays the sole reservation); demo counts
> **26/41/136 UNCHANGED** (the final-position pin deliberately did not move); hybrid set N = 7
> unchanged.
>
> - **What shipped:** the `LimitFamily` registry + exact set-equality census over `_METRIC_MAP`;
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

