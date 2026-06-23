# P1B-2 Implementation Plan — Legal Entity / Issuer / Counterparty (Reference Data, Proprietary Tenant-Scoped)

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1B2-PLAN-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-01 Chief Architect AI (with R-05 Data Architect AI, R-04 Security AI, R-07 Audit/Controls AI) |
| Approver | H-06 Engineering Lead |
| Created | 2026-06-22 |
| Related Documents | `p1b0_decision_record.md` (ratified `4fae26b`, OD-P1B-D / OD-P1B-C / OD-P1B-F), `p1b_implementation_plan.md` (P1B-2 section), `p1b1_implementation_plan.md` (the realized reference-data conventions, committed `6568cb1`), `../02_requirements/requirements_backbone.md` (REQ-SMR-002), `../02_requirements/requirements_traceability_matrix.md`, `../04_data_model/canonical_data_model_standard.md` (ENT-002/003), `../04_data_model/temporal_reproducibility_standard.md` (§2A), `../04_data_model/audit_event_taxonomy.md` (REFERENCE.*), `../06_security/entitlement_sod_model.md` (§5A), `../09_compliance_controls/control_matrix_skeleton.md`, `packages/shared-python/src/irp_shared/reference/*` (the shipped P1B-1 service/binder/RLS conventions), `packages/shared-python/src/irp_shared/model/service.py` (the parent-resolve precedent) |
| Supported Build Rules | BR-3, BR-5, BR-7, BR-11, BR-12 (N/A — no IA tables), BR-13, BR-17, BR-19 |

**Purpose.** Author the authoritative, build-ready plan for **P1B-2**, the second Security Master & Reference Data slice: a shared **`legal_entity` core** (implementation-only, no canonical ENT id — OD-P1B-D) with separate **`issuer`** (ENT-002) and **`counterparty`** (ENT-003) 1:1 role/profile tables, plus the **structural parent hierarchy** (LEI + `parent_legal_entity_id` adjacency) REQ-SMR-002 names. All three are **EV** and — critically, unlike P1B-1 — **PROPRIETARY and tenant-scoped: NEVER hybrid, NEVER SYSTEM_TENANT** (OD-P1B-C hard invariant; MNPI/cross-tenant leakage risk). P1B-2 reuses every P1A rail **and** the P1B-1 reference conventions (the `irp_shared.reference` service core, `ensure_manual_source`, `REFERENCE.CREATE/UPDATE`, additive entitlements, the constrained-role PG RLS tests) and **adds no new rail and no new audit code**. It uses the **shipped symmetric RLS loop** (`USING == WITH CHECK == own-tenant`), NOT the asymmetric hybrid loop. Migration head advances `0008 → 0009`.

**In-scope statement (the deliverable cap).** Exactly: (1) THREE new EV tables — `legal_entity`, `issuer`, `counterparty` — added to the `irp_shared.reference` package (ORM in `reference/models.py`; binders `legal_entity.py` / `issuer.py` / `counterparty.py`); (2) ONE migration **0009** creating the three tables under the **symmetric** tenant-isolation RLS loop (no hybrid, no SYSTEM_TENANT, no append-only trigger), with the `parent_legal_entity_id` self-FK and the profile→core FKs; (3) reuse of `REFERENCE.CREATE` / `REFERENCE.UPDATE` (each entity emits its **own** event — issuer/counterparty are independently-governed, NOT folded into the core); (4) the additive entitlement permissions `reference.legal_entity.view` / `reference.legal_entity.edit` (issuer/counterparty perms already exist); (5) thin `POST`/`GET` endpoints in a new `irp_backend/api/reference_entities.py`; (6) per-tenant **MANUAL** `data_source` origin lineage on every write; (7) a bounded **read-only ultimate-parent resolver** (pure structural adjacency walk — NO exposure/credit math); (8) OPTIONAL generic DQ (`not_null` on `name`/`code`) where configured; (9) the test matrix; (10) the in-slice baseline-doc + control-matrix/RTM updates. **No instrument / instrument_terms / identifier_xref / corporate_action; no rating ASSIGNMENTS; no netting/CSA/collateral; no exposure / credit / counterparty-risk calculation; no hybrid/SYSTEM_TENANT; no ingestion; no implementation code is produced in this planning phase.**

---

## 1. Requirements included

| REQ | Owns | Entities (this slice) | CAP | Acceptance clauses bound here | RTM transition |
|---|---|---|---|---|---|
| **REQ-SMR-002** | issuer (ENT-002) + counterparty (ENT-003) over an implementation-only `legal_entity` core; LEI + parent hierarchy | `legal_entity`, `issuer`, `counterparty` | CAP-2.2 | shared core + distinct 1:1 role profiles; LEI present; **structural** parent/ultimate-parent hierarchy; tenant-isolated; audited; lineage-rooted | `Ratified (P1B-0)` → `In-Progress (P1B-2)` |

**Clause → deliverable → test binding (acceptance is provably mapped):**
- **shared core + distinct role profiles (OD-P1B-D)** → `legal_entity` core + `issuer`/`counterparty` 1:1 profile tables (`UNIQUE(tenant_id, legal_entity_id)`); a `legal_entity` may carry BOTH profiles → both-roles test.
- **profile cannot exist without its core (1:1 integrity)** → `legal_entity_id` NOT NULL FK + RLS-scoped parent resolution (fail-closed if the core is cross-tenant/unknown) → orphan-profile-rejected test.
- **LEI present** → `legal_entity.lei` (`String(20)`, ISO-17442 field-shape, CTRL-004) + (Postgres) partial-unique `(tenant_id, lei) WHERE lei IS NOT NULL` (OQ-P1B2-004).
- **parent / ultimate-parent hierarchy (structural)** → `parent_legal_entity_id` self-FK (intra-tenant adjacency) + the bounded `resolve_ultimate_parent` walk (cycle-safe, depth-capped) → hierarchy-rollup + cycle-guard tests. **The exposure-rollup CALCULATION (REQ-SMR-002 "exposure rolls to ultimate parent") is DEFERRED — P1B-2 builds only the structural target the future rollup attaches to.**
- **tenant-isolated** → **symmetric** RLS (`USING == WITH CHECK == own-tenant`) on all three; cross-tenant invisible; 42501 on forged/no-context write → PG isolation tests.
- **audited** → `REFERENCE.CREATE`/`.UPDATE` (EVT-140/141) per entity (own event); literal-code CTRL-012 assertion.
- **lineage-rooted** → origin edge `data_source(MANUAL) → entity` per row via `record_lineage` + `assert_has_lineage`.

**Net-new this slice (not inherited freebies).** The `legal_entity` core shape (LEI/jurisdiction/`entity_type`/`parent_legal_entity_id`), the 1:1 core↔profile contract, the **explicitly-tenant-filtered profile→core resolution**, and the bounded ultimate-parent resolver are all first-class deliverables with their own tests.

**Resolution discipline (load-bearing — applies to §5, §6, §7, §10, §14, §21).** The profile→core resolver, the write-time parent resolver, AND each hop of `resolve_ultimate_parent` MUST carry an **explicit `tenant_id == acting_tenant` predicate** in the query — the `ensure_manual_source` / `assert_registered_model_version(tenant_id=…)` shipped pattern (`reference/service.py` lines 79–84; `model/service.py` lines 247–249), **NOT** the bare RLS-only `register_model_version` lookup (`model/service.py:187`, which filters by id alone and relies entirely on Postgres RLS). Reason: RLS is a no-op on SQLite, so an id-only resolver would FIND a cross-tenant core on SQLite, stamp the profile with the wrong tenant, and silently persist it — defeating the §14 SQLite-local "cross-tenant `legal_entity_id` fails closed" tests. The PG RLS `WITH CHECK` remains the production backstop; the explicit predicate makes the SQLite logic tests genuinely fail-closed.

---

## 2. Requirements excluded

**Deferred within SMR (do NOT appear in any P1B-2 entity / endpoint / migration / test):**
- `instrument`, `instrument_terms` (FR), `identifier_xref` (REQ-SMR-001/003) → **P1B-3** (instrument's issuer FK will target the `issuer` profile — a forward seam only, not built here).
- `corporate_action` (REQ-SMR-004, ENT-008) → **P1B-4**.
- **rating ASSIGNMENTS** (ENT-007 FR) → credit phase.

**Risk/analytics excluded (the load-bearing fences for this slice):**
- **netting set / CSA / collateral** depth on `counterparty` (OD-015) → **P1C**. `counterparty` carries NO netting/CSA/collateral columns.
- **counterparty exposure, current/potential exposure, netting calc** (REQ-CPT-001/003) → P2+.
- **credit risk, concentration, spread** (REQ-CRD-*) → P2+.
- **exposure-rollup CALCULATION** to ultimate parent (the risk math behind REQ-SMR-002's acceptance) → P2+. P1B-2 ships the structural hierarchy + a pure-structural resolver ONLY.

**Rejected alternative (do NOT build):** a **unified single `legal_entity` table with role flags** (`is_issuer`/`is_counterparty`) — explicitly rejected by OD-P1B-D (contradicts canonical ENT-002/003, weakens the SoD permission split).

**P1C/P2+ and platform (excluded):** portfolio, positions, valuations, market prices, market-data / private-asset ingestion, GP-report parsing, risk calculations, exposure aggregation, limits, breach workflow, dashboards, reporting, real SSO. **No hybrid/SYSTEM_TENANT** for any P1B-2 table. **No global LEI directory** (a future GLEIF-style hybrid reference catalog is out of scope — issuer/counterparty as a firm uses them are proprietary; §10).

**Done eligibility.** REQ-SMR-002 reaches **In-Progress (structural)** at P1B-2; it stays In-Progress (not Done) until the exposure-rollup-to-ultimate-parent *calculation* lands in the risk phase (the acceptance clause that needs the math).

---

## 3. Proposed entities

All three: ORM in `irp_shared/reference/models.py` (extend); registered in `irp_shared/models.py` aggregator (`LegalEntity`, `Issuer`, `Counterparty` + `__all__`). All carry `TenantMixin` (indexed `tenant_id`), `EffectiveDatedMixin`, `TimestampMixin`, explicit `record_version`. **None is in the hybrid set; none is append-only.** Open-vocab attributes (`entity_type`, `issuer_type`, `counterparty_type`, `sector`, `jurisdiction`) are plain `String` (MG-01 genericity — no enum/CHECK/lookup). GUID columns = `postgresql.UUID(as_uuid=False)`; temporal/timestamp = `DateTime(timezone=True)`. Migration column order mirrors the `model`/P1B-1 EV sequence: `id, tenant_id, valid_from, valid_to, created_at, created_by, updated_at, updated_by, <domain cols>, record_version`.

### 3.1 `legal_entity` (implementation-only core, EV, tenant-scoped) — NO canonical ENT id
Mixins: `PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base`; `__temporal_class__ = TemporalClass.EFFECTIVE_DATED`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `code` | String(150) | NO | tenant-local stable identity code |
| `name` | String(255) | NO | legal name |
| `lei` | String(20) | YES | ISO-17442 LEI (20-char), plain string — **no global FK** (CTRL-004 field-shape) |
| `jurisdiction` | String(10) | YES | ISO-3166 domicile/country, plain string |
| `entity_type` | String(50) | YES | CORP/BANK/FUND/SOVEREIGN/SPV/… — plain string, **no enum** |
| `parent_legal_entity_id` | GUID | YES | self-FK → `legal_entity.id` (**intra-tenant** adjacency); NULL = a root; self-parent rejected |
| `is_active` | Boolean | NO | default True |
| `record_version` | Integer | NO | default 1 |

Constraints: `pk_legal_entity`; `UniqueConstraint('tenant_id','code', name='uq_legal_entity_tenant_code')`; `ForeignKeyConstraint(['parent_legal_entity_id'],['legal_entity.id'], name='fk_legal_entity_parent_legal_entity_id_legal_entity')`; `ix_legal_entity_tenant_id`; `ix_legal_entity_parent_legal_entity_id`. **`code` is `String(150)`** (firm-assigned legal-entity codes are longer than the short ISO vocab codes in P1B-1; matches the `data_source`/`model` `code` width). **LEI uniqueness is a Postgres-only partial-unique index** `(tenant_id, lei) WHERE lei IS NOT NULL` (OQ-P1B2-004) — declared on the ORM as `Index('uq_legal_entity_tenant_lei', 'tenant_id', 'lei', unique=True, postgresql_where=text('lei IS NOT NULL'))` so `alembic check` stays drift-clean on PG (the migration creates the same partial index; confirm the name does not collide with Alembic auto-naming). SQLite has no partial-unique, so on SQLite LEI uniqueness is an **application/test-level** assertion only (logic tests), not a DB constraint.

### 3.2 `issuer` (ENT-002, EV, tenant-scoped role profile)
Same mixin stack + `record_version`. A thin 1:1 profile over the core (no LEI/name/hierarchy duplication — those live on `legal_entity`).

| Column | Type | Null | Notes |
|---|---|---|---|
| `legal_entity_id` | GUID | NO | FK → `legal_entity.id` (1:1 per tenant; intra-tenant) |
| `issuer_type` | String(50) | YES | CORPORATE/SOVEREIGN/AGENCY/MUNICIPAL/SUPRANATIONAL — plain string |
| `sector` | String(100) | YES | industry/sector classification — plain string |
| `is_active` | Boolean | NO | default True |
| `record_version` | Integer | NO | default 1 |

Constraints: `pk_issuer`; `UniqueConstraint('tenant_id','legal_entity_id', name='uq_issuer_tenant_legal_entity')` (the **1:1** contract — at most one issuer profile per legal entity per tenant); `fk_issuer_legal_entity_id_legal_entity`; `ix_issuer_tenant_id`; `ix_issuer_legal_entity_id`.

### 3.3 `counterparty` (ENT-003, EV, tenant-scoped role profile)
Same mixin stack + `record_version`. Distinct from `issuer` (OD-P1B-D); **ZERO netting/CSA/collateral columns** (OD-015 deferred).

| Column | Type | Null | Notes |
|---|---|---|---|
| `legal_entity_id` | GUID | NO | FK → `legal_entity.id` (1:1 per tenant; intra-tenant) |
| `counterparty_type` | String(50) | YES | BANK/BROKER/CCP/CLIENT/FUND — plain string |
| `is_active` | Boolean | NO | default True |
| `record_version` | Integer | NO | default 1 |

Constraints: `pk_counterparty`; `UniqueConstraint('tenant_id','legal_entity_id', name='uq_counterparty_tenant_legal_entity')` (1:1); `fk_counterparty_legal_entity_id_legal_entity`; `ix_counterparty_tenant_id`; `ix_counterparty_legal_entity_id`.

**Both-roles invariant.** A single `legal_entity` may carry one `issuer` row AND one `counterparty` row (a bank that both issues debt and trades with the firm). The two profiles are independent rows; neither `UNIQUE` collides with the other.

**Per-profile `is_active` is intentional role-level activation** (distinct from the core's `is_active`): the same legal entity can be retired *as a counterparty* while remaining active *as an issuer*. It is the only "status" attribute on a profile and is a legitimate role-specific attribute (so the "profiles hold only role-specific attributes" contract holds). An `is_active` flip rides on `REFERENCE.UPDATE` (NOT `REFERENCE.STATUS_CHANGE`, which stays reserved — §8).

---

## 4. Temporal classifications

- **All three are EV** — `__temporal_class__ = TemporalClass.EFFECTIVE_DATED` (AD-005 §2A; canonical ENT-002/003 are EV reference/master data). Heads + profiles use `EffectiveDatedMixin` + explicit `record_version`. **No IA, no FR.** `irp_prevent_mutation` is NOT attached; no `APPEND_ONLY_TABLES` entry. A `REFERENCE.UPDATE` (effective-dated supersede / attribute change / `is_active` flip / re-parent) must succeed at the DB; an EV-mutability test documents this (mirror P1B-1).
- **No FR usage** — `instrument_terms` (FR, the first real bitemporal usage) is **P1B-3**, NOT here. A scope-fence test asserts none of the three declares FR or carries a `system_from`/bitemporal column.
- An effective-dated supersede (e.g. a re-domicile, a re-parent, an `is_active` retire) is a `REFERENCE.UPDATE` of the same logical entity (stable `entity_id` per row id), never a new CREATE, never `REFERENCE.CORRECTION` (reserved).
- **One physical row per logical entity (decisive for the uniques).** Like P1B-1 `currency`/`calendar`, these tables keep a **single mutable row** per logical entity — an EV supersede is an **in-place** attribute change + `record_version` bump, and the version history is reconstructed from the `REFERENCE.UPDATE` audit trail, NOT from multiple physical rows. This is what makes `uq_legal_entity_tenant_code` and the `(tenant_id, lei)` partial-unique provably collision-free. **(Contrast OD-P1B-G `identifier_xref`,** which DOES keep superseded version rows and therefore scopes its unique `WHERE valid_to IS NULL` — P1B-2 deliberately does NOT, and an EV-mutability test asserts an UPDATE mutates the same row id.) If multi-row EV history were ever intended, both uniques would have to become `WHERE valid_to IS NULL` partials.

---

## 5. Legal entity / issuer / counterparty relationship (OD-P1B-D — special focus)

- **legal_entity is the IMPLEMENTATION-ONLY shared core — NO canonical ENT id** (OD-P1B-D §7). Canonical **ENT-002 (issuer)** and **ENT-003 (counterparty)** are preserved as the two 1:1 role profiles; `legal_entity` is a normalization that removes LEI/name/hierarchy **duplication** between them, not a new domain concept. **No canonical-model amendment / no new ENT id** — only an annotation that ENT-002/003 share a `legal_entity` core (already present at canonical ENT-002/003; reaffirmed in §19). *Justification to canonicalize (the OD-P1B-D escape hatch) is NOT met here:* there is no requirement, FK target, or report that needs a bare `legal_entity` as a first-class canonical entity — every domain reference (instrument's issuer FK in P1B-3, future ratings/exposure) targets a **role profile**, not the bare core.
- **Sharing mechanism = 1:1 FK from each profile to the core.** `issuer.legal_entity_id` and `counterparty.legal_entity_id` are NOT NULL FKs to `legal_entity.id`, each `UNIQUE(tenant_id, legal_entity_id)`. A profile cannot exist without its core (FK + NOT NULL + **explicitly-tenant-filtered** resolution per the §1 resolution discipline — `select(LegalEntity).where(LegalEntity.id == core_id, LegalEntity.tenant_id == acting_tenant)`; a cross-tenant/unknown core resolves to zero rows → `LegalEntityNotVisible`, fail-closed on BOTH SQLite and PG). A legal entity may carry both, one, or neither profile.
- **Identity lives on the core only.** Profiles hold ONLY role-specific attributes (`issuer_type`/`sector`; `counterparty_type`) — never a second copy of LEI/name/jurisdiction/hierarchy. This is the "shared core, distinct role tables" contract; the rejected unified-table-with-flags alternative is out (§2).
- **Future credit/counterparty risk seam (no implementation now, §15.special).** Credit risk attaches ratings/exposure to the **issuer** profile (and resolves issuer-group concentration via the core hierarchy); counterparty risk attaches exposure/netting to the **counterparty** profile (and nets at the core's ultimate parent). Both reach the shared hierarchy through the core regardless of role — which is exactly why the hierarchy lives on `legal_entity`, not on a profile. P1B-2 builds the identity + hierarchy backbone these will FK into; it builds none of the risk math.

---

## 6. Hierarchy / parent / ultimate parent approach (special focus)

- **Representation = adjacency list** (`parent_legal_entity_id` self-FK on the core), NOT a closure table (OQ-P1B2-002). Adjacency is the minimal structural hook; a closure/materialized-path table is a performance optimization deferred until exposure rollup at scale needs it.
- **Hierarchy is on the CORE** (OD-P1B-D §4) so rollup resolves through `legal_entity` regardless of issuer/counterparty role. **Intra-tenant only:** the self-FK references `legal_entity.id` within the same tenant (legal_entity is tenant-scoped, symmetric RLS); there is no cross-tenant parent and no shared/global hierarchy.
- **Belongs in P1B-2 (special focus #3): YES, the STRUCTURE — recommended.** REQ-SMR-002 explicitly names "LEI + parent hierarchy"; deferring it would split the entity across slices and force a later migration on a populated table. P1B-2 ships: (a) the `parent_legal_entity_id` column; (b) a **self-parent guard** (reject `parent_legal_entity_id == id` on write); (c) a bounded **read-only `resolve_ultimate_parent(session, legal_entity, *, acting_tenant)`** that walks the adjacency to the root (`parent_legal_entity_id IS NULL`), with a **visited-set (guarantees termination) + a depth cap of 32 (defense-in-depth; exceeding it raises `HierarchyCycleError` regardless of whether a true cycle exists — acceptable for the skeleton, revisited with a closure table at rollup-at-scale)**. **Each hop queries the passed-in RLS-scoped session with an EXPLICIT `tenant_id == acting_tenant` predicate** (the §1 resolution discipline) — never a new session/connection, never a recursive CTE, never a BYPASSRLS path — so a `parent_legal_entity_id` that points at another tenant's core resolves to None and the walk **terminates at the tenant boundary** (it cannot cross tenants on SQLite or PG). This is a **pure structural traversal — NO exposure/credit math, no numeric aggregation** — the single piece of "logic" in an otherwise pure-CRUD slice.
- **Deferred (NOT P1B-2):** the exposure-rollup *calculation*; multi-parent / percentage-ownership graphs; a denormalized computed `ultimate_parent_id` column (the resolver computes it on read — no stored rollup to drift); write-time deep-cycle prevention (the read-time resolver guard suffices for the skeleton; OQ-P1B2-003); closure table.

---

## 7. APIs

Thin endpoints in a NEW `irp_backend/api/reference_entities.py` (one file, three sub-routers under `/reference`). **Rationale for a new file:** `api/reference.py` (the P1B-1 currency/calendar/rating endpoints) is already ~330 lines; adding three entities + a hierarchy read would breach the ~250-line split guideline (OD-ARCH-A) — so split per OQ-P1B2-007. Mirror `api/reference.py` exactly.

| Method + path | Permission (deny-by-default) | Behavior |
|---|---|---|
| `POST /reference/legal-entities` | `reference.legal_entity.edit` | governed create (optional `parent_legal_entity_id`, RLS-resolved; self-parent → 422) |
| `GET /reference/legal-entities` `(/{id})` | `reference.legal_entity.view` | list / detail (detail includes resolved `ultimate_parent_id` + immediate `parent_legal_entity_id`) |
| `POST /reference/issuers` | `reference.issuer.edit` (exists) | governed create; resolves `legal_entity_id` RLS-scoped (fail-closed) |
| `GET /reference/issuers` `(/{id})` | `reference.issuer.view` (exists) | list / detail (joins the core for LEI/name) |
| `POST /reference/counterparties` | `reference.counterparty.edit` (exists) | governed create; resolves `legal_entity_id` RLS-scoped (fail-closed) |
| `GET /reference/counterparties` `(/{id})` | `reference.counterparty.view` (exists) | list / detail (joins the core) |

Invariants (copied from `api/reference.py`): `require_permission(...)` module-level singletons; `get_tenant_session` sets context; **`tenant_id` server-stamped from the principal — never the body**; profiles **resolve `legal_entity_id` with an explicit `tenant_id == principal.tenant_id` predicate** (§1 resolution discipline) and stamp `tenant_id` from the resolved core (cross-tenant/unknown core → indistinguishable 404, fail-closed on SQLite and PG); single end-of-request `db.commit()`; **404** on cross-tenant/unknown id; **422** on malformed UUID path/body id or self-parent. **No PUT/DELETE/bulk/search.** **No `DISTINCT ON` dedup** (not hybrid — no SYSTEM rows to dedup; a plain `ORDER BY code` list). Register the router in `apps/backend/src/irp_backend/main.py`.

---

## 8. Audit events (reuse REFERENCE.CREATE / .UPDATE — already activated P1B-1)

- **No new audit code.** `REFERENCE.CREATE` (EVT-140) / `REFERENCE.UPDATE` (EVT-141) were activated in P1B-1; P1B-2 reuses the `irp_shared/reference/events.py` constants against the FROZEN `record_event`. `apps/.../audit/service.py` stays FROZEN.
- **Each entity emits its OWN event (NOT folded).** Unlike P1B-1's parent/child fold-in (holidays/grades had no own event because they are sub-collections written in the parent's transaction), `legal_entity`, `issuer`, and `counterparty` are **independently-governed first-class entities** — a `legal_entity` create emits one `REFERENCE.CREATE` (`entity_type='legal_entity'`); a later `issuer` create emits its own `REFERENCE.CREATE` (`entity_type='issuer'`); likewise `counterparty`. `source_module='reference'`, `action='create'|'update'`.
- **`entity_type`** is the literal table name (`'legal_entity'` | `'issuer'` | `'counterparty'`); `entity_id` = the row id.
- **`before_value`/`after_value` are DC-2 metadata only:** CREATE `after_value` = identifying/controlled-vocab fields (`legal_entity`: `{code, name, lei, jurisdiction, entity_type, is_active, parent_legal_entity_id}`; `issuer`: `{legal_entity_id, issuer_type, sector, is_active}`; `counterparty`: `{legal_entity_id, counterparty_type, is_active}`); UPDATE = diffed changed keys only. **Never serialize the joined core, full rows, or raw client input.** A re-parent or `is_active` flip rides on `REFERENCE.UPDATE`.
- **Emission ordering vs RLS (AUD-04).** The governed row (and profile) is `add` + `flush`ed FIRST, so any RLS `WITH CHECK` rejection (42501) aborts the transaction **before** `record_event` runs — no `REFERENCE.*` event is emitted for a write the DB rejects. On a cross-tenant profile/parent **resolution** failure the path raises `LegalEntityNotVisible` → 404 **before** any add/flush/audit, so no denied-outcome event is written to any chain (in particular never to another tenant's chain).
- **Per-tenant chains** (`chain_id = tenant_id`); no SYSTEM chain (no SYSTEM_TENANT rows). `verify_chain` green per tenant. On a tenant's **first** governed write, the lazily-created MANUAL `data_source` emits exactly one `DATA.SOURCE_REGISTER` on the tenant chain (then reused) — assert exactly-one across the three creates (§14).
- **Do NOT** emit `REFERENCE.CORRECTION` / `REFERENCE.STATUS_CHANGE` (reserved), and **do NOT** introduce generic `DATA.*` for entity CRUD.

---

## 9. Entitlement checks

- **Additive only** to `irp_shared/entitlement/bootstrap.py` PERMISSIONS (append two tuples; `reference.issuer.*` / `reference.counterparty.*` already exist and are **not re-added**):
  - `reference.legal_entity.view`, `reference.legal_entity.edit`
- **Grants (least-privilege; `legal_entity` is PROPRIETARY identity — match the issuer/counterparty family, NOT the global-vocabulary family):** `.edit` → `data_steward` (+ `platform_admin` via `ALL_CODES`); `.view` → **`data_steward`, `risk_analyst_1l`, `risk_manager_2l`** (+ `platform_admin`). **`legal_entity.view` is granted to EXACTLY the recipients of the shipped `reference.issuer.view` / `reference.counterparty.view`** — i.e. it deliberately **EXCLUDES `auditor_3l`**. Rationale (SoD, R-04): the shipped catalog grants the 3L auditor `.view` only on the **non-proprietary** global vocabularies (`currency`/`rating_scale`/`calendar`, `bootstrap.py` lines 113–121); it withholds `reference.issuer.view`/`counterparty.view` from `auditor_3l`. `legal_entity` is where the proprietary identity (LEI/name/jurisdiction/hierarchy) those profile perms gate actually lives (§5 "identity on the core only"), so granting `auditor_3l` `legal_entity.view` would open a read path into proprietary identity the auditor is denied at the profile level — an SoD inconsistency. **Correcting the prior draft's false claim:** `auditor_3l` is NOT an existing recipient of `reference.issuer.view`/`counterparty.view` (only `data_steward`/`risk_analyst_1l`/`risk_manager_2l` are). Whether to additively grant `auditor_3l` the issuer/counterparty/legal_entity views is a separate SoD decision, out of scope here (OD-P1B-F: additive grants only). **No role-template restructure** beyond the two additive `legal_entity` grants.
- **`reference.rating.*` stays RESERVED — do NOT mint.** No new permission family for credit/counterparty risk (those land with their phases).
- **Deny-by-default (CTRL-011):** every GET needs a real `.view`; a principal lacking `reference.legal_entity.edit` is denied `POST /reference/legal-entities`. Issuer/counterparty creates require the existing `reference.issuer.edit`/`reference.counterparty.edit`.
- **Seeding the new permission/role_permission rows:** the established P1A/P1B-1 catalog precedent — `0002_entitlement_seed` materializes the live `bootstrap.PERMISSIONS` on a fresh `alembic upgrade head` (CI runs fresh), so the two new `legal_entity` rows seed automatically; no forward migration. A bootstrap unit test asserts: the new codes present; `reference.rating.*` absent; AND a **recipient-set-parity** assertion — `legal_entity.view`'s granted roles EQUAL `issuer.view`'s granted roles (so the proprietary-identity family cannot drift, and `auditor_3l` is provably excluded).

---

## 10. RLS behavior (SYMMETRIC tenant-scoped — NOT hybrid; special focus: no cross-tenant leakage)

**The shipped symmetric loop — NOT the P1B-1 asymmetric hybrid loop.** Migration 0009 reuses the exact pattern from 0004/0005/0007: for each of `legal_entity`, `issuer`, `counterparty`:

```
ALTER TABLE t ENABLE ROW LEVEL SECURITY;
ALTER TABLE t FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_t ON t
  USING (tenant_id::text = current_setting('app.current_tenant', true))
  WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true));
```

- **`USING == WITH CHECK == own-tenant` (single-tenant, fully fail-closed).** No SYSTEM_TENANT disjunct. A no-context read returns **zero rows** (unlike the hybrid tables, which return the global slice); a no-context / forged / cross-tenant write fails `WITH CHECK` → **42501**. This is the proprietary/MNPI default (OD-P1B-C hard invariant: legal_entity/issuer/counterparty are NEVER hybrid).
- **Cross-tenant leakage is prevented on every axis (special focus #4):**
  1. **Reads:** symmetric `USING` hides every other tenant's `legal_entity`/`issuer`/`counterparty` (no SYSTEM disjunct to leak through).
  2. **Writes:** `WITH CHECK` + server-stamped `tenant_id` reject a forged tenant (42501); the body tenant is ignored.
  3. **Profile→core resolution:** `create_issuer`/`create_counterparty` resolve `legal_entity_id` with an **explicit `tenant_id == acting_tenant` predicate** (§1 resolution discipline — NOT id-only) and stamp the profile's `tenant_id` from the resolved core — a cross-tenant `legal_entity_id` resolves to zero rows → `LegalEntityNotVisible` (fail-closed **on SQLite AND PG**), so a tenant cannot attach a profile to another tenant's core.
  4. **Hierarchy:** `parent_legal_entity_id` is resolved with the same explicit tenant predicate on write (cross-tenant parent → not-visible → rejected); the FK is single-column to `legal_entity.id` but intra-tenant **by resolution** (not by the FK, which the DB does not tenant-qualify); the resolver walks only within the tenant.
  5. **RLS structure assertions (regression guards):** (a) the EXISTING P1B-1 closed-set `pg_policies` test already guards the negative globally (the SYSTEM literal exists on ONLY the five P1B-1 tables) — it needs **no change** and confirms P1B-2 did not widen the hybrid set; (b) **net-new:** a POSITIVE assertion that each of `legal_entity`/`issuer`/`counterparty` has a `tenant_isolation_<t>` policy with `relrowsecurity` AND `relforcerowsecurity` true and **no** SYSTEM literal in `qual`/`with_check` (so a forgotten or symmetrized-to-SYSTEM policy is caught structurally, in addition to the behavioral isolation/42501 tests below).
- **No append-only trigger** on any of the three (all EV). Native-uuid trap applies to PG tests. `revision='0009_legal_entity'`, `down_revision='0008_reference_data'`.

---

## 11. Lineage behavior (OD-P1B-I — reuse P1B-1)

- **One ORIGIN edge per entity row** (`legal_entity`, `issuer`, `counterparty` each), rooted **through the shipped `record_reference_create`** (which internally calls `ensure_manual_source` + `record_lineage(..., edge_kind=EDGE_KIND_ORIGIN)`) — the binders do NOT call `record_lineage` directly (a redundant binder-level call would double the edge). Co-transactional, in the row's own tenant context. Reuse the P1B-1 `ensure_manual_source(session, tenant_id, actor_id)` (idempotent per-tenant MANUAL `data_source`).
- **Profile→core and parent→child are referential FKs, NOT lineage edges.** The only lineage edge per row is its MANUAL ORIGIN edge; no `STRUCTURE`/`DERIVED` edge kind is introduced (this forecloses a spurious "add lineage for the relationship" change and keeps the `EDGE_KIND` vocab closed).
- **All edges are tenant-scoped** (`edge.tenant_id = tenant`) — there is **no SYSTEM seed path** in P1B-2 (no global rows). `data_source` stays symmetric (unchanged).
- A profile's lineage roots in the **profile's own** tenant context (same tenant as its resolved core). An UPDATE adds **no** second edge (CREATE-only, the P1B-1 single-origin invariant) — tested.
- `assert_has_lineage` available to downstream consumers; a test asserts every created row has exactly one ORIGIN edge from a MANUAL source.

---

## 12. Data quality behavior

- **Generic only, optional, where configured** (reuse P1A-3 / P1B-1; `rule_type='NOT_NULL'`, the existing generic kind — no new `rule_type` minted). Recommend wiring `not_null` on `legal_entity.name` and `legal_entity.code` as cheap generic guards (OQ-P1B2-006). **No DQ rule on `issuer`/`counterparty`; no `allowed_values`/format/checksum/LEI-validation rule on `lei`/`jurisdiction`/`*_type`** — LEI is field-shape only (`String(20)`), validation beyond `not_null` is out of scope; `entity_type`/`issuer_type`/`counterparty_type` stay open-vocab. A scope-fence test asserts no `allowed_values` DQ rule is seeded for P1B-2 entities. DQ is NOT forced on every write.

---

## 13. Ingestion usage

**NONE.** P1B-2 is **direct governed CRUD only** (the P1A-4 staging→canonical mapping is the conditional P1B-5). `irp_shared.reference` must not import `irp_shared.ingestion`; no `ingestion_batch_id` on any P1B-2 row.

---

## 14. Tests

**Logic (SQLite-local):**
- Generic create/update core for all three; EV mutability (head/profile update succeeds, bumps `record_version`).
- **1:1 contract:** a second `issuer` for the same `legal_entity` (same tenant) violates `uq_issuer_tenant_legal_entity`; same for `counterparty`. A `legal_entity` carrying BOTH an issuer and a counterparty profile succeeds (both-roles test).
- **Orphan-profile-rejected:** `create_issuer`/`create_counterparty` with an unknown/cross-tenant `legal_entity_id` raises `LegalEntityNotVisible` (fail-closed); no profile row persists.
- **Hierarchy:** set `parent_legal_entity_id`; `resolve_ultimate_parent` walks to the root; **self-parent rejected** (write → ValueError/422); **cycle-safe** (a hand-built A→B→A cycle terminates with `HierarchyCycleError` within the depth cap, never loops).
- **Audit (own-event, not folded):** `REFERENCE.CREATE`/`.UPDATE` per entity with **literal code strings** + correct `entity_type`; **assert creating an issuer profile emits exactly ONE `REFERENCE.CREATE` with `entity_type='issuer'` and does NOT fold into / re-emit a `legal_entity` event** (same for counterparty) — a legal_entity + issuer + counterparty = exactly 3 `REFERENCE.CREATE`, one per `entity_type`; reserved `CORRECTION`/`STATUS_CHANGE` never emitted (assert those literal strings never appear in `AuditEvent.event_type`).
- **Lineage:** exactly one ORIGIN edge per created row from a MANUAL `data_source`; **MANUAL-source idempotency** — across a legal_entity + issuer + counterparty create in ONE tenant, assert exactly ONE `data_source(MANUAL)` and exactly ONE `DATA.SOURCE_REGISTER` event on the tenant chain (idempotent reuse, mirroring the P1B-1 SYSTEM-seed test on the tenant chain) while each of the three rows still has its own ORIGIN edge; **single-origin on UPDATE** — for EACH entity, after one UPDATE (incl. a legal_entity re-parent and an `is_active` flip) assert the ORIGIN edge count is still 1 and the edge id is unchanged; `assert_has_lineage` passes. **Profile→core and parent→child are referential FKs, NOT lineage edges** — no STRUCTURE/DERIVED edge kind is introduced (§11).
- **Fail-closed — CREATE (AUD-04 / CTRL-032), THREE enumerated tests (legal_entity, issuer, counterparty):** each constructs a VALID core FIRST so resolution PASSES (the cross-tenant resolution short-circuits BEFORE any side-effect and is covered by the orphan test above — it does NOT exercise rollback), then monkeypatches **`reference.service.record_event`** to raise (NOT the lineage-module binding, so `DATA.SOURCE_REGISTER` is genuinely created-then-rolled-back) and asserts the entity/profile row + its ORIGIN lineage edge + the lazily-created MANUAL `data_source` + its `DATA.SOURCE_REGISTER` all count **zero** after `rollback()` (the P1B-1 no-orphan shape, now proven for the profile writes too).
- **Fail-closed — UPDATE (AUD-04 / CTRL-032):** apply an update (e.g. an `is_active` flip or a re-parent), monkeypatch `record_event` to raise, then after `rollback()` assert the row's mutated attributes AND `record_version` are unchanged and that **zero `REFERENCE.UPDATE` events persisted** (CTRL-032 covers governed CHANGE, not just CREATE).
- **Gap-free chain after rollback (AUD-03 / CTRL-026):** after a fail-closed rollback, perform a successful create on the same tenant and assert `verify_chain(tenant).ok is True` with a contiguous `sequence_no` (the rolled-back event left no gap).
- **DC-2 metadata-only:** `after_value` carries only identifying/vocab fields (+ ids) — never the joined core or raw input.

**Endpoint:** deny-by-default per entity (missing `.edit` → 403 + no write; missing `.view` → 403); server-stamped tenant (forged body ignored); profile create resolves the core (cross-tenant core → 404); indistinguishable 404; 422 on malformed UUID and on self-parent; detail read returns resolved `ultimate_parent_id`.

**PG (constrained `irp_app`, symmetric RLS, native-uuid trap).** The `app_url` fixture (mirroring `test_reference_pg.py`) MUST add the three new tables to its per-table `GRANT SELECT, INSERT, UPDATE, DELETE … TO irp_app` list, or the matrix cannot run under the constrained role.
- Tenant isolation: tenant A cannot see B's `legal_entity`/`issuer`/`counterparty`; no-context read → **zero rows** (fully fail-closed — contrast the hybrid tables); forged/no-context write → 42501.
- **Profile→core cross-tenant rejection:** under tenant A, creating an issuer whose `legal_entity_id` belongs to tenant B fails closed (RLS-invisible core + the explicit tenant predicate).
- **Hierarchy intra-tenant + boundary-terminating:** a `parent_legal_entity_id` pointing at another tenant's core is rejected on write; and a parent chain that (by raw insert) links into another tenant's core **terminates at the boundary** — the cross-tenant hop resolves to None, the walk stops, no other-tenant node is visited.
- **Structural RLS assertions (`pg_policies` introspection):** (a) the existing P1B-1 closed-set test (unchanged) confirms the SYSTEM literal is on ONLY the five P1B-1 tables; (b) **net-new positive assertion** — each of `legal_entity`/`issuer`/`counterparty` has a `tenant_isolation_<t>` policy, `relrowsecurity` AND `relforcerowsecurity` are both true, and neither `qual` nor `with_check` contains the SYSTEM literal (catches a forgotten/over-permissive/symmetrized-to-SYSTEM policy structurally, beyond the behavioral 42501 tests).
- **Forged-tenant write emits no audit (AUD-04):** a forged-tenant profile create (DB rejects via `WITH CHECK` 42501, OR resolution raises `LegalEntityNotVisible` → 404) leaves **zero `REFERENCE.CREATE` events on every chain** — no event is written for a write the DB rejects, and no denied-outcome event lands on another tenant's chain.
- EV-mutable: a `REFERENCE.UPDATE` (raw UPDATE) succeeds (no `irp_prevent_mutation`).
- `verify_chain(tenant)` green.

**Import-direction (extend the P1B-1 scanner):** the new `reference/*.py` still import only `lineage`/`dq`/`audit`/`entitlement`/`db`/`temporal` (allowlist); no `irp_backend`, no `irp_shared.models` (plural), no `irp_shared.ingestion`.

**Scope-fence (negative):** exactly three new tables in 0009 (enumerated); no `instrument`/`instrument_terms`/`identifier_xref`/`corporate_action` object; **no netting/CSA/collateral/exposure column** on `counterparty`; no FR mixin / no `system_from` on any of the three; no SYSTEM_TENANT row / no hybrid policy; `reference.rating.*` absent; bootstrap diff append-only. Additionally:
- **Identity-on-core-only:** assert the `issuer` and `counterparty` column sets are exactly `{legal_entity_id, <role attr(s)>, is_active, record_version}` + mixin columns — i.e. **NO `code`/`lei`/`name`/`jurisdiction`/`parent_legal_entity_id` on either profile** (the shared-core contract, §5).
- **No stored rollup:** assert `legal_entity` has NO `ultimate_parent_id`/rollup/exposure/concentration column (only the `parent_legal_entity_id` self-FK); `resolve_ultimate_parent` returns an id by walking adjacency only (no numeric aggregation, no exposure import) — the structure-now/rollup-later split is test-enforced, not prose-only.
- **Source-of-truth drift guard:** a path/diff guard asserting migrations 0001–0008 and `irp_shared/audit/service.py` are unmodified by the P1B-2 diff, and that `HYBRID_TABLES` (in `reference/models.py` AND migration 0008) still equals exactly the five P1B-1 names (complements the runtime closed-set pg_policies test).

**CI:** add a **reference legal-entity RLS PG step** (mirror the model/dq/ingestion/reference `*_pg.py` steps) running the symmetric-RLS + profile-resolution + closed-set matrix under `irp_app`; `alembic check` covers 0009.

---

## 15. Acceptance criteria

1. **Three EV tables** (`legal_entity`, `issuer`, `counterparty`) in migration 0009, all `__temporal_class__ = EFFECTIVE_DATED`, tenant-scoped **symmetric** RLS, no append-only trigger, no hybrid/SYSTEM_TENANT.
2. **Shared core + distinct 1:1 role profiles** (OD-P1B-D): `issuer`/`counterparty` are 1:1 over `legal_entity` (`UNIQUE(tenant_id, legal_entity_id)`); a profile cannot exist without its core; a legal entity can carry both.
3. **LEI + structural hierarchy present:** `legal_entity.lei` + `parent_legal_entity_id` self-FK (intra-tenant); `resolve_ultimate_parent` resolves to the root (cycle-safe); self-parent rejected. (Exposure-rollup *calc* deferred.)
4. **Tenant-isolated:** cross-tenant `legal_entity`/`issuer`/`counterparty` invisible; no-context read returns zero rows; forged-tenant write 42501; profile/parent resolution fails closed cross-tenant; the closed-hybrid-set invariant holds (these 3 are NOT hybrid).
5. **Audited:** each entity emits its own `REFERENCE.CREATE`/`.UPDATE` (EVT-140/141) co-transactionally, fail-closed; `verify_chain` green per tenant.
6. **Lineage-rooted:** every row has exactly one ORIGIN edge from a MANUAL `data_source` in its own tenant context.
7. **Entitlement:** `reference.legal_entity.view/edit` minted (additive); `.view` granted to EXACTLY the `issuer.view`/`counterparty.view` recipient set (data_steward/risk_analyst_1l/risk_manager_2l + platform_admin — **excludes auditor_3l**, proprietary-identity SoD); existing issuer/counterparty perms gate the endpoints deny-by-default; `reference.rating.*` absent; recipient-set parity asserted.
8. **Package boundary + scope fences:** import-direction green; `make check` + `alembic check` clean; CI legal-entity RLS step green; only three tables; no excluded entity/column/permission; no netting/exposure/credit; no ingestion; no hybrid.

---

## 16. Risks

- **Cross-tenant leakage of proprietary entities (load-bearing, SEC-RLS).** A mis-applied hybrid policy or an unscoped profile/parent resolution would expose a firm's issuer/counterparty book (MNPI). **Mitigation:** symmetric `USING == WITH CHECK`; RLS-scoped profile→core + parent resolution (fail-closed); the closed-hybrid-set `pg_policies` test; server-stamped tenant.
- **1:1 contract / orphan profiles.** A profile without a core, or two issuer profiles for one core, breaks the model. **Mitigation:** `legal_entity_id` NOT NULL FK + `UNIQUE(tenant_id, legal_entity_id)` + resolution fail-closed.
- **Hierarchy cycles / unbounded recursion.** A data cycle (A→B→A) in the ultimate-parent resolver could loop. **Mitigation:** visited-set + depth cap → `HierarchyCycleError`; self-parent rejected on write; closure/deep-cycle prevention deferred (OQ-P1B2-003).
- **Scope creep into exposure/netting/credit.** REQ-SMR-002's "exposure rolls to ultimate parent" tempts building rollup math. **Mitigation:** explicit exclusions + scope-fence tests (no netting/CSA/exposure column; resolver is pure structural walk).
- **Canonicalization drift.** Treating `legal_entity` as a canonical entity would force a model amendment. **Mitigation:** implementation-only, no ENT id (OD-P1B-D); annotation only.
- **`api/reference.py` bloat.** Adding three entities to the P1B-1 file would exceed the split guideline. **Mitigation:** new `api/reference_entities.py` (OQ-P1B2-007).

---

## 17. Open decisions

| ID | Question | Recommendation |
|---|---|---|
| OQ-P1B2-001 | `legal_entity` implementation-only vs canonicalized (new ENT id)? | **Implementation-only, NO ENT id** (OD-P1B-D) — canonical annotation only; the escape-hatch justification to canonicalize is not met (every domain FK targets a role profile, not the bare core). |
| OQ-P1B2-002 | Hierarchy representation — adjacency vs closure table? | **Adjacency** (`parent_legal_entity_id`) for the skeleton; closure/materialized-path deferred to exposure-rollup-at-scale. |
| OQ-P1B2-003 | Ultimate-parent resolver in P1B-2, and how cycle-safe? | **Include a bounded read-only resolver** (structural walk to root; visited-set + depth cap → `HierarchyCycleError`); self-parent rejected on write; **deep write-time cycle prevention deferred** (read-time guard suffices). NO exposure math. |
| OQ-P1B2-004 | Enforce LEI uniqueness per tenant? | **Postgres partial-unique** `(tenant_id, lei) WHERE lei IS NOT NULL` (LEI unique per tenant when present; nullable so unidentified entities are allowed); SQLite-local equivalent in logic tests. |
| OQ-P1B2-005 | Do profiles carry their own `code`, or are they identified solely by `legal_entity_id`? | **Identified by `legal_entity_id`** (`UNIQUE(tenant_id, legal_entity_id)`) — no second identity/code on the profile (avoids divergent identity). |
| OQ-P1B2-006 | Generic DQ on create? | **`not_null` on `legal_entity.code` + `name`** as cheap guards; no `allowed_values` vocab gates; no domain rules. |
| OQ-P1B2-007 | Endpoint file layout? | **New `api/reference_entities.py`** (legal-entity/issuer/counterparty routers) — `api/reference.py` (~330 lines) would breach the ~250-line split guideline. |
| OQ-P1B2-008 | Combined create (core + profiles in one call, fold-in) vs independent governed creates? | **Independent governed creates** (each its own `REFERENCE.CREATE` + lineage edge); a convenience combined endpoint is deferred (profiles are independently-governed, not sub-collections). |
| OQ-P1B2-009 | A global LEI directory (hybrid, like currency)? | **No** — out of scope; issuer/counterparty as a firm uses them are proprietary/tenant-scoped. Raise as a separate future reference catalog if ever needed; do NOT couple it to P1B-2. |

---

## 18. Controls impacted

| Control | Impact in P1B-2 |
|---|---|
| **CTRL-004** (data-dictionary field definition) | LEI (ISO-17442), `jurisdiction` (ISO-3166), `entity_type`/`issuer_type`/`counterparty_type` vocab field shapes. |
| **CTRL-011** (deny-by-default + tenant isolation) | New `reference.legal_entity.*` perms + **symmetric RLS on three PROPRIETARY tables** (reaffirms single-tenant isolation; explicitly NOT hybrid — the proprietary-never-hybrid evidence). |
| **CTRL-005 / 012 / 017** (audit coverage) | `REFERENCE.CREATE`/`.UPDATE` on legal_entity/issuer/counterparty (own events). CTRL-017 = the `__temporal_class__ = EFFECTIVE_DATED` declaration test (EV, not append-only). |
| **CTRL-032** (failed audit blocks governed change) | Fail-closed evidence for **both** governed CREATE (three per-entity tests — legal_entity/issuer/**profile**: entity + lineage edge + lazily-created MANUAL source + `DATA.SOURCE_REGISTER` roll back together, valid-core-first so the profile write actually materializes) AND governed UPDATE (mutated attributes + `record_version` revert, zero `REFERENCE.UPDATE` persisted) — covers CTRL-032's full governed-change scope, not just create. |
| **CTRL-013** (lineage no-bypass) | One ORIGIN edge per entity row. |

---

## 19. Documentation updates (in-slice deliverables, gated in the same PR — DoD D19)

- **`canonical_data_model_standard.md`** ENT-002/003: annotate **REALIZED (P1B-2)** as 1:1 role profiles over an implementation-only `legal_entity` core (no new ENT id); hierarchy on the core.
- **`temporal_reproducibility_standard.md`** §2A: ENT-002/003 EV realized (P1B-2); FR still unexercised (P1B-3).
- **`audit_event_taxonomy.md`** §3 REFERENCE row: note legal_entity/issuer/counterparty now also emit `REFERENCE.CREATE`/`.UPDATE` (own events, per-tenant chains).
- **`entitlement_sod_model.md`** §5A: `reference.legal_entity.*` → IMPLEMENTED (P1B-2); issuer/counterparty perms now wired.
- **RTM** (`requirements_traceability_matrix.md`) **and the backbone REQ-SMR-002 row** (backbone is canonical for status — keep both in sync): REQ-SMR-002 → In-Progress (P1B-2, structural). **Bind the RTM's named acceptance test explicitly:** the RTM "Hierarchy rollup test" / "Exposure rolls to ultimate parent" clause is delivered for P1B-2 by the **structural `resolve_ultimate_parent` test** (root resolution + cycle guard + self-parent reject); the **exposure-math half** of that single clause is the reason REQ-SMR-002 stays In-Progress (mirror the REQ-SMR-004/005 phrasing that names exactly what shipped vs deferred).
- **`control_matrix_skeleton.md`** §4: P1B-2 additions paragraph (CTRL-004/005/011/012/017/032; proprietary-never-hybrid evidence).
- **`ci_enforcement_overview.md`** + `ci.yml`: add the reference legal-entity RLS PG step.

---

## 20. Whether P1B-2 is ready to implement

**Yes — ready to implement**, contingent on confirming the open decisions (none are blockers; all have firm recommendations). Every design choice maps to a ratified P1B-0 decision (OD-P1B-D shared-core / distinct-profiles; OD-P1B-C proprietary-never-hybrid; OD-P1B-F entitlements) and to a **verified, shipped** convention: the P1B-1 reference service core (`record_reference_create`/`record_reference_update`/`ensure_manual_source`), the **symmetric** RLS loop (0004/0005/0007), the `register_model_version` RLS-scoped parent-resolve precedent, the `api/reference.py` endpoint shape, and the additive-`bootstrap.py` catalog pattern. The seven lenses converge; the resolved conflicts (implementation-only core; hierarchy structure-now/rollup-later; profiles-own-events; new endpoint file) are decided above.

This plan incorporated a **7-lens UltraCode adversarial review** (Product, Architect, Data, Security/RLS, Audit/Controls, Lineage/DQ, Scope); the confirmed findings are folded in above — most load-bearingly the **explicit-tenant-predicate resolution discipline** (§1, so SQLite cross-tenant tests genuinely fail closed, not just under PG RLS), the **proprietary-identity grant correction** (§9, `legal_entity.view` excludes `auditor_3l` to match the issuer/counterparty family), the **per-entity valid-core-first CREATE + UPDATE fail-closed tests** (§14/§18), the **single-physical-row EV** clarification (§4, so the uniques are collision-free), and the **positive symmetric-RLS structural assertion** (§10/§14).

**Must-resolve-before-merge (not before-start):** confirm OQ-P1B2-003 (resolver depth/cycle policy — depth cap 32), OQ-P1B2-004 (LEI partial-unique mechanism), and the canonical-model ENT-002/003 annotation wording with R-05.

---

## 21. Implementation kickoff prompt (paste-ready)

> **DO NOT START until explicitly directed.** When directed, implement **P1B-2 (legal_entity core + issuer / counterparty role profiles)** per `10_delivery_backlog/p1b2_implementation_plan.md`.
>
> **Full scope (the deliverable cap — nothing beyond this):**
> 1. Extend the `irp_shared/reference/` package: add `LegalEntity`, `Issuer`, `Counterparty` EV ORM classes to `reference/models.py` (register in `irp_shared/models.py`); add thin binders `reference/legal_entity.py` / `issuer.py` / `counterparty.py` reusing the shipped `record_reference_create` / `record_reference_update` / `ensure_manual_source`; add a `legal_entity` parent-resolution helper + a bounded read-only `resolve_ultimate_parent(session, legal_entity, *, acting_tenant)` (visited-set + depth cap 32 → `HierarchyCycleError`; NO exposure math). **All three resolvers (profile→core, write-time parent, and each `resolve_ultimate_parent` hop) carry an EXPLICIT `tenant_id == acting_tenant` predicate** (the `ensure_manual_source` / `assert_registered_model_version(tenant_id=…)` pattern — NOT the RLS-only `register_model_version` id-only lookup), so cross-tenant fails closed on SQLite AND PG; PG RLS `WITH CHECK` is the production backstop.
> 2. ONE migration **0009** (`revision='0009_legal_entity'`, `down_revision='0008_reference_data'`) creating `legal_entity`, `issuer`, `counterparty`, with NAMING_CONVENTION names, the **SYMMETRIC** tenant-isolation RLS loop (`USING == WITH CHECK == own-tenant` — reuse 0004/0005/0007; **NO hybrid, NO SYSTEM_TENANT, NO append-only trigger**), `UNIQUE(tenant_id, code)` on the core, `UNIQUE(tenant_id, legal_entity_id)` on each profile, the `parent_legal_entity_id` self-FK, and the Postgres partial-unique `(tenant_id, lei) WHERE lei IS NOT NULL`. Do NOT touch the hybrid loop, migrations 0001–0008, or `audit/service.py`.
> 3. The three EV entities exactly as specified (§3) — EV; `__temporal_class__ = EFFECTIVE_DATED`; `record_version`; open-vocab attributes as plain Strings; NO netting/CSA/collateral/exposure column; NO FR/`system_from`.
> 4. Reuse `REFERENCE.CREATE`/`REFERENCE.UPDATE` (each entity emits its OWN event — NOT folded); `entity_type` = the table name; before/after = DC-2 metadata only; per-tenant chains.
> 5. **Additive** entitlement permissions in `bootstrap.py`: `reference.legal_entity.view/edit` (issuer/counterparty already exist — do not re-add); grant `.edit` → `data_steward`; grant `.view` to **EXACTLY the `reference.issuer.view`/`counterparty.view` recipient set** (`data_steward`/`risk_analyst_1l`/`risk_manager_2l` + `platform_admin` — **NOT `auditor_3l`**; proprietary-identity SoD); add a bootstrap test asserting new codes present, `reference.rating.*` absent, AND `legal_entity.view` recipients == `issuer.view` recipients (parity, no drift); **reserve `reference.rating.*`**.
> 6. Thin endpoints in a NEW `irp_backend/api/reference_entities.py` (register in `main.py`): `POST`/`GET` (list + `/{id}`) per entity; `require_permission` deny-by-default; `get_tenant_session`; server-stamped `tenant_id`; profiles resolve `legal_entity_id` RLS-scoped (cross-tenant → 404); self-parent → 422; indistinguishable 404; single end-of-request commit; detail read returns resolved `ultimate_parent_id`. **No `DISTINCT ON` (not hybrid).**
> 7. Per-tenant **MANUAL `data_source`** origin lineage on every write (`record_lineage` + `assert_has_lineage`; reuse `ensure_manual_source`). No SYSTEM seed path.
> 8. OPTIONAL generic DQ (`not_null` on `legal_entity.code`/`name`) only where configured.
> 9. Tests: SQLite logic (1:1 contract, both-roles, orphan-profile-rejected **with the explicit tenant predicate so cross-tenant fails closed on SQLite**, hierarchy + self-parent + cycle guard, own-event-not-folded audit, single-origin-on-UPDATE lineage + MANUAL-source idempotency, **three valid-core-first CREATE fail-closed tests + an UPDATE fail-closed test + verify_chain-after-rollback**, DC-2) + endpoint + PG (symmetric isolation, no-context-zero-rows, profile/parent cross-tenant fail-closed, boundary-terminating hierarchy walk, **positive symmetric-policy + FORCE-RLS assertion AND the unchanged closed-hybrid-set test**, forged-write-emits-no-audit, EV-mutable) + import-direction + scope-fence (identity-on-core-only, no-stored-rollup column, migrations 0001–0008 + audit/service.py + HYBRID_TABLES unchanged). **The `app_url` PG fixture must GRANT on the three new tables.** Add the reference legal-entity RLS step to CI.
> 10. In-slice doc updates: canonical ENT-002/003 realized annotation, temporal §2A, audit taxonomy, entitlement_sod_model, RTM (REQ-SMR-002 In-Progress, exposure-rollup calc deferred), control matrix, ci_enforcement_overview.
>
> **STRICT EXCLUSIONS (must NOT appear in any deliverable / entity / endpoint / test / migration):** instrument, instrument_terms, identifier_xref, corporate_action; rating ASSIGNMENTS and `reference.rating.*`; netting set / CSA / collateral; counterparty exposure / current-exposure / netting calc; credit risk / concentration / spread; market data, private-asset ingestion, reporting, dashboards, real SSO; portfolio/positions/valuations; the exposure-rollup-to-ultimate-parent CALCULATION (structure only); P1B-3/4/5 work. Do NOT make any P1B-2 table hybrid or stamp SYSTEM_TENANT. Do NOT modify the FROZEN `audit/service.py`, the asymmetric hybrid loop, or migrations 0001–0008. `irp_shared.reference` imports only `lineage`/`dq`/`audit`/`entitlement`/`db`/`temporal`.
>
> **Review cadence:** follow the multi-lens **UltraCode** cycle — implement → review (Product, Architect, Data, Security/RLS, Audit/Controls, Lineage/DQ, Scope) → fix in-scope findings → re-review until clean.
> **Gate:** run `make check` (lint + types + tests + `alembic check`) and the new legal-entity RLS PG step until green.
> **Commit only on explicit approval.** Do not commit or push until the reviewers sign off and you are told to commit.

### Build-sequence subsection

1. **Models + aggregator** — `LegalEntity`/`Issuer`/`Counterparty` in `reference/models.py` (mixins, uniques, self-FK, profile FKs); register in `irp_shared/models.py`. Verify `alembic check` sees the new metadata.
2. **Migration 0009** — DDL + the **symmetric** RLS loop + the LEI partial-unique; `alembic upgrade head` + `alembic check` clean; downgrade smoke.
3. **Binders + service helpers** — `legal_entity.py`/`issuer.py`/`counterparty.py`; the RLS-scoped parent-resolve + `resolve_ultimate_parent`; lineage + audit wiring (fail-closed); reuse the P1B-1 core.
4. **Entitlement** — additive `bootstrap.py` `legal_entity` perms + grants; bootstrap unit test.
5. **Endpoints** — `api/reference_entities.py` POST/GET per entity + hierarchy read; register in `main.py`.
6. **Tests** — logic → endpoint → PG symmetric-RLS matrix + closed-set guard → import-direction → scope-fence; add the CI legal-entity RLS step.
7. **Docs** — canonical/temporal/audit-taxonomy/entitlement_sod/RTM/control-matrix/ci_enforcement.
8. **`make check` green → multi-lens review → fix in-scope → commit on approval.**
