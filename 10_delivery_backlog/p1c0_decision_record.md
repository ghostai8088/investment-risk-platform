# P1C-0 Decision Record — Portfolio, Transactions, Positions, Valuations

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1C0-DR-001 |
| Version | 0.1 (Draft for Review) |
| Status | **Ratified (P1C-0, 2026-06-23)** — the twelve P1C decisions are recorded into the governance source-of-truth: **AD-017** (P1C capture-only stance) in `11_decision_log/architecture_decision_log.md`; **REQ-PPM-001** → In-Progress + annotation in `02_requirements/requirements_backbone.md` + the RTM; the **`PORTFOLIO.*`** audit family **RESERVED** (EVT-150 block, not emitted) in `04_data_model/audit_event_taxonomy.md`; the **ENT-010** realization note + **OD-013 closure** in `04_data_model/canonical_data_model_standard.md`, with the EV classification + P1C capture-only note in temporal §2A; **`portfolio.view`/`portfolio.edit`** grants + **OD-025 closure** in `06_security/entitlement_sod_model.md` §5B; the control-coverage note in `09_compliance_controls/control_matrix_skeleton.md`. This mirrors P1B-0's plan→ratification split (`4fae26b`). **No code was minted at ratification:** the `PORTFOLIO.*` codes, the permission grants, and migration `0012` are **activated/minted caller-side only in the P1C-1 build slice** (`audit/service.py` stays FROZEN). The sibling `TRANSACTION.*`/`POSITION.*`/`VALUATION.*` families + `transaction.*`/`position.edit`/`valuation.*` permissions are reserved for their later P1C slices (not in this P1C-1-focused ratification). |
| Owner | R-01 Chief Architect AI (with R-05 Data Architect AI) |
| Approver | H-06 Engineering Lead (H-04 Head of Architecture; H-03 Security; H-08 Internal Audit — consulted) |
| Created | 2026-06-23 |
| Related Documents | p1c_implementation_plan.md, p1b_closeout_p1c_readiness.md, p1_decision_record.md, p1_scoping_plan.md, ../02_requirements/requirements_backbone.md, ../02_requirements/requirements_traceability_matrix.md, ../04_data_model/canonical_data_model_standard.md, ../04_data_model/temporal_reproducibility_standard.md, ../04_data_model/audit_event_taxonomy.md, ../06_security/entitlement_sod_model.md, ../09_compliance_controls/control_matrix_skeleton.md, ../11_decision_log/architecture_decision_log.md |
| Supported Build Rules | BR-3, BR-5, BR-6, BR-7, BR-9, BR-11, BR-12, BR-13, BR-17, BR-19 |

> **Scope of this record.** Resolve the twelve P1C open decisions and fix the architecture for the first **domain-analytics** block: portfolio/fund/strategy/account hierarchy, transactions, positions, valuations, as-of reconstruction, and synthetic-dataset planning. **P1C is CAPTURE + AS-OF RECONSTRUCTION only** — no calculation, no derived governed output. Explicit exclusions (binding): no risk calcs, no exposure aggregation (unless `dataset_snapshot` is explicitly approved — it is **not**, OD-P1C-G/H), no VaR/ES, no market-data ingestion, no pricing/valuation models, no corporate-action application, no counterparty exposure, no credit/liquidity risk, no limits/breaches, no reporting dashboards, no real SSO, no P2+ work.

> **Grounding (verified 2026-06-23).** Next free ADR = **AD-017** (AD-016 is current highest). `bootstrap.py` declares four placeholder permissions in the catalog: `portfolio.view`, `portfolio.edit`, `position.view`, `exposure.aggregate.run`. **Grant reality (verified):** `portfolio.view` + `position.view` are granted to `risk_analyst_1l` + `risk_manager_2l` (and `platform_admin` via `ALL_CODES`); `portfolio.edit` + `exposure.aggregate.run` are **catalog-only — granted to `platform_admin` only** (no read/maker role holds them; effectively reserved-unwired). **No** `valuation.*`/`transaction.*` codes exist. **No `dataset_snapshot` table/skeleton exists** anywhere. Migration head = `0011_corporate_action`; next = `0012`. The shipped FR protocol (`reference/instrument_terms.py`: `create`/`supersede`/`correct`/`reconstruct_terms_as_of`; one-`now`; close-first; current-head partial-unique `WHERE valid_to IS NULL AND system_to IS NULL`; NOT append-only) is the reusable template for positions/valuations. Canonical temporal classes (§2A): position (ENT-011) = **FR**, valuation (ENT-013) = **FR**, transaction (ENT-012) = **IA**, portfolio (ENT-010) = **EV**, exposure_aggregate (ENT-014) = **IA** (class — `REQ-PPM-004` is deferred to P2 by AD-014; the deferral is a build-scope state, not the temporal class).

---

## OD-P1C-A — ABAC granularity & portfolio-scope model

1. **Decision.** P1C-1 builds the portfolio hierarchy as the **entitlement scope ANCHOR** (it records the scope-attribute structure ABAC will later bind to) but does **NOT enforce** portfolio-scoped access. Access stays **RBAC + tenant-RLS** (deny-by-default `portfolio.view`/`position.view`/`valuation.view`/`transaction.view`). Scope **granularity = portfolio-level** (not position-level) when ABAC enforcement is later built — this **resolves OD-025** in principle (portfolio-level). Full ABAC enforcement (the `entitlement_grant` subject→role→scope payload, ENT-P-06) is **deferred to P6+**.
2. **Rationale.** ENT-P-06 / AD-008 declare tenancy + portfolio scope mandatory attributes *eventually*, but the `entitlement_grant` table + scope payload is a P6 maker-checker deliverable (DR-P1-3). P1C's own data is **synthetic DC-1/DC-2** (OD-P1C-L), so shipping capture before ABAC creates **no real DC-3 exposure**. Anchoring the hierarchy now means ABAC enforcement later is additive (bind grants to existing nodes), not a remodel.
3. **Alternatives considered.** (a) Enforce portfolio ABAC in P1C — rejected: pulls the P6 `entitlement_grant`/scope-resolution surface forward, large scope, no real-data driver yet. (b) Position-level granularity — rejected (OD-025): finer than the hierarchy needs for the foreseeable roles; portfolio-level is the natural grant unit (a PM is entitled to a fund, not individual holdings). (c) Defer the hierarchy too — rejected: REQ-PPM-001 needs the node tree now; it is the anchor everything else hangs on.
4. **Risks.** Within a tenant, **anyone with `portfolio.view` sees all portfolios** until ABAC lands — must be stated explicitly in the P1C plan and acceptable **only** because P1C data is synthetic. Mitigation: the plan flags it; real DC-3 portfolios stay gated behind P6+ ABAC; the hierarchy is built so subtree scope resolution (OD-P1C-B) is computable when enforcement arrives.
5. **Impacted requirements.** REQ-PPM-001 (portfolio hierarchy = "entitlement scope anchor"). No scope change.
6. **Impacted controls.** CTRL-011 (deny-by-default entitlement — still enforced at the RBAC layer); the future ABAC scope control is recorded as deferred (P6+).
7. **ADR update required?** Recorded in the proposed **AD-017** (P1C capture-only domain; scope anchored-not-enforced). Conforms to AD-008/ENT-P-06.
8. **Requirements update required?** Annotate REQ-PPM-001 (entitlement scope **anchor** delivered in P1C; ABAC **enforcement** → P6+) at ratification.

## OD-P1C-B — Node vs subtree access (OQ-014)

1. **Decision.** When ABAC enforcement is later built, a grant on a portfolio node implies its **subtree** (descendant inheritance via the hierarchy adjacency), not the single node. P1C-1 **records the hierarchy** (parent/child adjacency + a bounded, cycle-safe, tenant-filtered ancestor/descendant resolver) so subtree resolution is **computable**; **enforcement itself is deferred** (per OD-P1C-A). This **resolves OQ-014 = subtree**.
2. **Rationale.** Subtree matches how desks are entitled: a grant on a fund should reach its strategies/accounts without per-node grants. The `legal_entity` adjacency (`parent_legal_entity_id` self-FK + the bounded `resolve_ultimate_parent`) is the proven precedent — but note the shipped `resolve_ultimate_parent` walks **upward** (ancestor). Subtree scope needs **descendant** traversal, which is a **NEW bounded resolver** built to the same **safety invariants** (visited-set, depth cap, cycle-safe via a `HierarchyCycleError`-style guard, tenant-filtered) — a reuse of the *shape*, not a literal call of the upward resolver.
3. **Alternatives considered.** (a) Node-only scope — rejected: forces an explicit grant per node, unusable at scale. (b) Flat (no hierarchy in scope) — rejected: defeats the "organize for aggregation & entitlement scope" purpose of REQ-PPM-001.
4. **Risks.** Subtree resolution must be **bounded** (depth cap, cycle-safe, tenant-filtered) to avoid traversal blowups / cross-tenant leakage — mitigated by reusing the proven `legal_entity` resolver shape; no enforcement code ships in P1C, so the risk is confined to the read resolver.
5. **Impacted requirements.** REQ-PPM-001 (hierarchy supports subtree scoping).
6. **Impacted controls.** Future ABAC scope control (P6+) — semantics recorded now.
7. **ADR update required?** Folded into AD-017. Closes OQ-014.
8. **Requirements update required?** None beyond the REQ-PPM-001 annotation.

## OD-P1C-C — Portfolio / fund / strategy / account node model

1. **Decision.** A **single `portfolio` EV table** with a `node_type` controlled-vocab string (`PORTFOLIO`/`FUND`/`STRATEGY`/`ACCOUNT`) + a `parent_id` intra-tenant self-FK adjacency — **NOT** four separate tables. Self-parent and cycles rejected in the service; a bounded, cycle-safe, tenant-filtered resolver handles ancestor/descendant traversal. `UNIQUE(tenant_id, code)`.
2. **Rationale.** Canonical ENT-010 groups the four as "hierarchy nodes"; the genericity rule (controlled-vocab **strings**, extend by value never migration) + the `legal_entity` single-table-adjacency precedent make one table + one resolver the right model. Distinct semantics per node_type (e.g. an account is typically a leaf) are **service/validation rules**, not separate schemas.
3. **Alternatives considered.** (a) Four tables (portfolio/fund/strategy/account) — rejected: 4× the RLS/lineage/audit surface for one conceptual entity; cross-type parenting becomes a polymorphic-FK mess. (b) An enum/CHECK on node_type — rejected: violates the no-enum/no-CHECK genericity rule (new node types must extend by value).
4. **Risks.** Node-model over-design (modeling fund-of-fund / overlay semantics now) — mitigated by keeping P1C to a plain adjacency tree + node_type label; richer semantics deferred. Mixed-type hierarchies need clear validation rules (e.g. permitted parent/child node_type pairs) — captured as an open question, default permissive.
5. **Impacted requirements.** REQ-PPM-001.
6. **Impacted controls.** CTRL-004 (data-dictionary definition of `portfolio` + node_type vocab).
7. **ADR update required?** No new ADR — a modeling choice; recorded in the canonical ENT-010 annotation + AD-017 context.
8. **Requirements update required?** Annotate ENT-010 realized as a single `portfolio` EV table with `node_type`. Also annotate **REQ-PPM-001** (and its RTM row), whose wording is "portfolio/fund/strategy" and omits `account`: record that the hierarchy is realized over the **full ENT-010 set including `ACCOUNT`** (node_type vocab `PORTFOLIO/FUND/STRATEGY/ACCOUNT`), reconciling the backbone wording with canonical ENT-010 (an additive clarification, no scope reduction).

## OD-P1C-D — Position grain

1. **Decision.** Positions are **aggregated by `(portfolio_id, instrument_id)`** — one open current-head FR version per portfolio+instrument — **NOT lot-level**. Quantity is **signed** (long/short via sign). The position carries quantity + an inert reference cost basis; **market value is a valuation concern (P1C-4), not a position column**. Current-head partial-unique: `(tenant_id, portfolio_id, instrument_id) WHERE valid_to IS NULL AND system_to IS NULL`.
2. **Rationale.** REQ-PPM-002 = "single source of holdings"; an aggregated grain is the canonical holding. Lot-level / tax-lot accounting is a deferred elaboration (a downstream cost-basis/tax concern, not core holdings). Signed quantity captures long/short without a separate side column. Keeping market value out of `position` avoids coupling two FR lifecycles (a re-mark must not version the holding).
3. **Alternatives considered.** (a) Lot-level positions — rejected for P1C: multiplies row volume and introduces tax-lot matching (a calc); deferrable. (b) Separate long/short rows — rejected: signed quantity is simpler and matches the single-current-head invariant. (c) Embed market value in position — rejected: conflates holding (P1C-3) with valuation (P1C-4).
4. **Risks.** A later need for lot-level grain would require a new entity, not a position remodel — acceptable (additive). Aggregated grain must define the netting rule (sum signed quantity per portfolio+instrument) — a capture rule, not a calc.
5. **Impacted requirements.** REQ-PPM-002.
6. **Impacted controls.** CTRL-006/013/017 (lineage + reproducibility on the FR position).
7. **ADR update required?** Folded into AD-017 (positions as aggregated FR holdings master).
8. **Requirements update required?** Annotate REQ-PPM-002 grain = aggregated-by-(portfolio, instrument).

## OD-P1C-E — Transaction-to-position relationship

1. **Decision.** Positions are **captured directly** as the authoritative FR holdings master (REQ-PPM-002); transactions are an **independent IA event log** (REQ-PPM-003). There is **NO transaction→position derivation engine** in P1C and **no derivation FK** — the two are captured independently (the P1C-2→P1C-3 build order is provenance ordering only). Deriving/reconciling positions from transactions is a reproducible **calculation**, deferred.
2. **Rationale.** AD-014 / the no-calc fence: a derived holding must bind a reproducible input snapshot, which P1C does not build (OD-P1C-G). Capturing positions directly keeps P1C verifiable (stored as-of data) and avoids a position-keeping engine. Independent capture also matches real feeds, where a custodian/accounting position file and a transaction file arrive separately.
3. **Alternatives considered.** (a) Derive positions from transactions — rejected: that is a calc (reproducibility-gated, AD-014); large scope; not P1C. (b) A non-FK "source transaction" pointer on position — rejected for P1C: implies a derivation relationship we are explicitly not building; can be added later if a derivation phase needs provenance.
4. **Risks.** Captured positions and the transaction log can **disagree** (no reconciliation in P1C) — explicitly accepted; reconciliation (REQ-DQR-002) is P7. The plan states positions are NOT derived, so no false expectation of consistency.
5. **Impacted requirements.** REQ-PPM-002, REQ-PPM-003.
6. **Impacted controls.** —
7. **ADR update required?** Folded into AD-017 (captured-not-derived; no calc in P1C).
8. **Requirements update required?** Annotate REQ-PPM-003 (transactions = independent IA log; no derivation in P1C).

## OD-P1C-F — Valuation source model

1. **Decision.** `valuation` (FR) is keyed to `(portfolio_id, instrument_id, valuation_date)` and captures a **single mark: `mark_value` + `currency_code` + a `mark_source` controlled-vocab label** (inert). `valuation_date` is an **immutable logical-key component** (a peer of `instrument_id`, not a versioned attribute): it is carried forward verbatim by `supersede_valuation`/`correct_valuation` and never mutated; the current-head close-out/open logic keys on the full `(tenant, portfolio, instrument, valuation_date)` tuple while the two temporal axes (`valid_*`/`system_*`) version the **mark** for a fixed valuation_date. **Exactly one mark is captured per `(portfolio, instrument, valuation_date)`** in P1C. **No valuation math, no pricing model, no source-precedence engine.** A second mark from a different source for the same key is **out of P1C scope** (not modeled, not a correction) — multi-source precedence is deferred (an echo of OD-012).
2. **Rationale.** P1C is capture-not-compute; valuation/pricing models are P2 (market data + calc). Keying to `(portfolio, instrument, valuation_date)` parallels the position grain and keeps the valuation lifecycle independent of the position version (a re-mark does not version the holding). `mark_source` as a label (not a FK to a market-data source) avoids coupling to the unbuilt market-data domain.
3. **Alternatives considered.** (a) Compute valuations from positions × prices — rejected: that is the P2 valuation engine. (b) Key valuation to a specific position row version — rejected: couples two FR lifecycles; OD-P1C-D keeps market value out of position for the same reason. (c) Build source precedence now — rejected: no multi-source driver in P1C; defer with OD-012.
4. **Risks.** Multiple marks for the same `(portfolio, instrument, valuation_date)` from different sources would collide on the FR current-head unique — **resolved (not deferred): exactly one mark per key in P1C**; a second source is out of scope. If a multi-source need is later confirmed, it is a deliberate later decision (add `mark_source` to the logical key), not an implicit P1C capability.
5. **Impacted requirements.** REQ-PPM-003 (valuation half).
6. **Impacted controls.** CTRL-006/013/017.
7. **ADR update required?** Folded into AD-017 (valuations captured-not-computed).
8. **Requirements update required?** Annotate REQ-PPM-003 (valuation = captured mark, as-of; no model).

## OD-P1C-G — Does `dataset_snapshot` enter P1C or stay P2? (OQ-013a)

1. **Decision.** **`dataset_snapshot` does NOT enter P1C** — no snapshot skeleton is built in this block. This **resolves OQ-013a = stays deferred to P2**.
2. **Rationale.** A `dataset_snapshot` pins input record versions to a **run** (TR-13..16, temporal §5) and is only meaningful once **derived outputs / calculation runs** exist (P2). P1C's as-of reconstruction is served directly by the FR bitemporal columns (`reconstruct_*_as_of(valid_at, known_at)`) — it needs **no** snapshot table. Building the skeleton now would exist only to unlock exposure aggregation (AD-014), which P1C explicitly excludes.
3. **Alternatives considered.** (a) Build a minimal `dataset_snapshot` skeleton in P1C to re-enable PPM-004 — rejected: pulls a derived-output capability into a capture-only block; no value without the P2 calc engine. (b) Build it "for later" — rejected: speculative; AD-002 (sequence scope, build when needed).
4. **Risks.** None for P1C. When P2 builds calc runs, the snapshot skeleton is added then (additive; the FR record-version columns positions/valuations already carry are exactly what a snapshot will pin).
5. **Impacted requirements.** REQ-PPM-004 (stays P2).
6. **Impacted controls.** AD-014 reproducibility gate (honored by NOT shipping derived output).
7. **ADR update required?** Conforms to AD-014; recorded as the OQ-013a closure (stays P2).
8. **Requirements update required?** Confirm REQ-PPM-004 status = deferred to P2.

## OD-P1C-H — Does exposure aggregation remain deferred?

1. **Decision.** **Yes — exposure aggregation (REQ-PPM-004) remains deferred to P2** (a direct consequence of OD-P1C-G + AD-014). P1C ships **no** aggregate/exposure/rollup number. The already-seeded `exposure.aggregate.run` permission stays **reserved and unwired** (no endpoint, no calc). P1C-5 delivers as-of holdings **views** (read composition) that compute **no** aggregate.
2. **Rationale.** AD-014 / DR-P1-2: no governed derived output without a bound reproducible input snapshot, which P1C does not build (OD-P1C-G). Exposure aggregation is the canonical derived governed number — it must wait.
3. **Alternatives considered.** (a) Ship a "best-effort" aggregation now — rejected: a non-reproducible governed number violates BR-6/BR-9/AD-014. (b) Remove the `exposure.aggregate.run` permission — rejected: harmless reserved placeholder; leaving it documents the intended P2 capability and avoids a bootstrap churn (parity tests pin it).
4. **Risks.** P1C-5 read views must not silently sum/rollup — enforced by an explicit **scope-fence test** ("no aggregation/exposure number is computed").
5. **Impacted requirements.** REQ-PPM-004 (deferred, P2).
6. **Impacted controls.** AD-014; CTRL-018 (reproducibility of aggregates — N/A until P2).
7. **ADR update required?** Conforms to AD-014.
8. **Requirements update required?** Confirm REQ-PPM-004 = P2; note `exposure.aggregate.run` reserved-unwired.

## OD-P1C-I — Corporate-action application exclusion

1. **Decision.** Corporate actions remain **capture-only** (the P1B-4 / OD-P1B-B contract). P1C does **NOT apply** them to positions or valuations — no quantity/price adjustment, no split/dividend processing, no event engine. Application is a **later explicit phase**.
2. **Rationale.** Applying a corporate action mutates holdings/valuations via a rule — a calculation/event-processing concern, outside the no-calc capture fence. P1C positions are **captured directly** (OD-P1C-E), already reflecting whatever the source provides; the platform does not yet compute adjustments.
3. **Alternatives considered.** (a) Apply simple actions (e.g. splits) in P1C — rejected: even a split is an application rule (a calc) and opens the event-engine surface; explicitly excluded. 
4. **Risks.** Captured positions may not reflect an announced-but-unapplied action — accepted; the corporate_action records are captured (P1B-4) for a later application phase; no P1C consumer applies them.
5. **Impacted requirements.** REQ-SMR-004 (corporate_action stays capture-only); REQ-PPM-002/003 (positions/valuations captured, not action-adjusted).
6. **Impacted controls.** —
7. **ADR update required?** Conforms to OD-P1B-B; reaffirmed in AD-017 scope fence.
8. **Requirements update required?** None.

## OD-P1C-J — Identifier precedence scope (OD-012)

1. **Decision.** **OD-012 stays deferred** — P1C builds **no** cross-vendor identifier-precedence engine. The position/transaction/valuation → instrument link uses the **internal `instrument_id`** via the shipped `resolve_instrument` (explicit-tenant-predicate, fail-closed); no external identifier resolution is required for capture. Any synthetic-seed import that needs to resolve an identifier uses the existing **deterministic** `resolve_identifier` (single result / `None` / `AmbiguousIdentifier`).
2. **Rationale.** Precedence (ISIN > CUSIP > … or a firm order) only matters for **multi-vendor ingestion** (P1B-5 / vendor adapters / P9), which P1C does not do. Capturing a portfolio holding references an instrument the platform already owns by internal id — no precedence needed.
3. **Alternatives considered.** (a) Build precedence in P1C — rejected: no multi-vendor driver; premature. (b) Forbid identifier use entirely in P1C — unnecessary; the deterministic `resolve_identifier` is available and sufficient.
4. **Risks.** None for P1C capture. OD-012 re-surfaces when vendor ingestion is built.
5. **Impacted requirements.** REQ-SMR-003 (identifier precedence stays deferred).
6. **Impacted controls.** —
7. **ADR update required?** No.
8. **Requirements update required?** Confirm OD-012 remains deferred (now beyond P1C — re-targets to the vendor-ingestion phase).

## OD-P1C-K — Netting / CSA exclusion (OD-015)

1. **Decision.** **OD-015 stays deferred — out of P1C.** P1C adds **no** netting-set / CSA / collateral / counterparty-exposure columns or entities. (This **refines** the earlier readiness expectation that "OD-015 lands in P1C": the explicit P1C exclusion of **counterparty exposure / credit risk** moves OD-015 to a later counterparty-credit-exposure phase, P2+.)
2. **Rationale.** Netting/CSA depth exists to compute **counterparty credit exposure** — squarely in the excluded set (no counterparty exposure, no credit risk, no exposure aggregation). P1C captures portfolio **holdings**, not derivative collateral relationships. Building netting/CSA now would be schema for a capability P1C cannot exercise.
3. **Alternatives considered.** (a) Add netting/CSA columns to `counterparty` in P1C — rejected: dead schema (no consumer); OD-015 is a credit-exposure concern. (b) Keep "OD-015 → P1C" — rejected: contradicts the P1C exclusion list.
4. **Risks.** A re-target of OD-015 must be recorded so it is not lost — done here (→ counterparty-credit-exposure phase, P2+).
5. **Impacted requirements.** REQ-SMR-002 / REQ-CPT-* (counterparty credit, P2+).
6. **Impacted controls.** —
7. **ADR update required?** No.
8. **Requirements update required?** Re-target OD-015 from "P1C" to the counterparty-credit-exposure phase (P2+) at ratification.

## OD-P1C-L — Synthetic data strategy

1. **Decision.** Adopt a **deterministic synthetic-data strategy** as a P1C enabler (it replaces P1B-5 for P1C): (a) a **synthetic reference seed pack** (a fixed set of currencies, a calendar, several legal_entities/issuers, instruments + instrument_terms, identifiers, a couple corporate_actions) built **through the governed binders** (so it carries audit + MANUAL-source lineage like prod); (b) a **synthetic portfolio/transaction/position/valuation dataset** over that seed (exercising FR as-of across multiple valid/known versions); (c) **deterministic** ids via `uuid5` namespaces + **fixed timestamps passed in** (never wall-clock/random); (d) **no real client/vendor data** — synthetic **instances** are DC-1/DC-2 demo fixtures (the entity **type** is DC-3); (e) a **labeled, never-auto-run** seed module (analogous to the governed SYSTEM seeder — test-proven, not wired to a prod post-migrate path), for tests/demos/UI/visualization. The reference seed lands in P1C-1; the domain dataset is built per-slice and consolidated in P1C-6.
2. **Rationale.** P1C needs reference + portfolio data to **exist** (for tests/endpoints/UI), not bulk ingestion (P1B-5 deferred, OD from the readiness review). A deterministic, governed seed is reproducible and safe (no real data), and it is what makes shipping capture before ABAC acceptable (OD-P1C-A).
3. **Alternatives considered.** (a) Do P1B-5 (ingestion mapping) first — rejected: delays the domain without unblocking it. (b) Hand-built per-test fixtures only — rejected: no coherent demo dataset; duplication; non-deterministic risk. (c) Use anonymized real data — rejected: DC-3/DC-4 risk; synthetic-only is the rule.
4. **Risks.** Synthetic data leaking into a prod path — mitigated by a clearly-labeled, **never-auto-run** module, **not** in migrations, distinct from the SYSTEM seeder. Determinism must hold across machines — mitigated by `uuid5` + injected timestamps (the bootstrap precedent; scripts may not call wall-clock/random).
5. **Impacted requirements.** Test/demo enablement (not a product REQ); supports REQ-PPM-001..003 acceptance tests.
6. **Impacted controls.** Governed-write controls (audit + lineage) exercised by the seed.
7. **ADR update required?** No (a build-tooling decision; noted in AD-017 context).
8. **Requirements update required?** None.

---

## Decision summary & required baseline changes

| Decision | Resolution | New ADR? | Governance change at ratification |
|---|---|---|---|
| OD-P1C-A ABAC granularity / scope model | Anchor-not-enforce in P1C; **portfolio-level** granularity (closes **OD-025**); enforcement → P6+ | AD-017 | REQ-PPM-001 annotation; entitlement_sod_model OD-025 closure |
| OD-P1C-B node vs subtree | **Subtree** semantics (closes **OQ-014**); recorded now, enforced P6+ | AD-017 | REQ-PPM-001 annotation; OQ-014 closure |
| OD-P1C-C node model | **Single `portfolio` EV table** + `node_type` vocab + self-FK adjacency | No | ENT-010 canonical annotation |
| OD-P1C-D position grain | **Aggregated by (portfolio, instrument)**, signed qty; market value excluded | AD-017 | REQ-PPM-002 annotation |
| OD-P1C-E txn↔position | **Captured independently**; no derivation engine/FK in P1C | AD-017 | REQ-PPM-003 annotation |
| OD-P1C-F valuation source | **Single captured mark** + source label; no model; precedence deferred | AD-017 | REQ-PPM-003 annotation |
| OD-P1C-G dataset_snapshot | **Stays P2** (closes **OQ-013a**); not built in P1C | Conforms AD-014 | REQ-PPM-004 status confirm |
| OD-P1C-H exposure aggregation | **Stays deferred (P2)**; `exposure.aggregate.run` reserved-unwired | Conforms AD-014 | REQ-PPM-004 status confirm |
| OD-P1C-I corporate-action application | **Excluded** (capture-only holds) | Conforms OD-P1B-B | none |
| OD-P1C-J identifier precedence (OD-012) | **Deferred** beyond P1C (vendor-ingestion phase); internal `instrument_id` used | No | OD-012 re-target note |
| OD-P1C-K netting/CSA (OD-015) | **Deferred out of P1C** → counterparty-credit-exposure phase (P2+) | No | OD-015 re-target note |
| OD-P1C-L synthetic data | **Deterministic governed synthetic seed + dataset**; no real data | No | none |

**Proposed new ADR — AD-017 (to be ratified post-approval):** *"P1C is a capture-only domain block. Positions (FR) and valuations (FR) are captured directly as as-of-reconstructable masters — never derived from transactions (IA log) and never computed from prices; no calculation, no derived governed output, no `dataset_snapshot`, no exposure aggregation in P1C (AD-014 honored by exclusion). The portfolio hierarchy (single EV table, node_type + subtree adjacency) is the entitlement scope ANCHOR; portfolio-level ABAC enforcement is deferred to P6+. Corporate actions stay capture-only; identifier precedence (OD-012) and netting/CSA (OD-015) stay deferred."* Conforms to AD-005 (temporal classes), AD-013-R1 (symmetric-never-hybrid for proprietary), AD-008/ENT-P-06 (scope), AD-014 (reproducibility gate).

**Net:** all twelve decisions resolved; **OD-025, OQ-014, OQ-013a closed**; OD-012 / OD-015 re-targeted with a recorded home; no decision requires building any excluded capability. **P1C-1 is ready to plan** (see `p1c_implementation_plan.md`).

> **Ratification scope note (2026-06-23):** this P1C-0 ratification is **P1C-1-focused** — it records REQ-PPM-001 (→ In-Progress) + AD-017 + the **portfolio** baselines (`PORTFOLIO.*` reserved, `portfolio.*` grants, ENT-010/OD-013/OD-025). The **REQ-PPM-002/003** annotations (positions / transactions / valuations) named in OD-P1C-D/E/F are **intentionally deferred to their P1C-2/3/4 slice ratifications** (they stay `Draft` for now), and the sibling `TRANSACTION.*`/`POSITION.*`/`VALUATION.*` families + their permissions are reserved for those later slices — not granted in this turn.
