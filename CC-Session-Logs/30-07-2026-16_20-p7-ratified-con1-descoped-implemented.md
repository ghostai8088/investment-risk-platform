# Session Log: 30-07-2026 16:20 - P7 Ratified, CON-1 Descoped and Implemented

## Quick Reference (for AI scanning)

**Confidence keywords:** P7, lessons-as-acts, pre-flight-manifests, seventh-ledger, error-trend-audit,
mechanization-stops-an-enumeration, escape-rate-flat, detection-intensity-confound, build-assessment,
inward-facing, PERF-0, DATA-1, DEP-1, RPT-1, document-surface-shrink, roadmap-313K-to-164K,
build_sequence-status-retired, CON-1, descope, share_invested_long, denominator_basis,
IRC-851(b)(3)(A)(i), OQ-CON-1-15-reversal, _METRIC_MAP-deferred-to-LIM-2, three-code-mint,
concentration.issuer.view, auditor_3l-excluded, row_kind, bucket_code, dunder-sentinels,
partial-unique-indexes, sqlite_where, ENT-069, migration-0057, P4-staged-rows-destructive-proof,
code-first-re-resolve, leaf-override-reddens-pin, OQ-CON-1-27, OQ-CON-1-28, fail-closed-ancestor-walk,
demo-stage-19, DEMO-CONCENTRATION, counts-26-41-136, census-layout-sensitivity-reproduces-on-main,
citation-lane, ESMA-para-87-AuM-qualifier, UCITS-its-assets, four-verifier-passes

**Projects:** investment-risk-platform (Wave 14: REF-1 closed → CON-1 → PERF-0 → LIM-2 → CAL-1 → DATA-1 → LQ-1)

**Outcome:** Answered "why more errors?" with a measured 4-lane audit (escape rate FLAT; finding counts
track verifier intensity), ratified P7 + four assessment-driven roadmap changes, then took CON-1 from
twice-refuted planning through descope → four verifier passes → user ratification → a complete
implementation (12 commits, 63 files, +7393/−1492) with both closing gates still running at session end.

---

## Decisions Made

- **P7 ratified (standing rule, `claude_operating_instructions.md`):** every lesson lands as an ACT —
  a mechanical gate (preferring **exact census > coverage floor > enumerating matcher**), procedural
  prose bound to a trigger moment, or an explicit recurrence acceptance. Declarative "remember that X"
  is no longer a valid countermeasure form.
- **Pre-flight manifests (P7 companion):** per-change-class pin/fence enumeration consulted BEFORE
  drafting (migration / governed family / permission / entity / demo stage / dependency). Converts the
  `dbce327` class from CI-discovery into a lookup. **It worked on first use** — 21 head pins + the
  next-free glob were relayed in the same commit as migration 0057.
- **P1 gains a SEVENTH ledger:** every "shipped/enforced/delivered" claim in a record is verified
  against the MERGED diff and cited to its artifact before close (the REF-1 five-false-claims class).
- **Both-tier verification before EVERY push** (the `dbce327` lesson made standing).
- **Roadmap Part 4 rule 6a strengthened:** citations enter records ONLY as verbatim quotes with
  locators, plus an independent citation-verification lane reading only the sources.
- **Wave 14 re-sequenced** (from the build assessment): CON-1 descoped; **PERF-0** (measured scale
  probe) inserted at 1.5; **DATA-1** (first genuinely-sourced external dataset) at 3.5; **DEP-1**
  (deployment floor) + **RPT-1** (first reproducible risk report) committed as Wave-15 openers.
- **Document surface shrunk:** roadmap 313KB → 164KB (Part 5 pre-2026-07-27 rows archived, done-set
  invariance verified first); `current_state.md` 1,331 → ~110 lines; `build_sequence.md`'s decayed
  Status column RETIRED to a pointer (it said "Not started" for capabilities shipped waves ago);
  `00_ai_operating_model/` marked HISTORICAL.
- **CON-1 DESCOPED (the stopping rule's first application):** after TWO consecutive refuted denominator
  foundations, ship ONE share — `share_invested_long` (bucket long ÷ Σ long) — with a
  `denominator_basis` controlled vocabulary, explicitly NOT any regulatory ratio.
- **OQ-CON-1-15 REVERSED:** `_METRIC_MAP` registration DEFERRED to LIM-2. In-slice registration would
  have opened a one-slice window where a UCITS-shaped threshold could bind an unbased share — the v2
  false-breach harm relocated a third time. With no registration, shipped `_validate_config` refuses
  every concentration limit by existing code. REQ-CRD-003 advances to "produced, bindable at LIM-2",
  deliberately not Done.
- **Three-code R-07 mint split by what the read exposes:** `concentration.run` /
  `concentration.view` (auditor INCLUDED, payload structurally free of issuer identity) /
  `concentration.issuer.view` (auditor EXCLUDED — consistent with three prior issuer-identity refusals).
- **Decision point 8: the minimal FE read KEPT in-slice** (split order fixed: country dimension first,
  FE second, never the correctness rails).

## Key Learnings

- **Mechanization stops an ENUMERATION, not a class.** The closure-stamp gate recurred FIVE times
  *after* being mechanized, each at its matcher's enumeration boundary; the eslint fences were bypassed
  on three unenumerated axes; the fail-closed npm-audit gate was found fail-OPEN. Only exact
  set-equality censuses have zero recorded recurrences. This refuted my own going-in hypothesis.
- **Prose splits by type.** Procedural prose ("before X, run Y") has zero recorded recurrences;
  declarative prose ("remember that X is true") recurs every time. 31 of 53 memory lessons were
  declarative-prose-only, and every top recurring class was in that set.
- **The error-volume rise is measurement, not decline.** Escape rate roughly FLAT across the project;
  the same Wave-14 document produced 24 findings under one instrument and 52 under another hours later.
  Widening one gate retroactively exposed five records defective for many waves.
- **Reference literals earn their keep immediately.** The kernel's first test run computed HHI as
  0.356058 (quantize-then-square); the ratified convention is 0.356057 (unrounded ratios, then
  quantize). A test written from the implementation would have enshrined the wrong convention.
- **A verifier catching MY measurement is the highest-value finding.** The v5 targeted pass found the
  holder sets I had "measured from source" used `ops` where the bootstrap has `data_steward`, and
  claimed seven roles where there are six — a regex extraction presented as a measurement.
- **A ratified guard can be unreachable.** Repeatedly: OQ-CON-1-24's mixed-VERSION refusal needed
  `scheme_family` that lived nowhere pinned; REF-1's node fence had no writer; the by-id
  `_reresolve_content` idiom would have made the leaf-override control unable to fire.
- **Ledger sweeps find OTHER slices' omissions.** The seven-ledger sweep discovered REF-1's permission
  mint was never recorded in `entitlement_sod_model.md` at all — added as a labeled catch-up row.
- **Two DB env vars, different consumers:** `DATABASE_URL` drives alembic; `IRP_TEST_DATABASE_URL`
  gates the PG suites. Using the wrong one silently skips rather than fails.

## Solutions & Fixes

- **P4 staged-rows destructive proof (the SCH-2 zero-rows lesson, executed):** staged 3 real rows →
  `alembic downgrade -1` → `to_regclass` NULL (table gone) → `upgrade head` → 0 rows + trigger restored.
- **The pre-flight relay in one commit:** `grep -rln "0056"` over the test tree found 21 head-pin files;
  `test_synthetic.py`'s next-free glob relayed 0057→0058 with its note.
- **Code-first `_reresolve_content` branch** (the platform's first): re-runs `resolve_node` on the
  pinned `(scheme_id, node_code)` with tenant precedence then re-walks ancestors, so a LEAF override
  reddens the pin — proven by a PG control that a by-id re-read would have passed green.
- **Both-dialect partial indexes:** `postgresql_where` AND `sqlite_where` (the shipped convention the
  v4 record wrongly called "SQLite is structurally blind").
- **Three fence amendments, each with rationale in place:** the snapshot import fence, the
  `_EXPOSURE_IMPORTERS` set-equality whitelist, and the GS2 run/metric censuses (18→19, 38→39).
- **Isolation-pair diagnosis via `git worktree`:** ran the same suite subset on my tree and on untouched
  `main` against fresh schemas; identical failure proved the census defect pre-existing.
- **zsh word-splitting trap:** unquoted `$FILES` passes as ONE argument; `echo "$FILES" | xargs pytest`
  is the fix.

## Files Modified

**Governance batch (merged, PR #150 = `d598ba4`):**
- `docs/project_memory/claude_operating_instructions.md`: P7 + pre-flight manifests + seventh ledger +
  both-tier push rule + the citation-lane pointer.
- `10_delivery_backlog/delivery_roadmap.md`: Part 2.18 re-sequence, Part 3 Wave-15 openers, rule 6a,
  Part 5 split + three amendment rows. `delivery_roadmap_amendment_archive.md`: 63 archived rows.
- `docs/project_memory/current_state.md` (capped) + `current_state_archive.md` (1,292 lines).
- `10_delivery_backlog/build_sequence.md`: Status column retired. `00_ai_operating_model/README.md`: new.

**CON-1 planning (`c192979` → `b89601e`):** `10_delivery_backlog/con_1_decision_record.md` v4 → v5 → v6
→ RATIFIED; `ref_1_decision_record.md` scope amendment; `wave_14_planning.md` + roadmap in-place amendments.

**CON-1 implementation (12 commits `668e04f` → `91a4b2e`; 63 files, +7393/−1492):**
- `packages/shared-python/src/irp_shared/concentration/`: `models.py` (ENT-069), `kernel.py`,
  `service.py` (binder + readers), `bootstrap.py` (registrar), `events.py`.
- `migrations/versions/0057_concentration_result.py` (+ 21 head-pin relays, glob relay).
- `packages/shared-python/src/irp_shared/snapshot/models.py` + `service.py`: purpose, 3 component kinds,
  4 pinned shapes, code-first branch, except-tuple.
- `packages/shared-python/src/irp_shared/classification/service.py`: fail-closed ancestor walk,
  `asserted_ancestor_code` guard, dunder-code refusal.
- `packages/shared-python/src/irp_shared/entitlement/bootstrap.py`: the three-code mint.
- `apps/backend/src/irp_backend/api/concentration.py` (7 routes) + `main.py`.
- `apps/frontend/src/api/types.ts`, `views/RunsList.tsx`, regenerated `api-types.d.ts`/`openapi.json`.
- `packages/shared-python/src/irp_shared/demo/con1_stage19.py` + `__init__.py`.
- Tests: `test_concentration_kernel.py`, `test_concentration_pg.py`,
  `test_demo_stage9zzzzzzzzzz_con1_pg.py`, `apps/backend/tests/test_concentration_endpoint.py`,
  plus fence/census amendments in `test_snapshot.py`, `test_sharpe.py`, `test_scheduler.py`,
  `test_classification.py`, `test_demo_stage9zzzzzzzzz_ref1_pg.py`.
- Ledgers: `canonical_data_model_standard.md`, `audit_event_taxonomy.md`,
  `control_matrix_skeleton.md`, `requirements_backbone.md`, `requirements_traceability_matrix.md`,
  `entitlement_sod_model.md`, `.github/workflows/ci.yml`.

## Setup & Config

- **PG container:** single reused `irp_pg_local` (`postgres:16`). Reset recipe (must include the GRANT):
  `DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT USAGE ON SCHEMA public TO PUBLIC; GRANT ALL ON SCHEMA public TO irp;`
  then `DATABASE_URL=... alembic upgrade head`. **Reset BEFORE each full-PG run.**
- **Env vars:** `DATABASE_URL` → alembic; `IRP_TEST_DATABASE_URL` → PG suites (absent ⇒ silent skip).
- **testpaths:** `apps/backend/tests`, `apps/worker/tests`, `packages/shared-python/tests` — all three.
- **Log capture:** redirect to a plain file + `echo "PYTEST_EXIT=$?"` (pipes mask the exit code).
- **Worktree isolation:** `git worktree add <scratch>/main-check main` with
  `PYTHONPATH=<worktree>/packages/shared-python/src`; remove with `--force` when done.

## Pending Tasks

1. **Two gates running at session end:** the fresh-schema full-PG battery over all three testpaths
   (`fullpg_run.log`) and the three-lane adversarial review workflow (`wf_ab30eefe-bc2`: quant,
   security, record-vs-diff).
2. **Then:** fold surviving findings → push `con-1-descope-planning` → CI-to-green → hand the PR link.
3. **After merge:** the P1 verify-on-main sweep (runs AFTER the last merge), then the CON-1 closeout
   stamp, then **PERF-0** (the measured scale probe).
4. **Recorded for OPS hygiene (not CON-1):** the stage-14 ops role census encodes its CI execution
   layout; it fails on a single-database local battery on untouched `main`.
5. **Named CON-1 obligation to LIM-2:** the `limit_definition` basis column + basis-match refusal +
   the refusal-after-success staleness state in `limit_health`.

## Errors & Workarounds

- **The stage-14 ops role census (13 vs 2):** reproduced identically on untouched `main` via an
  isolation pair → pre-existing environment-layout sensitivity, recorded in the CON-1 record's
  execution addendum rather than papered over.
- **Import-fence red chained past (process slip, disclosed):** commit 5 was made before its pytest
  result was read; fixed in `64597df` with the amendment rationale. Branch was never pushed red.
- **HHI convention divergence** (0.356058 vs ratified 0.356057) — kernel corrected to compute from
  unrounded ratios.
- **Fixture column guesses:** `Model(status=...)`, `ModelVersion(created_at=...)` don't exist; and
  `uq_issuer_tenant_legal_entity` forbids two issuers on one legal entity. Fixed by reading the ORM.
- **mypy narrows:** a reused loop variable (`str | None` vs `str`) and `version.status` into a
  non-optional DTO field.
- **Constraint-name double-prefixing:** the NAMING_CONVENTION prepends `ck_<table>_`, so ORM CHECK
  names must be SUFFIXES only (the 0055 note).
- **FastAPI route introspection:** this version wraps included routers as `_IncludedRouter`, so
  `app.routes` yields no `APIRoute`; the census introspects the router's own routes instead.

## Key Exchanges

- **"It appears like you are generating and subsequently catching more and more errors. Is there
  something we can update in the instructions that would fix that?"** → the 4-lane audit; my
  hypothesis was refuted by the adversarial lane; P7 proposed and ratified.
- **"Improve this prompt and then run it"** (the build assessment) → improved to separate summary from
  assessment, force document-grounding, add a measured shipped-state baseline and a divergences ask;
  produced the "coherent but increasingly inward-facing" verdict and four roadmap changes.
- **"Proceed"** at the CON-1 gate → all eight briefed decision points ratified as recommended.

## Custom Notes

None

---

## Quick Resume Context

CON-1 (concentration, the 23rd governed number) is fully implemented on branch
`con-1-descope-planning` — 12 commits from `b89601e` (ratification) through `91a4b2e`, with
`make check` green (2244 passed) and the first live demo battery at 143/144. Two closing gates were
still running when the session ended: the fresh-schema full-PG battery over all three testpaths and
the three-lane adversarial review workflow (`wf_ab30eefe-bc2`). Next: read both results, fold
surviving findings, push, watch CI to green, and hand the user the PR compare link — then the P1
verify-on-main sweep after merge, the closeout stamp, and PERF-0.

---

## Raw Session Log

> **Fidelity note.** This session ran ~120 turns with several multi-hundred-KB subagent payloads
> (four workflow runs plus a targeted agent). A literal transcript is impractical and would be
> unusable; what follows is a faithful phase-by-phase record with every decision, finding, command
> class and correction preserved. Raw payloads are retained at
> `/private/tmp/claude-501/-Users-andrewcox-Projects-investment-risk-platform-investment-risk-platform/70b746c9-.../tasks/`
> as `wsyc6crzu.output` (error-trend audit), `w7nvh66re.output` (build assessment),
> `wxpl2onwq.output` (CON-1 v4 verifier pass), `a9cc3a0d29e432669.output` (v5 targeted pass), and
> `fullpg_run.log` / `demo_pg_run1.log` / `iso3.log` (battery + isolation logs).

### Phase 1 — The error-trend question

User asked whether instructions could be updated to address "generating and subsequently catching more
and more errors." I proposed testing a specific hypothesis — that classes stop recurring once the
countermeasure is mechanical and keep recurring while it is prose — and ran a 4-lane workflow: session-log
error-class inventory, standing-rules enforcement audit, memory-lesson mechanization sweep, and an
adversarial lane instructed to refute the thesis.

**Result: thesis REFUTED.** The closure-stamp class recurred five times after mechanization; fences were
bypassed on three unenumerated axes; a fail-closed audit gate was fail-open. The refined findings:
mechanization stops an enumeration, not a class (census > floor > matcher); prose splits procedural
(zero recurrences) vs declarative (recurs); the finding-count rise is dominated by detection intensity
(the same document: 24 findings vs 52 hours later) with claim density secondary; escape rate flat.
Two named gaps: no rule required converting a lesson into an enforceable form, and no pre-flight
enumeration existed.

I proposed P7 + pre-flight manifests + delivery-claims-cite-artifact, and flagged that late findings are
increasingly interactions BETWEEN shipped invariants — inherent to 25 governed numbers and 7 hybrid tables.

### Phase 2 — The build assessment

User: "Improve this prompt and then run it." I restructured the ask into five parts (goal / plan /
measured shipped state / assessment / divergences), forcing document-grounding and a measured baseline,
then ran four lanes.

Findings: the ratified goal is the differentiation thesis (unified public+private risk, best-in-class
math, AI-ready governance) for mid-sized US asset managers; 13 waves closed; 22 governed number families
measured on main; **coherent but increasingly inward-facing** — no real market data ever ingested (a
3-instrument synthetic book), no deployment story (CI only), multi-tenancy proven by tests but never
operated, reporting 100% Draft, and `build_sequence.md` actively misinforming.

### Phase 3 — Ratification and execution of both packages

User: "Okay, please make these updates as well as all the proposed P7 proposed changes."

Executed as a single editing thread (shared-tree rule) on the unmerged branch: P7 + companions into the
operating instructions; the CON-1 descope into the record; the roadmap re-sequence (PERF-0, DATA-1,
DEP-1, RPT-1) + rule 6a + Part 5 archive split (done-set invariance verified BEFORE splitting: 55 ids,
floor 38); build_sequence Status retired; current_state capped; `00_ai_operating_model` bannered.
Five commits, `make check` green (2224 passed), CI green all six, merged as PR #150.

### Phase 4 — CON-1 v4: folding 47 findings into the descoped form

Recovered the second-pass ledger from the retained payload. Folded all 47: the exact share formula and
definition-time limit refusal; HHI excluding residuals with the identity restated; UNCLASSIFIABLE split
from UNCLASSIFIED; the leaf/ancestor drift mechanics corrected (v3 had them inverted); the ten-name
metric census with measured widths; the OQ-23 grain redesign (row_kind + NOT NULL bucket_code + partial
indexes); OQ-24 repaired; OQ-25 re-decided as three codes; new OQ-26 (basis discipline), OQ-27 (REF-1's
unbuilt guard paid here), OQ-28 (fail-closed ancestor walk); the reachable demo book; counts pinned;
citations restated with locators. Committed `c192979`, CI green.

### Phase 5 — The v4 verifier pass (four lanes, first citation-lane execution)

Citation lane: **zero BLOCKING/HIGH** — ESMA ¶87's "under management of the AIF" qualifier verified
verbatim, IRC §851(b)(3) structure confirmed on all three claims, CESR box numbers corrected. Its MEDs:
a non-verbatim IRC quote and UCITS Art. 52 saying "its assets", not NAV. Registers lane: CLEAN 12/12.
Design lane: 1 HIGH (the "SQLite is blind" claim refuted by the repo's own `sqlite_where` convention) +
4 MED. Descope lane: 1 BLOCKING — in-slice `_METRIC_MAP` registration would open an unbased-limit
window — plus the entirely-unfolded subtree scope finding and the unpinned LONG predicate.

Folded to v5 (`573d07d`): the OQ-15 reversal, the LONG predicate pinned, subtree scope ratified,
both-dialect indexes, dunder sentinels, per-dimension residual predicates, refusal timings split,
code-first closure re-resolve, hybrid resolvers, enumerated holder sets, the short-bearing fixture.

### Phase 6 — The v5 targeted pass and v6

A single refuter over ONLY the v5 diff returned **NOT RATIFIABLE**: 1 BLOCKING — my enumerated holder
sets used `ops` where the bootstrap has `data_steward`, and claimed seven roles where there are six —
plus four HIGHs (the demo issuer-dimension literals contradicting the new predicates; MULTIASSET's
refusal being the 0/0 gap not the coverage floor; Part 3's binder line still listing post-build refusals
as pre-build; the `portfolio_id = scope_portfolio_id` pin not total). Verified-clean: the fixture
arithmetic exact to 6dp, the fail-closed `_validate_config` premise quoted, the index convention.

All folded to v6 (`aca97a1`), CI green. Gate briefing delivered with eight decision points.

### Phase 7 — Ratification and implementation

User: "proceed." Stamped RATIFIED, executed the Part 6b in-place amendments (`b89601e`), then built
across 12 commits: ENT-069 + kernel + 15 tests; migration 0057 with the pre-flight relay and the P4
staged-rows destructive proof; the snapshot legs; events + registrar; the binder; the REF-1 hardenings
with executed controls; the three-code mint; reads + 7-route API + minimal FE; demo stage 19 + PG
suites (first live battery 143/144, the single failure reproduced on main via isolation pair); CI steps
+ the seven-ledger sweep (which found REF-1's own uncatalogued mint); and the gate fixes.

`make check` green (2244 passed, mypy clean, docs clean). Both closing gates — the fresh-schema full-PG
battery and the three-lane adversarial review — were launched and still running when the user invoked
`/compress`.
