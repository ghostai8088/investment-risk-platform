# OPS-H1 Decision Record — operations hygiene (Wave-13 slice 3)

| | |
|---|---|
| Status | **VERIFIED 2026-07-28 — the pass returned NOT RATIFIABLE as drafted (1 BLOCKING, 1 MATERIAL, 7 minor), ALL FOLDED: H1-9's planned fix was for a route that does not exist paying a debt NOTIF-1 already paid (redrafted against the real FE truncation); H1-4's fix shape contradicted its own discharge rationale (restated: regeneration removes the absurdity, not the mutation — the prohibition becomes a documented consequence). RATIFIED 2026-07-28 — OQ-OPS-H1-1/2/3 all approved as recommended (scope as verified; the demo-clock prohibition becomes a documented consequence with backdated offsets preserving the walk; the interleave attempted first with the disclosed fallback).** |
| Slice | Wave-13 slice 3, per the ratified sequence (OQ-W12C-2=A); a Part-4 rule-3 insertion (the MD-H1 precedent) |
| Kind | **Hygiene** — no governed number, no entity, no migration, no permission, no audit code. Pays the fired-trigger cluster + the recorded LOW cluster from the Wave-12 close register (§2/§5 of `wave_12_close_review.md`) |
| Counts | **UNCHANGED at 25/40/133** — and this record says so NOW, before implementation, so a drift is a defect in the code rather than in the expectation (the SCH-2 lesson) |
| Demo | No new stage. Stage 14 is EDITED in place (`_NOW` regenerate-on-seed); the 8-z final-position count pin stays the baton holder |
| Sizing | **S/M** as roadmapped — genuinely, this time: every item is a bounded edit at a known site, and the two preceding hygiene-adjacent slices (MD-H1, CI-parity) both ran at their estimate |

## Part 0 — What OPS-H1 is

The slice that pays operational debt the Wave-12 close **measured and slotted** rather than merely
recorded. Three items had their triggers FIRE in-wave (the register's TIPPED class); six more are
recorded LOWs whose fix is cheaper than their re-inventory. Nothing here changes what the platform
computes; everything here changes what it costs to run, how honestly it describes itself, and how
much of the demo tenant's curated history survives contact with a real tick.

## Part 1 — The fired-trigger cluster (the slice's reason to exist)

### H1-1 — `select_overdue_breaches`: retire the N+1 (TIPPED item 1)

**Site:** `limit/lifecycle.py:750-772`. The tick-side escalation pre-filter loads **every breach in
the tenant — including CLOSED ones — then issues 1–2 queries per breach**
(`current_breach_state` + `_governing_assign`). CAD-1 made this a recurring per-interval cost: the
cadence pays it every tick, forever, on a table that only grows (breaches are append-only history).

**Fix shape — the D9 batched template, already shipped 100 lines above.** `list_breaches`
(`lifecycle.py:650-746`) solves the identical greatest-n-per-group problem in ONE portable
PG+SQLite statement (plain GROUP-BY max-seq joins, no `DISTINCT ON`/window; explicit tenant
predicates inside every subquery; `uq_breach_action_seq` guarantees ≤1 row per join). The overdue
pre-filter is that template with three deltas: filter the DERIVED state to
`_ESCALATABLE_STATES` ({ASSIGNED, RESPONDED}), filter `governing.response_due < now` **in SQL**,
keep `ORDER BY Breach.id` (the deterministic cross-tick lock order, VERIFIER-F3-MED1 — this
ordering is load-bearing and must be pinned, not incidentally preserved).

**Contract preserved:** it stays a read-side PRE-FILTER — `escalate_overdue_breach` re-checks every
condition under the lock, so a stale candidate remains harmless and no behavioral guarantee moves.
**Owed tests:** result-equivalence against the old shape on a mixed fixture (open/closed/assigned/
responded/no-deadline/future-deadline breaches); a statement-count assertion (the N+1 is the defect,
so the test must COUNT queries, not infer from timing); the lock-order pin; and the SQLite
datetime-bind caveat the verifier raised — the D9 template has never carried a datetime WHERE on
SQLite, where stored deadlines return NAIVE while a bound aware `now` serializes with an offset
suffix, so the bind convention is pinned explicitly (naive-UTC on SQLite) with a boundary test at
exact-equality.

### H1-2 — the honest tick-stall statement (TIPPED item 1, second half)

**Site:** the scheduler/supervisor docstrings amended at the M-C1 fold (`wave_12_close_review.md`
§1 M-C1). The ratified *"phases 1–2 take NO row locks"* claim was FALSE — a new-breach INSERT takes
FK `FOR KEY SHARE` on the parent `limit_definition` row. The M-C1 fold corrected the scheduler
docstring; OPS-H1 owes the **survey completion**: every remaining doc/docstring that repeats the
no-locks claim (grep the phrase and its paraphrases across `scheduling/` and `worker/` — the verifier confirmed
`scheduler.py:169` already carries the corrected statement and the residue is DOC-side: historical
records quote the falsified claim as history and may stay; anything presenting it as CURRENT truth
is corrected) states the honest version — phases 1–2 take FK `FOR KEY SHARE`; the conflict
window with the limit verbs' `FOR UPDATE`→advisory order is real, bounded, self-healing tick-side
(per-limit SAVEPOINT, retried next tick), and surfaced HTTP-side as 503 + Retry-After.

### H1-3 — the M-C1 PG interleave regression (from §1 M-C1, named OPS-H1 scope at the close)

**The missing executed control for a shipped fold.** `deadlock_503` now guards all five limit write
verbs, but no test EXECUTES the interleave that motivated it. Owed: a PG-tier regression driving the
actual sequence — tick holds the per-limit advisory from an earlier same-transaction emit; an HTTP
verb takes `FOR UPDATE` on the same `limit_definition`; the tick's new-breach INSERT requests
`FOR KEY SHARE` → 40P01 — and asserting BOTH declared outcomes: the tick side retries next tick
(per-limit SAVEPOINT, no supervisor crash), the HTTP side maps to 503 + Retry-After (never a raw
500). Two sessions + a barrier, the `test_audit_concurrency.py` pattern. If the exact 40P01 proves
un-forcible deterministically, the fallback is asserting each HALF against a synthetic
`OperationalError` carrying `40P01` — and the verifier found the HTTP half of that fallback already
ships (`test_breaches_endpoint.py:561-575`, `test_limits_endpoint.py:360-372`), so the new content
is the TICK half plus the true-interleave attempt; recorded honestly as the weaker control if the
attempt fails, not passed off as the interleave.

### H1-4 — demo `_NOW` regenerate-on-seed (TIPPED item 3; retires the OQ-W12C-3d interim rule)

**Site:** `demo/ops_stage14.py:110` — `_NOW = datetime(2026, 7, 25, 9, 0, tzinfo=UTC)`, frozen. The
seeded overdue breach reads permanently overdue, so the first real tick against the demo tenant
auto-escalates + notifies and MUTATES the curated walk — which is why the interim standing rule
(`DEMO_TENANT_ID` never enters `IRP_TENANT_IDS`) exists.

**Fix shape:** `_NOW` becomes seed-time-relative — resolved once at stage entry, every seeded
instant an OFFSET from it, and **the choreography-defining offsets BACKDATED so the curated walk is
preserved exactly**: the assign lands at `seed − 2d`, its HARD-SLA deadline (`+1d`) therefore at
`seed − 1d`, so the seeded breach reads OVERDUE at seed just as it does today. The healthy limit
stays healthy. The already-seeded refusal path is unchanged (re-runs still refuse; existing
deployments keep their frozen history until re-seeded).

**What regeneration does and does NOT buy — stated plainly, because the draft got it wrong.** The
verifier caught the draft claiming regeneration prevents the tick-driven mutation. It does not, and
CANNOT while the walk shows an overdue breach: an overdue breach under a running tick escalates,
because that is what the platform is FOR. What regeneration removes is the ABSURDITY — today a first
tick would escalate + notify on a breach frozen a year stale, instantly, mutating the walk into
nonsense. After H1-4 the demo tenant behaves like a real tenant: enrol it in `IRP_TENANT_IDS` and
the lifecycle RUNS — the overdue breach escalates on the first tick as governed, correct behavior,
and an operator who wants the pristine walk back re-seeds. **The OQ-W12C-3d interim PROHIBITION is
therefore retired and REPLACED by a documented consequence**, not silently deleted: the standing-
rule text in `wave_12_close_review.md` §6d gets a dated amendment stating that enrolling the demo
tenant runs its lifecycle and mutates the walk BY DESIGN, with re-seed as the recovery. The config
flip itself remains an operator choice.

**Determinism boundary:** demo timestamps stop being byte-identical across seed days; the PG suites
must assert RELATIVE facts. Audit scope covers absolute-timestamp **assertions or inputs** (the
stage-14 suite's one absolute input at `test_demo_stage9zzzzz_ops_pg.py:284` is a pre-insert
refusal and is harmless, but it is rewritten relative anyway so the file carries one convention).

## Part 2 — The recorded LOW cluster

- **H1-5 — dev_header GUC canonicalization symmetry** (`backend/deps.py` dev-mode path): the
  `X-Tenant-Id` header arms the RLS GUC un-canonicalized — the OQ-a class's third boundary. Dev-only
  (refused outside `app_env == "local"`), but the SSO-1 standing rule is *any code path arming a
  tenant GUC from an external string canonicalizes first*, and a rule with a carve-out is weaker
  than a rule. Canonicalize + the same-refusal test the OIDC path has.
- **H1-6 — the L4 sibling helpers** (`db/tenant.py:124-146` `tenant_session`/`run_in_tenant`;
  `worker/jobs.py:20` `run_tenant_job`): no external-string caller at HEAD, but they arm the GUC and
  lack the defensive canonicalization the L1–L3 boundaries carry. Same treatment, plus a test
  pinning that a non-canonical id is canonicalized (not refused — these are internal seams).
- **H1-7 — ops-stage teardown narrowing** (`test_demo_stage9zzzzz_ops_pg.py:96-100`): the teardown
  deletes **ALL** demo-tenant `role_permission` rows, not the **16** this stage seeded (4+3+3+4
  wiring rows across the four operator roles, `ops_stage14.py:100-104`, + 2 auditor additions —
  the draft said six; the verifier counted). CI-safe today (fresh schema), but on a shared/local DB it
  strips the living tenant's wiring — exactly what its own comment says teardowns must not do. Narrow
  the DELETE to the stage's own role codes + the two named auditor grants.
- **H1-8 — a role/permission census pin after stage 14 — the FIRST, not a re-pin.** The verifier
  found the draft's referent does not exist: no demo-tenant role/permission census exists anywhere
  (the set-equality locks pin governed MODEL codes; the only role census is template-level). The
  register's claim holds vacuously. Add the first one: a post-stage-14 set-equality assertion in
  the 5-z suite over the demo tenant's role codes AND their wiring counts, so a drift in either
  direction fails.
- **H1-9 — the notifications pager (L-7), REDRAFTED after the verifier REFUTED the draft.** The
  draft planned a backend pager for `/breach-notifications` — **a route that does not exist, for a
  debt already paid**: the real read is `GET /breaches/{id}/notifications`
  (`api/breaches.py:547-565`) and it has carried `limit`/`offset` (default 50, capped 200) plus the
  deterministic ordering pin since NOTIF-1 (PR #123) — BEFORE OPS-1 even recorded L-7. The genuine
  residual is FE-side: `views/ops/BreachDetail.tsx:40` fetches with no paging params and no pager
  UI, so the 51st notification silently vanishes from the operator's view. The fix is the FE pager
  (params + a load-more affordance + a truncation-visible test), not the backend. *Recorded as the
  slice's own instance of the standing lesson: a register entry is a CLAIM about the code, and it
  can be stale the day it is written.*
- **H1-10 — `client.ts` success-parse placement (L-9)**: the success body is parsed OUTSIDE the
  try, so a 200-with-HTML (a proxy error page) still misreports as "unreachable". Move the parse
  inside; pin with a 200-non-JSON fixture test.

## Part 3 — What OPS-H1 is NOT

No new notification channel (BR-10 still forbids the credentials); no `limit_utilization`
(ENT-032 stays reserved); no reviewer≠closer stringency change; no FE `assign` consumer (weighed at
the next ops-UI slice); no React/router work (FE-M1's, deadline 2026-10-24); no supervisor
restart-policy/L3 co-change work (recorded, still LOW); nothing that moves a governed number, a
count, or a permission.

## Part 4 — Open questions for the gate

- **OQ-OPS-H1-1** — scope as drafted (the four fired-trigger items + the six LOWs, nothing else)?
  *Recommend APPROVE.*
- **OQ-OPS-H1-2** — H1-4's discharge semantics AS REVISED: backdated seed-relative offsets preserve
  the curated walk exactly; the interim PROHIBITION is retired and REPLACED by a documented
  consequence (enrolling the demo tenant runs its lifecycle and mutates the walk BY DESIGN; re-seed
  is the recovery); the config flip stays an operator choice? *Recommend APPROVE — the alternative
  (due-in-future offsets) keeps the walk stable under a tick for ~1 day but LOSES the overdue read
  the walk exists to show, and still mutates after the SLA elapses.*
- **OQ-OPS-H1-3** — H1-3's fallback (synthetic-40P01 halves, disclosed as the weaker control) is
  acceptable IF the true interleave proves un-forcible after a bounded attempt? *Recommend
  APPROVE — with the attempt made first and its outcome recorded either way.*

## Part 5 — Verification plan

`make check` + full-PG on a reset schema (the demo suites are the ones this slice touches);
statement-count test for H1-1; the interleave regression (or its disclosed fallback) for H1-3; the
canonicalization matrix for H1-5/6; the narrowed-teardown and census pins for H1-7/8; FE typecheck +
the 200-non-JSON fixture for H1-9/10. Counts pinned UNCHANGED at 25/40/133 in this record — the
final-position pin in the 8-z suite must keep passing untouched, which is itself the drift alarm.
