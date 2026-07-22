# Session Log: 22-07-2026 15:27 - PPF Arc (Pure-Private Factor → Private Covariance)

## Quick Reference (for AI scanning)
**Confidence keywords:** PPF-1, PPF-2, PPF-3, §2.1 unification arc, pure-private factor, private covariance, Ω_pp, ENT-060, migration 0047, `risk.factor_return.pure_private`, `risk.covariance.private`, 18th/19th governed number, MSCI PE Factor Model, Shepard 2014/2025, Vasicek 1973, Geltner desmoothing, FACTOR_FAMILY_PRIVATE, FREQUENCY_APPRAISAL, isolation guards, `update_factor` freeze, block-diagonal, latent shared-table run_type bug, 4-finder review, pre-ratification verifier, demo stage 11/12, counts 20/35/101→21/36/103→22/37/104, PR #98/#99, ppf-2-planning
**Projects:** investment-risk-platform (Andrew Cox's governed enterprise investment-risk platform)
**Outcome:** PPF-1 (the pure-private factor return, the 18th governed number) fully built, reviewed, merged (PR #98) and closed (PR #99); PPF-2 (the private covariance block Ω_pp, the 19th) planned + verifier-passed + ratified + pushed for merge.

## Decisions Made
- **§2.1 scope = fork B "pure-private systematic factor"** (deepen the math), ratified over attribution-only (A) and refinement-only (C). Rationale: the planning census found the unification EMBRYO already shipped (`risk.var.parametric_total`, PA-4 — public-factor + diagonal idiosyncratic residual), but MISSING the MSCI decomposition's PurePrivate leg. The user chose to add the correlated pure-private systematic factor over a 3-slice arc: **PPF-1 (return series) → PPF-2 (covariance Ω_pp) → PPF-3 (unified number √(x'Σx + p'Ω_pp·p + residual))**.
- **PPF-1 OQ forks (all as recommended):** 3-slice arc; equal-weight pooling + RETAIN_ALPHA (the liquidity premium stays in the factor, per MSCI); membership = weight-1 MANUAL rows in the existing `proxy_mapping` table WITH three verifier-mandated isolation guards; min_members=1 loudly disclosed.
- **PPF-2 OQ forks (all as recommended):** equal-weight sample covariance (thin-N disclosed; Vasicek/Ledoit-Wolf shrinkage = recorded v2); block-diagonal Ω_pp (disclosed as APPROXIMATELY orthogonal, not exact); the appraisal→daily frequency conversion lives in PPF-3 (the combiner), not PPF-2; reuse the `covariance_result` table (frequency=APPRAISAL + a new run_type — NO migration, NO ENT) + three run_type read-filters.
- **PPF-1 counts moved 20/35/101 → 21/36/103** (1 new model code + 1 INITIAL validation + 2 runs). PPF-2 will move to 22/37/104.

## Key Learnings
- **The generalizable isolation lesson (PPF-1 MED-1):** an isolation guard enforced only at WRITE/CAPTURE time can be bypassed by an in-place UPDATE on the referenced entity. `update_factor` admitted `factor_family`/`frequency` as updatable, so a public factor with an existing REGRESSION blend could be FLIPPED to PRIVATE/APPRAISAL in place, retroactively bypassing the capture-time guards. Fix: FREEZE any attribute that gates admission (like code/source already are), don't just validate it at the one write path you designed for.
- **The PPF-2 latent-bug lesson:** reusing a shipped result table for a sibling family (distinguished by run_type) ACTIVATES any latent read on that table that omits the `run_type` filter — `calc/reads.py` explicitly warns about this for shared tables. `latest_covariances`/`resolve_covariance` were run_type-unfiltered; reuse would leak a private APPRAISAL matrix as "the latest public covariance." Audit every read on a table the moment a second run_type starts writing to it.
- **The pre-ratification verifier keeps earning its keep:** PPF-1's verifier REFUTED the guard-free membership design (an unguarded PRIVATE row would refuse every new exposure run) → forced 3 guards pre-implementation. PPF-2's verifier REFUTED "orthogonal-by-construction" → the promoted proxy weights are a strict SUBSET of the OLS fit (PE 1/2, PC 2/3), so `pp` retains a dropped-factor public component; block-diagonal is a disclosed approximation, not an identity. RETAIN_ALPHA is a non-issue for covariance (a constant adds zero covariance).
- **The covariance kernel is fully generic** (`estimate_covariance`: aligned `(date, Decimal)` series, N≥2, no daily/factor_return coupling) — reusable for APPRAISAL series unchanged; the DAILY wall is only in two adjudicator gates. The result-table-as-series pinning is doubly proven (proxy-weight + PPF-1).
- **The write-boundary / deploy-boundary generalization** (from API-1b/FE-3b, still applying): when a read can't resolve read-only, stamp the scope at write time; a "works end-to-end" demo goal needs its own infra proof.

## Solutions & Fixes
- **PPF-1 4-finder folds (ZERO HIGH, 1 MED + 2 LOW):** MED — froze `factor_family`+`frequency` in `_UPDATABLE_FACTOR` (byte-identical for all shipped usage; every existing `update_factor` call only amends `description`/`region`). LOW — the magnitude gate `1E8` envelope equaled the `Numeric(20,12)` column cap (a raw value could pass then quantize UP into a PG-only overflow, the CC-2 lesson); fixed to gate the QUANTIZED values. LOW — a by-segment read ordered on `metric_type` alone; fixed to `(metric_type, period_start)`.
- **PPF-2 verifier folds (in the plan, not yet coded):** step 1 = add `run_type=RUN_TYPE_COVARIANCE` to `latest_covariances` + `resolve_covariance` + `GET /covariances/latest`/`{id}` (behavior-identical for existing data; a correct latent-bug fix) — before any private rows can exist.
- **Demo mechanics:** the `stage9zz`/`stage9zzz` filename convention (the zero-pad alpha-sort hazard: `stage11`/`stage12` sort BEFORE `stage2`; extend `z` suffixes so the count-pin ordering holds — stage9z asserts 20/35/101 before ppf1 seeds). Governed-number stage moves counts by exactly +1 code +1 validation +N runs. "ZERO new seeding" proven by the verifier's exact census (PE-HARBOR-IV + PC-BRIDGEWATER-II already carry desmoothing runs + promoted REGRESSION blends; they share exactly 5 common quarter-end intervals).
- **The FK-name-too-long fix (PPF-1 migration 0047):** the convention name exceeds PG's 63-char cap for long tables; name FKs explicitly-short inline in the model to match the migration (the P3-8/proxy_weight lesson). `alembic check` confirmed no drift.

## Files Modified
**PPF-1 (shipped, merged PR #98 `9d64b49`; closeout PR #99):**
- `packages/shared-python/src/irp_shared/marketdata/models.py` — `FACTOR_FAMILY_PRIVATE`, `FREQUENCY_APPRAISAL`, `PROXY_MAPPING_CAPTURE_FAMILIES` (split off `LOADING_FACTOR_FAMILIES`).
- `marketdata/factor.py` — family↔frequency coupling in `_validate_frequency`; FROZE `factor_family`+`frequency` in `_UPDATABLE_FACTOR` (MED-1 fold).
- `marketdata/proxy_mapping.py` — `_resolve_factor_id` uses the capture set + PRIVATE⇒MANUAL invariant (capture + supersede).
- `snapshot/service.py` — the exposure-builder family filter (guard 1); `build_private_factor_return_snapshot`.
- `risk/period_alignment.py` (NEW) — shared alignment helper extracted from PA-3.
- `risk/private_factor_kernel.py` (NEW), `risk/private_factor_service.py` (NEW) — the binder + kernel.
- `risk/models.py` — `PrivateFactorReturnResult` (ENT-060); `migrations/versions/0047_private_factor_return.py` (NEW).
- `risk/bootstrap.py` — `register_pure_private_factor_model` + `declared_pure_private_parameters`.
- `apps/backend/src/irp_backend/api/risk.py` — `/private-factor-returns[/latest,/{id}]`; `apps/frontend/src/api/decimal-contract.ts` — extended guard.
- `demo/ppf1_stage11.py` (NEW) + `demo/dossiers.py` + tests `test_demo_stage9zz_ppf1*.py` + `test_pure_private_factor.py` + `test_private_factor_pg.py`.
- Docs: `04_data_model/canonical_data_model_standard.md` (ENT-060), `10_delivery_backlog/ppf_1_decision_record.md` + plan, `delivery_roadmap.md`, `docs/project_memory/current_state.md`.

**PPF-2 (planning, pushed `ppf-2-planning`, awaiting USER PR):**
- `10_delivery_backlog/ppf_2_decision_record.md` + `ppf_2_implementation_plan.md` (RATIFIED).

**Memory:** `ppf-1-planning-state.md`, `ppf-2-planning-state.md`, `delivery-roadmap-state.md`, `MEMORY.md` (compacted 20.3KB→9.8KB).

## Pending Tasks
- **USER: merge the `ppf-2-planning` PR.**
- **PPF-2 implementation** (7-step plan; step 1 = the 3 run_type read-filters FIRST, regression-proven byte-identical; reuse the covariance kernel + `covariance_result` table; NO migration; the 19th governed number; demo stage 12 over the 2 seeded segments at N=5, zero new seeding; 4-finder with a dedicated public-covariance isolation finder). Then closeout.
- **PPF-3** (the unified number `√(x'Σx + p'Ω_pp·p + residual)`) — the §2.1 headline itself; owns the appraisal→daily frequency conversion (the iid variance-scaling parameter) + the VaR-gate widening to admit the private block. May close Wave 10 or roll to Wave 11.

## Custom Notes
None

---

## Quick Resume Context
The §2.1 private/public-unification arc (Wave-10 slice 3) is a 3-slice build: PPF-1 (pure-private factor return, the 18th governed number) is DONE + merged (PR #98/#99); PPF-2 (private covariance block Ω_pp, the 19th) is PLANNED + RATIFIED + pushed (branch `ppf-2-planning`, awaiting the USER's PR+merge). Resume by: USER merges `ppf-2-planning`, then implement PPF-2 per its 7-step plan (step 1 = the run_type read-filters first; reuse the covariance kernel + `covariance_result` table, NO migration; demo runs a 2×2 over the 2 seeded segments at N=5 with zero new seeding). Then PPF-3 assembles the unified number and owns the appraisal→daily frequency conversion. Standing directives: last sentence of every response = model+effort rec; plain-language gate briefings via AskUserQuestion OQ forks; the USER opens+merges PRs; pre-ratification verifier + 4-finder review per slice.

---

## Raw Session Log

_(Structured archive — this session continued from a prior compaction. The full turn-by-turn detail lives in the committed decision records, the dated roadmap log, and the memory planning-state files. Chronology:)_

1. **FE-3b closeout** (post-merge PR #96): decision record CLOSED, roadmap DONE, current_state; memory.
2. **PPF-1 planning** — §2.1 scope gate: fetch/cite (MSCI PE Factor Model; True = (β·Public + PurePrivate + Specific)×Leverage), codebase substrate map (found the `parametric_total` embryo), surfaced the scope fork → user chose **fork B**. Then the OQ forks (arc/pooling/intercept/membership/min_members), pre-ratification verifier (REFUTED the guard-free membership → 3 guards), ratified, pushed (PR #97).
3. **PPF-1 implementation** — 8 steps: (1) vocab + 3 isolation guards + byte-identical proof; (2) shared alignment helper; (3) migration 0047 + `PrivateFactorReturnResult` (ENT-060), PG-validated (alembic check, downgrade/upgrade, RLS+trigger); (4) multi-member snapshot builder; (5) binder+kernel — the 18th governed number COMPUTES end-to-end (matched an independent recompute); (6) rule-7 API reads + OpenAPI regen; (7) demo stage 11 (both segments, min_members=1, zero new seeding, counts 20/35/101→21/36/103 PG-proven); (8) full gate + 4-finder review. Merged PR #98 (`9d64b49`).
4. **PPF-1 4-finder review** — ZERO HIGH; 1 MED (the `update_factor` family/frequency flip back-door → froze both) + 2 LOW (magnitude-gate quantize; read ordering), all folded. Then the closeout (record CLOSED, roadmap DONE row + dated log, current_state banner, memory + MEMORY.md compacted), merged PR #99.
5. **PPF-2 planning** — fetch/cite (mixed-frequency covariance; MSCI PE/Private-Credit models; Vasicek 1973 Bayesian shrinkage for thin data), codebase grounding (the covariance kernel is generic; reuse it + the `covariance_result` table; the DAILY wall is two adjudicator gates), decision record with 4 OQ forks, pre-ratification verifier (2 adversarial: CLAIM 4 REFUTED "orthogonal-by-construction" → approximate/subset-promotion; CLAIM 2 latent shared-table run_type bug → 3 filters named; CLAIM 3 HOLDS — exactly 5 common quarters, zero new seeding; CLAIMs 1/5 HOLD), ratified all 4 forks as recommended, wrote the 7-step plan, pushed `ppf-2-planning`.
6. **/compress** (this).

**Standing directives honored throughout:** last sentence of every response = best-fit model+effort rec; plain-language gate briefings via AskUserQuestion OQ forks; concise prose; clickable PR links. **Hard invariants held:** `audit/service.py` FROZEN; no BYPASSRLS/hybrid beyond the 5-table set; no new permission/role/audit-code outside R-07; no secrets (BR-10); verification gates never waived; governed numbers bind snapshot+run+model_version; the USER opens+merges PRs.
