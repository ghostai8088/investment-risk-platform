# Phase P1A-2 Implementation Plan — Model Registry Skeleton

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1A2PLAN-001 |
| Version | 1.0 (Draft for Review) |
| Status | Draft |
| Owner | H-06 Engineering Lead |
| Approver | H-07 Product Owner (H-02 Model Risk consulted on governance fields; H-03 CISO consulted on RLS/leak vectors) |
| Created | 2026-06-21 |
| Last Reviewed | 2026-06-21 |
| Related Documents | p1a_implementation_plan.md, p1a1_implementation_plan.md, ../02_requirements/requirements_traceability_matrix.md, ../02_requirements/requirements_backbone.md, ../03_architecture/foundational_adrs.md, ../04_data_model/temporal_reproducibility_standard.md, ../04_data_model/audit_event_taxonomy.md, ../04_data_model/canonical_data_model_standard.md, ../06_security/entitlement_sod_model.md, ../07_model_governance/model_governance_independence_policy.md, ../09_compliance_controls/control_matrix_skeleton.md, ../packages/shared-python/src/irp_shared/calc/models.py |
| Supported Build Rules | BR-2, BR-3, BR-4, BR-11, BR-12, BR-14, BR-15, BR-17, BR-19 |

## 1. Requirements included

P1A-2 implements **exactly one** Step-2 backbone requirement and **builds** one forward dependency:

- **REQ-MDG-001 — Model inventory & versioning** (backbone §7 CAP-12.1 model inventory + CAP-12.2 versioning/assumptions/limitations; RTM row 73; Phase **P1**; personas **P-MV** Model Validator (PERSONA-04/H-02, 2L) + **P-RM** Risk Manager (PERSONA-02/H-01, 2L); LoD **2L**; control **CTRL-003** (with **CTRL-014** for limitations); **ModelGov = Y**; audit **BX-AUD**; entitlement **BX-ENT**; lineage column `—` because model registration is **not** a lineage-recorded data output). Backbone acceptance (row L223): *"Register every model/version + assumptions/limitations; no calc runs without an inventory entry (BR-3)."*
- **DEP-MREG** — P1A-2 *is* the build of the model-registry forward dependency (RTM §4 rollup: first needed P1; required-by REQ-MDG-001, REQ-MKT-\*, REQ-CRD-001, REQ-CPT-002). Confirms downstream consumers depend on a **stable `model_version` anchor**.

**Precise in-scope statement.** Establish the model-registry data model (`model` head + immutable `model_version` + minimal `model_assumption` / `model_limitation`) and the `register_model()` / `register_model_version()` capture contract, plus retrieve-the-inventory reads. Concretely the slice ships:

1. `model` (ENT-035, **EV**, tenant-scoped) with DR-P1-3 nullable, non-enforcing maker-checker hook columns and the **reserved non-enforcing** governance placeholder columns (§3).
2. `model_version` (ENT-035, **IA**, immutable — change = new version) — the stable referent for future `CalculationRun`/lineage binding.
3. `model_assumption` + `model_limitation` (ENT-036, **IA**, minimal capture tied to a version).
4. `register_model()` / `register_model_version()` (+ `record_assumption`/`record_limitation`) and an `assert_registered_model_version()` gate — the inventory-write + MG-02/BR-3 verification contract (shared-python).
5. A governed-write `POST /models` plus `GET /models` and `GET /models/{id}` read endpoints (resolved §4).
6. **No new permission** — reuse the existing `model.inventory.register` / `model.inventory.view` (bootstrap.py:26-27), with one role-template grant change (§7).
7. **No new audit code** — reuse the existing `MODEL.REGISTER` + `MODEL.VERSION` (audit_event_taxonomy.md L64, EVT-050…); assumption/limitation writes fold into `MODEL.VERSION` (§6).
8. One Alembic migration (`0005_model_registry_skeleton`, revises `0004_lineage_skeleton`) creating all four tables with FORCE RLS + tenant-isolation policy and append-only enforcement on the three IA tables.

This realizes **MG-01** (definition of a model = metadata only), **MG-02/BR-3** (inventory-before-use), and **BX-LIM/CTRL-014** (limitations documented) at **skeleton level only** — no tier, validation, or approval **enforcement**. REQ-AUD-001 is **satisfied cross-cutting** (the register path emits taxonomy events) and is **not** scoped as a P1A-2 requirement of its own (verified by the shared audit-coverage enforcement test across P1A-1…4, CTRL-012).

**Backbone-shorthand reconciliation.** Backbone §7 CAP-12 (L223) tags Data as `model, model_version (IA)` — shorthand that wrongly implies the `model` head is IA. P1A-2 intentionally refines this to `model = EV` (the head mutates tier/status/owner over time) and `model_version / model_assumption / model_limitation = IA` (immutable). This is a legitimate decomposition authorized by temporal_reproducibility_standard.md §2A (which lists ENT-035 `model_version` and ENT-036 `model_assumption set` under IA), not a conflict — see §10/§17 for the backbone correction, exactly mirroring the P1A-1 `data_source=EV` reconciliation.

## 2. Requirements excluded

The following are explicitly **out of scope** for P1A-2 and must not appear in any deliverable, test, or endpoint:

- **REQ-MDG-002 — Model tiering** (CAP-12.3, RTM row 74, **Phase P7**, DEP-MGW): tier assignment-by-criteria and Tier-1 human-approval gating. `tier` is a **non-enforcing placeholder column** only.
- **REQ-MDG-003 — Validation workflow & effective challenge** (CAP-12.4/12.5, RTM row 75, **Phase P7**, DEP-MGW + REQ-ADM-002/SoD): developer≠validator workflow (SOD-03/MG-04), `validation_status` transitions, approval/restricted-use status workflow, and the **`model_validation` entity (ENT-037)**. `validation_status` / `approved_use` / `restricted_use` / `owner` / `developer` are **non-enforcing placeholders**; MG-04/05/06/07 are **recorded-not-enforced**.
- **Any analytical / risk-model implementation** (VaR, credit, liquidity, scenario, private-asset proxy, AI/ML engines): the registry stores metadata **about** models, never model **logic** (MG-01).
- **Tier ENFORCEMENT, model VALIDATION workflow, model APPROVAL workflow, challenger workflow, model performance monitoring** (MG-09…14; MODEL.VALIDATE/.APPROVE/.RESTRICT/.RETIRE reserved EVT-050+).
- **Maker-checker approval ENFORCEMENT** (DR-P1-3 → P6): the `model` head's nullable `approval_status`/`approval_ref`/`made_by`/`checked_by` hooks are non-enforcing.
- **Sibling P1A slices**: REQ-LIN-001 lineage (P1A-1), REQ-DQR-001 data quality (P1A-3), REQ-INT-001 ingestion (P1A-4); and P1B/P1C.
- **All domain requirements** (PPM/SMR/PUB/PRV/MKT/CRD/CPT/LIQ/SCN/LIM/BRC) and every domain entity: no instrument, issuer, portfolio, position, valuation, or risk-result entity; no Security Master, Reference Data, dashboards, reporting, private assets.
- **Real SSO / verified tenant identity** (P9 — the dev `X-User-Id` / `X-Tenant-Id` header shim remains *unverified* per DR-P1A0-3/AD-007).
- **Methodology documents** (BR-2/CTRL-002 — no calc in P1A-2; a `methodology_ref` string pointer is captured, the document itself is not).

QA scope note: the BR-3 inventory-before-use gate is tested with a **synthetic unregistered `model_version_id`** (not a domain calc) so the contract is proven without pulling in any excluded slice — exactly mirroring P1A-1's synthetic-governed-write pattern. A negative scope-fence test asserts P1A-2 emits **none** of the reserved `MODEL.VALIDATE/.APPROVE/.RESTRICT/.RETIRE` codes, and that `tier`/`validation_status`/`approved_use`/`owner` are writable but enforce nothing.

## 3. Proposed database entities

Four new tables, one migration (`0005_model_registry_skeleton`, revises `0004_lineage_skeleton`). All four are tenant-scoped and carry FORCE RLS + a `tenant_isolation_<table>` policy reusing the migration `0004` `TENANT_SCOPED_TABLES` loop verbatim (USING **and** explicit WITH CHECK). ORM models follow the established `calc/models.py` / `lineage/models.py` pattern: `class X(PrimaryKeyMixin, TenantMixin, <TemporalMixin>, Base)` with an explicit `__temporal_class__`. Named `pk_`/`ix_`/`uq_`/`fk_` constraints satisfy the `alembic check` drift gate + NAMING_CONVENTION.

**Genericity contract (load-bearing, MG-01).** `model_type` is a **controlled-vocabulary `String(50)` — NOT a Python `Enum`, NOT a DB `CHECK`/enum type** — so market/credit/liquidity/scenario/private-asset-proxy/AI-ML model families register by supplying a **new value, never a schema migration**. This mirrors the domain-agnostic polymorphic pattern already proven in-repo by `lineage_edge.source_type` and `audit_event.entity_type`. No table carries a foreign key to any domain/analytical table.

**Governance-attribute placement (deliberate EV-head vs IA-version split).** Governance state that **mutates** over a model's life (tier, owner, validation_status, approved_use, restricted_use) lives on the **EV `model` head** so it can change without minting a new version; the **immutable, version-bound facts** (assumptions, limitations, methodology_ref, code_version) live on/under the **IA `model_version`**. This is correct because MG-09/10 require a *new version* to re-enter validation, while tier/owner/status are model-level governance state, not version-level immutable facts.

### 3.1 `model` (ENT-035, EV, tenant-scoped)

```
class Model(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base)
    __tablename__ = "model"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
```

| Column | Type | Null | Source / Notes |
|---|---|---|---|
| `id` | GUID PK | no | PrimaryKeyMixin |
| `tenant_id` | GUID (indexed) | no | TenantMixin; RLS predicate column; **server-stamped from context, never caller-supplied** |
| `valid_from` / `valid_to` | DateTime(tz) | no / yes | EffectiveDatedMixin (null `valid_to` = currently effective) |
| `created_at` / `created_by` / `updated_at` / `updated_by` | — | mixed | TimestampMixin |
| `record_version` | Integer | no (default 1) | **Additive** — satisfies canonical §4 mandatory common column and §2A EV system-time-versioning (EffectiveDatedMixin omits it); mirrors the P1A-1 `data_source` OQ-VER resolution |
| `code` | String(150) | no | Stable business key (per-tenant unique) |
| `name` | String(255) | no | Display name |
| `model_type` | String(50) | no | **Controlled-vocab string, no enum/CHECK** (the genericity contract); seed minimally e.g. `STATISTICAL`/`ANALYTICAL`/`AI_ML`; promote to reference data (DM-N-08) later |
| `description` | String(500) | yes | |
| `is_active` | Boolean | no (default true) | |
| `owner` | String(255) | yes | **Non-enforcing** — model owner principal/team; reserved for MG-04/SOD-03 |
| `developer` (a.k.a. `developed_by`) | String(255) | yes | **Non-enforcing** — maker/author side of the future SOD-03 maker-checker; free string accepting a human **or** an AI-agent principal id (MG-05 attribution) |
| `tier` | String(20) | yes | **Non-enforcing placeholder** — reserved for REQ-MDG-002/P7 |
| `validation_status` | String(30) | yes (default `UNVALIDATED`) | **Non-enforcing placeholder** — reserved for REQ-MDG-003/P7; never advanced by any P1A-2 path |
| `approved_use` | String(500) / Text | yes | **Non-enforcing placeholder** — reserved for MG-11/P7 |
| `restricted_use` | Boolean | yes (default false) | **Non-enforcing placeholder** — reserved for MG-12/P7 |
| `restriction_reason` | String(500) | yes | **Non-enforcing placeholder** — reserved for MG-12/P7 |
| `approval_status` | String(20) | yes | **DR-P1-3 hook — non-enforcing** (reserved P6 maker-checker) |
| `approval_ref` | String(255) | yes | **DR-P1-3 hook — non-enforcing**; maps to audit `approval_ref` for future linkage |
| `made_by` | String(255) | yes | **DR-P1-3 hook — non-enforcing** |
| `checked_by` | String(255) | yes | **DR-P1-3 hook — non-enforcing** |

Constraints/indexes: `UniqueConstraint('tenant_id','code', name='uq_model_tenant_code')`; named tenant index `ix_model_tenant_id`. `model` is **EV (mutable)** and does **NOT** get the append-only trigger.

> **Resolved divergence (OQ-P1A-2-FIELDS, §15).** The Chief Architect lens recommended **omitting** `tier`/`validation_status`/`approved_use` (carrying only the DR-P1-3 hooks) on the grounds these belong to ENT-037 (P7). The Model-Governance, Data-Architecture, Product, Security, and QA lenses recommended **reserving** them as nullable non-enforcing columns to avoid a P7 `ALTER` on the EV head. **Decision: RESERVE them (the majority position), with the architect's coupling fence enforced** — they are nullable, default-unset, write-but-do-not-gate, documented "non-enforcing, reserved REQ-MDG-002/003 (P7)," and locked by the AC-7 non-enforcement test (a Tier-1 `UNVALIDATED` model registers and binds with no gate). This pays a few nullable columns now to save a cross-entity migration in P7 and keeps the canonical-model semantics on the validation **workflow** (ENT-037), not the fields, in P7.

### 3.2 `model_version` (ENT-035, IA, tenant-scoped)

```
class ModelVersion(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base)
    __tablename__ = "model_version"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
```

| Column | Type | Null | Source / Notes |
|---|---|---|---|
| `id` | GUID PK | no | PrimaryKeyMixin |
| `tenant_id` | GUID (indexed) | no | TenantMixin; RLS predicate; **server-stamped** |
| `system_from` | DateTime(tz) | no (default `utcnow`) | ImmutableAppendOnlyMixin — the **only** temporal axis (TR-21); no `valid_from`/`valid_to` |
| `model_id` | GUID | no | **Real intra-context FK** → `model.id` (`fk_model_version_model_id_model`) — both tables are in the model-registry bounded context (BC-11), so this does NOT cross a context boundary (unlike the polymorphic no-FK `lineage_edge`) |
| `version_label` | String(50) | no | e.g. `1.0.0` |
| `methodology_ref` | String(500) | yes | Pointer to a methodology doc (BR-2/MG-05); the document itself is not in scope |
| `code_version` | String(100) | yes | Mirrors `CalculationRun.code_version` semantics |
| `status` | String(20) | yes | **Non-enforcing** version status placeholder (e.g. `DRAFT`/`REGISTERED`); NOT a validation gate |

Constraints: `UniqueConstraint('tenant_id','model_id','version_label', name='uq_model_version_tenant_model_label')`; index `ix_model_version_tenant_id`. **No `created_by`/`updated_by`** (IA — actor attribution lives in the `MODEL.VERSION` audit event; `system_from` is the record timestamp). Add to `APPEND_ONLY_TABLES` (DB trigger) **and** an ORM `before_update`/`before_delete` guard (§3.5). `model_version` is the **stable, durable anchor** for future `CalculationRun.model_version_id` and run→result lineage (TR-11, AD-006).

### 3.3 `model_assumption` (ENT-036, IA, tenant-scoped)

```
class ModelAssumption(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base)
    __tablename__ = "model_assumption"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
```

| Column | Type | Null | Source / Notes |
|---|---|---|---|
| `id` | GUID PK | no | PrimaryKeyMixin |
| `tenant_id` | GUID (indexed) | no | TenantMixin; **server-stamped from the resolved parent** |
| `system_from` | DateTime(tz) | no | ImmutableAppendOnlyMixin |
| `model_version_id` | GUID | no | **Intra-context FK** → `model_version.id` (`fk_model_assumption_model_version_id_model_version`); ENT-036 "declared per version" |
| `assumption_text` | Text / String | no | The captured assumption |
| `category` | String(50) | yes | Optional label (minimal; no controlled-vocab enforcement) |
| `authored_by` | String(255) | yes | **Governance-critical** — free string accepting a human **or** AI-agent principal id so MG-05 (AI may draft) authorship is attributable for the future MG-04 dev≠validator check |

### 3.4 `model_limitation` (ENT-036, IA, tenant-scoped)

```
class ModelLimitation(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base)
    __tablename__ = "model_limitation"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
```

| Column | Type | Null | Source / Notes |
|---|---|---|---|
| `id` | GUID PK | no | PrimaryKeyMixin |
| `tenant_id` | GUID (indexed) | no | TenantMixin; **server-stamped from the resolved parent** |
| `system_from` | DateTime(tz) | no | ImmutableAppendOnlyMixin |
| `model_version_id` | GUID | no | **Intra-context FK** → `model_version.id` (`fk_model_limitation_model_version_id_model_version`) |
| `limitation_text` | Text / String | no | BX-LIM/CTRL-014 capture |
| `severity` | String(20) | yes | Optional label (minimal; no workflow/enforcement) |
| `authored_by` | String(255) | yes | Same MG-05 attribution rationale as `model_assumption` |

> **Intra-context FK note.** `model_version.model_id`, `model_assumption.model_version_id`, and `model_limitation.model_version_id` are **real FKs** because all four tables live in the same bounded context (BC-11), all rows share the same `tenant_id` (stamped server-side), and this does **not** violate ARCH-P-01/DM-N-09. **Caveat (P1A-1 lesson):** an FK does **not** enforce same-tenant integrity across the RLS boundary — `register_model()` MUST resolve the parent through the RLS-scoped session and stamp each child's `tenant_id` server-side from the resolved parent (§8). The canonical mandatory `source_id` FK (every *domain* record → `data_source`, BR-13) does **NOT** apply here: a model is methodology metadata, not ingested data (consistent with §9 "registration is not a data output"). No `source_id` column on `model`/`model_version`.

### 3.5 IA append-only enforcement (both layers)

Add `('model_version', 'model_assumption', 'model_limitation')` to the migration's `APPEND_ONLY_TABLES` so the existing `irp_prevent_mutation()` trigger (from `0001`) blocks UPDATE/DELETE at the DB layer, **and** add an ORM `event.listen(<cls>, 'before_update'/'before_delete', _block_mutation)` guard raising `AppendOnlyViolation` (mirroring `lineage/models.py`) so IA is provable on both SQLite-local and Postgres-CI. `model` (EV) gets **neither** — a negative-control test (§12) proves the trigger is not over-applied.

## 4. Proposed API surfaces

**Resolution (OQ-P1A-2-API, §15): expose a governed `POST /models` write endpoint plus read endpoints — the legitimate-write case that genuinely differs from P1A-1.**

| Surface | Method | Auth | Behavior |
|---|---|---|---|
| `POST /models` | write | `require_permission('model.inventory.register')` under `get_tenant_session` | Register a model + initial `model_version` (+ optional assumptions/limitations) in one tenant-scoped transaction. Thin wrapper over `register_model()`. |
| `GET /models` | read | `require_permission('model.inventory.view')` under `get_tenant_session` | RLS-scoped inventory list (caller's tenant only). |
| `GET /models/{id}` | read | `require_permission('model.inventory.view')` under `get_tenant_session` | Detail with nested versions + assumptions + limitations; `uuid.UUID` path param. |

**Why `POST /models` (vs the P1A-1 no-public-write stance).** Unlike P1A-1 lineage (recorded as a *side-effect* of governed writes, hence utility-only), model registration is a **legitimate, user-initiated, first-class governed write** with its own existing write permission (`model.inventory.register`) and its own backbone functional requirement (REQ-MDG-001 "Register every model/version") and persona (a model owner/developer). The P1A-1 no-public-write rationale does not transfer. The Chief Architect lens preferred a read-only API + internal utility to keep one P1A pattern and an open contract; Product, Security, Model-Governance, and QA preferred the gated POST. **Decision: gated POST**, because the permission and user journey already exist and the contract is well-bounded at skeleton scope. The single contract is single-sourced: `register_model()` lives in `irp_shared.model` (callable by backend **and** workers); the endpoint is a thin wrapper.

**Hard guardrails (Scope/Governance lens):** reject any `POST/PUT /models/{id}/validate|approve|restrict|retire` or any tier/validation/approval **workflow** endpoint (REQ-MDG-002/003/P7); the register payload MAY record `tier`/`owner`/`developer`/`validation_status` as **metadata** but the endpoint MUST treat **none** of them as a gate (no "403 unless Tier-1 approved", no "reject unless validated"); `validation_status` defaults to `UNVALIDATED` and is never advanced.

**Endpoint requirements (Security lens):**
- MUST depend on `get_tenant_session` (sets `app.current_tenant`), **not** `get_db`, so RLS scopes/stamps every read/write to the caller's tenant.
- `POST /models` **never** reads `tenant_id` from the body (server-stamps from principal/context); a forged/foreign `tenant_id` is ignored and backstopped by `WITH CHECK` → SQLSTATE 42501. Audits `MODEL.REGISTER` + `MODEL.VERSION` in the **same** transaction (fail-closed rollback).
- For reads, entitlement (403) is checked **first**, then the RLS-scoped lookup yields **404** for both "not found" and "exists in another tenant" — the two cases must be **indistinguishable** (fixed detail body, no existence/oracle leak; never 200 for a cross-tenant id). `GET /models` list returns only the caller's tenant's rows.
- Malformed `uuid` path param → uniform **422** before any DB hit; missing principal headers → **401**.

## 5. Worker / CLI impact

- **No standalone worker or CLI in P1A-2.** No model-import job, no inventory-export CLI, no validation worker (validation is P7).
- **`register_model()` / `register_model_version()` (+ `record_assumption` / `record_limitation`) MUST live in a new `irp_shared.model` package** (shared-python), a **sibling to `irp_shared.lineage` and `irp_shared.calc`**, **not** in `apps/backend`. Placing them in backend would couple workers/ingestion and the calc engine (AD-006 FW-MDL references the registry) to the web app and break the single-contract guarantee — this is the P1A-1 R3/AC-8 trap applied to the registry.
- The utilities take a **caller-managed `Session`**, run **co-transactionally** with the audit write (same pattern as `record_event` / `register_data_source` / `create_run`), and **stamp `tenant_id` server-side**. They MUST NOT COMMIT/ROLLBACK mid-call in a request scope (the single-transaction invariant; a mid-call commit drops the transaction-local GUC and the next write fails closed).
- Ship `assert_registered_model_version(session, model_version_id, *, tenant_id=None)` → raises `UnregisteredModelError` | returns the `ModelVersion`. This is the operational hook that makes **MG-02/BR-3/CTRL-003** testable now (the analog of P1A-1's `assert_has_lineage`).
- The slice's primary downstream deliverable is that it supplies **real `model_version` rows** that FW-RUN `CalculationRun.model_version_id` will reference and that future BX-LIN run→result lineage anchors on.

## 6. Audit events — resolved

**Decision (resolves OQ-P1A-2-AUDIT): reuse the two existing taxonomy codes; mint NO new code; fold assumption/limitation capture into `MODEL.VERSION`.**

The MODEL category already exists (audit_event_taxonomy.md L64, EVT-050…): `MODEL.REGISTER`, `.VERSION`, `.VALIDATE`, `.APPROVE`, `.RESTRICT`, `.RETIRE`.

| Governed write | Event code | Notes |
|---|---|---|
| `model` create | `MODEL.REGISTER` | `record_event(session, event_type='MODEL.REGISTER', tenant_id=<ctx>, actor_type='user'|'agent', actor_id=<principal>, source_module='model', entity_type='model', entity_id=<model.id>, action='create', after_value={code,name,model_type,owner,tier:null,validation_status:null,approved_use:null,approval_status:null}, data_classification='DC-1')` |
| `model_version` create (incl. its assumptions/limitations) | `MODEL.VERSION` | `entity_type='model_version'`, `entity_id=<version.id>`; `after_value={model_id, version_label, is_immutable:true, assumption_count, limitation_count}` (optionally a content hash so an auditor can reconcile captured items to the audited version) |
| `model_assumption` / `model_limitation` write | **none** | **Folded into `MODEL.VERSION`.** They are IA captures co-created with (and immutable to) a single version in the **same transaction** — metadata of the already-audited version write, exactly as `lineage_edge` is metadata of a governed write (P1A-1 §6 precedent, no per-edge event). A dedicated code would double-count and inflate the taxonomy. |

**Reserved-but-unused in P1A-2:** `MODEL.VALIDATE`, `MODEL.APPROVE`, `MODEL.RESTRICT`, `MODEL.RETIRE` are **reserved** for the P7 validation/approval/restricted-use/retirement workflow (REQ-MDG-002/003; MG-09…12). Do **not** emit or reference them. A negative scope-fence test asserts none are emitted on any P1A-2 path. Document them as reserved so P7 does not re-litigate.

**Fail-closed (AUD-04 / CTRL-005 / CTRL-012 / CTRL-032):** each `record_event` MUST occur in the **same tenant-scoped transaction** as the `model`/`model_version` row (mirror `register_data_source`: add row → flush → `record_event` → return, no mid-call commit); if the audit insert is rejected (RLS 42501 or hash-chain failure) the registry row MUST roll back, never silently persist. `record_event` itself writes to the tenant-scoped + FORCE-RLS `audit_event`, inheriting the same fail-closed-without-context behavior.

**Correlation:** `MODEL.REGISTER` and the first (and any later) `MODEL.VERSION` should share a `correlation_id` per registration request so an auditor can join a model to its versions without extra events.

**AI-authorship (MG-08/BR-16):** when a model/version/assumption is registered by an AI-agent principal (MG-05 AI may draft), the `MODEL.REGISTER`/`MODEL.VERSION` event MUST carry `actor_type='agent'` + `agent_model`/`agent_model_version` + `on_behalf_of` (the audit schema already supports these); `register_model()` passes these through so agent-authored inventory is logged — even though no approval is enforced.

**Note:** `event_type` is a free-form string (no code-level allowlist exists in `audit/service.py record_event`), so a typo passes silently — the cross-cutting audit-coverage test (CTRL-012) MUST assert the **literal** `MODEL.REGISTER`/`MODEL.VERSION` codes and `entity_type`.

## 7. Entitlement checks

All access is `require_permission`-gated, deny-by-default, tenant-scoped (BX-ENT, CTRL-011), sequenced under `get_tenant_session` so RLS does not false-deny the principal's own `role`/`user_role` rows. **No new permission is created** (the key difference from P1A-1, which had to add `lineage.source.manage`).

| Permission | Status | Gates | Currently granted to |
|---|---|---|---|
| `model.inventory.view` | **Exists** (bootstrap.py:26) | `GET /models`, `GET /models/{id}` | `risk_analyst_1l`, `risk_manager_2l`, `auditor_3l`, `platform_admin` |
| `model.inventory.register` | **Exists** (bootstrap.py:27) | `POST /models` + `register_model()` call site | `platform_admin` only (via `ALL_CODES`) — verified by reading bootstrap.py |

**Decision (resolves OQ-P1A-2-ENT/PERSONA): grant `model.inventory.register` to `risk_analyst_1l` (the 1L model developer/owner — the maker side of the future SOD-03 maker-checker) in addition to `platform_admin`.** Do **NOT** grant it to:
- `auditor_3l` (3L read-only independence), or
- `risk_manager_2l` / the future ROLE-MV model-validator role — granting register to the **independent validator** would pre-seed a `dev = validator` conflict that **MG-04/SOD-03/CTRL-022** forbid (even though P1A-2 enforces no validation, this sets the least-privilege precedent P7 needs).

`model.inventory.view` stays exactly as-is (the inventory **readers** P-MV/P-RM/P-RA/admin per RTM row 73 + UJ-3). Every grant gets a **deny-by-default test**: an ungranted principal → `PermissionDenied`/403; a `view`-only principal cannot register. No `model.approve` / `model.validate` permission is created (those are P7). The product principle: **"developer registers; validator only reads (until P7 validation)."** This is a role-template grant decision only — `platform_admin` already holds `register`, so the slice is buildable even if the grant decision slips.

## 8. RLS / tenant-context behavior (built on P1A-0)

All four tables are tenant-scoped and rely entirely on the P1A-0 wiring (AD-015/AD-016): per-session `app.current_tenant` via `set_config(..., is_local=true)` (transaction-local) + durable pool `RESET`; `get_tenant_session` dependency; `run_in_tenant` for worker paths. All P1A-2 DB surfaces MUST run under this context; missing context **fails closed**.

Confirmed behaviors (mirroring `test_lineage_pg.py` under the constrained non-superuser `irp_app` role):
- **Policy form (identical to migration `0004`):** `ENABLE` + `FORCE` ROW LEVEL SECURITY (FORCE so the app role is also subject to RLS, BR-17/AD-013) + `tenant_isolation_<t>` with `USING` **and** explicit `WITH CHECK` (resolved — OQ-P1A-2-SEC-1; mandatory because these are new write-bearing tables and the SYSTEM_TENANT_ID option introduces read/write-scope divergence).
- **No-context fail-closed:** with the GUC unset, `current_setting('app.current_tenant', true)` returns NULL → reads return empty, INSERTs rejected with **SQLSTATE 42501** on all four tables.
- **Tenant-mismatch write denied:** under context A, inserting `tenant_id=B` is rejected by `USING`/`WITH CHECK` (42501); `tenant_id` is server-stamped, never caller-supplied.
- **Parent→child same-tenant binding (the NEW vector vs P1A-1):** `model_version`/`assumption`/`limitation` reference `model.id`/`model_version.id`, but an FK cannot span the RLS boundary and RLS protects the **row**, not the **reference**. Therefore `register_model()`/`register_model_version()` MUST **resolve the parent through the RLS-scoped session** (a cross-tenant parent id → zero rows → fail closed, mirroring `record_lineage`'s `DataSourceNotVisible` guard) and **stamp each child's `tenant_id` server-side from the resolved parent** — never from caller input; cross-tenant child inserts are also backstopped by `WITH CHECK`.
- **Single-transaction invariant:** the utilities MUST NOT COMMIT/ROLLBACK mid-call in a request scope (a mid-call commit drops the transaction-local GUC and the next write fails closed).

**Ops-role isolation (AD-015):** the BYPASSRLS `irp_ops` role MUST have **no** grant (SELECT/INSERT/UPDATE/DELETE) on `model`/`model_version`/`model_assumption`/`model_limitation`; no P1A-2 code path connects via the ops `DATABASE_URL`; the app DB role stays NOSUPERUSER NOBYPASSRLS. A regression test asserts `has_table_privilege('irp_ops', <table>, …)` is False (mirroring `test_ops_role_has_no_grant_on_lineage_tables`). The PG-CI fixture must `GRANT SELECT,INSERT` on the four new tables (+ `audit_event` already granted) to `irp_app`.

**SYSTEM_TENANT_ID global/template models (OQ-P1A-2-1 resolution):** **tenant-scoped by default**; the mechanism for global/template models under the reserved `SYSTEM_TENANT_ID` (`00000000-0000-0000-0000-000000000001`, already in bootstrap.py) is **available with FORCE RLS retained** (no RLS-exempt table), but **no system-tenant models are seeded or enabled in P1A-2** and **cross-tenant READ is NOT widened** (that would require `tenant_id = current OR tenant_id = SYSTEM_TENANT_ID` in the `USING` clause and is a deliberate, separately-tested later change). This mirrors the resolved P1A-1 OQ-P1A-1-2 and keeps strict tenant-equality; it is never a doorway to general global data. Governance note: a global model still needs per-tenant tier/approval state eventually, so global is the deliberate exception, not the default.

## 9. Lineage behavior

Model registration is **NOT a data output and is NOT lineage-recorded** — `record_lineage()` is **not** called for `register_model()` / `register_model_version()` (confirmed: RTM row 73 lineage column = `—`). There is **no schema change to `lineage_edge`** and **no import dependency** between `irp_shared.model` and `irp_shared.lineage`.

`model_version` is the **referent** of future RUN/RESULT lineage: `calculation_run.model_version_id` → the canonical `source→run→result` chain materialized in `lineage_edge` later (P2+, via the existing logical `run_id` reference), with `model_version` reachable **transitively through the run** (TR-11, canonical §6). Dependency direction is strictly **calc → model** (a run references a model version), never model → calc, so **no circular dependency** exists with `calculation_run`, `lineage_edge`, `data_source`, or the future `data_snapshot`. No FK from `model_version` to `data_source`/`data_snapshot`. The only governance action in P1A-2 is ensuring `model_version.id` is a stable GUID the future lineage/run can bind.

## 10. Temporal classification

| Entity | Class | Mixin | Authority |
|---|---|---|---|
| `model` (ENT-035) | **EV** | `EffectiveDatedMixin` (+ `record_version`) | The head mutates governance state (tier/validation_status/owner/approved_use/restricted_use) over time, current-state queryable with retained history via the audit trail. Not in §2A's IA list; correctly classed EV as registry/config (parity with `data_source`). |
| `model_version` (ENT-035) | **IA** | `ImmutableAppendOnlyMixin` | temporal_reproducibility_standard.md §2A **explicitly lists "ENT-035 model_version" under IA**. A version is immutable; change = new version (TR-06/TR-11/MG-10). |
| `model_assumption` (ENT-036) | **IA** | `ImmutableAppendOnlyMixin` | §2A **explicitly lists "ENT-036 model_assumption set" under IA**. Immutable capture tied to a version. |
| `model_limitation` (ENT-036) | **IA** | `ImmutableAppendOnlyMixin` | IA by parity with `model_assumption` — immutable capture tied to a version. |

Each entity declares `__temporal_class__` (BR-19, CTRL-017). IA tables carry **only** `system_from` (single axis, TR-21).

**Two flagged doc discrepancies to reconcile (not model changes):**
1. Backbone §7 CAP-12 (L223) tags Data as `model, model_version (IA)` — shorthand that wrongly implies the `model` head is IA. The plan/standard split (`model=EV`, `model_version/assumption/limitation=IA`) is **authoritative** (temporal §2A). Update the CAP-12 Data column to read `model (EV), model_version (IA), model_assumption/model_limitation (IA)` when REQ-MDG-001 moves off Draft — so an implementer does not pick `ImmutableAppendOnlyMixin` for the mutable `model` head (a silent CTRL-017 mis-classification and an append-only trigger on a table that legitimately UPDATEs). This mirrors the P1A-1 CAP-14 `(IA)`-shorthand fix.
2. `EffectiveDatedMixin` provides only `valid_from`/`valid_to` — it lacks the `system_from`/`record_version` §2A's EV system-time-versioning implies. Resolve identically to P1A-1 OQ-VER: add an explicit `record_version` Integer column on the `model` head only; do **NOT** modify the shared mixin (would ripple to `data_source` and future EV tables). Flag to R-05/H-04 that the mixin is lighter than §2A's EV definition.

## 11. Data dictionary impact

Additions limited to the four new entities and the vocabulary this slice introduces (per DM-N-06/DM-N-07, every field needs a DC-\* classification tag; CTRL-004):

- **`model` (ENT-035, EV):** all columns; `code`/`name`/`model_type`/`owner`/`description` are **DC-1/DC-2** (registry metadata, not client data). Document `model_type` as a **controlled-vocabulary string** (the genericity contract) seeded minimally, with a note that new model families add **values, not columns**. Document `tier`/`validation_status`/`approved_use`/`restricted_use`/`restriction_reason`/`owner`/`developer` explicitly as **"non-enforcing placeholder, reserved for REQ-MDG-002/003 (P7)"**; DR-P1-3 hooks as **"non-enforcing, reserved P6 maker-checker."** Record the temporal class (EV) and `record_version`.
- **`model_version` (ENT-035, IA):** all columns DC-1/DC-2 structural metadata; `methodology_ref`/`code_version` may be **DC-2/DC-3** if they point at proprietary quant detail — flag to H-04. Record the temporal class (IA).
- **`model_assumption` / `model_limitation` (ENT-036, IA):** `assumption_text`/`limitation_text` are **DC-2** (model IP, possibly commercially sensitive) — flag to H-04; `authored_by` documented as supporting MG-05 AI-or-human attribution. Record the temporal class (IA).
- **Reused event codes** `MODEL.REGISTER` / `MODEL.VERSION` (EVT-050…) as the controlled-vocabulary entries already present (no new EVT-nnn); `MODEL.VALIDATE/.APPROVE/.RESTRICT/.RETIRE` annotated reserved/unused-in-P1A-2.

Design note: `canonical_data_model_standard.md` §5 already lists ENT-035/036/037 — **no entity-set change**, only dictionary detail. Do **NOT** register **ENT-037 `model_validation`** (P7), any tier-criteria reference table, or any domain/canonical-mapping entity now.

## 12. Tests

Split by harness, mirroring P1A-1's three-file layout. **SQLite-local** (fast unit; RLS is a no-op) reuses the in-memory `session`/`seed` fixtures in `packages/shared-python/tests/conftest.py`; **Postgres-CI** (RLS/fail-closed) runs in the CI `migration` job under the **constrained non-superuser `irp_app` role**, reusing the `app_url` fixture + `_is_rls_violation` (SQLSTATE 42501) helper from `test_lineage_pg.py`. RLS proofs MUST NOT run as superuser or on SQLite (they pass vacuously). Coverage target: DR-P1-4 advisory ≥85% on the new `irp_shared.model` modules.

**Apply the three P1A-1 CI lessons everywhere:** (a) tables use **native postgres `uuid`**; psycopg3 returns `uuid` columns as `uuid.UUID` — use the ORM/`GUID` type for inserts, `CAST(:x AS uuid)` for raw `text()` comparisons/mutations by id, and `str(r[0])` when reading `uuid` columns via `text()`; (b) assert SQLSTATE 42501 via the `_is_rls_violation` helper; (c) the **`alembic check` drift gate** requires `0005` to EXACTLY match the four models + NAMING_CONVENTION (`pk_`/`ix_`/`uq_`/`fk_`) — declare the three intra-context FKs in BOTH the ORM and the migration with matching `fk_` names.

**SQLite-local — model / temporal / utility (`packages/shared-python/tests/test_model_registry.py`):**
1. Temporal classes: `Model.__temporal_class__ == EFFECTIVE_DATED` (valid_from/valid_to present); `ModelVersion`/`ModelAssumption`/`ModelLimitation == IMMUTABLE_APPEND_ONLY` (system_from present, no valid_to, TR-21).
2. `register_model(...)` creates a `Model` inventory row queryable by id, `tenant_id` stamped server-side.
3. `register_model_version(...)` creates an immutable `ModelVersion` linked via `model_id`, queryable.
4. Register a version WITH assumptions + limitations in one call → `ModelAssumption` + `ModelLimitation` rows persisted, each tied to `model_version_id` (ENT-036).
5. Multiple versions per model: register v1, v2 → two distinct immutable versions; `model` (EV) head mutates status/owner without violating IA on versions.
6. `UniqueConstraint(tenant_id, code)` rejects duplicate model code within a tenant, allows same code across tenants; `UniqueConstraint(tenant_id, model_id, version_label)` rejects a duplicate version label.
7. DR-P1-3 hooks and governance placeholders (`tier`/`validation_status`/`approved_use`/`owner`) default NULL and are writable but **enforce nothing**.

**SQLite-local — genericity / extensibility (the AC-8 analog, architect-load-bearing):**
8. `register_model` with an **arbitrary `model_type` string** (`'MARKET_VAR'`, `'PRIVATE_ASSET_PROXY'`, `'AI_ML'`) succeeds with NO schema branch — proving new model families need no migration.

**SQLite-local — audit (CTRL-005, BX-AUD, fail-closed AUD-04/CTRL-032):**
9. `register_model` emits **exactly one** `MODEL.REGISTER` (`entity_type='model'`, `entity_id==model.id`) and `verify_chain(session, tenant).ok is True`.
10. `register_model_version` emits **exactly one** `MODEL.VERSION` (`entity_type='model_version'`, `entity_id==version.id`); multiple versions → multiple events, chain still verifies.
11. **(decision-locking)** adding assumptions/limitations to a version emits **NO additional** `MODEL.*` event (folded into `MODEL.VERSION`); assert audit count by `event_type` unchanged, and `after_value` reflects `assumption_count`/`limitation_count`. (Locks OQ-P1A-2-AUDIT the way P1A-1's no-per-edge-event test locked its decision.)
12. **(fail-closed)** monkeypatch `record_event` to raise → `register_model`/`register_model_version` rolls back the data row (no orphaned model/version persists).
13. **(reserved-codes guard)** the skeleton emits **none** of `MODEL.VALIDATE/.APPROVE/.RESTRICT/.RETIRE` on any P1A-2 path.

**SQLite-local — immutability (IA, ENT-035/036, headline negative):**
14. **(negative)** ORM append-only guard: persist+commit a `ModelVersion`, mutate a field → `flush()` raises `AppendOnlyViolation`; `delete` → raises. Repeat for `ModelAssumption` and `ModelLimitation`.
15. **(positive contrast)** `Model` (EV) is mutable: update `status`/`owner`/`tier`/`validation_status` → succeeds, `record_version` bumps, NO `AppendOnlyViolation` (proves `model` is EV not IA, and placeholder governance fields are writable but non-enforcing).

**SQLite-local — BR-3 inventory-before-use gate (MG-02/CTRL-003, the synthetic-check headline):**
16. **(negative)** a synthetic governed/calc use referencing a random (unregistered) `model_version_id` → `assert_registered_model_version` raises `UnregisteredModelError`.
17. **(happy companion)** register model+version first, then the same check passes and returns the version.
18. **(tenant-scoping at logic level)** a version registered under tenant A does NOT satisfy the gate when checked under tenant B's scope (mirror `test_assert_has_lineage_is_tenant_scoped`).

**SQLite-local — entitlement deny matrix (CTRL-011, BR-11; permissions EXIST, so this EXTENDS):**
19. Extend `test_entitlement_bootstrap.py`: assert `model.inventory.register`/`model.inventory.view` in `ALL_CODES`; `register` granted to `platform_admin` (via `ALL_CODES`) **and** `risk_analyst_1l`, NOT to `auditor_3l`/`risk_manager_2l`; `view` held by `risk_analyst_1l`/`risk_manager_2l`/`auditor_3l` (lock current state).
20. **(negative)** no grant → `has_permission(...,'model.inventory.register',...)` is False; `require_permission(...)` raises `PermissionDenied`.
21. **(negative)** a `model.inventory.view`-only principal CANNOT register; tenant-mismatch principal → `has_permission` False.

**Postgres-CI (`packages/shared-python/tests/test_model_registry_pg.py`, constrained `irp_app`, after `alembic upgrade head`):**
22. Tenant isolation on all four tables: context A sees only A's rows; B invisible.
23. **(negative, fail-closed)** no `app.current_tenant` → INSERT into each of the four tables raises with `_is_rls_violation` True (42501); SELECT count == 0 (ORM insert so `GUID` binds uuid correctly).
24. **(negative)** context A, insert `tenant_id=B` into `model`/`model_version` → rejected by `USING`+`WITH CHECK` (42501).
25. **(negative, cross-tenant parent ref)** register a version/assumption/limitation against a parent id owned by tenant B while under context A → parent resolves to zero rows → `ModelNotVisible`, no cross-tenant child row created.
26. **(negative, append-only at DB)** raw `UPDATE`/`DELETE` (via `CAST(:i AS uuid)`, re-setting context first so the row is RLS-visible for the per-row trigger) on `model_version`/`model_assumption`/`model_limitation` → `ProgrammingError` from `irp_prevent_mutation()`.
27. **(negative-control)** `model` (EV) is NOT in `APPEND_ONLY_TABLES` → a raw `UPDATE` under correct context **succeeds** (proves the trigger is correctly scoped, not over-applied).
28. **(regression)** `irp_ops` BYPASSRLS role has **no** grant on the four tables.
29. `GET /models/{id}` for a model owned by tenant B requested by a tenant-A principal → **404** (RLS-hidden), indistinguishable from non-existent.

**Backend HTTP (`apps/backend/tests/test_model_endpoint.py`, mirror `test_lineage_endpoint.py`):**
30. `GET /models/{id}` granted (`model.inventory.view`) → 200; list returns only the caller's tenant's models.
31. **(negative)** missing principal headers → 401; caller without `model.inventory.view` → 403.
32. **(negative)** `POST /models` without `model.inventory.register` → 403; with it → 201, model inventoried, `MODEL.REGISTER` emitted.
33. **(negative)** `POST /models` with a forged/foreign `tenant_id` in the body → the persisted `tenant_id == principal tenant` (and under PG a genuine cross-tenant attempt is 42501).
34. **(negative)** unknown model id → 404 with a **fixed** detail body; malformed (non-UUID) id → 422 before any DB hit.

No tests for tiering enforcement, validation workflow / dev≠validator (CTRL-022), approval gates (BR-15), restricted-use/retirement, challenger/monitoring, `model_validation` (ENT-037), analytical/risk-model logic, or any domain entity.

## 13. Acceptance criteria

The slice is **DONE** (inventory + versioning + assumptions/limitations only) when:

- **AC-1 (inventory + retrieve, CTRL-003):** `register_model` + `register_model_version` create queryable inventory rows retrievable by id via `GET /models/{id}`; all tenant-tagged. (T2/3/30)
- **AC-2 (BR-3 inventory-before-use, MG-02/CTRL-003):** a governed/calc use of an unregistered `model_version` fails `assert_registered_model_version`; a registered one passes — proven with a **synthetic** stand-in until a real calc exists at P2. (T16/17)
- **AC-3 (assumptions/limitations captured, BX-LIM/CTRL-014):** each version carries ≥0 `model_assumption` + `model_limitation` rows, immutably tied to the version, retrievable. (T4/14)
- **AC-4 (version immutability, IA/ENT-035, CTRL-017):** `model_version`/`assumption`/`limitation` are append-only at BOTH the ORM guard and the DB trigger; UPDATE and DELETE both rejected; `model` (EV) remains mutable. (T14/15/26/27)
- **AC-5 (tenant isolation, CTRL-011/BR-17):** under PG RLS with the constrained `irp_app` role, all four tables are visible only to the owning tenant; cross-tenant reads return zero rows. (T22)
- **AC-6 (fail-closed):** with no tenant context, writes rejected (42501), reads empty — never an open read. (T23)
- **AC-7 (entitlement deny-by-default, CTRL-011/BR-11):** `model.inventory.register`/`view` are deny-by-default; ungranted → `PermissionDenied`/403; missing principal → 401; bootstrap placement asserted (`register` → `risk_analyst_1l` + `platform_admin` only). (T19-21/31/32)
- **AC-8 (audit, CTRL-005/BX-AUD):** `register_model` emits exactly one `MODEL.REGISTER`, `register_model_version` exactly one `MODEL.VERSION`, chain verifies, assumptions/limitations emit no extra event, and a simulated audit-capture failure rolls back the data row (AUD-04/CTRL-032). (T9-12)
- **AC-9 (temporal, BR-19/CTRL-017):** `model` declares EV, `model_version`/`assumption`/`limitation` declare IA (no second axis). (T1)
- **AC-10 (genericity / extensibility):** a new model family (market/credit/liquidity/scenario/private-asset-proxy/AI-ML) is registrable by supplying a new `model_type` **value** with NO schema migration; `register_model()` lives in `irp_shared.model` (importable by backend AND workers without importing the web app). (T8)
- **AC-11 (scope fence / non-enforcement):** NO tiering/validation/approval/restricted-use enforcement is testable or tested; `tier`/`validation_status`/`approved_use`/`owner` are non-enforcing placeholders — a Tier-1 `UNVALIDATED` model registers and binds with no gate; the skeleton emits none of the reserved `MODEL.VALIDATE/.APPROVE/.RESTRICT/.RETIRE` codes. (T7/13/15)
- **AC-12 (governance forward-compat):** the reserved governance columns exist so P7 (REQ-MDG-002/003) adds tier/validation/approval/restricted-use semantics with NO schema migration; `developer`/`authored_by` can hold an AI-agent principal id so the future MG-04 dev≠validator check has its inputs.

**DoR/DoD posture:** R5 Calc = N/A (the registry has no calculation). **R7 ModelGov = Y and IS the subject of this slice** (unlike P1A-1), satisfied at **skeleton** level — BR-3 inventory is the load-bearing rule; CTRL-003 → Designed, CTRL-022 stays Planned (P7). DoD D7 lineage = N/A for this slice's own exit (registration is not a governed data output; `model_version` is referenced by future RUN/RESULT lineage, not lineage-recorded itself). "Done" boundary = inventory + versioning + assumptions/limitations + BR-3 gate; any tier/validation/approval logic has crossed into REQ-MDG-002/003/P7. First **real** BR-3 proof lands when calc runs bind a `model_version` in P2.

## 14. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Scope creep into full model governance** (CAP-12.3/12.4/12.5, MG-04/05/06/07, `MODEL.VALIDATE/.APPROVE/.RESTRICT/.RETIRE`, ENT-037) — the single biggest scope risk. | Strict exclusion list (§2) + the **AC-11 non-enforcement test** that FAILS if any approval/validation/tier gate appears (a Tier-1 UNVALIDATED model must register and bind freely); reject any validate/approve/restrict/retire endpoint or ENT-037 table. |
| R2 | **Missing reserved column → P7 migration** — if the governance placeholders are omitted, REQ-MDG-002/003 forces an `ALTER` on the EV head. | Reserve `tier`/`validation_status`/`approved_use`/`restricted_use`/`restriction_reason`/`owner`/`developer`/`authored_by` as nullable non-enforcing now (OQ-P1A-2-FIELDS, §3.1). |
| R3 | **BR-3 gate passes vacuously** — no calc runs/domains exist yet. | Prove with a synthetic unregistered `model_version_id` + `assert_registered_model_version`; require the first REAL proof when calc runs bind a version in P2; mark CTRL-003 **Designed (skeleton)**, NOT Implemented. |
| R4 | **Dev = validator seeded by entitlement** — granting `register` to the validator/2L or auditor role pre-violates MG-04/SOD-03/CTRL-022. | Grant `register` to `risk_analyst_1l` (developer/owner) + `platform_admin` only; deny test (§7). |
| R5 | **Cross-tenant parent reference leak** (PRIMARY new vector vs P1A-1) — FKs can't span RLS; RLS protects the row not the reference. | `register_model()` resolves the parent through the RLS-scoped session (cross-tenant id → zero rows → fail closed) and stamps child `tenant_id` server-side; `WITH CHECK` backstop. |
| R6 | **Genericity erosion** — modeling `model_type` as a Python `Enum` or DB `CHECK`/enum would require a migration per model family. | `model_type` is a free-text/controlled-vocab `String` (no enum, no CHECK); the AC-10 extensibility test guards it. |
| R7 | **Service-boundary drift** — `register_model()` in `apps/backend` couples workers/ingestion/calc engine to the web app. | Utilities MUST live in `irp_shared.model`; import-location acceptance criterion + test. |
| R8 | **Anchor instability** — making `model_version` mutable would break its role as the durable CalculationRun/lineage referent (TR-11/AD-006). | `model_version` is IA, append-only at ORM + DB; change = new version. |
| R9 | **Temporal mis-classification** — backbone `(IA)` shorthand vs implemented `model=EV`; implementer could pick the wrong mixin and put governance state on the immutable version. | Resolve the backbone shorthand before coding (§10/§17); explicit EV-head vs IA-version split (§3). |
| R10 | **Control over-claim** — marking CTRL-003/014 Implemented, or CTRL-022/015 touched, on the skeleton. | CTRL-003/014 → Designed (skeleton) only; CTRL-022/015 stay Planned; the DR-P1-3 hooks do NOT constitute CTRL-022/015 coverage (§16). |
| R11 | **Audit/permission proliferation** — minting `MODEL.ASSUMPTION` or a new permission. | Fold assumptions/limitations into `MODEL.VERSION` (no new code); both permissions already exist (no new permission). |
| R12 | **Audit fail-open / typo** — `event_type` is free-form (no allowlist), and a separate-transaction audit would let a model persist unaudited. | `record_event` in the same transaction (rollback on failure); the CTRL-012 audit-coverage test asserts the literal `MODEL.REGISTER`/`MODEL.VERSION` codes. |
| R13 | **IA immutability untested at the DB layer** — ORM-guard-only leaves the claim unproven against raw SQL on PG. | Both layers (`APPEND_ONLY_TABLES` trigger + ORM guard) with PG-CI UPDATE/DELETE-blocked tests (T26) + an EV negative-control (T27). |
| R14 | **`alembic check` drift** — `0005` must EXACTLY match the four models + NAMING_CONVENTION; the three intra-context FKs must be declared in BOTH ORM and migration with matching `fk_` names. | CI `alembic check` step + a structural test over the four `__tablename__`/`__temporal_class__` pairs (highest-probability CI failure). |
| R15 | **Mid-call COMMIT** in `register_model()` drops the transaction-local GUC → next write fails closed (availability bug masking isolation). | Honor the single-transaction-request invariant; re-set context after any intentional commit. |
| R16 | **SYSTEM_TENANT_ID global model as a backdoor** to cross-tenant metadata. | Mechanism available but not enabled; strict tenant-equality `USING`; no cross-tenant READ widening in P1A-2 (OQ-P1A-2-1). |
| R17 | **AI-authorship un-attributable** — without `developer`/`authored_by` able to hold an AI-agent principal, the future MG-04 check can't run against MG-05 AI-drafted content. | Free-string `developer`/`authored_by` + agent-aware audit passthrough (`actor_type='agent'`, MG-08/BR-16). |

## 15. Open decisions — all resolved

| ID | Question | Decision & rationale |
|---|---|---|
| **OQ-P1A-2-1** | `model` tenant-scoped only vs global/system models (AD-013)? | **Tenant-scoped by default; the SYSTEM_TENANT_ID template mechanism is available (FORCE RLS retained, no RLS-exempt table) but NOT seeded/enabled, and cross-tenant READ is NOT widened in P1A-2.** Mirrors the resolved P1A-1 OQ-P1A-1-2. Models are tenant-proprietary methodology IP; a shared/standard library is a real future need but is the deliberate exception (and still needs per-tenant tier/approval state in P7), so default to strict tenant-equality and defer the `USING`-clause widening to a separately-tested later change. |
| **OQ-P1A-2-2** | Wire a real FK `calculation_run.model_version_id → model_version` now, or keep the nullable placeholder GUID (calc/models.py:51)? | **Keep nullable (no DB FK now).** Data-Architecture, Architecture, Security, and Model-Governance lenses recommend deferral; QA/Scope preferred wiring it for a DB-enforced gate. **Resolved: keep nullable** — consistent with AD-014 (snapshot/assumption-set FKs stay deferred), the `lineage_edge.run_id` logical-reference precedent, and avoiding a calc↔registry cross-context migration coupling with no functional payoff (no run binds a version in P1A-2). The QA concern is addressed by the **logic-level `assert_registered_model_version` gate + negative test** (the skeleton RECORDS fields, ENFORCES no workflow). Promote to a hard FK in P2 when real model-governed calcs run; document CTRL-003 as logic-level/skeleton, not DB-enforced. |
| **OQ-P1A-2-3** | Minimal `model_assumption` / `model_limitation` shape (ENT-036)? | **Minimal IA rows: `model_version_id` FK + text + optional `category`/`severity` + nullable `authored_by`.** No severity workflow, status, or review/disposition fields (those imply validation, P7). Right altitude for CTRL-014 "limitations explicitly documented" at skeleton level; the `authored_by` is the governance-critical addition for MG-05 attribution. Promote richer taxonomy to reference data only when P7 validation needs it. |
| **OQ-P1A-2-FIELDS** (new, governance — highest priority) | Which future-governance fields must the skeleton RESERVE now to avoid a P7 migration? | **Reserve the full non-enforcing placeholder set on the EV `model` head** (`tier`, `validation_status` default `UNVALIDATED`, `approved_use`, `restricted_use`, `restriction_reason`, `owner`, `developer`) plus `authored_by` on assumptions/limitations and the DR-P1-3 hooks. The Chief Architect's "omit them / they belong to ENT-037" concern is honored by the **coupling fence**: nullable, non-enforcing, documented reserved-for-P7, locked by the AC-11 non-enforcement test. Cost = a handful of nullable columns; benefit = P7 adds workflow with zero schema migration. |
| **OQ-P1A-2-API** | Expose `POST /models`, or internal `register_model()` utility only (P1A-1 mirror)? | **Expose `POST /models`** (gated by `model.inventory.register`, `get_tenant_session`, audited in-txn fail-closed, never reads `tenant_id` from the body, `WITH CHECK` backstop) **plus `GET /models` + `GET /models/{id}`.** Model registration is a legitimate user-initiated first-class governed write with an existing write permission and backbone requirement — the genuine difference from P1A-1's side-effect-only lineage. The Chief Architect preferred read-only + utility to keep one P1A pattern; Product/Security/Governance/QA preferred the gated POST. **Resolved: gated POST**, with `register_model()` kept in `irp_shared` so the endpoint is a thin single-sourced wrapper. The register payload records `tier`/`owner`/`validation_status` as metadata but gates on none of them. |
| **OQ-P1A-2-AUDIT** | Separate audit code for assumption/limitation writes, or fold into `MODEL.VERSION`? | **Fold into `MODEL.VERSION`; mint NO new code.** Assumptions/limitations are IA metadata of the version, co-created in the same transaction — exactly the P1A-1 lineage_edge "metadata-of-the-governed-write, no separate event" precedent. Record `assumption_count`/`limitation_count` in the `MODEL.VERSION` `after_value`. Keeps P1A-2 to the two existing codes with zero taxonomy additions. |
| **OQ-P1A-2-ENT** | Which role template(s) hold `model.inventory.register` (currently only `platform_admin` via `ALL_CODES`)? | **Grant to `risk_analyst_1l` (1L model developer/owner) + `platform_admin`; NOT to `auditor_3l` or `risk_manager_2l`/the future validator role.** Register is the maker/author side of the future SOD-03 maker-checker; granting it to the independent validator pre-seeds a `dev = validator` conflict (MG-04/SOD-03/CTRL-022). `model.inventory.view` stays as-is. Deny-by-default test required. (No new permission — the codes already exist.) |
| **OQ-P1A-2-SEC-1** | Explicit `WITH CHECK` on the four new RLS policies, or `USING`-only? | **Explicit `WITH CHECK` on all four**, identical to migration `0004`. New write-bearing tables; removes reliance on `USING`-as-implicit-INSERT-check, self-documents cross-tenant-write rejection, and future-proofs the SYSTEM_TENANT_ID read/write-scope divergence. The PG test asserts the policy violation (42501), not the clause text. |

No open decision blocks implementation (see §18).

## 16. Controls impacted — exact CTRL row update text

Update `09_compliance_controls/control_matrix_skeleton.md` §3 as follows (status-and-evidence edits only; no new CTRL row is required — existing CTRL-003/005/011/012/014/017/032 carry P1A-2; CTRL-022/015 are untouched):

- **CTRL-003** (Every model/version inventoried before use; Preventive; BR-3; Owner R-08): Status **Planned → Designed (skeleton, P1A-2)**. Test/Assurance: "Model-inventory gate (skeleton): `register_model` creates a `model` + immutable `model_version` inventory entry (ENT-035) with `MODEL.REGISTER`/`MODEL.VERSION` audit; a governed use of an unregistered `model_version` fails `assert_registered_model_version`." Evidence: inventory entry (ENT-035) + `MODEL.REGISTER`/`MODEL.VERSION` events + BR-3 negative test. **Do NOT mark Implemented** — full enforcement (runs actually blocked) completes when calc runs bind `model_version_id` (P2+); the BR-3 gate is logic-level (no DB FK per OQ-P1A-2-2).
- **CTRL-014** (Limitations explicitly documented; BR-14; Owner R-10): Status **Planned → Designed (skeleton, P1A-2)**. Test/Assurance: "Limitations-capture test (skeleton): a `model_version` can record `model_limitation` rows (ENT-036, IA), retrievable from the inventory; folded into `MODEL.VERSION` audit." Evidence: `model_limitation` rows (ENT-036) + `MODEL.VERSION` event. The manual "Limitations register review" assurance remains; P1A-2 makes the structured capture executable, not the review. **Do NOT mark Implemented.**
- **CTRL-005** (Data-changing actions emit audit events; BR-5/BR-12; Owner R-07): Status remains **Implemented**; extend the covered set/qualifier to include `model`/`model_version` create. Test/Assurance: add "`model`/`model_version` create emit `MODEL.REGISTER`/`MODEL.VERSION` (P1A-2)." Evidence: append "incl. model/model_version."
- **CTRL-011** (No module bypasses entitlement; tenant isolation end-to-end): Status remains **Implemented (1E + P1A-0)**. Coverage note: the four `model*` tables are FORCE-RLS (USING + WITH CHECK) proven under the constrained `irp_app` role + `model.inventory.register`/`view` deny-by-default tests.
- **CTRL-012** (No module bypasses audit framework; BR-12; Owner R-07): Status remains **Planned/Designed**; add `model`/`model_version` create to the cross-cutting audit-coverage enforcement test scope ("no governed write without a taxonomy event"; assert the literal codes).
- **CTRL-017** (Temporal-class declared + append-only): extend to the four new entities (`model` EV; `model_version`/`assumption`/`limitation` IA append-only at both layers).
- **CTRL-032** (Failed audit capture blocks governed change, AUD-04; BR-12; Owner R-07): no status change; add `model`/`model_version` create to its scope note as new governed writes inheriting fail-closed semantics (`record_event` in the same transaction; rollback on audit failure).
- **CTRL-022** (Independent model validation, dev≠validator; BR-15; Owner H-02): **NO CHANGE — remains Planned.** P1A-2 records NO validation and creates no ENT-037 `model_validation`; the DR-P1-3 hooks and the `register`-off-the-validator-role grant only *pre-position* dev≠validator. Explicitly note CTRL-022 is **NOT implemented in P1A-2**.
- **CTRL-015** (Human approval gate for restricted change types; BR-15): **NO CHANGE — remains Planned.** The DR-P1-3 `approval_ref` hook is reserved/non-enforcing.

**§4 Coverage Note — add a P1A-2 line:** "P1A-2 additions: the `model`/`model_version`/`model_assumption`/`model_limitation` registry skeleton makes BR-3 model-inventory executable — `register_model` + inventory read move CTRL-003 and CTRL-014 to Designed (skeleton); `model`/`model_version` create audit (`MODEL.REGISTER`/`MODEL.VERSION`) extends CTRL-005/012/017/032. CTRL-022 (validation independence) and CTRL-015 (approval gate) remain Planned — no validation/approval workflow in P1A-2."

## 17. Documentation updates (at slice exit, DoD D19)

1. **RTM** (`requirements_traceability_matrix.md`) row 73: REQ-MDG-001 Status Draft → In-Progress → **Done** (inventory + versioning + assumptions/limitations skeleton); annotate that CAP-12.3 tiering (REQ-MDG-002) and CAP-12.4/12.5 validation/approval (REQ-MDG-003) are **outside** its acceptance (P7). Annotate that CTRL-014 is additionally exercised at skeleton level and CTRL-022 remains future (REQ-MDG-003/P7). Reconcile the persona note: P-MV/P-RM are the inventory **readers**; the register **writer** is the model owner/developer (`risk_analyst_1l`).
2. **Backbone** (`requirements_backbone.md`): §7 CAP-12 (L223) Data column → `model (EV), model_version (IA), model_assumption/model_limitation (IA)` (fixes the `(IA)` shorthand); annotate that 12.3/12.4/12.5 remain P7; §6 Forward Dependency Registry → flip **DEP-MREG** from "Future (CAP-12)" to "Exists (inventory + version-binding skeleton, P1A-2; tiering REQ-MDG-002/P7, validation REQ-MDG-003/P7)."
3. **Control matrix** (`control_matrix_skeleton.md`): CTRL-003/005/011/012/014/017/032 row edits per §16 + the §4 Coverage Note P1A-2 line; CTRL-022/015 unchanged with the explicit "not implemented in P1A-2" note.
4. **Audit taxonomy** (`audit_event_taxonomy.md`): annotate the MODEL row that `MODEL.REGISTER`/`MODEL.VERSION` are **activated** in P1A-2 and `MODEL.VALIDATE/.APPROVE/.RESTRICT/.RETIRE` are **reserved** for P7; note assumption/limitation writes are folded into `MODEL.VERSION`. Annotation only — no new EVT-nnn.
5. **Entitlement / SoD** (`entitlement_sod_model.md` + bootstrap catalog): record that `model.inventory.register` is granted to `risk_analyst_1l` (model developer/owner) + `platform_admin` and explicitly NOT to the validator/auditor roles (OQ-P1A-2-ENT). No new permission code.
6. **Data dictionary / canonical model**: register ENT-035 (`model` EV + `record_version` + DR-P1-3 hooks + reserved non-enforcing governance columns; `model_version` IA) and ENT-036 (`model_assumption`, `model_limitation` IA, `authored_by`) with DC-\* tags and temporal classes. No entity-set change (canonical §5 already lists ENT-035/036/037).
7. **Model governance policy** (`model_governance_independence_policy.md`): add a note that MG-02 inventory is realized at skeleton in P1A-2 while MG-04/05/06/07 enforcement is P7.
8. **Personas** (`personas_and_user_journeys.md`): annotate UJ-3 that step 1 (open inventory; select model/version) is enabled by P1A-2; steps 2-4 (record validation, set approval/restricted-use) remain P7.
9. **CI enforcement overview** (`08_testing_qa/ci_enforcement_overview.md`): note the new PG RLS tests for the four `model*` tables in the `migration` job and the `alembic check` drift coverage for `0005`.

**Guardrail:** do NOT pre-document REQ-MDG-002 tiering thresholds (OD-032), REQ-MDG-003 validation/approval workflow, revalidation cadence (OD-033), or ENT-037 `model_validation` — those belong to P7 planning.

## 18. Is P1A-2 ready to implement?

**YES.** The slice is well-bounded to REQ-MDG-001, fully **additive** (grep confirms zero existing `model`/`model_version`/`model_assumption`/`model_limitation` ORM tables or `register_model` utility; next Alembic revision is `0005`, revising `0004_lineage_skeleton`), and **independent** of P1A-1/3/4 (plan §6/§8 DAG — fully parallelizable after P1A-0). Its only hard prerequisite — P1A-0 tenant context — is landed (AD-015/AD-016), and the pattern to mirror (P1A-1 lineage models/service/migration/api/tests) is shipped and CI-green. **No new ADR is required** (realizes AD-005 temporal, AD-013 tenancy, AD-014 deferred snapshot FKs, DR-P1-3 non-enforcing hooks, AD-006 model_version anchor). **No new permission and no new audit code** — both `model.inventory.view`/`register` and all six `MODEL.*` codes already exist.

**No open decision blocks implementation** — every OQ in §15 is resolved with a concrete, scope-preserving recommendation:
- **Tenancy:** tenant-scoped; SYSTEM_TENANT_ID mechanism available but not enabled, no cross-tenant read (OQ-1).
- **Calc FK:** keep `calculation_run.model_version_id` nullable; logic-level BR-3 gate (OQ-2).
- **Assumption/limitation shape:** minimal IA + `authored_by` (OQ-3).
- **Governance fields:** reserve the non-enforcing placeholder set now, fenced (OQ-FIELDS).
- **API:** gated `POST /models` + read endpoints (OQ-API).
- **Audit:** reuse `MODEL.REGISTER`/`MODEL.VERSION`, fold assumptions/limitations, reserve P7 codes (OQ-AUDIT).
- **Entitlement:** `register` → `risk_analyst_1l` + `platform_admin` only (OQ-ENT).
- **Security:** explicit `WITH CHECK` on all four (OQ-SEC-1), server-side tenant stamping + RLS-scoped parent resolution, DB+ORM append-only.

Recommended build sequence: grant `model.inventory.register` to `risk_analyst_1l` → `model` model + governance placeholders → `model_version` model (IA) → `model_assumption`/`model_limitation` models (IA) → `0005` migration (FORCE RLS USING+WITH CHECK on all four; three IA tables into `APPEND_ONLY_TABLES`; intra-context FKs) → `register_model`/`register_model_version`/`record_assumption`/`record_limitation`/`assert_registered_model_version` utilities in `irp_shared.model` → `POST /models` + `GET /models` + `GET /models/{id}` → SQLite-local + PG-CI tests. End-state deliverable cap: **4 models + 1 migration + register/assert utilities + 1 write + 2 read endpoints + a one-line role-template grant + the tests above.** Recommend approval of the slice boundary and proceed to implementation with the §19 kickoff.

## 19. Exact implementation kickoff prompt for P1A-2

> **Begin P1A-2 — Model Registry Skeleton (REQ-MDG-001, builds DEP-MREG). Implement code.**
>
> **Scope (only this):**
> (1) **`model`** model (ENT-035, **EV**, tenant-scoped) following the `lineage/models.py` mixin pattern `class Model(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base)` with `__temporal_class__ = TemporalClass.EFFECTIVE_DATED`. Columns: `code` (String(150)), `name` (String(255)), `model_type` (String(50) — **controlled-vocab string, NO Python enum, NO DB CHECK**, so new model families register by value not migration), `description` (String(500) null), `is_active` (Boolean default true), `record_version` (Integer default 1). **Reserve, as NULLABLE NON-ENFORCING columns:** `owner`, `developer`/`developed_by`, `tier`, `validation_status` (default `UNVALIDATED`), `approved_use`, `restricted_use` (default false), `restriction_reason` — plus the **DR-P1-3 nullable non-enforcing** maker-checker hooks `approval_status`/`approval_ref`/`made_by`/`checked_by` — so P7 REQ-MDG-002/003 adds tiering/validation/approval/restricted-use semantics with NO schema migration. `UniqueConstraint('tenant_id','code')`. `model` is EV/mutable — do NOT add it to `APPEND_ONLY_TABLES`.
> (2) **`model_version`** model (ENT-035, **IA**, tenant-scoped) `class ModelVersion(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base)` with `__temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY`. Columns: `model_id` (GUID, **real intra-context FK** → `model.id`, `fk_model_version_model_id_model`), `version_label` (String(50)), `methodology_ref` (String(500) null), `code_version` (String(100) null), `status` (String(20) null — non-enforcing). `UniqueConstraint('tenant_id','model_id','version_label')`. No `created_by`/`updated_by` (IA — actor lives in the `MODEL.VERSION` audit event).
> (3) **`model_assumption`** + **`model_limitation`** models (ENT-036, **IA**, tenant-scoped). Each: `model_version_id` (GUID, intra-context FK → `model_version.id`), a text field (`assumption_text` / `limitation_text`), an optional label (`category` / `severity`), and a nullable `authored_by` (String(255)) accepting a human OR AI-agent principal id (MG-05).
> (4) **One Alembic migration** `0005_model_registry_skeleton` (revises `0004_lineage_skeleton`) creating all four tables; add all four to the `TENANT_SCOPED_TABLES` loop with `ENABLE` + `FORCE ROW LEVEL SECURITY` + `CREATE POLICY tenant_isolation_<t> ON <t> USING (tenant_id::text = current_setting('app.current_tenant', true)) WITH CHECK (...)` — **include the explicit `WITH CHECK`**. Add `model_version`, `model_assumption`, `model_limitation` to `APPEND_ONLY_TABLES` so the existing `irp_prevent_mutation()` trigger applies; `model` does NOT get the trigger. Declare the three intra-context FKs in BOTH the ORM and the migration with matching `fk_` names; named `pk_`/`ix_`/`uq_` constraints so `alembic check` is drift-clean.
> (5) **`register_model()` / `register_model_version()` (+ `record_assumption` / `record_limitation`) and `assert_registered_model_version(session, model_version_id, *, tenant_id=None)`** in a **NEW `irp_shared.model`** package (shared-python, sibling to `irp_shared.lineage`/`irp_shared.calc`, **NOT** backend) — each takes a caller-managed `Session`, runs in the caller's transaction, **stamps `tenant_id` server-side from the tenant context (never caller-supplied)**, resolves the parent through the RLS-scoped session so a cross-tenant parent id fails closed, and stamps each child's `tenant_id` from the resolved parent. Add ORM `before_update`/`before_delete` append-only guards on the three IA models (mirror `lineage/models.py`). `assert_registered_model_version` raises `UnregisteredModelError` for an unregistered version (the MG-02/BR-3/CTRL-003 gate).
> (6) **Audit:** emit **`MODEL.REGISTER`** (model create) and **`MODEL.VERSION`** (version create) via `record_event` **in the same tenant-scoped transaction** as the data row (fail-closed: roll back the row if the audit insert fails). **FOLD** assumption/limitation capture into `MODEL.VERSION` (record `assumption_count`/`limitation_count` in `after_value`) — emit **no** separate event and mint **no** new code. Pass `actor_type='agent'` + agent fields through when an AI principal registers (MG-08). Do NOT emit `MODEL.VALIDATE/.APPROVE/.RESTRICT/.RETIRE` (reserved P7).
> (7) **`POST /models`** (register model + initial version + optional assumptions/limitations) depending on **`get_tenant_session`** and gated by **`require_permission('model.inventory.register')`** — a thin wrapper over `register_model()`; **never reads `tenant_id` from the body** (server-stamps from principal); records `tier`/`owner`/`validation_status` as metadata but gates on none of them. Plus **`GET /models`** and **`GET /models/{id}`** gated by `require_permission('model.inventory.view')` under `get_tenant_session`; entitlement-check first, then an RLS-scoped lookup returning an **indistinguishable 404** (fixed detail body) for both not-found and cross-tenant ids; `uuid.UUID` path param → 422 on malformed; 401 on missing principal. NO validate/approve/restrict/retire endpoint.
> (8) **Entitlement:** add `model.inventory.register` to the **`risk_analyst_1l`** template (already held by `platform_admin` via `ALL_CODES`); do NOT grant it to `auditor_3l` or `risk_manager_2l`/the validator role. **Add NO new permission** (`model.inventory.view`/`register` already exist). Keep `model.inventory.view` as-is.
> (9) Tests, split SQLite-local vs **Postgres-CI under the constrained non-superuser `irp_app` role** (CI `migration` job, after `alembic upgrade head`, using the `app_url` fixture + `_is_rls_violation` SQLSTATE-42501 helper): temporal-class assertions; `register_model`/`register_model_version` create retrievable inventory rows; **genericity/extensibility — an arbitrary `model_type` registers with no schema branch**; **BR-3 gate — a synthetic unregistered `model_version` fails `assert_registered_model_version`** (and a registered one passes); `MODEL.REGISTER`/`MODEL.VERSION` emitted exactly once with `verify_chain.ok`; **assumptions/limitations emit NO extra event** (locks the fold decision); simulated audit failure rolls back the row; **IA immutability — UPDATE/DELETE on `model_version`/`assumption`/`limitation` blocked at BOTH the ORM guard and the DB trigger**, with an **EV negative-control** that `model` UPDATE succeeds; **deny-by-default** for `model.inventory.register`/`view` (403/PermissionDenied); PG **tenant isolation**, **no-context fail-closed (42501)**, **cross-tenant write rejected**, **cross-tenant parent-reference fails closed**, **`GET /models/{id}` cross-tenant id → 404**, **forged-tenant `POST` body stamped to caller tenant**, and an **ops-role-no-grant regression** test. Apply the P1A-1 CI lessons: native `uuid` columns → use the ORM/`GUID` type, `CAST(:x AS uuid)`/`str()` in raw `text()` SQL; the `alembic check` drift gate requires `0005` to exactly match the four models + NAMING_CONVENTION.
>
> **Constraints (strict exclusions — none of these):** model VALIDATION workflow & effective challenge (REQ-MDG-003/P7); model APPROVAL/restricted-use/retirement workflow (MG-11/12/P7); tier ENFORCEMENT (REQ-MDG-002/P7 — `tier`/`validation_status`/`approved_use`/`restricted_use`/`owner` are **non-enforcing placeholders only**, gate nothing); `model_validation` (ENT-037); `MODEL.VALIDATE/.APPROVE/.RESTRICT/.RETIRE` events (reserved P7); dev≠validator ENFORCEMENT (MG-04/SOD-03 — recorded only); AI-approval gating (MG-07/BR-15); challenger workflow; model performance monitoring (MG-13/14); any analytical/risk-model logic (the registry stores metadata ABOUT models, never model logic, MG-01); methodology documents (BR-2 — a `methodology_ref` string only); maker-checker approval ENFORCEMENT (DR-P1-3/P6 — hooks non-enforcing); a hard `calculation_run.model_version_id` FK (keep it the nullable placeholder per AD-014); P1A-1 lineage, P1A-3 data quality, P1A-4 ingestion; Security Master; Reference Data; portfolio; positions; valuations; risk calculations; dashboards; reporting; private assets; real SSO; any domain entity. The **only** write endpoint permitted is `POST /models`; reads are `GET /models` + `GET /models/{id}`. **No new permission** and **no new audit code** (reuse `model.inventory.view`/`register` and `MODEL.REGISTER`/`MODEL.VERSION`).
>
> **Include an AC-11 non-enforcement test:** a `tier='Tier 1'`, `validation_status='UNVALIDATED'` model registers and binds with **no** approval/validation gate (proving MG-06/MG-07/BR-15 are P7).
>
> **Honor:** AD-013 (tenant scoping), AD-005 (temporal — `model=EV`, `model_version`/`assumption`/`limitation`=IA), AD-014 (deferred snapshot/assumption-set FKs), AD-006 (`model_version` is the run-binding anchor), BR-3/MG-02 (inventory-before-use), BR-17 (tenant isolation), BR-19 (declare `__temporal_class__`), DR-P1-3 (non-enforcing hooks), the DoR/DoD, and DR-P1-4 coverage targets. Use **`set_config`** / the P1A-0 tenant context for every DB surface; deny-by-default; **no secrets** in code; honor the single-transaction invariant (no mid-call commit); never use the BYPASSRLS ops role on any normal path and grant it nothing on the four new tables; the app role stays NOSUPERUSER NOBYPASSRLS. Update `04_data_model/audit_event_taxonomy.md` (annotate MODEL row), `06_security/entitlement_sod_model.md` + bootstrap catalog (register grant), `09_compliance_controls/control_matrix_skeleton.md` (CTRL-003/005/011/012/014/017/032 → Designed/extended; CTRL-022/015 unchanged), `02_requirements/requirements_traceability_matrix.md` (REQ-MDG-001 row 73), `02_requirements/requirements_backbone.md` (CAP-12 temporal shorthand + DEP-MREG flip), `07_model_governance/model_governance_independence_policy.md` (MG-02 realized note), and `08_testing_qa/ci_enforcement_overview.md`.
>
> **Return:** files created/updated, DB/migration changes, tests added (SQLite-local + PG-CI), CI impact, controls now executable (note CTRL-003/014 are skeleton/Designed, NOT Implemented; CTRL-022/015 remain Planned), known placeholders (synthetic unregistered `model_version`; first real BR-3 proof at P2; `calculation_run.model_version_id` stays nullable), whether P1A-2 is complete, and confirmation that **`make check` passes** and the `migration` job should pass. **Do not commit until approved. Do not start P1A-3.**