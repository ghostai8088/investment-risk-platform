# Current State

> **Purpose.** Entry-point snapshot so a fresh Claude Code session can recover context without chat
> history. Read this first, then `project_state.yaml`, `next_actions.md`, and
> `claude_operating_instructions.md`. **As of 2026-06-22.** Values that drift are flagged; re-verify the
> ones in "Re-check at session start" before acting.

## Repository
- **Project:** full-scope enterprise investment-risk platform (monorepo). NOT an MVP/POC — see `build_plan.md`.
- **Layout:** `apps/backend` (FastAPI), `apps/worker`, `apps/frontend`, `packages/shared-python` (`irp_shared`, web-framework-free), `packages/shared-ts`. Postgres + RLS, SQLAlchemy 2.0, Alembic. Numbered governance dirs `01_…`–`11_…`; delivery docs in `10_delivery_backlog/`.
- **Remote:** `github.com/ghostai8088/investment-risk-platform` (branch `main`).

## Latest known committed state
- **origin/main HEAD:** `b1efc05` — "Add durable project-memory artifacts for session recovery" (the P1B-0 docs landed at `dbed93e`, just prior).
- **Local == origin:** at last commit; the P1B-0 ratification edits below are uncommitted in the working tree.
- **Latest CI:** **GREEN** for `b1efc05` (Actions run 27971541638 = success — all 5 jobs: Backend, Frontend, DB migration (Postgres), Documentation check, Secret scan).
- **Migration head:** `0007_generic_ingestion_staging` (next migration is `0008`).

## Working tree (uncommitted)
- **P1B-0 ratification edits** (governance + project_memory) — **modified tracked files**, commit pending approval: AD-013-R1 (decision log); REQ-SMR-005 + annotations + CAP-2.5 re-partition (requirements/capability map); ENT-001…008 annotations (canonical model + temporal §2A); `REFERENCE.*` reserved (audit taxonomy); reference permissions (entitlement model); decision-record status → Ratified; these project_memory files. **No code.**

## Current active gate
**P1B-0 (planning & decisioning) — COMMITTED** (`dbed93e`, CI-green). **P1B-0 ratifications — RECORDED into
the governance source-of-truth (working tree, commit pending approval):** AD-013-R1 (decision log); REQ-SMR-005
+ REQ-SMR-001/003/004 annotations + CAP-2.5 re-partition (backbone/RTM/capability map); ENT-001..008
annotations (canonical model + temporal §2A); `REFERENCE.*` reserved (audit taxonomy); reference permissions
(entitlement model). **No code:** audit codes + entitlement bootstrap are minted inside the P1B build slices.
P1B *implementation* remains **BLOCKED**; next is **P1B-1 planning — NOT implementation**. The platform follows
a strict planning-first, commit-only-on-explicit-approval cadence.

## Completed phases
- **P0.5** engineering hygiene & foundation hardening (scaffold, audit framework, RLS foundation, CI).
- **P1A-0** tenant context / PostgreSQL RLS — `7cdc2f9`.
- **P1A-1** data source + lineage skeleton — `96a1564`.
- **P1A-2** model registry skeleton — `c9be657`.
- **P1A-3** data quality skeleton — `cc472be`.
- **P1A-4** generic ingestion staging — `c781bb8` (+ PG-test fix `0282359`).
- **P1A closeout / P1B readiness review** — `69afedf`.
- **P1B-0 decision record + implementation plan** — `dbed93e` (CI-green). *Planning only — P1B implementation not started.*
- **Durable project-memory artifacts** — `b1efc05` (CI-green).

All P1A slices committed and CI-green. **P1A milestone is CLOSED.** **P1B-0 planning is committed; P1B-0 ratifications are recorded (commit pending).**

## Next required action
The **P1B-0 ratifications are recorded** (working tree, pending commit approval). Next: **commit the
ratification updates** on approval, then **plan P1B-1** (currency / calendar / rating_scale) via the UltraCode
planning workflow — each step gated on explicit approval. **Do not begin P1B implementation.** See `next_actions.md`.

## What MUST NOT be started yet
- **P1B implementation** (any reference entity, migration `0008`, `irp_shared.reference` package, endpoints) — blocked until P1B-0 ratifications + explicit direction.
- **P1C / P2+** — anything beyond Security Master & Reference Data.
- **Any domain functionality:** portfolio, positions, valuations, market prices, market-data ingestion, private-asset ingestion, GP-report parsing, risk calculations, exposure aggregation, limits, breach workflow, dashboards, reporting, real SSO.
- **Never** modify `packages/shared-python/src/irp_shared/audit/service.py` (frozen audit framework).

## Re-check at session start (may have drifted)
- `git log -1 --oneline` and `git status --short` — confirm HEAD and whether the P1B-0 docs / these memory docs were committed since this snapshot.
- Latest CI conclusion for the current HEAD (GitHub Actions; `gh` CLI is NOT installed — query the REST API).
- Whether any P1B-0 ratification (AD-013-R1 in `11_decision_log/architecture_decision_log.md`; REQ-SMR-005 in `02_requirements/`) has been recorded yet.
