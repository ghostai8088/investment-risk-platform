# P1C-1 Implementation Plan — Portfolio / Fund / Strategy / Account Hierarchy (ABAC scope anchor)

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1C1-PLAN-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-01 Chief Architect AI (with R-05 Data Architect AI, R-04 Security AI, R-07 Audit/Controls AI) |
| Approver | H-06 Engineering Lead (H-03 Security; H-08 Internal Audit — consulted) |
| Created | 2026-06-23 |
| Related Documents | `p1c0_decision_record.md`, `p1c_implementation_plan.md`, `p1b_closeout_p1c_readiness.md`, `p1b2_implementation_plan.md` (the `legal_entity` hierarchy precedent), `../02_requirements/requirements_backbone.md`, `../02_requirements/requirements_traceability_matrix.md`, `../04_data_model/canonical_data_model_standard.md`, `../04_data_model/temporal_reproducibility_standard.md`, `../04_data_model/audit_event_taxonomy.md`, `../06_security/entitlement_sod_model.md`, `../09_compliance_controls/control_matrix_skeleton.md`, `../11_decision_log/architecture_decision_log.md`, `packages/shared-python/src/irp_shared/reference/legal_entity.py`, `packages/shared-python/src/irp_shared/reference/service.py`, `packages/shared-python/src/irp_shared/entitlement/bootstrap.py` |
| Supported Build Rules | BR-3, BR-5, BR-7, BR-11, BR-13, BR-17, BR-19 |
| Decisions inherited | OD-P1C-A (anchor-not-enforce; portfolio-level; OD-025 closed), OD-P1C-B (subtree; OQ-014 closed), OD-P1C-C (single `portfolio` EV table + `node_type`), OD-P1C-L (synthetic seed), AD-017 (P1C capture-only domain). |

> **Purpose.** Realize **ENT-010** as a single `portfolio` EV table with a `node_type` controlled-vocab and a `parent_portfolio_id` self-FK adjacency — the platform's first **domain** (non-reference) entity and the **entitlement scope ANCHOR** for CAP-1. Governed CRUD on the P1A rails (symmetric RLS, co-transactional audit, MANUAL-source lineage, deny-by-default entitlement), a bounded cycle-safe hierarchy traversal (both ancestor and descendant), and the substrate a future ABAC grant will bind to. **No transactions/positions/valuations/holdings/aggregation/ABAC-enforcement** (those are later slices / P6+). This doc is planning only — no code, no migration is written here.

> **Prerequisite (governance, before the build slice):** the P1C-0 ratification (AD-017 + REQ-PPM-001 annotation + the audit-family reservation, §8) must be recorded first, mirroring P1B-0's plan→ratification split. See §16 OD-P1C1-1.

---

## 1. Requirements included

| REQ | Owns | Entity (this slice) | CAP | Acceptance clauses bound here | RTM transition |
|---|---|---|---|---|---|
| **REQ-PPM-001** | Portfolio/fund/strategy/account hierarchy + the **entitlement scope anchor** | `portfolio` (ENT-010, EV) | CAP-1 | a node tree persists; tenant-scoped; bounded hierarchy traversal (ancestor + descendant); is the scope anchor; governed CRUD audited + lineage-rooted | `Draft` → `In-Progress (P1C-1)` |

**Clause → deliverable → test binding (acceptance is provably mapped):**
- **node tree persists** → the `portfolio` EV table (migration `0012`) + `create_portfolio`/`update_portfolio` binders; round-trip CRUD test.
- **tenant-scoped** → symmetric RLS (`USING == WITH CHECK == own-tenant`, FORCE RLS) + the constrained-`irp_app` PG test (own visible / other-tenant invisible / no-context 0 rows).
- **bounded hierarchy traversal** → `resolve_ultimate_parent` (ancestor, reused shape) **and** a new `resolve_descendants` (subtree) — both `MAX_HIERARCHY_DEPTH=32`, visited-set, `HierarchyCycleError`, tenant-predicate per hop; cycle/self-parent/depth tests.
- **scope anchor** → the node `id` + `parent_portfolio_id` adjacency + the descendant resolver = the substrate a future `SCOPE-PORTFOLIO` grant binds to (§6); a test that the subtree of a node is computable and tenant-bounded. **No enforcement asserted.**
- **governed CRUD audited** → `PORTFOLIO.CREATE`/`PORTFOLIO.UPDATE` (or REFERENCE.* fallback — §8) co-transactional via the FROZEN `record_event`; literal-code assertion + `verify_chain`.
- **lineage-rooted** → origin edge `data_source(MANUAL) → portfolio` via `record_lineage` + `assert_has_lineage`.

**Synthetic reference seed (OD-P1C-L):** the synthetic reference seed pack (currencies, a calendar, a few legal_entities/issuers/instruments) is **not** built in P1C-1's product code; it is planned as a labeled, never-auto-run seed module that P1C-1 may land alongside (or defer to P1C-6). For P1C-1 the only seed need is a handful of synthetic portfolios for tests — created through the governed `create_portfolio` binder.

## 2. Requirements excluded

- **No transactions, positions, valuations, market values, holdings** (P1C-2/3/4; a portfolio in P1C-1 holds nothing — it is an empty hierarchy node).
- **No exposure aggregation, no risk calculation, no portfolio performance** (P2+; AD-014; REQ-PPM-004 deferred).
- **No corporate-action application; no `dataset_snapshot`** (excluded by P1C-0).
- **No portfolio-level ABAC ENFORCEMENT** (OD-P1C-A: anchor only; the `entitlement_grant` scope payload + scope-predicate reads → P6+). Unless explicitly approved (§16 OD-P1C1-4), P1C-1 ships **zero** scope-filtering.
- **No `node_type`-specific business semantics** beyond a soft permitted-parent validation (default permissive).
- **No materialized scope path / closure table** in P1C-1 (adjacency + bounded resolver only — §6; a denormalized path is a P6 enforcement optimization, OD-P1C1-5).
- **No FR/bitemporal columns** (portfolio is EV — no `system_from/system_to`).
- **No P1C-2/3/4 or P2+ work.**

## 3. Proposed entity

### 3.1 `portfolio` (ENT-010, EV) — single table, hierarchy node
| Column | Type | Notes |
|---|---|---|
| `id` | GUID PK | server-stamped |
| `tenant_id` | GUID NOT NULL, indexed | RLS scope; symmetric |
| `code` | String(150) NOT NULL | firm-assigned node code; `UNIQUE(tenant_id, code)` |
| `name` | String(255) NOT NULL | display name |
| `node_type` | String(50) NOT NULL | controlled-vocab **string** (no enum/CHECK): `PORTFOLIO`/`FUND`/`STRATEGY`/`ACCOUNT`; extend by value |
| `parent_portfolio_id` | GUID self-FK → `portfolio.id`, NULL=root, indexed | intra-tenant adjacency; self-parent rejected in service |
| `base_currency_code` | String(3), nullable | plain str (the P1B-3 no-FK-to-hybrid precedent), inert |
| `status` | String(30) NOT NULL, default `ACTIVE` | controlled-vocab; single status (NO `is_active`) |
| `description` | String(500), nullable | |
| `record_version` | Integer NOT NULL, default 1 | EV bump on amend |
| + `EffectiveDatedMixin` | `valid_from` / `valid_to` | EV effective-dating columns |
| + `TimestampMixin` | `created_at` / `updated_at` | |

- `__tablename__ = "portfolio"`; `__temporal_class__ = TemporalClass.EFFECTIVE_DATED`.
- `__table_args__`: `UniqueConstraint("tenant_id", "code", name="uq_portfolio_tenant_code")`.
- Register in `packages/shared-python/src/irp_shared/models.py` (import + `__all__`).
- **Column-name note (OD-P1C1-8):** the inherited OD-P1C-C wrote the adjacency column as `parent_id`; P1C-1 adopts **`parent_portfolio_id`** to mirror the shipped `legal_entity.parent_legal_entity_id` precedent — an editorial refinement (no scope change), to be recorded at the P1C-0 ratification.
- **Package:** a new `packages/shared-python/src/irp_shared/portfolio/` package (the first domain package) — `models.py` (the `Portfolio` class), `events.py` (`PORTFOLIO.*` constants), `service.py` (thin `record_portfolio_create`/`record_portfolio_update` mirroring `record_reference_create`/`update`), and the binder (`portfolio.py`). If the REFERENCE.* fallback (§8) is chosen, the binder reuses `reference/service.py` helpers and no `portfolio/events.py`/`service.py` are needed.

## 4. Temporal classification

- **EV** (`EffectiveDatedMixin`) — by the AD-005 §2A **default-for-a-new-entity** rule + the `legal_entity` hierarchy precedent (both EV); ENT-010 is not yet explicitly enumerated in the §2A EV list, so §18 commits to adding it at ratification. Matches REQ-PPM-001 (`portfolio/fund/strategy (EV)`). **NOT FR** (a portfolio node is not a risk-driving as-of-reconstructable input — that is positions/valuations, P1C-3/4) and **NOT IA** (the hierarchy is mutable: re-parenting, renaming, retiring nodes are in-place EV supersedes).
- **EV realization (the P1B reference-EV precedent):** a portfolio is a **single current-state row**; an amend (rename, re-parent, status change, effective-date change) is an **in-place supersede** — `record_version` bump + a `PORTFOLIO.UPDATE` audit event carrying the diff — **not** a new physical row. The `valid_from`/`valid_to` columns carry the effective-dating; there is **no system-time axis** (that is FR, reserved for P1C-3/4).
- Declared via `__temporal_class__` (BR-19); **not** in `APPEND_ONLY_TABLES` (EV is mutable; no `irp_prevent_mutation` trigger).

## 5. Hierarchy model

- **Adjacency list**: `parent_portfolio_id` self-FK (NULL = root), **intra-tenant** (a parent in another tenant fails closed). Mirrors the shipped `legal_entity.parent_legal_entity_id`.
- **Bounded traversal** (reuse the `legal_entity` safety invariants — `MAX_HIERARCHY_DEPTH = 32`, visited-set, `HierarchyCycleError`, explicit `tenant_id == acting_tenant` predicate on **every** hop, boundary-stop when a parent is not visible):
  - `resolve_ultimate_parent(session, portfolio, *, acting_tenant) -> str` — **ancestor / upward** walk (a direct reuse of the shipped `legal_entity.resolve_ultimate_parent` shape).
  - `resolve_descendants(session, portfolio, *, acting_tenant) -> list[Portfolio]` — **descendant / downward** subtree walk. This is a **NEW** bounded resolver (the shipped resolver only walks upward); it is built to the **same** invariants (visited-set, `MAX_HIERARCHY_DEPTH`, `HierarchyCycleError`, tenant filter) and is the substrate for subtree scope (OD-P1C-B).
- **`node_type` nesting**: a soft, **default-permissive** validation (recommended typical nesting `PORTFOLIO ⊃ FUND ⊃ STRATEGY ⊃ ACCOUNT`, but cross-pairings are not rejected in P1C-1 — the permitted-pair matrix is OD-P1C1-2). Self-parent is rejected (`ValueError`, the `legal_entity` precedent); cycles are rejected by the resolver's visited-set.
- **Re-parenting**: an `update_portfolio` that changes `parent_portfolio_id` re-runs the cycle guard (the new parent's ancestor chain must not contain the node) before committing.

## 6. ABAC scope-anchor design

This is the load-bearing design of the slice. **P1C-1 builds the anchor substrate; it does NOT enforce scope** (OD-P1C-A).

- **What the anchor IS:** the `portfolio.id` + the `parent_portfolio_id` adjacency + the `resolve_descendants` subtree resolver. A future `entitlement_grant` (P6+) will bind `subject → role → SCOPE-PORTFOLIO{portfolio_id, subtree=true}`; the **subtree semantics** (OD-P1C-B) mean a grant on a node reaches all its descendants — computable today via `resolve_descendants`, enforced later.
- **What P1C-1 delivers toward it:** (1) the hierarchy + bounded descendant resolver (so subtree membership is computable + tenant-bounded); (2) a documented mapping that `SCOPE-PORTFOLIO` will reference `portfolio.id`; (3) a test that the subtree of a node is correctly + tenant-safely computed. **Nothing reads or filters by scope.**
- **What P1C-1 does NOT deliver:** the `entitlement_grant` table, any scope payload, any scope predicate on `GET /portfolios`/holdings, any portfolio-scoped `require_permission`. `portfolio.view` gates by **role + tenant** only — within a tenant, any holder sees **all** portfolios (the residual risk, §15, acceptable only because P1C data is synthetic, OD-P1C-L).
- **ENT-P-06 (tenancy + portfolio scope mandatory on every entitled query, AD-008) is PARTIALLY satisfied:** the **tenant** attribute is enforced now (RLS + tenant-scoped reads); the **portfolio scope** attribute is **anchored (recorded), not enforced** — the second half of ENT-P-06 lands with the P6+ ABAC `entitlement_grant`. This is a deliberate, documented deferral, not a silent gap.
- **Representation choice (OD-P1C1-5):** **adjacency + on-demand bounded resolver** (recommended for P1C-1 — simplest, matches `legal_entity`) vs a **materialized `scope_path`/closure table** (O(1) subtree checks, a P6 enforcement optimization). Recommend adjacency-only now; revisit at ABAC-enforcement time.
- **Granularity (OD-025, closed):** **portfolio-level** (a grant scopes to a node + its subtree), **not** position-level.

## 7. APIs

Thin, bounded (mirror the reference routers). All under `get_tenant_session` + `require_permission`, `uuid.UUID` path params (422 + indistinguishable 404), single end-of-request commit.
- `POST /portfolios` — create (`portfolio.edit`).
- `GET /portfolios` — list (+ `?node_type` / `?parent_portfolio_id` filter) (`portfolio.view`).
- `GET /portfolios/{id}` — read one (`portfolio.view`).
- `POST /portfolios/{id}` — amend = EV supersede (rename / re-parent / status / effective dates) (`portfolio.edit`).
- `GET /portfolios/{id}/tree` — bounded subtree read via `resolve_descendants` (`portfolio.view`).

No delete (retire via `status`); no scope/holdings/aggregate endpoints.

## 8. Audit events

**Decision (item 7): mint a NEW `PORTFOLIO.*` family** — `PORTFOLIO.CREATE` / `PORTFOLIO.UPDATE`, reserved as a **fresh contiguous PORTFOLIO.* block** (the EVT index is **assigned by R-07 at reservation** — EVT-144+ is free after the REFERENCE EVT-140–143 block; the P1C domain corridor PORTFOLIO/TRANSACTION/POSITION/VALUATION takes successive blocks), activated caller-side via a new `irp_shared/portfolio/events.py` + a thin `record_portfolio_create`/`record_portfolio_update` that mirror the reference helpers and call the **FROZEN** `audit/service.record_event` (R-07; `audit/service.py` unchanged). `before/after` = DC-2 metadata only (code/name/node_type/parent link — never full rows); per-tenant chain (`chain_id = tenant_id`, no SYSTEM chain — portfolio is proprietary).

- **Rationale:** consistent with AD-017 (the P1C domain block gets its own families) and the coming `TRANSACTION.*`/`POSITION.*`/`VALUATION.*`; portfolio is **domain** data (CAP-1/BC-02), semantically distinct from the **reference-data** `REFERENCE.*` (BC-03). Establishing `PORTFOLIO.*` now sets the clean precedent for the whole block.
- **Fallback (lower governance):** reuse `REFERENCE.CREATE`/`UPDATE` (EVT-140/141), already activated + frozen — defensible because `portfolio` is structurally a near-twin of the EV `legal_entity` hierarchy (which reuses REFERENCE.*), and it avoids a taxonomy reservation. **The choice is the #1 open decision (OD-P1C1-1)** and is a **prerequisite governance step** either way (a new `PORTFOLIO.*` row, or an annotation that REFERENCE.* now covers portfolio, in `audit_event_taxonomy.md`).
- **Status changes:** a `status` flip rides on `PORTFOLIO.UPDATE` (no separate STATUS_CHANGE — the P1B reference precedent for `is_active`/status flips that are not a governed lifecycle).

## 9. Entitlement checks

- **Reuse the seeded catalog codes** `portfolio.view` and `portfolio.edit` (these exist in `bootstrap.py`; **not** `reference.portfolio.*`). Verified grant reality: `portfolio.view` is granted to `risk_analyst_1l` + `risk_manager_2l` (and `platform_admin` via `ALL_CODES`); **`portfolio.edit` is catalog-only — granted to `platform_admin` only**.
- **Additive change this slice (R-07):** grant a **maker** role both `portfolio.view` **and** `portfolio.edit` so non-admins can create/amend portfolios **and read their own writes**. **Recommend `data_steward`** (the established maker/steward for master/structural data; mirrors the reference-data steward `view`+`edit` pairing) — note `data_steward` currently holds **neither** code, so this grants **both** (an edit-only grant would leave the maker unable to read what it wrote). Recipient confirmation is OD-P1C1-3 (a dedicated `ROLE-PM`/`portfolio_manager` is a future option). `auditor_3l` stays **excluded** (scope SoD).
- Deny-by-default `require_permission` (module-level guard singletons); parity test pins the recipient sets (the existing `portfolio.view` recipients `risk_analyst_1l`/`risk_manager_2l` unchanged; **`data_steward` newly holds both `portfolio.view` + `portfolio.edit`**).

## 10. RLS behavior

- **Symmetric proprietary** loop (byte-for-byte the `0011`/`0009` loop): `ALTER TABLE portfolio ENABLE/FORCE ROW LEVEL SECURITY` + `CREATE POLICY tenant_isolation_portfolio USING (tenant_id::text = current_setting('app.current_tenant', true)) WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))`. `TENANT_SCOPED_TABLES = ("portfolio",)`.
- **NEVER hybrid** (AD-013-R1); the closed hybrid set stays the 5 P1B-1 tables (assert unchanged via `pg_policies`).
- `parent_portfolio_id` cross-tenant target **fails closed at the service layer** (`resolve_portfolio` explicit `tenant_id == acting_tenant` predicate raising `PortfolioNotVisible`) — RLS `WITH CHECK` only gates the writing row's own `tenant_id`.
- `set_config` (never parameterized `SET`); re-set tenant context after any commit before a read-back.

## 11. Lineage behavior

- One ORIGIN edge `data_source(MANUAL) → portfolio` on **create** (`ensure_manual_source` + `record_lineage`, server-stamped tenant, fail-closed); `assert_has_lineage` (CTRL-013).
- An EV **amend** adds **no** new edge (the node keeps its origin edge — the `record_reference_update`/`record_portfolio_update` precedent: update events root no edge).

## 12. DQ behavior

- Generic evaluators only: `not_null` on `code`/`name`/`node_type`; `allowed_values` on `node_type` (+ `status`). No domain DQ engine, no reconciliation (P7).
- **Inert** `base_currency_code` is captured as provided — **not** validated against the currency table at write (a soft data-dictionary obligation, CTRL-004, not a runtime FK/gate — the P1B-1 ISO-4217 precedent).

## 13. Tests

- **Logic (SQLite):** CRUD round-trip; EV amend (in-place supersede, `record_version` bump); `node_type`/`status` controlled-vocab; `UNIQUE(tenant_id, code)`; self-parent rejected; **cycle rejected** (`HierarchyCycleError`); **depth cap** (`MAX_HIERARCHY_DEPTH`); `resolve_ultimate_parent` (ancestor) and **`resolve_descendants` (subtree)** correctness + tenant-bounded; cross-tenant `parent_portfolio_id` → `PortfolioNotVisible`.
- **Endpoint:** the 5 routes; deny-by-default (no perm → 403); 422 on bad UUID; 404 indistinguishable for cross-tenant/unknown id; amend dispatch.
- **PG (constrained `irp_app`):** symmetric RLS (own visible / other-tenant invisible / **no-context → 0 rows**); forged-tenant-stamp write → 42501; FORCE-RLS + symmetric-policy structural assertion (`pg_policies`); **closed-hybrid-set unchanged**; hierarchy traversal isolation (a descendant in another tenant is not reachable).
- **Audit/lineage:** `PORTFOLIO.CREATE`/`UPDATE` (or REFERENCE.* fallback) emitted co-transactionally + `verify_chain`; origin edge present (`assert_has_lineage`); amend roots no new edge.
- **ABAC-anchor scope fence:** the subtree of a node is computable + tenant-bounded, **and** an explicit test that **no scope filtering / enforcement** is applied to `GET /portfolios` (any `portfolio.view` holder in the tenant sees all nodes) — the anchor-not-enforce contract.

## 14. Acceptance criteria

1. A tenant-scoped `portfolio` node tree persists (CRUD), is EV-mutable (amend supersedes in place), and enforces `UNIQUE(tenant_id, code)` (REQ-PPM-001).
2. Bounded hierarchy traversal works **both directions** (ancestor + descendant), is cycle-safe, depth-capped, self-parent-rejecting, and tenant-bounded.
3. The hierarchy is the **entitlement scope anchor**: a node's subtree is computable + tenant-safe; the `SCOPE-PORTFOLIO`→`portfolio.id` mapping is documented; **no scope enforcement ships**.
4. Governed CRUD is audited (`PORTFOLIO.*` or REFERENCE.* per OD-P1C1-1) + lineage-rooted; tenant isolation proven under FORCE RLS by the constrained-role PG tests.
5. `make check` green; the new portfolio symmetric-RLS CI step green; `alembic check` drift-clean; downgrade smoke green.

## 15. Risks

- **ABAC anchored-not-enforced (must be stated):** within a tenant, any `portfolio.view` holder reads **all** portfolios until the P6+ `entitlement_grant` scope payload lands — acceptable **only** because P1C data is synthetic (DC-1/DC-2). Real DC-3 portfolios stay gated behind P6+ ABAC.
- **New descendant resolver** has no shipped precedent (the shipped resolver walks upward) — mitigated by reusing the exact safety invariants + an explicit subtree test incl. a planted cycle.
- **Node-model over-design** — held by keeping P1C-1 to adjacency + `node_type` label + default-permissive nesting; the permitted-pair matrix is deferred (OD-P1C1-2).
- **Audit-family governance round-trip** — minting `PORTFOLIO.*` requires the R-07 reservation before the build; mitigated by doing it in the P1C-0 ratification step (OD-P1C1-1).
- **First domain package** (`irp_shared/portfolio/`) sets the structural precedent for positions/valuations — keep it a thin mirror of the reference package.

## 16. Open decisions (resolve before / at implementation)

| ID | Decision | Recommendation | ⚑ sign-off before build? |
|---|---|---|---|
| **OD-P1C1-1** | Audit family: new `PORTFOLIO.*` vs reuse `REFERENCE.*`. | **New `PORTFOLIO.*`** (AD-017-consistent; domain block) — a new contiguous EVT block, **index assigned by R-07 at reservation** (EVT-144+ is free; the P1C domain corridor PORTFOLIO/TRANSACTION/POSITION/VALUATION takes successive blocks). Reserve in the P1C-0 ratification step (a **prerequisite**). | ⚑ Yes |
| **OD-P1C1-2** | `node_type` permitted parent/child pairs (e.g. must ACCOUNT be a leaf?). | **Default-permissive** in P1C-1; record the typical nesting; enforce pairs only if a real need appears. | No |
| **OD-P1C1-3** | `portfolio.edit` maker recipient (and the matching `.view`). | Grant **`data_steward` BOTH `portfolio.view` + `portfolio.edit`** (the steward currently holds neither; both are needed so the maker can read its own writes); `platform_admin` already holds both via ALL_CODES; `ROLE-PM` a future option. | ⚑ Yes (additive grant = R-07) |
| **OD-P1C1-4** | Any ABAC **enforcement** in P1C-1? | **No** — anchor only (OD-P1C-A). Enforcement → P6+. | ⚑ Yes (confirm "no") |
| **OD-P1C1-5** | Scope representation: adjacency-only vs materialized `scope_path`/closure table. | **Adjacency + bounded resolver** now; materialized path is a P6 optimization. | No |
| **OD-P1C1-6** | `node_type='PORTFOLIO'` as a value vs the table name suffices. | **Keep `PORTFOLIO` as a valid top-container node_type** (vocab `PORTFOLIO/FUND/STRATEGY/ACCOUNT`, extensible). | No |
| **OD-P1C1-7** | **OD-013** (canonical) — portfolio hierarchy depth/flexibility: fixed levels vs arbitrary tree. | **Resolve OD-013 = arbitrary adjacency tree**, depth-capped at `MAX_HIERARCHY_DEPTH=32`, default-permissive `node_type` pairs (close OD-013 at ratification). | No |
| **OD-P1C1-8** | Adjacency column name: `parent_id` (OD-P1C-C wording) vs `parent_portfolio_id`. | **`parent_portfolio_id`** (mirrors the shipped `legal_entity.parent_legal_entity_id`) — an editorial refinement of OD-P1C-C's `parent_id`; record the chosen name at ratification. | No |

## 17. Controls impacted

P1C-1 makes these controls **executable** for the portfolio domain (no new CTRL minted — reuses the matrix). These cover the RTM-declared control set for REQ-PPM-001 (CTRL-001/005/011) plus the additional rails this slice exercises:
- **CTRL-001** (every feature has tests before completion — exercised by the §13 SQLite/endpoint/PG suite gated in `make check`; detective/automated).
- **CTRL-004** (data dictionary / field definition — `portfolio` columns + `node_type`/`status` vocab; preventive/manual).
- **CTRL-005** (data-changing actions emit audit events — `PORTFOLIO.CREATE`/`UPDATE`; detective/automated).
- **CTRL-006 / CTRL-013** (lineage capture + no-bypass — origin edge + `assert_has_lineage`; preventive/automated).
- **CTRL-011** (no entitlement/RLS bypass; deny-by-default + tenant isolation end-to-end; the constrained-role PG tests; preventive/automated).
- **CTRL-017** (temporal-class declared — `__temporal_class__ = EFFECTIVE_DATED`; preventive/detective).
- **CTRL-032** (fail-closed audit blocks the governed change; AUD-04; preventive/automated).

## 18. Documentation updates (in-slice deliverables, gated in the same build PR)

- **canonical_data_model_standard.md** — annotate **ENT-010**: realized P1C-1 (migration `0012`) as a single `portfolio` EV table + `node_type` (PORTFOLIO/FUND/STRATEGY/ACCOUNT) + `parent_portfolio_id` adjacency; `__temporal_class__ = EFFECTIVE_DATED`; the scope anchor. Also **close OD-013** (portfolio hierarchy depth/flexibility) = arbitrary adjacency tree, depth-capped at 32, default-permissive `node_type` pairs (OD-P1C1-7).
- **requirements_backbone.md + requirements_traceability_matrix.md** — REQ-PPM-001 `Draft` → `In-Progress (P1C-1: CRUD + hierarchy + scope anchor; ABAC enforcement deferred to P6+; exposure aggregation P2)`. Reconcile the backbone wording "portfolio/fund/strategy" with **ENT-010 incl. ACCOUNT** (P-01 from the P1C-0 review).
- **temporal_reproducibility_standard.md §2A** — add a P1C-1 realization note (ENT-010 EV, single-table hierarchy, MANUAL-source lineage, scope anchor).
- **audit_event_taxonomy.md** — record the chosen family (new `PORTFOLIO.*` block with the R-07-assigned EVT index **or** the REFERENCE.* extension to portfolio per OD-P1C1-1).
- **entitlement_sod_model.md** — record the `data_steward` maker grant of **both `portfolio.view` + `portfolio.edit`** (OD-P1C1-3) + the **OD-025 closure** (portfolio-level granularity) + auditor_3l exclusion.
- **architecture_decision_log.md** — ratify **AD-017** (if not already done in the P1C-0 ratification step).
- **control_matrix_skeleton.md** — note CTRL-004/005/006/011/013/017/032 now exercised by `portfolio`.
- **ci_enforcement_overview.md + .github/workflows/ci.yml** — add the "Portfolio symmetric-RLS tests (Postgres, REQ-PPM-001 / BR-17)" step in the `migration` job (after corporate-action, before downgrade).

## 19. Whether P1C-1 is ready to implement

**Ready to implement — conditional on the prerequisite governance step.** The entity, temporal class, RLS pattern, hierarchy resolver, lineage/audit/entitlement plumbing, and tests are all specified against shipped precedents (the `legal_entity` hierarchy is a near-twin). The **one blocker** is the P1C-0 ratification (AD-017 + REQ-PPM-001 annotation + the **audit-family reservation**, OD-P1C1-1) — `PORTFOLIO.*` must be reserved (or the REFERENCE.*-reuse decision recorded) before the build slice activates it. Resolve OD-P1C1-1/3/4 (the ⚑ items), run the ratification, then P1C-1 build is unblocked.

## 20. Exact implementation kickoff prompt (paste-ready)

> **DO NOT START until explicitly directed and until the P1C-0 ratification (AD-017 + REQ-PPM-001 annotation + the `PORTFOLIO.*` audit-family reservation) is recorded.** When directed, implement **P1C-1 (portfolio / fund / strategy / account hierarchy — the ABAC scope anchor)** per `10_delivery_backlog/p1c1_implementation_plan.md`.
>
> **Full scope (the deliverable cap — nothing beyond this):**
> 1. NEW web-framework-free package `irp_shared/portfolio/`: `models.py` (the `Portfolio` EV class — columns per §3.1; `__temporal_class__ = EFFECTIVE_DATED`; `UNIQUE(tenant_id, code)`; `parent_portfolio_id` self-FK), `events.py` (`PORTFOLIO.CREATE`/`PORTFOLIO.UPDATE` constants — or REFERENCE.* per OD-P1C1-1), `service.py` (`record_portfolio_create`/`record_portfolio_update` mirroring `record_reference_*`: ORIGIN MANUAL-source edge + create event; update = event only, no edge; fail-closed, no mid-call commit), and `portfolio.py` (the binder: `PortfolioNotVisible`, `resolve_portfolio`, `create_portfolio`, `update_portfolio` with re-parent cycle guard, `resolve_ultimate_parent` ancestor, **`resolve_descendants` subtree** — both `MAX_HIERARCHY_DEPTH=32` + visited-set + `HierarchyCycleError` + tenant predicate per hop). Register `Portfolio` in `irp_shared/models.py` (import + `__all__`).
> 2. ONE migration **0012** (`revision='0012_portfolio'`, `down_revision='0011_corporate_action'`) creating exactly `portfolio` with NAMING_CONVENTION names, `UNIQUE(tenant_id, code)`, the `parent_portfolio_id` self-FK, indices on `tenant_id` + `parent_portfolio_id`, and the **symmetric RLS loop** over `TENANT_SCOPED_TABLES = ("portfolio",)` (`USING == WITH CHECK == own-tenant`, ENABLE+FORCE). **No append-only trigger. Do NOT touch the hybrid loop, the closed hybrid set, or any prior migration.**
> 3. The EV entity exactly as specified (EV; `record_version`; controlled-vocab `node_type`/`status` as plain Strings; single `status`, no `is_active`; inert `base_currency_code`).
> 4. **Activate** the chosen audit family caller-side (per OD-P1C1-1) via the FROZEN `record_event`; `before/after` = DC-2 metadata only; per-tenant chain.
> 5. Entitlement: **grant `data_steward` BOTH `portfolio.view` + `portfolio.edit`** (OD-P1C1-3) additively in `bootstrap.py` (the steward currently holds neither — both are needed so the maker reads its own writes); the existing `portfolio.view` recipients (`risk_analyst_1l`/`risk_manager_2l`) are unchanged; deny-by-default guards on the routes; parity test pins both grants.
> 6. Backend router `apps/backend/.../api/portfolios.py` (the 5 routes in §7) registered in `main.py`; `get_tenant_session` + `require_permission`; `uuid.UUID` path params; single end-of-request commit.
> 7. Lineage: origin MANUAL-source edge per create; `assert_has_lineage`.
> 8. DQ: generic `not_null`/`allowed_values` where configured (§12) — no recomputation.
> 9. Tests: SQLite logic + endpoint + PG (constrained `irp_app`) per §13, incl. the bounded-resolver (ancestor + descendant + cycle + depth), cross-tenant fail-closed, the symmetric-RLS proofs, the closed-hybrid-set-unchanged assertion, and the **anchor-not-enforce scope-fence** test.
> 10. CI: add the "Portfolio symmetric-RLS tests (Postgres, REQ-PPM-001 / BR-17)" step. Governance doc updates per §18 in the same PR.
>
> **STRICT EXCLUSIONS:** no transactions/positions/valuations/holdings/market-values; no exposure aggregation/risk/performance; no ABAC enforcement / `entitlement_grant` / scope-filtering (anchor only); no materialized scope path; no `dataset_snapshot`; no corporate-action application; no FR columns; no P1C-2/3/4 or P2+ work; `audit/service.py` stays FROZEN.
>
> **Build sequence:** (1) `Portfolio` model + aggregator; `alembic check` sees new metadata. (2) Migration 0012 (DDL + symmetric RLS loop); `alembic upgrade head` + `alembic check` clean. (3) `portfolio/` package (events/service/binder + resolvers). (4) Entitlement grant + bootstrap parity. (5) Backend router + registration. (6) Tests (logic → endpoint → PG). (7) Governance doc updates + CI step. (8) `make check` green → PG validate on `postgres:16` → **8-lens UltraCode review** → fix in-scope → **commit on explicit approval** → watch CI green.

---

*Planning only — no code, no migration written in this turn. P1C-1 build begins only on explicit approval, after the prerequisite ratification.*
