# Build Plan

> **As of 2026-06-26.** The durable roadmap. Authoritative sources: `10_delivery_backlog/p1a_implementation_plan.md`,
> the per-slice plans, `02_requirements/requirements_backbone.md`, `04_data_model/canonical_data_model_standard.md`.

## North star
A **full-scope enterprise investment-risk platform** — multi-tenant, auditable, reproducible, governed —
**not an MVP or POC**. Every slice is built to enterprise standards from the first commit: tenant isolation
(RLS), co-transactional fail-closed audit with a hash chain, lineage on every governed write, selective
bitemporality, deny-by-default entitlements, and CI that enforces the ratified standards. Scope is delivered
in thin, reviewed, independently green slices — depth and governance are never traded for speed.

## Delivery method (every slice)
UltraCode planning workflow → committed plan doc → implementation → multi-lens adversarial review → fix
in-scope findings → `make check` → **commit only on explicit approval** → watch CI to green. See
`claude_operating_instructions.md`.

## Phase roadmap

### P0.5 — Engineering hygiene & foundation hardening — **DONE**
Monorepo scaffold; the frozen audit framework (`record_event`, hash chain, `verify_chain`); the RLS
foundation (migration `0001`); entitlement seed; CI (lint/format/typecheck/test + Postgres migration job +
secret-scan + docs-check). Establishes BR-rules, AD-decisions, the canonical data model, and the control matrix.

### P1A — Cross-cutting rails (the foundation every domain slice reuses) — **DONE / CLOSED**
- **P1A-0 Tenant context / RLS** — `set_config` tenant context, FORCE RLS + USING/WITH CHECK, constrained `irp_app` PG-test role, `irp_ops` BYPASSRLS ops role.
- **P1A-1 Data source + lineage** — `data_source` (EV) + `lineage_edge` (IA); `record_lineage` / `assert_has_lineage`.
- **P1A-2 Model registry** — `model` (EV) + `model_version`/assumption/limitation (IA); inventory + BR-3 gate.
- **P1A-3 Data quality** — `data_quality_rule` (EV) + `data_quality_result` (IA); generic `not_null`/`allowed_values`; no-silent-failure; `run_quality_check` / `assert_passed_quality_checks`.
- **P1A-4 Generic ingestion staging** — `ingestion_batch` (IA status-mutable) + `ingestion_staged_record` (IA immutable); CSV anti-corruption; composes lineage + DQ + audit; durable-evidence-on-reject.

### P1A rails now reusable by all downstream phases
Tenant context/RLS · audit + hash chain · entitlements · data_source · lineage · model registry · data
quality · generic ingestion staging · temporal mixins (EV/IA/FR) · Alembic migration + drift gate ·
constrained-role PG RLS tests · append-only trigger tests. (Full inventory: `10_delivery_backlog/p1a_closeout_p1b_readiness.md` Part 2.)

### P1B — Security Master & Reference Data — **DELIVERED (P1B-1..P1B-4 done & CI-green; P1B-5 conditional/deferred; closeout + P1C-0 ratification done; P1C-1..P1C-6 CLOSED → FULL P1C block DELIVERED; REQ-PPM-003 Done)**
Direction (canonical BC-02/BC-03): the first **domain** data, built on the P1A rails, reference-data only.
Sub-slices (see `10_delivery_backlog/p1b_implementation_plan.md`):
- **P1B-1** currency / calendar / rating_scale (EV; first hybrid global+tenant RLS) — **DONE / CLOSED (`6568cb1`, CI-green).** First asymmetric hybrid RLS (AD-013-R1); `REFERENCE.CREATE`/`UPDATE`; SYSTEM_TENANT global-read; app-layer tenant-wins dedup; MANUAL-`data_source` lineage; `irp_shared.reference` package.
- **P1B-2** legal_entity core + issuer / counterparty role profiles (EV) — **DONE / CLOSED (`32c7778`, CI-green, 7-lens reviewed).** `legal_entity` implementation-only (no ENT id); separate 1:1 role profiles; tenant-scoped SYMMETRIC RLS, **NEVER hybrid** (the proprietary-never-hybrid evidence); LEI partial-unique; hierarchy structure + bounded ultimate-parent resolver (rollup calc deferred).
- **P1B-3** instrument (EV identity) + instrument_terms (**FR** — first real bitemporal usage) + identifier_xref (EV) — **DONE / CLOSED (`8545ed6`, CI-green, 8-lens reviewed).** First persisted FR/bitemporal entity (create/supersede/correct + both-axes `reconstruct_terms_as_of`); `REFERENCE.CORRECTION` (EVT-142) activated for restatement; deterministic single-result-or-ambiguity identifier resolution (OD-P1B-G); precedence/external-validation deferred (OD-012 → P1C).
- **P1B-4** corporate_action (EV, effective-dated) — **DONE / CLOSED (`060b2a4`, CI-green, 8-lens reviewed).** Capture-only reference entity; single status lifecycle (ANNOUNCED→CONFIRMED→CANCELLED); `REFERENCE.STATUS_CHANGE` (EVT-143) activated (first use); `instrument_id` NOT-NULL FK; NO application-to-positions / valuation-adjustment / event-engine / roll math (OD-P1B-B).
- **P1B-5** reference-data ingestion mapping (**conditional / deferred** — only if bulk loading is needed; not now).
Open decisions resolved in P1B-0: OD-P1B-A…J — **all REALIZED P1B-1..P1B-4** (see `decision_summary.md`).
**Next (DONE): P1B closeout / P1C readiness (`e99633a`); P1C-0 decision record + plan (`705d3ba`) + ratification (`dca7bc0`, AD-017).**

### P1C — Portfolio, positions, valuations, exposure (domain analytics base) — **DELIVERED (capture-only, AD-017; P1C-1…P1C-6 CLOSED & CI-green)**
Direction (canonical BC-01): the first **domain** data. Capture + as-of reconstruction only — NO exposure aggregation /
risk / pricing / valuation models / corporate-action application / dataset_snapshot (deferred to P2, AD-014/AD-017).
**P1C closeout + P2 planning + governance ratification are DONE (see the P2 section below); next: P2-1 `dataset_snapshot` IMPLEMENTATION ONLY (migration `0016`), on explicit approval.**
Sub-slices (see `10_delivery_backlog/p1c_implementation_plan.md`):
- **P1C-0** decision record + plan + ratification — **DONE** (`705d3ba` + `dca7bc0`): the twelve P1C decisions; **AD-017** (P1C capture-only stance); OD-013/OD-025 closed; OD-012/OD-015 re-targeted.
- **P1C-1** portfolio / fund / strategy / account hierarchy + ABAC scope anchor (ENT-010, **EV**) — **DONE / CLOSED (`bb89c74`, CI-green run #43, 8-lens reviewed).** The platform's **first domain entity**: single `portfolio` EV table; bounded ancestor + **NEW** descendant resolvers; **ABAC anchor-not-enforce** (P6+); `PORTFOLIO.CREATE`/`UPDATE` (EVT-150/151) activated; symmetric RLS; fail-closed rollback; new `irp_shared/portfolio/` package.
- **P1C-2** transactions (ENT-012, **IA append-only**) — **DONE / CLOSED (`abb230f`, CI-green run #46, 8-lens reviewed, 0 block).** The platform's **first domain IA / append-only entity**: capture-only trade/cashflow log; two-layer append-only (P0001 trigger + ORM guard); reversal-as-new-record (original never mutated); `TRANSACTION.RECORD`/`REVERSE` (EVT-160/161) activated; `transaction.view`/`record` minted (`data_steward` maker; `auditor_3l` excluded); symmetric RLS; MANUAL-source lineage; new `irp_shared/transaction/` package; **NO transaction-to-position derivation**.
- **P1C-3** positions (ENT-011, **FR** bitemporal — reuse the P1B-3 `instrument_terms` protocol; captured directly, NOT derived from transactions) — **DONE / CLOSED (`4ee124e`, CI-green run #49, 8-lens reviewed, 0 block).** The platform's **first FR domain entity**: `position` FR captured holdings master; both-axes as-of reconstruction; NOT append-only (close-out UPDATEs allowed; content-immutability service-enforced); `POSITION.CREATE`/`UPDATE`/`CORRECTION` (EVT-170/171/172) activated; `position.edit` minted + `position.view` wired to `data_steward` (`auditor_3l` excluded); symmetric RLS; MANUAL-source lineage per version; new `irp_shared/position/` package; **NO market value / exposure aggregation / holdings view**.
- **P1C-4** valuations (ENT-013, **FR** bitemporal — captured marks; reuse the `position`/`instrument_terms` protocol; NOT computed by a valuation model) — **DONE / CLOSED (`c5c5806`, CI-green run #54, 8-lens reviewed, 0 block).** The platform's **second FR domain entity**: `valuation` FR captured mark history; `valuation_date` an immutable logical-key (4-part current-head key); both-axes as-of; NOT append-only; `VALUATION.CREATE`/`UPDATE`/`CORRECTION` (EVT-180/181/182) activated; both `valuation.view`/`valuation.edit` minted (`data_steward` maker; `auditor_3l` excluded); symmetric RLS; new `irp_shared/valuation/` package (no `position` import); **NO valuation model / price lookup / market-value rollup / exposure aggregation**. **REQ-PPM-003 → Done** (both conjuncts).
- **P1C-5** as-of holdings / portfolio views (read-only, composed from captured position + valuation via `reconstruct_*_as_of`; no aggregation, no new entity) — **DONE / CLOSED (`0bef45b`, CI-green run #57, 8-lens reviewed, 0 block).** The platform's **first read-model / composition package**: read-only `irp_shared/holdings/` + `GET /portfolios/{id}/holdings` reconstructs the as-of holdings SET by composing the captured `portfolio` + `position` FR + (optional, display-only) `valuation` FR reads; `reconstruct_holdings_as_of` (set-generalized) / `reconstruct_subtree_holdings_as_of` (bounded subtree composition, not ABAC enforcement) / `attach_marks_as_of`; `portfolio.view`+`position.view` route guards, `valuation.view` in-handler→403; **NO entity / migration / write endpoint / permission / audit / lineage / DQ write; NO aggregation / market-value / `quantity × mark` / exposure / `dataset_snapshot`**. `migration_head` stays `0015_valuation`. **No REQ status change.**
- **P1C-6** deterministic synthetic dataset (synthetic reference seed pack + portfolio hierarchy + transactions/positions/valuations; `uuid5` IDs + fixed timestamps; labeled never-auto-run seed module; no real/sensitive data) — **DONE / CLOSED (`3e9882d`, CI-green run #60, 8-lens reviewed).** New `irp_shared/synthetic/` package seeded through the **governed** binders via a keyword-only default-None deterministic-injection seam (production call sites byte-for-byte unchanged); NEVER-AUTO-RUN + production/non-synthetic refusal guard; SYNTHETIC tenant under FORCE RLS, never BYPASSRLS; NO entity/migration/real-data/market/risk/exposure/`dataset_snapshot`. **Completes the FULL P1C block.** **DONE next:** the **P1C closeout / P2 readiness review** (`7070dff`, #62) → **P2 planning + governance ratification** (below).
Exposure aggregation (ENT-014, REQ-PPM-004) stays **P2** (AD-014, now **In-Progress**). Identifier precedence (OD-012) and counterparty netting/CSA (OD-015) re-targeted beyond P1C.

### P2 — Reproducibility foundation, market & private data, risk analytics — **PLANNED + RATIFIED (P2-1 build next)**
**Reproducibility-first** sequencing (chosen at the P1C closeout / readiness review): **P2-1 `dataset_snapshot` → P2-2 FX → P2-3 `calculation_run` + basic exposure → P2-4 price history → P2-5 curves → P2-6 benchmark**. The AD-014-gated first governed derived number (exposure) needs only positions+valuations(+FX), so the **reproducibility primitive lands before any market-data history** (the P3 factor-model on-ramp).
- **P2-0** decision record + implementation plan — **DONE / COMMITTED (`2d19992`, #63; 8-lens, 0 block).** OD-P2-A…L; the reproducibility-first subphase structure.
- **P2-1** `dataset_snapshot` implementation plan — **PLAN DONE (`d7be981`, #64; 8-lens, 0 block).** The AD-014 reproducible input snapshot (IA true-append-only header + per-input physical-version-pin component + `captured_content` + canonical hash; cross-tenant binding invariant; narrow internal lineage writer; caller-side completeness DQ gate; `calculation_run` readiness, no wiring).
- **P2 governance ratification** — **RATIFIED (`63be23a`, #65; 7-lens, 7× approve).** ENT-049/050 + SNAPSHOT.CREATE (EVT-190 reserved) + snapshot.* (reserved) + **AD-004-R1** (Postgres-first; OD-014 resolved) + REQ-PPM-004→In-Progress, into the source-of-truth — RESERVED/PLANNED, **no code**.
- **NEXT: P2-1 IMPLEMENTATION** (the `dataset_snapshot` primitive; migration `0016`), on explicit approval. Then P2-2…P2-6, then P3+.
**Still FUTURE (each separately planned + approved):** private assets (ENT-015–019), risk results & sensitivities (ENT-027/028), scenarios (ENT-029), the limit framework, breach workflow, reporting/dashboards, real SSO/OIDC, vendor/SFTP/API ingestion adapters (REQ-INT-002/003, P9), production AV (OD-042), WORM/anchored audit hardening.

## Future risk-domain roadmap (north-star capabilities, sequenced later)
Reproducible calculation runs (FW-RUN); market/credit/liquidity risk; scenario & stress; limit monitoring
and breach lifecycle (1L/2L/3L); model validation & effective challenge (REQ-MDG-002/003); reconciliation
(REQ-DQR-002) and manual override/exception management (REQ-DQR-003); regulatory reporting and dashboards.
All gated behind the reference/domain data they depend on; none may be pulled forward.
