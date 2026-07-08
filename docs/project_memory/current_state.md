# Current State

> **Purpose.** Entry-point snapshot so a fresh Claude Code session can recover context without chat
> history. Read this first, then `10_delivery_backlog/delivery_roadmap.md` (the operative sequence) + `var_hs_1_decision_record.md` (the latest record), `next_actions.md`, and `claude_operating_instructions.md`. **As of HEAD
> `29ae31b` / CI #117 (refreshed 2026-07-08).** Values that
> drift are flagged; re-verify the ones in "Re-check at session start" before acting. *(`project_state.yaml`
> is RETIRED — see its stub; the recovery set is `CLAUDE.md` → this file → `phase_status.md` → `next_actions.md`.)*

## Repository
- **Project:** full-scope enterprise investment-risk platform (monorepo). NOT an MVP/POC — see `build_plan.md`.
- **Layout:** `apps/backend` (FastAPI), `apps/worker`, `apps/frontend`, `packages/shared-python` (`irp_shared`, web-framework-free), `packages/shared-ts`. Postgres + RLS, SQLAlchemy 2.0, Alembic. Numbered governance dirs `01_…`–`11_…`; delivery docs in `10_delivery_backlog/`.
- **Remote:** `github.com/ghostai8088/investment-risk-platform` (branch `main`). **origin is now SSH** (`git@github.com:…`; Keychain-backed key — see Housekeeping).

## Latest known committed state
- **origin/main HEAD:** `29ae31b` — "Implement VAR-HS-1 historical-simulation VaR with adversarial-review folds" (**CI run #117 green**). Chain since P3-3: `7c50c43` (**P3-3 implementation**, #95) → `362481a` (P3-3 closeout memory) → `8abe764` (**P3-4 planning**, OQs ratified) → `a9b6567` (**P3-4-R0 refactor**, #98) → `c2bd126` (**P3-4 IMPLEMENTATION + 12 review folds**, #99) → `c2480a4` (P3-4 closeout memory, #100) → `c2c1b4d` (**P3-5 parametric-VaR planning**, OQ-P3-5-1..10 ratified + the historical-sim/MC ROADMAP note, #101) → `5ed8271` (**P3-5 IMPLEMENTATION + 13 review folds**, #102) → `d94e572` (P3-5 closeout memory, #103) → `c2e85ac` (**P3-C1 hardening planning**, OQ-P3-C1-1..8 ratified after a plain-language briefing, #104) → `0599f7f` (**P3-C1 IMPLEMENTATION + 12 review folds**, #105) → `ee3c581` (P3-C1 closeout memory, #106) → `416cb1d` (**FE-1 frontend runs-view planning**, OQ-FE-1-1..8 ratified, #107) → `678a651` (**FE-1 IMPLEMENTATION + 16 review folds — the FIRST VISIBLE UI SLICE**, #108) → `945661d` (FE-1 closeout memory, #109) → `63a1bb8` (**the RATIFIED delivery roadmap + the documentation-alignment audit**, #110) → `76c7942` (**TC-1 planning**, OQ-TC-1-1..5 ratified, #111) → `c34b346` (**TC-1 IMPLEMENTATION — Wave-1 slice 1**, #112) → `df04e1d` (TC-1 closeout memory, #113) → `ec1f582` (**VAR-HS-1 planning**, OQ-VAR-HS-1-1..7 ratified, #116) → `29ae31b` (**VAR-HS-1 IMPLEMENTATION — Wave-1 slice 2 — the FIFTH governed risk number**, **CI #117 green**). Earlier chain: Chain since P2-6: `ae2be8e` (P2-6 closeout memory, #85) → `bb73211` (**P2 closeout / P3 readiness review**; CI re-trigger `6663452` = #86) → `07607a5` (**P3-0 decision record + P3 implementation plan**, #87) → `1a8b2a4` (**P3-1 plan**, #88) → `e8e2e59` (**P3-1 implementation**, batch-pushed) → `5466a09` (**P3-2 plan**, batch-pushed) → `402cb12` (**P3-2 implementation**, #89) → `c452229` (**P3-2 closeout / P3-3 readiness anchor**, #90) → `f941d50` (**P3-3 plan + memory refresh + governance-qualifier cleanup + model-agnostic trailer rule**, #91) → `b3d3923` (**operating-discipline modernization**, #92) → `5c64cf1` (**retrospective model-upgrade audit + status-decay fixes**, #93) → `bd5ba3c` (**gate tiers + OQ-P3-3 ratification**, #94) → `7c50c43` (**P3-3 IMPLEMENTATION + review folds**, #95).
- **Local == origin:** yes (0 ahead / 0 behind); only this closeout memory refresh is uncommitted.
- **Latest CI:** **GREEN** — `29ae31b` = GitHub Actions **run #117** = success (full-PG 1142 passed at implementation time; the new `test_var_hs_pg.py` step green). Chain #98–#117 all green.
- **Migration head:** `0028_var_historical` — advanced `0027_run_failure_reason` → `0028_var_historical` (VAR-HS-1, `29ae31b`: `var_result.z_score`/`sigma`/`covariance_run_id` made nullable, metric-conditional via a new `ck_var_result_parametric_not_null` CHECK; the downgrade is DESTRUCTIVE — it deletes `VAR_HISTORICAL` rows, RLS-safe, cycled twice in both directions with real exit codes over suite-created data). Drift-clean.
- **Networking note (this machine):** SSH to GitHub is unreliable on some networks (lossy-link/PMTU class — pushes stall mid-key-exchange while HTTPS works); the reliable push path is **HTTPS + the keychain-cached PAT**; CI verification via the public REST API always works. A full-repo safety bundle exists at `../irp-p3-3-7c50c43.bundle`.

## Working tree (uncommitted)
- **This VAR-HS-1 closeout memory refresh only** (Tier 0 — docs-only): the five project-memory files + the `var_hs_1_decision_record.md` status/closeout stamps advanced to `29ae31b`/#117 + the roadmap's Wave-1 slice-2 DONE marker.

## Current active gate
**P3-0 … P3-5 + P3-C1 + FE-1 + TC-1 + VAR-HS-1 are ALL COMPLETE and CI-green; the RATIFIED `delivery_roadmap.md`
(Wave 1) is the operative sequence.** VAR-HS-1 (`29ae31b`, CI #117; plan `ec1f582`, #116) closed Wave-1 slice 2:
**the platform's FIFTH governed risk number and second VaR method** — plain equal-weight factor-based historical
simulation (`risk.var.historical` v1; the empirical lower order statistic over pinned factor-return windows, no
distributional assumption). See the deliverables section below. **Next per the roadmap: P3-C2 (the hardening
bundle), planning on explicit direction.** Model/effort recommendation standing rule (2026-07-08): append a
next-step model+effort suggestion to every gate briefing (Sonnet/medium for commit-and-closeout mechanics;
Opus 4.8/high for templated implementation with a shipped exemplar like P3-C2; Fable/high for novel
methodology/planning/review-synthesis — extra-high/max reserved for wave-close benchmark reviews or gnarly
debugging). Strict planning-first cadence + the gate tiers hold. **Frontend visibility: the FE-1 read-only view
EXISTS (dev-shim session, permanent DEV banner) and now ALSO surfaces VAR-HS-1 runs with zero frontend changes;
anything further (dashboards, charts, mutations, more domains) remains explicitly gated.**

## VAR-HS-1 key deliverables (closed, `29ae31b`, CI-green run #117) — Wave-1 slice 2; the FIFTH governed risk number
**Historical-simulation VaR** (OD-VHS-A…G; plan `ec1f582`, #116): plain equal-weight factor-based historical
simulation — `risk.var.historical` v1 registered model family (declared confidence/horizon/window/quantile-
convention; the empirical lower order statistic `k=⌈N(1−c)⌉` over pinned factor-return windows; NO distributional
assumption). Reuses `var_result` (ENT-027) via `metric_type='VAR_HISTORICAL'`; additive migration
`0028_var_historical` makes `z_score`/`sigma`/`covariance_run_id` nullable, GUARDED by a new metric-conditional
`ck_var_result_parametric_not_null` CHECK constraint (the parametric method's NOT-NULL invariant stays
DB-enforced); the downgrade is DESTRUCTIVE (deletes `VAR_HISTORICAL` rows — unrepresentable pre-0028) and RLS-safe
(disables FORCE RLS + the append-only trigger transactionally around the delete — cycled twice in both directions
with real exit codes over suite-created data). New snapshot purpose `VAR_HS_INPUT` (`SNAPSHOT_PURPOSES` member) +
`build_var_hs_snapshot` (FACTOR_EXPOSURE IA-row pins + aligned per-factor FACTOR_RETURN bitemporal window pins).
Two new endpoints (`POST /risk/models/var-historical`, `POST /risk/vars-historical/runs`); reads flow through the
EXISTING parametric VaR GET family + the FE-1 listing with **zero frontend changes**. Methodology doc
`var_historical_v1.md` carries CITED external benchmarks (BoE WP525, Pritsker 2006, arXiv 2505.05646, BIS
d305/d457 — the ratified roadmap's Part 4 rule 6, its first discharge). **Independent 6-finder review: 30 filings
folded into 16 fixes**, incl. TWO ratification amendments recorded in the record's Part 5: **OD-VHS-E tightened**
(the adequacy floor `N≥⌈1/(1−c)⌉` still permitted `k=1`, the sample minimum, at its own boundary — now
`N·(1−c)>1` strictly, 21@0.95/101@0.99, enforced at BOTH the registrar and the declared-parameter re-check — the
generic-registration floor-bypass is closed too); **OD-VHS-C widened** (the third nullable column + the CHECK
constraint + the destructive/RLS-safe downgrade, above). Kernel/binder precision fixes (the magnitude-FAILED gate
was dead code — now reachable and test-proven on both engines); registry-honesty corrections to the parametric
model's own limitation text (it no longer denies the shipped method exists). 26 backend tests (a hand-minted
adjudication vehicle now drives 16 gate probes, incl. a cross-tenant provenance regression that had silently
survived the original suite). `audit/service.py` FROZEN; zero new permissions. Full-PG **1142 passed** at
implementation time.

## FE-1 key deliverables (closed, `678a651`, CI-green run #108) — the FIRST VISIBLE UI slice; NO migration
The read-only **"risk runs & results" view** (OD-FE-1-A…H; plan `416cb1d`, #107): TWO screens — the **runs list**
(the four RISK families; run_type/status filters; has-more offset pagination via a PAGE_SIZE+1 probe; truncated
`failure_reason`; whole-row click-through) and the deep-linkable **run detail** (`/runs/:family/:runId` — provenance
verbatim in monospace, per-family result tables, a FAILED run's persisted reason rendered prominently — the P3-C1
column's designed first consumer; **decimal strings rendered byte-for-byte, never Number()** — tested with
NON-round-tripping constants). **The ONE backend addition:** `GET /risk/runs` (`irp_shared/risk/queries.py` +
router; `risk.view`; explicit tenant predicate + RLS; the four RISK run_types ONLY — `EXPOSURE_AGGREGATE` fenced
out and its request a 422; fail-closed filters; `created_at DESC, run_id` deterministic order; items-only; NO audit
on reads). **Dev-session posture:** header-shim session (`sessionStorage`; printable-ASCII validation at entry AND
on load) under a permanent non-dismissable "DEV SESSION — identity is unverified" banner; honest 401/403 states on
BOTH screens; enforcement stays server-side; SSO unchanged at P6+. **Dependencies:** runtime = react/react-dom/
react-router-dom ONLY; jsdom + @testing-library/react as dev-only test tooling (disposition recorded in the
record). Vite dev proxy — NO backend CORS. **16 review findings folded** (Part 7): 2 stale-response races; runId
URL-injection (encodeURIComponent + attack-shaped test); the has-more pager; non-ASCII session-id refusal; the
fence test re-pinned to LITERALS with the real `EXPOSURE_AGGREGATE` witness; deterministic tie-break ids; **NEW
`test_risk_runs_pg.py`** (irp_app RLS posture) + its ci.yml step; RunDetail honest 401/403; row-click navigation
(the user caught this live); strengthened proofs (path pins, DOM order, pager click-through, all four families).
`apps/frontend/README.md` = the verified demo run-book (uvicorn + vite + a TESTED seeding snippet). 12 + 2 backend
tests, 37 frontend tests. **Recorded follow-ups:** the vite5/vitest2 toolchain major-bump slice (+ production-deps
`npm audit` in CI); exposure runs in the listing (`exposure.view` family).

## P3-C1 key deliverables (closed, `0599f7f`, CI-green run #105) — the hardening/consolidation slice; NO new governed number
The deferral-register paydown (OD-P3-C1-A…H; plan `c2e85ac`, CI #104): **(B) the REGISTERED-status bind** —
`assert_model_version_of` (the risk-family gate all four binders route through) now requires
`version.status == "REGISTERED"` → `UnregisteredModelError`; AND (the review's principal fold) **all FOUR governed
registrars refuse a non-REGISTERED same-label twin** (`WrongModelVersionError` 422) — register/run consistency (the
generic resolver + P7 validation semantics untouched). **(C) persisted `calculation_run.failure_reason`** (additive
Text; migration `0027_run_failure_reason`; `update_run_status(failure_reason=)` persists on the FAILED transition
ONLY; the audit payload UNCHANGED — DQ rows remain the durable evidence; the four GET-run endpoints surface it; all
four binder reason formats preserved VERBATIM). **(D) the run-scaffold extraction** —
`risk/scaffold.py::execute_governed_run` (create_run → RUNNING → DEPENDS_ON → compute → fail-closed gate → FAILED+
reason | rows+ORIGIN+COMPLETED) consumed by all four risk binders under the R0 behavior-preservation bar, **proven
by golden captures written green PRE-extraction** (`test_p3c1_scaffold_preservation.py`: audit sequences + lineage
CONTENT + DQ-rule CONTENT + exact reason formats; one finder re-ran the goldens against the stashed pre-extraction
code). **(E) `PreciseDecimal` parity** for the 8 float53-unsafe result columns (`sensitivity_value(28,12)`,
`loading(20,12)`, `exposure_amount(28,6)`×2, `signed_quantity(28,8)`, `mark_value(20,6)`, `fx_rate(28,12)`,
`z_score(20,12)` — the review fold); PG DDL identical, NO migration. **(F) the MRO-walking `deps.map_refusal`**
shared by the risk/exposure/snapshot routers (a subclass of a mapped refusal no longer 500s). **(G) both-modes
ambiguity refusal ×5 binders** covering EVERY build-mode argument incl. the as-of args (exposure's `base_currency`
deliberately excluded — verified honored on the snapshot path); checks sit BEFORE the model gate (request-shape
first). **(H) the P3-3 mixed-base adjudication check** (`_adjudicate_pins` base-currency uniformity — the latent
hole closed at adjudication, grain unchanged). **12 review findings folded; 1 residual recorded** (the DQ-rule
first-registration race — pre-existing, faithfully preserved; a deliberate-behavior-change slice if wanted).
**Recorded follow-ups:** exposure-family scaffold/`failure_reason` adoption; captured-input-table PreciseDecimal
parity. 1111 PG-backed tests; `audit/service.py` FROZEN; zero new permissions/audit codes/entities.

## P3-5 key deliverables (closed, `5ed8271`, CI-green run #102) — ENT-027 REALIZED; the FIRST derived-of-derived number
**`var_result`** (**ENT-027 `risk_result` REALIZED**; migration `0026_var`; **IA TRUE append-only** + P0001 trigger +
symmetric RLS): zero-mean delta-normal 1-day parametric VaR — `σ_p = √(xᵀΣx)`, `VaR = z·σ_p` — over the pinned
result rows of TWO upstream governed runs (`x` = a COMPLETED FACTOR_EXPOSURE run's per-factor totals; `Σ` = a
COMPLETED COVARIANCE run), the platform's first SINGLE-SUMMARY-ROW result (grain `(calculation_run_id,
metric_type)`; `VAR_PARAMETRIC`, ES reserved) with **hard-FK provenance columns** `exposure_run_id`/
`covariance_run_id` (re-resolved own-tenant on BOTH paths pre-create — PG FK checks bypass RLS; the review's
principal fold). **Declared-parameter version identity** (OD-P3-5-D): confidence/horizon/z are strict-parsed
`model_assumption`s (vocab {0.9500, 0.9900}; dual-verified 12dp z constants; horizon must equal `1` verbatim; NO
runtime inverse-CDF). Fail-closed adjudication on BOTH paths: coverage (exposure factors ⊆ covariance factors, NO
zero-variance imputation), single-run provenance, uniform base currency, canonical-order + duplicate refusals,
source-column magnitude envelopes, structurally-malformed-content 422s. The declared radicand quantization floor
(`tol = F²·max(xᵢ²)·1e-19`; clamp within, committed FAILED below — REACHABLE and test-proven) + a magnitude gate
(σ beyond Numeric(28,6) ⇒ FAILED, never a PG overflow 500). σ/VaR carried as `PreciseDecimal(28,6)`. Dual-path
verification: exact hand references (σ=500/700/7) through the kernel AND the governed consume path; `numpy`
cross-check @1e-9; erf round-trip + bisection of the z constants; NON-VACUOUS pin invariance (upstream supersede
moves a fresh build but not the pin). `RISK.VAR_CREATE` reserved-not-emitted; **`risk.*` REUSED — zero new
permissions**; `var_parametric_v1.md` methodology (**specific-risk = 0 the first-class limitation**); 4 endpoints;
the VaR PG CI step; 52 new tests. **13 review findings folded; 2 recorded deferrals** (the
`assert_registered_model_version` status-bind check — cross-slice, a P3-6-planning carry-in; shipped result-column
float parity — a dedicated PreciseDecimal parity slice) — **both PAID DOWN at P3-C1 (`0599f7f`)**. **REQ-MKT-001 → In-Progress (parametric leg);
historical-sim + MC = user-directed ROADMAP method slices.**

## P3-4 key deliverables (closed, `c2bd126`, CI-green run #99) — the THIRD governed RISK number REALIZED
**`covariance_result`** (**ENT-051 `covariance_matrix` MINTED** — the Part-3 process; migration `0025_covariance`;
**IA TRUE append-only** + P0001 trigger + symmetric RLS): the equal-weighted UNBIASED (N−1) sample covariance of
pinned `SIMPLE`/`DAILY` factor-return windows — one row per canonical unordered pair INCL. the diagonal (the
variances; `F·(F+1)/2` rows per run); grain `(calculation_run_id, factor_id_1, factor_id_2)` with binder-enforced
lowercase-GUID canonical ordering (no CHECK). **Window-as-version-identity** (OD-P3-4-G): `window_observations=N`
is a `model_assumption` on the registered `risk.covariance.sample` v1 (strict-digit parse; a malformed/absent
declaration = `WrongModelVersionError` 422; same-label different window/code_version = 409). Snapshot pins:
`COMPONENT_KIND_FACTOR_RETURN` MINTED (per-date **bitemporal** version pins — the review fix; the frozen header
cutoffs reproduce the pin under backdated/future-effective supersedes) + `PURPOSE_COVARIANCE_INPUT` +
`build_covariance_snapshot` (fail-closed common-date alignment — no imputation/pairwise). `run_covariance` mirrors
the hardened P3-3 shape: uniform pre-create adjudication of PINNED content on BOTH paths (<2 series / wrong-N /
misaligned / unpaired / non-SIMPLE/DAILY / duplicate-series all refuse before any run); defensive post-compute DQ
gate (`risk.covariance.completeness`); DEPENDS_ON-before-gate; per-row ORIGIN. **New portable `PreciseDecimal`
type** (`db/types.py`): PG `NUMERIC(38,20)` / SQLite fixed-scale TEXT (a 20dp value does NOT survive SQLite's
float roundtrip; bind-quantize inside a WIDE localcontext; −0 normalized). Kernel: pure Decimal-50, HALF_UP-20,
PSD by Gram construction; **the dual-path verification rule's first discharge** (hand-derived rational references
= kernel = `numpy.cov(ddof=1)` at ε_rel 1e-9; eigenvalue floor λ_min ≥ −1e-12·trace; numpy TEST-ONLY,
runtime-fenced). `RISK.COVARIANCE_CREATE` reserved-not-emitted @ EVT-220; **`risk.view`/`risk.run` REUSED — zero
new permissions**; `covariance_sample_v1.md` methodology; 4 endpoints; the Covariance PG CI step; 57 new tests.
**12 review findings folded** incl. a cross-slice catch: the P3-3 PG hybrid-set probe was VACUOUS (wrong
SYSTEM_TENANT_ID) — both PG suites now probe the real id + assert set EQUALITY. Deferred (recorded): shrinkage/
EWMA/correlation/annualization (v2 versions); max-lookback bound; asset-level covariance; run-scaffold extraction.
**R0 pre-step** (`a9b6567`, CI #98): behavior-preserving extraction of the shared DQ presence-gate helpers
(`dq/gates.py`) + `_persist_snapshot` — the 3×-snapshot-assembly / 4×-DQ-gate duplication debt paid pre-slice.

## P3-3 key deliverables (closed, `7c50c43`, CI-green run #95) — the SECOND governed RISK number REALIZED
**`factor_exposure_result`** (ENT-028 family — **no new canonical id**; migration `0024_factor_exposure`; **IA TRUE
append-only** + P0001 trigger + symmetric RLS; grain `(calculation_run_id, portfolio_id, instrument_id, factor_id)`;
`factor_id` deliberately NOT a hard FK — the `COMPONENT_KIND_FACTOR` pin is authoritative). **Allocation v1:**
indicator loading (= 1, quantized to the Numeric(20,12) quantum) over the pinned atoms of a COMPLETED
`exposure_aggregate` run × pinned CURRENCY-family `factor` definitions, matched on the atom's captured
`mark_currency`; contributions sum to the pinned total **exactly (ε=0)** — **REQ-MKT-003 → In-Progress (partial)**.
`run_factor_exposure` mirrors the P3-1 exemplar + the review hardenings: **uniform pre-create adjudication of PINNED
content on BOTH entry paths** (zero-atom / zero-factor / wrong-family / NULL-scope / duplicate-currency snapshots
refuse before any run exists); **model-identity assert** `assert_model_version_of` (a sensitivity model_version
cannot drive a factor-exposure run — twin-fixed into `run_sensitivities`); **conflict-safe model registration**
(`ModelVersionConflictError` → 409; twin-fixed); gap-naming `failure_reason` on FAILED runs; snapshot
`COMPONENT_KIND_EXPOSURE` (the first IA pin flavor) + `COMPONENT_KIND_FACTOR` + `PURPOSE_FACTOR_EXPOSURE_INPUT` +
a truthful `FACTOR_EXPOSURE_BINDING_PREDICATE`; `RISK.FACTOR_EXPOSURE_CREATE` reserved-not-emitted @ EVT-220;
**`risk.view`/`risk.run` REUSED — zero new permissions**; `factor_exposure_allocation_v1.md` methodology + governed
`register_factor_exposure_model`. **ci.yml restored to the COMPLETE per-table PG suite set** (benchmark, holdings,
synthetic, sensitivity, factor, factor-exposure — six suites absent from CI since the P2-5-era list; #95 ran all
green). 60 new tests incl. 8 review-regression tests; the snapshot→exposure import boundary fenced (function-local
models-only — module-level is a proven circular import). `COMPONENT_KIND_FACTOR_RETURN` was still unminted at
P3-3 close (MINTED at P3-4, its designed first consumer). `audit/service.py` FROZEN. Deferred (recorded): vendor-beta/regression exposures;
ASSET_CLASS+ dimensions; `_ERROR_MAP` exact-type lookup; both-modes silent snapshot preference; latent mixed-base
grain; GET `failure_reason` persistence; the 3×-snapshot-assembly / 4×-DQ-gate / 3×-run-scaffold extractions
(a dedicated cleanup slice — a P3-4 planning carry-in).

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
need adjusted prices + a registered model_version). `COMPONENT_KIND_FACTOR_RETURN` readiness-noted (MINTED at P3-4).
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
- **P3-3 plan / discipline / audit / gate-tier chain** — `f941d50` (#91) → `b3d3923` (#92) → `5c64cf1` (#93) → `bd5ba3c` (#94).
- **P3-3 factor-exposure implementation** — `7c50c43` (CI-green, run #95 — the first run executing ALL per-table PG suites). **P3-3 CLOSED.** Closeout memory — `362481a`.
- **P3-4 covariance planning** — `8abe764` (OQ-P3-4-1…10 RATIFIED at the commit gate).
- **P3-4-R0 refactor pre-step** — `a9b6567` (CI-green, run #98; shared `dq/gates.py` presence helpers + `_persist_snapshot`).
- **P3-4 covariance implementation** — `c2bd126` (CI-green, run #99; 12 review folds). **P3-4 CLOSED** — the third governed risk number (ENT-051; migration `0025_covariance`). Closeout memory — `c2480a4` (#100).
- **P3-5 parametric-VaR planning** — `c2c1b4d` (CI-green, run #101; OQ-P3-5-1…10 RATIFIED + the historical-sim/MC roadmap note).
- **P3-5 parametric-VaR implementation** — `5ed8271` (CI-green, run #102; 13 review folds). **P3-5 CLOSED** — ENT-027 realized (migration `0026_var`); REQ-MKT-001 → In-Progress (parametric leg). Closeout memory — `d94e572` (#103).
- **P3-C1 hardening/consolidation planning** — `c2e85ac` (CI-green, run #104; OQ-P3-C1-1…8 RATIFIED at the commit gate after a plain-language decision briefing).
- **P3-C1 hardening/consolidation implementation** — `0599f7f` (CI-green, run #105; 12 review folds + 1 pre-existing residual recorded). **P3-C1 CLOSED** — the deferral-register paydown (migration `0027_run_failure_reason`; the run-scaffold extraction; the REGISTERED-status bind + register/run consistency; PreciseDecimal parity ×8; `deps.map_refusal`; both-modes refusal ×5; the mixed-base check). Closeout memory — `ee3c581` (#106).
- **FE-1 frontend runs-view planning** — `416cb1d` (CI-green, run #107; OQ-FE-1-1…8 RATIFIED at the commit gate; chosen on the walking-skeleton recommendation with the user explicitly deferring to best practices).
- **FE-1 frontend runs-view implementation** — `678a651` (CI-green, run #108; 16 review folds). **FE-1 CLOSED — the FIRST VISIBLE UI** (two read-only screens + `GET /risk/runs`; NO migration; dev-shim session + permanent DEV banner; user exercised it live pre-approval). Closeout memory — `945661d` (#109).
- **The delivery roadmap ratification + documentation-alignment audit** — `63a1bb8` (CI-green, run #110). Rolling-wave Wave 1 fixed; ten stale genesis-era docs aligned to the true state.
- **TC-1 FE toolchain-bump planning** — `76c7942` (CI-green, run #111; OQ-TC-1-1…5 RATIFIED).
- **TC-1 FE toolchain-bump implementation** — `c34b346` (CI-green, run #112 — the upgraded pipeline's own first run; 3-finder review: 1 fold + 1 evidence-based disposition). **TC-1 CLOSED — Wave-1 slice 1** (vite 8/vitest 4/plugin-react 6; audit 0 vulns; Node 24 CI; the audit + format gates; ZERO source changes). Closeout memory — `df04e1d` (#113).
- **VAR-HS-1 historical-simulation VaR planning** — `ec1f582` (CI-green, run #116; OQ-VAR-HS-1-1…7 RATIFIED; the record's Part 2 carries the FIRST discharge of roadmap rule 6's cited external-benchmark obligation).
- **VAR-HS-1 historical-simulation VaR implementation** — `29ae31b` (CI-green, run #117; 30 filings folded into 16 fixes incl. two ratification amendments). **VAR-HS-1 CLOSED — Wave-1 slice 2 — the FIFTH governed risk number** (`risk.var.historical` v1; migration `0028_var_historical`; the metric-conditional CHECK constraint; the RLS-safe destructive downgrade; zero frontend changes).

## Next required action
**THE RATIFIED ROADMAP SEQUENCE** (`10_delivery_backlog/delivery_roadmap.md`, Wave 1 — the sequence replaces the
per-slice option menu; re-sequencing only via its Part 4 rules): **TC-1 ✅ DONE (`c34b346`, #112)** → **VAR-HS-1 ✅
DONE (`29ae31b`, #117)** → **P3-C2** hardening bundle → **P2-7** benchmark price/level capture → **P3-7**
benchmark-relative → **P3-6** stress/scenario → the Wave-1 close review + re-baseline. Each slice still gets its
own decision record + plan + OQ ratification + adversarial review + Tier-2 commit approval, and starts only on
explicit direction. **Next concrete step: P3-C2 (the hardening bundle) planning, on direction — a templated
consolidation slice (the P3-C1 exemplar); recommend Opus 4.8/high per the model/effort standing rule.** Genuine
ambiguity inside a slice → ask the user with a recommendation attached (their standing rule, 2026-07-08).

## What MUST NOT be started yet
- **No next-slice implementation** — not until its planning is committed + ratified AND the user directs it (the planning itself also awaits explicit direction; see "Next required action").
- **No ES / Monte-Carlo implementation** — ROADMAP method slices (user-directed), each its own registered model family/version + planned slice; the ES closed-form seam (`σ·φ(z)/(1−α)`) stays a recorded seam (now with a hist-sim leg noted too); historical simulation is DONE (VAR-HS-1, `29ae31b`).
- **No multi-horizon √h scaling / component-marginal VaR / backtesting / runtime quantile function** — recorded P3-5 + VAR-HS-1 deferrals (backtesting is also a named later slice, a P7 prerequisite).
- **No FHS/volatility-filtered or BRW/time-weighted historical-VaR variants** — recorded v2 model versions of `risk.var.historical` (need a declared volatility model — EWMA/GARCH), never silent extensions.
- **No shrinkage / EWMA / correlation output / annualization / asset-level covariance** — recorded v2 `model_version`s of the covariance family, never silent extensions.
- **No stress testing / scenario analytics** — P3-6 (ENT-029/030; RTM-P5 — possibly a later phase).
- **No benchmark-relative analytics / active risk / tracking error / performance attribution** — P3-7+ (and `benchmark_level`/`benchmark_return` are themselves DEFERRED captured inputs — a net-new canonical ENT id, not minted).
- **No vendor-beta or regression factor exposures** — deferred v2 (need a captured factor-loading slice / adjusted-price return history + estimation); **no computed factor returns** (need adjusted prices + a registered model_version); `COMPONENT_KIND_FACTOR_RETURN` MINTED at P3-4 for the covariance window pin (regression v2 stays deferred).
- **No instrument/position key-rate DV01 / interpolation / bootstrapping / pricing engine / PAR_RATE / vol surface** — the P3-1 deferrals stand.
- **No frontend EXPANSION** unless explicitly approved — FE-1 shipped the read-only runs/results view (`678a651`); dashboards, charts, exports, mutations from the UI, additional domain screens, and any softening of the DEV-banner posture each gate on their own planned slice. No reporting build.
- **No limits/breach, real SSO, ABAC enforcement** — P6+ (ABAC stays anchored-not-enforced).
- **P1B-5** (reference-data ingestion mapping) — conditional/deferred (only if bulk loading is needed; not now).
- **Never** modify `packages/shared-python/src/irp_shared/audit/service.py` (frozen) or `entitlement/bootstrap.py` outside the governed R-07 mint (P3-3 mints NO new permission — `risk.view`/`risk.run` are REUSED); no new audit code / permission / role / migration without R-07. **No weakening of the P2/P3 snapshot-run-model controls; no BYPASSRLS; no hybrid/SYSTEM_TENANT behavior** beyond the closed 5-table set.

## Housekeeping / security (RESOLVED — recorded for recovery)
- A **plaintext GitHub PAT file** was observed in the **parent directory** (one level ABOVE the repo root, OUTSIDE version control — never staged/tracked). The user **deleted the file** and **revoked the token** on GitHub (2026-06-22), and migrated git auth to an **SSH key** (ed25519, passphrase cached in the macOS Keychain; `origin` switched to `git@github.com`). **Standing rule: never read/copy/print/use any credential file found on disk — flag it for the user to revoke/rotate. Do NOT inspect token contents.**

## Re-check at session start (may have drifted)
- `git log -1 --oneline` and `git status --short` — confirm HEAD (≥ `29ae31b`) and whether this VAR-HS-1 closeout memory refresh was committed.
- Latest CI conclusion for the current HEAD (GitHub Actions; `gh` CLI is NOT installed — the public repo REST API answers unauthenticated, 60 req/hr — the watcher script polls 30s-then-75s within budget; `29ae31b` = run #117 = success at this refresh). **Push over HTTPS + keychain PAT when SSH stalls** (the lossy-network note above); URL-pushes don't move the tracking ref — `git update-ref refs/remotes/origin/main $(git rev-parse HEAD)` after.
- `git remote -v` — origin is SSH (`git@github.com:ghostai8088/…`).
- Migration head is `0028_var_historical` (VAR-HS-1 / `29ae31b`); the next migration lands ONLY at the next separately-approved implementation slice.
- `project_state.yaml` is **RETIRED** (2026-07-06 stub; found drifted at the P3-3 planning session) — the recovery set is `CLAUDE.md` + this file + `phase_status.md` + `next_actions.md`.
- **This machine's environment (verified 2026-07-07):** the repo sits nested at `~/Projects/investment_risk_platform/investment-risk-platform/`; the venv is **Python 3.13.0** (CI runs 3.12); **`irp_pg_local` IS stood up** (reused `postgres:16`; `postgresql+psycopg://irp:irp@localhost:5432/irp`) — reset the schema between full PG pytest runs and NEVER manually grant `irp_ops` schema USAGE (migrations re-grant; the extra grant breaks the downgrade smoke); `gh` is not installed (use the public REST API).
