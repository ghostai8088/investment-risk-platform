# Regulatory & Product Scope (Initial Baseline)

## Document Control

| Field | Value |
|---|---|
| Document ID | PRODSTRAT-REGSCOPE-001 |
| Version | 0.1 (Draft Baseline) |
| Status | Accepted as initial baseline (regulatory detail to be confirmed by H-05) |
| Owner | H-07 Product Owner (with R-10 Compliance & Controls AI) |
| Approver | H-05 Head of Compliance (regulatory themes), H-07 Product Owner (scope) |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | capability_map.md, control_matrix_skeleton.md, model_governance_independence_policy.md, entitlement_sod_model.md |
| Supported Build Rules | BR-2, BR-3, BR-7, BR-9, BR-14, BR-15 |

## 1. Purpose

Bound "full-scope" by stating the **initial regulatory and product scope** so domain construction has a defined target,
while keeping the platform **regime-configurable**. This baseline is U.S.-first; other jurisdictions are future overlays, not
re-architecture. Regulatory specifics here are working themes to be confirmed by Compliance (H-05), not legal advice.

## 2. Initial Baseline: U.S. Asset Management

| ID | Scope statement |
|---|---|
| SCOPE-01 | Primary initial market: **U.S.-based asset managers** (SEC-registered investment advisers) expanding from public into private markets. |
| SCOPE-02 | Asset coverage: public (equity, fixed income, derivatives, FX, cash) and private (PE, private credit, direct loans, real estate, infrastructure) — both first-class. |
| SCOPE-03 | Risk coverage: market, credit, counterparty, liquidity, scenario/stress, limits/breach across both asset domains. |
| SCOPE-04 | Operating model: 1st Line (risk-taking) and 2nd Line (independent risk/oversight) workflows; 3rd Line (Internal Audit) read-only assurance. |
| SCOPE-05 | Deployment: multi-tenant SaaS with single-tenant option (AD-008, AD-010). |

## 3. Target Users / Personas (high level)

| Persona ID | Persona | Line | Primary needs |
|---|---|---|---|
| PERSONA-01 | Chief Risk Officer / Head of Risk | 2L | Risk appetite, board reporting, oversight |
| PERSONA-02 | Risk Manager / Risk Analyst | 2L/1L | Run analytics, monitor limits, review breaches |
| PERSONA-03 | Portfolio Manager | 1L | Exposure/risk in scope, breach response |
| PERSONA-04 | Model Validator (independent) | 2L | Validate models, effective challenge |
| PERSONA-05 | Data Steward | — | Data quality, reconciliation, overrides |
| PERSONA-06 | Compliance Officer | 2L | Controls, MNPI/restricted lists, regulatory themes |
| PERSONA-07 | Internal Auditor | 3L | Independent assurance, audit extracts |
| PERSONA-08 | Platform Administrator | — | Users, entitlements, configuration |
| PERSONA-09 | Board / Investment Committee (consumer) | — | Governed summary reporting |
| PERSONA-10 | Buyer/Operations (COO/CTO) | — | Security, due diligence, deployment fit |

Initial buyer profile: **mid-sized asset managers** building institutional risk/governance capability as they enter private
markets and face enterprise/institutional-client due diligence.

## 4. Initial Regulatory / Governance Themes (U.S.)

Themes drive requirements and controls; they are **configurable overlays**, not hardcoded logic. To be confirmed with H-05.

| ID | Theme | Relevance to platform |
|---|---|---|
| REG-US-01 | SEC Investment Advisers Act — compliance program (Rule 206(4)-7) | Controls, evidence, oversight workflows |
| REG-US-02 | Books & records / recordkeeping (Rule 204-2) | Retention, audit trail, reproducibility (BR-9, temporal standard) |
| REG-US-03 | Form PF / private fund reporting | Private-markets data model, scenario/liquidity reporting inputs |
| REG-US-04 | '40 Act liquidity risk management (Rule 22e-4) where applicable | Liquidity classification & redemption stress capabilities |
| REG-US-05 | Marketing Rule / performance presentation | Report governance, reproducibility, disclaimers (BR-14) |
| REG-US-06 | Fiduciary duty / best execution context | Traceability, model governance, transparency |
| REG-US-07 | Model risk governance — SR 11-7 (banking guidance adopted as best practice) | Model independence policy, tiering, validation |
| REG-US-08 | Enterprise trust frameworks — SOC 2, ISO 27001, NIST CSF | Security, audit, entitlement, evidence packs |
| REG-US-09 | Derivatives/counterparty context — Dodd-Frank, UMR (where relevant) | Counterparty exposure, collateral, netting capabilities |

## 5. Future Jurisdictional Overlays (not initial scope)

| ID | Overlay | Adds |
|---|---|---|
| REG-FUT-01 | UK — FCA, PRA SS1/23 (model risk), Consumer Duty | UK model-risk and conduct overlays |
| REG-FUT-02 | EU — AIFMD, UCITS, MiFID II, SFDR, ESMA stress-testing guidelines | EU fund/conduct/ESG and stress overlays |
| REG-FUT-03 | Basel-aligned counterparty (SA-CCR) for bank-affiliated clients | Standardised counterparty methodology overlay |
| REG-FUT-04 | Insurance clients — Solvency II | Capital/risk overlays |
| REG-FUT-05 | APAC — MAS and peers | Regional reporting/retention overlays |

## 6. Regime-Configurable by Design

| ID | Principle |
|---|---|
| RCD-01 | Capabilities are **regime-agnostic**; regulatory specifics are expressed as configuration: reporting templates, limit definitions, retention periods, calculation parameters, and disclosure text. |
| RCD-02 | Adding a jurisdiction is an **overlay configuration + content** exercise, not a structural change (ARCH-P-07). |
| RCD-03 | Retention, data-residency, and classification rules are parameterized per tenant/jurisdiction (links temporal & entitlement standards). |
| RCD-04 | Each governed report/methodology declares the regime themes it satisfies (traceable to the control matrix). |

## 7. Open Decisions

| ID | Open Decision |
|---|---|
| OD-037 | Confirm authoritative U.S. regulatory theme list and applicability with H-05 (which apply to which client types). |
| OD-039 | Confirm which client segments are in initial commercial scope (RIA vs private fund adviser vs both). |
| OD-040 | Confirm retention periods by record type and jurisdiction (feeds TR-19, AUD-03). |
| OD-041 | Confirm first overlay to be built after U.S. baseline (likely UK or EU). |

## 8. Dependencies

- capability_map.md (capabilities the themes map onto; CAP IDs pending — OD-036).
- control_matrix_skeleton.md (regulatory mapping layer — OD-037).
- temporal_reproducibility_standard.md, entitlement_sod_model.md (retention, classification, residency).
