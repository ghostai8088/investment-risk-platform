# P1B-1 Implementation Plan — Currency / Calendar / Rating Scale (Reference Data, First Hybrid-Tenancy Slice)

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1B1-PLAN-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-01 Chief Architect AI (with R-05 Data Architect AI, R-04 Security AI, R-07 Audit/Controls AI) |
| Approver | H-06 Engineering Lead |
| Created | 2026-06-22 |
| Related Documents | `p1b0_decision_record.md` (ratified 4fae26b), `p1b_implementation_plan.md`, `p1a4_implementation_plan.md`, `p1a_closeout_p1b_readiness.md`, `../02_requirements/requirements_backbone.md`, `../02_requirements/requirements_traceability_matrix.md`, `../03_architecture/capability_map.md`, `../04_data_model/canonical_data_model_standard.md`, `../04_data_model/temporal_reproducibility_standard.md`, `../04_data_model/audit_event_taxonomy.md`, `../06_security/entitlement_sod_model.md`, `../09_compliance_controls/control_matrix_skeleton.md`, `../10_governance/definition_of_ready_done.md`, `packages/shared-python/src/irp_shared/lineage/service.py`, `packages/shared-python/src/irp_shared/dq/service.py`, `packages/shared-python/src/irp_shared/audit/service.py`, `packages/shared-python/src/irp_shared/entitlement/bootstrap.py` |
| Supported Build Rules | BR-3, BR-5, BR-7, BR-11, BR-12 (N/A — no IA tables), BR-13, BR-17, BR-19 |

**Purpose.** Author the authoritative, build-ready plan for **P1B-1**, the first Security Master & Reference Data slice and the first slice to exercise **AD-013-R1 hybrid tenancy** (SYSTEM_TENANT global rows + tenant overrides), the **asymmetric hybrid RLS** policy, the **REFERENCE.\*** audit taxonomy, the new reference entitlements, and the new web-framework-free **`irp_shared.reference`** package. P1B-1 delivers three EV reference vocabularies — **currency**, **calendar** (+ `calendar_holiday`), **rating_scale** (+ `rating_grade`) — via direct governed CRUD (no ingestion). It reuses every P1A rail (RLS, audit, lineage, DQ, entitlement, temporal mixins, Alembic drift gate, constrained-role PG tests) and **adds no new rail**. Migration head advances `0007 → 0008`.

**In-scope statement (the deliverable cap).** Exactly: (1) a NEW `irp_shared.reference` package (`models.py`, `events.py`, `service.py`, thin per-entity binders `currency.py` / `calendar.py` / `rating.py`, and a `bootstrap.py` seed catalog); (2) ONE migration **0008** creating exactly five tables — `currency`, `calendar`, `calendar_holiday`, `rating_scale`, `rating_grade` — with a NEW **asymmetric hybrid RLS loop** distinct from the shipped symmetric loop; (3) an OPTIONAL data-only migration **0009** for SYSTEM_TENANT global seeds + the additive permission/role_permission rows; (4) **activation** of `REFERENCE.CREATE` / `REFERENCE.UPDATE` (EVT-140 block) as value-level event-type strings passed to the FROZEN `record_event`; (5) the additive entitlement permissions `reference.currency.view/edit`, `reference.rating_scale.view/edit`, `reference.calendar.view`; (6) thin `POST`/`GET` endpoints in `irp_backend/api/reference*`; (7) per-tenant **MANUAL** `data_source` origin lineage on every write; (8) OPTIONAL generic DQ (`not_null` / `allowed_values`) where a rule is configured; (9) the test matrix; (10) the in-slice baseline-doc and control-matrix/RTM updates. **No issuer / instrument / counterparty / legal_entity / identifier_xref / corporate_action; no rating ASSIGNMENTS; no ingestion mapping; no implementation code is produced in this planning phase.**

---

## 1. Requirements included

| REQ | Owns | Entities (this slice) | CAP | Acceptance clauses bound here | RTM transition |
|---|---|---|---|---|---|
| **REQ-SMR-005** (minted P1B-0, new) | currency (ENT-005) + rating_scale/grade **taxonomy** (ENT-007 EV split) | `currency`, `rating_scale` (+ `rating_grade`) | CAP-2.5b | seeded global; tenant-overridable; effective-dated; audited; lineage-rooted | `Ratified (P1B-0, new)` → `In-Progress (P1B-1)` |
| **REQ-SMR-004** (calendar portion only) | calendar (ENT-006) | `calendar` (+ `calendar_holiday`) | CAP-2.5a | calendar reference entity + holidays only | `Ratified (P1B-0, calendar partial)` → `In-Progress (P1B-1, calendar partial)` |

**Clause → deliverable → test binding (acceptance is provably mapped):**
- **seeded global** → SYSTEM_TENANT seed under SYSTEM context (migration 0009 or service-under-system) + no-context hybrid-read test returns only the global slice.
- **tenant-overridable** → `UNIQUE(tenant_id, code)` tenant row shadows global + application-layer `DISTINCT ON (code)` tenant-wins dedup test.
- **effective-dated** → `EffectiveDatedMixin` (`valid_from` / `valid_to`) supersede test + `__temporal_class__ = EFFECTIVE_DATED` declaration test.
- **audited** → `REFERENCE.CREATE` / `REFERENCE.UPDATE` (EVT-140/141) emitted co-transactionally; literal-code CTRL-012 assertion.
- **lineage-rooted** → origin edge `data_source(MANUAL) → entity` via `record_lineage` + `assert_has_lineage` in the row's own tenant context.

**ISO-4217 note (CTRL-004, not runtime validation).** `currency.code` being ISO-4217 alpha-3 is a **data-dictionary / field-shape obligation** documented under CTRL-004 (`String(3)`), NOT a runtime allowed-values gate forced on every write in P1B-1.

**Net-new this slice (not inherited freebies).** `REFERENCE.*` activation and the per-tenant MANUAL `data_source` origin edge do **not** exist yet; both are first-class acceptance-mapped deliverables with their own tests (PRD-04, AUD-1, LDQ-1).

---

## 2. Requirements excluded

**Deferred within SMR (do NOT appear in any P1B-1 entity / endpoint / migration / test):**
- **rating ASSIGNMENTS** (the FR half of ENT-007 — rating-to-instrument/issuer linkage, as-of, outlook, watch). Deferred to the credit phase. `rating_scale` / `rating_grade` are **EV taxonomy only**.
- **corporate_action** (REQ-SMR-004, ENT-008) → **P1B-4**.
- **QS-10/11 day-count / roll math** ("calendars drive rolls" clause of REQ-SMR-004) → P1C+.
- `reference.rating.*` permission is **RESERVED, not minted** (future FR assignment domain, OD-P1B-F).

**Other SMR slices (excluded):** `legal_entity`, `issuer`, `counterparty` (REQ-SMR-002 / P1B-2); `instrument`, `instrument_terms`, `identifier_xref` (REQ-SMR-001/003 / P1B-3).

**P1C/P2+ and platform (excluded):** portfolio, positions, valuations, market prices, market-data / private-asset ingestion, GP-report parsing, risk calculations, exposure aggregation, limits, breach workflow, dashboards, reporting, real SSO. `data_source` is **NOT hybrid**; ingestion staging→canonical mapping is OPTIONAL **P1B-5**, not P1B-1.

**Done eligibility.** REQ-SMR-005 reaches **Done** only when all five acceptance clauses are test-proven AND a representative global slice is seeded (see OQ-P1B1-001); otherwise it stays In-Progress. REQ-SMR-004 stays **In-Progress (partial)** regardless, pending P1B-4 + roll math.

---

## 3. Proposed entities

All five tables: ORM in NEW `irp_shared/reference/models.py`; registered in `irp_shared/models.py` aggregator (`Currency`, `Calendar`, `CalendarHoliday`, `RatingScale`, `RatingGrade` + `__all__`). All carry `TenantMixin` (indexed `tenant_id`). All five are in the **closed hybrid set** with the asymmetric RLS policy (§10). **No append-only trigger / no ORM mutation guard on any of the five** (all EV-mutable, like `model`). `UNIQUE(tenant_id, code)` — **never `UNIQUE(code)`**. GUID columns = `postgresql.UUID(as_uuid=False)`; temporal/timestamp columns = `DateTime(timezone=True)`; `calendar_holiday.holiday_date` = `sa.Date()` (first Date column in the schema; DM-N-05). Migration column order mirrors the `model` EV sequence: `id, tenant_id, valid_from, valid_to, created_at, created_by, updated_at, updated_by, record_version, <domain cols>`.

### 3.1 `currency` (ENT-005, EV) — head, no child
Mixins: `PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base`; `__temporal_class__ = TemporalClass.EFFECTIVE_DATED`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `code` | String(3) | NO | ISO-4217 alpha-3 (CTRL-004 field-shape) |
| `name` | String(255) | NO | |
| `symbol` | String(8) | YES | multi-codepoint symbol |
| `minor_units` | Integer | YES | e.g. 2=USD, 0=JPY (DM-N-04 monetary rounding) |
| `numeric_code` | String(3) | YES | optional ISO-4217 numeric (deferred-populate) |
| `is_active` | Boolean | NO | default True |
| `record_version` | Integer | NO | default 1 (EV system-time aspect) |

Constraints: `UniqueConstraint('tenant_id','code', name='uq_currency_tenant_code')`; `pk_currency`; `ix_currency_tenant_id`.

### 3.2 `calendar` (ENT-006, EV) — head
Same mixin stack + `record_version`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `code` | String(50) | NO | |
| `name` | String(255) | NO | |
| `mic` | String(10) | YES | ISO-10383 MIC tag, plain string, **no FK / no enum** |
| `is_active` | Boolean | NO | default True |
| `record_version` | Integer | NO | default 1 |

Constraints: `uq_calendar_tenant_code`; `pk_calendar`; `ix_calendar_tenant_id`.

### 3.3 `calendar_holiday` (child of `calendar`, EV-mutable, NOT append-only)
Mixins: `PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base`; `__temporal_class__ = EFFECTIVE_DATED`. Carries `record_version`. Tenant-scoped; hybrid (own policy — §10). Child `tenant_id` server-stamped from the RLS-resolved parent (the `register_model_version` precedent; cross-tenant parent → not-visible fail-closed). No per-holiday EV history independent of the head (OD-DA-4).

| Column | Type | Null | Notes |
|---|---|---|---|
| `calendar_id` | GUID | NO | FK → `calendar.id` (intra-context) |
| `holiday_date` | Date | NO | **`sa.Date`**, business date (DM-N-05) |
| `name` | String(255) | YES | |
| `recurrence` | String(20) | YES | controlled-vocab string, value-level; **stored only — NO recurrence-expansion logic** (OQ-P1B1-002) |
| `record_version` | Integer | NO | default 1 |

Constraints: `fk_calendar_holiday_calendar_id_calendar`; `UniqueConstraint('tenant_id','calendar_id','holiday_date', name='uq_calendar_holiday_calendar_date')`; `ix_calendar_holiday_tenant_id`; `ix_calendar_holiday_calendar_id`.

### 3.4 `rating_scale` (ENT-007 **taxonomy only**, EV) — head
Same mixin stack + `record_version`. **ZERO assignment columns** (no `instrument_id` / `issuer_id` / `rated_entity` / `as_of` / `outlook` / `watch`).

| Column | Type | Null | Notes |
|---|---|---|---|
| `code` | String(50) | NO | |
| `name` | String(255) | NO | |
| `agency` | String(100) | YES | SP/MOODYS/FITCH/INTERNAL — plain string, **no enum / no FK** |
| `is_active` | Boolean | NO | default True |
| `record_version` | Integer | NO | default 1 |

Constraints: `uq_rating_scale_tenant_code`; `pk_rating_scale`; `ix_rating_scale_tenant_id`.

### 3.5 `rating_grade` (child of `rating_scale`, EV-mutable, NOT append-only)
Mixins as the child above; `__temporal_class__ = EFFECTIVE_DATED`; `record_version`. Tenant-scoped, hybrid; `tenant_id` server-stamped from the resolved parent. **Only parent FK is `rating_scale_id`** — no rated-entity FK (scope fence).

| Column | Type | Null | Notes |
|---|---|---|---|
| `rating_scale_id` | GUID | NO | FK → `rating_scale.id` (intra-context) |
| `code` | String(20) | NO | grade symbol (AAA/Aaa/BBB-) |
| `rank` | Integer | NO | ordinal (lower=stronger by convention; documented, not enforced beyond uniqueness) |
| `description` | String(500) | YES | |
| `record_version` | Integer | NO | default 1 |

Constraints: `fk_rating_grade_rating_scale_id_rating_scale`; **TWO uniques** — `UniqueConstraint('tenant_id','rating_scale_id','code', name='uq_rating_grade_scale_code')` AND `UniqueConstraint('tenant_id','rating_scale_id','rank', name='uq_rating_grade_scale_rank')` (deterministic ordering, OQ-P1B1-003); `ix_rating_grade_tenant_id`; `ix_rating_grade_rating_scale_id`.

**Open-vocab genericity rule (MG-01 / `source_type` precedent).** Every open-vocabulary attribute (`agency`, `mic`, `recurrence`, `numeric_code`) is a plain `String` — no enum, no CHECK, no lookup table — so new agencies/markets are value-level additions with no schema churn.

---

## 4. Temporal classifications

- **All five tables are EV** — `__temporal_class__ = TemporalClass.EFFECTIVE_DATED`. Heads use `EffectiveDatedMixin` (`valid_from`/`valid_to`, mutable config head) + explicit `record_version`. Children version implicitly with the parent head's `record_version` (no independent per-child effective-dating in P1B-1).
- **No IA / FR variant.** `irp_prevent_mutation` is **NOT** attached to any of the five, and no APPEND_ONLY_TABLES entry is created. A `REFERENCE.UPDATE` must succeed at the DB; an EV-mutability test documents this (mirror `test_rule_is_mutable_at_db`).
- **rating ASSIGNMENTS are FR and DEFERRED** — explicitly NOT in P1B-1. `rating_scale`/`rating_grade` declare EV, never FR; a scope-fence test asserts `__temporal_class__ == EFFECTIVE_DATED` and that no FR mixin or rated-entity column exists.
- An effective-dated **supersede** of a head (new `valid_from` config) is modeled as a **`REFERENCE.UPDATE`** of the same logical entity (stable `entity_id` per `(tenant_id, code)`), NOT a new CREATE, and NOT a `REFERENCE.CORRECTION` (OQ resolution in §8 / OD-AUD-3).

---

## 5. Hybrid tenancy behavior (AD-013-R1)

- **Closed hybrid set = {currency, calendar, rating_scale}** + their owned children (`calendar_holiday`, `rating_grade`). **Proprietary entities are NEVER SYSTEM_TENANT / NEVER hybrid.** `data_source` is **NOT hybrid** (stays symmetric).
- A **global** row carries `tenant_id = SYSTEM_TENANT_ID` (`00000000-0000-0000-0000-000000000001`); a **tenant override** carries `tenant_id = <tenant>`. Both with the same `code` coexist because they differ in `tenant_id` and satisfy `UNIQUE(tenant_id, code)`. **`UNIQUE(code)` must never appear** — it would collapse the override pattern.
- **"Tenant row wins" is APPLICATION-LAYER read dedup, NOT an RLS merge.** RLS `USING` returns the **union** (own + SYSTEM). The reference service read path applies `SELECT DISTINCT ON (code) ... ORDER BY code, (tenant_id = :acting_tenant) DESC` so the own-tenant row is preferred over the SYSTEM row. **No dedup logic in the policy.** (Postgres-specific `DISTINCT ON`; a SQLite-local equivalent is used in logic tests.)
- **Override semantics = full replacement at the head level.** A tenant override is a complete tenant-owned `calendar`/`rating_scale` (same `code`) WITH its own full child set under the tenant's `tenant_id`. Per-grade / per-holiday patching onto a SYSTEM head is impossible by design (child `WITH CHECK` is single-tenant) and avoids partial-merge ambiguity (OD-SEC-4 / OD-DA-2).

---

## 6. SYSTEM_TENANT behavior

- **Global seeds are written under SYSTEM context** — `set_config('app.current_tenant', SYSTEM_TENANT_ID, local=true)` (the migration-0002 `_set_system_tenant()` helper), **never** under the BYPASSRLS ops role. This exercises the same `WITH CHECK` path the constrained `irp_app` role uses (a system-context write of a SYSTEM row succeeds; the same insert under a tenant context fails `WITH CHECK` → SQLSTATE 42501).
- Global SYSTEM rows are **readable by every tenant** (the asymmetric `USING` disjunct) but **writable only under system context**.
- Global seeds get a **SYSTEM_TENANT MANUAL `data_source`** + an origin lineage edge under system context, and emit **`REFERENCE.CREATE` on the SYSTEM chain** (`chain_id = SYSTEM_TENANT_ID`), so the global reference set is itself audited and lineage-rooted (OD-AUD-4). Any in-migration seed must go through the same governed `register_*` utility under SYSTEM context — **not a raw INSERT** — so the event + edge are produced (OQ-P1B1-005).

---

## 7. APIs

Thin endpoints in `irp_backend/api/reference.py` (single file mounting three routers / sub-prefixes; split per-entity only if it exceeds ~250 lines — OD-ARCH-A). Mirror `api/models.py` exactly.

| Method + path | Permission (deny-by-default) | Behavior |
|---|---|---|
| `POST /reference/currencies` | `reference.currency.edit` | governed create (+ no children) |
| `GET /reference/currencies` | `reference.currency.view` | list, `DISTINCT ON (code)` tenant-wins dedup |
| `GET /reference/currencies/{id}` | `reference.currency.view` | detail |
| `POST /reference/calendars` | `reference.calendar.edit` (exists) | governed create + holiday children via parent write |
| `GET /reference/calendars` `(/{id})` | `reference.calendar.view` (new) | list (deduped) / detail with holidays |
| `POST /reference/rating-scales` | `reference.rating_scale.edit` | governed create + grade children via parent write |
| `GET /reference/rating-scales` `(/{id})` | `reference.rating_scale.view` | list (deduped) / detail with grades |

Invariants (copied from `api/models.py`): `require_permission(...)` module-level singletons; `get_tenant_session` sets context; **`tenant_id` server-stamped from the principal — never from the body** (a forged value is ignored and backstopped by RLS `WITH CHECK`); single end-of-request `db.commit()`; **indistinguishable 404** on cross-tenant/unknown id; **422** on malformed UUID path param before any DB hit. **No PUT/DELETE/bulk/search/resolve.** Child rows are written via the **parent governed write** (the assumptions/limitations precedent), never standalone CRUD.

---

## 8. Audit events (ACTIVATE REFERENCE.CREATE / .UPDATE)

- **Mint two module constants** in `irp_shared/reference/service.py`: `REFERENCE_CREATE_EVENT = "REFERENCE.CREATE"`, `REFERENCE_UPDATE_EVENT = "REFERENCE.UPDATE"` (mirroring `INGEST_EVENT='DATA.INGEST'` / `SOURCE_REGISTER_EVENT`). There is no central event enum; "activation" = first emission of these constants. **`apps/.../audit/service.py` is FROZEN — call `record_event`, do not modify it.**
- **EVT allocation (R-07 sign-off in the taxonomy doc):** `REFERENCE.CREATE = EVT-140`, `REFERENCE.UPDATE = EVT-141`; `REFERENCE.CORRECTION = EVT-142`, `REFERENCE.STATUS_CHANGE = EVT-143` remain **reserved, not emitted** (OQ-P1B1 / OD-AUD-1). 10-wide block, collision-free.
- **Emission shape** (the `register_data_source` body, no mid-call commit, fail-closed AUD-04): `session.add → flush → record_lineage(...) → record_event(REFERENCE.*) → return`. `source_module='reference'`, `actor_type='user'`, `actor_id` from the principal. `action='create'` on CREATE, `action='update'` on each effective-dated head update (lowercase-verb convention).
- **`entity_type`** is the literal table name (`'currency'` | `'calendar'` | `'rating_scale'`); `entity_id` = the parent row id.
- **Children fold into the parent event** (the MODEL.VERSION / DATA.INGEST precedent): `calendar_holiday` / `rating_grade` get **no own event_type**. A negative test asserts child create/replace emits zero extra audit events.
- **`before_value`/`after_value` are DC-2 metadata only**: CREATE `after_value` = identifying/controlled-vocab fields (`{code, name, is_active}` + per-entity `{minor_units}` / `{mic}` / `{agency}`); UPDATE `before`/`after` = diffed changed keys only (the `update_data_source` diff pattern). **Never serialize full rows, full child collections, or raw client input.** `is_active` flips ride on `REFERENCE.UPDATE` (no `STATUS_CHANGE` in P1B-1).
- **Per-tenant + SYSTEM_TENANT chains.** `record_event` keys `chain_id = tenant_id` unconditionally — **no chain logic change needed**. SYSTEM seeds land on `chain_id = SYSTEM_TENANT_ID`; tenant/override writes on `chain_id = tenant_id`. Both are independently `verify_chain`-able.
- **Do NOT** emit `REFERENCE.CORRECTION` / `REFERENCE.STATUS_CHANGE`, and **do NOT** introduce or reuse generic `DATA.CREATE`/`DATA.UPDATE` for reference CRUD.

---

## 9. Entitlement checks

- **Additive only** to `irp_shared/entitlement/bootstrap.py` PERMISSIONS (append five tuples; no edit/reorder/removal of existing rows; `reference.calendar.edit` already exists at line 38 and is **not re-added**):
  - `reference.currency.view`, `reference.currency.edit`
  - `reference.rating_scale.view`, `reference.rating_scale.edit`
  - `reference.calendar.view`
- **Grants (least-privilege, no role-template churn beyond grants):** `.edit` perms → `data_steward`; `.view` perms → `data_steward` and the view-tier roles (`risk_analyst_1l` / `risk_manager_2l` / `auditor_3l`) following the existing `reference.*.view` grant pattern; `platform_admin` auto-includes all via `list(ALL_CODES)`.
- **`reference.rating.*` is RESERVED — do NOT mint** (future FR assignment domain, OD-P1B-F).
- **Deny-by-default (CTRL-011):** every GET needs a real `.view`; a principal lacking `reference.currency.edit` is denied `POST /reference/currencies`.
- **Seeding the new permission/role_permission rows.** Because migration 0002 already ran, the new rows are materialized either by the additive bootstrap catalog edit re-applied by CI's fresh `alembic upgrade head`, or by a deterministic data-only **0009** reusing `permission_id` / `role_permission_id` / `_set_system_tenant`. (See OQ-P1B1-005 for the seed-mechanism decision; either way deterministic `uuid5`, additive, SYSTEM-context for `role_permission`.) A bootstrap unit test asserts the new codes present and `reference.rating.*` absent.

---

## 10. RLS behavior (asymmetric hybrid policy — net-new)

**A SECOND, NAMED hybrid loop in migration 0008, DISTINCT from the shipped symmetric loop.** The symmetric loop (0001/0004/0005/0007) is `USING (...) WITH CHECK (same)` — it is **NOT touched and NOT reused** for these tables. Define `HYBRID_TABLES = ('currency','calendar','calendar_holiday','rating_scale','rating_grade')` and a named helper emitting, per table `t`:

```
ALTER TABLE t ENABLE ROW LEVEL SECURITY;
ALTER TABLE t FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_t ON t
  USING (tenant_id::text = current_setting('app.current_tenant', true)
         OR tenant_id::text = '00000000-0000-0000-0000-000000000001')
  WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true));
```

- **`USING` = own-tenant OR SYSTEM_TENANT** (reads see own + global). **`WITH CHECK` = single-tenant only** (no SYSTEM disjunct), so a tenant session can SELECT but cannot INSERT/UPDATE a SYSTEM row → SQLSTATE **42501**. **The SYSTEM_TENANT literal must NEVER leak into `WITH CHECK`** (would let any tenant overwrite global vocabularies — a cross-tenant breach) and **must NEVER be omitted from `USING`** (would collapse hybrid to plain isolation).
- **SYSTEM_TENANT_ID injected as a Python-side f-string** from `bootstrap.SYSTEM_TENANT_ID` (one source of truth → a stable literal in the emitted SQL). No runtime GUC/function (keeps the policy plannable and auditable — OD-SEC-2).
- **Children get their own identical hybrid policy + own FORCE RLS + own `tenant_id`.** RLS is per-table; an unpoliced child is a cross-tenant leak. A SYSTEM head's children must be readable in tenant context, so children are in `HYBRID_TABLES`.
- **No-context read caveat (accepted, must be tested).** With no `app.current_tenant`, `current_setting(...,true)` returns `''`; the own-tenant clause is false but the SYSTEM clause is true → the query returns **only the global slice** (zero tenant rows). This differs from symmetric tables (which return zero rows with no context). No-context **writes** still fail `WITH CHECK` → 42501.
- **Policy name kept as `tenant_isolation_<t>`** (downgrade symmetry); the asymmetry is asserted structurally by a `pg_policies` introspection test (`with_check` must NOT contain the SYSTEM literal; `qual` MUST), and a closed-set test asserts the hybrid `qual` exists on **only** these five tables (proprietary-never-hybrid invariant, SEC-RLS-08).
- Keep `revision='0008_reference_data'`, `down_revision='0007_generic_ingestion_staging'`. Native-uuid trap applies to PG tests (ORM/GUID inserts; `CAST(:x AS uuid)` raw by-id; `str()` raw uuid reads).

---

## 11. Lineage behavior (OD-P1B-I)

- **One ORIGIN edge per reference entity at the PARENT level** (no per-child lineage). Each write calls `record_lineage(session, source=<MANUAL data_source>, target_entity_type=<'currency'|'calendar'|'rating_scale'>, target_entity_id=<row id>, edge_kind=EDGE_KIND_ORIGIN)` **co-transactionally, in the SAME tenant context as the row**. `record_lineage` resolves the source through the RLS-scoped session and stamps `edge.tenant_id` from the resolved source; a cross-tenant source id → `DataSourceNotVisible` (fail-closed).
- **Tenant/override writes use the TENANT's own MANUAL `data_source`** (edge.tenant_id = tenant); **SYSTEM global seeds use the SYSTEM_TENANT MANUAL source under system context** (edge.tenant_id = SYSTEM). `data_source` is **NOT hybrid** (symmetric policy unchanged); `source_type='MANUAL'` is a **value-level vocab addition (no schema change)**.
- **MANUAL source seeding home (LDQ-1, the one high finding).** A MANUAL `data_source` does not exist yet, and `record_lineage` fails closed without it. The reference service provides a **lazy `ensure_manual_source(session, tenant_id, actor_id)`** helper (recommended over eager) that idempotently resolves-or-registers the tenant's MANUAL source via `register_data_source` before the first reference write; the SYSTEM seed path ensures the SYSTEM MANUAL source under system context.
- The generic create core records the edge then does **not** re-assert in the hot path (matches ingestion); a test asserts every created reference row has exactly one ORIGIN edge from a MANUAL source (`assert_has_lineage` remains available to downstream consumers — OD-ARCH-D).

---

## 12. Data quality behavior

- **Generic only, optional, where configured.** Reuse the P1A-3 rail (`run_quality_check` with the two generic evaluators `not_null` / `allowed_values`; `assert_passed_quality_checks` gate). **DQ is NOT forced on every reference write**, and **no domain-specific currency/rating rules** are introduced (OD-P1B-I).
- Where a rule is explicitly configured (e.g. `not_null` on `code`), the generic evaluator runs at entry; otherwise the write proceeds without DQ. Whether to wire `not_null(code)` by default on create is OQ-P1B1-006 (recommend: yes for `code` only, as a cheap generic guard; no allowed_values vocab gates).

---

## 13. Ingestion usage

**NONE.** P1B-1 is **direct governed CRUD only**. The P1A-4 staging→canonical mapping is the OPTIONAL **P1B-5** slice. The `irp_shared.reference` package **must not import `irp_shared.ingestion`**, and nothing in ingestion imports reference. No `ingestion_batch_id` is bound on any P1B-1 reference row.

---

## 14. Tests

**Logic (SQLite-local):**
- Generic create/update core: row persisted, `record_version` bump on update, EV mutability (head update succeeds — mirror `test_rule_is_mutable_at_db`).
- `REFERENCE.CREATE`/`.UPDATE` emitted with **literal code strings** asserted (CTRL-012; catches a rename) + correct `entity_type`/`action`.
- Child fold-in: holiday/grade create emits **zero extra** audit events (mirror `test_assumptions_limitations_emit_no_extra_event`).
- Override dedup: `DISTINCT ON (code)` tenant-wins read returns exactly the tenant row when a tenant + SYSTEM row share a `code`.
- Lineage: exactly one ORIGIN edge from a MANUAL `data_source` per created entity; `assert_has_lineage` passes.
- Fail-closed (AUD-04 / CTRL-032): monkeypatch `record_event` to raise → the reference row, its children, AND the lineage edge all roll back (no orphan).

**Endpoint:** deny-by-default (missing `.edit` → denied POST; missing `.view` → denied GET); server-stamped tenant (forged body `tenant_id` ignored); indistinguishable 404 (cross-tenant/unknown); 422 on malformed UUID; child rows written via parent write.

**PG (constrained `irp_app` role, native-uuid trap):**
- Hybrid read both arms: (a) tenant sees own + SYSTEM rows; (b) tenant CANNOT write a SYSTEM_TENANT row (`WITH CHECK` → 42501); (c) **no-context read returns only the global slice** (a known tenant override row absent); (d) cross-tenant tenant-override row hidden.
- **Structural asymmetry**: `pg_policies` introspection — `with_check` lacks the SYSTEM literal, `qual` contains it; the hybrid `qual` exists on **only** the five tables (closed-set / proprietary-never-hybrid).
- **Child RLS**: SYSTEM head's children readable in tenant context; other-tenant child invisible; child SYSTEM-write rejected under tenant context.
- **Forged tenant_id**: under tenant A, insert with `tenant_id=B` and `tenant_id=SYSTEM` → both 42501.
- **SYSTEM seed under system context succeeds; same insert under tenant context fails** (no BYPASSRLS anywhere).
- **Dual-chain**: seed a global currency under SYSTEM + a tenant override of the same code → two distinct `chain_id`s; `verify_chain(SYSTEM_TENANT_ID).ok` and `verify_chain(tenant_id).ok` both True; `assert_has_lineage(tenant_id=SYSTEM_TENANT_ID)` for the seeded global.
- EV-mutable (no `irp_prevent_mutation` on the five): a `REFERENCE.UPDATE` succeeds at the DB.

**Import-direction (static text scanner, copied from `test_ingestion.py`):** `irp_shared.reference` imports only from `lineage`, `dq`, `audit`, `entitlement`, `db`, `temporal`; forbid `irp_backend`, `irp_shared.models` (plural aggregator), `irp_shared.ingestion`, and any risk/portfolio/reporting module; assert the rails (`dq`/`lineage`/`audit`) do NOT import `reference` back.

**Scope-fence (negative) tests:** exactly five new tables in 0008 (enumerated); no `legal_entity`/`issuer`/`counterparty`/`instrument`/`instrument_terms`/`identifier_xref`/`corporate_action` object; `rating_scale`/`rating_grade` declare EV and carry no rated-entity FK/as-of column; `reference.rating.*` absent from the catalog; bootstrap diff is append-only.

**CI:** add a **reference RLS PG step** (mirror the model/dq/ingestion `*_pg.py` steps) to `ci.yml` running the new hybrid-RLS matrix under the constrained role; the `alembic check` drift gate covers 0008.

---

## 15. Acceptance criteria

1. **Three EV reference vocabularies exist** (`currency`, `calendar`+`calendar_holiday`, `rating_scale`+`rating_grade`) as the five tables in migration 0008, all `__temporal_class__ = EFFECTIVE_DATED`, `UNIQUE(tenant_id, code)`, no append-only trigger.
2. **Seeded global** (representative slice) readable by every tenant; **no-context read returns only the global slice** (test-proven).
3. **Tenant-overridable**: a tenant row of the same `code` shadows the global; both coexist under RLS; the governed read returns exactly the tenant row (`DISTINCT ON (code)` tenant-wins).
4. **Tenant-isolated writes**: a tenant cannot write a SYSTEM_TENANT row (42501); a forged `tenant_id` is ignored by the service and rejected by `WITH CHECK`.
5. **Audited**: every write emits `REFERENCE.CREATE`/`.UPDATE` (EVT-140/141) co-transactionally, fail-closed; children fold into the parent event; SYSTEM seeds audit on the SYSTEM chain; `verify_chain` green on both chains.
6. **Lineage-rooted**: every entity has exactly one ORIGIN edge from a MANUAL `data_source` in its own tenant context.
7. **Entitlement**: the five additive permissions exist and gate the endpoints deny-by-default; `reference.rating.*` is absent.
8. **Effective-dated supersede** of a head succeeds (EV-mutable) and emits `REFERENCE.UPDATE`.
9. **Package boundary**: import-direction test green; `make check` and `alembic check` clean; CI reference RLS step green.
10. **Scope fences hold**: only five tables; no excluded entity/permission/column; no ingestion import; no rating assignment.

---

## 16. Risks

- **First asymmetric hybrid RLS (load-bearing, SEC-RLS-01/02).** A symmetrized `WITH CHECK` is a cross-tenant integrity breach; an omitted `USING` disjunct collapses the model. **Mitigation:** pin exact policy text; structural `pg_policies` test; both-arm behavioral tests; closed-set invariant test.
- **Child-table RLS gap (SEC-RLS-02).** Assuming the parent policy protects children leaks holiday/grade rows. **Mitigation:** children in `HYBRID_TABLES` with own FORCE RLS + own policy + own tests.
- **SYSTEM seed / lineage attribution (SEC-RLS-07/09, LDQ-1).** Seeding via BYPASSRLS or without a SYSTEM MANUAL source mis-attributes the chain/edge or fails closed. **Mitigation:** seed under system context (never ops role); `ensure_manual_source`; dual-chain + SYSTEM-lineage tests.
- **Override dedup mis-specified as RLS (SEC-RLS-04).** Encoding "tenant wins" in the policy is fragile/slow. **Mitigation:** `DISTINCT ON (code)` in the service read; policy stays merge-free; coexistence + dedup tests.
- **Cycle via the plural aggregator (ARCH-3).** `reference.service` importing `irp_shared.models` (plural) creates a cycle. **Mitigation:** import concrete classes from `lineage.models`/`audit.service`/`db.*`/`temporal`; aggregator imports reference one-way; import-direction test.
- **Scope creep into rating ASSIGNMENTS / corporate_action / roll math.** **Mitigation:** explicit negative scope-fence tests.

---

## 17. Open decisions

| ID | Question | Recommendation |
|---|---|---|
| OQ-P1B1-001 | Does P1B-1 actually SEED a global SYSTEM_TENANT slice, or ship mechanism + CRUD only? | **Seed a minimal representative slice** (enough ISO-4217 codes + one agency rating scale + one market calendar) so seeded-global / tenant-overridable / no-context-read clauses are end-to-end test-provable; defer comprehensive catalogs to a data-population follow-up. Mechanism-only keeps REQ-SMR-005 at In-Progress. |
| OQ-P1B1-002 | `calendar_holiday.recurrence` depth — stored tag vs expansion logic? | **Store the controlled-vocab string only; NO recurrence-expansion logic** in P1B-1 (expansion implies roll/day-count math, deferred). |
| OQ-P1B1-003 | Does `rating_grade` need an explicit `(rating_scale_id, rank)` unique, or is rank advisory? | **Enforce `uq_rating_grade_scale_rank`** — a non-unique ordinal makes the scale non-deterministically orderable; cheap correctness, no FR-assignment impact. |
| OQ-P1B1-004 | Are children (`calendar_holiday`, `rating_grade`) hybrid or tenant-only? | **Hybrid** — include in `HYBRID_TABLES`; a global head is useless if its children aren't readable cross-context. Children of EV heads, not IA. |
| OQ-P1B1-005 | Where do SYSTEM_TENANT global seeds (and the new permission rows) live — migration 0008, a data-only 0009, or service-under-system post-migrate? | **Keep 0008 DDL drift-clean; seed via a data-only 0009 (deterministic `uuid5`) OR the reference service under SYSTEM context**, either way honoring OD-P1B-I (SYSTEM MANUAL source + origin lineage + `REFERENCE.CREATE`) — never a raw INSERT that bypasses the lineage/audit contract. Permission rows are additive `uuid5` under SYSTEM context. |
| OQ-P1B1-006 | Generic DQ on create — wire `not_null(code)` by default, or leave DQ fully optional? | **Optional by default; if any rule is wired, only `not_null` on `code`** as a cheap generic guard. No `allowed_values` vocab gates; no domain-specific rules. |
| OQ-P1B1-007 | `currency` column set — include `minor_units` / `numeric_code`? | **Include `minor_units` (nullable)** for future DM-N-04 monetary rounding; keep `numeric_code` nullable/deferred-populate; `symbol` nullable. |
| OQ-P1B1-008 | Endpoint file layout — one `api/reference.py` or three files? | **One `api/reference.py`** mounting three routers; split only if it exceeds ~250 lines. |

---

## 18. Controls impacted

| Control | Impact in P1B-1 |
|---|---|
| **CTRL-003** (matrix label = model-inventory, not tenant-isolation) | **Do NOT edit CTRL-003 for tenant isolation.** Flag the label discrepancy to R-10; attribute tenant-isolation/RLS evidence to **CTRL-011**. |
| **CTRL-004** (data-dictionary field definition — Preventive/Manual) | Moves toward Designed via the REQ-SMR-004/005 field definitions (ISO-4217 `code` shape, MIC, agency, minor_units, etc.). |
| **CTRL-005 / 012 / 017** (audit coverage) | Extended by `REFERENCE.CREATE`/`.UPDATE` on the three hybrid EV entities (children fold in). **CTRL-017 coverage for these EV entities = the `__temporal_class__ = EFFECTIVE_DATED` declaration test, NOT append-only** (EV, not IA). |
| **CTRL-011** (deny-by-default + tenant isolation) | Extended by the new reference permissions AND by the **first asymmetric hybrid RLS** evidence (own+SYSTEM read; single-tenant write; no-context-global). |
| **CTRL-032** (failed audit blocks governed change, AUD-04) | First reference-CRUD fail-closed evidence (parent + children + lineage edge roll back together) moves it toward Implemented for the reference domain. |

This slice is the **first hybrid-RLS evidence** in the platform.

---

## 19. Documentation updates (in-slice deliverables, gated in the same PR — DoD D19)

- **`audit_event_taxonomy.md`** §3: flip the REFERENCE row from "Reserved … NOT yet emitted" to **"REFERENCE.CREATE (EVT-140) / REFERENCE.UPDATE (EVT-141) ACTIVATED in P1B-1 for currency/calendar/rating_scale governed CRUD"**; record R-07 EVT confirmation inline; restate DC-2 metadata-only and child-fold-in; `.CORRECTION`/`.STATUS_CHANGE` remain reserved.
- **`control_matrix_skeleton.md`** §3/§4: P1B-1 additions paragraph (CTRL-004/005/011/012/017/032 as §18); attribute RLS to CTRL-011; flag the CTRL-003 mis-seed to R-10 (do not silently edit).
- **RTM** (`requirements_traceability_matrix.md`): REQ-SMR-005 → In-Progress (P1B-1); REQ-SMR-004 → In-Progress (calendar partial); bind each acceptance clause to its test.
- **`entitlement_sod_model.md`**: record the five additive permissions + grants; `reference.rating.*` reserved.
- **`canonical_data_model_standard.md`** ENT-005/006/007 + **`temporal_reproducibility_standard.md`** §2A: annotate the ENT-007 EV-taxonomy / FR-assignment split (assignments deferred); ENT-005/006 EV reference entities.
- **`ci_enforcement_overview.md` + `ci.yml`**: add the reference RLS PG step.

---

## 20. Whether P1B-1 is ready to implement

**Yes — ready to implement**, contingent on confirming the open decisions (none are blockers; all have firm recommendations). Every design choice maps to a ratified P1B-0 decision (AD-013-R1, REQ-SMR-005, OD-P1B-C/E/F/H/I/J) and to a verified P1A rail: the EV-entity shape (`DataSource`/`Model`), the symmetric-vs-new-hybrid RLS loop structure (verified in 0005/0007), the co-transactional `record_event`/`record_lineage` plumbing, the `register_data_source` body, the `api/models.py` endpoint shape, the `bootstrap.py` additive-catalog pattern, and the SYSTEM-context seed helper (0002). The seven lenses converge with no unresolved conflict; the conflicts that existed (children hybrid? seed mechanism? rank uniqueness? override semantics?) are resolved decisively above. 

**Must-resolve-before-merge (not before-start):** (a) confirm OQ-P1B1-001 seed scope (drives REQ-SMR-005 Done eligibility); (b) confirm OQ-P1B1-005 seed mechanism; (c) R-07 sign-off of EVT-140/141 recorded in the taxonomy doc. **Reconciled label note:** tenant-isolation evidence attaches to CTRL-011, not the mis-seeded CTRL-003.

---

## 21. Implementation kickoff prompt (paste-ready)

> **DO NOT START until explicitly directed.** When directed, implement **P1B-1 (currency / calendar / rating_scale reference data)** per `10_delivery_backlog/p1b1_implementation_plan.md`.
>
> **Full scope (the deliverable cap — nothing beyond this):**
> 1. NEW web-framework-free package `irp_shared/reference/`: `models.py` (the 5 ORM classes), `events.py` (REFERENCE.\* string constants), `service.py` (a single generic `_create_reference`/`_update_reference` core replicating the `register_data_source` body: `add → flush → record_lineage(MANUAL source) → record_event(REFERENCE.*) → return`, no mid-call commit, fail-closed; plus a lazy `ensure_manual_source`), thin per-entity binders `currency.py`/`calendar.py`/`rating.py`, and a `bootstrap.py` seed catalog. Register all 5 models in `irp_shared/models.py` (one-way).
> 2. ONE migration **0008** (`revision='0008_reference_data'`, `down_revision='0007_generic_ingestion_staging'`) creating exactly `currency`, `calendar`, `calendar_holiday`, `rating_scale`, `rating_grade`, with NAMING_CONVENTION names (`pk_`/`ix_`/`uq_`/`fk_`), `UNIQUE(tenant_id, code)` on heads, child uniques per the plan, `sa.Date` for `holiday_date`, and a SECOND **asymmetric hybrid RLS loop** over `HYBRID_TABLES = (currency, calendar, calendar_holiday, rating_scale, rating_grade)`: `USING (own-tenant OR SYSTEM_TENANT) WITH CHECK (own-tenant only)`, SYSTEM_TENANT_ID injected as a Python f-string from `bootstrap.SYSTEM_TENANT_ID`. **No append-only trigger on any of the five.** Do NOT touch the symmetric loop or any prior migration.
> 3. The three EV entities + the two child tables exactly as specified (EV; `__temporal_class__ = EFFECTIVE_DATED`; `record_version`; open-vocab attributes as plain Strings; NO rating-assignment columns/FKs).
> 4. **Activate** `REFERENCE.CREATE = "REFERENCE.CREATE"` (EVT-140) and `REFERENCE.UPDATE = "REFERENCE.UPDATE"` (EVT-141) as constants in `reference/events.py`/`service.py`, passed to the FROZEN `record_event` co-transactionally; children fold into the parent event; before/after = DC-2 metadata only.
> 5. **Additive** entitlement permissions in `bootstrap.py`: `reference.currency.view/edit`, `reference.rating_scale.view/edit`, `reference.calendar.view` (`reference.calendar.edit` already exists — do not re-add); grant per least-privilege; **reserve `reference.rating.*` — do NOT add**; seed new permission/role_permission rows deterministically (optional 0009 or service-under-SYSTEM).
> 6. Thin endpoints in `irp_backend/api/reference.py`: `POST`/`GET` (list + `/{id}`) per entity; `require_permission` deny-by-default; `get_tenant_session`; server-stamped `tenant_id` (never from body); indistinguishable 404; 422 on bad UUID; single end-of-request commit; children via parent write; `DISTINCT ON (code)` tenant-wins dedup in the service read.
> 7. Per-tenant **MANUAL `data_source`** origin lineage on every write (`record_lineage` + `assert_has_lineage` invariant test); SYSTEM seeds under SYSTEM context with a SYSTEM_TENANT MANUAL source.
> 8. OPTIONAL generic DQ (`not_null`/`allowed_values`) only where a rule is configured — never forced; no domain-specific rules.
> 9. Tests: SQLite logic + endpoint + PG hybrid-RLS matrix (both arms, no-context-global, child RLS, forged-tenant, structural `pg_policies` asymmetry + closed-set, SYSTEM-context seed, dual-chain `verify_chain`, EV-mutability) + import-direction + override-wins + REFERENCE.\* literal-code + fail-closed rollback + negative scope-fence. Add the reference RLS step to CI.
> 10. In-slice doc updates: audit taxonomy activation, control matrix (CTRL-004/005/011/012/017/032; flag CTRL-003 to R-10), RTM (REQ-SMR-005 In-Progress, REQ-SMR-004 calendar-partial), entitlement_sod_model, canonical ENT-005/006/007 + temporal §2A, ci_enforcement_overview.
>
> **STRICT EXCLUSIONS (must NOT appear in any deliverable / entity / endpoint / test / migration):** legal_entity, issuer, counterparty, instrument, instrument_terms, identifier_xref, corporate_action; portfolio, positions, valuations, market prices, market-data ingestion, private-asset ingestion, risk calculations, exposure aggregation, reporting, dashboards, real SSO; rating ASSIGNMENTS (FR, deferred) and `reference.rating.*` permissions; QS-10/11 day-count/roll math and recurrence-expansion; P1B-2/3/4/5 work (including the staging→canonical ingestion mapping). Do NOT modify the FROZEN `apps/.../audit/service.py`, the symmetric RLS loop, or any migration 0001–0007. Do NOT make `data_source` hybrid. Do NOT encode tenant-override-wins in RLS. Do NOT use the BYPASSRLS ops role on any path. `irp_shared.reference` imports only `lineage`/`dq`/`audit`/`entitlement`/`db`/`temporal`.
>
> **Review cadence:** follow the P1A multi-lens **UltraCode** cycle — implement → multi-lens review (Product, Architect, Data, Security/RLS, Audit/Controls, Lineage/DQ, Scope) → fix in-scope findings → re-review until clean.
> **Gate:** run `make check` (lint + types + tests + `alembic check` drift gate) and the new reference RLS PG step until green.
> **Commit only on explicit approval.** Do not commit or push until the reviewers sign off and you are told to commit.

### Build-sequence subsection

1. **Models + aggregator** — author `reference/models.py` (5 EV classes, mixins, uniques, FKs); register in `irp_shared/models.py`. Verify `alembic check` sees the new metadata.
2. **Migration 0008** — DDL for the five tables (mirror the `model` column order) + the asymmetric hybrid RLS loop over `HYBRID_TABLES`; `alembic upgrade head` + `alembic check` clean.
3. **events.py + service.py** — REFERENCE.\* constants; generic create/update core; `ensure_manual_source`; lineage + audit wiring (fail-closed).
4. **Per-entity binders** — `currency.py`/`calendar.py`/`rating.py` (thin; calendar/rating handle children via the parent write).
5. **Entitlement** — additive `bootstrap.py` permissions + grants; seed path for new rows; bootstrap unit test.
6. **Endpoints** — `api/reference.py` POST/GET per entity with `DISTINCT ON (code)` read.
7. **Seeds** — minimal SYSTEM_TENANT global slice under SYSTEM context (per OQ-P1B1-001/005) with MANUAL source + lineage + REFERENCE.CREATE.
8. **Tests** — logic → endpoint → PG hybrid-RLS matrix → import-direction → scope-fence; add CI reference RLS step.
9. **Docs** — taxonomy, control matrix, RTM, entitlement_sod_model, canonical/temporal, ci_enforcement_overview.
10. **`make check` green → multi-lens review → fix in-scope → commit on approval.**
