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

Establish model risk governance consistent with recognized standards (e.g., US SR 11-7 — superseded 2026-04-17 by SR 26-2;
UK PRA SS1/23) for the platform's calculations and embedded AI. It defines what a model is, tiering, the independence boundary
(including AI), the validation lifecycle, and approval authority. This operationalizes BR-3 (inventory), BR-15 (human approval
for Tier-1), and BR-16 (agent logging).

> **VW-1 realization note (2026-07-14, migration `0039`; ENT-037):** the validation LIFECYCLE and INDEPENDENCE boundary are
> now partially executable. A `model_validation` record (outcome ∈ {APPROVED, APPROVED_WITH_CONDITIONS, REJECTED}, type ∈
> {INITIAL, PERIODIC, TRIGGERED}, findings, evidence incl. cited governed runs) is captured at `model_version` grain; a
> latest-outcome REJECTED refuses new governed runs (CTRL-022). **MG-04 (dev≠validator) is enforced at the ROLE level** — the
> `model.validate` write is 2L-only (`risk_manager_2l`), withheld from the `risk_analyst_1l` register-holder — but NOT yet at
> the data level (the registry stamps no per-version developer identity; a same-person author-then-validate is not
> code-blocked). **MG-07 (AI never sole approver)** is honored fail-safe: validation is **human-only in v1** (no tier exists,
> so every model is potentially Tier-1). **MG-13/14 ongoing monitoring:** each non-REJECTED record carries a
> validator-declared `next_review_due` + an `overdue` read flag; **OD-033 (periodic revalidation CADENCE per tier) stays
> OPEN** — cadence is validator-declared until tiering (REQ-MDG-002) ships. The Tier-1 H-02 **approval** step and
> `MODEL.APPROVE`/`.RESTRICT`/`.RETIRE` remain reserved (later slices).

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

> **MG-1 realization (RATIFIED 2026-07-15 — the MG-1 ratification CLOSES OD-032 + OD-033):** tiering is now executable
> (NO migration). Each `model` head is assigned a **materiality rating** ∈ {HIGH, MEDIUM, LOW} — labeled per **SR 26-2**,
> where materiality = model purpose together with model exposure ONLY (complexity is deliberately NOT folded in; a
> composite labeled "SR 26-2 materiality" would repeat the F3 citation-class defect) — and a **complexity rating** ∈
> {HIGH, MEDIUM, LOW} (SS1/23 P1.3(c) / SR 26-2 *inherent risk*), from which the **tier** ∈ {TIER_1, TIER_2, TIER_3} is
> DERIVED (SS1/23 P1.3(a): a "risk-based materiality and complexity rating"). The derivation matrix is **HOUSE POLICY,
> stated as such** (no external text prescribes a matrix):
>
> | Derived tier | Rule (HOUSE POLICY) |
> |---|---|
> | TIER_1 | materiality HIGH |
> | TIER_2 | materiality MEDIUM, or materiality LOW with complexity HIGH (complexity escalates one step, never de-escalates) |
> | TIER_3 | the rest |
>
> Assignment is a **2L act** — `assign_model_tier`, gated on `model.validate`, audited as `MODEL.TIER_ASSIGN` with the
> two ratings + a required rationale in the payload (their durable home); the 1L register-time tier write is CLOSED
> (OD-MG-1-B/C — HOUSE POLICY motivated by the SOD fact: the 1L author must not set the materiality that scales
> scrutiny of his own model; SS1/23 P1.3(e) anchors only the independent-reassessment-at-validation hook).
>
> **Revalidation cadence (OD-033 CLOSED):** tier-bounded MAXIMA, enforced at `record_validation` write time as a
> CEILING on an approving outcome's `next_review_due` — a ceiling, not a schedule (SR 26-2's posture: frequency varies
> by purpose, methodology, and change-rate; the validator declares any date within the bound):
>
> | Tier | Max review interval | Sourcing (honest labels) |
> |---|---|---|
> | TIER_1 | 365 days | Anchored on **ECB EGIM market-risk §4.2 ¶90** ("at least annually" — the model class our flagship belongs to) + **SS1/23 P4.5(b)** (frequency "consistent with the model tier"). Adopted **VOLUNTARILY** — we are outside every cited text's scope. |
> | TIER_2 | 730 days | **HOUSE POLICY** — NO citable source anywhere prescribes a multi-year tier cadence (SR 26-2 dropped SR 11-7's "at least annually" without replacement; SS1/23 and OSFI E-23 give no numbers). |
> | TIER_3 | 1095 days | **HOUSE POLICY** (the same decisive negative fact). |
>
> An UNTIERED model gets the TIER_1 bound — the direct continuation of VW-1's ratified fail-safe ("while NO model
> carries a tier, every model is potentially Tier-1").

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

## 5A. Use Before Validation — the Exception Regime (ADDED at MG-1, 2026-07-15)

This section is NEW at MG-1 (no use-before-validation section existed before it — verified). It records the ratified
per-model, time-boxed EXCEPTION regime (OD-MG-1-E/F) and the two disclosures the MG-1 record carries (its Part 3).

| ID | Rule |
|---|---|
| MG-15 | A model version may be used before validation only under a **per-version, time-boxed EXCEPTION**: a `model_validation` row with `validation_type = "EXCEPTION"`, outcome `APPROVED_WITH_CONDITIONS` (mandatory — the conditions ARE the **SR 26-2 §V** exception elements: the urgent-need/POC justification, limits on use, closer monitoring, greater attention to limitations, stakeholder notice), and `next_review_due` = the **expiry**. Time-boxing ("temporary") is anchored on **SS1/23 P5.3(a)(i)** — SR 26-2 never says time-boxed — and the grant is an act of the MRM control function per **SS1/23 §2.13** (the 2L files it). **The third P5.3(a)(i) limb — post-model adjustments (PMAs) — is explicitly NOT adopted**: the platform has no PMA/overlay machinery of any kind; exception records disclose the limb as not-implemented rather than silently dropping it. |
| MG-16 | An EXCEPTION can never SUBSTITUTE for validation — ONE fail-closed write guard: it may only be filed for a version with **NO prior non-EXCEPTION validation rows** (a validated model revalidates, never excepts — and since a REJECTED row IS a non-EXCEPTION row, the rejection gate cannot be laundered either; the originally-drafted second guard was provably unreachable and was removed as dead code, MG-1 Part 6.1 — corrected at the Wave-6 close). **An EXPIRED exception refuses new governed runs** (OD-MG-1-F: `ExpiredModelExceptionError` → 422 at the bind seam, mapped at every run endpoint). Versions with no validation rows at all keep binding (the disclosed default posture — filing an exception is what arms its own expiry); overdue PERIODIC revalidation stays display-only (the deliberate, recorded asymmetry — MG-2 candidate). |
| MG-17 | **Renewal semantics, disclosed:** an expired exception is curable by a FRESH exception — each renewal a separate, recorded, audited human 2L act — but **the renewal count is UNBOUNDED** (a TIER_3 exception is "temporary" for up to 1095 days per grant). Recorded as a limitation; a renewal bound is a named MG-2 candidate. Expiry discipline rests on the audited re-grant ceremony, not on arithmetic. |
| MG-18 | **The disclosed POC posture:** outside the demo-campaign tenant, the blanket use-before-validation default survives (every test tenant registers and binds models with no validation rows — unchanged by design, or the whole test corpus breaks). This is disclosed as a **proportionality-anchored POC posture** (SR 26-2: the guidance "does not set forth enforceable standards", is most relevant to organizations over $30 billion in total assets, and permits tailoring "with a level of rigor commensurate with that risk" — we are outside every cited text's scope and adopt voluntarily), NOT presented as the per-model regime. The demo tenant demonstrates the full regime: every registered model there is either validated or under a recorded, expiring exception. |
| MG-19 | **Person-level independence disclosure:** role-level SOD-03 holds (the 2L validator principal holds `model.validate` only; no non-admin role holds both register and validate), but at POC scale ONE human wears both 1L-adjacent and 2L hats — person-level independence does not exist and is disclosed in every campaign record. The honest tension is named, not dodged: SR 26-2's effective-challenge definition requires "sufficient independence to maintain objectivity" — cited beside its rigor-over-structure sentence ("the rigor and effectiveness of the review rather than … organizational structure"), never only the friendly half; SS1/23 P4.1(d) (separate reporting lines) is cited as **not-applicable-by-scope**, never as satisfied. |

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
| OD-032 | **CLOSED (MG-1 ratification, 2026-07-15 — OQ-MG-1-1/3):** tiering thresholds ratified — dual ratings (materiality per SR 26-2, complexity per SS1/23 P1.3(c)/SR 26-2 inherent risk) with the tier DERIVED by the HOUSE-POLICY matrix recorded in §3; assignment is the audited 2L `assign_model_tier` act (`MODEL.TIER_ASSIGN`). *(Was: Ratify tiering thresholds (materiality/regulatory criteria) with H-02/H-01.)* |
| OD-033 | **CLOSED (MG-1 ratification, 2026-07-15 — OQ-MG-1-3):** cadence = tier-bounded MAXIMA {365 / 730 / 1095 days} on `next_review_due`, enforced at `record_validation` write time; TIER_1 anchored on ECB EGIM MR §4.2 ¶90 + SS1/23 P4.5(b) (adopted voluntarily); TIER_2/3 **explicitly HOUSE POLICY** (no citable multi-year source exists); untiered ⇒ the TIER_1 bound (§3). *(Was: Confirm periodic revalidation cadence per tier.)* |
| OD-034 | Confirm treatment of embedded AI/LLM features under tiering (MG-03) and any provider-model validation expectations. |
| OD-035 | Confirm minimum independent-validation staffing/sourcing at small scale while preserving MG-04. |

## 9. Dependencies

- reconciled_agent_role_registry.md (R-06/R-08, H-02, SOD-03 independence).
- numerical_quant_standards.md (QS adherence in validation step 3).
- temporal_reproducibility_standard.md (reproducibility step 6).
- audit_event_taxonomy.md (`MODEL.*`, `AGENT.*`).
- entitlement_sod_model.md (ROLE-MV, SOD-03).
