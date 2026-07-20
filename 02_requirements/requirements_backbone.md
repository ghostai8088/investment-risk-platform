# Requirements Backbone

## Document Control

| Field | Value |
|---|---|
| Document ID | REQ-BACKBONE-001 |
| Version | 0.1 (Draft baseline) |
| Status | Accepted as the governed requirements baseline (extended per phase) |
| Owner | R-01 Product Manager AI |
| Approver | H-07 Product Owner |
| Created | 2026-06-18 |
| Last Reviewed | 2026-06-18 |
| Related Documents | requirements_traceability_matrix.md, personas_and_user_journeys.md, definition_of_ready_done.md, ../10_delivery_backlog/build_sequence.md, ../01_product_strategy/capability_map.md, ../09_compliance_controls/control_matrix_skeleton.md |
| Supported Build Rules | BR-1 … BR-19 (this is the governance backbone that future build work traces to) |

## 1. Purpose & Method

Convert the full-scope capability map into a controlled requirements backbone that governs all future build work. This is **not
application code** and adds no domain functionality. It assigns stable IDs to capabilities (CAP-x.y) and requirements
(REQ-DOMAIN-NNN), and — together with the [traceability matrix](requirements_traceability_matrix.md) — maps every requirement to
its capability, persona, line of defense, governance obligations, control, build phase, dependency, acceptance criteria, and
status.

**Document split.** To keep every attribute legible, descriptive attributes (business purpose, functional, data, calculation,
test, acceptance) live here; traceability attributes (persona, LoD, audit, entitlement, lineage, model-governance, control,
phase, dependency) live in the RTM. Both are keyed by REQ-ID; **Status is canonical here**.

**Granularity.** Requirements are at *feature/epic* level. Granular, testable user stories are derived per phase at the point a
requirement enters build, gated by the [Definition of Ready/Done](definition_of_ready_done.md). Version 0.1 establishes the
governing set; each phase entry expands and refines its domain's requirements.

## 2. ID Conventions

| Artifact | Pattern | Example |
|---|---|---|
| Capability | `CAP-<domain#>.<sub#>` | `CAP-5.1` (Market Risk → VaR/ES) |
| Requirement | `REQ-<DOMAIN>-<NNN>` | `REQ-MKT-001` |
| Baseline cross-cutting requirement | `BX-<CODE>` | `BX-AUD` |
| Persona | `P-<code>` (alias of `PERSONA-0x`) | `P-RA` |
| Build phase | `P<n>` | `P2` |
| Dependency token | `DEP-<CODE>` / `FW-<CODE>` | `DEP-LIN`, `FW-RUN` |
| Control | `CTRL-NNN` (from control matrix) | `CTRL-006` |

Domain codes: PPM, SMR, PUB, PRV, MKT, CRD, CPT, LIQ, SCN, LIM, BRC, MDG, DQR, LIN, AUD, RPT, ADM, INT, BAI.

## 3. Foundation Status & Assumptions (what already exists)

The cross-cutting foundation slice (Step 1E, commit `4f93a33`) exists and is CI-green, **but only to its documented extent** —
see `../03_architecture/foundation_slice.md`. Requirements must not assume more than the following:

| Foundation | Exists | Known placeholders (do NOT assume) |
|---|---|---|
| `FW-TMP` Persistence + temporal base | Yes (FR/IA/EV mixins, tenant column, RLS in migration) | FR/EV used only by the audit/entitlement tables so far; domain FR usage unproven |
| `FW-AUD` Audit framework | Yes (append-only, SHA-256 chain, verify, checkpoint) | Per-tenant write concurrency control pending (OD-051); signing/WORM later |
| `FW-ENT` Entitlement skeleton | Yes (deny-by-default, tenant-scoped, FastAPI gate) | **No SoD/maker-checker; identity is a dev header shim, not SSO** |
| `FW-RUN` Calculation-run framework | Yes (run record, status, audit on transitions) | Reproducibility FKs (snapshot/model/assumption) are **nullable placeholders** |

These limits define the explicit forward dependencies in §6.

## 4. Capability Taxonomy (CAP-x.y) — stable IDs for all capabilities

| Domain | Sub-capabilities |
|---|---|
| **CAP-1 Portfolio & Position Management** | 1.1 Portfolio/Fund/Strategy hierarchy · 1.2 Position master · 1.3 Transaction history · 1.4 Valuation history · 1.5 Exposure aggregation |
| **CAP-2 Security Master & Reference Data** | 2.1 Instrument master · 2.2 Issuer/Counterparty entities + hierarchy · 2.3 Identifier cross-reference · 2.4 Corporate actions · 2.5a Calendars · 2.5b Currencies/rating scales *(2.5 re-partitioned P1B-0: 2.5a→REQ-SMR-004, 2.5b→REQ-SMR-005)* |
| **CAP-3 Public Asset Data** | 3.1 Market prices · 3.2 Yield curves · 3.3 Volatility data · 3.4 Credit spreads · 3.5 Ratings/benchmarks |
| **CAP-4 Private Asset Data** | 4.1 Commitments + funded/unfunded · 4.2 Capital calls & distributions · 4.3 GP NAV reports & appraisals · 4.4 Private company financials (MNPI) · 4.5 Valuation dates/stale flags/proxy mappings |
| **CAP-5 Market Risk** | 5.1 VaR/Expected Shortfall · 5.2 Sensitivities (duration/convexity/greeks/spread duration) · 5.3 Factor exposure & contribution · 5.4 Drawdown/basis risk · 5.5 Market stress |
| **CAP-6 Credit Risk** | 6.1 PD/LGD/EAD/EL · 6.2 Migration/downgrade stress · 6.3 Spread risk · 6.4 Concentration · 6.5 Internal/shadow ratings |
| **CAP-7 Counterparty Risk** | 7.1 Current exposure · 7.2 PFE/EPE · 7.3 Netting sets/collateral/CSA · 7.4 Counterparty limits/wrong-way · 7.5 CVA (placeholder maturity) |
| **CAP-8 Liquidity Risk** | 8.1 Liquidity classification · 8.2 Redemption stress/waterfall · 8.3 Funding liquidity/facility usage · 8.4 Margin-call stress · 8.5 Capital-call forecasting/CFP indicators |
| **CAP-9 Scenario & Stress Testing** | 9.1 Historical · 9.2 Hypothetical/macro · 9.3 Reverse stress · 9.4 Combined market-credit-liquidity · 9.5 Private asset valuation shock |
| **CAP-10 Limit Monitoring** | 10.1 Limit framework definition · 10.2 Utilization computation · 10.3 Soft/hard limits · 10.4 Breach detection |
| **CAP-11 Breach Workflow** | 11.1 Breach record & assignment · 11.2 1L response · 11.3 2L review · 11.4 Escalation & closure evidence |
| **CAP-12 Model Governance** | 12.1 Model inventory · 12.2 Versioning/assumptions/limitations · 12.3 Tiering · 12.4 Validation workflow & effective challenge · 12.5 Approval/restricted-use status |
| **CAP-13 Data Quality & Reconciliation** | 13.1 DQ rules · 13.2 Reconciliation · 13.3 Exception management · 13.4 Manual overrides |
| **CAP-14 Data Lineage** | 14.1 Source-to-target mapping · 14.2 Lineage capture for results/reports · 14.3 Lineage query/visualization |
| **CAP-15 Auditability** | 15.1 Audit event capture · 15.2 Hash-chain integrity & verification · 15.3 Audit query & extract · 15.4 Override/approval audit |
| **CAP-16 Reporting** | 16.1 Risk reports (market/credit/liquidity) · 16.2 Scenario/breach reports · 16.3 Board risk report · 16.4 DQ/model-inventory reports · 16.5 Audit extract/reproducibility |
| **CAP-17 Administration & Entitlements** | 17.1 Authentication/SSO · 17.2 RBAC/ABAC entitlements · 17.3 SoD/maker-checker · 17.4 Admin console · 17.5 Export controls/classification (MNPI) |
| **CAP-18 Integration Readiness** | 18.1 CSV/Excel upload · 18.2 API adapter · 18.3 SFTP adapter · 18.4 Vendor/accounting/market-data adapters · 18.5 GP report ingestion adapter |
| **CAP-19 BAU AI Agent Support** | 19.1 DQ monitoring agent · 19.2 Breach triage agent · 19.3 Scenario commentary agent · 19.4 Model monitoring agent · 19.5 Board reporting/evidence agent |
| **CAP-20 Performance Measurement** *(MINTED PM-1, 2026-07-09; the ENT-mint analog for a homeless governed number — OQ-PM-1-9)* | 20.1 Portfolio return (time-weighted, Modified-Dietz) · 20.2 Money-weighted return / IRR *(PA-0)* · 20.3 Performance attribution *(deferred)* · 20.4 Composites / GIPS presentation *(deferred)* · 20.5 Ex-post benchmark-relative (active return / tracking error / tracking difference / information ratio) *(REALIZED P3-8, 2026-07-10)* |

## 5. Baseline Cross-Cutting Requirements (BX) — inherited by every applicable requirement

These encode the non-negotiable build rules once. Each requirement in §7 inherits the applicable BX (flagged in the RTM); a
requirement is not Done unless its inherited BX are satisfied.

| BX | Requirement | Build Rule | Control | Dependency |
|---|---|---|---|---|
| BX-AUD | Every create/update/approve/override emits an audit event via `FW-AUD` | BR-5, BR-12 | CTRL-005, CTRL-012 | FW-AUD |
| BX-ENT | Every access is entitlement-checked, deny-by-default, tenant-scoped | BR-11, BR-17 | CTRL-011 | FW-ENT |
| BX-LIN | Every governed output binds source→run lineage | BR-6, BR-13 | CTRL-006, CTRL-013 | DEP-LIN |
| BX-TMP | Every persisted entity declares a temporal class (FR/IA/EV) | BR-19 | CTRL-017 | FW-TMP |
| BX-REPRO | Every calculation result is reproducible from its bound run | BR-6, BR-9 | CTRL-018 | FW-RUN |
| BX-TEST | No requirement is Done without tests | BR-1 | CTRL-001 | — |
| BX-DOC | Calcs have methodology docs; models inventoried; fields in dictionary | BR-2, BR-3, BR-4 | CTRL-002/003/004 | DEP-MREG, DEP-DQF |
| BX-LIM | Known limitations explicitly documented | BR-14 | CTRL-014 | — |
| BX-SOD | Maker-checker / SoD enforced for overrides, limits, model & entitlement changes, publication, deploy | BR-7, BR-15 | CTRL-015, CTRL-021, CTRL-025 | FW-ENT (SoD pending) |

## 6. Forward Dependency Registry

| Token | Meaning | Status |
|---|---|---|
| FW-TMP / FW-AUD / FW-ENT / FW-RUN | Foundation slice frameworks | Exist (with §3 placeholders) |
| DEP-LIN | Data lineage skeleton (capture + source-to-target + query) | **Exists** (capture skeleton, P1A-1: `data_source`/`lineage_edge` + `record_lineage`; query/viz is REQ-LIN-002/P7) |
| DEP-MREG | Model registry skeleton (inventory + version binding) | **Exists** (inventory + version-binding skeleton, P1A-2: `model`/`model_version`/`model_assumption`/`model_limitation` + `register_model`; tiering REQ-MDG-002/P7, validation REQ-MDG-003/P7) |
| DEP-DQF | Data quality framework (rules engine + exceptions) | **Exists** (DQ rules-engine skeleton — `data_quality_rule`/`data_quality_result` + `DQRule.evaluate` + `run_quality_check` + `assert_passed_quality_checks`, P1A-3; reconciliation REQ-DQR-002/P7, overrides REQ-DQR-003/P7) |
| DEP-SMR | Security Master / Reference Data domain | **Future** (CAP-2) |
| DEP-SSO | Real SSO / OIDC identity (replaces dev header shim) | **Future** (CAP-17, AD-007) |
| DEP-MGW | Full model governance / validation workflow | **Future** (CAP-12) |
| DEP-WFL | Workflow/state-machine engine (breach lifecycle) | **Future** (CAP-11) |
| DEP-RPT | Reporting/rendering engine | **Future** (CAP-16) |
| DEP-CIH | CI hardening: Alembic autogenerate drift check (OD-052) + audit-write concurrency control (OD-051) | **Future** (P0 hardening) |
| DEP-FELOCK | Frontend lockfile + `npm ci` reproducibility | **Future** (P0 hardening) |

## 7. Requirements by Domain

Columns: **REQ** · **Title** · **CAP** · **Business purpose** · **Functional requirement** · **Data requirement** ·
**Calc requirement** (— if none) · **Test requirement** · **Acceptance criteria (key)** · **Status**. Persona/LoD/audit/
entitlement/lineage/model-gov/control/phase/dependency are in the [RTM](requirements_traceability_matrix.md).

### CAP-1 Portfolio & Position Management (PPM)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-PPM-001 | Portfolio/fund/strategy/account hierarchy | 1.1 | Organize holdings for aggregation & entitlement scope | CRUD + versioned hierarchy nodes; entitlement scope anchor (ABAC **anchored, not enforced** in P1C-1 — enforcement P6+) | `portfolio/fund/strategy/account` (**EV — single table + `node_type` + `parent_portfolio_id` adjacency**, P1C-1) | — | Hierarchy build + scope test | A node tree persists, is tenant-scoped, and is the portfolio-scope anchor (subtree semantics recorded; enforcement deferred) | **In-Progress (P1C-0 ratified 2026-06-23; P1C-1 planned)** |
| REQ-PPM-002 | Position master (as-of) | 1.2 | Single source of holdings for all risk | Positions keyed to instrument + portfolio, bitemporal | `position` (FR) → CAP-2 instruments | — | As-of reconstruction test | A position is reconstructable for any past as-of date | In-Progress (P1C-3: `position` FR captured + both-axes as-of reconstruction built, migration `0014`; the residual open conjunct is portfolio-scope ABAC enforcement → P6+ — not closeable until then) |
| REQ-PPM-003 | Transaction & valuation history | 1.3/1.4 | Provenance of holdings and value | Append-only transactions; valuation history | `transaction` (IA), `valuation` (FR) | — | Append-only + history test | Transactions immutable; valuations queryable as-of | **Done (both conjuncts realized: `transaction` IA append-only, P1C-2 migration `0013`; `valuation` FR captured-marks + both-axes as-of, P1C-4 migration `0015`; no scope-enforcement residual gates it — OD-P1C4-5)** |
| REQ-PPM-004 | Exposure aggregation | 1.5 | Roll up exposures across hierarchy | Run-tracked aggregation over scope | derived from positions/valuations | Aggregation (QS-21) | Aggregation benchmark | Aggregates reproduce within tolerance and bind lineage | In-Progress (P2; P2-0 ratified 2026-06-26; AD-014 `dataset_snapshot` prereq IMPLEMENTED P2-1 `0016` + `fx_rate` P2-2 `0017`. **P2-3 ratified-in-planning 2026-06-26 (AD-018):** `exposure_aggregate` (ENT-014, IA append-only) = **basic, run-bound + snapshot-gated, signed market value v1** (signed qty × captured mark × effective FX), reproducible within tolerance + lineage-bound. **Basic exposure ONLY — does NOT imply market/factor risk, VaR, ES, stress, performance, or reporting** (deferred P3+). Builds at the P2-3 implementation slice, migration `0018`) |

### CAP-2 Security Master & Reference Data (SMR)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-SMR-001 | Instrument master | 2.1 | Canonical instrument terms for pricing/risk | CRUD instruments with effective-dated terms | `instrument` (**EV identity**) + `instrument_terms` (**FR** economic/legal terms) — split ratified P1B-0/OD-P1B-A, per AD-005 §2A | — | Effective-dating + reconstruct-as-of test | Instrument terms reconstructable as-of (FR); classified per DC | **In-Progress (P1B-3, migration 0010):** instrument EV + instrument_terms FR with as-of reconstruction on BOTH axes delivered; pricing/cashflow/valuation terms math deferred to P2+ |
| REQ-SMR-002 | Issuer/counterparty entities + hierarchy | 2.2 | Aggregate credit/counterparty exposure | Entities with LEI + parent hierarchy | `issuer`, `counterparty` (EV) — separate role/profile tables over an implementation-only `legal_entity` core (OD-P1B-D; no canonical ENT id) | — | Hierarchy rollup test | Exposure rolls to ultimate parent | **In-Progress (P1B-2):** core + 1:1 profiles + LEI + parent-hierarchy STRUCTURE shipped (migration 0009, symmetric RLS); exposure-rollup CALC deferred (P2+) |
| REQ-SMR-003 | Identifier cross-reference | 2.3 | Resolve vendor/standard identifiers | Xref ISIN/CUSIP/SEDOL/FIGI/internal | `identifier_xref` (EV) | — | Resolution + precedence test | Any known identifier resolves to one instrument — **P1B partial**: deterministic single-result-or-`AmbiguousIdentifier`; cross-vendor **precedence deferred to P1C/OD-012** (OD-P1B-G) | **In-Progress (P1B-3, migration 0010, partial):** deterministic single-result-or-`AmbiguousIdentifier` delivered; cross-vendor precedence / external validation deferred to P1C/OD-012 |
| REQ-SMR-004 | Corporate actions & calendars | 2.4/2.5a | Correct economics over time | Effective-dated corporate actions; market calendars | `corporate_action`, `calendar` (EV) — corporate_action EV ratified P1B-0/OD-P1B-B | Day-count/roll (QS-10/11) | Calendar/roll test | Actions apply on effective date — **P1B delivers the calendar (P1B-1) + corporate_action (P1B-4) reference ENTITIES only; "calendars drive rolls" (QS-10/11 day-count/roll math) deferred to P1C** (OD-P1B-B) | **In-Progress (P1B-1 calendar partial + P1B-4 corporate_action, migration 0011):** corporate_action EV capture-only delivered (status lifecycle + REFERENCE.STATUS_CHANGE); roll/day-count math (QS-10/11) deferred to P1C |
| REQ-SMR-005 | Standard reference vocabularies (currency, rating scale) | 2.5b | Curated ISO/standard taxonomies for pricing/risk | CRUD currency (ISO-4217) + rating-scale/grade taxonomy; hybrid global+tenant-override (AD-013-R1) | `currency` (EV), `rating_scale` (EV — scale/grade taxonomy only; rating **assignments** are FR, ENT-007, deferred) | — | Hybrid-RLS + override test | ISO-4217 currency + rating scales seeded global, tenant-overridable; effective-dated; audited + lineage-rooted | Ratified (P1B-0, new); build P1B-1 |

### CAP-3 Public Asset Data (PUB)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-PUB-001 | Market prices (time-series) | 3.1 | Inputs for valuation & risk | Bitemporal price points per instrument/source | `price_point` (FR) | — | As-of + staleness test | Price reconstructable as-of; stale flagged (QS-16) | **In-Progress (partial, P2-4 implementation, migration `0019`):** `price_point` (ENT-020, FR) realized — the **"price reconstructable as-of"** acceptance leg delivered on BOTH axes (`reconstruct_price_as_of`; captured RAW vendor prices; 6-part current-head key with `price_source`; `MARKET.PRICE_*` audited; VENDOR_PRICE ORIGIN lineage; symmetric RLS; required-field + strictly-positive RANGE DQ). The **"stale flagged (QS-16)"** leg is **DEFERRED** (OQ-P2-4-4) — REQ does **NOT** close |
| REQ-PUB-002 | Curves & volatility surfaces | 3.2/3.3 | Discounting & options risk | Versioned curves/surfaces with interpolation method | `yield_curve`, `volatility_surface` (FR) | Interpolation (QS-13) | Interpolation test | Curve/surface values reproduce; method declared | **In-Progress (partial, P2-5 implementation, migration `0020`):** `yield_curve` (ENT-021) realized as the unified `curve` (FR header) + `curve_point` (IA append-only nodes) — the **"curve values reproduce"** acceptance leg delivered on BOTH axes (`reconstruct_curve_as_of`; captured curves; 6-part current-head key; `MARKET.CURVE_*` audited; VENDOR_CURVE ORIGIN lineage; symmetric RLS; required-field + value-type-conditional RANGE DQ). **`volatility_surface`** (ENT-022) AND the **"interpolation method declared" / QS-13 interpolation-test** leg are **DEFERRED** (`interpolation_method` captured as an inert label, OQ-P2-5-9; NO interpolation engine) — REQ does **NOT** close |
| REQ-PUB-003 | Credit spreads, ratings, benchmarks | 3.4/3.5 | Credit & relative risk inputs | Spread series, ratings, benchmark constituents | `credit_spread`, `rating`, `benchmark` (FR/EV) | — | Coverage test | Inputs present & as-of for the risk engine | **In-Progress (partial, P2-6 implementation, migration `0021`):** `credit_spread` (ENT-023, P2-5 by value) + **`benchmark` (ENT-009) REALIZED** (P2-6: `benchmark` EV definition + `benchmark_constituent` FR membership) — the **"inputs present & as-of"** spread-coverage AND benchmark-membership legs delivered (`reconstruct_membership_as_of`; symmetric RLS; VENDOR_BENCHMARK lineage; `REFERENCE.*`/`MARKET.BENCHMARK_CONSTITUENT_*` audited). **`rating`** + the deferred `benchmark_level`/`benchmark_return` + the full **Coverage test** remain **DEFERRED** — REQ does **NOT** close |

### CAP-4 Private Asset Data (PRV)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-PRV-001 | Commitments & funded/unfunded | 4.1 | Track private exposure & dry powder | Commitment records with funded/unfunded | `commitment` (FR) | — | Funded/unfunded test | Unfunded exposure computed and aggregated | **In-Progress (CC-1, 2026-07-20)** — ENT-015 REALIZED (migration `0044`; the FR capture lifecycle + the chain-immutable currency + the stable (portfolio, instrument) identity; `commitment.edit`/`.view` mint; demo stage 8 live). **The acceptance clause "Unfunded exposure computed and aggregated" and the "Funded/unfunded test" leg are explicitly OPEN → CC-2** (a persisted unfunded number is a governed derived output — snapshot/run/model-bound — and lands with the pacing projection; OD-CC-1-E). |
| REQ-PRV-002 | Capital calls & distributions | 4.2 | Cashflow & liquidity inputs | Append-only call/distribution events | `capital_call`, `distribution` (IA) | — | Cashflow test | Events immutable; feed liquidity forecast | **In-Progress (CC-1, 2026-07-20)** — ENT-016 REALIZED (migration `0044`; truly-immutable IA events under P0001 triggers + ORM guards; the FULL-REVERSAL negation correction path; `is_recallable` captured as data; `commitment.record`/`.view` mint; the OD-CC-1-D read rule recorded at every consumer surface). **"Events immutable" DISCHARGED (test-pinned both layers); the "feed liquidity forecast" clause stays OPEN → CC-2** (the pacing/liquidity projection is the governed consumer). |
| REQ-PRV-003 | GP NAV / appraisals + stale flags | 4.3/4.5 | Valuation of illiquid assets | NAV/appraisal with valuation date + staleness | `gp_report`, `appraisal` (FR) | Staleness (QS-16) | Stale-valuation test | Stale NAV flagged; proxy mapping recorded | Draft |
| REQ-PRV-004 | Private company financials (MNPI) | 4.4 | Fundamental private credit/equity input | Restricted (DC-4) financials behind barriers | `private_company_financials` (FR) | — | MNPI access-denied test | DC-4 access requires need-to-know grant; denials audited | Draft |
| REQ-PRV-005 | Private-to-public factor proxy mapping | 4.6 | Represent a private holding's risk as a loading on public risk factors — the substrate the desmoothing/proxy transform projects onto (the differentiation-thesis destination) | Captured FR proxy-weight table mapping a private instrument to public `factor` definitions (a governance judgment call, not a computed regression in v1) | `proxy_mapping` (ENT-019, FR) | — | Capture/supersede/reconstruct + cross-tenant-FK refusal test | A private instrument maps to ≥1 public factor with signed weights (NOT forced to sum to 1 — a partial proxy is honest); versions reconstruct bitemporally; both FK targets fail closed cross-tenant | **In-Progress (PA-0, 2026-07-11, migration `0034`):** `proxy_mapping` (ENT-019) — captured private→public factor proxies v1 (MANUAL method; CURRENCY-family factors); REUSES `marketdata.view`/`.ingest`. **The desmoothing/proxy TRANSFORM (Geltner AR(1) v1) is the PA-1 follow-on; regression-derived weights, capital calls/distributions/IRR, and non-CURRENCY factor families DEFERRED.** *(Dated refresh, Wave-7 close 2026-07-19 — the F5 status-decay fix: the desmoothing transform SHIPPED at PA-1 and gained the AR1_ESTIMATED/OKUNEV_WHITE_ITERATIVE estimator conventions at DS-2 (migration `0042`); regression-derived weights SHIPPED at PA-3 with the EWMA/EB-shrinkage residual conventions added at RS-1; non-CURRENCY factor families SHIPPED at FL-1; **capital calls/distributions/IRR remain the open clause** — the presumptive Wave-8 headline.)* REQ does **NOT** close |

### CAP-5 Market Risk (MKT)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-MKT-001 | Value at Risk / Expected Shortfall | 5.1 | Quantify tail loss for limits & board | Pluggable VaR/ES (parametric/historical/MC) as run | positions+market (FR) snapshot | Deterministic, seeded MC (QS-18) | Benchmark VaR within ε; reproduction test | VaR matches reference within ε; re-run identical; method has methodology doc + inventory entry | In-Progress (parametric VaR P3-5; historical-sim VAR-HS-1; total PA-4/BT-2; **parametric ES ES-1 2026-07-15; ES-over-HS ES-HS-1 2026-07-17** — Monte-Carlo VaR + ES-over-MC still open, so the REQ does not close) |
| REQ-MKT-002 | Sensitivities | 5.2 | Risk decomposition & hedging | Duration/convexity/greeks/spread duration | positions+market (FR) | Analytic/bump (QS) | Sensitivity benchmark | Greeks reproduce within ε; conventions declared | In-Progress (P3-1: analytic curve-node DV01/spread-DV01, migration `0022`; instrument-attributed greeks deferred — backbone status aligned to the RTM at the 2026-07-06 status-decay audit rule) |
| REQ-MKT-003 | Factor exposure & contribution | 5.3 | Attribute risk to factors | Factor model exposures & contributions | factor returns (FR) | Factor calc | Attribution test | Contributions sum to total within ε | In-Progress (P3-2 inputs `0023` + P3-3 allocation-v1 exposures `0024` — sum-to-total exact; beta/regression + contribution-to-risk deferred) |
| REQ-MKT-004 | Market stress | 5.5 | Loss under defined shocks | Apply shock set to portfolio | scenario defs (CAP-9) | Revaluation | Stress benchmark | Stress P&L reproduces; binds scenario version | Draft |
| REQ-MKT-005 | VaR backtesting (outcomes analysis) | 5.1/12.5 | Hold the shipped VaR numbers accountable against realized outcomes — the SR 11-7 "outcomes analysis" leg and the Basel backtesting discipline (the Wave-1 close review's named nearest supervisory gap) | Governed backtest as a run over ONE portfolio-return run + N pinned VaR forecasts of ONE method: per-pair exception indicators + Kupiec POF (fixed-critical decision at a DECLARED alpha) + the Basel traffic-light zone on its defined (0.99, 250) domain only | PM-1 `portfolio_return_result` rows (realized flow-adjusted P&L) + `var_result` rows, all snapshot-pinned | STRICT exception rule; Kupiec χ²(1) TWO-SIDED; Decimal-50 `Decimal.ln`; `Numeric(28,6)`; calendar-day horizon alignment, ALL-OR-NOTHING | Kernel goldens + independent float `math.log` cross-check + TR-09 reproduction under re-runs of both sides | Statistics match the independent reference within ε; re-run identical; a later VaR or return re-run cannot move a historical backtest; method has methodology doc + inventory entry | **In-Progress (BT-1, 2026-07-10, migration `0033`):** `var_backtest_result` (ENT-055) — v1 (`risk.var_backtest`, declared alpha {0.05, 0.01}); REUSES `risk.run`/`risk.view`. **ACTUAL P&L only (hypothetical/clean deferred); Kupiec only (Christoffersen = a BT-3 candidate); no Basel multiplier arithmetic; no p-values; the PM-1 captured-holdings bias propagates ANTI-CONSERVATIVELY (recorded).** **ADVANCED at BT-2 (2026-07-15): `VAR_PARAMETRIC_TOTAL` ADMITTED to the lane (the PA-4 exclusion discharged) under the recorded honest-pairing doctrine — daily pairing on an appraisal-marked book is biased two ways by construction (suppressed off-mark, clustered on-mark), so its unconditional verdict is NOT valid evidence of adequacy in either direction; the dated per-pair rows are the evidence surface. Appraisal-frequency pairing + a Christoffersen leg = BT-3 candidates *(dated PARTIAL discharge, BT-3 2026-07-19: the Christoffersen leg SHIPPED as v2-christoffersen; appraisal-frequency pairing stays the open clause)*.** REQ does **NOT** close |

### CAP-6 Credit Risk (CRD)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-CRD-001 | PD/LGD/EAD/EL | 6.1 | Expected credit loss | Compute EL from PD×LGD×EAD | exposures, ratings | EL calc | EL benchmark | EL reproduces; assumptions/limitations documented | Draft |
| REQ-CRD-002 | Migration & downgrade stress | 6.2 | Credit deterioration impact | Rating migration matrices & downgrade shocks | ratings, migration matrix | Migration calc | Migration test | Downgrade stress reproduces; binds scenario | Draft |
| REQ-CRD-003 | Concentration & spread risk | 6.3/6.4 | Identify credit concentrations | Concentration metrics; spread sensitivity | exposures, spreads | Concentration/spread calc | Concentration test | Limits-ready metrics produced per issuer/sector | Draft |
| REQ-CRD-004 | Internal/shadow ratings | 6.5 | Rate unrated/private exposures | Internal rating model + override (audited) | financials, ratings | Rating model | Rating + override test | Internal rating produced; overrides carry BR-7 fields | Draft |

### CAP-7 Counterparty Risk (CPT)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-CPT-001 | Current exposure & netting sets | 7.1/7.3 | Net counterparty exposure | CE per netting set incl. collateral/CSA | trades, CSA, collateral | Netting calc (QS-22) | Netting test | CE nets correctly per CSA; no double count | Draft |
| REQ-CPT-002 | PFE / EPE | 7.2 | Potential future exposure | Simulated PFE/EPE profiles | market, trades | Deterministic seeded MC (QS-18) | PFE benchmark | PFE reproduces with recorded seed | Draft |
| REQ-CPT-003 | Counterparty limits & wrong-way | 7.4 | Control counterparty risk | Limit checks; wrong-way flagging | exposures, limits | Exposure calc | Limit/wrong-way test | Breaches feed CAP-10; wrong-way flagged | Draft |
| REQ-CPT-004 | CVA placeholder | 7.5 | Future credit valuation adjustment | Structural placeholder, marked low-maturity | exposures, spreads | CVA (placeholder) | Placeholder test | Capability present, limitations documented (BX-LIM) | Draft |

### CAP-8 Liquidity Risk (LIQ)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-LIQ-001 | Liquidity classification | 8.1 | Bucket assets by liquidity | Classify positions into liquidity tiers | positions, instrument attrs | Classification | Classification test | Each position has a liquidity tier; % illiquid computed | Draft |
| REQ-LIQ-002 | Redemption stress & waterfall | 8.2 | Survive redemption shocks | Apply redemption scenarios; waterfall | positions, scenarios | Waterfall calc | Redemption test | Waterfall reproduces; coverage ratios produced | Draft |
| REQ-LIQ-003 | Margin-call & funding stress | 8.3/8.4 | Funding adequacy under stress | Facility usage, margin-call stress | facilities, collateral | Stress calc | Funding test | Funding gap computed under shocks | Draft |
| REQ-LIQ-004 | Capital-call forecasting | 8.5 | Forecast private cash needs | Forecast calls from commitments | commitments (CAP-4) | Forecast calc | Forecast test | Forecast reproduces; feeds CFP indicators | Draft |

### CAP-9 Scenario & Stress Testing (SCN)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-SCN-001 | Scenario definition & versioning | 9.1/9.2 | Saved, versioned shock sets | Define historical/hypothetical/macro scenarios | `scenario_definition` (IA) | — | Versioning test | Scenario versioned with saved assumptions (BR-8) | Draft |
| REQ-SCN-002 | Reverse stress testing | 9.3 | Find shocks that breach tolerance | Search for breaching scenarios | scenarios, results | Reverse-solve | Reverse-stress test | Produces shock set hitting a target loss | Draft |
| REQ-SCN-003 | Combined & private-asset shock | 9.4/9.5 | Holistic stress incl. illiquids | Combined market-credit-liquidity + NAV shock | scenarios, private NAV | Revaluation | Combined-stress test | Combined run reproduces; binds all input versions | Draft |

### CAP-10 Limit Monitoring (LIM)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-LIM-001 | Limit framework definition | 10.1/10.3 | Encode risk appetite | Define soft/hard limits with scope; maker-checker | `limit_definition` (EV) | — | Limit-definition + SoD test | Limit changes are maker-checked & audited (BX-SOD) | Draft |
| REQ-LIM-002 | Utilization computation | 10.2 | Measure usage vs limit | Compute utilization from risk results | risk results, limits | Utilization calc | Utilization test | Utilization reproduces and binds source results | Draft |
| REQ-LIM-003 | Breach detection | 10.4 | Detect limit breaches | Evaluate utilization vs thresholds; raise breach | utilization | Threshold eval | Detection test | Soft/hard breach raised and emits `LIMIT`/`BREACH` events | Draft |

### CAP-11 Breach Workflow (BRC)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-BRC-001 | Breach record & assignment | 11.1 | Track breaches to closure | Create breach, assign owner, start timer | `breach` (IA) | — | Workflow-state test | Breach has owner, state machine, audit trail | Draft |
| REQ-BRC-002 | 1L response & 2L review (SoD) | 11.2/11.3 | Independent oversight | 1L responds; 2L reviews; SoD enforced | `breach_action` (IA) | — | SoD (SOD-02) test | 1L cannot approve own closure; 2L review required | Draft |
| REQ-BRC-003 | Escalation & closure evidence | 11.4 | Demonstrable remediation | Escalate overdue; capture closure evidence | breach_action | — | Closure-evidence test | Closure requires evidence + approval; fully audited | Draft |

### CAP-12 Model Governance (MDG)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-MDG-001 | Model inventory & versioning | 12.1/12.2 | Single register of models | Register every model/version + assumptions/limitations | `model` (EV), `model_version` (IA), `model_assumption`/`model_limitation` (IA) | — | Inventory-binding test | No calc runs without an inventory entry (BR-3) | In-Progress (P1A-2 skeleton) |
| REQ-MDG-002 | Tiering | 12.3 | Proportionate governance | Assign Tier 1/2/3 by criteria | model metadata | — | Tiering test | Each model has a tier; Tier-1 gated to human approval | In-Progress (MG-1, 2026-07-15: dual ratings + derived tier via the 2L `assign_model_tier` + `MODEL.TIER_ASSIGN`; the Tier-1 H-02 human-approval gate stays open) |
| REQ-MDG-003 | Validation workflow & effective challenge | 12.4/12.5 | Independent assurance | Developer≠validator workflow; approval status | `model_validation` (IA) | — | Independence (SOD-03) test | Author cannot validate; Tier-1 needs H-02 approval (BR-15) | Draft |

### CAP-13 Data Quality & Reconciliation (DQR)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-DQR-001 | DQ rules engine | 13.1 | Detect bad data early | Configurable DQ rules run on ingest | `data_quality_rule` (EV), `data_quality_result` (IA) | Rule eval | DQ-rule test | Rules run on load; exceptions raised, not silent | In-Progress (P1A-3 skeleton) |
| REQ-DQR-002 | Reconciliation | 13.2 | Agreement across sources | Reconcile positions/valuations across feeds | recon inputs | Recon calc | Recon test | Discrepancies surfaced with severity | Draft |
| REQ-DQR-003 | Manual overrides (maker-checker) | 13.4 | Controlled correction | Override with BR-7 fields + approval | `manual_override` (IA) | — | Override (BR-7) test | Override carries prior/new/justification/approval; audited | Draft |

### CAP-14 Data Lineage (LIN)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-LIN-001 | Lineage skeleton & capture | 14.1/14.2 | Trace every output to source | Lineage edges from source→run→result | `lineage_edge` (IA), `data_source` (EV) | — | Lineage-completeness test | Every governed output has a complete lineage path (BR-6/13) | In-Progress (P1A-1 skeleton) |
| REQ-LIN-002 | Lineage query & extract | 14.3 | Answer "where did this number come from" | Query/visualize lineage for a result/report | lineage edges | — | Lineage-query test | Given a result, the full upstream graph is returned | Draft |

### CAP-15 Auditability (AUD)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-AUD-001 | Audit coverage of governed actions | 15.1/15.4 | Complete, immutable trail | All governed writes emit taxonomy events (extends FW-AUD) | `audit_event` (IA) | — | Audit-coverage test | No governed write without an audit event (CTRL-012) | Draft |
| REQ-AUD-002 | Chain integrity & verification | 15.2 | Tamper evidence | Scheduled `verify_chain` + checkpoints | audit_event/checkpoint | Hash verify | Tamper-detection test | Chain break is detected & alertable (BR-18) | Draft |
| REQ-AUD-003 | Audit query & regulator extract | 15.3 | Investigations & DD | Entitled audit query + signed extract | audit_event | — | Extract test | Extract is entitled, complete, and reproducible | Draft |

### CAP-16 Reporting (RPT)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-RPT-001 | Risk reports (market/credit/liquidity) | 16.1 | Communicate risk | Generate governed, reproducible risk reports | approved results | — | Report-reproduction test | Report binds run IDs; regenerates identically (BR-9) | Draft |
| REQ-RPT-002 | Board risk report | 16.3 | Board-level oversight | Aggregate narrative from approved metrics | approved results | — | Board-report test | Publication is maker-checked (SOD-08); no unapproved data | Draft |
| REQ-RPT-003 | DQ / model-inventory / audit extracts | 16.4/16.5 | Control transparency | Generate control/DQ/inventory/audit reports | DQ, inventory, audit | — | Extract test | Extracts reproduce and are entitlement-scoped | Draft |

### CAP-17 Administration & Entitlements (ADM)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-ADM-001 | Real SSO / OIDC identity | 17.1 | Enterprise identity | Replace dev header shim with OIDC + MFA | users/principals | — | Auth integration test | Principal comes from OIDC; MFA enforced (AD-007) | Draft |
| REQ-ADM-002 | RBAC/ABAC entitlement administration | 17.2/17.3 | Manage access safely | Admin roles/permissions/grants; SoD/maker-checker | entitlement tables (EV) | — | SoD + maker-checker test | Entitlement changes are maker-checked & audited (BX-SOD) | Draft |
| REQ-ADM-003 | Data classification & export controls (MNPI) | 17.5 | Protect confidential/MNPI | DC tagging; DC-4 export blocked by default; barriers | classified data | — | Export-control + MNPI test | DC-4 export blocked; bulk export four-eyes; denials audited | Draft |
| REQ-ADM-004 | Admin console | 17.4 | Operate the platform | Entitled admin UI for users/config | admin entities | — | Admin-console test | All admin actions entitled and audited | Draft |

### CAP-18 Integration Readiness (INT)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-INT-001 | File upload (CSV/Excel) | 18.1 | Onboard data without integration | Validated, sandboxed upload via anti-corruption layer | staged files | — | Upload-validation + malicious-file test | Bad/malicious files rejected; lineage origin + audit recorded (P1A-4 skeleton is **CSV-only**, XLSX later; **canonical mapping deferred to P1B/P1C** — staged rows are generic JSON, not canonical data) | In-Progress (P1A-4) |
| REQ-INT-002 | API & SFTP adapters | 18.2/18.3 | Automated feeds | Inbound API/SFTP adapters to canonical model | feed payloads | — | Adapter-mapping test | Feeds map to canonical entities; audit + lineage on ingest | Draft |
| REQ-INT-003 | Vendor / accounting / GP-report adapters | 18.4/18.5 | Connect ecosystem | Adapter abstraction for vendors & GP reports | vendor feeds | — | Adapter-abstraction test | New vendor added via config; no structural change (ARCH-P-07) | Draft |

### CAP-19 BAU AI Agent Support (BAI)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-BAI-001 | DQ & private-asset monitoring agent | 19.1 | Scale data ops | Agent summarizes DQ exceptions; recommends remediation | DQ results (read-only) | — | Agent-logging test | Agent actions logged (BR-16); read-only tier; cites sources | Draft |
| REQ-BAI-002 | Breach triage & scenario commentary agents | 19.2/19.3 | Faster, clearer ops | Draft breach narratives / scenario commentary | approved results | — | Cite-don't-invent test | Agent cites governed metrics; no invented numbers; human approves action | Draft |
| REQ-BAI-003 | Model monitoring & board/evidence assistants | 19.4/19.5 | Governance & reporting support | Flag model drift; draft board/evidence packs | monitoring/approved data | — | Approval-gate test | Drafts only; publication needs human approval (BR-15/16) | Draft |

### CAP-20 Performance Measurement (PRF)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-PRF-001 | Portfolio return (time-weighted) | 20.1 | Measure the return a book actually earned, external cash flows neutralised (the prerequisite for ex-post benchmark-relative analytics, VaR backtesting, and private-asset returns) | Governed chain-linked TWR (Modified-Dietz within caller-supplied exposure-run valuation boundaries) as a run — a `DIETZ_PERIOD` series + a `TWR_LINKED` summary | exposure-run market values + `transaction` external flows (`TRANSFER_IN`/`TRANSFER_OUT`) + FX legs, all snapshot-pinned | Modified-Dietz + geometric linking (GIPS 2020); Decimal-50, `Numeric(20,12)` fraction | Hand golden + independent float cross-check + reproduction-under-correction (TR-09) | Return matches hand/independent reference within ε; re-run identical; a later exposure re-run OR a transaction append cannot move a historical return; method has methodology doc + inventory entry | **In-Progress (PM-1, 2026-07-09, migration `0031`):** `portfolio_return_result` (ENT-053) — time-weighted return v1 (`perf.return.twr`), single-portfolio book; gross-of-fees, unannualized. **Money-weighted/IRR (PA-0), net-of-fees, attribution, composites, annualization, and multi-portfolio/subtree books DEFERRED; captured-holdings book (no cash ledger) a first-class recorded limitation.** REQ does **NOT** close |
| REQ-PRF-002 | Ex-post benchmark-relative performance | 20.5 | Measure realized performance vs a benchmark, after the fact — active return, tracking difference, realized tracking error, information ratio (the UCITS ex-post disclosure figures + the skill measure) | Governed ex-post statistics as a run over ONE portfolio-return run + a captured `benchmark_return` series — an `ACTIVE_RETURN` series + `TRACKING_DIFFERENCE`/`TRACKING_ERROR`/`INFORMATION_RATIO` summaries | PM-1 `portfolio_return_result` rows + the in-span SIMPLE `benchmark_return` rows of the chosen `return_basis`, all snapshot-pinned | arithmetic active returns; geometric compounding; unbiased (n−1) sample TE; Grinold-Kahn IR; Decimal-50, `Numeric(20,12)`; unannualized | Hand golden + independent `statistics.stdev` cross-check + reproduction-under-correction (TR-09) | Metrics match hand/independent reference within ε; re-run identical; a later PM-1 re-run OR a benchmark vendor correction cannot move a historical result; method has methodology doc + inventory entry | **In-Progress (P3-8, 2026-07-10, migration `0032`):** `benchmark_relative_result` (ENT-054) — realized active return / TE / TD / IR v1 (`perf.benchmark_relative`); `benchmark_return`'s FIRST governed consumer; closes P3-7 OD-G; REUSES `perf.run`/`perf.view`. **Annualization, geometric-excess, active share, relative VaR, attribution, multi-benchmark, LOG return_type DEFERRED; the PM-1 captured-holdings-book bias PROPAGATES (first-class limitation); benchmark missing-day compounding hazard recorded (calendar validation deferred).** REQ does **NOT** close |

## 8. Open Questions

See [RTM §Open Questions](requirements_traceability_matrix.md) — consolidated there to avoid duplication.

## 9. Dependencies

All forward dependencies are registered in §6 and applied per requirement in the RTM. The backbone assumes only the foundation
described in §3.
