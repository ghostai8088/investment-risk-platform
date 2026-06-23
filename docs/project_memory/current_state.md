# Current State

> **Purpose.** Entry-point snapshot so a fresh Claude Code session can recover context without chat
> history. Read this first, then `project_state.yaml`, `next_actions.md`, and
> `claude_operating_instructions.md`. **As of 2026-06-23.** Values that drift are flagged; re-verify the
> ones in "Re-check at session start" before acting.

## Repository
- **Project:** full-scope enterprise investment-risk platform (monorepo). NOT an MVP/POC — see `build_plan.md`.
- **Layout:** `apps/backend` (FastAPI), `apps/worker`, `apps/frontend`, `packages/shared-python` (`irp_shared`, web-framework-free), `packages/shared-ts`. Postgres + RLS, SQLAlchemy 2.0, Alembic. Numbered governance dirs `01_…`–`11_…`; delivery docs in `10_delivery_backlog/`.
- **Remote:** `github.com/ghostai8088/investment-risk-platform` (branch `main`). **origin is now SSH** (`git@github.com:…`; Keychain-backed key — see Housekeeping).

## Latest known committed state
- **origin/main HEAD:** `32c7778` — "Implement P1B-2 reference data legal entity issuer counterparty" (the P1B-2 plan landed at `410cc7e`, just prior).
- **Local == origin:** yes; **only this `docs/project_memory/` refresh is uncommitted** (docs-only, commit pending). No code.
- **Latest CI:** **GREEN** for `32c7778` (GitHub Actions **run #31 = 28029190858** = success — all 5 jobs; the migration job's new **"Legal-entity symmetric-RLS tests (Postgres)"** step passed). P1B-1's `6568cb1` was green at run #28.
- **Migration head:** `0009_legal_entity` (the P1B-3 **build** will add `0010`).

## Working tree (uncommitted)
- **This `docs/project_memory/*` refresh** — modified tracked files, commit pending approval. **No code, no migration, no backend/frontend/worker/shared-package/test/bootstrap/CI changes.**

## Current active gate
**P1B-2 (Reference Data — legal_entity core + issuer/counterparty profiles) is CLOSED and CI-green**
(`32c7778`, run #31), 7-lens UltraCode reviewed. The next step is **P1B-3 PLANNING ONLY** (instrument EV
identity + `instrument_terms` **FR** — the first real bitemporal usage — + `identifier_xref` EV), via the
UltraCode planning workflow, **on explicit approval**. **P1B-3 implementation is NOT started** and must not
begin until the P1B-3 plan is approved. The platform follows a strict planning-first,
commit-only-on-explicit-approval cadence; plan / implement / commit are separate approvals.

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
- **P1B-2 implementation plan** — `410cc7e` (CI-green, run #29).
- **P1B-2 reference-data implementation** — `32c7778` (CI-green, run #31). **P1B-2 CLOSED.**

## P1B-2 key deliverables (closed, `32c7778`)
REQ-SMR-002 (migration `0009`); the platform's **proprietary-never-hybrid** evidence (the inverse of P1B-1).
- **`legal_entity` IMPLEMENTATION-ONLY core — NO canonical ENT ID** (OD-P1B-D); LEI + hierarchy live on the core.
- **`issuer` (ENT-002) + `counterparty` (ENT-003) as SEPARATE 1:1 role/profile tables** over the core (`UNIQUE(tenant_id, legal_entity_id)` + NOT-NULL FK); a legal entity may carry both; the unified-table-with-flags alternative was NOT built.
- **Symmetric tenant-scoped RLS** (`USING == WITH CHECK == own-tenant`; FORCE RLS) — **proprietary-never-hybrid**: no SYSTEM_TENANT rows; no-context read returns **zero** rows; `pg_policies` positive symmetric assertion + the **closed hybrid set stays exactly the 5 P1B-1 tables**; `data_source` stays symmetric.
- **LEI partial-uniqueness:** Postgres partial-unique `(tenant_id, lei) WHERE lei IS NOT NULL` (per-tenant when present; NULLs coexist; same lei across tenants allowed); drift-clean; SQLite + PG behavioral tests.
- **Legal-entity hierarchy STRUCTURE:** `parent_legal_entity_id` intra-tenant self-FK adjacency; the **exposure-rollup CALCULATION is DEFERRED** (no risk math, no stored `ultimate_parent` column; counterparty has zero netting/CSA/collateral/exposure columns).
- **Bounded ultimate-parent resolver:** `resolve_ultimate_parent` (visited-set + depth cap 32, cycle-safe, boundary-terminating); each hop carries an EXPLICIT `tenant_id` predicate (cross-tenant fails closed on SQLite + PG); pure structural walk.
- Reuse `REFERENCE.CREATE/UPDATE` (each entity OWN event, NOT folded; `audit/service.py` FROZEN); one MANUAL-`data_source` ORIGIN edge per row; additive `reference.legal_entity.view/edit` (`.view` recipients == issuer/counterparty.view set — **EXCLUDES `auditor_3l`**, proprietary-identity SoD).

## P1B-3 focus (the PLANNED next slice — NOT yet planned/built)
REQ-SMR-001 (instrument) + REQ-SMR-003 (identifier_xref). The **first real bitemporal usage** on the platform.
- **`instrument` = EV identity** (asset_class, status, issuer FK → the `issuer` profile) — OD-P1B-A.
- **`instrument_terms` = FR** (`FullReproducibleMixin`) — coupon/maturity/call/day-count/denomination ccy; instrument FK. **The first persisted user of FR / bitemporality** (it has been unexercised through P1B-2).
- **`identifier_xref` = EV** (scheme/value, valid_from/valid_to); tenant-scoped.
- **Deterministic single-result-or-`AmbiguousIdentifier` resolution** (OD-P1B-G); partial-unique `(tenant_id, scheme, value) WHERE valid_to IS NULL`; cross-vendor precedence DEFERRED (OD-012 → P1C).
- All tenant-scoped SYMMETRIC RLS (proprietary, NEVER hybrid); FR temporal queries apply the native-uuid CI lessons.

## Next required action
**Plan P1B-3** (instrument EV + `instrument_terms` FR + identifier_xref EV — OD-P1B-A/G) via the UltraCode
planning workflow → committed plan doc, **on explicit approval. Planning only — do NOT implement P1B-3.**
See `next_actions.md` for the exact prompt and gates.

## What MUST NOT be started yet
- **P1B-3 implementation** (instrument / instrument_terms FR / identifier_xref entities, migration `0010`, endpoints) — until the P1B-3 plan is **approved**.
- **P1B-4** (corporate_action), **P1B-5** (ingestion mapping) — later sub-slices, not now.
- No **corporate_action**; no **portfolio / positions / valuations**; no **market data / private-asset ingestion / risk calculations / exposure aggregation / reporting / dashboards / real SSO**.
- **P1C / P2+** — anything beyond Security Master & Reference Data.
- **Never** modify `packages/shared-python/src/irp_shared/audit/service.py` (frozen); no new audit code / permission / role without the governed R-07 update.

## Housekeeping / security (RESOLVED — recorded for recovery)
- A **plaintext GitHub PAT file** was observed in the **parent directory** (one level ABOVE the repo root, OUTSIDE version control — never staged/tracked). The user **deleted the file** and **revoked the token** on GitHub (2026-06-22), and migrated git auth to an **SSH key** (ed25519, passphrase cached in the macOS Keychain; `origin` switched to `git@github.com`). **Standing rule: never read/copy/print/use any credential file found on disk — flag it for the user to revoke/rotate. Do NOT inspect token contents.**

## Re-check at session start (may have drifted)
- `git log -1 --oneline` and `git status --short` — confirm HEAD (≥ `32c7778`) and whether this memory refresh was committed.
- Latest CI conclusion for the current HEAD (GitHub Actions; `gh` CLI is NOT installed — query the REST API).
- `git remote -v` — origin is now SSH (`git@github.com:ghostai8088/…`).
- Migration head is `0009_legal_entity` (the P1B-3 build will add `0010`).
