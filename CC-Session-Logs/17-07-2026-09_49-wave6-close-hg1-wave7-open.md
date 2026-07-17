# Session Log: 17-07-2026 09:49 - Wave-6 Close / HG-1 / Wave-7 Open

## Quick Reference (for AI scanning)
**Confidence keywords:** investment-risk-platform, MF-1, MF-1-closeout, Wave-6-close, wave_6_close_review, HG-1, hg_1_decision_record, Wave-7, ES-HS-1, RS-1, DS-2, ultracode, workflow, promotion-age-gate, promotion_age_days, ProxyWeightStaleEstimateError, constants-sweep, PROXY_WEIGHT_LIMITATIONS, finding-key-conformance, stage-3-demo, PC-BRIDGEWATER-II, alpha=0.4, multi-family, living-demo-tenant, TRIGGERED-re-validation, estimate-staleness, phase_status-stub, 3-verifier-pass, 4-finder-review, ratification, closure-stamp, PR#50, PR#51, PR#52, PR#53, PR#54, 9e3200a
**Projects:** investment-risk-platform (nested at ~/Projects/investment_risk_platform/investment-risk-platform); governed enterprise investment-risk system (multi-tenant, auditable, reproducible, governed — NOT an MVP)
**Outcome:** MF-1 closed → Wave-6 close review authored+ratified (first full ultracode workflow, zero shipped-code defects) → Wave 7 ratified (fork A: HG-1→ES-HS-1→RS-1→DS-2) → HG-1 planned+implemented+reviewed (zero HIGH), pushed on hg-1-impl (9e3200a), awaiting user merge.

## Decisions Made
- **MF-1 closeout confirmed** (impl PR #50 = `96b766c`, CI #323 green; closeout PR #51 = merged). Wave 6 functionally complete.
- **Ran the Wave-6 close as an ultracode Workflow** (user turned ultracode on for that turn). Recommended per-turn opt-in over standing-on; the user enabled it, then it auto-turned-off later.
- **Wave-6 close ratified (OQ-W6C-1…6, "Approve all")**: findings recorded/fixed; estimate-staleness residual RE-OPENED and assigned to Wave-7 HG-1 (register discipline's teeth — TIPPED debt that survives its assigned wave escalates); living-tenant durability practice adopted (re-seed after schema-reset batteries); `phase_status.md`/`next_actions.md` RETIRED to pointer stubs (OQ-W6C-4); MF-1 OD-E ride-along re-tee DISCHARGED by sequencing into Wave 7.
- **Wave 7 = fork A "deepen the mathematics"**: HG-1 (S) → ES-HS-1 (M, headline, needs the ONE 0041 migration widening the 0028 CHECK) → RS-1 (S/M residual shrinkage/EWMA) → DS-2 (S/M estimated-α desmoothing). Riders: SC-2 the named pull-forward if the wave underruns; commitment/capital-call handling the PRESUMPTIVE WAVE-8 HEADLINE (the last thesis §2.1 leg with zero code).
- **HG-1 gate (OD-A) = always-measure-and-audit + opt-in bound** (NOT a mandatory default — promotion has no economic as-of, so a mandatory default would rot every fixed-date fixture against the wall clock). Distinct `ProxyWeightStaleEstimateError` (not a subclass) with its own exact-type map entry; three unmeasurable shapes fail closed under a bound; promote-day anchor ratified (valid_from rejected). Declared-on-model v2 recorded as the escalation, not taken (captured-vs-governed fence).
- **HG-1 OD-B = expire-a-mapping DEFERRED** with the census facts (no time-based op exists; three structural shapes; per-family "no head" divergence; migration + pin-serializer landmine).
- **HG-1 OD-C = the 11-row constants sweep** with finding keys preserved verbatim; the executable per-searched-set conformance fence; `MF1_CLOSURE_FINDING` note amended; 6 methodology docs' dated amendments.
- **HG-1 OD-D = stage 3 of the living tenant** — a NEW private-credit instrument (`PC-BRIDGEWATER-II`) runs the genuinely-private α=0.4 chain on multi-family factors (the one combination nothing demonstrated); NO validation record filed (OQ-5: every bound version has a live outcome; an EXCEPTION would be false ceremony).
- **audit key named `promotion_age_days`, NOT `estimate_age_days`** — BT-2's persisted column of that name has a DIFFERENT anchor (covariance window_end vs promote-day); an evidence reader must never see two same-named ages disagree.

## Key Learnings
- **A wave close is the single best-fit task for an ultracode Workflow** in this project's cadence (wide adversarial fan-out: per-slice audit × per-lens, 2-refuter verification, judge claim-checks, completeness critic). The Wave-6 close ran 78 agents; verification killed 4 findings + downgraded 3 before they reached the document. Planning/implementation slices don't need standing-on — the census→3-verifier→4-finder pattern already catches everything.
- **Workflow resilience**: (1) the safety classifier can transiently block INDIVIDUAL workflow agents ("Stage 2 classifier error") — resume-from-cache recovers at zero re-spend; (2) a session usage limit mid-workflow loses only the un-cached tail — the journal preserves everything completed. Merge two runs' result files by domain to recover the full evidence set.
- **A promote-time age gate has NO pinned "new" side** (unlike BT-2's two-pinned-dates arithmetic: covariance window_end − span end). This is why the bound must be opt-in and the anchor must be the promote-day (an audited FR-write instant), and why every fixed-date fixture/demo-seed would rot under a mandatory default.
- **The marketdata write-error dispatcher is an EXACT-TYPE lookup with FIXED details** (`api/marketdata.py` `_raise_mapped_write` does `errors[type(exc)]`): (a) it discards `str(exc)` and substitutes the mapped detail, so a reused `ProxyWeightInputError` would give a FALSE "cited run is not visible" detail for a staleness refusal; (b) a subclass 500s (KeyError inside the handler). Fix = a DISTINCT class with its own exact-type entry. This is the same VW-1-class raw-500-vs-422 trap.
- **The pre-ratification verifier pass keeps paying for itself** — HG-1's changed the ratified shape THREE times (the wire mechanism; the demo date redesign; a 7-vs-6 count correction in my own census). MF-1's killed 2 of my own claims. Standing lesson.
- **Small fixture noise can dominate a small regression** — at df=2 (6 quarterly periods, intercept + 3 slopes) any useful idiosyncratic term swamps recovery; the honest generator carries NO eps term (only 6dp mark quantization). Also the declared factor paths must be checked for near-collinearity (the numeric finder caught corr≈0.99 MKT≈CRSPD, cond 1147 → decorrelated to 317).
- **Closure-by-supersession** is the only mechanical condition-closure concept (latest-outcome-wins per model_version_id); there is no finding-status/remediation lifecycle (the MG-2 candidate, SR 26-2 §VI).
- **CI suite ORDERING is load-bearing** — all PG suites share one DB; the campaign suite's 16-code pins are false on an extended tenant, so it's fresh-schema-only and runs FIRST; extension/stage-3 suites run after it, before the downgrade smoke.
- **Wave-6 outward-benchmark verdict**: the Wave-4 five-gap list is FULLY CONSUMED (first close ever); the frontier moved structure→governance→**missing depth** (2003-vintage transformation math, real ES, remediation tracking, first scheduler). Nothing runs on a schedule (worker still `{"status":"idle"}`); no limits/breaches.

## Solutions & Fixes
- **Recover a truncated ultracode Workflow result**: `json.load(open(task_output))['result']` then merge two runs (`resumeFromRunId` re-run) by audit domain, taking verdicts from whichever run has them. Judge analyses live in `result['judges'][n]['analysis']`.
- **GitHub API degraded-service handling**: the Actions `workflow_runs` API returned a "Unicorn!" HTML error page repeatedly; poll `.../commits/<sha>/check-runs` instead (returned `CHECKS 5 ['success']`), and get the run number from `actions/runs?head_sha=<full_sha>`. Token via `printf 'protocol=https\nhost=github.com\n\n' | git credential fill | sed -n 's/^password=//p'`.
- **Local PG battery recipe** (recurring): `docker exec irp_pg_local psql -U irp -d irp -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO irp; GRANT USAGE ON SCHEMA public TO PUBLIC;"` then `alembic upgrade head` — the `GRANT USAGE ... TO PUBLIC` is MANDATORY (else ops tests fail UndefinedTable). Container is `irp_pg_local` on port 5432. Run `cd` into the repo before `alembic` (it's not on PATH from the parent dir).
- **Three-stage demo re-seed** (the OQ-W6C-3 durability practice): `run_demo_campaign.py` → `run_demo_multifamily.py` → `run_demo_hg1.py`, each `DATABASE_URL=...`. End state: 17 models / 23 validation records / 63 runs + the stage-3 private chain.
- **SnapshotNotFound / dangling snapshot**: `input_snapshot_id` is a bare non-FK GUID column; `resolve_snapshot` raises `SnapshotNotFound` on a dangling id — the THIRD unmeasurable shape (the first draft missed it; BT-2 handles it by name at `var_service.py`).
- **The conformance fence caught its own author** — the `'FL-1' not in edited constant` test failed on my rewrite of `VAR_LIMITATIONS[0]` ("the pre-FL-1 CURRENCY-only framing"); reworded to "pre-widening". Exactly the hazard it was ratified to catch.
- **Test helper API drift**: `update_run_status(session, run, RunStatus.RUNNING)` (positional run object + enum member, NOT `run.run_id` + `.value` + `acting_tenant=`); `DatasetSnapshot` needs `label`/`as_of_known_at`/`component_count`/`manifest_hash` (not `as_of_system_at`).

## Files Modified
### Wave-6 close + ratification (branches wave-6-close `be24ccc`, wave-6-ratify `820926d`; merged PR #52 `9d561bf` + PR #53 `3842b7d`)
- `10_delivery_backlog/wave_6_close_review.md`: NEW — the full close review (Parts 1–7, OQ-W6C-1…6); flipped RATIFIED.
- `10_delivery_backlog/delivery_roadmap.md`: MF-1 DONE row + amendment log; Part 2.10 (Wave-7 sequence); register hygiene ×3.
- `docs/project_memory/current_state.md`: banner → Wave-6 closed/ratified, Wave-7 ratified, NEXT = HG-1 planning.
- `docs/project_memory/phase_status.md` + `next_actions.md`: RETIRED to pointer stubs.
- `10_delivery_backlog/mg_1_decision_record.md`: dated MF-1 supersession note (16/6/10 → 17/7+11/63); `07_.../model_governance_independence_policy.md` MG-16 guard-count fix; `02_.../requirements_traceability_matrix.md` REQ-MDG-001 flip; `10_.../mf_1_decision_record.md` Part-4 header; `CLAUDE.md` autonomy-mechanics note + read-order.
### MF-1 closeout (branch mf-1-closeout, PR #51)
- `mf_1_decision_record.md` CLOSED + CI #323; roadmap row + banner + `mf-1-planning-state` memory.
### HG-1 (branch hg-1-impl, commit `9e3200a`, PR pending)
- `packages/shared-python/src/irp_shared/risk/proxy_weight_service.py`: `ProxyWeightStaleEstimateError` class + the promote-path age logic (3 unmeasurable shapes, opt-in bound, promote-day anchor); stale comment fix.
- `packages/shared-python/src/irp_shared/marketdata/proxy_mapping.py`: `promotion_age_days` optional param on capture/supersede; merged into the CREATE audit `after_value` only-when-supplied.
- `apps/backend/src/irp_backend/api/marketdata.py`: `max_promotion_age_days` field (ge=1); exact-type map entry; except-tuple; import.
- `packages/shared-python/src/irp_shared/risk/bootstrap.py`: the 11-row constants sweep (C1–C7/P1–P2/S1/O1); token-purge fold.
- `packages/shared-python/src/irp_shared/demo/hg1_private.py`: NEW — stage-3 runner (PC-BRIDGEWATER-II, 8 quarterly marks, 18-row mint, α=0.4 chain); income-carry + decorrelated MKT folds.
- `scripts/run_demo_hg1.py`: NEW CLI shim; `demo/__init__.py` exports; `demo/dossiers.py` MF1_CLOSURE_FINDING note.
- `packages/shared-python/tests/test_demo_hg1.py` + `test_demo_hg1_pg.py`: NEW (12 unit + 4 PG); `apps/backend/tests/test_proxy_weight_endpoint.py` additions; `.github/workflows/ci.yml` stage-3 step; 6 methodology-doc dated amendments.
- `10_delivery_backlog/hg_1_decision_record.md` + `hg_1_implementation_plan.md`: NEW (planning PR #54 `4c8829f`); Part 5.5 + Part 6 dispositions.
### Memory (~/.claude/.../memory/)
- NEW `mf-1-planning-state.md`; updated `MEMORY.md`, `delivery-roadmap-state.md`, `mg-1-planning-state.md`, `fl-1-planning-state.md`.

## Setup & Config
- Repo: `/Users/andrewcox/Projects/investment_risk_platform/investment-risk-platform` (git repo IS this nested dir); branch `main`; origin HTTPS (SSH:22 blocked); `gh` NOT installed — use the GitHub REST API.
- Local PG: container `irp_pg_local` (postgres:16), `postgresql+psycopg://irp:irp@localhost:5432/irp`; alembic reads `DATABASE_URL` (not `IRP_DATABASE_URL`); head `0040_var_estimate_age` (NO Wave-6/HG-1 migration).
- Battery: `make check` (green ~1490); full local-PG fresh 1810/0/0; `.venv/bin/` for python/ruff/alembic/pytest.
- Autonomy: full plan→impl→commit→push→PR→merge grant, BUT the auto-mode classifier blocks Claude's REST PR-create/merge on this repo, so Claude pushes + hands the compare link and the USER opens+merges (recorded in CLAUDE.md at the Wave-6 close).
- Model: switched to `opus[1m]` (Opus 4.8) at session end for /compress.

## Pending Tasks
- **HG-1 impl PR pending user merge** — branch `hg-1-impl` (`9e3200a`), compare link handed. On merge: CI-watch to green, run the OQ-W5C-5 closure-stamp checklist INCLUDING grep-for-"pending" (the Part-4 header is the known tripwire this time), flip Status CLOSED, roadmap Part 2.10 HG-1 DONE row + amendment log, current_state banner, memory (new `hg-1-planning-state`).
- **THEN: ES-HS-1 planning** (Wave-7 slice 2, the headline) — MUST fetch Acerbi-Szekely 2014 to paragraph FIRST (UNVERIFIED); needs the ONE `0041` migration widening the `0028` CHECK (`ck_var_result_parametric_not_null` exempts only literal 'VAR_HISTORICAL' — an ES_HISTORICAL row violates it in PG while passing the SQLite battery); the α-tail-mean estimator (never TCE) pre-pinned at ES-1 inherits; in-slice fork = ship the Acerbi-Szekely ES backtest here or tee as BT-3 with TIPPED Christoffersen.
- Recorded Wave-7 residuals to fetch at their planning: RS-1 → Ledoit-Wolf/RiskMetrics (UNVERIFIED); DS-2 → Getmansky-Lo-Makarov 2004 + Okunev-White 2003 at paragraph (record-cited at PA-1, never extraction-verified).
- ultracode is now OFF — future substantive tasks use the standard opt-in (census/verifier workflow shape is the planning default only when the user opts in).

## Errors & Workarounds
- **Workflow `audit:mf1` blocked by the safety classifier mid-run** ("Stage 2 classifier error") → resumed via `resumeFromRunId` (cached agents replay free); the resume then hit the session usage limit on the judges/critic (which had completed in run 1) → merged the two result files by domain.
- **GitHub Actions API returned HTML "Unicorn!" error pages** (partial degraded service) → switched to the check-runs endpoint + retries; confirmed CI #314/#323 green.
- **`make check` output truncated the pass count** → ran `pytest ... --collect-only` / grepped the dot-log with a python counter for exact numbers.
- **`update_run_status` / `DatasetSnapshot` kwarg errors** in the new unit test → corrected to the real signatures (positional run+enum; label/as_of_known_at/component_count/manifest_hash).
- **The 'FL-1' conformance test failed on my own constant rewrite** → reworded "pre-FL-1" → "pre-widening" across the edited rows (the fence working as designed).
- **`SnapshotNotFound` was an unmapped 500 risk** in the first gate draft (dangling non-FK snapshot id) → the verifier caught it; added as the third unmeasurable shape (None ungated / closed gated).
- **Cosmetic MD060 table-pipe lint warnings** throughout the decision records — the repo's standing table style; ignored (not real errors).

## Key Exchanges
- User: "Should I turn on ultracode (with workflows)?" → recommended YES for the Wave-6 close specifically (best-fit task), per-turn opt-in over standing-on; user enabled it for that turn.
- User "Approve all" (Wave-6 close) → ratification stamps + Wave-7 sequencing; user "Approve" (HG-1) → implementation.
- Recurring pattern: each slice = plan (census workflow → draft record+plan → 3-verifier pass → fold → OQ gate briefing in plain language) → user merges planning PR + approves → implement → 4-finder review → fold → battery → push impl PR → user merges → closeout stamps.

## Custom Notes
None

---

## Quick Resume Context
HG-1 (Wave-7 hygiene opener) is implemented+reviewed (zero HIGH) on branch `hg-1-impl` (`9e3200a`) with the PR compare link handed to the user — awaiting their merge. On merge: CI-watch, then the closure-stamp checklist (watch the Part-4 "pending ratification" header tripwire), then memory. The next slice is **ES-HS-1 planning** (Wave-7 headline) which MUST begin by fetching Acerbi-Szekely 2014 to paragraph and needs the ONE `0041` migration widening the `0028` `ck_var_result_parametric_not_null` CHECK. Wave 7 = HG-1→ES-HS-1→RS-1→DS-2; capital-calls is the presumptive Wave-8 headline. ultracode is OFF (standard opt-in for workflows).

---

## Raw Session Log

*(This session continued from a prior compacted session. It covered: the MF-1 closeout after PR #50 merge; the Wave-6 close review run as the first full ultracode Workflow (78 agents — 6 audit domains with 2-refuter verification, 2 judge passes with claim-checks, a completeness critic), authored single-threaded into `wave_6_close_review.md`, then ratified "Approve all" (OQ-W6C-1…6) with the fix-at-close diff, the estimate-staleness residual re-opened→HG-1, the ledger stubs, and Wave 7 ratified as fork A; the HG-1 planning census (3-domain workflow) → draft record+plan → 3-verifier pre-ratification pass (3 HIGHs folded: the wire-mechanism trap, the demo date three-way redesign, the count correction) → OQ gate → user "Approve" → implementation of the promote age gate + the 11-row constants sweep + stage-3 demo + tests → the 4-finder review (zero HIGH; fence-coverage MED + numeric carry/decorrelation folds applied) → battery green (full-PG 1810/0/0) → push `9e3200a`. Full turn-by-turn detail is preserved in the conversation transcript at the session JSONL; this log's structured sections above capture the decisions, learnings, fixes, files, pending tasks, and errors verbatim from that work.)*
