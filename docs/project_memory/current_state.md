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
- **origin/main HEAD:** `bb89c74` — "Implement P1C-1 portfolio hierarchy and ABAC scope anchor". Chain since P1B-4: `060b2a4` (P1B-4 impl) → `2069b1a` (memory) → `e99633a` (P1B closeout / P1C readiness) → `705d3ba` (P1C-0 decision record + P1C plan) → `b52ad9e` (P1C-1 plan) → `dca7bc0` (P1C-0 ratification) → `bb89c74` (P1C-1 build).
- **Local == origin:** yes; **only this `docs/project_memory/*` refresh is uncommitted** (docs-only, commit pending). No code.
- **Latest CI:** **GREEN** — `bb89c74` = GitHub Actions **run #43 (id 28068172716)** = success, all 5 jobs; the migration job's new **"Portfolio symmetric-RLS tests (Postgres, REQ-PPM-001 / AD-017 / BR-17)"** step + `0012_portfolio` + `alembic check` drift + downgrade smoke all passed. Prior: ratification #42, P1C-1 plan #41.
- **Migration head:** `0012_portfolio` (the P1C-2 **build** will add `0013`).

## Working tree (uncommitted)
- **This `docs/project_memory/*` refresh** (P1C-1 closeout) — modified tracked files, commit pending approval. **No code, no migration, no backend/frontend/worker/shared-package/test/bootstrap/CI changes.**

## Current active gate
**P1C-1 (portfolio hierarchy + ABAC scope anchor) is CLOSED and CI-green** (`bb89c74`, run #43), 8-lens UltraCode reviewed
(7 approve / 1 approve_with_changes, 0 block; the lone MEDIUM = a missing CTRL-032 fail-closed-rollback test, fixed before
commit). The platform's **first domain entity** is delivered: `portfolio` (ENT-010, EV), `PORTFOLIO.CREATE`/`UPDATE`
(EVT-150/151) activated, `data_steward` holds `portfolio.view`+`portfolio.edit`, ABAC **anchored not enforced** (P6+).
The next step is **P1C-2 PLANNING ONLY** (transactions — IA append-only, capture-only), **on explicit approval**.
**P1C-2 implementation is NOT started.** The platform follows a strict planning-first, commit-only-on-explicit-approval
cadence; plan / implement / commit are separate approvals.

## P1C-1 key deliverables (closed, `bb89c74`, CI-green run #43)
REQ-PPM-001 (migration `0012`); the platform's **first domain entity** + the entitlement portfolio-scope **ANCHOR**.
- **`portfolio` = EV entity** (ENT-010) — single `portfolio` table; `__temporal_class__ = EFFECTIVE_DATED`; amend = in-place supersede (`record_version` bump); NOT append-only; NO `system_*`/FR axis; single `status` (no `is_active`). `node_type`/`status` controlled-vocab plain Strings (no enum/CHECK). A portfolio **holds nothing** (no position/valuation/holding/exposure column).
- **Portfolio hierarchy via `parent_portfolio_id`** — intra-tenant self-FK adjacency (NULL = root); `UNIQUE(tenant_id, code)`; self-parent rejected; re-parent re-runs a write-time cycle guard.
- **Bounded ANCESTOR resolver** — `resolve_ultimate_parent` (upward walk; `MAX_HIERARCHY_DEPTH=32` + visited-set + `HierarchyCycleError` + per-hop tenant predicate + boundary-stop) — a direct reuse of the `legal_entity` shape.
- **Bounded DESCENDANT resolver** — `resolve_descendants` (NEW; downward subtree BFS to the same safety invariants) — the substrate for future ABAC subtree scope.
- **ABAC scope ANCHOR (anchor-not-enforce, AD-017 / OD-P1C-A/B):** the node id + adjacency + descendant resolver record future subtree semantics, but **NOTHING reads/filters by scope**. `portfolio.view` gates by role + tenant only; within a tenant any view-holder sees ALL portfolios (documented residual risk + tested as a scope fence). Enforcement → P6+.
- **`PORTFOLIO.CREATE` (EVT-150) / `PORTFOLIO.UPDATE` (EVT-151) ACTIVATED** — caller-side constants in `irp_shared/portfolio/events.py` to the FROZEN `record_event`; per-tenant chain; DC-2 metadata only; a `status` flip rides on `PORTFOLIO.UPDATE` (no STATUS_CHANGE in P1C-1). `audit/service.py` **untouched**.
- **`portfolio.view` / `portfolio.edit`** — the seeded catalog codes wired; `data_steward` granted BOTH (maker reads its own writes); existing `portfolio.view` recipients (`risk_analyst_1l`/`risk_manager_2l`) unchanged; `portfolio.edit` maker/admin only; `auditor_3l` excluded; parity-tested. Deny-by-default `require_permission`.
- **MANUAL `data_source` lineage** — one ORIGIN edge per create (`ensure_manual_source` resolve-or-register + `record_lineage`, fail-closed; `assert_has_lineage`); an EV amend roots **no** new edge.
- **Symmetric tenant-scoped RLS** — `USING == WITH CHECK == own-tenant`, ENABLE+FORCE (migration `0012`); **NEVER hybrid** (no SYSTEM_TENANT; the closed 5-table hybrid set is asserted unchanged — `portfolio` did NOT join it); cross-tenant `parent_portfolio_id` fails closed at the **service layer** (`resolve_portfolio` → `PortfolioNotVisible`) pre-commit; no BYPASSRLS app path.
- **Fail-closed audit rollback (CTRL-032)** — co-transactional: if `record_event`/`record_lineage` raises, the whole unit (portfolio + MANUAL source + ORIGIN edge + audit event) rolls back (no mid-call commit); proven by a negative test.
- **New `irp_shared/portfolio/` package** (the first domain package) — `models`/`events`/`service`/binder; imports ONLY the rails (lineage/audit/db/temporal), never reference/irp_backend/aggregator (import-direction test). 35 portfolio tests (17 logic + 11 endpoint + 7 PG) + a parity test; the 5 thin endpoints (`/portfolios` CRUD + `/{id}/tree`).

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
- **P1B-4 implementation plan** — `f6d691a` (CI-green).
- **P1B-4 reference-data implementation** — `060b2a4` (CI-green, run #37). **P1B-4 CLOSED → P1B block DELIVERED.**
- **P1B closeout / P1C readiness review** — `e99633a` (CI-green, run #39).
- **P1C-0 decision record + P1C implementation plan** — `705d3ba` (CI-green, run #40).
- **P1C-1 portfolio-hierarchy implementation plan** — `b52ad9e` (CI-green, run #41).
- **P1C-0 ratification into governance** — `dca7bc0` (AD-017 + REQ-PPM-001 + PORTFOLIO.* reserved + OD-013/OD-025 closed; CI-green, run #42).
- **P1C-1 portfolio-hierarchy + ABAC scope anchor implementation** — `bb89c74` (CI-green, run #43). **P1C-1 CLOSED** — the first domain entity.

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

## P1B-4 key deliverables (closed, `060b2a4`)
REQ-SMR-004 (corporate_action portion); migration `0011`. The **last reference entity** — capture-only (OD-P1B-B).
- **`corporate_action` = EV reference data** — one physical row; amend = in-place EV supersede (`REFERENCE.UPDATE`); **not IA, not FR**. The EV `valid_from/valid_to` record axis is distinct from the inert business-date columns (`announcement/ex/record/pay/effective_date`); `ratio/amount/currency_code` are inert placeholders.
- **`instrument_id` relationship** — NOT-NULL FK to the P1B-3 `instrument` head; resolved via the **reused `resolve_instrument`** tenant-filtered → cross-tenant/unknown fails closed (`InstrumentNotVisible`) pre-commit (RLS `WITH CHECK` gates only the row's own `tenant_id`).
- **`REFERENCE.STATUS_CHANGE` (EVT-143) ACTIVATED** (R-07 sign-off, OQ-1) — the platform's **first persisted user of EVT-143** — via a NEW caller-side `record_reference_status_change` in `reference/service.py` (no new lineage edge; **`audit/service.py` FROZEN**); used **only** for corporate_action (other entities' `is_active` flips still ride `REFERENCE.UPDATE`; the existing reservation tests stay green).
- **Status lifecycle `ANNOUNCED → CONFIRMED → CANCELLED`** (CANCELLED terminal; **single `status` flag, no `is_active`** — the P1B-3 `arch-1` lesson); a thin guard rejects illegal/no-op/out-of-vocab moves (→ 409; bad initial status → 422) with **no DB write** — validation, not a workflow engine.
- **CAPTURE-ONLY** — **NO** application to positions/valuations, **NO** entitlement/tax calc, **NO** event-processing engine, **NO** roll/day-count math (QS-10/11 → P1C), **NO** vendor feed/reconciliation/override. "No double-apply" holds trivially (nothing is ever applied); scope-fence test asserts no applied/position/valuation/entitlement/tax column.
- Symmetric proprietary RLS (byte-for-byte the `0010` loop); additive `reference.corporate_action.view` (== instrument.view set; `auditor_3l` excluded); parity test. 8-lens reviewed — zero behavioral defect.

## P1B block — DELIVERED
With **P1B-1 (vocabularies/hybrid) + P1B-2 (legal_entity/issuer/counterparty) + P1B-3 (instrument/terms/identifier) + P1B-4 (corporate_action)** all closed and CI-green, the **Security-Master & Reference-Data block is complete**. **P1B-5** (reference-data ingestion mapping) is **conditional/deferred** (only if bulk loading is needed). The CAP-2 EV/FR reference entities (ENT-001..006/008) are realized; the *requirements* REQ-SMR-001/002/003/004 stay **In-Progress** (terms math, exposure-rollup calc, cross-vendor precedence, and QS-10/11 roll math respectively deferred to P1C/P2+).

## Next required action
**P1C-2 PLANNING ONLY** — plan the `transaction` slice (ENT-012, **IA append-only**) via the UltraCode planning workflow:
the first **domain IA** entity (mirror the `ingestion_staged_record`/`lineage_edge` append-only precedent — `APPEND_ONLY_TABLES`
+ `irp_prevent_mutation` P0001 trigger + ORM guard); **capture-only** (an independent trade/cashflow event log keyed to
portfolio + instrument). **On explicit approval. Planning only — do NOT implement P1C-2.** **P1C-2 focus / fences:**
transaction = IA append-only; **capture-only**; **no position derivation** (positions are captured directly in P1C-3, not
derived from transactions); **no valuation**; **no exposure aggregation**. See `next_actions.md`.

## What MUST NOT be started yet
- **P1C-2 implementation** (the `transaction` build) — until its plan is approved (planning is the next step; plan / implement / commit are separate approvals).
- **No position derivation** from transactions (a calc — deferred; P1C-3 captures positions directly). **No positions / no valuations / no holdings.**
- **P1C-3/4/5/6** and **P2+** — not until their slices are planned + approved.
- **Exposure aggregation / `dataset_snapshot` / risk calculations / market data / pricing / valuation models / portfolio performance / corporate-action application / reporting / dashboards / real SSO** — deferred (AD-017 / AD-014); P1C is capture-only.
- **ABAC enforcement** — anchored in P1C-1 but NOT enforced (enforcement → P6+).
- **P1B-5** (reference-data ingestion mapping) — conditional/deferred (only if bulk loading is needed; not now).
- **Never** modify `packages/shared-python/src/irp_shared/audit/service.py` (frozen); no new audit code / permission / role / migration without the governed R-07 update.

## Housekeeping / security (RESOLVED — recorded for recovery)
- A **plaintext GitHub PAT file** was observed in the **parent directory** (one level ABOVE the repo root, OUTSIDE version control — never staged/tracked). The user **deleted the file** and **revoked the token** on GitHub (2026-06-22), and migrated git auth to an **SSH key** (ed25519, passphrase cached in the macOS Keychain; `origin` switched to `git@github.com`). **Standing rule: never read/copy/print/use any credential file found on disk — flag it for the user to revoke/rotate. Do NOT inspect token contents.**

## Re-check at session start (may have drifted)
- `git log -1 --oneline` and `git status --short` — confirm HEAD (≥ `060b2a4`) and whether this memory refresh was committed.
- Latest CI conclusion for the current HEAD (GitHub Actions; `gh` CLI is NOT installed — query the REST API).
- `git remote -v` — origin is now SSH (`git@github.com:ghostai8088/…`).
- Migration head is `0011_corporate_action` (the P1C build will add `0012`).
