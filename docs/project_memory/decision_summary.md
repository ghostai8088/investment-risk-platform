# Decision Summary

> **As of 2026-06-22.** Ratified and load-bearing decisions. **Do not relitigate the "Ratified" items unless
> the user explicitly reopens them.** Authoritative sources: `11_decision_log/architecture_decision_log.md`
> (AD-*), the per-slice plan docs, and `10_delivery_backlog/p1b0_decision_record.md` (OD-P1B-*).

## Major ratified architecture decisions (AD-*, Accepted by H-04)
- **AD-004** segregated/append-only audit store; native uuid + JSONB on Postgres.
- **AD-005** **selective bitemporality**: **FR** (bitemporal) for risk-driving inputs, **IA** (immutable append-only) for outputs/events/audit, **EV** (effective-dated) for reference/config. Risk = entity misclassification.
- **AD-007** real identity via OIDC/SSO (deferred; dev header shim is not a security boundary).
- **AD-008 / BR-17** tenant isolation; investment data MNPI-adjacent → isolation by default.
- **AD-013** **hybrid reference-data tenancy**: global system reference shared read-only; investment reference tenant-scoped; tenant-override pattern; no cross-tenant proprietary sharing. (P1B-0 **ratifies** refinement **AD-013-R1** — Accepted (H-04), in the decision log — see below.)
- **AD-015 / AD-016** RLS tenant context via `set_config`; BYPASSRLS reserved to the ops role.
- **BR-3** inventoried-before-use (models); **BR-7** override fields; **BR-10** no secrets in source; **BR-11** deny-by-default; **BR-12** non-bypassable audit; **BR-13** lineage; **BR-16** AI-agent logging; **BR-19** declare `__temporal_class__`.

## P1A-0 decisions (tenant context / RLS)
- Tenant context set via `set_config('app.current_tenant', …, true)` — **never** a parameterized `SET`.
- FORCE ROW LEVEL SECURITY + policy with `USING` **and explicit `WITH CHECK`** (the explicit WITH CHECK pattern is from migration `0004`+; the `0001` foundation tables are `USING`-only).
- PG RLS tests run under a constrained **non-superuser `irp_app`** role (NOSUPERUSER NOBYPASSRLS) — superusers bypass RLS even under FORCE.
- Durable pool-checkin `RESET`; single-transaction-per-request invariant (no mid-request commit, or RLS fails closed). Dev `X-User-Id`/`X-Tenant-Id` header shim is **not** a security boundary until SSO (DR-P1A0-3).

## P1A design decisions (per slice)
- **P1A-1:** `data_source` EV + `lineage_edge` IA; polymorphic `(target_entity_type, target_entity_id)`, **no domain FK**; `record_lineage` is co-transactional, server-stamps tenant, fails closed on cross-tenant source; lineage edges are metadata of an already-audited governed write (no per-edge audit event). Audit codes `DATA.SOURCE_REGISTER/UPDATE`.
- **P1A-2:** `model` EV + `model_version`/assumption/limitation IA; reuse `MODEL.REGISTER`/`MODEL.VERSION`; `register`-as-maker preserves SoD (developer ≠ validator). DR-P1-3 maker-checker hooks reserved, non-enforcing.
- **P1A-3:** `data_quality_rule` EV + `data_quality_result` IA; **exactly two generic evaluators** (`not_null`, `allowed_values`) — extend by value + registry entry, never schema. **No-silent-failure** (ERROR raises + persists flag; WARNING flags-only; evaluator error propagates + audited `outcome='failure'`). `assert_passed_quality_checks` is the fail-closed gate. Audit `DATA.VALIDATE` (runs) + `DATA.DQ_RULE_DEFINE/UPDATE`.
- **P1A-4:** `ingestion_batch` **IA-classed but status-mutable** (the CalculationRun precedent — NOT in `APPEND_ONLY_TABLES`); `ingestion_staged_record` IA immutable (in `APPEND_ONLY_TABLES` + ORM guard + P0001 trigger). CSV anti-corruption: 10 MiB cap counted while reading, CSV-only allowlist, filename sanitization, encoding validation, formula-injection neutralization, ragged-row rejection, no-op AV seam (`scan_status`, OD-042). Composes P1A-1 lineage + P1A-3 DQ; **durable-evidence-on-reject** (REJECTED batch + flagged result + audit committed; 4xx, never 200). Activates `DATA.INGEST`; reuses `data.upload` (no new audit code, no new permission). `data_quality_result.ingestion_batch_id` populated via an additive `run_quality_check` kwarg (set-before-flush; the only P1A-3 service change).

## P1B open decisions resolved in P1B-0 (OD-P1B-A … OD-P1B-J)
Recorded in `10_delivery_backlog/p1b0_decision_record.md` (**committed at `dbed93e`**, CI-green; 7-lens reviewed).
**Ratifications COMMITTED into the governance source-of-truth at `4fae26b`** (CI-green): **AD-013-R1**
(decision log); **REQ-SMR-005** + REQ-SMR-001/003/004 annotations + CAP-2.5 re-partition (backbone/RTM/capability
map); ENT-001..008 annotations (canonical model + temporal §2A); **`REFERENCE.*`** reserved (audit
taxonomy); reference permissions (entitlement model). Audit codes + entitlement bootstrap **code** are minted in
the P1B build slices (currency/calendar/rating_scale codes + perms landed in P1B-1). Summary of the resolutions:
- **OD-P1B-A** Instrument split: `instrument` = **EV** identity + `instrument_terms` = **FR** (per AD-005 §2A / REQ-SMR-001). Canonical annotation (ENT-001 realized as two tables).
- **OD-P1B-B** `corporate_action` = **EV** (AD-005 §2A / REQ-SMR-004); status history via audit trail.
- **OD-P1B-C** Hybrid tenancy via **SYSTEM_TENANT rows + asymmetric RLS** (`USING own OR SYSTEM` / `WITH CHECK` single-tenant); closed hybrid set = **{currency, calendar, rating_scale}**; proprietary entities never hybrid; override-wins is application-layer. **Refinement ADR AD-013-R1** (R-04/R-05/H-04).
- **OD-P1B-D** Shared `legal_entity` **core (implementation-only, no ENT id)** + separate `issuer`/`counterparty` role profiles (preserves canonical ENT-002/003).
- **OD-P1B-E** New **`REFERENCE`** audit category (EVT-140 block: `CREATE/UPDATE/CORRECTION/STATUS_CHANGE`); reconciled vs reserved `DATA.CORRECTION` / TR-08. R-07.
- **OD-P1B-F** Add `currency`/`rating_scale`/`legal_entity` + missing `.view` permissions; reserve `reference.rating.*`. R-07.
- **OD-P1B-G** Deterministic single-result-or-`AmbiguousIdentifier` resolution; partial-unique index `(tenant_id, scheme, value) WHERE valid_to IS NULL`; cross-vendor precedence deferred (OD-012 → P1C; REQ-SMR-003 partial).
- **OD-P1B-H** New web-framework-free `irp_shared.reference` package; one-way deps (→ lineage/dq/audit/entitlement only; no risk/portfolio/ingestion-mapping/reporting in the CRUD core).
- **OD-P1B-I** Per-tenant `MANUAL` `data_source`; lineage **rooted in each row's own context** (SYSTEM-context for global rows) — `data_source` is **not** made hybrid.
- **OD-P1B-J** Mint **REQ-SMR-005** (currency, rating_scale) + re-partition CAP sub-cap 2.5 + annotate ENT-007 EV/FR. R-02/R-05.

## P1B-1 design decisions (REALIZED — `6568cb1`, CI-green)
The first reference-data slice and the platform's first hybrid-tenancy / asymmetric-RLS evidence (AD-013-R1).
- **Five EV tables** (mig `0008`): `currency` (ENT-005), `calendar`+`calendar_holiday` (ENT-006), `rating_scale`+`rating_grade` (ENT-007 **taxonomy only** — zero assignment columns; FR rating assignments deferred). `UNIQUE(tenant_id, code)`, **never `UNIQUE(code)`**; no append-only trigger (all EV-mutable — a `REFERENCE.UPDATE` succeeds at the DB).
- **Asymmetric hybrid RLS** (net-new, distinct from the symmetric loop): `USING (own-tenant OR SYSTEM_TENANT) / WITH CHECK (own-tenant only)`. The SYSTEM literal is in `USING`/`qual` but **never** in `WITH CHECK` (a tenant overwriting global vocab = cross-tenant breach); FORCE RLS + own policy on every table **including children**; closed hybrid set = exactly these 5 (`data_source` stays symmetric — NOT hybrid). SYSTEM_TENANT_ID injected as a fixed literal from `entitlement.bootstrap`.
- **Tenant override wins = APPLICATION-LAYER dedup** (`service.dedupe_tenant_wins`, DISTINCT-ON-by-`code`, own-tenant preferred) — NOT an RLS merge.
- **`REFERENCE.CREATE` (EVT-140) / `REFERENCE.UPDATE` (EVT-141) activated** as caller constants to the FROZEN `record_event`; children fold into the parent event (no own event); DC-2 metadata only; per-tenant + SYSTEM chains. `CORRECTION`/`STATUS_CHANGE` reserved, not emitted.
- **Lineage** (OD-P1B-I): one ORIGIN edge per entity from a per-tenant **MANUAL** `data_source` (`ensure_manual_source`, idempotent); SYSTEM seeds rooted on the SYSTEM chain. New web-framework-free **`irp_shared.reference`** package (one-way deps). Additive `reference.currency.*` / `reference.rating_scale.*` / `reference.calendar.view` perms seeded via the existing `0002` catalog path (no new audit framework code). Governed SYSTEM seeder is test-proven (not yet wired to prod).

## P1B-2 design decisions (REALIZED — `32c7778`, CI-green; 7-lens reviewed)
REQ-SMR-002 (OD-P1B-D); migration `0009`. The contrast with P1B-1: these are **PROPRIETARY** entities, so they are the inverse of P1B-1's hybrid model.
- **Shared `legal_entity` core, IMPLEMENTATION-ONLY (NO canonical ENT id)** (OD-P1B-D) + **separate 1:1 `issuer` (ENT-002) / `counterparty` (ENT-003) role profiles** (`UNIQUE(tenant_id, legal_entity_id)`, NOT-NULL FK; a legal entity may carry both). The unified-table-with-role-flags alternative is REJECTED. All three **EV** (one physical row per logical entity).
- **Tenant-scoped SYMMETRIC RLS — NEVER hybrid / NEVER SYSTEM_TENANT** (OD-P1B-C proprietary invariant): `USING == WITH CHECK == own-tenant`, no global rows. Cross-tenant leakage blocked on every axis (symmetric reads/`WITH CHECK`, **explicitly-tenant-filtered** profile→core + parent resolution, positive + closed-set `pg_policies` guards). The resolvers carry an EXPLICIT `tenant_id` predicate (the `ensure_manual_source` pattern, NOT id-only `register_model_version`) so cross-tenant fails closed on SQLite too.
- **Hierarchy STRUCTURE in P1B-2** (`parent_legal_entity_id` self-FK adjacency + a bounded, cycle-safe, tenant-filtered `resolve_ultimate_parent`, depth cap 32, no exposure math); the **exposure-rollup CALCULATION is DEFERRED**. **No netting / CSA / collateral / exposure columns** (OD-015 deferred).
- Reuse `REFERENCE.CREATE/UPDATE` (each entity OWN event — NOT folded, unlike P1B-1 children; `audit/service.py` FROZEN); one MANUAL-`data_source` ORIGIN edge per row. Additive `reference.legal_entity.view/edit` only (issuer/counterparty perms exist); `legal_entity.view` matches the issuer/counterparty recipient set — **EXCLUDES `auditor_3l`** (proprietary-identity SoD).

## P1B-3 design decisions (REALIZED — `8545ed6`, CI-green; 8-lens reviewed)
REQ-SMR-001 + REQ-SMR-003 (OD-P1B-A/G); migration `0010`. The platform's **first real FR / bitemporal** slice.
- **`instrument` = EV identity-only** + **`instrument_terms` = FR** (OD-P1B-A) + **`identifier_xref` = EV**. `instrument` carries NO terms/price/valuation/risk columns; `is_active` is the single lifecycle flag (no `status` string); nullable `issuer_id` FK → the issuer profile (cash/FX/index allowed). `currency_code` is a plain ISO string (NOT a FK to the hybrid `currency` table).
- **FR bitemporal protocol** (the net-new mechanism): `FullReproducibleMixin` (`valid_from/valid_to` + `system_from/system_to`) — its **first persisted user**. create → effective-dated supersede (close prior `valid_to`) → as-known correction/restatement (close prior `system_to`). **One `now` per op** (so `prior.system_to == corrected.system_from`); **close-first ordering** (prior close-out flushed before the new row, so the dual-open current-head partial-unique is never transiently violated); prior versions' economics **never mutated**; the FR table is **NOT** append-only (no `irp_prevent_mutation` trigger — the close-outs UPDATE). `reconstruct_terms_as_of(valid_at, known_at)` proves reconstruction on **BOTH** axes; `known_at` default = now = current view.
- **`REFERENCE.CORRECTION` (EVT-142) ACTIVATED** (R-07 sign-off, OQ-7) for the terms restatement path — caller-side only via a NEW `record_reference_correction` in `reference/service.py`; **`audit/service.py` stays FROZEN**. TR-08 `restatement_reason` recorded on the canonical `justification` field + `supersedes_id` link in DC-2 `after_value`. EVT-143 STATUS_CHANGE still reserved.
- **Deterministic identifier resolution** (OD-P1B-G / CTRL-029): `resolve_identifier` returns exactly one Instrument / `None` / `AmbiguousIdentifier` (>1 distinct entity_ids) — **never a silent arbitrary match**. Active partial-unique `(tenant_id, scheme, value) WHERE valid_to IS NULL`; ambiguity is reachable via historical-overlap + past as-of (defense-in-depth). Polymorphic `(entity_type, entity_id)` no-FK, scoped to `entity_type='instrument'`. Cross-vendor precedence DEFERRED (OD-012 → P1C); no external/check-digit validation.
- **Symmetric proprietary RLS** (byte-for-byte the `0009` loop; NEVER hybrid; closed-hybrid-set still the 5). Cross-tenant `issuer_id`/`instrument_id`/`entity_id` fail closed via the **service-layer** `*NotVisible` resolver predicate pre-commit (RLS `WITH CHECK` gates only the row's own `tenant_id`). Additive `reference.identifier.view/edit` (`.resolve` recipients UNCHANGED — not widened to risk_manager_2l; `auditor_3l` excluded; parity test).

## P1B-4 design decisions (REALIZED — `060b2a4`, CI-green; 8-lens reviewed) — the P1B block is DELIVERED
REQ-SMR-004 corporate_action (OD-P1B-B); migration `0011`. The **last reference entity** — capture-only.
- **`corporate_action` = EV** effective-dated reference data (NOT IA, NOT FR). One physical row; amend = in-place EV supersede (`REFERENCE.UPDATE`). The EV `valid_from/valid_to` **record** axis is distinct from the inert **business-date** columns (`announcement/ex/record/pay/effective_date`); `ratio/amount/currency_code` are inert placeholders. **Single `status` lifecycle** (ANNOUNCED→CONFIRMED→CANCELLED, terminal; **no `is_active`** — the P1B-3 `arch-1` dual-flag lesson); a thin transition guard rejects illegal/no-op/out-of-vocab moves with **no DB write** (validation, not a workflow/state-machine engine).
- **`REFERENCE.STATUS_CHANGE` (EVT-143) ACTIVATED** (R-07 sign-off, OQ-1) — the platform's **first persisted EVT-143 user** — caller-side via a NEW `record_reference_status_change` in `reference/service.py` (NO new lineage edge; `before/after = {status}` + optional `justification`); **`audit/service.py` stays FROZEN**. Used **only** for corporate_action status transitions; other entities' `is_active` flips still ride `REFERENCE.UPDATE`, and the existing EVT-143-reservation tests stay green (entity-scoped). **No `REFERENCE.CORRECTION`** (FR-only).
- **`instrument_id` NOT-NULL FK** to the P1B-3 `instrument` head, resolved via the **reused** `resolve_instrument` tenant-filtered → cross-tenant/unknown fails closed (`InstrumentNotVisible`) pre-commit. Symmetric proprietary RLS (byte-for-byte the `0010` loop). Additive `reference.corporate_action.view` (== instrument.view set; `auditor_3l` excluded; parity test); `.edit` pre-existing unchanged.
- **CAPTURE-ONLY** (the load-bearing scope fence): **NO** application to positions/valuations, **NO** entitlement/tax calc, **NO** event-processing engine, **NO** roll/day-count math (QS-10/11 → P1C), **NO** vendor feed/reconciliation/override workflow. "No double-apply" holds trivially (nothing is ever applied); a scope-fence test pins absence of any applied/position/valuation/entitlement/tax column.

## Deferred (sound; do not pull forward)
OD-012 identifier precedence → P1C; OD-015 counterparty netting/CSA → P1C; REQ-INT-002/003 vendor/SFTP/API
adapters → P9; OD-042 production AV → later; manual_override/BR-7 enforcement → P6/P7; reconciliation
(REQ-DQR-002) and override workflow (REQ-DQR-003) → P7; model validation/tiering (REQ-MDG-002/003) → P7;
WORM/anchored audit hardening → later.

## Do not relitigate unless explicitly reopened
All AD-* above; the selective-bitemporality classes; the no-silent-failure DQ policy; the
audit-frozen / no-new-audit-code-without-R-07 rule; the IA-status-mutable precedent; the durable-evidence
ingestion contract; the P1B-0 OD-P1B-* resolutions (once committed/ratified).
