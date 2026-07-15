# Audit Event Taxonomy

## Document Control

| Field | Value |
|---|---|
| Document ID | DATA-AUDIT-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-07 Security Architect AI (with R-10 Compliance & Controls AI) |
| Approver | H-06 Engineering Lead (H-08 Internal Audit consulted) |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | canonical_data_model_standard.md, temporal_reproducibility_standard.md, entitlement_sod_model.md, reconciled_agent_role_registry.md, control_matrix_skeleton.md |
| Supported Build Rules | BR-5, BR-7, BR-12, BR-16 |

## 1. Purpose

Define the canonical audit event schema, the controlled event vocabulary, integrity/retention requirements, and the AI-agent
and override logging rules. This makes "the audit event framework" (BR-12) a concrete, non-bypassable contract.

## 2. Canonical Audit Event Schema (ENT-045)

| Field | Required | Description |
|---|---|---|
| `event_id` | yes | UUID, immutable |
| `event_type` | yes | Controlled code (§3), e.g., `OVERRIDE.CREATE` |
| `event_time` | yes | System time (UTC) of the event |
| `tenant_id` | yes* | Tenant scope (*where multi-tenant) |
| `actor_type` | yes | `user` \| `system` \| `agent` |
| `actor_id` | yes | Principal id (ENT-043) |
| `on_behalf_of` | no | Human principal an agent acted for |
| `source_module` | yes | Bounded context (BC-xx) emitting the event |
| `entity_type` | yes | Affected entity (ENT-xxx) |
| `entity_id` | yes | Affected record id |
| `action` | yes | create/update/approve/reject/run/export/login/… |
| `before_value` | cond. | Prior value (or secure reference/hash if large/sensitive) |
| `after_value` | cond. | New value (or reference/hash) |
| `justification` | cond. | Required for overrides/approvals (BR-7) |
| `approval_ref` | cond. | Link to maker-checker approval record |
| `correlation_id` | yes | Request/trace correlation |
| `session_id` | no | Session identifier |
| `source_ip` / `channel` | no | Origin metadata |
| `outcome` | yes | success \| failure \| denied |
| `severity` | yes | info \| notice \| warning \| critical |
| `data_classification` | yes | DC tag of affected data (entitlement_sod_model.md) |
| `agent_model` / `agent_model_version` | cond. | Required when `actor_type=agent` (BR-16) |
| `agent_input_ref` | cond. | Reference to inputs/prompt context for agent actions |

Sensitive `before/after` values (e.g., Restricted/MNPI) are stored as secure references or hashes, not plaintext, in the audit
store.

## 3. Event Vocabulary (controlled)

Codes are `CATEGORY.ACTION`. Stable event IDs `EVT-nnn` index notable events.

| Category | Example codes | Notes |
|---|---|---|
| `AUTH` | `AUTH.LOGIN`, `AUTH.LOGOUT`, `AUTH.MFA_CHALLENGE`, `AUTH.DENIED` | Authentication (EVT-001…) |
| `ENTITLEMENT` | `ENTITLEMENT.GRANT`, `.REVOKE`, `.ROLE_CHANGE`, `.REQUEST`, `.APPROVE` | Access changes; maker-checker (EVT-010…) |
| `DATA` | `DATA.INGEST`, `.VALIDATE`, `.CORRECTION`, `.RECONCILE`, `.PURGE`, `.SOURCE_REGISTER`, `.SOURCE_UPDATE`, `.DQ_RULE_DEFINE`, `.DQ_RULE_UPDATE` | Data lifecycle incl. restatement + data-source provenance (EVT-020…; `.SOURCE_REGISTER`=EVT-026, `.SOURCE_UPDATE`=EVT-027, P1A-1). `LINEAGE.RECORD` (EVT-028) **reserved/unused** — standalone lineage correction/backfill (P7/REQ-LIN-002); lineage edges are otherwise metadata of an already-audited governed write (no per-edge event). **P1A-3:** `.VALIDATE` is **activated** for DQ rule runs (one per run; `outcome='failure'` on a failing/errored rule, never swallowed); `.DQ_RULE_DEFINE` / `.DQ_RULE_UPDATE` for rule CRUD (new DATA-category codes; they fill the free DATA-block slots **EVT-025/EVT-029** to avoid the OVERRIDE EVT-030 anchor — final EVT index confirmed with R-07). `.RECONCILE` (reconciliation REQ-DQR-002/P7) and `.CORRECTION` (override/restatement REQ-DQR-003/P7) stay **reserved** — not emitted in P1A-3. **P1A-4:** `.INGEST` is **activated** for the ingestion-batch lifecycle (one `create` event + a per-transition `status_change`, mirroring `CALC.RUN_CREATE`/`CALC.RUN_STATUS_CHANGE`; `outcome='failure'` on REJECTED/FAILED with a reason code in `after_value`; `after_value` carries metadata/reason only — **never raw payload or full client path**, DC-2). `.VALIDATE` is reused for the on-ingest DQ runs (no double-emit; the `data_quality_result.ingestion_batch_id` placeholder is now populated). **No new DATA code is minted in P1A-4.** `.PURGE` remains reserved. |
| `OVERRIDE` | `OVERRIDE.CREATE`, `.APPROVE`, `.REJECT` | Manual overrides — BR-7 fields mandatory (EVT-030…) |
| `CALC` | `CALC.RUN_CREATE`, `CALC.RUN_STATUS_CHANGE` | Calculation runs; binds run metadata (EVT-040…). **Doc-vs-code reconciliation (R-07, P2-3 ratification 2026-06-26):** the SHIPPED emitters are **`CALC.RUN_CREATE`** (run create) + **`CALC.RUN_STATUS_CHANGE`** (per status transition; the `ingestion_batch` `.INGEST` precedent) — the earlier doc-only labels `CALC.RUN_START`/`.RUN_COMPLETE`/`.RUN_FAIL` **never existed in code** and are **retired** here. **P2-3 (`exposure_aggregate`, OD-P2-3-F/H):** the exposure run **reuses these two codes** — `update_run_status` gains an additive **`outcome`** param (`'success'` default; **`'failure'` on a post-create FAILED run**) forwarded to the FROZEN `record_event` (the sole change is in `calc/service.py`; **`audit/service.py` stays FROZEN**). Failure model: a **pre-create refusal** emits ZERO audit (no run); a **post-create FAILED** run commits `CALC.RUN_CREATE` + `CALC.RUN_STATUS_CHANGE(→FAILED, outcome='failure')` with ZERO exposure rows. `before/after` = DC-2 metadata only; per-tenant chain. |
| `MODEL` | `MODEL.REGISTER`, `.VERSION`, `.VALIDATE`, `.APPROVE`, `.RESTRICT`, `.RETIRE` | Model governance (EVT-050…). `MODEL.REGISTER`/`MODEL.VERSION` **activated in P1A-2** (model/version inventory; assumption/limitation writes fold into `MODEL.VERSION`, no per-row event); **`.VALIDATE` activated in VW-1** (2026-07-14 — one event per `model_validation` record, `after_value` = outcome + validation_type + finding/evidence counts + next_review_due, DC-2; this taxonomy row IS the activation record, the P3-2 precedent); `.APPROVE/.RESTRICT/.RETIRE` stay **reserved** for the P7 approval/restricted-use/retirement legs (the Tier-1 H-02 approval step rides tiering, REQ-MDG-002/003). |
| `LIMIT` | `LIMIT.DEFINE`, `.CHANGE`, `.APPROVE` | Limit framework changes (EVT-060…) |
| `BREACH` | `BREACH.DETECT`, `.ASSIGN`, `.1L_RESPONSE`, `.2L_REVIEW`, `.ESCALATE`, `.CLOSE` | Breach workflow (EVT-070…) |
| `SCENARIO` | `SCENARIO.DEFINE`, `.VERSION`, `.RUN` | Scenario lifecycle (EVT-080…) |
| `REPORT` | `REPORT.GENERATE`, `.PUBLISH`, `.EXPORT` | Reporting (EVT-090…) |
| `EXPORT` | `EXPORT.DATA`, `.DENIED` | Data export controls (EVT-100…) |
| `CONFIG` | `CONFIG.CHANGE`, `.DEPLOY` | Configuration/deployment (EVT-110…) |
| `ADMIN` | `ADMIN.USER_CREATE`, `.DISABLE`, `.SECRET_ROTATE` | Administration (EVT-120…) |
| `AGENT` | `AGENT.ACTION`, `.RECOMMEND`, `.DRAFT`, `.REVIEW` | Material AI agent actions — BR-16 (EVT-130…) |
| `REFERENCE` | `REFERENCE.CREATE`, `.UPDATE`, `.CORRECTION`, `.STATUS_CHANGE` | **`REFERENCE.CREATE` (EVT-140) / `REFERENCE.UPDATE` (EVT-141) ACTIVATED in P1B-1** (R-07 sign-off) for `currency`/`calendar`/`rating_scale` governed CRUD — emitted co-transactionally to the FROZEN `record_event` from `irp_shared/reference/events.py` constants. **Children fold into the parent event** (`calendar_holiday`/`rating_grade` get no own event). `before_value`/`after_value` are **DC-2 metadata only** (identifying/controlled-vocab fields + child counts — never full rows or raw input). SYSTEM seeds chain on `chain_id = SYSTEM_TENANT_ID`; tenant/override writes on `chain_id = tenant_id`. `is_active` flips ride on `REFERENCE.UPDATE` (no `STATUS_CHANGE`). **P1B-2 extends emission** to `legal_entity` / `issuer` / `counterparty` governed CRUD (same EVT-140/141 constants, FROZEN `record_event`); these are **PROPRIETARY** (per-tenant chains only — no SYSTEM chain) and each entity emits its **OWN** event (the profiles are NOT folded into the `legal_entity` event, unlike P1B-1's calendar/rating children). **P1B-4 ACTIVATES `REFERENCE.STATUS_CHANGE` (EVT-143)** (R-07 sign-off, OQ-1) for the `corporate_action` status-lifecycle transitions (ANNOUNCED → CONFIRMED → CANCELLED) — caller-side via a new `record_reference_status_change` helper in `irp_shared/reference/service.py` (`audit/service.py` stays FROZEN), `before/after = {status}` (+ optional `justification`=reason). It is used **ONLY** for corporate_action; for the P1B-1/P1B-2/P1B-3 entities `is_active` flips still ride on `REFERENCE.UPDATE` (no STATUS_CHANGE). `corporate_action` create/amend reuse `REFERENCE.CREATE`/`UPDATE`. **P1B-3 extends `REFERENCE.CREATE`/`UPDATE` emission** to `instrument` / `instrument_terms` / `identifier_xref` (same FROZEN `record_event`; each emits its OWN event; per-tenant chains) **and ACTIVATES `REFERENCE.CORRECTION` (EVT-142)** (R-07 sign-off, OQ-7) for the FR `instrument_terms` as-known restatement path, via a new caller-side `record_reference_correction` helper in `irp_shared/reference/service.py` (`audit/service.py` stays FROZEN). **Reconciliation:** `REFERENCE.CORRECTION` is the **reference-domain** restatement code, distinct from the reserved `DATA.CORRECTION` (data-lifecycle restatement); the `instrument_terms` restatement carries the **TR-08** `restatement_reason` (on the canonical `justification` field) + the `supersedes_id` superseded-version link (`approval_ref`/manual_override BR-7 enforcement is P6/P7). No generic `DATA.CREATE`/`DATA.UPDATE` is used. **P2-6 extends `REFERENCE.CREATE`/`REFERENCE.UPDATE` emission** to the EV `benchmark` *definition* (ENT-009; same FROZEN `record_event`; per-tenant chain; its OWN event; `before/after` = DC-2 metadata `benchmark_code/source/currency/index_family/record_version`) — the reference/definition family per **OQ-P2-6-11 Option A** (the captured `benchmark_constituent` *membership* is the `MARKET.*` half, NOT `REFERENCE.*`). **P3-2 extends `REFERENCE.CREATE`/`REFERENCE.UPDATE` emission** to the net-new EV `factor` *definition* (ENT-025; same FROZEN `record_event`; per-tenant chain; its OWN event; `before/after` = DC-2 metadata `factor_code/source/family/type/region/currency_code/asset_class/frequency/record_version`) — the reference/definition family, mirroring `benchmark` (the captured `factor_return` *series* is the `MARKET.*` half, NOT `REFERENCE.*`). Committed `402cb12`, CI #89 green. |
| `PORTFOLIO` | `PORTFOLIO.CREATE`, `.UPDATE`, `.STATUS_CHANGE` | **`PORTFOLIO.CREATE` (EVT-150) / `PORTFOLIO.UPDATE` (EVT-151) ACTIVATED in P1C-1** (2026-06-23; R-07 sign-off) — emitted caller-side to the FROZEN `record_event` from `irp_shared/portfolio/events.py` constants. The first **domain** event family (beyond reference/rails), for `portfolio` hierarchy governed CRUD (CAP-1/BC-01), at the **EVT-150 block**: `PORTFOLIO.CREATE`=EVT-150, `PORTFOLIO.UPDATE`=EVT-151, `PORTFOLIO.STATUS_CHANGE`=EVT-152 — the head of the P1C domain corridor (TRANSACTION / POSITION / VALUATION take successive ~10-wide blocks EVT-160/170/180). EVT-144–149 are left as REFERENCE headroom; the established ~10-wide-per-category convention (EXPORT 100 / CONFIG 110 / ADMIN 120 / AGENT 130 / REFERENCE 140) places the P1C domain corridor at the **EVT-150 decade** — EVT-150 is the R-07 index assigned at this P1C-0 ratification (the source plan reserved "EVT-144+ free, index assigned by R-07"). **Activated caller-side in P1C-1** via the new `irp_shared/portfolio/events.py` + thin `record_portfolio_create`/`record_portfolio_update` mirroring `record_reference_*` — `audit/service.py` stays **FROZEN** (no central event enum; "activation" = first emission). `before/after` = DC-2 metadata only (code/name/node_type/parent link); per-tenant chain (PROPRIETARY, no SYSTEM chain). For P1C-1 a `status` flip rides on `PORTFOLIO.UPDATE` (the P1B `is_active`/status precedent), so `PORTFOLIO.STATUS_CHANGE` is **reserved-but-not-required** in P1C-1 (held for a future governed portfolio lifecycle if needed). |
| `TRANSACTION` | `TRANSACTION.RECORD`, `.REVERSE` | **`TRANSACTION.RECORD` (EVT-160) / `TRANSACTION.REVERSE` (EVT-161) ACTIVATED in P1C-2** (2026-06-24; R-07 sign-off, OD-P1C2-1) — emitted caller-side to the FROZEN `record_event` from `irp_shared/transaction/events.py` constants. The second **domain** family (after PORTFOLIO), for the `transaction` IA **append-only** event log (CAP-1/BC-01), at the **EVT-160 block** — the next decade in the P1C domain corridor (POSITION EVT-170 / VALUATION EVT-180 follow in their slices). **Create-only** (append-only): there is **no** `TRANSACTION.UPDATE`/`.STATUS_CHANGE` — a transaction is immutable, so the only governed events are the **record** of a new row (`TRANSACTION.RECORD`) or a **reversal** record (`TRANSACTION.REVERSE` — itself a NEW row with `reverses_transaction_id`, never a mutation of the original). Each emits one event + roots one MANUAL-source ORIGIN lineage edge; per-tenant chain (PROPRIETARY, no SYSTEM chain); `before/after` = DC-2 metadata only. `audit/service.py` stays **FROZEN**. |
| `POSITION` | `POSITION.CREATE`, `.UPDATE`, `.CORRECTION` | **`POSITION.CREATE` (EVT-170) / `POSITION.UPDATE` (EVT-171) / `POSITION.CORRECTION` (EVT-172) ACTIVATED in P1C-3** (2026-06-25; R-07 sign-off, OD-P1C3-1) — emitted caller-side to the FROZEN `record_event` from `irp_shared/position/events.py` constants. The third **domain** family (after PORTFOLIO/TRANSACTION), for the `position` **FR** (bitemporal) captured holdings master (CAP-1/BC-01), at the **EVT-170 block** (VALUATION EVT-180 follows in P1C-4). The FR lifecycle maps to three codes (mirroring the `instrument_terms`/`REFERENCE.CORRECTION` EVT-142 precedent): **`POSITION.CREATE`** = a captured new version (initial capture, and the new open row of a valid-time supersede); **`POSITION.UPDATE`** = a prior-head **close-out** (the `valid_to`/`system_to` stamp on supersede/correction; no new lineage edge; before/after carry the changed boundary column); **`POSITION.CORRECTION`** = an as-known restatement (a corrected NEW row over the same valid period; `restatement_reason` TR-08 on the canonical `justification` field + `supersedes_id` in `after_value`). Each new physical version roots one MANUAL-source ORIGIN edge (the close-out adds none); per-tenant chain (PROPRIETARY, no SYSTEM chain); `before/after` = DC-2 metadata only. `audit/service.py` stays **FROZEN**. **Captured directly, NOT derived from transactions** (OD-P1C-E). |
| `VALUATION` | `VALUATION.CREATE`, `.UPDATE`, `.CORRECTION` | **`VALUATION.CREATE` (EVT-180) / `VALUATION.UPDATE` (EVT-181) / `VALUATION.CORRECTION` (EVT-182) ACTIVATED in P1C-4** (2026-06-25; R-07 sign-off, OD-P1C4-1) — emitted caller-side to the FROZEN `record_event` from `irp_shared/valuation/events.py` constants. The fourth **domain** family (after PORTFOLIO/TRANSACTION/POSITION), for the `valuation` **FR** (bitemporal) captured mark history (CAP-1/BC-01), at the **EVT-180 block** — the last decade in the P1C domain corridor. The FR lifecycle maps to three codes (mirroring the `position`/EVT-172 precedent): **`VALUATION.CREATE`** = a captured new mark version (initial capture, and the new open row of a valid-time re-mark); **`VALUATION.UPDATE`** = a prior-head **close-out** (the `valid_to`/`system_to` stamp; no new lineage edge; before/after carry the changed boundary column); **`VALUATION.CORRECTION`** = an as-known restatement (a corrected NEW row over the same valid period + same `valuation_date`; `restatement_reason` TR-08 on the canonical `justification` field + `supersedes_id` in `after_value`). Each new physical version roots one MANUAL-source ORIGIN edge (the close-out adds none); per-tenant chain (PROPRIETARY, no SYSTEM chain); `before/after` = DC-2 metadata only. `audit/service.py` stays **FROZEN**. **Captured marks, NOT computed by a valuation/pricing model, NO market-value rollup / NO position link** (OD-P1C-F). |
| `SNAPSHOT` | `SNAPSHOT.CREATE` | **ACTIVATED (P2-1 implementation, `3629baa`; reserved at the P2-0 ratification, 2026-06-26).** The reproducible-input-snapshot family for ENT-049 `dataset_snapshot` (AD-014), at the **EVT-190 block** — the next domain decade after VALUATION (EVT-180); final R-07 index assigned at activation. **`SNAPSHOT.CREATE`** = one event per snapshot create (`before/after` = **DC-2 metadata only** — `component_count`, `manifest_hash`, the `(as_of_valid_at, as_of_known_at, as_of_valuation_date)` cutoffs; **never the captured payloads**); **no event on read/verify** (OD-023 no-emit-on-read). **Activated in the P2-1 implementation** — caller-side from `irp_shared/snapshot/events.py` to the **FROZEN** `record_event` (`audit/service.py` stays FROZEN). Per-tenant chain (PROPRIETARY, no SYSTEM chain). |
| `MARKET` | `MARKET.FX_CREATE`, `MARKET.FX_UPDATE`, `MARKET.FX_CORRECTION` | **ACTIVATED (P2-2 implementation, 2026-06-26).** The captured-market-data family at the **EVT-200 block** (the next domain decade after SNAPSHOT/EVT-190); FX is the first member (ENT-024 `fx_rate`, FR). Caller-side from `irp_shared/marketdata/events.py` to the **FROZEN** `record_event` (`audit/service.py` UNTOUCHED). Per-op grain: capture=1 `FX_CREATE`; supersede=2 (`FX_UPDATE` close-out + `FX_CREATE`); correct=2 (`FX_UPDATE` close-out + `FX_CORRECTION`). `before/after` = **DC-2 metadata only** (`base/quote/rate_date/rate_type/rate_source`; **never a vendor-licensed payload dump**); **no event on read/`convert`** (OD-023). Per-tenant chain (PROPRIETARY, no SYSTEM chain). Price (`MARKET.PRICE_*`, P2-4) + curve (`MARKET.CURVE_*`, P2-5) joined additively. **P2-6 ACTIVATES `MARKET.BENCHMARK_CONSTITUENT_CREATE`/`_UPDATE`/`_CORRECTION`** for the FR `benchmark_constituent` membership (ENT-009; **set-grained — ONE event per membership set, independent of constituent count**; capture=1, supersede=2 (UPDATE close-out + CREATE), correct=2 (UPDATE + CORRECTION); `before/after` = DC-2 metadata `benchmark_code/source/currency/effective_date/constituent_count`, never the membership payload; no event on read). The EV `benchmark` *definition* is `REFERENCE.*`, NOT `MARKET.*` (OQ-P2-6-11 Option A). **P3-2 ACTIVATES `MARKET.FACTOR_RETURN_CREATE`/`_UPDATE`/`_CORRECTION`** for the FR `factor_return` captured series (ENT-025; **single-row per `(factor, return_date, return_type)`** — unlike the set-grained `benchmark_constituent`; capture=1, supersede=2 (UPDATE close-out + CREATE), correct=2 (UPDATE + CORRECTION); `before/after` = DC-2 metadata `factor_code/source/return_date/return_type/record_version`, never the vendor-licensed return payload; no event on read). The net-new EV `factor` *definition* is `REFERENCE.*`, NOT `MARKET.*` (the `benchmark` split precedent). Committed `402cb12`, CI #89 green. **P2-7 ACTIVATES `MARKET.BENCHMARK_LEVEL_CREATE`/`_UPDATE`/`_CORRECTION` + `MARKET.BENCHMARK_RETURN_CREATE`/`_UPDATE`/`_CORRECTION`** (R-07 sign-off — this taxonomy row IS the activation record; the P3-2 precedent) for the FR `benchmark_level` + `benchmark_return` captured series (ENT-052; caller-side from `irp_shared/marketdata/benchmark_series.py` to the FROZEN `record_event`; **single-row grain** per `(benchmark, level_date, level_type)` / `(benchmark, return_date, return_type, return_basis)`; capture=1, supersede=2 (UPDATE close-out + CREATE), correct=2 (UPDATE + CORRECTION); `before/after` = DC-2 metadata `benchmark_code/source` + the logical key + `record_version`, **never the captured level/return value payload** — vendor-licensed; no event on read). Reuses the `VENDOR_BENCHMARK` `data_source` ORIGIN lineage + `marketdata.view`/`.ingest` (no new source/permission). **PA-0 ACTIVATES `MARKET.PROXY_MAPPING_CREATE`/`_UPDATE`/`_CORRECTION`** (R-07 sign-off — this taxonomy row IS the activation record; the P3-2 precedent) for the FR `proxy_mapping` captured private→public factor proxies (ENT-019; caller-side from `irp_shared/marketdata/proxy_mapping.py` to the FROZEN `record_event`; **single-row grain** per `(private_instrument_id, factor_id)`; capture=1, supersede=2 (UPDATE close-out + CREATE), correct=2 (UPDATE + CORRECTION); `before/after` = DC-2 metadata `private_instrument_id/factor_id/mapping_method/record_version` (+ the weight as a string on a correction), **never bulk data**; no event on read). NEW `MANUAL_PROXY` `data_source` ORIGIN lineage (a non-vendor manual-judgment source ROW, not a new lineage KIND); reuses `marketdata.view`/`.ingest` (no new permission). |
| `EXPOSURE` | `EXPOSURE.AGGREGATE_CREATE` | **RESERVED — NOT minted (P2-3 ratification, 2026-06-26; OD-P2-3-H / OQ-P2-3-5).** The would-be per-result exposure-audit family at the **EVT-210 block** (the next domain decade after MARKET/EVT-200; final R-07 index assigned only at activation). **NOT used in P2-3:** the `exposure_aggregate` rows (ENT-014) are **run-tracked + lineaged** — metadata of the already-audited `calculation_run` (which emits `CALC.RUN_CREATE`/`CALC.RUN_STATUS_CHANGE`) — so P2-3 mints **no** `EXPOSURE.*` code (the `ingestion_staged_record`/result precedent). `EXPOSURE.AGGREGATE_CREATE` is reserved **only** for a possible future granular per-result audit, **if later adopted and documented**. `audit/service.py` stays **FROZEN**. |
| `RISK` | `RISK.SENSITIVITY_CREATE`, `RISK.FACTOR_EXPOSURE_CREATE`, `RISK.COVARIANCE_CREATE`, `RISK.VAR_CREATE`, `RISK.ACTIVE_RISK_CREATE`, `RISK.VAR_BACKTEST_CREATE`, `RISK.SCENARIO_CREATE` | **RESERVED — NOT minted (P3-1 implementation, 2026-06-30, OD-P3-1-H; P3-3 implementation, OD-P3-3-K; P3-4 implementation, 2026-07-07, OD-P3-4-L; P3-5 implementation, 2026-07-07, OD-P3-5-K; P3-7 implementation, 2026-07-09, OD-P3-7-A; P3-6 implementation, 2026-07-12, OD-P3-6-E).** The would-be per-result risk-audit family at the **EVT-220 block** (the next domain decade after EXPOSURE/EVT-210; final R-07 index assigned only at activation). **NOT used in P3-1:** the `sensitivity_result` rows (ENT-028) are **run-tracked + lineaged** — metadata of the already-audited `calculation_run` (`CALC.RUN_CREATE`/`CALC.RUN_STATUS_CHANGE`) + the model-registry `MODEL.REGISTER`/`MODEL.VERSION` for the bound model_version — so P3-1 mints **no** `RISK.*` code (the `EXPOSURE.*`/EVT-210 precedent). `RISK.SENSITIVITY_CREATE` is reserved **only** for a possible future granular per-result audit, **if later adopted and documented**. **P3-3 reserves `RISK.FACTOR_EXPOSURE_CREATE` the same way** — the `factor_exposure_result` rows are run-tracked + lineaged (the run reuses `CALC.RUN_CREATE`/`CALC.RUN_STATUS_CHANGE`; the model registration `MODEL.REGISTER`/`MODEL.VERSION`); NO `RISK.*` code is emitted. **P3-4 reserves `RISK.COVARIANCE_CREATE` identically** — the `covariance_result` rows (ENT-051) are run-tracked + lineaged; zero `RISK.*` events emitted (test-asserted). **P3-5 reserves `RISK.VAR_CREATE` identically** — the `var_result` row (ENT-027) is run-tracked + lineaged; zero `RISK.*` events emitted (test-asserted). **P3-7 reserves `RISK.ACTIVE_RISK_CREATE` identically** — the `active_risk_result` row (ENT-027, third realization) is run-tracked + lineaged (the run reuses `CALC.RUN_CREATE`/`CALC.RUN_STATUS_CHANGE`; the model registration `MODEL.REGISTER`/`MODEL.VERSION`); zero `RISK.*` events emitted (test-asserted). **BT-1 reserves `RISK.VAR_BACKTEST_CREATE` identically (2026-07-10, OD-BT-1-B)** — the `var_backtest_result` rows (ENT-055) are run-tracked + lineaged; zero `RISK.*` events emitted (test-asserted). **P3-6 reserves `RISK.SCENARIO_CREATE` identically (2026-07-12, OD-P3-6-E)** — the `scenario_result` rows (ENT-030) are run-tracked + lineaged (the run reuses `CALC.RUN_CREATE`/`CALC.RUN_STATUS_CHANGE`; the model registration `MODEL.REGISTER`/`MODEL.VERSION` for `risk.scenario.factor_shock`); zero `RISK.*` events emitted (test-asserted). The captured `scenario_definition`/`scenario_shock` assumptions are `REFERENCE.*`-audited (the EV-definition split precedent), NOT `RISK.*`. `audit/service.py` stays **FROZEN**. |
| `PERF` | `PERF.RETURN_CREATE`, `PERF.BENCHMARK_RELATIVE_CREATE`, `PERF.DESMOOTHED_RETURN_CREATE` | **RESERVED — NOT minted (PM-1 implementation, 2026-07-09, OD-PM-1-A; P3-8 implementation, 2026-07-10, OD-P3-8-A; PA-1 implementation, 2026-07-12, OD-PA-1-F).** The would-be per-result performance-audit family at the **EVT-230 block** (the next domain decade after RISK/EVT-220; final R-07 index assigned only at activation). **NOT used in PM-1:** the `portfolio_return_result` rows (ENT-053) are **run-tracked + lineaged** — metadata of the already-audited `calculation_run` (`CALC.RUN_CREATE`/`CALC.RUN_STATUS_CHANGE`) + the model-registry `MODEL.REGISTER`/`MODEL.VERSION` for the bound `perf.return.twr` model_version — so PM-1 mints **no** `PERF.*` code (the `RISK.*`/EVT-220 precedent). `PERF.RETURN_CREATE` is reserved **only** for a possible future granular per-result audit, **if later adopted and documented**. **P3-8 reserves `PERF.BENCHMARK_RELATIVE_CREATE` identically** — the `benchmark_relative_result` rows (ENT-054) are run-tracked + lineaged (the run reuses `CALC.RUN_*`; the model registration `MODEL.REGISTER`/`MODEL.VERSION` for `perf.benchmark_relative`); no `PERF.*` code emitted. **PA-1 reserves `PERF.DESMOOTHED_RETURN_CREATE` identically (2026-07-12, OD-PA-1-F)** — the `desmoothed_return_result` rows (ENT-056) are run-tracked + lineaged (the run reuses `CALC.RUN_*`; the model registration for `perf.return.desmoothed_geltner`). Zero `PERF.*` events emitted (test-asserted). `audit/service.py` stays **FROZEN**. |

## 4. Integrity, Segregation & Retention

| ID | Rule |
|---|---|
| AUD-01 | Audit store is **append-only and segregated** (AD-004); application administrators cannot edit or delete audit records (SoD). |
| AUD-02 | Tamper-evidence: events are sequenced and integrity-protected (e.g., hash-chained) so gaps/alterations are detectable. |
| AUD-03 | Audit retention ≥ NFR-04 (≥ 7 years; confirm per jurisdiction); purge only via controlled, approved, audited process (TR-20). |
| AUD-04 | Audit capture failures fail the originating action closed where the action is governed (no silent unaudited change to governed data). |
| AUD-05 | Audit queries are themselves entitlement-controlled; export of audit data emits `EXPORT.DATA`. |

## 4A. Tamper-Evidence: Application-Level Hash Chain (initial mechanism, Step 1C)

The initial tamper-evidence mechanism (AUD-02) is an **application-level hash chain**, with **WORM / immutable storage as a
later-hardening option** layered on top — not a replacement.

### Hash-chain design
| ID | Rule |
|---|---|
| HC-01 | Events are written to a per-stream sequence. A **stream** is scoped by `chain_id` (per tenant, default one stream per tenant; high-volume tenants may shard with documented stream keys). |
| HC-02 | Each event stores `event_hash = SHA-256( canonical_serialization(event_payload) ‖ prev_hash )`, where `prev_hash` is the prior event's `event_hash` in the same stream (genesis uses a fixed seed hash). |
| HC-03 | Canonical serialization is a deterministic, versioned encoding of the immutable event fields (excludes the hash fields themselves); the encoding version is recorded in `hash_version`. |
| HC-04 | Sensitive values (DC-3/DC-4) are referenced/hashed, not stored plaintext (consistent with §2); the hash still covers the reference so tampering is detectable. |
| HC-05 | A break or gap (missing `sequence_no`, mismatched `prev_hash`) is an **alertable security incident** (BR-18) and a control finding (CTRL-026). |

### Required hash fields (extend ENT-045)
| Field | Description |
|---|---|
| `chain_id` | Stream identifier (per tenant/shard) |
| `sequence_no` | Monotonic position within the stream (gap-detectable) |
| `prev_hash` | `event_hash` of the prior event in the stream |
| `event_hash` | SHA-256 chained hash for this event |
| `hash_algorithm` | e.g., `SHA-256` |
| `hash_version` | Canonical-serialization version |
| `checkpoint_id` | Nullable link to the checkpoint covering this event |

### Checkpoint concept
| ID | Rule |
|---|---|
| CP-01 | A **checkpoint** is a periodic signed record (every N events or time interval) capturing `chain_id`, the latest `sequence_no`, and the cumulative `event_hash` at that point. |
| CP-02 | Checkpoints are signed and may be exported/anchored to a separate system (and, later, to WORM/an external transparency log) for stronger non-repudiation. |
| CP-03 | Verification recomputes the chain **between checkpoints**, enabling efficient integrity checks without rehashing the full history. |
| CP-04 | A scheduled verification job validates chains against checkpoints; failure blocks release and raises an incident (links CTRL-026). |

### Later-hardening
| ID | Rule |
|---|---|
| HARD-01 | Add WORM/object-lock immutable storage for events and/or checkpoints. |
| HARD-02 | Optionally anchor checkpoint hashes to an external/independent service for third-party-verifiable non-repudiation. |

## 5. Override & Approval Logging (BR-7)

`OVERRIDE.*` events must carry: user id, timestamp, justification, prior value, new value, approval status, and `approval_ref`
to the maker-checker record (entitlement_sod_model.md). An override without all fields is rejected.

## 6. AI Agent Logging (BR-16)

`AGENT.*` events must carry `actor_type=agent`, `actor_id`, `agent_model`, `agent_model_version`, `on_behalf_of` (if any),
the action, inputs/justification reference, and the human `approval_ref` where BR-15 requires human approval. Agents cannot
suppress or bypass audit emission.

## 7. Open Decisions

| ID | Open Decision |
|---|---|
| ~~OD-020~~ | **Resolved (Step 1C, §4A):** application-level SHA-256 hash chain + signed checkpoints initially; WORM/anchoring as later-hardening (HARD-01/02). |
| OD-021 | Confirm retention per event category and jurisdiction (AUD-03). |
| OD-022 | Confirm storage strategy for large/sensitive before/after values (reference vs hash vs encrypted blob). |
| OD-023 | Confirm whether read/view access to Restricted/MNPI data generates access-audit events. |

## 8. Dependencies

- canonical_data_model_standard.md (ENT-045, ENT-041 override).
- entitlement_sod_model.md (DC tags, maker-checker `approval_ref`).
- temporal_reproducibility_standard.md (`DATA.CORRECTION`, restatement, purge).
- reconciled_agent_role_registry.md (agent principals — `AGENT.*`).
- AD-004 (segregated audit store).
