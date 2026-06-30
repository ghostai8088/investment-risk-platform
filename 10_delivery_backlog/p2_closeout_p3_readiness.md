# P2 Closeout & P3 Readiness Review

## Document Control

| Field | Value |
|---|---|
| Purpose | Confirm the full P2 captured market-data / reproducibility foundation is complete enough to support **P3 (risk/factor analytics) PLANNING**; inventory the P2 capabilities available to P3; identify remaining prerequisites; and recommend the P3-0 planning structure. **Assessment / governance ONLY** — NO application code, NO migrations, NO P3 implementation. |
| Status | **Readiness review — ASSESSMENT ONLY; NO code, NO migrations, NO P3 implementation.** |
| HEAD at writing | `ae2be8e` ("Refresh project memory after P2-6 closeout"); migration head `0021_benchmark`; origin/main clean. The full P2 block (P2-1…P2-6) is committed + CI-green. |
| Predecessors | `p2_0_decision_record.md` + `p2_implementation_plan.md` (the reproducibility-first P2 structure); the six P2 slice decision-records/plans (`p2_1`…`p2_6`); the P1A-2 model-registry skeleton; the AD-014/FW-RUN/TR-15 governed-run framework. |
| Review | 8-lens UltraCode adversarial review — **Part 11** (filled after the review workflow). |
| Governance | This is a readiness review; it mints **no** entity, migration, permission, audit event, or canonical id. The P3-0 decision record (a SEPARATE later approval) ratifies the P3 structure. |

> **Bottom line (Part 3 conclusion, stated up front):** **P2 is complete and sufficient to begin P3 PLANNING.** Every cross-cutting prerequisite (RLS, audit, entitlement, lineage, DQ, model registry, `calculation_run`, `dataset_snapshot`, captured FX/prices/curves/benchmarks, basic exposure, synthetic dataset) is REALIZED and CI-green. The remaining items are **deferred-by-design** (the model-validation *workflow* is P7; a methodology-documentation *framework* needs a P3-0 decision; `volatility_surface` and `rating` are unbuilt *inputs* gating specific risk domains; time-series *depth* is a data-provisioning concern, not a schema gap) — **none blocks P3 planning.** Recommended entry: **P3-0 decision record first**, then methodology + model-governance hardening + a factor-input foundation **before** any VaR/ES.

---

## Part 1 — P2 closeout summary

The reproducibility-first P2 block (OD-P2-D): the reproducibility primitive (P2-1) → the captured market-data inputs (P2-2/4/5/6) → the first governed derived number (P2-3). All six slices committed + CI-green.

### P2-1 — `dataset_snapshot` / reproducible input snapshot (`3629baa`, CI #67)
- **Migration head impact:** `0015_valuation` → `0016_dataset_snapshot` (the first since P1C-4).
- **Entities/modules:** `dataset_snapshot` (ENT-049) + `dataset_snapshot_component` (ENT-050); new `irp_shared/snapshot/` package + `api/snapshots.py`.
- **Temporal:** IA **TRUE append-only** (both in `APPEND_ONLY_TABLES` → `irp_prevent_mutation` P0001 trigger + ORM guard). Physical-version pin + `captured_content` + SHA-256 `content_hash` (HALF_UP-quantized, engine-independent) + header `manifest_hash`.
- **RLS:** symmetric tenant-scoped (FORCE); NEVER hybrid; cross-tenant binding fails closed.
- **Audit:** `SNAPSHOT.CREATE` (EVT-190) caller-side; DC-2 metadata; zero on read/verify.
- **Entitlements:** `snapshot.view` / `snapshot.create` minted; `auditor_3l` excluded.
- **Lineage:** narrow internal `data_snapshot` writer (one `snapshot→component` edge per component).
- **DQ:** caller-side completeness gate (Protocol untouched); gap → `DataQualityError` → CTRL-032 rollback.
- **Known placeholders / follow-ups:** computes NO derived number; wires NO `calculation_run` (readiness-only — the run binding begins at P2-3). **Risk carried forward:** none material; the snapshot is the load-bearing reproducibility anchor for all P3 risk outputs.

### P2-2 — `fx_rate` / captured FX market data (`c257e5c`, CI #70)
- **Migration head impact:** `0016` → `0017_fx_rate`.
- **Entities/modules:** `fx_rate` (ENT-024); new `irp_shared/marketdata/` package + `api/marketdata.py`; the pure published-rate `convert`.
- **Temporal:** FR/bitemporal (NOT append-only; close-out UPDATEs; content-immutability service-enforced).
- **RLS:** symmetric (FORCE); NEVER hybrid.
- **Audit:** `MARKET.FX_CREATE`/`UPDATE`/`CORRECTION` (EVT-200) caller-side; zero on read/`convert`.
- **Entitlements:** `marketdata.view` / `marketdata.ingest` minted (reusable, not per-entity); `auditor_3l` excluded.
- **Lineage:** VENDOR (`VENDOR_FX`) `data_source` ORIGIN edge per physical version.
- **DQ:** new generic `RANGE` evaluator (additive; Protocol unchanged) + strictly-positive rate gate.
- **Known placeholders / follow-ups:** exact-date `rate_date` matching v1 (most-recent-on-or-before deferred); BID/ASK reserved. **Risk carried forward:** time-series *depth* not enforced (a data-provisioning concern for factor/VaR history — Part 5).

### P2-3 — `calculation_run` wiring + basic `exposure_aggregate` (`da178fc`, CI #74; AD-018)
- **Migration head impact:** `0017` → `0018_exposure_aggregate` (+ the additive `calculation_run.environment_id`).
- **Entities/modules:** `exposure_aggregate` (ENT-014) — the platform's **FIRST official governed derived number**; new `irp_shared/exposure/` package + `api/exposure.py`; `calculation_run` (ENT-026) binding wired.
- **Temporal:** `exposure_aggregate` IA **TRUE append-only**; run-bound + snapshot-gated (NOT-NULL FKs to `calculation_run.run_id` + `dataset_snapshot.id`). `calculation_run` IA status-mutable (NOT in `APPEND_ONLY_TABLES`).
- **RLS:** symmetric (FORCE); NEVER hybrid.
- **Audit:** reuse `CALC.RUN_CREATE` + `CALC.RUN_STATUS_CHANGE` (NO `EXPOSURE.AGGREGATE_CREATE` — EVT-210 `EXPOSURE.*` reserved); the additive `outcome` param on `update_run_status` (the sole non-frozen `calc/service.py` change; `audit/service.py` FROZEN).
- **Entitlements:** `exposure.view` + `exposure.aggregate.run`; `exposure.view` is the **first** domain perm granting `auditor_3l` a read (governed-output oversight).
- **Lineage:** `dataset_snapshot --DEPENDS_ON--> calculation_run --ORIGIN--> exposure_aggregate` (`run_id` stamped); new `SOURCE_TYPE_CALCULATION_RUN` + `EDGE_KIND_DEPENDENCY`.
- **DQ:** fail-closed gates before any write (snapshot completeness + FX completeness + mark-required + cross-tenant).
- **Known placeholders / follow-ups:** **signed market value v1 only** (`signed qty × captured mark × effective FX`); `exposure_type = MARKET_VALUE`; grain `(portfolio, instrument, base)` — **no portfolio/subtree TOTAL rows** (a deterministic Σ deferred); `model_version_id = N/A` (deterministic rollup — never minted a sham model_version). **Risk carried forward:** the model-less rollup is the precedent that a P3 *model-driven* risk result MUST instead populate `model_version_id` (Part 7).

### P2-4 — `price_point` / captured price history (`2b63b76`, CI #77)
- **Migration head impact:** `0018` → `0019_price_point`.
- **Entities/modules:** `price_point` (ENT-020); `marketdata/price.py` binder + `PricePoint` model.
- **Temporal:** FR/bitemporal (NOT append-only).
- **RLS / Audit / Entitlements / Lineage:** symmetric RLS (FORCE, never hybrid); `MARKET.PRICE_*` (EVT-200); reuse `marketdata.*`; `VENDOR_PRICE` ORIGIN lineage.
- **DQ:** required-field + strictly-positive `RANGE` (fail-closed).
- **Known placeholders / follow-ups:** RAW vendor prices only (no corporate-action adjustment engine); captured `currency_code`, NO conversion; staleness DQ (QS-16) deferred. **REQ-PUB-001 → In-Progress (partial).** **Risk carried forward:** price *adjustment* (total-return / split/dividend-adjusted series) is unbuilt — a factor-return-input consideration (Part 5/9).

### P2-5 — `curve` + `curve_point` / captured yield/spread curves (`49ca3bd`, CI #80)
- **Migration head impact:** `0019` → `0020_curves`.
- **Entities/modules:** unified `curve` (ENT-021, FR header) + `curve_point` (IA append-only nodes); `marketdata/curve.py` binder. **ENT-023 `credit_spread` realized BY VALUE** (`curve_type=CREDIT_SPREAD` + `reference_key`).
- **Temporal:** `curve` FR (NOT append-only); `curve_point` IA append-only (P0001 trigger).
- **RLS / Audit / Entitlements / Lineage:** symmetric RLS both tables; `MARKET.CURVE_*` (EVT-200, one event per curve); reuse `marketdata.*`; `VENDOR_CURVE` ORIGIN lineage.
- **DQ:** required-field + tenor-validity + value-type-conditional `RANGE` (DF strictly-positive; rates/spreads `[-1,1]`; Protocol untouched).
- **Known placeholders / follow-ups:** `interpolation_method` an inert label (NO interpolation engine); completeness/staleness deferred. **REQ-PUB-002 + REQ-PUB-003 → In-Progress (partial).** **`volatility_surface` (ENT-022) NOT built** (deferred to P3+). **Risk carried forward:** NO curve construction/interpolation/discounting/duration — these are **P3 compute** that consumes the captured curve; and the **missing vol surface gates options/vega risk** (Part 3).

### P2-6 — `benchmark` + `benchmark_constituent` / captured benchmark/index data (`b6284a4`, CI #84)
- **Migration head impact:** `0020` → `0021_benchmark`.
- **Entities/modules:** `benchmark` (ENT-009, EV definition) + `benchmark_constituent` (FR/bitemporal membership); `marketdata/benchmark.py` binder.
- **Temporal:** `benchmark` EV (in-place version); `benchmark_constituent` FR; **NEITHER append-only** (no P0001 trigger).
- **RLS:** symmetric both tables; NEVER hybrid; constituent `tenant_id` server-stamped from the parent.
- **Audit — the ratified split (OQ-P2-6-11 Option A):** EV definition → `REFERENCE.CREATE`/`REFERENCE.UPDATE` (EVT-140/141); FR membership → `MARKET.BENCHMARK_CONSTITUENT_CREATE`/`_UPDATE`/`_CORRECTION` (EVT-200, set-grained one-event-per-set). The definition is NOT moved into `MARKET.*`.
- **Entitlements:** reuse `marketdata.view`/`.ingest`.
- **Lineage:** `VENDOR_BENCHMARK` ORIGIN (benchmark-row-targeted; edge carries no `effective_date`).
- **DQ:** required-field + weight `RANGE [0,1]` (non-vacuous — empty set rejected 422; Protocol untouched).
- **Known placeholders / follow-ups:** `benchmark_level` + `benchmark_return` DEFERRED (a net-new canonical ENT id, not minted); weight-sum completeness + staleness deferred; opaque-constituent-id fallback deferred; `rating` deferred. **REQ-PUB-003 benchmark leg advanced** (does not close). **Risk carried forward:** the captured benchmark membership is the **confirmed P3 input** for benchmark-relative/active risk; captured benchmark *levels/returns* (for return-based benchmark analytics) are a future captured-data slice.

### Confirmations
- **P2-1…P2-6 committed:** ✅ (`3629baa` / `c257e5c` / `da178fc` / `2b63b76` / `49ca3bd` / `b6284a4`).
- **P2-1…P2-6 CI-green:** ✅ (runs #67 / #70 / #74 / #77 / #80 / #84, all 5 jobs each).
- **origin/main clean:** ✅ (HEAD `ae2be8e`; this readiness review is the only pending docs change).
- **migration head:** ✅ `0021_benchmark`.
- **P3 not started:** ✅ (no `p3_*` doc, no `0022` migration, no risk-entity code).
- **No unresolved P2 defect blocks P3 planning:** ✅ — every 8-lens review across P2 closed at 0 blocks; all material findings were folded before commit. The open items are deferred-by-design (above), not defects.

---

## Part 2 — P2 capability inventory (what P3 may use)

| Capability (entity) | What P3 CAN use | What P3 must NOT assume | Known limitations |
|---|---|---|---|
| `dataset_snapshot` (ENT-049) | Pin a knowledge-time-cut input set; the authoritative reproducibility anchor every official risk result binds to (Part 7). | That it pins risk *outputs* — it pins *inputs* only; it computes nothing. No `COMPONENT_KIND_*` for risk results. | Component kinds today: PORTFOLIO/POSITION/VALUATION/FX. PRICE/CURVE/BENCHMARK/REFERENCE are **readiness-only** (no kind minted yet) — P3 mints the kind(s) it needs to pin curve/price/benchmark inputs. |
| `dataset_snapshot_component` (ENT-050) | Physical-version pinning + captured_content + content_hash for reproducibility. | That every market input is already pinnable — only the minted kinds are. | A P3 risk run that consumes a curve/price/benchmark must first mint the component kind + extend `build_snapshot` (the `COMPONENT_KIND_FX`-at-P2-3 precedent). |
| `fx_rate` (ENT-024) | Captured FX as a risk input; the pure `convert` for base-currency conversion. | Triangulation = risk; it is a published-rate lookup, not analytics. No implied/forward FX. | Exact-date matching; MID-only; time-series depth not enforced. |
| `price_point` (ENT-020) | Captured RAW vendor prices as factor/return/VaR inputs. | That prices are adjusted (total-return / corporate-action-adjusted). | RAW only; no adjustment engine; staleness DQ deferred. |
| `curve` / `curve_point` (ENT-021/023) | Captured yield + credit-spread curves as discounting/sensitivity inputs; `credit_spread` by value. | That curves are *constructed/interpolated/bootstrapped* — they are captured nodes only. | NO interpolation engine; `volatility_surface` (ENT-022) **not built** (no vol input). |
| `benchmark` / `benchmark_constituent` (ENT-009) | Captured benchmark membership + weights as as-of inputs for benchmark-relative / active risk. | That benchmark *levels/returns* exist (deferred) or that weights sum to 1.0 (completeness DQ deferred). | `benchmark_level`/`benchmark_return` deferred; weight-sum + staleness DQ deferred; `rating` deferred. |
| `calculation_run` (ENT-026) | The governed run framework (FW-RUN): bind `input_snapshot_id` + `model_version_id` + `assumption_set_id` + `random_seed` + `code_version` + `environment_id`; CREATED/RUNNING/COMPLETED/FAILED; reuse `CALC.RUN_*` audit. | That `model_version_id` is optional for a *model-driven* result — P2-3 left it N/A only because the rollup is deterministic (Part 7). | The reproducibility-binding columns are present + exercised; P3 risk runs populate `model_version_id` + (for MC) `random_seed`. |
| `exposure_aggregate` (ENT-014) | The IA run-bound + snapshot-gated derived-number **template** (the first governed derived number) to mirror for `risk_result`/`sensitivity`. | That it is *risk* — it is signed market value v1 (MARKET_VALUE only); no VaR/factor/sensitivity. | Per-holding atom grain; no portfolio/subtree TOTAL rows; deterministic Σ deferred. |
| `model` / `model_version` (ENT-035) | The model registry referent: `model` (EV head) + `model_version` (IA, immutable) carrying `methodology_ref` + `code_version`; `model_assumption` + `model_limitation` (IA, ENT-036). The stable anchor `CalculationRun.model_version_id` + run→result lineage bind to. | That validation/approval is **enforced** — the governance columns (tier/validation_status/approved_use + maker-checker hooks) are **non-enforcing placeholders reserved for P7**. | Registry is ready as a referent; the validation/approval *workflow* enforcement is P7. P3 uses `model_version` as a referent with a non-enforcing `validation_status` placeholder. |
| synthetic inputs (P1C-6) | A deterministic, reproducible synthetic portfolio/reference/position/valuation dataset (via the governed binders) for P3 test/demo. | That it includes market/risk/exposure/snapshot data — it is **capture-only** (reference/hierarchy/transactions/positions/valuations). | No synthetic market data (FX/price/curve/benchmark) or risk; NEVER-AUTO-RUN; SYNTHETIC tenant only. A P3 deterministic-risk test may need synthetic market inputs added via the P1C-6 seam. |

---

## Part 3 — P3 readiness assessment

**Prerequisite checklist (for P3 risk/factor PLANNING):**

| Prerequisite | Status | Notes |
|---|---|---|
| tenant context / RLS | ✅ READY | Symmetric FORCE RLS across all domain + market-data tables; never hybrid; closed 5-table hybrid set stable; PG-proven as `irp_app`. |
| audit | ✅ READY | Hash-chained `record_event` (FROZEN `audit/service.py`); EVT-210 `EXPOSURE.*` reserved; a `RISK.*`/`CALC.*` family extends additively via R-07 at P3. |
| entitlement | ✅ READY | Deny-by-default `require_permission`; the `auditor_3l`-in-view governed-output pattern established at P2-3; P3 risk perms mint via R-07. |
| lineage | ✅ READY | `snapshot --DEPENDS_ON--> run --ORIGIN--> result` realized at P2-3; the exact shape a `risk_result` reuses. |
| data quality | ✅ READY | Fail-closed `run_quality_check` (Protocol stable; `RANGE`/`NOT_NULL` evaluators); CTRL-032 rollback; CTRL-029 no-silent-failure. |
| model registry | ✅ READY (referent) / ⚠️ validation enforcement P7 | `model`/`model_version`/`assumption`/`limitation` exist; `model_version` is the immutable run referent. Validation/approval is **non-enforcing** (P7) — acceptable for P3 if the methodology + non-enforcing-status stance is decided at P3-0. |
| `calculation_run` | ✅ READY | All FW-RUN bindings present + exercised (P2-3); `model_version_id` populated by P3 risk runs. |
| `dataset_snapshot` | ✅ READY (inputs) / ⚠️ component kinds | Pins inputs; P3 mints the curve/price/benchmark component kind(s) it consumes (the `COMPONENT_KIND_FX` precedent). |
| captured FX | ✅ READY | `fx_rate` (ENT-024). |
| captured prices | ✅ READY (RAW) | `price_point` (ENT-020); adjusted/total-return series unbuilt. |
| captured curves | ✅ READY (rates + credit) / ⚠️ no vol | `curve`/`curve_point`; **`volatility_surface` NOT built** — gates options/vega risk. |
| captured benchmarks | ✅ READY (membership) | `benchmark`/`benchmark_constituent`; levels/returns deferred. |
| basic exposure | ✅ READY | `exposure_aggregate` (the governed-derived-number template). |
| synthetic dataset | ✅ READY (capture-only) | P1C-6; no synthetic market/risk inputs yet. |
| methodology documentation framework | ⚠️ DECISION NEEDED (P3-0) | `model_version.methodology_ref` exists as a pointer; there is **no methodology-doc framework/location/required-fields standard**. REQ-MKT-001 acceptance requires "method has methodology doc + inventory entry". A P3-0 decision must establish the framework BEFORE the first risk method ships. |
| control mappings | ✅ READY (extend) | **CTRL-003** (model/version inventoried-before-use, BR-3 — the `assert_registered_model_version` gate, Designed-skeleton at P1A-2; **becomes load-bearing/executable at the first model-driven risk run**, the most P3-relevant model-governance control), CTRL-009 (governed output) executable, CTRL-014 (limitations/BX-LIM), CTRL-017 (append-only), CTRL-018/TR-13 (reproduction test), CTRL-029, CTRL-032 in place; P3 maps risk results to these + any new risk CTRL via R-07. |

**Conclusion:** **P2 is sufficient to begin P3 PLANNING.** Three items need a P3-0 *decision* (not a build) before the first risk *implementation*: (1) the methodology-documentation framework; (2) the model-validation stance (non-enforcing-status vs an enforced gate, given P7 owns enforcement); (3) which market inputs the first risk method needs (and therefore whether a captured `volatility_surface` and/or adjusted prices are prerequisite captured-data slices). **No unresolved P2 defect blocks P3 planning.**

---

## Part 4 — P3 risk boundary

**P3 may EVENTUALLY include (each its own planned, separately-approved slice):** factor-model decisioning + versioning; factor-return inputs; factor-exposure calculations; volatility/covariance estimation; VaR / Expected Shortfall; stress / scenario analytics; market-risk methodology docs; model-governance linkage; risk-output reproducibility.

**P3 MUST NOT start until planned (hard gates — carry forward verbatim):**
- **No risk calculations without methodology documentation** (REQ-MKT-001 acceptance — methodology doc + model-inventory entry).
- **No model output without model registry / `model_version` linkage** (`CalculationRun.model_version_id` populated; the model-less P2-3 rollup is NOT a precedent for a model-driven result).
- **No official risk result without `dataset_snapshot` + `calculation_run` binding** (the AD-014/FW-RUN/TR-15 gate; the `exposure_aggregate` template).
- **No risk output without audit, lineage, and reproducibility metadata** (the `snapshot→run→result` lineage + `CALC.*`/`RISK.*` audit + reproducible-under-correction property).
- **No reporting / dashboard unless separately planned.**
- **No frontend work unless explicitly approved.**

---

## Part 5 — P3 data-history requirements (non-binding planning guidance)

These are **planning targets**, not a P3 commitment; the readiness review builds nothing:
- **Minimum pilot:** ~**3 years daily** (enough for a basic historical-window or short-lookback estimate).
- **Initial production target:** ~**5 years daily**.
- **Strategic target:** **10+ years daily**.
- **Stress / regime target:** **15–20 years** where available (to span multiple regimes/crises).

Clarifications:
- **Store as much clean history as available** — the captured-data tables (`fx_rate`/`price_point`/`curve`/`benchmark_constituent`) impose **no history-depth limit**; depth is a data-provisioning concern, not a schema gap. Capturing more history is additive (new captured rows), not a migration.
- **Each `model_version` must declare its estimation window** (lookback length, frequency, decay/half-life or window type) in `methodology_ref` / assumptions — so a result is reproducible and interpretable.
- The following must be **explicit** per risk model (captured as `model_assumption`s / methodology fields): **frequency** (daily/weekly), **lookback**, **decay/window** (EWMA half-life vs equal-weight window), **missing-data policy** (gaps/holidays/new instruments), **outlier policy** (winsorization/exclusion), and **adjustment policy** (raw vs total-return / corporate-action-adjusted prices — note P2-4 captures RAW only, so an adjusted series is a prerequisite captured-data decision).
- **NO factor/risk model implementation in this readiness review.**

---

## Part 6 — Model governance readiness

**Existing model governance (P1A-2, ENT-035/036) — how P3 should use it:**

| Element | Present | P3 stance |
|---|---|---|
| `model` (EV head) | ✅ | The model-inventory head; P3 registers each risk model (code + name + `model_type` controlled-vocab string). |
| `model_version` (IA) | ✅ | The **immutable referent** for `CalculationRun.model_version_id` + run→result lineage; change = new version (MG-10). Carries `methodology_ref` + `code_version`. |
| **CTRL-003 inventory-before-use gate** | ✅ (skeleton) | `assert_registered_model_version` (BR-3, Preventive) already refuses a use of an unregistered `model_version` (logic-level today); at the first model-driven risk run it becomes **load-bearing** — a risk run MUST reference a *registered* `model_version`, not merely a non-null FK. P3 wires it into the risk-run create path. |
| `model_assumption` (IA) | ✅ | Capture each estimation assumption (window, decay, distribution, missing-data) per version. |
| `model_limitation` (IA) | ✅ | Capture limitations (CTRL-014 / BX-LIM) per version. |
| `calculation_run` | ✅ | Binds model_version + snapshot + assumptions + seed + code_version + environment_id. |
| methodology docs | ⚠️ pointer only | `methodology_ref` is a free pointer; the **framework** (where docs live, required sections, inventory linkage) is a P3-0 decision. |
| validation status / future validation workflow | ⚠️ non-enforcing | `validation_status` + tier + approved_use + maker-checker hooks are **non-enforcing placeholders reserved for P7**. P3 uses them as metadata; enforcement is P7. |
| `model_version` vs `code_version` usage | — | **`code_version`** = the deterministic algorithm/commit anchor (mandatory on every run, model-driven or not). **`model_version_id`** = the registered model + its methodology/assumptions/limitations (mandatory **when a model is involved**). |
| when `model_version` is mandatory | — | Any run that applies an **estimation/statistical model** (factor model, covariance, VaR, sensitivity-with-conventions). |
| when `code_version` alone suffices | — | A **deterministic, model-less** transform (the P2-3 exposure rollup precedent — `model_version_id` N/A-with-rationale; never mint a sham model_version). |

**P3-0 decisions needed before implementation:**
- **Whether the first risk model is** a factor model, a covariance/volatility model, a sensitivity model, or a scenario engine (Part 8 recommends the order).
- **Model-registry requirements:** what `model_type` vocabulary + which `model`/`model_version` fields are mandatory at registration for a risk model.
- **`model_version` creation/approval stance:** auto-`UNVALIDATED` at registration (non-enforcing) vs an enforced approval gate — given P7 owns enforcement, the recommended P3 stance is **non-enforcing status + mandatory methodology_ref**, with the enforced workflow deferred to P7.
- **Methodology-documentation requirements:** the framework (location, required sections, inventory-entry linkage) satisfying REQ-MKT-001's "methodology doc + inventory entry".
- **Validation placeholder vs enforced workflow:** confirm P3 uses the placeholder (P7 enforces) — recorded as an explicit deferral, not a silent gap.

---

## Part 7 — Reproducibility & `calculation_run` requirements (P3 output contract)

Every **official** P3 risk result must satisfy (the AD-014/FW-RUN/TR-15 contract, extending the `exposure_aggregate` template):
- **Bind to a `dataset_snapshot`** (a non-null `input_snapshot_id`) — the pinned, knowledge-time-cut inputs.
- **Bind to a `calculation_run`** (a non-null `run_id`) — no result row without a complete run.
- **`calculation_run.code_version`** present (the deterministic algorithm anchor).
- **`calculation_run.environment_id`** present (the FW-RUN §5 run-environment label).
- **`model_version` attached AND registered** (`model_version_id` non-null **AND** passing the `assert_registered_model_version` inventory gate — CTRL-003/BR-3) **when a model is involved** (factor/covariance/VaR/sensitivity); N/A-with-recorded-rationale only for a deterministic model-less transform (the P2-3 precedent). A risk run must reference a *registered* model_version, never a bare FK.
- **Assumptions and limitations captured** (`model_assumption` / `model_limitation` per version).
- **Input components reconstructable** — the snapshot pins every market/position input; the compute makes NO live market read (the P2-3 import-fence + pure-compose precedent) → **reproducible under a later input correction** (re-run over the same snapshot is identical, within ε for seeded MC).
- **Result records append-only** unless explicitly justified — `risk_result` (ENT-027 "immutable result rows linked to a run") + `sensitivity` (ENT-028) should be IA **TRUE append-only** (the `exposure_aggregate` precedent; a re-run = a new run + new rows, never an edit).

---

## Part 8 — P3 entry-point options

| Option | Description | Dependency order | Impl risk | Methodology readiness | Model-gov implications | Data sufficiency | Testability | Control implications | Scope-creep risk |
|---|---|---|---|---|---|---|---|---|---|
| **A. P3-0 decision record only** | Ratify the P3 structure + the model-gov/methodology/reproducibility decisions; no entity. | First (gates all) | Minimal (docs only) | Establishes it | Sets the stance | N/A | N/A (governance) | Maps the risk CTRLs | Low — by construction |
| **B. P3-1 factor model foundation** | Mint the factor-model registry usage + a first factor model. | After A + factor inputs | Medium-high | Needs methodology framework first | High — first real model_version | Needs factor-return inputs (not yet captured) | Hard without inputs | New risk CTRLs | High if inputs not ready |
| **C. P3-1 risk methodology + model-registry hardening** | Establish the methodology-doc framework + the model_version-for-risk stance + risk CTRL mappings; no risk number. | After A | Low | Builds it | Establishes mandatory-fields | N/A (governance) | Governance tests | Maps + reserves | Low |
| **D. P3-1 factor-returns / covariance INPUT foundation** | Capture/derive factor returns (or a captured factor-return series) as the input substrate. | After A (+ ideally C) | Medium | Some methodology needed | Medium | Depends on captured price/benchmark depth (Part 5) | Moderate (deterministic) | Lineage/DQ extend | Medium |
| **E. P3-1 sensitivity / exposure extension** | Add deterministic-ish analytic sensitivities (duration/DV01/spread-duration) over captured curves + positions. | After A (+ C) | Medium | Conventions doc needed | Medium (conventions = a model) | Curves ready; no vol (no vega) | Good (analytic, reproducible) | Risk CTRLs | Medium |
| **F. P3-1 VaR / ES prototype** | A pluggable VaR/ES run. | LAST (needs inputs + methodology + model-gov) | High | Highest bar (REQ-MKT-001 acceptance) | Highest | Needs history depth + covariance/return inputs | Hardest (seeded-MC ε) | Most CTRLs | Highest |

**Recommended (safest) P3 entry point:** **Option A — the P3-0 decision record first** (it gates everything and resolves the three open decisions of Part 3). Then, before any VaR/ES (Option F), do **Option C** (methodology + model-governance hardening) and a **factor/sensitivity input foundation** (Option D and/or the analytic-sensitivity Option E, which is the most testable first *number* because it is reproducible-by-construction over the already-captured curves). **VaR/ES (F) is last** — it has the highest methodology, model-governance, and data-depth bar.

---

## Part 9 — Proposed P3 subphase structure (recommendation; ratified at P3-0)

A reproducibility-first, governance-first P3 sequence. Each subphase below is sketched at the readiness level; the full per-subphase contract is authored in its own plan.

| Subphase | Requirements included | Excluded | Entities/modules | Temporal | APIs | Audit | Entitlements | RLS | Lineage | DQ | Model gov | run/snapshot binding | Tests | Acceptance | Risks | Open questions |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **P3-0** planning / decision record | the P3 structure + the model-gov/methodology/reproducibility decisions | any risk number | none (governance) | — | — | — | — | — | — | — | sets stance | sets contract | governance-doc tests | the decisions are ratified | premature build | which first risk method; methodology framework; validation stance |
| **P3-1** risk methodology + model-governance hardening | methodology-doc framework; `model_version`-for-risk required fields; risk CTRL mappings; `RISK.*` audit reservation | any risk number | model-registry usage + governance docs | — | model-registry reads | reserve `RISK.*` (R-07) | reserve `risk.*` perms | symmetric | — | — | mandatory methodology_ref + assumptions/limitations | — | governance + parity tests | a risk model is registrable with mandatory methodology + assumptions | over-engineering governance | enforce vs non-enforce (P7 boundary) |
| **P3-2** factor universe / factor-return inputs | a captured/derived factor-return input substrate (**REQ-MKT-003**) | factor *exposures*; risk numbers | `factor_return` (ENT-025) | likely IA append-only or FR captured | capture/read | `MARKET.*` or `RISK.*` (decide) | `marketdata.*` or new | symmetric | VENDOR/derived ORIGIN | required-field + range | model_version if derived | snapshot-pinnable | capture/reconstruct tests | factor returns present + as-of | captured vs computed factor returns | history depth (Part 5) |
| **P3-3** factor-exposure engine | factor exposures of positions (**REQ-MKT-003** — contributions sum to total within ε) | VaR/covariance | exposure-metric (ENT-028 family) or new | IA append-only (run-bound) | run + read | `RISK.*`/`CALC.*` | `risk.*` | symmetric | snapshot→run→result | fail-closed | model_version mandatory | mandatory | reproducibility + ε tests | exposures reproduce; bound to run+snapshot+model_version | model conventions | linear-only first? |
| **P3-4** covariance / volatility estimation | a covariance/vol model over factor/asset returns | VaR | covariance/vol result (new) | IA append-only | run + read | `RISK.*` | `risk.*` | symmetric | snapshot→run→result | fail-closed | model_version mandatory | mandatory | PSD/within-ε reproduction | covariance reproduces; PSD; methodology doc | estimation-window choices | EWMA vs window; shrinkage |
| **P3-5** VaR / Expected Shortfall | pluggable VaR/ES as a run (REQ-MKT-001) | stress/scenario | `risk_result` (ENT-027) | IA TRUE append-only | run + read | `RISK.*` | `risk.*` | symmetric | snapshot→run→result | fail-closed | model_version mandatory + methodology doc | mandatory; seeded MC `random_seed` | reproduction + ε + seed tests | VaR matches reference within ε; re-run identical; methodology doc + inventory entry | seeded-MC determinism (QS-18) | parametric/historical/MC scope |
| **P3-6** stress / scenario analytics | apply shock sets (**REQ-MKT-004 — note: RTM-phase P5; the most-deferred, conditional/late — may fall to a later phase, not core P3**) | reporting | `scenario_definition` (ENT-029) + stress results | EV (scenario defs) + IA (results) | scenario CRUD + run | `RISK.*` | `risk.*` | symmetric | snapshot→run→result | fail-closed | model_version where revalued | mandatory; binds scenario version | reproduction tests | stress P&L reproduces; binds scenario version | revaluation reuse | scenario versioning (BR-8) |
| **P3-7** benchmark-relative analytics | active risk / tracking error over captured benchmark membership | performance attribution (unless scoped) | risk result (active) | IA append-only | run + read | `RISK.*` | `risk.*` | symmetric | snapshot→run→result | fail-closed | model_version mandatory | mandatory | reproduction tests | active risk reproduces vs the captured benchmark | needs benchmark levels/returns? | the confirmed P2-6 dependency |

> **Sequencing note (reconciling Part 8 ↔ Part 9):** the subphase **numbering is a recommendation, not a strict dependency chain**. Per Part 8, the **lowest-dependency first computed NUMBER is analytic sensitivities (Option E, REQ-MKT-002 — duration/DV01/spread-duration over the already-shipped `curve`/`curve_point` + positions)** because it needs **no new captured input** and is reproducible-by-construction; it may therefore precede or run **in parallel with** the factor-return-input substrate (P3-2, which needs not-yet-captured factor returns, Part 5). The P3-0 decision record settles the exact order; a reasonable concrete sequence is **P3-1 (methodology + model-gov, incl. analytic sensitivities as the first reproducible number) → P3-2/P3-3 (factor inputs → exposures) → P3-4 (covariance) → P3-5 (VaR/ES) → P3-6 (stress, RTM-P5, conditional) → P3-7 (benchmark-relative)**. **Input gates:** P3-2+ need factor-return inputs; options/vega risk needs a captured `volatility_surface` (ENT-022, unbuilt); credit risk needs `rating` (unbuilt) — these are prerequisite *captured-data* decisions for the affected subphases, not blockers for the sensitivity/rates first numbers.

## Part 10 — Frontend / visualization readiness

- **What P2 enables (for FUTURE, separately-planned frontend slices):** market-data views (FX/price/curve/benchmark lookups), snapshot views (input-set inspection), exposure-result views (the first governed derived number), benchmark views (definitions + membership), and — once P3 risk results exist — risk-readiness dashboards (VaR/sensitivity/factor evidence).
- **This review creates NO frontend work** (assessment/governance only; no `apps/frontend` change).
- **P3 planning may decide** whether to introduce UI visibility for risk evidence; any frontend implementation must be **separately planned and approved** (the standing rule — no frontend unless explicitly directed).

---

## Part 11 — UltraCode 8-lens adversarial review log
**8 lenses (Product/Requirements, Chief-Architect, Data-Architecture, Security/RLS, Audit/Controls, Lineage/Data-Quality, Model-Governance/Quant, Scope) — verdicts: 5 `approve` (Data-Arch, Security/RLS, Audit/Controls, Lineage/DQ, Scope) + 3 `approve_with_changes` (Product, Architect, Model-Gov); 0 `block`.** The five factual-accuracy lenses confirmed every load-bearing fact (commits 3629baa/c257e5c/da178fc/2b63b76/49ca3bd/b6284a4; CI runs #67/#70/#74/#77/#80/#84; migration heads 0016–0021; audit families incl. the P2-6 `REFERENCE.*`/`MARKET.BENCHMARK_CONSTITUENT_*` split; the `CalculationRun`/model-registry shapes; the input gaps — `volatility_surface`/`rating`/`benchmark_level`-`return`/adjusted prices) matches shipped HEAD `ae2be8e`; the security/RLS, audit/control, lineage/DQ, and scope claims are all accurate and **no P3 implementation / risk number / frontend is pulled forward**. The folds:
- **Model-Governance (the key lens) — CTRL-003 / inventory-before-use (verified):** the shipped enforcing gate `assert_registered_model_version` (CTRL-003 / BR-3) was missing from the prerequisites + the output contract. **Fold (Part 3 control-mappings row + Part 6 + Part 7):** a risk run must reference a **registered** `model_version` (not a bare FK); CTRL-003 added; it becomes load-bearing at the first model-driven run.
- **Product — REQ traceability + REQ-MKT-004 phasing (verified):** the factor subphases lacked their governing requirement and the stress subphase over-stated its phase. **Fold (Part 9):** P3-2/P3-3 cite **REQ-MKT-003** (factor exposure & contribution); P3-6 stress flagged as **RTM-phase P5** (most-deferred / conditional / possibly later than core P3).
- **Architect — Part 8 ↔ Part 9 consistency (verified):** Part 8 recommends analytic sensitivities (Option E, REQ-MKT-002) as the lowest-dependency first *number* on shipped curves, but Part 9 front-loaded the factor substrate. **Fold:** a sequencing note reconciles them (numbering is a recommendation; analytic sensitivities is the earliest reproducible number, needing no new captured input; the input gates — factor returns / vol surface / rating — are named per subphase).
- All folds are documentation-accuracy improvements; **no readiness conclusion changed** (P2 remains complete + sufficient for P3 planning; P3-0 ready to plan). 0 blocks; no scope leak (assessment-only confirmed across all lenses).

---

## Readiness gate
**P3-0 is ready to plan.** P2 is complete + CI-green; every cross-cutting prerequisite is satisfied; the three open decisions (methodology framework, model-validation stance, first-risk-method inputs incl. the vol-surface/adjusted-price/rating input gaps) are exactly the P3-0 decision-record agenda. The recommended path: **P3-0 decision record first → P3-1 methodology + model-governance hardening + a factor/sensitivity input foundation → … → VaR/ES last.** No P3 implementation begins until P3-0 is approved.
