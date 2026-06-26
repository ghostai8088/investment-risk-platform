# P1C Closeout & P2 Readiness Review

## Document Control

| Field | Value |
|---|---|
| Purpose | Confirm the P1C **Portfolio / Transaction / Position / Valuation capture + as-of read** block is complete enough to support P2 (market & private data, risk analytics), inventory the P1C capabilities available to P2, assess P2 prerequisites, and recommend the correct **P2 entry point + subphase structure**. |
| Status | **Closeout / readiness artifact — PLANNING ONLY; NO code, NO migrations, NO P2 implementation.** |
| HEAD at writing | `9584ba4` (P1C-6 closeout project-memory refresh; build `3e9882d`); origin/main clean and in-sync. |
| Scope of this doc | Parts 1–7 (P1C closeout, capability inventory, P2 readiness, P2 entry-point decision, P2 subphase structure, factor-model/real-data readiness, synthetic-data usage) + Part 8 (8-lens UltraCode review log, **populated**, in-scope findings folded back into Parts 1–7). Mirrors `p1a_closeout_p1b_readiness.md` / `p1b_closeout_p1c_readiness.md`. |
| Predecessor | `p1b_closeout_p1c_readiness.md` (the P1B→P1C equivalent). |
| Review | **8-lens UltraCode adversarial review run (Part 8): 8 × approve_with_changes, 0 block.** In-scope corrections (calculation_run layer, FR temporal class, canonical ENT names + P3 carve-out, AD-004/OD-014 storage, AD-013-R1 tenancy, catalog reuse, re-sequencing) folded in below. |

> **Grounding (verified this turn):** the six P1C impl commits all exist in `main` and are CI-green (P1C-6 run #60 re-confirmed via the GitHub Actions REST API: success, all 5 jobs); `git status` clean except this artifact; migration head `0015_valuation` (no `0016`). Authoritative state: `docs/project_memory/*` (refreshed at `9584ba4`). Canonical (`04_data_model/canonical_data_model_standard.md`): ENT-009 benchmark (EV reference), ENT-010..014 portfolio/position/transaction/valuation/exposure_aggregate, ENT-020 price_point / ENT-021 yield_curve / ENT-022 volatility_surface / ENT-023 credit_spread / ENT-024 fx_rate / ENT-025 factor_return, ENT-026 calculation_run, ENT-015..019 private assets. Temporal (`temporal_reproducibility_standard.md` §2A): position/valuation = FR, transaction = IA, exposure_aggregate = IA, **market data ENT-020..025 = FR**; §5 FW-RUN / TR-15 = the calculation_run reproducibility bind. Decisions: **AD-017** (P1C capture-only), **AD-014** (snapshot gates derived output), **AD-013-R1** (closed 5-table hybrid set), **AD-004 / OD-014** (Postgres SoR vs TimescaleDB time-series split, OPEN), **AD-005** (selective bitemporality), **AD-007** (SSO deferred).

---

## Part 1 — P1C closeout (per-slice)

All six P1C slices are **committed and CI-green**. The four entity slices (P1C-1..P1C-4) are governed writes on the P1A rails: caller-side `*.*` audit constants to the **FROZEN** `record_event`, one MANUAL-`data_source` ORIGIN lineage edge per new physical version, deny-by-default entitlements, the temporal class declared via `__temporal_class__`, and an entity-specific PG RLS CI step under the constrained non-superuser `irp_app` role. P1C-5 is a read-only composition (no entity); P1C-6 is a never-auto-run deterministic seed (no entity). Each entity slice was 8-lens UltraCode reviewed (0 block).

### 1.1 P1C-1 — portfolio hierarchy + ABAC scope anchor
| Field | Value |
|---|---|
| Commit / CI | `bb89c74` / **green (run #43 = 28068172716)** |
| Entities / modules | `portfolio` (ENT-010, migration `0012`); new `irp_shared/portfolio/` package; bounded `resolve_ultimate_parent` (ancestor) + **NEW** `resolve_descendants` (subtree BFS); 5 thin endpoints (`/portfolios` CRUD + `/{id}/tree`) |
| Temporal | **EV** (`EFFECTIVE_DATED`); amend = in-place supersede (`record_version` bump); NOT append-only; single `status` |
| RLS | **SYMMETRIC** proprietary (`USING == WITH CHECK == own-tenant`, FORCE; mig `0012`); **NEVER hybrid** (closed 5-table hybrid set asserted unchanged); cross-tenant `parent_portfolio_id` fails closed at the service layer (`resolve_portfolio` → `PortfolioNotVisible`) |
| Audit | `PORTFOLIO.CREATE` (EVT-150) / `PORTFOLIO.UPDATE` (EVT-151) ACTIVATED; status flip rides `UPDATE`; **EVT-152 `STATUS_CHANGE` reserved-not-emitted**; `audit/service.py` FROZEN |
| Entitlements | `portfolio.view` + `portfolio.edit`; `data_steward` BOTH; existing `.view` recipients unchanged; `auditor_3l` excluded |
| Lineage | one MANUAL-source ORIGIN edge per create; an EV amend roots NONE |
| DQ | generic rails available; none entity-specific configured |
| Placeholders | **a portfolio HOLDS NOTHING**; **ABAC anchor-not-enforce** (adjacency + descendant resolver recorded; NOTHING reads/filters by scope) |
| Follow-ups / risk | REQ-PPM-001 In-Progress (ABAC enforcement → P6+; exposure aggregation → P2); residual: any `portfolio.view` holder sees all tenant portfolios (accepted; synthetic data). **No P2 blocker.** |

### 1.2 P1C-2 — transaction capture (IA append-only)
| Field | Value |
|---|---|
| Commit / CI | `abb230f` / **green (run #46 = 28108904570)** |
| Entities / modules | `transaction` (ENT-012, migration `0013`); new `irp_shared/transaction/` package; 4 thin endpoints (record/list/get/reverse) |
| Temporal | **IA** (`IMMUTABLE_APPEND_ONLY`; `system_from` only). Two-layer immutability: `irp_prevent_mutation` **P0001 DB trigger** + ORM `before_update`/`before_delete` guard. Truly immutable |
| RLS | SYMMETRIC proprietary (mig `0013`); NEVER hybrid; cross-tenant `portfolio_id`/`instrument_id`/`reverses_transaction_id` fail closed at the service layer |
| Audit | `TRANSACTION.RECORD` (EVT-160) / `TRANSACTION.REVERSE` (EVT-161) ACTIVATED; create-only; FROZEN |
| Entitlements | `transaction.view` + `transaction.record` minted; `data_steward` maker; risk tiers `.view`; `auditor_3l` excluded |
| Lineage | one MANUAL-source ORIGIN edge per record AND per reversal |
| DQ | generic only |
| Placeholders | **CAPTURE-ONLY** — NO transaction-to-position derivation; fields inert; **reversal-as-new-record** (original NEVER mutated) |
| Follow-ups / risk | REQ-PPM-003 transaction conjunct delivered (valuation conjunct → P1C-4 → REQ-PPM-003 **Done**). **No P2 blocker.** |

### 1.3 P1C-3 — position capture (FR bitemporal)
| Field | Value |
|---|---|
| Commit / CI | `4ee124e` / **green (run #49 = 28177012516)** |
| Entities / modules | `position` (ENT-011, migration `0014`); new `irp_shared/position/` package; `reconstruct_position_as_of(valid_at, known_at)`; reads `GET /positions` + `/positions/as-of` |
| Temporal | **FR** (`FULL_REPRODUCIBLE`). Reuses the P1B-3 `instrument_terms` protocol VERBATIM (create → supersede → as-known correction). **NOT append-only** (close-out UPDATEs; content-immutability service-enforced + PG-tested) |
| RLS | SYMMETRIC proprietary (mig `0014`); NEVER hybrid; cross-tenant FKs fail closed at the service layer |
| Audit | `POSITION.CREATE`/`UPDATE`/`CORRECTION` (EVT-170/171/172) ACTIVATED; per-op grain create=1 / supersede=2 / correct=2; FROZEN |
| Entitlements | `position.edit` MINTED (FR maker verb); `position.view` wired to `data_steward`; `auditor_3l` excluded |
| Lineage | one MANUAL-source ORIGIN edge per NEW physical version; the close-out roots NONE |
| DQ | generic only |
| Placeholders | **captured-not-derived** (no `transaction` FK); aggregated `(portfolio, instrument)` grain; signed quantity; opaque `cost_basis`; `valid_from` IS the as-of date; **NO market value / exposure / holdings view** |
| Follow-ups / risk | REQ-PPM-002 In-Progress (residual = ABAC enforcement → P6+); maker-checker → P6+. **No P2 blocker.** |

### 1.4 P1C-4 — valuation capture (FR bitemporal)
| Field | Value |
|---|---|
| Commit / CI | `c5c5806` / **green (run #54 = 28186419856)** |
| Entities / modules | `valuation` (ENT-013, migration `0015`); new `irp_shared/valuation/` package (forbids importing `position`); `reconstruct_valuation_as_of(valid_at, known_at)`; reads `GET /valuations` + `/valuations/as-of` |
| Temporal | **FR**; reuses the `position`/`instrument_terms` protocol; **NOT append-only**. `valuation_date` = a separate immutable logical-key `Date`; 4-part current-head partial-unique `(tenant_id, portfolio_id, instrument_id, valuation_date) WHERE valid_to IS NULL AND system_to IS NULL` |
| RLS | SYMMETRIC proprietary (mig `0015`); NEVER hybrid; cross-tenant FKs fail closed at the service layer |
| Audit | `VALUATION.CREATE`/`UPDATE`/`CORRECTION` (EVT-180/181/182) ACTIVATED; per-op grain create=1 / supersede=2 / correct=2; FROZEN |
| Entitlements | `valuation.view` + `valuation.edit` **both newly minted**; `data_steward` maker; risk tiers view; `auditor_3l` excluded |
| Lineage | one MANUAL-source ORIGIN edge per NEW physical version; `mark_source` (row label) DISTINCT from the `data_source` ORIGIN edge |
| DQ | generic only |
| Placeholders | **captured marks, NOT modeled** (OD-P1C-F) — `mark_value` supplied (never recomputed); **NO valuation/pricing model, price lookup, market-value rollup, `position_id` FK, `quantity × mark`**; **NO exposure / holdings view / `dataset_snapshot`** |
| Follow-ups / risk | **REQ-PPM-003 now Done** (both conjuncts); maker-checker → P6+. **The captured `mark_value` is the input the first P2 exposure rollup consumes — no market price needed.** **No P2 blocker.** |

### 1.5 P1C-5 — read-only as-of holdings / portfolio views
| Field | Value |
|---|---|
| Commit / CI | `0bef45b` / **green (run #57 = 28196900649)** |
| Entities / modules | **NO entity, NO migration** (head stays `0015_valuation`). Read-only `irp_shared/holdings/` package (`service.py` + plain read DTOs; no `models.py`/`events.py`); `GET /portfolios/{id}/holdings`. Composers `reconstruct_holdings_as_of` / `reconstruct_subtree_holdings_as_of` / `attach_marks_as_of` |
| Temporal | N/A — a read composition of FR `position` + (optional) FR `valuation`; bitemporal as-of (`valid_at` required, `known_at` optional default-now) |
| RLS | inherited SYMMETRIC FORCE-RLS via `get_tenant_session` + a service tenant predicate; cross-tenant/unknown → 404; cycle → 409; no BYPASSRLS; PG-proven as `irp_app` |
| Audit | **NONE** (reads do not emit; OD-023); FROZEN; zero-audit-write endpoint assertion |
| Entitlements | **mint NOTHING** — `portfolio.view` + `position.view` route guards; `valuation.view` in-handler before any mark lookup → 403 |
| Lineage / DQ | none (reads bind none) |
| Placeholders | subtree = read COMPOSITION, NOT ABAC enforcement (→ P6+); display-only opt-in marks; **NO aggregation / market-value / `quantity × mark` / exposure / `dataset_snapshot`** (AST scope-fence + DTO-field fence) |
| Follow-ups / risk | **No REQ status change.** **The holdings read-model is the P2 consumption surface** for captured positions+marks. **No P2 blocker.** |

### 1.6 P1C-6 — deterministic synthetic dataset
| Field | Value |
|---|---|
| Commit / CI | `3e9882d` / **green (run #60 = 28207899969)** |
| Entities / modules | **NO entity, NO migration.** New `irp_shared/synthetic/` package — `ids.py` (uuid5 namespace + `synthetic_id`; `SYNTHETIC_TENANT_ID`/`ACTOR_ID`; `SEED_EPOCH` + deterministic `SeedClock`; `business_date`) + `builder.py` (`build_synthetic_dataset` → `SyntheticDatasetSummary`). Leaf tooling |
| Temporal | N/A — seeds **through the existing governed binders** via a **keyword-only default-None deterministic-injection seam** (`entity_id`/`now`). The frozen `record_event` already exposes `event_time: datetime \| None = None`; the P1C-6 seam only threads `now` from the caller-side binders/`_emit` helpers into that pre-existing parameter (**no change to `audit/service.py`**); production call sites pass nothing ⇒ byte-for-byte unchanged |
| RLS | writes **only** the reserved SYNTHETIC tenant under FORCE RLS, **never BYPASSRLS**; PG FORCE-RLS tests: only the synthetic tenant's rows visible; other tenant + no-context see ZERO rows |
| Audit | composes the existing binders' governed audit (per-tenant chain `verify_chain(...).ok is True`); `audit/service.py` FROZEN |
| Entitlements / Lineage | reuses existing (mints nothing); one MANUAL-source ORIGIN edge per governed write |
| DQ | none new |
| Placeholders | **NEVER-AUTO-RUN** + **production / non-synthetic-tenant REFUSAL guard**; **no real client/vendor data**; **no market/risk/exposure/`dataset_snapshot` scope**; rails' internal surrogate PKs stay wall-clock (domain-row surface is deterministic) |
| Follow-ups / risk | **No REQ status change** (a deterministic test/demo/UI enabler, OD-P1C-L; replaced P1B-5). **No P2 blocker.** |

### 1.7 Closeout confirmations
- **P1C-1 through P1C-6 are committed** — `bb89c74`, `abb230f`, `4ee124e`, `c5c5806`, `0bef45b`, `3e9882d` all in `main`. ✅
- **P1C-1 through P1C-6 are CI-green** — runs #43 / #46 / #49 / #54 / #57 / #60 (P1C-6 re-confirmed this turn: all 5 jobs success). ✅
- **origin/main is clean** — HEAD `9584ba4`, local == origin, `git status` empty (except this artifact). ✅
- **P2 has not started** — migration head `0015_valuation` (no `0016`); no market/snapshot/exposure source. ✅
- **No unresolved P1C defect blocks P2** — every slice closed 0-block; carried items are deferred-by-design, not defects. ✅

### 1.8 P1C known placeholders carried forward (consolidated)
| # | Placeholder | Origin | Disposition |
|---|---|---|---|
| 1 | **ABAC portfolio-scope enforcement** (anchor exists; nothing filters) | P1C-1/3/5 | → **P6+** (NOT P2) |
| 2 | **Exposure aggregation** (ENT-014, REQ-PPM-004 — status **Draft**) — no `quantity × mark`, no rollup | P1C-3/4/5 | → **P2**, **through `calculation_run` (ENT-026)** and **only after `dataset_snapshot`** (AD-014). REQ-PPM-004 is promoted Draft→In-Progress at P2-0 |
| 3 | **`dataset_snapshot` / reproducible input snapshot** (AD-014 gate; temporal class to ratify at P2-0) | P1C-4/5 | → **P2** (the reproducibility primitive) |
| 4 | **`calculation_run` (ENT-026)** — shipped as a P1A skeleton (migration `0001`; placeholder FKs `input_snapshot_id`/`model_version_id`/`random_seed`), never exercised | P1A/P0.5 | the **run-record binding vehicle** for any P2 derived output (FW-RUN §5/TR-15); wired in P2 |
| 5 | **Valuation/pricing model, price lookup, market-value rollup** | P1C-4 | → **P2** (market data + the gated compute) |
| 6 | **Market data** (price_point/curves/FX/benchmark levels) — none exists; **storage split OPEN (AD-004 / OD-014: Postgres SoR vs TimescaleDB)** | all P1C | → **P2**; OD-014 ratified at P2-0 |
| 7 | **Maker-checker on FR corrections** | P1C-3/4 | → **P6+** |
| 8 | **Private-asset entities (ENT-015..019)** — commitment / capital_call / gp_report / private_company_financials / proxy_mapping | canonical | **recognized P2-band CAPTURE scope, deliberately OUT of this market-data/snapshot/exposure sub-band** — sequenced as a separate later P2 effort (a P2-0 open item), not pulled into this band |
| 9 | Transaction→position derivation; corporate-action application | P1C-2 / P1B-4 | deferred (capture-only) |
| 10 | Identifier cross-vendor precedence (OD-012) / counterparty netting-CSA (OD-015) | P1B | vendor-ingestion phase / P2+ |
| 11 | Reference SYSTEM seeder not wired to prod post-migrate; **P1B-5 reference ingestion mapping** | P1B | governance follow-up / conditional-deferred; not a P2 blocker |

---

## Part 2 — P1C capability inventory (what P2 inherits)

| Capability | What P2 CAN use | What P2 must NOT assume | Known limitations |
|---|---|---|---|
| **portfolio** (ENT-010, EV) | The governed entity + `PORTFOLIO.*` audit, RLS, lineage | That it holds positions/exposure; that scope is enforced | EV only; EVT-152 reserved |
| **portfolio hierarchy** | adjacency + bounded ancestor/descendant resolvers (depth-cap 32, cycle-safe, per-hop tenant predicate) | That the hierarchy **restricts** access (anchor-not-enforce → P6+) | A read substrate, not an authz filter |
| **transactions** (ENT-012, IA) | Immutable append-only event log; `TRANSACTION.*`; reversal-as-new-record | That positions are derived from transactions | Numeric fields inert |
| **positions** (ENT-011, FR) | Captured holdings + both-axes as-of (`reconstruct_position_as_of`); signed quantity; opaque `cost_basis` | Market value / exposure on the row; `cost_basis` recomputed | Aggregated `(portfolio, instrument)` grain |
| **valuations** (ENT-013, FR) | Captured marks per 4-part key + both-axes as-of; **`mark_value` is the input the first exposure rollup multiplies** | That marks are modeled/priced; a `position` link | One mark per key; multi-source out of scope |
| **holdings read-composition** (P1C-5) | `reconstruct_holdings_as_of` / `_subtree_` / `attach_marks_as_of` + `GET /portfolios/{id}/holdings` — **the P2 consumption surface** | That it aggregates / computes market value / exposure | Read-only; display-only opt-in marks |
| **deterministic synthetic dataset** (P1C-6) | A reproducible synthetic-tenant dataset for planning/UI/fixtures/tests | That it runs in prod / holds real data / can emit a derived number | Computes nothing; rails' surrogate PKs not deterministic |
| **`calculation_run` (ENT-026)** | The **shipped run-record skeleton** (migration `0001`) with placeholder FKs `input_snapshot_id` / `model_version_id` / `random_seed` — the FW-RUN binding vehicle for any P2 derived output | That it is exercised today (it is an unexercised skeleton) | Needs P2 wiring; the binding contract (FW-RUN §5) is ratified, the code path is not |
| **model registry** (P1A-2, ENT-026-adjacent) | `model` + `model_version`/assumption/limitation; BR-3 inventoried-before-use; **estimation window declared as a model_version assumption** | A structured `estimation_window` field (none — it is a declared assumption) | Registry skeleton; maker-checker non-enforcing |
| **other P1A rails** | tenant-context/RLS, audit+hash-chain (frozen `record_event` + `verify_chain`), entitlements (R-07 governs the catalog), `data_source`+lineage, **data quality** (generic `not_null`/`allowed_values` + no-silent-failure gate), **generic CSV ingestion staging** (anti-corruption + durable-evidence-on-reject), temporal mixins EV/IA/FR, Alembic+drift gate, constrained-role PG RLS tests | That the **DQ evaluator catalog** or **canonical mapping** are complete (see Part 3) | DQ = 2 generic evaluators only; staging maps NOTHING into canonical tables |

---

## Part 3 — P2 readiness assessment

**Conclusion: the platform is READY to PLAN P2** (a P2-0 decision record). Every cross-cutting prerequisite is shipped and CI-green. The gaps are the **P2 domain data itself** (market data), the **reproducibility primitive** (`dataset_snapshot`), and **wiring the existing `calculation_run` skeleton** — precisely what P2 builds. Two rails need *additive* growth (not new frameworks): the **DQ evaluator catalog** and a **staging→canonical mapping** layer.

| Prerequisite | Status | Evidence / note |
|---|---|---|
| tenant context / RLS | ✅ Ready | Symmetric + hybrid loops proven; extends to P2 entities. **Tenancy of market data = a P2-0 decision** (default symmetric; hybrid would reopen AD-013-R1 → AD-013-R2) |
| audit (hash chain) | ✅ Ready | Frozen `record_event` + `verify_chain`; `event_time` seam proven. **Reuse `CALC.RUN_*` (EVT-040) for the compute; `DATA.VALIDATE` for DQ; MARKET.*/SNAPSHOT.* are PROPOSED new categories pending an R-07 EVT-block** |
| entitlement | ✅ Ready | Deny-by-default; additive via R-07. **`exposure.aggregate.run` is already seeded (reserved-unwired) — wire it, do not mint a parallel** |
| lineage | ✅ Ready | `data_source` + polymorphic `lineage_edge` (already carries `run_id` + a `data_snapshot` source_type forward-compat note — reconcile the token vs `dataset_snapshot` at P2-0). **A real VENDOR `data_source` must be registered before rooting vendor ORIGIN edges** |
| data quality | ⚠️ Ready (plumbing) — **catalog grows** | The persistence + no-silent-failure gate + lineage/audit plumbing reuse UNCHANGED, but price/FX/curve/snapshot rules need **NEW generic evaluator functions** in `dq/rules.py` (non-negative/range, staleness, gap/continuity, set-coverage, monotonic-sequence) + REGISTRY entries. **Staleness + snapshot-completeness may exceed the current `(params, dataset)` evaluator contract** — P2-0 decides: extend the contract or make them caller-side gates |
| ingestion staging | ⚠️ Ready (generic) — **mapping is new** | P1A-4 anti-corruption + durable-evidence reuse UNCHANGED, but it maps NOTHING into canonical tables — a **NEW staging→canonical market-data mapping/promotion** step + canonical-targeted DQ is genuine P2 code |
| reference data | ✅ Ready | The anchors market data keys to (instrument/instrument_terms FR, currency hybrid, calendar; **benchmark = ENT-009 EV reference**) |
| portfolio / transactions / positions / valuations / holdings | ✅ Ready | The capture surface + the read-model consumption surface |
| deterministic synthetic dataset | ✅ Ready | Fixtures for P2 planning/tests (input-only; fenced from emitting derived numbers — Part 7) |

**Gaps (by design = the P2 build):** market data (FR), `dataset_snapshot` (IA), wiring `calculation_run`, exposure (ENT-014, IA). The **storage split (AD-004 / OD-014)** and **market-data tenancy** are P2-0 ratification items.

---

## Part 4 — P2 entry-point decision

### 4.1 The gating questions (answered, corrected per review)
- **Does exposure aggregation require `dataset_snapshot` first?** → **YES, airtight (AD-014).** No governed derived output without a bound reproducible input snapshot. ⇒ **Option C (exposure first) is disqualified.**
- **Does market data need to land before `dataset_snapshot`?** → **NO — corrected.** AD-014 gates **snapshot-before-exposure**, not **market-data-before-snapshot**. The snapshot binds **exactly the inputs its consumer uses** (TR-09). The first exposure consumes **captured marks** (P1C-4 `mark_value`) + positions (+ FX for multi-currency) — **not** price_point/curves/benchmark. `dataset_snapshot` is IA/append-only, so adding market references later is a **new** snapshot (additive), not a re-version.
- **Can `dataset_snapshot` reference captured positions and valuations *before* market data exists?** → **YES** — and it is the **high-value** path, not (as the earlier draft said) low-value: it is exactly what the first captured-mark exposure needs. The FR reconstructors it binds (`reconstruct_position_as_of` / `reconstruct_valuation_as_of`) are shipped.
- **Minimum P2 slice that preserves reproducibility?** → a **P2-0 decision record** that ratifies the snapshot + `calculation_run` contract **before** any build (the P1B-0 / P1C-0 precedent), then the **snapshot primitive** itself.
- **Safest sequencing to avoid premature risk calculations?** → plan first (P2-0), then the **reproducibility primitive (snapshot)**, then the **one market input the first compute needs (FX)**, then the **gated `calculation_run` + exposure rollup** — with **no factor/risk/pricing math** anywhere. Broad market-data history (prices/curves/benchmark) follows as the **P3 factor-model on-ramp**, not as an exposure prerequisite.
- **What data is required before factor models or market-risk analytics?** → multi-year price/return + FX + curves + optional benchmark history, a `model_version` with a **declared estimation window**, and a bound snapshot via `calculation_run`. **None of this is built here.**

### 4.2 Decision
**Recommended entry point: Option D — P2-0 planning / decision record first.** (All eight review lenses agree on D; the disagreement was over the *build* ordering D should ratify — corrected below.)

P2-0 should ratify, before any build:
1. **Canonical entity cross-walk + P3 carve-out** — P2 captured-market band = **ENT-020 `price_point`, ENT-021 `yield_curve`, ENT-023 `credit_spread`, ENT-024 `fx_rate`** (+ ENT-009 `benchmark` levels if needed). **ENT-022 `volatility_surface` (modeled) and ENT-025 `factor_return` are P3+ and are NOT ratified by P2-0.** (Do **not** carry the loose "ENT-020..025" label — it pulls factor/vol entities forward.)
2. **Temporal class** — market data is **FR** per §2A/AD-005 (market date = valid-time; ingest/knowledge = system-time; vendor restatements = as-known corrections). Reuse the shipped FR protocol. (Not an EV/IA choice.)
3. **`calculation_run` (ENT-026)** as the run-record binding vehicle between `dataset_snapshot` and any derived output, binding the full **FW-RUN §5 / TR-15** item set.
4. **Storage split (AD-004 / OD-014)** — Postgres-SoR-with-RLS vs TimescaleDB-behind-a-repo-interface for ENT-020..025, and what that implies for RLS/audit/lineage/DQ reuse.
5. **Tenancy** — default **symmetric proprietary** for market data (vendor data is per-tenant licensed / MNPI); a shared-global (hybrid) set would **reopen AD-013-R1** (→ AD-013-R2), not a free toggle.
6. **Catalog reuse** — wire the seeded `exposure.aggregate.run`; reuse `CALC.RUN_*` + `DATA.VALIDATE`; flag MARKET.*/SNAPSHOT.* as proposed R-07 additions.
7. **Promote REQ-PPM-004** Draft→In-Progress with the `calculation_run` binding.
8. **The build sequence** (below).

> **Sequencing recommendation (corrected by the Data-Architecture lens): reproducibility-first.** The AD-014-gated first compute (captured-mark exposure) needs only positions+valuations(+FX) — **not** price/curve/benchmark history. So the shortest safe path is **snapshot → FX → calculation_run + exposure**, with the broad market-data history foundation deferred to its real consumer (the P3 factor-model phase). This reaches the gated first compute on the narrowest bound set and defers the high-volume/Timescale-decision work until it is actually needed.
>
> **Alternative (the "market-data-foundation-first" order, e.g. the requesting prompt's example):** price → FX → curves → snapshot → exposure. It builds the market substrate first, but **front-loads the highest-volume / storage-risk / P3-facing work** and is **not required** by the captured-mark exposure. **Recommend the reproducibility-first order; P2-0 ratifies the final choice.**

---

## Part 5 — Recommended P2 subphase structure (reproducibility-first)

> All entities key to existing anchors and reuse the P1A rails (audit/lineage/DQ/RLS/entitlement) — **no new framework**, with two *additive* exceptions surfaced in Part 3 (new generic DQ evaluators; a staging→canonical mapping layer) and the **OD-014 storage decision**. Market data is **captured/ingested, FR, never modeled**; the **first compute (exposure) runs through `calculation_run`, gated on a `dataset_snapshot` (AD-014)**; **no factor/risk/pricing math** anywhere in this band.

### P2-0 — Planning / decision record  *(the entry point)*
- **Included:** ratify items 1–8 in §4.2 (entity cross-walk + P3 carve-out; FR temporal class; `calculation_run` binding + FW-RUN bind; AD-004/OD-014 storage; AD-013-R1 tenancy default-symmetric; catalog reuse; REQ-PPM-004 promotion; the build sequence). **Excluded:** any implementation; any factor/risk model. **Entities/APIs/audit/RLS/lineage/DQ:** none built. **Tests:** n/a. **Acceptance:** ratified decisions + a P2-1 plan-ready gate; explicit note "ENT-022(modeled)/ENT-025 are P3+ and NOT ratified here." **Risks:** over-scoping. **Open Qs:** snapshot temporal class (recommend IA/append-only per TR-09); private-asset (ENT-015..019) sub-band sequencing; lineage `data_snapshot` vs `dataset_snapshot` source_type token; DQ evaluator-contract extension vs caller-side gates.

### P2-1 — `dataset_snapshot` / reproducible input snapshot  *(the reproducibility primitive; AD-014)*
- **Included:** a `dataset_snapshot` entity binding an **immutable, as-of set of governed input record versions** (positions + valuations + reference + `model_version` refs; **market refs OPTIONAL/additive in v1**) by `(valid_at, known_at)` + content hashes. **Excluded:** any calc that consumes it (P2-3).
- **Entities:** `dataset_snapshot` (**IA**, append-only — a P2-0 ratification). **APIs:** create-snapshot (binds refs) + read/verify. **Audit:** `SNAPSHOT.CREATE` (proposed R-07). **Entitlement:** `snapshot.view`/`.create` (deny-by-default; maker = a steward; `auditor_3l` excluded). **RLS:** symmetric tenant-scoped; **resolution + verify proven under FORCE-RLS as `irp_app`**, incl. the mixed-tenancy case if market refs are ever hybrid. **Lineage:** the snapshot roots an edge to **every bound input version**. **DQ:** bound-set completeness = **expected-vs-actual coverage** (every bound position/instrument has its required inputs as-of), fail-closed. **Tests:** binds + verifies + **immutable (append-only)** + RLS isolation + a **temporal-reproducibility test** (correct/supersede a bound FR input → re-resolving the SAME snapshot returns the originally-bound versions, hashes unchanged; live as-of returns the corrected version) + a negative incomplete-bound-set test. **Acceptance:** a snapshot reproducibly resolves the same pinned versions under later mutation. **Risks:** binding scope. **Open Qs:** hash strategy; whether `model_version` binds at snapshot-time or run-time (recommend run-time per FW-RUN §5).

### P2-2 — FX rates + currency conversion foundation
- **Included:** `fx_rate` (ENT-024, **FR**) time-series (pair, date, source) + a **pure-lookup** conversion helper (the one market input a multi-currency exposure rollup needs). **Excluded:** triangulation-as-derived-math beyond a ratified rule; any return/vol.
- **Entities:** `fx_rate` (ENT-024, FR). **APIs:** as-of/range reads + convert. **Audit:** `MARKET.FX_INGEST`/`.CORRECT` (proposed R-07). **Entitlement:** `marketdata.view`/`.ingest` (reconcile vs `data.upload`; specify maker = a market-data steward; `auditor_3l` excluded). **RLS:** symmetric (default). **Lineage:** register a VENDOR `data_source` (ratify the `source_type` token) → ORIGIN edge per ingested series version. **DQ:** positive rate, pair coverage, staleness (via new evaluators / caller-gate per P2-0). **Tests:** as-of + convert + RLS + **scope-fence (convert = lookup × published rate only; AST/token fence, no triangulation/return/vol math)**. **Acceptance:** convert a captured valuation's currency as-of a date. **Risks:** base-currency policy. **Open Qs:** triangulation rule (ratified, not code-derived).

### P2-3 — `calculation_run` wiring + basic exposure foundation  *(the FIRST compute; AD-014 gate)*
- **Included:** wire **`calculation_run` (ENT-026)** to bind the FW-RUN §5 set, and produce `exposure_aggregate` (ENT-014, **IA**) = a deterministic `quantity × captured-mark` (FX-converted) rollup **over a bound `dataset_snapshot`, through a `calculation_run`**, binding a `model_version` (even trivial). **Excluded:** factor models, sensitivities, scenarios, VaR — anything beyond a deterministic market-value/exposure rollup.
- **Entities:** `calculation_run` (wired) + `exposure_aggregate` (ENT-014, IA, **run-tracked**). **APIs:** run-exposure (over a snapshot, via a run) + read. **Audit:** **reuse `CALC.RUN_START`/`.RUN_COMPLETE`/`.RUN_FAIL` (EVT-040)** — do not mint `EXPOSURE.*` unless R-07 justifies it. **Entitlement:** **wire the seeded `exposure.aggregate.run`** (maker/admin) + mint `exposure.view` if a distinct read verb is needed; `auditor_3l` excluded. **RLS:** symmetric. **Lineage:** result → `calculation_run` → (`dataset_snapshot` + `model_version`) → inputs (BR-6/BR-13; §6). **DQ:** the snapshot completeness-coverage gate (P2-1) is the fail-closed precondition. **Control (FW-RUN §5/TR-15):** an `exposure_aggregate` row exists **only** joined to a `calculation_run` referencing a non-null `dataset_snapshot` **and** `model_version` **and** the §5 metadata (assumptions, seed-disposition, initiator, run timestamps/environment). **Tests:** binds the full run set; **negative: a run with a null snapshot raises and writes ZERO result rows**; **negative: the synthetic seed path cannot emit an `exposure_aggregate`/run result** (Part 7); RLS; scope-fence (no factor/risk math). **Acceptance:** reproducible exposure for a snapshot, fully run-bound. **Risks:** scope creep into risk. **Open Qs:** grouping dimensions.

### P2-4 — Market price history  *(the P3 factor-model on-ramp begins; NOT on the exposure critical path)*
- **Included:** `price_point` (ENT-020, **FR**) captured price time-series keyed to `instrument`. **Excluded:** **NO `return` entity** (returns are derived → ENT-025/P3); no vol/pricing/factor math; corp-action adjustment scope is a P2-0 decision (raw vs adjusted).
- **Entities:** `price_point` (ENT-020, FR). **APIs:** governed ingest (staging→canonical mapping is new) + as-of/range reads. **Audit:** `MARKET.PRICE_INGEST`/`.CORRECT` (proposed R-07). **Entitlement/RLS/Lineage:** as P2-2. **DQ:** non-negative, staleness, gap detection. **Storage:** **per OD-014 (Postgres vs Timescale).** **Tests:** ingest + as-of + RLS + DQ-reject + scope-fence (no return/vol math) + **closed-hybrid-set-unchanged** assertion. **Acceptance:** price history queryable as-of for a range. **Risks:** time-series volume; storage-engine choice. **Open Qs:** adjusted-vs-raw; OD-014.

### P2-5 — Yield curves / credit spreads
- **Included:** `yield_curve` (ENT-021, FR) + `credit_spread` (ENT-023, FR), **captured** (not bootstrapped/modeled). **Excluded:** bootstrapping, interpolation-as-model, discounting/pricing.
- **Entities:** `yield_curve` (ENT-021) + `credit_spread` (ENT-023). **APIs:** as-of reads. **Audit:** `MARKET.CURVE_INGEST`/`.CORRECT`. **Entitlement/RLS/Lineage:** as P2-2. **DQ:** tenor monotonicity, point coverage, staleness. **Tests:** as-of + RLS + scope-fence (no bootstrapping). **Acceptance:** retrieve an as-of curve/spread. **Risks:** interpolation creep. **Open Qs:** curve identity/versioning; OD-014 storage.

### P2-6 — Benchmark / index data  *(if required before factor models)*
- **Included:** **benchmark DEFINITION/constituents = ENT-009 (EV reference data)** + benchmark **levels** (a price-like FR time-series). **Excluded:** active-return/attribution/factor math. **Entities:** `benchmark` (ENT-009, EV) + `benchmark_level` (FR levels). **Rails:** EV reference rails for the definition (AD-013 tenancy question); P2-2 market-data rails for the levels. **Acceptance:** as-of benchmark retrieval. **Open Qs:** whether needed before the P3 factor phase (defer unless a P3 dependency is confirmed); a canonical ENT id for `benchmark_level` if net-new.

> **Boundary line:** P2 as scoped ends at a **reproducible market-value/exposure rollup, run-bound and snapshot-gated**. **ENT-022 `volatility_surface` (modeled), ENT-025 `factor_return`, factor models, covariance/vol estimation, scenarios, VaR, limits, breach, reporting, real SSO are P3+** and must not be pulled forward. **Private assets (ENT-015..019)** are a separate later P2 capture sub-band (P2-0 sequences them).

---

## Part 6 — Factor-model & real-data readiness (forward guidance; NOT built here)

Eventually (P3+), real history will be needed for **asset-class factor models**, a **multi-asset factor model**, **volatility / covariance estimation**, and **stress / scenario calibration**. These depend on the P2 market-data foundation (price/FX/curve history) + the `dataset_snapshot` primitive + a `model_version` with a declared estimation window (bound at the `calculation_run`).

**Historical-data depth guidance — non-binding planning estimates, to be ratified when the P3 factor-model phase is planned (no AD/REQ pins these yet; do not read as a committed capture SLA):**
| Horizon | Target |
|---|---|
| Minimum pilot | **3 years daily** |
| Initial production target | **5 years daily** |
| Strategic target | **10+ years daily** |
| Stress / regime target | **15–20 years daily where available** |

**Clarifications:**
- **Store as much clean history as available** — depth drives estimation quality; the market-data entities (P2-2/P2-4/P2-5) should accept long history without rework (the OD-014 storage decision matters here).
- **Model versions must declare their estimation window** — reuse the P1A-2 model registry (BR-3 inventoried-before-use); the estimation window is a declared assumption/limitation on the `model_version` (no structured field exists today).
- **NO factor-model implementation in this readiness review**, and **NO risk calculations until explicitly planned** (P3+). P2 stops at a deterministic, run-bound market-value/exposure rollup.

---

## Part 7 — Synthetic-data usage in P2

The P1C-6 deterministic synthetic dataset should **support** P2 without ever becoming production or real:
| Use | How |
|---|---|
| **P2 planning** | A concrete, reproducible portfolio+positions+valuations fixture to reason about snapshot/run/exposure shapes |
| **UI / demo testing** | Drive the holdings read-model + future market-data UIs with stable, non-sensitive data |
| **Market-data fixtures** | Extend the synthetic builder (SYNTHETIC tenant only) with **synthetic** FX/prices/curves to test ingest/as-of/DQ paths |
| **Exposure-readiness tests** | Feed a synthetic `dataset_snapshot` + a trivial `model_version` to test the P2-3 gate (and its negative/refusal tests) |
| **Future visualization** | Deterministic data for charts/dashboards demos (the dashboards themselves are P3+) |

**Clarifications (hard fences):**
- **Synthetic data remains synthetic** — SYNTHETIC tenant only; uuid5 + fixed clock; never co-mingled with real tenants.
- **No real client/vendor data** — synthetic prices/FX/curves must be structurally-valid but obviously synthetic (the `ZZ0000000001` ISIN precedent).
- **No production auto-run** — the never-auto-run + refusal guard extends to any synthetic market-data fixtures.
- **No risk calculations hidden in synthetic data** — the builder may seed **INPUTS only** and **must be fenced from writing `exposure_aggregate` / any `calculation_run` result**; the only path to a derived number is the gated compute (P2-3). The synthetic package's AST/scope fence (today forbidding `quantity × mark`) is **extended in P2-3 to forbid the seed from emitting a derived exposure result**, with a negative test asserting it cannot.

---

## Part 8 — UltraCode 8-lens adversarial review log

Read-only review of this artifact + the repo. **Outcome: 8 × `approve_with_changes`, 0 block.** All material in-scope findings folded into Parts 1–7 above. The reviewers independently re-verified the closeout facts (six P1C commits in `main`; HEAD `9584ba4`; migration head `0015_valuation`; `audit/service.py` frozen since P0.5; AD-014/AD-017 quoted accurately; the P1C scope-fences real in `test_holdings.py`/synthetic builder).

| # | Lens | Verdict | Headline findings (severity) → disposition |
|---|---|---|---|
| 1 | Product / Requirements | approve_with_changes | "ENT-020..025" pulls ENT-022/ENT-025 (P3+) into scope **(HIGH)** → carved out (§4.2/Part 5); private assets ENT-015..019 silent **(MED)** → Part 1.8 #8; Part 8 dangling ref **(LOW)** → control inlined in P2-3; depth horizons unpinned **(INFO)** → labelled non-binding (Part 6). REQ/temporal mappings confirmed correct. |
| 2 | Chief Architect | approve_with_changes | **Missing `calculation_run` (ENT-026) layer (HIGH)** → inserted (Part 1.8 #4, Part 2, §4.2, P2-3); non-canonical entity names **(MED)** → canonical cross-walk; AD-004/OD-014 storage omitted **(MED)** → P2-0 item + Part 3; REQ-PPM-004 Draft **(LOW)** → noted. Acyclicity + clean-transition confirmed. |
| 3 | Data Architecture | approve_with_changes | **Market-data temporal class is ratified FR, not open (HIGH)** → fixed; **AD-004/Timescale (HIGH)** → P2-0; **re-sequencing: market-data NOT on the exposure critical path (HIGH)** → adopted reproducibility-first order; "market-data before snapshot" overstated **(MED)** → §4.1 corrected; entity-naming/benchmark-EV **(MED)** → fixed; snapshot/temporal + hybrid-set **(LOW)** → P2-0 items. Agrees Option D. |
| 4 | Security / RLS | approve_with_changes | Hybrid market data reopens AD-013-R1 → needs AD-013-R2 **(HIGH)** → default-symmetric + scope-fence; seeded `exposure.aggregate.run` exists **(HIGH)** → wire it; RLS-posture inconsistency / ingest-authority SoD / snapshot cross-tenant binding **(MED×3)** → P2-0/P2-1/P2-3 specified; per-table RLS checklist + canonical ids **(LOW)**. RLS rails confirmed grounded. |
| 5 | Audit / Controls | approve_with_changes | **FW-RUN/TR-15 seven-item bind understated (HIGH)** + **missing `calculation_run` (HIGH)** + **reuse `CALC.RUN_*` not `EXPOSURE.*` (HIGH)** → all folded into P2-3; `exposure.aggregate.run` reuse **(MED)**; expected-vs-actual completeness gate **(MED)** → P2-1; synthetic-result fence **(MED)** → Part 7; frozen-seam wording **(LOW)** → Part 1.6 clarified. |
| 6 | Lineage / Data Quality | approve_with_changes | **DQ "config not framework" misleading — new evaluator functions needed (HIGH)**; **staleness/snapshot-completeness exceed the evaluator contract (HIGH)** → Part 3 reworded + P2-0 decision; reuse `DATA.VALIDATE` / register vendor `data_source` / staging→canonical is new / source_type token **(MED/LOW)** → Part 3 + P2 slices. Lineage + DQ-gate plumbing reuse confirmed. |
| 7 | QA | approve_with_changes | "ENT-020..025" hidden scope creep **(HIGH)** → carved; exposure binding untestable without `calculation_run` **(HIGH)** → P2-3 testable control; snapshot acceptance not a reproducibility test **(MED)** → strengthened (mutation test); hybrid scope-fence test / FX no-triangulation fence / benchmark canonical id **(MED/LOW)**. Shipped fences confirmed real. |
| 8 | Scope | approve_with_changes | Market-data temporal class FR not open **(HIGH)**; `calculation_run`/`calc` package omitted from inventory **(HIGH)** → Part 2; benchmark = ENT-009 EV **(MED)**; "ENT-020..025"/"return" entity drift **(MED/LOW)** → fixed. **Confirmed: NO code/migration this turn; P2 not started; P3+/SSO not pulled forward.** |

**Net effect of the review on the recommendation:** the **entry point is unchanged (Option D, P2-0 first)**; the **build sequence changed** from market-data-first to **reproducibility-first** (snapshot → FX → `calculation_run`+exposure → then market-data history), the **`calculation_run` (ENT-026) layer + FW-RUN bind** were added as mandatory, entity names were aligned to canon with the **ENT-022/ENT-025 P3 carve-out**, and **AD-004/OD-014 storage + AD-013-R1 tenancy + catalog reuse** were surfaced as P2-0 ratification items. No finding blocks the conclusion that **P1C is complete and P2-0 is ready to plan.**

---

## Appendix — Return summary (for the requesting prompt)

See the chat response accompanying this artifact for the 13-item return.
