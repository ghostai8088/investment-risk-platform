# P1C-4 Implementation Plan — Valuation Capture (FR bitemporal, captured marks)

## Document Control

| Field | Value |
|---|---|
| Document ID | P1C4-IMPL-PLAN |
| Version | 1.0 (sign-offs recorded; OD-P1C4-1..6 approved 2026-06-25) |
| Status | Approved for build — planning only; no code, no migration, not implemented (build on explicit kickoff) |
| Owner | Platform Engineering |
| Approver | H-06 Engineering Lead |
| Created | 2026-06-25 |
| Related documents | `10_delivery_backlog/p1c_implementation_plan.md` (master), `10_delivery_backlog/p1c3_implementation_plan.md` (sibling — the FR template), `10_delivery_backlog/p1c0_decision_record.md` (OD-P1C-F), `04_data_model/canonical_data_model_standard.md` (ENT-013), `04_data_model/temporal_reproducibility_standard.md` (§2A FR), `04_data_model/audit_event_taxonomy.md` (EVT-180), `02_requirements/requirements_backbone.md` (REQ-PPM-003) |
| Supported build rules | BR-6, BR-9, BR-10, BR-11, BR-12, BR-13, BR-16, BR-17, BR-19 |
| Decisions inherited | AD-005 (§2A selective bitemporality), AD-013-R1 (hybrid closed set), AD-017 (P1C capture-only), OD-P1C-F (valuation source model — single captured mark), OD-P1C-G (no dataset_snapshot in P1C), OD-P1C-H (exposure aggregation → P2) |

**Precedent reused verbatim:** the **just-shipped P1C-3 `position` FR implementation** (`irp_shared/position/`, migration `0014`), which itself reuses the P1B-3 `instrument_terms` protocol — `FullReproducibleMixin`; create → effective-dated supersede → as-known correction; `reconstruct_*_as_of(valid_at, known_at)` both axes; one-`now`; close-first; current-head partial-unique; **NOT append-only** (content-immutability service-enforced + tested). P1C-4 is the **third** persisted FR entity and the **second FR DOMAIN entity**.

---

## 1. Requirements included

- **REQ-PPM-003 — Transaction & valuation history** (currently **In-Progress** — transaction conjunct delivered in P1C-2): the **"valuations queryable as-of"** conjunct is the P1C-4 piece. Acceptance: *"Transactions immutable; valuations queryable as-of."* P1C-4 realizes ENT-013 `valuation` as an **FR** captured-mark history with both-axes as-of reconstruction, which (together with the already-delivered transaction conjunct) satisfies REQ-PPM-003 in full — see §18/§23 for the close-vs-keep-In-Progress decision (OD-P1C4-5).
- **AD-017 conformance** — valuation is a P1C **capture-only** domain entity: **captured marks**, **not** model/pricing outputs.
- **Temporal §2A (AD-005)** — ENT-013 valuation is listed FR in §2A; P1C-4 is the second realization of an FR **domain** entity (after `position`).
- **The cross-cutting rails** — symmetric RLS (BR-17), co-transactional fail-closed audit + hash chain (BR-12), MANUAL-source lineage per governed write (BR-13), deny-by-default entitlements (BR-11), `__temporal_class__` declared (BR-19), AI-agent logging readiness (BR-16).

## 2. Requirements excluded (and where they live)

| Excluded | Why / where it lives |
|---|---|
| Valuation **model** / pricing **model** / any valuation math | **P2** (AD-017/AD-014). Marks are **captured, not computed** (OD-P1C-F). No `quantity × price`, no `mark = f(position, price)`. |
| Price lookup / market-data join | **P2**. `mark_source` is an inert **label**, NOT a FK to a `price_point`/market-data source. |
| Market-data ingestion (ENT-020–025) | **P2** (AD-014). |
| **Market value rollup** (position × mark) | **P2 valuation/exposure engine**. `valuation` carries **no `position_id` FK, no `quantity`, no `market_value`** — it cannot roll a holding up to a value (the special-focus fence). |
| Exposure aggregation (ENT-014, REQ-PPM-004) | **P2** (AD-014/AD-017/OD-P1C-H). No netting, no rollup, no aggregate table. |
| `dataset_snapshot` | **P2** (OD-P1C-G). |
| Holdings / as-of holdings **views** | **P1C-5**. P1C-4 ships only single-valuation reads + a single-valuation as-of reconstruction (no rollup/aggregation — §10/§11). |
| Multi-source marks / source-precedence engine | **Deferred** (OD-P1C-F resolves: **exactly one mark per key** in P1C; a second source is out of scope, an echo of OD-012). |
| Corporate-action application | **P2+** (AD-017). No CA-to-valuation adjustment. |
| Cashflow engine / risk / performance / reporting / dashboards / real SSO | later phases. |
| P1C-5 / P1C-6 and all P2+ | separate, later, individually-planned + approved slices. |

## 3. Proposed entity / entities

**One new table: `valuation` (ENT-013).** No child tables, no association tables, no derived/aggregate tables. No `position` FK.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | GUID (PK) | no | `PrimaryKeyMixin` |
| `tenant_id` | GUID | no | `TenantMixin`; symmetric RLS axis |
| `valid_from` | DateTime(tz) | no | `FullReproducibleMixin`; the FR **valid-time** axis (when this mark version is effective) |
| `valid_to` | DateTime(tz) | yes | NULL = open in valid time |
| `system_from` | DateTime(tz) | no | knowledge-time open |
| `system_to` | DateTime(tz) | yes | NULL = open in system time |
| `created_at`/`created_by`/`updated_at`/`updated_by` | TimestampMixin | mixed | operational metadata (not a bitemporal axis) |
| `portfolio_id` | GUID FK→`portfolio.id` | no | indexed; resolved tenant-filtered (§7) |
| `instrument_id` | GUID FK→`instrument.id` | no | indexed; resolved tenant-filtered (§8) |
| `valuation_date` | Date | no | **immutable logical-key component** (OD-P1C-F) — the business date the mark is FOR; a peer of `instrument_id`, NOT a versioned attribute; carried forward verbatim by supersede/correct; **distinct from `valid_from`** (§4/§5) |
| `mark_value` | Numeric(20,6) | no | the captured mark/value; **inert** (captured, never recomputed) |
| `currency_code` | String(3) | yes | ISO captured label; inert (capture-not-validate; OD-P1C4-4) |
| `mark_source` | String(150) | yes | controlled-vocab **provenance label** (e.g. `CUSTODIAN`/`ADMIN`/`MANUAL`); inert; **NOT** a FK to market-data |
| `price_basis` | String(20) | yes | inert controlled-vocab (e.g. `DIRTY`/`CLEAN`/`NAV`); captured-not-validated (OD-P1C4-4) |
| `restatement_reason` | String(255) | yes | set **only** on a correction (TR-08) |
| `supersedes_id` | GUID FK→`valuation.id` | yes | self-FK link to the version this row supersedes/corrects |
| `record_version` | Integer | no | default 1; increments on supersede/correct |

**Mixin stack (verbatim reuse of `position`):** `class Valuation(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base)`, `__tablename__ = "valuation"`, `__temporal_class__ = TemporalClass.FULL_REPRODUCIBLE`.

**Holds nothing it should not:** **no** `position_id` FK, **no** `quantity`, **no** `market_value`/`exposure`/`nav`/`pnl`/`unrealized` column, **no** FK to `price_point`/market-data, **no** model/run/snapshot column. A scope-fence test pins these absences (§16).

## 4. Temporal classification

**FR — Full Reproducible / bitemporal** (`TemporalClass.FULL_REPRODUCIBLE = "FR"`), reusing `FullReproducibleMixin` (`valid_from`/`valid_to` + `system_from`/`system_to`). `__temporal_class__` declared (BR-19).

- **Valid-time axis** (`valid_from`/`valid_to`): the period this **mark version** is effective for a fixed `(portfolio, instrument, valuation_date)` — i.e. a re-mark (revised value for the same valuation date) is an effective-dated supersede.
- **System-time axis** (`system_from`/`system_to`): when the platform knew it; enables as-known restatement (a wrong mark was recorded).
- **`valuation_date` is NOT a temporal axis** — it is a **logical-key dimension** (a Date the value is *for*). You can hold marks for many `valuation_date`s per `(portfolio, instrument)`, each independently bitemporally versioned. (This is the deliberate contrast with `position`, where `valid_from` itself was the as-of date and there was no separate date column — OD-P1C3-4. For `valuation`, OD-P1C-F makes `valuation_date` a separate immutable key column; see OD-P1C4-3.)
- **NOT append-only** (verbatim from `position`): `valuation` is **NOT** in `APPEND_ONLY_TABLES` and gets **NO** `irp_prevent_mutation` trigger — the FR protocol *requires* close-out UPDATEs to `valid_to`/`system_to`. Prior-version **content** immutability is **service-enforced + test-proven**.

## 5. Valuation grain (OD-P1C-F)

**Keyed by `(portfolio_id, instrument_id, valuation_date)`** — **exactly one open mark per key** (multi-source out of scope). The grain dimensions:

1. **portfolio** — `portfolio_id`.
2. **instrument** — `instrument_id`.
3. **valuation_date** — the business date the value is FOR (`valuation_date` Date; immutable logical-key component).
4. **source** — `mark_source` (inert provenance label; part of the captured mark, **not** part of the uniqueness key — a second source for the same key is out of scope, OD-P1C-F).
5. **amount / value** — `mark_value` (Numeric(20,6); the captured mark).
6. **currency** — `currency_code` (inert ISO label).

**Current-head partial-unique (the `position` rule, logical key extended per OD-P1C-F):**
`uq_valuation_current = UNIQUE(tenant_id, portfolio_id, instrument_id, valuation_date) WHERE valid_to IS NULL AND system_to IS NULL` (both `postgresql_where` and `sqlite_where`). At most one version open on **both** axes per (tenant, portfolio, instrument, valuation_date). The FR axes version the **mark** for a fixed `valuation_date`.

## 6. Captured-not-modeled convention (OD-P1C-F) + correction convention

**Captured, never modeled.** A `mark_value` is an authoritative valuation **supplied to** the platform (custodian/admin/manual capture), **not computed** from positions × prices or any pricing/valuation model. There is **no** valuation math, **no** pricing model, **no** price lookup, **no** source-precedence engine, **no** market-value rollup. A valuation is an **independent** FR capture — it does **not** reference or version a `position` (a re-mark does not version the holding; OD-P1C-F).

**Three governed writes (verbatim reuse of the `position` protocol):**

1. **Create** (`create_valuation`) — opens the first mark version for a `(portfolio, instrument, valuation_date)`: `valid_from` = supplied (default now), `valid_to=None`, `system_from=now`, `system_to=None`, `record_version=1`. Emits `VALUATION.CREATE` + one ORIGIN lineage edge.
2. **Effective-dated supersede** (`supersede_valuation`) — a revised mark for the **same** `valuation_date` (e.g. the custodian restated the value): **close-first** — stamp prior open head `valid_to = effective_at`, flush, then add the new open row (`valid_from=effective_at`, `valid_to=None`, `system_from=now`, `system_to=None`, `supersedes_id=prior.id`, `record_version+1`, `valuation_date` carried verbatim). One `now`. Prior content untouched (only `valid_to` closed). Emits `VALUATION.UPDATE` on the close-out and `VALUATION.CREATE` (with ORIGIN edge) on the new row.
3. **As-known correction / restatement** (`correct_valuation`) — a wrong mark for an already-known period: **close-first** — stamp prior `system_to = now`, flush, then add the corrected row over the **same** valid period (`valid_from`/`valid_to`/`valuation_date` copied), `system_from=now` (== prior `system_to`), `system_to=None`, `restatement_reason` set (TR-08), `supersedes_id=prior.id`, `record_version+1`. Emits `VALUATION.CORRECTION` (the restatement) + one ORIGIN edge; the prior close-out is a `VALUATION.UPDATE` with no new edge.

**`valuation_date` is never mutated** (a logical-key peer of `instrument_id`); it is carried forward verbatim. **The prior version's content is never mutated** — only its close-out column (`valid_to` or `system_to`) is stamped, and only by the protocol. No in-place mark edit, no delete (corrections are new rows).

**Prior-head sourcing (cross-tenant safety):** `supersede_valuation`/`correct_valuation` obtain the prior open head **only** via a tenant-predicated current-head lookup (`_current_open(session, *, acting_tenant, portfolio_id, instrument_id, valuation_date)`, or `resolve_valuation` for the correct-this-row case) — **never** from a caller-supplied `supersedes_id` — and set `supersedes_id` **internally**. Mirrors the shipped `position` binder.

## 7. Relationship to portfolio

`portfolio_id` — NOT-NULL GUID FK → `portfolio.id`, indexed. Resolved at the start of every governed write via the shipped `resolve_portfolio(session, portfolio_id, acting_tenant=...)` (explicit `tenant_id == acting_tenant` predicate → raises `PortfolioNotVisible` on a hidden/unknown/cross-tenant id, **pre-commit** — the service-layer fence, the rls-1 lesson). No hierarchy traversal, no ABAC scope filtering (anchored-not-enforced, P6+).

## 8. Relationship to instrument

`instrument_id` — NOT-NULL GUID FK → `instrument.id`, indexed. Resolved via the shipped `resolve_instrument(session, instrument_id, acting_tenant=...)` (same explicit-tenant-predicate fail-closed pattern) → `InstrumentNotVisible`. No `instrument_terms` join, no pricing/terms math.

## 9. Relationship to position (if any)

**None — by design (OD-P1C-F).** No FK to `position`, no shared key beyond the coincidental `(portfolio, instrument)` pair, no derivation, no `quantity × mark` market-value computation. `valuation` and `position` are **independent FR lifecycles** keyed to the same `(portfolio, instrument)` but never linked or computed one from the other — a re-mark does not version the holding, and a re-position does not version the mark. A scope-fence test asserts `valuation` has **no `position_id`/`quantity`/`market_value` column** and the package imports no `position` or market-value-derivation symbol (§16). **This directly satisfies the special-focus fence: the relationship to position creates no derived holdings or market-value calculations.**

## 10. As-of reconstruction

**`reconstruct_valuation_as_of(session, *, acting_tenant, portfolio_id, instrument_id, valuation_date, valid_at, known_at=None)`** — verbatim reuse of `reconstruct_position_as_of`, with the 4-part logical key. Returns the single `Valuation` version satisfying **both** half-open axes for the given `(portfolio, instrument, valuation_date)`, or `None`:

- valid-time: `valid_from <= valid_at AND (valid_to IS NULL OR valid_to > valid_at)`
- system-time: `system_from <= known AND (system_to IS NULL OR system_to > known)`, where `known = known_at or now`.
- carries the explicit `tenant_id == acting_tenant` predicate (fail-closed cross-tenant).

This satisfies REQ-PPM-003 acceptance ("valuations queryable as-of") on both axes: **what was the mark for valuation date D as-of valid time X** (`valid_at=X`, `known_at=now`) **and as-known-at knowledge date Y** (`valid_at=X`, `known_at=Y`). **Single mark only — no aggregation, no rollup, no holdings view, no market value** (those are P1C-5 / P2). This is a read; it computes nothing beyond the bitemporal selection.

## 11. APIs

Thin FastAPI endpoints under a new `apps/backend/src/irp_backend/api/valuations.py` (`prefix="/valuations"`); module-level `require_permission` guard singletons; single end-of-request commit; `uuid.UUID` path params (422 on malformed; 404 indistinguishable for hidden/unknown). **No PUT in-place mutation; no DELETE.**

| Method/path | Guard | Behavior | Errors |
|---|---|---|---|
| `POST /valuations` | `valuation.edit` | create_valuation → 201 | unknown portfolio/instrument → 404 |
| `POST /valuations/{id}/supersede` | `valuation.edit` | supersede_valuation (effective-dated re-mark) → 201 (new version) | unknown id → 404; no open head → 409 |
| `POST /valuations/{id}/correct` | `valuation.edit` | correct_valuation (as-known restatement; body carries `restatement_reason`) → 201 | unknown id → 404 |
| `GET /valuations/{id}` | `valuation.view` | fetch one version row | 404 |
| `GET /valuations` | `valuation.view` | list current-head marks; filters `portfolio_id`/`instrument_id`/`valuation_date` (NO sum/net/aggregate) | — |
| `GET /valuations/as-of` | `valuation.view` | reconstruct_valuation_as_of (query: `portfolio_id`,`instrument_id`,`valuation_date`,`valid_at`,optional `known_at`) → one version or 404 | 422 on bad params |

No model/pricing endpoint, no market-value/rollup/aggregate endpoint, no holdings/position-join endpoint, no PUT/PATCH/DELETE.

## 12. Audit events (R-07 — VALUATION.* / EVT-180 block)

The VALUATION family is **reserved-by-corridor** in `audit_event_taxonomy.md` (PORTFOLIO=EVT-150, TRANSACTION=EVT-160, POSITION=EVT-170 active; **VALUATION=EVT-180 reserved**). P1C-4 **R-07-reserves + activates** at the EVT-180 block (mirroring the `position`/EVT-170 FR pattern):

- `VALUATION.CREATE` = **EVT-180** — initial capture (and the new open row of a supersede).
- `VALUATION.UPDATE` = **EVT-181** — a close-out of a prior head (the `valid_to`/`system_to` stamp on supersede/correct).
- `VALUATION.CORRECTION` = **EVT-182** — an as-known restatement (mirrors `POSITION.CORRECTION` EVT-172); carries `restatement_reason` on the canonical `justification` field + `supersedes_id` in DC-2 `after_value`.

All are **caller-side `event_type` string constants** in a new `irp_shared/valuation/events.py`, passed to the **FROZEN** `audit.service.record_event` (no central enum; "activation" = first emission). `audit/service.py` is **untouched**. Per-tenant chain (PROPRIETARY, no SYSTEM chain). `before/after` = DC-2 metadata only (identifying + controlled-vocab fields + the captured `mark_value`/`currency_code`/`valuation_date`; never full rows or raw input). **Per-operation event count (pinned, mirroring `position`):** create → **1** (`CREATE`); supersede → **2** (`UPDATE` close-out then `CREATE`); correct → **2** (`UPDATE` close-out then `CORRECTION`). **OD-P1C4-1:** keep `VALUATION.CORRECTION` a distinct code (EVT-182) — **recommended** (mirrors the FR `position`/EVT-172 precedent; keeps restatements queryable).

## 13. Entitlement checks

Two **new additive** permission codes (R-07) — **both genuinely new** (neither exists in the seeded catalog yet, unlike `position.view` which pre-existed; this mirrors the `transaction.view`/`transaction.record` mint-both case), seeded via the existing `0002` catalog path + the entitlement bootstrap (no audit-framework code change):

- `valuation.view` — granted to `risk_analyst_1l`, `risk_manager_2l`, **`data_steward`** (+ `platform_admin` via `ALL_CODES`).
- `valuation.edit` — the **maker** governed-write verb (create/supersede/correct); **`data_steward`** + `platform_admin` **only**.

**`data_steward` is the maker** (parallels `position.edit`). **Verb choice (`.edit`, not `.record`):** an FR valuation **is** close-out-updated (supersede/correct stamp `valid_to`/`system_to`), so `.edit` (parallel to `position.edit`) is the right verb. **`auditor_3l` is EXCLUDED** from both (operational client valuations — proprietary-data SoD, matching position/transaction); auditor sees nothing here, not even `.view`. Deny-by-default `require_permission`. A parity test (`test_valuation_permissions_grants_as_ratified`) pins `valuation.view` = {`risk_analyst_1l`, `risk_manager_2l`, `data_steward`, `platform_admin`} and `valuation.edit` = {`data_steward`, `platform_admin`}; `auditor_3l` excluded from both. **OD-P1C4-2:** single `valuation.edit` verb for all three governed writes — **recommended** to fold for P1C-4; a maker-checker split on corrections is a P6+ concern.

## 14. RLS behavior

**Symmetric proprietary tenant isolation** (new migration `0015`, byte-for-byte the `0014` loop): `ENABLE` + `FORCE ROW LEVEL SECURITY`; one policy `tenant_isolation_valuation` with `USING == WITH CHECK == tenant_id::text = current_setting('app.current_tenant', true)`. **NEVER hybrid** — no `SYSTEM_TENANT`, `valuation` does **not** join the closed 5-table P1B-1 hybrid set (asserted unchanged via `pg_policies`). No-context read returns **zero** rows. **No BYPASSRLS app path** (PG tests run under the constrained non-superuser `irp_app`). Cross-tenant `portfolio_id`/`instrument_id`/`supersedes_id` resolution fails closed at the **service layer** (§7/§8/§6). FR close-out UPDATEs are gated by the symmetric `WITH CHECK` like any write.

## 15. Lineage behavior (BR-13)

One MANUAL-`data_source` **ORIGIN** edge per **new physical version row** — `create_valuation`, the new open row of a `supersede_valuation`, and a `correct_valuation` each root **exactly one** ORIGIN edge (`ensure_manual_source` resolve-or-register the shared per-tenant `code='MANUAL'` source + `record_lineage`, fail-closed; `assert_has_lineage`). The prior-head **close-out** roots **no** new edge — it is a `VALUATION.UPDATE` only. The exact `position` per-version lineage rule. **Note:** `mark_source` (a String label on the row) is the *captured provenance* of the mark; the MANUAL `data_source` ORIGIN edge is the *governed-write provenance* — these are distinct and both retained. Co-transactional: add → flush → `record_lineage` → `record_event`; if either rail raises, the whole unit rolls back (CTRL-032).

## 16. Data quality behavior

**Generic evaluators only** (the shipped `not_null` / `allowed_values` — extend by value, never schema): e.g. `mark_value` not-null; `currency_code`/`mark_source`/`price_basis` allowed-values (if a vocab is adopted, as a config `ALLOWED_VALUES` rule's `params['allowed']`, never a new evaluator or DB CHECK). **No domain DQ, no valuation math, no price-reasonableness/tolerance check, no position-vs-valuation tie-out, no FX/market-value cross-foot** (those are calcs / P7). `mark_value` is captured-not-validated beyond not-null. **Scope-fence tests** assert: no `position_id`/`quantity`/`market_value`/`exposure`/`nav` column; no FK to `position` or `price_point`; no derivation function/symbol; and (NOT-append-only proof) a direct close-out UPDATE on a `valuation` row **succeeds** (FR, not IA).

## 17. Tests

**SQLite logic (`packages/shared-python/tests/test_valuation.py`):** FR temporal class; holds-nothing scope fence (no position/quantity/market_value/etc.); `create_valuation` lineage + `VALUATION.CREATE` audit (+ `verify_chain`); `supersede_valuation` (close-first: prior `valid_to` stamped, two rows for the key, new open head, current-head uniqueness holds, prior content unchanged, **new row roots exactly one ORIGIN edge / close-out roots none**, per-op event count [UPDATE+CREATE], **`new.supersedes_id == prior.id` and `new.record_version == prior.record_version + 1`**); `correct_valuation` (prior `system_to` stamped, corrected row same valid period + same `valuation_date`, `restatement_reason`/`supersedes_id`, `VALUATION.CORRECTION`, **content-immutability-on-correction** — refetch prior, content unchanged, only `system_to` moved; **two-part correction-audit payload** — the close-out `VALUATION.UPDATE` carries `before={system_to: None}`/`after[system_to]==prior.system_to`, and the `VALUATION.CORRECTION` carries `justification==restatement_reason` with `after_value` containing `restatement_reason`+`supersedes_id`); **both-axes** `reconstruct_valuation_as_of` (valid-time as-of; as-known-at known_at; current view = latest system-known); **`valuation_date` is a key dimension** (two marks for different `valuation_date`s on the same `(portfolio, instrument)` coexist as two open heads — the partial-unique does NOT collide); current-head partial-unique violation on a second dual-open insert for the same 4-part key; cross-tenant `portfolio`/`instrument`/`valuation` fail-closed; `valuation_date` carried-forward-unchanged through supersede + correct; **NOT-append-only proof** (a close-out UPDATE succeeds); fail-closed audit rollback (monkeypatch `record_event`); no-derivation/no-position-link scope fence (no `position_id`/`quantity`/`market_value` symbol); CTRL-012 no-silent-write (every governed path emits ≥1 `VALUATION.*`); import-direction (`valuation → {portfolio, reference, rails}` only — **no `position` import**).

**PG (`packages/shared-python/tests/test_valuation_pg.py`, under `irp_app`):** tenant isolation; no-context → zero rows; symmetric + FORCE policy assertion; closed 5-table hybrid set unchanged; FR reconstruction under FORCE RLS; current-head partial-unique (4-part key) enforced in PG; cross-tenant FK service-layer reject; forged-tenant INSERT denied (42501 WITH CHECK); **NOT-append-only positive proof** (a raw close-out `UPDATE` of `valid_to`/`system_to` returns `rowcount == 1` — permitted; no P0001 trigger — mirroring `test_position_pg`). **No** P0001 trigger test (FR, not IA).

**Endpoint (`apps/backend/tests/test_valuation_endpoint.py`):** create 201 + audit; supersede books a new version; correct books a restatement; denied without `valuation.edit`; viewer cannot edit; unknown portfolio/instrument → 404; get + 404; bad uuid → 422; supersede with no open head → 409; as-of query returns the right version (both axes) + 422 on bad params; list filter (incl. `valuation_date`); no PUT/DELETE content-edit endpoint (405); `auditor_3l` cannot view.

**Entitlement parity (`test_entitlement_bootstrap.py`):** `valuation.view` = {risk_analyst_1l, risk_manager_2l, data_steward, platform_admin}; `valuation.edit` = {data_steward, platform_admin}; `auditor_3l` excluded from both.

## 18. Acceptance criteria

1. `valuation` (ENT-013) built FR (mixin + `__temporal_class__`), migration `0015_valuation` (`revision="0015_valuation"`, `down_revision="0014_position"` — the current head), `alembic check` drift-clean; the migration defines **no** `APPEND_ONLY_TABLES`/`irp_prevent_mutation` trigger loop (only the symmetric RLS loop), so `valuation` is **not** append-only.
2. Create / supersede / correct honor close-first + one-`now`; prior versions' content never mutated; `valuation_date` carried forward unchanged; current-head partial-unique on the 4-part key holds; corrections carry `restatement_reason` + `supersedes_id`.
3. `reconstruct_valuation_as_of` returns the correct mark on **both** axes for any past as-of/known date, per `(portfolio, instrument, valuation_date)` (REQ-PPM-003 valuation conjunct) — concretely: `reconstruct_valuation_as_of(valid_at=X, known_at=Y_before_correction)` returns the **pre-correction** mark; `reconstruct_valuation_as_of(valid_at=X, known_at=None)` returns the **latest system-known (corrected)** mark; and an effective-dated re-mark is selected by `valid_at` across the supersede boundary (mirroring the position `test_reconstruct_known_at_and_current_view` precedent).
4. Captured-not-modeled: no `quantity × mark`, no pricing/valuation model, no price lookup, no source-precedence engine; `mark_source` is an inert label, not a FK — scope-fence tests green.
5. No position link / no market-value rollup: no `position_id` FK, no `quantity`/`market_value` column, no holdings-view/aggregation/`dataset_snapshot`/CA-application — scope-fence tests assert column + symbol absence.
6. `VALUATION.CREATE/UPDATE/CORRECTION` (EVT-180/181/182) emitted caller-side; `audit/service.py` untouched; per-tenant chain verifies.
7. `valuation.view`/`valuation.edit` minted additively (both new); `data_steward` maker; `auditor_3l` excluded; parity-tested.
8. Symmetric RLS + FORCE; never hybrid; closed hybrid set unchanged; cross-tenant FK fail-closed; no BYPASSRLS; one MANUAL ORIGIN edge per new version; fail-closed rollback.
9. `make check` green; PG validation (upgrade → drift → valuation RLS/FR tests under `irp_app` → downgrade) green; CI step added.
10. 8-lens UltraCode review: 0 unresolved block. REQ-PPM-003 status updated per OD-P1C4-5.

## 19. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Market-value-rollup leakage** — a `position` FK or `quantity`/`market_value` column creeps in, enabling `qty × mark`. | OD-P1C-F (no position link); scope-fence test asserts absence of `position_id`/`quantity`/`market_value`; import-direction test forbids importing `position`. |
| R2 | **Modeled-not-captured drift** — a pricing/valuation computation sneaks in. | `mark_value` is a supplied input; no calc symbol; `mark_source` is a label not a market-data FK; scope-fence + import-direction tests. |
| R3 | **`valuation_date` vs `valid_from` confusion** — collapsing the logical-key date into the valid-time axis would lose the "many dates per instrument" grain. | OD-P1C4-3: `valuation_date` is a separate immutable Date key column (OD-P1C-F); tests prove two `valuation_date`s coexist + `valuation_date` carried forward unchanged. |
| R4 | **Multi-source collision** — two marks for the same key from different sources. | OD-P1C-F resolved: exactly one mark per key in P1C; `mark_source` not in the uniqueness key; a second source is out of scope (documented, not an implicit capability). |
| R5 | **FR/IA confusion** — adding `valuation` to `APPEND_ONLY_TABLES` / a trigger would break close-out UPDATEs. | Explicit NOT-append-only positive test; migration comments; review lens. |
| R6 | **Transient dual-open** current-head uniqueness violation. | Close-first ordering (proven in `position`/`instrument_terms`); PG + SQLite uniqueness tests on the 4-part key. |
| R7 | **Holdings-view scope bleed** — an aggregating/rollup read sneaks in. | Only single-valuation reads; `GET /valuations/as-of` is one mark, no aggregation; fence test; P1C-5 owns views. |

## 20. Controls impacted

CTRL-001 (tests-before-completion), CTRL-004 (data-dictionary fields), CTRL-005 (data-changing actions emit audit), CTRL-006 (lineage per governed write), CTRL-011 (deny-by-default + tenant isolation + RLS; `auditor_3l` excluded), CTRL-012 (no audit bypass), CTRL-032 (fail-closed audit rollback), and **CTRL-017 with the FR reading**: temporal-class **declared** (`FULL_REPRODUCIBLE`) ✓; append-only immutability **does NOT apply** to FR — `valuation` is **not** in `APPEND_ONLY_TABLES` and has **no** P0001 trigger; prior-version content immutability is **service-enforced + test-proven** (the PG close-out-UPDATE `rowcount==1` proof). `valuation` is the **third exercised FR entity** (after `instrument_terms` P1B-3 + `position` P1C-3) and the **second FR domain entity** — no new temporal infrastructure, only domain columns + the FR lifecycle.

## 21. Documentation updates (in the BUILD slice, not this plan)

The P1C-4 **build** will additively update: `04_data_model/canonical_data_model_standard.md` (ENT-013 → REALIZED in P1C-4, migration `0015`); `04_data_model/temporal_reproducibility_standard.md` (§2A ENT-013 BUILT — second FR domain entity); `04_data_model/audit_event_taxonomy.md` (VALUATION family row, EVT-180/181/182 ACTIVATED, FR create/update/correction, `audit/service.py` FROZEN); `02_requirements/requirements_backbone.md` + `requirements_traceability_matrix.md` (REQ-PPM-003 — valuation conjunct delivered; status per OD-P1C4-5); `06_security/entitlement_sod_model.md` §5B (valuation.view/edit row; **both newly minted**; data_steward maker; auditor_3l excluded); `09_compliance_controls/control_matrix_skeleton.md` (P1C-4 coverage note — CTRL-001/004/005/006/011/012/017/032, **second FR domain entity, NOT append-only, captured-not-modeled**); `08_testing_qa/ci_enforcement_overview.md` (P1C-4 prose + the new Valuation RLS/FR CI step). **This planning slice creates only this plan doc.**

## 22. Whether P1C-4 is ready to implement

**Yes — ready, pending sign-off on §23 open decisions.** The FR protocol is shipped and proven twice (`instrument_terms` P1B-3, `position` P1C-3); the upstream FKs (`portfolio`, `instrument`) and their fail-closed resolvers exist; the rails are in place; the grain + captured-not-modeled stance + single-mark-per-key are ratified (OD-P1C-F); the EVT-180 corridor is reserved; the entitlement mint pattern is established. The only pre-build items are the OD-P1C4-* decisions below (each has a recommended default). No upstream dependency is missing.

## 23. Open decisions (sign-off before build)

| ID | Decision | Recommendation | Status |
|---|---|---|---|
| **OD-P1C4-1** | `VALUATION.CORRECTION` a distinct code (EVT-182) vs fold into `VALUATION.UPDATE`. | **Distinct EVT-182** (mirrors FR `position`/EVT-172; keeps restatements queryable). | ✅ Approved |
| **OD-P1C4-2** | Permission shape: single `valuation.edit` for create/supersede/correct vs split a `valuation.correct`; both codes newly minted. | **Both newly minted; single `valuation.edit`** (maker=`data_steward`); maker-checker on corrections → P6+. | ✅ Approved |
| **OD-P1C4-3** | `valuation_date` as a separate immutable logical-key Date column (OD-P1C-F) vs reuse `valid_from` (the position OD-P1C3-4 approach). | **Separate immutable `valuation_date`** (per OD-P1C-F — needed to hold marks for many dates per `(portfolio, instrument)`, each bitemporally versioned). | ✅ Approved |
| **OD-P1C4-4** | `currency_code`/`price_basis` required vs nullable opaque capture; include `price_basis`. | **`mark_value` NOT NULL; `currency_code`/`mark_source`/`price_basis` nullable, captured-not-validated** (generic `ALLOWED_VALUES` DQ only if a vocab is adopted); include `price_basis` as an inert optional. | ✅ Approved |
| **OD-P1C4-5** | REQ-PPM-003 → **Done** (both conjuncts realized) vs keep **In-Progress**. | **Done** — the transaction conjunct (P1C-2, immutable) + the valuation conjunct (P1C-4, queryable as-of) jointly satisfy the acceptance; no scope-enforcement clause gates it (unlike REQ-PPM-002's ABAC residual). Alternative: keep In-Progress if a portfolio-scope ABAC residual is deemed to apply. | ✅ Approved |
| **OD-P1C4-6** | Expose a `GET /valuations/as-of` reconstruction endpoint vs keep reconstruction service-only. | **Expose it** (read-only, single-valuation, no aggregation) — needed to demonstrate REQ-PPM-003 "valuations queryable as-of". | ✅ Approved |

**Sign-offs recorded (H-06 Engineering Lead, 2026-06-25):**
- ⚑ **OD-P1C4-1 — ✅ signed off.** Use a **distinct `VALUATION.CORRECTION`** at **EVT-182**. Caller-side only; `audit/service.py` remains **frozen**.
- ⚑ **OD-P1C4-2 — ✅ signed off.** **Mint `valuation.view` and `valuation.edit`.** `data_steward` is the maker/editor role. Maker-checker remains **deferred to P6+**.
- ⚑ **OD-P1C4-3 — ✅ signed off.** Use a **separate immutable `valuation_date`** as a logical-key component. Do **not** reuse `valid_from` as `valuation_date`.
- ⚑ **OD-P1C4-4 — ✅ signed off.** `mark_value` is **NOT NULL**. `currency_code`, `mark_source`, and `price_basis` are **nullable captured fields**. `price_basis` is **captured metadata only**.
- ⚑ **OD-P1C4-5 — ✅ signed off.** **REQ-PPM-003 may move to Done once P1C-4 lands**, because both the transaction and valuation conjuncts are realized. Do **not** imply exposure, pricing, risk, or aggregation scope.
- ⚑ **OD-P1C4-6 — ✅ signed off.** Expose a **read-only single-valuation as-of reconstruction**. Do **not** implement holdings views, aggregation, exposure, market value, or `dataset_snapshot`.

## 24. Exact implementation kickoff prompt

> "Begin P1C-4 implementation only: valuations / FR bitemporal / captured marks. Use the approved plan `10_delivery_backlog/p1c4_implementation_plan.md`. Before coding: read the 4 grounding docs (canonical ENT-013, temporal §2A, audit taxonomy EVT-180, REQ-PPM-003), restate the top-10 invariants, confirm HEAD/git status, confirm not started.
>
> Implement only: (1) `valuation` entity (ENT-013, FR — `FullReproducibleMixin`, `__temporal_class__ = FULL_REPRODUCIBLE`; **NOT** in `APPEND_ONLY_TABLES`, **no** `irp_prevent_mutation` trigger); (2) migration `0015_valuation` (`revision="0015_valuation"`, `down_revision="0014_position"`; symmetric RLS loop + current-head partial-unique `(tenant_id, portfolio_id, instrument_id, valuation_date) WHERE valid_to IS NULL AND system_to IS NULL`; **no** `APPEND_ONLY_TABLES`/append-only trigger loop); (3) `irp_shared/valuation/` package (models/events/service/binder, one-way → {portfolio, reference, rails}; **NO `position` import**); (4) the FR protocol verbatim from `position`: `create_valuation` / `supersede_valuation` (effective-dated re-mark, close-first) / `correct_valuation` (as-known, `restatement_reason`+`supersedes_id`) / `reconstruct_valuation_as_of(valuation_date, valid_at, known_at)`; `valuation_date` is an immutable logical-key Date column carried forward verbatim; (5) `VALUATION.CREATE/UPDATE/CORRECTION` (EVT-180/181/182) caller-side constants — `audit/service.py` FROZEN; (6) mint the TWO new codes `valuation.view` + `valuation.edit` + grant (data_steward maker holds both; risk tiers hold view; auditor_3l excluded); (7) thin endpoints (create/supersede/correct/get/list/as-of; no PUT/PATCH content-edit, no DELETE); (8) one MANUAL-source ORIGIN edge per new physical version; (9) symmetric RLS; (10) `mark_value` captured (never recomputed); (11) `mark_source` an inert label (NOT a market-data FK); (12) tests (SQLite logic + PG-under-`irp_app` + endpoint + parity), incl. the NOT-append-only positive test, both-axes reconstruction, and the two-`valuation_date`s-coexist test; (13) the §21 doc/control updates.
>
> Strict exclusions: NO valuation model / pricing model / valuation math; NO price lookup; NO market-data ingestion; NO market value rollup (no `position` FK, no `quantity`, no `quantity × mark`); NO exposure aggregation; NO holdings view (single-valuation reads only); NO dataset_snapshot; NO corporate-action application; NO cashflow engine; NO risk/performance/reporting/dashboards/SSO; NO P1C-5/6 or P2+.
>
> Then run an 8-lens UltraCode adversarial review (Product, Architect, Data, Security/RLS, Audit/Controls, Lineage/DQ, QA, Scope), fix in-scope findings, run `make check`, validate the migration on Postgres if available, and do NOT commit until I approve. Return the standard 13-item report."

---

### Special-focus conformance (the user's emphasis, restated)

- **FR / bitemporal** — §4 (FR mixin, both axes, `__temporal_class__`), reusing the proven `position`/`instrument_terms` protocol.
- **Captured marks, not computed** — §6/§9 (OD-P1C-F; `mark_value` supplied, no valuation math).
- **No valuation model / no pricing model** — §2/§6 (P2).
- **No price lookup** — §3/§9 (`mark_source` is a label, not a market-data/`price_point` FK).
- **No market data ingestion** — §2 (P2).
- **No market value rollup** — §2/§9/§16/§19-R1 (no `position` FK, no `quantity`, no `quantity × mark`, no `market_value` column).
- **No exposure aggregation** — §2 (P2).
- **No dataset_snapshot** — §2 (OD-P1C-G, P2).
- **No holdings view** — §10/§11 (single-valuation reads only; views → P1C-5).
- **No corporate-action application** — §2 (P2+).
- **Relationship to position must not create derived holdings or market-value calculations** — §9: **no `position` FK, no shared key beyond coincidence, no `quantity × mark`**; independent FR lifecycles (OD-P1C-F); scope-fence + import-direction tests forbid a `position` import / `quantity`/`market_value` column.
