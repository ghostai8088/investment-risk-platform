# P1B-3 Implementation Plan — Instrument / Instrument Terms / Identifier Cross-Reference

## Document Control

| Field | Value |
|---|---|
| Slice | **P1B-3** — third Security Master & Reference Data slice |
| Status | **PLAN — planning only; NOT implemented.** Do not write code/migrations until explicitly approved. |
| Requirements | REQ-SMR-001 (instrument master), REQ-SMR-003 (identifier cross-reference / resolution, partial) |
| Entities | `instrument` (ENT-001 identity, **EV**), `instrument_terms` (ENT-001 terms, **FR**), `identifier_xref` (ENT-004, **EV**) |
| Migration | **0010_instrument** (`down_revision='0009_legal_entity'`) — the next head after P1B-2 |
| Predecessors | P1B-1 `6568cb1` (reference vocabularies; first hybrid RLS), P1B-2 `32c7778` (legal_entity core + issuer/counterparty; symmetric proprietary RLS) |
| Headline | **The first real Full-Reproducible (FR) / bitemporal construct on the platform** (`instrument_terms`). `FullReproducibleMixin` has had **no persisted user** through P1B-2; P1B-3 is its first exercise (OD-P1B-A; temporal standard §2A note). |
| Ratified decisions | OD-P1B-A (instrument = EV identity + instrument_terms = FR), OD-P1B-G (deterministic-or-ambiguity resolution), OD-012 (precedence → P1C, **deferred**) — all ratified at P1B-0 (`4fae26b`) |
| Owner / review | UltraCode multi-lens planning + 8-lens adversarial review; sign-offs OBTAINED 2026-06-23 — OQ-7 (EVT-142 activation, caller-side; audit/service.py frozen) + OQ-9 (auditor_3l excluded) (§10/§18/§21) |
| Cadence | plan → (this doc, on approval) → implement → multi-lens review → fix → `make check` + new PG RLS step → **commit only on explicit approval** |

> **Grounding (verified against the repo this turn):** FR mixin `packages/shared-python/src/irp_shared/db/mixins.py:53-63`; binder/resolver pattern `reference/legal_entity.py`; audit constants `reference/events.py:18-24` + `reference/service.py:43-172`; entitlement catalog `entitlement/bootstrap.py:21-55`; migration head `0009_legal_entity`; NAMING_CONVENTION `db/base.py:8-14`; CI RLS step shape `.github/workflows/ci.yml:120-133`; temporal standard TR-01..TR-08 + §2A `04_data_model/temporal_reproducibility_standard.md`.

---

## §1. Requirements included

| REQ | Coverage in P1B-3 | Deliverable | Acceptance test |
|---|---|---|---|
| **REQ-SMR-001** Instrument master | **In-Progress (substantive).** `instrument` EV identity + `instrument_terms` FR terms via the OD-P1B-A split; terms **reconstructable as-of** on both time axes. | `instrument` + `instrument_terms` tables (mig 0010); governed CRUD + FR supersede/correction binders; as-of reconstruction. | FR bitemporal "reconstruct as-of valid-time T₁ as-known-at T₂" returns the correct single version; current view = latest system-time. |
| **REQ-SMR-003** Identifier cross-reference | **In-Progress (partial, as ratified).** `identifier_xref` EV + the OD-P1B-G deterministic **single-result-or-`AmbiguousIdentifier`** resolver. Cross-vendor **precedence deferred** (OD-012 → P1C). | `identifier_xref` table; partial-unique on active `(tenant_id, scheme, value)`; `resolve_identifier` binder + `GET /reference/identifiers/resolve`. | A known `(scheme, value)` resolves to exactly one instrument or an explicit ambiguity error — **never a silent arbitrary match**. |

**Partial-coverage markers (carried into the RTM at closeout):**
- REQ-SMR-001: the FR **terms-as-of** half is delivered; pricing/cashflow/valuation/derivative-and-structured-product term math is **out of scope** (P2+).
- REQ-SMR-003: deterministic-or-ambiguity is delivered; **cross-vendor precedence / vendor authority ranking is deferred** to P1C/OD-012 (REQ-SMR-003 remains *partially met*, exactly as ratified at P1B-0).

---

## §2. Requirements excluded (explicit scope fence)

- **REQ-SMR-004 corporate_action** — P1B-4 (the `corporate_action` EV entity itself; day-count/roll math → P1C). Not here.
- **Identifier precedence engine / vendor authority (OD-012)** — P1C. P1B-3 ships only the deterministic-or-ambiguity skeleton.
- **External identifier validation** — no CUSIP/ISIN check-digit service, no vendor lookup/integration, no identifier normalization beyond basic string hygiene (trim).
- **Terms math** — no pricing, no cashflow/coupon-schedule engine, no day-count/roll computation, no valuation, no sensitivities, no full derivative or structured-product term models.
- **Market data / pricing** (ENT-020–025), **portfolio / positions / valuations** (P1C), **risk & analytics** (VaR/ES/factor/credit/counterparty-exposure), **rating assignments** (`reference.rating.*` stays RESERVED), **reporting / dashboards / real SSO** — none pulled forward.
- **P1B-5** reference-data ingestion mapping — conditional/deferred; P1B-3 uses **direct governed CRUD only** (no ingestion path).
- **Rejected alternatives:** a single combined `instrument` table holding terms (rejected — violates OD-P1B-A EV/FR split); a hard FK from `instrument.currency_code`/`identifier_xref` into the **hybrid** `currency` table (rejected — couples proprietary→hybrid across RLS models; use value-level ISO strings); per-term-type rows for `instrument_terms` (rejected for the skeleton — one wide versioned terms row).

---

## §3. Proposed entities

All three are **PROPRIETARY, tenant-scoped, SYMMETRIC RLS, NEVER hybrid** (the P1B-2 model, not the P1B-1 hybrid model). Added to `reference/models.py`; registered in `irp_shared/models.py`. Open-vocabulary attributes are **plain Strings** (no enum/CHECK; MG-01 genericity).

### 3.1 `instrument` (ENT-001 identity, **EV**)
`PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin` → `__temporal_class__ = EFFECTIVE_DATED`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | GUID PK | NO | |
| `tenant_id` | GUID | NO | indexed (TenantMixin) |
| `valid_from` / `valid_to` | DateTime(tz) | NO / YES | EV effective dating |
| `created_at/by`, `updated_at/by` | — | — | TimestampMixin |
| `code` | String(150) | NO | firm-assigned internal instrument key (stable identity handle) |
| `name` | String(255) | NO | display name / description |
| `asset_class` | String(50) | NO | controlled-vocab plain string (EQUITY/BOND/FX/CASH/FUND/DERIVATIVE/…) |
| `instrument_type` | String(50) | YES | finer subtype, plain string (GOVT_BOND/CORP_BOND/COMMON_STOCK/…) |
| `issuer_id` | GUID FK→`issuer.id` | **YES** | **nullable** (cash/FX/index have no issuer); intra-tenant; resolved tenant-filtered (§8) |
| `currency_code` | String(3) | YES | denomination/quote ccy — **plain ISO-4217 string, NOT a FK** (avoids proprietary→hybrid coupling) |
| `is_active` | Boolean | NO | default True |
| `record_version` | Integer | NO | default 1 |

**Constraints:** `UNIQUE(tenant_id, code)`; index on `tenant_id`, `issuer_id`. **NO** price/valuation/holding/risk/terms columns (terms live in 3.2). **No `status` string column** (review arch-1): `is_active` is the single lifecycle flag — a display/lifecycle projection that rides `REFERENCE.UPDATE` (EVT-143 `STATUS_CHANGE` stays RESERVED), exactly the P1B-1/P1B-2 precedent; the EV **active window (`valid_to IS NULL`)**, not a status string, is the resolution predicate.

### 3.2 `instrument_terms` (ENT-001 terms, **FR** — first real bitemporal entity)
`PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin` → `__temporal_class__ = FULL_REPRODUCIBLE`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | GUID PK | NO | one **physical row per version** (FR keeps full history in-table) |
| `tenant_id` | GUID | NO | indexed |
| `valid_from` / `valid_to` | DateTime(tz) | NO / YES | **valid time** (TR-01) — when the terms are true in the business world |
| `system_from` / `system_to` | DateTime(tz) | NO / YES | **system time** (TR-02) — when the system knew it |
| `created_at/by`, `updated_at/by` | — | — | TimestampMixin |
| `instrument_id` | GUID FK→`instrument.id` | NO | **logical key** (all version rows of one instrument's terms); indexed |
| `coupon_rate` | Numeric(12,6) | YES | skeleton economic placeholder |
| `coupon_frequency` | String(20) | YES | plain string (ANNUAL/SEMI_ANNUAL/QUARTERLY/…) |
| `issue_date` | Date | YES | skeleton |
| `maturity_date` | Date | YES | skeleton |
| `day_count` | String(20) | YES | plain string (ACT/360, 30/360, ACT/ACT, …) |
| `denomination_currency` | String(3) | YES | plain ISO-4217 string |
| `face_value` | Numeric(20,4) | YES | skeleton (par/denomination amount) |
| `term_source` | String(150) | YES | methodology/source pointer (terms provenance label; complements lineage) |
| `restatement_reason` | String(255) | **YES** | set **only** on a correction/restatement (TR-08) |
| `supersedes_id` | GUID FK→`instrument_terms.id` | **YES** | link to the superseded version (TR-08); set on **both** effective supersede **and** correction (a complete, queryable version chain); `restatement_reason` is what distinguishes a restatement (review data-7) |
| `record_version` | Integer | NO | default 1 — **logical** version count of the terms set (create = 1; each effective supersede / correction = prev + 1), so the version lineage is queryable without ordering by timestamps (review data-5) |

**Constraints:**
- **Current-version partial-unique:** `Index('uq_instrument_terms_current', 'tenant_id', 'instrument_id', unique=True, postgresql_where=text('valid_to IS NULL AND system_to IS NULL'))` — **at most one version open on BOTH axes (dual-open: `valid_to IS NULL AND system_to IS NULL`) per `(tenant, instrument)`** (the bitemporal current-head invariant; correctness of as-of reconstruction comes from the §4.2 query predicate, **not** this index — see review data-2). SQLite supports partial indexes with `WHERE`, so the same predicate is emitted for both engines (drift-clean, behavior-matched). Migration 0010 must emit the **byte-identical** literal index name + `postgresql_where` text as the ORM `Index` so `alembic check` stays drift-clean (the `uq_legal_entity_tenant_lei` precedent; review data-8).
- index on `instrument_id`, `tenant_id`.
- **NOT in `APPEND_ONLY_TABLES`; NO `irp_prevent_mutation` trigger** — the bitemporal protocol must `UPDATE` `valid_to`/`system_to` close-out columns. **Content immutability** (economic columns of a prior version are never mutated in place — only close-out columns) is enforced by the **service layer + tests**, not a DB trigger (a DB-level content-immutability guard is a noted future hardening, **not** P1B-3). The economic columns (`coupon_rate`/`coupon_frequency`/`day_count`/`face_value`/…) are **inert placeholder strings/numerics — no evaluator or engine in P1B-3** (review scope-2).

### 3.3 `identifier_xref` (ENT-004, **EV**)
`PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin` → `__temporal_class__ = EFFECTIVE_DATED`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | GUID PK | NO | |
| `tenant_id` | GUID | NO | indexed |
| `valid_from` / `valid_to` | DateTime(tz) | NO / YES | EV effective dating (the identifier's active window) |
| `created_at/by`, `updated_at/by` | — | — | TimestampMixin |
| `entity_type` | String(50) | NO | **polymorphic** controlled-vocab plain string; P1B-3 writes only `instrument` (§7/§18) |
| `entity_id` | GUID | NO | **polymorphic ref, NO domain FK** (genericity); resolves to an instrument tenant-filtered |
| `scheme` | String(50) | NO | controlled-vocab plain string (ISIN/CUSIP/SEDOL/FIGI/TICKER/INTERNAL/…) |
| `value` | String(255) | NO | identifier value (basic hygiene: trim; no external validation) |
| `source` | String(150) | YES | vendor/source label (provenance hint — **NOT** precedence authority) |
| `is_active` | Boolean | NO | default True — single lifecycle flag (no `status` string; review arch-1) |
| `record_version` | Integer | NO | default 1 |

**Constraints:**
- **OD-P1B-G structural uniqueness:** `Index('uq_identifier_xref_active', 'tenant_id', 'scheme', 'value', unique=True, postgresql_where=text('valid_to IS NULL'))` — at most one **active** row per `(tenant, scheme, value)` (a plain UNIQUE cannot express "over the active period" and would collide across superseded EV versions).
- index on `tenant_id`, `(entity_type, entity_id)`.
- **`entity_id` carries NO domain FK by design** (polymorphic genericity, MG-01): there is no DB referential/cascade backstop on the target. Its referential **and** tenant integrity is guaranteed solely by `create_identifier_xref`'s tenant-filtered `resolve_instrument` + the RLS `WITH CHECK` on the xref row's own `tenant_id` (review arch-3 / rls-1; §12).

---

## §4. Temporal classifications

| Entity | Class | Why |
|---|---|---|
| `instrument` | **EV** (Effective-dated Versioned) | identity/master attributes are not risk-driving; system-time versioning + audit history is sufficient (AD-005 §2A; OD-P1B-A). One physical row per instrument; in-place supersede; history via `REFERENCE.UPDATE` audit. |
| `instrument_terms` | **FR** (Full Reproducible / bitemporal) | economic/legal terms **drive pricing/risk** and must be reconstructable "as-of valid-time T₁ as-known-at T₂" (REQ-SMR-001 acceptance; AD-005 §2A FR clause names instrument terms explicitly). Multi-row version history in-table on **both** axes. |
| `identifier_xref` | **EV** | reference/master cross-reference; needs effective-dated history but not dual-axis as-of (AD-005 §2A EV list names `identifier_xref`). |

### 4.1 Why `instrument_terms` is the first true FR/bitemporal usage
`FullReproducibleMixin` (`db/mixins.py:53`) exists structurally but **no P1A/P1B-1/P1B-2 entity or test exercises it** (temporal standard §2A: "the `FullReproducibleMixin` (FR) still has no first persisted user; P1B-3 is its first exercise"). The currency/calendar/rating and legal_entity/issuer/counterparty tables are all **EV**. P1B-3's "reconstructable as-of" proof is therefore **net-new validation of the FR mixin itself** (column behavior, the two time axes, as-of query correctness), not a regression check of tested code.

### 4.2 What FR means in this codebase (the bitemporal protocol)
The FR mixin provides four columns: `valid_from`/`valid_to` (**valid time**, TR-01) and `system_from`/`system_to` (**system/knowledge time**, TR-02). The protocol (service-layer, `reference/instrument_terms.py`):

- **Create (first version):** insert a row with `valid_from = effective start`, `valid_to = NULL`, `system_from = now`, `system_to = NULL`. → `REFERENCE.CREATE` + one MANUAL-source origin edge.
- **Effective-dated supersede (a new *valid-time* version — terms change effective at date T):** close the current row's `valid_to = T`; insert a new row `valid_from = T`, `valid_to = NULL`, `system_from = now`, `system_to = NULL`, `supersedes_id = prior.id`. → `REFERENCE.CREATE` on the new row (its own origin edge) **+** `REFERENCE.UPDATE` on the prior row (valid_to close-out; `before/after = {valid_to: null→T}`). **No economic column of the prior row is mutated.**
- **Correction / restatement (a new *system-time* version — we recorded the terms wrong for an existing valid period; TR-08):** close the prior row's `system_to = now`; insert a corrected row with the **same valid period**, `system_from = now`, `system_to = NULL`, `restatement_reason` set, `supersedes_id = prior.id`. → `REFERENCE.CORRECTION` (EVT-142; see §10/§18) on the corrected row **+** `REFERENCE.UPDATE` on the prior row (system_to close-out).
- **Reconstruct as-of** `reconstruct_terms_as_of(session, instrument_id, *, acting_tenant, valid_at, known_at=None)`: `WHERE instrument_id = X AND tenant_id = acting_tenant AND valid_from <= valid_at AND (valid_to IS NULL OR valid_to > valid_at) AND system_from <= known_at AND (system_to IS NULL OR system_to > known_at)` (`known_at` defaults to now → **current view**, TR-04). Returns the single version true at `valid_at` as-known-at `known_at`, or `None`.

**Binder invariants (load-bearing — review data-6 / data-1):**
- **One `now` per operation:** the supersede/correction binder computes `now = utcnow()` **once** and uses the same value for the prior row's close-out (`valid_to`/`system_to`) **and** the new row's open boundary (`valid_from`/`system_from`), so `prior.system_to == corrected.system_from` exactly and no sub-microsecond gap can leave a `known_at` matching neither row (tested).
- **Close-first ordering:** mutate + `session.flush()` the prior row's close-out column **first**, then `session.add()` + flush the new version row — and avoid an intervening autoflush-triggering query between the `add()` and the close-out — so the dual-open partial-unique is never transiently violated. (SQLAlchemy 2.0's unit-of-work already emits same-mapper UPDATE before INSERT in a single flush, so this is defensive, not load-bearing; a two-supersedes-in-one-transaction regression test guards it.)

**No silent overwrite of prior terms** (TR-03/TR-05 spirit): every change inserts a new row and only ever close-outs the prior row's time-axis columns; corrections are explicitly flagged (TR-08). The system-time axis is genuinely exercised **only** if the correction path ships (hence the §18/OQ-7 governance decision).

---

## §5. Instrument model design
Skeleton **identity-level only** (see 3.1). Included: `code` (stable key), `name`, `asset_class`, `instrument_type`, `issuer_id` (nullable), `currency_code` (plain ISO string), `status`, `is_active`, `record_version` + EV/tenant/timestamp mixins. **Explicitly excluded** from `instrument` (belongs in `instrument_terms` or out of scope): coupon/maturity/day-count/denomination/face-value (→ terms), and any price, valuation, holding/position, or risk-sensitivity field. Binder `reference/instrument.py`: `InstrumentNotVisible`, `resolve_instrument(session, instrument_id, *, acting_tenant)` (explicit `tenant_id == acting_tenant` predicate — fail-closed on SQLite + PG, mirroring `resolve_legal_entity`), `create_instrument` (resolves `issuer_id` tenant-filtered when present), `update_instrument` (EV in-place supersede of `_UPDATABLE` attrs; bumps `record_version`; `REFERENCE.UPDATE`; no new lineage edge).

---

## §6. Instrument terms design (FR)
Minimum FR fields per 3.2 — **one wide versioned terms row per instrument** (not per-term-type rows; the skeleton recommendation). Inserted / superseded / corrected / queried exactly per the §4.2 protocol. Binder `reference/instrument_terms.py`:
- `create_instrument_terms(session, *, instrument_id, acting_tenant, actor, valid_from=now, **terms)` — resolves `instrument_id` tenant-filtered (fail closed); inserts the open version; `REFERENCE.CREATE` + origin edge.
- `supersede_instrument_terms(session, instrument_id, *, effective_at, acting_tenant, actor, **new_terms)` — effective-dated valid-time version (close prior `valid_to`, insert new open row).
- `correct_instrument_terms(session, terms_row, *, restatement_reason, acting_tenant, actor, **corrected)` — as-known restatement (close prior `system_to`, insert corrected row, `supersedes_id` + `restatement_reason`).
- `reconstruct_terms_as_of(...)` — the bitemporal read (§4.2).
All resolvers carry the explicit tenant predicate. **The new/superseded/corrected version row is always inserted via the governed create path** (`record_reference_create` for `REFERENCE.CREATE`, or `record_reference_correction` for `REFERENCE.CORRECTION` — §10) so its **own origin lineage edge** is rooted structurally, not by convention; the prior row is closed via `record_reference_update` (no new edge) (review lineage-3 / audit-1). **Deferred (NOT in P1B-3):** pricing, cashflow/coupon-schedule expansion, full derivative terms, structured-product terms, valuation logic, risk sensitivities, day-count/roll math.

---

## §7. Identifier cross-reference design
Fields per 3.3: `entity_type` / `entity_id` (polymorphic), `scheme`, `value`, `valid_from`/`valid_to`, `source`, `status`. **Supported schemes (skeleton, value-level — new schemes added by value, no migration):** `INTERNAL_ID`, `CUSIP`, `ISIN`, `SEDOL`, `TICKER`, `FIGI`, `PRIVATE_INTERNAL_ID` (placeholder). (`LEI` for legal entities is **not** added here — it already lives on `legal_entity.lei` from P1B-2; §18/OQ-4.)

**Deterministic single-result-or-ambiguity** `resolve_identifier(session, *, scheme, value, acting_tenant, as_of=None)` (`reference/identifier.py`):
1. Query `identifier_xref WHERE tenant_id == acting_tenant AND entity_type == 'instrument' AND scheme == scheme AND value == trim(value) AND active-as-of(as_of or now)` (`valid_from <= asof AND (valid_to IS NULL OR valid_to > asof)`).
2. **0 rows → return `None`** (endpoint → 404, indistinguishable from cross-tenant).
3. **>1 rows → raise `AmbiguousIdentifier(scheme, value, matched_entity_ids)`** (endpoint → 409) — **never a silent arbitrary match**.
4. **1 row → resolve the instrument** by `entity_id` with the explicit tenant predicate (`resolve_instrument`); if not visible, fail closed (treated as not-found). Return the `Instrument`.

**Partial unique on active rows** (`uq_identifier_xref_active`, §3.3) guarantees ≤1 *current* match, so the ambiguity branch is **defense-in-depth**: it is genuinely reachable via **historical overlapping windows** (two rows whose `[valid_from, valid_to)` overlap but neither is the open row are not constrained by the active-only index) resolved with a past `as_of` — the test exercises exactly this (no silent pick). `create_identifier_xref` forces `entity_type='instrument'` in P1B-3 and validates `entity_id` is a visible instrument (tenant-filtered). **Public vs private instruments** are carried by value (`asset_class`/`instrument_type` strings + the `PRIVATE_INTERNAL_ID` scheme) — **no public/private subtype table or schema fork**; private-instrument-specific economics (canonical ENT-015 commitments / ENT-017 private NAV) are out of scope and would attach as future FR entities, never as `instrument` columns (review arch-4). **Deferred:** precedence ranking, vendor-authority logic, external validation, normalization beyond trim.

---

## §8. Relationship to issuer
`instrument.issuer_id` is a **nullable** FK to the **`issuer` profile** (ENT-002, P1B-2) — not to the bare `legal_entity` core. On create/update, a non-null `issuer_id` is resolved through a tenant-filtered `resolve_issuer(session, issuer_id, *, acting_tenant)` (added to `reference/issuer.py`, mirroring `resolve_legal_entity`) so a **cross-tenant/unknown issuer fails closed on SQLite AND PG**. Instruments **without** an issuer (cash, FX, index placeholders) are explicitly allowed — no issuer-required rule (asset-class-specific rules deferred). **No credit risk, issuer concentration, or exposure rollup** is implemented (scope fence; OD-015 → P1C).

---

## §9. APIs (thin; bounded count)
New router `apps/backend/src/irp_backend/api/reference_instruments.py` — a **third** `APIRouter(prefix="/reference")` (the existing same-prefix routers `reference.py` (P1B-1 vocabularies) and `reference_entities.py` (P1B-2 legal_entity/issuer/counterparty) are **both untouched**; the new sub-paths `/instruments*`, `/identifier-xrefs`, `/identifiers/resolve` are disjoint from both — review arch-2). Registered in `main.py`. All endpoints: `get_tenant_session`, `require_permission` (deny-by-default, module-level guard singletons), `uuid.UUID` path params (422 + indistinguishable 404), server-stamped `tenant_id`, single end-of-request commit.

| Method + path | Permission | Notes |
|---|---|---|
| `POST /reference/instruments` | `reference.instrument.edit` | create instrument |
| `GET /reference/instruments` | `reference.instrument.view` | list (tenant-scoped) |
| `GET /reference/instruments/{id}` | `reference.instrument.view` | detail |
| `POST /reference/instruments/{id}/terms` | `reference.instrument.edit` | create/supersede/correct terms (mode in body: `create`/`supersede`/`correct`) |
| `GET /reference/instruments/{id}/terms` | `reference.instrument.view` | list term versions |
| `GET /reference/instruments/{id}/terms/as-of?valid_at=&known_at=` | `reference.instrument.view` | bitemporal reconstruction (§4.2) |
| `POST /reference/identifier-xrefs` | `reference.identifier.edit` | create xref (entity_type forced `instrument`) |
| `GET /reference/identifiers/resolve?scheme=&value=` | `reference.identifier.resolve` | 200 (one) / 404 (none) / 409 (ambiguous) |

**No** broad search, external lookup, vendor validation, pricing, or bulk endpoints. **No** DELETE/PUT.

---

## §10. Audit events
Reuse the FROZEN `audit.service.record_event` via `reference/service.py` (DC-2 metadata-only `after_value`/`before_value` — a **terms summary**, never raw payload). Each entity emits its **own** event (not folded).
- `instrument`: `REFERENCE.CREATE` (EVT-140) / `REFERENCE.UPDATE` (EVT-141) — already activated.
- `instrument_terms`: **create →** `REFERENCE.CREATE`; **effective-dated supersede →** `REFERENCE.CREATE` (new row) + `REFERENCE.UPDATE` (prior `valid_to` close); **correction/restatement →** `REFERENCE.CORRECTION` (**EVT-142**, carrying `restatement_reason` + `supersedes_id`, TR-08) + `REFERENCE.UPDATE` (prior `system_to` close).
- `identifier_xref`: `REFERENCE.CREATE` / `REFERENCE.UPDATE`.

**New caller-side emitter (review audit-1 / product-3):** the two existing helpers `record_reference_create` / `record_reference_update` **hard-code** their event type, so the correction path needs a NEW helper `record_reference_correction(session, *, entity, entity_type, before_value, after_value, actor)` in `reference/service.py` (**which is NOT frozen** — only `audit/service.py` is) that emits `REFERENCE_CORRECTION_EVENT` (EVT-142) **and roots one ORIGIN edge on the new corrected row** (mirroring `record_reference_create`); the prior-row `system_to` close-out reuses `record_reference_update` (no edge). Add `ENTITY_INSTRUMENT` / `ENTITY_INSTRUMENT_TERMS` / `ENTITY_IDENTIFIER_XREF` constants. **TR-08 justification field:** the CORRECTION event sets `justification = restatement_reason` (the canonical audit field), with `approval_ref` left `None` until BR-7 manual-override enforcement lands (P6/P7) — review audit-3. **Emission order (review audit-4):** within the single end-of-request commit, emit the prior-row `REFERENCE.UPDATE` close-out first, then the new-row `REFERENCE.CREATE`/`CORRECTION` (consistent across supersede and correction); `verify_chain` passes after the two-event write. **`REFERENCE.CREATE`-per-version is intentional (review audit-5):** for FR, each physical version row is itself a governed record (its own origin edge), so a CREATE per valid-time version is by design — distinct from the EV in-place supersede (one row + `REFERENCE.UPDATE`).

**EVT-142 activation — APPROVED 2026-06-23 (see §18/OQ-7):** `REFERENCE.CORRECTION` is today **RESERVED** (`reference/events.py:23`, `audit_event_taxonomy.md`); P1B-3 **activates** it for the `instrument_terms` restatement path (the same governed activation P1B-1 used for EVT-140/141) + a taxonomy-doc update. It does **NOT** touch the FROZEN `audit/service.py` (caller-side constant only). It is recommended because it is the **only** way to honestly exercise + test the FR system-time axis and TR-08 mandates restatements be flagged distinctly. `REFERENCE.STATUS_CHANGE` (EVT-143) stays RESERVED. Per-tenant chains only (proprietary; no SYSTEM chain). `verify_chain` after every write path.

---

## §11. Entitlement checks (additive `bootstrap.py`)
**Already exist** (verified `bootstrap.py:30-36`): `reference.instrument.view`, `reference.instrument.edit`, `reference.identifier.resolve`. **Missing → P1B-3 adds:** `reference.identifier.view`, `reference.identifier.edit`. **No** separate `reference.instrument_terms.*` (terms writes require `reference.instrument.edit` — terms are part of the instrument aggregate). `reference.rating.*` stays RESERVED.

**Grants — exact per-code target matrix** (review product-1/product-2/scope-1: P1B-3 is purely **additive**; it grants only the two NEW permissions and **does NOT widen any existing permission's recipient set**). Verified current state: `reference.identifier.resolve` is held today by `data_steward` + `risk_analyst_1l` (+ `platform_admin` via `ALL_CODES`) — `risk_manager_2l` does **not** hold it.

| Permission | Status | Recipients (target) |
|---|---|---|
| `reference.identifier.edit` | **NEW** | `data_steward` (+ `platform_admin` via `ALL_CODES`) |
| `reference.identifier.view` | **NEW** | `data_steward`, `risk_analyst_1l`, `risk_manager_2l` (== the existing `reference.instrument.view` set) |
| `reference.identifier.resolve` | **UNCHANGED** | `data_steward`, `risk_analyst_1l` (+ `platform_admin`) — **NOT** re-granted to `risk_manager_2l` |
| `reference.instrument.view` / `.edit` | exists | recipients unchanged |

`auditor_3l` is **EXCLUDED** from all instrument/identifier `.view`/`.edit`/`.resolve` (proprietary-identity SoD, consistent with P1B-2) — see §18/OQ-9 (governance confirm). The bootstrap **parity test pins these exact recipient sets** (including that `.resolve` is left untouched), so no pre-existing permission can silently drift. No broad admin bypass. (If 2L `.resolve` access is ever wanted, it must be a deliberate governance change via a new ⚑ OQ — not an "additive" bundle.)

---

## §12. RLS behavior
All three tables are **tenant-scoped, SYMMETRIC RLS** — the P1B-2 loop byte-for-byte: `FORCE ROW LEVEL SECURITY`; `USING (tenant_id = current_setting('app.current_tenant', true)) == WITH CHECK (...)`. **No hybrid, no SYSTEM_TENANT, no append-only trigger, no BYPASSRLS application path.** Migration 0010 reuses the 0004/0005/0007/0009 symmetric loop over `("instrument", "instrument_terms", "identifier_xref")`. The closed hybrid set stays **exactly** the five P1B-1 tables (`HYBRID_TABLES` unchanged; positive `pg_policies` assertion + closed-set guard test).

**Cross-tenant linked-id guarantee is service-predicate-ONLY (review rls-1).** RLS `WITH CHECK` validates only the **writing row's own `tenant_id`** — it does **not** tenant-check a linked id (`issuer_id`, `instrument_id`, or the polymorphic `entity_id`); the symmetric policy has no visibility into the target's tenant. So a cross-tenant `issuer_id`/`instrument_id`/`entity_id` is failed closed **exclusively** by the explicit-tenant-predicate resolver (`resolve_issuer`/`resolve_instrument`) raising `*NotVisible` **pre-commit** — the P1B-2 precedent (`test_reference_entities_pg.py` notes "RLS does not tenant-check FK targets"). The PG `WITH CHECK` is the backstop for the row's own tenant_id only. PG tests run under the constrained `irp_app` role; the `app_url` fixture must `GRANT SELECT, INSERT, UPDATE, DELETE` on `instrument`/`instrument_terms`/`identifier_xref` to `irp_app` (**UPDATE is mandatory** for the FR close-out and EV in-place supersede paths) and keep `audit_event` at `SELECT, INSERT` only — role stays `NOSUPERUSER NOBYPASSRLS` so FORCE RLS is genuinely exercised (review rls-2).

---

## §13. Lineage behavior
One MANUAL-`data_source` ORIGIN edge per **new governed row** via the unchanged `record_reference_create` (= `ensure_manual_source` + `record_lineage` + `REFERENCE.CREATE` — review lineage-1: the create core does **not** itself call `assert_has_lineage`):
- `instrument` create → one origin edge. `instrument` EV update → **no** new edge (keeps its origin; `REFERENCE.UPDATE` only).
- `instrument_terms`: **each new physical version row** (create, effective supersede, correction) is inserted through the governed create path (`record_reference_create`, or `record_reference_correction` for a restatement — §10) → its **own** origin edge. The prior row's close-out (valid_to/system_to) creates **no** new edge.
- `identifier_xref` create → one origin edge; EV update → no new edge.

`assert_has_lineage` is the **no-bypass CTRL-013 enforcement check exercised in the TESTS** (per-row, keyed on each row's id — the `legal_entity`/`issuer` precedent), **not** a call inside the reused create core. Per-tenant MANUAL source; no FK-driven lineage edges.

---

## §14. Data quality behavior (optional, generic only)
Generic evaluators only, where configured — the two existing rule types `NOT_NULL` / `ALLOWED_VALUES` (the `dq/rules.py` constants; review dq-1): `NOT_NULL` on `instrument.code` / `instrument.asset_class` / `identifier_xref.scheme` / `identifier_xref.value` / `instrument_terms.instrument_id`; optional `ALLOWED_VALUES` on controlled-vocab fields (`asset_class`, `scheme`, `currency_code`) **only where a rule is explicitly configured**. **No** domain-specific security-master DQ complexity, **no** identifier external validation, **no** reconciliation. A scope-fence test asserts no domain DQ rule is hard-wired.

---

## §15. Tests
**SQLite logic** (`test_reference_instruments.py`): instrument create/update (EV), `UNIQUE(tenant_id, code)`, issuer_id optional, currency_code plain string. **FR `instrument_terms`:**
- create (open version: `valid_to`/`system_to` NULL); effective-dated supersede (prior `valid_to` closed, new open row, `CREATE`+`UPDATE` events); correction (prior `system_to` closed, corrected row with `restatement_reason`+`supersedes_id`, `CORRECTION`+`UPDATE` events).
- **as-of reconstruction on BOTH axes** — a dedicated **system-time-only correction** test (review/QA): `reconstruct_terms_as_of(valid_at=old, known_at=before_correction)` returns the prior row; `known_at=after` returns the corrected row; the corrected row's `valid_from` == prior's (valid-time unchanged); current view (`known_at=now`) = corrected. Plus a valid-time-only supersede test. Correctness comes from the §4.2 predicate, **not** the index (review data-2).
- **content-immutability — named columns** (review/QA-4): after a correction, refetch the prior row and assert `prior.coupon_rate == original` (NOT the corrected value), `prior.system_to is not None`, `prior.restatement_reason is None`.
- **single-`now`** (review data-6): assert `prior.system_to == corrected.system_from` exactly. **`instrument_terms` not append-only** (a close-out UPDATE succeeds). **Two supersedes in one transaction** regression (review data-1) — the dual-open partial-unique is never transiently violated.

**Identifier:** create (entity_type forced `instrument`); active partial-unique (dup active `(scheme,value)` → IntegrityError); resolve single → instrument; resolve none → None; **resolve ambiguous** — explicit fixture (review/QA-2): two rows for the same `(tenant, scheme, value)` **both with non-null `valid_to`** whose `[valid_from, valid_to)` windows overlap, resolved with a **past `as_of` inside the overlap** → raises `AmbiguousIdentifier` (no silent pick).

**Fail-closed — pin the rejection mechanism** (review rls-1 / QA-3): cross-tenant `issuer_id` (instrument), `instrument_id` (terms), `entity_id` (xref) creates must raise the **service-layer** `IssuerNotVisible`/`InstrumentNotVisible` **pre-commit** (`pytest.raises(...)`, **NOT** `IntegrityError`/a 42501), then `rollback()` → `Instrument`/`InstrumentTerms`/`IdentifierXref` == 0 **and** `AuditEvent` == 0 **and** `DataSource` == 0; `verify_chain` intact. **CORRECTION audit payload** (review audit-2): assert the `REFERENCE.CORRECTION` `after_value` (DC-2 metadata) carries `restatement_reason` + `supersedes_id`, and the prior-row `REFERENCE.UPDATE` `before/after` captures `system_to: null→now` — mirroring the P1B-2 `test_audit_after_value_is_metadata_only` exact-key-set pattern (metadata only, no raw economic payload).
**Endpoint** (`test_reference_instruments_endpoint.py`): deny-by-default (403), server-stamped tenant, uuid path params (422 + indistinguishable 404), resolve 200/404/409, as-of terms read, single end-of-request commit.
**PostgreSQL under `irp_app`** (`test_reference_instruments_pg.py`, new CI step; the `app_url` fixture adds `instrument`/`instrument_terms`/`identifier_xref` to a `_P1B3` GRANT tuple — `SELECT, INSERT, UPDATE, DELETE` — review QA-6/rls-2): tenant isolation on all 3 tables; no-context → zero rows; **cross-tenant `issuer_id`/`instrument_id`/`entity_id` fail closed at the service layer pre-commit** (the linked-id guard is the resolver, not RLS — review rls-1; the test asserts the `*NotVisible` exception + row-count 0, not a 42501); positive symmetric-policy + FORCE-RLS assertion; **closed-hybrid-set unchanged**; forged-write-emits-no-audit; **FR bitemporal as-of under RLS**; downgrade smoke (`alembic downgrade base`).
**Import-direction:** `irp_shared.reference` imports only `lineage`/`dq`/`audit`/`entitlement`/`db`/`temporal` (allowlist test extended).
**Scope-fence:** new asset_class/scheme by value (no migration); no precedence ranking; `entity_type` only `instrument`; no pricing/valuation/risk columns on any entity; FR mixin unchanged; migrations 0001–0009 + `audit/service.py` + `HYBRID_TABLES` + the hybrid loop unchanged.

---

## §16. Acceptance criteria
1. `instrument` identity modeled as **EV**; `instrument_terms` modeled as **FR** and **reconstructable as-of** on both axes; `identifier_xref` modeled as **EV**.
2. Identifier resolution is **deterministic or explicitly ambiguous** (`AmbiguousIdentifier`) — never a silent arbitrary match.
3. All three tables **tenant-isolated** (symmetric RLS, FORCE RLS, no-context → zero rows); **no hybrid behavior**; closed hybrid set still the five P1B-1 tables.
4. Every reference write is **audited** (REFERENCE.* incl. CORRECTION for restatements) and **lineage-rooted** (MANUAL origin edge per new row); fail-closed (no row ⇒ no audit ⇒ no lineage). The **restatement audit record carries the TR-08 reason + superseded-version link** (provable in the audit trail, not only the data row).
5. **No** pricing, valuation, holdings, market data, risk, precedence-engine, or external-validation logic added.
6. CI PG RLS + FR-bitemporal tests prove the behavior; `make check` green; `alembic check` drift-clean; downgrade smoke passes.

---

## §17. Risks
- **First real FR/bitemporal implementation** — temporal-query correctness + as-of reconstruction are load-bearing and expensive to retrofit. *Mitigation:* the as-of/both-axes tests are acceptance-gating; the protocol is fully specified in §4.2.
- **`instrument_terms` overbuilding** into pricing/cashflow/valuation. *Mitigation:* skeleton placeholder columns only; scope-fence test; deferred list in §6.
- **Identifier resolver becoming a vendor-authority/precedence engine.** *Mitigation:* deterministic-or-ambiguity only; precedence explicitly deferred (OD-012); scope-fence test.
- **Asset-class complexity** / over-generic vs over-specific instrument model. *Mitigation:* plain controlled-vocab strings (extensible by value); identity-only columns; terms split out.
- **Cross-tenant issuer/instrument/identifier linkage leakage.** *Mitigation:* explicit tenant predicate on every resolver + PG `WITH CHECK` backstop + cross-tenant fail-closed tests.
- **FR table is not trigger-protected** (must allow close-out UPDATEs). *Mitigation:* service-layer content-immutability discipline + a content-immutability test; DB-level guard noted as future hardening. **The FR-without-trigger choice does not relax tenant isolation** — RLS `WITH CHECK` still gates every UPDATE on the row's own `tenant_id`, and the close-out never mutates `tenant_id` (review rls-3).
- **Orphan `identifier_xref` rows** (review data-4): with no DB FK/cascade on the polymorphic `entity_id` (MG-01 genericity), an xref pointing at a logically-retired instrument is tolerated; referential cleanup is out of scope. Note the resolver filters on `id`+`tenant_id` only (not `is_active`), so a retired target still resolves — retirement-aware resolution is a deliberate future enhancement, **not** claimed as handled by fail-closed resolution today.

---

## §18. Open decisions (resolved with recommendation; ⚑ = needs explicit sign-off before implementation)

| # | Question | Recommendation |
|---|---|---|
| OQ-1 | FR representation for `instrument_terms`? | Use the 4-column FR mixin + entity-level `instrument_id` logical key + TR-08 `supersedes_id`/`restatement_reason`; **one wide versioned terms row**. |
| OQ-2 | Does `FullReproducibleMixin` need refinement before first use? | **No structural change.** The mixin is sufficient; the bitemporal protocol lives in the binder + the current-version partial-unique + tests. (Future option: a DB content-immutability guard — not now.) |
| OQ-3 | Minimal term fields now? | The §3.2 skeleton economic set (coupon/frequency/issue/maturity/day-count/denomination-ccy/face-value) as **nullable placeholders**; no pricing/cashflow/derivative/structured fields. |
| OQ-4 | Does `identifier_xref` cover legal-entity/issuer/counterparty identifiers, or instrument-only? | **Polymorphic `(entity_type, entity_id)` schema, scoped to `entity_type='instrument'` in P1B-3.** LEI already lives on `legal_entity` (P1B-2); entity-identifier resolution deferred. |
| OQ-5 | Can instruments exist without `issuer_id`? | **Yes** — `issuer_id` nullable (cash/FX/index); no issuer-required rule. |
| OQ-6 | `asset_class`/`instrument_type` representation? | Controlled-vocab **plain Strings** (no enum/CHECK), value-level extensible (MG-01). |
| OQ-7 ✅ **APPROVED** | `REFERENCE.CORRECTION` (EVT-142) for terms, or is `REFERENCE.UPDATE` enough? | **APPROVED (2026-06-23): activate `REFERENCE.CORRECTION` / EVT-142** for the `instrument_terms` restatement/correction path — **caller-side only; `audit/service.py` remains FROZEN.** Effective-dated (valid-time) supersede stays `REFERENCE.UPDATE`; create = `REFERENCE.CREATE`. This delivers the FR **system-time axis** proof and the TR-08 distinct-restatement-flagging requirement. (The defer-corrections fallback is therefore NOT taken.) |
| OQ-8 | Exact ambiguity response shape? | Typed `AmbiguousIdentifier(scheme, value, matched_entity_ids)` → API **409**; resolution accepts optional `as_of` (defaults now); the active partial-unique guarantees ≤1 for current resolution, so ambiguity is the historical-overlap defense-in-depth. |
| OQ-9 ✅ **APPROVED** | `auditor_3l` access to instrument/identifier view/resolve? | **APPROVED (2026-06-23): `auditor_3l` remains EXCLUDED** from instrument/identifier view/resolve/edit in P1B-3 (proprietary-identity SoD, consistent with P1B-2). May be revisited when reporting/attestation lands. |
| OQ-10 | `currency_code` as FK to `currency` or plain string? | **Plain ISO-4217 String** (avoids proprietary→hybrid FK coupling); optional DQ `allowed_values`. |

---

## §19. Controls impacted
- **CTRL-004** — data dictionary / field definitions (three new entities; canonical annotation).
- **CTRL-017** — reproducibility (**the headline** — FR's first exercise; `instrument_terms` reconstructable as-of); **BR-6** reproducibility; **TR-01..TR-08** (bitemporal axes + TR-08 restatement now realized).
- **CTRL-005 / CTRL-012** — audit coverage (REFERENCE.CREATE/UPDATE + **CORRECTION** for restatements; fail-closed; hash chain).
- **CTRL-011** — tenant isolation / entitlements (symmetric RLS; deny-by-default; proprietary SoD).
- **CTRL-013** — lineage no-bypass (origin edge per new governed row; `assert_has_lineage`).
- **CTRL-029** — no silent wrong/empty identifier resolution (OD-P1B-G; deterministic-or-ambiguity).

---

## §20. Documentation updates (at implementation)
`04_data_model/canonical_data_model_standard.md` (ENT-001 `instrument`+`instrument_terms` realized; ENT-004 `identifier_xref` realized) · `04_data_model/temporal_reproducibility_standard.md` (§2A: FR "first persisted user" note flips to *exercised P1B-3*; TR-08 restatement realized for `instrument_terms`) · `04_data_model/audit_event_taxonomy.md` (EVT-142 `REFERENCE.CORRECTION` **ACTIVATED** for `instrument_terms` restatement under R-07; `instrument`/`identifier_xref` added to REFERENCE.* emitters) · `entitlement_sod_model.md` (`reference.instrument.*` / `reference.identifier.*` grants + proprietary SoD) · `02_requirements/requirements_backbone.md` + `requirements_traceability_matrix.md` (REQ-SMR-001 In-Progress; REQ-SMR-003 In-Progress partial, precedence → P1C/OD-012) · `control_matrix_skeleton.md` (CTRL-017/029 now exercised) · `ci_enforcement_overview.md` (new instrument/identifier symmetric-RLS + FR-bitemporal PG step) · project memory at closeout.

---

## §21. Whether P1B-3 is ready to implement
**READY — both gating sign-offs OBTAINED (2026-06-23): OQ-7 APPROVED** (activate EVT-142 `REFERENCE.CORRECTION`, caller-side only; `audit/service.py` frozen) and **OQ-9 APPROVED** (auditor_3l excluded). All other patterns are **already shipped and proven**: EV governed CRUD, symmetric proprietary RLS, MANUAL-source lineage, REFERENCE.* audit, additive entitlements with parity tests, partial-unique indexes, the explicit-tenant-predicate resolver. The **net-new** work is the FR bitemporal protocol (§4.2) — fully specified, with acceptance-gating as-of/both-axes tests. The 8-lens UltraCode adversarial review (this turn) findings are folded in below the kickoff. No structural change to any frozen artifact (audit/service.py, the hybrid loop, migrations 0001–0009, the FR mixin).

---

## §22. Exact implementation kickoff prompt for P1B-3 (paste-ready)

> **DO NOT START until explicitly directed.** When directed, implement **P1B-3 (instrument identity + instrument_terms FR + identifier_xref)** per `10_delivery_backlog/p1b3_implementation_plan.md`.
>
> **Pre-req sign-offs — both OBTAINED (2026-06-23):** (a) **OQ-7 APPROVED** — `REFERENCE.CORRECTION` (EVT-142) is activated for the `instrument_terms` restatement path (caller-side only; `audit/service.py` frozen); (b) **OQ-9 APPROVED** — `auditor_3l` excluded from instrument/identifier view/resolve/edit.
>
> **Full scope (the deliverable cap — nothing beyond this):**
> 1. Extend `irp_shared/reference/`: add `Instrument` (EV), `InstrumentTerms` (**FR**, `FullReproducibleMixin`), `IdentifierXref` (EV) to `reference/models.py` (register in `irp_shared/models.py`); add binders `reference/instrument.py` (`InstrumentNotVisible`, `resolve_instrument`, `create_instrument`, `update_instrument`), `reference/instrument_terms.py` (`create`/`supersede`/`correct`/`reconstruct_terms_as_of` per §4.2), `reference/identifier.py` (`AmbiguousIdentifier`, `resolve_identifier`, `create_identifier_xref`, `update_identifier_xref`); add `resolve_issuer` to `reference/issuer.py`. **Every resolver carries the EXPLICIT `tenant_id == acting_tenant` predicate** (the `resolve_legal_entity` pattern) so cross-tenant fails closed on SQLite AND PG.
> 2. ONE migration **0010** (`revision='0010_instrument'`, `down_revision='0009_legal_entity'`) creating `instrument`, `instrument_terms`, `identifier_xref` with NAMING_CONVENTION names, the **SYMMETRIC** tenant-isolation RLS loop (reuse 0009 — **NO hybrid, NO SYSTEM_TENANT, NO append-only trigger**), `UNIQUE(tenant_id, code)` on instrument, the `instrument_terms` current-version partial-unique `(tenant_id, instrument_id) WHERE valid_to IS NULL AND system_to IS NULL`, the `identifier_xref` active partial-unique `(tenant_id, scheme, value) WHERE valid_to IS NULL`, the `issuer_id`/`instrument_id` FKs, and the four FR columns on `instrument_terms`. Do NOT touch the hybrid loop, migrations 0001–0009, or `audit/service.py`.
> 3. The three entities exactly as §3 — open-vocab attributes as plain Strings; **`is_active` is the single lifecycle flag (NO `status` string column)**; `record_version` is the logical version count; `supersedes_id` set on both supersede and correction, `restatement_reason` only on correction; `instrument_terms` **NOT** in `APPEND_ONLY_TABLES` (content-immutability is service-enforced + tested); NO pricing/valuation/holding/risk columns; `currency_code`/`denomination_currency` plain ISO strings (no FK to hybrid `currency`). Migration 0010 emits **byte-identical** partial-index names + `postgresql_where` text as the ORM `Index`es.
> 4. Audit (§10): `instrument`/`identifier_xref` reuse `REFERENCE.CREATE`/`UPDATE`; `instrument_terms` create→CREATE, effective supersede→CREATE+UPDATE, correction→**CORRECTION (EVT-142, if approved)**+UPDATE. Add a NEW `record_reference_correction` helper to `reference/service.py` (NOT frozen — the two existing emitters hard-code their event type) that emits EVT-142 (`justification = restatement_reason`, `approval_ref=None`) **and roots one ORIGIN edge on the new corrected row**; the prior-row close-out reuses `record_reference_update` (no edge). Add `ENTITY_INSTRUMENT`/`ENTITY_INSTRUMENT_TERMS`/`ENTITY_IDENTIFIER_XREF` constants. Each entity emits its OWN event; before/after = DC-2 terms-summary metadata; emission order = prior-row UPDATE then new-row CREATE/CORRECTION; per-tenant chains; `verify_chain`. Use one `now = utcnow()` per supersede/correction (close-out == new-row open boundary).
> 5. **Additive** entitlements in `bootstrap.py` (§11 — P1B-3 grants ONLY the two new perms; it does NOT widen any existing permission): add `reference.identifier.view`/`.edit` (instrument perms + `identifier.resolve` already exist — do NOT re-add); grant `reference.identifier.edit`→`data_steward`, `reference.identifier.view`→`data_steward`/`risk_analyst_1l`/`risk_manager_2l` (== the existing `reference.instrument.view` set); **leave `reference.identifier.resolve` recipients UNCHANGED (`data_steward` + `risk_analyst_1l` — do NOT add `risk_manager_2l`)**; `auditor_3l` excluded from all three; bootstrap parity test pins these exact recipient sets (new codes present, `reference.rating.*` absent, `.resolve` untouched); reserve `reference.rating.*`.
> 6. Thin endpoints in a NEW `irp_backend/api/reference_instruments.py` (register in `main.py`) per §9; `require_permission` deny-by-default; `get_tenant_session`; server-stamped tenant; resolve → 200/404/409; as-of terms read; single end-of-request commit. Do NOT modify `reference_entities.py`.
> 7. Per-tenant MANUAL-`data_source` origin lineage on every new governed row via the unchanged `record_reference_create`/`record_reference_correction` (§13); `assert_has_lineage` is the TEST-side CTRL-013 check (per-row), not a call in the create core; no new edge on EV in-place update.
> 8. OPTIONAL generic DQ only (§14) where configured.
> 9. Tests per §15 (SQLite logic incl. the **FR as-of/both-axes proof** incl. a system-time-only correction test, named-column content-immutability, the explicit historical-overlap ambiguity fixture, fail-closed asserting the **service-layer `*NotVisible` pre-commit** (not a 42501) + audit/lineage rollback, the CORRECTION `after_value` TR-08 payload; endpoint; PG under `irp_app` incl. FR-bitemporal-under-RLS + closed-hybrid-set guard; import-direction; scope-fence). The `app_url` PG fixture GRANTs `SELECT, INSERT, UPDATE, DELETE` on the three new tables (a `_P1B3` tuple; UPDATE mandatory for FR close-out + EV supersede) and keeps `audit_event` at `SELECT, INSERT`; role stays `NOSUPERUSER NOBYPASSRLS`. Add the new instrument/identifier symmetric-RLS PG step to CI.
> 10. In-slice doc updates per §20.
>
> **STRICT EXCLUSIONS (must NOT appear in any deliverable/entity/endpoint/test/migration):** corporate_action; identifier **precedence/vendor-authority** engine (OD-012); external identifier validation (CUSIP/ISIN check-digit, vendor lookup); terms math (pricing, cashflow/coupon-schedule, day-count/roll, valuation, sensitivities, derivative/structured-product terms); rating assignments & `reference.rating.*`; market data; portfolio/positions/valuations; risk/exposure/VaR/ES/credit/counterparty calc; reporting/dashboards/real SSO; P1B-4/P1B-5; P1C/P2+. Do NOT make any P1B-3 table hybrid or stamp SYSTEM_TENANT. Do NOT modify the FROZEN `audit/service.py`, the asymmetric hybrid loop, the `FullReproducibleMixin`, or migrations 0001–0009. `irp_shared.reference` imports only `lineage`/`dq`/`audit`/`entitlement`/`db`/`temporal`.
>
> **Review cadence:** UltraCode multi-lens — implement → review (Product, Architect, Data, Security/RLS, Audit/Controls, Lineage/DQ, QA, Scope) → fix in-scope → re-review until clean.
> **Gate:** `make check` (lint + types + tests + `alembic check`) + the new instrument/identifier RLS PG step until green.
> **Commit only on explicit approval.**
>
> ### Build-sequence subsection
> 1. **Models + aggregator** — `Instrument`/`InstrumentTerms`/`IdentifierXref` in `reference/models.py`; register in `irp_shared/models.py`; `alembic check` sees the new metadata.
> 2. **Migration 0010** — DDL + symmetric RLS loop + the two partial-uniques + the FR columns; `alembic upgrade head` + `alembic check` clean; downgrade smoke.
> 3. **Binders** — instrument / instrument_terms (the FR protocol) / identifier (resolve) + `resolve_issuer`; lineage + audit wiring (fail-closed); explicit tenant predicate everywhere.
> 4. **Entitlement** — additive `bootstrap.py` perms + grants; bootstrap parity test.
> 5. **Endpoints** — `api/reference_instruments.py`; register in `main.py`.
> 6. **Tests** — logic (incl. FR as-of/both-axes) → endpoint → PG symmetric-RLS + FR-bitemporal + closed-set guard → import-direction → scope-fence; add the CI step.
> 7. **Docs** — §20 list.
> 8. **`make check` green → multi-lens review → fix in-scope → commit on approval.**

---

## §23. UltraCode adversarial-review log (this planning turn)

The plan was reviewed by an 8-lens UltraCode workflow (Product, Architect, Data, Security/RLS, Audit/Controls, Lineage/DQ, QA, Scope); every HIGH/MEDIUM finding was independently, adversarially verified (default-skeptical) before counting. Verdicts: all returning lenses **approve_with_changes** — no `block`. The QA lens was re-run after a mid-run connection error.

**Confirmed (real) findings — folded into the plan:**
- **arch-1** (MED): dropped the redundant `status` String from `instrument`/`identifier_xref`; `is_active` is the single lifecycle flag, EV active-window is the resolution predicate (§3.1, §3.3).
- **product-1/product-2/scope-1** (MED): the grant block no longer widens the existing `reference.identifier.resolve` to `risk_manager_2l`; an exact per-code grant matrix + parity test pin recipients (§11, §22.5).
- **audit-2** (MED): added §15 assertions that the CORRECTION `after_value` carries the TR-08 `restatement_reason`+`supersedes_id` and that the prior-row UPDATE captures the `system_to` close; AC-4 updated (§15, §16).
- **rls-1** (LOW): §12 corrected — the cross-tenant linked-id (`issuer_id`/`instrument_id`/`entity_id`) guarantee is **service-predicate-only**; RLS `WITH CHECK` gates only the row's own `tenant_id`; §15 pins the rejection mechanism (service `*NotVisible` pre-commit, not a 42501).
- **audit-1** (LOW): named the new `record_reference_correction` emitter (reference/service.py, not frozen) + `ENTITY_*` constants; justification field; emission order (§10, §22.4).
- **lineage-1** (LOW): §13 corrected — `record_reference_create` does not call `assert_has_lineage`; the latter is the test-side CTRL-013 check.
- Plus in-scope LOW/INFO tightenings: single-`now` per supersede/correction (data-6), `supersedes_id` on both paths + FR `record_version` semantics (data-5/data-7), `entity_id` no-FK integrity note (arch-3), public/private-by-value (arch-4), both existing routers named untouched (arch-2), orphan-tolerance + FR-isolation notes (data-4/rls-3), DQ rule-type casing (dq-1), app_url GRANT privilege set (rls-2/QA-6), explicit ambiguity & content-immutability test fixtures (QA-2/QA-4), byte-identical index names (data-8).

**Rejected by adversarial verification (no change):** **data-1** — the lone HIGH; its premise that "SQLAlchemy emits INSERTs before UPDATEs in a flush" is empirically false (2.0 emits same-mapper UPDATE before INSERT), so the claimed IntegrityError hazard does not arise; a cheap close-first/two-supersede regression note was added defensively, not on the false rationale. **data-2, data-3, lineage-2** — wording/test items already covered by the plan as written.

**Gating sign-offs — both OBTAINED (2026-06-23):** **OQ-7 APPROVED** (activate EVT-142 `REFERENCE.CORRECTION`, caller-side only; `audit/service.py` frozen) and **OQ-9 APPROVED** (auditor_3l excluded). The plan is cleared for implementation on explicit direction.
