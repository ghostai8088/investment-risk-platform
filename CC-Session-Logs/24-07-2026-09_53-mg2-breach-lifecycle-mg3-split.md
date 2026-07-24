# Session Log: 24-07-2026 09:53 - MG-2 Breach Lifecycle + MG-3 Split

## Quick Reference (for AI scanning)
**Confidence keywords:** MG-2, breach remediation lifecycle, DEP-WFL state machine, ENT-034 breach_action, migration 0051, LIM-1 closeout, MG-3 split, LIMIT.APPROVE deferred, OQ-1=B scope fork, person-level SoD, SOD-02, breach.respond, breach.review, FOR UPDATE lock, epoch_seq idempotency, uq_breach_escalation, monotonic seq, recency-derived state, poll_tenant_breach_deadlines, third tick phase, auto-escalation, pre-ratification verifier, 4-finder review, review-requires-response HIGH, ORDER BY lock-order deadlock, _as_utc tz-naive, RLS GUC txn-local, migration head guards, Wave-11, PR #113 aa6503f, PR #112, PR #111, mg-2-closeout, make check 1915, alembic zero-drift
**Projects:** investment-risk-platform (governed enterprise investment-risk platform; Wave 11 "operationalize")
**Outcome:** MG-2 (the breach remediation lifecycle, Wave-11 slice 3) fully delivered — planned → pre-ratification-verified (3 blocking folds) → RATIFIED OQ-1=B (LIMIT.APPROVE split to a new slice MG-3) → implemented → 4-finder reviewed (1 HIGH + 4 MED folded) → merged (PR #113) → closed out. LIM-1 closeout also merged (PR #112). Next = MG-3 planning, then the Wave-11 close review.

## Decisions Made
- **LIM-1 closeout completed first** (resume-time): PR #111 was already merged; stamped lim_1_decision_record CLOSED, swept roadmap/current_state/memory, pushed `lim-1-closeout` (eff668e → merged as PR #112 `886a86f`).
- **MG-2 scope re-opened as a Part-4-rule-3 STRUCTURAL finding → OQ-1=B (user-ratified).** MG-2's ratified scope was "breach lifecycle AND the LIMIT.APPROVE maker-checker gate." At the gate I surfaced that these are TWO distinct governance primitives; user chose **B**: ship the breach lifecycle as MG-2, **split LIMIT.APPROVE to a NEW focused slice MG-3** (it's the platform's first person-level SoD AND changes the limit EVALUATION path — a DRAFT limit is not polled — so it warrants its own adversarial review). **Wave 11 is now 4 slices: SCH-1 → LIM-1 → MG-2 → MG-3.**
- **OQ-4=A (user-ratified): auto-escalation with teeth** — a THIRD phase of the SCH-1 per-tenant operational tick auto-escalates overdue breaches. (OQ-2=A append-only action log + recency state; OQ-3=A the transition/role/SoD map — adopted as recommended.)
- **Recency-derived current state, NEVER a mutated flag** (forced by breach_action being IA append-only; the VW-1 model_validation precedent; the LIM-1 "recompute from truth" lesson).
- **Deadlines do NOT ride `current_tick`** — a fixed response deadline is compared `response_due < now` (the `next_review_due < today` precedent), not a recurring grid.
- **Audit codes REALIZE (no taxonomy mint)** — BREACH.ASSIGN/.1L_RESPONSE/.2L_REVIEW/.ESCALATE/.CLOSE are genesis-reserved (EVT-070); MG-2 mints only PERMISSIONS (breach.respond/breach.review) via R-07. Reserved spellings are `.1L_RESPONSE`/`.2L_REVIEW` (not `.RESPOND`/`.REVIEW`).
- **Idempotency epoch re-keyed to `epoch_seq` (a monotonic id), not the derived `response_due` timestamp** — 4-finder F1-MED1 fold (two epochs computing the same due-time would silently suppress a real re-escalation).

## Key Learnings
- **THE HEADLINE LESSON (MG-2): a state machine layered on an append-only log needs (1) a DB-monotonic ordering key — NOT a random uuid or a caller-supplied timestamp — for deterministic recency; (2) a per-item write lock (SELECT … FOR UPDATE) for linearizable transitions under concurrent ticks; (3) an idempotency epoch keyed on a monotonic id, never a derived value. AND a "requires a prior step" control must be enforced EXPLICITLY, because an empty set-check passes vacuously** (the F1 HIGH: the person-level SoD existed but was toothless on the no-1L-response path — an empty responder set made `actor in responders` trivially False).
- **Run the pre-ratification verifier BEFORE the user's ratification gate** (the standing ES-1 lesson) — it caught 3 BLOCKING concurrency holes in the DEP-WFL design that were folded before ratify, so the user ratified a sound design.
- **Concurrent per-tenant ticks are a first-class, designed-for condition** (OQ-SCH-1-1=B: infra invokes the worker once per tenant, and may retry) — so any new tick phase that takes cross-loop row locks needs a deterministic lock order (`ORDER BY`) to avoid a lock-ordering deadlock.
- **A PG-only guarantee (FOR UPDATE) exercised by ZERO concurrency tests is false security** — a regression dropping the lock stays green. Prove the lock with a two-connection `FOR UPDATE NOWAIT` test (55P03).
- **The closure-docs gate (`scripts/check_docs.py`) fires on a DONE-in-roadmap record still not-CLOSED** — keep the impl PR at "RATIFIED (impl PENDING)" + roadmap NOT-DONE, and mark DONE/CLOSED only in the separate post-merge closeout (DONE means "merged to main").
- **The migration-head guard convention:** ~20 per-family test files hardcode `get_current_head() == "<latest>"`; a new migration must bump ALL of them, and advance the `test_synthetic` no-migration guard to the NEXT free slot (glob `00NN*`).

## Solutions & Fixes
- **The 3 pre-ratification blocking folds** (design-level, before impl): B-1 nondeterministic recency (`uuid4` id not monotonic; SYSTEM escalate creates a same-`occurred_at` tie) → a per-breach monotonic `seq` (`max+1` under the lock); B-2 escalate-idempotency TOCTOU + unresolved "index OR pre-check" → ONE constraint-backed epoch + a per-breach FOR UPDATE lock; B-3 SoD compared only the LATEST 1L responder → the SET of ALL prior 1L responders.
- **The 4-finder folds (1 HIGH + 4 MED):**
  - HIGH (F1): a breach could reach CLOSED with ZERO 1L response (single 2L assign→review→close, vacuous SoD) → `review_breach` now REFUSES when `_prior_1l_responders` is empty (`BreachTransitionError`, REQ-BRC-002) + regression tests.
  - MED (F1): epoch keyed on derived `response_due` → re-keyed `uq_breach_escalation(breach_id, epoch_seq)` where `epoch_seq` = the governing ASSIGN action's `seq` (new column via `_governing_assign` helper).
  - MED (F3): no `ORDER BY` in `select_overdue_breaches` → lock-ordering deadlock → added `ORDER BY Breach.id`.
  - MED (F3): FOR UPDATE lock untested → `test_for_update_lock_serializes_concurrent_transitions` (two engines, `FOR UPDATE NOWAIT` → OperationalError while locked).
  - MED (F4): audit payload shape + ESCALATED→2L_REVIEW untested → `test_audit_payload_shape_and_severity` (+ narrative NOT leaked) + ESCALATED-review + reject-recovery-to-close tests.
  - LOWs: `_as_utc(now)` at comparison sites; `_sla_due` `KeyError`→`BreachTransitionError` (422); decision-record Part-2 table corrected (v1 escalation is SYSTEM-only).

## Files Modified (MG-2, all merged via PR #113)
- `packages/shared-python/src/irp_shared/limit/models.py`: `BreachAction` (ENT-034, IA append-only) — `seq`, `epoch_seq`, `action_type`, `from/to_state`, `actor_id/actor_line`, `assigned_to`, `response_due`, `narrative`, `review_outcome`, `evidence_ref`, `occurred_at`; `uq_breach_action_seq` + partial-unique `uq_breach_escalation(breach_id, epoch_seq)` (postgresql_where + sqlite_where); `_block_mutation` on before_update/delete.
- `packages/shared-python/src/irp_shared/limit/lifecycle.py`: the DEP-WFL service — `_resolve_to_state` (transition table), `_lock_breach` (FOR UPDATE + tenant re-resolve), `current_breach_state` (recency by seq), `_governing_assign` (epoch/deadline), `_prior_1l_responders` (SoD set), `_next_seq`, `_as_utc`, `_sla_due`; `assign_breach`/`respond_breach`/`review_breach`(requires prior response)/`close_breach`/`escalate_overdue_breach`/`select_overdue_breaches`.
- `packages/shared-python/src/irp_shared/limit/events.py`: BREACH lifecycle event constants, states/action-types/review-outcome vocab, `BREACH_SLA_DAYS` (HARD=1/SOFT=5), `BreachActor`; `breach.status` deprecated-in-place note.
- `migrations/versions/0051_breach_action.py`: breach_action table (FORCE RLS + P0001 append-only trigger + no ops grant); the two idempotency structures; down_revision 0050.
- `apps/worker/src/irp_worker/deadlines.py`: `poll_tenant_breach_deadlines` (the 3rd tick phase, phase-2 single-layer isolation shape).
- `apps/worker/src/irp_worker/scheduler.py`: `_work` adds the "escalated" phase; `main()` surfaces `escalated=N`.
- `packages/shared-python/src/irp_shared/entitlement/bootstrap.py`: R-07 mint `breach.respond`(1L)/`breach.review`(2L), never co-granted.
- Tests: `test_breach_lifecycle.py` (16 unit/e2e), `test_breach_lifecycle_pg.py` (RLS, append-only trigger, cross-tenant lock, uq-escalation, ops-no-grant, FOR UPDATE lock proof), `test_entitlement_bootstrap.py` (SoD conformance), 20 migration-head guard bumps + `test_synthetic` → 0052.
- Docs: `04_data_model/{audit_event_taxonomy.md (BREACH codes ACTIVATED), canonical_data_model_standard.md (ENT-034 REALIZED)}`; `10_delivery_backlog/{mg_2_decision_record.md (Parts 0-6 + CLOSED), delivery_roadmap.md (Part 2.14 + amendment log + MG-3 slice)}`; `docs/project_memory/current_state.md`.
- Memory (`~/.claude/.../memory/`): new `mg-2-planning-state.md`; refreshed `MEMORY.md` + `delivery-roadmap-state.md`; earlier `lim-1-planning-state.md`.

## Pending Tasks
- **Merge `mg-2-closeout`** (docs-only closeout PR, pushed; USER opens+merges).
- **MG-3 planning** (the final Wave-11 slice): the `LIMIT.APPROVE` DRAFT→ACTIVE maker-checker gate LIM-1/MG-2 deferred — mints `limit.approve`, realizes the genesis-reserved `LIMIT.APPROVE` audit code, adds DRAFT to LIMIT_STATUSES + `created_by` on limit_definition, reuses MG-2's person-level SoD primitive (approver ≠ drafter); a DRAFT limit is not evaluated by `select_active_limits`. Decision-record fork options are in `mg_2_decision_record.md` OQ-MG-2-5 (deferred). Same discipline: recon → decision record → pre-ratification verifier → user ratification gate → impl → 4-finder → closeout.
- **The mandatory Wave-11 close review** after MG-3 (Part-4 rule-2 re-baseline).
- **Carries:** SCH-1's `create_schedule` has the SAME P3-5 cross-tenant FK gap (harden at the API endpoints); the `schedule.manage`/`limit.manage`/`breach.respond`/`breach.review` API forward-gate (`require_permission` is latent until the endpoints land); `select_overdue_breaches` N+1 (bound later); PPF-3 v2 leverage seam.

## Errors & Workarounds
- **Branch base:** `mg-2-planning` was first branched from `main` (which lacked the LIM-1 closeout stamps) → rebased it onto `lim-1-closeout` so the roadmap/current_state edits wouldn't collide.
- **SQLite tz-naive round-trip:** `response_due` read back tz-naive on SQLite (PG preserves tz) → `TypeError: can't compare offset-naive and offset-aware` → added `_as_utc` (the `db/bitemporal.py` convention) at every stored-deadline comparison.
- **PG test harness (3 bugs, not code defects):** (1) `set_tenant_context` is txn-local — cleared by `commit()`, so re-arm the RLS GUC before a post-commit read; (2) mutating `breach.tenant_id` on the append-only Breach object triggers a flush→P0001, masking the RLS refusal — use a TRANSIENT stub instead; (3) the append-only test's `rollback()` after the failed UPDATE discarded the un-committed action before the DELETE — COMMIT the action first.
- **`FOR UPDATE NOWAIT` test:** the raw `SELECT id` returns a UUID object; compare `str(got) == breach_id`.
- **mypy:** reassigning a `datetime` param to `datetime | None` (`now = _as_utc(now)`) failed — used a distinct `now_utc` local.
- **NULL-in-unique-index:** the raw-insert escalation test needed `epoch_seq` set on both rows (two NULLs don't collide in a PG unique index).
- **21 migration-head test failures** after adding 0051: bumped all `get_current_head() == "0050_limit_breach"` → `"0051_breach_action"` and advanced `test_synthetic` glob to `0052*`.

## Key Exchanges
- User "proceed" (post-/compact) → discovered LIM-1 PR #111 already merged → ran LIM-1 closeout.
- User "Proceed" → MG-2 planning (parallel recon of LIM-1 surface + VW-1 state-machine precedent + SCH-1 tick/roles/audit substrate → decision record → 2 pre-ratification verifiers → 3 blocking folds).
- Ratification gate (AskUserQuestion): user chose **OQ-1=B** (lifecycle now, LIMIT.APPROVE → MG-3) + **OQ-4=A** (auto-escalate).
- Implementation (6 committed steps) → gates green → 4-finder review (F2 zero HIGH; F1 one HIGH + MED; F3/F4 MEDs) → fold → re-gate → push → CI green → user merged.
- User "proceed" → MG-2 closeout (both PRs #112/#113 merged) → stamped CLOSED + swept.

## Custom Notes
None

---

## Quick Resume Context
MG-2 (the breach remediation lifecycle, Wave-11 slice 3) is DONE + CLOSED (PR #113 `aa6503f`, migration 0051; counts UNCHANGED 23/38/109). The `mg-2-closeout` docs PR is pushed and awaiting the USER's merge. Wave 11 is now 4 slices (SCH-1 ✅ → LIM-1 ✅ → MG-2 ✅ → **MG-3**). **Next work = MG-3 planning:** the `LIMIT.APPROVE` DRAFT→ACTIVE maker-checker gate that MG-2's OQ-1=B split out — mints `limit.approve`, realizes the genesis-reserved `LIMIT.APPROVE` code, reuses MG-2's person-level SoD primitive (approver ≠ the limit's drafter). Then the mandatory Wave-11 close review. Standing directives: last sentence of every response = model+effort rec; plain-language gate briefings; concise prose; clickable PR links; USER opens+merges PRs.

---

## Raw Session Log

*(This session continued from a compacted summary. The full turn-by-turn transcript lives in the session JSONL at `/Users/andrewcox/.claude/projects/-Users-andrewcox-Projects-investment-risk-platform/90ba9b22-3c6e-4eee-b2f8-1f24eaa552bb.jsonl`. Condensed arc below.)*

1. **Resume + LIM-1 closeout:** post-/compact "proceed" → found LIM-1 PR #111 merged → stamped `lim_1_decision_record.md` CLOSED, swept roadmap/current_state/memory, committed `eff668e` on `lim-1-closeout`, pushed (later merged as PR #112 `886a86f`).
2. **MG-2 planning:** "Proceed" → 3 parallel recon agents (LIM-1 breach/limit surface + ENT-034 reservation; VW-1 model_validation state-machine precedent [an append-only judgment log with recency state, role-level SoD only — MG-2's DEP-WFL is greenfield]; SCH-1 tick/roles/audit substrate [3rd phase seam, no reusable overdue primitive, all breach codes genesis-reserved, no clean checker role, no person-level SoD anywhere]). Wrote `mg_2_decision_record.md` (Parts 0-6, OQ-MG-2-1…5). Ran 2 pre-ratification verifiers → 3 BLOCKING concurrency holes (B-1/B-2/B-3) → folded into the record before the gate. Rebased `mg-2-planning` onto `lim-1-closeout`.
3. **Ratification gate:** AskUserQuestion → OQ-1=B (breach lifecycle now; LIMIT.APPROVE → MG-3) + OQ-4=A (auto-escalate). Stamped record RATIFIED, re-scoped roadmap (MG-2 lifecycle-only + new MG-3 slice + amendment entry), committed `d1c1556`/`c4f170e`.
4. **Implementation (one commit per step):** step 1-2 model+events+migration 0051; step 3 lifecycle.py state machine; step 4 permission mint + SoD conformance; step 5 the 3rd tick phase + wiring; step 6 tests (unit + PG) + doc sweep; then bumped 20 migration-head guards + test_synthetic→0052 + a chain test.
5. **Gates:** `make check` GREEN (1911 → 1915 after fold); local PG (0051 up/down smoke, alembic zero-drift, breach+limit families green); fixed 3 PG-harness bugs + the tz-naive `_as_utc`.
6. **4-finder review** over `main...HEAD`: F2 doctrine ZERO HIGH (all 9 hard invariants held); F1 ONE HIGH (vacuous-SoD close path) + MED (derived epoch key) + LOWs; F3 two MED (no ORDER BY deadlock; untested lock); F4 two MED (payload/ESCALATED-review coverage). **All folded:** review-requires-response gate, `epoch_seq` re-key (new column + migration amend), `ORDER BY Breach.id`, the FOR UPDATE NOWAIT lock proof, payload/coverage tests, `_as_utc(now)`, `_sla_due` clean 422, doc corrections. Re-gated green; committed; pushed `mg-2-planning`; CI GREEN all 6 checks.
7. **User merged** (#112 then #113, main HEAD `aa6503f`) → "proceed" → **MG-2 closeout:** stamped `mg_2_decision_record.md` CLOSED, roadmap DONE + NEXT=MG-3 + amendment entry, current_state MG-2 CURRENT TRUTH, new `mg-2-planning-state.md` memory + index/roadmap-state refresh; closure gate green; committed + pushed `mg-2-closeout` (awaiting merge).
8. **/compress** (this step).
