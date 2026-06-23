# P1B Closeout & P1C Readiness Review

## Document Control

| Field | Value |
|---|---|
| Purpose | Confirm the P1B **Security-Master & Reference-Data** block is complete enough to support P1C (portfolio / position / valuation), decide whether **P1B-5** (reference ingestion mapping) is needed before P1C, and recommend a P1C subphase structure + synthetic-data strategy. |
| Status | **Closeout / readiness artifact — planning only; NO code, NO migrations.** |
| HEAD at writing | `060b2a4` (P1B-4 closed; project memory refreshed at `2069b1a`); origin/main clean. |
| Scope of this doc | Parts 1–6 (closeout, inventory, P1B-5 decision, P1C readiness, P1C subphase structure, synthetic-data strategy) + Part 7 (7-lens UltraCode review log) + Part 8 (P1C-0 open-decision / OQ register). Mirrors `10_delivery_backlog/p1a_closeout_p1b_readiness.md`. |
| Predecessor | `p1a_closeout_p1b_readiness.md` (the P1A→P1B equivalent). |

> **Grounding (verified this turn):** canonical ENT-010..014 (`04_data_model/canonical_data_model_standard.md:82-86`); temporal classes (`temporal_reproducibility_standard.md` §2A — position/valuation = FR, transaction = IA, exposure_aggregate = IA); REQ-PPM-001..004 (`requirements_backbone.md` CAP-1, all Draft) + RTM; OD-012/OD-015/OD-025 + AD-014 (the dataset-snapshot gate on exposure aggregation); ABAC declared-not-built (`entitlement_sod_model.md` ENT-P-06 / SCOPE-* / OD-025); the shipped rails (`irp_shared/{db,audit,entitlement,lineage,model,dq,ingestion,reference}`); the FR protocol (`reference/instrument_terms.py` `reconstruct_terms_as_of`).

---

## Part 1 — P1B closeout (per-slice)

All four P1B reference slices are **committed and CI-green**. Each is governed CRUD on the P1A rails: per-entity `REFERENCE.*` audit to the FROZEN `record_event`, one MANUAL-`data_source` ORIGIN lineage edge per created row, deny-by-default entitlements, the temporal class declared via `__temporal_class__`, and an entity-specific PG RLS CI step under the constrained `irp_app` role. 8-lens (P1B-2: 7-lens) UltraCode reviewed.

### 1.1 P1B-1 — currency / calendar(+holiday) / rating_scale(+grade)
| Field | Value |
|---|---|
| Commit / CI | `6568cb1` / **green (run #28)** |
| Entities | `currency` (ENT-005), `calendar` (ENT-006) + `calendar_holiday`, `rating_scale` (ENT-007 taxonomy) + `rating_grade` (migration `0008`) |
| Temporal | All **EV**; no append-only trigger |
| RLS | **FIRST asymmetric HYBRID loop (AD-013-R1):** `USING (own OR SYSTEM_TENANT) / WITH CHECK (own only)`; FORCE RLS; the **closed hybrid set = these 5 tables**; SYSTEM_TENANT global-read; tenant-override-wins is an app-layer `dedupe_tenant_wins`, never an RLS merge; `UNIQUE(tenant_id, code)` (never `UNIQUE(code)`) |
| Audit | `REFERENCE.CREATE` (EVT-140) / `REFERENCE.UPDATE` (EVT-141) ACTIVATED; children fold into the parent event; per-tenant + SYSTEM chains |
| Entitlements | additive `reference.currency.*` / `reference.rating_scale.*` / `reference.calendar.view` |
| Lineage | one MANUAL-source ORIGIN edge per row; SYSTEM seeds on the SYSTEM chain |
| DQ | generic `not_null`/`allowed_values` only (where configured) |
| Placeholders | governed SYSTEM seeder is test-proven, **not yet wired to a prod post-migrate path** (OQ-P1B1-001) |
| Follow-ups / risk | REQ-SMR-005 In-Progress (comprehensive global catalog deferred); REQ-SMR-004 calendar partial (roll math deferred). **No P1C blocker.** |

### 1.2 P1B-2 — legal_entity core + issuer / counterparty profiles
| Field | Value |
|---|---|
| Commit / CI | `32c7778` / **green (run #31)** |
| Entities | `legal_entity` (impl-only core, NO ENT id), `issuer` (ENT-002), `counterparty` (ENT-003) (migration `0009`) |
| Temporal | All **EV** |
| RLS | **SYMMETRIC** proprietary loop (`USING == WITH CHECK == own-tenant`); **NEVER hybrid**; no-context read → 0 rows; positive `pg_policies` + closed-hybrid-set-unchanged assertions; LEI partial-unique `(tenant_id, lei) WHERE lei IS NOT NULL` |
| Audit | reuse `REFERENCE.CREATE/UPDATE` — each entity its **own** event (NOT folded) |
| Entitlements | additive `reference.legal_entity.view/edit`; `.view` == issuer/counterparty.view set, **excludes `auditor_3l`** (proprietary-identity SoD) |
| Lineage | one MANUAL-source ORIGIN edge per row |
| DQ | generic only |
| Placeholders | hierarchy STRUCTURE only (`parent_legal_entity_id` + bounded `resolve_ultimate_parent`); **exposure-rollup CALC deferred**; `counterparty` has **ZERO netting/CSA/collateral/exposure columns (OD-015 → P1C)** |
| Follow-ups / risk | REQ-SMR-002 In-Progress (rollup calc → P2+); **OD-015 lands in P1C** (counterparty netting). **No P1C blocker.** |

### 1.3 P1B-3 — instrument / instrument_terms / identifier_xref
| Field | Value |
|---|---|
| Commit / CI | `8545ed6` / **green (run #34)** |
| Entities | `instrument` (ENT-001 identity, EV), `instrument_terms` (ENT-001 terms, **FR**), `identifier_xref` (ENT-004, EV) (migration `0010`) |
| Temporal | instrument EV; **instrument_terms FR — the platform's FIRST persisted `FullReproducibleMixin` user**; identifier_xref EV |
| RLS | SYMMETRIC proprietary (byte-for-byte the 0009 loop); NEVER hybrid; cross-tenant `issuer_id`/`instrument_id`/`entity_id` fail closed via the **service-layer** `*NotVisible` predicate pre-commit (RLS `WITH CHECK` gates only the row's own `tenant_id`) |
| Audit | reuse CREATE/UPDATE + **`REFERENCE.CORRECTION` (EVT-142) ACTIVATED** (R-07, OQ-7) for the FR as-known restatement; caller-side `record_reference_correction`; `audit/service.py` FROZEN; TR-08 reason + supersedes link |
| Entitlements | additive `reference.identifier.view/edit` (`.resolve` recipients UNCHANGED; `auditor_3l` excluded) |
| Lineage | per new FR version row gets its own ORIGIN edge; EV in-place update → no new edge |
| DQ | generic only |
| Placeholders | terms are inert (no pricing/cashflow/day-count/valuation math → P2+); identifier resolution is deterministic-or-`AmbiguousIdentifier`, **cross-vendor precedence deferred (OD-012 → P1C)**; polymorphic `entity_id` scoped to `instrument` |
| Follow-ups / risk | REQ-SMR-001/003 In-Progress; **OD-012 lands in P1C** (only if multi-vendor identifier authority is needed). The FR protocol (`reconstruct_terms_as_of`) is **the reusable template for P1C positions/valuations**. **No P1C blocker.** |

### 1.4 P1B-4 — corporate_action
| Field | Value |
|---|---|
| Commit / CI | `060b2a4` / **green (run #37)** |
| Entities | `corporate_action` (ENT-008, EV — **capture-only**) (migration `0011`) |
| Temporal | **EV**; one physical row; amend = in-place supersede; NOT IA, NOT FR; the EV `valid_from/valid_to` record axis is distinct from the inert business-date columns (announcement/ex/record/pay/effective) |
| RLS | SYMMETRIC proprietary (byte-for-byte the 0010 loop); `instrument_id` NOT-NULL FK resolved via the reused `resolve_instrument` (cross-tenant fails closed pre-commit) |
| Audit | reuse CREATE/UPDATE + **`REFERENCE.STATUS_CHANGE` (EVT-143) ACTIVATED** (R-07, OQ-1) — the platform's FIRST EVT-143 user — for the ANNOUNCED→CONFIRMED→CANCELLED lifecycle; caller-side `record_reference_status_change`; used ONLY for corporate_action; `audit/service.py` FROZEN |
| Entitlements | additive `reference.corporate_action.view` (== instrument.view set; `auditor_3l` excluded); `.edit` pre-existing unchanged |
| Lineage | one ORIGIN edge on create; amend / status transition add no new edge |
| DQ | generic only |
| Placeholders | **CAPTURE-ONLY** — no application to positions/valuations, no entitlement/tax calc, no event engine, **no roll/day-count math (QS-10/11 — a calc; repo-labeled "→ P1C" but it is math, OUTSIDE P1C's no-calc capture fence; lands in a calc phase, P1C+/P2)**; issuer-level corporate actions deferred (instrument-level only); single `status` lifecycle (no `is_active`) |
| Follow-ups / risk | REQ-SMR-004 In-Progress; **corporate-action APPLICATION is a later explicit phase (NOT P1C)** — P1C must keep them capture-only. **No P1C blocker.** |

### 1.5 Closeout confirmations
- ✅ **P1B-1..P1B-4 are committed** — `6568cb1`, `32c7778`, `8545ed6`, `060b2a4` (each preceded by a committed plan: `05ee5f5`/`410cc7e`/`43c042e`/`f6d691a`).
- ✅ **P1B-1..P1B-4 are CI-green** — runs #28, #31, #34, #37 (all 5 jobs each; the per-entity PG RLS steps under `irp_app` all pass; `alembic check` drift-clean; downgrade smoke green).
- ✅ **origin/main is clean** — HEAD `060b2a4` (impl) → `2069b1a` (memory refresh); working tree clean; 0 ahead/0 behind.
- ✅ **P1B-5 has NOT started** — no ingestion-mapping module; conditional/deferred.
- ✅ **P1C has NOT started** — no `0012` migration; no portfolio/position/valuation models.
- ✅ **No unresolved P1B defect blocks P1C** — every UltraCode review closed with 0 `block` findings and 0 behavioral defects; all confirmed findings were folded in before each commit. Carried-forward items (SYSTEM-seeder prod wiring, OD-012, OD-015, exposure-rollup calc, roll math, corporate-action application) are **deferred by design**, none gating P1C capture work.

---

## Part 2 — P1B rail / domain inventory (available to P1C)

### 2.1 Cross-cutting rails (P1A; reused throughout P1B; available to P1C)
| Rail | What P1C can use | What P1C must NOT assume | Known limitations |
|---|---|---|---|
| Tenant context / RLS | `set_tenant_context`/`get_tenant_session`; the **SYMMETRIC** loop (`USING == WITH CHECK == tenant_id::text=current_setting('app.current_tenant',true)`, FORCE RLS) — the pattern for ALL P1C proprietary tables; the constrained-`irp_app` PG test fixture | That RLS scopes **within** a tenant — it isolates tenants only. **Portfolio-level scoping is NOT in RLS** (it is ABAC, deferred — §4) | foundation `0001` policies are USING-only; re-set tenant context after any commit before a read-back |
| Audit + hash chain | `record_event` (co-transactional, fail-closed, advisory-lock per-tenant chain), `verify_chain`; the `REFERENCE.*`/`DATA.*`/`MODEL.*` families | That new event codes are free — a **new `PORTFOLIO.*`/`POSITION.*`/`TRANSACTION.*` (or reuse) family is a governed R-07 taxonomy change**; `audit/service.py` is **FROZEN** | reads not yet access-audited (OD-023) |
| Entitlement (RBAC) | deny-by-default `require_permission`; `bootstrap.py` catalog + ROLE templates; the **additive-permission + parity-test** pattern | That **portfolio-scope / ABAC** is enforced — it is **declared (ENT-P-06) but NOT built** (RBAC + tenant-RLS only; OD-025 open). A P1C `portfolio.view`/`position.view` grant gates by role+tenant, **not by which portfolios** | ABAC `entitlement_grant` + scope payload → P6+; maker-checker non-enforcing |
| data_source + lineage | `ensure_manual_source`, `record_lineage` (origin edge, server-stamped tenant, fail-closed), `assert_has_lineage` (CTRL-013) | That lineage query/graph/field-level exists (P7) | capture + retrieve-by-id only |
| Model registry | available; `assert_registered_model_version` (inventory-before-use gate) — **relevant once P1C does any calc** (valuation method, exposure) | That P1C capture needs it — position/valuation **capture** does not run models | calc binding is a later concern |
| Data quality | `run_quality_check`, `assert_passed_quality_checks`; generic `NOT_NULL`/`ALLOWED_VALUES` (extend by value) | that domain DQ evaluators exist | generic only; reconciliation/override → P7 (REQ-DQR-002/003) |
| Generic ingestion staging | `stage_upload`, `ingestion_batch` (IA status-mutable) + `ingestion_staged_record` (IA), CSV anti-corruption | That a staging→canonical **mapping exists** — it does not (that mapping is the deferred P1B-5/P1C deliverable) | CSV-only; in-DB JSON; AV no-op |
| Temporal mixins | **EV** `EffectiveDatedMixin`, **IA** `ImmutableAppendOnlyMixin` (+ `irp_prevent_mutation` P0001 trigger + `APPEND_ONLY_TABLES`), **FR** `FullReproducibleMixin`; `__temporal_class__` | That a class is implied — each P1C entity is classified deliberately (portfolio EV, transaction IA, position/valuation FR) | native-uuid CI lessons; GUID surfaces as str |
| Alembic / drift / downgrade | `alembic upgrade head` + `alembic check` (`compare_type=False`) + downgrade smoke; NAMING_CONVENTION; register models in `irp_shared.models` (import + `__all__`) | that type nuances auto-resolve | migrations sequential — next is **0012** |

### 2.2 Reference entities (P1B; available to P1C)
| Entity | What P1C can use | What P1C must NOT assume | Known limitations |
|---|---|---|---|
| `currency` (EV, hybrid) | a value-level ISO-4217 vocabulary; positions/valuations reference a **plain `currency_code` string** (the P1B-3 precedent — NOT a FK to the hybrid table, to avoid proprietary→hybrid coupling) | that a tenant has any currency rows (synthetic seed must create them) | hybrid; SYSTEM seed not prod-wired |
| `calendar` (+holiday) (EV, hybrid) | a calendar reference for future date/roll logic | that roll/day-count **math** exists — it does not (QS-10/11 is a calc, deferred to a calc phase; NOT P1C capture) | calendar entity only |
| `rating_scale` (+grade) (EV, hybrid) | the rating **taxonomy** | that rating **assignments** exist (FR, deferred) | taxonomy only |
| `legal_entity` / `issuer` / `counterparty` (EV) | the issuer/counterparty identities a position's instrument resolves to; `resolve_issuer`; the hierarchy + `resolve_ultimate_parent` | that **netting/CSA/collateral/exposure** columns exist on counterparty (**ZERO** — OD-015 → P1C) | rollup calc deferred (P2+) |
| `instrument` (EV) | **the spine of P1C** — a `position` keys to `instrument_id`; reuse `resolve_instrument` (explicit-tenant-predicate, fail-closed) for the position→instrument link | that an instrument carries terms/price/valuation (terms are FR on `instrument_terms`; price is P2 market data) | identity only |
| `instrument_terms` (FR) | **the reusable FR bitemporal protocol** (`reconstruct_terms_as_of(valid_at, known_at)`; create→supersede→correct; one-`now`; close-first; dual-open partial-unique) — the **template P1C `position`/`valuation` copy** | that terms drive valuation math (inert; P2+) | terms math deferred |
| `identifier_xref` (EV) | `resolve_identifier` (deterministic-or-`AmbiguousIdentifier`) if a P1C import resolves external ids to instruments | that cross-vendor **precedence** exists (OD-012 → P1C) | scoped to `entity_type='instrument'` |
| `corporate_action` (EV, capture-only) | the captured action records | that they are **applied** to positions/valuations — **NO application engine; P1C keeps them capture-only** | application is a later explicit phase |

---

## Part 3 — P1B-5 decision (reference ingestion mapping before P1C?)

**Recommendation: Option B + Option C — DEFER full P1B-5; begin P1C with direct governed-API writes seeded by a deterministic SYNTHETIC reference seed pack.**

| Question | Assessment |
|---|---|
| Does P1C require bulk reference ingestion now? | **No.** P1C portfolio/position/valuation **capture** needs a handful of instruments/issuers/currencies to exist and be resolvable — not a bulk CSV→canonical mapping. Positions reference instruments by the **internal `instrument_id`** (via `resolve_instrument`), which the governed binders already create. |
| Is direct API / seeded reference data enough for P1C? | **Yes.** The shipped reference binders + a deterministic synthetic seed pack (Part 6) create exactly the reference rows P1C tests/demos/UI need, governed (audit + lineage) the same way prod data is. |
| Would P1B-5 delay portfolio/position progress unnecessarily? | **Yes.** P1B-5 (mapping P1A-4 staged rows → reference tables, per-type field mapping, bulk lineage/DQ) is real work that does **not unblock** any P1C capability — it would push portfolio/position progress without benefit. |
| Risks of deferring P1B-5? | **Low, bounded.** The staging→canonical mapping stays unbuilt (already a documented deferral). When a **real bulk-loading need** arises (vendor/SFTP feeds, REQ-INT-002/003 → P9, or a large client onboarding), P1B-5 (or a vendor-adapter phase) is planned then — the rails (ingestion staging, lineage, DQ, audit) are already in place, so it is additive, not a rework. **No data-integrity risk**: synthetic seed rows are governed exactly like ingested rows. |
| Synthetic strategy needed before P1C? | **Yes** — see Part 6. A deterministic seed pack is the prerequisite that replaces P1B-5 for P1C. |

**Rejected:** Option A (do P1B-5 first) — premature; no P1C dependency, delays the domain. Full P1B-5 is **conditional/deferred** until a bulk-loading driver exists.

---

## Part 4 — P1C readiness

**Conclusion: READY to plan P1C** (the portfolio/position/valuation **capture + as-of reconstruction** scope), contingent on the P1C-0 open decisions (**Part 8**) and the synthetic seed pack (Part 6). The reusable rails + reference spine are all shipped; P1C is the first **domain-analytics** phase but its CAPTURE layer reuses proven patterns.

| Prerequisite | Status for P1C | Notes |
|---|---|---|
| tenant context / RLS | ✅ READY | symmetric loop for all P1C proprietary tables |
| audit | ✅ READY (governed addition) | a P1C event family (`PORTFOLIO.*`/`POSITION.*`/`TRANSACTION.*`/`VALUATION.*`, or a reused taxonomy) is an **R-07 governed** addition; `audit/service.py` FROZEN |
| entitlement | ⚠️ READY (RBAC) — **ABAC gap** | RBAC deny-by-default works; **portfolio-scope ABAC is declared (ENT-P-06) but NOT built** (OD-025 + OQ-014 open). P1C-1 builds the portfolio hierarchy as the **scope ANCHOR**; **portfolio-level access enforcement is deferred to P6+** — within a tenant, anyone with `portfolio.view` sees all portfolios until ABAC lands. **Real portfolios/positions are DC-3** (Confidential — strict entitlement + portfolio scope; masked in logs); P1C may ship without ABAC enforcement **only because P1C's own data is synthetic DC-1/DC-2 demo fixtures** (Part 6) — real DC-3 portfolios stay gated behind the P6+ ABAC enforcement. This must be stated explicitly in the P1C plan. |
| lineage | ✅ READY | origin edge per governed write |
| data quality | ✅ READY | generic rules |
| ingestion staging | ✅ READY (unused in P1C capture) | available; P1C uses direct API + synthetic seed |
| reference data | ✅ READY | currency/calendar/rating/legal_entity/issuer/counterparty all shipped |
| instruments | ✅ READY | `resolve_instrument` is the position→instrument link |
| identifiers | ✅ READY | `resolve_identifier` available (precedence deferred OD-012) |
| issuers / counterparties | ✅ READY | available; **counterparty netting/CSA (OD-015) lands in P1C** if exposure work needs it — but exposure CALC is gated to P2+ |
| corporate actions captured but not applied | ✅ READY (constraint) | **P1C must NOT apply corporate actions** to positions/valuations — capture-only holds; application is a later explicit phase |
| **dataset-snapshot mechanics (AD-014)** | ⚠️ GATE | **REQ-PPM-004 exposure aggregation is deferred to P2 BY DEFAULT** (AD-014 / DR-P1-2: no governed derived output without a bound, reproducible input snapshot). Per OQ-013a it **may re-enter P1C ONLY IF** a minimal `dataset_snapshot` skeleton (pinning the position/valuation record versions to the run) is built first — **this doc recommends NOT building it in P1C** (Part 8/OQ-D), so PPM-004 stays P2 and P1C delivers capture + as-of reconstruction with **NO exposure rollup calc**. |

**Net:** P1C is ready for **capture + as-of reconstruction** of portfolio/transaction/position/valuation. Two readiness caveats to carry into the P1C plan: (a) **ABAC portfolio-scope is not enforced yet** (P1C-1 builds the anchor; enforcement → P6+), and (b) **exposure aggregation is out of P1C scope** (AD-014 / dataset-snapshot → P2+).

---

## Part 5 — Candidate P1C subphase structure (planning-first; thin slices)

Each subphase keeps the P1B cadence: plan → commit plan → implement → 8-lens review → fix → `make check` + new PG RLS step → commit-on-approval → CI. Per-slice dimensions below are a **readiness sketch** (the full per-slice plan is authored at that subphase, not here).

### P1C-0 — Planning & decision record
- **Requirements:** none built — resolve the **Part 8** open-decision register (OQ-A…OQ-J): ABAC granularity (OD-025) + shape (OQ-014), position grain, valuation source model, dataset-snapshot stance (AD-014), transaction↔position relationship, corporate-action-application exclusion, OD-012/OD-015 scope, portfolio node model.
- **Excluded:** any code/migration. **Deliverable:** the P1C decision record + the P1C implementation plan skeleton; ratify into governance (canonical/temporal/RTM) as P1B-0 did.
- **Acceptance:** every P1C-1..N entity has a ratified temporal class, RLS model, audit-event decision, and entitlement plan. **Risks:** mis-scoping ABAC or pulling exposure/risk forward. **OQs:** the **Part 8** register (OQ-A…OQ-J).

### P1C-1 — portfolio / fund / strategy / account hierarchy (EV)
- **Requirements:** REQ-PPM-001 (the **entitlement scope anchor**). **Excluded:** ABAC enforcement (P6+), positions/valuations.
- **Entities:** `portfolio` (+ fund/strategy/account as **either** one polymorphic `node_type` table **or** separate tables — a P1C-0 decision; recommend a single `portfolio` EV table with a `node_type` controlled-vocab + `parent_id` self-FK, mirroring `legal_entity`'s adjacency + bounded `resolve_ultimate_parent`).
- **APIs:** thin `POST/GET /portfolios (+/{id})`, hierarchy read. **Audit:** `REFERENCE.*` or a new `PORTFOLIO.*` family (R-07 decision). **Entitlement:** additive `portfolio.view/edit` (deny-by-default; **scope anchor recorded, not enforced**). **RLS:** symmetric proprietary. **Lineage:** origin edge per node. **DQ:** generic. **Tests:** hierarchy + cycle-safe resolver, cross-tenant fail-closed, audit/lineage, PG RLS. **Acceptance:** a tenant-scoped node tree persists and is the scope anchor (REQ-PPM-001). **Risks:** node-model over-design. **OQs:** node-type modeling; whether `account` is a leaf.

### P1C-2 — transaction skeleton (IA append-only)
- **Requirements:** REQ-PPM-003 (transaction half). **Excluded:** position **derivation** from transactions (a calc — deferred), settlement/cash engines.
- **Note (review ARCH-2 / OQ-E):** the P1C-2→P1C-3 order is **provenance ordering only** — `transaction` (IA log) and `position` (FR master) are **captured independently**; there is **no transaction→position derivation edge** in P1C (derivation is a deferred calc).
- **Entities:** `transaction` (**IA** — the first real **domain** IA use beyond the rails; in `APPEND_ONLY_TABLES`; `irp_prevent_mutation` P0001 trigger; mirror `ingestion_staged_record`/`lineage_edge`). Keyed to portfolio + instrument; trade/settle dates, quantity, price (inert capture).
- **APIs:** `POST/GET /transactions`. **Audit:** create event (no update — append-only). **Entitlement:** `transaction.view/edit`. **RLS:** symmetric. **Lineage:** origin edge. **DQ:** generic. **Tests:** **append-only DB-trigger proof** (the IA negative-control pattern — grant UPDATE/DELETE so the rejection is the P0001 trigger, not a privilege denial), cross-tenant, audit/lineage, PG RLS. **Acceptance:** transactions immutable (REQ-PPM-003). **Risks:** scope creep into a settlement/derivation engine. **OQs:** transaction taxonomy breadth; corrections-as-reversals (append a reversing txn, never mutate).

### P1C-3 — position skeleton (FR bitemporal)
- **Requirements:** REQ-PPM-002 (position master, as-of). **Affirmative invariant (review DA-3 / OQ-E):** P1C captures `position` **directly as the authoritative FR holdings master** (REQ-PPM-002 single-source-of-holdings) — positions are **NOT derived/reconstructed from the transaction event log**; no derivation engine exists in P1C. **Excluded:** position-from-transaction derivation calc; risk/exposure.
- **Entities:** `position` (**FR** — reuse the P1B-3 `instrument_terms` protocol: `valid_from/valid_to` + `system_from/system_to`; create → effective-dated supersede → as-known correction; `reconstruct_position_as_of(valid_at, known_at)`; one-`now`; close-first; dual-open current-head partial-unique on `(tenant_id, portfolio_id, instrument_id)`). Keyed to **portfolio_id + instrument_id** (both resolved tenant-filtered, fail-closed).
- **APIs:** `POST/GET /positions`, `/positions/as-of`. **Audit (review AUD-02):** an R-07 decision — a **new `POSITION.*` family OR a justified REFERENCE.* reuse** (do NOT assume EVT-142 reuse; EVT-142 is the reference-domain restatement code). **Entitlement:** `position.view/edit`. **RLS:** symmetric; cross-tenant portfolio_id/instrument_id fail closed at the service layer. **Lineage (review LDQ-2):** one ORIGIN edge per **NEW version row** (create + as-known correction root an edge; the close-first supersede of the prior head adds none) — mirroring §1.3. **DQ:** generic. **Tests:** **as-of reconstruction on BOTH axes** (the P1B-3 acceptance pattern), content-immutability, cross-tenant fail-closed, PG-under-FORCE-RLS. **Acceptance:** a position reconstructable for any past as-of (REQ-PPM-002). **Risks:** FR-protocol mis-reuse (mitigated — proven in P1B-3); position **grain** (lot vs aggregate). **OQs:** grain; long/short; quantity vs market-value capture (Part 8/OQ-C).

### P1C-4 — valuation skeleton (FR bitemporal)
- **Requirements:** REQ-PPM-003 (valuation half). **Excluded:** pricing/valuation **math** (mark sourced/captured, not computed — P2 market data + calc).
- **Entities:** `valuation` (**FR**, same protocol). Keyed to position (or instrument) + valuation date; captured value + currency + mark source (inert). **Reuses** the FR template.
- **APIs:** `POST/GET /valuations`, `/valuations/as-of`. **Audit (review AUD-02):** an R-07 decision — a new `VALUATION.*` family OR a justified REFERENCE.* reuse (NOT an assumed EVT-142 reuse). **Lineage (review LDQ-2):** one ORIGIN edge per NEW version row (create + correction root an edge; the supersede adds none). **Entitlement/RLS/DQ:** as P1C-3. **Tests:** as-of both axes; mark-source captured-not-computed scope fence; PG RLS. **Acceptance:** valuations queryable as-of (REQ-PPM-003). **Risks:** valuation-math creep. **OQs:** valuation source model (Part 8/OQ-F — dirty/clean; which source wins — a precedence echo of OD-012).

### P1C-5 — as-of portfolio / holdings views (read-only)
- **Requirements:** the read half of REQ-PPM-001/002/003. **Excluded:** **exposure aggregation (REQ-PPM-004 → P2+ by AD-014)**; any rollup/derived governed number.
- **Entities:** none new — read endpoints composing the hierarchy + positions + valuations as-of. **APIs:** `GET /portfolios/{id}/holdings?as_of=` (a tenant-scoped, RLS-bounded as-of read; **no computed exposure**). **Audit:** read-not-audited (OD-023). **Entitlement:** view perms. **Tests:** as-of holdings correctness; tenant isolation; **scope-fence: NO aggregation/exposure number is computed**. **Acceptance:** holdings reconstructable as-of, per portfolio. **Risks:** sliding into exposure rollup (the AD-014 gate). **OQs:** view shape; pagination.

### P1C-6 — synthetic portfolio dataset (deterministic; could land earlier)
- **Requirements:** test/demo/UI enablement (not a product REQ). **Excluded:** real client/vendor data.
- **Deliverable:** a deterministic synthetic dataset builder (Part 6) — portfolios + transactions + positions + valuations over the synthetic reference seed. **Recommend landing the synthetic *reference* seed in P1C-0/P1C-1 and the synthetic *portfolio* dataset per-slice as each entity arrives** (so each subphase has realistic fixtures), with P1C-6 consolidating a full coherent demo dataset.
- **Tests:** the builder is deterministic + governed (audit/lineage). **Acceptance:** a reproducible, non-sensitive demo portfolio exists. **Risks:** synthetic data leaking into prod paths (mitigate: a clearly-labeled seed module, never auto-run). **OQs:** dataset size/shape.

---

## Part 6 — Synthetic data strategy

**Recommendation: YES — establish a deterministic synthetic-data strategy as a P1C prerequisite** (it replaces P1B-5 for P1C and underpins tests/demos/UI/future visualization).

- **Synthetic reference seed pack** — a deterministic set of governed reference rows (a few `currency`, a `calendar`, several `legal_entity`/`issuer`/`counterparty`, a handful of `instrument` + `instrument_terms` + `identifier_xref`, a couple of `corporate_action`) created through the **existing governed binders** (so they carry audit + MANUAL-source lineage exactly like prod). Lands in P1C-0/P1C-1.
- **Synthetic portfolio / position dataset** — deterministic portfolios + transactions + positions + valuations over the seed instruments, exercising the FR as-of reconstruction (multiple valid/known versions). Lands per-slice + consolidated at P1C-6.
- **Deterministic seed approach** — `uuid5`-derived ids from fixed namespaces; fixed timestamps passed in (never `Date.now()`/random); reproducible across runs and machines (the P1A-4/bootstrap precedent). A re-run produces byte-identical ids.
- **No real client / vendor data** — synthetic only; no vendor feeds; no DC-4 MNPI. **Note (review PR-3/SEC-02):** the portfolio/position entity **TYPE is canonically DC-3** (Confidential — client portfolios/positions); the synthetic *instances* carry no real client data, so they are treated as **DC-1/DC-2 demo fixtures**. This is what lets P1C ship before ABAC enforcement — the demo data is non-sensitive *because it is synthetic*, not because the entity class is non-confidential. Real DC-3 portfolios stay gated behind the P6+ ABAC scope enforcement.
- **Intended use** — unit/endpoint/PG tests, local demos, the frontend/UI, and future visualization work. A **labeled, never-auto-run** seed module (analogous to the governed SYSTEM seeder — test-proven, not wired to a prod post-migrate path).

---

## Part 7 — UltraCode adversarial-review log (this turn)

The doc was reviewed by a 7-lens UltraCode workflow (Product, Architect, Data, Security/RLS, Audit/Controls, Lineage/DQ, Scope); every HIGH/MEDIUM finding was independently, adversarially verified. Verdicts: **all 7 lenses `approve_with_changes` — no `block`, no HIGH.**

**Confirmed findings — folded in:**
- **Dangling open-decisions cross-reference** (raised by 5 lenses — PR-1/ARCH-1/DA-2/SEC-01/LDQ-1/SCOPE-1, MEDIUM): the P1C-0 open-decisions list was referenced but not anchored as a section. **Fixed** by adding **Part 8 (P1C-0 open-decision / OQ register)** and repointing those references to Part 8 (Document Control scope updated to Parts 1–8).
- **Exposure-aggregation deferral is conditional, not unconditional** (DA-1/PR-2, LOW): per AD-014 / DR-P1-2 / OQ-013a, REQ-PPM-004 is deferred to P2 **by default** and may re-enter P1C **only if** a minimal `dataset_snapshot` skeleton is built first — this doc recommends **not** building it (Part 4 GATE row, Part 8/OQ-D, readiness summary).
- **Positions are captured directly, not derived from transactions** (DA-3): added as an affirmative P1C invariant in P1C-3 (REQ-PPM-002 single-source-of-holdings; no transaction→position derivation engine), plus a provenance-ordering note in P1C-2 (ARCH-2).
- **DC-3 framing** (PR-3/SEC-02): real portfolios/positions are **DC-3** (strict entitlement + portfolio scope); the synthetic *instances* are DC-1/DC-2 demo fixtures — P1C may ship without ABAC enforcement *because the demo data is synthetic*, with real-DC-3 access gated by the P6+ ABAC enforcement (Part 4 entitlement row, Part 6).
- **FR-slice audit + lineage precision** (AUD-02/LDQ-2): P1C-3/P1C-4 audit family is an **R-07 decision** (a new `POSITION.*`/`VALUATION.*` family or a justified REFERENCE.* reuse — NOT an assumed EVT-142 reuse); lineage is "one ORIGIN edge per NEW version row (create + correction root an edge; the close-first supersede adds none)".
- **OQ-014 + QS-10/11 label** (DA-4/SCOPE-2): added OQ-014 (node-vs-subtree ABAC scope granularity) alongside OD-025 in Part 8; clarified the QS-10/11 roll/day-count deferral is **math** (P2+, outside P1C's no-calc capture fence).

**Verified non-defects (no change):** DA-3 (the "captured not derived" invariant was already present as an exclusion — added the affirmative line for clarity only). No finding survived as a behavioral or scope defect; nothing was a `block`.

**Unchanged conclusions after review:** P1B delivered; P1B-5 deferred (Option B+C); P1C ready to plan for capture + as-of reconstruction; exposure aggregation out of P1C scope; the two caveats (ABAC enforcement → P6+; dataset-snapshot gate). **P1C-0 is ready to plan.**

---

## Part 8 — P1C-0 open decisions / OQ register (to resolve in the P1C-0 decision record)

These are the load-bearing decisions a P1C plan must ratify (the inventory the P1C-0 planning slice resolves; this register replaces the earlier inline-only list). None is a code change; each is a design ratification.

| # | Open decision | Source | Recommendation (to confirm in P1C-0) |
|---|---|---|---|
| OQ-A | **ABAC scope granularity** — position-level vs portfolio-level access. | OD-025 (`entitlement_sod_model.md`) | Portfolio-level scope anchor in P1C-1; **enforcement deferred to P6+**. |
| OQ-B | **ABAC scope shape** — node vs subtree (a grant on a portfolio node implies its descendants?). | OQ-014 (`p1_scoping_plan.md` / `p1_decision_record.md`) | Subtree semantics on the hierarchy (descendant inheritance), recorded with the anchor; enforcement → P6+. |
| OQ-C | **Position grain** — lot-level vs aggregated-by-instrument; long/short; quantity vs market-value capture. | new (P1C-3) | Aggregated-by-(portfolio, instrument) FR position for the skeleton; lot-level deferred. |
| OQ-D | **Exposure aggregation (REQ-PPM-004) re-entry** — deferred to P2 by default (AD-014/DR-P1-2); re-enters P1C **only if** a minimal `dataset_snapshot` skeleton is built first. | AD-014, DR-P1-2, OQ-013a | **Do NOT build the snapshot skeleton in P1C** — keep P1C capture-only; PPM-004 stays P2. |
| OQ-E | **Transaction ↔ position relationship** — capture both independently vs derive positions from transactions. | new (P1C-2/P1C-3) | **Capture positions directly** (authoritative FR holdings master, REQ-PPM-002); transactions are an independent IA log; **no derivation engine** in P1C. |
| OQ-F | **Valuation source model** — which mark/source; dirty vs clean; source precedence. | new (P1C-4) | A single captured value + currency + mark-source label (inert); valuation **math** and source precedence → P2 (an echo of OD-012). |
| OQ-G | **Corporate-action application** — confirm it stays **out of P1C**. | OD-P1B-B (capture-only) | **Excluded from P1C**; application is a later explicit phase. |
| OQ-H | **OD-012 identifier precedence** — needed in P1C? | OD-012 (→ P1C) | Only if a P1C import resolves multi-vendor identifiers; the position→instrument link uses the internal `instrument_id`, so **likely not needed in P1C** — confirm. |
| OQ-I | **OD-015 counterparty netting/CSA** — needed in P1C? | OD-015 (→ P1C) | Only if P1C captures derivative/collateral positions; **defer** unless a P1C slice requires it (exposure CALC is P2+ regardless). |
| OQ-J | **Portfolio node model** — single polymorphic `node_type` table vs separate fund/account/strategy tables; new event family vs REFERENCE.* reuse. | new (P1C-1) | Single `portfolio` EV table with a `node_type` controlled-vocab + `parent_id` self-FK (the `legal_entity` precedent); audit-family choice is an R-07 decision. |

---

## Readiness summary

- **P1B is DELIVERED** (P1B-1..P1B-4 committed + CI-green; the Security-Master & Reference-Data reference entities ENT-001..006/008 are realized). REQ-SMR-001..005 stay In-Progress with their documented deferrals.
- **P1B-5 is DEFERRED** (Option B+C) — P1C proceeds on direct governed-API writes + a deterministic synthetic seed pack; full ingestion mapping waits for a bulk-loading driver.
- **P1C is READY to plan** for portfolio/transaction/position/valuation **capture + as-of reconstruction**, reusing the EV/IA/FR patterns proven in P1B (the `instrument_terms` FR protocol is the position/valuation template). Two caveats carried into the P1C plan: **ABAC portfolio-scope is not enforced yet** (anchor in P1C-1; enforcement → P6+) and **exposure aggregation is out of scope** (deferred to P2 by default; re-enters P1C only if a `dataset_snapshot` skeleton is built first, which this doc recommends against — Part 8/OQ-D).
- **Open decisions to resolve in P1C-0:** Part 8 (OQ-A…OQ-J).
- **Next action:** P1C-0 (planning & decision record) — on explicit approval.
