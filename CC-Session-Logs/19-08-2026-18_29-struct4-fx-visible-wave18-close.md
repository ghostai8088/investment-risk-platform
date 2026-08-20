# Session Log: 19-08-2026 18:29 - struct4-fx-visible-wave18-close

## Quick Reference (for AI scanning)
**Confidence keywords:** STRUCT-4, REQ-PPM-010, DP-11, DP-12, DP-14, reporting currency, FX translation, silent USD default, UndeclaredReportingCurrencyError, ReportingCurrencyConflictError, triangulation pivot, derive_pivot, serialize_legs, fx_legs, NODE_FX_BINDING_PREDICATE, v3 predicate, migration 0073, 0073_declare_root_currency, migration_0073_p17_check, three-currency book, DEMO-FX, stage 27, hand-derived oracle, 6080.000000, 432.000000, rollup translation, missing-fx honesty, RunDetail drill-in, conversion path, fx_pivot, via USD, Wave-18 close, wave_18_close_review, G4, capability coverage, zero-bindings control, seven-ledger sweep, CTRL-018, P16 citation re-take, V-008 scope stamp exploit, M-W18C-1, rename residual, clause-7 amendment, G2 lapse, backbone status cells, RTM, PR 227, PR 228, PR 229, PR 230, e8ab540, d465b6b, 7dcb3a3, d886fb8, ultracode, adversarial review, GitHub 503 outage
**Projects:** investment-risk-platform (Wave 18: STRUCT-4 + the wave close)
**Outcome:** STRUCT-4 (the last Wave-18 slice) built, adversarially reviewed (19/0 findings folded incl. a BLOCKING irreproducible-run class), merged as PR #227 = `d465b6b`; the Wave-18 close then ran (G4 first fire, ten-lane sweep 34 findings dispositioned, three owner-ratified decisions) and merged as PR #229 = `e8ab540` with stamp PR #230 = `d886fb8` — Wave 18 is CLOSED; next is the Wave-19 planning gate.

## Decisions Made
- **All STRUCT-4 design under the ratified DPs**: DP-11 resolution = explicit arg → declared chain (own `base_currency_code` else nearest declared ancestor) → REFUSE; migration 0073 backfills 'USD' onto undeclared ROOTS only (children NULL = inherit); refusal fires at RESOLUTION time, not create time.
- **Version-marker keying (the STRUCT-3 lesson applied in advance)**: all new strictness keys to a NEW binding predicate `v3:subtree-open-positions+full-node-pin+node-fx` — v1/v2 snapshots keep byte shapes and semantics exactly; pivot-stating in `fx_legs` is v3-only; FX-completeness redefinition (targets = {run base} ∪ resolved node reporting currencies) is v3-only.
- **Symmetric conflict refusal (review BLOCKING C9)**: an explicit base contradicting a DECLARED scope refuses at BUILD too, not just node-scoped consume — the asymmetric version minted v3 runs whose own CTRL-018 reproduction was refused.
- **v3-only scoping of the conflict refusal recorded as a pinned decision** (test + fx_translation_v1.md §4), with the 0073-backfill reproduction rationale.
- **Consume-path base resolution**: node's pinned chain when strict+node-scoped; else pinned top(s)-of-tree with EVERY top required to resolve identically (unknown ≠ agreement, P3-C1) — mixed/partial declarations refuse.
- **DEMO-GLOBAL declares USD** (campaign.py): the scheduler's cadence dispatch builds with no explicit base; fix at the BOOK, never a scheduler default.
- **Wave-18 close decisions, owner-ratified ("proceed")**: D1 rename-residual = ACCEPT RECURRENCE on the name census's strength with a touch-trigger (any slice touching backtest/desmoothing/pacing adds its fresh post-rename re-run); D2 the ratified clause-7 "every family executed at a non-root node" AMENDED to the delivered form (4/21 executed; representative-per-node-scope-class + exact-set declaration + stamp censuses; per-family execution rides each family's next slice); D3 the annotation-lapsed PPM-006/PPM-010 G2 adjudications stay lapsed (re-ask at next scope entry).
- **G4 wording**: the coverage table records delivered-substance-against-already-cited leaves (1.1/1.4/1.5, labels verbatim) — never gate-sense "newly covered" (all three were cited pre-wave; K29/K30).
- **G2 scope emptied at the wave boundary** with a declared written reason (slice=null); control-mint candidates (backup/DR; aggregation-contract enforcement layer) flagged for the Wave-19 planning gate, not minted unilaterally.
- **fx_translation_v1.md sits outside the CTRL-002 model-methodology census BY DESIGN** (exposure is model-less; DP-14 convention doc, not a registered model methodology).

## Key Learnings
- **A new refusal must be checked at EVERY mint site of the artifact it later judges** — the BLOCKING C9: build-path override + consume-path conflict check = irreproducible governed runs (proven by execution).
- **Declaration-without-firing recurs at the SURFACE level**: two deliverable-shaped surfaces (the API `fx_pivot` wiring, the 2-leg rollup-translation branch) never executed TRUE in any test until the review forced a book extension (SLEEVE-ALBION) + HTTP triangulated row + mutants M-S4-10/11.
- **A verifier-CONFIRMED finding can be wrong**: two sweep lanes + verifiers held full-PG 3,499 "arithmetically unreachable"; ONE execution showed the battery's own selection passes 3,500/zero skips — they had counted the whole-repo selection (+40 root-`tests/` gate tests never in the battery). Reading-lane consensus is not evidence; the battery's selection is now stated in the close record.
- **The register-status class recurs at WAVE scale**: all six delivered requirement rows still read Draft/In-Progress in backbone AND RTM (2 BLOCKING) — per-slice sweeps checked entities/controls but nobody owned requirement Status until the close.
- **Acceptance-cell ANNOTATIONS lapse G2 hashes by design** — the mechanism cannot tell annotation from amendment; plan for it (it fired mid-close and was resolved by the wave-boundary scope emptiness + decision D3).
- **alembic_version is varchar(32)**: `0073_backfill_root_reporting_currency` (37 chars) blew it — found only by EXECUTING the migration; renamed `0073_declare_root_currency`.
- **The full-PG battery catches integration seams no unit tier can**: the scheduler's cadence dispatch (no explicit base) hit the new undeclared-root refusal on DEMO-GLOBAL → 10 downstream count-pin failures from one cause.
- **GitHub API can 503 for extended periods** (both GraphQL and REST /pulls while rate_limit works): REST retry loops in the background landed PRs #227/#228/#230; `gh pr merge` (GraphQL) replaced by REST `PUT /pulls/N/merge`.
- **Confirm a merge succeeded BEFORE branch cleanup**: a 503'd merge followed by branch deletion closed PR #228 unmerged (recovered: recreate branch at the commit, PATCH state=open, REST merge).
- **A reciprocal leg's stored base/quote are the PUBLISHED row's orientation** — travel is quote→base; any renderer must invert or the path reads backwards.

## Solutions & Fixes
- **DP-11 kill**: `exposure/service.py:138` (`or DEFAULT_BASE`, build) and `:480` (consume) both dead; `resolve_reporting_currency` walk in `portfolio/portfolio.py` (bounded, cycle-safe, tenant-boundary-stopping); `_pinned_reporting_currency` mirror over pinned content; refusal classes subclass `ExposureInputError` with OWN error-map keys (the API-2 lesson).
- **DP-12**: `serialize_legs(legs, pivot=)` states `"pivot"` on each leg of a 2-leg path (v3 only; `pivot=None` reproduces legacy bytes exactly); `derive_pivot` (stated key wins; reciprocal-aware travel derivation) for shipped rows at read time.
- **Rollup translation**: `rollup_exposure` translates each node total into the pinned-declared currency from PINNED FX only (12dp/6dp HALF_UP); identity = exact pass-through; missing path = honest `missing-fx:X->Y`, never a refusal or a fabricated 1.0.
- **The three-currency book**: USD/EUR/GBP, only EUR/USD + GBP/USD published (GBP↔EUR only-triangulated); SLEEVE-UK declares USD holding GBP+EUR; hand literals worked in `08_testing_qa/struct4_fx_test_spec.md` BEFORE code ran: composite 1.25/1.08 = 1.157407407407 (12dp), foreign-node oracle 6,080.000000 USD, two-leg node translation 500 EUR × 0.864 = 432.000000 GBP.
- **K24 fix (close)**: legacy v1 consume now `resolve_portfolio`s any `scope_node_id` before stamping (pre-create refusal for nonexistent/foreign UUIDs; the reproduction adapter's replay resolves by construction); mutant M-W18C-1.
- **Local PG recipe held**: drop/create schema + GRANT ALL to irp + GRANT USAGE TO PUBLIC + `alembic upgrade head` before every full-PG run; battery gets the tree to itself.
- **Per-conclusion CI verification**: background until-loops requiring ≥9 runs REGISTERED and all completed-success on the exact head SHA (the exit-0-before-registration trap avoided throughout).
- **Emulating pre-era artifacts**: a true v1 EXPOSURE_INPUT snapshot can no longer be minted (the builder auto-upgrades) — tests emulate via raw SQL predicate rewrite + component deletion; `build_snapshot` now documents this.

## Files Modified
STRUCT-4 slice (PR #227, 33 files, +2,753/−70):
- `packages/shared-python/src/irp_shared/marketdata/legs.py`: `serialize_legs` + `derive_pivot` (DP-12)
- `packages/shared-python/src/irp_shared/exposure/service.py`: DP-11 resolution both paths, refusal classes, stated_pivot threading, rollup translation fields/logic, v3 branch matrix
- `packages/shared-python/src/irp_shared/snapshot/service.py`: `NODE_FX_BINDING_PREDICATE` (v3), node-currency FX-completeness union
- `packages/shared-python/src/irp_shared/portfolio/portfolio.py`: `resolve_reporting_currency`; `TreeNodeAsOf.base_currency_code`
- `migrations/versions/0073_declare_root_currency.py` + `scripts/migration_0073_p17_check.py`: the DP-11 backfill + populated-DB harness
- `packages/shared-python/src/irp_shared/demo/struct4_stage27.py` + `tests/test_demo_stage9zzzzzzzzzzzzzzzzzz_struct4_pg.py` + `.github/workflows/ci.yml`: the DEMO-FX book (18-z alpha-sort, own CI step)
- `packages/shared-python/tests/test_struct4_fx.py`: the 17-test battery (oracles, refusals fired, legacy shapes, v2-conflict pin)
- `apps/backend/src/irp_backend/api/exposure.py` + `portfolios.py`: `fx_pivot`, NodeRollupOut translation fields, error-map keys, TreeNodeAsOfOut currency
- `apps/frontend/src/views/RunDetail.tsx` (+test): conversion-path drill-in + node-totals pane ("via USD" pivot cells, node-id input)
- `packages/shared-python/src/irp_shared/demo/campaign.py`: DEMO-GLOBAL declares USD
- `scripts/mutants.toml`: struct-4 group M-S4-1..11 (11/11 killed)
- `05_analytics_methodologies/fx_translation_v1.md` + `08_testing_qa/struct4_fx_test_spec.md`: DP-14 citations + hand derivations

Wave-18 close (PR #229, 20 files, +316/−59):
- `10_delivery_backlog/wave_18_close_review.md`: NEW — the close record (G4 table, sweep dispositions, ratified D1-D3, measured counts)
- `10_delivery_backlog/wave_18_planning.md` + `delivery_roadmap.md`: D2 amendment; merge-identity stamps (STRUCT-1/2/4); Part 5 item 5 outcome
- `02_requirements/requirements_backbone.md` + `requirements_traceability_matrix.md`: six Status cells advanced; three acceptance-cell annotations
- `02_requirements/g2_slice_scope.json`: wave-boundary declared emptiness (slice=null)
- `04_data_model/canonical_data_model_standard.md` + `audit_event_taxonomy.md`: ENT-014 extension, stale footers retired, 0073_BACKFILL enumeration, Wave-18 minted-nothing sentence
- `09_compliance_controls/control_matrix_skeleton.md`: CTRL-018 EXTENDED + 4th P16 re-take (CI run 32056226029, head 7dcb3a3); CTRL-009 re-cite; CTRL-029 exercise
- `packages/shared-python/src/irp_shared/exposure/service.py` (+`models.py`, `portfolio/models.py`, `reproduction/registry.py`, `snapshot/service.py`): K24 fix + docstring corrections
- `apps/backend/tests/test_capability_coverage.py`: zero-bindings control DELETED per its own instruction
- `apps/frontend/src/views/ops/PortfolioStructure.tsx` (+test): Reporting-ccy column (the DP-11 declaration visible)
- `docs/project_memory/current_state.md`: two stamps (post-#227, then the close truth via PR #230)
- Memory: `~/.claude/.../memory/struct-1-state.md` + `MEMORY.md` (WAVE 18 CLOSED position)

## Setup & Config
- Merge mechanics under the GitHub outage: REST `POST /pulls` + `PUT /pulls/N/merge` via `gh api` (GraphQL `gh pr create/merge` 503'd repeatedly); background retry loops (90-120s intervals).
- Local PG: container `irp_pg_local` (postgres:16), reset recipe per the standing memory; full-PG battery selection = `packages/shared-python/tests apps/backend/tests` (3,500 tests; the whole-repo collection is 3,540 incl. root `tests/`).
- G2 gate: `slice: null` + `no_scope_reason` ≥60 chars = the declared-emptiness shape; a NAMED slice with empty scope refuses.
- alembic_version column is varchar(32) — revision ids must fit.

## Pending Tasks
- **The Wave-19 planning gate** (next, on the owner's go, ultracode): sequence slices from roadmap Part 4 rules; decide two control-mint candidates (backup/DR standing since DEP-1; aggregation-contract enforcement layer, close K8); G2 re-adjudication for lapsed PPM-006/PPM-010 if they enter scope.
- Standing touch-triggers from the ratified close decisions: rename re-runs for backtest/desmoothing/pacing ride their next slice (D1); per-family non-root execution rides each family's next slice (D2).
- Carries: PPM-001 clause 3 (ABAC P6+); the Part-1 OUT-list triggers (none fired); the pin-bounded-resolution asymmetry (documented, trigger-based).

## Errors & Workarounds
- `0073_backfill_root_reporting_currency` > varchar(32) → StringDataRightTruncation on `alembic upgrade` → renamed `0073_declare_root_currency` (found by executing, not reading).
- First full-PG run: 10 failures from ONE cause (scheduler dispatch hit the undeclared-root refusal on DEMO-GLOBAL) → declare USD on the demo root.
- GitHub 503s (GraphQL + REST): retry loops; a 503'd `gh pr merge` followed by branch deletion closed PR #228 unmerged → branch recreated from the local commit, PR PATCHed open, merged via REST. Rule: confirm merged=true before any cleanup.
- G2 lapse mid-close (annotations changed hashed cells) → wave-boundary scope emptiness + D3.
- `make check` mypy: `Portfolio | None` loop var + `dict[str, object]` rollup typing → explicit annotations/`NodeRollup` import.
- FE: old exposure fixture lacked `fx_legs` → TypeError in the new section → fixture updated + defensive `?? []`/`Array.isArray`; vacuous `getAllByText("USD")` pivot assertion → distinct "via USD" rendering.
- Aggregation census caught stage 27's oracle `sum()` → classified deliberately (N).
- M-S1-9 and M-S4-1 mutant anchors went stale after code evolution → re-anchored (never deleted).

## Key Exchanges
- User: "proceed ultracode" (STRUCT-4) → full slice cycle: G2 scope move, 5-reader understand workflow, build, 6-lane adversarial review (19 confirmed/0 rejected, BLOCKING C9 symmetric-refusal fix), gates, PR #227, per-conclusion verify, merge, stamp #228 (with the outage recovery).
- User: "proceed ultracode" (the close) → ten-lane sweep workflow (45 agents, 34 confirmed/1 rejected), ledger repairs, K24 exploit fix, G4 first fire + zero-bindings deletion, the measured 3,500 refutation, plain-language briefing of D1/D2/D3.
- User: "proceed" (ratification) → outcomes filled, D2 amendments, PR #229 merged = `e8ab540` (40th autonomous merge), stamp #230 = `d886fb8`, memory updated. Wave 18 CLOSED.

## Custom Notes
None

---

## Quick Resume Context
Wave 18 is fully CLOSED: STRUCT-4 (PR #227 = d465b6b) delivered REQ-PPM-010 (DP-11/12/14, hand oracles, drill-in screen), and the close (PR #229 = e8ab540, stamp #230 = d886fb8) ran G4's first fire, the ten-lane sweep (34 findings dispositioned incl. a fixed v1-scope-stamp exploit), and three owner-ratified decisions. Main is d886fb8, head 0073_declare_root_currency, ENT-077 next free, G2 scope a declared emptiness. NEXT = the Wave-19 planning gate (ultracode): slice sequencing, two control-mint candidates, lapsed PPM-006/PPM-010 re-ask on scope entry.

---

## Raw Session Log

*(This session ran under context compaction; the full verbatim transcript is not reconstructable from the live window. What follows is the complete turn-by-turn record at summary fidelity — every user message verbatim, every action sequence in order.)*

**[Session opened from a compaction summary]** — prior context: Wave 18 at three of four slices (STRUCT-1 #220, STRUCT-2 #223, STRUCT-3 #225 = f74d207 38th merge); pending task: finish the STRUCT-3 close-out (verify main CI, merge stamp PR #226, prune, memory).

**[auto]** STRUCT-3 close-out completed: memory updated with the STRUCT-3 lessons; main f74d207 CI verified ALL GREEN (9 runs); PR #226 verified per-conclusion then merged (main 9a54a8d); stamp branch pruned; task #19 completed.

**User: "proceed ultracode"** (STRUCT-4)
- G2 slice scope → [REQ-PPM-010] (adjudication CURRENT); gate exit 0.
- Understand workflow `struct4-understand` (5 readers): mapped the FX core (convert/legs/compose_effective_rate; DEFAULT_BASE=USD pivot; fx_legs as_dict shape; byte-compared reproduction field), the two silent USD defaults (exposure/service.py:138, :480), snapshot FX pinning + predicate strings, the fx_legs API/no-screen gap, demo-book currencies (USD/EUR only), the mutants/stage conventions, the rename-residual chains.
- Build: resolve_reporting_currency; DP-11 refusals both paths; v3 predicate + node-currency FX-completeness; serialize_legs/derive_pivot (DP-12); rollup translation with honesty fields; migration 0073 (renamed after the varchar(32) refusal) + P17 harness (exit 0 over populated rows); test_struct4_fx (11 tests initially, hand oracles passing first run); HTTP tests; RunDetail drill-in + node-totals pane; stage 27 + PG suite + CI step; DP-14 citations doc + test-spec doc; mutants M-S4-1..9 9/9.
- First full-PG: 10 failures, one cause (scheduler dispatch vs undeclared DEMO-GLOBAL) → root declares USD → re-run 3,495→green 3,499? (final: PG_PYTEST_EXIT=0, 3,499 passed).
- Adversarial review workflow (6 lanes incl. the DP-14 citation lane, 25 agents): 19 confirmed / 0 rejected. Folds: symmetric build-path conflict refusal (BLOCKING C9/C6); SLEEVE-ALBION 2-leg rollup translation + node-scoped triangulation (C0/C12/C14); HTTP triangulated fx_pivot (C11); FE "via USD" + exact URL pin + node-id input (C13/C15/C8); v1 multi-top all-resolve rule (C7); v1 node-anchored base resolution removed (C10); v2-conflict-completes pin (C3); 0073 verify-drift docstring (C4); citation locator fixes (C16-18); roadmap stamps + Part 5 item 5 (C1/C2); mutants M-S4-10/11 → 11/11.
- Gates: make check 0 (2,908), fe-check 0, gen-api-check 0, anchors 129/129, alembic check clean, final full-PG exit 0 (3,499→ with fold tests 3,499).
- Commit → PR #227 (created via REST retry loop through a GitHub 503 outage) → per-conclusion green (9 runs, head aa1f8f1) → merged = main d465b6b (39th) → main CI verified green → stamp PR #228 (503 recovery: a premature branch delete closed it unmerged; branch recreated, PATCHed open, merged via REST) → main 7dcb3a3 → memory updated.

**User: "proceed ultracode"** (the Wave-18 close)
- Close obligations mapped: planning Part 5 (5 items), G4 mechanics (heading, table, NONE-mark rules; zero-bindings control's deletion instruction), the seven-ledger sweep + verify-on-main standing rule.
- Ten-lane close workflow `wave18-close-sweep` (7 ledgers + 3 wave lenses, 45 agents, per-finding verification): 34 confirmed / 1 rejected.
- Folds: K24 v1-scope-stamp exploit FIXED (+test +M-W18C-1); six backbone + six RTM Status cells advanced; three acceptance-cell annotations; ENT-014 row extended; three stale footers retired; 0073_BACKFILL enumerations; taxonomy minted-nothing sentence; CTRL-018 EXTENDED + 4th P16 re-take (CI 32056226029); CTRL-009 re-cite; CTRL-029 exercise note; repro-registry prose; route-census arithmetic; build_snapshot v1 honesty note; PortfolioStructure Reporting-ccy column (+test); roadmap merge stamps.
- G2 lapse (annotation) → wave-boundary declared emptiness (slice=null); gate green.
- The measured refutation: close battery = 3,500 passed / 0 skips / exit 0; whole-repo collect 3,540 — the "unreachable 3,499" finding refuted by execution.
- wave_18_close_review.md written (G4 table 1.1/1.4/1.5 verbatim labels, accurate wording); zero-bindings control deleted; gates green (2,908/2,909→2,908, fe 0, anchors 130/130, capability gate: 18 close reviews, 1 bound).
- Briefing delivered: D1 (rename residual → accept recurrence + touch-trigger), D2 (clause-7 → amend to delivered form + trigger), D3 (lapsed adjudications → leave lapsed). STOPPED for ratification.

**User: "proceed"** (ratification)
- Outcomes filled (all three AS RECOMMENDED); D2 amendments to planning line 52 + roadmap STRUCT-3 row; Part 5 item 5 annotated DECIDED.
- make check 0 → commit → PR #229 → per-conclusion green (9 runs, head dd13027) → merged via REST = main e8ab540 (40th autonomous merge) → branch pruned → main CI watcher launched.

**User: "proceed"**
- PR #229 checks confirmed green; merged; main pulled; stamp branch current-state-stamp-229 created; CURRENT TRUTH stamped (WAVE 18 CLOSED, NEXT = Wave-19 planning gate); DOCS_EXIT=0, CHECK_EXIT=0; stamp PR #230; memory updated (struct-1-state.md close lessons + MEMORY.md "WAVE 18 CLOSED" position).
- Main e8ab540 CI verified ALL GREEN (9 runs); PR #230 verified ALL GREEN then merged via REST (merged=true CONFIRMED before cleanup) = main d886fb8; branch pruned; task #24 completed.

**User: "/compress"** → this log.

Final state: main `d886fb8`, tree clean (one pre-existing untracked session log), migration head `0073_declare_root_currency`, ENT-077 next free, no background processes, Wave 18 CLOSED, next = the Wave-19 planning gate.
