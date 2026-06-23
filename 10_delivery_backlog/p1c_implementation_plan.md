# P1C Implementation Plan — Portfolio, Transactions, Positions, Valuations

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1C-PLAN-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-01 Chief Architect AI (with R-05 Data Architect AI) |
| Approver | H-06 Engineering Lead |
| Created | 2026-06-23 |
| Related Documents | p1c0_decision_record.md, p1b_closeout_p1c_readiness.md, p1b_implementation_plan.md, ../02_requirements/requirements_backbone.md, ../02_requirements/requirements_traceability_matrix.md, ../04_data_model/canonical_data_model_standard.md, ../04_data_model/temporal_reproducibility_standard.md, ../04_data_model/audit_event_taxonomy.md, ../06_security/entitlement_sod_model.md, ../09_compliance_controls/control_matrix_skeleton.md |
| Supported Build Rules | BR-3, BR-5, BR-6, BR-7, BR-9, BR-11, BR-12, BR-13, BR-17, BR-19 |

### Purpose & scope
The first **domain-analytics** block, built on the P1A rails + the P1B reference spine. **Capture + as-of reconstruction only.** No application code/migrations are written at P1C-0 (this is the plan); each subphase is separately planned, reviewed, and committed on approval. The twelve P1C decisions are fixed in `p1c0_decision_record.md` (OD-P1C-A…L).

### P1C scope entities
`portfolio` (ENT-010, **EV**, single table + `node_type`), `transaction` (ENT-012, **IA** append-only), `position` (ENT-011, **FR** bitemporal), `valuation` (ENT-013, **FR** bitemporal). Plus as-of holdings **views** (no new entity) and a **synthetic dataset** (seed tooling, no product entity).

### Explicit exclusions (binding scope fence)
No risk calculations; **no exposure aggregation** (REQ-PPM-004 stays P2 — `exposure.aggregate.run` reserved-unwired, OD-P1C-G/H); **no `dataset_snapshot`** (stays P2, OQ-013a closed); no VaR/ES; no market-data ingestion; no pricing/valuation **models** (marks are captured, not computed); **no corporate-action application** (capture-only holds); no counterparty exposure / netting / CSA / collateral (OD-015 deferred, OD-P1C-K); no credit risk; no liquidity risk; no limits/breaches; no reporting dashboards; no real SSO; **no transaction→position derivation engine** (positions captured directly, OD-P1C-E); no identifier-precedence engine (OD-012 deferred, OD-P1C-J); no P2+ work.

### Global build conventions (every subphase)
- **Temporal classes (AD-005 §2A):** portfolio = **EV** (`EffectiveDatedMixin`), transaction = **IA** (`ImmutableAppendOnlyMixin` + `irp_prevent_mutation` P0001 trigger + entry in that migration's `APPEND_ONLY_TABLES` + ORM `before_update`/`before_delete` guard), position/valuation = **FR** (`FullReproducibleMixin`; **NOT** append-only — the bitemporal protocol UPDATEs close-out columns). Declare `__temporal_class__` (BR-19); register every model in `irp_shared.models` (import + `__all__`).
- **RLS:** all four P1C tables are **PROPRIETARY → SYMMETRIC** tenant-isolation (`USING == WITH CHECK == tenant_id::text = current_setting('app.current_tenant', true)`, FORCE RLS); **NEVER hybrid** (AD-013-R1); the closed hybrid set stays the 5 P1B-1 tables (asserted unchanged via `pg_policies`). `set_config` (never parameterized `SET`); re-set tenant context after any commit before a read-back.
- **Cross-tenant linked ids fail closed at the SERVICE layer:** every `*_id` FK target (parent_id, portfolio_id, instrument_id) is resolved by an explicit `tenant_id == acting_tenant` predicate (`resolve_portfolio`/`resolve_position` + the shipped `resolve_instrument`) raising a `*NotVisible` exception **pre-commit** — RLS `WITH CHECK` only gates the writing row's own `tenant_id` (the rls-1 lesson).
- **FR protocol reuse:** positions/valuations copy the shipped `reference/instrument_terms.py` protocol exactly — `create_X` / `supersede_X` (valid-time) / `correct_X` (system-time, TR-08 `restatement_reason` + `supersedes_id`) / `reconstruct_X_as_of(valid_at, known_at)`; **one-`now`** per op; **close-first** (mutate+flush prior close-out before insert); prior versions **never mutated in place**; current-head partial-unique `WHERE valid_to IS NULL AND system_to IS NULL`.
- **Audit:** a **new domain event family** (`PORTFOLIO.*`, `TRANSACTION.*`, `POSITION.*`, `VALUATION.*`) is a **governed R-07 taxonomy addition** — at P1C-0 ratification the **family + a reserved EVT index block** (one ~10-wide block per category, like REFERENCE's EVT-140 block) is **recorded** in `audit_event_taxonomy.md`; the specific codes are then **activated caller-side** in each build slice; `audit/service.py` stays **FROZEN**. Service helpers follow the P1B `record_reference_*` shape (a thin domain `record_*` per entity: ORIGIN MANUAL-source edge + create event; close-out = update event, no edge; correction = new edge + correction event).
- **Entitlement:** additive per slice (R-07-governed `bootstrap.py` additions); parity tests pin recipient sets; deny-by-default `require_permission` (module-level guard singletons). **Reconcile the existing seeded placeholders (verified grant reality):** `portfolio.view` + `position.view` are granted to `risk_analyst_1l` + `risk_manager_2l` (and `platform_admin` via `ALL_CODES`); `portfolio.edit` + `exposure.aggregate.run` are **catalog-only — granted to `platform_admin` only** (no read/maker role; effectively reserved-unwired). New `transaction.*`, `position.edit`, `valuation.*` are **R-07 additions named at ratification** and activated per slice.
- **Lineage:** every governed create roots one MANUAL-source ORIGIN edge (`ensure_manual_source` + `record_lineage`); `assert_has_lineage` test-side (CTRL-013). **DQ:** generic `not_null`/`allowed_values` only.
- **FastAPI:** `get_tenant_session` (sets context), `require_permission` deny-by-default, `uuid.UUID` path params (422 + indistinguishable 404), single end-of-request commit.
- **Migrations:** sequential — `0012` portfolio, `0013` transaction, `0014` position, `0015` valuation; `alembic check` drift gate (`compare_type=False`); NAMING_CONVENTION `pk_/ix_/uq_/fk_`; each new tenant table → a dedicated CI PG RLS step (transaction also gets an append-only step); downgrade smoke.

---

## P1C-1 — Portfolio / fund / strategy / account hierarchy (EV)

1. **Requirements included.** REQ-PPM-001 (portfolio/fund/strategy/account hierarchy — the entitlement **scope anchor**). Realize ENT-010 as a single EV table. Land the **synthetic reference seed pack** (OD-P1C-L) in this slice so downstream slices have instruments/currencies to reference. Reserve + activate the `PORTFOLIO.*` audit codes (R-07).
2. **Requirements excluded.** transactions/positions/valuations (later slices); **ABAC enforcement** (anchor only — OD-P1C-A/B; enforcement → P6+); exposure aggregation; any node-type-specific business semantics beyond a permitted-parent validation rule.
3. **Entities.** `portfolio` (ENT-010, **EV** = `EffectiveDatedMixin`, `valid_from`/`valid_to`) — `code` (String 150), `name` (String 255), `node_type` (String 50 controlled-vocab: PORTFOLIO/FUND/STRATEGY/ACCOUNT), `parent_id` (GUID self-FK, nullable=root, indexed, intra-tenant), `base_currency_code` (String 3, plain str — the P1B-3 no-FK-to-hybrid precedent), `status` (String 30, default ACTIVE), `description` (String 500), `record_version` (Integer). `UNIQUE(tenant_id, code)`. NO `is_active` (single `status`). **EV realization (the P1B reference-EV precedent):** a portfolio is a **single current-state row**; an amend is an **in-place supersede** (`record_version` bump + a `PORTFOLIO.UPDATE` audit event carrying the diff) — not a new physical row — with the `valid_from`/`valid_to` effective-dating columns available; no system-time axis (that is FR, reserved for position/valuation).
4. **APIs.** `POST /portfolios` (create), `GET /portfolios` (+ `?node_type` / `?parent_id` filter), `GET /portfolios/{id}`, `POST /portfolios/{id}` (amend = EV supersede), `GET /portfolios/{id}/tree` (bounded subtree read).
5. **Audit events.** `PORTFOLIO.CREATE` / `PORTFOLIO.UPDATE` (mint the `PORTFOLIO.*` family, R-07; activated caller-side). Reuse `DATA.VALIDATE` for any DQ run.
6. **Entitlement checks.** Reuse the seeded `portfolio.view` (granted to `risk_analyst_1l` + `risk_manager_2l`, and `platform_admin` via `ALL_CODES`) and `portfolio.edit` (**catalog-only — currently granted to `platform_admin` only**; a maker role must be **granted** `portfolio.edit` in this slice for non-admin portfolio writes, an additive R-07 change). Confirm/extend recipients (e.g. a Portfolio-Manager role if added) additively; parity-test the recipient sets. Deny-by-default.
7. **RLS behavior.** Symmetric proprietary loop; FORCE RLS; `UNIQUE(tenant_id, code)`; no-context read → 0 rows; closed hybrid set unchanged (`pg_policies` assertion). `parent_id` cross-tenant resolved fail-closed in the service.
8. **Lineage behavior.** ORIGIN edge `data_source(MANUAL) → portfolio` on create; `assert_has_lineage`.
9. **DQ behavior.** `not_null` on `code`/`name`/`node_type`; `allowed_values` on `node_type` (+ `status`).
10. **Tests.** SQLite logic + endpoint; **hierarchy build + bounded cycle-safe resolver** (self-parent rejected; cycle rejected; depth cap; tenant-filtered). Note the **descendant/subtree** resolver is a **NEW** traversal built to the `legal_entity` safety invariants (visited-set + depth cap + cycle guard + tenant filter) — the shipped `resolve_ultimate_parent` walks **upward** only, so the descendant direction has its own explicit test. Cross-tenant `parent_id` → `PortfolioNotVisible`; EV mutability (amend supersedes in place); deny-by-default; `PORTFOLIO.*` emitted + `verify_chain`; PG symmetric RLS (own visible / other-tenant invisible / no-context 0 rows).
11. **Acceptance criteria.** A tenant-scoped node tree persists, is the entitlement **scope anchor**, and supports bounded subtree resolution (REQ-PPM-001); audited (`PORTFOLIO.*`) + lineage-rooted; isolation proven under FORCE RLS.
12. **Risks.** Node-model over-design (keep to adjacency + `node_type` label); cycle/self-parent safety (reuse the `legal_entity` resolver shape). **ABAC anchored-not-enforced (OD-P1C-A, must be stated):** within a tenant, **any principal holding `portfolio.view`/`position.view`/`valuation.view`/`transaction.view` can read ALL nodes/holdings in that tenant** — there is no portfolio-scope enforcement until the P6+ `entitlement_grant` scope payload lands. This is acceptable **only** because P1C data is synthetic (DC-1/DC-2, OD-P1C-L); real DC-3 portfolios stay gated behind P6+ ABAC. The existing seeded `portfolio.*` placeholders must reconcile cleanly (parity test).
13. **Open questions.** `node_type` vocab finalization; permitted parent/child node_type pairs (default permissive); whether `ACCOUNT` is always a leaf; Portfolio-Manager role/recipient set for `portfolio.view`.

## P1C-2 — Transactions (IA append-only)

1. **Requirements included.** REQ-PPM-003 (transaction half — append-only trade/cashflow event log). Reserve + activate `TRANSACTION.RECORD` (R-07). Add `transaction.view` / `transaction.record` permissions.
2. **Requirements excluded.** **position derivation from transactions** (a calc — OD-P1C-E, deferred); settlement/cash engines; corporate-action application; reconciliation (REQ-DQR-002, P7).
3. **Entities.** `transaction` (ENT-012, **IA** — the first real **domain** append-only entity beyond the rails; in this migration's `APPEND_ONLY_TABLES`; `irp_prevent_mutation` P0001 trigger; ORM `before_update`/`before_delete` guard) — `portfolio_id` (GUID FK→portfolio, NOT NULL, indexed), `instrument_id` (GUID FK→instrument, NOT NULL, indexed), `txn_type` (String 50 controlled-vocab: BUY/SELL/DIVIDEND/INTEREST/FEE/TRANSFER_IN/TRANSFER_OUT/…), `trade_date` (Date), `settle_date` (Date, nullable), `quantity` (Numeric 28,8, signed), `price` (Numeric 20,6, nullable, inert), `gross_amount` (Numeric 20,6, nullable, inert), `currency_code` (String 3), `external_ref` (String 150, nullable), `description` (String 500, nullable).
4. **APIs.** `POST /transactions` (record), `GET /transactions` (+ `?portfolio_id` / `?instrument_id` filter), `GET /transactions/{id}`. **No** update/delete endpoint (append-only).
5. **Audit events.** `TRANSACTION.RECORD` (create-only; no update event — append-only).
6. **Entitlement checks.** New `transaction.view` / `transaction.record` (additive, R-07); deny-by-default.
7. **RLS behavior.** Symmetric proprietary; `portfolio_id` + `instrument_id` cross-tenant fail-closed at the service layer (`resolve_portfolio`, `resolve_instrument`).
8. **Lineage behavior.** ORIGIN edge `data_source(MANUAL) → transaction` on record.
9. **DQ behavior.** `not_null` on `portfolio_id`/`instrument_id`/`txn_type`/`trade_date`/`quantity`/`currency_code`; `allowed_values` on `txn_type`.
10. **Tests.** SQLite logic + endpoint; **append-only DB-trigger proof** (grant `irp_app` UPDATE/DELETE so the rejection is the **P0001 trigger** P0001, not a 42501 privilege denial) **and** the ORM guard; cross-tenant `portfolio_id`/`instrument_id` → `*NotVisible`; **corrections-as-reversals** (a correction is a new reversing/booking transaction, never a mutation); `TRANSACTION.RECORD` emitted + `verify_chain`; PG symmetric RLS + append-only.
11. **Acceptance criteria.** Transactions are immutable (DB trigger + ORM guard proven); tenant-isolated; audited + lineage-rooted; an independent event log (no position derivation) (REQ-PPM-003).
12. **Risks.** Scope creep into a settlement / position-keeping / derivation engine — held by the OD-P1C-E fence + the exclusion list; `txn_type` taxonomy breadth (keep a starter vocab, extend by value).
13. **Open questions.** Reversal/correction modeling convention (reversing entry vs linked correction id, non-FK); whether `gross_amount` is captured or always null in P1C.

## P1C-3 — Positions (FR bitemporal)

1. **Requirements included.** REQ-PPM-002 (position master, as-of). Realize ENT-011 as the authoritative **FR holdings master**. Reserve + activate `POSITION.*` (R-07). Add `position.edit` (reuse seeded `position.view`).
2. **Requirements excluded.** **position-from-transaction derivation** (OD-P1C-E); risk/exposure; lot-level grain (OD-P1C-D → aggregated); embedding market value (that is valuation, P1C-4).
3. **Entities.** `position` (ENT-011, **FR** — reuse the `instrument_terms` protocol) — `portfolio_id` (GUID FK, NOT NULL, indexed), `instrument_id` (GUID FK, NOT NULL, indexed), `quantity` (Numeric 28,8, **signed** long/short), `cost_basis` (Numeric 20,6, nullable — an **opaque captured reference value**, NOT lot-level cost accounting, never recomputed; decided on position per OD-P1C-D), `currency_code` (String 3), `source` (String 150, nullable), `restatement_reason` (String **255**, nullable — TR-08; matches the shipped `instrument_terms`/`justification` length), `supersedes_id` (GUID, nullable), `record_version` (Integer). **FR** axes `valid_from/valid_to` + `system_from/system_to`. Current-head partial-unique: `(tenant_id, portfolio_id, instrument_id) WHERE valid_to IS NULL AND system_to IS NULL`. **NOT** in `APPEND_ONLY_TABLES`.
4. **APIs.** `POST /positions` (create open version), `POST /positions/{id}` (`?mode=supersede` valid-time | `?mode=correct` system-time/TR-08), `GET /positions` (+ filters), `GET /positions/{id}`, `GET /positions/as-of?valid_at=&known_at=` (bitemporal read).
5. **Audit events.** `POSITION.CREATE` / `POSITION.UPDATE` (close-out of prior head) / `POSITION.CORRECTION` (a **new** `POSITION.*` correction code — **NOT** a reuse of the reference-domain EVT-142; R-07).
6. **Entitlement checks.** Reuse seeded `position.view`; add `position.edit` (additive, R-07); deny-by-default.
7. **RLS behavior.** Symmetric proprietary; cross-tenant `portfolio_id`/`instrument_id` fail-closed at the service layer.
8. **Lineage behavior.** One ORIGIN edge per **NEW physical version row** — `create`, the **new open row of a valid-time supersede**, and an as-known **correction** each root exactly one edge; only the **prior-head close-out** (the `valid_to`/`system_to` stamp on the superseded row) adds **no** edge — mirroring the shipped `instrument_terms` protocol (the P1B-3 lineage-per-version rule; cf. `p1b_closeout_p1c_readiness.md` LDQ-2).
9. **DQ behavior.** `not_null` on `portfolio_id`/`instrument_id`/`quantity`/`currency_code`.
10. **Tests.** **As-of reconstruction on BOTH axes** (the P1B-3 acceptance pattern: create → supersede → correct, then `reconstruct_position_as_of(valid_at, known_at)` returns the right version per (valid, known) quadrant); **content-immutability** of prior versions (only close-out columns change); current-head partial-unique (no two dual-open rows per key); one-`now`/close-first (no inter-version gap, no transient unique violation); cross-tenant fail-closed; PG-under-FORCE-RLS; **affirmative scope-fence: positions are captured, never derived from transactions**.
11. **Acceptance criteria.** A position is reconstructable for any past as-of on both axes (REQ-PPM-002); prior versions immutable; tenant-isolated; audited (`POSITION.*`) + lineage-rooted.
12. **Risks.** FR-protocol mis-reuse (mitigated — proven in P1B-3; copy `instrument_terms` exactly); grain is **decided** (OD-P1C-D → aggregated by (portfolio, instrument)); `cost_basis` is **decided** on position as an opaque captured reference (OD-P1C-D), not a position-vs-valuation open question.
13. **Open questions.** Whether to capture a `source`/`as_of_date` business column beyond the FR axes; confirm the netting rule for the aggregated grain (sum of signed quantity per (portfolio, instrument)) is a capture rule, not a calc.

## P1C-4 — Valuations (FR bitemporal)

1. **Requirements included.** REQ-PPM-003 (valuation half — valuation history, as-of). Realize ENT-013 as **FR**. Reserve + activate `VALUATION.*` (R-07). Add `valuation.view` / `valuation.edit`.
2. **Requirements excluded.** pricing/valuation **math** (marks are **captured, not computed** — OD-P1C-F); source-precedence engine (deferred, echo of OD-012); market-data ingestion.
3. **Entities.** `valuation` (ENT-013, **FR**, same protocol as position) — `portfolio_id` (GUID FK, NOT NULL, indexed), `instrument_id` (GUID FK, NOT NULL, indexed), `valuation_date` (Date — an **immutable logical-key component**, a peer of `instrument_id`, carried forward verbatim by supersede/correct and never mutated; distinct from the FR `valid_*`/`system_*` axes, which version the mark *for* a fixed valuation_date), `mark_value` (Numeric 20,6), `currency_code` (String 3), `mark_source` (String 150 controlled-vocab label, inert), `price_basis` (String 20, nullable — e.g. DIRTY/CLEAN, inert), `restatement_reason` (String **255**, nullable — TR-08), `supersedes_id` (GUID, nullable), `record_version` (Integer). Current-head partial-unique: `(tenant_id, portfolio_id, instrument_id, valuation_date) WHERE valid_to IS NULL AND system_to IS NULL` — **exactly one mark per key** (OD-P1C-F; multi-source out of scope). **NOT** append-only.
4. **APIs.** `POST /valuations` (create), `POST /valuations/{id}` (`?mode=supersede|correct`), `GET /valuations` (+ filters), `GET /valuations/{id}`, `GET /valuations/as-of?valid_at=&known_at=`.
5. **Audit events.** `VALUATION.CREATE` / `VALUATION.UPDATE` / `VALUATION.CORRECTION` (new `VALUATION.*` codes; R-07).
6. **Entitlement checks.** New `valuation.view` / `valuation.edit` (additive, R-07); deny-by-default.
7. **RLS behavior.** Symmetric proprietary; `portfolio_id`/`instrument_id` cross-tenant fail-closed.
8. **Lineage behavior.** One ORIGIN edge per **NEW physical version row** — `create`, the new open row of a valid-time supersede, and an as-known correction each root one edge; only the prior-head close-out adds none (as P1C-3 §8).
9. **DQ behavior.** `not_null` on `portfolio_id`/`instrument_id`/`valuation_date`/`mark_value`/`currency_code`; `allowed_values` on `mark_source` (+ `price_basis`).
10. **Tests.** As-of reconstruction on BOTH axes; content-immutability; current-head partial-unique (incl. `valuation_date` in the key); **scope-fence: the mark is captured, no valuation math is performed**; cross-tenant fail-closed; PG symmetric RLS.
11. **Acceptance criteria.** A valuation is queryable as-of on both axes (REQ-PPM-003); marks captured not computed; tenant-isolated; audited (`VALUATION.*`) + lineage-rooted.
12. **Risks.** Valuation-math creep (held by the OD-P1C-F fence). Multi-source marks are **decided out of scope** (exactly one mark per `(portfolio, instrument, valuation_date)`, OD-P1C-F) — not an open question; adding `mark_source` to the logical key is a deliberate future change if ever needed.
13. **Open questions.** `price_basis` controlled-vocab scope (DIRTY/CLEAN/…); whether `valuation_date` ever needs a sub-day granularity (default: Date).

## P1C-5 — As-of holdings / portfolio views (read-only)

1. **Requirements included.** The **read** half of REQ-PPM-001/002/003 — as-of holdings reconstruction across the hierarchy.
2. **Requirements excluded.** **Exposure aggregation / any rollup or derived governed number (REQ-PPM-004 → P2, OD-P1C-G/H)**; sums/weights/percentages; valuation math.
3. **Entities.** None new — read endpoints compose `portfolio` + `position` (as-of) + `valuation` (as-of).
4. **APIs.** `GET /portfolios/{id}/holdings?valid_at=&known_at=` (the as-of positions for a portfolio, optionally joined to the as-of valuation per holding — **listed, not aggregated**); `GET /portfolios/{id}/tree` (bounded). Subtree holdings composition (descendants) is a read convenience gated behind the bounded resolver — **still no aggregation**.
5. **Audit events.** None (reads not yet access-audited — OD-023).
6. **Entitlement checks.** `portfolio.view` + `position.view` (+ `valuation.view`); deny-by-default.
7. **RLS behavior.** Symmetric (inherited); tenant-isolated reads only.
8. **Lineage behavior.** N/A (read).
9. **DQ behavior.** N/A (read).
10. **Tests.** As-of holdings correctness across both axes (the reconstructed set matches the per-entity `reconstruct_*_as_of`); tenant isolation; **explicit scope-fence test: NO aggregation/exposure/sum/rollup number is computed AND no per-holding COMPUTED value** (e.g. `market_value = quantity × mark_value`) — the response returns only the **stored** position quantity + the **stored** valuation mark per holding, never a total and never a derived number.
11. **Acceptance criteria.** Holdings are reconstructable as-of, per portfolio (and bounded subtree), with **no** derived aggregate (read half of REQ-PPM-001/002/003).
12. **Risks.** Sliding into exposure rollup (the AD-014 gate) — held by the scope-fence test; subtree composition must reuse the bounded cycle-safe resolver.
13. **Open questions.** View shape + pagination; whether subtree holdings ship in P1C-5 or wait (default: node-level holdings in P1C-5; bounded subtree optional).

## P1C-6 — Synthetic dataset (deterministic; may land earlier per-slice)

1. **Requirements included.** Test/demo/UI/visualization enablement (not a product REQ) — the **synthetic portfolio/transaction/position/valuation dataset** over the synthetic reference seed pack (OD-P1C-L).
2. **Requirements excluded.** **Real client/vendor data**; any prod auto-run; bulk ingestion (P1B-5 deferred); DC-3/DC-4 data.
3. **Entities.** None new — a **labeled, never-auto-run** seed builder that calls the governed binders (so seeded rows carry audit + MANUAL-source lineage like prod).
4. **APIs.** None (build-time/test tooling; not an HTTP surface).
5. **Audit events.** Whatever the governed binders emit for the rows they create (CREATE events) — proving the seed path is governed, not a back door.
6. **Entitlement checks.** Runs under a system/test actor; not a runtime permission surface.
7. **RLS behavior.** Seeds per a fixed synthetic tenant (or a small set) under proper tenant context; never BYPASSRLS.
8. **Lineage behavior.** ORIGIN edges rooted by the binders (governed).
9. **DQ behavior.** Inherits the binders' generic checks.
10. **Tests.** The builder is **deterministic** (re-run → byte-identical `uuid5` ids; fixed timestamps injected — no wall-clock/random); the seeded dataset exercises FR as-of (multiple valid/known versions) and is **governed** (audit + lineage present); a guard test that the module is **not** wired to any prod post-migrate path / migration.
11. **Acceptance criteria.** A reproducible, non-sensitive demo dataset (portfolios + transactions + positions + valuations over synthetic reference data) exists for tests/demos/UI; no real data; never auto-run.
12. **Risks.** Synthetic data leaking into a prod path — mitigated by the labeled never-auto-run module, kept out of migrations and distinct from the SYSTEM seeder; non-determinism — mitigated by `uuid5` + injected timestamps.
13. **Open questions.** Dataset size/shape (how many portfolios/instruments/versions); whether the reference seed lands fully in P1C-1 and the domain dataset accretes per-slice (recommended) vs all consolidated here.

---

## Sequencing & gating

1. **Order.** P1C-0 (this plan + decision record) → **ratification** (AD-017 + REQ-PPM/ENT/audit-taxonomy annotations, a separate governed commit, mirroring P1B-0 `4fae26b`) → **P1C-1** portfolio (+ synthetic reference seed) → **P1C-2** transactions → **P1C-3** positions → **P1C-4** valuations → **P1C-5** as-of holdings views → **P1C-6** synthetic dataset consolidation. Migrations `0012`→`0015` (P1C-5/P1C-6 add none).
2. **Per-slice cadence.** Plan → commit plan (on approval) → implement → **8-lens UltraCode adversarial review** (read-only) → fix in-scope findings → `make check` (ruff format + lint, mypy, pytest, secret-scan, docs-check) → add the slice's CI PG RLS step (transaction also adds an append-only step) → **commit on explicit approval** → watch CI to green. **Do not start the next slice until directed.**
3. **Hard invariants (every slice).** `audit/service.py` FROZEN; new audit codes/permissions/roles only via the governed R-07 update (taxonomy reserved at P1C-0, activated caller-side per slice); symmetric-never-hybrid RLS (closed hybrid set stays the 5); FR positions/valuations copy the `instrument_terms` protocol exactly; cross-tenant linked ids fail closed at the service layer; deny-by-default entitlements; no secrets in source; no BYPASSRLS app path.
4. **Scope fence (every slice).** No calculation, no derived governed output, no `dataset_snapshot`, no exposure aggregation, no market data, no pricing/valuation model, no corporate-action application, no netting/CSA, no risk/limits/reporting. Positions captured-not-derived; marks captured-not-computed; holdings listed-not-aggregated. **Inert numeric columns (`price`, `gross_amount`, `cost_basis`) are captured as provided and are NEVER recomputed or arithmetically cross-validated** (no `gross_amount == price × quantity` DQ rule, no per-holding `market_value = quantity × mark_value`) — that is calc, deferred.
5. **Readiness.** **P1C-1 is ready to plan** on approval — its prerequisites (portfolio EV model, symmetric RLS pattern, `PORTFOLIO.*` reservation, seeded `portfolio.*` reconciliation, synthetic reference seed) are all specified and grounded.
