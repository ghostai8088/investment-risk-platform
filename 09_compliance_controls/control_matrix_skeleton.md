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
| CTRL-003 | Every model/version inventoried before use | Preventive | Hybrid | §10 | BR-3 | R-08 | Model-inventory gate: `register_model`/`register_model_version` create a `model` + immutable `model_version` (ENT-035) with `MODEL.REGISTER`/`MODEL.VERSION` audit. **EXECUTABLE in P3-1 (2026-06-30):** the first model-driven run (`run_sensitivities`, ENT-028) calls **`assert_registered_model_version` in the PRE-CREATE gate** — an unregistered `model_version_id` raises `UnregisteredModelError` BEFORE the run is created ⇒ zero run/result/audit (no risk number escapes the inventory). | Inventory entry (ENT-035) + `MODEL.REGISTER`/`MODEL.VERSION` events + BR-3 negative test (`test_unregistered_model_version_refused_pre_create_zero_run_zero_rows`) | **Operational (P3-1: load-bearing at the first model-driven run)** |
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
audit framework code; no hybrid/SYSTEM_TENANT; no netting/CSA/exposure column or calc.** **P1C-1 (AD-017, REQ-PPM-001,
2026-06-23):** the portfolio-hierarchy slice (migration `0012`) **exercises** **CTRL-001** (tests-before-completion: the SQLite
logic + endpoint + PG suites), **CTRL-004** (`portfolio` columns + `node_type`/`status` vocab field defs), **CTRL-005/012**
(`PORTFOLIO.CREATE`/`.UPDATE` **ACTIVATED** at the EVT-150 block caller-side; `audit/service.py` FROZEN), **CTRL-006/013**
(one MANUAL-`data_source` ORIGIN edge per portfolio create; amend roots none), **CTRL-011** (deny-by-default
`portfolio.view`/`.edit` + symmetric proprietary RLS on `portfolio`, never hybrid; the constrained-`irp_app` PG tests),
**CTRL-017** (EV `__temporal_class__` declaration), and **CTRL-032** (fail-closed audit rollback). **No new CTRL minted.**
`PORTFOLIO.*`, the `data_steward` `portfolio.*` grant, and migration `0012` are minted in **code** in this build (the
P1C-0 ratification only reserved them; `audit/service.py` stays FROZEN). ABAC portfolio scope is **anchored, not enforced**
(enforcement P6+; the descendant resolver records subtree semantics, the endpoints apply no scope filter — a tested fence).
**P1C-2 (REQ-PPM-003 transaction conjunct, AD-017, 2026-06-24):** the `transaction` IA append-only slice (migration `0013`)
is the **first DOMAIN append-only entity** — it exercises **CTRL-017** with new force (the `irp_prevent_mutation` P0001
trigger + the ORM `before_update`/`before_delete` guard, proven by the PG trigger test that grants `irp_app` UPDATE/DELETE so
the rejection is the **P0001 trigger**, not a 42501 privilege denial), **CTRL-012** (no audit bypass — `TRANSACTION.RECORD`/
`.REVERSE` EVT-160/161 on every record), and **CTRL-001/004/005/006/011/032** (tests / data-dict / audit / lineage /
deny-by-default + RLS / fail-closed rollback). New `transaction.view`/`transaction.record` perms (`data_steward` maker;
`auditor_3l` excluded); `audit/service.py` FROZEN. **Capture-only** — corrections are explicit reversal records, no position
derivation / cashflow engine / valuation / exposure calc.
**P1C-3 (REQ-PPM-002, AD-005 §2A, 2026-06-25):** the `position` **FR bitemporal** slice (migration `0014`) is the **first FR
DOMAIN entity** (second FR entity after the P1B-3 `instrument_terms`). It exercises **CTRL-017 with the FR reading**:
temporal-class **declared** (`FULL_REPRODUCIBLE`) ✓, but **append-only immutability does NOT apply** — `position` is **NOT** in
`APPEND_ONLY_TABLES` and has **no** `irp_prevent_mutation` trigger (the FR protocol requires close-out UPDATEs); prior-version
CONTENT immutability is **service-enforced + test-proven** (the PG test asserts a close-out UPDATE returns `rowcount == 1`,
the inversion of the transaction P0001 guard). Also **CTRL-012** (no audit bypass — `POSITION.CREATE`/`.UPDATE`/`.CORRECTION`
EVT-170/171/172 on every governed write) and **CTRL-001/004/005/006/011/032** (tests / data-dict / audit / lineage /
deny-by-default + symmetric RLS / fail-closed rollback). New `position.edit` perm minted + existing `position.view` grant
extended to `data_steward` (maker; `auditor_3l` excluded); `audit/service.py` FROZEN. **Capture-only** — positions are captured
directly, **NOT derived from transactions** (no transaction FK, no derivation engine); no market value / valuation / exposure /
holdings-view / dataset_snapshot.
**P1C-4 (REQ-PPM-003 valuation conjunct, AD-005 §2A / OD-P1C-F, 2026-06-25):** the `valuation` **FR bitemporal** slice
(migration `0015`) is the **second FR DOMAIN entity** (captured marks). It exercises **CTRL-017 with the FR reading**
(temporal-class declared `FULL_REPRODUCIBLE` ✓; append-only does **NOT** apply — `valuation` is **not** in any
`APPEND_ONLY_TABLES`/`irp_prevent_mutation` trigger loop; prior-version content immutability is **service-enforced +
test-proven** via the PG close-out-UPDATE `rowcount==1` proof), **CTRL-012** (no audit bypass — `VALUATION.CREATE`/`.UPDATE`/
`.CORRECTION` EVT-180/181/182 on every governed write), and **CTRL-001/004/005/006/011/032** (tests / data-dict / audit /
lineage / deny-by-default + symmetric RLS / fail-closed rollback). Both `valuation.view`/`valuation.edit` perms newly minted
(`data_steward` maker; `auditor_3l` excluded); `audit/service.py` FROZEN. **Captured marks** — `mark_value` captured (never
computed), `mark_source` an inert label; **NO valuation/pricing model, NO price lookup, NO market-data, NO market-value rollup
(no `position` FK / no `quantity`), NO exposure aggregation, NO holdings view, NO dataset_snapshot**. `valuation_date` is an
immutable logical-key column (OD-P1C-F). This jointly with the P1C-2 transaction conjunct **closes REQ-PPM-003 (Done)**. As
construction phases

**P1C-5 (read half of REQ-PPM-001/002, AD-017 / OD-P1C-A/B/F/G/H, 2026-06-25):** the as-of holdings / portfolio **views** slice
is a **read-only composition** (new `irp_shared/holdings/` read-model package + `GET /portfolios/{id}/holdings`) — it adds
**NO entity, NO migration, NO permission, NO audit event, NO lineage/DQ write** (`migration_head` stays `0015_valuation`). It
exercises **CTRL-001** (tests), **CTRL-004** (response fields in the data dictionary), and **CTRL-011** as its primary control
(deny-by-default `portfolio.view` + `position.view`; `valuation.view` in-handler before any mark lookup; tenant isolation via
inherited symmetric FORCE-RLS on `position`/`portfolio`/`valuation`; no BYPASSRLS). The write-side controls **do NOT apply** to
a pure read: **CTRL-005/012** (audit emit), **CTRL-006/013** (lineage bind/no-bypass), **CTRL-032** (fail-closed audit rollback)
— and a tested **zero-audit-write** assertion proves it. Subtree traversal reuses the bounded cycle-safe descendant resolver as
**read composition, NOT ABAC enforcement** (anchor-not-enforce → P6+). **CTRL-017** applies to the underlying captured FR
entities (already declared), not to the read DTOs. **Capture-only fences (load-bearing scope test):** NO aggregation / sum /
rollup / total / weight, NO `market_value` or `quantity × mark_value`, NO exposure, NO `dataset_snapshot`, NO risk/pricing/
valuation model, NO market-data/price lookup, NO position-from-transaction derivation, NO corporate-action application. Marks
are **display-only** (opt-in, deterministic by an explicit `valuation_date`). **No REQ status change** (read-composition over
already-satisfied capture; REQ-PPM-002 stays In-Progress, ABAC residual → P6+). As construction phases

**P1C-6 (deterministic synthetic dataset, OD-P1C-L REALIZED / AD-017, 2026-06-25):** a **labeled, never-auto-run** synthetic-data
seed (new `irp_shared/synthetic/` package — `build_synthetic_dataset`) that builds a small reproducible demo dataset **through the
governed binders**, so every seeded row **PRESERVES** the production controls: **CTRL-005/012** (each row emits its `*.CREATE`/
`RECORD` audit event; `verify_chain` passes), **CTRL-006/013** (each row roots its MANUAL-source ORIGIN lineage edge;
`assert_has_lineage`), **CTRL-011** (writes only under the reserved SYNTHETIC tenant context — symmetric FORCE-RLS, **never
BYPASSRLS**; a different tenant sees zero synthetic rows), plus **CTRL-001** (the determinism / governed-path / guard tests). **No
control is weakened.** It adds **NO entity, NO migration** (`migration_head` stays `0015_valuation`), **NO HTTP endpoint, NO
permission, NO audit-code** (`audit/service.py` FROZEN); the only shared-package change is a **narrow, keyword-only, default-None
deterministic-injection seam** (`entity_id` / `now`) on the governed binders — **production call sites are byte-for-byte unchanged**
(test-proven). Determinism: `uuid5` ids + an injected fixed seed clock; an **AST fence** forbids `datetime.now`/`utcnow`/`uuid4`/
`new_uuid`/`uuid1`/`random` in the seed module + any multiplication (no `quantity × mark` / market value / exposure — capture-only).
**Never-auto-run** is enforced architecturally (not in migrations/startup) + an explicit confirm-flag + an `IRP_ALLOW_SYNTHETIC_SEED=1`
env gate + a refuse-non-synthetic-tenant guard (all tested). Synthetic-only data (DC-1/DC-2 demo fixtures): `SYNTH_*`/neutral names,
no real vendor/agency/client names, no real ISIN/CUSIP/SEDOL/LEI. **No REQ status change.** As construction phases
open, controls will be split to specific bounded contexts and capabilities and given Test/Evidence detail.

**P2-0 / P2-1 (reproducible input snapshot — `dataset_snapshot`, AD-014; ratified 2026-06-26, REALIZED in P2-1 `3629baa`, migration `0016_dataset_snapshot`):** the
P2 reproducibility primitive (ENT-049 `dataset_snapshot` + ENT-050 `dataset_snapshot_component`) is **ratified into governance**
(`p2_0_decision_record.md` + `p2_1_dataset_snapshot_implementation_plan.md`). Control mapping (activated at the P2-1
implementation): **CTRL-009** (reproducibility — the snapshot
**pins input record versions + a SHA-256 manifest hash** so a later run reproduces; **AD-014: no official derived number is
produced before snapshot/run binding** — P2-1 produces **none**, exposure binds `calculation_run` at P2-3); **CTRL-017** (the
**IA TRUE-append-only** reading — both tables in `APPEND_ONLY_TABLES` + the `irp_prevent_mutation` P0001 trigger + ORM
`before_update`/`before_delete` guard, the `transaction` precedent; **distinct** from the status-mutable `calculation_run`);
**CTRL-006/013** (lineage — a **narrow internal snapshot/component lineage writer** roots one `data_snapshot`-sourced ORIGIN
edge per pinned input; **not** a broad lineage-framework rewrite); **CTRL-011/023** (tenant isolation — **symmetric** FORCE-RLS,
**never hybrid/SYSTEM_TENANT**; **cross-tenant component binding FAILS CLOSED** via the explicit-tenant-predicate resolvers,
whole-unit rollback, on SQLite **and** PG); **CTRL-032** (fail-closed co-transactional governed write — snapshot + audit
(`SNAPSHOT.CREATE`, reserved) + lineage + the **caller-side completeness DQ gate** (reuses `run_quality_check` / `DATA.VALIDATE`,
**no DQ-protocol change**; a coverage gap fails closed and **prevents snapshot creation**)). `audit/service.py` stays **FROZEN**;
`entitlement/bootstrap.py` UNCHANGED. **No control is weakened; no new CTRL minted** (existing controls gain a planned P2-1
binding).

**P2-2 additions (FX market data — `fx_rate`, ENT-024, IMPLEMENTED `0017_fx_rate`, 2026-06-26):** captured vendor FX (FR) +
a pure published-rate `convert` (no analytics). Controls now executable for FX: **CTRL-006/013** (lineage — one VENDOR
`data_source` ORIGIN edge per physical version, reusing `record_lineage` unchanged); **CTRL-011** (deny-by-default
`marketdata.view`/`.ingest` + symmetric FORCE-RLS, PG-proven as `irp_app`; a new **Snapshot/FX symmetric-RLS CI step** + a new
migration); **CTRL-023** (vendor-licensed FX tenant-scoped — NEVER hybrid; closed 5-table hybrid set asserted unchanged);
**CTRL-017** (`fx_rate` declares `FULL_REPRODUCIBLE`; NOT append-only); **CTRL-026** (`MARKET.FX_*` hash-chain `verify_chain`);
**CTRL-032** (fail-closed co-transactional rollback if audit/lineage/DQ raises). The DQ no-silent-failure gate gains an
**additive generic `RANGE` evaluator** (strictly-positive rate) — `(params, dataset)` Protocol **unchanged**, the two shipped
evaluators behavior-unchanged. **CTRL-009 / the AD-014 gate are UNTOUCHED** — FX produces no governed derived number (exposure
stays P2-3, snapshot+run-gated). `audit/service.py` **FROZEN**. **No control weakened; no new CTRL minted.**

**P2-3 ratification (basic exposure + `calculation_run` wiring — `exposure_aggregate` ENT-014, RATIFIED-IN-PLANNING 2026-06-26;
AD-018; REALIZED `da178fc`, migration `0018_exposure_aggregate`):** the platform's **FIRST official governed derived number**, which makes the
**AD-014 / FW-RUN §5 / TR-15 gate LOAD-BEARING** (it had no producer before P2-3). Control bindings (all to **existing** CTRLs —
**no control weakened, no new CTRL minted**): **CTRL-009 becomes EXECUTABLE** (no official derived number without a `dataset_snapshot`
+ a complete `calculation_run` — `input_snapshot_id` non-null + `code_version` + the additive `environment_id`; reproducible from the
snapshot-pinned captured content per TR-09); **CTRL-006/018** (run-binding + lineage — the `dataset_snapshot → calculation_run`
(`DEPENDS_ON`) + `calculation_run → exposure_aggregate` (`ORIGIN`, `run_id`-stamped) edges, via the generalized internal-lineage
writer); **CTRL-013** (no lineage bypass); **CTRL-017** (`exposure_aggregate` declares `IMMUTABLE_APPEND_ONLY`, in
`APPEND_ONLY_TABLES` + P0001 trigger + ORM guard — append-only derived result); **CTRL-011/023** (deny-by-default `exposure.view` /
`exposure.aggregate.run` + symmetric FORCE-RLS, NEVER hybrid; a new **exposure symmetric-RLS CI step**); **CTRL-026** (the run reuses
the `CALC.RUN_CREATE`/`CALC.RUN_STATUS_CHANGE` hash-chain — `verify_chain`); **CTRL-032** (fail-closed: a **pre-create refusal** = ZERO
run/result/audit; a **post-create FAILED** run = committed FAILED run + ZERO result; an emit-path failure rolls the whole unit back).
DQ gates fail closed **before any result write** (snapshot completeness + FX completeness + valuation-mark-required + cross-tenant) —
reusing `run_quality_check`/`DATA.VALIDATE`, the `(params, dataset)` Protocol **unchanged**. **NO-RISK BOUNDARY:** exposure is **signed
market value v1** (`MARKET_VALUE` only) — **NOT** VaR/Expected Shortfall/factor/sensitivity/scenario/stress/P&L/performance; those stay
P3+. The additive `calc/service.py` `outcome` param is the only calc change; `audit/service.py` **FROZEN**.

**P3-2 additions (factor-return inputs — net-new `factor` EV definition + `factor_return` FR series, ENT-025, IMPLEMENTED
`0023_factor_return`; committed `402cb12`, CI #89 green):**
captured vendor/external factor returns (FR) + a net-new EV definition — the same captured-market-data control pattern as
`fx_rate`/`price_point`/`curve`/`benchmark` (**no control weakened; no new CTRL minted; the `factor.*` permission space is NOT
minted — `marketdata.view`/`.ingest` REUSED**). Controls now executable for factor: **CTRL-006/013** (lineage — one VENDOR_FACTOR
`data_source` ORIGIN edge per captured version, reusing `record_lineage` unchanged); **CTRL-011** (deny-by-default
`marketdata.view`/`.ingest` + symmetric FORCE-RLS, PG-proven as `irp_app` in `test_factor_pg.py`); **CTRL-023** (vendor-licensed
factor data tenant-scoped — NEVER hybrid; closed 5-table hybrid set asserted unchanged); **CTRL-017** (`factor_return` declares
`FULL_REPRODUCIBLE`, `factor` declares `EFFECTIVE_DATED`; **NEITHER append-only** — no `irp_prevent_mutation` trigger, the `benchmark`
precedent); **CTRL-026** (`REFERENCE.*` definition + `MARKET.FACTOR_RETURN_*` series hash-chain `verify_chain`); **CTRL-032**
(fail-closed co-transactional rollback if audit/lineage/DQ raises). The DQ gate reuses the generic `NOT_NULL` + `RANGE` evaluators
(a `> -1` economic-sanity floor) — `(params, dataset)` Protocol **unchanged**; a **binder-side finiteness guard** rejects NaN/±Inf
BEFORE any write (the min-only RANGE does not catch +Inf). **CTRL-009 / the AD-014 gate are UNTOUCHED** — a captured factor return
is an **INPUT**, not a governed derived number (**NO `calculation_run`, NO `model_version`, NO snapshot pin**); computed factor
returns are DEFERRED (would re-engage CTRL-003/009 with a registered `model_version` — the ENT-028 `sensitivity_result` precedent).
`audit/service.py` **FROZEN**. **No control weakened; no new CTRL minted.**

**P3-3 additions (factor-exposure engine — `factor_exposure_result`, ENT-028 family, IMPLEMENTED
`0024_factor_exposure`):** the SECOND governed derived risk number — indicator-loading allocation exposures over pinned
`exposure_aggregate` atoms × pinned `factor` EV definitions (**no control weakened; no new CTRL minted; NO new permission —
`risk.view`/`risk.run` REUSED**). Controls exercised: **CTRL-003** (inventory-before-use — `assert_registered_model_version`
pre-create on the SECOND model-driven run family, `risk.factor_exposure.allocation` v1; an unregistered version = zero
run/rows/audit, negative-tested); **CTRL-002/014** (the `factor_exposure_allocation_v1.md` methodology doc + mirrored
assumption/limitation rows); **CTRL-009** (governed output — non-null `input_snapshot_id` + complete `calculation_run`;
snapshot-only compute); **CTRL-017** (IA TRUE append-only — `APPEND_ONLY_TABLES` + P0001 trigger + ORM guard, PG-proven);
**CTRL-018/TR-13** (reproduction — re-run over the same snapshot identical; invariant under a later factor amend / exposure
re-run); **CTRL-006/013** (lineage — `snapshot --DEPENDS_ON--> run --ORIGIN--> result`, the DEPENDS_ON edge kept on a FAILED
run); **CTRL-011/023** (deny-by-default reused `risk.*` + symmetric FORCE-RLS, NEVER hybrid; closed 5-table hybrid set
asserted unchanged); **CTRL-026** (`CALC.RUN_*` hash chain — `verify_chain`); **CTRL-029/032** (fail-closed
`risk.factor_exposure.completeness` DQ — an unmapped atom ⇒ committed FAILED run + ZERO rows, no silent residual; Protocol
untouched; co-transactional rollback). The `RISK.*` family stays reserved-not-emitted (`RISK.FACTOR_EXPOSURE_CREATE` joins
`RISK.SENSITIVITY_CREATE`). `audit/service.py` **FROZEN**.

**P3-4 additions (covariance engine — `covariance_result`, ENT-051, IMPLEMENTED `0025_covariance`):** the THIRD governed
derived risk number — the equal-weighted unbiased sample covariance matrix over pinned factor-return windows (**no control
weakened; no new CTRL minted; NO new permission — `risk.view`/`risk.run` REUSED**). Controls exercised: **CTRL-003**
(inventory-before-use with model IDENTITY — `assert_model_version_of` pre-create on the THIRD model family,
`risk.covariance.sample` v1; an unregistered OR wrong-family version = zero run/rows/audit, both negative-tested);
**CTRL-002/014** (the `covariance_sample_v1.md` methodology doc + mirrored assumption/limitation rows **including the
registration-declared `window_observations=N`** — the window is version identity, a same-label different-window re-register
is a governed 409, never a silent re-point); **CTRL-009** (governed output — non-null `input_snapshot_id` + complete
`calculation_run`; snapshot-only compute over `COMPONENT_KIND_FACTOR_RETURN` pins); **CTRL-017** (IA TRUE append-only —
`APPEND_ONLY_TABLES` + P0001 trigger + ORM guard, PG-proven); **CTRL-018/TR-13** (reproduction — same-snapshot re-run
byte-identical; **invariant under a post-pin vendor supersede AND correction** of a window return; **the dual-path
verification standing rule's first discharge**: hand-computed exact rational references + an independent `numpy.cov(ddof=1)`
cross-check at `ε_rel = 1e-9` + eigenvalue-PSD property tests at `λ_min ≥ −1e-12·trace` — numpy TEST-ONLY, import-fenced out
of the `irp_shared` runtime); **CTRL-006/013** (lineage — `snapshot --DEPENDS_ON--> run --ORIGIN--> result`, DEPENDS_ON kept
on a FAILED run); **CTRL-011/023** (deny-by-default reused `risk.*` + symmetric FORCE-RLS, NEVER hybrid; closed 5-table
hybrid set asserted unchanged); **CTRL-026** (`CALC.RUN_*` hash chain — `verify_chain`); **CTRL-029/032** (fail-closed
window/alignment gates on BOTH entry paths — fewer than N common dates ⇒ pre-create refusal with ZERO writes, **no
imputation, no pairwise deletion**; a short/misaligned/wrong-N/unpaired pinned snapshot refused at adjudication; the
defensive output-sanity DQ `risk.covariance.completeness` ⇒ committed FAILED run + ZERO rows; co-transactional rollback).
The `RISK.*` family stays reserved-not-emitted (`RISK.COVARIANCE_CREATE` joins the row). `audit/service.py` **FROZEN**.

**P3-5 additions (parametric VaR — `var_result`, ENT-027 realized, IMPLEMENTED `0026_var`):** the FOURTH governed
derived risk number and the FIRST derived-of-derived one (**no control weakened; no new CTRL minted; NO new permission —
`risk.view`/`risk.run` REUSED**). Controls exercised: **CTRL-003** (inventory-before-use with model IDENTITY on the
FOURTH family, `risk.var.parametric` v1 — incl. the DECLARED confidence/horizon/z: a malformed/absent/tampered
declaration (mintable via the generic registration) is a fail-closed identity refusal, never a parse crash);
**CTRL-002/014** (the `var_parametric_v1.md` methodology + mirrored declarations incl. the radicand tolerance and the
**specific-risk = 0** first-class limitation); **CTRL-009** (governed output — snapshot-only compute over the pinned
result rows of TWO upstream governed runs; hard-FK provenance columns); **CTRL-017** (IA TRUE append-only, PG-proven);
**CTRL-018/TR-13** (reproduction — exact hand references through kernel AND the governed consume path; the numpy float
cross-check; the erf round-trip z-constant verification; pin INVARIANCE under upstream re-runs); **CTRL-006/013**
(lineage — DEPENDS_ON kept on FAILED); **CTRL-011/023** (deny-by-default reused `risk.*` + symmetric FORCE-RLS, NEVER
hybrid; the hybrid probe uses the REAL system-tenant id + set EQUALITY); **CTRL-026** (`CALC.RUN_*` chain);
**CTRL-029/032** (fail-closed COVERAGE/consistency adjudication on BOTH paths — an uncovered exposure factor, mixed-run
rows, mixed base currency, or wrong vocabulary refuse pre-create with ZERO writes, **NO zero-variance imputation**; the
REACHABLE non-PSD radicand gate ⇒ committed FAILED run + DQ evidence + ZERO rows). The `RISK.*` family stays
reserved-not-emitted (`RISK.VAR_CREATE` joins the row). `audit/service.py` **FROZEN**.

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
