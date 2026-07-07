# Next Actions

> **As of HEAD `c452229` / CI #90 (refreshed 2026-07-06, new machine — the Zscaler blockage is RESOLVED).** What to do
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

**IN THIS WORKING TREE (commit pending approval):** the **P3-3 planning commit** —
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

**NEXT — P3-3 IMPLEMENTATION (on explicit approval, after the planning commit + OQ-P3-3 sign-offs):** build the
factor-exposure engine per the committed plan. The exact kickoff prompt is
`p3_3_factor_exposure_implementation_plan.md` **Part 11**. Implementation is a SEPARATE approval from the plan commit.

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — plan, implementation, and commit are distinct approvals.
- **Do not start P3-3 implementation** until the P3-3 plan is committed AND the OQ-P3-3-1…9 sign-offs are ratified AND
  the user directs the build. Do not start P3-4+ (covariance), P3-5 (VaR/ES), P3-6 (stress), or P3-7
  (benchmark-relative) — each is its own later planned slice.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-entity RLS suites (through **Sensitivity** `0022` + **Factor** `0023`; the migration job auto-covers new
  heads — the P2-6/P3-2 precedent) + downgrade smoke, Documentation check, Secret scan. **HEAD `c452229` = run #90 =
  success; P3-2 impl `402cb12` = run #89 = success** (verified via the REST API — `gh` is not installed; the public
  repo answers unauthenticated). Python 3.12 runners; local validation also passes on 3.14 + full PG (`irp_pg_local`,
  `postgres:16`).
- **PG re-run gotcha:** don't run the full pytest twice against the same DB without a schema reset
  (`data_quality_pg`/`lineage_pg`/`synthetic_pg` self-seed a `GLOBAL_OK` system-tenant row) — `DROP SCHEMA public
  CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO irp;` then `alembic upgrade head`.

## Stop conditions (halt and ask)
- Any request to pull **P3-4+ scope into P3-3**: covariance/volatility estimation, VaR/ES, stress/scenario,
  benchmark-relative/active-risk/tracking-error, performance attribution, regression/beta estimation, factor-loading
  capture, computed factor returns, reporting/dashboards, frontend — refuse and flag; each is a separately planned slice.
- Any change to **`audit/service.py`** (frozen) or **`entitlement/bootstrap.py`** outside the governed R-07 mint
  (P3-3 mints NO new permission — `risk.view`/`risk.run` are REUSED); any new audit code / permission / role /
  migration without R-07.
- Any weakening of the P2/P3 snapshot-run-model controls; any BYPASSRLS app path; any hybrid/SYSTEM_TENANT behavior
  beyond the closed 5-table set.
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
