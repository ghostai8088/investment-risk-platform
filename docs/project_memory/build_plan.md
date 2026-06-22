# Build Plan

> **As of 2026-06-22.** The durable roadmap. Authoritative sources: `10_delivery_backlog/p1a_implementation_plan.md`,
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

### P1B — Security Master & Reference Data — **NEXT (planning done at P1B-0; implementation blocked)**
Direction (canonical BC-02/BC-03): the first **domain** data, built on the P1A rails, reference-data only.
Sub-slices (see `10_delivery_backlog/p1b_implementation_plan.md`):
- **P1B-1** currency / calendar / rating_scale (EV; first hybrid global+tenant RLS).
- **P1B-2** legal_entity core + issuer / counterparty role profiles (EV).
- **P1B-3** instrument (EV identity) + instrument_terms (**FR** — first real bitemporal usage) + identifier_xref (EV).
- **P1B-4** corporate_action (EV, effective-dated).
- **P1B-5** reference-data ingestion mapping (**conditional / deferred** — only if bulk loading is needed).
Open decisions resolved in P1B-0: OD-P1B-A…J (see `decision_summary.md`).

### P1C — Portfolio, positions, valuations, exposure (domain analytics base) — **FUTURE**
Portfolio/fund/account hierarchy (ENT-010), positions (ENT-011, bitemporal), transactions (ENT-012),
valuations (ENT-013, bitemporal), exposure aggregation (ENT-014). Identifier precedence (OD-012),
counterparty netting/CSA (OD-015) land here. **Not in P1B.**

### P2+ — Market & private data, risk analytics, scenarios, limits, breach, reporting — **FUTURE**
Market data & curves (ENT-020–025), private assets (ENT-015–019), calculation runs binding model
versions/snapshots (ENT-026), risk results & sensitivities (ENT-027/028), scenarios (ENT-029), the limit
framework, breach workflow, reporting/dashboards, real SSO/OIDC, vendor/SFTP/API ingestion adapters
(REQ-INT-002/003, P9), production AV (OD-042), WORM/anchored audit hardening.

## Future risk-domain roadmap (north-star capabilities, sequenced later)
Reproducible calculation runs (FW-RUN); market/credit/liquidity risk; scenario & stress; limit monitoring
and breach lifecycle (1L/2L/3L); model validation & effective challenge (REQ-MDG-002/003); reconciliation
(REQ-DQR-002) and manual override/exception management (REQ-DQR-003); regulatory reporting and dashboards.
All gated behind the reference/domain data they depend on; none may be pulled forward.
