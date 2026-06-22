# Model Governance & Independence Policy

## Document Control

| Field | Value |
|---|---|
| Document ID | MODELGOV-INDEP-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-08 Model Governance AI |
| Approver | H-02 Head of Model Risk |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | reconciled_agent_role_registry.md, numerical_quant_standards.md, temporal_reproducibility_standard.md, audit_event_taxonomy.md, control_matrix_skeleton.md |
| Supported Build Rules | BR-2, BR-3, BR-6, BR-9, BR-15, BR-16 |

## 1. Purpose & Alignment

Establish model risk governance consistent with recognized standards (e.g., US SR 11-7, UK PRA SS1/23) for the platform's
calculations and embedded AI. It defines what a model is, tiering, the independence boundary (including AI), the validation
lifecycle, and approval authority. This operationalizes BR-3 (inventory), BR-15 (human approval for Tier-1), and BR-16 (agent
logging).

## 2. Definition of a Model (MG)

| ID | Rule |
|---|---|
| MG-01 | A **model** is any quantitative method that processes inputs into estimates used for risk, valuation, limits, scenarios, or reporting (incl. statistical, analytical, and AI/ML methods). |
| MG-02 | Every model and version is registered in the inventory (`model`, `model_version`, ENT-035) before use (BR-3); unregistered calculations may not feed governed outputs. **Realized at skeleton in P1A-2** (`register_model`/`register_model_version` + `assert_registered_model_version` inventory-before-use gate; assumptions/limitations ENT-036); MG-04/05/06/07 validation/approval **enforcement** is P7 (REQ-MDG-002/003) — P1A-2 records owner/developer/tier/validation_status as non-enforcing fields only. |
| MG-03 | Embedded product AI features that produce risk-relevant outputs are in scope as models or model-adjacent tools and are inventoried. |

## 3. Model Risk Tiering (MG)

| Tier | Criteria | Governance intensity |
|---|---|---|
| Tier 1 | High materiality / regulatory / board-facing / high complexity | Full independent validation; **human (H-02) approval required (BR-15)**; periodic revalidation |
| Tier 2 | Moderate materiality/complexity | Independent review; H-02 or delegate approval; scheduled revalidation |
| Tier 3 | Low materiality / simple / supporting | Lightweight review; documented; monitored |

Tiering criteria (materiality thresholds, regulatory flags) are recorded per model and are themselves reviewable.

## 4. Independence Boundary (MG)

| ID | Rule |
|---|---|
| MG-04 | **Developer ≠ validator.** The party (human or AI) that develops/drafts a methodology must not validate or approve it (SOD-03). |
| MG-05 | The Quant/Risk Methodology Agent (AG-06/R-06) may draft methodology, assumptions, limitations, and benchmark tests, and may perform *self-test*, but **may not perform independent validation** of its own output. |
| MG-06 | Independent validation is conducted under R-08/ROLE-MV by a party not involved in development, with H-02 sign-off for Tier 1. |
| MG-07 | **AI is never the sole approver** for Tier-1 models; AI validation findings inform, but do not substitute for, the human approval gate (BR-15). |
| MG-08 | All material model-governance agent actions are logged (`MODEL.*`, `AGENT.*`) with model/version and approver (BR-16). |

## 5. Validation Lifecycle (MG)

Validation covers, proportionate to tier:

1. **Conceptual soundness** — theory, assumptions, limitations (BR-2).
2. **Data quality & relevance** — inputs, lineage, proxies.
3. **Implementation testing** — code correctness vs methodology; numerical standards (QS) adherence.
4. **Benchmarking** — independent reproduction / challenger comparison using benchmark portfolios (BR-1).
5. **Outcomes analysis / back-testing** — where applicable.
6. **Reproducibility** — confirm run-binding and as-of reproduction (TR-13).
7. **Limitations & restricted-use** — documented; restricted-use status recorded.

Effective-challenge evidence (questions raised, challenger results, resolutions) is captured per validation (`model_validation`,
ENT-037).

## 6. Lifecycle & Change Management (MG)

| ID | Rule |
|---|---|
| MG-09 | Re-validation is triggered by: methodology/code change, material data/source change, performance/monitoring breach, scope change, or periodic schedule by tier. |
| MG-10 | Each new `model_version` re-enters the validation workflow proportionate to the change and tier. |
| MG-11 | Approval, restricted-use, and retirement are recorded as audited events (`MODEL.APPROVE`, `.RESTRICT`, `.RETIRE`). |
| MG-12 | A model failing validation may be granted time-limited **restricted use** only with H-02 approval and documented conditions/limitations. |

## 7. Ongoing Monitoring (MG)

| ID | Rule |
|---|---|
| MG-13 | Tier-1/2 models have defined monitoring metrics and thresholds; breaches raise validation alerts (Model Performance Monitoring Agent AG-17). |
| MG-14 | Overdue validations are flagged on the validation dashboard; H-02 owns disposition. |

## 8. Open Decisions

| ID | Open Decision |
|---|---|
| OD-032 | Ratify tiering thresholds (materiality/regulatory criteria) with H-02/H-01. |
| OD-033 | Confirm periodic revalidation cadence per tier. |
| OD-034 | Confirm treatment of embedded AI/LLM features under tiering (MG-03) and any provider-model validation expectations. |
| OD-035 | Confirm minimum independent-validation staffing/sourcing at small scale while preserving MG-04. |

## 9. Dependencies

- reconciled_agent_role_registry.md (R-06/R-08, H-02, SOD-03 independence).
- numerical_quant_standards.md (QS adherence in validation step 3).
- temporal_reproducibility_standard.md (reproducibility step 6).
- audit_event_taxonomy.md (`MODEL.*`, `AGENT.*`).
- entitlement_sod_model.md (ROLE-MV, SOD-03).
