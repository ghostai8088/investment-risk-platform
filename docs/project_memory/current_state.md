# Current State

> **Purpose.** Entry-point snapshot so a fresh Claude Code session can recover context without chat
> history. Read this first, then `project_state.yaml`, `next_actions.md`, and
> `claude_operating_instructions.md`. **As of 2026-06-24.** Values that drift are flagged; re-verify the
> ones in "Re-check at session start" before acting.

## Repository
- **Project:** full-scope enterprise investment-risk platform (monorepo). NOT an MVP/POC — see `build_plan.md`.
- **Layout:** `apps/backend` (FastAPI), `apps/worker`, `apps/frontend`, `packages/shared-python` (`irp_shared`, web-framework-free), `packages/shared-ts`. Postgres + RLS, SQLAlchemy 2.0, Alembic. Numbered governance dirs `01_…`–`11_…`; delivery docs in `10_delivery_backlog/`.
- **Remote:** `github.com/ghostai8088/investment-risk-platform` (branch `main`). **origin is now SSH** (`git@github.com:…`; Keychain-backed key — see Housekeeping).

## Latest known committed state
- **origin/main HEAD:** `8545ed6` — "Implement P1B-3 reference data instrument terms identifiers" (the P1B-3 plan landed at `43c042e`; P1B-2 implementation at `32c7778`, just prior).
- **Local == origin:** yes; **only this `docs/project_memory/` refresh is uncommitted** (docs-only, commit pending). No code.
- **Latest CI:** **GREEN** for `8545ed6` (GitHub Actions **run #34 = 28042611593** = success — all 5 jobs; the migration job's new **"Instrument / identifier symmetric-RLS + FR-bitemporal tests (Postgres)"** step passed). P1B-2's `32c7778` was green at run #31.
- **Migration head:** `0010_instrument` (the P1B-4 **build** will add `0011`).

## Working tree (uncommitted)
- **This `docs/project_memory/*` refresh** — modified tracked files, commit pending approval. **No code, no migration, no backend/frontend/worker/shared-package/test/bootstrap/CI changes.**

## Current active gate
**P1B-3 (Reference Data — instrument + `instrument_terms` FR + `identifier_xref`) is CLOSED and CI-green**
(`8545ed6`, run #34), 8-lens UltraCode reviewed — the platform's **first real FR / bitemporal** slice. The
next step is **P1B-4 PLANNING ONLY** (`corporate_action` = EV effective-dated reference data), via the
UltraCode planning workflow, **on explicit approval**. **P1B-4 implementation is NOT started** and must not
begin until the P1B-4 plan is approved. The platform follows a strict planning-first,
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
- **P1B-3 implementation plan** — `43c042e` (CI-green).
- **P1B-3 reference-data implementation** — `8545ed6` (CI-green, run #34). **P1B-3 CLOSED.**

## P1B-2 key deliverables (closed, `32c7778`)
REQ-SMR-002 (migration `0009`); the platform's **proprietary-never-hybrid** evidence (the inverse of P1B-1).
- **`legal_entity` IMPLEMENTATION-ONLY core — NO canonical ENT ID** (OD-P1B-D); LEI + hierarchy live on the core.
- **`issuer` (ENT-002) + `counterparty` (ENT-003) as SEPARATE 1:1 role/profile tables** over the core (`UNIQUE(tenant_id, legal_entity_id)` + NOT-NULL FK); a legal entity may carry both; the unified-table-with-flags alternative was NOT built.
- **Symmetric tenant-scoped RLS** (`USING == WITH CHECK == own-tenant`; FORCE RLS) — **proprietary-never-hybrid**: no SYSTEM_TENANT rows; no-context read returns **zero** rows; `pg_policies` positive symmetric assertion + the **closed hybrid set stays exactly the 5 P1B-1 tables**; `data_source` stays symmetric.
- **LEI partial-uniqueness:** Postgres partial-unique `(tenant_id, lei) WHERE lei IS NOT NULL` (per-tenant when present; NULLs coexist; same lei across tenants allowed); drift-clean; SQLite + PG behavioral tests.
- **Legal-entity hierarchy STRUCTURE:** `parent_legal_entity_id` intra-tenant self-FK adjacency; the **exposure-rollup CALCULATION is DEFERRED** (no risk math, no stored `ultimate_parent` column; counterparty has zero netting/CSA/collateral/exposure columns).
- **Bounded ultimate-parent resolver:** `resolve_ultimate_parent` (visited-set + depth cap 32, cycle-safe, boundary-terminating); each hop carries an EXPLICIT `tenant_id` predicate (cross-tenant fails closed on SQLite + PG); pure structural walk.
- Reuse `REFERENCE.CREATE/UPDATE` (each entity OWN event, NOT folded; `audit/service.py` FROZEN); one MANUAL-`data_source` ORIGIN edge per row; additive `reference.legal_entity.view/edit` (`.view` recipients == issuer/counterparty.view set — **EXCLUDES `auditor_3l`**, proprietary-identity SoD).

## P1B-3 key deliverables (closed, `8545ed6`)
REQ-SMR-001 (instrument) + REQ-SMR-003 (identifier_xref, partial); migration `0010`. The platform's **first real FR / bitemporal** slice.
- **`instrument` = EV identity/master data only** — code, name, asset_class, instrument_type, nullable `issuer_id` FK → the `issuer` profile, plain-ISO `currency_code`, `is_active` (single lifecycle flag, **no `status` string**). **No** price/valuation/holding/risk/terms columns.
- **`instrument_terms` = FR / fully-reproducible / bitemporal** — the platform's **first persisted user of `FullReproducibleMixin`** (`valid_from/valid_to` + `system_from/system_to`). Protocol: create → effective-dated supersede (close prior `valid_to`) → as-known **correction/restatement** (close prior `system_to`). One-`now` per op; close-first ordering; prior versions' economics never mutated; **NOT append-only** (no `irp_prevent_mutation` trigger); current-head partial-unique `(tenant_id, instrument_id) WHERE valid_to IS NULL AND system_to IS NULL`.
- **Valid-time reconstruction** — `reconstruct_terms_as_of(valid_at)` returns the version effective at the business date (TR-01). **Known-at / system-time reconstruction** — `reconstruct_terms_as_of(valid_at, known_at)` returns the version as-known-at the knowledge date (TR-02/TR-04; default `known_at`=now=current view). Both axes acceptance-tested on SQLite **and** PG-under-FORCE-RLS.
- **`REFERENCE.CORRECTION` (EVT-142) ACTIVATED** for terms restatement (R-07 sign-off, OQ-7) via a NEW caller-side `record_reference_correction` in `reference/service.py`; **`audit/service.py` stays FROZEN**; TR-08 `restatement_reason` on the canonical `justification` field + `supersedes_id` link in DC-2 `after_value`.
- **`identifier_xref` = EV** — polymorphic `(entity_type, entity_id)` no-FK, scoped to `entity_type='instrument'`; active partial-unique `(tenant_id, scheme, value) WHERE valid_to IS NULL`. **Deterministic single-result-or-`AmbiguousIdentifier`** resolution (OD-P1B-G / CTRL-029) — never a silent arbitrary match; endpoint 200/404/409; cross-vendor precedence DEFERRED (OD-012 → P1C).
- All three PROPRIETARY tenant-scoped **SYMMETRIC RLS** (byte-for-byte the `0009` loop); **NEVER hybrid**; closed-hybrid-set still the 5 P1B-1 tables. Cross-tenant `issuer_id`/`instrument_id`/`entity_id` fail closed via the **service-layer** `*NotVisible` predicate pre-commit. Additive `reference.identifier.view/edit` (`.resolve` recipients unchanged; `auditor_3l` excluded). 8-lens reviewed — zero behavioral defect.

## P1B-4 focus (the PLANNED next slice — NOT yet planned/built)
REQ-SMR-004 (corporate_action portion). OD-P1B-B.
- **`corporate_action` = EV (effective-dated reference data)** — the reference ENTITY only (effective-dated declarations); tenant-scoped SYMMETRIC RLS (proprietary, never hybrid); REFERENCE.* audit; MANUAL-source lineage; additive entitlements.
- **Excluded:** **NO** application of corporate actions to positions; **NO** valuation/position adjustment; **NO** event-processing / lifecycle engine; **NO** day-count/roll math (QS-10/11 → P1C).

## Next required action
**Plan P1B-4** (`corporate_action` = EV effective-dated reference data — OD-P1B-B) via the UltraCode planning
workflow → committed plan doc, **on explicit approval. Planning only — do NOT implement P1B-4.**
See `next_actions.md` for the exact prompt and gates.

## What MUST NOT be started yet
- **P1B-4 implementation** (`corporate_action` entity, migration `0011`, endpoints) — until the P1B-4 plan is **approved**.
- **No application of corporate actions to positions; no valuation/position adjustment; no event-processing engine** (the corporate_action ENTITY only).
- No **portfolio / positions / valuations**; no **market data / pricing / risk calculations / exposure aggregation / reporting / dashboards / real SSO**.
- **P1C / P2+** — anything beyond Security Master & Reference Data.
- **Never** modify `packages/shared-python/src/irp_shared/audit/service.py` (frozen); no new audit code / permission / role without the governed R-07 update.

## Housekeeping / security (RESOLVED — recorded for recovery)
- A **plaintext GitHub PAT file** was observed in the **parent directory** (one level ABOVE the repo root, OUTSIDE version control — never staged/tracked). The user **deleted the file** and **revoked the token** on GitHub (2026-06-22), and migrated git auth to an **SSH key** (ed25519, passphrase cached in the macOS Keychain; `origin` switched to `git@github.com`). **Standing rule: never read/copy/print/use any credential file found on disk — flag it for the user to revoke/rotate. Do NOT inspect token contents.**

## Re-check at session start (may have drifted)
- `git log -1 --oneline` and `git status --short` — confirm HEAD (≥ `8545ed6`) and whether this memory refresh was committed.
- Latest CI conclusion for the current HEAD (GitHub Actions; `gh` CLI is NOT installed — query the REST API).
- `git remote -v` — origin is now SSH (`git@github.com:ghostai8088/…`).
- Migration head is `0010_instrument` (the P1B-4 build will add `0011`).
