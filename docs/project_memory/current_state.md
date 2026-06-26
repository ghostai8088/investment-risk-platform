# Current State

> **Purpose.** Entry-point snapshot so a fresh Claude Code session can recover context without chat
> history. Read this first, then `project_state.yaml`, `next_actions.md`, and
> `claude_operating_instructions.md`. **As of 2026-06-26.** Values that drift are flagged; re-verify the
> ones in "Re-check at session start" before acting.

## Repository
- **Project:** full-scope enterprise investment-risk platform (monorepo). NOT an MVP/POC — see `build_plan.md`.
- **Layout:** `apps/backend` (FastAPI), `apps/worker`, `apps/frontend`, `packages/shared-python` (`irp_shared`, web-framework-free), `packages/shared-ts`. Postgres + RLS, SQLAlchemy 2.0, Alembic. Numbered governance dirs `01_…`–`11_…`; delivery docs in `10_delivery_backlog/`.
- **Remote:** `github.com/ghostai8088/investment-risk-platform` (branch `main`). **origin is now SSH** (`git@github.com:…`; Keychain-backed key — see Housekeeping).

## Latest known committed state
- **origin/main HEAD:** `63be23a` — "Ratify P2 dataset snapshot governance". Chain since P1C-6 build: `3e9882d` (P1C-6 build, #60) → `9584ba4` (P1C-6 closeout memory, #61) → `7070dff` (P1C closeout / P2 readiness review, #62) → `2d19992` (P2-0 decision record + P2 implementation plan, #63) → `d7be981` (P2-1 dataset_snapshot implementation plan, #64) → `63be23a` (P2 dataset_snapshot governance ratification, #65).
- **Local == origin:** yes; **only this `docs/project_memory/*` refresh (P2 closeout) is uncommitted** (docs-only, commit pending). No code.
- **Latest CI:** **GREEN** — `63be23a` = GitHub Actions **run #65 (id 28245890604)** = success — verified via the REST API this session. A **docs-only** governance ratification (8 markdown files); the migration job gained NO new step (head stays `0015_valuation`). Prior P2 runs all green: P2-1 plan #64 (`d7be981`), P2-0 #63 (`2d19992`), P1C closeout/readiness #62 (`7070dff`), P1C-6 closeout memory #61 (`9584ba4`), P1C-6 build #60 (`3e9882d`).
- **Migration head:** `0015_valuation` — **unchanged through the entire P2 planning + ratification phase** (all planning/governance docs, no code; the next migration `0016_dataset_snapshot` lands only when **P2-1 is implemented**).

## Working tree (uncommitted)
- **This `docs/project_memory/*` refresh** (P2 closeout — P1C closeout/readiness + P2-0 + P2-1 plan + P2 governance ratification) — modified tracked files, commit pending approval. **No code, no migration, no backend/frontend/worker/shared-package/test/bootstrap/CI changes.**

## Current active gate
**P2 PLANNING + GOVERNANCE RATIFICATION are COMPLETE and CI-green.** The full P1C block (P1C-1…P1C-6) is **DELIVERED**
(capture-only domain base, AD-017). On top of it, the **P2 reproducibility-foundation phase is planned and ratified into the
governance source-of-truth** — **all planning-only, NO code**:
- **P1C closeout / P2 readiness review** (`7070dff`, run #62; 8-lens) — chose **reproducibility-first** P2 sequencing (snapshot before any official derived number).
- **P2-0 decision record + P2 implementation plan** (`2d19992`, run #63; 8-lens, 0 block) — OD-P2-A…L; the reproducibility-first subphase structure **P2-1 snapshot → P2-2 FX → P2-3 calculation_run+exposure → P2-4 price → P2-5 curves → P2-6 benchmark**.
- **P2-1 `dataset_snapshot` implementation plan** (`d7be981`, run #64; 8-lens, 0 block) — the detailed build plan for the AD-014 reproducibility primitive (§1–§24).
- **P2 `dataset_snapshot` governance ratification** (`63be23a`, run #65; **7-lens, 7× approve, 0 block**) — recorded into the source-of-truth (see next section).
**The next step is P2-1 IMPLEMENTATION ONLY** — build the `dataset_snapshot` primitive per `10_delivery_backlog/p2_1_dataset_snapshot_implementation_plan.md` §24, **on explicit approval. P2-1 implementation is NOT started** (no `snapshot` package; migration head `0015_valuation`; `audit/service.py` FROZEN; `entitlement/bootstrap.py` unchanged). Strict planning-first, commit-only-on-explicit-approval cadence holds (plan / review / ratify / implement / commit are separate approvals).

## P2 governance ratification (committed `63be23a`, CI-green run #65) — RESERVED/PLANNED, no code
Ratified-in-planning into the governance source-of-truth (8 markdown files). **`audit/service.py` FROZEN; `entitlement/bootstrap.py` UNCHANGED; migration head `0015_valuation`; no `snapshot` package.** 7-lens reviewed (7× approve, 0 block — zero drift from the committed plans).
- **ENT-049 `dataset_snapshot`** + **ENT-050 `dataset_snapshot_component`** minted into the canonical model — the AD-014 reproducible input snapshot (header + per-input physical-version pin: `target_entity_id` (surrogate id) + `valid_from`/`system_from` (FR; NULL for EV) + `record_version` + `captured_content` + `content_hash`; SHA-256 app-side canonical serialization excluding `valid_to`/`system_to`; vocab PORTFOLIO/POSITION/VALUATION, FX reserved P2-2; **no status / no model_version component**).
- **IA TRUE append-only** temporal classification (in `APPEND_ONLY_TABLES`, the `transaction` precedent — NOT the status-mutable `calculation_run`); recorded in `temporal_reproducibility_standard.md` §2A.
- **`SNAPSHOT.CREATE` RESERVED at the EVT-190 block** in the audit taxonomy — **not activated** (activation only in P2-1 impl; DC-2 metadata only; no read/verify emit).
- **`snapshot.view` / `snapshot.create` RESERVED** in the entitlement model — `data_steward` maker; `auditor_3l` excluded; deny-by-default; **NOT minted** in `bootstrap.py`.
- **AD-004-R1** — Postgres-first behind the AD-004 market-data repository interface (honest deviation from "Timescale initially"; Timescale deferred to a measured threshold); **OD-014 resolved**.
- **REQ-PPM-004 (exposure aggregation) → In-Progress** — the AD-014 `dataset_snapshot` prereq is P2-1; the `calculation_run`-bound aggregation builds at P2-3 (RTM control set CTRL-006/018 + FW-RUN/DEP-LIN/CAP-1 preserved).
- **Control matrix** maps reproducibility / append-only / lineage / RLS / fail-closed to **existing** CTRLs (009/017/006/013/011/023/032) — **no new CTRL minted, no control weakened**; records "no official derived number before snapshot/run binding".
- **No implementation yet.**

## P2-1 implementation focus (the NEXT build — on explicit approval)
`dataset_snapshot` + `dataset_snapshot_component` (IA TRUE append-only) · **physical-version pins** (surrogate id + `valid_from`/`system_from` + `record_version`) · **`captured_content` + canonical SHA-256 hash** (app-side, excludes close-out markers) · the **cross-tenant binding-integrity invariant** (resolve only under the acting tenant's RLS; foreign proprietary id → fail closed, no snapshot) · a **narrow internal snapshot lineage writer** (not a framework rewrite) · a **caller-side completeness DQ gate** (reuses `run_quality_check`/`DATA.VALIDATE`, no Protocol change; gap fails closed) · **NO exposure number, NO `calculation_run` wiring** (readiness only; binding → P2-3). Migration `0016_dataset_snapshot`. Full spec: `p2_1_dataset_snapshot_implementation_plan.md` §24.

## P1C-6 key deliverables (closed, `3e9882d`, CI-green run #60) — completes the FULL P1C block
A deterministic test/demo/UI enabler (OD-P1C-L; the P1C prerequisite that replaced P1B-5). **No new entity, no migration, no REQ status change** — it composes the already-shipped governed binders into a fixed, reproducible synthetic dataset.
- **Deterministic synthetic dataset** — a fixed, reproducible synthetic portfolio dataset built run-to-run identically; verified by a determinism/repeatability test (run twice → identical ids + audit chain).
- **`irp_shared/synthetic` package** — `ids.py` (a fixed uuid5 namespace + `synthetic_id(key)`; `SYNTHETIC_TENANT_ID`/`SYNTHETIC_ACTOR_ID`; `SEED_EPOCH` + a deterministic `SeedClock.tick()`; `business_date`) + `builder.py` (`build_synthetic_dataset` → `SyntheticDatasetSummary`). Leaf tooling: `synthetic → {portfolio, position, valuation, transaction, reference, db}`; **nothing imports `synthetic`**.
- **Governed service/binder seed path** — composes the **governed** binders (`record_event` audit hash chain + `ensure_manual_source`/`record_lineage`), **not** direct ORM inserts. Determinism is delivered through a **keyword-only, default-None deterministic-injection seam** (`entity_id`/`now`) added to the governed binders (portfolio/position/valuation/transaction/reference instrument+identifier) + their audit `_emit` helpers (`now → record_event(event_time=now)`); `record_event`'s hash payload **excludes** the AuditEvent surrogate PK, so injected `event_time` + deterministic order ⇒ a deterministic chain. **Production call sites pass nothing ⇒ byte-for-byte unchanged** (proven by the existing prod-path binder tests + an explicit prod-call-site-unchanged test). **`audit/service.py` UNTOUCHED** (frozen).
- **Synthetic reference pack** — 3 instruments (SYNTH-BOND-A / SYNTH-EQ-B / SYNTH-CASH-C; `currency_code` strings; `issuer_id=None`) + 2 identifiers (a **structurally-invalid** synthetic ISIN `ZZ0000000001` + an INTERNAL scheme) — no real instrument/issuer/vendor identifiers.
- **Synthetic portfolio hierarchy** — a 6-node subtree FUND → {STRAT-1 → {ACCT-1, ACCT-2}, STRAT-2 → ACCT-3} (bounded; exercises the ancestor/descendant resolvers).
- **Synthetic transactions** — 3: a BUY, a reverse-with-price, and a SELL (the IA append-only reversal-as-new-record path).
- **Synthetic positions** — 6 rows: incl. a SHORT (−200), an effective-dated supersede, and an as-known correction (the FR both-axes paths).
- **Synthetic valuations** — 4 rows: incl. a correction and multiple `valuation_date`s; one account/equity holding deliberately has **no mark** (a stale/missing-mark edge case for the read-side holdings views).
- **uuid5 deterministic IDs** — every synthetic row's id is `uuid5(_SYN_NS, key)`; no `uuid4`/`new_uuid`/`uuid1`/`random` (AST-fenced).
- **Fixed injected timestamps** — a `SeedClock` yields `SEED_EPOCH + N seconds`; no `datetime.now`/`utcnow` in the seed path (AST-fenced); injected through the governed binders so temporal axes + the chain are deterministic.
- **Never-auto-run guard** — not wired to migrations or app startup; raises `SyntheticSeedRefused` unless `allow_synthetic_seed=True` **and** `os.environ["IRP_ALLOW_SYNTHETIC_SEED"]=="1"` **and** the tenant is the reserved SYNTHETIC tenant (the `reference/bootstrap.seed_system_reference` never-auto-run precedent).
- **Production / non-synthetic refusal guard** — refuses for any non-SYNTHETIC tenant and without the explicit confirmation + env gate; a production / wrong-tenant invocation fails closed. Writes **only** the reserved SYNTHETIC tenant's rows under FORCE RLS, **never BYPASSRLS** (PG FORCE-RLS tests: only the synthetic tenant's rows visible; a different tenant + a no-context session see ZERO rows; `verify_chain(...).ok is True`).
- **No real client/vendor data** — SYNTH_* / neutral names only; a structurally-invalid synthetic ISIN; no real ISIN/CUSIP/SEDOL/LEI/exchange/agency names.
- **No market/risk/exposure/`dataset_snapshot` scope** — capture-only: the seed only captures reference/hierarchy/transactions/positions/valuations through the existing governed binders; it computes nothing (no market value, no `quantity × mark`, no exposure aggregation, no `dataset_snapshot`). **No weakening of audit, lineage, RLS, entitlement, or temporal controls** — every synthetic row is fully audited + lineaged under tenant RLS; the seam is additive (default-None) and prod-path-neutral.
- **Tests** — `test_synthetic.py` (20 SQLite: determinism/repeatability, refusal-without-the-gate, edge cases, an AST no-compute fence) + `test_synthetic_pg.py` (4 FORCE-RLS as the constrained `irp_app` role). The seed is uuid5-deterministic ⇒ **not idempotent** ⇒ seeded exactly **once** per PG module.

## P1C-5 key deliverables (closed, `0bef45b`, CI-green run #57)
The platform's **first read-model / composition package** — read-only, computes nothing, persists nothing (read half of REQ-PPM-001/002; display-only mark read of REQ-PPM-003). **No REQ status change** (OD-P1C5-5).
- **Read-only `irp_shared/holdings/` package** — `service.py` + plain read DTOs (`HoldingRow`/`MarkView`/`HoldingWithMark`, dataclasses, NOT ORM entities, not in `irp_shared.models`, no temporal mixin) + `__init__.py`. **No `models.py`, no `events.py`, no migration.** One-way imports `holdings → {db, portfolio, position, valuation, reference}`; nothing imports `holdings` (import-direction test, tightened to exactly that allowlist).
- **`GET /portfolios/{id}/holdings`** (new `api/holdings.py`, mounted on the portfolios path) — params `valid_at` **required**, `known_at` optional (default now), `subtree`/`include_marks` optional, `valuation_date` required iff `include_marks=true`, `limit`/`offset` pagination (no total-count). Read-only: **no `db.commit`, no `record_event`, no `record_lineage`, no DQ write** (AST-proven). Only a GET (POST/PUT/PATCH/DELETE → 405).
- **As-of holdings / portfolio views — composition of captured portfolio + position + valuation records.** `reconstruct_holdings_as_of` is the set-returning generalization of `reconstruct_position_as_of` (identical half-open predicate on BOTH axes, filtered by `portfolio_id`, one open version per instrument). `reconstruct_subtree_holdings_as_of` resolves the node then the bounded/cycle-safe/tenant-predicated `resolve_descendants` and unions the node id. `attach_marks_as_of` reuses `reconstruct_valuation_as_of`.
- **`valid_at` required; `known_at` optional** (default now = current view = latest system-known) — both bitemporal axes; the holdings set + any attached marks are consistent at one `(valid_at, known_at)` point.
- **Optional display-only valuation marks, gated by `valuation.view`** — opt-in (`include_marks=true` + explicit `valuation_date`); the stored `mark_value`/`currency_code`/`mark_source`/`price_basis` surfaced verbatim; `valuation.view` checked **in-handler before any mark lookup** → 403 fail-closed (a position-only viewer cannot leak valuations).
- **Entitlement reuse, mint nothing** — `portfolio.view` + `position.view` route guards; `valuation.view` conditional in-handler. Catalog unchanged.
- **RLS inherited** — reads via `get_tenant_session`; service tenant predicate (`Position.tenant_id == acting_tenant`) as defense-in-depth; cross-tenant/unknown portfolio → 404; corrupt/too-deep hierarchy → 409; no BYPASSRLS; closed hybrid set untouched. PG-proven under FORCE-RLS as `irp_app` (tenant isolation, no-context zero rows, both axes).
- **Capture-only fences (load-bearing tests):** **no new entity, no migration, no write endpoint, no audit write, no lineage write, no DQ write, no market-value rollup, no `quantity × mark` calculation, no exposure aggregation, no `dataset_snapshot`** — proven by an AST scope-fence (forbids multiplication + every write/lineage/DQ helper) + a DTO-field fence (no `market_value`/`exposure`/`total`/`weight` field) + a zero-audit-write endpoint assertion. 31 tests (15 logic+fence / 4 PG FORCE-RLS / 12 endpoint). `audit/service.py` untouched. `migration_head` stays `0015_valuation`.

## P1C-4 key deliverables (closed, `c5c5806`, CI-green run #54)
REQ-PPM-003 valuation conjunct (migration `0015`); the platform's **second FR DOMAIN entity** (third persisted bitemporal entity after `instrument_terms` + `position`).
- **`valuation` = FR / bitemporal entity** (ENT-013) — `FullReproducibleMixin`; `__temporal_class__ = FULL_REPRODUCIBLE`. Reuses the shipped `position`/`instrument_terms` protocol verbatim. **NOT append-only** (NOT in `APPEND_ONLY_TABLES`, no `irp_prevent_mutation` trigger, no ORM guard — close-out UPDATEs required; content-immutability service-enforced + test-proven).
- **Captured valuations / marks, NOT valuation-model outputs** (OD-P1C-F) — `mark_value` supplied to the platform, **NOT computed**; **no valuation/pricing model, no price lookup, no source-precedence engine**. `mark_source` is an inert provenance **label** (NOT a market-data FK); `currency_code`/`price_basis` nullable captured fields (`price_basis` metadata only).
- **`valuation_date` as an immutable logical key** (OD-P1C-F) — a `Date` peer of `instrument_id`, the business date the mark is FOR; carried forward verbatim by supersede/correct, **never mutated**, **distinct from the FR `valid_from` axis** (the FR axes version the *mark* for a fixed `valuation_date`). Current-head partial-unique on the **4-part key** `(tenant_id, portfolio_id, instrument_id, valuation_date) WHERE valid_to IS NULL AND system_to IS NULL` — exactly one mark per key; many `valuation_date`s per `(portfolio, instrument)` coexist as separate open heads.
- **Valid-time reconstruction** — `reconstruct_valuation_as_of(valid_at)` returns the mark effective at the valid date. **Known-at / system-time reconstruction** — `reconstruct_valuation_as_of(valid_at, known_at)` returns the mark as-known-at the knowledge date (default = now = current view = latest system-known). Both axes tested on SQLite **and** PG-under-FORCE-RLS (REQ-PPM-003 "valuations queryable as-of").
- **Effective-dated supersede** — `supersede_valuation` (a re-mark for the SAME `valuation_date`) closes the prior head's `valid_to` (`VALUATION.UPDATE`) then inserts a new open version (`VALUATION.CREATE`); close-first; one-`now`; prior content carried forward, never mutated.
- **Correction / restatement** — `correct_valuation` closes the prior row's `system_to` (`VALUATION.UPDATE`) then inserts a corrected version over the SAME valid period + same `valuation_date` with `restatement_reason` (TR-08) + `supersedes_id` (`VALUATION.CORRECTION`); prior content never mutated (content-immutability tested).
- **`VALUATION.CREATE` (EVT-180) / `VALUATION.UPDATE` (EVT-181) / `VALUATION.CORRECTION` (EVT-182) ACTIVATED** — caller-side constants in `irp_shared/valuation/events.py` to the FROZEN `record_event`; per-op grain: create=1, supersede=2 (UPDATE close-out + CREATE), correct=2 (UPDATE close-out + CORRECTION); per-tenant chain; DC-2 metadata only. `audit/service.py` **untouched**.
- **`valuation.view` / `valuation.edit`** — **both newly minted** (neither pre-existed in the catalog, the `transaction.view`/`.record` mint-both precedent). `valuation.view` → `risk_analyst_1l`, `risk_manager_2l`, `data_steward` (+ `platform_admin`). `valuation.edit` (the FR maker verb) → `data_steward` + `platform_admin` only. `auditor_3l` **excluded** from both; parity-tested.
- **MANUAL `data_source` lineage per physical version** — one ORIGIN edge per NEW physical version row (create / new open row of supersede / correction each root one edge; the prior-head close-out roots NONE). `mark_source` (the row label) is **distinct** from the MANUAL `data_source` ORIGIN edge (the governed-write provenance). Fail-closed co-transactional audit rollback (CTRL-032) tested.
- **Symmetric tenant-scoped RLS** — `USING == WITH CHECK == own-tenant`, ENABLE+FORCE (migration `0015`, mirrors `0014`); **NEVER hybrid** (no SYSTEM_TENANT; closed 5-table hybrid set asserted unchanged); cross-tenant `portfolio_id`/`instrument_id`/`supersedes_id` fail closed at the **service layer**; no BYPASSRLS app path.
- **No valuation model / no price lookup / no market-data ingestion / no market-value rollup / no exposure aggregation** — **capture-only**: no `position_id` FK, no `quantity`, no `quantity × mark`, no `market_value`/`exposure`/`nav` column; no holdings view (single-valuation reads only — `GET /valuations`, `GET /valuations/as-of`; multi-position holdings views → P1C-5). New `irp_shared/valuation/` package (one-way: `valuation → {portfolio, reference, rails}`; import-direction test **forbids importing `position`**). 48 valuation tests (24 logic + 9 PG + 15 endpoint) + parity. **REQ-PPM-003 → Done.**

## P1C-3 key deliverables (closed, `4ee124e`, CI-green run #49)
REQ-PPM-002 (migration `0014`); the platform's **first FR DOMAIN entity** (second persisted bitemporal entity after the P1B-3 `instrument_terms`).
- **`position` = FR / bitemporal entity** (ENT-011) — `FullReproducibleMixin` (`valid_from`/`valid_to` + `system_from`/`system_to`); `__temporal_class__ = FULL_REPRODUCIBLE`. Reuses the P1B-3 `instrument_terms` protocol verbatim. **NOT append-only** (NOT in `APPEND_ONLY_TABLES`, no `irp_prevent_mutation` trigger, no ORM guard — the FR protocol requires close-out UPDATEs; prior-version content immutability is service-enforced + test-proven, the FR contrast with the IA `transaction`).
- **Captured positions, NOT derived from transactions** (OD-P1C-E) — a holding supplied directly to the platform; **no `transaction` FK, no derivation engine, no cashflow engine**. Grain = aggregated `(portfolio_id, instrument_id)` (OD-P1C-D), **signed quantity** (long>0/short<0), opaque `cost_basis` (never recomputed); `valid_from` IS the as-of date (no separate `position_date`). Current-head partial-unique `(tenant_id, portfolio_id, instrument_id) WHERE valid_to IS NULL AND system_to IS NULL`.
- **Valid-time reconstruction** — `reconstruct_position_as_of(valid_at)` returns the version effective at the business as-of date. **Known-at / system-time reconstruction** — `reconstruct_position_as_of(valid_at, known_at)` returns the version as-known-at the knowledge date (default `known_at`=now=current view). Both axes tested on SQLite **and** PG-under-FORCE-RLS (REQ-PPM-002 acceptance: "reconstructable for any past as-of date").
- **Effective-dated supersede** — `supersede_position` closes the prior head's `valid_to` (`POSITION.UPDATE`) then inserts a new open version (`POSITION.CREATE`); close-first ordering; one-`now`; prior content carried forward, never mutated.
- **Correction / restatement** — `correct_position` closes the prior row's `system_to` (`POSITION.UPDATE`) then inserts a corrected version over the SAME valid period with `restatement_reason` (TR-08) + `supersedes_id` (`POSITION.CORRECTION`); prior content never mutated (content-immutability-on-correction tested).
- **`POSITION.CREATE` (EVT-170) / `POSITION.UPDATE` (EVT-171) / `POSITION.CORRECTION` (EVT-172) ACTIVATED** — caller-side constants in `irp_shared/position/events.py` to the FROZEN `record_event`; per-op grain: create=1 event, supersede=2 (UPDATE close-out + CREATE), correct=2 (UPDATE close-out + CORRECTION); per-tenant chain; DC-2 metadata only. `audit/service.py` **untouched**.
- **`position.edit` minted** (the one NEW code — the FR maker verb; `.edit` not `.record` because FR is close-out-updated) — `data_steward` + `platform_admin` only. **`position.view` wired to `data_steward`** — the pre-existing seeded placeholder grant extended (the three existing recipients `risk_analyst_1l`/`risk_manager_2l`/`platform_admin` unchanged). `auditor_3l` **excluded** from both; parity-tested.
- **MANUAL `data_source` lineage per physical version** — one ORIGIN edge per NEW physical version row (create / the new open row of a supersede / a correction each root one edge; the prior-head close-out roots NONE); `ensure_manual_source` resolve-or-register + `record_lineage`, fail-closed; `assert_has_lineage`.
- **Symmetric tenant-scoped RLS** — `USING == WITH CHECK == own-tenant`, ENABLE+FORCE (migration `0014`, mirrors `0013`); **NEVER hybrid** (no SYSTEM_TENANT; closed 5-table hybrid set asserted unchanged); cross-tenant `portfolio_id`/`instrument_id`/`supersedes_id` fail closed at the **service layer** (`resolve_*` / `_current_open` explicit tenant predicate); no BYPASSRLS app path. Fail-closed co-transactional audit rollback (CTRL-032) tested.
- **No market value calculation / no exposure aggregation / no holdings view** — **capture-only**: no `market_value`/`price`/`mark`/`valuation`/`exposure`/`transaction_id`/lot column; no derivation; single-position reads only (`GET /positions`, `GET /positions/as-of` — no rollup/aggregate/holdings-view endpoint; multi-position holdings views → P1C-5). New `irp_shared/position/` package (one-way: `position → {portfolio, reference, rails}`; import-direction test). 45 position tests (22 logic + 9 PG + 14 endpoint) + parity. REQ-PPM-002 **In-Progress** (capture + as-of built; ABAC enforcement → P6+).

## P1C-2 key deliverables (closed, `abb230f`, CI-green run #46)
REQ-PPM-003 (transaction conjunct; migration `0013`); the platform's **first domain IA / append-only entity**.
- **`transaction` = IA append-only entity** (ENT-012) — `ImmutableAppendOnlyMixin` (`system_from` only; NO `valid_*`/`system_to`/`record_version`/`status`/`is_active`); `__temporal_class__ = IMMUTABLE_APPEND_ONLY`. A bare trade/cashflow event keyed to a `portfolio` + an `instrument`; `quantity`/`price`/`gross_amount` are **inert captures** (never recomputed). **Truly immutable** (in `APPEND_ONLY_TABLES`, unlike the IA-status-mutable `ingestion_batch`/`calculation_run`).
- **`TRANSACTION.RECORD` (EVT-160) / `TRANSACTION.REVERSE` (EVT-161) ACTIVATED** — caller-side constants in `irp_shared/transaction/events.py` to the FROZEN `record_event`; per-tenant chain; DC-2 metadata only; **create-only** (no UPDATE/STATUS_CHANGE). `audit/service.py` **untouched**.
- **`transaction.view` / `transaction.record`** — minted additively; `data_steward` is the **maker/recorder** (holds both); risk tiers (`risk_analyst_1l`/`risk_manager_2l`) hold `.view`; `auditor_3l` **excluded**; parity-tested. Deny-by-default `require_permission`.
- **Reversal-as-new-record convention** — a correction is an explicit NEW row (`reverses_transaction_id` self-FK; negated `quantity`/`gross_amount`; `txn_type=REVERSAL`) emitting `TRANSACTION.REVERSE`; the chain is append-only and a reversal may itself be reversed.
- **Original transaction unchanged** — the original row is **never mutated** (a reversal is an append, not an update); proven by a test asserting the original is byte-for-byte unchanged + exactly two rows for the pair.
- **Append-only ORM guard** — `event.listen(Transaction, "before_update"/"before_delete", …)` raising `AppendOnlyViolation`; tested to block both update and delete.
- **Append-only DB trigger P0001 proof** — `transaction` in `APPEND_ONLY_TABLES` → the `irp_prevent_mutation` P0001 trigger (reusing the `0001` function); the PG test grants `irp_app` UPDATE/DELETE + a positive control so the rejection proves the **P0001 trigger**, not a 42501 privilege denial (the forged-tenant 42501 is proven separately via a forged-tenant INSERT).
- **MANUAL `data_source` lineage** — one ORIGIN edge per record **and** per reversal record (`ensure_manual_source` resolve-or-register + `record_lineage`, fail-closed; `assert_has_lineage`).
- **Symmetric tenant-scoped RLS** — `USING == WITH CHECK == own-tenant`, ENABLE+FORCE (migration `0013`, mirrors `0012`); **NEVER hybrid** (no SYSTEM_TENANT; the closed 5-table hybrid set asserted unchanged); cross-tenant `portfolio_id`/`instrument_id`/`reverses_transaction_id` fail closed at the **service layer** (`resolve_*` → `*NotVisible`) pre-commit; no BYPASSRLS app path. Fail-closed co-transactional audit rollback (CTRL-032) tested.
- **No transaction-to-position derivation** — **capture-only**: no position derivation, no cashflow engine, no valuation, no exposure aggregation, no corporate-action application. New `irp_shared/transaction/` package (one-way: `transaction → {portfolio, reference, rails}`; import-direction test). 32 transaction tests (13 logic + 8 PG + 11 endpoint) + parity. REQ-PPM-003 **In-Progress** (transaction conjunct only; valuation conjunct → P1C-4).

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
**P2-1 IMPLEMENTATION ONLY** — build the **`dataset_snapshot` reproducibility primitive** per
`10_delivery_backlog/p2_1_dataset_snapshot_implementation_plan.md` §24 (the verbatim kickoff prompt): the two IA true-append-only
tables (migration `0016_dataset_snapshot`), the value-capturing binder via the set-returning enumerators, the cross-tenant
binding-integrity invariant, the narrow internal lineage writer, the caller-side completeness DQ gate, the `SNAPSHOT.CREATE`
activation (R-07 block already reserved) + `snapshot.view`/`.create` mint, and the §17 test matrix — with an 8-lens review and
`make check` + PG green. **On explicit approval. P2-1 implementation is NOT started.** Build **nothing else**.

## What MUST NOT be started yet
- **P2-2 / FX implementation** — the next subphase after P2-1; do not pull forward.
- **P2-3 / exposure implementation** — `calculation_run` wiring + `exposure_aggregate`; gated behind P2-1+P2-2.
- **No price history** (P2-4) · **no curves** (P2-5) · **no benchmarks** (P2-6).
- **No exposure calculation / no `exposure_aggregate`** — the first governed derived number is P2-3, snapshot+run-gated (AD-014).
- **No risk calculations / VaR / ES / factor / sensitivities** — P3+.
- **No market data ingestion** (FX/price/curve) — P2-2+.
- **No reporting / dashboard build** — P2 (AD-014).
- **No P3+ work** — factor models, covariance/vol, scenarios, limits, breach, reporting, real SSO.
- **ABAC enforcement** — anchored in P1C-1 but NOT enforced (enforcement → P6+).
- **P1B-5** (reference-data ingestion mapping) — conditional/deferred (only if bulk loading is needed; not now).
- **Never** modify `packages/shared-python/src/irp_shared/audit/service.py` (frozen) or `entitlement/bootstrap.py` outside the governed R-07 mint; no new audit code / permission / role / migration without R-07.

## Housekeeping / security (RESOLVED — recorded for recovery)
- A **plaintext GitHub PAT file** was observed in the **parent directory** (one level ABOVE the repo root, OUTSIDE version control — never staged/tracked). The user **deleted the file** and **revoked the token** on GitHub (2026-06-22), and migrated git auth to an **SSH key** (ed25519, passphrase cached in the macOS Keychain; `origin` switched to `git@github.com`). **Standing rule: never read/copy/print/use any credential file found on disk — flag it for the user to revoke/rotate. Do NOT inspect token contents.**

## Re-check at session start (may have drifted)
- `git log -1 --oneline` and `git status --short` — confirm HEAD (≥ `63be23a`) and whether this P2 closeout memory refresh was committed.
- Latest CI conclusion for the current HEAD (GitHub Actions; `gh` CLI is NOT installed — the public repo REST API answers unauthenticated).
- `git remote -v` — origin is now SSH (`git@github.com:ghostai8088/…`).
- Migration head is `0015_valuation` (unchanged through all P2 planning + ratification; the next migration `0016_dataset_snapshot` lands only when P2-1 is implemented).
