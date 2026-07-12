# Next Actions

> **As of HEAD `ad3d3fe` (merge of PR #8 = `c9d41a7`, PA-0 private-asset foundations, ENT-019 + migration 0034;
> CI green; refreshed 2026-07-11).** What to do
> next, the exact prompts, and the gates. **Nothing proceeds without explicit user approval.** Re-verify `git status` /
> HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE (all pushed + CI-green, verified live via the GitHub REST API):** the P2 closeout / P3 readiness review (`bb73211`,
re-trigger `6663452` = CI **#86**) → **P3-0** risk-analytics decision record + P3 implementation plan (`07607a5`, **#87**;
OD-P3-0-A…N ratified — analytic-sensitivities-first, the derived-number output contract, `RISK.*`@EVT-220 +
`risk.view`/`risk.run` reservations, methodology framework at `05_analytics_methodologies/`) → **P3-1 plan** (`1a8b2a4`,
**#88**) → **P3-1 IMPLEMENTATION** (`e8e2e59`, batch-pushed, covered by CI **#89**): ENT-028 `sensitivity_result` — the
first reproducible governed RISK number (curve-node analytic DV01/spread-DV01; migration `0022_sensitivity`; IA TRUE
append-only; run+snapshot+**registered model_version** bound — CTRL-003 now EXECUTABLE; `COMPONENT_KIND_CURVE` +
`PURPOSE_SENSITIVITY_INPUT`; `risk.view`/`risk.run` minted; `RISK.SENSITIVITY_CREATE` reserved-not-emitted;
`05_analytics_methodologies/` framework + `sensitivities_analytic_v1.md`) → **P3-2 plan** (`5466a09`, batch-pushed) →
**P3-2 IMPLEMENTATION** (`402cb12`, CI **#89** green): net-new `factor` EV definition + ENT-025 `factor_return` FR
captured series (migration `0023_factor_return`; captured INPUT — NO run/model/snapshot; `MARKET.FACTOR_RETURN_*` +
`REFERENCE.*` audit; `marketdata.view`/`.ingest` reused; symmetric RLS, NEITHER table append-only; VENDOR_FACTOR ORIGIN
lineage) → **P3-2 closeout / P3-3 readiness handoff** (`c452229`, CI **#90** green).

**DONE — the P3-3 planning commit (`f941d50`, CI #91 green):**
1. `10_delivery_backlog/p3_3_decision_record.md` (OD-P3-3-A…O + OQ-P3-3-1…9 recommended defaults) and
   `10_delivery_backlog/p3_3_factor_exposure_implementation_plan.md`: the **factor-exposure engine (allocation v1)** —
   indicator-loading CURRENCY-family factor exposures over the pinned atoms of a COMPLETED `exposure_aggregate` run
   against the P3-2 `factor` definitions; a governed DERIVED number mirroring the P3-1 `sensitivity_result` exemplar
   (snapshot + run + **registered model_version** + IA append-only + `risk.*` reuse + fail-closed DQ); vendor-beta /
   regression exposures and `factor_return` consumption honestly DEFERRED; migration `0024_factor_exposure` planned
   (NOT built).
2. Resume-anchor housekeeping: `docs/project_memory/{current_state,next_actions,phase_status}.md` refreshed to
   P3-0/P3-1/P3-2 DONE, head `0023_factor_return`, CI #89/#90; the stale degraded-mode "LOCAL-ONLY / push-CI-PENDING"
   qualifiers replaced with "committed `402cb12`, CI #89 green" in the 5 governance docs
   (`canonical_data_model_standard` / `audit_event_taxonomy` / `temporal_reproducibility_standard` /
   `entitlement_sod_model` / `control_matrix_skeleton`).

**DONE since:** the operating-discipline modernization (`b3d3923`, #92) → the retrospective model-upgrade audit +
status-decay fixes (`5c64cf1`, #93) → the gate tiers + OQ-P3-3 ratification (`bd5ba3c`, #94) → **P3-3 IMPLEMENTATION
(`7c50c43`, CI #95 green)**: the factor-exposure engine (allocation v1) — `factor_exposure_result` (ENT-028 family,
migration `0024_factor_exposure`), `run_factor_exposure` with uniform pre-create adjudication of pinned content on
both entry paths, the model-identity assert (twin-fixed in sensitivities), conflict-safe model registration,
`risk.*` reuse (no new permission), the methodology doc, 60 new tests, and **ci.yml restored to running ALL
per-table PG suites** (six were missing since P2-5-era; #95 executed them all green). The max-effort /code-review
fallback filed 15 findings; 11 folded pre-commit; 4 deferred with rationale (see the ReportFindings record +
`p3-3` memory). `irp_pg_local` is stood up on this machine (reset recipe incl. the 0003-exact `irp_ops` re-grants
is in the session memory).

**DONE since:** **P3-4 PLANNING** (`8abe764`; `p3_4_decision_record.md` OD-P3-4-A…P + the plan; OQ-P3-4-1…10
RATIFIED at the commit gate) → **P3-4-R0 refactor pre-step** (`a9b6567`, CI **#98** green — shared `dq/gates.py`
presence helpers + `_persist_snapshot`; the 3×-snapshot-assembly/4×-DQ-gate duplication debt paid; run-scaffold
extraction stays deferred) → **P3-4 IMPLEMENTATION (`c2bd126`, CI #99 green)**: the covariance engine (sample v1)
— `covariance_result` (**ENT-051 MINTED**, migration `0025_covariance`), `run_covariance` with the
declared-window-as-version-identity contract + uniform pre-create adjudication on both paths,
`COMPONENT_KIND_FACTOR_RETURN` bitemporal window pins, the portable `PreciseDecimal` type, `risk.*` reuse (no new
permission), the methodology doc, the Covariance PG CI step, 57 new tests incl. the dual-path numeric legs
(hand-derived rational references + `numpy.cov` cross-check + eigenvalue PSD — the standing rule's first
discharge). The independent 6-finder review confirmed + folded **12 findings** pre-commit (log =
`p3_4_decision_record.md` Part 7; incl. the cross-slice vacuous-hybrid-probe fix in BOTH PG suites); nothing
deferred from this review.

**DONE since:** **P3-5 PLANNING** (`c2c1b4d`, CI **#101** — OQ-P3-5-1…10 RATIFIED; the user additionally set the
**historical-sim + Monte-Carlo ROADMAP** direction) → **P3-5 IMPLEMENTATION (`5ed8271`, CI #102 green)**: the
parametric-VaR engine (delta-normal v1) — `var_result` (**ENT-027 REALIZED**, migration `0026_var`), `run_var`
with the declared-parameter identity + both-path adjudication (coverage/canonical-order/magnitude/malformed-content
gates) + own-tenant provenance re-resolution (the review's principal fold — PG FK checks bypass RLS), the
`VAR_INPUT` snapshot pins, `PreciseDecimal` σ/VaR, the methodology doc, the VaR PG CI step, 52 new tests incl. the
dual-path exactness legs. Independent 6-finder review: **13 findings folded**, 2 deferrals recorded
(`p3_5_decision_record.md` Part 7). **REQ-MKT-001 → In-Progress (parametric leg).**

**DONE since:** **P3-5 closeout memory** (`d94e572`, CI #103) → **P3-C1 PLANNING** (`c2e85ac`, CI **#104** —
`p3_c1_decision_record.md` OD-P3-C1-A…H + `p3_c1_implementation_plan.md`; **OQ-P3-C1-1…8 RATIFIED at the commit
gate after a plain-language decision briefing** — the standing presentation calibration) → **P3-C1 IMPLEMENTATION
(`0599f7f`, CI #105 green)**: the hardening/consolidation slice — the deferral-register paydown, NO new governed
number. The REGISTERED-status bind at the risk gate (`assert_model_version_of` → `UnregisteredModelError`) + the
review's principal fold: **register/run consistency** (all four governed registrars refuse a non-REGISTERED
same-label twin, `WrongModelVersionError` 422); **persisted `calculation_run.failure_reason`** (additive migration
`0027_run_failure_reason`; FAILED-only; audit payload unchanged; the four GET-run endpoints surface it; reason
formats verbatim); **the run-scaffold extraction** (`risk/scaffold.py::execute_governed_run` ×4 risk binders) under
the R0 bar, proven by **golden captures written green PRE-extraction** (audit/lineage/DQ CONTENT + exact reason
formats; re-run against the stashed pre-extraction code); `PreciseDecimal` parity ×8 result columns (NO migration);
the MRO-walking `deps.map_refusal` ×3 routers; both-modes ambiguity refusal ×5 binders (every build-mode arg incl.
as-of); the P3-3 mixed-base adjudication check. **Independent 6-finder review: 12 findings folded**, 1 pre-existing
residual recorded (the DQ-rule first-registration race) (`p3_c1_decision_record.md` Part 7). 1111 PG-backed tests;
a FAILED run now executes on PG in CI.

**DONE since:** **P3-C1 closeout memory** (`ee3c581`, CI #106) → **FE-1 PLANNING** (`416cb1d`, CI **#107** —
`fe_1_decision_record.md` OD-FE-1-A…H + `fe_1_implementation_plan.md`; **OQ-FE-1-1…8 RATIFIED**; chosen on the
walking-skeleton recommendation, the user explicitly deferring to best practices over their own preference — they
coincided) → **FE-1 IMPLEMENTATION (`678a651`, CI #108 green)**: **the platform's FIRST VISIBLE UI** — the
read-only "risk runs & results" view. Two screens (runs list: 4 RISK families / filters / has-more pagination /
truncated reasons / row click-through; run detail: `/runs/:family/:runId` deep links, provenance verbatim,
per-family result tables, FAILED reason prominent, **decimal strings byte-for-byte**) + the ONE backend addition
`GET /risk/runs` (`risk.view`; the EXPOSURE_AGGREGATE fence; fail-closed filters; deterministic order; NO audit on
reads; NEW `irp_shared/risk/queries.py`). Dev header-shim session + the permanent DEV banner; enforcement
server-side; NO migration; runtime deps = react/react-dom/react-router-dom only. **Independent 6-finder review: 16
findings folded** (record Part 7 — incl. 2 stale-response races, runId URL-injection, the has-more pager, the
fence-test re-pin with the real `EXPOSURE_AGGREGATE` witness, NEW `test_risk_runs_pg.py` + its ci.yml step, and
the row-click miss the USER caught exercising the view live). Full-PG 1119 passed; frontend 37 vitest; the demo
run-book verified end-to-end (`apps/frontend/README.md`).

**DONE since:** FE-1 closeout memory (`945661d`, #109) → **the RATIFIED delivery roadmap + documentation-alignment
audit** (`63a1bb8`, #110) → **TC-1 PLANNING** (`76c7942`, #111; OQ-TC-1-1…5 ratified) → **TC-1 IMPLEMENTATION
(`c34b346`, CI #112 green — the upgraded pipeline's own first run)**: vite 8.1.3 / vitest 4.1.10 / plugin-react 6
(+ shared-ts's own vitest — the hidden old-chain keeper); `npm audit` 0 vulnerabilities full-tree; ZERO source
changes; CI frontend job → Node 24 + the blocking `npm audit --omit=dev --audit-level=high` gate + `format:check`;
3-finder review (supply-chain CLEAN; behavior parity CLEAN with mutation-probes proving the FE-1 fences bite;
the moderate-runtime-advisory gap folded into OD-TC-1-D; one observed-once test exit dispositioned 12/12-serial-green).

**DONE since:** TC-1 closeout memory (`df04e1d`, #113) → **VAR-HS-1 PLANNING** (`ec1f582`, CI **#116** —
`var_hs_1_decision_record.md` OD-VHS-A…G + `var_hs_1_implementation_plan.md`; **OQ-VAR-HS-1-1…7 RATIFIED**; the
record's Part 2 carries roadmap rule 6's FIRST discharge — cited external benchmarks: BoE WP525, Pritsker 2006,
arXiv 2505.05646, BIS d305/d457) → **VAR-HS-1 IMPLEMENTATION (`29ae31b`, CI #117 green)**: **the platform's FIFTH
governed risk number and second VaR method** — plain equal-weight factor-based historical simulation
(`risk.var.historical` v1; the empirical lower order statistic over pinned factor-return windows, no
distributional assumption). Reuses `var_result` (`metric_type='VAR_HISTORICAL'`) via additive migration
`0028_var_historical` (z_score/sigma/covariance_run_id nullable, GUARDED by a new metric-conditional
`ck_var_result_parametric_not_null` CHECK — the parametric invariant stays DB-enforced); the downgrade is
DESTRUCTIVE + RLS-safe (deletes hist-sim rows; disables FORCE RLS + the append-only trigger transactionally —
cycled twice in both directions with real exit codes over suite-created data). New snapshot purpose
`VAR_HS_INPUT` + `build_var_hs_snapshot`; two new endpoints; reads reuse the EXISTING parametric VaR GET family +
the FE-1 listing with **zero frontend changes**. **Independent 6-finder review: 30 filings folded into 16 fixes**,
incl. TWO ratification amendments (OD-VHS-E tightened — the adequacy floor still permitted the sample minimum at
its own boundary, now strict `N·(1−c)>1`, 21@0.95/101@0.99, closing the generic-registration bypass too;
OD-VHS-C widened — the third nullable column + the CHECK constraint + the RLS-safe destructive downgrade), kernel/
binder precision fixes (the magnitude-FAILED gate was dead code — now reachable, test-proven both engines),
registry-honesty corrections, and a hand-minted adjudication vehicle driving 16 new gate-probe tests (incl. a
cross-tenant provenance regression that had silently survived the original 17-test suite). Full-PG 1142 passed.
→ **P3-C2 PLANNING** (`a4d0f89`, CI **#118** — `p3_c2_decision_record.md` OD-P3-C2-A…F; OQ-P3-C2-1…6 RATIFIED) →
**P3-C2 IMPLEMENTATION (`6fb1a13`, CI green)**: **Wave-1 slice 3 — the four-follow-up hardening paydown.** Exposure
adopts the shared `execute_governed_run` scaffold (RELOCATED `risk/scaffold.py`→`calc/scaffold.py` so exposure
adopts it without crossing the one-way exposure↛risk fence — Part 4.5; FAILED exposure runs now persist
`failure_reason` + keep the DEPENDS_ON edge, COMPLETED byte-preserved to the P3-C1 golden bar); new
`exposure.view`-gated `GET /exposure/runs` + the FE runs view surfacing exposure as a fifth family (source-switch,
not merge — Part 4.6); `PreciseDecimal` parity for every captured decimal column with precision ≥16 (incl. the
`transaction` table via the review — NO migration, DDL-identical); the DQ-rule first-registration savepoint race.
**Full 6-finder review: 9 findings, ALL folded, no deferrals** (2 finders clean). Validation: make check 968 /
full-PG 1177 / alembic no-op / downgrade clean / fe-check 39+build / diff fence clean (30 files).
→ **P2-7 PLANNING** (`04c4135`, CI green — `p2_7_decision_record.md` OD-P2-7-A…H; OQ-P2-7-1…8 ratified; ENT-052
`benchmark_level`+`benchmark_return`, migration `0029`; captured returns ONLY). → **TD-1** (test-data realism
audit, Wave-1 slice **3.5** insertion): **PLANNING** `2569151` → **IMPLEMENTATION** `ac92e0b` + follow-up
`4534a38` (CI green). The base market-value fixtures were already plausible; 8 implausible values in the
factor-return/covariance/VaR/sensitivity/exposure test fixtures were remediated (three-bucket classify-then-fix;
test-and-docs only; NO golden re-derivation). **4 independent finder passes corrected 2 author errors + caught 2
same-class completeness misses**, all folded. NEW `08_testing_qa/test_data_realism.md` + a standing review-angle;
the fixture-realism rule is now in force for all future slices. → **P2-7 IMPLEMENTATION (`ea2863d`, CI green)**:
Wave-1 slice 4 — the net-new **ENT-052** (`benchmark_level` + `benchmark_return`, two FR bitemporal captured-input
tables under the ENT-009 header; migration `0029`). Captured vendor-published returns ONLY (no calc from levels);
`level_type`/`return_basis` variant discriminators; a `_SeriesSpec`-parameterized binder; race-safe DQ from birth;
six additive `MARKET.BENCHMARK_LEVEL_*`/`_RETURN_*` codes; no new permission. **Full 6-finder review: ~10 findings
folded, no deferrals, no shipped logic bug** (a real forced-collision race test + a genuinely float-unsafe
precision value among the folds). Discharges OD-P2-6-K; unblocks P3-7. → **P3-7 PLANNING** (`552b954` —
`p3_7_decision_record.md` OD-P3-7-A…H; OQ-P3-7-1…10 RATIFIED; Part 2 = the rule-6 external-benchmark section:
Roll 1992, Grinold-Kahn 2000, Pope-Yadav 1994, CESR/10-788, ESMA 2012/832, MSCI Barra) → **P3-7 IMPLEMENTATION
(`65e6dbe`, CI #130 green)**: **Wave-1 slice 5 — the SIXTH governed risk number**, ex-ante active risk /
parametric tracking error `TE = √(wₐᵀΣwₐ)` — `active_risk_result` (ENT-027 third realization, migration
`0030_active_risk`, IA append-only, symmetric FORCE RLS, hard-FK provenance incl. `benchmark_id`); the
`ACTIVE_RISK_INPUT` snapshot pinning FACTOR_EXPOSURE + COVARIANCE + FACTOR + the newly minted
`COMPONENT_KIND_BENCHMARK` (FR-version pins, TR-09); registered `risk.active_risk.parametric` v1
(code_version-only identity); run family `ACTIVE_RISK` ≠ metric `TRACKING_ERROR` (a review amendment to OD-F);
EX-ANTE only (ex-post deferred on the portfolio-return prerequisite, OD-G). **The FIRST user-directed FULL
max-effort multi-agent review ("ultrareview"): 10 finder angles → 6 empirical verifiers → a gap sweep — 21
findings folded** (adjudication hardening each test-pinned; kernel overflow → committed FAILED never a 500;
the `fexp-rows` binding-predicate rename + import-time varchar(50) guard; **3 previously-missing CI PG RLS
steps** incl. two pre-existing gaps), 3 refuted/rejected-as-designed, **3 recorded-deferred** (record Part 6:
the `var_service.py` TypeError/base_currency twins; the shared covariance-pin adjudicator; `_persist_snapshot`
lineage batching). Validation: make check 1044 / full-PG 230 / downgrade smoke / fe-check 43+build.

**NEXT — per the RATIFIED `10_delivery_backlog/delivery_roadmap.md` (Wave 1; no option menu — the sequence IS the
decision; re-sequencing only via its Part 4 rules):**
1. ✅ **TC-1 — FE toolchain bump** — **DONE (`c34b346`, CI #112)**
2. ✅ **VAR-HS-1 — historical-simulation VaR** — **DONE (`29ae31b`, CI #117)**
3. ✅ **P3-C2 — hardening bundle** — **DONE (`6fb1a13`, CI green)** (exposure scaffold/reason + FE listing;
   captured-table PreciseDecimal parity incl. `transaction`; the DQ-rule registration savepoint race; scaffold
   relocated risk→calc; full 6-finder review, 9 folds; NO migration)
3.5. ✅ **TD-1 — test-data realism audit** — **DONE (`ac92e0b` + `4534a38`, CI green)** (a hygiene insertion; 8
   implausible test fixtures remediated to the new fixture-realism standing rule; test-and-docs only; 4 independent
   finder passes; `08_testing_qa/test_data_realism.md` + a standing review-angle)
4. ✅ **P2-7 — benchmark price/level capture** — **DONE (`ea2863d`, CI green)** (ENT-052 `benchmark_level`+
   `benchmark_return`, migration `0029`; captured returns only; full 6-finder review, ~10 folds; unblocks P3-7)
5. ✅ **P3-7 — benchmark-relative analytics (ex-ante)** — **DONE (`65e6dbe`, CI #130 green)** (the SIXTH governed
   risk number; ultrareview 21 folds + 3 recorded deferrals; ex-post leg deferred on the portfolio-return
   prerequisite)
5.5. ✅ **P3-C3 — binder adjudication consistency** — **DONE (`1bf172b`, CI #132 green)** (a hardening CARRY-IN,
   Part 4 rule 3, paying the P3-7 item-A deferral: `TypeError` + `base_currency` shape gate across var/var_hs/
   factor so every binder fails-close identically on malformed pins; factor also gained the malformed-pin wrapper
   it lacked. Test-and-binder only; NO migration. Items B+C re-deferred, record OD-E)
6. ✅ **WAVE 1 CLOSED** — **`wave_1_close_review.md` RATIFIED (2026-07-09, OQ-W1C-1…6)**: honest audit +
   reconciled deferral register (all P3-3/P3-5/P3-C1 deferrals PAID in-wave; open items trigger-based) + the
   outward benchmark review + the thesis destination check. P3-6 moved to Wave 2 slot 5 (pre-authorized). The
   npm-audit CI gate tightened high→moderate at this close (tree at 0); **branch protection (OD-050) ✅ DONE
   2026-07-10** (`enforce_admins=everyone` + 5 required CI checks — no direct pushes to `main`; PR flow binds
   everyone from P3-8 on; the repo's first PRs are the P3-8 planning + implementation commits).

**WAVE 2 (ratified — roadmap Part 2.5): PM-1 → P3-8 → BT-1 → PA-0 → P3-6.** Organized around the return-series
triple unlock: ONE new primitive (a governed portfolio-return series) unblocks ex-post TE/IR (P3-7 OD-G), VaR
backtesting (the P7 prerequisite), and the private-asset desmoothing substrate (the thesis destination).
Each slice still: PLANNING ONLY first (decision record + plan + OQ ratification) → implementation on direction →
Tier-2 commit approval. **PM-1 (slice 1) is DONE** (`b2445c7` + ruff-format `f5e16b6`, CI #137 green — the SEVENTH
governed number + FIRST non-risk, the `perf` family; ENT-053, migration `0031`, `perf.run`/`perf.view` R-07 mint).
**P3-8 (slice 2) is DONE** (planning PR #1 `4880b36`; impl PR #2 `86ef3ec` merged as `d769f59`, CI #142; cleanup+
closeout PR #3 `962974f` merged as `503a9e2` — the 3 dedup folds per the clean-code standing bar). **BT-1 (slice 3)
is DONE** (planning PR #4 `3e81ef4` merged as `1da87c7`, OD-BT-1-A..K + OQ-BT-1-1..9 ratified; impl PR #5
`e7b615d` merged as `868f892`, CI green — the NINTH governed number: VaR backtesting, Kupiec POF + Basel
traffic-light zone over realized flow-adjusted P&L vs ONE VaR method's pinned forecasts, `var_backtest_result`
ENT-055, migration `0033`, run family `VAR_BACKTEST` reusing `risk.run`/`risk.view`; FULL 4-finder local review,
14 findings/13 folded; closes the Wave-1 close review's named nearest supervisory gap, SR 11-7 outcomes
analysis). **PA-0 (slice 4) is DONE** (planning PR #7 `07e5d6a` merged as `7a422aa` — the capture-first split ratified,
OD-PA-0-A..J + OQ-PA-0-1..8, the Okunev-White citation honestly flagged UNVERIFIED for PA-1; impl PR #8
`c9d41a7` merged as `ad3d3fe`, CI green — ENT-019 `proxy_mapping` REALIZED, migration `0034`, the
CURRENCY-family v1 scope ENFORCED per a review fold, `marketdata.*` reused; proportionate 2-finder review,
4 folds + 2 family-wide deferrals in the record Part 6). The next concrete steps, in order: **(1) land THIS
closeout PR** (branch `pa-0-closeout` — the Part 6 dispositions + this docs refresh; docs-only) — Claude
pushes on Tier-2 approval, the USER opens+merges after CI green; then **(2) P3-6 PLANNING, on explicit
direction** — stress/scenario, the LAST Wave-2 slice (ENT-029/030 scenario definitions + results; moved from
Wave 1 pre-authorized; MAY defer again at the Wave-2 close — an expected outcome, not a failure); then **(3)
the WAVE-2 CLOSE REVIEW** (the mandatory Part-4 rule-2 re-baseline: honest audit, deferral-register
reconciliation — now incl. the P3-8/BT-1/PA-0 Part-6 items — the outward benchmark review, the thesis
destination check, and the PA-1 sequencing decision: the desmoothing governed number is the natural Wave-3
opener, with the Okunev-White citation to resolve first). P3-6
IS a **methodology-adjacent slice** → roadmap Part 4 rule 6 applies; model/effort: **Fable / High** (scenario
definition/shock design is novel surface). **All new fixtures follow the TD-1 realism
rule.**

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — plan, implementation, and commit are distinct approvals.
- **Do not start the next slice's planning** until directed; do not start any implementation until its plan +
  sign-offs are ratified. The Wave-2 slices (PM-1, P3-8, BT-1, PA-0, P3-6), the VaR roadmap methods, and the
  trigger-based register items — each its own separately planned + approved slice.
- Commit/push follow the **gate tiers** (`claude_operating_instructions.md`): Tier 0/1 land-and-report; Tier 2/3
  (code, migrations, new slices, governed surfaces) need explicit approval.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  ALL per-table RLS/append-only PG suites (complete since `7c50c43`; Covariance added at `c2bd126`, VaR at
  `5ed8271`; the **Risk-runs-listing PG step** at `678a651`; the **Historical-VaR PG step** at `29ae31b`; the
  **Active-risk PG step + the two previously-MISSING steps** `test_benchmark_series_pg.py`/
  `test_exposure_runs_pg.py` added at `65e6dbe` — an ultrareview conventions finding: every new tenant table
  needs its CI RLS step AND the step must actually be added) + downgrade smoke, Documentation check, Secret
  scan. The **Frontend job (TC-1): Node 24, `npm audit --omit=dev --audit-level=high` (blocking), lint,
  typecheck, `format:check`, 43 vitest, build**. **HEAD `1bf172b` = run #132 = success** (REST-API watcher;
  #98–#132 all green; P3-7 impl #130 / closeout #131). Python 3.12 runners. Migration head `0030_active_risk`
  (P3-C3 added NO migration). **origin flipped SSH→HTTPS at P3-C3** (SSH:22 blocked on this network) — plain
  `git push` works over HTTPS + the cached PAT.
  **This machine:** venv = Python 3.13.0; `irp_pg_local` IS stood up (`postgres:16`). After a schema reset just run
  `alembic upgrade head` — migration 0003 re-grants `irp_ops` itself; **NEVER manually grant schema USAGE to
  `irp_ops`** (it breaks the `downgrade base` smoke at DROP ROLE; fixed 2026-07-07 with
  `REVOKE ALL ON SCHEMA public FROM irp_ops`).
  **Networking:** SSH to GitHub is flaky/blocked on some networks (PMTU-black-hole/lossy-link class) — HTTPS + the
  keychain-cached PAT is the reliable push path; the REST API always works for CI verification.
- **PG re-run gotcha:** don't run the full pytest twice against the same DB without a schema reset
  (`data_quality_pg`/`lineage_pg`/`synthetic_pg` self-seed a `GLOBAL_OK` system-tenant row) — `DROP SCHEMA public
  CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO irp;` then `alembic upgrade head`.

## Stop conditions (halt and ask)
- Any request to pull unplanned scope into the next slice: EX-POST tracking error / active return / IR (needs
  the governed portfolio-return series — a performance-measurement slice, OD-G), performance attribution,
  relative VaR, TE annualization, reporting/dashboards, frontend — refuse and flag. Regression/beta factor
  loadings, computed factor returns, covariance v2 (shrinkage/EWMA/correlation/annualization), the VaR deferrals
  (ES/√h/component-VaR/backtesting/quantile-function), and the P3-7 recorded deferrals (var_service
  TypeError/base_currency twins; the shared covariance-pin adjudicator; lineage batching) stay deferred named
  slices/versions until planned.
- Any change to **`audit/service.py`** (frozen) or **`entitlement/bootstrap.py`** outside the governed R-07 mint
  (P3-3/P3-4/P3-5/P3-C1 mint NO new permission — `risk.view`/`risk.run` are REUSED); any new audit code / permission /
  role / migration without R-07.
- Any weakening of the P2/P3 snapshot-run-model controls; any BYPASSRLS app path; any hybrid/SYSTEM_TENANT behavior
  beyond the closed 5-table set.
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
