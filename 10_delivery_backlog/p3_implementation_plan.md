# P3 Implementation Plan — Market-Risk / Factor Analytics

## Document Control

| Field | Value |
|---|---|
| Purpose | The P3 build roadmap: a **governance-first, reproducibility-first** subphase structure (P3-1…P3-7) that lands the risk methodology + model-governance contract **proven by the lowest-dependency reproducible number (analytic sensitivities)**, then the factor / covariance / VaR / stress / benchmark-relative analytics. Companion to `p3_0_decision_record.md` (OD-P3-0-A…N). |
| Status | **Implementation PLAN — PLANNING ONLY (historical).** P3-1…P3-5 + the inserted P3-C1 hardening slice and FE-1 UI slice are DELIVERED (see `docs/project_memory/build_plan.md`); the remaining legs (P3-6 stress, P3-7 benchmark-relative, further VaR methods) are sequenced by **`delivery_roadmap.md`** (Wave 1), which supersedes this document's ordering. |
| HEAD at writing | `6663452`; migration head `0021_benchmark`; origin/main clean. The full P2 captured market-data / reproducibility foundation (P2-1…P2-6) is committed + CI-green. |
| Predecessors | `p3_0_decision_record.md`; `p2_closeout_p3_readiness.md` (the readiness assessment); `p2_implementation_plan.md` (the per-subphase template + the reproducibility-first precedent); the `exposure_aggregate` (P2-3) governed-derived-number realization. |
| Review | 8-lens UltraCode review — **Part 7**. |

> **What P3 is — and is NOT.** P3 **computes governed risk/factor numbers** over the P2-captured inputs, each bound to a `dataset_snapshot` + a `calculation_run` + (where a model applies) a registered `model_version` with a methodology doc + assumptions/limitations, written as IA append-only result rows, reproducible under input correction. It builds the analytics the captured-data foundation enables: sensitivities → factor inputs → factor exposures → covariance → VaR/ES → (stress) → benchmark-relative. **This plan builds NOTHING** — it is the roadmap; each subphase is its own planned, separately-approved slice. **NO risk/factor/covariance/VaR/ES/stress/scenario implementation; NO model-validation-workflow; NO API/migration/test/frontend; NO `audit/service.py` change; NO BYPASSRLS; NO weakening of the P2 snapshot/run controls.**

---

## Part 1 — Subphase map

| Subphase | Title | First number? | Governing REQ | New canonical id? | Key input(s) | Captured-data gate |
|---|---|---|---|---|---|---|
| **P3-1** | Risk methodology + model-governance hardening **+ analytic sensitivities** | ✅ analytic sensitivities | REQ-MKT-002 | ENT-028 `sensitivity` (realize) | captured `curve`/`curve_point` + positions | none (uses shipped curves) |
| **P3-2** | Factor universe / factor-return inputs | — (inputs) | REQ-MKT-003 | ENT-025 `factor_return` (realize) | captured prices/benchmarks + history | adjusted/total-return prices (if price-derived) |
| **P3-3** | Factor-exposure engine | ✅ factor exposures | REQ-MKT-003 | factor_exposure (mint if net-new) | factor returns + positions | P3-2 inputs |
| **P3-4** | Covariance / volatility estimation | ✅ covariance | (supports REQ-MKT-001) | **covariance_matrix (mint)** | factor/asset returns + history | history depth (Part 4) |
| **P3-5** | VaR / Expected Shortfall | ✅ VaR/ES | REQ-MKT-001 | ENT-027 `risk_result` (realize) | covariance + positions + market | P3-4 + history |
| **P3-6** | Stress / scenario analytics | ✅ stress P&L | REQ-MKT-004 (**RTM-P5**) | ENT-029 `scenario_definition` + ENT-030 `scenario_result` (realize) | scenario defs + revaluation | revaluation; **conditional/late** |
| **P3-7** | Benchmark-relative analytics | ✅ active risk / TE | (relative risk) | risk result (active) | captured benchmark membership + a risk model | benchmark levels/returns (if return-based) |

**Sequencing note (OD-P3-0-A/B):** the numbering is a **recommendation, not a strict chain**. Analytic sensitivities (P3-1) is the **first computed number** because it needs no new captured input; the factor substrate (P3-2/3) and covariance (P3-4) may proceed in parallel once their inputs exist. **VaR/ES (P3-5) is gated on P3-4 + history; stress (P3-6) is RTM-P5 (the most-deferred, possibly a later phase).** The P3-0 decision record fixes the order.

---

## Part 2 — Subphase definitions (the per-slice contract template; each is its own approved plan)

Each subphase, when planned, fills the standard fields: **(1) Requirements included · (2) Requirements excluded · (3) Entities/modules · (4) Temporal classification · (5) APIs · (6) Audit events · (7) Entitlements · (8) RLS behavior · (9) Lineage behavior · (10) Data-quality behavior · (11) Model-governance behavior · (12) `calculation_run` / `dataset_snapshot` binding · (13) Tests · (14) Acceptance criteria · (15) Risks · (16) Open questions.** The sketches below set the readiness-level contract.

### P3-1 — Risk methodology + model-governance hardening + analytic sensitivities  *(the FIRST risk slice; the contract-proving number)*
- **Included:** the **methodology-doc framework** (`05_analytics_methodologies/` + the §-template, OD-P3-0-C); the **model_version-for-risk contract** (registry-required via `assert_registered_model_version`; `methodology_ref` mandatory; `validation_status` non-enforcing); the **`RISK.*` (EVT-220) reservation + `risk.view`/`risk.run` mint** (R-07); **`COMPONENT_KIND_CURVE`** minted + `build_snapshot` extended; and the **first analytic sensitivities** (duration / DV01 / spread-duration) over captured `curve`/`curve_point` + positions, REQ-MKT-002.
- **Excluded:** factor/covariance/VaR/ES/stress; options/vega (no vol surface); the enforced validation workflow (P7); any non-curve input pin beyond what sensitivities need.
- **Entities/modules:** realize **ENT-028 `sensitivity`** (IA TRUE append-only, run-bound + snapshot-gated); a new `irp_shared/risk/` package + `api/risk.py`; the sensitivity binder reuses the P2-3 governed-run + snapshot-pin + lineage pattern verbatim.
- **Temporal:** sensitivity = **IA TRUE append-only** (OD-P3-0-M). `scenario_definition`/`covariance` N/A here.
- **Audit:** reuse `CALC.RUN_CREATE`/`CALC.RUN_STATUS_CHANGE` for the run; activate the reserved `RISK.*` only if a risk-specific signal is needed (default: none — results run-tracked + lineaged). `MODEL.REGISTER`/`MODEL.VERSION` for the sensitivity model_version. `audit/service.py` FROZEN.
- **Entitlements:** mint `risk.view` + `risk.run` (R-07; auditor_3l in `.view`).
- **RLS:** symmetric tenant-scoped (FORCE) on the sensitivity table; NEVER hybrid; closed hybrid set unchanged.
- **Lineage:** `dataset_snapshot --DEPENDS_ON--> calculation_run --ORIGIN--> sensitivity` (the P2-3 shape; `run_id` stamped).
- **DQ:** fail-closed gates before any write (snapshot completeness + curve-present + cross-tenant); Protocol untouched.
- **Model governance:** a registered `sensitivity` `model_version` with a methodology doc declaring the conventions (bump, day-count, compounding, curve) + assumptions + limitations; `assert_registered_model_version` enforced.
- **run/snapshot binding:** a sensitivity result binds `input_snapshot_id` (a curve+positions snapshot) + `run_id`; `code_version` + `environment_id` + `model_version_id` set.
- **Tests:** reproducibility (re-run over the same snapshot is identical); convention-declared; snapshot-pinned (no live read); IA append-only (P0001); RLS (PG forced); entitlement parity; lineage; scope fences (no VaR/factor/covariance symbol; no vol-surface).
- **Acceptance:** analytic sensitivities reproduce within ε; conventions declared (REQ-MKT-002 partial); the methodology framework + model-gov contract + `RISK.*`/`risk.*` reservations are proven end-to-end. **REQ-MKT-002 → In-Progress (partial).**
- **Risks / open questions:** scope creep into VaR/factor; the model-vs-code_version boundary (settled OD-P3-0-E); which sensitivities v1 (rates DV01 + credit spread-duration recommended).

### P3-2 — Factor universe / factor-return inputs
- **Included:** a captured/derived **factor-return** input substrate (REQ-MKT-003 input leg); **Excluded:** factor *exposures*; risk numbers.
- **Entities:** realize **ENT-025 `factor_return`** (IA if derived-as-run-output, FR if a captured vendor series — decided in-slice, OD-P3-0-M); **Captured-data gate:** if price-derived, an **adjusted/total-return price series** is a prerequisite captured-data slice (P2-4 is RAW). **History** becomes load-bearing (Part 4). Audit/RLS/lineage/DQ per the captured-or-derived pattern.

### P3-3 — Factor-exposure engine
- **Included:** factor exposures of positions (REQ-MKT-003 — contributions sum to total within ε); **Entities:** factor_exposure (ENT-028 family or a **net-new canonical id minted via Part-3** at this slice); IA append-only, run-bound + snapshot-gated + **`model_version` mandatory**; the full output contract (OD-P3-0-F).

### P3-4 — Covariance / volatility estimation
- **Included:** a covariance/vol model over factor/asset returns (supports REQ-MKT-001); **Entities:** **`covariance_matrix` — net-new canonical id (mint via Part-3)**; IA append-only + run-bound + `model_version` mandatory + methodology doc (estimation window, decay/shrinkage, PSD). **History load-bearing** (Part 4). Acceptance: PSD + reproduces within ε.

### P3-5 — VaR / Expected Shortfall  *(LAST of the core risk numbers; highest bar)*
- **Included:** pluggable VaR/ES (parametric / historical / MC) as a run (REQ-MKT-001); **Entities:** realize **ENT-027 `risk_result`** (IA TRUE append-only); **seeded MC** binds `random_seed` (QS-18, deterministic); `model_version` mandatory + a full methodology doc + inventory entry. Acceptance (REQ-MKT-001): "VaR matches reference within ε; re-run identical; method has methodology doc + inventory entry". **Gated on P3-4 + history.**

### P3-6 — Stress / scenario analytics  *(REQ-MKT-004 — RTM-phase P5; conditional / late)*
- **Included:** apply shock sets, revaluation (REQ-MKT-004); **Entities:** **ENT-029 `scenario_definition` (EV, versioned saved assumptions, BR-8)** + a stress_result (**ENT-030 `scenario_result`** — realize, not mint); binds the scenario version. **NOTE: RTM-phase P5 — may fall to a later phase, not core P3.** Acceptance: stress P&L reproduces; binds scenario version.

### P3-7 — Benchmark-relative analytics
- **Included:** active risk / tracking error over captured benchmark membership (the confirmed P2-6 dependency); **Excluded:** performance attribution (unless separately scoped). **Captured-data gate:** **return-based** active analytics need `benchmark_level`/`benchmark_return` (a prerequisite captured-data slice); membership-based active risk uses the captured constituents + a risk model. IA append-only result; `model_version` mandatory; the full output contract.
- **Delivered scope (P3-7 slice, 2026-07-09; `p3_7_decision_record.md` OD-P3-7-A…E, `p3_7_implementation_plan.md`):** the **EX-ANTE, membership-based** leg — `active_risk_result` (ENT-027 third realization, migration `0030`), `TE = √(wₐᵀΣwₐ)` over the pinned factor-exposure + covariance runs and the reconstructed benchmark membership; the registered `risk.active_risk.parametric` v1 model (code_version = sole identity). The **EX-POST / return-based** leg (realized TE / active return / IR / tracking difference — the first governed `benchmark_return` consumer) is **DEFERRED on a governed portfolio-return series** (a separate performance-measurement slice; OD-G).

---

## Part 3 — Cross-cutting contracts (apply to EVERY P3 risk slice)
- **The output contract (OD-P3-0-F):** every official risk result binds `dataset_snapshot` + `calculation_run`; `code_version` + `environment_id` present; a **registered** `model_version_id` where a model applies; assumptions/limitations captured; snapshot-only compute (reproducible under correction); IA append-only result rows. Failure model = P2-3 (pre-create refusal / post-create FAILED).
- **Model governance (OD-P3-0-D/E):** registry-required via `assert_registered_model_version` (CTRL-003); `methodology_ref` mandatory on a risk model_version; `model_version` mandatory when a model/convention/estimation applies; `code_version`-only only for a convention-free deterministic transform. Validation enforcement deferred to P7 (non-enforcing status recorded).
- **Methodology (OD-P3-0-C):** a versioned `05_analytics_methodologies/` doc per method/version (the §-template), mandatory before the method ships; assumptions/limitations mirrored into `model_assumption`/`model_limitation`.
- **Audit (OD-P3-0-H):** reuse `CALC.RUN_*`; reserve `RISK.*` (EVT-220), activate per slice; caller-side; `audit/service.py` FROZEN.
- **Entitlement (OD-P3-0-I):** `risk.view` + `risk.run`; deny-by-default; auditor_3l in `.view`.
- **RLS:** symmetric tenant-scoped (FORCE) on all risk tables; NEVER hybrid; closed hybrid set unchanged; no BYPASSRLS.
- **Lineage:** `snapshot --DEPENDS_ON--> run --ORIGIN--> result` (the P2-3 shape).
- **DQ:** fail-closed `run_quality_check` (Protocol untouched; CTRL-029/032).
- **Snapshot component kinds (OD-P3-0-G):** mint the consumed kind additively (`COMPONENT_KIND_CURVE` first); tables unchanged.
- **Temporal (OD-P3-0-M):** risk results IA append-only; `scenario_definition` EV.

---

## Part 4 — Captured-data gap register (OD-P3-0-K) + data-history (OD-P3-0-L)
| Gap | Affected subphase(s) | Resolution | Blocks P3-1? |
|---|---|---|---|
| `volatility_surface` (ENT-022) absent | options/vega risk; options VaR | a P2-style captured `volatility_surface` slice (FR header + nodes, the `curve` precedent) | **No** |
| adjusted / total-return prices absent (P2-4 RAW) | price-derived factor returns; equity total-return | a captured adjusted-price series (a P2-4 extension or a derived-as-run output) | **No** |
| `rating` assignments / history absent | credit risk (REQ-CRD) | a captured `rating` slice (REQ-PUB-003 rating leg / ENT-007 FR assignments) | **No** |
| `benchmark_level` / `benchmark_return` deferred | return-based benchmark analytics | a captured benchmark-levels/returns slice (the net-new canonical id deferred at P2-6) | **No** |

**Data-history (non-binding targets):** ~3y daily pilot · ~5y daily prod · 10+y strategic · 15–20y stress. Captured tables impose **no depth limit** (additive). Each risk `model_version` declares its estimation window + data policy. Load-bearing at P3-2 (factor returns) + P3-4 (covariance), NOT P3-1.

---

## Part 5 — Deferrals (OD-P3-0-N)
Stress/scenario (REQ-MKT-004, RTM-P5 — late P3 or P5); credit risk PD/LGD (REQ-CRD — needs ratings); counterparty PFE (REQ-CPT-002); model-validation **workflow** enforcement (P7); performance attribution; reporting/dashboards/risk UI (separately planned frontend); limits/breach + ABAC enforcement (P6+). Recorded so the roadmap does not pull them forward.

---

## Part 6 — Risks & open questions register
- **Scope creep into VaR/factor before the contract is proven** → mitigated by P3-1-first (sensitivities prove the contract) + per-slice scope fences.
- **A risk number escaping model governance** ("it's just arithmetic") → mitigated by OD-P3-0-E (analytic sensitivities carry a model_version; only the P2-3 convention-free rollup is code_version-only).
- **Captured-data gaps treated as blockers vs prerequisites** → each gap is a named prerequisite captured-data slice for its affected subphase, not a P3-1 blocker.
- **Validation non-enforcement misread as "no governance"** → mitigated by CTRL-003 inventory-before-use being load-bearing + the explicit P7 deferral.
- **Open:** the OQ-P3-0-1…10 (Part 4 of the decision record) — recommended defaults, pending sign-off; the exact v1 sensitivities (rates DV01 + credit spread-duration recommended); whether factor returns are captured vs computed (P3-2).

---

## Part 7 — UltraCode 8-lens adversarial review log
8-lens adversarial review (shared with `p3_0_decision_record.md` Part 5; full per-lens log there). **Tally: 4 approve · 4 approve_with_changes · 0 block.** Folds touching THIS plan:
- **Data-Architecture (MEDIUM, confirmed):** P3-6 `stress_result` is **ENT-030 `scenario_result`** (realize), not a net-new mint — corrected in the Part-1 subphase map + the P3-6 definition; only `covariance_matrix` (P3-4) + a net-new `factor_exposure` (P3-3) remain genuine mints.
- **Scope:** the methodology home is the **existing `05_analytics_methodologies/`** (not a new `08_methodology/`, which collides with `08_testing_qa`) — corrected in P3-1 + Part 3 + the Part-8 kickoff prompt.
- **Architect / Security / Audit / Lineage:** approve — the P2-3 governed-run/snapshot-pin/`snapshot→run→result`/IA-append-only template, the symmetric-RLS expectation, the `CALC.RUN_*`-reuse + `RISK.*`-reserve, and the lineage/DQ contract all verified clean vs HEAD `6663452`.

No high/block findings; VaR/ES stays last; captured-data gaps honest; no frontend; nothing implemented.

---

## Part 8 — P3-1 planning prompt (when approved)
> "Begin P3-1 planning only: the risk methodology + model-governance hardening + analytic sensitivities decision record + implementation plan, per `p3_0_decision_record.md` (OD-P3-0-A…N) + `p3_implementation_plan.md`. Plan EXACTLY: the `05_analytics_methodologies/` framework + the first sensitivity methodology doc (conventions: bump / day-count / compounding / curve); the model_version-for-risk contract (registry-required via `assert_registered_model_version`; `methodology_ref` mandatory; `validation_status` non-enforcing); realize **ENT-028 `sensitivity`** (IA TRUE append-only, run-bound + snapshot-gated) — analytic duration / DV01 / spread-duration over captured `curve`/`curve_point` + positions (REQ-MKT-002); a new `irp_shared/risk/` package + `api/risk.py` reusing the P2-3 governed-run + snapshot-pin + `snapshot→run→result` lineage; mint `COMPONENT_KIND_CURVE` + extend `build_snapshot`; reuse `CALC.RUN_*` (reserve `RISK.*` EVT-220, activate nothing unless needed); mint `risk.view` + `risk.run` (auditor_3l in `.view`, R-07); symmetric RLS; fail-closed DQ; the output contract (snapshot + run + registered model_version + IA result + reproducible-under-correction). STRICT EXCLUSIONS: NO factor model / factor exposure / covariance / VaR / ES / stress / scenario; NO options/vega (no vol surface); NO model-validation workflow (P7); NO performance attribution; NO reporting/dashboard/frontend; NO `audit/service.py` change; NO BYPASSRLS; NO hybrid. N-lens UltraCode planning workflow; produce the decision record + implementation plan markdown under `10_delivery_backlog/`. Do not commit until I approve."
