# API-1b Decision Record — the flagship VaR / active-risk entity reads (Wave-10 slice 1)

| | |
|---|---|
| **Status** | **RATIFIED by the user 2026-07-21 (OQ-API-1b-1…5); the pre-ratification verifier pass RAN (Part 5 — the crux + all correctness claims HELD; 2 COMPLICATED findings folded, no redesign). Implementation follows.** Forks decided: **OQ-API-1b-1 = A "honest-NULL"** (the snapshot-consume NULL-origin class disclosed as unresolvable; the gap-closing FactorExposureResult column is a recorded v2 — keeps the slice to ONE additive column); **OQ-API-1b-2/3/4/5 = approved as recommended** (VaR read = latest-run + optional `metric_type`; NO new demo stage, counts UNCHANGED; `pip-audit` hard fail-on-any + commented allowlist; the closure-check filename-keyed row-anchored mechanic). Wave-10 slice 1 (roadmap Part 2.13), the named fast-follow OD-API-1-H, ratified at the Wave-9 close (OQ-W9C-3 fork A "finish the surface first"). Pays the ONE read API-1 deferred: **"latest VaR / active-risk for portfolio P"** — the single most-wanted UI/agent read. API-1's verifier REFUTED the *read-only* resolution (subtree-scoped runs; no root portfolio recorded); API-1b resolves it at the **write** boundary — one additive `calculation_run.scope_portfolio_id` column stamped at run creation. Carries the two ratified Wave-10 CI riders (OQ-W9C-4 `pip-audit`; OQ-W9C-5 closure-discipline docs-check). |
| **Premise** | `VarResult` and `ActiveRiskResult` carry **NO `portfolio_id`** (`risk/models.py:196`, `:279`) — the portfolio is implicit via the `exposure_run_id`/`factor_exposure_run_id` provenance FKs, and those upstream runs are **subtree-scoped** (they span a portfolio's descendants). So "latest VaR for P" cannot be resolved from the result rows (unlike the Class-A families, whose result rows carry their own `portfolio_id`). The verifier F1-HIGH established that neither `calculation_run` nor `dataset_snapshot` records a run's ROOT portfolio — read-only resolution is unsound. **But at run-creation time the root IS in hand:** `run_exposure` receives `portfolio_id` as a first-class argument (`exposure/service.py:213`) — the ROOT of the subtree it aggregates — and every downstream binder re-resolves its upstream run object. API-1b records that root once, at the write boundary, and the read becomes a trivial equality filter. |

## Part 1 — Grounding (file:line; the API-1b write-boundary census 2026-07-21)

**The single run-creation choke point.** Every governed run is created through `create_run`
(`calc/service.py:13-53`) via the shared scaffold `execute_governed_run` (`calc/scaffold.py:58-93`,
the `create_run` call at `:84`). All five target run types route through it (exposure / factor /
var / var_hs / active_risk). `create_run` currently takes no portfolio/scope parameter (params end
at `environment_id`, `:24`) — `scope_portfolio_id` threads through this one function + the scaffold,
and each binder passes what it holds.

**What each binder holds at creation (the propagation chain).** These runs ARE subtree-scoped and
their ROOT is exactly `run_exposure`'s `portfolio_id`:

| Binder (entry) | run_type | Root portfolio at creation | How 0046 stamps it |
|---|---|---|---|
| `run_exposure` (`exposure/service.py:206`) | `EXPOSURE_AGGREGATE` | **`portfolio_id` — a direct arg (`:213`)**, the subtree ROOT (build path). NULL on the `snapshot_id` consume path. | Pass `portfolio_id` straight to `create_run`. |
| `run_factor_exposure` (`risk/factor_service.py:524`) | `FACTOR_EXPOSURE` | Re-resolves the upstream `EXPOSURE_AGGREGATE` run object (`resolve_exposure_run`, `:596`) — build path only. | Copy `exposure_run.scope_portfolio_id` forward. |
| `run_var` (`risk/var_service.py:623`) | `VAR` (parametric + total) | Re-resolves the pinned factor-exposure run (`:800`) in BOTH paths. | Copy the pinned run's `scope_portfolio_id`. |
| `run_var_historical` (`risk/var_hs_service.py:316`) | `VAR` (shares `RUN_TYPE_VAR`; `metric_type` distinguishes) | Re-resolves the pinned factor-exposure run (`:401`) in BOTH paths. | Copy the pinned run's `scope_portfolio_id`. |
| `run_active_risk` (`risk/active_risk_service.py:478`) | `ACTIVE_RISK` | Re-resolves the pinned factor-exposure run (`:594`) in BOTH paths; also holds `benchmark_id` directly (`:488`). | Copy the pinned run's `scope_portfolio_id`. |

**The NULL-origin class (to disclose, not paper over) — verifier-corrected CLAIM 3.** A run carries
a NULL scope whenever the ROOT is not derivable at creation. There are **two** such origins, and they
are the SAME class — *any snapshot-consume entry point*: (1) `run_exposure(snapshot_id=…)` — the
consume path takes no `portfolio_id` (`exposure/service.py`; API-reachable at `api/exposure.py:107`,
passed at `:188`), so the exposure run itself is NULL-scoped, and a downstream factor-BUILD → var-BUILD
chain copies that NULL end-to-end; (2) `run_factor_exposure(snapshot_id=…)` — its consume path does
NOT re-resolve an upstream exposure run and `FactorExposureResult` has no `exposure_run_id` column, so
it stamps NULL. In BOTH, the copy-forward faithfully **propagates** the NULL (it is not a broken
resolve — the verifier confirmed the resolution itself is sound). The **fully build-in-request** chain
(the demo, the UI, and the default API flow — the HTTP POST bodies for var/active-risk take
`exposure_run_id`/`covariance_run_id`/`benchmark_id`, `api/risk.py:1565/1794/1962`) always stamps a
real root; only a chain that consumes a hand-fed snapshot at exposure OR factor yields NULL. Honest-
NULL is tier-agnostic — a NULL is unresolvable regardless of which tier introduced it. See OQ-API-1b-1.

**The read side needs no new machinery.** `list_governed_results` (`calc/reads.py:35`) already
`.join(CalculationRun …)` (`:59`) and applies `filters` as arbitrary `column == str(value)` pairs
(`:67`). A Class-C read passes `(CalculationRun.scope_portfolio_id, portfolio_id)` with
`run_type=RUN_TYPE_VAR` / `RUN_TYPE_ACTIVE_RISK`, then `latest_run_rows` (`:81`) — **zero helper
change.** `ActiveRiskResult.benchmark_id` is a native NOT-NULL indexed column (`risk/models.py:318`),
so its filter is real and index-backed. All VaR flavors share `run_type="VAR"`, distinguished by
`metric_type`.

**Migration precedent.** Head = `0045_pacing_projection`; next = `0046`. The exact shape is
`0018`'s `environment_id` and `0027`'s `failure_reason` additive nullable columns on
`calculation_run` — **no RLS change, no grant re-issue** (PG column privileges inherit table-level
grants; `calculation_run` is under tenant-isolation RLS from `0001` but adding a column touches
neither the policy nor the `irp_ops` audit-only grants), no trigger. `calculation_run` is NOT in
`APPEND_ONLY_TABLES` (it is status-mutable: `update_run_status` mutates `status`/`completed_at`/
`failure_reason` in place — `calc/service.py:74`); `environment_id` is itself stamped-at-creation-
never-mutated, exactly `scope_portfolio_id`'s shape. Downgrade = `drop_column` one-liner; no
dedicated non-superuser downgrade test needed (additive column, no DML, no zero-row trap — the `0018`/
`0027` precedent). Add `ix_calculation_run_scope_portfolio_id` (37 chars, within the 63 limit) for
the read filter.

## Part 2 — Design decisions

### OD-API-1b-A — The scope column (additive, write-boundary, not a security boundary)
`calculation_run.scope_portfolio_id` — `GUID`, **nullable**, the ROOT portfolio a run was scoped to,
stamped at creation and never mutated (the `environment_id` precedent). It is a **within-tenant scope
label**, NOT a security boundary — tenant isolation stays the RLS `tenant_id` policy; a NULL means
"root not recorded" (honestly unresolvable), never "all portfolios." Migration `0046` adds the column
+ `ix_calculation_run_scope_portfolio_id`; the in-file `_IDENTIFIERS` assert list mirrors `0045`.

### OD-API-1b-B — Stamp at the choke point + copy-forward the chain
`create_run` (`calc/service.py`) + `execute_governed_run` (`calc/scaffold.py`) gain a
`scope_portfolio_id: str | None = None` parameter. Each binder supplies it:
- `run_exposure` → its own `portfolio_id` arg (the ROOT; NULL on the snapshot-consume path).
- `run_factor_exposure` → `exposure_run.scope_portfolio_id` from the resolved upstream run (build
  path; NULL on the snapshot-consume path — the gap, OQ-API-1b-1).
- `run_var` / `run_var_historical` / `run_active_risk` → the pinned factor-exposure run's
  `scope_portfolio_id`, copied forward (both paths — they always re-resolve the pinned run).

**Reproducibility (TR-09) is untouched:** `scope_portfolio_id` is provenance metadata *about* the
run, not an input to it; the pinned snapshot content, the result values, and the run-id reads do not
move. The stamp is deterministic from inputs already in hand.

### OD-API-1b-C — The Class-C entity reads (mirror the Class-A house pattern)
Two new read pairs in the risk family's `service.py`, each via the existing `list_governed_results` +
`latest_run_rows` (no helper change), gated `risk.view`:
- **VaR:** `list_var_results(portfolio_id, metric_type?, as_of?)` filtering
  `CalculationRun.scope_portfolio_id == P` (+ optional `metric_type`), `run_type=RUN_TYPE_VAR`;
  `latest_var_for_portfolio(...)` = the newest COMPLETED VAR run scoped to P. Silent-empty on an
  unknown/foreign/NULL-scope id. **`/latest` returns `[]` (200) on no scoped run — NOT 404**
  (review-corrected: the shipped endpoints are **list-shaped** `list[VarRowOut]`, matching the
  covariance / sensitivity / factor-exposure / var-backtest `/latest` siblings which all return `[]`;
  the "404 the pacing precedent" wording was a MIS-CITE — pacing's `/latest` returns a **single**
  `PacingRunOut`, so it must 404-on-empty, whereas a list resolver returns the empty list).
- **Active-risk:** `list_active_risk_results(portfolio_id, benchmark_id?, as_of?)` filtering
  `scope_portfolio_id == P` (+ the native `benchmark_id` filter), `run_type=RUN_TYPE_ACTIVE_RISK`;
  `latest_active_risk_for_portfolio(...)`.

New endpoints in `api/risk.py` mirroring the Class-A additions (`GET /risk/vars?portfolio_id&…&as_of`
+ `/vars/latest`; `GET /risk/active-risk?portfolio_id&benchmark_id&as_of` + `/active-risk/latest`),
gated `risk.view`; the run-id reads stay. The `/latest` route is declared BEFORE `/{id}` so it is not
shadowed (the API-1 covariance-latest lesson).

### OD-API-1b-D — Historical-NULL honesty
Runs created before `0046` (and any chain rooted in a snapshot-consume entry point — exposure OR
factor, OQ-API-1b-1) carry `scope_portfolio_id = NULL` and are **honestly unresolvable** by the new read — they do not appear in
"latest for P", and this is disclosed, not back-fabricated (the HG-1 staleness / desmoothing
estimated-α honesty precedent). No data migration back-fills historical runs. In CI every demo run is
created fresh on an empty DB (`alembic upgrade head` per job), so the demo renders non-NULL; only a
persistent/living tenant carries legacy NULLs, and re-seeding stamps them.

### OD-API-1b-E — The two ratified CI riders (OQ-W9C-4/5)
- **`pip-audit` gate** (OQ-W9C-4): a hard CI step mirroring `npm audit --omit=dev` (`ci.yml:44`),
  added to the `backend` job AFTER the editable installs. **It audits the INSTALLED ENVIRONMENT (bare
  `pip-audit`), NOT `-r requirements-dev.txt`** (review finding A1 corrected the initial `-r` target):
  a package's runtime pins declared only in its `pyproject.toml` — e.g. `python-multipart` (the
  `/ingest/upload` form-parse surface) — are NOT in `requirements-dev.txt` and would slip a `-r` audit;
  auditing the installed env covers everything actually shipped (the three first-party editable
  packages skip cleanly, not on PyPI). Strictness + any disclosed-advisory allowlist = OQ-API-1b-4.
- **Closure-discipline docs-check** (OQ-W9C-5): teeth for the 5th-consecutive missing-stamp class.
  **A naive grep is wrong, and a naive roadmap cross-reference is ALSO wrong** — the verifier (CLAIM 6)
  proved "API-1b" appears as *prose* inside 2 `✅ **DONE**` roadmap rows (the API-1 and FE-3 rows), so
  a "does any DONE line mention the slice-id?" check would falsely fail CI on this very in-flight DRAFT.
  The mechanic must be **filename-keyed and row-anchored**: (1) derive the slice-id from the record's
  filename (`(.+)_decision_record\.md` → normalize case + `_`↔`-`, e.g. `api_1b` → `API-1B`); (2) build
  `{slice_id: done}` by scanning each roadmap line for its **leading bold title token** as the slice-id
  AND `✅ **DONE**` **in that same line** (never a whole-file substring); (3) fail iff a record's
  `| **Status** |` cell contains "DRAFT for ratification" AND its filename-slice maps `done=True`. This
  kills the demonstrated false positive while still catching the exact API-1-class miss (a shipped
  slice's record left DRAFT). Extends `scripts/check_docs.py` (`ci.yml` `docs-check` job, `:469`),
  stdlib-only. Ratify the mechanic at OQ-API-1b-5.

### OD-API-1b-F — Scope fence
API-1b is **the one migration (0046, additive column + index) + the choke-point + 5-binder scope
stamp + the Class-C reads/endpoints + the demo-test read assertions + the two CI riders.** NO new
governed number, model code, permission, role, ENT, or snapshot purpose; `audit/service.py` FROZEN;
the closed 5-table hybrid set untouched; RLS/write posture unchanged (the column is a within-tenant
label); the run-id reads + TR-09 reproducibility untouched; NO FE change (FE-3b/a later FE slice
consumes these). Demo counts UNCHANGED (17/20/35/101 — runs-only reads over existing runs; see
OQ-API-1b-3).

## Part 3 — Open decisions (OQ-API-1b-1…5) — ALL RATIFIED 2026-07-21 (OQ-1 = A honest-NULL; OQ-2/3/4/5 = as recommended)

- **OQ-API-1b-1 — The snapshot-consume NULL-origin class (verifier-corrected).** A NULL scope arises
  from **any snapshot-consume entry point — exposure OR factor** (not just factor; the verifier proved
  `run_exposure(snapshot_id=…)` is API-reachable and yields a NULL-scoped root that cascades). **(A,
  recommended)** honest-NULL for the whole class — disclose the snapshot-consume chains as
  unresolvable (the fully build-in-request chain — demo/UI/default-API — always stamps a real root);
  keep the slice to one column. **(B)** close the gap by adding an `exposure_run_id` provenance column
  to `FactorExposureResult` and/or resolving the root from the snapshot's pinned content — more
  complete but widens the migration and the binder touch well beyond "one additive column."
  Recommendation **A**; B is a recorded v2. (No code change either way — the read is a
  `scope_portfolio_id == P` equality filter; NULL rows simply do not match.)
- **OQ-API-1b-2 — The VaR read's metric grain.** `var_result` shares `run_type="VAR"` across
  `VAR_PARAMETRIC` / `VAR_PARAMETRIC_TOTAL` / `VAR_HISTORICAL` / the ES metric_types. "Latest VaR for
  P" = the newest COMPLETED VAR run scoped to P, returning its row(s); an **optional `metric_type`
  filter** lets a caller ask for a specific flavor. Confirm this shape (vs. a separate endpoint per
  flavor — rejected: the run IS the object, metric_type is a row filter).
- **OQ-API-1b-3 — Demo: no new stage.** **(A, recommended)** NO new demo stage — the existing stages
  already create VaR runs (multiple) and one ACTIVE_RISK run (`stage10_api1.py:474`), all downstream
  of a `run_exposure(portfolio_id=…)`, so a fresh re-seed stamps them; API-1b only ADDS
  `latest_var(…)` / `latest_active_risk(…, portfolio_id=demo_global)` read assertions to
  `test_demo_stage9z_api1_reads_pg.py` (mirroring `:159`). **Counts UNCHANGED** (no new runs;
  `ACTIVE_RISK==1` pin holds). **(B)** add a stage exercising more books. Recommendation **A**.
- **OQ-API-1b-4 — `pip-audit` strictness.** Fail on any advisory (recommended — mirrors the npm
  hard-gate posture), with an explicit, commented allowlist ONLY for a disclosed-and-accepted advisory
  (as the FE side does for `@redocly`); vs. a softer `--ignore-vuln`-heavy start. Confirm the level
  and whether the current `pyjwt`/`cryptography`/`fastapi`/`uvicorn`/`sqlalchemy` pins are clean at
  ratification (the plan will run `pip-audit` once and record the result).
- **OQ-API-1b-5 — The closure-check rule.** Ratify the **filename-keyed, row-anchored** mechanic
  (OD-API-1b-E, verifier-specified): fail iff a `*_decision_record.md` Status cell says "DRAFT for
  ratification" AND its filename-slice is `✅ **DONE**` on its own roadmap row. The verifier proved a
  looser roadmap cross-reference false-fails on this DRAFT (the slice-id appears in other rows' prose);
  a blanket "any DRAFT Status cell" rule false-fails during the legitimate planning→impl window.
  Recommendation: the filename-keyed row-anchored rule (no false positive on an in-flight planning
  DRAFT — including THIS one; catches exactly the stamp-after-ship miss).

## Part 4 — Invariants & gates (re-affirmed)

`make check` + full-PG (fresh-schema + the new `0046` in the CI order) + `alembic check` +
downgrade/upgrade smoke + `make gen-api-check` (the new endpoints re-stamp the OpenAPI → regenerate
the committed `openapi.json` + FE types, or the API-type-drift job goes red — the SSO-1 lesson) +
`make fe-check`. 4-finder adversarial review (it touches a migration + the write path). Closure-stamp
checklist (grep-for-"pending"/"candidate"; CI-run-id; **stamp THIS record CLOSED at closeout** — the
API-1 miss this very slice's OQ-W9C-5 rider exists to prevent). The pre-ratification verifier pass
(Part 5) RUNS before ratification.

## Part 5 — Verifier pass — RAN 2026-07-21 (adversarial; 4 HOLD, 2 COMPLICATED folded — NO redesign)

An adversarial verifier read the actual binder/migration/route code to REFUTE the six load-bearing
claims. Verdicts:

- **CLAIM 1 — copy-forward correctness (THE CRUX): HOLDS.** Every binder has the upstream
  `CalculationRun` **ORM row** in hand before `create_run`, in the paths the plan claims. Decisively,
  var/var_hs/active_risk resolve `resolve_factor_exposure_run(...)` (`var_service.py:800`,
  `var_hs_service.py:401`, `active_risk_service.py:594`) **OUTSIDE the build/snapshot if-else**, so it
  runs in BOTH paths, and it returns a genuine `CalculationRun` row (via `resolve_run_of_type`) — **not
  reconstructed from snapshot content**. The write-boundary resolves a real root where API-1's
  read-boundary could not. The premise is sound.
- **CLAIM 2 — TR-09 neutrality: HOLDS.** `scope_portfolio_id` is a `calculation_run` column present on
  no result row, so it reaches no `*_content()` serializer in `snapshot/serialize.py`; `create_run`/
  `execute_governed_run` compute no run-row hash; the frozen pin-key tests
  (`test_var_result_pin_key_set_is_frozen`) guard against an implementer wrongly adding it. It appears
  nowhere in the codebase today (genuinely additive).
- **CLAIM 3 — the NULL-origin count: COMPLICATED → folded.** The exposure-snapshot-consume path is a
  SECOND, API-reachable NULL-origin (not just factor). No code change (honest-NULL is tier-agnostic);
  the wording is corrected in Part 1 + OD-API-1b-D + OQ-API-1b-1 to name the whole class.
- **CLAIM 4 — migration neutrality: HOLDS.** Exact `0018`/`0027` additive-nullable precedent on
  `calculation_run`; no RLS-policy change; `irp_ops` holds no grant on the table (nothing to re-issue,
  and PG grants inherit to new columns); not in `APPEND_ONLY_TABLES` (no trigger); index name 37 chars;
  `drop_column` downgrade needs no dedicated non-superuser test.
- **CLAIM 5 — read not shadowed: HOLDS.** `/vars/{id}` (`api/risk.py:1641`) and `/active-risk/{id}`
  (`:2047`) are the only capturing routes; no existing `/vars` or `/active-risk` collection route, so
  no collision; `/latest`-before-`/{id}` is the uniform pattern across six precedents. The plan already
  commits to the ordering.
- **CLAIM 6 — closure-check soundness: COMPLICATED → folded.** "API-1b" appears in 2 `✅ **DONE**`
  roadmap rows as prose, so a loose cross-reference false-fails this DRAFT; the mechanic is pinned
  filename-keyed + row-anchored in OD-API-1b-E / OQ-API-1b-5.

**Net: the crux and every correctness claim held under attack; the two COMPLICATED findings were
precision fixes to this record's wording and the CI-check spec — no change to the column, the stamp,
or the reads.** The decision record is ready for the ratification gate.

## Part 6 — 4-finder adversarial review (RAN 2026-07-21) — ZERO HIGH; folds applied

Four cross-cutting finders over the impl diff (`origin/main..HEAD`), each Opus, on top of the
pre-ratification verifier pass: (1) write-path correctness, (2) doctrine/security, (3) read
correctness + route shadowing, (4) CI riders + test quality + record honesty. **ZERO HIGH from any
lens.** The crux held: the scope-stamp copy-forward is correct across all five binders and both input
paths, immutable-after-creation, TR-09-neutral (`scope_portfolio_id` appears in no serializer/hash —
grep-verified), and complete (no unstamped run creator). All six hard invariants re-verified; the
"scope is not a security boundary" cross-tenant probe confirmed the reads are double-bound (RLS + the
explicit tenant filter) so a foreign portfolio_id is silent-empty with no existence oracle.

**Folds applied (this review):**
- **A1 (MED, real) — the `pip-audit` gate scanned the wrong target.** `-r requirements-dev.txt` misses
  runtime pins declared only in a package's `pyproject.toml` (`python-multipart`, the `/ingest/upload`
  surface, CVE history) — a shipped runtime dep slipping the gate. Fixed to audit the **installed
  environment** (bare `pip-audit`, after the editable installs); verified clean (the 3 first-party
  editable packages skip cleanly). OD-API-1b-E reworded.
- **B2 (MED) — the closure-check's teeth were untested.** Extracted a pure `_is_unstamped_shipped`
  predicate and added a failure-path test proving it FIRES on a DONE-in-roadmap + `DRAFT`-status
  record (and does not fire on CLOSED / not-done / no-Status). Without it an inverted implementation
  would have passed the happy-path + trap tests (the ES-1 "mutation-test the assertion" lesson).
- **B1 (MED, honesty) — the closure-check's guarantee was over-claimed.** Its comment now scopes it to
  the go-forward cadence (roadmap rows leading `**SLICE — …** ✅ **DONE**`); pre-cadence rows without
  that shape or without a Status cell are out of scope, not silently guaranteed.
- **C1 (MED, = verifier CLAIM-3 sibling / finder-3 H1) — the `/latest` 404 wording was a mis-cite.**
  The shipped list-shaped `/latest` returns `[]` (matching the covariance/sensitivity/factor-exposure/
  var-backtest latest siblings); the code is right, OD-API-1b-C reworded (pacing's 404 is for a
  single-object resolver).
- **C3 (LOW) — copy-forward VALUE strengthened.** The endpoint tests now assert the result run's
  `scope_portfolio_id` EQUALS its upstream factor-exposure run's scope (not merely non-null), pinning
  the multi-hop propagation by value.
- **Advisory disclosure (finder-2 LOW-1):** the one accepted `pip-audit` allowlist entry is
  **PYSEC-2026-1845** — a DEV-ONLY `pytest==8.3.3` advisory (fix = a risky 8→9 major bump), deferred to
  its own hygiene slice; `pyjwt`/`cryptography` (the identity surface) audit CLEAN and are NOT ignored.
  `pydantic-settings` was bumped 2.14.1→2.14.2 to clear GHSA-4xgf-cpjx-pc3j (a real runtime fix the
  gate surfaced).
- **Carried (LOW, disclosed, no code change):** the collection reads (`/vars`, `/active-risk`) with no
  `portfolio_id` widen to the whole tenant unpaginated (the pre-existing Class-A/B list behavior); a
  living-tenant "missing from latest-for-P" can mean a legacy-NULL scope (OD-API-1b-D), not "no run".

**Gates after folds:** `make check` (Python) + `make fe-check` (97) + `make gen-api-check` (drift-clean)
+ full-PG affected families + `0046` downgrade/upgrade smoke + `pip-audit` (env, clean) +
`check_docs.py` (clean, teeth-tested) all green. Counts UNCHANGED (17/20/35/101).
