# Phase P1 Scoping Plan

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1SCOPE-001 |
| Version | 0.1 (Draft) |
| Status | Proposed for approval (planning only — no code) |
| Owner | R-01 Product Manager AI (with R-02 Chief Architect AI) |
| Approver | H-07 Product Owner (H-06 Engineering Lead) |
| Created | 2026-06-18 |
| Last Reviewed | 2026-06-18 |
| Related Documents | ../02_requirements/requirements_backbone.md, ../02_requirements/requirements_traceability_matrix.md, ../02_requirements/definition_of_ready_done.md, build_sequence.md, ../03_architecture/foundation_slice.md |
| Supported Build Rules | BR-1 … BR-19 |

## 1. Recommendation (split decision)

**Split P1 into four subphases, built in this order: P0.5 → P1A → P1B → P1C.** The boundaries follow clean dependency cuts and
keep each subphase independently DoD-able and reviewable:

- **P0.5 Engineering hygiene** must precede the first schema-adding domain work so the first governed writes land on a
  byte-stable CI baseline with reproducible migrations and concurrency-safe audit.
- **P1A skeletons (lineage / model registry / DQ / ingestion)** build the *rails* every domain write rides; they must exist
  before any domain entity so BX-LIN/BX-DOC/BX-AUD are enforceable from the first row.
- **P1B Security Master & Reference Data** is the dependency root for all risk; it stabilizes the first real **FR (bitemporal)**
  domain pattern before positions consume it.
- **P1C Portfolio & Positions** depends on instruments (P1B) and the rails (P1A); it produces the first **run-tracked derived
  output** (exposure aggregation) exercising FW-RUN + reproducibility.

**Alternatives considered & rejected:** (a) *one monolithic P1* — too large to review, mixes enabling and domain work, and risks
domain entities landing before lineage/DQ exist; (b) *fold P0.5 into P1A* — hygiene is independent of and should precede schema
changes; (c) *merge P1B+P1C* — reference data is a self-contained dependency; separating lets the FR pattern stabilize first.

**Parallelization:** P0.5 and the *non-ingestion* parts of P1A can overlap. P1B starts only after P1A's lineage/DQ/ingestion
rails exist. P1C starts only after P1B (positions reference instruments).

---

## 2. P0.5 — Engineering Hygiene & Foundation Hardening

| # | Dimension | Detail |
|---|---|---|
| 1 | **Requirements included** | REQ-AUD-002 (scheduled chain verification + checkpoints); DEP-CIH (Alembic autogenerate drift check in CI; audit-write concurrency control); DEP-FELOCK (frontend `package-lock.json` + CI `npm ci`); entitlement **bootstrap seeding** (baseline roles/permissions so P1B/P1C checks are real). Closes OD-051, OD-052; resolves OQ-008/OQ-011. |
| 2 | **Requirements excluded** | All domain data (SMR/PPM); real SSO (P9); SoD/maker-checker (P6); lineage/model-registry/DQ skeletons (P1A). |
| 3 | **Dependencies** | Existing FW-AUD/FW-ENT/FW-RUN/FW-TMP. Needs a Node-equipped env for the lockfile (CI). Postgres service in CI for drift check. |
| 4 | **Database entities** | No new tables. One data-only migration seeding baseline `permission`/`role`/`role_permission` rows (EV reference/config). |
| 5 | **API surfaces** | None new (health/version only). An internal **ops CLI** for `verify-chain`/`checkpoint` (not HTTP). |
| 6 | **Audit events** | `ENTITLEMENT.GRANT` (seeding); audit-integrity check result on verify run (extend taxonomy with `AUDIT.VERIFY`); `CONFIG.CHANGE` for the drift-gate addition. |
| 7 | **Entitlement checks** | `ops.audit.verify` (ops only); seeding is a migration/admin action. No new user-facing surface. |
| 8 | **Data lineage hooks** | None (lineage skeleton is P1A). |
| 9 | **Tests** | Drift-check job fails on injected model/migration mismatch, passes on none; concurrency test — parallel `record_event` for one tenant yields gapless, unique `sequence_no`; `npm ci` reproducible install + build from committed lockfile; `verify-chain` CLI test. |
| 10 | **Acceptance criteria** | CI has a migration-drift gate (red on mismatch); concurrent audit writes never duplicate/gap `sequence_no` (per-tenant lock + unique constraint); frontend builds via `npm ci` from a committed lockfile; scheduled chain verification runs and reports; baseline roles/permissions seeded and queryable. |
| 11 | **Risks** | Per-tenant audit lock may serialize writes → keep lock granularity per-tenant, not global. `npm ci` needs Node (run in CI, not locally). Drift-check false positives across dialects → run against Postgres only. |
| 12 | **Estimated sequence** | (a) frontend lockfile + `npm ci`; (b) Alembic drift-check CI job; (c) audit-write concurrency (per-tenant advisory lock) + test; (d) entitlement bootstrap seed; (e) scheduled `verify-chain` ops CLI/job. |

## 3. P1A — Lineage / Model-Registry / Data-Quality Skeletons (+ generic ingestion)

| # | Dimension | Detail |
|---|---|---|
| 1 | **Requirements included** | REQ-LIN-001 (lineage skeleton & capture), REQ-MDG-001 (model inventory & versioning skeleton), REQ-DQR-001 (DQ rules engine skeleton), REQ-INT-001 (file upload / anti-corruption ingestion), REQ-AUD-001 (audit coverage of governed writes). Delivers DEP-LIN, DEP-MREG, DEP-DQF as *skeletons*. |
| 2 | **Requirements excluded** | SMR/PPM entities (P1B/P1C); reconciliation DQR-002 (P7); lineage query/visualization LIN-002 (P7); model tiering/validation MDG-002/003 (P7); manual overrides DQR-003 (P7); API/SFTP/vendor adapters INT-002/003 (P9). |
| 3 | **Dependencies** | P0.5 (entitlement bootstrap, drift-check, audit concurrency); FW-AUD/ENT/RUN/TMP. Ingestion targets a **generic staging area**; canonical mapping is defined per-domain in P1B/P1C. |
| 4 | **Database entities** | `data_source` (ENT-038, EV), `lineage_edge` (ENT-042, IA), `ingestion_batch` (IA, upload provenance); `model` + `model_version` (ENT-035, IA), `model_assumption`/`model_limitation` (ENT-036); `data_quality_rule` (ENT-039, EV), `dq_result` (ENT-039, IA). |
| 5 | **API surfaces** | `POST /ingest/upload` (multipart → validate → stage → DQ → lineage origin → audit); `POST /models`, `GET /models` (inventory); `POST /dq/rules`, `GET /dq/results`; minimal `GET /lineage/edges/{id}` (capture verification; full query is LIN-002). All tenant-scoped, deny-by-default. |
| 6 | **Audit events** | `DATA.INGEST`, `DATA.VALIDATE` (DQ run), `MODEL.REGISTER`, `MODEL.VERSION`, create events for rules/sources. Lineage edges created (referenced by downstream writes). |
| 7 | **Entitlement checks** | `data.upload`, `lineage.view`, `model.inventory.view`, `model.inventory.register`, `dq.rule.manage`, `dq.result.view` — all deny-by-default, tenant-scoped. |
| 8 | **Data lineage hooks** | **This delivers the hook contract:** a `record_lineage(source → target/run)` utility every governed create/derive calls. BX-LIN becomes executable; a governed derived write without a lineage edge fails a test. |
| 9 | **Tests** | Upload validation + malicious-file/formula-injection rejection (THR-05/06); DQ rule runs on ingest and raises exceptions (no silent pass, QS-15); lineage edge created + retrievable; model register → inventory entry + audit; **gate:** a derived write without lineage fails. |
| 10 | **Acceptance criteria** | End-to-end ingest validates + stages + DQ + lineage + audit on a sample file; a model is unusable without an inventory entry (BR-3 enforced at skeleton level); lineage edges retrievable by id; DQ exceptions surfaced not swallowed. |
| 11 | **Risks** | Scope creep into lineage query/full model governance — keep capture/inventory only. DQ rule engine over-engineering — start with a minimal rule interface. Upload security surface — sandbox parsing + type/size checks now; AV is later-hardening (OD-042). |
| 12 | **Estimated sequence** | (a) `data_source` + `lineage_edge` + capture utility/API; (b) `model`/`model_version` inventory + register API; (c) `data_quality_rule`/`dq_result` + run-on-ingest; (d) upload anti-corruption endpoint wiring all three; (e) AUD-001 coverage tests. |

## 4. P1B — Security Master & Reference Data

| # | Dimension | Detail |
|---|---|---|
| 1 | **Requirements included** | REQ-SMR-001 (instrument master), REQ-SMR-002 (issuer/counterparty entities + hierarchy), REQ-SMR-003 (identifier cross-reference), REQ-SMR-004 (corporate actions & calendars). Delivers DEP-SMR. |
| 2 | **Requirements excluded** | Public market data PUB-* (P2); private asset data PRV-* (P4); ratings/benchmark depth (P2/P3); pricing/risk (P2+); corporate-action *application to positions* (P1C/later — here store effective-dated actions only). |
| 3 | **Dependencies** | P1A (lineage capture, DQ rules, ingestion), P0.5 (entitlement bootstrap). FW-TMP (FR for instrument terms; EV for entities). **First real FR-class domain usage.** |
| 4 | **Database entities** | `instrument` (ENT-001, FR terms), `issuer` (ENT-002, EV), `counterparty` (ENT-003, EV), `identifier_xref` (ENT-004, EV), `corporate_action` (ENT-008, effective-dated EV), `calendar` (ENT-006, EV), `currency` (ENT-005, EV), `rating_scale` (ENT-007, EV). |
| 5 | **API surfaces** | CRUD + as-of read for instrument/issuer/counterparty; `GET /instruments/resolve?identifier=…` (xref); corporate-action & calendar management; ingestion mapping from P1A upload → instruments/entities. Tenant-scoped, entitled. |
| 6 | **Audit events** | `DATA.*` create/update per entity (entity_type=instrument/issuer/…); `DATA.CORRECTION` on edits; `DATA.INGEST` for mapped ingestion. Effective-dated changes audited with before/after. |
| 7 | **Entitlement checks** | `reference.instrument.view/.edit`, `reference.issuer.view/.edit`, `reference.counterparty.view/.edit`, `reference.identifier.resolve`, `reference.corporate_action.edit`, `reference.calendar.edit` — deny-by-default, tenant-scoped. |
| 8 | **Data lineage hooks** | Each reference record binds `source_id` + a `lineage_edge` to its ingestion batch (uses P1A). FR instrument terms reconstructable as-of. |
| 9 | **Tests** | Instrument terms reconstructable as-of (FR bitemporal); identifier resolution + precedence → one instrument; issuer→ultimate-parent rollup; corporate action applies on effective date; calendar/day-count roll (QS-10/11); entitlement deny tests; ingestion-mapping test. |
| 10 | **Acceptance criteria** | Any known identifier resolves to exactly one instrument; instrument terms queryable as-of any past date; issuer hierarchy rolls to ultimate parent; corporate actions effective-dated; reference data carries lineage + audit; unentitled access denied. |
| 11 | **Risks** | First real FR bitemporality → modeling complexity (mitigate via temporal mixins + as-of tests). **Open decision: reference-data tenancy** (shared cross-tenant vs per-tenant). Identifier precedence ambiguity. Scope creep into pricing/ratings depth (excluded). |
| 12 | **Estimated sequence** | (a) currency/calendar/rating_scale; (b) issuer/counterparty + hierarchy; (c) instrument (FR terms) + identifier_xref + resolve; (d) corporate_action effective-dated; (e) ingestion mapping + lineage + tests. |

## 5. P1C — Portfolio Hierarchy & Positions

| # | Dimension | Detail |
|---|---|---|
| 1 | **Requirements included** | REQ-PPM-001 (portfolio/fund/strategy hierarchy), REQ-PPM-002 (position master as-of), REQ-PPM-003 (transaction & valuation history), REQ-PPM-004 (exposure aggregation). |
| 2 | **Requirements excluded** | Risk analytics (P2+); limits (P6); private positions/commitments (P4); valuation *computation* from market data (P2 — here valuations are stored/ingested, not derived). |
| 3 | **Dependencies** | P1B (instruments — positions reference them), P1A (lineage, ingestion), P0.5 (entitlement, audit concurrency), FW-RUN (exposure aggregation run-tracked), FW-TMP (FR positions/valuations; IA transactions). |
| 4 | **Database entities** | `portfolio`/`fund`/`strategy`/`account` (ENT-010, EV hierarchy), `position` (ENT-011, FR), `transaction` (ENT-012, IA), `valuation` (ENT-013, FR), `exposure_aggregate` (ENT-014, IA, run-tracked). |
| 5 | **API surfaces** | Hierarchy CRUD; position as-of read; transaction append; valuation as-of; `POST /portfolios/{id}/aggregate` → `CalculationRun` + result read. Tenant-scoped + **portfolio-level ABAC scope** (first real use). |
| 6 | **Audit events** | `DATA.*` for hierarchy/positions/valuations; transactions append (immutable); `CALC.RUN_CREATE`/`CALC.RUN_STATUS_CHANGE` for aggregation (uses FW-RUN). |
| 7 | **Entitlement checks** | `portfolio.view/.edit` scoped to hierarchy node/subtree (ABAC — the scope anchor from PPM-001); `position.view`; `exposure.aggregate.run`. Deny-by-default + tenant + portfolio scope. |
| 8 | **Data lineage hooks** | Positions/valuations bind source→lineage; `exposure_aggregate` (PPM-004) binds `CalculationRun` + input snapshot + lineage edges — **first governed derived output** (BX-LIN + BX-REPRO via FW-RUN). |
| 9 | **Tests** | Position reconstructable as-of (FR); transactions immutable (IA); valuation as-of; aggregation reproduces within tolerance + binds lineage + reproducible; **portfolio-scope entitlement** (entitled to A ⇒ denied B within a tenant); hierarchy rollup. |
| 10 | **Acceptance criteria** | Positions/valuations queryable as-of any past date; aggregation produces reproducible, lineage-bound exposures over an entitled scope; portfolio-level entitlement enforced (cross-portfolio denied within a tenant); transactions immutable. |
| 11 | **Risks** | **PPM-004 needs an input snapshot** but FW-RUN's reproducibility FKs are nullable placeholders → either deliver a *minimal dataset-snapshot* in P1C (pin position+valuation record versions at run time) or **defer PPM-004 to P2** (open decision). Portfolio ABAC granularity (node vs subtree). FR position volume. |
| 12 | **Estimated sequence** | (a) portfolio hierarchy + ABAC scope anchor; (b) position master (FR) referencing instruments; (c) transaction (IA) + valuation (FR); (d) exposure aggregation (FW-RUN + lineage + repro); (e) entitlement scope + tests. |

## 6. Recommended Sequence & Critical Path

```
P0.5 hygiene ──► P1A rails (lineage / model-registry / DQ / ingestion) ──► P1B reference data ──► P1C portfolio & positions
   (CI baseline)        (BX-LIN/DOC executable)                              (DEP-SMR, first FR)     (first run-tracked output)
```

- **Hard ordering:** P1A before any domain entity; P1B before P1C.
- **Allowed overlap:** P0.5 with non-ingestion parts of P1A.
- Each subphase exits only on full DoD + control-matrix `Implemented` + green CI + clean enterprise review (build_sequence §3).

## 7. Open Decisions to resolve before/within P1

| ID | Decision | Needed by |
|---|---|---|
| OQ-004 | Minimal SoD in P1 for overrides, or defer all maker-checker to P6? | P1A (DQ overrides excluded → likely defer; confirm) |
| OQ-012 (new) | Reference-data tenancy: shared cross-tenant vs per-tenant `instrument`/`issuer`/`calendar`? | P1B |
| OQ-013 (new) | Deliver a minimal dataset-snapshot in P1C for PPM-004, or defer exposure aggregation to P2? | P1C |
| OQ-008 | Test-coverage threshold + CI enforcement | P0.5 |
| OQ-011 | Exact minimum P0.5 hardening scope | P0.5 (this plan proposes it) |

## 8. Dependencies

This plan depends on the Step 2 backbone (requirement scope/IDs), the canonical data model (ENT-xxx), the audit taxonomy
(event codes), the entitlement model (permission codes/ABAC), and the foundation slice (FW-AUD/ENT/RUN/TMP with documented
placeholders). No code is produced here.
