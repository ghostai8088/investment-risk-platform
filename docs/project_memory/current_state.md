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
- **origin/main HEAD:** `dbed93e` — "Add P1B-0 decision record and P1B implementation plan".
- **Local == origin:** 0 ahead / 0 behind (at time of writing).
- **Latest CI:** **GREEN** for `dbed93e` (Actions run 27969793585 = success — all 5 jobs: Backend, Frontend, DB migration (Postgres), Documentation check, Secret scan).
- **Migration head:** `0007_generic_ingestion_staging` (next migration is `0008`).

## Working tree (uncommitted)
- `docs/project_memory/*` — these memory artifacts; **untracked**, pending their own commit approval.
- (The two P1B-0 planning docs are now **committed** at `dbed93e` — see "Latest known committed state".)

## Current active gate
**P1B-0 (planning & decisioning) — COMMITTED** (`dbed93e`, CI-green). P1B *implementation* remains
**BLOCKED** until the P1B-0 ratifications are recorded (still planning/governance docs, **no code**):
**AD-013-R1**; **REQ-SMR-005** + CAP-2.5 re-partition; the **`REFERENCE.*`** audit category + entitlement
additions. The next work is those ratifications and **P1B-1 planning — NOT implementation**. The platform
follows a strict planning-first, commit-only-on-explicit-approval cadence.

## Completed phases
- **P0.5** engineering hygiene & foundation hardening (scaffold, audit framework, RLS foundation, CI).
- **P1A-0** tenant context / PostgreSQL RLS — `7cdc2f9`.
- **P1A-1** data source + lineage skeleton — `96a1564`.
- **P1A-2** model registry skeleton — `c9be657`.
- **P1A-3** data quality skeleton — `cc472be`.
- **P1A-4** generic ingestion staging — `c781bb8` (+ PG-test fix `0282359`).
- **P1A closeout / P1B readiness review** — `69afedf`.
- **P1B-0 decision record + implementation plan** — `dbed93e` (CI-green). *Planning only — P1B implementation not started.*

All P1A slices committed and CI-green. **P1A milestone is CLOSED.** **P1B-0 planning is committed.**

## Next required action
Record the **P1B-0 ratifications** (planning/governance docs only — AD-013-R1; REQ-SMR-005 + CAP-2.5
re-partition; the `REFERENCE.*` audit category + entitlement additions) and **plan P1B-1** — each step gated
on explicit approval. **Do not begin P1B implementation.** (The `docs/project_memory/*` artifacts are also
pending their own commit approval.) See `next_actions.md`.

## What MUST NOT be started yet
- **P1B implementation** (any reference entity, migration `0008`, `irp_shared.reference` package, endpoints) — blocked until P1B-0 ratifications + explicit direction.
- **P1C / P2+** — anything beyond Security Master & Reference Data.
- **Any domain functionality:** portfolio, positions, valuations, market prices, market-data ingestion, private-asset ingestion, GP-report parsing, risk calculations, exposure aggregation, limits, breach workflow, dashboards, reporting, real SSO.
- **Never** modify `packages/shared-python/src/irp_shared/audit/service.py` (frozen audit framework).

## Re-check at session start (may have drifted)
- `git log -1 --oneline` and `git status --short` — confirm HEAD and whether the P1B-0 docs / these memory docs were committed since this snapshot.
- Latest CI conclusion for the current HEAD (GitHub Actions; `gh` CLI is NOT installed — query the REST API).
- Whether any P1B-0 ratification (AD-013-R1 in `11_decision_log/architecture_decision_log.md`; REQ-SMR-005 in `02_requirements/`) has been recorded yet.
