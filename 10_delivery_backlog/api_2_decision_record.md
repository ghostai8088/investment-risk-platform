# API-2 Decision Record — the Limit / Breach / Approve API (Wave-12 slice 1, "Operations, Reachable")

| | |
|---|---|
| **Status** | **✅ RATIFIED 2026-07-24 — implementing.** Gate: **OQ-1=B** (split — API-2 = limits + approve + the shared auth foundation; API-2b = breach lifecycle), **OQ-2=A** (human-doctrine + a hard provisioning gate), **OQ-3=A** (SoD refusal = **409 Conflict**), **OQ-4=A** (provisioning doctrine now; the `app_user` schema tightening is a hard precondition of the provisioning slice). Prior draft below. Recon complete (API/auth/DTO patterns + the limit/breach service surface). Folds the Fable Wave-12 API-boundary audit (`wave_12_api_boundary_audit.md`, D1–D10 + OQ-a–f) as its inputs. **Pre-ratification verifier ran (Part 6): 2 BLOCKING folded** — F1 (canonicalize in the service/actor layer, not the router — self-defending, inherited by API-2b's breach SoD) + B1 (the SoD refusal must get its own error-map key or it collapses to 422/500) — plus N1/N3/N4/N5/F2 non-blocking + the F3/F4 provisioning-slice preconditions. |
| **Premise** | Wave 11 shipped the governed operational controls entirely at the service/tick layer — a supervisor cannot see an open breach, an owner cannot respond, an approver cannot sign off, because there is **no HTTP surface**. API-2 is the first consumption surface: the governed read+write API over limits, the breach lifecycle, and the LIMIT.APPROVE gate. It is where the platform's person-level SoD is either preserved or, per the Fable audit, "one string-form away from decorative." |
| **Governed number?** | **NO.** Counts stay **23/38/109**. An API is a transport surface over existing governed operations; it opens no `calculation_run`, pins no snapshot, binds no model. No new permission (the six R-07 codes exist), no migration to schema (see OQ-4 on the app_user provisioning doctrine). |

---

## 1. Scope (OQ-API-2-1 decides the cut)

The full Wave-11 control surface exposed over HTTP is large: **5 limit writes** (create/update/suspend/resume/approve), **4 breach transitions** (assign/respond/review/close), **~6 reads** (list/get limits, approval queue, limit health, list/get breaches, breach timeline), the D1/D2/D5 auth-boundary foundation, plus DTOs + the error map + the OpenAPI/FE-types regen. That is a heavy single slice. The **recommended cut (OQ-1=B)** splits it on the API-1→API-1b precedent:

- **API-2 (this slice):** the **limit** surface — `POST /limits` (create→DRAFT), `PATCH /limits/{id}` (update, auto-demote), `POST /limits/{id}/approve`, `POST /limits/{id}/suspend`|`/resume`; reads `GET /limits` (by status; `status=DRAFT` = the approval queue), `GET /limits/{id}`, `GET /limits/health`; **AND the shared auth-boundary foundation (D1/D2/D5)** — because `approve` is where the person-level SoD first meets HTTP.
- **API-2b (fast-follow):** the **breach lifecycle** surface — `POST /breaches/{id}/assign|respond|review|close`; reads `GET /breaches` (by state/portfolio), `GET /breaches/{id}` (+ its `breach_action` timeline). Reuses API-2's auth foundation unchanged.

OQ-1=A ships both together. Recommend B (each independently reviewable; the person-level-SoD boundary work lands once in API-2 where `approve` needs it; API-2b is then a thin, foundation-reusing slice).

---

## 2. The auth-boundary foundation (the Fable CRITICAL demands — the headline of this slice)

**D1 — one actor-identity space, one canonicalization point, symmetric at stamp and compare.** Recon confirmed: `Principal` (`entitlement/service.py:28-34`) carries only `user_id` + `tenant_id`; in OIDC mode `user_id` is the server-resolved `app_user.id` (`deps.py:136`, canonical), but in `dev_header` mode it is the raw unverified header (`deps.py:84`); and **every existing router passes `principal.user_id` RAW into the domain actor** (`snapshots.py:60`, `ingest.py:96`, …) — no canonicalization. The person-level SoD then compares raw strings (`service.py:506` `actor.actor_id in {created_by, updated_by}`) while `require_permission`→`has_permission` compares the same identity through PG's case-INsensitive `uuid` cast — so a non-canonical form passes the gate but escapes the maker set → **self-approval**.
- **Design (REVISED per verifier F1 — canonicalize in the SERVICE/actor layer, not the router):** the single canonicalization point is `LimitActor.__post_init__` / `BreachActor.__post_init__` (`limit/events.py`, the shared package) — a **lenient** normalization: `str(uuid.UUID(actor_id))` when the id is UUID-shaped, else pass through unchanged. So every UUID-shaped actor id (the production `app_user.id`, in ANY casing/format) is canonical BY CONSTRUCTION at both the STAMP (`created_by`/`updated_by`) and the COMPARE (`approve` maker-set; the MG-2 breach responder-set) sites — the control is self-defending and does NOT rest on each caller remembering. Non-UUID ids (the synthesized tick SYSTEM actors `limit-eval:{id}`/`breach-deadline:{id}`; existing test fixtures like `risk-mgr-2l`) pass through untouched, so nothing breaks. This makes "one identity space" a structural guarantee that **API-2b's breach SoD inherits for free** (verifier F1: a separate `_breach_actor` helper would be a copy, not a shared guarantee — MG-2's first person-level SoD is defeatable identically if canonicalization lives in the router).
- **Pin as a SERVICE-LEVEL invariant** (not an API convention): `actor_id`/`created_by`/`updated_by` for a human actor MUST be a canonical `app_user.id` — enforced by the actor dataclass, so a future non-API writer (seed/demo) inherits it too.
- **The API boundary ADDITIONALLY fail-closes** (verifier F2): the router's actor-construction validates `principal.user_id` parses as a UUID and raises a clean **401** (never a bubbled 500); the **dev-header contract** is stated — `X-User-Id` MUST be a parseable `app_user.id` UUID.
- **Test (blocking):** a maker whose dev-header presents the UPPERCASE form of their `app_user.id` creates a limit, then approves it under the lowercase form → **SoD-refused** (today this SUCCEEDS — the defeat); two distinct principals do NOT falsely collide; OIDC end-to-end both directions; the SAME defeat replayed on the MG-2 breach 1L→review path (API-2b) is refused by the inherited canonicalization. *Scope note: this fold means API-2 touches `limit/events.py` in the shared package (the actor dataclasses), not only the API layer — a small, correct expansion.*

**D2 — one human = one live `app_user` row.** Recon: uniqueness is `(tenant_id, external_subject)` but `external_subject` is **NULLABLE** (`entitlement/models.py:26-31`) — two NULL-subject rows don't collide, and an IdP `sub` change would mint a sibling row, defeating the SoD invisibly. **Ratify a standing provisioning doctrine (OQ-4):** a human in OIDC mode always has a non-null `external_subject`; rebinding updates `external_subject` on the SAME row (never a sibling insert); deactivate-don't-delete (`is_active`); `sub` matched exactly (canonicalize by RESOLVING to `app_user.id`, never by normalizing the claim). The schema tightening (a partial unique index / NOT-NULL-for-active) is carried to whenever user-provisioning/onboarding is built (not this slice — no provisioning endpoint here).

**D5 — human-only (BR-15) at the edge.** Recon: there is NO human-vs-machine plumbing; `Principal` has no `actor_type`, and an HTTP-built actor is ALWAYS `actor_type="user"`; the machine distinction is enforced by ENTRYPOINT (HTTP=user, tick=synthesized SYSTEM). **OQ-2 decides the mechanism:** (A) ratify the doctrine "an `app_user` row is a human; a service/automation principal is NEVER provisioned as an `app_user` holding approve/review/respond" + a note (leaner; the entrypoint IS the distinction; no machine principal has an `app_user` row today), or (B) add an `is_human`/`principal_type` marker on `app_user` threaded into `actor_type`. The service-layer `_require_human` stays the backstop either way.

**D3 — the API mints no second write path.** `status` is NOT a field on the create/update request DTOs (OpenAPI-asserted); suspend/resume/approve are dedicated endpoints onto `suspend_limit`/`resume_limit`/`approve_limit`; PATCH builds `**changes` from `model_dump(exclude_unset=True, exclude={reserved})` (the `positions.py:174` pattern); handlers are thin pass-throughs — no direct ORM writes to `LimitDefinition`/`Breach`/`BreachAction`. **Belt-and-suspenders (verifier N1):** the PATCH handler additionally `changes.pop("status", None)` — Pydantic's default `extra="ignore"` drops an unknown body key, but an explicit drop makes the "status never rides the edit path" guarantee independent of the DTO shape (a future `extra="allow"` or an added field would otherwise silently re-open the redundant suspend/resume write path). *Tests:* the MG-3 bypass suite (suspend→edit→resume; status+governing combo) replayed through HTTP; a `"status":"ACTIVE"` smuggled into **create** yields DRAFT-or-422; a `"status":"SUSPENDED"` smuggled into **PATCH** is ignored (limit unchanged).

---

## 3. The endpoints + the reads to BUILD

Mutators take a domain OBJECT, not an id (`update_limit(limit, …)`, `approve_limit(limit, …)`, the breach transitions take a `Breach`) — so each write handler **loads the entity tenant-filtered first** (the get-by-id read doubles as the load step). Recon confirmed these reads are **ABSENT and must be built** (in the shared package, not inline SQL): `list_limits(acting_tenant, status?)`, `get_limit(acting_tenant, id)`, `list_breaches(acting_tenant, state?/portfolio?)`, `get_breach(acting_tenant, id)`, `breach_action_timeline(acting_tenant, breach_id)` (ordered by `seq`). Only `limit_health` and `current_breach_state` exist. `evaluate_limit`/`escalate_overdue_breach` are **TICK-ONLY — never exposed** (D10; a route-inventory test pins the exact verb set).

**Reads doctrine (D6/D9):** a breach DTO's `state` is `current_breach_state` (recency-derived), NEVER the frozen `Breach.status` column (which serializes `DETECTED` forever). Any read touching a governed number goes through the AD-019 seam — `GET /limits/health` wraps `limit_health` verbatim (which already recomputes from `calc/reads` — confirmed). New list-reads carry the explicit `tenant_id == acting_tenant` predicate atop RLS; batch the per-breach state derivation (do NOT replicate the `select_overdue_breaches` N+1 at list scale).

**FE contract (verifier N5):** the response DTOs type the enums as `Literal[...]` so `make gen-api` emits stable FE unions and `gen-api-check` stays drift-clean — limit `status` (`DRAFT`/`ACTIVE`/`SUSPENDED`) and `LimitHealth.state` (`IN_APPETITE`/`NEVER_EVALUABLE`/`BREACHED`) in API-2; the breach `state` enum in API-2b.

**The intermediate-state contract (verifier N3, OQ-1=B):** shipping API-2 (limits) before API-2b (breach lifecycle) is a strict superset of Wave-11 — the tick still DETECTs, audits, and auto-escalates breaches entirely at the tick layer. But `GET /limits/health` will surface `state=BREACHED` + `latest_breach_id` with **no endpoint to fetch or action that breach until API-2b**. This is a shippable, honestly-recorded intermediate (breaches remain tick/DB-visible + a health teaser), not a strand — stated so ops isn't surprised.

**Per-endpoint permission table (D4)** — deny-by-default `require_permission` guard singletons at module level:

| Endpoint | Permission |
|---|---|
| POST /limits · PATCH /limits/{id} · /suspend · /resume | `limit.manage` |
| POST /limits/{id}/approve | `limit.approve` |
| GET /limits · /limits/{id} · /limits/health | `limit.view` |
| (API-2b) POST /breaches/{id}/respond | `breach.respond` |
| (API-2b) POST /breaches/{id}/assign · /review · /close | `breach.review` |
| (API-2b) GET /breaches · /breaches/{id} | `breach.view` |

*Conformance test:* every route rejects a principal without its mapped code (403); a `platform_admin` (holds ALL codes) is STILL person-level-SoD-refused on its own draft.

---

## 4. Error mapping, concurrency, DTO/contract (D7 + the mechanical patterns)

- **Error map (REVISED per verifier B1 — the SoD subclasses get their OWN keys, or the status silently collapses to 422/500):** dispatch domain refusals through `map_refusal` (the MRO walk); register `LimitError`→422 (validation) **AND `LimitSodError`→OQ-3-status as a SEPARATE, more-derived key** (else the MRO walk hits the `LimitError` base and returns 422, not the ratified SoD status — B1 defeat 1); `BreachTransitionError`→409 (illegal transition) **AND `BreachSodError`→OQ-3-status as its own key**; not-found/cross-tenant→404 (indistinguishable). **Reserve the exact-type `raise_mapped_write` for `IntegrityError`-unique→409 ONLY** — routing a domain subclass through it would `KeyError`→500 on the SoD refusal (B1 defeat 2). *Test (blocking):* self-approve → the OQ-3 status (NOT 422, NOT 500); a base `LimitError` (bad threshold) → 422; a breach SoD refusal → the same OQ-3 status. Uniform across API-2/API-2b.
- **The create-duplicate `(tenant, code)`** raises `LimitError`→422 on the pre-check but `IntegrityError`→409 under a concurrent race (verifier N4) — map the pre-check duplicate to **409** too, for a uniform "already exists" contract.
- **Response-before-commit (load-bearing):** the RLS GUC is transaction-local and clears at `db.commit()`; any handler that re-SELECTs to build its body (e.g. returning the approved limit + fresh health, or a breach + its timeline) must serialize BEFORE commit (the `snapshots.py:174-179` invariant). Single end-of-request commit (AD-016); no mid-request commit/rollback-then-continue.
- **Concurrency:** a double-submitted approve blocks on `approve_limit`'s `FOR UPDATE`, then reads ACTIVE and raises `LimitError` → a clean 409/422, never a 500 (*two-session PG test*).
- **DTO contract:** decimals (`threshold_value`/`observed_value`, `PreciseDecimal(34,12)`) serialize as fixed-point `f"{x:f}"` strings (the FE-2 exhaustive-decimal contract; never a float, never scientific); uuid path params → auto-422 + domain-404; the new router is registered in `main.py`, `make gen-api` run, and `openapi.json` + `apps/frontend/src/api/generated` committed drift-clean.
- **D8 (P3-5 guards):** `create_limit` already carries the cross-tenant FK guard (verified). The `create_schedule` guard is **carried to the cadence-wiring slice** (no schedule endpoint here). In API-2b, `assigned_to` on breach-assign must resolve to an ACTIVE `app_user` in the acting tenant (today any string dangles).

---

## 5. Open questions for the ratification gate (Tier-3)

**OQ-API-2-1 — slice cut.** **B [rec]:** API-2 = the limit surface (writes + approve + reads + the D1/D2/D5 auth foundation); API-2b fast-follow = the breach lifecycle surface (reuses the foundation). **A:** both in one slice. *Recommend B — each is independently reviewable, the person-level-SoD boundary work lands once where `approve` needs it, and API-1→API-1b is the precedent. A is viable if you want the whole operational API in one pass.*

**OQ-API-2-2 — BR-15 human-vs-machine mechanism (Fable D5).** **A [rec]:** a ratified doctrine ("`app_user` = human; never provision a service/automation principal as an `app_user` with approve/review/respond") + the entrypoint-derived `actor_type="user"` + the `_require_human` backstop. **B:** an explicit `is_human`/`principal_type` marker on `app_user` threaded through `Principal`→`actor_type`. *Recommend A — leaner; the entrypoint IS the human/machine boundary (HTTP=user, tick=SYSTEM), and no machine principal has an `app_user` row today. B is a schema+plumbing change for a distinction the architecture already makes structurally.*

**OQ-API-2-3 — HTTP status for a person-level SoD refusal (Fable OQ-c).** **A [rec] 409 Conflict:** keeps 403 meaning ONLY "missing permission" (the principal HOLDS `limit.approve`/`breach.review`; the refusal is a conflict between the actor and the record's maker/responder set — a state conflict, like the other 409s). **B 403 Forbidden:** "you may not perform this action on this resource." *Recommend A — a clean operational split (403 = entitlement gap, 409 = SoD/state conflict) that ops and the FE can act on distinctly; uniform across `LimitSodError`/`BreachSodError`, pinned by test.*

**OQ-API-2-4 — the `app_user` one-human-one-row doctrine + the nullable `external_subject` (Fable D2).** **A [rec]:** ratify the provisioning doctrine NOW as a standing invariant (rebind-in-place; non-null `external_subject` for OIDC humans; deactivate-don't-delete) and **carry the schema tightening** (partial unique index / NOT-NULL-for-active on `external_subject`) to whenever user-provisioning is built — there is no provisioning endpoint in this slice. **B:** tighten the schema in this slice. *Recommend A — the doctrine is what protects the SoD; the schema tightening belongs with the provisioning code, not a limit-API slice.*

---

## 6. Pre-ratification verifier — folds (2 BLOCKING + non-blocking, all folded above)

Two independent verifiers ran against the design + code before this gate (the ES-1 lesson):
- **F1 (BLOCKING, folded into §2/D1):** canonicalization must live in the SERVICE/actor layer (the `LimitActor`/`BreachActor` dataclasses), not a per-router helper — else it is not self-defending and API-2b's separate `_breach_actor` could diverge and defeat MG-2's breach SoD identically (the P3-5 "guard in the service, not the transport" doctrine).
- **B1 (BLOCKING, folded into §4):** "register the domain bases" would collapse the SoD refusal to 422 (MRO walk hits `LimitError`) or 500 (`raise_mapped_write` exact-type `KeyError`) — the SoD subclasses must get their own map keys; the SoD status is now a blocking test.
- **Non-blocking, folded:** N1 (explicit PATCH `status` drop + a PATCH-side smuggle test); N3 (the intermediate-state contract); N4 (create-duplicate → uniform 409); N5 (`Literal[...]` enums for FE drift); F2 (dev-header UUID contract + 401 not 500).
- **Affirmed sound (no change):** the response-before-commit ordering is correct AND aligned with `limit_health` (approve flushes-not-commits, so the same-txn `select_active_limits` sees the freshly-ACTIVE limit before commit — verifier N2); no service fn commits internally; the D3 DRAFT-bypass cannot be reconstructed through the DTO.

**HARD preconditions recorded for the FUTURE user-provisioning slice (verifier F3/F4 — NOT this slice, but must not be lost):** (1) tighten `app_user` — a partial unique index on `external_subject WHERE is_active` (the current `(tenant_id, external_subject)` unique permits multiple NULL-subject rows → two `app_user.id`s for one human → the SoD is defeatable via the second identity); `app_user.id`-one-row-per-human is the load-bearing SoD invariant. (2) Provisioning a non-human/service principal as an `app_user` holding `limit.approve`/`breach.review`/`breach.respond` is FORBIDDEN (OQ-2=A's doctrine made a hard gate — `_require_human` at the HTTP edge is otherwise structurally vacuous since `Principal` carries no human/machine signal).

## 7. Cadence

Recon ✅ → this decision record → **pre-ratification verifier** (fold blocking holes; the ES-1 lesson) → **user ratification gate** (OQ-1 scope, OQ-2 human/machine, OQ-3 SoD status, OQ-4 provisioning doctrine) → implement (the D1 canonicalization dependency + the endpoints + the 5 new reads + DTOs/error-map/OpenAPI) → `make check` + `make gen-api-check` + full-PG + CI-to-green → **4-finder adversarial review** (with a mandatory lens re-probing the D1 SoD-canonicalization defeat through HTTP) → merge → closeout → API-2b.
