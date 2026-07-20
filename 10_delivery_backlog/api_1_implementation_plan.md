# API-1 Implementation Plan — the governed read surface (read-only)

Companion to `api_1_decision_record.md` (OD-API-1-A…H, RATIFIED with the verifier reshape). **Pure read-only: no migration, no write endpoints, no permission mint; `audit/service.py` FROZEN; the run-id reads + TR-09 untouched.** One commit per step; each green through `make check`; the 4-finder review + full-PG battery before push.

## Step 1 — The shared read helper
Factor the CC-2 pacing read pattern into a small shared helper (the `CalculationRun`-join + `status=='COMPLETED'` + `system_from <= as_of` filter + `system_from DESC, run_id DESC, <grain> ASC` ordering) IF ≥3 families would otherwise carry byte-identical copies (the clean-code bar; else keep per-family). Home: a read-utility in `calc/` or a per-package mirror of `pacing/service.py`. Unit-test the helper against the pacing golden (behavior byte-identical to `list_pacing_projections`).

## Step 2 — Class A entity reads (8 families)
Per family, add to its `service.py` a `list_{family}(portfolio_id?, instrument_id?/benchmark_id?, as_of?)` + `latest_{family}(entity…, as_of?)` (the pacing shape), gated the family's existing `.view`. **Single-book families** (portfolio_return, benchmark_relative, desmoothed, var_backtest, es_backtest, proxy_weight) = verbatim. **Subtree-spanning** (exposure_aggregate, factor_exposure_result) = ROW-FILTER to the queried portfolio; `/latest` = newest COMPLETED run containing an entity row (docstring: "may be an ancestor's subtree run; rows returned are the entity's own"). Endpoints in the routers (`api/{risk,perf,exposure}.py`) mirroring `api/pacing.py`. Endpoint tests: entity filter, `as_of` cutoff, latest determinism, silent-empty on foreign id, 404 on `/latest` when none, the auditor `.view` parity where the family includes auditor.

## Step 3 — Class B latest-run resolvers + parity by-id GETs
`GET /{covariance,scenario,sensitivity}/latest[?filter]` (newest COMPLETED run + its rows): covariance (no entity filter), scenario (`scenario_definition_id`), sensitivity (curve selector). Add the two missing by-result-id GETs: `GET /risk/scenario-results/{id}` + `GET /risk/proxy-weight-estimates/{id}` (gated `risk.view`) — closing the house-pattern asymmetry. Tests.

## Step 4 — The F2 governance reads
- **Validation findings/evidence:** `GET /models/{model_id}/validations/{validation_id}` detail returning findings + evidence (query over the existing `model_validation_finding`/`_evidence` tables), gated `model.inventory.view`.
- **`tier` on inventory:** add `tier` + `validation_status` (already columns on `model`) to `ModelSummary`; a pure DTO change.
- **Snapshot listing:** `GET /snapshots?purpose&as_of_valuation_date&…` gated the existing `snapshot.view`; silent-empty; RLS-scoped.
- **Audit read:** NEW `audit/queries.py` (read-only, NEVER `audit/service.py`) + NEW `api/audit.py` router `GET /audit/events?entity_type&entity_id&event_type&since&until` (paginated), gated `lineage.view`; register in `main.py`. Tests incl. the RLS-isolation assertion (a tenant sees only its own events — the non-superuser precedent) + metadata-only shape.

## Step 5 — Demo stage 10 (the 5 zero-run codes; pays OQ-W7C-5)
`demo/{zero-padded}stage10.py` + runner + CI step: exercise `risk.sensitivity.analytic`, `risk.active_risk.parametric`, `risk.scenario.factor_shock`, `perf.benchmark_relative`, and a proxy-mode `risk.factor_exposure.proxy` run on the living tenant (all 5 already registered — runs-only; counts move 96 → 96+N COMPLETED, codes 20 / records 35 UNCHANGED barring a legitimately-warranted AWC). **Filename zero-padded** (`stage10` sorts before `stage2` — the CC-2-recorded caveat). Then the new Class-A/B reads render non-empty for those families (assert in the stage suite). CI step after stage 9, before the downgrade smoke.

## Step 6 — Docs
`ui_read_surface_assessment.md` F1/F2 marked IN-PROGRESS (API-1 discharges the entity-native reads + the 4 governance reads; Class-C VaR read → API-1b); the thesis-§2.3 machine-readability clause noted as advanced; a short read-surface note in the relevant methodology/API docs if warranted; API-1b named in the roadmap Part 2.12 as the fast-follow.

## Step 7 — Battery + review + push
Full fresh-schema local-PG battery (the ordered demo suites incl. stage 10 + all endpoint suites) + `make check` + the 4-finder review (adversarial: read-filter correctness + the subtree row-filter; numeric: n/a — read-only; doctrine: RLS on every new read + the frozen-service fence + no-write/no-migration; scope-fence: the read-only touch-list) + folds + push the impl PR.

## Scope fence (the touch-list)
NEW: `audit/queries.py`, `api/audit.py`, `demo/stage10*.py` + runner + suites, the per-family read functions + endpoints, endpoint/read tests, the doc updates. CHANGED (additive-only): each family `service.py` (+read funcs), the routers (+read endpoints), `api/models.py` (`ModelSummary` +2 fields; the validation detail endpoint), `api/snapshots.py` (+list), `snapshot/service.py` (+list query), `main.py` (+audit router), `ci.yml` (+stage-10 step). FROZEN/UNTOUCHED: `audit/service.py`; ALL migrations (none added); every write/mutating path; the 5-table hybrid set; the run-id reads; the FE (FE-2 owns it). ZERO migration.
