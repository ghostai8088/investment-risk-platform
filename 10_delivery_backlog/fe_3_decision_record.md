# FE-3 Decision Record — the product UI (governance-narrative walk), Wave-9 slice 4

| | |
|---|---|
| **Status** | **RATIFIED 2026-07-21 (OQ-FE-3-1/2/3, user answers). Implementation follows.** Wave-9 slice 4 (roadmap Part 2.12), the LAST slice — the first surface a non-developer sees, depending on API-1's reads (DONE) + SSO-1's identity (DONE). The three forks decided **as recommended**: **(1)** the IA spine is the **governance-narrative walk** — the living demo tenant's own lifecycle (capture → exposures → governed numbers → backtest evidence → validation status → disclosed limitations) as the product narrative, with provenance/validation/limitations **first-class on every governed number** ("verifiability as the product", thesis §2.3) — NOT a generic run browser (OQ-W8C-5, the deferred Tier-3 decision, now taken); **(2)** the browser OIDC auth-code+PKCE login is **deferred to a bounded FE-3b** — FE-3 builds the IA/screens on the preserved `dev_header` client path (the demo runs on it locally); **(3)** a **focused vertical on `DEMO-GLOBAL`, full depth** — the single richest book tells the whole story at high polish, other books/families follow later. **FE-ONLY: NO backend change, NO migration, NO new governed number/code/permission/role, `audit/service.py` untouched.** Consumes only existing API-1/governance reads through the existing GET-only `apiGet` client. Counts UNCHANGED (17/20/35/101). |
| **Premise** | Read-surface assessment F1–F4 are all now discharged (API-1 + FE-2 + SSO-1 DONE), but **the UI still doesn't reflect any of it**: the FE is a two-screen **generic run browser** (`views/RunsList.tsx` + `RunDetail.tsx`) that calls only `/{risk,perf,exposure}/runs` + run-id detail — it wires in **zero** of API-1's entity/time/latest reads, zero governance reads (models/validations/snapshots/audit/lineage), zero private-capital/pacing, even though FE-2's generated types already type the whole API. The assessment (`ui_read_surface_assessment.md:46`) and roadmap (`delivery_roadmap.md:190`) both name the fix as a **Tier-3 USER decision**: make the platform's governance story — traceability, reproducibility, validation, disclosed limitations — the product narrative, not a run table. FE-3 realizes that: the demo tenant's `DEMO-GLOBAL` book carries the entire arc (17 numbers, 35 validations, 101 runs; a designed 2026-05-22 drawdown the currency-factor model deliberately cannot see — the flagship limitation made concrete, not decorated). |

## Part 1 — Grounding (what's BUILT vs. what FE-3 adds, file:line)

### 1.1 The current FE (`apps/frontend/src/`) — a generic run browser
- **Stack (deliberately minimal):** React 18 + React Router 7 + Vite; runtime deps = exactly `react`/`react-dom`/`react-router-dom` (`package.json:12-16`); **no component library, no CSS framework** — one hand-written `styles.css` (OD-FE-1-F). The "no new runtime dep without a decision record" rule stands.
- **Two screens + a gate:** `App.tsx` renders a permanent red `DevBanner`, a session chip, and two routes — `/` → `RunsList` (a paginated run table with run-type/status filters, source-endpoint chosen per permission-family), `/runs/:family/:runId` → `RunDetail` (provenance strip + per-family result rows). No sidebar, no nav, no sections.
- **The GET-only client (`api/client.ts:35-55`):** `apiGet<T>(path, session)` is the only exported call ("deliberately exposes no way to make a non-GET request", `:1-5`); injects `X-User-Id`/`X-Tenant-Id`; maps status→typed `ApiError`. **The read-only fence lives here — PRESERVED by FE-3.**
- **Generated types (`api/generated/api-types.d.ts`, 17k lines):** FE-2's `openapi-typescript` output already types the ENTIRE backend surface — every API-1 read is typed today; only `types.ts` under-wires them. The CI drift-check keeps them honest.
- **The decimal contract (the verifiability seed already in code):** decimals are `string` and rendered verbatim (`RunDetail.tsx:12-15` `cell()`, never `Number()`); `api/decimal-contract.ts` is the exhaustive compile-time guard (FE-2 HIGH fold). The ES `z×σ ≠ value` honesty annotation (`RunDetail.tsx:17-28`) is the precedent for FE-3's "show the arithmetic, flag when it doesn't check out" treatment.

### 1.2 The reads FE-3 consumes (all shipped by API-1; RLS-scoped, silent-empty on foreign id)
- **Capture** (walk step 1): the captured-input reads (positions/valuations/holdings routers, `main.py:55-58`) for `DEMO-GLOBAL` + the FX/factor series. *(Exact entity-filter params verified at Step 0.)*
- **Exposures** (step 2): `GET /risk/factor-exposures?portfolio_id&as_of` + `/latest` (`risk.py:927,948`); `GET /exposure?portfolio_id&instrument_id&as_of` + `/latest` (`exposure.py:283,305`).
- **Governed numbers** (step 3): covariance `/risk/covariances/latest` (`risk.py:1199`); VaR + active-risk **by-id / run-id only** (`risk.py:1641,2047` — Class-C, see §1.3); portfolio-return `/perf/portfolio-returns?portfolio_id` + `/latest` (`perf.py:444,463`); ES via the var-family by-id reads; the seeded 8-point parametric-VaR series via the run listing.
- **Backtest** (step 4): `GET /risk/var-backtests?portfolio_id` + `/latest` (`risk.py:2284,2303`); `GET /risk/es-backtests?portfolio_id` (`risk.py:2619`) — the domain-gated verdict (evidence, no off-domain verdict).
- **Validation** (step 5): `GET /models` (`ModelSummary` w/ `tier`+`validation_status`, `models.py:158`); `GET /models/{id}` (versions w/ assumptions, limitations, `latest_validation`, `models.py:178`); **`GET /models/{id}/validations/{vid}`** — findings + evidence (`models.py:480`). Gate `model.inventory.view`.
- **Limitations** (step 6): the `model_limitation` rows from model detail.
- **Provenance thread** (on every number): `GET /snapshots/{id}` + `/verify` (`snapshots.py:207,226`, gate `snapshot.view`); `GET /audit/events?entity_id` (`audit.py:74`, metadata-only, gate `lineage.view`); `GET /lineage/edges/{id}` (`lineage.py:39`).

### 1.3 The three constraints FE-3 designs AROUND
- **Class-C gap (VaR & active-risk):** NO entity/time list and NO latest-resolver — only by-id + run-id (`risk.py:1641,2047`). "Latest VaR for portfolio P" was verifier-REFUTED as read-only-infeasible and **deferred to API-1b** (needs `calculation_run.scope_portfolio_id`; `ui_read_surface_assessment.md:7`, `delivery_roadmap.md:298`). FE-3 shows VaR via the **seeded 8-point series (run listing) + run-id reads**, and states the "latest-by-portfolio arrives with API-1b" honestly. No workaround that fakes a resolver.
- **No time-series / cross-family summary reads** exist. FE-3 renders the seeded VaR series as the one legitimate multi-point view (it IS a real series of runs) and does not invent a synthetic trend.
- **Partial entitlement:** a session may hold `risk.view` but not `model.inventory.view`/`lineage.view`/`snapshot.view` (`deps.py:158-171`). Every governance pane must **hide/deny gracefully** (a "you don't have `model.inventory.view`" state), never error the whole screen. The client already surfaces a typed 403 (`client.ts:27-33`).

### 1.4 Auth (post-SSO-1) — the two-track reality
SSO-1 made the backend an OIDC resource server (default `oidc`, fail-closed; `dev_header` only when `app_env==local`). The FE today sends `X-User-Id`/`X-Tenant-Id` and no Bearer token. **FE-3 keeps the `dev_header` path** (the demo runs on it locally; the `DevBanner` stays, honest), and **defers the browser OIDC auth-code+PKCE login + Bearer client to FE-3b** (OQ-FE-3-2) — a bounded follow-up that swaps only the client's identity injection. FE-3 does NOT weaken the fail-closed backend posture.

## Part 2 — Design decisions

### OD-FE-3-A — The IA: a governance-narrative walk over `DEMO-GLOBAL` (OQ-FE-3-1, ratified)
A left-nav **six-step walk**, each step a route, all scoped to `DEMO-GLOBAL`:
1. **Capture** — positions + valuations/marks; the designed 2026-05-22 drawdown day called out (the limitation-in-waiting).
2. **Exposures** — factor exposures (the currency-only factor set) + the exposure aggregate.
3. **Governed numbers** — covariance, parametric VaR (the 8-point series), HS-VaR, total-VaR, ES/ES-total, portfolio-return — each rendered as a **GovernedNumber** (OD-C).
4. **Backtest evidence** — VaR backtests (Kupiec/Basel zone) + the ES backtest (domain-gate honesty: evidence, no off-domain verdict).
5. **Validation status** — the models behind those numbers, their tier + validation outcome, and the **findings + evidence** detail (the read that first makes governance visible).
6. **Disclosed limitations** — the `model_limitation` rows tied back to the numbers (currency-only blindness the drawdown day exposes; desmoothing small-sample bias; declared-α riders).
The walk is **linear but free-navigable** (any step reachable); it is the demo tenant's own story, not a run table.

### OD-FE-3-B — The app shell (net-new; no run-browser regression)
Add a shell: a header (product name, portfolio-context chip `DEMO-GLOBAL`, session chip, the `DevBanner` while on `dev_header`) + a left nav listing the six steps. The **existing run browser (`RunsList`/`RunDetail`) is KEPT** reachable (a "Runs" nav item) — FE-3 adds the walk alongside it; no existing behavior removed (the decimal contract + provenance strip carry over).

### OD-FE-3-C — `GovernedNumber`: verifiability first-class (the differentiator, in a component)
A reusable component rendering a governed value with its full trust context inline, never a click-through:
`value` (strings-verbatim, never `Number()`) · **provenance strip** (snapshot ✓/✗ via `/verify`, run id, model version + code version) · **validation badge** (tier + outcome + overdue) · **limitations** (the disclosed caveats) · a **lineage/audit affordance** (`entity_id`→`/audit/events`). This is thesis §2.3 realized on-screen: "every number traces to its inputs and reproduces; every governance artifact is machine-readable" — now also screen-readable. Each sub-pane degrades gracefully on missing entitlement (OD-E).

### OD-FE-3-D — Client + type posture: KEEP the GET-only `apiGet`; wire the reads via generated types
Retain `apiGet<T>` (the read-only fence, OD-FE-2-B) and type every new call against the FE-2 generated `paths`/`components` — **no new runtime dependency**, no `openapi-fetch`. Extend `types.ts`'s view-config for the new families with keys bound to generated `*RowOut`/`*Out` types (the FL-1-kill pattern). The `dev_header` identity injection is untouched (FE-3b swaps it).

### OD-FE-3-E — Partial-entitlement graceful degradation (a first-class UI state)
Every governance pane (validation, limitations, snapshots, audit, lineage) renders a **"requires `<permission>`"** empty-state on a typed 403, never erroring the screen or the walk. The risk/perf/exposure reads similarly degrade per family. This makes the deny-by-default entitlement model legible instead of a failure.

### OD-FE-3-F — Scope fence
FE-3 = the six-step walk over `DEMO-GLOBAL` + the shell + `GovernedNumber` + the governance panes + graceful-degradation states + the Vite proxy prefixes (`/perf`, `/exposure`, `/models`, `/snapshots`, `/audit`, `/pacing`, `/commitments`, `/lineage` — today only `/risk` is proxied, `vite.config.ts:8`) + FE tests. **NO backend change, NO migration, NO new read endpoint** (if a needed read is genuinely absent, STOP and re-scope — do not add backend surface silently). **NO OIDC login (FE-3b), NO time-series/summary invention (the reads don't exist), NO other book/tenant, NO VaR-latest-by-portfolio fake (API-1b).** The GET-only fence + the decimal-strings contract stay byte-behavior-identical.

### OD-FE-3-G — Styling: extend the hand-written CSS, WCAG 2.1 AA
Grow `styles.css` (no framework); semantic HTML, keyboard-navigable nav, sufficient contrast, `aria` on the walk stepper and the provenance/validation badges. The walk stepper communicates progress without relying on color alone.

## Part 3 — Open decisions (OQ-FE-3-1…3) — ALL RATIFIED 2026-07-21
- **OQ-FE-3-1 — IA spine** → **governance-narrative walk** (OD-A). *Ratified.* Rejected: portfolio-first workspace; enhanced run browser.
- **OQ-FE-3-2 — OIDC login scope** → **defer to a bounded FE-3b**; build on `dev_header` now (OD-F, §1.4). *Ratified.* Rejected: build PKCE login inside FE-3.
- **OQ-FE-3-3 — Depth** → **focused vertical on `DEMO-GLOBAL`, full depth** (OD-A/F). *Ratified.* Rejected: broad shallow coverage.

## Part 4 — Invariants & gates
- **Hard invariants:** FE-only (no backend/migration/governed-number/code/permission/role change; `audit/service.py` untouched — not even reachable from the FE); the GET-only client fence preserved; decimals strings-verbatim to the DOM (OD-FE-1-G / the FE-2 exhaustive guard — a test asserts a governed value renders its string unmodified on a new screen); no new runtime dependency (OD-FE-1-F).
- **Gates (never waived):** `make fe-check` green (typecheck / lint / format / tests / build); `make gen-api-check` clean (no schema drift — FE-3 changes no backend DTO, so the committed `openapi.json` must stay byte-identical); the 4-finder adversarial review (FE-weighted: the decimal contract on every new screen, the read-only fence, partial-entitlement degradation, no-fabricated-data honesty, accessibility). `make check` (Python) stays green trivially (no Python change).
- **Counts UNCHANGED** (17/20/35/101) — FE-3 computes nothing.

## Part 5 — Verifier pass (pre-ratification) — to RUN before Step 1
Check: **(V1)** the exact entity-filter params on the capture reads (positions/valuations/holdings) for `DEMO-GLOBAL` — confirm they take `portfolio_id` (the walk step 1 depends on it); **(V2)** that every read the walk needs returns the seeded `DEMO-GLOBAL` data non-empty against a locally-seeded tenant (the demo must actually render — run the reads); **(V3)** that the seeded parametric-VaR "8-point series" is retrievable as a set of runs the FE can list + read by id (the one legitimate multi-point view); **(V4)** that a `dev_header` session as the demo registrar/validator holds the permissions each pane needs, and which panes a `risk.view`-only session must degrade (drives OD-E's test matrix); **(V5)** that no walk step secretly needs a read that doesn't exist (would trip OD-F's "STOP and re-scope"). Findings fold into the plan before Step 1.
