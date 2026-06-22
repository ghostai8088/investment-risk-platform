# Decision Summary

> **As of 2026-06-22.** Ratified and load-bearing decisions. **Do not relitigate the "Ratified" items unless
> the user explicitly reopens them.** Authoritative sources: `11_decision_log/architecture_decision_log.md`
> (AD-*), the per-slice plan docs, and `10_delivery_backlog/p1b0_decision_record.md` (OD-P1B-*).

## Major ratified architecture decisions (AD-*, Accepted by H-04)
- **AD-004** segregated/append-only audit store; native uuid + JSONB on Postgres.
- **AD-005** **selective bitemporality**: **FR** (bitemporal) for risk-driving inputs, **IA** (immutable append-only) for outputs/events/audit, **EV** (effective-dated) for reference/config. Risk = entity misclassification.
- **AD-007** real identity via OIDC/SSO (deferred; dev header shim is not a security boundary).
- **AD-008 / BR-17** tenant isolation; investment data MNPI-adjacent → isolation by default.
- **AD-013** **hybrid reference-data tenancy**: global system reference shared read-only; investment reference tenant-scoped; tenant-override pattern; no cross-tenant proprietary sharing. (P1B-0 proposes refinement **AD-013-R1** — see below.)
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
Recorded in `10_delivery_backlog/p1b0_decision_record.md` (**committed at `dbed93e`**, CI-green; 7-lens reviewed;
several require ratification before P1B-1 builds):
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

## Deferred (sound; do not pull forward)
OD-012 identifier precedence → P1C; OD-015 counterparty netting/CSA → P1C; REQ-INT-002/003 vendor/SFTP/API
adapters → P9; OD-042 production AV → later; manual_override/BR-7 enforcement → P6/P7; reconciliation
(REQ-DQR-002) and override workflow (REQ-DQR-003) → P7; model validation/tiering (REQ-MDG-002/003) → P7;
WORM/anchored audit hardening → later.

## Do not relitigate unless explicitly reopened
All AD-* above; the selective-bitemporality classes; the no-silent-failure DQ policy; the
audit-frozen / no-new-audit-code-without-R-07 rule; the IA-status-mutable precedent; the durable-evidence
ingestion contract; the P1B-0 OD-P1B-* resolutions (once committed/ratified).
