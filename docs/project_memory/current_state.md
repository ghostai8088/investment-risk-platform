# Current State

> **Purpose.** Entry-point snapshot so a fresh Claude Code session can recover context without chat
> history. Read this first, then `project_state.yaml`, `next_actions.md`, and
> `claude_operating_instructions.md`. **As of 2026-06-22.** Values that drift are flagged; re-verify the
> ones in "Re-check at session start" before acting.

## Repository
- **Project:** full-scope enterprise investment-risk platform (monorepo). NOT an MVP/POC — see `build_plan.md`.
- **Layout:** `apps/backend` (FastAPI), `apps/worker`, `apps/frontend`, `packages/shared-python` (`irp_shared`, web-framework-free), `packages/shared-ts`. Postgres + RLS, SQLAlchemy 2.0, Alembic. Numbered governance dirs `01_…`–`11_…`; delivery docs in `10_delivery_backlog/`.
- **Remote:** `github.com/ghostai8088/investment-risk-platform` (branch `main`). **origin is now SSH** (`git@github.com:…`; Keychain-backed key — see Housekeeping).

## Latest known committed state
- **origin/main HEAD:** `410cc7e` — "Add P1B-2 implementation plan" (the P1B-1 implementation landed at `6568cb1`, just prior).
- **Local == origin:** yes; **only this `docs/project_memory/` refresh is uncommitted** (docs-only, commit pending). No code.
- **Latest CI:** **GREEN** for `410cc7e` (GitHub Actions **run #29 = 27996506127** = success; docs-only change). P1B-1's `6568cb1` was green at run #28 (27982349921).
- **Migration head:** `0008_reference_data` (the P1B-2 plan commit added no migration; the P1B-2 **build** will add `0009`).

## Working tree (uncommitted)
- **This `docs/project_memory/*` refresh** — modified tracked files, commit pending approval. **No code, no migration, no backend/frontend/worker/shared-package/test/bootstrap/CI changes.**

## Current active gate
**P1B-1 (Reference Data — currency / calendar / rating_scale) is CLOSED and CI-green** (`6568cb1`, run #28).
The **P1B-2 implementation PLAN is COMMITTED and CI-green** (`410cc7e`, run #29), 7-lens UltraCode reviewed and
hardened. **P1B-2 IMPLEMENTATION is READY to begin, pending EXPLICIT approval — implementation is NOT started.**
Do not begin the build until directed; the paste-ready kickoff is **§21 of `10_delivery_backlog/p1b2_implementation_plan.md`**.
The platform follows a strict planning-first, commit-only-on-explicit-approval cadence; plan / implement / commit are separate approvals.

## P1B-1 key deliverables (closed, `6568cb1`)
- **Five EV reference tables** (migration `0008`): `currency`, `calendar`, `calendar_holiday`, `rating_scale`, `rating_grade` — all `__temporal_class__ = EFFECTIVE_DATED`, `UNIQUE(tenant_id, code)` (never `UNIQUE(code)`), no append-only trigger.
- **First asymmetric hybrid RLS slice (AD-013-R1):** `USING (own-tenant OR SYSTEM_TENANT) / WITH CHECK (own-tenant only)`; FORCE RLS on all five; children carry their **own** hybrid policy. The shipped symmetric loop (0001/0004/0005/0007) is untouched.
- **SYSTEM_TENANT global-read behavior:** SYSTEM rows readable by every tenant (closed set = these 5 tables only); a tenant **cannot** write a SYSTEM row (`WITH CHECK` → 42501); no-context read returns only the global slice; `data_source` stays symmetric (NOT hybrid).
- **Tenant-wins application-layer dedup:** `service.dedupe_tenant_wins` (DISTINCT-ON-by-`code`, own-tenant wins) — precedence in the app layer, **never** in RLS.
- **`REFERENCE.CREATE` (EVT-140) / `REFERENCE.UPDATE` (EVT-141) ACTIVATED** as caller constants to the FROZEN `record_event`; children fold into the parent event; per-tenant + SYSTEM hash chains. (`REFERENCE.CORRECTION`/`STATUS_CHANGE` reserved, not emitted.)
- **Lineage:** one ORIGIN edge per entity from a per-tenant **MANUAL** `data_source` (`ensure_manual_source`, idempotent); SYSTEM seeds rooted on the SYSTEM chain.
- **New web-framework-free `irp_shared.reference` package** (one-way deps) + thin `api/reference.py` endpoints + additive `reference.currency.*` / `reference.rating_scale.*` / `reference.calendar.view` permissions + a governed SYSTEM seeder (test-proven; not yet wired into a prod post-migrate path).

## Completed phases
- **P0.5** engineering hygiene & foundation (scaffold, audit framework, RLS foundation, CI).
- **P1A-0…P1A-4** the cross-cutting rails — `7cdc2f9`, `96a1564`, `c9be657`, `cc472be`, `c781bb8` (+ PG fix `0282359`). **P1A milestone CLOSED.**
- **P1A closeout / P1B readiness** — `69afedf`.
- **P1B-0 decision record + plan** — `dbed93e`; **ratifications into governance** — `4fae26b`; **project-memory artifacts** — `b1efc05`.
- **P1B-1 implementation plan** — `05ee5f5`.
- **P1B-1 reference-data implementation** — `6568cb1` (CI-green, run #28). **P1B-1 CLOSED.**
- **P1B-2 implementation plan** — `410cc7e` (CI-green, run #29). *Plan only — P1B-2 implementation not started.*

## P1B-2 invariants (the PLANNED next slice — committed plan `410cc7e`, NOT yet built)
Plan: `10_delivery_backlog/p1b2_implementation_plan.md` (§21 = kickoff). REQ-SMR-002 (issuer ENT-002 +
counterparty ENT-003 over a shared `legal_entity` core).
- **`legal_entity` is IMPLEMENTATION-ONLY — NO canonical ENT ID** (OD-P1B-D); a normalization of shared LEI/name/hierarchy, not a new domain entity.
- **`issuer` and `counterparty` are SEPARATE 1:1 role/profile tables** over the core (`UNIQUE(tenant_id, legal_entity_id)`, NOT-NULL FK); the unified-table-with-flags alternative is REJECTED; a legal entity may carry both.
- **All three are EV** (`__temporal_class__ = EFFECTIVE_DATED`); none append-only, none FR; one physical row per logical entity (in-place supersede, history via `REFERENCE.UPDATE` audit).
- **All three are tenant-scoped and NEVER hybrid** — PROPRIETARY → SYMMETRIC RLS (`USING == WITH CHECK == own-tenant`), no SYSTEM_TENANT (OD-P1B-C). Resolvers carry an EXPLICIT tenant predicate (cross-tenant fails closed on SQLite + PG).
- **Hierarchy STRUCTURE belongs in P1B-2** (`parent_legal_entity_id` self-FK adjacency + a bounded, cycle-safe, tenant-filtered `resolve_ultimate_parent`, depth cap 32); the **exposure-rollup CALCULATION is DEFERRED** (no risk math).
- **No netting / CSA / collateral / exposure columns** (OD-015 deferred); no stored rollup column.
- Reuse `REFERENCE.CREATE/UPDATE` (each entity OWN event; `audit/service.py` FROZEN); additive `reference.legal_entity.view/edit` only (`legal_entity.view` matches the issuer/counterparty recipient set — EXCLUDES `auditor_3l`).

## Next required action
**Implement P1B-2** (legal_entity core + issuer / counterparty role profiles) **on explicit approval**, via the
§21 kickoff prompt of `p1b2_implementation_plan.md` (multi-lens review → fix → `make check` + the new
legal-entity RLS PG step → commit on approval). **Do NOT begin the build until directed.** See `next_actions.md`.

## What MUST NOT be started yet
- **P1B-2 implementation** (legal_entity / issuer / counterparty entities, migration `0009`, `api/reference_entities.py`) — until **explicitly approved**.
- **P1B-3** (instrument / instrument_terms FR / identifier_xref), **P1B-4** (corporate_action), **P1B-5** (ingestion mapping) — later sub-slices, not now.
- No **instrument / instrument_terms / identifier_xref / corporate_action**; no **portfolio / positions / valuations**; no **market data / private-asset ingestion / risk calculations / exposure aggregation / reporting / dashboards / real SSO**.
- **P1C / P2+** — anything beyond Security Master & Reference Data.
- **Never** modify `packages/shared-python/src/irp_shared/audit/service.py` (frozen); no new audit code / permission / role without the governed R-07 update.

## Housekeeping / security (RESOLVED — recorded for recovery)
- A **plaintext GitHub PAT file** was observed in the **parent directory** (one level ABOVE the repo root, OUTSIDE version control — never staged/tracked). The user **deleted the file** and **revoked the token** on GitHub (2026-06-22), and migrated git auth to an **SSH key** (ed25519, passphrase cached in the macOS Keychain; `origin` switched to `git@github.com`). **Standing rule: never read/copy/print/use any credential file found on disk — flag it for the user to revoke/rotate. Do NOT inspect token contents.**

## Re-check at session start (may have drifted)
- `git log -1 --oneline` and `git status --short` — confirm HEAD (≥ `410cc7e`) and whether this memory refresh was committed.
- Latest CI conclusion for the current HEAD (GitHub Actions; `gh` CLI is NOT installed — query the REST API).
- `git remote -v` — origin is now SSH (`git@github.com:ghostai8088/…`).
- Migration head is `0008_reference_data` (the P1B-2 build will add `0009`).
