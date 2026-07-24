# Session Log: 23-07-2026 18:49 - wave11-scheduler-limits

## Quick Reference (for AI scanning)
**Confidence keywords:** investment-risk-platform, SCH-1 scheduler, LIM-1 limits/breach, Wave-11 operationalize, Fable audit, 4-finder review, OQ-1=B non-BYPASSRLS, 2L-maker SoD, not-a-governed-number, INV-SCH-1, current_tick no-backfill, breach_direction ABOVE/BELOW, PreciseDecimal(34,12), limit_health recompute, silent-green fail-open, P3-5 cross-tenant FK, marketdata import fence, json_safe dedup, sibling-import CI, migration 0049/0050, run_operational_tick_for_tenant, MG-2 deferral, PR #108 #110, ratification gate, closeout
**Projects:** investment-risk-platform (governed enterprise investment-risk platform; nested repo at `~/Projects/investment_risk_platform/investment-risk-platform`; branch main; origin HTTPS on ghostai8088/investment-risk-platform)
**Outcome:** Wave-11 opened: SCH-1 (first scheduler) shipped + CLOSED (PR #108/#110) with a Fable foundation audit (SOUND); LIM-1 (first governed write-side limit+breach control) planned→ratified→implemented→4-finder-reviewed (ZERO HIGH, 6 MED folded)→pushed→CI GREEN, awaiting user merge, then closeout, then MG-2.

## Decisions Made
- **SCH-1 OQ-1=B (Tier-3 crux, ratified):** cross-tenant dispatch is INFRA-DRIVEN per-tenant (the app stays 100% non-BYPASSRLS). Option A (in-app ops-role cross-tenant read) was REFUTED by the verifier as a genuine 3-part doctrine expansion (first-ever ops grant on non-audit tables + inverting the test-enforced no-grant invariant + reading governed-run provenance cross-tenant). SCH-1 OQ-2/3/4 = rec (reuse worker; no-backfill interval cadence VaR-only; record+continue on failure).
- **SCH-1 = NOT a governed number** (counts unchanged 23/38/109) — a control-plane object (schedule EV ENT-061 + scheduled_run IA ENT-062).
- **Fable foundation audit (post-SCH-1-close): verdict SOUND, proceed straight to LIM-1, no SCH-1b shim.** Four demands ratified into LIM-1: (1) breach discovery via `calculation_run`/`calc.reads` NOT `scheduled_run` (manual runs limit-checked too); (2) breach eval is a PHASE of the ONE per-tenant operational tick, not a Schedule row; (3) notifications assembled per-tenant inside the tick (OQ-1=B forbids cross-tenant DB reads, not outbound egress); (4) "re-cadence = new schedule" grid-frozen-for-life is a STANDING invariant (MG-2's expected-tick arithmetic depends on it).
- **LIM-1 OQ-1..4 = A (all ratified):** OQ-1=A EV `limit_definition` header + self-describing breach echo (threshold history via LIMIT.CHANGE audit trail, NOT FR-bitemporal); OQ-2=A exact `scope_portfolio_id` match (firm rollup=v2); OQ-3=A metric set = VAR/`var_value` + ACTIVE_RISK/`te_value`, hardcoded map + fail-closed unit guard + required benchmark_id for ACTIVE_RISK; OQ-4=A DETECT+record+read, the limit is 2L-managed and immediately ACTIVE (the formal LIMIT.APPROVE maker-checker gate + the breach ASSIGN/1L/2L/ESCALATE/CLOSE lifecycle DEFERRED to MG-2).
- **LIM-1 = NOT a governed number** — a breach references an already-governed `calculation_run`, binds no snapshot/model (counts stay 23/38/109). Realizes pre-reserved ENT-031 `limit_definition` (EV) + ENT-033 `breach` (IA); activates genesis-reserved LIMIT.* (EVT-060) / BREACH.* (EVT-070) audit codes.
- **The SoD twist (LIM-1):** `limit.manage` is a 2L RISK-MANAGER function (risk_manager_2l), NOT the 1L analyst (author≠limit-setter, the VW-1 precedent) — DIVERGES from SCH-1's `schedule.manage` 1L placement (per personas + BX-SOD).
- **Fable audit spend decision:** the user had 9% of Fable allocation + 1-day-to-reset → use-it-or-lose-it → spent it on a forward-looking SCH-1-foundation architecture audit (highest-value, not a code re-review). Confirmed worthwhile (4 concrete LIM-1 demands recorded).

## Key Learnings
- **A health/status surface for a fail-open control must RECOMPUTE its verdict from the source of truth, never infer it from the presence of an evidence row.** LIM-1's `limit_health` originally read the breach TABLE → false-green on a breaching-but-not-yet-evaluated run, false-red after a loosened threshold. Fixed to recompute `_breaches(observed, threshold, direction)` from the latest value.
- **An echo/store column must carry at least the integer-range of every source it copies.** Breach echo was `PreciseDecimal(28,12)` (16 integer digits, ~10^16 cap) but source `var_value` is `(28,6)` (22 integer digits, ~10^22) → a low-unit-currency (IDR/IRR/VND) large-book VaR overflows → DataError → swallowed by the catch-all → silent-green forever. Fixed to `(34,12)` (22 integer digits + 12 scale — holds both var_value and te_value losslessly).
- **A per-item isolation loop that swallows exceptions must classify the SPECIFIC benign exception (constraint name), never a whole class.** `poll_tenant_breaches` masked ALL IntegrityError as the benign dedup; fixed with `_is_breach_dedup(exc)` checking `uq_breach_limit_run` specifically + logging any other IntegrityError/eval failure. (Same pattern SCH-1 established with `_is_tick_dedup`.)
- **The isolation guarantee is only as strong as its narrowest `except`.** SCH-1's failure-recording path caught only IntegrityError → a non-integrity error there could escape and unwind sibling schedules; made fully catch-all.
- **A cross-test-module import MUST use the bare sibling form `from test_x import ...`, never `from tests.test_x import ...`** — the latter only resolves when cwd is on sys.path (local run from packages/shared-python), NOT under CI's repo-root `python -m pytest` (ModuleNotFoundError: No module named 'tests'). The repo convention (test_es_hs, test_p3c1_hardening) uses the bare form.
- **PG FK checks BYPASS RLS (the P3-5 doctrine):** any caller-supplied FK id (scope_portfolio_id, benchmark_id) must be re-resolved tenant-filtered before write, else a cross-tenant FK reference + existence oracle. SCH-1's `create_schedule` has the SAME latent gap (carry).
- **When a compare/PR is merged, verify what actually landed on main (`git ls-tree origin/main`), don't assume the branch tip merged.** PR #107 merged ONLY the SCH-1 planning DRAFT (`a382b93`), not the implementation; the full impl re-landed via PR #108.
- **A fail-closed invariant spanning a per-item isolation loop AND the reproducibility invariant (INV-SCH-1: `scheduled_for` = pure `current_tick` grid value, never a wall clock) must be self-enforced at the write boundary** (`_assert_current_tick`), not just upheld by the caller contract.
- **The no-backfill cadence model:** a fresh re-pin is inherently as-of-now, so a scheduler must NEVER backfill (which would manufacture a fraudulent daily series of identical numbers wearing different date stamps); fire at most the current grid tick, leave missed ticks as honest ledger gaps. This one fix folded two blocking verifier defects (fake-series + pause/resume storm).

## Solutions & Fixes
- **`(34,12)` precision** — `limit/models.py` threshold_value/observed_value + migration `0050` Numeric(34,12) (was 28,12) — the overflow/silent-green fix.
- **`limit_health` recompute** — `limit/service.py` derives state from `_breaches(observed,...)`, not the breach table.
- **Constraint-specific dedup + logging** — `apps/worker/src/irp_worker/breaches.py` `_is_breach_dedup` (uq_breach_limit_run only) + `logging.getLogger` on non-dedup/eval failures.
- **P3-5 cross-tenant FK guard** — `create_limit` calls `assert_portfolio_in_tenant` (portfolio.guards, models-only fence-safe) + a raw-SQL `SELECT 1 FROM benchmark WHERE id=:id AND tenant_id=:t` (avoids the marketdata import fence) + a duplicate-code pre-check → clean LimitError.
- **marketdata import fence fix** — `test_nothing_imports_marketdata` caught `from irp_shared.marketdata.benchmark` in limit/service.py (marketdata is a leaf; limit not whitelisted); replaced `resolve_benchmark` with the raw-SQL existence check.
- **json_safe dedup** — `test_no_binder_redefines_json_safe_locally` caught a local `_json_safe`; replaced with the canonical `irp_shared.audit.payload.json_safe`. (Root cause: LIM-1's `update_limit` audit before/after carried a raw Decimal threshold_value — not JSON-serializable; LIM-1 is the first EV entity with a Decimal knob.)
- **SCH-1 CI-collection fix** — `test_scheduler_dispatch.py` switched `from tests.test_var` → `from test_var` sibling import.
- **Migration-head assertion sweep** — 20 test files `get_current_head()` 0048→0049 (SCH-1) then 0049→0050 (LIM-1); `test_synthetic` next-slot guard 0049→0050→0051.
- **Local PG recipe** — `postgresql+psycopg://irp:irp@localhost:5432/<db>` on container `irp_pg_local`; DROP/CREATE DB + `alembic upgrade head` + `GRANT USAGE ON SCHEMA public TO PUBLIC`; RESET the schema between FULL runs (a shared-DB accumulation artifact caused false demo-count failures on a second run).
- **breach_direction anti-inversion** — `ABOVE`=breach⟺observed>threshold (ceiling, default), `BELOW`=breach⟺observed<threshold (floor); strict boundary (==threshold is compliant). Replaced the ambiguous `LTE`/`GTE` naming that invited backwards coding.
- **run_operational_tick_for_tenant** — renamed from run_scheduler_for_tenant; composes poll_tenant_schedules (phase 1) then poll_tenant_breaches (phase 2) under one run_in_tenant terminal commit; schedules-before-breaches so a fresh VaR is evaluable same-tick.

## Files Modified
### SCH-1 (shipped, merged main via PR #108/#110)
- `packages/shared-python/src/irp_shared/scheduling/{__init__,events,models,service}.py` — Schedule (ENT-061 EV) + ScheduledRun (ENT-062 IA); current_tick/is_due/select_active_due/dispatch_one/record_failed_dispatch + schedule CRUD + audit emit.
- `apps/worker/src/irp_worker/scheduler.py` — poll_tenant_schedules (per-schedule SAVEPOINT isolation, `_is_tick_dedup`, catch-all `_record_failed`) + run_operational_tick_for_tenant + main().
- `migrations/versions/0049_scheduling.py`; `packages/shared-python/tests/test_scheduler{,_dispatch,_pg}.py`.
### LIM-1 (branch lim-1-planning, HEAD 3f3fe7d, CI green, awaiting merge)
- `packages/shared-python/src/irp_shared/limit/{__init__,events,models,service}.py` — LimitDefinition (ENT-031 EV) + Breach (ENT-033 IA self-describing); `_METRIC_MAP` (hardcoded (run_type,metric_type)→(col,unit,requires_benchmark)); `_breaches` predicate; `evaluate_limit`/`select_active_limits`; create/update/suspend/resume_limit; `limit_health`; audit emit.
- `apps/worker/src/irp_worker/breaches.py` — poll_tenant_breaches (per-limit SAVEPOINT + `_is_breach_dedup` + logging).
- `migrations/versions/0050_limit_breach.py`; `packages/shared-python/src/irp_shared/models.py` (aggregator).
- `packages/shared-python/src/irp_shared/entitlement/bootstrap.py` — limit.manage (risk_manager_2l), limit.view/breach.view (all 4 tiers incl auditor_3l).
- `04_data_model/audit_event_taxonomy.md` (LIMIT/BREACH activation rows) + `canonical_data_model_standard.md` (ENT-031/033 realized + SCH-1 ENT-061/062 doc-lag swept).
- `packages/shared-python/tests/test_limit{,_breach,_active_risk,_pg}.py`.
### Decision records / roadmap / memory
- `10_delivery_backlog/{sch_1,lim_1}_decision_record.md` (Parts 0-6); `delivery_roadmap.md` (Part 2.14 + amendment log + Fable audit demands); `docs/project_memory/current_state.md`.
- Memory: `~/.claude/projects/-Users-andrewcox-Projects-investment-risk-platform/memory/{sch-1-planning-state,delivery-roadmap-state}.md` + MEMORY.md index (LIM-1 pending on merge).

## Pending Tasks
- **Merge `lim-1-planning`** (CI green, HEAD 3f3fe7d) → main; user opens+merges (auto-mode classifier blocks Claude's REST merge).
- **LIM-1 closeout** (on merge): stamp lim_1_decision_record.md CLOSED with merge hash + PR#; sweep roadmap (Part 2.14 mark LIM-1 DONE + amendment entry + NEXT=MG-2), current_state.md (LIM-1 CURRENT TRUTH), memory (new lim-1-planning-state.md + MEMORY.md index + delivery-roadmap-state.md).
- **MG-2** (Wave-11 slice 3, the FINAL slice) — the remediation lifecycle: realize ENT-034 breach_action + the DEP-WFL breach state machine (ASSIGN→1L_RESPONSE→2L_REVIEW→ESCALATE→CLOSE), the formal LIMIT.APPROVE maker-checker gate, and MG-2's deadline enforcement rides the SCH-1 cadence. Then the mandatory Wave-11 close review.
- **Carries (recorded):** SCH-1 `create_schedule` has the SAME P3-5 cross-tenant FK gap (scope_portfolio_id + model_version_id) — harden when the schedule/limit API endpoints land; the `schedule.manage`/`limit.manage` API forward-gate (require_permission) when endpoints ship; PPF-3 v2 leverage seam.

## Errors & Workarounds
- **PR #107 merged only the planning DRAFT** (a382b93), not the SCH-1 implementation — discovered via `git ls-tree origin/main` showing no scheduling models/migration. Re-landed the full impl via PR #108; PR #110 = SCH-1 closeout.
- **SCH-1 CI failure `ModuleNotFoundError: No module named 'tests'`** — `from tests.test_var` import resolves locally (cwd on path) but not under CI repo-root pytest → switched to bare `from test_var` sibling import.
- **Shared-PG-DB accumulation artifact** — running the FULL suite twice against the same un-reset DB caused false `test_ppf1/ppf2_governed_number_counts_moved` failures (demo-count tests are order/accumulation sensitive). Fixed by rebuilding a fresh DB per authoritative full run (the standing "reset schema between full runs" rule).
- **Conformance-test catches (the clean-code bars):** `test_no_binder_redefines_json_safe_locally` (local _json_safe dup) and `test_nothing_imports_marketdata` (limit importing marketdata.benchmark) — both real architecture-fence violations caught by the suite, both folded (canonical json_safe; raw-SQL benchmark check).
- **Network drop mid-review** — the pre-ratification verifier agents died on ENOTFOUND/stalled-stream; relaunched cleanly.

## Custom Notes
None

---

## Quick Resume Context
Wave-11 ("operationalize") is in progress on the governed investment-risk platform. SCH-1 (first scheduler) is CLOSED on main; LIM-1 (first governed write-side limit+breach control) is implemented, 4-finder-reviewed (ZERO HIGH, 6 MED folded), pushed to branch `lim-1-planning` (HEAD 3f3fe7d), CI GREEN — awaiting the USER's merge. On merge: run the LIM-1 closeout (stamp CLOSED, sweep roadmap/current_state/memory) then plan MG-2 (Wave-11 slice 3, the final slice — the breach remediation lifecycle + LIMIT.APPROVE gate, realizing ENT-034). Standing cadence: plan→ratify-via-OQ-forks→implement-one-commit-per-step→make-check→pre-ratification-verifier→4-finder-review→fold→push; USER opens+merges PRs. Standing directives: last sentence of every response = model+effort rec; concise prose; plain-language gate briefings; clickable PR links.

---

## Raw Session Log

> Note: this multi-hour session is far too long to reproduce verbatim; the following is a faithful, detailed reconstruction of the arc. The Decisions/Learnings/Fixes/Files sections above capture the substance; this section records the sequence.

**Continuation entry point:** Session resumed mid-SCH-1-planning (post-compaction). SCH-1 grounding census recon (agent) had just completed, mapping the substrate: no tenant registry exists (TenantMixin is a column, not a table); audit_verify's cross-tenant enumeration under a runtime rolbypassrls self-check + a separate ops DATABASE_URL is the AD-015 precedent; execute_governed_run scaffold; the worker's run_in_tenant per-tenant slot; the calendar tables carry no business-day logic; utcnow() is the only clock (reproducibility = the snapshot pin, AD-014).

**SCH-1 planning:** Drafted the decision record realizing the crux fork F-DISPATCH (in-app ops-role cross-tenant read vs infra-driven per-tenant). Two pre-ratification verifiers RAN: REFUTED Option A as a 3-part doctrine expansion (rec flipped to B) + found TWO blocking cadence defects (backfill fraudulent-series + pause/resume storm), both folded by the no-backfill/coalesce-to-current_tick model; INV-SCH-1 elevated. Surfaced OQ-SCH-1-1..4; user ratified OQ-1=B, OQ-2/3/4=rec.

**SCH-1 implementation** (one commit per step): scheduling models/events (ENT-061/062) → migration 0049 → R-07 mint + SCHEDULE audit taxonomy (EVT-260) → the service (current_tick/is_due/select_active_due/dispatch_one, audited CRUD) → the worker poll loop (per-schedule SAVEPOINT isolation) → tests (unit + e2e dispatch + PG RLS/append-only/ops-no-grant). Build-time bug caught by recon: dispatch resolved a plain EXPOSURE run when run_var needs a FACTOR_EXPOSURE run — fixed. make check + full-PG green; 4-finder review: ZERO HIGH, 4 MED folded (over-broad IntegrityError masking; non-catch-all failure path; INV write-boundary enforcement; resilience coverage). Pushed.

**SCH-1 CI failure + re-land:** CI red on `ModuleNotFoundError: No module named 'tests'` (the `from tests.test_var` import). Fixed to the bare sibling import; discovered PR #107 had merged only the planning DRAFT (a382b93). Full impl re-landed via PR #108 (CI green). SCH-1 closeout (PR #110): stamped CLOSED, swept roadmap/current_state/memory.

**Fable foundation audit:** user asked whether to spend 9%-remaining Fable allocation (1-day reset). Recommended a forward-looking architecture audit ("is SCH-1 the right foundation for LIM-1/MG-2?") over a code re-review. Ran (Fable agent): verdict SOUND, no shim; recorded 4 demands for LIM-1 planning (calc-run discovery, tick-phase not schedule-row, per-tenant notification, grid-frozen-for-life). Riders committed to the roadmap + memory.

**LIM-1 planning:** substrate census (entities ENT-031..034 + LIMIT/BREACH audit codes reserved since genesis; requirements prescribe EV/IA temporal classes; the 2L-maker SoD from personas + BX-SOD; the metric-selector (run_type,metric_type)→var_value/te_value with a currency-vs-fraction unit landmine; discovery via calc/reads). Rule-6 research (FSB RAF, three-lines breach lifecycle, hard/soft limits). Decision record drafted; two pre-ratification verifiers RAN: two BLOCKING correctness holes folded pre-gate (the breach predicate inversion trap → breach_direction; active-risk under-specified without benchmark_id → added) + hardening (hardcoded metric map + fail-closed unit assert; self-describing echo; limit-health surface; ordering invariant). Surfaced OQ-LIM-1-1..4; user ratified all = A.

**LIM-1 implementation** (one commit per step): models (ENT-031/033) + events + migration 0050 → R-07 2L mint + LIMIT/BREACH taxonomy activation → the service (metric map, _breaches predicate, evaluate_limit, audited CRUD, limit_health) → the worker breaches phase + run_operational_tick_for_tenant rename → tests (unit + e2e breach "living demo" + active-risk e2e + PG) + canonical-doc sweep. Reference-card recon corrected benchmark_id to a nullable hard FK. json_safe conformance failure fixed (Decimal audit payload). 4-finder review: ZERO HIGH, 6 MED + LOWs folded (the silent-green fail-open cluster: limit_health recompute + constraint-specific dedup + logging; the (34,12) precision overflow; the P3-5 cross-tenant FK guard; active-risk + floor e2e coverage; unit assert/dup-code/coercion/severity/count LOWs). marketdata import fence violation (from the FK guard) fixed with a raw-SQL benchmark check. Full suite exit-0 on a fresh DB; pushed (3f3fe7d); CI GREEN all 6 checks.

**Current state:** awaiting the user's merge of lim-1-planning, then the LIM-1 closeout, then MG-2 (the final Wave-11 slice) + the Wave-11 close review.
