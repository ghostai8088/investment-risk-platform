# OPS-1 — The operations UI (Wave-12 slice 4) — decision record

**Status:** DRAFT — pre-ratification (verifier pass pending; then the OQ gate).
**Slice:** Wave-12 ("Operations, Reachable") slice 4 of 4 — the LAST. Prior: API-2/API-2b (1), NOTIF-1 (2), CAD-1 (3).
**Size:** M/L. **Migration:** NONE expected. **New governed number:** NONE. **New permission / audit code:** NONE.
**Counts:** UNCHANGED 23/38/109 (a UI computes nothing).
**Sign-off class:** the roadmap flags this as a **Tier-3 FE information-architecture sign-off**.

---

## 1. The goal

Wave 11 built the governance engine, Wave-12 slices 1–3 made it reachable (HTTP), alarmed (notification)
and running (cadence). But **the limits/breach surface has no frontend at all** — today it is Swagger and
curl. OPS-1 is the **first genuinely VISIBLE deliverable**: the breach/limits dashboard — open breaches,
ownership, limit health, the approval queue — i.e. the honest demo of the whole Wave-11/12 investment.

## 2. Recon findings that CHANGE the ratified slice description

The roadmap's one-line framing ("rides the react-router v7→v8 migration") does not survive contact with
the code. Four findings, each with a decision attached:

### F1 — The "react-router v7→v8 migration" is really a **React 18 → 19 upgrade**
`react-router-dom` **has no v8** (latest is `7.18.1`; verified against the registry). The advisory's fix is
the restructured **`react-router@8.3.0`** package — whose `peerDependencies` are **`react >= 19.2.7`** and
`react-dom >= 19.2.7`. The app is on **React `^18.3.1`**. So the "migration" is: 15 `react-router-dom`
import sites → `react-router`, **PLUS** React 18→19, `react-dom`, `@types/react`, `@types/react-dom` and
`@testing-library/react` compatibility across **22 test files**. Good news for the blast radius: every API
this app uses (`BrowserRouter`/`MemoryRouter`/`Routes`/`Route`/`Link`/`NavLink`/`Outlet`/`Navigate`/
`useParams`/`useNavigate`/`useLocation`) **is still exported by v8** — the router half is a specifier swap.
The React half is not. **Runway: the allowlist exception expires 2026-10-24 (~3 months).**

### F2 — The FE API client has a **ratified READ-ONLY FENCE** this slice must deliberately breach
`apps/frontend/src/api/client.ts` hard-codes `method: "GET"` and documents it as *"READ-ONLY — this module
deliberately exposes no way to make a non-GET request (the `method: "GET"` below is the fence)"*. Every FE
slice to date (FE-1/2/3/3b, API-1/1b) has been a pure read surface. An operations UI with
assign/respond/review/close/approve is **the platform's first frontend write path** — a deliberate,
recorded architectural change, not an incidental one.

### F3 — The FE has **no way to know the caller's permissions**
`Session` is identity-only (`dev`: `userId`+`tenantId`; `oidc`: token+`subject`+`expiresAt`). There is **no
`/me` endpoint** and no permission claim surfaced. So the UI cannot know whether to offer *Respond* (1L,
`breach.respond`), *Review* (2L, `breach.review`) or *Approve* (`limit.approve`) without either a new read
or a show-and-let-the-server-refuse policy.

### F4 — The demo tenant has **ZERO limits, breaches, schedules or notifications seeded**
The demo campaign (`irp_shared/demo/`, 15 stage modules) seeds the whole governed-number surface but
**nothing from Wave 11/12** — no `create_limit`, no `Breach`, no `create_schedule` anywhere in it. Pointed
at the demo tenant today, the operations UI would render **empty tables**. A slice whose stated purpose is
"the first VISIBLE demo" therefore needs a demo-seeding leg, or it demonstrates nothing.

## 3. Proposed scope

### Part A — the operations UI (the ratified four surfaces)
1. **Breach queue** (`/ops/breaches`) — the open-breach worklist off `GET /breaches`: severity, limit code,
   observed vs threshold (fixed-point strings, never floats), state, owner, response-due (with an overdue
   marker). Filterable by state; the default view is "needs attention".
2. **Breach detail** (`/ops/breaches/:id`) — the governance narrative for one breach: the identity/arithmetic
   echo, the **action timeline** (`GET /{id}/actions` — the DETECTED→ASSIGNED→RESPONDED→REVIEWED→CLOSED walk),
   the **alert evidence** (`GET /{id}/notifications` — proof-of-alert, the NOTIF-1 leg), and the lifecycle
   **actions** (assign / respond / review / close).
3. **Limit health** (`/ops/limits`) — off `GET /limits/health` + `GET /limits`: per-limit OK/BREACHED/
   NEVER-EVALUATED state, with the fail-open-honest "never evaluated" case shown as its own state, not as OK.
4. **Approval queue** (`/ops/limits?state=DRAFT`) — DRAFT limits awaiting `POST /{id}/approve`, the MG-3
   maker-checker gate made visible (and the SoD refusal legible — see Part C).

### Part B — the write surface (F2)
5. A typed **write path** for the seven action verbs, sharing ONE internal identity/error core with
   `apiGet` (never a second copy of identity injection — the SSO-1 "two places drift" lesson), plus the
   `client.ts` fence comment **re-written to state the new, narrower guarantee** rather than silently
   falsified.

### Part C — governance legibility (the point of the demo)
6. **Refusals are first-class UI, not errors to hide.** A **409** (person-level SoD — "you responded to this
   breach, so you may not review it") and a **403** (you don't hold the permission) must render as distinct,
   plain-language explanations naming the control. This is the demo's most valuable screen: it *shows*
   maker-checker and 1L/2L separation actually biting.

### Part D — demo data (F4)
7. A demo **operations extension** (the established additive `run_demo_*_extension` pattern: refuse-not-skip,
   single-commit, base campaign byte-untouched) seeding limits against the demo book — some deliberately
   breached — then running the operational tick to produce real `breach` + `breach_action` +
   `breach_notification` rows, so the UI opens onto a populated, honest queue.

### Explicitly OUT of scope (recorded)
- **The React 19 / react-router 8 migration** (OQ-1) — see below; its own slice.
- Limit **creation** UI (the create form is a governed 2L-maker write with its own validation surface;
  approval of existing DRAFTs is in scope, authoring new limits is not).
- Any new API endpoint (OPS-1 consumes the 17 endpoints API-2/2b/NOTIF-1 already shipped) — **unless OQ-3=B**.
- Realtime/push updates (the queue is poll-on-navigate; a live socket is a v2).

## 4. Open questions (the ratification gate)

| OQ | Question | Options | Recommended |
|----|----------|---------|-------------|
| **OQ-1** | The React 19 + react-router 8 migration (F1) | **A** SPLIT it into its OWN slice (OPS-1 ships on React 18 / react-router-dom 7; migrate before the 2026-10-24 expiry) · **B** bundle it into OPS-1 as the roadmap's one-liner implied | **A** — F1 shows this is a framework upgrade (React 18→19 across 22 test files), not the specifier swap the roadmap assumed. Bundling a framework migration with the platform's FIRST write path means a failure in either is indistinguishable in review. ~3 months of runway makes splitting free. |
| **OQ-2** | How the UI reaches the write verbs (F2) | **A** a DEDICATED write module (`apiPost`) sharing one internal identity/error core with `apiGet`; the read module keeps its no-write property · **B** add `apiPost` directly into `client.ts`, retiring the fence | **A** — keeps the ratified read-only guarantee true of the read module, puts the entire new write capability in ONE auditable file, and still has exactly one identity-injection implementation. |
| **OQ-3** | Action affordances vs. permissions (F3) | **A** show the actions; map **403** to a plain "you do not hold `breach.review`" and **409** to the SoD explanation — NO new endpoint · **B** add a `/me/permissions` read so the UI can hide what you cannot do | **A** — enforcement is server-side by doctrine, and a *visible refusal* is the single best demonstration of maker-checker/SoD this platform can show. B adds API surface to hide the very thing the demo exists to prove. |
| **OQ-4** | Demo data (F4) | **A** ship a demo operations extension seeding limits + a tick-produced breach/notification set · **B** ship the UI and let the operator create limits via Swagger/curl first | **A** — B means the "first VISIBLE demo" opens on four empty tables; the slice would not achieve its stated purpose. |

## 5. Verifier folds (pre-ratification pass, 2026-07-25)

All four recon findings **CONFIRMED** with evidence. But the verifier found **six BLOCKING holes** the
plan missed — each would have broken the slice on merge or on demo day — plus a third OQ-1 option that
changes that question's arithmetic. All are folded into scope.

- **H1 (BLOCKING) — the dev proxy and deployed nginx do not route `/breaches` or `/limits`.**
  `vite.config.ts:12-26` and `infra/docker/frontend-nginx.conf:13` each hand-mirror the SAME 13 API
  prefixes; neither lists `limits` or `breaches`. The failure is worse than a 404: nginx's
  `try_files … /index.html` returns **200 + HTML**, and `client.ts:56` parses JSON *outside* the
  try/catch, so the `SyntaxError` surfaces as **"the API is unreachable"** while the backend is fine.
  This is precisely the FE-3b deployed-nginx HIGH class, invisible to `make check`. **Fold:** add both
  prefixes to both lists **and add a test asserting the two hand-mirrored lists are equal.**
- **H2 (BLOCKING) — "409 = SoD" is false, and it falsifies the slice's own showcase screen.** FOUR
  refusals share 409, and **stale-`expected_seq` and illegal-transition share the identical detail
  string** (`lifecycle.py:205-207` raises a plain `BreachTransitionError`). So Part C would confidently
  say "you responded to this breach, so you may not review it" when the *tick escalated underneath the
  operator*. Compounding: `client.ts:29-35` has **no 409 case** (falls through to `"server"`) and
  `ApiError` **discards the response body**, so the detail never reaches the UI. **Fold:** the write core
  must carry `status` + parsed `detail`; discriminate SoD on the `"separation of duties"` prefix, never
  on bare 409; add a `BreachStaleSeqError` with its own error-map key + distinct detail (~4 backend lines).
- **H3 (BLOCKING) — `expected_seq` is absent from the plan, and its token is unreachable.** All four
  verbs accept `expected_seq` (`breaches.py:158,171,186,208`), defaulting to `None` = **unconditioned**,
  the fail-open path API-2b OQ-4=A added it to close. But **`BreachOut` does not serialize `seq`** — it
  exists only on `BreachActionOut` — so the UI must fetch the timeline, take `max(seq)`, and re-fetch
  after every write (the verb's own `BreachOut` response also lacks it). **Fold:** add `seq` to
  `BreachOut` (one additive field) so the token is free, and render stale-seq as "this breach changed
  while you were reading it — reload".
- **H4 (BLOCKING) — `useApiGet` cannot refetch.** It keys on `[path, session]` and exposes no
  `refetch` (`useApiGet.ts:18-51`); re-requesting the same path is a no-op. Every FE slice to date was
  read-only, so this never mattered — but after every write the queue, detail, timeline and notification
  list are all stale. **Fold:** add a `reloadKey`/`refetch` and bump it from the write handlers.
- **H5 (BLOCKING) — the demo seed needs permissions AND approval, not just limits.** The demo's
  auditor_3l persona holds 11 `*.view` codes but **NOT `limit.view`/`breach.view`** (`campaign.py:246-259`)
  — a stakeholder walking the demo would get **403 on every ops read**. And MG-3 means `create_limit`
  yields **DRAFT**, while both `limit_health` and breach detection read `select_active_limits`
  (`status == ACTIVE`) — so seeding limits and running the tick **without a second actor approving them**
  produces zero health rows and zero breaches: the four empty tables OQ-4 exists to prevent. **Fold:**
  Part D must also grant the two view codes to `auditor_3l`, wire the maker/checker verbs across **≥2
  distinct app_users** (approver ∉ `{created_by, updated_by}`; reviewer ∉ prior 1L responders), and
  **approve** the seeded limits before the tick.
- **H6 (BLOCKING, a scope decision) — "assign" has no assignee source.** `assigned_to` must be a UUID
  resolving to an active tenant user who holds `breach.respond`, else 422 — but the OpenAPI has **222
  paths and zero user/`/me` paths**. Worse, **under OIDC the FE never learns its own `app_user.id`**
  (`OidcSession` carries only `subject`), so even self-assignment cannot be pre-filled. This is a real
  limit of OQ-3=A that F3 understated. → **new OQ-5.**

**Medium folds (not blocking, but real):**

- **The health join must not default to green.** `limit_health` iterates ACTIVE limits only, so DRAFT and
  SUSPENDED limits produce **no health row**. Joining `/limits/health` onto `/limits` and rendering an
  unmatched limit as OK would make a SUSPENDED limit read as healthy — the exact fail-open-honesty failure
  LIM-1 was built to avoid. Render `status !== ACTIVE` as its own row state.
- **`assigned_to_me` must be the server filter, never a client-side compare** — the D1 stamp≠compare class
  repeated on the FE (and impossible under OIDC anyway).
- **`response_due` is deliberately NULLed in REVIEWED/CLOSED** (`lifecycle.py:573-582`) — the overdue
  marker must never read a null as "no deadline".
- **422 bodies are `ValidationError[]`, not a string** — a decoder rendering `detail` as text prints
  `[object Object]` on the very "refusals are first-class" screen. Handle both shapes in the write core.
- **503 + `Retry-After: 1`** (deadlock victim) is *retryable*; `kindFor` maps it to `"server"` and would
  tell the operator the platform failed.
- **The refusal surface is absent from the OpenAPI contract** (verbs document only 200/422), so 403/409/503
  are **not in the generated types** and `gen-api-check` gives the refusal map zero drift protection —
  FE-2's lesson biting exactly where the plan hand-models. Declare the responses on the routers (doc-only,
  regenerates types) or pin the status→message map with a test.
- **Demo-suite ordering:** CI runs the demo PG suites against ONE shared DB in a load-bearing order with an
  explicit filename leg (`ci.yml:404-408,474-478`); a naturally-named `test_demo_ops_pg.py` sorts at `o` —
  **before** `stage*` and `multifamily` — breaking their set-equal count pins. Name it
  `test_demo_stage9zzz_ops_pg.py` and insert the CI step after stage-11, before the downgrade smoke.
- **AppShell IA (the Tier-3 item the DR left implicit):** the nav hard-codes two groups under the doctrine
  "the walk is the front door"; OPS-1 adds a third, **operationally primary** group. Also the global
  `book-chip` titled *"The walk is scoped to this book"* becomes **false** the moment `/ops` renders, since
  the queue is tenant-wide across portfolios. Both need an explicit call (see OQ-6).

**Verifier corrections to this record:** the endpoint count is **16**, not 17; Part A/C touch **five** write
verbs (assign/respond/review/close/approve), not seven. **The decimal contract needs NO work** — API-2b and
NOTIF-1 already back-filled all five DTOs into the exhaustive guard (`decimal-contract.ts:92-96`), with
`seq`/`epoch_seq`/`expected_seq` already whitelisted as counts; recorded so the slice does not redo it.

## 6. Open questions — REVISED after the verifier pass

OQ-1 gains a third option the verifier found; OQ-5 and OQ-6 are new (H6 and the Tier-3 IA call).

| OQ | Question | Options | Recommended |
|----|----------|---------|-------------|
| **OQ-1** | The React 19 / react-router 8 migration (F1) | **A** SPLIT into its own slice · **B** bundle into OPS-1 · **C** **pin `react-router-dom` down to ≤7.11.x**, which is BELOW the advisory's affected range (`>=7.12.0, <8.3.0`) and keeps `react >= 18` — clearing the advisory today with **zero React work** | **C, then A** — C retires the CI allowlist exception immediately (no 2026-10-24 cliff, no framework upgrade inside the first write-path slice), at the cost of 7 minor releases; the React 19 + RR8 migration then happens on its own merits, on its own slice, unforced. |
| **OQ-5** | The assignee directory (H6) | **A** scope **assign** OUT of OPS-1 — the tick/demo seeds ownership, and the UI demos respond/review/close on already-assigned breaches · **B** add a bounded assignee-candidate read (contradicts the "no new endpoint" scope line) | **A** — it keeps the slice's no-new-endpoint fence intact and loses little: the governance story OPS-1 exists to show is the 1L/2L **response** and the maker-checker **approval**, not the clerical assign step. Assign returns with a directory read in a later slice. |
| **OQ-6** | Where the ops surface sits in the IA (the Tier-3 call) | **A** a THIRD nav group ("Operations") placed **first**, above "The walk" — operations is the primary daily surface, the walk becomes the explainer · **B** keep the walk first and add Operations below it | **A** — the walk was the front door when there was nothing operational to do; with a live breach queue the daily user is an operator. Requires scoping the global `book-chip` to the walk (it is false over a tenant-wide queue). |

**Unchanged from §4 (re-affirmed by the verifier):** **OQ-2=A** (a dedicated write module sharing one
identity/error core), **OQ-3=A** (show actions; render 403/409 as first-class explanations; no `/me`),
**OQ-4=A** (a demo operations extension) — now with the H5 grant/approval legs folded in.

## 7. Ratification (2026-07-25)

**RATIFIED** at the user gate — all six as recommended:

- **OQ-1 = C** — **pin `react-router-dom` to ≤7.11.x NOW** (below the advisory's `>=7.12.0` affected
  range, keeps `react >= 18`): the CI allowlist exception is **retired immediately**, with zero React
  work and no 2026-10-24 cliff. The React 19 + react-router 8 migration is de-coupled entirely and will
  be planned later on its own merits — it is no longer a security-driven deadline, so it must NOT be
  smuggled into a feature slice.
- **OQ-2 = A** — a dedicated write module sharing ONE internal identity/error core with `apiGet`; the
  read module keeps its no-write guarantee, and identity injection stays single-implementation.
- **OQ-3 = A** — show the actions; render **403** and **409** as first-class plain-language explanations
  naming the control. No `/me`. A visible SoD refusal IS the governance demo.
- **OQ-4 = A** — ship a demo operations extension, **including the H5 legs**: grant `limit.view` +
  `breach.view` to `auditor_3l`, wire maker/checker across ≥2 distinct users, and **approve** the seeded
  limits so they are ACTIVE before the tick runs.
- **OQ-5 = A** — **Assign is OUT of OPS-1.** The demo seed + tick establish ownership; the UI demos
  respond / review / close / approve. The no-new-endpoint fence holds; assign returns with a directory
  read in a later slice.
- **OQ-6 = A** *(the Tier-3 IA sign-off)* — **"Operations" becomes the FIRST nav group, above "The
  walk."** The walk was the front door when there was nothing operational to do; with a live breach queue
  the daily user is an operator and the walk becomes the explainer. The global `book-chip` is scoped to
  the walk (it is false over a tenant-wide queue).

**Net scope:** the four ops surfaces (assign dropped), the write module, the refusal UX, the demo
operations extension, the six blocking folds (H1–H6) + the medium folds, and the OQ-1=C router pin.
Status → **RATIFIED**; proceed to implementation.
