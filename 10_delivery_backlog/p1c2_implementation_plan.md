# P1C-2 Implementation Plan — Transactions (IA append-only, capture-only)

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1C2-PLAN-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-01 Chief Architect AI (with R-05 Data Architect AI, R-04 Security AI, R-07 Audit/Controls AI) |
| Approver | H-06 Engineering Lead (H-03 Security; H-08 Internal Audit — consulted) |
| Created | 2026-06-23 |
| Related Documents | `p1c0_decision_record.md`, `p1c_implementation_plan.md`, `p1c1_implementation_plan.md` (the portfolio-domain precedent), `p1a4_implementation_plan.md` (the `ingestion_staged_record` IA append-only precedent), `../02_requirements/requirements_backbone.md`, `../02_requirements/requirements_traceability_matrix.md`, `../04_data_model/canonical_data_model_standard.md`, `../04_data_model/temporal_reproducibility_standard.md`, `../04_data_model/audit_event_taxonomy.md`, `../06_security/entitlement_sod_model.md`, `../09_compliance_controls/control_matrix_skeleton.md`, `../11_decision_log/architecture_decision_log.md`, `packages/shared-python/src/irp_shared/portfolio/portfolio.py`, `packages/shared-python/src/irp_shared/reference/instrument.py`, `packages/shared-python/src/irp_shared/ingestion/models.py` |
| Supported Build Rules | BR-3, BR-5, BR-7, BR-11, BR-12, BR-13, BR-17, BR-18, BR-19 |
| Decisions inherited | AD-017 (P1C capture-only domain); AD-005 §2A (transaction ENT-012 = IA); OD-P1C-E (transactions captured independently — positions are NOT derived from them); the P1C-1 domain-package + governed-write patterns. |

> **Purpose.** Realize **ENT-012** `transaction` as an **immutable append-only (IA)** trade/cashflow **event log** — the platform's first **domain IA** entity. Keyed to a `portfolio` + an `instrument`, governed (symmetric RLS, co-transactional audit, MANUAL-source lineage, deny-by-default entitlement), and **two-layer immutable** (the `irp_prevent_mutation` P0001 DB trigger **and** the ORM `before_update`/`before_delete` guard — the `ingestion_staged_record` precedent). **CAPTURE-ONLY** — transactions are recorded, never applied: **no position derivation, no valuation, no exposure aggregation, no cashflow engine, no corporate-action application.** Corrections are **explicit reversal records**, never updates. This doc is planning only — no code, no migration is written here.

> **Prerequisite (governance, before the build slice):** the `TRANSACTION.*` audit-family reservation (EVT-160 block, §10/OD-P1C2-1) and the new `transaction.*` permission additions (§11/OD-P1C2-2) are **R-07-governed**. As in P1C-1, these are done as **in-slice governance/bootstrap deliverables** in the build (the family decision is ratified in this plan; AD-017 already ratified the capture-only stance + temporal class, so no new AD is required).

---

## 1. Requirements included

| REQ | Owns | Entity (this slice) | CAP | Acceptance clauses bound here | RTM transition |
|---|---|---|---|---|---|
| **REQ-PPM-003** (transaction **half**) | Append-only transaction history (provenance of holdings) | `transaction` (ENT-012, IA) | CAP-1 | transactions are immutable (append-only, DB-trigger-proven); captured independently; tenant-scoped; governed CRUD audited + lineage-rooted; reversals are explicit records | `Draft` → `In-Progress (P1C-2, transaction conjunct only)` |

> **REQ-PPM-003 conjunct decomposition (the requirement spans two slices):** its shipped backbone acceptance is *"Transactions immutable; valuations queryable as-of"*. P1C-2 satisfies + tests **only the "transactions immutable (append-only)" conjunct**; the **"valuations queryable as-of" conjunct remains OPEN → P1C-4** (the valuation FR half). REQ-PPM-003 is therefore **not closeable until P1C-4** — its In-Progress status here means the transaction conjunct is underway, not the whole requirement.

**Clause → deliverable → test binding (acceptance is provably mapped):**
- **transactions immutable (append-only)** → `transaction` in `APPEND_ONLY_TABLES` + the `irp_prevent_mutation` P0001 trigger (migration `0013`) + the ORM `before_update`/`before_delete` guard (`AppendOnlyViolation`); the PG **trigger-proof** test (grant `irp_app` UPDATE/DELETE so the rejection is the **P0001 trigger**, not a 42501).
- **captured independently (no derivation)** → `record_transaction` writes the immutable row; an affirmative scope-fence test that **no position/valuation is created or derived**.
- **tenant-scoped** → symmetric RLS (`USING == WITH CHECK == own-tenant`, FORCE) + the constrained-`irp_app` PG test (own visible / other-tenant invisible / no-context 0 rows).
- **governed CRUD audited** → `TRANSACTION.RECORD` (+ `TRANSACTION.REVERSE` for a reversal) co-transactional via the FROZEN `record_event`; literal-code assertion + `verify_chain`.
- **lineage-rooted** → origin edge `data_source(MANUAL) → transaction` via `record_lineage` + `assert_has_lineage` (per record, incl. reversals).
- **reversals are explicit records** → `POST /transactions/{id}/reverse` books a NEW immutable row with `reverses_transaction_id` set; a test that the original row is **never mutated** and the reversal links to it.

## 2. Requirements excluded

- **No positions / no valuations / no holdings / no market values** (P1C-3/4; a transaction is a bare event — it does not compute or hold anything).
- **No transaction-to-position derivation engine** (OD-P1C-E: positions are **captured directly** in P1C-3, NOT derived from the transaction log — derivation is a calc, deferred). **No cashflow engine** (no schedule/accrual/settlement processing).
- **No exposure aggregation, no risk calculation, no portfolio performance** (P2+; AD-014).
- **No corporate-action application; no `dataset_snapshot`** (excluded by AD-017).
- **No market data, no pricing** (`price`/`gross_amount` are **inert** captured fields — never recomputed or arithmetically cross-validated).
- **No reporting/dashboards; no real SSO.**
- **No P1C-3/4/5/6 or P2+ work.**

## 3. Proposed entity

### 3.1 `transaction` (ENT-012, IA — immutable append-only event log)
| Column | Type | Notes |
|---|---|---|
| `id` | GUID PK | server-stamped |
| `tenant_id` | GUID NOT NULL, indexed | RLS scope; symmetric |
| `system_from` | DateTime(tz) NOT NULL | the IA knowledge-time marker (`ImmutableAppendOnlyMixin`); **no** `valid_*`/`system_to` (not EV/FR) |
| `portfolio_id` | GUID FK → `portfolio.id`, NOT NULL, indexed | resolved tenant-filtered (`resolve_portfolio`, fail-closed) |
| `instrument_id` | GUID FK → `instrument.id`, NOT NULL, indexed | resolved tenant-filtered (`resolve_instrument`, fail-closed) |
| `txn_type` | String(50) NOT NULL | controlled-vocab **string** (no enum/CHECK): `BUY`/`SELL`/`DIVIDEND`/`INTEREST`/`FEE`/`TRANSFER_IN`/`TRANSFER_OUT`/`REVERSAL`/… extend by value |
| `trade_date` | Date NOT NULL | the business event date (inert; distinct from `system_from`) |
| `settle_date` | Date, nullable | inert |
| `quantity` | Numeric(28,8) NOT NULL | **signed** (long/short, +buy/−sell per convention OD-P1C2-7); inert capture |
| `price` | Numeric(20,6), nullable | inert (no market-data FK; not recomputed) |
| `gross_amount` | Numeric(20,6), nullable | inert (not recomputed; no `gross == price × quantity` check) |
| `currency_code` | String(3), nullable | plain ISO str (the P1B-3 no-FK-to-hybrid precedent), inert |
| `external_ref` | String(150), nullable | external/source idempotency key (OD-P1C2-4) |
| `reverses_transaction_id` | GUID self-FK → `transaction.id`, nullable, indexed | set on a **reversal** record (NULL = an original); intra-tenant; resolved fail-closed |
| `description` | String(500), nullable | |

- `__tablename__ = "transaction"`; `__temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY`.
- **In `APPEND_ONLY_TABLES`** (migration `0013`) → `irp_prevent_mutation` P0001 trigger; **ORM `before_update`/`before_delete` → `AppendOnlyViolation`** (mirror `ingestion_staged_record`). **NO `record_version`, NO `status`, NO `is_active`** (immutable — there are no updates/lifecycle; a correction is a new reversal row).
- `__table_args__`: a partial-unique idempotency guard on `external_ref` (OD-P1C2-4 — recommended: `UNIQUE(tenant_id, external_ref) WHERE external_ref IS NOT NULL`, the LEI partial-unique precedent); indices on `tenant_id`, `portfolio_id`, `instrument_id`, `reverses_transaction_id`.
- Register `Transaction` in `packages/shared-python/src/irp_shared/models.py` (import + `__all__`).
- **Package:** a new `packages/shared-python/src/irp_shared/transaction/` package (`models`/`events`/`service`/binder). It is the first entity that depends on **two** upstream packages — it imports `resolve_portfolio` (from `portfolio`) + `resolve_instrument` (from `reference`) + the rails (lineage/audit/db/temporal). One-way: `transaction → {portfolio, reference, rails}`; neither portfolio nor reference imports transaction (import-direction test). The audit/lineage plumbing (`ensure_manual_source` + `record_transaction_record`) is self-contained, mirroring `portfolio.service`.

## 4. Temporal classification

- **IA — immutable append-only** (`ImmutableAppendOnlyMixin`: `system_from` only). Conforms to AD-005 §2A ("transactions as an event log (ENT-012)") + AD-017 + REQ-PPM-003 (`transaction (IA)`). **NOT EV** (a transaction is never superseded/amended — it is an immutable fact) and **NOT FR** (it is an event, not an as-of-reconstructable risk input; positions/valuations are the FR entities, P1C-3/4).
- **Truly immutable** (unlike the IA-status-mutable `ingestion_batch`/`calculation_run` precedent, which are deliberately NOT in `APPEND_ONLY_TABLES`): a `transaction` row is **never** updated or deleted — enforced by BOTH the `irp_prevent_mutation` P0001 DB trigger **and** the ORM guard. A correction is an **append** (a reversal record), never a mutation (§6).
- Declared via `__temporal_class__ = IMMUTABLE_APPEND_ONLY` (BR-19); `transaction` is added to the migration's `APPEND_ONLY_TABLES`.

## 5. Transaction grain

- **One immutable row per trade/cashflow EVENT**, keyed to `(portfolio_id, instrument_id)` with a `txn_type`. **Not netted, not aggregated, not derived** — the row captures a single booked event exactly as provided. Multiple events for the same `(portfolio, instrument)` coexist (an event log, not a current-state master).
- **No current-head/"latest" concept** (that is EV/FR). Querying "the transactions for a portfolio" returns the full event list; computing a net position from them is a **calc, deferred to P1C-3** (and even there, positions are captured directly, not derived — OD-P1C-E).
- **Idempotency (OD-P1C2-4):** when `external_ref` is supplied, the partial-unique `(tenant_id, external_ref)` prevents double-booking the same source event (re-post → rejected). When absent, duplicate economic events are permitted (two identical trades are two events).

## 6. Transaction reversal / correction convention

**Transactions are immutable — corrections are explicit REVERSAL records, never updates** (the load-bearing P1C-2 contract; the user's special focus).

- A `transaction` row is **never** updated or deleted (the P0001 trigger + ORM guard reject it). To correct/cancel a booked transaction, **append a new reversal record**: a row with `reverses_transaction_id = <original id>`, `txn_type = REVERSAL` (or the original type tagged), and the **negating** economics (e.g. negated `quantity`/`gross_amount`). The original row is left **exactly** as recorded.
- The original is resolved tenant-filtered (`resolve_transaction` → `TransactionNotVisible`) before the reversal is booked (cross-tenant/unknown original fails closed). A reversal may itself be reversed (re-book) — the chain is append-only.
- **Audit:** a reversal emits **`TRANSACTION.REVERSE`** (linked to the original in `after_value` / `justification`), distinct from a normal **`TRANSACTION.RECORD`** — so the audit trail makes reversals first-class (OD-P1C2-1). Each reversal also roots its **own** MANUAL-source ORIGIN lineage edge (it is a new record).
- **NO unwind/derivation:** a reversal does **not** "undo" a position or valuation (there are none in P1C-2). It is purely a compensating **event** in the log. Net effect is computed downstream (a deferred calc), never here.

## 7. Relationship to portfolio

- `portfolio_id` GUID FK → `portfolio.id`, **NOT NULL**, indexed. Resolved via the shipped **`resolve_portfolio(session, id, *, acting_tenant)`** (P1C-1 binder) — a cross-tenant/unknown portfolio **fails closed at the service layer** (`PortfolioNotVisible`) **pre-commit** (RLS `WITH CHECK` only gates the writing row's own `tenant_id`). `transaction → portfolio` is a one-way dependency (portfolio never imports transaction).
- A transaction references a portfolio **node** of any `node_type` (PORTFOLIO/FUND/STRATEGY/ACCOUNT) — typically a leaf (ACCOUNT), but P1C-2 does not enforce node_type (a soft concern, OD-P1C2-9, default permissive).

## 8. Relationship to instrument

- `instrument_id` GUID FK → `instrument.id`, **NOT NULL**, indexed. Resolved via the shipped **`resolve_instrument(session, id, *, acting_tenant)`** (P1B-3 binder) — cross-tenant/unknown **fails closed** (`InstrumentNotVisible`) pre-commit. `transaction → reference` is one-way.
- Uses the **internal `instrument_id`** (not an external identifier) — no cross-vendor identifier precedence is needed (OD-012 stays deferred; the P1C-0 OD-P1C-J decision).

## 9. APIs

Thin, bounded (mirror the reference/portfolio routers). All under `get_tenant_session` + `require_permission`, `uuid.UUID` path params (422 + indistinguishable 404), single end-of-request commit.
- `POST /transactions` — record a transaction (`transaction.record`).
- `GET /transactions` — list (+ `?portfolio_id` / `?instrument_id` / `?txn_type` filter) (`transaction.view`).
- `GET /transactions/{id}` — read one (`transaction.view`).
- `POST /transactions/{id}/reverse` — book a reversal record against the original (`transaction.record`).

**No `PUT`/`PATCH`/`DELETE`** (immutable — there is no update or cancel endpoint; correction is `/reverse`). No position/valuation/holdings/aggregate endpoint.

## 10. Audit events

**Decision (item 8): mint a NEW `TRANSACTION.*` family at the EVT-160 block** — `TRANSACTION.RECORD` (EVT-160) for a normal capture + `TRANSACTION.REVERSE` (EVT-161) for a reversal record — caller-side constants in a new `irp_shared/transaction/events.py` to the **FROZEN** `audit/service.record_event` (R-07; `audit/service.py` unchanged). `before/after` = DC-2 metadata only (portfolio/instrument ids, txn_type, trade_date, signed quantity, `reverses_transaction_id`); per-tenant chain (`chain_id = tenant_id`, no SYSTEM chain — proprietary).

- **Create-only** (append-only): there is **no** `TRANSACTION.UPDATE`/`.STATUS_CHANGE` — a transaction is immutable, so the only events are the **record** of a new row (a reversal is itself a record, emitting `TRANSACTION.REVERSE`).
- **EVT block:** `TRANSACTION.*` is the **EVT-160 decade** — the next block in the P1C domain corridor after PORTFOLIO (EVT-150); POSITION (EVT-170) / VALUATION (EVT-180) follow in their slices. The exact index is the R-07 assignment at reservation.
- **Fallback (OD-P1C2-1):** a single `TRANSACTION.RECORD` for both normal + reversal (the reversal distinguished only by `reverses_transaction_id` in `after_value`) — simpler, but loses first-class reversal visibility in the audit trail. **Recommended: RECORD + REVERSE.**
- `audit/service.py` stays **FROZEN** — `TRANSACTION.*` are caller-side `event_type` strings only.

## 11. Entitlement checks

- **New permissions (R-07 additive):** `transaction.view` + `transaction.record` (the append-only verb — a transaction is *recorded*, never *edited*; **not** `transaction.edit`). **`.record` is a deliberate departure from the shipped `.edit` governed-write verb convention** (`portfolio.edit`, `reference.*.edit`), justified by append-only semantics (there is no edit) — recorded so the catalog parity reviewer reads it as intentional, not drift. These do **not** exist in `bootstrap.py` yet (unlike `portfolio.*`, which were pre-seeded) — they are **minted** in this slice's `bootstrap.py` + entitlement-model update.
- **Grants (recommended, OD-P1C2-2):** `transaction.record` → **`data_steward`** (the maker) + `platform_admin` (via `ALL_CODES`) — maker/admin only. `transaction.view` → `risk_analyst_1l`, `risk_manager_2l`, `data_steward` (+ `platform_admin`); **`auditor_3l` excluded** (operational client data — the proprietary/portfolio SoD precedent). A dedicated `ROLE-PM`/trader/ops maker is a future option.
- Deny-by-default `require_permission` (module-level guard singletons). Parity test pins the recipient sets (`transaction.record` = `{data_steward, platform_admin}`; `transaction.view` excludes `auditor_3l`).

## 12. RLS behavior

- **Symmetric proprietary** loop (byte-for-byte the `0012`/`0011` loop): `ALTER TABLE transaction ENABLE/FORCE ROW LEVEL SECURITY` + `CREATE POLICY tenant_isolation_transaction USING (tenant_id::text = current_setting('app.current_tenant', true)) WITH CHECK (...)`. `TENANT_SCOPED_TABLES = ("transaction",)`.
- **PLUS append-only** (the IA layer): `transaction` in `APPEND_ONLY_TABLES` → the `irp_prevent_mutation` P0001 trigger (`BEFORE UPDATE OR DELETE`). So the PG test must grant `irp_app` UPDATE/DELETE and prove the rejection is the **P0001 trigger** (append-only), distinct from the **42501** forged-tenant RLS rejection.
- **NEVER hybrid** (AD-013-R1); the closed hybrid set stays the 5 P1B-1 tables (assert unchanged via `pg_policies`).
- `portfolio_id` / `instrument_id` / `reverses_transaction_id` cross-tenant targets **fail closed at the service layer** (`resolve_*` explicit-tenant predicate). `set_config` (never parameterized `SET`); re-set tenant context after any commit before a read-back.

## 13. Lineage behavior

- One ORIGIN edge `data_source(MANUAL) → transaction` on **each record** (`ensure_manual_source` + `record_lineage`, server-stamped tenant, fail-closed; `assert_has_lineage`). A **reversal** is a new record → roots its **own** ORIGIN edge.
- There is **no** "amend roots no edge" case (transactions are never amended — every governed write is a new record with its own edge).

## 14. Data quality behavior

- Generic evaluators only: `not_null` on `portfolio_id`/`instrument_id`/`txn_type`/`trade_date`/`quantity` (the NOT-NULL schema columns); `allowed_values` on `txn_type` — a **soft/detective** check (it flags an out-of-vocab value, it does **not** reject the write), preserving the "extend by value" open-column stance of §3.1 (no enum/CHECK). No domain DQ engine, no reconciliation (REQ-DQR-002, P7).
- **Inert numerics captured-not-computed:** `price`/`gross_amount`/`quantity` are captured as provided — **never** recomputed or arithmetically cross-validated (no `gross_amount == price × quantity` DQ rule; that is a calc). `currency_code` is **nullable** and captured-as-provided — a soft data-dictionary obligation (CTRL-004), **not** a `not_null` DQ rule or a runtime FK/gate.

## 15. Tests

- **Logic (SQLite):** record round-trip (lineage + audit — **assert the emitted `event_type` equals the literal `TRANSACTION.RECORD` constant imported from `transaction/events.py`, not a re-typed string, + `verify_chain(session, tenant).ok`**); **IA immutability via the ORM guard** (an `update`/`delete` on a `transaction` raises `AppendOnlyViolation`); **reversal** — a new row with `reverses_transaction_id`; emits the literal `TRANSACTION.REVERSE`; **after the reversal commits, `expire_all`/refresh the ORIGINAL from the DB and assert its `id`/`system_from`/`quantity`/`gross_amount`/`txn_type` are byte-for-byte unchanged, exactly two rows exist for the pair, and the reversal's `reverses_transaction_id` points at the original**; cross-tenant `portfolio_id`/`instrument_id`/`reverses_transaction_id` → `*NotVisible`; controlled-vocab `txn_type`; `external_ref` idempotency (dup rejected); fail-closed audit rollback (CTRL-032 — monkeypatch `record_event` → the whole record rolls back, no orphan); **affirmative scope-fence: no position/valuation is created or derived**; import direction (transaction imports only portfolio/reference/rails).
- **Endpoint:** the 4 routes; deny-by-default (no perm → 403; a `transaction.view`-only principal cannot record → 403); 422 on bad UUID; 404 indistinguishable for cross-tenant/unknown portfolio/instrument/transaction; `/reverse` books a linked record; **no update/delete endpoint exists** (scope fence).
- **PG (constrained `irp_app`):** symmetric RLS (own visible / other-tenant invisible / **no-context → 0 rows**); forged-tenant-stamp write → **42501**; **append-only DB-trigger proof** — grant `irp_app` UPDATE/DELETE, **then a POSITIVE CONTROL first** (an `INSERT` under granted `irp_app` + tenant context succeeds **and** a `SELECT count(*)` of the seed row == 1, so the row is provably present + RLS-visible), so the subsequent raw `UPDATE`/`DELETE` provably *reaches* the row and its rejection is the **P0001 trigger** (`_is_append_only_violation`), NOT a zero-row no-op or a privilege denial (`transaction` has no mutable IA sibling, so this positive control replaces the `ingestion_batch`-mutable negative control); FORCE-RLS + symmetric-policy structural assertion (`pg_policies`); **closed-hybrid-set unchanged**; cross-tenant FK service-layer reject.

## 16. Acceptance criteria

1. A `transaction` is recorded as an **immutable** append-only row (REQ-PPM-003 transaction half), keyed to a tenant-resolved portfolio + instrument; **update/delete are rejected by BOTH the P0001 DB trigger AND the ORM guard**.
2. A correction is an **explicit reversal record** (`reverses_transaction_id` set; `TRANSACTION.REVERSE`); the original row is never mutated; the reversal links to it.
3. Transactions are **captured independently** — **no position/valuation is created or derived** (tested scope fence); no aggregation/cashflow/market-value computed.
4. Governed CRUD is audited (`TRANSACTION.RECORD`/`.REVERSE`) + lineage-rooted (one ORIGIN edge per record); tenant isolation proven under FORCE RLS by the constrained-role PG tests; idempotency on `external_ref` holds.
5. `make check` green; the new transaction symmetric-RLS **+ append-only** CI step green; `alembic check` drift-clean; downgrade smoke green.

## 17. Risks

- **Append-only mis-enforcement** — must be **two-layer** (DB trigger + ORM guard); mitigated by the PG trigger-proof test (grant UPDATE/DELETE so the rejection is the P0001 trigger, the `ingestion_staged_record` precedent).
- **Derivation creep** — the strongest pull is to "update positions from transactions"; held by OD-P1C-E + the affirmative no-derivation scope-fence test. **No cashflow/settlement engine.**
- **Reversal modeled as an update** — explicitly forbidden; a reversal is an append (a new row). Tested.
- **Two-package dependency** (`transaction → portfolio + reference`) — the first such entity; keep it one-way (import-direction test); neither upstream imports transaction.
- **Inert-numeric recompute creep** — `price`/`gross_amount` could tempt a `gross == price × quantity` validation (a calc) — fenced (§14).

## 18. Open decisions (resolve before / at implementation)

| ID | Decision | Recommendation | ⚑ sign-off before build? |
|---|---|---|---|
| **OD-P1C2-1** | Audit family: `TRANSACTION.RECORD` + `TRANSACTION.REVERSE` (EVT-160 block) vs a single `RECORD`. | **APPROVED (2026-06-24):** `TRANSACTION.RECORD` (EVT-160) + `TRANSACTION.REVERSE` (EVT-161) — first-class reversal audit trail; reserved via R-07 in-slice; **caller-side only, `audit/service.py` remains FROZEN**. | ⚑ ✅ signed off |
| **OD-P1C2-2** | `transaction.view` / `transaction.record` recipients. | **APPROVED (2026-06-24):** mint `transaction.view` + `transaction.record` in the P1C-2 build; **`data_steward` is the maker/recorder** (`transaction.record` → `data_steward` + admin); `transaction.view` → risk tiers + `data_steward` (+ admin); **`auditor_3l` excluded**. Additive R-07. | ⚑ ✅ signed off |
| **OD-P1C2-3** | Reversal model: `reverses_transaction_id` self-link + REVERSAL row vs a separate reversal table. | **Single-table self-link** (append a reversal row) — simplest, append-only-clean. | No |
| **OD-P1C2-4** | `external_ref` idempotency: partial `UNIQUE(tenant_id, external_ref) WHERE external_ref IS NOT NULL` vs no uniqueness. | **Partial-unique** (the LEI precedent) — prevents double-booking a source event; NULLs coexist. | No |
| **OD-P1C2-5** | `txn_type` starter vocabulary breadth. | A bounded starter set (BUY/SELL/DIVIDEND/INTEREST/FEE/TRANSFER_IN/TRANSFER_OUT/REVERSAL); extend by value. | No |
| **OD-P1C2-6** | Any position derivation / cashflow engine in P1C-2? | **APPROVED (2026-06-24): NO** — P1C-2 remains transaction **capture-only**: no position derivation, no cashflow engine, no valuation, no exposure aggregation (OD-P1C-E / AD-017). | ⚑ ✅ signed off |
| **OD-P1C2-7** | `quantity` sign convention. | **Signed** (+buy / −sell; long/short by sign) — one numeric column, no side column. | No |
| **OD-P1C2-8** | Package placement: new `irp_shared/transaction/` vs fold into `portfolio`. | **New `transaction/` package** (per-entity; depends one-way on portfolio + reference + rails). | No |
| **OD-P1C2-9** | `node_type` constraint on the referenced portfolio (must be a leaf/ACCOUNT?). | **Default-permissive** in P1C-2 (any node); tighten only if a real need appears. | No |

**Sign-offs recorded (H-06 Engineering Lead, 2026-06-24):** the three ⚑ decisions are approved — **OD-P1C2-1** (`TRANSACTION.RECORD`/`TRANSACTION.REVERSE` at EVT-160, caller-side only, `audit/service.py` frozen), **OD-P1C2-2** (mint `transaction.view`/`transaction.record` in the build; `data_steward` is the maker/recorder; `auditor_3l` excluded), **OD-P1C2-6** (P1C-2 stays transaction capture-only — no position derivation, no cashflow engine, no valuation, no exposure aggregation). The build may proceed on these baselines when directed. OD-P1C2-3/4/5/7/8/9 carry their recommended resolutions (non-blocking).

## 19. Controls impacted

P1C-2 makes these controls **executable** for the transaction domain (no new CTRL minted — reuses the matrix). REQ-PPM-003 binds CTRL-005/017; this slice also exercises the audit/lineage/entitlement rails:
- **CTRL-001** (every feature has tests before completion — the §15 SQLite/endpoint/PG suite gated in `make check`).
- **CTRL-004** (data dictionary — `transaction` columns + `txn_type` vocab; preventive/manual).
- **CTRL-005** (data-changing actions emit audit events — `TRANSACTION.RECORD`/`.REVERSE`; detective/automated).
- **CTRL-006 / CTRL-013** (lineage capture + no-bypass — origin edge per record + `assert_has_lineage`).
- **CTRL-011** (no entitlement/RLS bypass; deny-by-default + tenant isolation; constrained-role PG tests).
- **CTRL-012** (no audit-framework bypass — every governed record emits `TRANSACTION.*`).
- **CTRL-017** (temporal-class declared + **append-only immutability** — the IA P0001 trigger + ORM guard; the trigger-proof test; the **first DOMAIN append-only entity**, extending the audit/lineage/ingestion IA evidence).
- **CTRL-032** (fail-closed audit blocks the governed record; AUD-04).

## 20. Documentation updates (in-slice deliverables, gated in the same build PR)

- **audit_event_taxonomy.md** — add the `TRANSACTION` family row at the **EVT-160 block** (`TRANSACTION.RECORD`=EVT-160 / `.REVERSE`=EVT-161), ACTIVATED in P1C-2 caller-side (R-07; `audit/service.py` FROZEN).
- **canonical_data_model_standard.md** — annotate **ENT-012**: REALIZED P1C-2 (migration `0013`) as the `transaction` IA append-only event log; capture-only (no derivation).
- **temporal_reproducibility_standard.md §2A** — add a P1C-2 realization note (ENT-012 IA — the first DOMAIN append-only entity; `irp_prevent_mutation` trigger + ORM guard; reversal-not-update convention).
- **requirements_backbone.md + requirements_traceability_matrix.md** — REQ-PPM-003 `Draft` → `In-Progress (P1C-2: transaction half — append-only event log; valuation half → P1C-4)`.
- **entitlement_sod_model.md §5B** — record the new `transaction.view`/`transaction.record` permissions + grants (OD-P1C2-2) + `auditor_3l` exclusion.
- **control_matrix_skeleton.md** — note CTRL-005/012/017/032 (+001/004/006/011/013) now exercised by `transaction` (the first domain append-only entity).
- **ci_enforcement_overview.md + .github/workflows/ci.yml** — add the "Transaction symmetric-RLS + append-only tests (Postgres, REQ-PPM-003 / AD-017 / BR-17/BR-18)" step in the `migration` job (after portfolio, before downgrade).

## 21. Whether P1C-2 is ready to implement

**Ready to implement — conditional on the R-07 governance additions (done in-slice).** The entity, temporal class (IA), the two-layer append-only enforcement, the symmetric RLS, the reversal-not-update convention, the portfolio + instrument resolvers, and the tests are all specified against shipped precedents (`ingestion_staged_record` for IA append-only; `portfolio`/`legal_entity` for the domain governed-write + resolver pattern). The governed additions — the `TRANSACTION.*` taxonomy reservation (EVT-160) and the new `transaction.*` permissions — are **R-07** and are done as in-slice governance/bootstrap deliverables (the family decision is ratified in this plan; AD-017 already covers the capture-only stance + temporal class, so **no new AD is required**). Resolve OD-P1C2-1/2/6 (the ⚑ items), then the build is unblocked.

## 22. Exact implementation kickoff prompt (paste-ready)

> **DO NOT START until explicitly directed.** When directed, implement **P1C-2 (transactions — IA append-only, capture-only)** per `10_delivery_backlog/p1c2_implementation_plan.md`.
>
> **Full scope (the deliverable cap — nothing beyond this):**
> 1. NEW package `packages/shared-python/src/irp_shared/transaction/`: `models.py` (the `Transaction` IA class — columns per §3.1; `__temporal_class__ = IMMUTABLE_APPEND_ONLY`; `system_from` only; partial-unique `external_ref` idempotency; `reverses_transaction_id` self-FK; **ORM `before_update`/`before_delete` → `AppendOnlyViolation`**), `events.py` (`TRANSACTION.RECORD`/`TRANSACTION.REVERSE` constants), `service.py` (`ensure_manual_source` + `record_transaction_record`/`record_transaction_reverse` mirroring `record_portfolio_*`: ORIGIN MANUAL-source edge + record event; fail-closed, no mid-call commit), and the binder (`transaction.py`: `TransactionNotVisible`, `resolve_transaction`, `record_transaction`, `reverse_transaction` — reusing the shipped `resolve_portfolio` + `resolve_instrument`). Register `Transaction` in `irp_shared/models.py`.
> 2. ONE migration **0013** (`revision='0013_transaction'`, `down_revision='0012_portfolio'`) creating exactly `transaction` with NAMING_CONVENTION names, the FKs (`portfolio_id`/`instrument_id`/`reverses_transaction_id`), indices, the partial-unique `external_ref`, the **symmetric RLS loop** over `TENANT_SCOPED_TABLES = ("transaction",)`, **AND `transaction` in `APPEND_ONLY_TABLES`** → the `irp_prevent_mutation` P0001 trigger (`BEFORE UPDATE OR DELETE`, reusing the 0001 function). **Do NOT touch the hybrid loop, the closed hybrid set, or any prior migration.**
> 3. The IA entity exactly as specified (IA append-only; controlled-vocab `txn_type` plain String; signed `quantity`; inert `price`/`gross_amount`/`settle_date`; **NO `record_version`/`status`/`is_active`**).
> 4. **Activate** `TRANSACTION.RECORD` / `TRANSACTION.REVERSE` caller-side via the FROZEN `record_event`; `before/after` = DC-2 metadata only; per-tenant chain.
> 5. Entitlement: **mint** `transaction.view` + `transaction.record` in `bootstrap.py`; grant `transaction.record` → `data_steward` (+ admin), `transaction.view` → risk tiers + `data_steward` (+ admin), `auditor_3l` excluded; deny-by-default; parity test.
> 6. Backend router `apps/backend/.../api/transactions.py` (the 4 routes in §9 — record / list+filter / get / reverse; **no update/delete**) registered in `main.py`; `get_tenant_session` + `require_permission`; `uuid.UUID` path params; single end-of-request commit.
> 7. Lineage: one MANUAL-source ORIGIN edge per record (incl. reversals); `assert_has_lineage`. **DQ:** generic `not_null`/`allowed_values` (§14) — no recomputation.
> 8. Tests: SQLite logic + endpoint + PG per §15, incl. the **append-only DB-trigger proof** (grant `irp_app` UPDATE/DELETE → P0001), the ORM guard, the reversal-record + original-unchanged proof, cross-tenant fail-closed, symmetric-RLS proofs, closed-hybrid-set-unchanged, and the **no-position-derivation scope fence**.
> 9. CI: add the "Transaction symmetric-RLS + append-only tests (Postgres, REQ-PPM-003 / AD-017)" step. Governance doc updates per §20 in the same PR.
>
> **STRICT EXCLUSIONS:** no positions/valuations/holdings/market-values; no transaction→position derivation engine; no cashflow engine; no exposure aggregation/risk/performance; no `dataset_snapshot`; no corporate-action application; no market data/pricing; no reporting/dashboards/SSO; no P1C-3/4/5/6 or P2+ work; `audit/service.py` stays FROZEN; no prior-migration edits; no BYPASSRLS app path.
>
> **Build sequence:** (1) `Transaction` model + ORM append-only guard + aggregator; `alembic check` sees new metadata. (2) Migration 0013 (DDL + symmetric RLS loop + append-only trigger); `alembic upgrade head` + `alembic check` clean. (3) `transaction/` package (events/service/binder + reversal). (4) Entitlement mint + bootstrap parity. (5) Backend router + registration. (6) Tests (logic → endpoint → PG, incl. the trigger-proof). (7) Governance doc updates + CI step. (8) `make check` green → PG validate on `postgres:16` → **8-lens UltraCode review** → fix in-scope → **commit on explicit approval** → watch CI green.

---

*Planning only — no code, no migration written in this turn. P1C-2 build begins only on explicit approval.*
