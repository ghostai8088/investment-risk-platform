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
| **CAP-2 Security Master & Reference Data** | 2.1 Instrument master · 2.2 Issuer/Counterparty entities + hierarchy · 2.3 Identifier cross-reference · 2.4 Corporate actions · 2.5 Calendars/currencies/rating scales |
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
| REQ-PPM-001 | Portfolio/fund/strategy hierarchy | 1.1 | Organize holdings for aggregation & entitlement scope | CRUD + versioned hierarchy nodes; entitlement scope anchor | `portfolio/fund/strategy` (EV) | — | Hierarchy build + scope test | A node tree persists, is tenant-scoped, and drives entitlement scoping | Draft |
| REQ-PPM-002 | Position master (as-of) | 1.2 | Single source of holdings for all risk | Positions keyed to instrument + portfolio, bitemporal | `position` (FR) → CAP-2 instruments | — | As-of reconstruction test | A position is reconstructable for any past as-of date | Draft |
| REQ-PPM-003 | Transaction & valuation history | 1.3/1.4 | Provenance of holdings and value | Append-only transactions; valuation history | `transaction` (IA), `valuation` (FR) | — | Append-only + history test | Transactions immutable; valuations queryable as-of | Draft |
| REQ-PPM-004 | Exposure aggregation | 1.5 | Roll up exposures across hierarchy | Run-tracked aggregation over scope | derived from positions/valuations | Aggregation (QS-21) | Aggregation benchmark | Aggregates reproduce within tolerance and bind lineage | Draft |

### CAP-2 Security Master & Reference Data (SMR)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-SMR-001 | Instrument master | 2.1 | Canonical instrument terms for pricing/risk | CRUD instruments with effective-dated terms | `instrument` (FR terms) | — | Effective-dating test | Instrument terms reconstructable as-of; classified per DC | Draft |
| REQ-SMR-002 | Issuer/counterparty entities + hierarchy | 2.2 | Aggregate credit/counterparty exposure | Entities with LEI + parent hierarchy | `issuer`, `counterparty` (EV) | — | Hierarchy rollup test | Exposure rolls to ultimate parent | Draft |
| REQ-SMR-003 | Identifier cross-reference | 2.3 | Resolve vendor/standard identifiers | Xref ISIN/CUSIP/SEDOL/FIGI/internal | `identifier_xref` (EV) | — | Resolution + precedence test | Any known identifier resolves to one instrument | Draft |
| REQ-SMR-004 | Corporate actions & calendars | 2.4/2.5 | Correct economics over time | Effective-dated corporate actions; market calendars | `corporate_action`, `calendar` (EV) | Day-count/roll (QS-10/11) | Calendar/roll test | Actions apply on effective date; calendars drive rolls | Draft |

### CAP-3 Public Asset Data (PUB)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-PUB-001 | Market prices (time-series) | 3.1 | Inputs for valuation & risk | Bitemporal price points per instrument/source | `price_point` (FR) | — | As-of + staleness test | Price reconstructable as-of; stale flagged (QS-16) | Draft |
| REQ-PUB-002 | Curves & volatility surfaces | 3.2/3.3 | Discounting & options risk | Versioned curves/surfaces with interpolation method | `yield_curve`, `volatility_surface` (FR) | Interpolation (QS-13) | Interpolation test | Curve/surface values reproduce; method declared | Draft |
| REQ-PUB-003 | Credit spreads, ratings, benchmarks | 3.4/3.5 | Credit & relative risk inputs | Spread series, ratings, benchmark constituents | `credit_spread`, `rating`, `benchmark` (FR/EV) | — | Coverage test | Inputs present & as-of for the risk engine | Draft |

### CAP-4 Private Asset Data (PRV)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-PRV-001 | Commitments & funded/unfunded | 4.1 | Track private exposure & dry powder | Commitment records with funded/unfunded | `commitment` (FR) | — | Funded/unfunded test | Unfunded exposure computed and aggregated | Draft |
| REQ-PRV-002 | Capital calls & distributions | 4.2 | Cashflow & liquidity inputs | Append-only call/distribution events | `capital_call`, `distribution` (IA) | — | Cashflow test | Events immutable; feed liquidity forecast | Draft |
| REQ-PRV-003 | GP NAV / appraisals + stale flags | 4.3/4.5 | Valuation of illiquid assets | NAV/appraisal with valuation date + staleness | `gp_report`, `appraisal` (FR) | Staleness (QS-16) | Stale-valuation test | Stale NAV flagged; proxy mapping recorded | Draft |
| REQ-PRV-004 | Private company financials (MNPI) | 4.4 | Fundamental private credit/equity input | Restricted (DC-4) financials behind barriers | `private_company_financials` (FR) | — | MNPI access-denied test | DC-4 access requires need-to-know grant; denials audited | Draft |

### CAP-5 Market Risk (MKT)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-MKT-001 | Value at Risk / Expected Shortfall | 5.1 | Quantify tail loss for limits & board | Pluggable VaR/ES (parametric/historical/MC) as run | positions+market (FR) snapshot | Deterministic, seeded MC (QS-18) | Benchmark VaR within ε; reproduction test | VaR matches reference within ε; re-run identical; method has methodology doc + inventory entry | Draft |
| REQ-MKT-002 | Sensitivities | 5.2 | Risk decomposition & hedging | Duration/convexity/greeks/spread duration | positions+market (FR) | Analytic/bump (QS) | Sensitivity benchmark | Greeks reproduce within ε; conventions declared | Draft |
| REQ-MKT-003 | Factor exposure & contribution | 5.3 | Attribute risk to factors | Factor model exposures & contributions | factor returns (FR) | Factor calc | Attribution test | Contributions sum to total within ε | Draft |
| REQ-MKT-004 | Market stress | 5.5 | Loss under defined shocks | Apply shock set to portfolio | scenario defs (CAP-9) | Revaluation | Stress benchmark | Stress P&L reproduces; binds scenario version | Draft |

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
| REQ-MDG-002 | Tiering | 12.3 | Proportionate governance | Assign Tier 1/2/3 by criteria | model metadata | — | Tiering test | Each model has a tier; Tier-1 gated to human approval | Draft |
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
| REQ-INT-001 | File upload (CSV/Excel) | 18.1 | Onboard data without integration | Validated, sandboxed upload via anti-corruption layer | staged files | — | Upload-validation + malicious-file test | Bad/malicious files rejected; canonical mapping + lineage recorded | Draft |
| REQ-INT-002 | API & SFTP adapters | 18.2/18.3 | Automated feeds | Inbound API/SFTP adapters to canonical model | feed payloads | — | Adapter-mapping test | Feeds map to canonical entities; audit + lineage on ingest | Draft |
| REQ-INT-003 | Vendor / accounting / GP-report adapters | 18.4/18.5 | Connect ecosystem | Adapter abstraction for vendors & GP reports | vendor feeds | — | Adapter-abstraction test | New vendor added via config; no structural change (ARCH-P-07) | Draft |

### CAP-19 BAU AI Agent Support (BAI)

| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test | Acceptance | Status |
|---|---|---|---|---|---|---|---|---|---|
| REQ-BAI-001 | DQ & private-asset monitoring agent | 19.1 | Scale data ops | Agent summarizes DQ exceptions; recommends remediation | DQ results (read-only) | — | Agent-logging test | Agent actions logged (BR-16); read-only tier; cites sources | Draft |
| REQ-BAI-002 | Breach triage & scenario commentary agents | 19.2/19.3 | Faster, clearer ops | Draft breach narratives / scenario commentary | approved results | — | Cite-don't-invent test | Agent cites governed metrics; no invented numbers; human approves action | Draft |
| REQ-BAI-003 | Model monitoring & board/evidence assistants | 19.4/19.5 | Governance & reporting support | Flag model drift; draft board/evidence packs | monitoring/approved data | — | Approval-gate test | Drafts only; publication needs human approval (BR-15/16) | Draft |

## 8. Open Questions

See [RTM §Open Questions](requirements_traceability_matrix.md) — consolidated there to avoid duplication.

## 9. Dependencies

All forward dependencies are registered in §6 and applied per requirement in the RTM. The backbone assumes only the foundation
described in §3.
