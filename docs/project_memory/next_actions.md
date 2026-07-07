# Next Actions

> **As of HEAD `5ed8271` / CI #102 (refreshed 2026-07-07).** What to do
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

**NEXT — THE NEXT-SLICE DECISION (on explicit direction; none pre-approved):**
1. **P3-6 stress/scenario planning** (ENT-029/030; REQ-MKT-004 — **RTM-phase P5**: flagged by the P3-0 record as
   possibly a later phase, not core P3).
2. **A VaR ROADMAP method slice** (user-directed 2026-07-07): factor-based **historical simulation** (feasible with
   current data; new model family; quantile-interpolation + window-adequacy declarations) or **Monte-Carlo** (gated
   on a seeded simulator + revaluation engine; binds `random_seed`, QS-18).
3. **The hardening/parity carry-ins** (recorded): the `assert_registered_model_version` status-bind check
   (cross-slice, all four binders); shipped result-column `PreciseDecimal` parity; run-scaffold extraction (third
   copy); `_ERROR_MAP` exact-type lookup; both-modes silent snapshot preference; latent mixed-base grain; GET
   `failure_reason` persistence.
4. **P3-7 benchmark-relative** (blocked for return-based analytics on the deferred `benchmark_level`/`return`
   captured-data slice).
Whichever is chosen: PLANNING ONLY first — decision record + implementation plan under `10_delivery_backlog/`.

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — plan, implementation, and commit are distinct approvals.
- **Do not start the next slice's planning** until directed; do not start any implementation until its plan +
  sign-offs are ratified. P3-6 (stress), P3-7 (benchmark-relative), the VaR roadmap methods, and the hardening
  carry-ins — each its own separately planned + approved slice.
- Commit/push follow the **gate tiers** (`claude_operating_instructions.md`): Tier 0/1 land-and-report; Tier 2/3
  (code, migrations, new slices, governed surfaces) need explicit approval.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  ALL per-table RLS/append-only PG suites (complete since `7c50c43`; Covariance added at `c2bd126`, VaR at
  `5ed8271`) + downgrade smoke, Documentation check, Secret scan. **HEAD `5ed8271` = run #102 = success**
  (REST-verified; #98–#102 all green). Python 3.12 runners.
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
- Any request to pull unplanned scope into the next slice: benchmark-relative/active-risk/tracking-error,
  performance attribution, reporting/dashboards, frontend — refuse and flag. Regression/beta factor loadings,
  computed factor returns, covariance v2 (shrinkage/EWMA/correlation/annualization), and the VaR deferrals
  (ES/√h/component-VaR/backtesting/quantile-function) stay deferred named slices/versions until planned.
- Any change to **`audit/service.py`** (frozen) or **`entitlement/bootstrap.py`** outside the governed R-07 mint
  (P3-3/P3-4/P3-5 mint NO new permission — `risk.view`/`risk.run` are REUSED); any new audit code / permission / role /
  migration without R-07.
- Any weakening of the P2/P3 snapshot-run-model controls; any BYPASSRLS app path; any hybrid/SYSTEM_TENANT behavior
  beyond the closed 5-table set.
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
