# P1A Closeout & P1B Readiness Review

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1A-CLOSE-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | H-06 Engineering Lead (with R-01 Chief Architect AI) |
| Approver | H-06 Engineering Lead (H-08 Internal Audit consulted) |
| Created | 2026-06-22 |
| Related Documents | p1a_implementation_plan.md, p1a1/p1a2/p1a3/p1a4_implementation_plan.md, ../02_requirements/requirements_backbone.md, ../02_requirements/requirements_traceability_matrix.md, ../04_data_model/canonical_data_model_standard.md, ../04_data_model/audit_event_taxonomy.md, ../04_data_model/temporal_reproducibility_standard.md, ../06_security/entitlement_sod_model.md, ../06_security/threat_model_initial.md, ../09_compliance_controls/control_matrix_skeleton.md, ../08_testing_qa/ci_enforcement_overview.md |
| Supported Build Rules | BR-3, BR-5, BR-7, BR-10, BR-11, BR-12, BR-13, BR-16, BR-17, BR-18, BR-19 |

**Purpose.** Confirm the P1A cross-cutting / foundational rails are complete, committed, and CI-green;
inventory the reusable rails now available to downstream phases; and define the controlled entry
criteria, open decisions, and recommended sub-slice structure for **P1B — Security Master & Reference
Data**. This is a planning/governance artifact only — **no application code, migrations, or rail
changes are produced or implied by this document.**

---

## Part 1 — P1A Closeout

P1A delivered the five cross-cutting rails every domain slice depends on. All slices were built on a
strict cadence: UltraCode planning workflow → committed plan → implementation → multi-lens adversarial
review → fix in-scope findings → `make check` → commit on explicit approval → CI-green. HEAD of
`origin/main` is `0282359`; working tree clean; local == origin (0 ahead / 0 behind).

### 1.1 P1A-0 — Tenant Context / PostgreSQL RLS
| Field | Detail |
|---|---|
| Implementation commit | `7cdc2f9` (plan `4bc68c6`, decisions `c975450`) |
| CI status | Green |
| Key capabilities | `set_tenant_context` via `set_config` (transaction-local `app.current_tenant`, never parameterized `SET`); FORCE ROW LEVEL SECURITY + `tenant_isolation_<t>` policies; constrained non-superuser `irp_app` PG-test role (NOSUPERUSER NOBYPASSRLS); durable pool-checkin `RESET`; BYPASSRLS reserved for the `irp_ops` role (never normal app paths); `get_tenant_session` / `require_permission` deny-by-default dependencies. **Factual note:** the foundation policies in migration `0001` (P0 scaffold `4f93a33`, predates P1A-0) are **`USING`-only**; the **explicit `WITH CHECK`** pattern was introduced by the rail migrations `0004`–`0007` (P1A-1…P1A-4) and is the pattern P1B must replicate. P1A-0 (`7cdc2f9`) added the tenant-context wiring + the `irp_ops` migration `0003`, not the RLS policies. |
| Controls now executable | CTRL-003 (tenant isolation), CTRL-011 (deny-by-default), foundations for CTRL-005/017/032. |
| Known placeholders | The dev `X-User-Id`/`X-Tenant-Id` header shim is **unverified and not a security boundary** until real SSO (DR-P1A0-3 / AD-007); `classify_rls_denied` / `SECURITY.RLS_DENIED` emission deferred (DR-P1A0-4). |
| Follow-up items | Real SSO/OIDC (P9); DB-level RLS-denial audit eventing. |
| Risks carried forward | **The RLS read policy admits exactly one tenant** (`tenant_id::text = current_setting('app.current_tenant', true)`) — it does NOT admit `SYSTEM_TENANT_ID` rows. Any "global + tenant" hybrid read (P1B reference data) requires an explicit policy extension (OD-P1B-C). |

### 1.2 P1A-1 — Data Source + Lineage Skeleton
| Field | Detail |
|---|---|
| Implementation commit | `96a1564` (plan `3ff3213`); CI fixes `7a700f0`, `72b889f`; append-only-test hardening `97c2b1d` |
| CI status | Green |
| Key capabilities | `data_source` (ENT-038, EV) + `lineage_edge` (ENT-042, IA, append-only); `record_lineage(session, *, source, target_entity_type, target_entity_id, run_id=None, edge_kind=ORIGIN)` co-transactional, server-stamps tenant, cross-tenant source → `DataSourceNotVisible`; `register_data_source` / `update_data_source` (`DATA.SOURCE_REGISTER`/`.SOURCE_UPDATE`); `assert_has_lineage` (CTRL-013 no-bypass). Polymorphic `(target_entity_type, target_entity_id)`, no domain FK. |
| Controls now executable | CTRL-006 (provenance), CTRL-013 (lineage no-bypass). |
| Known placeholders | `lineage_edge.run_id` is a logical (non-FK) reference; no lineage query/graph/visualization. |
| Follow-up items | REQ-LIN-002 lineage query/graph (P7); field-level lineage (P7). |
| Risks carried forward | "Governed output" enforcement is by-convention + the BX-LIN test; each consumer must call `record_lineage` + `assert_has_lineage` (P1A-4 proved the pattern). |

### 1.3 P1A-2 — Model Registry Skeleton
| Field | Detail |
|---|---|
| Implementation commit | `c9be657` (plan `4be45f5`) |
| CI status | Green |
| Key capabilities | `model` (ENT-035, EV) + `model_version`/`model_assumption`/`model_limitation` (IA); `register_model` / `register_model_version` / `assert_registered_model_version` (BR-3 inventoried-before-use gate); reuses `MODEL.REGISTER`/`MODEL.VERSION`. |
| Controls now executable | CTRL-003 (inventory), CTRL-014 (limitations documented, BX-LIM). |
| Known placeholders | DR-P1-3 maker-checker hooks non-enforcing; tier/validation_status reserved; `calculation_run.model_version_id` stays nullable until P2 binds a version. |
| Follow-up items | REQ-MDG-002/003 tiering, validation workflow, effective-challenge, restricted-use (P7). |
| Risks carried forward | **Not on the P1B path** — P1B reference data does not run models; no P1B dependency on the model registry. |

### 1.4 P1A-3 — Data Quality Skeleton
| Field | Detail |
|---|---|
| Implementation commit | `cc472be` (plan `5da67be`) |
| CI status | Green |
| Key capabilities | `data_quality_rule` (ENT-039, EV) + `data_quality_result` (IA); pluggable `DQRule.evaluate()` REGISTRY with **exactly two generic evaluators** (`not_null`, `allowed_values`); `run_quality_check` (evaluate + persist + `DATA.VALIDATE`), `assert_passed_quality_checks` (fail-closed gate); **no-silent-failure** (ERROR raises + flags, WARNING flags-only, evaluator error propagates + audited `outcome='failure'`). |
| Controls now executable | CTRL-027 (DQ-on-ingest, Designed→ now Implemented at P1A-4), CTRL-029 (no-silent-failure). |
| Known placeholders | `data_quality_result.ingestion_batch_id` was a no-FK placeholder — **populated at P1A-4**; only generic rules (no domain-specific DQ). |
| Follow-up items | REQ-DQR-002 reconciliation, REQ-DQR-003 override/exception workflow (P7). |
| Risks carried forward | Domain-specific rules must extend by **value + a registry evaluator entry**, never schema; P1B must not invent a parallel engine. |

### 1.5 P1A-4 — Generic Ingestion Staging
| Field | Detail |
|---|---|
| Implementation commit | `c781bb8` (plan `563b6cf`); PG-test fix `0282359` |
| CI status | Green (run 27965086115) — incl. the new "Ingestion RLS + append-only tests (Postgres)" step + downgrade smoke |
| Key capabilities | `ingestion_batch` (ENT-047, IA-classed **status-mutable**, CalculationRun precedent) + `ingestion_staged_record` (ENT-048, IA append-only); `stage_upload` composes P1A-1 lineage origin + P1A-3 DQ + audit in one tenant-scoped transaction; CSV anti-corruption layer (10 MiB cap counted while reading, CSV-only allowlist, filename sanitization, encoding validation, formula-injection neutralization, ragged-row rejection, no-op AV seam); `POST /ingest/upload` + `GET /ingest/batches[/{id}]`; **durable-evidence-on-reject** (REJECTED batch + flagged result + audit committed, 4xx never 200); activates `DATA.INGEST` (no new code); reuses `data.upload` (no new permission). |
| Controls now executable | CTRL-027 **Implemented** on a real ingest path; CTRL-013 exercised non-synthetically; CTRL-029 first real ingest evidence; THR-05/THR-06 mitigations realized (AV deferred). |
| Known placeholders | `scan_status` AV hook is a no-op (OD-042); in-DB JSON staging (object store / AD-004 deferred); **canonical mapping deferred to P1B/P1C** — staged rows are generic JSON, not canonical data. |
| Follow-up items | REQ-INT-002/003 vendor/SFTP/API adapters (P9); XLSX parsing (CSV-only at P1A-4); canonical mapping (P1B/P1C). |
| Risks carried forward | The staging→canonical mapping seam is **the explicit P1B/P1C boundary**; P1B must decide whether to consume the staging path or use direct CRUD (Part 4, ingestion-usage decision — CRUD-first). |

### 1.6 Closeout confirmations
- **All P1A slices committed:** ✅ P1A-0 `7cdc2f9`, P1A-1 `96a1564`, P1A-2 `c9be657`, P1A-3 `cc472be`, P1A-4 `c781bb8` (+ test fix `0282359`).
- **All P1A slices CI-green:** ✅ latest run on HEAD `0282359` = success (all 5 jobs).
- **`origin/main` clean:** ✅ working tree clean; local == origin (0/0).
- **No unresolved P1A defect blocks P1B:** ✅ the only post-merge defect (P1A-4 PG test context-after-commit) was test-only, fixed in `0282359`, verified against `postgres:16`.
- **P1B has not started:** ✅ no P1B code, entities, migrations, or branches exist.

---

## Part 2 — P1A Rail Inventory (reusable by P1B)

| Rail | What P1B can use | What P1B must NOT assume | Known limitations |
|---|---|---|---|
| **Tenant context / RLS** | `get_tenant_session`, `set_tenant_context`, the FORCE RLS + `USING`+explicit-`WITH CHECK` policy loop from the **`0004`–`0007` rail migrations** (the pattern to replicate); constrained-role PG test pattern. | That the **current policy admits global/SYSTEM_TENANT rows** — it scopes to exactly one tenant. Hybrid "global + own tenant" reads need an explicit policy extension (OD-P1B-C). Also: the **`0001` foundation tables are `USING`-only** (no explicit `WITH CHECK`) — do not assume every existing tenant table has `WITH CHECK`. | Single-tenant read scope; no row-level sharing across tenants today; foundation/rail policies are not uniform. |
| **Audit events + hash chain** | `record_event(...)` co-transactional fail-closed (AUD-04); `verify_chain`; controlled `CATEGORY.ACTION` vocabulary; per-transition pattern (CalculationRun/ingestion). | That new event codes are free — additions are governed taxonomy changes (R-07). `audit/service.py` is **frozen**. | Sensitive `before/after` must be reference/hash, never plaintext; reads not yet access-audited (OD-023). |
| **Entitlements** | Deny-by-default `require_permission`; `bootstrap.py` catalog already contains `reference.instrument.view/edit`, `reference.issuer.view/edit`, `reference.counterparty.view/edit`, `reference.identifier.resolve`, `reference.corporate_action.edit`, `reference.calendar.edit`. | That **all** P1B permissions exist — **`currency` and `rating_scale` codes are absent**, and `calendar`/`corporate_action` ship `.edit` **but no `.view`** (read endpoints need view codes). All gaps in OD-P1B-F; R-07-governed catalog additions, no role-template change without governance. | Maker-checker (DR-P1-3) is a non-enforcing placeholder. |
| **Data source** | `register_data_source` / `update_data_source` (EV provenance root); `data.upload` / `lineage.source.manage`. | That a "manual"/"vendor" source exists — P1B must register the sources it cites. | No vendor-feed adapters (P9). |
| **Lineage** | `record_lineage` (origin edge), `assert_has_lineage` (CTRL-013). | That lineage query/graph/field-level exists (P7). | Capture + retrieve-by-id only. |
| **Model registry** | Available but **not required by P1B**. | Any P1B dependency on it (reference data does not run models). | — |
| **Data quality** | `run_quality_check`, `assert_passed_quality_checks`, the two generic evaluators (`not_null`, `allowed_values`); extend by value + registry entry. | That domain-specific evaluators exist or should be added early. | Generic rules only; no reconciliation/override (P7). |
| **Generic ingestion staging** | `stage_upload`, `ingestion_batch`/`ingestion_staged_record`, anti-corruption layer, `data_quality_result.ingestion_batch_id`. | That staged rows are canonical, or that a staging→canonical **mapping** exists (it is deferred — that mapping is the P1B/P1C deliverable). | CSV-only; in-DB JSON; sync; AV is a no-op seam. |
| **Temporal mixins** | `EffectiveDatedMixin` (EV), `ImmutableAppendOnlyMixin` (IA), `FullReproducibleMixin` (FR); `__temporal_class__` (BR-19); the **IA-status-mutable** precedent (CalculationRun / ingestion_batch). | That every entity is one class — P1B must classify each entity deliberately (OD-P1B-A/B). | `GUID` surfaces as `str`; native uuid on PG (CI lessons apply). |
| **Alembic migration / drift gates** | `alembic upgrade head` + `alembic check` (drift, `compare_type=False`) + downgrade smoke; NAMING_CONVENTION (`pk_/ix_/uq_/fk_`); model aggregator `irp_shared.models`. | That JSON↔JSONB or type nuances auto-resolve — mirror the established migration pattern exactly. | Migrations are sequential (next is `0008`). |
| **PostgreSQL constrained-role RLS tests** | The `app_url` fixture (creates `irp_app` NOSUPERUSER NOBYPASSRLS), `_is_rls_violation` (42501); per-table grants; **re-set tenant context after any commit before a read-back** (the `0282359` lesson). | That superuser test runs prove RLS (they bypass it). | Each new tenant table needs its own grant + RLS step in CI. |
| **Append-only trigger tests** | `_is_append_only_violation` (P0001); grant `irp_app` UPDATE/DELETE so rejection is the **trigger**, not a privilege denial; EV/IA negative-control pattern. | That ORM guard alone proves immutability — assert the DB trigger. | Applies only to tables in `APPEND_ONLY_TABLES`. |

---

## Part 3 — P1B Readiness Review

**P1B scope: Security Master & Reference Data ONLY.** Proposed entities map to the canonical model
BC-02/BC-03 (Reference / Security Master): `currency` (ENT-005), `calendar` (ENT-006),
`rating_scale` (ENT-007), `issuer` (ENT-002), `counterparty` (ENT-003), `instrument` (ENT-001),
`identifier_xref` (ENT-004), `corporate_action` (ENT-008). (`benchmark` ENT-009 is reference but
**out of the stated P1B set** — defer.)

**Confirmed P1B boundaries (hard exclusions):** No portfolio (ENT-010) · No positions (ENT-011) ·
No valuations (ENT-013) · No market prices (ENT-020) · No market-data ingestion (ENT-020–025) ·
No risk analytics (ENT-026–029) · No private-asset ingestion (ENT-015–019) · No performance/returns ·
No limit framework · No breach workflow · No reporting dashboards · No real SSO. All are P1C / later
phases and must not appear in any P1B deliverable, entity, endpoint, test, or migration.

**Readiness conclusion:** P1B is **ready to enter PLANNING / decisioning (P1B-0)** — **not** implementation,
and **not** with the decisions pre-confirmed. The rails are green and reusable, but a 7-lens review
(Part 7) found that several P1B design choices in this artifact **conflict with ratified baselines and
must be reconciled in P1B-0 before any build slice**, not silently confirmed:
- **OD-P1B-A (instrument temporal class):** AD-005 §2A, REQ-SMR-001 (`instrument (FR terms)`,
  "reconstructable as-of"), and the P1 scoping plan ("first real FR domain usage") classify instrument
  economic terms as **FR** — recommend the split *identity=EV / effective-dated economic terms=FR*; a
  blanket-EV would be an AD-005/REQ-SMR-001 amendment requiring R-05 + H-04 sign-off.
- **OD-P1B-B (corporate_action):** AD-005 §2A + REQ-SMR-004 classify it **EV** (effective-dated,
  supersedable) — **not IA**.
- **OD-P1B-C (hybrid tenancy):** AD-013 / P1-scoping-plan §4 record global reference as **separate
  no-`tenant_id` RLS-exempt tables**; the SYSTEM_TENANT-rows + `USING`-extension model here is a
  *proposed refinement* requiring R-04/R-05/H-04 ratification.
- **OD-P1B-D (issuer/counterparty):** canonical ENT-002/003 + REQ-SMR-002 + the existing separate
  permission pairs favor **separate role tables sharing a common legal-entity core**, not a unified
  `legal_entity`+role default.

All P1A rails remain sound; these are **planning decisions to ratify**, not P1A defects. P1B is ready
for P1B-0 to resolve OD-P1B-A…J (Part 4) and ratify the requirement/taxonomy/entitlement gaps.

---

## Part 4 — P1B Decisions to Confirm (OD-P1B-A … OD-P1B-J)

> The 7-lens review (Part 7) reclassified four of these from "confirm" to **ratify** because the draft
> recommendations conflicted with ratified baselines (AD-005, AD-013, the canonical model, the RTM).
> Each below states the **baseline**, the **recommendation**, and the **ratifier**. None may be silently
> "confirmed" in implementation — they are resolved and committed in **P1B-0**.

| ID | Decision | Baseline vs draft | Recommendation | Ratifier (P1B-0) |
|---|---|---|---|---|
| **OD-P1B-A** | **Instrument temporal class** (load-bearing — FR is the most expensive pattern to retrofit) | **AD-005 §2A + REQ-SMR-001 (`instrument (FR terms)`, "reconstructable as-of") + P1-scoping-plan ("first real FR domain usage") = FR.** Draft said blanket-EV. | Adopt the **split**: instrument **identity/master attributes = EV**; instrument **effective-dated economic terms (coupon/maturity/call schedules) = FR** (separate term-version/FR-classed entity). A blanket-EV is a formal **AD-005 + REQ-SMR-001 amendment**, not a confirm. | **R-05 + H-04** |
| **OD-P1B-B** | **Corporate-action temporal class** | **AD-005 §2A + REQ-SMR-004 = EV** (effective-dated, "applies on effective date", amendable/cancellable before application). Draft said IA. | Classify **`corporate_action` = EV**; effective-date + supersede. Drop the CalculationRun/IA-status-mutable rationale (category error — CalculationRun is an IA *run* record, not EV master data). A separate immutable announcement-event log, if wanted, is a **distinct** entity decision. | **R-05** |
| **OD-P1B-C** | **Hybrid global-data mechanism** | **AD-013 + P1-scoping-plan §4 = separate "Global (no `tenant_id`), RLS-exempt, write-restricted, leak-free" tables.** Draft proposed SYSTEM_TENANT rows in the tenant tables + `USING` extension. | Adopt the **SYSTEM_TENANT + `USING`-extension** model (keeps FORCE RLS everywhere; reuses the proven system-context-only write isolation) **AND amend AD-013 + scoping-plan §4** to ratify it. Policy: `USING (tenant_id::text = current_setting('app.current_tenant', true) OR tenant_id::text = SYSTEM_TENANT_ID)` / `WITH CHECK` **single-tenant**. Required PG test: own+SYSTEM readable, other-tenant invisible, SYSTEM write rejected under tenant context, **no-context read returns only global rows** (the extended `USING` is intentionally not fully fail-closed for the non-proprietary global slice). **Invariant:** proprietary entities (issuer/counterparty/instrument) are **never** stamped SYSTEM_TENANT and are **never** hybrid. | **R-04 + R-05 + H-04** |
| **OD-P1B-D** | **Issuer / counterparty entity shape** | **Canonical ENT-002/003 + REQ-SMR-002 + existing separate `reference.issuer.*`/`reference.counterparty.*` permissions + OD-015 (counterparty-only netting/CSA) = separate.** Draft led with unified `legal_entity`+role. | Recommend **separate `issuer`/`counterparty` role tables sharing a common legal-entity core** (shared LEI + parent/child hierarchy; distinct role tables) — preserves the canonical contract, the SoD permission split, and the OD-015 attachment point with no real duplication. A **unified** `legal_entity`+role table requires an explicit **canonical-model + REQ-SMR-002 amendment**. | **R-05 + H-04** |
| **OD-P1B-E** | **Reference-CRUD audit event codes** | **`audit_event_taxonomy.md` DATA category has no generic `.CREATE`/`.UPDATE` action and no `REFERENCE` category** — so reference CRUD codes are **net-new**, not a reuse. | Mint governed codes (new `DATA.*` actions mirroring `MODEL.REGISTER`, or a new `REFERENCE` category) with **R-07** sign-off + `EVT-nnn` index allocation. Promoted from an inline note to a tracked decision. | **R-07** |
| **OD-P1B-F** | **Missing entitlement codes** | Catalog lacks `currency` and `rating_scale` codes, and `calendar`/`corporate_action` ship `.edit` but **no `.view`** (read endpoints need them). | Add `reference.currency.view/edit`, `reference.rating_scale.view/edit`, `reference.calendar.view`, `reference.corporate_action.view`. Standardize `reference.<entity>.<verb>`; **reserve `reference.rating.*`** for the future FR rating-assignment domain. R-07-governed catalog addition; **no role-template change** without governance. | **R-07** |
| **OD-P1B-G** | **Identifier resolution contract** (precedence deferred) | **REQ-SMR-003 acceptance = "Any known identifier resolves to ONE instrument" + a precedence test; OD-012 (vendor precedence) is open.** A precedence-free polymorphic lookup can return multiple candidates. | `identifier_xref` = polymorphic `(entity_type, entity_id, scheme, value, valid_from, valid_to)`, `scheme` a **controlled-vocab string** (CUSIP/ISIN/SEDOL/TICKER/LEI/FIGI/INTERNAL/PRIVATE/SOURCE_SYSTEM — extend **by value**). `reference.identifier.resolve` is a **deterministic single-result-or-explicit-ambiguity-error** lookup with structural uniqueness on active `(scheme, value)` where feasible; **cross-vendor precedence ranking is deferred to P1C/OD-012**, so REQ-SMR-003 is **partially met** at P1B (record it). | **R-05** |
| **OD-P1B-H** | **Service package & dependency direction** (unstated in draft) | Repo pattern: per-domain web-framework-free `irp_shared.*` packages, zero web imports, one-way deps. | P1B reference services in a **new web-framework-free package** (recommend `irp_shared.reference`, or per-entity submodules); update the model aggregator; endpoints in `irp_backend/api/reference*`. Dependency direction **reference → (lineage, dq, audit, entitlement)** only — **no reverse, no circular dependency with ingestion** (the optional P1B-5 mapping may depend on ingestion; the CRUD core must not). | **R-01** |
| **OD-P1B-I** | **Manual `data_source` registration scope** | `data_source` is tenant-scoped `UNIQUE(tenant_id, code)`; `record_lineage` resolves it RLS-scoped (cross-tenant/global id → `DataSourceNotVisible`). | `source_type='MANUAL'` is a **value-level** controlled-vocab addition (no schema change). Decide **per-tenant seed vs once under SYSTEM_TENANT**; if SYSTEM_TENANT, **add `data_source` to the OD-P1B-C hybrid global-read extension** or tenant writers hit `DataSourceNotVisible`. | **R-05** |
| **OD-P1B-J** | **Requirement coverage for currency / rating_scale** | `currency` (ENT-005) and `rating_scale` (ENT-007) trace to **no concrete REQ-SMR row** — sub-cap 2.5 folds into REQ-SMR-004 whose entity column lists only `corporate_action, calendar (EV)`. | Before P1B-1 builds them, **extend REQ-SMR-004 or mint REQ-SMR-005** with explicit acceptance criteria + RTM entries for currency and rating_scale (or formally record them as CAP-2 sub-capability 2.5 derivations). Replace the `REQ-SMR-00x` placeholders with resolved ids. | **R-02 (Requirements) + R-05** |

**Unchanged confirmable decisions:** entity **sequencing** (currency/calendar/rating_scale → issuer/counterparty → instrument+identifier_xref → corporate_action); **ingestion usage** (CRUD-first; P1A-4 staging→canonical mapping is the optional/last P1B-5); **lineage** (one origin edge `data_source → <entity>` + `assert_has_lineage` per record); **DQ at entry** (generic `not_null`/`allowed_values` only, on configured rules — not every write). These reuse P1A rails directly and carry no baseline conflict.

---

## Part 5 — Recommended P1B Implementation Structure

**Recommendation: split P1B into six sub-slices** (P1B-0 planning + five build slices), each following
the P1A cadence (plan → implement → adversarial review → fix → `make check` → commit-on-approval → CI).
P1B-5 is **conditional** (only if bulk reference loading is needed at this phase).

**Slice → REQ-SMR mapping** (resolves the `REQ-SMR-00x` placeholders): P1B-1 = **REQ-SMR-004** (calendar) **+ currency/rating_scale (OD-P1B-J: no current REQ — extend SMR-004 or mint SMR-005)**; P1B-2 = **REQ-SMR-002** (issuer, counterparty); P1B-3 = **REQ-SMR-001** (instrument) **+ REQ-SMR-003** (identifier_xref); P1B-4 = **REQ-SMR-004** (corporate_action). Note **REQ-SMR-004 deliberately spans P1B-1 (calendar) and P1B-4 (corporate_action)**.

### P1B-0 — Planning & Decision Record
- **Requirements included:** resolve and commit **OD-P1B-A…J** (esp. the four ratification items: instrument FR-split, corporate_action=EV, hybrid-tenancy/AD-013 amendment, issuer/counterparty shape); the requirement-coverage and audit-taxonomy/entitlement governance additions; per-slice plans for P1B-1…4(/5).
- **Requirements excluded:** any code/migration.
- **Dependencies:** this artifact; **R-05 + H-04** (OD-P1B-A/B/C/D/I), **R-07** (OD-P1B-E/F), **R-04** (OD-P1B-C), **R-02** (OD-P1B-J), **R-01** (OD-P1B-H).
- **Acceptance criteria:** every OD-P1B-* decision resolved, with each baseline conflict (AD-005, AD-013, canonical model, RTM) either aligned-to or amended via a recorded ADR/requirement change, **before P1B-1**.

### P1B-1 — Currency / Calendar / Rating Scale (the standalone vocabularies)
| Dim | Detail |
|---|---|
| Requirements included | REQ-SMR-004 (calendar) + currency (ENT-005) + rating_scale (ENT-007), all **EV**, hybrid-tenancy (global seed + tenant override). **OD-P1B-J:** currency/rating_scale need a requirement row first. |
| Requirements excluded | issuer/counterparty/instrument/xref/corporate_action; **rating ASSIGNMENTS** (ENT-007's second half — FR per AD-005, deferred to a credit phase; P1B-1 ships only the scale/grade taxonomy); day-count/roll math (QS, later). |
| Dependencies | OD-P1B-C (global-read RLS extension); OD-P1B-F (currency/rating_scale + `.view` permission codes); OD-P1B-E (audit codes); OD-P1B-J (requirement coverage). |
| Entities | `currency`, `calendar` (+ `calendar_holiday` child if needed), `rating_scale` (+ `rating_grade` child) — **EV (scale/taxonomy only)**, tenant-scoped, **global-readable** via OD-P1B-C. |
| APIs | `POST/GET /reference/currencies`, `/calendars`, `/rating-scales` (+ `/{id}`), gated, server-stamped tenant, indistinguishable 404. |
| Audit events | **No existing DATA code covers reference CRUD** — emit the **net-new R-07-minted** reference create/update codes (OD-P1B-E); reuse `DATA.VALIDATE` only for any DQ run. |
| Entitlement checks | **Add (OD-P1B-F):** `reference.currency.view/edit`, `reference.rating_scale.view/edit`, `reference.calendar.view` (catalog has `reference.calendar.edit` only). |
| RLS behavior | Hybrid read (own tenant **OR** SYSTEM_TENANT) per OD-P1B-C; `WITH CHECK` single-tenant; `UNIQUE(tenant_id, code)` (**never** `UNIQUE(code)`); tenant override **wins** over the global of the same code at read time. |
| Lineage behavior | Origin edge `data_source → entity` on create; `assert_has_lineage`; manual source per OD-P1B-I. |
| DQ behavior | `not_null` on `code`; `allowed_values` where a controlled vocab applies. |
| Tests | SQLite logic + PG RLS (own+SYSTEM readable, other-tenant invisible, SYSTEM write rejected under tenant context, **no-context read returns only global rows**, override-coexists-and-wins) + endpoint; EV mutability; deny-by-default. |
| Acceptance criteria | Global taxonomies seeded + readable by tenants; tenant overrides shadow globals (tenant wins); writes tenant-isolated; audited + lineage-rooted. |

### P1B-2 — Issuer / Counterparty (REQ-SMR-002; OD-P1B-D)
| Dim | Detail |
|---|---|
| Requirements included | **Separate `issuer` (ENT-002) + `counterparty` (ENT-003)**, both **EV**, **sharing a common legal-entity core** (shared LEI + parent/child hierarchy; distinct role tables) — the canonical-aligned default. |
| Requirements excluded | netting set / CSA depth (OD-015, P1C); a unified single-table `legal_entity`+role (the alternative — requires a canonical-model + REQ-SMR-002 amendment, OD-P1B-D); instrument linkage; ratings assignment. |
| Dependencies | P1B-1 (currency for domicile/reporting ccy); **OD-P1B-D ratification (R-05 + H-04)**. |
| Entities | `issuer`, `counterparty` (+ a shared `legal_entity` core or embeddable for LEI/hierarchy/`parent_id`). |
| APIs | `POST/GET /reference/issuers` + `/reference/counterparties` (+ `/{id}`). |
| Audit / Entitlement | reuse existing `reference.issuer.*` / `reference.counterparty.*`; reference-CRUD audit codes (OD-P1B-E). |
| RLS / Lineage / DQ | **tenant-scoped, proprietary — NEVER hybrid/SYSTEM_TENANT** (the OD-P1B-C invariant); origin lineage; `not_null` on LEI/name. |
| Tests / Acceptance | shared-core hierarchy integrity; issuer vs counterparty role separation; cross-tenant issuer/counterparty invisibility; audited. |

### P1B-3 — Instrument / Identifier Cross-Reference (REQ-SMR-001 + REQ-SMR-003; OD-P1B-A, OD-P1B-G)
| Dim | Detail |
|---|---|
| Requirements included | `instrument` per the **OD-P1B-A split** — identity/master attributes **EV**, **effective-dated economic terms (coupon/maturity/call) FR** per AD-005 §2A / REQ-SMR-001 ("reconstructable as-of"); `identifier_xref` (ENT-004, **EV** effective-dated mapping). |
| Requirements excluded | identifier **authority/precedence** resolution engine (OD-012/P1C — so REQ-SMR-003 is **partially met**, OD-P1B-G); terms math/pricing; market data. |
| Dependencies | P1B-2 (issuer FK), P1B-1 (currency); **OD-P1B-A ratification (FR is the first real bitemporal domain usage — settle before building)**. |
| Entities | `instrument` (EV master) + an **FR-classed instrument-terms** entity/version (FullReproducibleMixin) for economic terms; `identifier_xref` (`entity_type`/`entity_id`/`scheme`/`value`/effective period). |
| APIs | `POST/GET /reference/instruments`; `reference.identifier.resolve` = **deterministic single-result-or-explicit-ambiguity-error** (OD-P1B-G). |
| Audit / Entitlement | reuse `reference.instrument.*`, `reference.identifier.resolve`; reference-CRUD audit codes (OD-P1B-E). |
| RLS / Lineage / DQ | tenant-scoped; origin lineage; `not_null` on primary identifier; `allowed_values` on asset_class/scheme; FR-terms reconstructable as-of (valid-time + system-time). |
| Tests / Acceptance | terms **reconstructable as-of** (FR bitemporal proof, REQ-SMR-001); xref resolves to ONE instrument or an explicit ambiguity error; structural uniqueness on active `(scheme, value)`; genericity (new scheme by value, no migration); **no precedence engine** (scope-fence, OD-012 deferred). |

### P1B-4 — Corporate Actions & Effective-Dated Reference Updates (REQ-SMR-004; OD-P1B-B)
| Dim | Detail |
|---|---|
| Requirements included | `corporate_action` (ENT-008, **EV** per AD-005 §2A / REQ-SMR-004 — effective-dated, "applies on effective date", supersedable/cancellable before application); demonstrate EV effective-dated update/restatement on a P1B-1/3 entity. |
| Requirements excluded | position/valuation adjustment from corporate actions (P1C); automatic application; a separate immutable announcement-event log (a distinct entity decision if ever wanted — **do not** reclass ENT-008 to IA). |
| Dependencies | P1B-3 (instrument); **OD-P1B-B (EV, not IA)**. |
| Entities | `corporate_action` (**EV**, effective-dated; instrument FK; type controlled vocab). |
| Audit / Entitlement | `reference.corporate_action.edit` + the new `reference.corporate_action.view` (OD-P1B-F); reference-CRUD audit codes (OD-P1B-E). |
| RLS / Lineage / DQ | tenant-scoped; origin lineage; `not_null`/`allowed_values` on type/effective-date. |
| Tests / Acceptance | **EV effective-dated supersede** (action applies on its effective date; an amendment supersedes via a new effective version) — **not** an append-only/P0001 proof; cross-tenant isolation; audited + lineage-rooted. |

### P1B-5 — Reference-Data Ingestion Mapping (CONDITIONAL / optional, last)
| Dim | Detail |
|---|---|
| Requirements included | ONLY if bulk loading is needed: map P1A-4 `ingestion_staged_record` rows → P1B canonical reference entities (the first real staging→canonical mapping), reusing `stage_upload` + a thin mapping step; bind `ingestion_batch_id`. |
| Requirements excluded | vendor/SFTP/API adapters (P9); any non-reference mapping. |
| Dependencies | P1B-1…4 entities exist; P1A-4 staging. |
| Acceptance criteria | a staged CSV maps to reference rows with lineage `data_source → ingestion_batch → entity` and DQ gating; **defer if not needed** — direct CRUD already satisfies P1B entry. |

---

## Part 6 — Readiness Summary

- **P1A:** complete, committed, CI-green (HEAD `0282359`); no defect blocks P1B.
- **Rails:** inventoried and reusable. Structural gaps P1B must close, not assume away: the **global-read RLS extension** (OD-P1B-C, an AD-013 refinement); the **`0001` foundation tables are `USING`-only** (replicate the `0004+` explicit-`WITH CHECK` pattern); **no reference-CRUD audit code** and **missing currency/rating_scale/`.view` entitlements** exist yet.
- **P1B:** **ready for planning/decisioning (P1B-0) — not implementation.** P1B-0 must resolve **OD-P1B-A…J**, four of which require ratifying a change against a ratified baseline (instrument FR-split, corporate_action=EV, hybrid-tenancy/AD-013, issuer/counterparty shape) with the named owners (R-01/R-02/R-04/R-05/R-07/H-04). Do **not** begin P1B-1 until those are recorded.
- **No application code, migrations, or rail changes are produced by this document.**

---

## Part 7 — Adversarial Review Record (7 lenses)

A 7-lens UltraCode review of this artifact returned **3 block + 4 ready-with-doc-fixes**; the blocking
findings were **factual/design conflicts in the draft's P1B recommendations** (not P1A defects), all
corrected above and converted into OD-P1B-A…J. Verdicts and headlines:

| Lens | Verdict | Headline |
|---|---|---|
| Product / Requirements | ready-with-doc-fixes | Scope fence & rail facts hold; instrument is REQ-SMR-001 **FR** (draft said EV); currency/rating_scale trace to no REQ. |
| Chief Architect | **block** | Draft's Decision 3 overturned ratified **AD-005** on three entities; service package/dependency direction unstated. |
| Data Architecture | **block** | instrument must **split EV-identity / FR-terms**; `corporate_action` must be **EV not IA**; issuer/counterparty should be **separate sharing a core**, not unified. |
| Security / RLS | **block** | P1A RLS is sound & fail-closed, but the SYSTEM_TENANT hybrid **diverges from AD-013** and needs ratification + a defined fail-closed/override contract. |
| Audit / Controls | ready-with-doc-fixes | Reproducibility chain is sound, no control overstated; reference-CRUD needs **net-new R-07 codes** (no DATA.CREATE/UPDATE exists). |
| Data Quality / Lineage | ready-with-doc-fixes | DQ/lineage reuse is realistic and not overbuilt; specify the **manual `data_source`** mechanics; identifier resolution only partially meets REQ-SMR-003. |
| Scope | ready-with-doc-fixes | Scope discipline exemplary, zero leaks, P1B unstarted; real issues are the AD-005/AD-013 conflicts (now recorded). |

**Disposition:** all 12 must-fix items applied to this document (temporal reclassifications, AD-013
divergence surfaced, issuer/counterparty default flipped, audit/entitlement/requirement gaps recorded,
WITH-CHECK attribution corrected, identifier/manual-source/service-package contracts specified). The
artifact now records conflicts for P1B-0 ratification rather than silently confirming them.
