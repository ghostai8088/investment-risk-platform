# P1C-3 Implementation Plan — Position Capture (FR bitemporal, captured directly)

## Document Control

| Field | Value |
|---|---|
| Document ID | P1C3-IMPL-PLAN |
| Version | 1.0 (sign-offs recorded; OD-P1C3-1..5 approved 2026-06-25) |
| Status | Approved for build — planning only; no code, no migration, not implemented (build on explicit kickoff) |
| Owner | Platform Engineering |
| Approver | H-06 Engineering Lead |
| Created | 2026-06-24 |
| Related documents | `10_delivery_backlog/p1c_implementation_plan.md` (master), `10_delivery_backlog/p1c2_implementation_plan.md` (sibling), `10_delivery_backlog/p1c0_decision_record.md` (OD-P1C-*), `04_data_model/canonical_data_model_standard.md` (ENT-011), `04_data_model/temporal_reproducibility_standard.md` (§2A FR), `04_data_model/audit_event_taxonomy.md` (EVT-170), `02_requirements/requirements_backbone.md` (REQ-PPM-002) |
| Supported build rules | BR-6, BR-9, BR-10, BR-11, BR-12, BR-13, BR-16, BR-17, BR-19 |
| Decisions inherited | AD-005 (§2A selective bitemporality), AD-013-R1 (hybrid closed set), AD-017 (P1C capture-only), OD-P1C-A/B (ABAC anchor), OD-P1C-D (position grain), OD-P1C-E (captured-not-derived), OD-P1C-F (valuation boundary) |

**Precedent reused verbatim:** the P1B-3 `instrument_terms` FR protocol (the platform's first persisted bitemporal entity) — `FullReproducibleMixin`, create → effective-dated supersede → as-known correction, `reconstruct_*_as_of(valid_at, known_at)` on both axes, one-`now`-per-op, close-first ordering, current-head partial-unique, **NOT append-only**. P1C-3 is the **second** persisted FR entity and the **first FR DOMAIN entity**.

---

## 1. Requirements included

- **REQ-PPM-002 — Position master (as-of)** (currently **Draft**): "Single source of holdings for all risk; positions keyed to instrument + portfolio, bitemporal; a position is reconstructable for any past as-of date." P1C-3 moves REQ-PPM-002 → **In-Progress** (the capture + as-of-reconstruction conjunct delivered). **It is NOT closeable to Done in P1C-3:** the residual open conjunct is **portfolio-scope ABAC enforcement** (anchored-not-enforced, → P6+, per the entitlement §5B anchor) plus any downstream consumers; the RTM update (§21) names this explicitly, mirroring how P1C-2 spelled out REQ-PPM-003's open valuation conjunct. REQ-PPM-002 is a stated dependency of REQ-PPM-003/004 — building it unblocks the chain without closing them.
- **AD-017 conformance** — position is a P1C **capture-only** domain entity: captured / as-of-reconstructable, **not** derived analytics.
- **Temporal §2A (AD-005)** — first realization of an FR **domain** entity (positions ENT-011 are listed FR in §2A); proves the FR protocol generalizes beyond reference data.
- **The cross-cutting rails** — symmetric RLS (BR-17), co-transactional fail-closed audit + hash chain (BR-12), MANUAL-source lineage per governed write (BR-13), deny-by-default entitlements (BR-11), `__temporal_class__` declared (BR-19), AI-agent logging readiness (BR-16).

## 2. Requirements excluded (and where they live)

| Excluded | Why / where it lives |
|---|---|
| Valuations / marks (ENT-013, REQ-PPM-003 valuation conjunct) | **P1C-4** (FR, same protocol). A position carries **no** market value / price / mark column. |
| Holdings / as-of holdings **views** | **P1C-5**. P1C-3 ships only a single-position read + a single-position as-of reconstruction (read-only, no aggregation/rollup — see §10/§11). |
| Market value calculation / pricing / price lookup | **P1C-4+ / P2** (AD-017/AD-014). No pricing, no `price_point`, no market-data join. |
| Market-data ingestion (ENT-020–025) | **P2** (AD-014). |
| Exposure aggregation (ENT-014, REQ-PPM-004) | **P2** (AD-014/AD-017). No netting, no rollup, no aggregate table. |
| `dataset_snapshot` | **P2** (OQ-013a, AD-017). |
| Risk calculations / portfolio performance | **P2+**. |
| Transaction → position **derivation engine** | **Deferred / not in P1C** (OD-P1C-E). Positions are captured directly; no derivation FK, no derivation function, no cashflow engine. |
| Corporate-action application | **P2+** (OD-P1B-B / AD-017). No CA-to-position application. |
| Cashflow engine | **P2+**. |
| Reporting / dashboards | later phases. |
| Real SSO | deferred (AD-007; dev header shim is not a boundary). |
| P1C-4 / P1C-5 / P1C-6 and all P2+ | separate, later, individually-planned + approved slices. |

## 3. Proposed entity / entities

**One new table: `position` (ENT-011).** No child tables, no association tables, no derived/aggregate tables.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | GUID (PK) | no | `PrimaryKeyMixin` |
| `tenant_id` | GUID | no | `TenantMixin`; symmetric RLS axis |
| `valid_from` | DateTime(tz) | no | `FullReproducibleMixin`; **the business as-of / valid date** of this version (see §5/§10) |
| `valid_to` | DateTime(tz) | yes | NULL = open in valid time |
| `system_from` | DateTime(tz) | no | knowledge-time open |
| `system_to` | DateTime(tz) | yes | NULL = open in system time |
| `portfolio_id` | GUID FK→`portfolio.id` | no | indexed; resolved tenant-filtered (§7) |
| `instrument_id` | GUID FK→`instrument.id` | no | indexed; resolved tenant-filtered (§8) |
| `quantity` | Numeric(28,8) | no | **signed** holding (long > 0, short < 0); the grain measure (§5) |
| `cost_basis` | Numeric(20,6) | yes | **opaque captured reference** (OD-P1C-D); never recomputed; **not** a market value (open decision OD-P1C3-3) |
| `quantity_unit` | String(20) | yes | controlled-vocab capture (e.g. `SHARES`/`UNITS`/`PAR`); if validated, only a generic `ALLOWED_VALUES` rule whose `params['allowed']` is a config value — never a new evaluator or DB CHECK |
| `position_source` | String(150) | yes | free-text provenance label (e.g. `CUSTODIAN_FILE`); inert capture |
| `restatement_reason` | String(255) | yes | set **only** on a correction (TR-08); rides the canonical `justification` audit field |
| `supersedes_id` | GUID FK→`position.id` | yes | self-FK link to the version this row supersedes/corrects |
| `record_version` | Integer | no | default 1; increments on supersede/correct (mirrors `instrument_terms`) |

**Mixin stack (verbatim reuse):** `class Position(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base)`, `__tablename__ = "position"`, `__temporal_class__ = TemporalClass.FULL_REPRODUCIBLE`.

**Holds nothing it should not:** **no** `market_value`/`price`/`mark`/`valuation`/`nav`/`exposure`/`pnl`/`unrealized`/`fx_rate` column, **no** `transaction_id` FK, **no** lot/tax-lot column, **no** aggregate/rollup column. A scope-fence test pins these absences (§16).

## 4. Temporal classification

**FR — Full Reproducible / bitemporal** (`TemporalClass.FULL_REPRODUCIBLE = "FR"`), reusing `FullReproducibleMixin` (`valid_from`/`valid_to` + `system_from`/`system_to`, all `DateTime(timezone=True)`). `__temporal_class__` declared (BR-19).

- **Valid-time axis** (`valid_from`/`valid_to`): the business as-of period the holding is effective for.
- **System-time axis** (`system_from`/`system_to`): when the platform knew it (knowledge time); enables as-known restatement.
- **NOT append-only (the load-bearing distinction from P1C-2 transaction):** `position` is **NOT** in `APPEND_ONLY_TABLES` and gets **NO** `irp_prevent_mutation` trigger — the FR protocol *requires* UPDATEs to close-out columns (`valid_to`, `system_to`). Prior-version **content** immutability is **service-enforced + test-proven** (only close-out columns are ever updated, and only by the write protocol), exactly as `instrument_terms`. This is the correct CTRL-017 reading for FR (see §20).

## 5. Position grain (OD-P1C-D)

**Aggregated by `(portfolio_id, instrument_id)`** — one current-head FR version per portfolio+instrument, **NOT lot-level** and **NOT tax-lot**. The grain dimensions:

1. **portfolio** — `portfolio_id` (the holder).
2. **instrument** — `instrument_id` (the held security).
3. **as-of / valid date** — carried by `valid_from` (the FR valid-time axis); a new business as-of date for the same portfolio+instrument is an **effective-dated supersede** (§6). (OD-P1C3-4: reuse `valid_from` as the as-of date rather than add a redundant `position_date` Date column — recommended, for exact protocol reuse.)
4. **signed quantity** — `quantity` is signed: **long = positive, short = negative** (no separate `side` column; OD-P1C-D).

**Current-head partial-unique (the same `instrument_terms` RULE, with the logical key generalized per OD-P1C-D):**
`instrument_terms` uses `uq_instrument_terms_current = (tenant_id, instrument_id) WHERE valid_to IS NULL AND system_to IS NULL`. P1C-3 reuses the **rule** (one version open on **both** axes per logical key) with the logical key generalized to the position grain:
`uq_position_current = UNIQUE(tenant_id, portfolio_id, instrument_id) WHERE valid_to IS NULL AND system_to IS NULL` (both `postgresql_where` and `sqlite_where`). At most one version open on both axes per (tenant, portfolio, instrument).

## 6. Captured-not-derived convention (OD-P1C-E) + correction convention

**Captured directly, never derived.** A position version is an authoritative as-of holding **supplied to** the platform (manual/custodian capture), **not computed** from the P1C-2 transaction log. There is **no** transaction→position derivation engine, **no** derivation FK, **no** cashflow/settlement engine, **no** corporate-action application. Positions and transactions are two **independent** captures (OD-P1C-E); a derivation/reconciliation engine is a future calc, explicitly out of scope.

**Three governed writes (verbatim reuse of the `instrument_terms` protocol):**

1. **Create** (`create_position`) — opens the first version for a (portfolio, instrument): `valid_from` = supplied as-of date (default now), `valid_to=None`, `system_from=now`, `system_to=None`, `record_version=1`. Emits `POSITION.CREATE` + one ORIGIN lineage edge.
2. **Effective-dated supersede** (`supersede_position`) — a new business as-of value (e.g. the holding changed): **close-first** — stamp prior open head `valid_to = effective_at`, flush, then add the new open row (`valid_from=effective_at`, `valid_to=None`, `system_from=now`, `system_to=None`, `supersedes_id=prior.id`, `record_version+1`). One `now`. Prior content untouched (only `valid_to` closed). Emits `POSITION.UPDATE` on the close-out and `POSITION.CREATE` (with ORIGIN edge) on the new row — mirroring `instrument_terms` (the close-out is an UPDATE event with no new edge; the new physical row roots one edge).
3. **As-known correction / restatement** (`correct_position`) — a wrong value for an already-known period: **close-first** — stamp prior `system_to = now`, flush, then add the corrected row over the **same** valid period (`valid_from`/`valid_to` copied), `system_from=now` (== prior `system_to`), `system_to=None`, `restatement_reason` set (TR-08), `supersedes_id=prior.id`, `record_version+1`. Emits `POSITION.CORRECTION` (the restatement) + one ORIGIN edge; the prior close-out is a `POSITION.UPDATE` with no new edge.

**Prior-head sourcing (cross-tenant safety):** `supersede_position`/`correct_position` obtain the prior open head **only** via a tenant-predicated current-head lookup (a `_current_open(session, *, acting_tenant, portfolio_id, instrument_id)` helper, or `resolve_position` for the correct-this-row case) — **never** from a caller-supplied `supersedes_id` — and set `supersedes_id` **internally** from the resolved prior row. This mirrors `instrument_terms` (where `supersedes_id` is never resolved from caller input) and keeps the cross-tenant fence at the service layer (§14); a `correct_position` against a non-visible row raises `PositionNotVisible`, and a supersede/correct with no open head raises a `NoCurrentTerms`-analog (`NoCurrentPosition`).

**The original/prior version is never mutated in content** — only its close-out column (`valid_to` or `system_to`) is stamped, and only by the protocol. No in-place quantity edit, no delete (corrections are new rows).

## 7. Relationship to portfolio

`portfolio_id` — NOT-NULL GUID FK → `portfolio.id` (the P1C-1 EV entity), indexed. Resolved at the start of every governed write via the **shipped** `resolve_portfolio(session, portfolio_id, acting_tenant=...)`, which carries an **explicit `tenant_id == acting_tenant` predicate** → raises `PortfolioNotVisible` on a hidden/unknown/cross-tenant id, **pre-commit** (RLS `WITH CHECK` gates only the writing row's own `tenant_id`, so the service-layer predicate is the real cross-tenant fence — the established rls-1 lesson). No hierarchy traversal, no ABAC scope filtering (anchored-not-enforced, P6+).

## 8. Relationship to instrument

`instrument_id` — NOT-NULL GUID FK → `instrument.id` (the P1B-3 EV identity head), indexed. Resolved via the **shipped** `resolve_instrument(session, instrument_id, acting_tenant=...)` (same explicit-tenant-predicate fail-closed pattern) → `InstrumentNotVisible`. No `instrument_terms` join, no pricing/terms math.

## 9. Relationship to transaction (if any)

**None — by design (OD-P1C-E).** No FK to `transaction`, no derivation from the transaction log, no shared key, no reconciliation. `position` and `transaction` are independent captures keyed to the same (portfolio, instrument) pair but are never linked or derived one from the other in P1C. A scope-fence test asserts `position` has no `transaction_id`/derivation column and the package imports no transaction-derivation symbol (§16).

## 10. As-of reconstruction

**`reconstruct_position_as_of(session, *, acting_tenant, portfolio_id, instrument_id, valid_at, known_at=None)`** — verbatim reuse of `reconstruct_terms_as_of`. Returns the single `Position` version satisfying **both** half-open axes, or `None`:

- valid-time: `valid_from <= valid_at AND (valid_to IS NULL OR valid_to > valid_at)`
- system-time: `system_from <= known AND (system_to IS NULL OR system_to > known)`, where `known = known_at or now` (TR-04 default = current view).
- carries the explicit `tenant_id == acting_tenant` predicate (fail-closed cross-tenant).

This directly satisfies REQ-PPM-002 acceptance ("reconstructable for any past as-of date") on both axes: **what was the position as-of business date X** (`valid_at=X`, `known_at=now`) **and as-known-at knowledge date Y** (`valid_at=X`, `known_at=Y`). **Single-position only — no aggregation, no rollup, no holdings view** (those are P1C-5). This is a read; it computes nothing beyond the bitemporal selection.

## 11. APIs

Thin FastAPI endpoints under a new `apps/backend/src/irp_backend/api/positions.py` (`prefix="/positions"`); module-level `require_permission` guard singletons; single end-of-request commit; `uuid.UUID` path params (422 on malformed; 404 indistinguishable for hidden/unknown). **No PUT in-place mutation of content; no DELETE.**

| Method/path | Guard | Behavior | Errors |
|---|---|---|---|
| `POST /positions` | `position.edit` | create_position → 201 | unknown portfolio/instrument → 404 |
| `POST /positions/{id}/supersede` | `position.edit` | supersede_position (effective-dated) → 201 (new version) | unknown id → 404 |
| `POST /positions/{id}/correct` | `position.edit` | correct_position (as-known restatement; body carries `restatement_reason`) → 201 | unknown id → 404 |
| `GET /positions/{id}` | `position.view` | fetch one version row | 404 |
| `GET /positions` | `position.view` | list current-head positions, filters `portfolio_id`/`instrument_id` (NO sum/net/aggregate) | — |
| `GET /positions/as-of` | `position.view` | reconstruct_position_as_of (query: `portfolio_id`,`instrument_id`,`valid_at`,optional `known_at`) → one version or 404 | 422 on bad params |

No derivation endpoint, no holdings/rollup endpoint, no valuation/price endpoint, no PUT/PATCH content-edit, no DELETE.

## 12. Audit events (R-07 — POSITION.* / EVT-170 block)

The POSITION family is **reserved-by-corridor but not yet specified** in `audit_event_taxonomy.md` (PORTFOLIO=EVT-150 active, TRANSACTION=EVT-160 active, **POSITION=EVT-170 reserved**, VALUATION=EVT-180 reserved). P1C-3 **R-07-reserves + activates** at the EVT-170 block:

- `POSITION.CREATE` = **EVT-170** — initial capture (and the new open row of a supersede).
- `POSITION.UPDATE` = **EVT-171** — a close-out of a prior head (the `valid_to`/`system_to` stamp on supersede/correct).
- `POSITION.CORRECTION` = **EVT-172** — an as-known restatement (mirrors `REFERENCE.CORRECTION` EVT-142, the FR precedent); carries `restatement_reason` on the canonical `justification` field + `supersedes_id` in DC-2 `after_value`.

All are **caller-side `event_type` string constants** in a new `irp_shared/position/events.py`, passed to the **FROZEN** `audit.service.record_event` (no central enum; "activation" = first emission). `audit/service.py` is **untouched**. Per-tenant chain (PROPRIETARY, no SYSTEM chain). `before/after` = DC-2 metadata only (identifying + controlled-vocab fields; signed `quantity`; never full rows or raw input).

**Per-operation event count + payload (pinned, mirroring `instrument_terms`):**
- `create_position` → exactly **1** event: `POSITION.CREATE` (`after_value` = the new row's DC-2 summary; one ORIGIN edge).
- `supersede_position` → exactly **2**, in order: `POSITION.UPDATE` on the prior-head close-out (`before_value = {valid_to: null}`, `after_value = {valid_to: effective_at}`; **no** new edge) then `POSITION.CREATE` on the new open row (`after_value` summary; one ORIGIN edge).
- `correct_position` → exactly **2**, in order: `POSITION.UPDATE` on the prior-head close-out (`before_value = {system_to: null}`, `after_value = {system_to: now}`; no new edge) then `POSITION.CORRECTION` on the corrected row (`justification = restatement_reason`; `after_value` carries `restatement_reason` + `supersedes_id`; `before_value` left `None` — the close-out UPDATE carries the boundary diff; one ORIGIN edge).

`verify_chain` holds across all paths. **OD-P1C3-1:** keep `POSITION.CORRECTION` a distinct code (EVT-172) rather than folding into `POSITION.UPDATE` — **recommended** (parallels the FR `instrument_terms`/EVT-142 precedent; keeps restatements queryable).

## 13. Entitlement checks

**Mint vs wire (corrected per review — `position.view` already exists).** `position.view` is a **pre-existing seeded catalog placeholder** (`entitlement/bootstrap.py` PERMISSIONS, already granted to `risk_analyst_1l`, `risk_manager_2l`, and `platform_admin` via `ALL_CODES` — but **not** yet to `data_steward`). `position.edit` is **the one genuinely NEW code** minted in P1C-3. This mirrors the `portfolio.view`/`portfolio.edit` precedent exactly (OD-P1C1-3 wired the seeded `portfolio.view` placeholder + minted/granted `portfolio.edit` to the `data_steward` maker). So P1C-3:

- **`position.view`** (existing) — P1C-3 **wires** it by **additively granting the `data_steward`** maker (so the maker reads its own writes); the existing recipients (`risk_analyst_1l`, `risk_manager_2l`, `platform_admin`) are **unchanged**. Resulting set: {`risk_analyst_1l`, `risk_manager_2l`, `data_steward`, `platform_admin`}.
- **`position.edit`** (NEW, additive R-07) — the **maker/recorder** governed-write verb (create/supersede/correct); **`data_steward`** + `platform_admin` **only**.

**`data_steward` is the maker/recorder** (parallels `portfolio.edit`). **Verb choice (`.edit`, not `.record`):** an FR position **is** close-out-updated (supersede/correct stamp `valid_to`/`system_to`), so `.edit` (parallel to `portfolio.edit`) is the right verb — distinct from the IA `transaction.record` (append-only, never edited). **`auditor_3l` is EXCLUDED** from both (operational client holdings — proprietary-data SoD, matching the transaction precedent); auditor sees nothing here, not even `.view`. Deny-by-default `require_permission`. A parity test (`test_position_permissions_grants_as_ratified`) pins `position.view` = {`risk_analyst_1l`, `risk_manager_2l`, `data_steward`, `platform_admin`} (asserting the existing three-recipient set is preserved and the `data_steward` grant is the only view-side delta) and `position.edit` = {`data_steward`, `platform_admin`}. **OD-P1C3-2:** single `position.edit` verb for all three governed writes (vs splitting a separate `position.correct` for 4-eyes on restatements) — **recommended** to fold for P1C-3; a maker-checker split on corrections is a P6+ concern.

## 14. RLS behavior

**Symmetric proprietary tenant isolation** (migration `0014`, byte-for-byte the `0010`/`0012`/`0013` loop): `ENABLE` + `FORCE ROW LEVEL SECURITY`; one policy `tenant_isolation_position` with `USING == WITH CHECK == tenant_id::text = current_setting('app.current_tenant', true)`. **NEVER hybrid** — no `SYSTEM_TENANT`, `position` does **not** join the closed 5-table P1B-1 hybrid set (asserted unchanged via `pg_policies`). No-context read returns **zero** rows. **No BYPASSRLS app path** (PG tests run under the constrained non-superuser `irp_app`, NOSUPERUSER NOBYPASSRLS). Cross-tenant `portfolio_id`/`instrument_id`/`supersedes_id` resolution fails closed at the **service layer** (§7/§8). FR close-out UPDATEs are gated by the symmetric `WITH CHECK` like any write.

## 15. Lineage behavior (BR-13)

One MANUAL-`data_source` **ORIGIN** edge per **new physical version row** — `create_position`, the new open row of a `supersede_position`, and a `correct_position` each root **exactly one** ORIGIN edge (`ensure_manual_source` resolve-or-register the shared per-tenant `code='MANUAL'` source + `record_lineage`, fail-closed; `assert_has_lineage`). The prior-head **close-out** (stamping `valid_to`/`system_to`) roots **no** new edge — it is a `POSITION.UPDATE` only. This is the exact `instrument_terms` per-version lineage rule. Co-transactional: add → flush → `record_lineage` → `record_event`; if either rail raises, the whole unit rolls back (CTRL-032).

## 16. Data quality behavior

**Generic evaluators only** (the shipped `not_null` / `allowed_values` — extend by value, never schema): e.g. `quantity` not-null; `quantity_unit` allowed-values (if vocab adopted). **No domain DQ, no reconciliation, no derivation check, no market-value/PnL check, no transaction-vs-position tie-out** (those are calcs / P7). `cost_basis` is captured-not-validated (opaque, never recomputed). **Scope-fence tests** assert: no `market_value`/`price`/`exposure`/`nav`/`pnl`/`valuation` column; no `transaction_id`/derivation column; no lot/aggregate column; and (NOT-append-only proof) a direct close-out UPDATE on a `position` row **succeeds** (FR, not IA).

## 17. Tests

**SQLite logic (`packages/shared-python/tests/test_position.py`):** FR temporal class (system_from + valid_*; declared `__temporal_class__`); holds-nothing scope fence; `create_position` lineage + `POSITION.CREATE` audit (+ `verify_chain`); `supersede_position` (close-first: prior `valid_to` stamped, two rows, new open head, current-head uniqueness holds, prior content unchanged, `POSITION.UPDATE` + `POSITION.CREATE`); `correct_position` (prior `system_to` stamped, corrected row same valid period, `restatement_reason`/`supersedes_id`, `POSITION.CORRECTION`); **both-axes** `reconstruct_position_as_of` (valid-time as-of; as-known-at known_at); current-head partial-unique violation on a second dual-open insert; cross-tenant `portfolio`/`instrument`/`supersedes` fail-closed; signed-quantity (short = negative) round-trip; **NOT-append-only proof** (a close-out UPDATE succeeds — FR vs the transaction IA guard); fail-closed audit rollback (monkeypatch `record_event`); no-derivation scope fence (no transaction FK / no derivation symbol); import-direction (`position → {portfolio, reference, rails}` only). **Folded from review (mirroring the `instrument_terms` test precedent):** (a) **content-immutability-on-correction** (QA-1) — after `correct_position`, `session.get` the prior row and assert its economic columns (`quantity`/`cost_basis`/…) are byte-for-byte **unchanged** and **only** `system_to` moved (mirrors `test_terms_content_immutability_on_correction`); (b) **per-operation event count + order** (AUD-1) — `create`=1 (`POSITION.CREATE`); `supersede`=2 in order (`POSITION.UPDATE` close-out → `POSITION.CREATE`); `correct`=2 in order (`POSITION.UPDATE` close-out → `POSITION.CORRECTION`); (c) **two-part correction-audit payload** (QA-2) — the close-out `POSITION.UPDATE` has `before_value={system_to: None}` / `after_value[system_to]==prior.system_to`, and the `POSITION.CORRECTION` has `justification==restatement_reason` with `after_value` carrying `restatement_reason`+`supersedes_id` (mirrors `test_correction_audit_payload_tr08`); (d) **no-current-head guard** (QA-5) — a supersede/correct against a (portfolio, instrument) with no open head raises `NoCurrentPosition` (mirrors `test_supersede_without_current_terms_raises`); (e) **CTRL-012 no-silent-write** (AUD-4) — every governed path emits ≥1 `POSITION.*` event.

**PG (`packages/shared-python/tests/test_position_pg.py`, under `irp_app`):** tenant isolation; no-context → zero rows; symmetric + FORCE policy assertion; closed 5-table hybrid set unchanged; FR reconstruction under FORCE RLS; current-head partial-unique enforced in PG; cross-tenant FK service-layer reject; forged-tenant INSERT denied (42501 WITH CHECK). **NOT-append-only positive proof** (QA-4): there is **no** P0001 append-only trigger (FR, not IA) — instead assert the seed row is RLS-visible to `irp_app`, then a raw close-out `UPDATE` of `valid_to`/`system_to` returns **`rowcount == 1`** (the update is *permitted*) — mirrors `test_instrument_terms_not_append_only`, the exact inversion of the transaction P0001 guard test.

**Endpoint (`apps/backend/tests/test_position_endpoint.py`):** create 201 + audit; supersede books a new version; correct books a restatement; denied without `position.edit`; viewer cannot edit; unknown portfolio/instrument → 404; get + 404; bad uuid → 422; as-of query returns the right version (both axes) + 422 on bad params; list filter; no PUT/DELETE content-edit endpoint (405); `auditor_3l` cannot view (no `position.view`).

**Entitlement parity (`test_entitlement_bootstrap.py`):** `position.view` = {risk_analyst_1l, risk_manager_2l, data_steward, platform_admin}; `position.edit` = {data_steward, platform_admin}; `auditor_3l` excluded from both.

## 18. Acceptance criteria

1. `position` (ENT-011) built FR (mixin + `__temporal_class__`), migration `0014`, `alembic check` drift-clean; **not** in `APPEND_ONLY_TABLES`, **no** `irp_prevent_mutation` trigger.
2. Create / supersede / correct honor close-first + one-`now`; prior versions' content never mutated; current-head partial-unique holds; corrections carry `restatement_reason` + `supersedes_id`.
3. `reconstruct_position_as_of` returns the correct version on **both** axes for any past as-of/known date (REQ-PPM-002 acceptance).
4. Captured-not-derived: no `transaction` FK, no derivation engine/function/endpoint; positions and transactions independent (OD-P1C-E) — scope-fence tests green.
5. No market value / pricing / exposure / valuation / holdings-view / aggregation / dataset_snapshot / CA-application / cashflow — scope-fence tests assert column + symbol absence.
6. `POSITION.CREATE/UPDATE/CORRECTION` (EVT-170/171/172) emitted caller-side; `audit/service.py` untouched; per-tenant chain verifies.
7. `position.edit` minted (the one NEW code); the existing `position.view` placeholder grant **extended** to add `data_steward` (the three existing recipients unchanged); `data_steward` maker; `auditor_3l` excluded; parity-tested (view set = {risk_analyst_1l, risk_manager_2l, data_steward, platform_admin}).
8. Symmetric RLS + FORCE; never hybrid; closed hybrid set unchanged; cross-tenant FK fail-closed; no BYPASSRLS; one MANUAL ORIGIN edge per new version; fail-closed rollback.
9. `make check` green; PG validation (upgrade → drift → position RLS/FR tests under `irp_app` → downgrade) green; CI step added.
10. 8-lens UltraCode review: 0 unresolved block.

## 19. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | **FR/IA confusion** — adding `position` to `APPEND_ONLY_TABLES` or an `irp_prevent_mutation` trigger would break the FR close-out UPDATEs. | Explicit "NOT-append-only" positive test (close-out UPDATE succeeds); plan + migration comments call it out; review lens. |
| R2 | **Captured-vs-derived drift** — a future dev wires transaction→position derivation. | OD-P1C-E; no transaction FK; no derivation symbol; scope-fence + import-direction tests. |
| R3 | **Market-value / valuation leakage** — a `market_value`/`price` column creeps in. | Scope-fence test asserts absence; `cost_basis` documented opaque/never-recomputed; valuation explicitly P1C-4. |
| R4 | **Grain creep to lot-level** — tax-lot or per-transaction rows. | OD-P1C-D aggregated grain; current-head partial-unique on (tenant, portfolio, instrument); fence test. |
| R5 | **Transient dual-open** current-head uniqueness violation. | Close-first ordering (proven in `instrument_terms`); flush-before-add; PG + SQLite uniqueness tests. |
| R6 | **As-of/valid-date ambiguity** (business date vs `valid_from`). | OD-P1C3-4: reuse `valid_from` as the as-of date; documented; reconstruction tests pin semantics. |
| R7 | **Holdings-view scope bleed** — an aggregating/rollup read sneaks in. | Only single-position reads; `GET /positions/as-of` is one version, no aggregation; fence test; P1C-5 owns views. |
| R8 | **Reconstruction correctness on both axes.** | Verbatim reuse of `reconstruct_terms_as_of`; both-axes tests incl. as-known-at-past. |

## 20. Controls impacted

CTRL-001 (tests-before-completion), CTRL-004 (data-dictionary fields), CTRL-005 (data-changing actions emit audit), CTRL-006 (lineage per governed write), CTRL-011 (deny-by-default + tenant isolation + RLS; `auditor_3l` excluded), CTRL-012 (no audit bypass), CTRL-032 (fail-closed audit rollback), and **CTRL-017 with the FR reading**: temporal-class **declared** (`FULL_REPRODUCIBLE`) ✓; append-only immutability **does NOT apply** to FR — `position` is **not** in `APPEND_ONLY_TABLES` and has **no** P0001 trigger; prior-version content immutability is **service-enforced + test-proven** (only close-out columns updated, only by protocol). This makes `position` the **second exercised FR entity** (after `instrument_terms` P1B-3) and the **first FR domain entity** — no new temporal infrastructure, only domain columns + the FR lifecycle.

## 21. Documentation updates (in the BUILD slice, not this plan)

The P1C-3 **build** will additively update: `04_data_model/canonical_data_model_standard.md` (ENT-011 → REALIZED in P1C-3, migration `0014`); `04_data_model/temporal_reproducibility_standard.md` (§2A ENT-011 BUILT — first FR domain entity); `04_data_model/audit_event_taxonomy.md` (POSITION family row, EVT-170/171/172 ACTIVATED, FR create/update/correction, `audit/service.py` FROZEN); `02_requirements/requirements_backbone.md` + `requirements_traceability_matrix.md` (REQ-PPM-002 → In-Progress, capture + as-of conjunct; **name the residual open conjunct** = portfolio-scope ABAC enforcement → P6+); `06_security/entitlement_sod_model.md` §5B (position row: **mint `position.edit`** [NEW]; **extend the existing `position.view` grant** to add `data_steward`; data_steward maker; auditor_3l excluded; **note the verb rationale** — `.edit` not `.record` because FR positions are close-out-updated, vs the IA `transaction.record`); `09_compliance_controls/control_matrix_skeleton.md` (P1C-3 coverage note — CTRL-001/004/005/006/011/012/017/032, **first FR domain entity, NOT append-only**); `08_testing_qa/ci_enforcement_overview.md` (P1C-3 prose + the new Position RLS/FR CI step). **This planning slice creates only this plan doc.**

## 22. Whether P1C-3 is ready to implement

**Yes — ready, pending sign-off on §23 open decisions.** The FR protocol is shipped and proven (`instrument_terms`, P1B-3); the upstream FKs (`portfolio`, `instrument`) and their fail-closed resolvers exist; the audit/lineage/RLS rails are in place; the grain + captured-not-derived stance are ratified (OD-P1C-D/E); the EVT-170 corridor is reserved. The only pre-build items are the five OD-P1C3-* decisions below (each has a recommended default). No upstream dependency is missing.

## 23. Open decisions (sign-off before build)

| ID | Decision | Recommendation | Status |
|---|---|---|---|
| **OD-P1C3-1** | `POSITION.CORRECTION` a distinct code (EVT-172) vs fold into `POSITION.UPDATE`. | **Distinct EVT-172** (mirrors FR `instrument_terms`/EVT-142; keeps restatements queryable). | ✅ Approved |
| **OD-P1C3-2** | Permission shape: single `position.edit` for create/supersede/correct vs split a `position.correct`. | **Single `position.edit`** (maker=`data_steward`); maker-checker on corrections → P6+. | ✅ Approved |
| **OD-P1C3-3** | Include `cost_basis` (opaque captured reference, OD-P1C-D) vs defer it. | **Include, opaque, never recomputed**, clearly not a market value; generic DQ only. | ✅ Approved |
| **OD-P1C3-4** | As-of/valid date: reuse `valid_from` vs add a business `position_date` Date column. | **Reuse `valid_from`** (exact protocol reuse; avoids a redundant axis). | ✅ Approved |
| **OD-P1C3-5** | Expose a `GET /positions/as-of` reconstruction endpoint in P1C-3 vs keep reconstruction service-only. | **Expose it** (read-only, single-position, no aggregation) — needed to demonstrate REQ-PPM-002 "reconstructable for any past as-of date". | ✅ Approved |

**Sign-offs recorded (H-06 Engineering Lead, 2026-06-25):**
- ⚑ **OD-P1C3-1 — ✅ signed off.** Use a **distinct `POSITION.CORRECTION`** at the EVT-170 block (EVT-172). Caller-side only; `audit/service.py` remains **frozen**.
- ⚑ **OD-P1C3-2 — ✅ signed off.** Use **one `position.edit`** permission for create/supersede/correct. Maker-checker and correction approval remain **deferred to P6+**.
- ⚑ **OD-P1C3-3 — ✅ signed off.** Include `cost_basis` as an **opaque captured reference value only**. Do **not** compute or use it for performance, tax, or analytics in P1C-3.
- ⚑ **OD-P1C3-4 — ✅ signed off.** Use **`valid_from`** as the position/as-of date. Do **not** add a separate `position_date`.
- ⚑ **OD-P1C3-5 — ✅ signed off.** Expose a **read-only single-position as-of reconstruction** endpoint. Do **not** implement holdings views, aggregation, exposure, market value, or `dataset_snapshot`.

## 24. Exact implementation kickoff prompt

> "Begin P1C-3 implementation only: positions / FR bitemporal / captured directly. Use the approved plan `10_delivery_backlog/p1c3_implementation_plan.md`. Before coding: read the 4 grounding docs (canonical ENT-011, temporal §2A, audit taxonomy EVT-170, REQ-PPM-002), restate the top-10 invariants, confirm HEAD/git status, confirm not started.
>
> Implement only: (1) `position` entity (ENT-011, FR — `FullReproducibleMixin`, `__temporal_class__ = FULL_REPRODUCIBLE`; **NOT** in `APPEND_ONLY_TABLES`, **no** `irp_prevent_mutation` trigger); (2) migration `0014_position` (symmetric RLS loop + current-head partial-unique `(tenant_id, portfolio_id, instrument_id) WHERE valid_to IS NULL AND system_to IS NULL`; **no** append-only trigger); (3) `irp_shared/position/` package (models/events/service/binder, one-way → {portfolio, reference, rails}); (4) the FR protocol verbatim from `instrument_terms`: `create_position` / `supersede_position` (effective-dated, close-first) / `correct_position` (as-known, `restatement_reason`+`supersedes_id`) / `reconstruct_position_as_of(valid_at, known_at)`; (5) `POSITION.CREATE/UPDATE/CORRECTION` (EVT-170/171/172) caller-side constants — `audit/service.py` FROZEN; (6) mint the ONE new code `position.edit` + extend the existing seeded `position.view` grant to add `data_steward` (data_steward maker; auditor_3l excluded; the three existing view recipients unchanged); (7) thin endpoints (create/supersede/correct/get/list/as-of; no PUT/PATCH content-edit, no DELETE); (8) one MANUAL-source ORIGIN edge per new physical version; (9) symmetric RLS; (10) signed quantity; (11) cost_basis opaque (never recomputed); (12) tests (SQLite logic + PG-under-`irp_app` + endpoint + parity), incl. the NOT-append-only positive test (close-out UPDATE succeeds) and both-axes reconstruction; (13) the §21 doc/control updates.
>
> Strict exclusions: NO market value / pricing / price lookup; NO valuation / mark / model; NO exposure aggregation; NO holdings view (single-position reads only); NO dataset_snapshot; NO risk / performance; NO transaction→position derivation engine (no transaction FK); NO corporate-action application; NO cashflow engine; NO reporting/dashboards/SSO; NO P1C-4/5/6 or P2+.
>
> Then run an 8-lens UltraCode adversarial review (Product, Architect, Data, Security/RLS, Audit/Controls, Lineage/DQ, QA, Scope), fix in-scope findings, run `make check`, validate the migration on Postgres if available, and do NOT commit until I approve. Return the standard 13-item report."

---

### Special-focus conformance (the user's emphasis, restated)

- **FR / bitemporal** — §4 (FR mixin, both axes, `__temporal_class__`), reusing the proven `instrument_terms` protocol.
- **Captured directly, not derived** — §6/§9 (OD-P1C-E; no transaction FK, no derivation engine/function).
- **No market value calculation** — §2/§3/§16/§19-R3 (no `market_value`/`price`/`mark` column; `cost_basis` opaque/never-recomputed; valuation is P1C-4).
- **No exposure aggregation** — §2/§16 (no aggregate/rollup; P2).
- **No dataset_snapshot** — §2 (P2).
- **No valuation model** — §2 (P1C-4+).
- **No corporate-action application** — §2 (P2+).
- **No transaction-to-position derivation** — §6/§9 (OD-P1C-E).
- **No holdings view unless explicitly read-only and non-computationally safe** — §10/§11: P1C-3 ships only single-position reads + a single-position as-of reconstruction (read-only, no aggregation/computation). Holdings **views** (multi-position rollups) are **P1C-5**, not built here.
