# Session Log: 17-07-2026 13:24 - ES-HS-1 Empirical ES Delivery

## Quick Reference (for AI scanning)
**Confidence keywords:** investment-risk-platform, ES-HS-1, ES_HISTORICAL, Acerbi-Tasche, Prop-4.1, tail-mean, historical-simulation, expected-shortfall, migration-0041, ck_var_result_parametric_not_null, risk.var.historical_es, _HS_FAMILIES, registry-map-dispatch, Acerbi-Szekely, BT-3, Christoffersen, verified-via-reproduction, Moldenhauer-Pitera, demo-stage-4, TIER_1, non-superuser-downgrade, MigrationContext, owner-via-membership, tied-tail, alpha-sort-filename, census-workflow, verifier-pass, 4-finder-review, HG-1-closeout, Wave-7, RS-1, PR#55, PR#56, PR#57, PR#58, dc2a494, c7b8c15, 0041_es_historical
**Projects:** investment-risk-platform (nested at ~/Projects/investment_risk_platform/investment-risk-platform); governed enterprise investment-risk system (multi-tenant, auditable, reproducible, governed — NOT an MVP)
**Outcome:** HG-1 closed out (PR #56); then ES-HS-1 fully delivered — planned (census+verifier workflows), ratified ("Approve all"), implemented, 4-finder-reviewed (0 HIGH, all folded), merged (PR #58 = dc2a494, CI green 5/5), and closed out — the 15th governed number (the empirical historical-simulation ES). Next = RS-1 planning.

## Decisions Made
- **HG-1 closeout confirmed** (impl PR #55 = `8260ea6`; closeout PR #56 = `e71455f`). The first Wave-7 slice closed; a transient CI Postgres deadlock in the downgrade smoke was re-run to green (not a code issue).
- **ES-HS-1 planning ran the STANDARD pattern, NOT full ultracode** — recommended and the user agreed: a census workflow (multi-agent, file:line grounding) + a pre-ratification verifier pass, ~10-15 agents, not the 78-agent wave-close shape. Ultracode's marginal yield at planning is low (the verifier pass already catches shape errors); its best-fit task is a wave close.
- **OD-A — the number:** `ES_HISTORICAL` = the Acerbi-Tasche Prop-4.1 empirical α-tail-mean (a=1−c, m=⌊n·a⌋, w=n·a−m: `ES = −(Σᵢ≤ₘ pnl₍ᵢ₎ + w·pnl₍ₘ₊₁₎)/(n·a)` — floor count + FRACTIONAL boundary weight). NEVER the mean of the worst ⌈n·a⌉ (that IS the TCE the ES-1 convention forbids, understating ~14% at n=41). Pre-pinned at ES-1 — the estimator is registered at three shipped sites. A sibling kernel function sharing the accumulation+sort helper; the plain-VaR path byte-preserved.
- **OD-D — the in-slice fork RESOLVED = TEE the Acerbi-Szekely backtest as BT-3, NOT ship in-slice.** Structural reasoning: shipping in-slice = a full backtest slice buried in the headline (pairing rework of two binder gates + a new backtest model identity + registered thresholds + its own appraisal-bias doctrine). The tee is named with teeth: BT-3 carries the verified AS statistics, TIPPED Christoffersen (finally homed), and the pairing design input (pair ES-HS + VaR-HS runs by shared `input_snapshot_id`). The user ratified "Approve all".
- **OD-B — the family:** `risk.var.historical_es` v1 through the SAME HS binder via a `_HS_FAMILIES` registry-map dispatch (the ES-1 `_VAR_FAMILIES` shape). Declared identity adds `estimator_convention=TAIL_MEAN_ACERBI_TASCHE_P41`; NO es_multiplier/z (empirical). VAR_HS_INPUT snapshot + builder reused byte-unchanged (adjudicated purpose-only reuse — identical pinned content).
- **OD-C — migration 0041:** widen the 0028 CHECK (drop+recreate, SAME short name; IN-list form). Destructive RLS-safe downgrade deleting ES_HISTORICAL rows (the 0028 sandwich verbatim).
- **OD-F — demo stage 4:** the 18th code (TIER_1 — HIGH materiality ⇒ TIER_1 under the MG-1 matrix), an INITIAL AWC dossier, the ES run bound to the flagship HS VaR's snapshot (BT-3 pairing live).
- **Acerbi-Szekely 2014 = VERIFIED-VIA-REPRODUCTION** (the primary is GATED at both hosts — risk.net paywall + MSCI form-gate). The Z2 formula verified via the Moldenhauer-Pitera verbatim reproduction (arXiv:1709.01337 p.15 Eq. 6.2) + the null-expectation identity; Z1 vendor-normalized and the −0.70/−1.8 thresholds single-attributed — both flagged for re-verification at BT-3.

## Key Learnings
- **The non-superuser downgrade-path PG test needs OWNER-VIA-MEMBERSHIP:** a `NOSUPERUSER NOBYPASSRLS` role GRANTED MEMBERSHIP in the table-owner role — role ATTRIBUTES don't inherit through membership, but ownership checks pass via `has_privs_of_role`, so the role runs the DDL while staying RLS-bound (the exact FORCE-RLS zero-row-trap geometry). A DML-grant role dies "must be owner"; the alembic CLI reconnects as the superuser (re-masking the exact gap the test exists to close). Drive the REAL migration module's `downgrade()` via `MigrationContext.configure(conn, opts={"target_metadata": metadata})` — **the metadata is REQUIRED** (it carries the naming convention that expands the short constraint name `parametric_not_null` → `ck_var_result_parametric_not_null`). Assert-then-ROLLBACK to restore the widened state for the rest of the shared-DB job.
- **A tied-tail demo window makes ES = VaR exactly.** The living tenant's seeded flagship HS window has tied worst-two scenarios, so the (VaR, ES) pair lands on the recorded equality case — a LIVE counterexample to any "strictly understates at every fractional n·a" claim. Softened to the weak form (never exceeds; strictly below only with an untied (m+1)-boundary). The same imprecision survives verbatim in ES-1's shipped texts — NAMED for the next re-registration, not touched (scope fence).
- **The `test_demo_stage4_*` filename is LOAD-BEARING for ordering.** Local full-PG runs collect ALPHABETICALLY, so a `test_demo_eshs*` name would run before the hg1/multifamily suites and break the multifamily EXACTLY-17 pin. The CI step order is separate (explicit); the local collection order needs the filename leg. The stage-4 TierDossier is a SEPARATE module constant (the MF1_LOADINGS_TIER shape), NEVER in TIER_DOSSIERS (the campaign suite derives its 16-pin from that dict).
- **Verified-via-reproduction is the honest citation shape for a paywalled primary** — grade each source: Z2 verified via ONE verbatim reproduction + the identity; Kratz-McNeil grounds procedure/posture only; Z1 vendor-normalized (flagged). Disclose the M-P sign-inconsistency (the prose is in a flipped convention vs the displayed equation). Never claim "peer-reviewed" of arXiv preprints. The planning verifier caught my own draft overclaiming "two peer-reviewed reproductions of the formulas" (a HIGH).
- **The reproducibility gain:** the ES-HS row is FULLY reproducible from its pinned snapshot + declared parameters alone (no registered constant participates — the tail mean is empirical), UNLIKE the parametric ES which reproduces only THROUGH its registered k_c.
- **A migration slice sweeps ALL migration-head test pins** — 17 tests hard-code `get_current_head() == "0040_var_estimate_age"`; a scripted sweep flipped them all to `0041_es_historical`, plus the synthetic-slice next-slot guard (glob `0041*` → `0042*`).
- **The workflow tool** (census + verifier + 4-finder review) is the right shape for a governed-number slice: parallel domain agents ground every claim to file:line; adversarial verifiers attack the draft before ratification; independent finders re-derive the math after implementation. The numeric finder fuzzed 2,400+ windows against an independent estimator implementation and recomputed the living tenant's stored ES byte-equal from its own pins.

## Solutions & Fixes
- **Migration 0041 body** (`migrations/versions/0041_es_historical.py`): `op.drop_constraint("parametric_not_null", "var_result", type_="check")` + `op.create_check_constraint("parametric_not_null", "var_result", "metric_type IN ('VAR_HISTORICAL', 'ES_HISTORICAL') OR (...)")`; the downgrade = the 0028 6-statement sandwich (disable trigger + DISABLE ROW LEVEL SECURITY → DELETE ES_HISTORICAL → ENABLE + FORCE RLS + enable trigger → recreate the narrow CHECK). The `_IDENTIFIERS` ≤63 assert.
- **The kernel** (`var_hs_kernel.py`): extracted `_sorted_scenario_pnls` shared helper (VaR path byte-preserved); `compute_historical_es` with exact-Decimal n·a/m/w inside the prec-50 localcontext, ONE HALF_UP quantize; refusal precedence pinned (k/confidence validation AHEAD of accumulation).
- **The registry-map dispatch** (`var_hs_service.py`): `_HS_FAMILIES` + `_resolve_hs_family` (the `_resolve_var_family` first-error contract — a non-family version gets the plain-HS code's `WrongModelVersionError`); `_compute` branches on `family.es`.
- **AS 2014 fetch:** the gated PDF was saved locally by WebFetch; extracted text with the project venv's `pypdf` (no `pdftotext`/poppler on the box). Verified the Test-2 formula through Moldenhauer-Pitera + Kratz-McNeil + MathWorks docs.
- **Transient CI Postgres deadlock** (HG-1 closeout): `alembic downgrade base` vs a lingering backend holding a lock on `audit_event` — re-ran the failed job via `POST .../actions/runs/<id>/rerun-failed-jobs`, passed clean. Not a code issue (identical commit had passed on push).
- **Battery recipe:** schema reset `docker exec irp_pg_local psql -U irp -d irp -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO irp; GRANT USAGE ON SCHEMA public TO PUBLIC;"` then `DATABASE_URL=... alembic upgrade head`; full local-PG via `DATABASE_URL=... IRP_TEST_DATABASE_URL=... pytest packages/shared-python/tests apps/backend/tests`.

## Files Modified
### ES-HS-1 implementation (branch `es-hs-1-impl`, `a05da5a` + review folds `c7b8c15`; merged PR #58 = `dc2a494`)
- `migrations/versions/0041_es_historical.py`: NEW — the CHECK widening + destructive RLS-safe downgrade.
- `packages/shared-python/src/irp_shared/risk/var_hs_kernel.py`: `compute_historical_es` + `HsEsEstimate` + the shared `_sorted_scenario_pnls` helper.
- `packages/shared-python/src/irp_shared/risk/bootstrap.py`: `ES_HS_MODEL_CODE`/`ES_HS_*` constants, `EsHsParameters`, `declared_es_hs_parameters`, `register_historical_var_es_model`; the `VAR_HS_LIMITATIONS[4]` reword; the TCE-claim softening.
- `packages/shared-python/src/irp_shared/risk/var_hs_service.py`: `_HS_FAMILIES` registry-map dispatch; the `_compute` es-branch; module docstring update.
- `packages/shared-python/src/irp_shared/risk/events.py`: `METRIC_TYPE_ES_HISTORICAL` (NOT in `METRIC_TYPES`).
- `packages/shared-python/src/irp_shared/risk/var_backtest_service.py`: the deliberate `ES_HISTORICAL` refusal branch naming BT-3.
- `packages/shared-python/src/irp_shared/risk/models.py`: the ORM CHECK comment (both exempt literals).
- `packages/shared-python/src/irp_shared/risk/__init__.py`: the new re-exports.
- `apps/backend/src/irp_backend/api/risk.py`: `POST /models/var-historical-es`; run/read docstrings updated.
- `packages/shared-python/src/irp_shared/demo/eshs_stage4.py` + `scripts/run_demo_eshs.py`: NEW — stage 4 (the 18th code, TIER_1, INITIAL AWC).
- `packages/shared-python/src/irp_shared/demo/dossiers.py` + `demo/__init__.py`: `ES_HS_TIER`/`ES_HS_INITIAL` (separate constants); exports.
- Tests: `test_es_hs.py`, `test_es_hs_pg.py`, `test_demo_stage4_eshs.py`, `test_demo_stage4_eshs_pg.py` (NEW); additions to `test_var_hs_endpoint.py`, `test_var_backtest.py`; the 17 head-pin sweeps + the synthetic guard.
- `.github/workflows/ci.yml`: two new PG steps (the ES-HS CHECK/downgrade suite beside `test_var_hs_pg`; the stage-4 suite after stage-3, before the downgrade smoke).
- `05_analytics_methodologies/var_historical_es_v1.md`: NEW referent (per-source citation grades); dated amendments to `var_parametric_es_v1.md` + `var_historical_v1.md`.
- `10_delivery_backlog/es_hs_1_decision_record.md` + `es_hs_1_implementation_plan.md`: NEW (planning PR #57 = `7568c49`); Part 5.5 deviations + Part 6 review dispositions.
### ES-HS-1 closeout (branch `es-hs-1-closeout`, pushed — awaiting user merge)
- `es_hs_1_decision_record.md` Status CLOSED; roadmap Part 2.10 DONE row + amendment log; `current_state.md` banner + counts 14→15 / 17→18; `canonical_data_model_standard.md` ENT-027 6th realization; RTM + backbone REQ-MKT-001 narrowed.
### HG-1 closeout (branch `hg-1-closeout`, PR #56 = `e71455f`)
- The HG-1 record/roadmap/banner/memory stamps (from the prior turn, merged this session).
### Memory (~/.claude/.../memory/)
- NEW `es-hs-1-planning-state.md`; updated `MEMORY.md`, `delivery-roadmap-state.md`.

## Pending Tasks
- **ES-HS-1 closeout PR pending user merge** — branch `es-hs-1-closeout` (docs-only stamps). On merge, the closeout is complete.
- **NEXT = RS-1 planning** (Wave-7 slice 3): residual shrinkage/EWMA — the PA-4 OD-E/OD-G v2s (the idiosyncratic-residual estimate, NOT the covariance v2s); remediates the raw-sample-σ_e rider on the flagship AWCs (a TRIGGERED re-validation candidate). **MUST fetch Ledoit-Wolf / RiskMetrics to paragraph at planning (UNVERIFIED).**
- **BT-3 (the teed AS backtest)** carries un-discharged verification debt: Z1's exact transcription is vendor-normalized and the −0.70/−1.8 thresholds are single-attributed — BOTH must be re-verified against the primary or a second independent source before BT-3 registers any threshold constant.
- Wave 7 remaining: RS-1 → DS-2, then the Wave-7 close. Riders: SC-2 the named pull-forward; capital-calls the presumptive Wave-8 headline.
- Model was on Opus 4.8 [1m] at session end for /compress (user switched from haiku after the closeout stamps).

## Errors & Workarounds
- **Dirty-DB spurious FK-violation** on `alembic downgrade base` during the final smoke: `update or delete on table "permission" violates fk_role_permission...` — caused by a double-seeded local DB (running demo suites twice against the same schema without a reset). NOT a real defect (0002_entitlement_seed's downgrade deletes permissions its FKs still reference under the doubled state). The standing reset-between-runs rule; the CI-shape (fresh schema) was proven green three separate ways with real exit codes.
- **Constraint-name UndefinedObject** in the first non-superuser downgrade test draft: `constraint "parametric_not_null" of relation "var_result" does not exist` — the `MigrationContext` lacked the naming-convention metadata. Fixed with `opts={"target_metadata": irp_shared.models.metadata}`.
- **The GUC name** for the RLS tenant context is `app.current_tenant` (transaction-local, `set_config(..., true)`) — NOT `irp.tenant_id` (my first test draft guessed wrong).
- **ruff/mypy fixes:** import sorting (`ruff check --fix`); an F811 `session` redefinition (renamed a helper param `session`→`db`); a `str | None` tier type narrowed with a guard; a line-length E501 in a docstring.
- **AskUserQuestion caps at 4 options** — the /compress skill's 7-option preserve list had to be consolidated into 4 grouped multi-select options.

## Key Exchanges
- User "Approve all" (ES-HS-1 planning, OQ-ES-HS-1-1…7) → implementation proceeded under the autonomy grant.
- Recurring cadence: fetch primary source → census workflow (4 parallel domain agents, file:line) → draft record+plan → 4-lens verifier pass (22 findings, all folded pre-gate) → OQ gate briefing in plain language → user ratifies + merges planning PR → implement → 4-finder review (8 findings, all folded) → battery → push impl PR → user merges → closeout stamps.
- The planning verifier pass changed the ratified shape (the non-superuser downgrade-test mechanics were NOT executable as first drafted; a HIGH citation overclaim; the raw-precision ES≥VaR assertion). The impl review's best catch was the tied-tail demo counterexample.
- User asked to "perform the merge-watch and closeout stamps and then pause (so I can update the model)" — did the merge-watch (PR #58 green) + all closeout stamps + memory, pushed the closeout branch, and paused.

## Custom Notes
None

---

## Quick Resume Context
ES-HS-1 (Wave-7 slice 2, the headline) is FULLY DELIVERED and CLOSED: the 15th governed number — the Acerbi-Tasche Prop-4.1 empirical historical-simulation ES (`ES_HISTORICAL` via `risk.var.historical_es` v1), migration `0041` widening the 0028 CHECK, the Acerbi-Szekely backtest teed as BT-3, demo stage 4 (the 18th code). Impl merged PR #58 = `dc2a494` (CI green 5/5); closeout stamps pushed on `es-hs-1-closeout` awaiting the user's merge. HEAD = `dc2a494`, migration head `0041_es_historical`. **NEXT = RS-1 planning** (residual shrinkage/EWMA — fetch Ledoit-Wolf/RiskMetrics to paragraph FIRST). The BT-3 tee carries un-discharged re-verification debt (Z1 transcription + the AS thresholds). Wave 7 = HG-1 ✅ → ES-HS-1 ✅ → RS-1 → DS-2.

---

## Raw Session Log

**Note:** This was a long multi-phase delivery session. The structured summary above captures the substantive content, decisions, and exchanges. The phase-by-phase arc:

1. **`/resume` + "PR is merged and closed"** — resumed context; verified HG-1 impl PR #55 (`8260ea6`) merged to main, CI green; ran the HG-1 closure-stamp checklist (record CLOSED, roadmap DONE + amendment, current_state banner, memory); pushed HG-1 closeout on `hg-1-closeout`.
2. **User: "The CI / DB migration check failed on the PR"** (HG-1 closeout) — diagnosed a transient Postgres deadlock in the downgrade smoke (`alembic downgrade base` vs a lingering `audit_event` lock); re-ran the failed job via the GitHub API; passed clean (5/5). Flagged the deadlock window as a watch-item, not a fix.
3. **User: "PR closed out. For the planning should I turn on Ultracode?"** — recommended the STANDARD pattern (census + verifier workflows, ~10-15 agents) over full ultracode for planning; explained the three levels and why ultracode's best-fit is a wave close, not planning.
4. **User: "Proceed with your recommendations. Currently on Fable Extra high"** — ES-HS-1 planning: fetched Acerbi-Szekely 2014 (gated → verified-via-reproduction through Moldenhauer-Pitera + Kratz-McNeil + MathWorks); ran a 4-domain census workflow (91 file:line claims); drafted the record + plan; ran a 4-lens verifier pass (22 findings: 1 HIGH, 7 MEDIUM, 14 LOW — all folded); briefed the OQ gate in plain language; pushed planning on `es-hs-1-planning`.
5. **User: "Approve all"** — implemented the full slice under the autonomy grant (migration, kernel, registrar, binder dispatch, API, tests, demo stage 4, docs, CI); ran the battery (`make check` 1524; full local-PG fresh; alembic check; downgrade smoke over seeded ES rows); ran a 4-finder review workflow (8 findings: 0 HIGH, 3 MEDIUM, 5 LOW — all folded); pushed impl on `es-hs-1-impl`.
6. **User (model→haiku, then→default): "PR is merged and closed. Please perform the merge-watch and closeout stamps and then pause"** — verified ES-HS-1 merged PR #58 (`dc2a494`), polled CI to green (5/5); ran the full closeout-stamp checklist (record CLOSED, roadmap DONE + amendment, current_state banner + counts 14→15 / 17→18, ENT-027 catalog 6th realization, RTM/backbone narrowing, memory); pushed closeout on `es-hs-1-closeout`; paused for the model update.
7. **`/compress`** — this session log.

Key artifacts and their commits/PRs are enumerated in the Files Modified and Decisions sections above. The decision records (`es_hs_1_decision_record.md` Parts 1-6, incl. the Part-5 verifier table and Part-6 review dispositions) and the memory file `es-hs-1-planning-state.md` hold the full technical detail.
