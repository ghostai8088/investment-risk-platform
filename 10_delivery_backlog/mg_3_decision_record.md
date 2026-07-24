# MG-3 Decision Record — the `LIMIT.APPROVE` maker-checker gate (Wave-11 slice 4, "operationalize", the FINAL slice)

| | |
|---|---|
| **Status** | **✅ RATIFIED 2026-07-24 — implementing.** Gate outcome: **OQ-MG-3-5=A** (gate limit CHANGES too, not just creation — full REQ-LIM-001: a material governing-field edit to an ACTIVE limit returns it to DRAFT for re-approval); **OQ-MG-3-2=A** (person-level SoD, `limit.approve` on the same `risk_manager_2l`); **OQ-MG-3-3=A** (standalone SoD check). Migration NONE (code-only, verifier B-1). Pre-ratification verifier folded 3 blocking mechanical holes (B-1 no-migration / B-2 stale-read-under-lock / B-3 create-side bypass) + the B#1 change-scope gap now ratified into scope as OQ-5=A. Recon complete (LIM-1 limit surface + MG-2 SoD primitive). |
| **Premise** | LIM-1 (`REQ-LIM-001`/`BX-SOD` "limit **changes** are maker-checked") deferred the formal DRAFT→ACTIVE approval gate (OQ-LIM-1-4=A) because the greenfield person-level SoD primitive did not yet exist. MG-2 built that primitive (SOD-02, same-actor refusal). MG-3 is the fast-follow OQ-MG-2-1=B split out: realize the genesis-reserved `LIMIT.APPROVE` (EVT-060) as a maker-checker gate — a newly-defined limit is created **DRAFT** (not evaluated), and only a 2L approver who is **not the drafter** can transition it DRAFT→ACTIVE. **How much of REQ-LIM-001 this closes depends on OQ-MG-3-5** (creation-approval only, or change-approval too). It is the last Wave-11 slice; after it, the mandatory Wave-11 close review. |
| **Migration?** | **NONE — code-only.** No schema change (the drafter reuses the existing `created_by` column) AND no seed migration: `0002_entitlement_seed` imports the **live** `bootstrap.py` `PERMISSIONS`/`ROLE_TEMPLATES` and bulk-inserts them, so adding `limit.approve` to the catalog is picked up on a fresh `alembic upgrade` automatically. A re-seed migration would collide with 0002 on the deterministic `permission_id` uuid5 PK and BREAK `upgrade head` (verifier B-1). MG-2's `breach.respond`/`breach.review` set the code-only precedent. Migration head stays `0051_breach_action`. |
| **Governed number?** | **NO.** Counts stay **23/38/109**. `LIMIT.APPROVE` is a control-plane state transition — it opens no `calculation_run`, pins no snapshot, binds no model. It is a **permission mint** (`limit.approve`, R-07) + an **audit-code realization** (`LIMIT.APPROVE`, genesis-reserved → activated caller-side against the FROZEN `record_event`). No taxonomy mint. |

---

## 1. What MG-3 IS (and is NOT)

- **IS** the platform's second person-level SoD (approver ≠ drafter, compared by principal id) — reusing MG-2's SOD-02 doctrine, applied to a single stored drafter (not a set of prior responders).
- **IS a behavior change to a shipped control surface:** `create_limit` no longer returns an immediately-ACTIVE limit. A new limit is DRAFT and is **not polled by `select_active_limits`** until approved. This is exactly why OQ-MG-2-1=B split it out for its own adversarial review.
- **IS a realization, not a taxonomy mint.** `LIMIT.APPROVE` is genesis-reserved at EVT-060 (`events.py:11`, `bootstrap.py:166`); MG-3 activates it caller-side. Permissions are minted (`limit.approve`) — a permission mint is not a taxonomy mint.
- **IS NOT** a new entity or (per OQ-MG-3-1=A) a new column: the drafter-of-record reuses the **existing `created_by` column** already present on `limit_definition` from `TimestampMixin` (`mixins.py:39`, materialized in migration `0050_limit_breach.py:66`). **No migration** (revises the stale OQ-MG-2-5 ALTER budget, which was written before this column was confirmed to exist).

---

## 2. Recon findings (the surface MG-3 builds on)

**Limit surface (LIM-1):**
- `LimitDefinition` is **EV** (edited in place via `record_version`; RLS only, no append-only trigger) — `models.py:56`. It already carries nullable `created_by`/`updated_by` String(255) via `TimestampMixin`, currently **unpopulated** by `create_limit`.
- `LIMIT_STATUSES = {ACTIVE, SUSPENDED}` — `events.py:53-56`. Validated service-layer only (no DB CHECK). DRAFT must be added.
- `create_limit(..., status=LIMIT_STATUS_ACTIVE)` — `service.py:263-339`; defaults ACTIVE, emits `LIMIT.DEFINE` via `_record_limit_event`. Guards: `assert_portfolio_in_tenant`, tenant-filtered benchmark check, dup-code, `_validate_config`.
- `select_active_limits` filters strictly `status == ACTIVE` — `service.py:176-185`; called from the tick's `poll_tenant_breaches` (`breaches.py:53`). A DRAFT limit is automatically excluded — no eval-path edit needed beyond the create default.
- `suspend_limit`/`resume_limit` are thin wrappers over `update_limit` (emits `LIMIT.CHANGE`) — `service.py:342-384`. `update_limit` currently permits **any** `status` in `LIMIT_STATUSES` → the bypass in §4.
- `LIMIT.APPROVE` string appears **nowhere** in `packages/`/`apps/` source (docs only) — confirmed reserved-not-realized.

**SoD primitive (MG-2):**
- `_prior_1l_responders` returns the SET of all 1L responder ids on a breach; the same-actor check is inlined at each 2L transition under a `FOR UPDATE` lock (`lifecycle.py:159-169, 342-351, 388-392`). It is a set-over-append-log — **not directly reusable** for MG-3's scalar `created_by` comparison → MG-3 uses a standalone check (OQ-MG-3-3=A).
- `_require_human(actor)` (BR-15) is called first line of every human transition (`lifecycle.py:254-256`) — the pattern MG-3 mirrors so an AI actor can never approve.
- Permission mint pattern: add `(code, desc)` to `PERMISSIONS` + bind in `ROLE_TEMPLATES` (`bootstrap.py`), re-seeded by a migration. `breach.respond`/`breach.review` are MG-2's precedent (`bootstrap.py:178-179, 319, 368`).

---

## 3. The design (under OQ-MG-3-1=A / -2=A / -3=A / -4)

**Vocabulary (`events.py`):**
- Add `LIMIT_STATUS_DRAFT = "DRAFT"` to `LIMIT_STATUSES`.
- Add `LIMIT_APPROVE_EVENT = "LIMIT.APPROVE"`.

**Create FORCES DRAFT (`service.py` `create_limit`) — verifier B-3:**
- Drop the public `status=` parameter from the governed `create_limit`; it **always** creates DRAFT and populates `limit.created_by = actor.actor_id` (the drafter-of-record). A public `create_limit(status="ACTIVE")` would otherwise mint an ACTIVE limit with no approver, no SoD — the symmetric twin of the §4 update bypass. The test/seed ACTIVE shortcut moves to an unmistakable test-only seam (a `_seed_active_limit` helper that creates-then-approves with two distinct principals, or a direct-ORM insert), never the governed path. A conformance test asserts the public create path always yields DRAFT.

**The approve transition — a DEDICATED function, NOT via `update_limit`:**
```python
approve_limit(session, limit, *, actor: LimitActor, approval_ref: str) -> LimitDefinition
  1. _require_human(actor)                          # BR-15: AI never approves
  2. approval_ref must be non-empty                 # sign-off evidence discipline (MG-2 evidence_ref precedent)
  3. locked = _lock_limit(session, limit.id, limit.tenant_id)   # SELECT ... FOR UPDATE, tenant-filtered,
                                                    #   populate_existing=True  (verifier B-2: EV status lives
                                                    #   ON the row; a stale identity-map read defeats the lock)
  4. maker = locked.updated_by or locked.created_by # the maker of the PENDING draft (updated_by set on a
                                                    #   change-triggered re-draft; created_by on first draft)
  5. if locked.status != DRAFT: raise LimitError    # sole legal from-state (re-approve of ACTIVE refused)
  6. if not maker: raise LimitSodError              # non-vacuous SoD (MG-2 precedent): a DRAFT with no maker
  7. if actor.actor_id == maker: raise LimitSodError# SOD-02: approver ≠ the maker of this draft
  8. locked.status = ACTIVE; record_version += 1; flush
  9. _record_limit_event(event_type=LIMIT.APPROVE, action=ACTION_UPDATE,
        before={status: DRAFT}, after={status: ACTIVE}, approval_ref=approval_ref, approved_by=actor.actor_id)
```
`record_event` natively carries `approval_ref: str | None` (`audit/service.py:115`, String(255)); `_record_limit_event` is extended to forward it. (Step 4's `maker` is `created_by` under OQ-MG-3-5=B; it becomes `updated_by or created_by` only if OQ-MG-3-5=A ships change-re-approval.)

**Permission mint — code-only (`bootstrap.py`), NO migration (verifier B-1):**
- Add `("limit.approve", "Approve a DRAFT limit into ACTIVE (2L maker-checker)")` to `PERMISSIONS`.
- Bind to `risk_manager_2l` (the same 2L role as the `limit.manage` maker — the **person-level** SoD is the gate; OQ-MG-3-2=A, spec-blessed by `personas_and_user_journeys.md:51` "P-CRO / second 2L"). Flows to `platform_admin` via `ALL_CODES`.
- `0002_entitlement_seed` imports the live catalog → fresh `upgrade` seeds it automatically. **No migration file.**

---

## 4. HARDENING — the `update_limit` bypass (recon-surfaced, load-bearing)

Once `DRAFT` is a valid status, the generic `update_limit` path — which today accepts any `status ∈ LIMIT_STATUSES` — would let a caller do `update_limit(draft_limit, status=ACTIVE)` and **activate a DRAFT limit with no approver, no SoD, and a `LIMIT.CHANGE` (not `LIMIT.APPROVE`) audit trail**. That silently defeats the entire maker-checker gate. Fix:

- `update_limit` **rejects any `status` change where the old OR new value is `DRAFT`.** DRAFT is reachable only via `create_limit` (→DRAFT) and leaves only via `approve_limit` (DRAFT→ACTIVE). `suspend_limit`/`resume_limit` operate strictly ACTIVE↔SUSPENDED.
- **The create-side twin (verifier B-3):** `create_limit` cannot mint ACTIVE either — see §3 (force DRAFT). Both entry points to ACTIVE are now the single approve gate.
- Editing a DRAFT limit's non-status fields (threshold, name, …) via `update_limit` stays allowed and keeps it DRAFT (still needs approval; the maker is preserved, so the SoD still binds).
- A conformance test asserts: `update_limit(draft, status=ACTIVE)` raises; `update_limit(active, status=DRAFT)` raises; `create_limit` yields DRAFT; approve is the only DRAFT→ACTIVE path.

---

## 5. Test / seed blast radius (in-scope, budgeted)

`create_limit` flipping to DRAFT makes every call site that expects an evaluable limit silently no-op (false-green "no breach"). All call sites are in tests (no seed/demo/app calls `create_limit`). Each must pass `status=ACTIVE` explicitly **or** route through the new `approve_limit` (the latter for at least one end-to-end case, to exercise the gate):

- `test_limit.py:74` (`_mk` helper — high fanout), `:212`, `:244`, `:246`
- `test_limit_breach.py:72` (`_var_limit` helper — feeds 5+ eval assertions), `:187`
- `test_limit_active_risk.py:45`
- `test_limit_pg.py:99` (`_seed_limit`)
- `test_breach_lifecycle_pg.py:113` (`_seed_breach`)

New tests: create→DRAFT (not evaluated); approver==maker refused (SOD-02); approver is AI refused (BR-15); re-approve of ACTIVE refused; NULL-maker DRAFT refused; the §4 `update_limit` bypass + create-force-DRAFT conformance tests; `LIMIT.APPROVE` emitted with `approval_ref`; the role grant (`limit.approve` on `risk_manager_2l`, pinned with `==`) seed test.
- **REQUIRED end-to-end (verifier B #7), on PG, routed THROUGH `approve_limit` (not a `status=ACTIVE` shortcut), same limit id:** create→DRAFT, assert **not** returned by `select_active_limits`; `approve_limit` by a second principal; assert now returned and the next tick records a breach. This is the minimum that proves the gate actually admits a limit to evaluation.
- **The double-approve lock test (PG)** must pre-load the limit in the second session **before** the first approver commits — else it false-greens by reading the fresh ACTIVE state (verifier B-2).
- **If OQ-MG-3-5=A:** loosening an ACTIVE limit's threshold via `update_limit` → DRAFT + not evaluated until re-approved; editor cannot self-re-approve (SoD vs `updated_by`).

---

## 6. Open questions for the ratification gate (Tier-3)

**OQ-MG-3-5 — SCOPE: does the gate cover limit CHANGES, or only creation? (THE decision — verifier B #1).** The requirement is worded as changes: `requirements_backbone.md:211` REQ-LIM-001 "Limit **changes** are maker-checked & audited (BX-SOD)"; `personas_and_user_journeys.md:51` anchor row is titled "Limit change." The base plan gates only create→DRAFT→approve; a solo `risk_manager_2l` can still **loosen an ACTIVE limit's threshold** via `update_limit` (emits `LIMIT.CHANGE`, no checker) — the single most risk-relevant operation, ungated.
- **A [rec] — change-approval too (literal-complete):** a **material governing-field** edit to an ACTIVE limit (threshold, `limit_kind`, `breach_direction`) via `update_limit` returns it to **DRAFT** and stamps `updated_by = editor`; it is not evaluated until a non-editor re-approves (`approve_limit`, SoD vs `updated_by or created_by`). Non-governing edits (name) stay in-place ACTIVE. **Fully meets REQ-LIM-001.** Cost: the `updated_by`-maker generalization (already in §3 step 4) + a brief honest eval-gap while a changed limit awaits re-approval + ~3 tests.
- **B — creation-approval only, defer change-approval to v2 (explicitly ratified):** ship the create gate; record a register carry + soften the premise's "closes REQ-LIM-001" to "closes the creation-approval half." *Honest tension: B leaves the requirement's headline verb (changes) unmet and hands a known gap to the Wave-11 close review; A is more scope but is the literal requirement and this is the last slice. Recommend A.*

**OQ-MG-3-2 — the approver role model. → RECOMMENDED-SETTLED (A), unless the gate overrides.** **A [rec]:** mint `limit.approve` on the **same** `risk_manager_2l` role that holds the maker verb; the **person-level** approver≠maker refusal is the gate. **B:** a distinct checker role (e.g. `risk_committee`). *Verifier confirmed A is spec-faithful: `personas_and_user_journeys.md:51` names the limit-change checker "P-CRO / second 2L" — a second 2L PERSON is explicitly acceptable; no 3L/committee required. B is heavier org-modeling for no letter gain. Recommend A.*

**OQ-MG-3-3 — the SoD check form (engineering, recommended-settled).** **A [rec]:** a standalone same-actor inequality inside the locked `approve_limit`; **do not touch** MG-2's reviewed `_prior_1l_responders` (set-over-append-log vs scalar). **B:** refactor MG-2 into a shared helper. Recommend A.

**Settled by the pre-ratification verifier (no longer forks — folded above):**
- **Migration:** NONE — code-only (verifier B-1; the header row). The old OQ-MG-3-1 (reuse `created_by` vs a new ALTER column) is settled A: `created_by` already exists and IS the drafter; a new column would need a migration and buys only a queryable `approved_by` (a v2 read-surface nicety; the approver lives in the `LIMIT.APPROVE` audit event).
- **Lock read (B-2):** `approve_limit` re-reads the from-state under the lock (`populate_existing=True`) — an EV row's status is on the row, so a stale identity-map read would defeat the lock and double-approve.
- **Create-side force-DRAFT (B-3):** the governed `create_limit` cannot mint ACTIVE.
- **The `update_limit` DRAFT bypass (§4):** `approve_limit` is the sole DRAFT→ACTIVE path.

---

## 7. Wave-11 carries NOT folded here (→ close-review handoff)

Verified NOT MG-3's surface, left for the mandatory Wave-11 close review (clean inventory so nothing is silently dropped): `create_schedule`'s P3-5 cross-tenant FK gap (SCH-1; note `create_limit` already carries the guard — verified); the `*.manage`/`breach.*`/`limit.approve` API forward-gate (latent until endpoints land); `select_overdue_breaches` N+1 (MG-2). **If OQ-MG-3-5=B**, change-re-approval joins this list as a new REQ-LIM-001 carry.

## 8. Implementation + 4-finder review (folded)

Implemented across two commits (`84bae83` record, `9631c91` impl); no migration (head stays `0051`); counts UNCHANGED 23/38/109. `make check` green (lint/typecheck/docs/secret-scan) + full SQLite + full PG suites green + zero alembic drift + `limit.approve` seeds from the live bootstrap catalog and binds to `risk_manager_2l`/`platform_admin`.

**4-finder adversarial review — 1 HIGH (3 finders independently converged) + 4 MED + LOWs, ALL folded:**
- **HIGH — the change-gate was bypassable two ways** (finders 1/2/4): a solo 2L could loosen a LIVE limit without a second sign-off by (a) `suspend → edit-while-SUSPENDED → resume` (the demote fired only on ACTIVE), or (b) slipping a no-op `status=` key alongside a governing change (the `"status" not in changes` guard suppressed the demote). Fold: **demote on a real governing change to any non-DRAFT limit (ACTIVE or SUSPENDED)**; **refuse combining a status toggle with a governing change** in one edit. Regression tests for both paths.
- **MED — `update_limit` TOCTOU** (finder 1): it trusted the in-memory status, so a concurrent approve could slip an un-demoted change past. Fold: read the fresh status under a scalar `SELECT … FOR UPDATE` (not a whole-object refresh — that would reformat in-flight Decimals / the audit payload).
- **MED — no-op re-save demoted a live limit** (finder 1): demote keyed off field *presence*, not an actual value change. Fold: `_governing_value_changed` compares values (Decimal-aware).
- **MED — SoD excluded only the LAST editor** (finder 2): a cosmetic edit by B let the original author A self-approve. Fold: **approver ∉ the SET `{created_by, updated_by}`** (author AND last editor) — the MG-2 responder-set philosophy applied to a scalar pair.
- **MED — audit durability** (finder 2): `LIMIT.APPROVE` now records `checked_makers` so the two-person control is provable from the immutable row (the maker columns are mutable EV state).
- **LOW — `evaluate_limit` fail-closed backstop**: it now refuses to evaluate a non-ACTIVE limit (defense-in-depth beyond the `select_active_limits` filter). Plus added tests: tick-level DRAFT-skip, cross-tenant approve refusal (PG), suspend/resume-on-DRAFT refusal, the `ACTION_STATUS_CHANGE` pin.
- **MED-3 (finder 2) NOT folded — forward-gate note:** the SoD compares raw `actor_id` strings; canonicalization belongs at the (not-yet-built) API auth boundary (the SSO-1 lesson). Recorded as a carry for when `limit.approve`/`limit.manage` endpoints land.

## 9. Cadence

Recon ✅ → decision record ✅ → pre-ratification verifier (3 blocking folds) ✅ → **user ratification gate** (OQ-5=A, OQ-2=A) ✅ → implement ✅ → `make check` + full-PG green ✅ → 4-finder review (1 HIGH + 4 MED folded) ✅ → **push → CI-to-green → merge → closeout → the mandatory Wave-11 close review** (remaining).
