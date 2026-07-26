# CAD-1 — Cadence wiring (Wave-12 slice 3) — decision record

**Status:** DRAFT — pre-ratification (verifier pass pending; then the OQ gate).
**Slice:** Wave-12 ("Operations, Reachable") slice 3 of 4. Prior: API-2/API-2b (slice 1), NOTIF-1 (slice 2).
**Size:** S/M. **Migration:** NONE. **New governed number:** NONE. **New permission / audit code:** NONE.
**Counts:** UNCHANGED 23/38/109 (this is transport/infra ignition, not a governed computation).

---

## 1. The problem — the engine is built but has never been switched on

Wave 11 built the whole per-tenant operational tick — `run_operational_tick_for_tenant` (schedules →
breaches → deadlines → notification) — and Wave-12 slices 1–2 put an HTTP surface and an alarm leg on
top of it. But **nothing invokes the tick on a cadence.** The shipped worker container still runs the
`worker/main.py` placeholder heartbeat (`{"status": "idle"}`); the real entrypoint
(`scheduler.py::main`, a one-shot per-tenant tick) is wired to no clock. The roadmap calls this slice
"the literal ignition of the whole Wave-11 investment."

Two standing carries are due to be **paid here** (both recorded across API-2b / Wave-11-close):

- **Carry-1 (OQ-a):** the worker `--tenant` argument arms the RLS GUC from a raw external string
  without canonicalization — the **SSO-1 bug's second instance** (a non-canonical UUID → RLS
  false-deny → the tick silently does nothing; a fail-*open*).
- **Carry-2 (OQ-W11C-2):** `create_schedule` stamps `scope_portfolio_id` / `model_version_id` into
  NOT-NULL FK columns **without re-resolving them under the acting tenant** — the P3-5 finding (PG FK
  checks BYPASS RLS, so a foreign id can be durably stamped).

## 2. Scope

### Part A — the ignition
1. **Retire** the `worker/main.py` placeholder heartbeat. The real worker entrypoint is the governed
   per-tenant operational tick.
2. **Add an in-process supervisor loop** (`irp_worker/supervisor.py`): every
   `IRP_TICK_INTERVAL_SECONDS`, iterate a **configured** tenant list (`IRP_TENANT_IDS`, comma
   separated) and run `run_operational_tick_for_tenant` once per tenant, each under **per-tenant
   try/except isolation** — one tenant's tick failure logs and never halts the loop or starves the
   other tenants. A structured summary line per (tenant, tick). This is a **supervisor/infra
   concern**, not a governance change: the governed unit (`run_operational_tick_for_tenant`) is
   UNCHANGED, and each tick still runs inside ONE tenant's non-BYPASSRLS session.
3. **Keep the one-shot** `scheduler.py::main --tenant` intact — an external scheduler (k8s CronJob,
   cloud scheduler, host cron) that invokes the worker once-per-tenant on a cadence remains a
   first-class, doctrinally-cleanest deployment (OQ-SCH-1-1=B). The loop is the additional driver
   that makes `docker compose up` a live ticking engine for the slice-4 demo.
4. **Point the worker Dockerfile CMD** at the supervisor loop; add the worker service's runtime env
   to `docker-compose.yml` (`DATABASE_URL`, `IRP_TENANT_IDS`, `IRP_TICK_INTERVAL_SECONDS`,
   `IRP_CODE_VERSION`).

### Part B — Carry-1: `--tenant` canonicalization (the OQ-a fail-open fix)
5. Canonicalize **every** tenant id (`str(uuid.UUID(x))`, mirroring `apps/backend/.../deps.py:122`)
   at the worker boundary — BOTH the one-shot `--tenant`/`$IRP_TENANT_ID` and EACH entry parsed from
   `IRP_TENANT_IDS` — BEFORE it arms the RLS GUC. A malformed / uncanonicalizable tenant id **fails
   closed** (never arm RLS with a raw string that would silently RLS-hide every row):
   - one-shot `main`: refuse to start, exit 2 with a clear stderr message;
   - supervisor loop: **skip** that tenant with a logged error and continue the others (see OQ-3).

### Part C — Carry-2: `create_schedule` cross-tenant FK guard (the P3-5 fix)
6. In `create_schedule`, BEFORE the insert, re-resolve the two hard FKs under the acting tenant with
   an explicit tenant predicate and refuse a foreign/non-existent reference with a clean
   `ScheduleError`:
   - `scope_portfolio_id` → reuse `irp_shared.portfolio.guards.assert_portfolio_in_tenant`;
   - `model_version_id` → a new mirror guard `assert_model_version_in_tenant` (models-only import,
     explicit `tenant_id == acting_tenant` predicate — the same one-implementation pattern).
   - `environment_id` is a **free `String(100)` label** (matches `calculation_run.environment_id`;
     "NOT a security boundary") — **no guard**, correctly.

### Tests
- Supervisor: per-tenant error isolation (a raising tenant does not stop siblings); the configured
  tenant list is honored; the interval is respected (injected/monkeypatched sleep — no real waits);
  a malformed tenant id is skipped, not fatal.
- Canonicalization: one-shot refuses a non-UUID `--tenant` (exit 2); an uppercase/braces UUID is
  canonicalized so the RLS GUC matches; the loop skips a bad entry and still ticks the good ones.
- `create_schedule` guard (SQLite unit + PG): a foreign `scope_portfolio_id` and a foreign
  `model_version_id` are each refused; an own-tenant pair is admitted; `environment_id` free label
  unaffected. On PG, prove the guard refuses BEFORE the FK-bypass-RLS insert would land.

### Explicitly OUT of scope (recorded)
- No external scheduler manifest (k8s CronJob / cloud scheduler YAML) is authored — the one-shot
  entrypoint already supports that deployment; the manifest is an infra-repo artifact, not app code.
- No leader election / distributed-lock across worker replicas — the `(schedule, tick)` unique
  constraint already makes concurrent double-fire benign (SKIPPED_DUPLICATE); a single supervisor
  replica per deployment is the v1 assumption (recorded; multi-replica coordination is a v2).
- No schedule HTTP API — `create_schedule` stays service-only (the guard lands where the write is).
- No `IRP_TENANT_IDS` hot-reload — the tenant list is read at process start (config change =
  restart, the ordinary 12-factor contract).

## 3. The doctrine point (why a loop over N tenants does NOT reopen OQ-SCH-1-1)

OQ-SCH-1-1=B rejected **an in-app cross-tenant ops READ** (sweeping the DB for the tenant set via the
BYPASSRLS ops role). It did **not** forbid the app iterating a **configured/injected** tenant list.
Under the supervisor loop, infra still SUPPLIES the tenant identities (via `IRP_TENANT_IDS` env), the
app never reads cross-tenant, never uses BYPASSRLS, and every tick still runs in exactly one tenant's
forced-RLS session. The "no BYPASSRLS business path / no tenant registry in-app" doctrine is intact.
OQ-2 below re-affirms this at the moment it first becomes concrete.

## 4. Open questions (the ratification gate)

| OQ | Question | Options | Recommended |
|----|----------|---------|-------------|
| **OQ-1** | The cadence driver | **A** in-process supervisor loop over a configured tenant list, PLUS keep the one-shot for external schedulers · **B** external-scheduler-only (no in-app loop; the tick stays one-shot, cadence lives entirely in undefined infra) | **A** — B leaves nothing runnable from `docker compose up`, so the slice-4 demo would still have a dead engine; A makes the engine actually tick while keeping the one-shot for prod. |
| **OQ-2** | The loop's tenant-list source | **A** config env `IRP_TENANT_IDS` (no DB read, no BYPASSRLS) · **B** a DB sweep of distinct tenants (needs the ops cross-tenant read) | **A** — B would reverse the ratified OQ-SCH-1-1=B doctrine and open a BYPASSRLS business path. |
| **OQ-3** | A malformed tenant id inside the loop | **A** skip that tenant, log an error, continue ticking the rest · **B** abort the whole loop at startup | **A** — one fat-fingered id in a shared config must not take the entire operational engine down for every tenant; the one-shot still fails closed (exit 2). |

## 5. Verifier folds (pre-ratification pass, 2026-07-25)

The verifier confirmed the four load-bearing design claims are **sound**: (1) every tenant id is a
canonical UUID (`SYSTEM_TENANT_ID`, and the demo tenant is `str(uuid.uuid5(...))`) and `tenant_id` is
`PG_UUID(as_uuid=False)` whose `::text` is lowercase-hyphenated — exactly `str(uuid.UUID(x))`, so
canonicalization is correct and rejects nothing legitimate; (2) `create_schedule` receives
`tenant_id` explicitly so both guards are RLS-independent defense-in-depth, and `scope_portfolio_id` /
`model_version_id` are the only hard FKs (`environment_id` is a free label); (3) each tick opens its
OWN session, and `persistent_tenant_context` keys its re-arm listener in a `WeakKeyDictionary` **by
session**, so no tenant context bleeds across ticks in one process (plus `attach_tenant_reset`'s
check-in `RESET`); (4) the tick's `finally: session.close()` guarantees per-tenant error isolation
cannot leak sessions or exhaust the pool.

Two folds into scope:

- **FOLD-1 (BLOCKING — was omitted):** `apps/worker/tests/test_worker.py:5` does
  `from irp_worker.main import run_once`; it is in `testpaths`, so bare retirement of `main.py` fails
  pytest at **collection** → `make check` and full-PG both go red. Part A must **rewrite
  `test_worker.py`** (drop the `run_once` import + `test_run_once`; add supervisor unit tests). The
  full retirement dependent-set is exactly three: this test, the CMD in
  **`infra/docker/worker.Dockerfile:16`**, and the run instructions in **`apps/worker/README.md`**.
- **FOLD-2 (fold):** an **empty** `IRP_TENANT_IDS` must **fail closed at startup** with a clear error
  — NOT silently idle (a silently-dead engine is the exact failure this slice exists to prevent). This
  is distinct from OQ-3 (a *malformed entry within a non-empty list* → skip-and-continue): an empty
  list is a misconfiguration and must be loud. Also seed the three worker vars
  (`IRP_TENANT_IDS`, `IRP_TICK_INTERVAL_SECONDS`, `IRP_CODE_VERSION`) into **`.env.example`**.

## 6. Ratification (2026-07-25)

**RATIFIED** at the user gate — all three as recommended:

- **OQ-1 = A** — in-process supervisor loop over a configured tenant list, PLUS keep the one-shot
  `scheduler.main --tenant` for external schedulers.
- **OQ-2 = A** — the loop's tenant list comes from config env `IRP_TENANT_IDS` (no DB read, no
  BYPASSRLS); OQ-SCH-1-1=B doctrine preserved.
- **OQ-3 = A** — a malformed tenant id inside the loop is skipped (logged) and the rest keep ticking;
  the one-shot still fails closed (exit 2), and an EMPTY list fails closed at startup (FOLD-2).

Status → **RATIFIED**; proceed to implementation (both verifier folds in scope).

## 7. Implementation notes (as built)

- **New:** `apps/worker/src/irp_worker/supervisor.py` (the cadence loop + env entrypoint),
  `apps/worker/src/irp_worker/tenants.py` (canonicalization: `canonical_tenant_id` /
  `parse_tenant_ids`), `packages/shared-python/src/irp_shared/model/guards.py`
  (`assert_model_version_in_tenant`).
- **Changed:** `scheduling/service.py::create_schedule` now calls both FK guards pre-insert;
  `scheduler.py::main` canonicalizes `--tenant` (fail-closed exit 2); worker `Dockerfile` CMD →
  `irp_worker.supervisor`; `docker-compose.yml` + `.env.example` gain the three worker vars;
  `apps/worker/README.md` rewritten. **Deleted:** `irp_worker/main.py` (the heartbeat placeholder).
- **Tests:** `test_worker.py` rewritten (10 supervisor + canonicalization unit tests);
  `test_scheduler.py` `_mk` seeds real referents + 3 guard tests; `test_scheduler_dispatch.py` uses
  a real bare-portfolio to trigger dispatch failure (the fake-FK setup now hits the create guard);
  `test_scheduler_pg.py` + 1 PG cross-tenant guard test under real forced-RLS `irp_app`.
- **A build discovery worth recording:** the create-time FK guard is a genuine behavior change — the
  SQLite unit tests that passed fake random FKs only passed because SQLite does not enforce FKs; the
  guard makes them honest, so every such caller now seeds a real in-tenant referent (the guard is
  exactly the P3-5 lesson: a foreign id must never reach a NOT-NULL FK, PG FK checks bypass RLS).
- NO migration; NO governed number; NO new permission/audit code. Counts UNCHANGED 23/38/109.
- Gates: `make check` GREEN; full-PG GREEN (exit 0, incl. the new PG cross-tenant guard test under
  forced-RLS `irp_app`); no OpenAPI/FE change so gen-api-check/fe-check are untouched.

## 8. 4-finder adversarial review — folds

**Verdict: ZERO HIGH.** The core (canonicalization at both boundaries before RLS is armed;
empty/all-malformed list fails closed twice over; no DB sweep / no BYPASSRLS; the P3-5 guard at the
SOLE FK-stamping entry — `create_schedule` is the only `Schedule(...)` constructor and
`update_schedule` can only touch name/status; FROZEN `audit/service.py` untouched; no migration) was
verified sound against the code. All five findings folded:

- **M1 (folded)** — the `main()` fail-closed/canonicalization wiring was untested (only the pure
  helpers were). Added exit-code tests: `scheduler.main` bad `--tenant`→2, missing tenant→2, missing
  db-url→2; `supervisor.main` missing db-url→2, empty `IRP_TENANT_IDS`→2, all-malformed→2.
- **M2 (folded)** — a permanently-failing tenant was log-only with no durable evidence (the
  per-tenant analogue of the silent-idle engine). Added `_update_failure_streaks`: consecutive
  per-tenant failures escalate to a distinct WARNING at `_FAILURE_STREAK_ALERT=3`; a success resets.
- **L3 (folded)** — the success `log.info` sat INSIDE the isolation `try`, so a formatting error
  could misreport a committed success as a failed tick; `summary[tenant]=result` is now recorded
  first and the logging moved after it.
- **L4 (folded)** — `run_operational_tick_for_tenant` now canonicalizes its `tenant_id` defensively
  (belt-and-suspenders) so a future direct caller cannot arm RLS from a non-canonical string.
- **L5 (folded)** — `docker-compose` `db` gains a `pg_isready` healthcheck and the worker waits on
  `condition: service_healthy` (avoids spurious first-cycle connection errors at startup).

Re-validated post-fold: `make check` GREEN, worker suite 18/18, scheduler PG+dispatch GREEN.

Status → **CLOSED-pending-merge.**
