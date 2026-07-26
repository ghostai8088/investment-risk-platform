# Session Log: 26-07-2026 14:32 - OPS-1 and CI-Parity Hardening

## Quick Reference (for AI scanning)

**Confidence keywords:** OPS-1, Wave-12 slice 4, operations UI, breach queue, limit health, approval
queue, first FE write path, `api/writes.ts`, `classifyRefusal`, `expected_seq`, `BreachStaleSeqError`,
`seq` on BreachOut, `useApiGet` reloadKey, Refusal component, AppShell IA, Operations-first nav,
demo `ops_stage14`, `DEMO-GLOBAL`, maker-checker SoD reachability, react-router downgrade refutation,
GHSA-qwww-vcr4-c8h2, GHSA-chx6-hx7r-mcp5, allowlist expiry 2026-10-24, CI-parity hardening,
PG-allowlist drift, `test_ci_pg_coverage.py`, conformance pin, `pg_role_permission_guard`,
role_permission FK, `alembic downgrade base` smoke, install surface, ModuleNotFoundError irp_worker,
`make dep-audit`, `make fe-audit`, `npm ci`, prettier format:check, Wave-12 close review agenda,
analytics breadth, rolling volatility, Sharpe, sector/geography exposure, information ratio

**Projects:** investment-risk-platform (ghostai8088/investment-risk-platform)

**Outcome:** Wave-12 slice 4 (OPS-1, the operations UI — the platform's first VISIBLE deliverable and
first frontend write path) planned, ratified, implemented, reviewed and merged as PR #127; a
follow-on CI-parity hardening slice then closed a systemic harness drift (six PG suites, including
the entire Wave-11/12 RLS enforcement layer, were never run by CI) with two negative-controlled
conformance pins. Wave 12 is functionally complete; the close review is queued and deliberately NOT
started.

---

## Decisions Made

### OPS-1 ratification gate (six OQs)

- **OQ-1 = C, then REVERSED to A in build.** Ratified: pin `react-router-dom` to ≤7.11.x (below the
  advisory's `>=7.12.0` range) to retire the CI allowlist exception with zero React work. **Refuted
  on evidence within the hour** — see Key Learnings. Slice shipped on **A** (split the migration into
  its own slice); tree unchanged at `^7.18.1`.
- **OQ-2 = A** — writes live in a dedicated module (`api/writes.ts`) sharing ONE internal
  identity/error core with `apiGet`. Rationale: keeps the read module's no-write property true, puts
  the whole new write capability in one auditable file, and keeps identity injection
  single-implementation (the SSO-1 drift lesson). Later enforced by eslint, not just a comment.
- **OQ-3 = A** — show all actions; render 403/409 as first-class plain-language explanations naming
  the control. No `/me` endpoint. Rationale: enforcement is server-side by doctrine, and a *visible*
  refusal is the best demonstration of maker-checker/SoD the platform can give.
- **OQ-4 = A** — ship a demo operations extension so the UI opens on real seeded data (later expanded
  with the permission grants + limit approval the verifier found missing).
- **OQ-5 = A** — **Assign dropped from scope.** There is no user-directory endpoint anywhere (222
  OpenAPI paths, zero), and under OIDC the FE cannot learn its own `app_user.id`, so the UI could only
  offer a free-text UUID box with two different 422s behind it.
- **OQ-6 = A** *(the Tier-3 IA sign-off)* — **Operations becomes the FIRST nav group**, above the
  governance walk; the walk becomes the explainer. The header book-chip is scoped to the walk, since
  "scoped to this book" is false over a tenant-wide breach queue.

### CI-parity hardening decisions

- Fix the drift **at the mechanism**, not just the instances: add the six missing CI steps AND a
  conformance pin so the class fails a test instead of recurring.
- Pin detection anchors on `pytest.mark.skipif` + the env var (not the bare word, which self-matches;
  not an `os.environ` regex, which would have silently dropped three real suites).
- `_EXEMPT` map deliberately EMPTY with a written-rationale requirement — an exemption is a governance
  decision, not a convenience.
- `make dep-audit` deliberately NOT folded into `make check`: it queries a live advisory service, so
  CI owns the blocking verdict (with its retry) while the local target makes the same answer reachable.
- Bundled the OPS-1 closeout into the same branch — both gate the Wave-12 close review.

### Direction check (user asked whether we've drifted)

- **Plan drift: none.** All 23 model codes, the ratified slice sequence, and every doctrine invariant
  verified intact by a five-reader audit.
- **Harness drift: real and structural** — see Key Learnings. Fixed rather than deferred.
- **Metrics breadth (user directed these INTO scope):** slotting proposal = rolling vol/returns and
  drawdown are computable from the existing governed return series TODAY; Sharpe needs one captured
  risk-free series first; sector/industry/geography-of-risk + concentration need reference-data
  dimensions that arrive WITH real data, so they fold into the Wave-13 real-data onboarding candidate
  rather than being built twice. To be ratified at the close review.

---

## Key Learnings

### 1. Never recommend a dependency DOWNGRADE as a security fix without re-running the audit gate ON the downgraded tree

OQ-1=C was ratified on the claim that `react-router-dom` 7.11.x sits below the advisory's affected
range. True — but pinning down **re-exposed SIX advisories** later 7.x had already fixed, verified
against the GitHub advisory API:

| advisory | severity | vulnerable | patched |
|---|---|---|---|
| `GHSA-chx6-hx7r-mcp5` unauth **DoS** | HIGH | `>=7.0.0,<7.18.0` | 7.18.0 |
| `GHSA-wrjc-x8rr-h8h6` **open redirect** via backslash in `<Link>`/`useNavigate` | medium | `>=6.0.0,<7.18.0` | 7.18.0 |
| `GHSA-jjmj-jmhj-qwj2` open redirect → XSS | medium | `>=7.9.6,<=7.12.0` | 7.13.0 |
| + 3 more moderate | | | |

The advisory being escaped (`GHSA-qwww-vcr4-c8h2`, RSC-mode CSRF) is genuinely **unreachable** here
(client-only SPA, no RSC, no server actions) — which is why it was allowlist-justified. Two of the
re-exposed ones are open redirects in `<Link>`/`useNavigate`, used on **15 sites** — i.e. reachable.
**A version below one advisory's floor is not below every other advisory's floor.**

### 2. A demo that cannot REACH a control does not demonstrate it

The OPS-1 demo split `limit.manage`/`limit.approve` across two roles. That contradicts the ratified
MG-3 doctrine (`bootstrap.py`): they share `risk_manager_2l` *"because the gate is PERSON-level, not
role-level … the runtime approver != created_by/updated_by refusal is the WHOLE gate."* Consequence:
the maker didn't hold `limit.approve`, so self-approval hit the **403 permission guard** and the
maker-checker **409 could never fire** — a control that *looks* enforced while being untested, with
two docstrings asserting the opposite. Fix: maker+checker share one 2L role, and a **dual-hat
supervisor** files the 1L response so their own review is a real 409. Test now asserts entitlement is
NOT what stops either actor.

### 3. Rehearsing CI's step ORDER is not rehearsing CI's ENVIRONMENT

A local full-PG rehearsal reproduced CI's ordering faithfully and passed — then CI failed with
`ModuleNotFoundError: No module named 'irp_worker'`. Cause: the migration job installed only
`packages/shared-python`, while two suites import `irp_worker`/`irp_backend` **inside test functions**.
A developer venv has all three packages, so **no local rehearsal of step order can ever surface a gap
in the install surface**. Verified the honest way: a throwaway venv built from CI's exact install list,
where the failure reproduced with the old list and vanished with the new one.

### 4. Grep the module name anywhere, not `^from module`

The pre-flight check used `^from irp_worker` (top-of-file only) and reported "shared-python only" —
wrong, because the imports were function-local. Wrong tool for the question.

### 5. A gate that depends on remembering is not a gate

CI's PG tier is a hand-enumerated per-file allowlist (~65 steps); the local merge gate is a wildcard
battery. A new `*_pg.py` suite therefore joins the local gate automatically and CI only if someone
remembers. For **four consecutive slices nobody did**, and the orphaned suites were
`test_scheduler_pg`, `test_limit_pg`, `test_breach_lifecycle_pg`, `test_notification_pg` — the entire
RLS/append-only/ops-no-grant enforcement layer of the Wave-11/12 governance surface — plus PPF-2/PPF-3
demo stages. Nothing was broken (all pass; the local battery is a merge precondition), but enforcement
rested on discipline.

### 6. Adding correct coverage surfaces latent bugs

Both CI failures in the hardening slice came from *adding coverage that had never run*: the orphaned
suites carried a latent `role_permission` leak (breaks `alembic downgrade base` via the FK to the
migration-seeded permission catalog) and a latent install-surface dependency. That is the accumulated
cost of drift going unnoticed.

### 7. A guard must not be the first thing that breaks

`pg_role_permission_guard` initially raised a confusing "relation role_permission does not exist" on
an unmigrated DB, masking the suite's own clearer failure. Now degrades to a no-op.

### 8. Conformance pins need negative controls and non-vacuity guards

Every pin written this session was verified by *breaking* the thing it guards and confirming it names
exactly the right item. The first pin flagged **itself** twice (it necessarily names the env var, then
the literal `"skipif"`), fixed by anchoring on `pytest.mark.skipif`. An `os.environ`-anchored regex
would have been a **fail-open in the guard itself**, silently dropping three real suites that import
`URL` from a sibling and name the var only in their skip reason.

### 9. Other technical findings

- Four refusals share HTTP **409** and stale-`expected_seq` was **wire-identical** to an illegal
  transition (same status, same detail) — the showcase screen would have confidently lied.
- `expected_seq` defaults to `None` = unconditioned (the fail-open API-2b added it to close), and
  `BreachOut` didn't serialize `seq`, so the token was unreachable → `seq` added (free from the
  existing `max_seq` subquery).
- nginx `try_files … /index.html` answers an unrouted API path with **200 + HTML**, which the client
  reports as "the API is unreachable" while the backend is healthy — worse than a 404.
- The limit **approver lives in the audit event** (`after_value.approved_by` + `checked_makers`), not
  on the row, because maker columns are mutable EV state — so prove the two-person control from the
  immutable ledger.
- FastAPI returns `detail` as a string for `HTTPException` but a `ValidationError[]` for 422 —
  rendering it directly prints `[object Object]`.
- The demo book is **`DEMO-GLOBAL`** (not `PC-BRIDGEWATER*`).
- `@types/node` is not installed; fs-reading contract tests live at the package root, outside the
  typechecked `src` tree.

---

## Files Modified

### OPS-1 (PR #127, merged `8b889ed`)

**Backend**
- `packages/shared-python/src/irp_shared/limit/lifecycle.py`: added `BreachStaleSeqError`
  (a `BreachTransitionError` subclass) raised by `_check_expected_seq`; surfaced `BreachQueueItem.seq`
  in both the batched query (free from the existing `max_seq` subquery) and the per-breach path.
- `apps/backend/src/irp_backend/api/breaches.py`: serialize `BreachOut.seq`; own `_ERROR_MAP` key for
  the stale-seq error with an actionable detail; `_WRITE_REFUSALS`/`_READ_REFUSALS`/`_COLLECTION_REFUSALS`
  declared on every verb so refusals reach the generated types.
- `apps/backend/src/irp_backend/api/limits.py`: same refusal declarations (incl. the PATCH verb).
- `apps/backend/tests/test_breaches_endpoint.py`: stale-seq vs illegal-transition distinguishability;
  `seq` token round-trip; the `_ERROR_MAP` detail-string contract pin.

**Frontend**
- `apps/frontend/src/api/client.ts`: refactored to a shared `request()` core carrying `status` +
  flattened `detail` (handles both FastAPI detail shapes); added `conflict`/`unavailable` kinds; the
  read-only fence became a documented read/write SEPARATION.
- `apps/frontend/src/api/writes.ts` **(new)**: the single write surface —
  `respondToBreach`/`reviewBreach`/`closeBreach`/`approveLimit` + `classifyRefusal`.
- `apps/frontend/src/api/useApiGet.ts`: added `reloadKey` so a write can invalidate reads.
- `apps/frontend/src/views/ops/{BreachQueue,BreachDetail,LimitHealth,Refusal}.tsx` **(new)**.
- `apps/frontend/src/components/AppShell.tsx`: Operations-first nav; book chip scoped to the walk.
- `apps/frontend/src/App.tsx`: `/ops/*` routes.
- `apps/frontend/api-prefixes.ts` **(new)** + `api-prefixes.test.ts` **(new)**: single source for the
  dev-proxy and nginx prefix lists, with the nginx alternation pinned by test.
- `apps/frontend/openapi-contract.test.ts` **(new)**, `src/api/refusal-contract.test.ts` **(new)**,
  `src/api/writes.test.ts` **(new)**, `src/views/ops/ops.test.tsx` **(new)**.
- `apps/frontend/eslint.config.js`: `no-restricted-imports` so only `writes.ts` may import `request`.
- `apps/frontend/src/styles.css`, `vite.config.ts`, `infra/docker/frontend-nginx.conf`.

**Demo**
- `packages/shared-python/src/irp_shared/demo/ops_stage14.py` **(new)** + `demo/__init__.py`.
- `packages/shared-python/tests/test_demo_stage9zzzzz_ops_pg.py` **(new)** — filename sorts last per
  the stage-ordering discipline.
- `.github/workflows/ci.yml`: stage-14 step.

### CI-parity hardening (branch `ci-parity-hardening-work`, `b7982c4` → `a3b2e91`)

- `.github/workflows/ci.yml`: six missing PG steps added (4 enforcement suites + PPF-2/PPF-3 demo
  stages); migration job now installs `-e apps/backend -e apps/worker`.
- `packages/shared-python/tests/test_ci_pg_coverage.py` **(new)**: two conformance pins —
  every PG-gated suite is referenced in `ci.yml`, and every job installs the packages its suites
  import (function-local imports included), plus non-vacuity guards.
- `packages/shared-python/tests/conftest.py`: `pg_role_permission_guard` fixture
  (snapshot-then-delete-new; tolerant of an unmigrated DB).
- `packages/shared-python/tests/test_{breach_lifecycle,notification}_pg.py`: request the guard.
- `Makefile`: `dep-audit` + `fe-audit` targets; `fe-check` gained `format:check` and the runtime audit;
  `fe-setup` → `npm ci`; `gen-api` → `$(PY)`; added `VENV_BIN`.
- `docs/developer_setup.md`: downgrade smoke recipe; bare `pytest`; Node 24; the install-surface caution
  with the throwaway-venv command.
- `08_testing_qa/ci_enforcement_overview.md`: "four jobs" → six.
- `10_delivery_backlog/ops_1_decision_record.md`: stamped CLOSED (header still read DRAFT).
- `10_delivery_backlog/delivery_roadmap.md`, `docs/project_memory/current_state.md`: Wave-12 complete.

### Memory

- `ops-1-planning-state.md` **(new)**, `wave-12-close-agenda.md` **(new)**, `MEMORY.md` compacted
  20.2KB → 8.8KB (restructured into Standing rules / Current position / per-wave sections).

---

## Pending Tasks

1. **Merge `ci-parity-hardening-work`** — CI green all 6 on `a3b2e91`. Contains the OPS-1 closeout, so
   the close review would otherwise audit a stale baseline.
2. **Wave-12 close review** — deliberately NOT started (user is switching models). Advised: ultracode
   with Fable 5 Max for the audit fan-out (~10–12 agents: 4 slice auditors + cross-slice integration +
   carry-register verifier + adversarial verify), optionally dropping to Opus for closeout mechanics.
   Agenda saved in `wave-12-close-agenda.md`:
   - the harness-parity audit results (HIGH finding now fixed — ratify the pins as the standing answer;
     note the remaining CI Python 3.12 vs local 3.13 asymmetry);
   - **analytics-breadth ratification** (user-directed): rolling vol/returns + drawdown computable
     today; Sharpe needs a risk-free capture slice; sector/industry/geo + concentration fold into
     Wave-13 real-data onboarding;
   - **recommendation-before-verification** process rule: any cheaply-testable gate option must carry
     its test result IN the decision record before the gate;
   - **React-19 / react-router-8 migration** as its own slice before the **2026-10-24** allowlist expiry;
   - OPS-1 LOWs not folded: demo `_NOW` freshness (seeded breach reads permanently overdue and will
     auto-escalate on the first real tick against the demo tenant), notifications pager, `client.ts`
     success-body parse outside the try.
3. **Wave-13 = real-data onboarding** (recorded tee).

---

## Quick Resume Context

Wave 12 ("Operations, Reachable") is functionally complete: API-2/API-2b → NOTIF-1 → CAD-1 → OPS-1, all
four merged with governed counts frozen at 23/38/109 by design. `main` is at `8b889ed` (PR #127, OPS-1);
one branch awaits merge — `ci-parity-hardening-work` (`a3b2e91`, CI green all 6) — which carries both
the OPS-1 closeout and the fix for a systemic CI harness drift plus two conformance pins.

The immediate next step is to merge that branch, then run the **Wave-12 close review** (the mandatory
Part-4 rule-2 re-baseline), which was deliberately paused for a model switch. Its full agenda lives in
the `wave-12-close-agenda.md` memory file and includes a user-directed ratification of analytics
breadth (rolling volatility/returns, drawdown, Sharpe, sector/geography exposure) and their slotting
relative to Wave-13 real-data onboarding.

---

## Raw Session Log

> Full turn-by-turn transcript for this session is preserved in the Claude Code session file:
> `/Users/andrewcox/.claude/projects/-Users-andrewcox-Projects-investment-risk-platform/19fbf1ce-c768-4810-a4da-2751c2f1a3fc.jsonl`
>
> The sections above capture the decisions, learnings, file changes and pending work in the detail
> needed to resume. Below is a condensed narrative of the exchange order.

1. **User:** "Approved. plan Wave-12 slice 3 (cadence wiring)" → recon, decision record, pre-ratification
   verifier (2 folds incl. a blocking `test_worker.py` collection break), OQ gate (3 OQs, all as
   recommended), implementation, 4-finder review (ZERO HIGH), pushed → merged as PR #125.
2. **User:** "Perform the CAD-1 closeout" → DR stamped CLOSED, roadmap/current_state swept, CTRL-031
   annotated INVOCABLE→OPERATING, memory updated, pushed → merged as PR #126.
3. **User:** "plan Wave-12 slice 4" → recon found four things overturning the roadmap's one-line framing
   (no react-router-dom v8; the FE client's read-only fence; no FE permission knowledge; zero demo
   limits/breaches). Pre-ratification verifier found **six blocking holes**. Six-OQ gate ratified.
4. **User:** "Approved. It's on high effort." → full OPS-1 implementation. OQ-1=C attempted and
   **refuted on evidence**, reversed to A and recorded. 4-finder review returned **4 HIGH + 5 MED**,
   all folded. Pushed.
5. **User:** "CI / DB migration (Postgres) is failing" → diagnosed to `alembic downgrade base`; the
   demo stage's `role_permission` rows violated the FK to the migration-seeded permission catalog.
   Teardown added, reproduced-then-verified locally. CI green → merged as PR #127.
6. **User:** "Are these errors symptomatic of drift? … should we be adding metrics like exposure by
   sector/geography, rolling vol, Sharpe, IR?" → ran a five-reader audit (governed-number inventory,
   requirements scan, data-model readiness, roadmap slotting, harness parity). Verdict: no plan drift;
   **one structural harness drift (HIGH)**; metrics gap map produced with slotting proposal.
7. **User:** "Please run the CI-parity hardening slice. Pause before the Wave-12 close review." →
   six CI steps added, two conformance pins written (each negative-controlled), the `role_permission`
   leak closed, MED/LOW parity gaps fixed, OPS-1 closeout bundled. Pushed.
8. **User:** "CI / DB migration (Postgres) is failing" → `ModuleNotFoundError: irp_worker`; the migration
   job installed only shared-python while two suites import the app packages function-locally. Fixed,
   verified in a throwaway venv mirroring CI's install list, and pinned. CI green all 6.
9. **User:** "Should I use ultracode with Fable for this upcoming step?" → advised yes for the close
   review's audit fan-out, with two qualifications (merge first; consider splitting cost between the
   audit phase and closeout mechanics).
10. **User:** `/compress`.
