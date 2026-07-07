# Current State

> **Purpose.** Entry-point snapshot so a fresh Claude Code session can recover context without chat
> history. Read this first, then `10_delivery_backlog/p3_2_closeout_p3_3_readiness.md` (the resume anchor),
> `next_actions.md`, and `claude_operating_instructions.md`. **As of HEAD `f941d50` / CI #91 (refreshed
> 2026-07-06, new machine — the 2026-07-02 Zscaler degraded-connectivity window is RESOLVED).** Values that
> drift are flagged; re-verify the ones in "Re-check at session start" before acting. *(`project_state.yaml`
> is RETIRED — see its stub; the recovery set is `CLAUDE.md` → this file → `phase_status.md` → `next_actions.md`.)*

## Repository
- **Project:** full-scope enterprise investment-risk platform (monorepo). NOT an MVP/POC — see `build_plan.md`.
- **Layout:** `apps/backend` (FastAPI), `apps/worker`, `apps/frontend`, `packages/shared-python` (`irp_shared`, web-framework-free), `packages/shared-ts`. Postgres + RLS, SQLAlchemy 2.0, Alembic. Numbered governance dirs `01_…`–`11_…`; delivery docs in `10_delivery_backlog/`.
- **Remote:** `github.com/ghostai8088/investment-risk-platform` (branch `main`). **origin is now SSH** (`git@github.com:…`; Keychain-backed key — see Housekeeping).

## Latest known committed state
- **origin/main HEAD:** `f941d50` — "Add P3-3 factor exposure planning and refresh project memory" (**the P3-3 planning commit, CI run #91 green**). Chain since P2-6: `ae2be8e` (P2-6 closeout memory, #85) → `bb73211` (**P2 closeout / P3 readiness review**; CI re-trigger `6663452` = #86) → `07607a5` (**P3-0 decision record + P3 implementation plan**, #87) → `1a8b2a4` (**P3-1 plan**, #88) → `e8e2e59` (**P3-1 implementation**, batch-pushed) → `5466a09` (**P3-2 plan**, batch-pushed) → `402cb12` (**P3-2 implementation**, #89) → `c452229` (**P3-2 closeout / P3-3 readiness anchor**, #90) → `f941d50` (**P3-3 plan + memory refresh + governance-qualifier cleanup + model-agnostic trailer rule**, #91).
- **Local == origin:** yes (0 ahead / 0 behind); only the model-upgrade operating-discipline housekeeping set is uncommitted (below).
- **Latest CI:** **GREEN** — `f941d50` = GitHub Actions **run #91** = success (all jobs: Backend on Python 3.12, **DB migration (Postgres)** incl. the sensitivity `0022` + factor `0023` suites, Frontend, Secret scan, Documentation check) — verified live via the REST API this session (runs #85–#91 all `success`). The 2026-07-02 Zscaler degraded-connectivity window is **RESOLVED**; nothing is push-pending.
- **Migration head:** `0023_factor_return` — advanced `0021_benchmark` → `0022_sensitivity` (P3-1, `e8e2e59`: `sensitivity_result` IA TRUE append-only + P0001 trigger + symmetric RLS) → `0023_factor_return` (P3-2, `402cb12`: `factor` EV + `factor_return` FR, symmetric RLS, NEITHER append-only). `alembic check` drift-clean; downgrade smoke green.

## Working tree (uncommitted)
- **The model-upgrade operating-discipline housekeeping set** (user-approved 2026-07-06; docs-only — no code, no migration, no backend/frontend/worker/shared-package/test/bootstrap/CI changes):
  - `claude_operating_instructions.md` — the legacy Workflow-tool fan-out replaced with the current review pattern (`/code-review ultra` and/or authorized subagent passes for implementation slices; disciplined single-pass floor for planning docs; findings-and-dispositions, not verdict tallies); NEW **"Verification & objectivity" standing rules** (no quant claim from model recall; external ground truth over self-consistency + dual-path verification from P3-4; capability-is-not-evidence; objectivity-over-agreement).
  - NEW repo-root `CLAUDE.md` — the auto-loaded entry pointer (read order + hard invariants + environment quick facts).
  - `project_state.yaml` — **RETIRED** (replaced by a stub; it had drifted to P2-6-era state — a fourth overlapping state file was a drift source).
  - This `current_state.md` — thinned (closed-phase deliverable sections removed in favor of `phase_status.md` + the backlog docs + git history), HEAD/CI advanced to `f941d50`/#91, environment facts for this machine added.
  - `next_actions.md` / `phase_status.md` — advanced to `f941d50`/#91 (the P3-3 plan is COMMITTED).

## Current active gate
**P3-0, P3-1, and P3-2 are COMPLETE and CI-green; the P3-3 factor-exposure PLAN is COMMITTED (`f941d50`, CI #91 green).**
P3-1 delivered the **first reproducible governed RISK number** (ENT-028 `sensitivity_result` — analytic curve-node
DV01/spread-DV01; run + snapshot + **registered model_version** bound; CTRL-003 executable; `risk.view`/`risk.run` minted;
the `05_analytics_methodologies/` framework). P3-2 delivered the **captured factor-return INPUT foundation** (net-new
`factor` EV definition + ENT-025 `factor_return` FR series; no run/model/snapshot — an input, not a derived number).
**P3-3 (committed `f941d50`) plans the factor-exposure engine — allocation v1:** indicator-loading CURRENCY-family factor
exposures over the pinned atoms of a COMPLETED `exposure_aggregate` run against the P3-2 `factor` definitions — a governed
DERIVED number mirroring the P3-1 exemplar (snapshot + run + registered model_version + IA append-only + `risk.*` reuse +
fail-closed DQ); vendor-beta/regression exposures and `factor_return` consumption honestly deferred; migration
`0024_factor_exposure` planned, NOT built. **P3-3 implementation has NOT started** — it is a separate approval gated on
the OQ-P3-3-1…9 sign-offs (the plan commit is done). Strict planning-first, commit-only-on-explicit-approval cadence holds. **Frontend
visibility: none of P3-0…P3-3 has a visible UI change (backend/shared-data + governance only); the P3 risk numbers enable
future factor-exposure result views / risk-run evidence panels / factor analytics dashboards, but no frontend is built
unless explicitly directed.**

## P3-2 key deliverables (closed, `402cb12`, CI-green run #89) — captured factor-return inputs REALIZED
Net-new **`factor` EV definition** (canonical id MINTED; identity `(tenant, factor_code, factor_source)`; `factor_family`
{STYLE, INDUSTRY, COUNTRY, MACRO, MARKET, CURRENCY, OTHER}; optional `factor_type`/`region`/`currency_code`/`asset_class`
scope; `frequency` DAILY v1; `REFERENCE.CREATE`/`UPDATE`-audited) **+ `factor_return` FR bitemporal captured series**
(ENT-025; grain `(tenant, factor_id, return_date, return_type)` current-head partial-unique; `return_value` decimal
fraction `Numeric(20,12)`; `return_type` SIMPLE (LOG reserved); capture/supersede/correct + both-axes
`reconstruct_factor_return_as_of`; `MARKET.FACTOR_RETURN_CREATE`/`_UPDATE`/`_CORRECTION`-audited). Migration
`0023_factor_return` — symmetric tenant RLS (never hybrid), **NEITHER table append-only**. `marketdata/factor.py` binder;
VENDOR_FACTOR ORIGIN lineage; **`marketdata.view`/`.ingest` REUSED** (no `factor.*` permission); binder-side
`Decimal.is_finite()` guard (NaN/±Inf rejected pre-write) + `> -1` economic-sanity DQ RANGE; 8 endpoints; 39 factor tests.
**Captured INPUT — NO `calculation_run`, NO `model_version`, NO snapshot pin** (computed factor returns DEFERRED — would
need adjusted prices + a registered model_version). `COMPONENT_KIND_FACTOR_RETURN` readiness-noted, NOT minted.
`audit/service.py` FROZEN. Validated green on Python 3.12 + 3.14 + full PG.

## P3-1 key deliverables (closed, `e8e2e59`, CI-covered at run #89) — the FIRST governed RISK number REALIZED
ENT-028 **`sensitivity_result`** (migration `0022_sensitivity`; **IA TRUE append-only** — `APPEND_ONLY_TABLES` + P0001
trigger + ORM guard; symmetric RLS) — **curve-node analytic DV01 / spread-DV01** (`−T·DF·1bp`; ACT/365F; continuous
compounding; nodes-only/no-interpolation; ZERO_RATE/DISCOUNT_FACTOR/SPREAD; PAR_RATE rejected/deferred;
`quantize_HALF_UP(…,12)`; curve-intrinsic — NO instrument/position attribution). **The model-governance hardening:**
`run_sensitivities` calls **`assert_registered_model_version` in the pre-create gate** (fail-closed ⇒ zero run/rows/audit)
— **CTRL-003 inventory-before-use is EXECUTABLE**; the model registered via governed `register_sensitivity_model`
(`risk.sensitivity.analytic` v1; `methodology_ref` → `05_analytics_methodologies/sensitivities_analytic_v1.md`;
assumptions/limitations mirrored; `validation_status` UNVALIDATED, non-enforcing until P7). New `irp_shared/risk/` package
(`models`/`kernel`/`service`/`events`/`bootstrap`) + `api/risk.py`; snapshot `COMPONENT_KIND_CURVE` +
`PURPOSE_SENSITIVITY_INPUT` + `curve_content` + `build_curve_snapshot`; **`risk.view`/`risk.run` MINTED** (auditor_3l in
`.view`); `RISK.SENSITIVITY_CREATE` **reserved-not-emitted** @ EVT-220; `CALC.RUN_*` reused; lineage `snapshot
--DEPENDS_ON--> run --ORIGIN--> result` (DEPENDS_ON recorded BEFORE the DQ gate); fail-closed
`risk.sensitivity.completeness` DQ; the methodology framework + first methodology doc. `audit/service.py` FROZEN.

## P3-0 key decisions (ratified, `07607a5`, CI-green run #87) — the P3 contract
OD-P3-0-A…N + the OQ-P3-0-1…10 sign-offs: **analytic-sensitivities-first** (NOT VaR/ES); the **derived-number output
contract** (every official risk result binds `dataset_snapshot` + `calculation_run` + a **registered `model_version`**
where a model applies + `code_version` + `environment_id`; IA append-only; snapshot-only compute; reproducible under
correction; pre-create-refusal / post-create-FAILED failure model); **`code_version`-only reserved for convention-free
transforms** (the P2-3 rollup — sole precedent); the methodology home `05_analytics_methodologies/` + the §-template;
`RISK.*` reserved @ EVT-220 + `CALC.RUN_*` reuse; `risk.view`/`risk.run` reservation; component kinds minted additively
per consumer; risk results IA append-only; validation-workflow enforcement deferred to P7; the captured-data gap register
(vol surface / adjusted prices / ratings / benchmark levels — later-subphase prerequisites only). Subphase map P3-1…P3-7
in `p3_implementation_plan.md` (sequencing a recommendation, not a strict chain; VaR/ES last; stress RTM-P5).

## P2 captured market-data foundation — COMPLETE (CI-green)
The full reproducibility-first P2 block is delivered and CI-green: **P2-1** `dataset_snapshot` (`3629baa`, the AD-014 reproducibility
primitive) · **P2-2** `fx_rate` (`c257e5c`, captured FX) · **P2-3** `calculation_run`+`exposure_aggregate` (`da178fc`, the first
governed derived number — MARKET_VALUE only) · **P2-4** `price_point` (`2b63b76`, captured prices) · **P2-5** `curve`+`curve_point`
(`49ca3bd`, captured curves) · **P2-6** `benchmark`+`benchmark_constituent` (`b6284a4`, captured benchmarks). The reproducibility
primitive + the captured market-data inputs (FX, prices, curves, benchmarks) + the first governed derived number (exposure) are all
realized. **NO risk analytics yet** — VaR/ES/factor/covariance/stress/scenario/attribution/tracking-error stay **P3+**.


> **Per-slice deliverable detail for CLOSED phases (P0.5–P2-6, P1B, P1C) was thinned out of this file on
> 2026-07-06** — it lives in `phase_status.md` (the ledger), the `10_delivery_backlog/` decision records /
> plans / closeout docs, and this file's own git history. Only the active-phase (P3) sections are kept here.

## Completed phases
- **P0.5** engineering hygiene & foundation (scaffold, audit framework, RLS foundation, CI).
- **P1A-0…P1A-4** the cross-cutting rails — `7cdc2f9`, `96a1564`, `c9be657`, `cc472be`, `c781bb8` (+ PG fix `0282359`). **P1A milestone CLOSED.**
- **P1A closeout / P1B readiness** — `69afedf`.
- **P1B-0 decision record + plan** — `dbed93e`; **ratifications into governance** — `4fae26b`; **project-memory artifacts** — `b1efc05`.
- **P1B-1 implementation plan** — `05ee5f5`.
- **P1B-1 reference-data implementation** — `6568cb1` (CI-green, run #28). **P1B-1 CLOSED.**
- **P1B-2 implementation plan** — `410cc7e` (CI-green, run #29).
- **P1B-2 reference-data implementation** — `32c7778` (CI-green, run #31). **P1B-2 CLOSED.**
- **P1B-3 implementation plan** — `43c042e` (CI-green).
- **P1B-3 reference-data implementation** — `8545ed6` (CI-green, run #34). **P1B-3 CLOSED.**
- **P1B-4 implementation plan** — `f6d691a` (CI-green).
- **P1B-4 reference-data implementation** — `060b2a4` (CI-green, run #37). **P1B-4 CLOSED → P1B block DELIVERED.**
- **P1B closeout / P1C readiness review** — `e99633a` (CI-green, run #39).
- **P1C-0 decision record + P1C implementation plan** — `705d3ba` (CI-green, run #40).
- **P1C-1 portfolio-hierarchy implementation plan** — `b52ad9e` (CI-green, run #41).
- **P1C-0 ratification into governance** — `dca7bc0` (AD-017 + REQ-PPM-001 + PORTFOLIO.* reserved + OD-013/OD-025 closed; CI-green, run #42).
- **P1C-1 portfolio-hierarchy + ABAC scope anchor implementation** — `bb89c74` (CI-green, run #43). **P1C-1 CLOSED** — the first domain entity.
- **P1C-1 closeout project-memory refresh** — `d1d6829` (CI-green, run #44).
- **P1C-2 transaction implementation plan** — `c398215` (CI-green, run #45).
- **P1C-2 transaction capture (IA append-only) implementation** — `abb230f` (CI-green, run #46). **P1C-2 CLOSED** — the first domain IA / append-only entity.
- **P1C-2 closeout project-memory refresh** — `f3fd7c9` (CI-green, run #47).
- **P1C-3 position implementation plan** — `42cc02c` (CI-green, run #48).
- **P1C-3 position capture (FR bitemporal) implementation** — `4ee124e` (CI-green, run #49). **P1C-3 CLOSED** — the first FR domain entity.
- **P1C-3 closeout project-memory refresh** — `2f7d647` (run #50) + cleanup `b38f182` (run #51).
- **CI hygiene** — `67741fb` (run #52): GitHub Actions bumped to Node-24 majors (`checkout@v5`/`setup-python@v6`/`setup-node@v5`); Node-20 deprecation warning eliminated.
- **P1C-4 valuation implementation plan** — `92a0264` (CI-green, run #53).
- **P1C-4 valuation capture (FR bitemporal, captured marks) implementation** — `c5c5806` (CI-green, run #54). **P1C-4 CLOSED** — the second FR domain entity; **REQ-PPM-003 now Done**.
- **P1C-4 closeout project-memory refresh** — `6e3dcc1` (CI-green, run #55).
- **P1C-5 holdings-views implementation plan** — `8a14173` (CI-green, run #56; OD-P1C5-1..6 signed off).
- **P1C-5 read-only as-of holdings / portfolio views implementation** — `0bef45b` (CI-green, run #57). **P1C-5 CLOSED** — the first read-model / composition package (no entity, no migration).
- **P1C-5 closeout project-memory refresh** — `867e576` (CI-green, run #58).
- **P1C-6 deterministic synthetic dataset implementation plan** — `7dfdb79` (CI-green, run #59; audit conclusions folded; OD-P1C6-1..7 signed off).
- **P1C-6 deterministic synthetic dataset implementation** — `3e9882d` (CI-green, run #60). **P1C-6 CLOSED** — the deterministic synthetic dataset (governed seam + never-auto-run). **The FULL P1C block (P1C-1…P1C-6) is DELIVERED.**
- **P1C-6 closeout project-memory refresh** — `9584ba4` (CI-green, run #61).
- **P1C closeout / P2 readiness review** — `7070dff` (CI-green, run #62; 8-lens). Reproducibility-first P2 sequencing chosen.
- **P2-0 decision record + P2 implementation plan** — `2d19992` (CI-green, run #63; 8-lens, 0 block). OD-P2-A…L; subphases P2-1…P2-6.
- **P2-1 dataset_snapshot implementation plan** — `d7be981` (CI-green, run #64; 8-lens, 0 block). The AD-014 reproducibility-primitive build plan.
- **P2 dataset_snapshot governance ratification** — `63be23a` (CI-green, run #65; 7-lens, 7× approve). ENT-049/050 + SNAPSHOT.CREATE (EVT-190 reserved) + snapshot.* (reserved) + AD-004-R1 + REQ-PPM-004→In-Progress.
- **P2 ratification closeout project-memory refresh** — `d45a31b` (CI-green, run #66; docs-only).
- **P2-1 `dataset_snapshot` implementation** — `3629baa` (CI-green, run #67; 8-lens, 6 in-scope folds). **P2-1 CLOSED** — the AD-014 reproducible input-snapshot primitive (ENT-049/050) realized; **migration head `0015_valuation` → `0016_dataset_snapshot`** (the first migration since P1C-4) + the first new Snapshot symmetric-RLS CI step. NO exposure number, NO `calculation_run` wiring.
- **P2-1 closeout project-memory refresh** — `85ff5b2` (CI-green, run #68; docs-only).
- **P2-2 `fx_rate` implementation plan** — `6020b03` (CI-green, run #69; 8-lens, 6 in-scope folds; build-ready). The 10 specific decisions settled (FR; base/quote direction; MID; USD-base triangulation; `marketdata.*`; etc.).
- **P2-2 `fx_rate` implementation** — `c257e5c` (CI-green, run #70; 8-lens, 6 approve / 2 approve_with_changes / 0 block; 1 in-scope fold). **P2-2 CLOSED** — captured FX market data (ENT-024, FR) realized; **migration head `0016_dataset_snapshot` → `0017_fx_rate`** + the new FX symmetric-RLS CI step. NO exposure number, NO `calculation_run` wiring, NO `dataset_snapshot` change.
- **P2-2 closeout project-memory refresh** — `adf4ac5` (CI-green, run #71; docs-only).
- **P2-3 decision record + implementation plan** — `d10c766` (CI-green, run #72; 8-lens, 10 in-scope folds; the five OQ-P2-3 sign-offs). `calculation_run` wiring + basic exposure; OD-P2-3-A…L.
- **P2-3 exposure + `calculation_run` governance ratification** — `851f976` (CI-green, run #73; AD-018; 7-lens, 6 approve / 1 approve_with_changes). ENT-014 ratified-in-planning; the `CALC.RUN_START/COMPLETE/FAIL` → `CALC.RUN_CREATE/STATUS_CHANGE` doc-vs-code reconciliation; EVT-210 `EXPOSURE.*` reserved; `exposure.*` perms; CTRL-009 executable; HALF_UP canonical-serialization exception. RATIFIED-IN-PLANNING, no code.
- **P2-3 `calculation_run` wiring + basic exposure implementation** — `da178fc` (CI-green, run #74; 8-lens, 5 approve / 3 approve_with_changes / 0 block; 2 in-scope folds). **P2-3 CLOSED** — the **first governed derived number** (`exposure_aggregate`, ENT-014, IA append-only) realized; **migration head `0017_fx_rate` → `0018_exposure_aggregate`** (+ the additive `calculation_run.environment_id`) + the new Exposure symmetric-RLS CI step. The AD-014/FW-RUN/TR-15 gate is now load-bearing. NO risk (MARKET_VALUE only).
- **P2-3 closeout project-memory refresh** — `0b12d85` (CI-green, run #75; docs-only).
- **P2-4 captured price history decision record + implementation plan** — `b73e65f` (CI-green, run #76; 8-lens, 4 in-scope folds; the six OQ-P2-4 sign-offs). `price_point` (ENT-020) FR/bitemporal captured prices; OD-P2-4-A…L.
- **P2-4 captured price history implementation** — `2b63b76` (CI-green, run #77; 8-lens, 7 approve / 1 approve_with_changes / 0 block; 1 in-scope fold). **P2-4 CLOSED** — `price_point` (ENT-020, FR/bitemporal captured vendor prices) realized; **migration head `0018_exposure_aggregate` → `0019_price_point`** + the new Price-point symmetric-RLS CI step. **REQ-PUB-001 → In-Progress (partial).** NO pricing model, NO conversion, NO `calculation_run`/`exposure_aggregate`/`dataset_snapshot`/FX change.
- **P2-4 closeout project-memory refresh** — `419db9d` (CI-green, run #78; docs-only).
- **P2-5 captured yield/spread curves decision record + implementation plan** — `326ad94` (CI-green, run #79; 8-lens, 8 in-scope folds; the ten OQ-P2-5 sign-offs). The unified `curve` + `curve_point`; OD-P2-5-A…N.
- **P2-5 captured yield/spread curves implementation** — `49ca3bd` (CI-green, run #80; 8-lens, 7 approve / 1 approve_with_changes / 0 block; 1 material + 3 low folds). **P2-5 CLOSED** — the unified `curve` (FR header, ENT-021) + `curve_point` (IA append-only nodes) realized; ENT-023 `credit_spread` by value; **migration head `0019_price_point` → `0020_curves`** + the new Curve symmetric-RLS CI step. **REQ-PUB-002 + REQ-PUB-003 → In-Progress (partial).** NO curve construction/interpolation/duration/pricing/risk; NO `calculation_run`/`exposure_aggregate`/`dataset_snapshot`/`fx_rate`/`price_point` change.
- **P2-5 closeout memory** — `0c5c068` (run #81); **P2-6 plan** — `8d2782f` (run #82); **operating rules** — `1e0dc08` (run #83).
- **P2-6 captured benchmark/index data implementation** — `b6284a4` (CI-green, run #84). **P2-6 CLOSED** — `benchmark` (ENT-009, EV definition) + `benchmark_constituent` (FR membership); **migration head `0020_curves` → `0021_benchmark`**. **THE FULL P2 FOUNDATION COMPLETE.** Closeout memory — `ae2be8e` (run #85).
- **P2 closeout / P3 readiness review** — `bb73211` (CI re-trigger `6663452`, run #86).
- **P3-0 decision record + P3 implementation plan** — `07607a5` (CI-green, run #87). **OD-P3-0-A…N RATIFIED** (the P3 contract; analytic-sensitivities-first; subphases P3-1…P3-7).
- **P3-1 analytic sensitivities plan** — `1a8b2a4` (CI-green, run #88; OQ-P3-1-1…6 ratified).
- **P3-1 analytic sensitivities implementation** — `e8e2e59` (batch-pushed; CI-covered at run #89). **P3-1 CLOSED** — the first governed RISK number (`sensitivity_result`, migration `0022_sensitivity`); CTRL-003 executable; `risk.view`/`risk.run` minted; the methodology framework + `sensitivities_analytic_v1.md`.
- **P3-2 factor-return inputs plan** — `5466a09` (batch-pushed; CI-covered at run #89).
- **P3-2 factor-return inputs implementation** — `402cb12` (CI-green, run #89). **P3-2 CLOSED** — the `factor` canonical id minted + ENT-025 `factor_return` realized (migration `0023_factor_return`); captured INPUT (no run/model/snapshot binding).
- **P3-2 closeout / P3-3 readiness handoff** — `c452229` (CI-green, run #90; the resume anchor for the machine move).

## Next required action
**COMMIT THE P3-3 PLANNING SET (on explicit approval):** the P3-3 decision record + implementation plan
(`10_delivery_backlog/p3_3_*.md`) + this project-memory refresh + the 5-doc degraded-qualifier cleanup — planning/
governance/project-memory markdown only, no code. Then, **on a further separate approval and after the OQ-P3-3-1…9
sign-offs, begin P3-3 IMPLEMENTATION** (the exact kickoff prompt is `p3_3_factor_exposure_implementation_plan.md`
Part 11): the factor-exposure engine, allocation v1 — `factor_exposure_result` (ENT-028 family; IA append-only;
migration `0024_factor_exposure`), `run_factor_exposure` mirroring the P3-1 `run_sensitivities` exemplar,
`COMPONENT_KIND_EXPOSURE` + `COMPONENT_KIND_FACTOR` snapshot pins, the `factor_exposure_allocation_v1.md` methodology
doc, `risk.*` entitlement REUSE. Build **nothing else**.

## What MUST NOT be started yet
- **P3-3 implementation** — not until the plan is committed, the OQ-P3-3 sign-offs are ratified, AND the user directs it.
- **No covariance / volatility estimation** — P3-4 (mints the net-new `covariance_matrix` canonical id at its slice).
- **No VaR / Expected Shortfall** — P3-5 (ENT-027 `risk_result`; gated on P3-4 + history).
- **No stress testing / scenario analytics** — P3-6 (ENT-029/030; RTM-P5 — possibly a later phase).
- **No benchmark-relative analytics / active risk / tracking error / performance attribution** — P3-7+ (and `benchmark_level`/`benchmark_return` are themselves DEFERRED captured inputs — a net-new canonical ENT id, not minted).
- **No vendor-beta or regression factor exposures** — deferred v2 (need a captured factor-loading slice / adjusted-price return history + estimation); **no computed factor returns** (need adjusted prices + a registered model_version); **no `COMPONENT_KIND_FACTOR_RETURN`** (readiness-noted; minted when P3-4 / regression v2 consumes returns).
- **No instrument/position key-rate DV01 / interpolation / bootstrapping / pricing engine / PAR_RATE / vol surface** — the P3-1 deferrals stand.
- **No reporting / dashboard build; no frontend changes** unless explicitly approved (P3-0…P3-3 have no visible UI change; the P3 numbers enable future factor-exposure/risk-run/factor-analytics UI but build none by default).
- **No limits/breach, real SSO, ABAC enforcement** — P6+ (ABAC stays anchored-not-enforced).
- **P1B-5** (reference-data ingestion mapping) — conditional/deferred (only if bulk loading is needed; not now).
- **Never** modify `packages/shared-python/src/irp_shared/audit/service.py` (frozen) or `entitlement/bootstrap.py` outside the governed R-07 mint (P3-3 mints NO new permission — `risk.view`/`risk.run` are REUSED); no new audit code / permission / role / migration without R-07. **No weakening of the P2/P3 snapshot-run-model controls; no BYPASSRLS; no hybrid/SYSTEM_TENANT behavior** beyond the closed 5-table set.

## Housekeeping / security (RESOLVED — recorded for recovery)
- A **plaintext GitHub PAT file** was observed in the **parent directory** (one level ABOVE the repo root, OUTSIDE version control — never staged/tracked). The user **deleted the file** and **revoked the token** on GitHub (2026-06-22), and migrated git auth to an **SSH key** (ed25519, passphrase cached in the macOS Keychain; `origin` switched to `git@github.com`). **Standing rule: never read/copy/print/use any credential file found on disk — flag it for the user to revoke/rotate. Do NOT inspect token contents.**

## Re-check at session start (may have drifted)
- `git log -1 --oneline` and `git status --short` — confirm HEAD (≥ `c452229`) and whether the P3-3 planning set was committed.
- Latest CI conclusion for the current HEAD (GitHub Actions; `gh` CLI is NOT installed — the public repo REST API answers unauthenticated; `c452229` = run #90 = success at this refresh).
- `git remote -v` — origin is SSH (`git@github.com:ghostai8088/…`).
- Migration head is `0023_factor_return` (advanced `0021_benchmark` → `0022_sensitivity` at P3-1 / `e8e2e59`, → `0023_factor_return` at P3-2 / `402cb12`; the next migration is `0024_factor_exposure`, planned at P3-3 — it lands ONLY at the separately-approved P3-3 implementation slice, no code in the planning commit).
- `project_state.yaml` is **RETIRED** (2026-07-06 stub; found drifted at the P3-3 planning session) — the recovery set is `CLAUDE.md` + this file + `phase_status.md` + `next_actions.md`.
- **This machine's environment (verified 2026-07-06):** the repo sits nested at `~/Projects/investment_risk_platform/investment-risk-platform/`; the venv is **Python 3.13.0** (CI runs 3.12 — the prior machine validated 3.12 + 3.14); **`irp_pg_local` is NOT yet stood up here** — stand up the reused `postgres:16` container + `export DATABASE_URL`/`IRP_TEST_DATABASE_URL` + `alembic upgrade head` BEFORE the P3-3 implementation slice (docs-only work needs none of it); `gh` is not installed (use the public REST API).
