# P1C-5 Implementation Plan — As-of Holdings / Portfolio Views (read-only composition)

## Document Control

| Field | Value |
|---|---|
| Document ID | `p1c5_implementation_plan` |
| Version | 1.0 (planning) |
| Status | DRAFT — planning only; not approved; no code written |
| Owner | Platform engineering (Claude Code, UltraCode cadence) |
| Approver | H-06 Engineering Lead (sign-off pending) |
| Created | 2026-06-18 (as-of clock; see project memory `uncertain_values`) |
| Related documents | `10_delivery_backlog/p1c_implementation_plan.md` (§P1C-5); `p1c4_implementation_plan.md`; `p1c3_implementation_plan.md`; `p1c0_decision_record.md`; `02_requirements/requirements_backbone.md`; `06_security/entitlement_sod_model.md`; `09_compliance_controls/control_matrix_skeleton.md`; `11_decision_log/architecture_decision_log.md` (AD-014/AD-017) |
| Supported build rules | BR-11 (deny-by-default entitlement), BR-12 (tenant isolation / RLS), BR-17 (RLS symmetric for proprietary), BR-19 (temporal class declared — inherited from the read entities), and the AD-017 capture-only posture (this slice **computes nothing**) |
| Decisions inherited | OD-P1C-A (portfolio-scope **anchor-not-enforce** → P6+); OD-P1C-B (subtree = **descendant composition** via the bounded resolver; enforcement deferred); OD-P1C-F (valuation marks are **captured, display-only, never computed**); OD-P1C-G (**no `dataset_snapshot`** in P1C); OD-P1C-H (**exposure aggregation → P2**, REQ-PPM-004); OD-023 (read access-audit open → no-emit precedent); AD-014/AD-017 (exposure/risk/snapshot deferred) |

> **One-line framing.** P1C-5 adds a thin **read-only composition layer** that reconstructs the **set of holdings** in a portfolio (or bounded subtree) **as-of** any `(valid_at, known_at)` by composing the already-shipped `portfolio` hierarchy reads + `position` FR as-of reads + (optionally, display-only) `valuation` FR marks. **No new entity, no migration, no new write verb, no new permission, no audit event, no aggregation, no derived number.** It lists stored holdings; it never sums, rolls up, weights, prices, or computes market value.

---

## 1. Requirements included

P1C-5 realizes the **read / as-of-reconstruction half** of capabilities already captured by P1C-1…P1C-4 — it adds **no new requirement** and **closes none**:

- **REQ-PPM-001** (portfolio hierarchy, In-Progress) — *read half*: enumerate holdings organized by the portfolio node (and, for convenience, its bounded subtree). The hierarchy remains the **scope anchor**; P1C-5 traverses it for **composition**, not enforcement.
- **REQ-PPM-002** (position master, as-of; In-Progress) — *read half*: "single source of holdings" surfaced as a **set-returning as-of holdings read** across both bitemporal axes. P1C-5 does **not** close REQ-PPM-002 (the residual portfolio-scope ABAC-enforcement conjunct stays → P6+).
- **REQ-PPM-003** (valuation history; **Done**) — *read half*: a holding row **may** carry its captured mark (display-only) when explicitly requested. No new obligation; REQ-PPM-003 stays Done.

**Net:** P1C-5 is a **query-layer composition** over already-satisfied capture. No REQ status changes (OD-P1C5-5).

---

## 2. Requirements excluded (and where they live)

| Excluded | Where it lives |
|---|---|
| Exposure aggregation / rollup / sum / net / weight / % / total | **REQ-PPM-004 → P2** (AD-014, OD-P1C-H) |
| Market value = `quantity × mark_value` (any derived governed number) | P2 valuation/exposure (OD-P1C-F: marks captured, never computed) |
| `dataset_snapshot` / as-of pinning table | **P2** (OD-P1C-G — P1C composes FR as-of columns directly) |
| Risk calculations (VaR / Expected Shortfall / factor / sensitivities) | P2+ risk analytics (ENT-027/028) |
| Market-data / price lookup; pricing or valuation model | P2 market data (ENT-020–025) |
| Position derivation from transactions | Out of scope permanently in P1C (OD-P1C-E: positions are **captured**, not derived) |
| Corporate-action application to holdings | P2+ (OD-P1C-B for P1B-4; no application engine) |
| Performance / returns / attribution | P2+ |
| Reporting dashboards / presentation layer | P2+ (real reporting/SSO) |
| Real SSO / OIDC | P2+ |
| P1C-6 synthetic dataset | Separate slice, separately planned/approved |

---

## 3. Proposed read models / service functions

All new code is **read-only, side-effect-free** (no INSERT/UPDATE/DELETE, no `record_event`, no `record_lineage`, no `db.commit()`). New thin composition package **`irp_shared/holdings/`** — **no `models.py`, no `events.py`, no migration**; service read functions only:

- **`reconstruct_holdings_as_of(session, *, acting_tenant, portfolio_id, valid_at, known_at=None) -> list[HoldingRow]`**
  The core set-returning generalization of `reconstruct_position_as_of`: applies the identical half-open bitemporal predicate over the `position` table **filtered to one `portfolio_id`**, returning the as-of position version **per `instrument_id`** (the holding set). One row per instrument; the **stored** `quantity`/`cost_basis`/`valid_from`/`record_version` only. No computed field.
  - Valid-time: `valid_from <= valid_at AND (valid_to IS NULL OR valid_to > valid_at)`
  - System-time: `system_from <= known AND (system_to IS NULL OR system_to > known)` (`known` defaults to `utcnow()`)
  - Tenant predicate: `tenant_id == acting_tenant` (defense-in-depth atop RLS).
- **`reconstruct_subtree_holdings_as_of(session, *, acting_tenant, portfolio_id, valid_at, known_at=None) -> list[HoldingRow]`**
  First calls `resolve_portfolio(session, portfolio_id, acting_tenant=...)` to obtain the **`Portfolio` object** (fail-closed on unknown/cross-tenant), then passes that **object** (not the id string) to the existing `resolve_descendants(session, portfolio, acting_tenant=...)` to get the bounded, cycle-safe, tenant-predicated descendant set, then runs `reconstruct_holdings_as_of` over `portfolio_id IN {node ∪ descendants}` (the node's own id is unioned explicitly — `resolve_descendants` excludes the root). Each returned row carries its owning `portfolio_id`. **Composition, not enforcement** (OD-P1C-B). Reuses `MAX_HIERARCHY_DEPTH=32` + `HierarchyCycleError` (surfaced as 409 at the endpoint).
- **`attach_marks_as_of(session, *, acting_tenant, holdings, valuation_date, valid_at, known_at=None) -> list[HoldingWithMark]`** *(opt-in, gated)*
  For each holding, looks up the captured mark via the existing `reconstruct_valuation_as_of(portfolio_id, instrument_id, valuation_date, valid_at, known_at)` and attaches the **stored** `mark_value`/`currency_code`/`mark_source`/`valuation_date` as a **display-only** block. **No arithmetic** — never `quantity × mark_value`, never a total. A holding with no mark for that `valuation_date` returns `mark = null`.

`HoldingRow` / `HoldingWithMark` are **plain read DTOs** (dataclass/Pydantic), **not ORM entities** — they are not persisted, not registered in `irp_shared.models`, and have no temporal mixin (they carry the underlying rows' temporal columns verbatim for transparency).

**Import direction:** `holdings → {portfolio, position, valuation, reference, rails}` only. The new package gets its own **outbound** allowlist test. The **inbound** property ("nothing imports `holdings`") is already enforced by the **existing per-package allowlist tests** of `portfolio`/`position`/`valuation`/`reference` (none of which list `holdings`); the build must NOT add `holdings` to any of those allowlists.

---

## 4. Database views vs service-layer views

**Decision (recommended): service-layer read models only — no database view, no migration (OD-P1C5-1).**

Rationale:
- A DB view would add **migration surface + its own RLS policy + an `alembic check` drift target** for zero functional gain at this read scale; the composition is naturally expressed by reusing the already-tested, tenant-predicated resolvers in-process.
- Service-layer composition keeps the **anchor-not-enforce** posture explicit and testable in Python (the subtree traversal is visibly a read convenience), and keeps the slice **migration-free** — consistent with `migration_head` staying `0015_valuation`.
- A DB view is reconsidered only if a future slice needs set-based pushdown for performance; that would be its own decision with its own migration + RLS step. Not now.

---

## 5. As-of reconstruction approach

- **Both bitemporal axes**, identical half-open semantics to the per-entity reads. To match the shipped primitive `reconstruct_position_as_of` (where `valid_at` is **required** and only `known_at` defaults), **`valid_at` is a required query parameter** and **`known_at` is optional (default = now = current view = latest system-known)**. A single `(valid_at, known_at)` pair governs the whole composed result, so the holdings set, and any attached marks, are **mutually consistent at one point in bitemporal space**.
- The holdings set is the **as-of current head per instrument**: for each `(portfolio_id, instrument_id)` the one position version whose valid- and system-intervals both contain the requested instants. Superseded/corrected versions are excluded automatically by the predicate (no "latest by date" selection logic).
- **No snapshot pinning** (OD-P1C-G): the FR columns *are* the reproducibility substrate; the read reconstructs directly.
- `known_at` defaulting and parsing reuse the existing endpoint convention (the `GET /positions/as-of` / `GET /valuations/as-of` parsing), so behavior is uniform across the read surface.

---

## 6. Relationship to portfolio hierarchy

- **Anchor, traversed for composition.** Node-level holdings filter `position.portfolio_id == {id}`. Subtree holdings additionally enumerate descendants via the **existing** `resolve_descendants` (bounded depth 32, visited-set, cycle-safe, per-hop tenant predicate) and union the node.
- **Still anchor-not-enforce (OD-P1C-A / OD-P1C-B).** Subtree traversal **shapes the read** (what holdings to list under a node); it does **not** restrict what a principal may see by scope. Within a tenant, any `portfolio.view` holder may read any portfolio's holdings — exactly as today. The P6+ `SCOPE-PORTFOLIO` grant will later *enforce* subtree membership; P1C-5 only *composes* over it. A tested fence asserts no scope filter is applied (parity with the P1C-1 anchor-not-enforce fence).
- `resolve_portfolio` (tenant-predicated by-id) gates the entry point: an unknown/cross-tenant `portfolio_id` fails closed (404, indistinguishable).

---

## 7. Relationship to positions

- The holdings set **is** the as-of `position` set — read directly from the captured `position` FR table. **Positions are captured, never derived from transactions** (OD-P1C-E); P1C-5 reads them, full stop.
- Returned per holding: the **stored** `instrument_id`, `quantity`, `quantity_unit`, `cost_basis`, `valid_from`/`valid_to`/`system_from`/`system_to`, `record_version`, `position_source`. No computed field; `cost_basis` is surfaced as the opaque captured reference (never recomputed).

---

## 8. Relationship to valuations

- Holdings and valuations share the `(portfolio_id, instrument_id)` grain, but **valuation is 4-part keyed** (`+ valuation_date`). A mark therefore attaches to a holding **only for an explicitly chosen `valuation_date`** — there is no "the" mark without a date.
- The mark, when attached, is the **captured** `mark_value` reconstructed as-of `(valid_at, known_at)` for that `valuation_date` — display-only, never an input to a calculation.

---

## 9. May captured valuation marks be displayed alongside positions?

**Yes — display-only, opt-in, deterministic, gated (OD-P1C-F; OD-P1C5-2).**

- **Opt-in:** marks are attached only when the caller passes `include_marks=true` **and** an explicit `valuation_date` (deterministic; no "latest mark" selection logic, which would edge toward derived semantics).
- **Display-only:** the response carries the **stored** `mark_value` + `currency_code` + `mark_source` + `valuation_date` (and may surface the inert `price_basis` label — a DIRTY/CLEAN/NAV-basis tag, still display-only, never a measure). The platform **never** computes `quantity × mark_value`, a market value, NAV, exposure, or any total. A scope-fence test asserts no such field/arithmetic exists.
- **Gated, fail-closed:** mark attachment additionally requires `valuation.view` (so a position-only viewer cannot obtain valuation data through the holdings endpoint). Without `valuation.view`, `include_marks=true` is **rejected with 403 before any mark lookup** (fail-closed — not a silent omission; OD-P1C5-2 recommendation).

---

## 10. APIs

New router **`apps/backend/src/irp_backend/api/holdings.py`** (read-only; `require_permission` guards; `get_tenant_session`; **no `db.commit()`**; **no audit emit**), mounted under the portfolio path:

- **`GET /portfolios/{portfolio_id}/holdings?valid_at=&known_at=&include_marks=&valuation_date=&subtree=`**
  Returns the as-of holdings list for the node (or bounded subtree when `subtree=true`), each row optionally carrying its display-only mark. **Listed, never aggregated** — no `total`, no `count`-as-exposure, no rollup.
  - `valid_at` **required**; `known_at` optional (default now); `subtree` default false; `include_marks` default false; `valuation_date` required iff `include_marks=true`.
- Response model `HoldingsOut` = `{ portfolio_id, as_of: {valid_at, known_at}, holdings: [ HoldingOut ] }` where `HoldingOut` = stored position fields (+ optional `mark` block). **No aggregate fields anywhere in the schema.**

Guards: `portfolio.view` + `position.view` enforced via stacked `require_permission` route dependencies; `valuation.view` additionally enforced **in-handler** (conditional on `include_marks=true`, since `require_permission` takes a single static code) → 403 before any mark lookup. Unknown/cross-tenant `portfolio_id` → 404; `subtree=true` over a corrupt/too-deep (`> MAX_HIERARCHY_DEPTH`) hierarchy → **409** (mirroring `GET /portfolios/{id}/tree`); missing `valuation_date` when `include_marks=true` → 422; bad date → 422.

*(Router placement — dedicated `api/holdings.py` vs extending `api/portfolios.py` — is a minor open decision, OD-P1C5-3; recommended: dedicated router for separation of the composition concern.)*

---

## 11. Audit events for read / query activity

**None.** P1C-5 emits **no audit events** — reads are not governed writes. This matches the platform precedent (`GET /portfolios/{id}/tree`, `GET /positions`, `GET /lineage/...` emit nothing) and OD-023 (read access-audit is **open**, current posture = no-emit). No `HOLDINGS.*` event family is minted; `audit/service.py` stays **frozen** and untouched. If access-audit on Restricted/MNPI reads is later mandated (OD-023), it is a **cross-cutting P6+** concern, not P1C-5.

---

## 12. Entitlement checks

- **Reuse existing `.view` permissions — mint none.** Holdings: `portfolio.view` **+** `position.view` (stacked `require_permission` route Depends). Marks: **+** `valuation.view`, enforced **in-handler** because it is conditional on `include_marks=true` (`require_permission(code)` takes a single static code, so a conditional perm cannot be a route Depends) — the in-handler check returns **403 before any mark lookup**.
- Holders (unchanged): `risk_analyst_1l`, `risk_manager_2l`, `data_steward` (+ `platform_admin`). **`auditor_3l` excluded** (operational-data SoD inherited from the three `.view` perms).
- **Deny-by-default** (BR-11): no permission → 403 before any read. No `holdings.view` / `report.*` permission is created (OD-P1C5: P1C-5 mints nothing).
- Parity test pins the permission catalog **unchanged** (no new code, no new grant).

---

## 13. RLS behavior

- **Inherited, symmetric, tenant-scoped.** P1C-5 adds **no table and no policy**; it reads `portfolio`/`position`/`valuation` through the RLS-scoped `get_tenant_session`, so the existing FORCE-RLS `USING == WITH CHECK == own-tenant` policies on those tables govern every row. Cross-tenant rows are invisible; no-context reads return zero rows.
- Service-layer `tenant_id == acting_tenant` predicates are reinforced in the read functions (defense-in-depth), matching the per-entity reads.
- **No BYPASSRLS path.** The closed 5-table hybrid set is unchanged (this slice touches no migration / `pg_policies`).

---

## 14. Lineage behavior

**N/A — reads bind no lineage.** Lineage (`record_lineage` / `assert_has_lineage`) attaches to **governed write outputs** (captured rows). A read-composition produces no new governed row, so it roots **no** lineage edge. The underlying positions/valuations already carry their MANUAL-source ORIGIN lineage from capture; P1C-5 surfaces those rows without creating or mutating lineage.

---

## 15. Data quality behavior

**N/A — reads run no DQ.** `run_quality_check` / `assert_passed_quality_checks` gate **ingest/governed writes**. P1C-5 writes nothing, so no DQ evaluation occurs. (Holdings reads simply reflect whatever DQ posture the captured rows already passed at capture time.)

---

## 16. Tests

New tests only (no production write paths exercised):

- **Read-model unit tests (`packages/shared-python/tests/test_holdings.py`):**
  - As-of holdings set correctness — node-level: the set returned equals, per instrument, what `reconstruct_position_as_of` returns for the same `(valid_at, known_at)` (consistency-with-the-primitive test).
  - Both axes: valid-time travel (a superseded holding disappears after its `valid_to`), system-time travel (`known_at` before a correction returns the pre-correction quantity).
  - Subtree composition: descendants' holdings included; bounded/cycle-safe (reuses `resolve_descendants` guarantees); each row carries its owning `portfolio_id`.
  - Mark attachment: display-only `mark_value` attaches for an explicit `valuation_date`; `mark = null` when none; **no `market_value`/total field present**.
  - **Scope-fence test (load-bearing):** assert on the DTO **field set** via `dataclasses.fields()` / Pydantic `model_fields` (the DTOs are plain — no `__table__` to introspect) that **no** `market_value`/`exposure`/`nav`/`total`/`weight`/`sum`/`count`-as-number field exists; plus a source-text scan of the `holdings/` module asserting **no `quantity * mark` / `* mark_value`** arithmetic and **no `record_event` / `record_lineage` / `session.add` / `db.commit` / `INSERT` / `UPDATE`** token is present in the read path.
  - Anchor-not-enforce fence: a `portfolio.view` holder reads holdings for any tenant portfolio (no scope filter applied).
  - Subtree cycle/depth: a corrupt/too-deep hierarchy raises `HierarchyCycleError` → endpoint **409** (parity with `GET /portfolios/{id}/tree`).
- **Endpoint tests (`apps/backend/tests/test_holdings_endpoint.py`):**
  - 200 node-level holdings; 200 subtree holdings; as-of params honored; `include_marks` opt-in.
  - Entitlement: no `portfolio.view`/`position.view` → 403; `include_marks=true` without `valuation.view` → 403; `auditor_3l` → 403.
  - Tenant isolation: cross-tenant `portfolio_id` → 404; no-context → empty/denied.
  - `include_marks=true` without `valuation_date` → 422.
  - **No-audit assertion:** a holdings read emits **zero** audit events (audit table row-count unchanged across the call).
- **PG tests (`packages/shared-python/tests/test_holdings_pg.py`):** the as-of set read under FORCE-RLS as the constrained `irp_app` role — tenant isolation + both-axes reconstruction hold against Postgres. **Pure read path — no mid-request commit**; tenant context is set once via `get_tenant_session` (the "re-set context after commit" precaution applies to write slices, not this one).

---

## 17. Acceptance criteria

1. Holdings for a portfolio (and bounded subtree) are **reconstructable as-of** any `(valid_at, known_at)`, returning the **stored** position rows only — the read half of REQ-PPM-001 (hierarchy composition) + REQ-PPM-002 (as-of holdings set), plus, when requested, the **captured-mark display read** of REQ-PPM-003 (the valuation conjunct only — the transaction conjunct of REQ-PPM-003 is untouched).
2. **No derived/aggregate number** is ever computed or returned (no total, sum, rollup, weight, market value, exposure) — proven by the scope-fence test.
3. Captured marks attach **display-only**, opt-in, deterministic by explicit `valuation_date`, gated behind `valuation.view`.
4. Tenant isolation holds (RLS + service predicate); deny-by-default entitlement holds; `auditor_3l` denied.
5. **Zero** audit events, lineage edges, DQ results, migrations, or new permissions are produced.
6. `make check` green; `migration_head` stays `0015_valuation`.

---

## 18. Risks

| Risk | Mitigation |
|---|---|
| Sliding into exposure rollup / market value (the AD-014 gate) | Load-bearing scope-fence test (no aggregate field, no `qty × mark`); response schema has no aggregate slot |
| Subtree traversal mistaken for ABAC enforcement | Explicitly documented as composition; anchor-not-enforce fence test; reuse the bounded resolver only |
| "Latest mark" convenience creeping in | Marks require an **explicit** `valuation_date`; no auto-selection logic |
| Mark-join leaking valuations to a position-only viewer | `include_marks` gated behind `valuation.view` (403 otherwise) |
| Becoming a reporting/dashboard slice | JSON read endpoints only; no presentation/aggregation layer; listed-not-aggregated |
| Accidental write path (commit/audit/lineage) | Read-only by construction; fence test asserts no write symbols reachable |
| Performance on large subtrees | Bounded depth 32 + per-instrument current-head predicate; pagination is an open decision (OD-P1C5-4) |

---

## 19. Open decisions (sign-off before build)

| ID | Decision | Recommendation | Status |
|---|---|---|---|
| OD-P1C5-1 | Service-layer read models vs database view | **Service-layer only** — no migration, no new RLS/drift surface; reuse tested resolvers | ✅ Approved |
| OD-P1C5-2 | Display captured marks alongside holdings, and behavior when `valuation.view` is absent | **Yes, display-only + opt-in + explicit `valuation_date`**; absent `valuation.view` ⇒ **403** when `include_marks=true` (fail-closed, not silent omission) | ✅ Approved |
| OD-P1C5-3 | Router placement of the holdings endpoint | **Dedicated `api/holdings.py`** mounted at `/portfolios/{id}/holdings` (separation of the composition concern) | ✅ Approved |
| OD-P1C5-4 | Ship bounded subtree composition in P1C-5, and pagination | **Ship both node-level and bounded-subtree** (resolver already exists/tested); **add limit/offset pagination** (no total-count exposure) | ✅ Approved |
| OD-P1C5-5 | Does P1C-5 change any REQ status | **No** — read-composition over already-satisfied capture; REQ-PPM-002 stays In-Progress (ABAC residual → P6+) | ✅ Approved |
| OD-P1C5-6 | New `irp_shared/holdings/` read package vs extending `position` service | **New `holdings/` read-only package** (no `models.py`/`events.py`); keeps composition cleanly separated; import-direction test forbids anything importing it | ✅ Approved |

---

## 20. Controls impacted

- **Exercised:** CTRL-001 (tests), CTRL-004 (response fields in the data dictionary), **CTRL-011** (deny-by-default entitlement + tenant isolation + RLS — the primary control for a read slice).
- **Not applicable (no governed write):** CTRL-005 / CTRL-012 (audit emit on data-changing actions), CTRL-006 / CTRL-013 (lineage bind / no-bypass on governed outputs), CTRL-032 (fail-closed audit rollback), CTRL-017 (temporal-class declared — applies to the **underlying** captured entities, which already declare it; the read DTOs are not entities).
- The control-matrix coverage note will record P1C-5 as a **read-composition slice exercising CTRL-011** with the explicit no-write / no-audit / no-lineage / no-aggregation fences.

---

## 21. Documentation updates (in the BUILD slice, not this plan)

- `09_compliance_controls/control_matrix_skeleton.md` — add the P1C-5 read-composition coverage note (CTRL-011 primary; explicit non-applicability of write-side controls).
- `02_requirements/requirements_traceability_matrix.md` — annotate REQ-PPM-001/002 with the P1C-5 **read-half** realization (no status change).
- `04_data_model/` data dictionary — register the `HoldingsOut`/`HoldingOut` read DTO fields (read models, not entities).
- `10_delivery_backlog/` — P1C-5 closeout note; project-memory refresh (separate closeout turn).
- **No** entitlement/audit-taxonomy/migration governance update (R-07 not invoked — nothing minted).

---

## 22. Whether P1C-5 is ready to implement

**Ready — OD-P1C5-1…6 are signed off (see §19 + the sign-off block below).** The slice composes only shipped, tested read surfaces; introduces no entity/migration/permission/audit/lineage; and is fenced read-only by design. **No blockers.** Implementation proceeds only on a separate, explicit "begin P1C-5 implementation" approval.

---

## 23. Exact implementation kickoff prompt

> "Begin P1C-5 implementation only: as-of holdings / portfolio views (read-only composition). Sign-offs: OD-P1C5-1 service-layer read models only (no DB view, no migration); OD-P1C5-2 display-only opt-in marks, explicit `valuation_date`, 403 when `include_marks` without `valuation.view`; OD-P1C5-3 dedicated `api/holdings.py`; OD-P1C5-4 ship node-level + bounded subtree + limit/offset pagination; OD-P1C5-5 no REQ status change; OD-P1C5-6 new read-only `irp_shared/holdings/` package.
> Implement: a new `irp_shared/holdings/` read-only package (service.py + read DTOs; **no models.py, no events.py, no migration**) with `reconstruct_holdings_as_of`, `reconstruct_subtree_holdings_as_of` (which **first** calls `resolve_portfolio(session, portfolio_id, acting_tenant=...)` to get the `Portfolio` **object**, then passes that object — not the id — to the bounded cycle-safe tenant-predicated `resolve_descendants`, and unions the node's own id), and `attach_marks_as_of` (reusing `reconstruct_valuation_as_of`); and `apps/backend/src/irp_backend/api/holdings.py` with `GET /portfolios/{id}/holdings` (params: **`valid_at` required**, `known_at` optional default-now, `subtree`, `include_marks`, `valuation_date`; `portfolio.view` + `position.view` via stacked `require_permission` route Depends, plus `valuation.view` enforced **in-handler** (conditional on `include_marks`) → 403 before any mark lookup; `HierarchyCycleError` → **409** on subtree; `get_tenant_session`; **no db.commit, no record_event, no record_lineage**).
> Tests: `test_holdings.py` (as-of set correctness vs the per-entity primitive, both axes, subtree, display-only marks, the load-bearing scope-fence test asserting on DTO **field names** + a source-text no-`qty*mark`/no-write-token scan, anchor-not-enforce fence, **409 on cycle/depth**), `test_holdings_endpoint.py` (200 node/subtree, entitlement 403s incl. marks-without-`valuation.view`, tenant 404, `include_marks` without `valuation_date` → 422, **zero-audit assertion**), `test_holdings_pg.py` (as-of set under FORCE-RLS as `irp_app`; no mid-request commit). Add the **outbound** import-direction allowlist test for `holdings`; do NOT add `holdings` to any existing package's allowlist.
> STRICT EXCLUSIONS: NO new entity/migration/permission/audit-event/lineage/DQ; NO aggregation/sum/rollup/total/weight/market-value/`quantity × mark`; NO `dataset_snapshot`; NO risk/pricing/valuation model; NO market-data/price lookup; NO position-from-transaction derivation; NO corporate-action application; NO reporting/dashboard; NO ABAC scope enforcement (subtree is composition only); NO real SSO; NO P1C-6 / P2+. `audit/service.py` stays frozen. `migration_head` stays `0015_valuation`.
> Then run an 8-lens UltraCode adversarial review, fix in-scope findings, run `make check`, and **do not commit until I approve**."

---

### Sign-off block

> Sign-offs recorded (H-06 Engineering Lead, 2026-06-25):
> - ⚑ OD-P1C5-1 — ✅ signed off — use **service-layer read models only**. No DB view, no migration, no persisted entity.
> - ⚑ OD-P1C5-2 — ✅ signed off — display captured valuation marks **only when** `include_marks=true`, an explicit `valuation_date` is provided, **and** the caller has `valuation.view`. Marks are **display-only**; no market value rollup or `quantity × mark` calculation.
> - ⚑ OD-P1C5-3 — ✅ signed off — use a **dedicated `api/holdings.py`** mounted at `GET /portfolios/{id}/holdings`.
> - ⚑ OD-P1C5-4 — ✅ signed off — support **node-level and bounded subtree** holdings reads with **limit/offset pagination**. Subtree traversal is **read composition only, not ABAC enforcement**.
> - ⚑ OD-P1C5-5 — ✅ signed off — **no requirements status change** from P1C-5 alone. This is read composition over already-captured entities.
> - ⚑ OD-P1C5-6 — ✅ signed off — create a **read-only `irp_shared/holdings/` package** with no `models.py`, no `events.py`, and no migration.
