# Current State

> ## ⚠️ CURRENT TRUTH (2026-07-30) — read this block; everything below it is HISTORY
>
> **THE GOVERNANCE BATCH (user-ratified 2026-07-30) — standing rules amended, Wave 14 re-sequenced,
> the document surface shrunk.** **MERGED to `main` via PR #150 = `d598ba4`** (carrying `3b74a52` =
> the delivered REF-1 `issuer.sector` write-freeze + record corrections, `dfe0591` = CON-1 planning
> v2, and the five governance commits — all CI green all six).
>
> - **Standing rules amended (`claude_operating_instructions.md`): P7 — lessons are recorded as
>   ACTS, not facts** (mechanical gate with the census > floor > matcher hierarchy / procedural
>   prose bound to a trigger moment / explicit recurrence acceptance — declarative "remember X" is
>   no longer a valid countermeasure), **plus the pre-flight manifests companion** (per change
>   class: migration, governed family, permission, entity, demo stage, dependency — the `dbce327`
>   class becomes a lookup), **the P1 sweep's SEVENTH ledger** (every delivery claim in a record
>   cites its artifact against the MERGED diff — the REF-1 five-false-claims class), **the
>   both-tier-before-push commit rule**, and **roadmap Part 4 rule 6a strengthened** (citations
>   enter records ONLY as verbatim quotes with locators + an independent citation-verification
>   lane — the RM-1/CON-1 misread class). Grounded in the 2026-07-30 four-lane error-trend audit:
>   the escape rate is roughly FLAT; finding counts track verifier intensity, not generation decline.
> - **Wave 14 re-sequenced (Part 2.18): CON-1 DESCOPED** to the `share_invested_long` core with a
>   `denominator_basis` controlled vocabulary — the stopping rule after TWO consecutive refuted
>   denominator foundations (the 2026-07-29 dual-share ratification refuted: `sum(long_amount)` ≠
>   total assets per IRC §851(b)(3)(A)(i), so the share OVERSTATES and LIM-2 would write false
>   breaches into a non-withdrawable lifecycle); **PERF-0** (the measured scale probe) inserted as
>   slice 1.5; **DATA-1** (the first genuinely-sourced external dataset — a real T-bill series
>   through the governed rails + the executed vendor-diligence artifact) inserted as slice 3.5;
>   **DEP-1 + RPT-1 COMMITTED as the Wave-15 openers.** Sequence now: CON-1 → PERF-0 → LIM-2 →
>   CAL-1 → DATA-1 → LQ-1.
> - **Document surface shrunk:** the roadmap 313KB → 164KB (Part 5 rows before 2026-07-27 →
>   `delivery_roadmap_amendment_archive.md`; done-set invariance verified BEFORE the split — 55
>   real ids, floor 38); this file capped to the truth block + live sections (history →
>   `current_state_archive.md`); `build_sequence.md`'s decayed Status column RETIRED to a roadmap
>   pointer; `00_ai_operating_model/` marked HISTORICAL.
> - **Position unchanged by this batch:** migration head `0056`; next free canonical id ENT-069;
>   demo counts 25/40/133; the closed hybrid set N = 7 (AD-013-R2).
> - **CON-1 PLANNING RATIFIED 2026-07-30 (v6, OQ-CON-1-1…28 all as recommended)** after FOUR
>   verifier passes (46 → 47 → 26 → 6 findings; the first citation-lane execution; the targeted
>   pass caught the record's own mis-measured holder sets). The ratified core:
>   `share_invested_long` + `denominator_basis`; `_METRIC_MAP` REVERSED to LIM-2 (no unbased-limit
>   window — REQ-CRD-003 = "produced, bindable at LIM-2"); the three-code mint (auditor_3l out of
>   issuer-identity reads, holder sets recomputed from `ROLE_TEMPLATES`); the row_kind/bucket_code
>   grain with both-dialect partial indexes; the basis discipline; two REF-1 hardenings paid
>   in-slice; the DEMO-CONCENTRATION book; counts 25/40/133 → 26/41/136; minimal FE read KEPT.
>   Branch `con-1-descope-planning`; the Part 6b in-place amendments EXECUTED.
> - **CON-1 IMPLEMENTED (2026-07-30, branch `con-1-descope-planning`, nine checkpoints
>   `668e04f`→`1754359` + the ledger sweep): ENT-069 + migration `0057` (P4 dry run EXECUTED —
>   up/no-drift/down-destroys-staged-rows/up-restores), the `concentration/` package (kernel
>   reproducing the Part 2 literals to 6dp; the binder with the ratified refusal timings), one
>   purpose + four pinned shapes incl. the platform's FIRST code-first re-resolve branch, the
>   three-code mint with recomputed holder sets, seven API routes with the exact route→code
>   census, the minimal FE read, demo stage 19 (counts 25/40/133 → 26/41/136 MEASURED), and the
>   PG suites (grain/RLS/drift-doors). FIRST LIVE BATTERY 143/144 — the single failure (the
>   stage-14 ops role census) REPRODUCES IDENTICALLY ON UNTOUCHED MAIN in the local layout
>   (isolation pair): a pre-existing census layout-sensitivity, recorded, CI adjudicates.**
> - **NEXT = the adversarial review pass, fold, push, CI-to-green, PR** (the merge preconditions).
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

