# P1B-4 Implementation Plan — Corporate Action (Effective-Dated Reference Data)

## Document Control

| Field | Value |
|---|---|
| Slice | **P1B-4** — fourth Security Master & Reference Data slice |
| Status | **PLAN — planning only; NOT implemented.** Do not write code/migrations until explicitly approved. |
| Requirements | REQ-SMR-004 (corporate_action portion; calendar already partial from P1B-1) |
| Entity | `corporate_action` (ENT-008, **EV** effective-dated) |
| Migration | **0011_corporate_action** (`down_revision='0010_instrument'`) — the next head after P1B-3 |
| Predecessors | P1B-1 `6568cb1` (calendar + hybrid RLS), P1B-2 `32c7778` (EV proprietary symmetric RLS), P1B-3 `8545ed6` (instrument EV + FR + identifier; `resolve_instrument`) |
| Headline | The **last reference entity** of the Security-Master block — a straightforward EV slice (the P1B-2/P1B-3 EV pattern) that captures corporate actions as **effective-dated reference data with an amend/cancel-before-application status lifecycle** — **capture-only, no application/event engine** (OD-P1B-B). |
| Ratified decisions | OD-P1B-B (`corporate_action` = EV; amend/cancel-before-application; status/reason history via the `REFERENCE.*` audit trail, **not** an IA table) — ratified P1B-0 (`4fae26b`) |
| Owner / review | UltraCode multi-lens planning + 8-lens adversarial review; sign-offs OBTAINED 2026-06-24 — OQ-1 (EVT-143 activation, caller-side; audit/service.py frozen) + OQ-5 (auditor_3l excluded) (§8/§16/§19) |
| Cadence | plan → (this doc, on approval) → implement → multi-lens review → fix → `make check` + new PG RLS step → **commit only on explicit approval** |

> **Grounding (verified against the repo this turn):** ENT-008 `corporate_action` = EV (`04_data_model/canonical_data_model_standard.md`); OD-P1B-B (`10_delivery_backlog/p1b0_decision_record.md`); REQ-SMR-004 (`02_requirements/requirements_backbone.md` + RTM); EV class + ENT-008 in the EV list (`temporal_reproducibility_standard.md` §2A); the committed P1B-4 outline (`10_delivery_backlog/p1b_implementation_plan.md` §P1B-4); the EV binder pattern (`reference/issuer.py`, `reference/instrument.py` — `resolve_instrument` reusable); audit taxonomy (`audit_event_taxonomy.md` — EVT-143 `STATUS_CHANGE` still **RESERVED**; EVT-140/141 activated, EVT-142 FR-only); entitlements (`entitlement/bootstrap.py` — `reference.corporate_action.edit` exists, `.view` missing).

---

## §1. Requirements included

| REQ | Coverage in P1B-4 | Deliverable | Acceptance test |
|---|---|---|---|
| **REQ-SMR-004** Corporate actions & calendars (corporate_action portion) | **In-Progress (substantive for corporate_action).** `corporate_action` EV effective-dated reference entity; amend/cancel-before-application via EV in-place supersede; status lifecycle audited. (Calendar half already shipped P1B-1; roll/day-count math **stays deferred to P1C**.) | `corporate_action` table (mig 0011); governed CRUD + amend + status-transition binder; instrument FK. | "Actions apply on effective date" is captured as the `effective_date` reference attribute; amend/cancel-before-application proven by an EV supersede + status-transition test (no double-apply — **because there is no application logic at all**, capture-only). |

**Partial-coverage markers (carried into the RTM):** (a) REQ-SMR-004's "calendars drive rolls" (QS-10/11 day-count/roll math) **remains deferred to P1C**; (b) **issuer-level** corporate actions (not tied to a single instrument — e.g. an issuer name change) are **deferred** (§16/OQ-3, `instrument_id` is NOT-NULL in P1B-4). P1B-4 delivers the instrument-level corporate_action **reference capture** only (consistent with OD-P1B-B and the calendar-partial precedent).

---

## §2. Requirements excluded (explicit scope fence)

- **Corporate-action APPLICATION engine** — no automatic application of an action to any `instrument_terms` / position / valuation; no cash/stock entitlement calculation; no tax treatment; no event-processing/lifecycle automation. **P1B-4 is capture-only** (application logic is P1C).
- **Position / valuation adjustment**, **portfolio / positions / valuations** (P1C), **market data / pricing / risk / exposure / performance/returns**, **reporting / dashboards / real SSO** — none pulled forward.
- **Roll / day-count math** (QS-10/11) — deferred to P1C (the calendar half of REQ-SMR-004).
- **Vendor corporate-action feed integration**, **reconciliation workflow**, **manual-override workflow** — out of scope (P6/P7/P9). `source` is a provenance label only, NOT a vendor adapter.
- **A separate immutable announcement-event log** — DEFERRED (a distinct future OD per OD-P1B-B; **do NOT reclass ENT-008 to IA**).
- **Rejected alternatives:** IA append-only for `corporate_action` (rejected at P1B-0 — contradicts AD-005 §2A and forbids the legitimate amend/cancel lifecycle); a terms **JSON blob** for action economics (rejected — typed columns are queryable and DQ-checkable, matching the committed outline's "typed fields"); a separate `is_active` flag alongside `status` (rejected — the P1B-3 review's `arch-1` dual-flag lesson; `status` is the single authoritative lifecycle field).

---

## §3. Proposed entity

`corporate_action` (ENT-008, **EV**) — PROPRIETARY, tenant-scoped, SYMMETRIC RLS, **NEVER hybrid** (the P1B-2/P1B-3 model). Added to `reference/models.py`; registered in `irp_shared/models.py`. Open-vocab attributes are **plain Strings** (no enum/CHECK; MG-01).
`PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin` → `__temporal_class__ = EFFECTIVE_DATED`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | GUID PK | NO | |
| `tenant_id` | GUID | NO | indexed (TenantMixin) |
| `valid_from` / `valid_to` | DateTime(tz) | NO / YES | **EV record-versioning** window (system-time effective-dating of the *record*) — distinct from the business dates below (§4.1) |
| `created_at/by`, `updated_at/by` | — | — | TimestampMixin |
| `code` | String(150) | NO | firm-assigned corporate-action reference (the stable key) |
| `instrument_id` | GUID FK→`instrument.id` | **NO** | the affected security; intra-tenant; resolved tenant-filtered (§6). (Issuer-level actions deferred — §16/OQ-3) |
| `action_type` | String(50) | NO | controlled-vocab plain string (DIVIDEND/SPLIT/MERGER/SPINOFF/RIGHTS/CALL/COUPON/NAME_CHANGE/OTHER) |
| `status` | String(30) | NO | controlled-vocab **lifecycle** plain string, default `ANNOUNCED` (ANNOUNCED → CONFIRMED → CANCELLED) — the SINGLE lifecycle flag (no `is_active`; §5) |
| `announcement_date` | Date | YES | business date — inert reference attribute |
| `ex_date` | Date | YES | business date — inert |
| `record_date` | Date | YES | business date — inert |
| `pay_date` | Date | YES | business date — inert |
| `effective_date` | Date | YES | the business date the action applies (REQ-SMR-004 "applies on effective date") — **a stored attribute; nothing is computed/applied** |
| `ratio` | Numeric(18,8) | YES | e.g. split ratio — **inert** reference value (NO calc) |
| `amount` | Numeric(20,6) | YES | e.g. dividend/coupon amount — **inert** (NO entitlement/tax calc) |
| `currency_code` | String(3) | YES | plain ISO-4217 string (NOT a FK to the hybrid `currency` table) |
| `description` | String(500) | YES | free-text label |
| `source` | String(150) | YES | provenance hint (NOT a vendor feed/adapter) |
| `record_version` | Integer | NO | default 1; bumped on each EV in-place supersede |

**Constraints:** `UNIQUE(tenant_id, code)`; index on `tenant_id`, `instrument_id`. **NO** `is_active` column (`status` is authoritative). **NO** position/holding/valuation/entitlement/tax/applied-flag column (scope fence). **NOT** append-only — EV-mutable (no `irp_prevent_mutation` trigger; a `REFERENCE.UPDATE` must succeed at the DB).

**On `code`** (review DA-1): unlike instrument/issuer, a corporate action may lack a firm-assigned master key. `code` is the firm's corporate-action reference (its event id) where one exists; where it does not, the caller passes a stable system reference (e.g. `{instrument_code}:{action_type}:{ex_date}` or a server-generated surrogate). The `UNIQUE(tenant_id, code)` contract stands either way; multiple actions on one instrument are distinct `code`s. (No design change; documented so the natural key is justified.)

---

## §4. Temporal classification

`corporate_action` = **EV** (Effective-dated Versioned) — AD-005 §2A lists ENT-008 under EV reference/master data; OD-P1B-B ratifies it. One physical row per logical corporate action; amend/cancel = **in-place supersede** (`REFERENCE.UPDATE`, `record_version` bump); status/reason **history via the `REFERENCE.*` audit trail**, not an IA table and not an FR second axis. **No FR / no bitemberality** (that is P1B-3's `instrument_terms`); **no IA append-only trigger** (rejected at P1B-0).

### 4.1 EV record-versioning vs business dates (load-bearing — likely review point)
The EV mixin's `valid_from`/`valid_to` track the **record's** effective-dating (system-time version window). The corporate action's **business dates** (`announcement_date`/`ex_date`/`record_date`/`pay_date`/`effective_date`) are ordinary **domain Date columns** — they are NOT the EV temporal axis and carry **no computation**. "Amend/cancel-before-application" is an EV in-place supersede of these attribute columns + a `status` transition; because P1B-4 has **no application engine**, "no double-apply" holds trivially (nothing is ever applied).

---

## §5. Corporate-action lifecycle / status model
A single `status` controlled-vocab field (no separate `is_active` — the P1B-3 `arch-1` dual-flag lesson): **`ANNOUNCED` → `CONFIRMED` → `CANCELLED`** (terminal). Plain string, value-extensible.
- **create** → `status` defaults to `ANNOUNCED`; a caller-supplied initial status is **validated against the controlled-vocab status set** (an out-of-vocab value is rejected with the typed guard error — the same validation the transitions use), so an invalid status can never be persisted on the create path → `REFERENCE.CREATE`.
- **amend** (attribute change, same status — e.g. a corrected `pay_date`) → EV in-place supersede → `REFERENCE.UPDATE` (`record_version`++).
- **status transition** (`ANNOUNCED→CONFIRMED`, `→CANCELLED`) → set `status` → **`REFERENCE.STATUS_CHANGE` (EVT-143) if activated** (§8/§16-OQ-1), else `REFERENCE.UPDATE` fallback (`record_version`++).
- **cancel-before-application** = the `→CANCELLED` transition; since nothing is ever applied, cancellation is purely a reference-state change (capture-only).
A transition guard rejects illegal moves (e.g. out of `CANCELLED`) with a typed error — a thin validation, **not** a workflow/event engine.

---

## §6. Relationship to instrument
`corporate_action.instrument_id` is a **NOT-NULL** FK to the P1B-3 `instrument` (EV) head. On create/amend, `instrument_id` is resolved through the tenant-filtered **`resolve_instrument`** (reused from P1B-3) so a **cross-tenant/unknown instrument fails closed on SQLite AND PG** (`InstrumentNotVisible` pre-commit). **No `instrument_terms` linkage, no application to terms/positions/valuations** (capture-only). Issuer-level corporate actions (e.g. an issuer name change not tied to one instrument) are **deferred** (§16/OQ-3).

---

## §7. APIs (thin; bounded count)
New router `apps/backend/src/irp_backend/api/reference_corporate_actions.py` (a **fourth** `/reference` router; `reference.py`/`reference_entities.py`/`reference_instruments.py` are all untouched). All endpoints: `get_tenant_session`, `require_permission` (deny-by-default, module-level guard singletons), `uuid.UUID` path params (422 + indistinguishable 404), server-stamped `tenant_id`, single end-of-request commit.

| Method + path | Permission | Notes |
|---|---|---|
| `POST /reference/corporate-actions` | `reference.corporate_action.edit` | create (resolves `instrument_id` tenant-filtered) |
| `GET /reference/corporate-actions` | `reference.corporate_action.view` | list (tenant-scoped); optional `?instrument_id=` filter |
| `GET /reference/corporate-actions/{id}` | `reference.corporate_action.view` | detail |
| `POST /reference/corporate-actions/{id}` | `reference.corporate_action.edit` | amend / status-transition (mode in body: `amend` / `status`) |

**No** broad search, external lookup, vendor validation, application, or bulk endpoints. **No** DELETE/PUT (cancellation is a `status` transition, not a delete). **Note (review SCOPE-1):** the committed outline lists `POST/GET /reference/corporate-actions (+ /{id})`; the **`POST /{id}` (amend / status-transition)** here is a deliberate, in-scope realization of the EV amend/cancel lifecycle the outline requires (a write path is needed for "amend/cancel-before-application"), not a new domain surface — ratified alongside OQ-1/OQ-5. It carries `require_permission("reference.corporate_action.edit")`, deny-by-default.

---

## §8. Audit events
Reuse the FROZEN `audit.service.record_event` via `reference/service.py` (DC-2 metadata-only `after_value`/`before_value` — identifying + controlled-vocab fields, never raw payload). `corporate_action` emits its **own** event (not folded). Per-tenant chains; `verify_chain`.
- **create →** `REFERENCE.CREATE` (EVT-140).
- **amend (attribute change) →** `REFERENCE.UPDATE` (EVT-141), diffed before/after.
- **status transition (`ANNOUNCED→CONFIRMED→CANCELLED`) →** **`REFERENCE.STATUS_CHANGE` (EVT-143)** — see the activation decision below.

**EVT-143 activation — APPROVED 2026-06-24 (see §16/OQ-1):** `REFERENCE.STATUS_CHANGE` is today **RESERVED** (`reference/events.py`, `audit_event_taxonomy.md` — through P1B-3 "is_active flips ride on `REFERENCE.UPDATE`"); P1B-4 **activates** it for `corporate_action` status transitions — caller-side only via a NEW `record_reference_status_change` helper in `reference/service.py` (the **FROZEN** `audit/service.py` is unchanged; the same governed activation P1B-3 used for EVT-142), `before/after = {status: old→new}`, optional `justification` = a `reason`. Ordinary attribute amendments stay `REFERENCE.UPDATE`; create = `REFERENCE.CREATE`. **Fallback** (if zero new audit-code activation is preferred): status transitions ride `REFERENCE.UPDATE` with `before_value`/`after_value` isolating exactly `{status: old→new}` (+ optional `justification`), EVT-143 stays reserved — but the lifecycle is then indistinguishable from attribute edits in the audit stream. **This is the key pre-implementation governance decision (R-07 sign-off).**

The committed P1B-4 outline lists four REFERENCE events (CREATE/UPDATE/CORRECTION/STATUS_CHANGE); P1B-4 **intentionally narrows to CREATE/UPDATE + (gated) STATUS_CHANGE**: `REFERENCE.CORRECTION` (EVT-142) is **NOT** used — it is the FR `instrument_terms` as-known restatement code (P1B-3), and `corporate_action` is EV (in-place supersede = `REFERENCE.UPDATE`), so there is no as-known second axis to restate.

---

## §9. Entitlement checks (additive `bootstrap.py`)
**Already exists** (verified `bootstrap.py`): `reference.corporate_action.edit` (held by `data_steward`). **Missing → P1B-4 adds:** `reference.corporate_action.view`. `reference.rating.*` stays RESERVED.

**Grants — exact per-code target matrix** (proprietary security-master SoD, mirroring P1B-3; purely **additive** — does NOT widen any existing permission):

| Permission | Status | Recipients (target) |
|---|---|---|
| `reference.corporate_action.view` | **NEW** | `data_steward`, `risk_analyst_1l`, `risk_manager_2l` (== the `reference.instrument.view` recipient set) |
| `reference.corporate_action.edit` | exists | recipients **UNCHANGED** (`data_steward` + `platform_admin` via `ALL_CODES`) |

`auditor_3l` is **EXCLUDED** from `reference.corporate_action.view`/`.edit` (proprietary security-master SoD, consistent with P1B-2/P1B-3 — corporate actions on a firm's instruments are MNPI-adjacent) — see §16/OQ-5 (governance confirm). A bootstrap **parity test** pins the recipient sets (new `.view` == instrument.view set; `.edit` unchanged; `auditor_3l` excluded; `reference.rating.*` absent). No broad admin bypass.

---

## §10. RLS behavior
`corporate_action` is **tenant-scoped, SYMMETRIC RLS** — the P1B-2/P1B-3 loop byte-for-byte: `FORCE ROW LEVEL SECURITY`; `USING (tenant_id::text = current_setting('app.current_tenant', true)) == WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))` (the `::text` cast matches migrations 0009/0010 exactly — drift-clean). **No hybrid, no SYSTEM_TENANT, no append-only trigger, no BYPASSRLS application path.** Migration 0011 reuses the 0009/0010 symmetric loop over `("corporate_action",)`. The closed hybrid set stays **exactly** the five P1B-1 tables (`HYBRID_TABLES` unchanged; positive `pg_policies` assertion + closed-set guard test). The cross-tenant `instrument_id` guarantee is **service-predicate-only** (`resolve_instrument` raising `InstrumentNotVisible` pre-commit) — RLS `WITH CHECK` gates only the corporate_action row's own `tenant_id`, not the FK target (the P1B-3 `rls-1` lesson). PG tests run under the constrained `irp_app` role; the `app_url` fixture GRANTs `SELECT, INSERT, UPDATE, DELETE` on `corporate_action` (+ `instrument` for FK resolution) and `SELECT, INSERT` on `audit_event`; role stays `NOSUPERUSER NOBYPASSRLS`.

---

## §11. Lineage behavior
One MANUAL-`data_source` ORIGIN edge per **created** `corporate_action` row (`record_reference_create` → `ensure_manual_source` + `record_lineage` + `REFERENCE.CREATE`, reused unchanged). An EV in-place amend / status transition emits `REFERENCE.UPDATE` / `REFERENCE.STATUS_CHANGE` only — **no new lineage edge** (the row keeps its origin edge). `assert_has_lineage` is the test-side CTRL-013 check (per-row, keyed on the row id — the P1B-2/P1B-3 precedent), not a call in the create core. Per-tenant MANUAL source; no FK-driven lineage edges.

---

## §12. Data quality behavior (optional, generic only)
Generic evaluators only, where configured — the two existing rule types `NOT_NULL` / `ALLOWED_VALUES` (`dq/rules.py`): `NOT_NULL` on `corporate_action.code` / `action_type` / `instrument_id`; optional `ALLOWED_VALUES` on `action_type` / `status` / `currency_code` **only where a rule is explicitly configured**. **No** domain-specific corporate-action DQ complexity, **no** reconciliation, **no** vendor validation. A scope-fence test asserts no domain DQ rule is hard-wired.

---

## §13. Tests
**SQLite logic** (`test_reference_corporate_actions.py`):
- temporal class (EV — has `valid_from`, no `system_from`); create records lineage + `REFERENCE.CREATE` + `verify_chain`; `UNIQUE(tenant_id, code)`; create **validates a caller-supplied initial status** (out-of-vocab rejected, review SEC-5); `instrument_id` NOT-NULL; business-date attributes stored/read (effective_date/ex_date/etc. are inert columns).
- **amend** (attribute change → `REFERENCE.UPDATE`, `record_version`+1); **EV in-place supersede — single physical row** (no new row per amend; history via audit, NOT FR).
- **status transitions** (review QA-2/QA-4): enumerate the guard matrix — **legal** `ANNOUNCED→CONFIRMED`, `ANNOUNCED→CANCELLED`, `CONFIRMED→CANCELLED` (each persists the new status and bumps `record_version` by exactly 1); **illegal** any move out of `CANCELLED` (terminal) and `CONFIRMED→ANNOUNCED` (rejected with the typed guard error, no DB write).
- **EVT-143 audit — positive + fence** (review QA-1, **if OQ-1 activates EVT-143**): a transition emits **exactly one** `REFERENCE.STATUS_CHANGE` with `before/after = {status: old→new}` (+ optional `justification=reason`) and `verify_chain` stays ok; a **fence** test asserts EVT-143 is emitted ONLY for corporate_action — an `instrument`/`issuer` attribute edit in the same session emits **zero** EVT-143. The two EXISTING reservation guards (`test_reference.py` `test_reserved_events_not_emitted*`, `test_reference_entities.py` `test_reserved_events_not_emitted`) stay green **because they are entity-scoped** (they never create a corporate_action) — they are NOT broadened. **If OQ-1 takes the fallback**, the transition instead emits `REFERENCE.UPDATE` with `before/after` isolating `{status: old→new}` and EVT-143 stays at zero everywhere (review AC-2).
- **cross-tenant `instrument_id` fail-closed** — `resolve_instrument` raises `InstrumentNotVisible` **pre-commit** (`pytest.raises(...)`, NOT `IntegrityError`/42501), `rollback()` → `CorporateAction`==0 **and** `AuditEvent`==0 **and** `DataSource`==0.

**Capture-only scope-fence** (the headline fence, parallel to P1B-3's no-precedence fence): assert `corporate_action` has **NO** applied/position/valuation/entitlement/tax/`is_active` column and that **no** corporate-action effect is computed or applied to any `instrument_terms` / position / valuation (no such code path exists); `action_type`/`status` extend by value (no migration).
**Endpoint** (`test_reference_corporate_actions_endpoint.py`): deny-by-default (403), server-stamped tenant, uuid path params (422 + indistinguishable 404), create + amend + status-transition + list (+ `instrument_id` filter), cross-tenant/unknown instrument → 404; **negative (review QA-3):** an illegal transition (e.g. `CANCELLED→CONFIRMED`) returns a stable **4xx** (the typed guard error mapped, NOT a 500), and a missing/invalid `mode` returns **422**.
**PostgreSQL under `irp_app`** (`test_reference_corporate_actions_pg.py`, new CI step): tenant isolation; no-context → zero rows; cross-tenant `instrument_id` fail-closed at the **service layer** pre-commit; positive symmetric-policy + FORCE-RLS assertion; **closed-hybrid-set unchanged**; forged-write-emits-no-audit; EV-mutable (an in-place UPDATE succeeds); downgrade smoke.
**Import-direction (review ARCH-3):** the `irp_shared.reference` allowlist is **UNCHANGED** — `corporate_action.py` imports only already-allowlisted subpackages (`reference` intra-package + `db`/`temporal` via the model/`utcnow`); the existing direction test auto-covers the new file. **Scope-fence:** migrations 0001–0010 + `audit/service.py` + `HYBRID_TABLES` + the hybrid loop + the FR mixin unchanged.

---

## §14. Acceptance criteria
1. `corporate_action` modeled as **EV** effective-dated reference data (one physical row; in-place supersede; history via the `REFERENCE.*` audit trail).
2. Amend / cancel-before-application via EV supersede + a status transition; **no double-apply** (because there is **no application logic** — capture-only).
3. Status transitions are **audited** (`REFERENCE.STATUS_CHANGE` if activated, else `REFERENCE.UPDATE`); each write is lineage-rooted; fail-closed (no row ⇒ no audit ⇒ no lineage).
4. `instrument_id` is a tenant-filtered FK; cross-tenant fails closed at the service layer.
5. Tenant-isolated (symmetric RLS, FORCE RLS, no-context → zero rows); **no hybrid**; closed hybrid set still the five P1B-1 tables.
6. **No** application engine, position/valuation adjustment, entitlement/tax calc, roll math, vendor feed, reconciliation, or override workflow.
7. CI PG RLS test green; `make check` green; `alembic check` drift-clean; downgrade smoke passes.

---

## §15. Risks
- **Scope creep into an application / event-processing engine** (the biggest risk for this entity). *Mitigation:* the capture-only scope-fence test (no applied/position/valuation column; no application code path); the deferred list in §2.
- **Status lifecycle over-modeling** (workflow/state-machine creep). *Mitigation:* a thin transition guard only (illegal-move rejection), no workflow engine; `status` is a plain controlled-vocab string.
- **EV-vs-business-date confusion** (treating `effective_date`/`ex_date` as the EV temporal axis). *Mitigation:* §4.1 makes the distinction explicit; tests treat business dates as inert columns.
- **Cross-tenant instrument leakage.** *Mitigation:* the explicit-tenant-predicate `resolve_instrument` + PG `WITH CHECK` backstop + cross-tenant fail-closed tests (service-layer pre-commit).
- **EVT-143 activation governance** (a reserved code). *Mitigation:* caller-side only (audit/service.py frozen), R-07 sign-off, mirrors the proven P1B-3 EVT-142 activation; a clean fallback (REFERENCE.UPDATE) exists.

---

## §16. Open decisions (resolved with recommendation; ⚑ = needs explicit sign-off before implementation)

| # | Question | Recommendation |
|---|---|---|
| OQ-1 ✅ **APPROVED** | Activate `REFERENCE.STATUS_CHANGE` (EVT-143) for status transitions, or ride `REFERENCE.UPDATE`? | **APPROVED (2026-06-24): activate `REFERENCE.STATUS_CHANGE` / EVT-143** for corporate_action status transitions — **caller-side only via `record_reference_status_change` in `reference/service.py`; `audit/service.py` remains FROZEN.** A first-class status-lifecycle audit trail (OD-P1B-B); ordinary amendments stay `REFERENCE.UPDATE`; create = `REFERENCE.CREATE`. (The `REFERENCE.UPDATE` fallback is therefore NOT taken.) |
| OQ-2 | Single `status` field, or `status` + `is_active`? | **Single `status`** (ANNOUNCED/CONFIRMED/CANCELLED) — no `is_active` (the P1B-3 `arch-1` dual-flag lesson); CANCELLED is the inactive terminal state. |
| OQ-3 | `instrument_id` NOT NULL, or nullable (issuer-level actions)? | **NOT NULL** — instrument-level only in P1B-4; issuer-level corporate actions deferred (raise a distinct OD if needed). |
| OQ-4 | Amendment model — EV in-place supersede, or a new versioned row? | **EV in-place supersede** (one physical row; history via the `REFERENCE.*` audit) — consistent with EV (NOT FR/new-row). |
| OQ-5 ✅ **APPROVED** | `auditor_3l` access to `corporate_action.view`? | **APPROVED (2026-06-24): `auditor_3l` remains EXCLUDED** from `corporate_action.view`/`.edit` in P1B-4 (proprietary security-master SoD, consistent with P1B-2/P1B-3). |
| OQ-6 | `action_type` vocabulary breadth? | A **minimal generic controlled-vocab set** (DIVIDEND/SPLIT/MERGER/SPINOFF/RIGHTS/CALL/COUPON/NAME_CHANGE/OTHER) as plain strings, value-extensible (MG-01); type-specific validation deferred. |
| OQ-7 | Which date fields? | `announcement_date`/`ex_date`/`record_date`/`pay_date`/`effective_date` as **nullable Date columns** (inert); per-type date-requirement validation deferred. |
| OQ-8 | Terms representation — typed columns or JSON? | **Typed columns** (`ratio` Numeric + `amount` Numeric + `currency_code`) as **inert** reference fields (queryable, DQ-checkable; the committed outline's "typed fields") — NOT a JSON blob; NO entitlement/tax calc. |
| OQ-9 | A separate immutable announcement-event log? | **DEFERRED** — a distinct future OD (OD-P1B-B); do **NOT** reclass ENT-008 to IA. |
| OQ-10 | Endpoint file? | A **new `api/reference_corporate_actions.py`** (per-family cohesion; 4th `/reference` router) — `reference_instruments.py` untouched. |

---

## §17. Controls impacted
- **CTRL-004** — data dictionary / field definitions (the new entity).
- **CTRL-017** — temporal-class declaration (`corporate_action` EV `__temporal_class__` test).
- **CTRL-005 / CTRL-012** — audit coverage (`REFERENCE.CREATE`/`UPDATE` + `STATUS_CHANGE` for transitions; fail-closed; hash chain).
- **CTRL-011** — tenant isolation / entitlements (symmetric RLS; deny-by-default; proprietary SoD).
- **CTRL-013** — lineage no-bypass (origin edge per created row; `assert_has_lineage`).

---

## §18. Documentation updates (at implementation)
`04_data_model/canonical_data_model_standard.md` (ENT-008 `corporate_action` realized) · `04_data_model/temporal_reproducibility_standard.md` (§2A: corporate_action EV exercised P1B-4) · `04_data_model/audit_event_taxonomy.md` (corporate_action added to REFERENCE.* emitters; **EVT-143 `REFERENCE.STATUS_CHANGE` ACTIVATED** for corporate_action status transitions under R-07, if OQ-1 approved) · `reference/events.py` (on EVT-143 activation, flip its docstring + the `# EVT-143 (reserved)` inline comment from "reserved/NOT emitted" to "ACTIVATED P1B-4 for corporate_action status transitions"; this file is NOT frozen — review AC-1) · `entitlement_sod_model.md` (`reference.corporate_action.view/edit` grants + proprietary SoD) · `02_requirements/requirements_backbone.md` + `requirements_traceability_matrix.md` (REQ-SMR-004 corporate_action In-Progress; **tighten RTM row-40 wording** from "deferred to P1B-4/P1C" to "corporate_action capture delivered P1B-4; roll/day-count math QS-10/11 deferred to P1C" — review PR-2) · `control_matrix_skeleton.md` (CTRL-017/005/012 now exercised for corporate_action) · `ci_enforcement_overview.md` (new corporate_action symmetric-RLS PG step) · project memory at closeout.

---

## §19. Whether P1B-4 is ready to implement
**READY — both gating sign-offs OBTAINED (2026-06-24): OQ-1 APPROVED** (activate EVT-143 `REFERENCE.STATUS_CHANGE`, caller-side only; `audit/service.py` frozen) and **OQ-5 APPROVED** (auditor_3l excluded). All other patterns are **already shipped and proven**: EV governed CRUD (P1B-2/P1B-3), symmetric proprietary RLS, `resolve_instrument` (P1B-3), `REFERENCE.CREATE/UPDATE` + the caller-side activation pattern (P1B-3 EVT-142), MANUAL-source lineage, additive entitlements with parity tests. The net-new work is small (one EV table + a thin binder + the status-transition path + a new audit-code activation) — this is the **lightest** P1B slice. The 8-lens UltraCode adversarial review (this turn) findings are folded in below the kickoff. No structural change to any frozen artifact (audit/service.py, the hybrid loop, migrations 0001–0010, the FR mixin).

---

## §20. Exact implementation kickoff prompt for P1B-4 (paste-ready)

> **DO NOT START until explicitly directed.** When directed, implement **P1B-4 (`corporate_action` EV reference data)** per `10_delivery_backlog/p1b4_implementation_plan.md`.
>
> **Pre-req sign-offs — both OBTAINED (2026-06-24):** (a) **OQ-1 APPROVED** — `REFERENCE.STATUS_CHANGE` (EVT-143) is activated for corporate_action status transitions (caller-side only; `audit/service.py` frozen); (b) **OQ-5 APPROVED** — `auditor_3l` excluded from `corporate_action.view`/`.edit`.
>
> **Full scope (the deliverable cap — nothing beyond this):**
> 1. Extend `irp_shared/reference/`: add `CorporateAction` (EV) to `reference/models.py`; **register in `irp_shared/models.py` in BOTH the import block AND `__all__`** (or `create_all`/autogenerate miss the table). Add a binder `reference/corporate_action.py` (`CorporateActionNotVisible`, `resolve_corporate_action`, `create_corporate_action` — resolves `instrument_id` via the reused `resolve_instrument` tenant-filtered + validates the initial `status`; `update_corporate_action` — EV in-place amend; `transition_corporate_action_status` — the ANNOUNCED→CONFIRMED→CANCELLED guard + audit). Mirror `reference/issuer.py`/`reference/instrument.py`.
> 2. ONE migration **0011** (`revision='0011_corporate_action'`, `down_revision='0010_instrument'`) creating `corporate_action` with NAMING_CONVENTION names, the **SYMMETRIC** tenant-isolation RLS loop (reuse 0010 — **NO hybrid, NO SYSTEM_TENANT, NO append-only trigger**), `UNIQUE(tenant_id, code)`, the `instrument_id` FK, the date/numeric/string columns per §3. Do NOT touch the hybrid loop, migrations 0001–0010, or `audit/service.py`.
> 3. The entity exactly as §3 — open-vocab attributes as plain Strings; **single `status` lifecycle field (NO `is_active`)**; NO position/valuation/entitlement/tax/applied column; `currency_code` plain ISO (no FK to hybrid `currency`); `ratio`/`amount` inert Numerics.
> 4. Audit (§8): create→`REFERENCE.CREATE`; amend→`REFERENCE.UPDATE`; status transition→**`REFERENCE.STATUS_CHANGE` (EVT-143, if approved)** via a NEW caller-side `record_reference_status_change` in `reference/service.py` (the two existing emitters hard-code their event type) that emits EVT-143 with `before/after={status}` (optional `justification`=reason); `audit/service.py` stays FROZEN. Add `ENTITY_CORPORATE_ACTION`. Each entity emits its OWN event; before/after = DC-2 metadata; per-tenant chains; `verify_chain`.
> 5. **Additive** entitlement in `bootstrap.py`: add `reference.corporate_action.view` (`.edit` already exists — do NOT re-add); grant `.view` → `data_steward`/`risk_analyst_1l`/`risk_manager_2l` (== the `reference.instrument.view` set); leave `.edit` recipients UNCHANGED; `auditor_3l` excluded; bootstrap parity test (new code present, recipients pinned, `reference.rating.*` absent).
> 6. Thin endpoints in a NEW `irp_backend/api/reference_corporate_actions.py` (register in `main.py`) per §7; `require_permission` deny-by-default; `get_tenant_session`; server-stamped tenant; cross-tenant/unknown instrument → 404; single end-of-request commit. Do NOT modify the other three reference routers.
> 7. Per-tenant MANUAL-`data_source` origin lineage on create via the unchanged `record_reference_create` (§11); `assert_has_lineage` is the TEST-side CTRL-013 check; no new edge on EV amend/transition.
> 8. OPTIONAL generic DQ only (§12) where configured.
> 9. Tests per §13 (SQLite logic incl. amend + status-transition + **capture-only scope-fence** + cross-tenant service-layer fail-closed + fail-closed audit rollback; endpoint; PG under `irp_app` incl. EV-mutable + closed-hybrid-set guard; import-direction; scope-fence). The `app_url` PG fixture GRANTs on `corporate_action` (+ `instrument`). Add the new corporate_action symmetric-RLS PG step to CI.
> 10. In-slice doc updates per §18.
>
> **STRICT EXCLUSIONS (must NOT appear in any deliverable/entity/endpoint/test/migration):** any corporate-action **application engine** / position adjustment / cash-or-stock entitlement calc / tax treatment; valuation/pricing logic; performance/returns; risk/exposure; roll/day-count math (QS-10/11); vendor corporate-action feed integration; reconciliation or manual-override workflow; a separate immutable announcement log (do NOT reclass ENT-008 to IA); portfolio/positions/valuations/market data/reporting/dashboards/real SSO; P1C/P2+. Do NOT make corporate_action hybrid or stamp SYSTEM_TENANT. Do NOT modify the FROZEN `audit/service.py`, the asymmetric hybrid loop, the `FullReproducibleMixin`, or migrations 0001–0010. `irp_shared.reference` imports only `lineage`/`dq`/`audit`/`entitlement`/`db`/`temporal`.
>
> **Review cadence:** UltraCode multi-lens — implement → review (Product, Architect, Data, Security/RLS, Audit/Controls, Lineage/DQ, QA, Scope) → fix in-scope → re-review until clean.
> **Gate:** `make check` (lint + types + tests + `alembic check`) + the new corporate_action RLS PG step until green.
> **Commit only on explicit approval.**
>
> ### Build-sequence subsection
> 1. **Model + aggregator** — `CorporateAction` in `reference/models.py`; register in `irp_shared/models.py`; `alembic check` sees the new metadata.
> 2. **Migration 0011** — DDL + the symmetric RLS loop; `alembic upgrade head` + `alembic check` clean; downgrade smoke.
> 3. **Binder + service helper** — `corporate_action.py` (resolve/create/amend/transition) reusing `resolve_instrument`; `record_reference_status_change` (if EVT-143 approved); lineage + audit wiring (fail-closed); explicit tenant predicate.
> 4. **Entitlement** — additive `bootstrap.py` `.view` + grants; bootstrap parity test.
> 5. **Endpoints** — `api/reference_corporate_actions.py`; register in `main.py`.
> 6. **Tests** — logic → endpoint → PG symmetric-RLS + closed-set guard → import-direction → scope-fence; add the CI step.
> 7. **Docs** — §18 list.
> 8. **`make check` green → multi-lens review → fix in-scope → commit on approval.**

---

## §21. UltraCode adversarial-review log (this planning turn)

The plan was reviewed by an 8-lens UltraCode workflow (Product, Architect, Data, Security/RLS, Audit/Controls, Lineage/DQ, QA, Scope); every HIGH/MEDIUM finding was independently, adversarially verified (default-skeptical). Verdicts: **3 lenses `approve`, 5 `approve_with_changes`** — **no `block`, no HIGH**.

**Confirmed (real) findings — folded into the plan:**
- **QA-1** (MED): the EVT-143 activation now has explicit **positive** (a transition emits exactly one `REFERENCE.STATUS_CHANGE` with `before/after={status}`, `verify_chain` ok) **and negative-fence** (EVT-143 emitted ONLY for corporate_action; the two existing reservation guards stay green, entity-scoped) tests (§13).
- **SEC-1** (LOW): §10/§20 RLS policy text corrected to the `tenant_id::text = current_setting(...)` cast (matches 0009/0010).
- **QA-4 / QA-2 / QA-3 / SEC-5 / AC-2** (LOW): §13 now enumerates the transition guard matrix (legal/illegal moves), `record_version`+1 per transition, endpoint negatives (illegal transition → 4xx; bad mode → 422), create-time status validation, and the `REFERENCE.UPDATE` fallback contract.
- **ARCH-3** (LOW): §13 import-direction reworded to "allowlist **UNCHANGED**".
- **PR-1 / PR-3 / DA-1 / SCOPE-1 / AC-1 / PR-2 / ARCH-1** (INFO): §8 notes CORRECTION is intentionally dropped (FR-only); §1 notes the issuer-level deferral; §3 justifies the `code` natural key; §7 flags the `POST /{id}` amend/status path as a ratified extension; §18 adds the `events.py` docstring flip + RTM-row tightening; §20.1 spells out the dual-touch (import + `__all__`) registration.

**Rejected by adversarial verification:** **AC-1** (the existing EVT-143-reservation tests are entity-scoped and stay green on activation — no defect; folded the doc-flip note only). No finding survived as a behavioral defect.

**Gating sign-offs — both OBTAINED (2026-06-24):** **OQ-1 APPROVED** (activate EVT-143 `REFERENCE.STATUS_CHANGE`, caller-side only; `audit/service.py` frozen) and **OQ-5 APPROVED** (auditor_3l excluded). The plan is cleared for implementation on explicit direction.
