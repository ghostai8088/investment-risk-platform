# PA-1 Implementation Plan — private-asset desmoothing (build contract)

> Executes `pa_1_decision_record.md` (OD-PA-1-A…K) once OQ-PA-1-1…7 are RATIFIED. Ten steps, each
> mirroring a shipped exemplar; the kernel + methodology doc are the genuinely novel surfaces. Full
> validation + the 4-finder battery at Step 10. Delivered under the delivery-autonomy grant
> (checkpoint WIP commits at clean seams; the USER merges the final PR).

## The build sequence

1. **Migration `0036_desmoothed_return`** (exemplar: `0035_scenario`'s IA table): ONE table
   `desmoothed_return_result` — IA columns (`id/tenant_id/system_from`), the three governed FKs
   (`calculation_run_id`/`input_snapshot_id`/`model_version_id`), provenance FKs `portfolio_id` +
   `instrument_id`, `metric_type` (DESMOOTHED_RETURN | DESMOOTHING_SUMMARY), `period_start/end`
   (dates), `metric_value Numeric(20,12)`, echoes `observed_return Numeric(20,12)` /
   `begin_mark`/`end_mark Numeric(28,6)` / `alpha Numeric(20,12)` / `mark_currency String(3)`,
   summary evidence `observed_stdev Numeric(20,12)` / `n_periods Integer` (NULL off their rows).
   Grain unique `(calculation_run_id, metric_type, period_start)`. Symmetric FORCE RLS; P0001
   append-only trigger; `_IDENTIFIERS` import-time assert. Standard landing side effects: bump the
   15 `get_current_head()` asserts → `0036_desmoothed_return`; synthetic-slice next-slot guard
   `0036*` → `0037*`.
2. **ORM model** in `perf/desmoothed_models.py` (`__temporal_class__ = IMMUTABLE_APPEND_ONLY`;
   append-only ORM guard; registered in `models.py` + `__all__`) + vocab/metric constants and
   `RUN_TYPE_DESMOOTHED_RETURN` + `PERF_DESMOOTHED_RETURN_CREATE_EVENT_RESERVED` in `perf/events.py`.
3. **Kernel `perf/desmoothing_kernel.py`** (exemplar: `var_backtest_kernel`) — PURE functions:
   `observed_returns(marks) -> list[Decimal]` (simple returns, 12dp), `desmooth_geltner(observed,
   alpha) -> list[Decimal]` (the OD-D inversion, 12dp, seed-period dropped), `sample_stdev(values)`
   (Decimal-50 sqrt, 12dp). Property tests live here-adjacent (Step 8): α=1 identity;
   stdev-inflation on a positively-autocorrelated series; hand-derived golden.
4. **Model registration** in `perf/bootstrap.py` (exemplar: `register_var_backtest_model`'s
   declared-alpha): `register_desmoothed_return_model(…, code_version, alpha)` — strict-parsed
   `alpha` domain `0 < α ≤ 1` (registration-time 422), identity `(code_version, alpha)`, same-label
   conflict 409, race-safe helpers; SCENARIO-style ASSUMPTIONS (AR(1) structure; declared-α;
   per-observation step) + LIMITATIONS (single lag; offline α; irregular spacing; no FX).
5. **Snapshot support** (exemplar: `build_scenario_snapshot`): `PURPOSE_DESMOOTHING_INPUT` in
   `snapshot/models.py`; `build_desmoothing_snapshot(…, portfolio_id, instrument_id, window_start,
   window_end)` pinning the window's current-head `valuation` rows as REUSED
   `COMPONENT_KIND_VALUATION` (existing serializer + existing `_reresolve_content` branch — verify
   the branch handles this purpose's rows; NO new component kind); refuses an empty mark set
   pre-write; binding predicate registered.
6. **Binder `perf/desmoothing_service.py`** (exemplar: `scenario_service`): `run_desmoothed_return`
   — build-XOR-consume gate; `assert_model_version_of` + parse-back of declared α; pre-create
   adjudication of the PINNED marks (OD-H gates: ≥4 marks, positive, unique dates, uniform
   currency, uniform portfolio/instrument, `parse_strict_decimal`, the P3-C3 malformed-pin
   wrapper); kernel invocation; magnitude gate (`_MAX_RESULT_ABS = 1E8`) → post-create FAILED;
   `execute_governed_run` scaffold; `resolve_run_of_type` (the RD-1 shared helper — NO new copy);
   `list_desmoothed_results` + `resolve_desmoothed_return_run`; exports.
7. **API + FE** (exemplar: the P3-8 endpoint set): `POST /perf/models/desmoothed-return`,
   `POST /perf/desmoothed-returns/runs`, `GET /perf/desmoothed-returns/runs/{id}` (+ row read if
   the family pattern has one); error-map entries; `DESMOOTHED_RETURN` into `PERF_RUN_TYPES`
   (`perf/queries.py`) + the ratified-set guard test; FE `types.ts` FAMILIES/RUN_TYPE_TO_FAMILY/
   runDetailUrl/FAMILY_ROW_COLUMNS + FE tests.
8. **Tests**: SQLite `test_desmoothed_return.py` (kernel property tests + the FULL-STACK golden
   over a TD-1-realistic quarterly PE NAV series with its hand derivation; TR-09 both sides;
   refusal battery incl. every OD-H gate + α-domain + ambiguous-input + unregistered-model, each
   with `assert_no_running_orphan`; append-only / run_type≠metric / zero-`PERF.*`-audit /
   migration-head guards; the magnitude-FAILED boundary case); PG `test_desmoothed_return_pg.py`
   (RLS + append-only + forged-tenant + cross-tenant snapshot + audit chain — the scenario_pg
   template) + its CI step; endpoint `test_desmoothed_return_endpoint.py` (roundtrip golden,
   deny-by-default, refusals, no-mutate).
9. **Docs**: `05_analytics_methodologies/desmoothing_geltner_v1.md` (incl. the offline-α estimation
   procedure `α ≈ 1 − ρ₁` and the honest-uncertainty statement); canonical ENT-056 row (the mint);
   RTM REQ-PRV-005 note (the desmoothing leg lands; REQ does NOT close); taxonomy EVT-230 row
   appends `PERF.DESMOOTHED_RETURN_CREATE` reserved; a dated RESOLUTION note on OD-PA-0-I
   (Okunev-White verified — pointing at `pa_1_decision_record.md` OD-J); roadmap slice row at
   closeout.
10. **Full validation + review**: `make check`; local-PG clean-schema (FULL reset recipe) + drift +
    downgrade smoke; fences (frozen `audit/service.py`; no mint beyond the ratified reuse); the
    FULL 4-finder battery → fold → Part 6 dispositions → push branch → the USER merges → closeout.

## Standing constraints (unchanged)

Frozen `audit/service.py`; no BYPASSRLS; symmetric FORCE RLS; no new permission/audit/role (perf
pair REUSED); TD-1 fixture realism; golden-derivation comments; CI-watch-to-green; clean-code
standing bar (fold dedup findings; the RD-1 shared resolver is the only run-resolution path).
