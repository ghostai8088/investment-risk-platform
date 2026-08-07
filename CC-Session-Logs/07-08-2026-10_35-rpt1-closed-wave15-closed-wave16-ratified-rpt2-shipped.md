# Session Log: 07-08-2026 10:35 - rpt1-closed-wave15-closed-wave16-ratified-rpt2-shipped

## Quick Reference (for AI scanning)

**Confidence keywords:** RPT-1, RPT-2, ENT-072 `report_generation`, migration 0063, migration
0064 `entitlement_sync`, Wave-15 close review, Wave-16 planning gate, OQ-W16P-1…7, P15, CTRL-009,
CTRL-018, REPRO-1, FK-1, `report.view`, `report.generate`, R-07 mint, P11 route census,
`portfolio_code` pinning, attribution fence, `scope_portfolio_id`, `as_of_date` fence, issuer
disclosure, `concentration.issuer.view`, auditor_3l, CSP sandbox, `apiGetHtml`, srcDoc iframe,
eslint 10, jsdom 30, TypeScript 7 refused, typescript-eslint peer, six root guard tests,
`tsconfig.guards.json`, psycopg missing from runtime images, GitHub Actions outage
`qcvjkzcs7j74`, adversarial review workflow, fresh-context pre-merge audit, mutation-proving,
G5/H1 survived mutations, P1 seven-ledger sweep, PRs #176–#182, 17th/18th autonomous merges,
`prove_report_identity.sh`, cross-generation identity, `CHECK_ALL_EXIT`, full-PG census 3085.

**Projects:** investment-risk-platform (multi-tenant governed enterprise investment-risk platform).

**Outcome:** RPT-1 closed and merged; Wave 15 closed with a fresh-context review whose six
ratification items the user approved; Wave 16 planned and ratified (RPT-2 → REPRO-1 → FK-1); RPT-2
built, adversarially reviewed, fresh-context audited, twice folded, and merged — the governed
report is now reachable over HTTP and in a browser, and every read re-proves reproducibility.

---

## Decisions Made

- **P15 ratified** — *"Two proofs sharing an assumption count as one proof; when a claim matters, at
  least one proof must be constructed under different assumptions than the implementation."*
  Deliberately NOT self-enacted; proposed at the Wave-15 close as an explicit item, on the P14
  precedent that an evidence-sufficiency rule for the builder's own claims is the user's to enact.
- **Wave-15 close review's §5 A–F all ratified** ("proceed"): CTRL-018 gets a host (REPRO-1, Wave
  16) after FOUR citations-without-host; PERF-0's four carries bound to *"before any parallelization
  or grain-level performance work"*; the FE toolchain decided at the Wave-16 gate; report endpoints
  (RPT-2) as an early Wave-16 item; P15 ratified; the FK slice sequenced.
- **Wave-16 gate ratified, all seven OQs as recommended**: slice order RPT-2 → REPRO-1 → FK-1;
  `generated_at` SERVER-stamped for HTTP callers; the FE report view IN scope; the FE toolchain
  majors paid as slice 0; REPRO-1 rides the existing scheduler; FK-1's acceptance is exact
  (115 → 0, pragma ON globally, per-suite count pinned); nothing outward-facing this wave.
- **TypeScript 7 REFUSED, with executed evidence** — `typescript-eslint` (installed AND
  registry-latest) peers `typescript >=4.8.4 <6.1.0`; `openapi-typescript` peers `^5.x`; both are
  gate-critical. TS 7.0.2 was actually installed (P12: execute the plainest alternative before
  recording an impossibility) and produced a **split-brain toolchain** — compiler on 7, the
  governance fences' parser still resolving 5.9 from the root, every gate green and nothing to say
  so. Reverted; no override. Trigger to pay: both tools declare TS-7 support.
- **The report binds ONE snapshot and pins the VALUE, not just the run id** (carried from RPT-1) —
  which is why ENT-072 stores the hash and deliberately NOT the body, making every HTTP read of the
  artifact a fresh reproduction check.
- **An identity divergence on the HTML endpoint is a 500, never a 4xx** — the platform failing its
  own BR-9 claim, not a client error.
- **The report's artifact response carries its OWN CSP** (`sandbox`, `default-src 'none'`) +
  `nosniff` + `no-referrer` — because nginx proxies the artifact on the SPA's origin, so the iframe
  sandbox protects the app but not a direct navigation with the bearer token in reach.
- **Migration 0064 keeps its no-op downgrade and its re-insertion of revoked grants** — it cannot
  distinguish "never delivered" from "revoked" (deterministic uuid5 ids), and without that it cannot
  do its job at all. Documented as the accepted consequence rather than claimed away.
- **The unscoped-run refusal STAYS** even though it makes VaR unbindable via the snapshot-consume
  path: for such a run nothing evidences the attribution, and admitting it re-opens the exact defect
  the fence closes. Recorded as carry (f) with the upstream fix named.
- **The `/reports` SPA route namespaced to `ops/reports`** — the API prefix of the same name shadows
  the bare path in both nginx and the vite dev proxy.
- **Branch pruning**: 126 fully-merged local branches deleted with `-d` (not `-D`), manifest saved
  first; the single refusal investigated and only then forced after proving both tips were ancestors
  of `main`. Remote branches deliberately NOT touched.

---

## Key Learnings

- **Layered scrutiny is not redundant — RPT-2 measured it.** Three stages each found defects the
  previous structurally could not: the deployed smoke (the runtime images had never installed the
  PostgreSQL driver); the 5-lens adversarial review (cross-book attribution; the undeliverable
  mint); and the fresh-context audit (an issuer disclosure the review had already looked for and
  missed, plus **a regression the review's own fold introduced**). *"Reviewed" is not "audited".*
- **A fix written and believed is not a control — twice in one slice.** Mutation G5 (the artifact's
  CSP headers) and mutation H1 (the issuer exclusion) each killed NOTHING until a test was written
  for them. Both were security fixes; both were caught only by mutating my own fixes.
- **Two individually-correct halves with no relation between them is a defect class.** The generate
  verb fenced the portfolio to the tenant and each run to the tenant+type — and nothing related the
  two, so a report could be headed `PF-A` while carrying `PF-B`'s numbers, same tenant throughout, no
  isolation control able to fire. The same class was then found still open on the DATE axis.
- **A permission mint has been undeliverable to live databases since P0.5.** `0002` live-imports the
  catalog and is long since applied, so `alembic upgrade head` on an existing database delivers ZERO
  new codes — and `require_permission` is deny-by-default, so the surface 403s for every holder while
  every from-empty test passes.
- **A security split can be defeated through a new door.** `report.view` (auditor_3l holds it) served
  the ISSUER rows `concentration.issuer.view` exists to withhold — the REF-1 blocking class, with
  every per-code holder pin still passing.
- **`gh pr checks` displays `cancelled` as `fail`.** The API says `cancelled`. Taking the CLI's word
  would have sent me hunting a defect in code the push run had already proven green.
- **`status` is a READ-ONLY variable in zsh.** A watcher assigning to it silently never fires its
  completion branch — right answer, broken instrument, caught only by querying the source of truth.
- **A mutation harness must never restore with `git checkout --`** — its subject is uncommitted by
  definition. The first harness destroyed the file it was testing. Snapshot in memory, and verify the
  mutation is STILL on disk after the run that claimed to survive it (an editor buffer-restore race
  faked a surviving mutant once).
- **The naive `app.routes` walk sees ZERO APIRoutes** — FastAPI wraps included routers in
  `_IncludedRouter`. A census without an anti-vacuity count pin passes green over nothing; that exact
  bug had been shipping in `test_schedules_endpoint.py`.
- **pytest's final summary line intermittently absent** from full-PG logs (3rd occurrence) — census
  by progress marks, cross-checked against `passed + skipped`, every time.

---

## Solutions & Fixes

- **The attribution fence** (`report/service.py`): `build_report_snapshot` takes a REQUIRED
  `portfolio_id` and `as_of_date` and refuses any run whose `scope_portfolio_id` differs, is NULL, or
  whose pinned snapshot's `as_of_valuation_date` differs from the report's heading date.
- **Migration `0064_entitlement_catalog_sync`** — idempotent, additive-only sync of the WHOLE
  permission catalog + role-template grants, using the deterministic `uuid5` ids. Proven on a
  simulated live DB: `0 → 2` report codes, `8` grants, `UPGRADE_EXIT=0`, second run changes nothing.
- **Issuer exclusion at the QUERY** (`report/families.py::_read_concentration`) using the identical
  predicate `list_concentration_results(include_issuer_detail=False)` applies.
- **UUID typing** — every report id/portfolio id typed `uuid.UUID` so FastAPI 422s before the query
  (a malformed value 500'd on PostgreSQL while SQLite proved a 404 production never exhibits).
- **`psycopg[binary]>=3.1` added to backend + worker Dockerfiles** — neither runtime image had the
  driver since DEP-1.
- **`apiGetHtml`** (a separate FE client verb) — `request()`'s JSON guard exists to catch proxies
  answering HTML where JSON belongs; teaching it HTML would blunt that guard everywhere else.
- **`tsconfig.guards.json`** — the six root guard tests typechecked as their OWN node program
  (they use `node:fs`, `process`, the programmatic ESLint API) rather than polluting the browser
  program with `@types/node`.
- **`scripts/check_frontend_audit.d.mts`** — a sibling declaration for the cross-package `.mjs`
  import; typechecking immediately caught the shim's own return type wrong.
- **`test_route_permission_census.py`** — the platform-wide P11 census that never existed: recurses
  through `original_router`, pins the EXACT route count (291), exact anonymous set, exact
  forward-gate dict, and the reverse direction (a route demanding an unminted code).
- **`prove_report_identity.sh` HTTP arm** — on the RESTORED stack: 401 unauthenticated, 403
  unentitled, the restored report listed, `GET /html` bytes hashing to the recorded identity, 403
  view-cannot-generate, 422 wire-cannot-assert-time, generate-over-HTTP re-read byte-identical, and
  **cross-generation identity** (two independent generations agree — the assertion an earlier commit
  message claimed but the script did not contain).

---

## Files Modified

**RPT-1 (closed this session):**
- `packages/shared-python/src/irp_shared/report/{service,families,models}.py` — the generate verb on
  the governed run rail; provenance resolved FROM THE BOUND RUN; `portfolio_code` pinned (audit B1).
- `packages/shared-python/tests/test_report_pg.py` — 7 PG controls, 7 mutations.
- `packages/shared-python/src/irp_shared/deploy/report_identity_proof.py` +
  `infra/deploy/prove_report_identity.sh` — I2's restore-cycle arm.
- `10_delivery_backlog/rpt_1_slice_record.md`; `09_compliance_controls/control_matrix_skeleton.md`
  (CTRL-009 → Implemented); `04_data_model/canonical_data_model_standard.md` (ENT-072 row).

**Wave-15 close / Wave-16 planning:**
- `10_delivery_backlog/wave_15_close_review.md` (§0–§7 incl. the ratified gate outcome).
- `10_delivery_backlog/wave_16_planning.md`, `10_delivery_backlog/rpt_2_remit.md`.
- `docs/project_memory/claude_operating_instructions.md` — **P15 added**; P13's stale "NOT yet
  ratified" header corrected.
- `10_delivery_backlog/delivery_roadmap.md` — history rows; PERF-0 carries bound; FE toolchain
  escalated.

**RPT-2:**
- `apps/backend/src/irp_backend/api/reports.py` (new), `main.py` (registration).
- `apps/backend/tests/test_reports_endpoint.py` (new, 22 tests),
  `test_route_permission_census.py` (new), `test_schedules_endpoint.py` (vacuous walker fixed).
- `packages/shared-python/src/irp_shared/entitlement/bootstrap.py` — the `report.*` mint.
- `packages/shared-python/tests/test_entitlement_bootstrap.py` — report + the unpaid LQ-1 pins.
- `06_security/entitlement_sod_model.md` — report row + the absent LQ-1 row + ratification correction.
- `apps/frontend/src/views/reports/{Reports.tsx,reports.test.tsx}` (new),
  `src/api/client.ts` (`apiGetHtml`), `App.tsx`, `AppShell.tsx`, `api-prefixes.ts`, `styles.css`.
- `apps/frontend/package.json`, `packages/shared-ts/package.json`, `tsconfig.guards.json`,
  `scripts/check_frontend_audit.d.mts`, `package-lock.json`.
- `infra/docker/{backend,worker}.Dockerfile` (psycopg), `frontend-nginx.conf` (reports prefix).
- `migrations/versions/0064_entitlement_catalog_sync.py` (new) + 21 migration-head pins moved.
- `10_delivery_backlog/rpt_2_slice_record.md` (new), `docs/project_memory/current_state.md`.

**Memory:** `layered-scrutiny-measured.md` (new), `delivery-roadmap-state.md`, `MEMORY.md`.

---

## Setup & Config

- Local PG container `irp_pg_local` (`postgres:16`), port 5432; schema reset BEFORE every full-PG run.
- `DATABASE_URL` is the alembic env var (not `IRP_DATABASE_URL`).
- `gh` at `~/.local/bin/gh`; `export PATH="$HOME/.local/bin:$PATH"` needed each shell.
- Deployed-proof compose projects and ports: `irp-dep1` (55432), `irp-dep1-br` (55433),
  `irp-rpt1-id` (55435, moved from 55434 after a collision); backend publishes **8000
  unconditionally** — the smoke now pre-flights it.
- Node 24.18 locally; CI pins node 24 (jsdom 30 needs `^22.22.2 || ^24.15 || >=26`).
- Installed after slice 0: eslint 10.8.0, @eslint/js 10.0.1, jsdom 30.0.1, typescript pinned ^5.9.3.

---

## Pending Tasks

- **OWED AT THE WAVE-16 CLOSE (user decisions, not settled):**
  1. `report.*` **holder-set ratification** — never put to the user; two records wrongly claimed it
     (corrected). Chosen sets: `report.view` = {data_steward, risk_analyst_1l, risk_manager_2l,
     auditor_3l, platform_admin}; `report.generate` = {data_steward, risk_analyst_1l, platform_admin}.
  2. **The mint-reachability rule** — appending to `bootstrap.py` is NOT sufficient for a live
     deployment — proposed as standing, not ratified.
- **NEXT SLICE = REPRO-1** (the CTRL-018 reproduction job, riding the existing scheduler; CTRL-018
  moves Planned → Implemented only on the first OBSERVED scheduled green), then **FK-1** (115 → 0).
- Carries (a)–(i) in `rpt_2_slice_record.md` §5: the worker's deployed DB path still unproven;
  jsdom cannot see sandbox semantics; VaR unbindable via the snapshot-consume path (upstream scope
  propagation); I1's refusal arm unit-tier only; I4's remit wording vs what was built; durable
  template-grant revocation; the 103-test SQLite FK gap.
- ~120 stale REMOTE branches on origin (local pruned to 1); offered, not done.
- The missing-pytest-summary anomaly (3rd occurrence) — diagnose on a future full-PG run.

---

## Errors & Workarounds

- **GitHub Actions major outage `qcvjkzcs7j74`** (15:22 UTC, ~6h): all runs queued indefinitely, one
  cancelled mid-queue. Waited, re-ran, cancelled superseded runs, tried close/reopen (webhooks
  throttled — no new run). Did NOT merge around the required checks. Resolved when the queue moved.
- **`gh pr merge` denied by the permission classifier** — reported and stopped; the user authorised
  it, then it worked.
- **Direct push to `main` rejected** (`GH006 … must be made through a pull request`) — correct;
  redone as a PR. My approach was wrong, not the protection.
- **Mutation harness destroyed uncommitted work** via `git checkout --`; rewritten to snapshot in
  memory. Later, an editor buffer-restore made a mutation appear to survive — fixed by asserting the
  mutated bytes on disk before AND after the run.
- **Zsh `status` read-only** broke a CI watcher's completion branch (see Key Learnings).
- **`gh pr checks` showed 8 "fail"** that the API reported as `cancelled` (outage casualties).
- **Fable quota exhausted mid-workflow** — 13 of 32 verifier agents died; the pre-merge audit was
  therefore run on Opus with fresh-context subagents, and the model-diversity gap was stated to the
  user rather than papered over.
- **`test_report_pg.py` raw INSERT** missed the new NOT NULL `portfolio_code` — `make check-all` was
  green (the suite skips without PG) and the full-PG battery caught it. The named-proof argument in
  miniature.
- Assorted self-inflicted: the same dead-initializer eslint 10 flagged in `request()` was copied into
  `apiGetHtml`; a fixture that always INSERTed a model version collided on its unique key; a test
  asserted a specific refusal message the error map deliberately makes opaque.

---

## Key Exchanges

- **"What do you recommend I do next?"** → recommended the Wave-15 close review over feature work,
  with the reasoning and the honest caveat that it is expensive and mostly reading.
- **"close review"** (on Fable) → found ONE blocking-class process defect: the ratified OQ-W15P-7
  commitment fired silently, and CTRL-018 reached a FOURTH citation-without-host in the very wave
  whose gate said three was the signal.
- **"approved. proceed"** → all six §5 items taken as recommended, each with its operating assumption
  stated; P15 became standing.
- **"proceed with Opus"** after the Fable quota limit → the RPT-2 review fold and the pre-merge audit
  ran on Opus; the reduced model diversity was disclosed rather than implied away.
- **"sweep"** → 127 local branches → 1, with a manifest, `-d` semantics, and the single refusal
  investigated before forcing.

---

## Custom Notes

None

---

## Quick Resume Context

`main` is at `88ccbed`; migration head `0064_entitlement_sync`; next free canonical id **ENT-073**;
eighteen autonomous merges through PR #182. Wave 16 is slice 1 of 3 complete (RPT-2 ✓ → REPRO-1 →
FK-1). **Two items are owed to the user at the Wave-16 close and must not be treated as settled:**
the `report.*` holder-set ratification and the mint-reachability rule. The next build slice is
REPRO-1 — the CTRL-018 nightly reproduction job riding the existing scheduler, whose control moves
Planned → Implemented only on the first OBSERVED scheduled green. Standing practice now: recon
fan-out → build → adversarial review workflow → **fresh-context pre-merge audit** (a different model
where quota allows), mutating every fix including those made while folding a review.

---

## Raw Session Log

**The authoritative verbatim transcript is the session JSONL:**
`/Users/andrewcox/.claude/projects/-Users-andrewcox-Projects-investment-risk-platform-investment-risk-platform/70b746c9-a66f-4a2f-a168-ed3b64166457.jsonl`

It is not reproduced here. Writing a "full conversation" from memory would fabricate a record, and
this session's own subject matter — a report that would have rendered `None` as a governed number,
controls that verified their own existence, commit messages asserting proofs that did not exist —
is exactly the failure class that practice produces. What follows is the accurate skeleton; the
JSONL is the archive.

### Session arc (chronological)

1. **RPT-1 completion** — the generate verb (`67aa3c3`), the PG tier (`02d7a44`, 7 controls / 7
   mutations), I5+VaR+I3+I2 (`9bd5423`), the measured SQLite FK gap (`8985967`), slice record +
   CTRL-009 (`f34361f`).
2. **RPT-1 pre-merge audit (Fable)** — 2 blocking: `portfolio_code` unpinned (both proof tiers shared
   the assumption); ENT-072 had no registry row. Folded as `4b2994f`; the PG suite's raw INSERT then
   caught by the full-PG battery (`31787c5`).
3. **Merge #176 → `4eab7e0`**, close #177 → `c532298`; P1 sweep clean.
4. **Branch sweep** — 127 → 1.
5. **Wave-15 close review (Fable)** — verdict COMPLETE/clean with one blocking-class process finding;
   merged #178 → `d904d6c`.
6. **Ratifications** ("approved. proceed") — P15 standing; CTRL-018 hosted; PERF-0 carries bound;
   two stale ledger rows corrected. Wave-16 planning drafted and merged (#179 → `3da0384`).
7. **Wave-16 gate ratified**; RPT-2 remit written with the first inherited-gate-commitments table
   (#180 → `4b31708`).
8. **RPT-2 build** — recon workflow (6 lanes); slice 0 `a02234b`; endpoints + P11 census `1383848`;
   FE view + HTTP smoke `250cdd8` (which found the psycopg-less images).
9. **Adversarial review workflow** (5 lenses, 27 findings) → fold `a487a07` (attribution fence,
   migration 0064, uuid typing, artifact CSP, route un-shadowing, Reload, identity alarm, two vacuous
   controls); mutation G5 survived and needed a new test.
10. **Fresh-context pre-merge audit workflow** (4 lenses, 12 blocking claims, all survived) → fold
    `545d2cb` (issuer disclosure closed; false ratification claims corrected; the unscoped-run
    regression given its own message and a carry; the date axis fenced); mutation H1 survived and
    needed a new test.
11. **Merge #181 → `c4019d5`** (17th), close #182 → `88ccbed` (18th); P1 sweep clean with ledger 7
    re-verified by importing from `main`.

### Gate evidence quoted this session (P14)

- `CHECK_ALL_EXIT=0` at every commit boundary (final: 2492 passed / 593 skipped, FE 216, mypy 287).
- Full-PG `PYTEST_EXIT=0` — censuses 3054 → 3057 → 3077 → 3083 → 3085, each cross-checked against
  `passed + skipped`.
- `SMOKE_EXIT=0` on every deployed-proof run after the psycopg fix.
- CI `conclusion=success` on `250cdd8`, `a487a07`, `545d2cb`, `11dac62` (8/8 check-runs).
- Migration `0064` on a simulated live DB: `0 → 2` codes, `8` grants, idempotent.
