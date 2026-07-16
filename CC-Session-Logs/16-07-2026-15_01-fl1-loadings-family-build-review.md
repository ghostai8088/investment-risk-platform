# Session Log: 16-07-2026 15:01 - FL-1 Loadings Family — Full Build + 4-Finder Review

## Quick Reference (for AI scanning)
**Confidence keywords:** FL-1, factor-exposure-loadings, risk.factor_exposure.loadings, third-family, registry-map-dispatch, _resolve_exposure_family, coverage-gate, 3x3-predicate-symmetry, LOADING_FACTOR_FAMILIES, FRTB, MAR33.14, RATES/CREDIT_SPREAD/COMMODITY, CURRENCY=FX, MARKET=equity, ENT-019-widen, ENT-058-reserved, private_instrument_id-misnomer, alpha=1-desmoothing-identity, PA-3-OLS-repoint, through-VaR-invariance, FE-drift-trio, proxy-weight-estimates, ES-echo-annotation, pre-ratification-verifier-pass, 4-finder-review, content-fence, duplicate-atom-gate, Fable-safety-classifier-switch, Opus-4.8, PG-schema-reset-PUBLIC-grant, OQ-FL-1-1..6, Wave-6, MF-1, MG-1-closeout, investment-risk-platform, ghostai8088
**Projects:** investment-risk-platform (nested at `~/Projects/investment_risk_platform/investment-risk-platform`; repo `ghostai8088/investment-risk-platform`)
**Outcome:** FL-1 (the third factor-exposure family — fractional multi-factor loadings, the proxy projection generalized) fully implemented on branch `fl-1-impl` (7 commits, tip `ca07529`, 33 files +2012/−134, NO migration), 3-verifier pre-ratification pass + user ratification ("Approve all") + full 4-finder Fable review with 0 shipped math defects; all merge gates green (make check 1488 / full-PG fresh 1784 / alembic no-drift / downgrade smoke / FE 64). Session ended holding on the user's PR merge before the OQ-W5C-5 closeout.

## Decisions Made
- **OQ-FL-1-1…6 all ratified** (user "Approve all", 2026-07-16, after a plain-language gate briefing): (1) mint RATES/CREDIT_SPREAD/COMMODITY + alias CURRENCY≡FX, MARKET≡equity, zero migration; (2) loadings method = PA-3's regression pointed at public instruments via the α=1 desmoothing identity, vendor-beta the v2; (3) WIDEN `proxy_mapping` (ENT-019) with the `private_instrument_id` misnomer recorded, ENT-058 reserved as the clean-schema v2; (4) the third exposure family = the proxy projection generalized, with a coverage gate (unloaded atom refuses — the verifier's HIGH); (5) three gate relaxations to explicit allow-lists, scenario's TWO gates stay closed; (6) scope fence + the FE drift trio.
- **Registry-map vs widen-the-proxy-family fork (OQ-4):** chose a THIRD family through the shared binder (the `_resolve_exposure_family` registry map, ES-1 precedent) over widening PA-2's proxy family — widening would mutate a validated governed model's contract under the MG-1 validation regime for zero capability gain, and the two contracts genuinely diverge (proxy has an indicator fallback; loadings has the coverage gate).
- **Opus-finder budget restriction LIFTED** (user: "My Fable usage has been reset, remove the restriction") — finders ran on Fable this slice; Opus stays the fallback if budget exhaustion recurs.
- **Implementation deviations from the ratified plan (recorded in record Part 5.5):** (a) ONE shared `LOADING_FACTOR_FAMILIES` constant instead of the plan's two (strictly stronger — can't diverge); (b) the allocation consume-path probe KEPT its STYLE refusal (allocation stays CURRENCY-only) rather than moving to OTHER; (c) the 3×3 predicate gate is an exact-match TIGHTENING that changed the allocation/proxy acceptance surface for hand-minted snapshots (COMPLETED outputs byte-identical; the ES-1 "byte-untouched" class).

## Key Learnings
- **The Fable→Opus mid-session switch has TWO harness-side triggers, both invisible from inside the model:** (1) the usage-cap fallback (MG-1); (2) **Fable 5's SAFETY CLASSIFIER flagging a message** → auto-switch to Opus 4.8 (VS Code banner: "Fable 5's safeguards flagged this message. This sometimes happens with safe, normal conversations."). The user saw #2 at FL-1 (a false positive on benign financial-risk work), NOT the cap. Mitigation: executed gates arbitrate regardless of which model authored the code; re-run the verification sweep over the suspect window (done: 1473 passed + the full battery + 4-finder review).
- **The 3-verifier pre-ratification pass keeps earning its keep:** it caught a FIFTH CURRENCY gate the census missed (`scenario_service.py:159`, the scenario run-binder — OD-D wrongly claimed scenario "works over fractional rows unchanged" when it refuses them) and that the loadings family's unloaded-atom behavior was UNDEFINED (a silent VaR-under-count hazard) — both folded into the plan as the coverage gate + the corrected gate inventory BEFORE the build.
- **The 4-finder review found 0 shipped math defects** but 4 HIGH doc/test gaps: the PA-3 referent was never amended (still claimed private-only/CURRENCY-only scope the diff had widened — the same V12 contradiction class the pre-ratification pass caught for the desmoothing referent, missed here despite an explicit plan promise); the loadings registrar lacked 409 + endpoint tests. Two adversarial hardenings worth folding: a CONTENT fence (a hand-minted snapshot with loading rows under an allocation predicate would COMPLETE and silently discard them — the predicate-STRING gate didn't close it) and a duplicate-atom gate.
- **The loadings family reuses the EXACT proxy `_build_rows` branch** — no loadings-specific arithmetic exists, so the through-VaR byte-identity (loadings VaR == proxy VaR at matching weights = 450.495329, hand + numpy) is structural. Numeric finder re-derived the α=1 OLS betas to 12dp via numpy lstsq.

## Solutions & Fixes
- **The loadings family (backend core):** `register_factor_exposure_loadings_model` (bootstrap.py) + the `v1:exposure-run-atoms+factor-list+loading-rows` predicate + `_resolve_exposure_family` registry-map dispatch (replaces the two-arm try/except; first-error-wins) + `_assert_full_coverage` (unloaded atom refuses closed) + the snapshot builder `loadings_family` mode (mutually exclusive with `include_proxy_rows`) + `POST /risk/models/factor-exposure-loadings`.
- **Gate relaxations:** `proxy_mapping.py:356` and `proxy_weight_service.py:266` widened `!= CURRENCY` → `not in LOADING_FACTOR_FAMILIES`; `factor_service.py` per-family via `_adjudicate_pins(atoms, factors, family)` — allocation/proxy stay CURRENCY-only, loadings admits the 9-family allow-list; scenario's two gates untouched.
- **Content fence (adversarial F2 fold):** in the adjudication block, `if not family.pins_rows and proxies: raise` — the allocation family refuses a rows-bearing snapshot on CONTENT, not just the predicate string.
- **Duplicate-atom gate (adversarial F1 fold):** a `seen_atoms` set-check on `(portfolio_id, instrument_id)` in `_adjudicate_pins` → governed 422 instead of a raw IntegrityError mid-run.
- **PG schema-reset recipe (bit again at FL-1, already in the local-pg-validation-gotchas memory):** `DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO irp; GRANT USAGE ON SCHEMA public TO PUBLIC;` — the PUBLIC grant is MANDATORY or `test_ops_bypassrls_reads_across_tenants` fails `UndefinedTable: audit_event` (missing schema USAGE makes tables invisible to name resolution). Grant to PUBLIC, never `irp_ops` directly. Alembic reads `DATABASE_URL`; the local container is on port 5432 (not 5433).
- **The α=1 chain:** α is a FREE declared identity parameter with domain (0,1] (not an enumerated vocab) — `register_desmoothed_return_model(..., alpha="1")` gives the Geltner identity (metric_value == observed_return per period); the plan's "extend the α vocabulary" contingency was moot (verifier LOW).

## Files Modified
### Backend (Steps 1/2/4)
- `packages/shared-python/src/irp_shared/marketdata/models.py`: FACTOR_FAMILIES += RATES/CREDIT_SPREAD/COMMODITY + the FRTB comment block + aliases; NEW `LOADING_FACTOR_FAMILIES`; the ProxyMapping ORM misnomer/gate-widen docstring.
- `packages/shared-python/src/irp_shared/marketdata/__init__.py`: export LOADING_FACTOR_FAMILIES.
- `packages/shared-python/src/irp_shared/marketdata/proxy_mapping.py` + `risk/proxy_weight_service.py`: the two literal-comparison gate relaxations.
- `packages/shared-python/src/irp_shared/risk/bootstrap.py`: `FACTOR_EXPOSURE_LOADINGS_MODEL_CODE` + assumptions/limitations + `register_factor_exposure_loadings_model`.
- `packages/shared-python/src/irp_shared/risk/factor_service.py`: `_ExposureFamily`/`_EXPOSURE_FAMILIES`/`_resolve_exposure_family` registry map; `_adjudicate_pins(family)` + the duplicate-atom gate; `_assert_full_coverage`; the content fence; the 3×3 predicate gate; the module docstring (three families); the magnitude failure-label proxy→loading.
- `packages/shared-python/src/irp_shared/risk/__init__.py`: re-export the loadings registrar + model code + methodology ref.
- `packages/shared-python/src/irp_shared/snapshot/service.py` + `__init__.py`: `FACTOR_EXPOSURE_LOADINGS_BINDING_PREDICATE` + the builder `loadings_family` mode.
- `apps/backend/src/irp_backend/api/risk.py`: `POST /risk/models/factor-exposure-loadings`.
### Frontend (Step 5, the FE drift trio)
- `apps/frontend/src/api/types.ts`: the `proxy-weight-estimates` family (FAMILIES + RUN_TYPE_TO_FAMILY + FAMILY_ROW_COLUMNS); vars columns += residual_variance/estimate_age_days/model_version_id.
- `apps/frontend/src/views/RunDetail.tsx`: `resultCell` — per-row metric_type-aware ES echo annotation.
- `apps/frontend/src/api/types.test.ts`, `views/RunDetail.test.tsx`, `views/RunsList.test.tsx`: the FL-1 wiring + ES-annotation + RunsList-filter tests (explicit RUN_TYPE_TO_FAMILY/runDetailUrl tests — NOT forced by the exhaustiveness net).
### Docs (Step 6)
- NEW `05_analytics_methodologies/factor_exposure_loadings_v1.md` (the referent + the FRTB mapping table w/ MAR33.12 Table-2 floors).
- `05_analytics_methodologies/desmoothing_geltner_v1.md` + `proxy_weight_regression_v1.md`: the FL-1 α=1 applicability sections (the latter was a review-fold HIGH — initially missed).
- `04_data_model/canonical_data_model_standard.md`: ENT-019 WIDENED row + ENT-025 vocab; `02_requirements/requirements_traceability_matrix.md`: REQ-MKT-003 + REQ-PRV-005; `10_delivery_backlog/wave_5_close_review.md`: FE-trio PAID; scenario referent two-gate note.
### Tests
- NEW `packages/shared-python/tests/test_factor_exposure_loadings.py` (16 tests: golden, widening, coverage gate, zero-loading-is-coverage, 3×3 incl. the 6th arm, through-VaR invariance, active-risk refusal, α=1 chain, fifth-gate scenario probe, registrar 409, unpinned-factor, committed-FAILED, binder-OTHER, content-fence forge).
- `packages/shared-python/tests/test_factor_exposure_pg.py`: the loadings PG twin (MARKET family under RLS).
- `apps/backend/tests/test_factor_exposure_endpoint.py`: the loadings register idempotent/409 test.
- Repaired existing probe tests for the widening + the 3×3 tightening (test_factor_exposure.py, test_proxy_mapping.py, test_proxy_weight.py, test_p3c1_hardening.py — STYLE/MARKET→OTHER probe moves; `_mint_fe_snapshot` re-stamps the allocation predicate).
### Planning docs
- `10_delivery_backlog/fl_1_decision_record.md` (RATIFIED, Planning verification V1–V13, Part 5.5 deviations, Part 6 dispositions) + `fl_1_implementation_plan.md` (folded).

## Pending Tasks
- **FL-1 PR merge IN PROGRESS** (user opened it; user said "hold until I tell you it's done"). Compare link: `https://github.com/ghostai8088/investment-risk-platform/compare/main...fl-1-impl?expand=1`.
- **ON MERGE:** the OQ-W5C-5 closure-stamp checklist — flip `fl_1_decision_record.md` Status → CLOSED (PR#/merge/CI refs), stamp the roadmap Part 2.9 MG-1→FL-1 DONE row, refresh `docs/project_memory/current_state.md` banner, update memory (fl-1 planning-state or a new memory + index).
- **THEN:** MF-1 planning (the next Wave-6 slice — ends with the TRIGGERED re-validation greping the flagship AWC conditions for 'FL-1'; the demo tenant stays CURRENCY-only through FL-1, MF-1 closes the condition).
- **Also open (unmerged this session):** the `mg-1-closeout` branch PR (docs-only closure stamps) — was handed to the user; and the `fl-1-planning` branch PR (the planning docs, RATIFIED).

## Errors & Workarounds
- **`UndefinedTable: audit_event` on the fresh full-PG run:** missing `GRANT USAGE ON SCHEMA public TO PUBLIC` after the manual schema reset. Fixed by adding the PUBLIC grant (the gotcha was ALREADY documented in the local-pg-validation-gotchas memory — I failed to apply it; sharpened the memory index line so it surfaces).
- **`AppendOnlyViolation` in the content-fence test:** tried to mutate `snap.binding_predicate_version` on an immutable append-only snapshot row. Fixed by hand-minting a fresh forged snapshot via `_persist_snapshot` + `_append_spec` (copying the real components under the allocation predicate).
- **`AttributeError: 'DatasetSnapshotComponent' object has no attribute 'entity_type'`:** the component's field is `target_entity_type`, not `entity_type`.
- **ruff I001 import-sort + F401 unused import:** fixed with `ruff check --fix` (twice — the `__all__` insertion and the test's `resolve_factor`/D-constant ordering).
- **Alembic URL parse error:** `IRP_DATABASE_URL` is wrong; alembic reads `DATABASE_URL` (migrations/env.py:17); the container is on port 5432 not 5433.

## Key Exchanges
- User set `/model claude-fable-5[1m]` twice mid-session (once at start, once mid-implementation after the safety-classifier switched to Opus).
- User: "My Fable usage has been reset, so you can remove the restriction on not using Fable" → lifted the Opus-finder rule across memory + the FL-1 planning docs.
- User asked to re-verify after the model downshift → ran the full sweep (1473 passed, lint/format/mypy clean), confirmed nothing needed redoing.
- User: "Proceed" → drove the entire FL-1 second half (α=1 chain, FE trio, docs, battery, 4-finder review, folds) autonomously.
- User attached the "Switched to Opus 4.8 — Fable 5's safeguards flagged this message" screenshot → corrected the memory (safety-classifier switch, not the usage cap).
- User: "PR is running now. Hold on additional work until I tell you it's done."

## Custom Notes
None

---

## Quick Resume Context
FL-1 (the third factor-exposure family `risk.factor_exposure.loadings` — fractional multi-factor loadings, the proxy projection generalized) is fully built + reviewed on branch `fl-1-impl` (tip `ca07529`, NO migration, head stays `0040`), all merge gates green. The user has the PR open and asked to HOLD until they confirm it merged. On merge: run the OQ-W5C-5 closeout (record CLOSED, roadmap Part 2.9 DONE, current_state banner, memory), then MF-1 is the next Wave-6 slice (it greps the demo tenant's flagship AWC conditions for 'FL-1' and runs the TRIGGERED re-validation; the demo tenant stayed CURRENCY-only through FL-1 by design). The Fable→Opus switches this session were the safety classifier (false positive), not the usage cap — executed gates + the 4-finder review arbitrate quality regardless of authoring model.

---

## Raw Session Log

Session resumed via /resume (loaded MEMORY.md + the PA-4 session log). Verified current state: `main` = `46ce296` (MG-1 impl merged), MG-1 fully closed, FL-1 planning drafts uncommitted in the working tree, `mg-1-closeout` branch pushed without a PR.

Ran the standing 3-verifier pre-ratification pass over the FL-1 planning drafts (all on Opus, per the then-standing budget lesson): a code-census verifier, a doctrine/citation verifier, and an internal-consistency verifier. Results: 2 HIGH (a fifth CURRENCY gate the census missed at `scenario_service.py:159`; the loadings family's unloaded-atom behavior was undefined — a silent VaR-under-count hazard), ~10 MEDIUM, a dozen LOWs. Folded all dispositions into `fl_1_decision_record.md` (Planning verification V1–V13) + `fl_1_implementation_plan.md`. Committed the planning branch `fl-1-planning` (`a2389fb`).

User: "My Fable usage has been reset, so you can remove the restriction on not using Fable." → lifted the Opus-finder rule in memory (mg-1-planning-state + index) and the three Opus pins in the FL-1 planning docs (`cfb417b`).

User: "Can you restate the OQ items?" → restated OQ-FL-1-1…6 in plain language with recommendations.

User: "Approve all" → flipped the record to RATIFIED (`b63478c`), cut branch `fl-1-impl`, began implementation.

Implemented Steps 1 (vocab), 2 (gate relaxations + probe moves), 4 (the loadings family: registrar, predicate, `_resolve_exposure_family` registry map, coverage gate, snapshot builder mode, endpoint). Wrote the core loadings test (golden, widening, coverage gate, zero-loading, 3×3) — all green. Repaired 6 existing tests broken by the widening + the 3×3 predicate-gate tightening. Committed the WIP checkpoint (`ffc90b7`); full non-PG suite green (1136).

[Mid-session: the harness switched the main loop Fable→Opus. User re-ran `/model claude-fable-5[1m]`.]

User asked whether anything triggered the downgrade and whether to redo work → explained agent-scoped Opus overrides can't change the session model; ran the full verification sweep (1473 passed, ruff/format/mypy clean); recorded the mechanism in memory. Nothing needed redoing.

User: "Proceed" → drove the FL-1 second half: the α=1 estimation chain test (public marks → desmooth-identity → OLS over MARKET+RATES → promote, betas byte-equal; 7 desmoothed periods); the fifth-gate scenario probe; the loadings PG twin; the FE drift trio (proxy-weight-estimates family, the three VaR columns, the ES-row echo annotation — 63 vitest + lint + tsc + prettier + build); the Step 6 doc set (methodology referent + FRTB mapping table, ENT-019 catalog widen, ORM misnomer comment, RTM, wave-5 register PAID, scenario two-gate note). Committed across `86b0549`, `24d3f8c`, `4146101`, `427eeb4`, `fad1bcb`.

Ran the Step 8 full battery: `make check` 1481 + secret scan + docs check; reset the PG schema and ran fresh + dirty full-PG (dirty: 1777 passed, 0 failures) — hit `UndefinedTable: audit_event`, fixed with the PUBLIC schema grant (the gotcha was already in memory); `alembic check` no drift; downgrade smoke exit 0.

Launched the 4-finder Fable review (adversarial gates, numeric re-derivation, doctrine alignment, scope/test completeness). Results: 0 shipped math defects (numeric re-derived every number byte-exact — through-VaR 450.495329 by hand + numpy, α=1 betas to 12dp). 4 HIGH: the PA-3 referent was never amended + the loadings registrar lacked 409/endpoint tests. 2 adversarial MEDIUM worth hardening: a content fence (allocation would silently discard hand-minted loading rows under its predicate) + a duplicate-atom gate. Folded everything: the two code hardenings + 6 new test arms + the endpoint test + the PA-3 referent section + REQ-PRV-005 + the mixed-family-instrument disclosure + doc corrections + record Parts 5.5/6. Re-ran the battery: make check 1488, full-PG fresh 1784, alembic no-drift, downgrade smoke, FE 64. Pushed the folds (`ca07529`). Verified the scope fence (no migration/audit/entitlement changes; head `0040`).

Handed the PR compare link to the user for manual open+merge (the classifier blocks Claude's PR-create; per the user's standing choice).

User: "PR is running now. Hold on additional work until I tell you it's done." + attached the "Switched to Opus 4.8 — Fable 5's safeguards flagged this message" VS Code screenshot → corrected the memory (the switch was the safety classifier, a false positive on benign work, not the usage-cap fallback). Holding for the merge confirmation before the OQ-W5C-5 closeout.

Then: /compress.
