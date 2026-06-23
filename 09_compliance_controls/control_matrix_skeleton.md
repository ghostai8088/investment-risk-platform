# Control Matrix Skeleton

## Document Control

| Field | Value |
|---|---|
| Document ID | COMPLIANCE-CTRLMTX-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft (skeleton — to be extended per phase) |
| Owner | R-10 Compliance & Controls AI |
| Approver | H-05 Head of Compliance (H-08 Internal Audit consulted) |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | build_rules.md, all 03–07 standards, audit_event_taxonomy.md, entitlement_sod_model.md, model_governance_independence_policy.md |
| Supported Build Rules | BR-1 … BR-16 (traceability layer) |

## 1. Purpose

Provide the control library that links each control to the capability it protects, the build rule(s) it enforces, the owning
role, the test/assurance method, and the evidence artifact. This is the traceability backbone that makes the build rules
auditable. It is a **skeleton**: controls are seeded across every framework and will be expanded per construction phase.

## 2. Schema

| Column | Meaning |
|---|---|
| Control ID | Stable `CTRL-nnn` |
| Control | Name/description |
| Type | Preventive / Detective |
| Mode | Automated / Manual / Hybrid |
| Capability | Capability map ref / bounded context |
| Build Rule | BR-n enforced |
| Owner | Accountable role (R-/H-) |
| Test / Assurance | How the control is verified |
| Evidence | Artifact proving operation |
| Status | Planned / Designed / Implemented |

## 3. Control Library (seed)

| Control ID | Control | Type | Mode | Capability | Build Rule | Owner | Test / Assurance | Evidence | Status |
|---|---|---|---|---|---|---|---|---|---|
| CTRL-001 | Every feature has tests before completion | Preventive | Automated | All | BR-1 | R-09 | CI gate; coverage report | Pipeline run, coverage | Planned |
| CTRL-002 | Every calculation has methodology doc | Preventive | Hybrid | §4–8 | BR-2 | R-06 | Doc-consistency hook | Methodology doc + QS-24 decl. | Planned |
| CTRL-003 | Every model/version inventoried before use | Preventive | Hybrid | §10 | BR-3 | R-08 | Model-inventory gate (skeleton, P1A-2): `register_model` creates a `model` + immutable `model_version` (ENT-035) with `MODEL.REGISTER`/`MODEL.VERSION` audit; a use of an unregistered `model_version` fails `assert_registered_model_version` (logic-level until calc runs bind a version, P2) | Inventory entry (ENT-035) + `MODEL.REGISTER`/`MODEL.VERSION` events + BR-3 negative test | Designed (skeleton, P1A-2) |
| CTRL-004 | Every field defined in data dictionary | Preventive | Manual | §11 | BR-4 | R-05 | Dictionary review | Data dictionary | Planned |
| CTRL-005 | Data-changing actions emit audit events | Detective | Automated | §11/12 | BR-5, BR-12 | R-07 | Audit completeness test; **data_source create/update emit `DATA.SOURCE_REGISTER`/`DATA.SOURCE_UPDATE`** (P1A-1); **model/model_version create emit `MODEL.REGISTER`/`MODEL.VERSION`** (P1A-2); **dq rule create/update emit `DATA.DQ_RULE_DEFINE`/`DATA.DQ_RULE_UPDATE`; result capture emits `DATA.VALIDATE`** (P1A-3) | Audit events (ENT-045) incl. `data_source`, `model`/`model_version`, `data_quality_rule`/`data_quality_result` | Implemented (1E + P1A-1 + P1A-2 + P1A-3, partial: calc-run + entitlement + data_source + model + dq) |
| CTRL-006 | Risk results bind full lineage (source→run) | Preventive | Automated | §4–8 | BR-6, BR-13 | R-05 | Lineage completeness test (skeleton): a recorded governed output has a complete `source→target` path retrievable by id (`record_lineage` + `GET /lineage/edges/{id}`); full source→run→result completes when calc runs exist (P2+) | Lineage edges, retrieval test | Designed (skeleton, P1A-1) |
| CTRL-007 | Manual overrides carry BR-7 fields + approval | Preventive | Automated | §11 | BR-7 | R-07 | Override schema validation | `OVERRIDE.*` events | Planned |
| CTRL-008 | Scenarios versioned with saved assumptions | Preventive | Automated | §8 | BR-8 | R-06 | Scenario version test | Scenario versions (ENT-029) | Planned |
| CTRL-009 | Reports reproducible from bound runs | Detective | Automated | §12 | BR-9 | R-09 | Report regeneration test | Report version + run ids | Planned |
| CTRL-010 | No secrets in source | Preventive | Automated | §13 | BR-10 | R-12 | Secret-scan hook | Scan results | Planned |
| CTRL-011 | No module bypasses entitlement framework; tenant isolation enforced end-to-end | Preventive | Automated | §13 | BR-11, BR-17 | R-07 | Deny-by-default tests (app) + **per-session tenant-context wiring** (`set_config` + durable pool RESET) + PG RLS tests **under a constrained non-superuser role** (visibility, fail-closed w/ SQLSTATE 42501, mismatch, isolation, recycle) + BYPASSRLS-ops-role restricted to cross-tenant ops | Entitlement + tenant-context tests, RLS migration, ops-role migration | Implemented (1E + P1A-0) |
| CTRL-012 | No module bypasses audit framework | Preventive | Automated | All | BR-12 | R-07 | Unaudited-write detection | Audit coverage report | Planned |
| CTRL-013 | No module bypasses lineage framework | Preventive | Automated | §11 | BR-13 | R-05 | BX-LIN enforcement test: a governed write lacking a lineage edge fails `assert_has_lineage` (skeleton; "governed output" stubbed via a synthetic target until domains exist) | Lineage coverage test | Designed (skeleton, P1A-1) |
| CTRL-014 | Limitations explicitly documented | Detective | Hybrid | All | BR-14 | R-10 | Limitations register review + structured capture (skeleton, P1A-2): a `model_version` records `model_limitation` rows (ENT-036, IA) retrievable from the inventory, folded into `MODEL.VERSION` audit | Limitations register; `model_limitation` rows (ENT-036) | Designed (skeleton, P1A-2) |
| CTRL-015 | Human approval gate for restricted change types | Preventive | Manual | §10/11/13 | BR-15 | H-02/H-03/H-05/H-06/H-10 | Approval-record check | `approval_ref` records | Planned |
| CTRL-016 | Material AI agent actions logged | Detective | Automated | All | BR-16 | R-07 | Agent-event completeness test | `AGENT.*` events | Planned |
| CTRL-017 | Temporal-class declared + append-only immutability of audit | Preventive | Automated | §11/12 | BR-6, BR-9, BR-19 | R-05 | Temporal-class + append-only/no-overwrite tests (audit IA; lineage_edge IA P1A-1; model EV + model_version/assumption/limitation IA P1A-2, ORM + DB trigger; data_quality_rule EV + data_quality_result IA P1A-3) | Append-only test, temporal test | Implemented (1E + P1A-1 + P1A-2 + P1A-3, audit/lineage/model/dq; **FR first exercised P1B-3** — `instrument_terms` bitemporal reconstruct-as-of; **EVT-143 `REFERENCE.STATUS_CHANGE` first exercised P1B-4** — corporate_action status lifecycle) |
| CTRL-018 | Reproduction test re-runs historical runs | Detective | Automated | §4–8 | BR-6, BR-9 | R-09 | Scheduled reproduction job (TR-13) | Reproduction report | Planned |
| CTRL-019 | Decimal-safe money; no float for currency | Preventive | Automated | §4–8 | BR-2 | R-06 | Static/type checks (QS-01) | Lint/test results | Planned |
| CTRL-020 | Deterministic seeds recorded for MC | Preventive | Automated | §4/6/8 | BR-6 | R-06 | Seed-binding test (QS-18) | Run parameters | Planned |
| CTRL-021 | SoD pairs enforced (maker≠checker) | Preventive | Automated | §13 | BR-7, BR-15 | R-07 | SoD conflict test (SOD-01…08) | SoD test results | Planned |
| CTRL-022 | Independent model validation (dev≠validator) | Preventive | Manual | §10 | BR-15 | H-02 | Validation independence review | Validation record (ENT-037) | Planned |
| CTRL-023 | Data classification + MNPI barriers enforced | Preventive | Hybrid | §3/13 | BR-11 | R-07/H-05 | Barrier access tests | Denied-access audit | Planned |
| CTRL-024 | Export controls (DC-4 blocked by default) | Preventive | Automated | §13 | BR-11 | R-07 | Export-control test | `EXPORT.*` events | Planned |
| CTRL-025 | Entitlement changes maker-checked + audited | Preventive | Automated | §13 | BR-7, BR-11 | R-07 | Entitlement-change test | `ENTITLEMENT.*` events | Planned |
| CTRL-026 | Audit store append-only + hash-chain integrity + concurrency-safe + verifiable | Preventive/Detective | Automated | §12 | BR-12, BR-18 | R-12 | Hash-chain verify + tamper-detection + append-only (app + PG trigger); per-tenant advisory-lock concurrency test (PG, gapless under N threads); audit-verify ops CLI | Audit tests, concurrency test, `audit_verify` CLI, migration trigger | Implemented (1E + P0.5) |
| CTRL-027 | Data quality rules run on ingest | Detective | Automated | §11 | BR-5 | R-05 | **Realized on a real ingest path (P1A-4):** `POST /ingest/upload` runs active generic staging rules over staged rows via `run_quality_check` and gates with `assert_passed_quality_checks` (ERROR rejects the batch, WARNING flags) — DQ-rule engine skeleton from P1A-3 (pluggable `DQRule.evaluate()`, `data_quality_result` ENT-039 IA + `DATA.VALIDATE`) | DQ results (ENT-039, `ingestion_batch_id` populated) + `DATA.VALIDATE` events + on-ingest no-silent-failure test (`test_ingest_endpoint`/`test_ingestion`) | Implemented (on-ingest, P1A-4) |
| CTRL-028 | Reconciliation of sources | Detective | Hybrid | §11 | BR-6 | R-05 | Recon job | Recon results (ENT-040) | Planned |
| CTRL-029 | Stale/missing data flagged, not silently filled | Preventive | Automated | §3/4–8 | BR-2, BR-14 | R-06 | Missing-data handling test (QS-15/16); **no-silent-failure framework** (P1A-3, QS-06): a failing/errored DQ rule surfaces as a raised exception or a persisted flagged `data_quality_result` and is audited (`DATA.VALIDATE`, `outcome='failure'`) — never silently passes/swallowed | Flagged records; `data_quality_result` rows + `DATA.VALIDATE` failure events | Designed (skeleton, P1A-3); **first reference-domain exercise P1B-3** — `resolve_identifier` returns one / `None` / `AmbiguousIdentifier`, never a silent arbitrary match (REQ-SMR-003 / OD-P1B-G) |
| CTRL-030 | Production change approval (release gate) | Preventive | Manual | §13 | BR-15 | H-10 | Release-readiness review | Go/no-go record | Planned |
| CTRL-031 | Breach workflow enforces 1L/2L separation | Preventive | Hybrid | §9 | BR-7 | R-01/H-01 | Workflow state test (SOD-02) | `BREACH.*` events | Planned |
| CTRL-032 | Failed audit capture blocks governed change | Preventive | Automated | All | BR-12 | R-07 | Fail-closed test (AUD-04) | Test results | Planned |
| CTRL-033 | Schema/migration drift gate (models vs migrations) | Preventive | Automated | §11 | BR-4, BR-19 | R-12 | `alembic check` in CI migration job (structural drift) | CI migration job | Implemented (P0.5) |

## 4. Coverage Note

Every build rule BR-1 … BR-19 is covered by at least one control above. The Step 1C rules map to existing controls: **BR-17**
(tenant isolation) → CTRL-011/CTRL-023; **BR-18** (audit hash-chain integrity) → CTRL-026/CTRL-032; **BR-19** (temporal-class
conformance) → CTRL-017/CTRL-018. **P0.5** additions: reproducible frontend builds → CTRL-001 (`npm ci`); audit-write
concurrency + verification ops CLI → CTRL-026; schema-drift gate → **CTRL-033**; entitlement bootstrap seed (baseline catalog +
role templates) underpins CTRL-011/CTRL-025. **P1A-1** additions: the `data_source` (EV) + `lineage_edge` (IA) skeleton makes
**BX-LIN** executable — `record_lineage`/`assert_has_lineage` + `GET /lineage/edges/{id}` under P1A-0 tenant context move
**CTRL-006/CTRL-013** to Designed (skeleton); `data_source` create/update audit (`DATA.SOURCE_REGISTER`/`DATA.SOURCE_UPDATE`)
extends **CTRL-005**; the new deny-by-default `lineage.source.manage` permission + FORCE-RLS (USING + WITH CHECK) on both tables,
proven under the constrained `irp_app` role, underpin **CTRL-011**. **P1A-2** additions: the `model` (EV) +
`model_version`/`model_assumption`/`model_limitation` (IA) registry skeleton makes **BR-3 model-inventory** executable —
`register_model`/`assert_registered_model_version` + the inventory reads move **CTRL-003** and **CTRL-014** to Designed (skeleton);
`model`/`model_version` create audit (`MODEL.REGISTER`/`MODEL.VERSION`, reusing existing codes) extends **CTRL-005/012/017/032**;
no new permission (`model.inventory.register`→`risk_analyst_1l`/`platform_admin`) or audit code. **CTRL-022** (validation
independence) and **CTRL-015** (approval gate) remain **Planned** — no validation/approval workflow in P1A-2 (governance fields are
non-enforcing placeholders). **P1A-3** additions: the `data_quality_rule` (EV) + `data_quality_result` (IA) skeleton with a
pluggable `DQRule.evaluate()` engine (2 generic rules) and `assert_passed_quality_checks()` gate makes **DEP-DQF / REQ-DQR-001**
executable — moves **CTRL-027** and **CTRL-029** to Designed (skeleton); rule create/update audit (`DATA.DQ_RULE_DEFINE`/
`DATA.DQ_RULE_UPDATE`) and result capture (`DATA.VALIDATE`) extend **CTRL-005/012/017/032**; no new permission
(`dq.rule.manage`→data_steward, `dq.result.view` broad — already bootstrapped, no role change). **CTRL-028** (reconciliation,
REQ-DQR-002/P7) and the manual-override/SoD controls (**CTRL-007/021**, REQ-DQR-003/P7) remain **Planned** — no reconciliation or
override workflow in P1A-3. **P1A-4** additions: generic ingestion staging (`ingestion_batch` ENT-047 IA-status-mutable +
`ingestion_staged_record` ENT-048 IA, REQ-INT-001) makes **CTRL-027** **Implemented (on-ingest)** — `POST /ingest/upload` runs DQ
over staged rows and gates the batch; **CTRL-029** gains first real on-ingest no-silent-failure evidence (a DQ ERROR persists a
REJECTED batch + flagged result + `DATA.INGEST`/`DATA.VALIDATE` audit, never silently rolled back) but stays **Designed**;
**CTRL-013** (lineage no-bypass) is exercised non-synthetically (a `data_source → ingestion_batch` ORIGIN edge + `assert_has_lineage`
on every batch); the `DATA.INGEST` lifecycle (create + per-transition `status_change`) extends **CTRL-005/011/012/017/032**;
anti-corruption file controls realize **THR-05/THR-06** at skeleton level (AV deferred, OD-042). **No new audit code, no new
permission, no role change** (`data.upload` already bootstrapped). **CTRL-028** (reconciliation) and **CTRL-007/021**
(override/SoD) remain **Planned** — no canonical mapping, reconciliation, or override workflow in P1A-4. **P1B-1** additions:
the first reference-data slice (`currency` ENT-005, `calendar`+`calendar_holiday` ENT-006, `rating_scale`+`rating_grade` ENT-007
taxonomy; REQ-SMR-005 + REQ-SMR-004 calendar) and the platform's **first asymmetric hybrid RLS** (AD-013-R1). **CTRL-004**
(data-dictionary field definitions) moves toward Designed via the ISO-4217 `code` shape / MIC / agency / minor_units field
definitions. **CTRL-011** is extended by the five additive reference permissions AND the **first hybrid-RLS evidence**
(own+SYSTEM read; single-tenant `WITH CHECK` write; no-context-global; structural `pg_policies` asymmetry + closed-set tests in
`test_reference_pg`). **CTRL-005/012** gain `REFERENCE.CREATE` (EVT-140) / `REFERENCE.UPDATE` (EVT-141) coverage (children fold
in). **CTRL-017** coverage for these EV entities is the `__temporal_class__ = EFFECTIVE_DATED` declaration test, **NOT**
append-only (EV, not IA). **CTRL-032** gains first reference-CRUD fail-closed evidence (parent + children + lineage edge roll
back together when `record_event` raises). **CTRL-013** is exercised again (one MANUAL-`data_source` ORIGIN edge per reference
entity). **Label note (R-10):** tenant-isolation/RLS evidence attaches to **CTRL-011**, not the mis-seeded **CTRL-003** (whose
matrix label is model-inventory) — flagged, not silently edited. **No new audit framework code** (`record_event` FROZEN),
**no `data_source` hybrid**, **no rating ASSIGNMENTS / `reference.rating.*`**. **P1B-2** additions: the second SMR slice
(`legal_entity` core + `issuer` ENT-002 + `counterparty` ENT-003 1:1 role profiles; REQ-SMR-002) is the **proprietary-never-hybrid
evidence** (the inverse of P1B-1). **CTRL-011** is extended by the additive `reference.legal_entity.*` permissions AND
**symmetric RLS on three proprietary tables** (`USING == WITH CHECK == own-tenant`; no-context read → zero rows; a positive
`pg_policies` symmetric+FORCE-RLS assertion + the unchanged closed-hybrid-set test prove these are NOT hybrid). **CTRL-004** advances
via LEI (ISO-17442) / jurisdiction (ISO-3166) / entity_type field shapes. **CTRL-005/012** gain `REFERENCE.CREATE`/`.UPDATE` on the
three entities (each its **own** event). **CTRL-017** = the EV `__temporal_class__` declaration test. **CTRL-032** gains
per-entity CREATE **and** UPDATE fail-closed evidence (entity + profile + lineage + lazily-created MANUAL source roll back; an
UPDATE's mutated attributes + `record_version` revert). **CTRL-013** = one MANUAL-`data_source` ORIGIN edge per entity. The
proprietary-identity SoD is honoured (`legal_entity.view` excludes `auditor_3l`, matching `issuer`/`counterparty.view`). **No new
audit framework code; no hybrid/SYSTEM_TENANT; no netting/CSA/exposure column or calc.** **P1C-0 ratification (AD-017,
2026-06-23):** the planned P1C-1 portfolio-hierarchy slice will exercise **CTRL-001** (tests-before-completion), **CTRL-004**
(`portfolio` columns + `node_type`/`status` vocab field defs), **CTRL-005/012** (new `PORTFOLIO.CREATE`/`.UPDATE` — **RESERVED**
at the EVT-150 block, activated caller-side in the build; `audit/service.py` FROZEN), **CTRL-006/013** (one MANUAL-`data_source`
ORIGIN edge per portfolio), **CTRL-011** (deny-by-default `portfolio.view`/`.edit` + symmetric proprietary RLS on `portfolio`,
never hybrid), **CTRL-017** (EV `__temporal_class__` declaration), and **CTRL-032** (fail-closed audit). **No new CTRL minted; no
audit code / permission / role / migration minted at ratification (all RESERVED for the P1C-1 build).** ABAC portfolio scope is
**anchored, not enforced** (enforcement P6+). As construction phases
open, controls will be split to specific bounded contexts and capabilities and given Test/Evidence detail.

## 5. Open Decisions

| ID | Open Decision |
|---|---|
| OD-036 | Add capability IDs (CAP-x.y) to capability_map.md so controls map 1:1 to capabilities. |
| OD-037 | Confirm regulatory mapping layer (which regimes/controls frameworks, e.g., SOC 2, ISO 27001) for buyer due diligence. |
| OD-038 | Confirm control testing cadence and independent assurance owner (H-08) per control. |

## 6. Dependencies

- build_rules.md (BR-1 … BR-16).
- audit_event_taxonomy.md, entitlement_sod_model.md, model_governance_independence_policy.md, temporal_reproducibility_standard.md, numerical_quant_standards.md (control mechanisms).
- capability_map.md (capability IDs — OD-036).
