# Current State

> ## ⚠️ CURRENT TRUTH (2026-07-22) — read this block; everything below it is HISTORY
>
> **HEAD `9d64b49`** = merge of **PR #98** (PPF-1: the pure-private factor return — Wave 10 slice 3,
> §2.1 unification arc slice 1 of 3; migration `0047_private_factor_return`; the 18th governed
> number, counts 20/35/101 → **21/36/103**), **CI green** (all 6 jobs). Opens the §2.1 headline: the
> planning census found the unification embryo already shipped (`risk.var.parametric_total`, PA-4)
> but missing the MSCI Private Equity Factor Model's (Shepard 2014/2025) "pure private" leg —
> systematic private risk a public proxy can't capture. Ratified **fork B** (deepen the math) over a
> **3-slice arc**: PPF-1 (this) → PPF-2 (the private covariance block Ω_pp) → PPF-3 (the unified
> number `√(x'Σx + p'Ω_pp·p + residual)`).
>
> **PPF-2 IMPLEMENTED (on branch `ppf-2-private-covariance`, pending merge; planning merged via
> PR #100):** the private covariance block **Ω_pp** — the **19th governed number**
> `risk.covariance.private`, **arc slice 2 of 3**. A fail-closed SIBLING of `risk.covariance.sample`
> that REUSES the generic `estimate_covariance` kernel UNCHANGED + the shared `covariance_result`
> table (`frequency=APPRAISAL`, `run_type=COVARIANCE_PRIVATE`) — **NO migration, NO ENT**. Equal-weight
> sample covariance of PPF-1's pure-private APPRAISAL series across ≥2 PRIVATE segments over their
> common appraisal grid; block-diagonal-with-Σ disclosed as an APPROXIMATION (the promoted proxy
> blend is a SUBSET of the OLS fit, so `pp` is only APPROXIMATELY orthogonal — the verifier fold).
> Step 1 closed a **latent shared-table read bug**: the public `latest_covariances`/`resolve_covariance`
> now filter `run_type` (behavior-identical for all pre-PPF-2 data), so a private matrix can never
> leak into a public read — proven both directions. Demo stage 12 (`stage9zzz`) runs ONE Ω_pp over
> the two seeded segments; counts **21/36/103 → 22/37/104** (1 code + 1 record + 1 run). **NEXT after
> merge = PPF-3** (the unified number — owns the appraisal→daily conversion + the VaR-gate widening).
>
> **The construction:** per member per appraisal period, `pp_i,t = desmoothed_i,t − Σ_f w_i,f·R_f,t`
> (the desmoothed return minus the proxy-implied return — the current-head REGRESSION blend, public
> factor returns compounded over the half-open `(period_start, period_end]` window via a shared
> alignment helper extracted from PA-3), pooled EQUAL-WEIGHT across members sharing the identical
> interval (RETAIN_ALPHA — the liquidity premium stays in the factor). A new `PRIVATE` factor family
> + `APPRAISAL` frequency, fail-closed OUT of every DAILY covariance/VaR gate until PPF-2/3 mint the
> conversion.
>
> **The pre-ratification verifier REFUTED the naive isolation premise** (an unguarded PRIVATE
> segment-membership row — a weight-1 MANUAL `proxy_mapping` row — would refuse every new PA-2/FL-1
> exposure run pre-create) and forced **three guards**: the exposure-snapshot-builder family filter;
> splitting the capture-admission family set off `LOADING_FACTOR_FAMILIES` (deliberately overturning
> a prior shared-verbatim invariant, FL-1/RBSA gates stay byte-identical); the PRIVATE⇒MANUAL capture
> invariant (keeping total-VaR's REGRESSION-method pin filter safe). **4-finder review: ZERO HIGH**,
> 1 MED + 2 LOW folded. **MED** — `update_factor` admitted `factor_family`/`frequency` as updatable,
> so a public factor with an existing REGRESSION blend could be FLIPPED to PRIVATE/APPRAISAL in
> place, retroactively bypassing the capture-time guards — fixed by FREEZING both as gate-admission
> identity (byte-identical for all shipped usage). **LOW** — the magnitude gate's `1E8` envelope
> equaled the `Numeric(20,12)` column cap (a raw value could pass the gate then quantize up into a
> PG-only overflow, the CC-2 lesson) — fixed to gate the quantized values; a by-segment read ordered
> on `metric_type` alone — fixed to `(metric_type, period_start)`.
>
> **Demo stage 11** pools both segments (PE-HARBOR-IV/PRIVATE_EQUITY→FX_USD;
> PC-BRIDGEWATER-II/PRIVATE_CREDIT→MF_RATES_GOV+MF_CRSPD_IG) at min_members=1 with **ZERO new seeded
> book data** — both already carried a COMPLETED desmoothing run + a promoted REGRESSION blend.
> Gates: `make check` 1802 passed; `make fe-check` 110+build; `make gen-api-check` clean; the full
> demo PG chain in CI order green; migration 0047 downgrade/upgrade smoke + `alembic check` clean;
> the ENT-060 RLS/append-only PG test green.
>
> **Prior: HEAD `2cbb68c`** = merge of **PR #95** (FE-3b: the SPA OIDC/PKCE browser login — Wave 10
> slice 2; NO migration; counts UNCHANGED 17/20/35/101), **CI green**. Turns SSO-1's real OIDC
> resource server into something a non-developer can actually reach: a hand-rolled browser auth-code
> + PKCE flow (Web Crypto, zero new runtime dep) against the Keycloak `irp-frontend` public client.
> **WAVE 10 SLICES 1+2 COMPLETE** (API-1b + FE-3b, both DONE) — see below for the API-1b summary.
>
> **Prior: HEAD `f1e830f`** = merge of **PR #92** (API-1b: the flagship VaR/active-risk entity reads —
> Wave 10 slice 1; migration `0046_run_scope_portfolio`; counts UNCHANGED 17/20/35/101), **CI green
> run #488**. Pays the ONE read API-1 deferred — "latest VaR / active-risk for portfolio P" — at the
> **write** boundary (API-1's verifier had refuted read-only resolution).
>
> **ONE additive nullable `calculation_run.scope_portfolio_id`** column (the `environment_id`/
> `failure_reason` precedent — no RLS/grant/trigger change) threaded through the SINGLE
> `create_run`/`execute_governed_run` choke point and stamped by all FIVE binders: `run_exposure`
> from its direct `portfolio_id` arg (the subtree ROOT); `run_factor_exposure`/`run_var`/
> `run_var_historical`/`run_active_risk` COPYING it forward from their resolved upstream run — proven
> to hold in BOTH the build and snapshot-consume input paths, the write-boundary crux API-1's
> read-boundary could not resolve. The Class-C reads (`list_var_results`/`latest_var_for_portfolio`,
> `list_active_risk_results`/`latest_active_risk_for_portfolio`) resolve via the EXISTING
> `calc/reads.py` helper (zero helper change — a `scope_portfolio_id == P` equality filter);
> `active_risk`'s native `benchmark_id` filter also lands. **OQ-API-1b-1 = A "honest-NULL"**: a
> snapshot-consume-rooted chain (exposure OR factor) stays NULL and is disclosed-unresolvable — the
> fully build-in-request chain (demo/UI/default-API) always stamps a real root; no data back-fill.
> Both ratified Wave-10 CI riders landed here: a **`pip-audit` gate** (audits the INSTALLED
> ENVIRONMENT — review-corrected from `-r requirements-dev.txt`, which missed the `python-multipart`
> runtime dep) and a **closure-discipline docs-check** (filename-keyed, row-anchored; fails on a
> DONE-in-roadmap record still reading "DRAFT for ratification" — teeth for the 5th-consecutive
> missing-stamp class, unit-tested to actually FIRE).
>
> Pre-ratification verifier pass RAN: the copy-forward crux + TR-09 hash-neutrality + migration
> neutrality + read non-shadowing all HELD; 2 COMPLICATED findings folded pre-implementation (a
> second snapshot-consume NULL-origin at the exposure tier, not just factor; the closure-check's
> mechanic, needed to dodge a demonstrated false-positive trap — "API-1b" appears as prose inside two
> other slices' `✅ DONE` rows). **4-finder review: ZERO HIGH.** Write-path: the copy-forward proven
> correct across all 5 binders + both paths, immutable-after-creation, TR-09-neutral, complete (no
> unstamped run creator). Doctrine/security: all 6 hard invariants held; the cross-tenant probe
> confirmed `scope_portfolio_id` is NOT a security boundary (RLS + an explicit tenant filter
> double-bind it — a foreign `portfolio_id` is silent-empty, no existence oracle). Read-correctness:
> filters/run_type/latest-run-selection correct; `/latest` declared before `/{id}`, zero shadowing;
> OpenAPI regen deterministic. CI-riders+honesty: found and fixed a REAL gate hole (the pip-audit
> target above). Folded **5 MED + 1 LOW**: the pip-audit target fix; the closure-check's own
> failure-path teeth were untested (added a test proving the rule FIRES); the closure-check's
> guarantee was over-claimed in its own comment (rescoped to the go-forward cadence); the record's
> "`/latest` 404" wording was a mis-cite (the shipped list-shaped `/latest` correctly returns `[]`,
> matching the covariance/sensitivity/factor-exposure/var-backtest siblings); the copy-forward
> endpoint tests strengthened from non-null to VALUE-equality against the upstream stamp. Disclosed:
> the one `pip-audit` allowlist entry is `PYSEC-2026-1845` (dev-only pytest, fix is a risky major
> bump) — `pyjwt`/`cryptography` (the identity surface) audit CLEAN, NOT ignored; `pydantic-settings`
> bumped 2.14.1→2.14.2 clearing a real advisory the gate surfaced. Battery: `make check` green;
> `make fe-check` green (97+build); `make gen-api-check` clean; full-PG affected-family battery
> green; `0046` downgrade/upgrade smoke + `alembic check` clean.
>
> **The OPERATIVE sequence doc is `10_delivery_backlog/delivery_roadmap.md`** (wave rows + the dated
> amendment log — it WINS wherever the sections below disagree). The latest decision record is
> `ppf_1_decision_record.md` (**CLOSED 2026-07-22**); prior `fe_3b_decision_record.md` (**CLOSED
> 2026-07-21**), `api_1b_decision_record.md` (**CLOSED 2026-07-21**). Prior wave: **WAVE 9 FUNCTIONALLY COMPLETE +
> CLOSED + RATIFIED 2026-07-21** (API-1 → FE-2 → SSO-1 → FE-3, all four slices DONE;
> `wave_9_close_review.md` RATIFIED, the FIFTH consecutive zero-shipped-defect close). Standing
> carries: the BT-3 D-F4 reword (a dedicated ES/var-backtest touch); the FE-2 `@redocly` dev-tree
> advisory (dev-only, no action); the FE-3 `auditor_3l` demo-viewer (demo-scoped). *(Everything from
> the "WAVE 7 IS UNDERWAY" line down is prior HISTORY, superseded by this block — the counts/
> next-pointers below are as-of their own date.)*
>
> **WAVE 7 IS UNDERWAY (roadmap Part 2.10, fork A "deepen the mathematics"): HG-1 → ES-HS-1 → RS-1 →
> DS-2**, riders: SC-2 the named pull-forward, commitment/capital-call the presumptive Wave-8
> headline. **HG-1 (slice 1) DONE** (impl PR #55 = `8260ea6`). **ES-HS-1 (slice 2, the headline)
> DONE** — planning PR #57 = `7568c49`, impl PR #58 = `dc2a494`, CI green: the **15th governed
> number** and the platform's FIRST empirical tail measure — the Acerbi-Tasche Prop-4.1 α-tail-mean
> (floor count + fractional boundary weight, NEVER the TCE) over the shipped HS scenario
> distribution; `metric_type='ES_HISTORICAL'`, the `risk.var.historical_es` v1 family through the
> HS binder's registry-map dispatch; the ONE migration `0041` widening the 0028 CHECK (destructive
> RLS-safe downgrade proven under a non-superuser owner-member role); the Acerbi-Szekely backtest
> TEED as BT-3 (Christoffersen finally homed; pairing via shared `input_snapshot_id`; AS 2014
> verified-via-reproduction — the primary is gated); demo stage 4 = the 18th code (TIER_1, an
> INITIAL AWC dossier, the flagship ES bound to the flagship HS VaR's snapshot). 4-finder review,
> zero HIGH, zero shipped math defects. **RS-1 (slice 3) DONE** — impl PR #61 = `9c15658` (planning
> PR #60): the PA-4 **OD-E/OD-G residual-estimator v2s REALIZED** as two declared conventions on
> `risk.proxy_weight.regression` — `EWMA_RISKMETRICS` (Axioma/RiskMetrics decay-weighted specific
> variance, declared λ; the s2 decoupling keeps OLS std-errors classical; raw v1 grandfathered) and
> `SHRINKAGE_CROSS_SECTIONAL_EB` (Barra USE4 empirical-Bayes cross-sectional shrinkage, data-driven
> per-instrument w_i, method-as-identity, N≥3-distinct-instrument fail-closed) — NO new governed
> number/code/migration; Ledoit-Wolf verified-and-explicitly-NOT-used (it leaves variances
> unshrunk). Demo **stage 5** = the SECOND lifecycle turn: the sleeve grown to 3 equities, MF-EQ-B
> EWMA-re-estimated + MF-EQ-A EB-shrunk (bond excluded, asserted-raw), fresh gated flagship
> total-VaR/ES-total evidence, **2 TRIGGERED re-validations closing the raw-sample-σ_e rider** (the
> `hostage to the PA-3 estimate quality` finding flipped to historical, both directions test-pinned)
> + 2 INITIAL AWC dossiers for the new versions. **DS-2 (slice 4, the LAST) DONE** — planning
> PR #63 = `0f199aa`, impl **PR #64 = `5120baa`** (CI green; migration **`0042`**): the
> declared-α rider REMEDIATED via two declared estimator conventions on
> `perf.return.desmoothed_geltner` — **`AR1_ESTIMATED`** (α̂ = 1−ρ̂₁ in-run; the CONSERVATIVE
> Bartlett band persisted as `alpha_stderr`; the Kendall/Marriott-Pope small-n UPWARD bias of α̂
> a registered limitation) + **`OKUNEV_WHITE_ITERATIVE`** (deterministic lag-i passes, the
> derivation-settled '−' root, the length-vs-order floor; alpha NULL on OW rows) — GLM MA(k)
> stays the named v2 (extraction-verified to equation numbers; the MLE-optimizer determinism
> obstacle recorded). Demo **stage 6** = `PE-HARBORVIEW-IX` (16 marks at known α_true = 0.4),
> the three-way declared/estimated/OW comparison, 2 INITIAL AWCs claiming
> **estimation-with-honest-uncertainty, NOT recovery**; **NO TRIGGERED re-validation, recorded
> honestly** (census-proved: no closable condition names the rider — deliberate contrast with
> the MF-1/RS-1 flywheel). 4-finder review ZERO HIGH/MEDIUM; + the missing-CI-step catch at the
> pre-push battery (the 0042 PG suite had no ci.yml step — the P3-7 class, fixed + recorded).
> **WAVE 7 IS CLOSED AND RATIFIED** (2026-07-19: `wave_7_close_review.md` OQ-W7C-1…6 "Approve
> all", merged as DRAFT via **PR #66** = `cc251b2`, ratified immediately after — the second
> full-ultracode close: 71 agents, all four slices SHIPPED-AS-RATIFIED, **ZERO shipped-code
> defects, the THIRD consecutive clean close**; 14 hygiene fixes applied at the close; the one
> code-behavior finding — the stage-4 flagship-pair uuid4 tie-break — ASSIGNED to BT-3).
> **WAVE 8 IS RATIFIED (roadmap Part 2.11, OQ-W7C-6 fork A "fund the third leg"): BT-3 (the
> Acerbi-Szekely ES backtest) → CC-1 (captured commitments/calls/distributions, ENT-015/016) →
> CC-2 (the Takahashi-Alexander pacing projection — the HEADLINE, the 16th-governed-number
> candidate — SEVENTEENTH after the BT-3 mint adjudication)**, riders: BT-3's Z1/threshold
> re-verification MUST; CC-2's Tier-3 forks named at planning + the TA-fetch fallback; SC-2 the
> named pull-forward (its Wave-7 condition expired unspent); the stage-7 demo obligation; the
> slot-zero opener option. **BT-3 (slice 1) DONE** — planning PR #68 = `b493c78`, impl
> **PR #69 = `109d11d`** (CI green run #399; migration **`0043`**): **`risk.es_backtest` = the
> SIXTEENTH governed number** — the AS Z1/Z2 evidence rows with the verdict **DOMAIN-GATED to
> (paired confidence 0.9750 ∧ n_pairs 250)** (the criticals are α/T/df-dependent — executed MC;
> off-domain runs persist Z evidence + `ES_PAIR_COUNT` and NO verdict; the per-(α,T) table =
> the named v2 under a governed offline MC derivation); the fetch MUSTs discharged (the '+1'
> null-expectation identity + the three-route threshold bar); **the Christoffersen
> `risk.var_backtest` v2** in-slice (`CHRISTOFFERSEN_MARKOV`, LR_IND/LR_CC from stored legs;
> v1 byte-preserved — the twice-re-teed item DISCHARGED); the OD-C sibling-pair gates on
> shared `input_snapshot_id`; the OQ-W7C-2 tie-break fix folded by name; demo **stage 7** =
> the DOMAIN-GATE HONESTY demo (Z2 = −127.09 verdict-WITHHELD; the LR_CC joint-power lesson
> live at n=3), 4 INITIAL AWCs, NO TRIGGERED census-proved, the 19th registered code.
> 4-finder review ZERO HIGH; 2 named D-F4 next-touch deferrals → the Wave-8 close register.
> **CC-1 (slice 2) DONE** — planning PR #71 + the rule-7 amendment PR #73, impl **PR #74 =
> `1cdc95b`** (CI green run #420; migration **`0044`**): ENT-015/016 REALIZED as captured
> inputs on the stable (portfolio, instrument) identity (chain-immutable currency; the
> negation FULL-reversal correction; the provenance-only version echo); the three-code
> `commitment.*` mint; EVT-240 ACTIVATED; REQ-PRV-001/002 → In-Progress (the computed +
> liquidity clauses OPEN → CC-2); demo stage 8 = the capture half of the commitment walk
> (counts pinned UNCHANGED — capture-only honesty); 4-finder ZERO HIGH, all 8 MED folded.
> **NEXT = CC-2 planning** (the SEVENTEENTH-number HEADLINE: Takahashi-Alexander pacing —
> fetch TA to paragraph FIRST, the ratified MUST; ENT-059 + family/permission Tier-3 forks;
> the projection half lands on the stage-8 seeded commitment). **WAVE 6 remains
> CLOSED AND RATIFIED** (2026-07-17: `wave_6_close_review.md` OQ-W6C-1…6 via PR #52 = `9d561bf`).
> The living tenant is **19 registered model codes / 34 validation records (11 EXCEPTION +
> 16 INITIAL + 7 TRIGGERED) / 95 COMPLETED runs — UNCHANGED by CC-1 (capture-only)** + the
> stage-8 captured lifecycle (1 commitment / 5 call rows incl. the reversal / 2
> distributions). `phase_status.md`/`next_actions.md` are pointer stubs (OQ-W6C-4).
>
> **Wave-6 history: Wave 6 was functionally complete 2026-07-16** (MG-1 → FL-1 → MF-1 all CLOSED). MF-1
> demonstrated **the full governance lifecycle**: the living demo tenant went multi-family — an
> additive extension (`scripts/run_demo_multifamily.py`; refuse-not-skip; the base campaign
> byte-untouched) seeded the multi-asset sleeve (2 equities + 1 credit, 3 FRTB-family factors),
> ran marks → α=1 desmooth (`v1-alpha1`) → the k=3 Sharpe-1992 OLS → promoted structural
> loadings → the loadings-family exposure → covariance → one VaR/HS/total/ES/ES-total run each
> **bound to the demo-mg1 flagship versions**, and filed **5 TRIGGERED AWC re-validations closing
> the CURRENCY-only condition** (freshly-drafted conditions, zero 'FL-1' — the conditions-grep
> finds the token in exactly the 5 HISTORICAL rows, test-pinned both directions at the version
> grain) + the loadings INITIAL (TIER_2) + the α=1 EXCEPTION. Demo tenant now: **17 codes / 17
> tiered / 7 validated + 11 excepted / 63 COMPLETED runs**. The mixed-family fence held (the
> legacy proxy family stays runnable). Two standing capabilities RETIRED, disclosed: the campaign
> suite's tolerate-living-tenant mode + the dirty-schema double-run (fresh-schema-only from MF-1
> on; the extension CI step is ordering-pinned after the campaign step).
>
> *(The close review this paragraph used to tee is DONE and RATIFIED — see the banner above; the
> OD-E re-tee was discharged by sequencing RS-1/DS-2 into Wave 7, and the four MF-1-unlocked
> candidates stay sequence-able with SC-2 the named pull-forward.)* The pre-ratification verifier
> pass is standing process.
>
> **Counts (2026-07-20, post-CC-1 — UNCHANGED by design, the capture-only honesty):** **16
> governed numbers** (`risk.es_backtest` = the SIXTEENTH; CC-2's candidate is the
> SEVENTEENTH; CC-1 deliberately mints NONE) / **19 registered model codes** in the demo
> tenant / 19 tiered, 16 validated (the Wave-6 seven + the ES-HS INITIAL + RS-1's two +
> DS-2's two + BT-3's four new INITIALs), 11 excepted, 34 validation records total
> (11 EXCEPTION + 16 INITIAL + 7 TRIGGERED, DB-verified) / **95 COMPLETED runs** — plus the
> NEW captured private-capital substrate (3 tables; the stage-8 lifecycle live). Delivery runs under the
> 2026-07-14 EXTENDED autonomy grant (the USER signs Tier-3 decisions; the USER creates AND merges
> PRs — the auto-mode classifier blocks Claude's REST create + merge on this repo).
>
> **Purpose.** Entry-point snapshot so a fresh Claude Code session can recover context without chat
> history. Read this block, then `10_delivery_backlog/delivery_roadmap.md` (the operative sequence),
> then `claude_operating_instructions.md`. Re-verify HEAD/CI before acting. *(`project_state.yaml` is
> RETIRED — see its stub; the recovery set is `CLAUDE.md` → this file → the roadmap.)*
>
> **⚠️ EVERYTHING BELOW THIS BANNER was last deep-refreshed at the PA-0 era (HEAD `ad3d3fe`,
> 2026-07-11) and UNDERSTATES the current state** — it stops before PA-1/PA-2/PA-3/PA-4, the Wave-4
> close, RD-3 and VW-1. Retained as history (the per-slice detail is accurate for the slices it
> covers). Where it disagrees with the roadmap or this banner, **they win**.

## Repository
- **Project:** full-scope enterprise investment-risk platform (monorepo). NOT an MVP/POC — see `build_plan.md`.
- **Layout:** `apps/backend` (FastAPI), `apps/worker`, `apps/frontend`, `packages/shared-python` (`irp_shared`, web-framework-free), `packages/shared-ts`. Postgres + RLS, SQLAlchemy 2.0, Alembic. Numbered governance dirs `01_…`–`11_…`; delivery docs in `10_delivery_backlog/`.
- **Remote:** `github.com/ghostai8088/investment-risk-platform` (branch `main`). **origin is now HTTPS** (`https://github.com/ghostai8088/…`; keychain-cached PAT — flipped from SSH 2026-07-09 at P3-C3 because SSH port 22 is BLOCKED on the current network, timing out; HTTPS push works cleanly. Plain `git push` now uses HTTPS + PAT — no hotspot / URL-push workaround needed).

## Latest known committed state
- **origin/main HEAD:** `ad3d3fe` — merge of **PR #8** (`c9d41a7`, "PA-0: private-asset foundations — proxy_mapping (ENT-019, captured input)", **CI green**); prior `7a422aa` (PR #7, PA-0 planning) ← `df92a9c` (PR #6, BT-1 closeout) ← `868f892` (PR #5, BT-1 impl). Chain since P3-3: `7c50c43` (**P3-3 implementation**, #95) → `362481a` (P3-3 closeout memory) → `8abe764` (**P3-4 planning**, OQs ratified) → `a9b6567` (**P3-4-R0 refactor**, #98) → `c2bd126` (**P3-4 IMPLEMENTATION + 12 review folds**, #99) → `c2480a4` (P3-4 closeout memory, #100) → `c2c1b4d` (**P3-5 parametric-VaR planning**, OQ-P3-5-1..10 ratified + the historical-sim/MC ROADMAP note, #101) → `5ed8271` (**P3-5 IMPLEMENTATION + 13 review folds**, #102) → `d94e572` (P3-5 closeout memory, #103) → `c2e85ac` (**P3-C1 hardening planning**, OQ-P3-C1-1..8 ratified after a plain-language briefing, #104) → `0599f7f` (**P3-C1 IMPLEMENTATION + 12 review folds**, #105) → `ee3c581` (P3-C1 closeout memory, #106) → `416cb1d` (**FE-1 frontend runs-view planning**, OQ-FE-1-1..8 ratified, #107) → `678a651` (**FE-1 IMPLEMENTATION + 16 review folds — the FIRST VISIBLE UI SLICE**, #108) → `945661d` (FE-1 closeout memory, #109) → `63a1bb8` (**the RATIFIED delivery roadmap + the documentation-alignment audit**, #110) → `76c7942` (**TC-1 planning**, OQ-TC-1-1..5 ratified, #111) → `c34b346` (**TC-1 IMPLEMENTATION — Wave-1 slice 1**, #112) → `df04e1d` (TC-1 closeout memory, #113) → `ec1f582` (**VAR-HS-1 planning**, OQ-VAR-HS-1-1..7 ratified, #116) → `29ae31b` (**VAR-HS-1 IMPLEMENTATION — Wave-1 slice 2 — the FIFTH governed risk number**, **CI #117 green**) → `a4d0f89` (**P3-C2 hardening/consolidation planning**, OQ-P3-C2-1..6 ratified, #118) → `6fb1a13` (**P3-C2 IMPLEMENTATION — Wave-1 slice 3 — the four-follow-up paydown; scaffold relocated risk→calc; full 6-finder review, 9 folds; NO migration**, **CI green**) → `13f71df` (P3-C2 closeout memory) → `a4d0f89`…`04c4135` (**P2-7 planning** — benchmark price/level capture / ENT-052, OQ-P2-7-1..8 ratified, CI green) → `2569151` (**TD-1 planning** — test-data realism audit, Wave-1 slice 3.5 insertion, OQ-TD-1-1..6 ratified) → `ac92e0b` (**TD-1 IMPLEMENTATION — fixture-realism remediation; 4 independent finder passes; test-and-docs only; NO migration**, **CI green**) → `4534a38` (**TD-1 follow-up** — 2 more completeness-sweep folds, **CI green**) → `ea2863d` (**P2-7 IMPLEMENTATION — Wave-1 slice 4 — ENT-052 benchmark_level+benchmark_return; migration `0029`; captured returns only; full 6-finder review, ~10 folds; unblocks P3-7**, **CI green**) → `367f602` (P2-7 closeout memory) → `552b954` (**P3-7 planning** — ex-ante active risk / tracking error, OQ-P3-7-1..10 ratified) → `65e6dbe` (**P3-7 IMPLEMENTATION — Wave-1 slice 5 — the SIXTH governed risk number: `active_risk_result` ENT-027, migration `0030`, `COMPONENT_KIND_BENCHMARK`; the FIRST user-directed FULL max-effort multi-agent review ("ultrareview": 10 finders + 6 empirical verifiers + gap sweep), 21 folds incl. run_type=ACTIVE_RISK + 3 missing CI PG steps; 3 deferred findings in the record Part 6**, **CI green**) → `18d35d5` (P3-7 closeout memory, #131) → `1bf172b` (**P3-C3 — binder adjudication-consistency hardening carry-in; the P3-7 item-A deferral: TypeError + base_currency shape gate across var/var_hs/factor + the factor malformed-pin wrapper it lacked; NO migration; B+C re-deferred**, **CI #132 green**) → `6a864c9` (P3-C3 closeout memory, #133) → `4e4648e` (**WAVE-1 CLOSE review + Wave-2 re-baseline**, #134) → `601bbec` (**PM-1 planning** — governed portfolio-return series, OQ-PM-1-1..10 ratified, #135) → `b2445c7` (**PM-1 IMPLEMENTATION — Wave-2 slice 1 — the SEVENTH governed number + FIRST non-risk (the `perf` family): `portfolio_return_result` ENT-053, migration `0031`, `PURPOSE_RETURN_INPUT`+`COMPONENT_KIND_TRANSACTION`, `perf.run`/`perf.view` R-07 mint, CAP-20+REQ-PRF-001; FULL 5-finder ultrareview, 3 HIGH + 1 MED folds each with a regression test**) → `f5e16b6` (**PM-1 ruff-format CI fix**, **CI #137 green**) → `4880b36` (**P3-8 planning — via PR #1, the FIRST PR under branch protection** — OD-P3-8-A..K + OQ-P3-8-1..10 ratified) → `d769f59` (**merge of PR #2 = `86ef3ec`: P3-8 IMPLEMENTATION — Wave-2 slice 2 — the EIGHTH governed number, the SECOND perf-family one, the FIRST governed consumer of `benchmark_return`/ENT-052 (closes P3-7 OD-G): `benchmark_relative_result` ENT-054 (realized ACTIVE_RETURN/TRACKING_DIFFERENCE/TRACKING_ERROR/INFORMATION_RATIO), migration `0032`, `PURPOSE_BENCHMARK_RELATIVE_INPUT` + `COMPONENT_KIND_PORTFOLIO_RETURN`/`_BENCHMARK_RETURN`, run family `BENCHMARK_RELATIVE` REUSING `perf.run`/`perf.view` (NO mint), exact-linkage + contiguity + currency gates; FULL 4-finder local review (user-authorized in lieu of cloud ultrareview), 5 folds incl. the HIGH evidence-echo magnitude gate; the 68-char FK name caught ONLY by local PG (the 63-char identifier cap)**, **CI #142 green**) → `503a9e2` (**merge of PR #3 = `962974f`: P3-8 CLEANUP+CLOSEOUT — the clean-code standing bar (2026-07-10, "as clean as possible" — proof-of-concept build) reactivated 3 dedup folds: `compound_returns` delegates to `link_periods`; the shared tenant guard relocated to `perf/guards.py`; `_register_perf_model` registrar core**, **CI green**) → `1da87c7` (**merge of PR #4 = `3e81ef4`: BT-1 planning — VaR backtesting, OD-BT-1-A..K + OQ-BT-1-1..9 ratified**) → `868f892` (**merge of PR #5 = `e7b615d`: BT-1 IMPLEMENTATION — Wave-2 slice 3 — the NINTH governed number: SR 11-7 outcomes analysis (Kupiec POF + Basel traffic-light zone) over realized flow-adjusted P&L (PM-1) vs ONE VaR method's pinned forecasts, `var_backtest_result` ENT-055, migration `0033`, run family `VAR_BACKTEST` REUSING `risk.run`/`risk.view` (NO mint), the all-or-nothing alignment + MV-chain integrity + cross-portfolio identity gates; FULL 4-finder local review, 14 findings/13 folded incl. a HIGH NaN-VaR-value detonation and a horizon-blind Basel gate; `portfolio/guards.py` relocation (a risk binder needed the shared P3-5 guard the perf home would have fenced off)**, **CI green**). → `df92a9c` (**merge of PR #6 = `05da04a`: BT-1 CLOSEOUT** — Part 6 dispositions: 13 folds + 2 deferred-with-reasons) → `7a422aa` (**merge of PR #7 = `07e5d6a`: PA-0 planning — the capture-first split ratified (OD-PA-0-A..J + OQ-PA-0-1..8); the Okunev-White citation honestly flagged UNVERIFIED for PA-1**) → `ad3d3fe` (**merge of PR #8 = `c9d41a7`: PA-0 IMPLEMENTATION — Wave-2 slice 4 — the FIRST private-asset foundation (differentiation-thesis destination §2.1): ENT-019 `proxy_mapping` REALIZED — FR bitemporal captured private→public factor proxy weights, migration `0034`, multi-factor blend per instrument, NO sum-to-1 (a partial proxy is honest), the CURRENCY-family v1 scope ENFORCED fail-closed (a review fold — was doc-stated but ungated), `MANUAL_PROXY` ORIGIN lineage, `MARKET.PROXY_MAPPING_*` caller-side audit, `marketdata.view`/`.ingest` REUSED (no mint); a private asset is an ORDINARY instrument+valuation under a documented asset_class convention (NO new NAV schema); merged planning-FIRST after a rebase so main's decision-record citations always resolve; proportionate 2-finder review (OQ-8), 4 folds + 2 family-wide deferrals**, **CI green**). Earlier chain: Chain since P2-6: `ae2be8e` (P2-6 closeout memory, #85) → `bb73211` (**P2 closeout / P3 readiness review**; CI re-trigger `6663452` = #86) → `07607a5` (**P3-0 decision record + P3 implementation plan**, #87) → `1a8b2a4` (**P3-1 plan**, #88) → `e8e2e59` (**P3-1 implementation**, batch-pushed) → `5466a09` (**P3-2 plan**, batch-pushed) → `402cb12` (**P3-2 implementation**, #89) → `c452229` (**P3-2 closeout / P3-3 readiness anchor**, #90) → `f941d50` (**P3-3 plan + memory refresh + governance-qualifier cleanup + model-agnostic trailer rule**, #91) → `b3d3923` (**operating-discipline modernization**, #92) → `5c64cf1` (**retrospective model-upgrade audit + status-decay fixes**, #93) → `bd5ba3c` (**gate tiers + OQ-P3-3 ratification**, #94) → `7c50c43` (**P3-3 IMPLEMENTATION + review folds**, #95).
- **Local == origin:** yes (0 ahead / 0 behind); working tree carries only this closeout-docs refresh (branch `pa-0-closeout`, pending gated commit+push).
- **Latest CI:** **GREEN** — `c9d41a7` (PA-0, PR #8) merged as `ad3d3fe`, GitHub Actions success. Locally `make check` **1191** passed + local-PG (incl. the 7 new proxy-mapping RLS legs) + fe-check 52. Chain #98–PA-0 all green.
- **Migration head:** `0034_proxy_mapping` — advanced `0033_var_backtest` → `0034_proxy_mapping` at **PA-0** (`c9d41a7`): the ENT-019 table `proxy_mapping` (FR bitemporal — `weight` NUMERIC(20,12), `mapping_method` MANUAL v1; FKs `private_instrument_id` + `factor_id` + `supersedes_id`; current-head partial-unique `(tenant, private_instrument_id, factor_id)`); **NOT append-only** (FR close-out UPDATEs — no trigger, the factor_return precedent); symmetric FORCE RLS (NEVER hybrid); downgrade smoke (0034↔0033) cycled clean; every DDL identifier ≤ 63, asserted at import (the P3-8/BT-1 lesson made structural). **Next migration lands at the next separately-approved implementation slice.**
- **Networking note (this machine):** **origin was flipped SSH→HTTPS at P3-C3 (2026-07-09)** — SSH port 22 is BLOCKED on the current network (`ls-remote`/push time out; SSH-over-443 also fails, broken pipe). **HTTPS is the working path** (github.com, REST API, and authenticated push all fast; keychain PAT cached) — plain `git push origin main` now works, no hotspot or URL-push workaround. CI verification via the public REST API always works. A full-repo safety bundle exists at `../irp-p3-3-7c50c43.bundle`.

## Working tree (uncommitted)
- **Branch `pa-0-closeout` — the PA-0 closeout PR** (pending gated commit+push): `pa_0_decision_record.md` Part 6 (proportionate 2-finder review — no HIGH bugs; 4 folds incl. the ENFORCED CURRENCY-family scope + the correction-audit `action` convention; 2 family-wide deferrals: the FR supersede window-coherence guard, the marketdata `IntegrityError`→409 mapping) + this docs refresh (roadmap/phase-ledger/current_state/next_actions). Docs-only — NO migration/permission/audit change.

## Current active gate
**WAVE 1 IS CLOSED — `wave_1_close_review.md` RATIFIED (2026-07-09, OQ-W1C-1…6); the RATIFIED Wave-2 sequence
(`delivery_roadmap.md` Part 2.5: PM-1 → P3-8 → BT-1 → PA-0 → P3-6) is now the operative sequence.** The close:
honest audit (5 slices + 2 insertions, all CI-green; ~90 review findings folded; npm audit 0 at all severities);
deferral register reconciled (P3-3/P3-5/P3-C1 deferrals all PAID in-wave; open items trigger-based incl. P3-7
B+C); outward benchmark review; the thesis destination check answered "forward, in dependency order" — Wave 2 is
organized around the **return-series triple unlock** (ex-post TE/IR + VaR backtesting + the desmoothing substrate
share ONE missing primitive, the governed portfolio-return series → PM-1 first). P3-6 moved to Wave-2 slot 5
(pre-authorized). npm CI gate tightened high→moderate at the close; **branch protection (OD-050) ✅ DONE
2026-07-10 — `enforce_admins=everyone` + 5 required CI checks; no direct pushes to `main`, PR flow binds
everyone (P3-8 onward).** **PM-1 (slice 1) DONE — `b2445c7` + `f5e16b6`, CI #137 green; the SEVENTH governed
number, FIRST non-risk (the `perf` family). P3-8 (slice 2) DONE — planning PR #1 `4880b36`, impl PR #2 `86ef3ec`
(merge `d769f59`, CI #142), cleanup+closeout PR #3 `962974f` (merge `503a9e2`); the EIGHTH governed number
(ex-post benchmark-relative AR/TD/TE/IR, ENT-054, migration 0032). BT-1 (slice 3) DONE — planning PR #4
`3e81ef4` (merge `1da87c7`), impl PR #5 `e7b615d` (merge `868f892`, CI green); the NINTH governed number
(VaR backtesting — Kupiec POF + Basel zone, ENT-055, migration 0033); FULL 4-finder local review, 14
findings/13 folded; closeout PR #6. PA-0 (slice 4) DONE — planning PR #7 `07e5d6a` (merge `7a422aa`;
capture-first split ratified; the Okunev-White citation flagged UNVERIFIED for PA-1), impl PR #8 `c9d41a7`
(merge `ad3d3fe`, CI green); the FIRST private-asset foundation: ENT-019 `proxy_mapping` REALIZED (migration
0034); proportionate 2-finder review, 4 folds + 2 family-wide deferrals. Next: THIS closeout PR (branch
`pa-0-closeout`), then **MD-H1** (slice 4.5 — a user-ratified 2026-07-11 Part-4-rule-3 hardening insertion
paying the three bug-shaped register items: FR supersede window-coherence guard, IntegrityError→409 capture
mapping, registrar first-registration race; NO migration), then P3-6 planning (stress/scenario — the LAST
Wave-2 slice; may defer again at the close, an expected outcome) on explicit direction, then the Wave-2 close
review (incl. the PA-1 sequencing decision).**
Prior state: P3-0 … P3-5 + P3-C1 + FE-1 + TC-1 + VAR-HS-1 + P3-C2 + TD-1 + P2-7 + P3-7 + P3-C3 + PM-1 + P3-8 + BT-1 + PA-0 all complete and CI-green.
Earlier slice detail: **P3-C3**
(`1bf172b`, CI run #132 green) — a hardening CARRY-IN (not a numbered slice) paying the P3-7 ultrareview's item-A deferral: binder
adjudication consistency (`TypeError` + a `base_currency` 3-letter shape gate across var/var_hs/factor so every
binder fails-close identically on malformed pins; factor_service also gained the malformed-pin wrapper it
lacked). Test-and-binder only; NO migration/permission/audit. Items B (shared covariance adjudicator) + C
(lineage batching) formally re-deferred (record OD-E). Before it, **P3-7** (`65e6dbe`,
CI run #130 green; plan `552b954`) closed Wave-1 slice **5** — the **SIXTH governed risk number: ex-ante active risk /
tracking error** `TE = √(wₐᵀΣwₐ)` (Grinold-Kahn/Roll, daily unannualized, EX-ANTE only — ex-post deferred on
the portfolio-return prerequisite, OD-G): `active_risk_result` (ENT-027 third realization, migration `0030`,
IA append-only, 3 hard-FK provenance columns incl. `benchmark_id`); `ACTIVE_RISK_INPUT` snapshot pinning
FACTOR_EXPOSURE + COVARIANCE + FACTOR + the newly minted `COMPONENT_KIND_BENCHMARK` (FR-version pins, TR-09);
registered `risk.active_risk.parametric` v1 (code_version-only identity); run family `ACTIVE_RISK`, metric
`TRACKING_ERROR`; fail-closed adjudication (NO imputation). **The FIRST user-directed FULL max-effort
multi-agent review ("ultrareview"): 10 finder angles + 6 empirical verifiers + a gap sweep — 21 findings
folded** (incl. the run_type family/metric split, kernel-overflow→committed-FAILED, adjudication hardening
each test-pinned, and 3 previously-missing CI PG RLS steps), 3 refuted/rejected-as-designed, **3
recorded-deferred in `p3_7_decision_record.md` Part 6** (var_service V2/V5 twins; shared covariance
adjudicator; lineage batching). **Remaining Wave-1: P3-6 (stress/scenario) then the Wave-1 close review**
(planning on explicit direction). Model/effort recommendation standing rule (2026-07-08): append a
next-step model+effort suggestion to every gate briefing (Sonnet/medium for commit-and-closeout mechanics;
Opus 4.8/high for templated implementation with a shipped exemplar like P3-C2; Fable/high for novel
methodology/planning/review-synthesis — extra-high/max reserved for wave-close benchmark reviews or gnarly
debugging). Strict planning-first cadence + the gate tiers hold. **Frontend visibility: the FE-1 read-only view
EXISTS (dev-shim session, permanent DEV banner) and now ALSO surfaces VAR-HS-1 runs with zero frontend changes;
anything further (dashboards, charts, mutations, more domains) remains explicitly gated.**

## P3-7 key deliverables (closed, `65e6dbe`, CI-green run #130) — Wave-1 slice 5; the SIXTH governed RISK number (record `p3_7_decision_record.md`)
**Ex-ante active risk / parametric tracking error** (OD-P3-7-A…H; plan `552b954`): `TE = √(wₐᵀΣwₐ)` — active
weights `wₐ = w_p − w_b`, BOTH sides mapped through the ONE allocation-v1 currency-factor model
(`build_factor_index` — Barra-style symmetry); daily UNANNUALIZED; EX-ANTE only (ex-post TE / active return /
IR deferred on a governed portfolio-return series — OD-G).
- **`active_risk_result`** (ENT-027, third realization; migration `0030`): single-summary-row grain
  `(calculation_run_id, metric_type='TRACKING_ERROR')`; IA TRUE append-only; symmetric FORCE RLS; hard-FK
  provenance `factor_exposure_run_id`/`covariance_run_id`/`benchmark_id` + `benchmark_effective_date` +
  `portfolio_value` evidence. **Run family `ACTIVE_RISK` ≠ metric `TRACKING_ERROR`** (a review amendment to
  OD-F — the family hosts the reserved ex-post metrics).
- **`ACTIVE_RISK_INPUT`** snapshot: FACTOR_EXPOSURE + COVARIANCE IA-row pins + FACTOR EV pins + the newly
  minted **`COMPONENT_KIND_BENCHMARK`** (FR-version constituent pins — supersede/correction invisible, TR-09;
  pin invariance test-proven under upstream re-runs AND a benchmark restatement). Binding predicate
  `v1:fexp-rows+cov-rows+cov-factors+benchmark-set` (+ an import-time varchar(50) guard over ALL predicates).
- **Registered `risk.active_risk.parametric` v1** — code_version-only identity (NO numeric parameter);
  methodology doc `active_risk_parametric_v1.md`; `risk.view`/`risk.run` REUSED; `RISK.ACTIVE_RISK_CREATE`
  reserved-not-minted; consume-path golden **0.007211102551**; fail-closed adjudication (NO imputation:
  NULL/blank currencies, unmappable currency, zero book, Σw_b ≤ 0, coverage gaps, duplicate pins of EVERY
  kind all refuse pre-create; kernel magnitude overflow → committed FAILED, never a 500).
- **Review (Part 6):** the FIRST user-directed FULL max-effort multi-agent "ultrareview" — 10 finder angles →
  22 deduped candidates → 6 verifiers with empirical probes → gap sweep. **21 folds** (correctness hardening
  each test-pinned; 3 previously-missing CI PG RLS steps incl. two PRE-EXISTING gaps; the run_type split; the
  fexp-rows rename), 3 refuted/rejected-as-designed (kept), **3 recorded-deferred**: the `var_service.py`
  TypeError/base_currency twins, the shared covariance-pin adjudicator extraction, `_persist_snapshot`
  lineage batching. Validation post-fold: make check 1044 / full-PG 230 / downgrade smoke / fe-check 43 +
  build / diff fence clean.

## P3-C2 key deliverables (closed, `6fb1a13`, CI-green) — Wave-1 slice 3; hardening/consolidation (record `p3_c2_decision_record.md`)
The four recorded FE-1/P3-C1/P3-5 follow-ups swept in one slice; NO new governed number/entity/permission/audit code; NO migration.
- **OD-B — exposure on the shared scaffold.** `run_exposure` adopts `execute_governed_run`, RELOCATED `risk/scaffold.py`→`calc/scaffold.py` (neutral home; keeps the ratified `test_scope_fence_no_risk_imports_or_identifiers` exposure↛risk fence clean — Part 4.5). FAILED exposure runs now PERSIST `failure_reason` and keep the snapshot→run DEPENDS_ON edge; COMPLETED-path behavior byte-preserved (golden at `test_p3c2_exposure_scaffold.py`, held to the P3-C1 audit-sequence + DQ-identity bar).
- **OD-C — exposure in the FE listing.** New `exposure.view`-gated `GET /exposure/runs` + `list_exposure_runs` (`irp_shared/exposure/queries.py`, fenced to `EXPOSURE_AGGREGATE`). FE runs view SOURCE-SWITCHES per family (not a client-side merge — Part 4.6); heading is now family-neutral "Runs"; `ExposureRunSummaryOut` carries `model_version_id: str|None` (always None) for byte parity with risk.
- **OD-D — captured-input `PreciseDecimal` parity.** Every captured decimal column with precision ≥16 converted (position/valuation/marketdata/reference + `transaction.{quantity,price,gross_amount}` via the review); `coupon_rate(12,6)`/`bump_bps(10,4)`/`confidence_level(6,4)` stay plain. DDL-identical on PG; invariant pinned by `test_p3c2_precision_parity._CONVERTED` (14 cols).
- **OD-E — DQ-rule first-registration race.** `ensure_presence_rule` wraps the INSERT in `begin_nested()` + `except IntegrityError` re-SELECT — 500-on-race → clean resolve, no dangling audit (`test_p3c2_dq_rule_race.py`).
- **Review (Part 6):** full 6-finder, 9 findings ALL folded (model_version_id parity, transaction completeness, exposure golden-bar proofs, exposure PG coverage `test_exposure_runs_pg.py`, doc conformance); 2 finders clean. Validation: make check 968 / full-PG 1177 / alembic no-op / downgrade clean / fe-check 39 + build / diff fence clean (30 files).

## VAR-HS-1 key deliverables (closed, `29ae31b`, CI-green run #117) — Wave-1 slice 2; the FIFTH governed risk number
**Historical-simulation VaR** (OD-VHS-A…G; plan `ec1f582`, #116): plain equal-weight factor-based historical
simulation — `risk.var.historical` v1 registered model family (declared confidence/horizon/window/quantile-
convention; the empirical lower order statistic `k=⌈N(1−c)⌉` over pinned factor-return windows; NO distributional
assumption). Reuses `var_result` (ENT-027) via `metric_type='VAR_HISTORICAL'`; additive migration
`0028_var_historical` makes `z_score`/`sigma`/`covariance_run_id` nullable, GUARDED by a new metric-conditional
`ck_var_result_parametric_not_null` CHECK constraint (the parametric method's NOT-NULL invariant stays
DB-enforced); the downgrade is DESTRUCTIVE (deletes `VAR_HISTORICAL` rows — unrepresentable pre-0028) and RLS-safe
(disables FORCE RLS + the append-only trigger transactionally around the delete — cycled twice in both directions
with real exit codes over suite-created data). New snapshot purpose `VAR_HS_INPUT` (`SNAPSHOT_PURPOSES` member) +
`build_var_hs_snapshot` (FACTOR_EXPOSURE IA-row pins + aligned per-factor FACTOR_RETURN bitemporal window pins).
Two new endpoints (`POST /risk/models/var-historical`, `POST /risk/vars-historical/runs`); reads flow through the
EXISTING parametric VaR GET family + the FE-1 listing with **zero frontend changes**. Methodology doc
`var_historical_v1.md` carries CITED external benchmarks (BoE WP525, Pritsker 2006, arXiv 2505.05646, BIS
d305/d457 — the ratified roadmap's Part 4 rule 6, its first discharge). **Independent 6-finder review: 30 filings
folded into 16 fixes**, incl. TWO ratification amendments recorded in the record's Part 5: **OD-VHS-E tightened**
(the adequacy floor `N≥⌈1/(1−c)⌉` still permitted `k=1`, the sample minimum, at its own boundary — now
`N·(1−c)>1` strictly, 21@0.95/101@0.99, enforced at BOTH the registrar and the declared-parameter re-check — the
generic-registration floor-bypass is closed too); **OD-VHS-C widened** (the third nullable column + the CHECK
constraint + the destructive/RLS-safe downgrade, above). Kernel/binder precision fixes (the magnitude-FAILED gate
was dead code — now reachable and test-proven on both engines); registry-honesty corrections to the parametric
model's own limitation text (it no longer denies the shipped method exists). 26 backend tests (a hand-minted
adjudication vehicle now drives 16 gate probes, incl. a cross-tenant provenance regression that had silently
survived the original suite). `audit/service.py` FROZEN; zero new permissions. Full-PG **1142 passed** at
implementation time.

## FE-1 key deliverables (closed, `678a651`, CI-green run #108) — the FIRST VISIBLE UI slice; NO migration
The read-only **"risk runs & results" view** (OD-FE-1-A…H; plan `416cb1d`, #107): TWO screens — the **runs list**
(the four RISK families; run_type/status filters; has-more offset pagination via a PAGE_SIZE+1 probe; truncated
`failure_reason`; whole-row click-through) and the deep-linkable **run detail** (`/runs/:family/:runId` — provenance
verbatim in monospace, per-family result tables, a FAILED run's persisted reason rendered prominently — the P3-C1
column's designed first consumer; **decimal strings rendered byte-for-byte, never Number()** — tested with
NON-round-tripping constants). **The ONE backend addition:** `GET /risk/runs` (`irp_shared/risk/queries.py` +
router; `risk.view`; explicit tenant predicate + RLS; the four RISK run_types ONLY — `EXPOSURE_AGGREGATE` fenced
out and its request a 422; fail-closed filters; `created_at DESC, run_id` deterministic order; items-only; NO audit
on reads). **Dev-session posture:** header-shim session (`sessionStorage`; printable-ASCII validation at entry AND
on load) under a permanent non-dismissable "DEV SESSION — identity is unverified" banner; honest 401/403 states on
BOTH screens; enforcement stays server-side; SSO unchanged at P6+. **Dependencies:** runtime = react/react-dom/
react-router-dom ONLY; jsdom + @testing-library/react as dev-only test tooling (disposition recorded in the
record). Vite dev proxy — NO backend CORS. **16 review findings folded** (Part 7): 2 stale-response races; runId
URL-injection (encodeURIComponent + attack-shaped test); the has-more pager; non-ASCII session-id refusal; the
fence test re-pinned to LITERALS with the real `EXPOSURE_AGGREGATE` witness; deterministic tie-break ids; **NEW
`test_risk_runs_pg.py`** (irp_app RLS posture) + its ci.yml step; RunDetail honest 401/403; row-click navigation
(the user caught this live); strengthened proofs (path pins, DOM order, pager click-through, all four families).
`apps/frontend/README.md` = the verified demo run-book (uvicorn + vite + a TESTED seeding snippet). 12 + 2 backend
tests, 37 frontend tests. **Recorded follow-ups:** the vite5/vitest2 toolchain major-bump slice (+ production-deps
`npm audit` in CI); exposure runs in the listing (`exposure.view` family).

## P3-C1 key deliverables (closed, `0599f7f`, CI-green run #105) — the hardening/consolidation slice; NO new governed number
The deferral-register paydown (OD-P3-C1-A…H; plan `c2e85ac`, CI #104): **(B) the REGISTERED-status bind** —
`assert_model_version_of` (the risk-family gate all four binders route through) now requires
`version.status == "REGISTERED"` → `UnregisteredModelError`; AND (the review's principal fold) **all FOUR governed
registrars refuse a non-REGISTERED same-label twin** (`WrongModelVersionError` 422) — register/run consistency (the
generic resolver + P7 validation semantics untouched). **(C) persisted `calculation_run.failure_reason`** (additive
Text; migration `0027_run_failure_reason`; `update_run_status(failure_reason=)` persists on the FAILED transition
ONLY; the audit payload UNCHANGED — DQ rows remain the durable evidence; the four GET-run endpoints surface it; all
four binder reason formats preserved VERBATIM). **(D) the run-scaffold extraction** —
`calc/scaffold.py::execute_governed_run` (**relocated from `risk/scaffold.py` at P3-C2** so exposure could adopt it
without crossing the one-way exposure↛risk fence; create_run → RUNNING → DEPENDS_ON → compute → fail-closed gate →
FAILED+reason | rows+ORIGIN+COMPLETED) consumed by all four risk binders AND exposure under the R0
behavior-preservation bar, **proven
by golden captures written green PRE-extraction** (`test_p3c1_scaffold_preservation.py`: audit sequences + lineage
CONTENT + DQ-rule CONTENT + exact reason formats; one finder re-ran the goldens against the stashed pre-extraction
code). **(E) `PreciseDecimal` parity** for the 8 float53-unsafe result columns (`sensitivity_value(28,12)`,
`loading(20,12)`, `exposure_amount(28,6)`×2, `signed_quantity(28,8)`, `mark_value(20,6)`, `fx_rate(28,12)`,
`z_score(20,12)` — the review fold); PG DDL identical, NO migration. **(F) the MRO-walking `deps.map_refusal`**
shared by the risk/exposure/snapshot routers (a subclass of a mapped refusal no longer 500s). **(G) both-modes
ambiguity refusal ×5 binders** covering EVERY build-mode argument incl. the as-of args (exposure's `base_currency`
deliberately excluded — verified honored on the snapshot path); checks sit BEFORE the model gate (request-shape
first). **(H) the P3-3 mixed-base adjudication check** (`_adjudicate_pins` base-currency uniformity — the latent
hole closed at adjudication, grain unchanged). **12 review findings folded; 1 residual recorded** (the DQ-rule
first-registration race — pre-existing, faithfully preserved; a deliberate-behavior-change slice if wanted).
**Recorded follow-ups:** exposure-family scaffold/`failure_reason` adoption; captured-input-table PreciseDecimal
parity. 1111 PG-backed tests; `audit/service.py` FROZEN; zero new permissions/audit codes/entities.

## P3-5 key deliverables (closed, `5ed8271`, CI-green run #102) — ENT-027 REALIZED; the FIRST derived-of-derived number
**`var_result`** (**ENT-027 `risk_result` REALIZED**; migration `0026_var`; **IA TRUE append-only** + P0001 trigger +
symmetric RLS): zero-mean delta-normal 1-day parametric VaR — `σ_p = √(xᵀΣx)`, `VaR = z·σ_p` — over the pinned
result rows of TWO upstream governed runs (`x` = a COMPLETED FACTOR_EXPOSURE run's per-factor totals; `Σ` = a
COMPLETED COVARIANCE run), the platform's first SINGLE-SUMMARY-ROW result (grain `(calculation_run_id,
metric_type)`; `VAR_PARAMETRIC`, ES reserved) with **hard-FK provenance columns** `exposure_run_id`/
`covariance_run_id` (re-resolved own-tenant on BOTH paths pre-create — PG FK checks bypass RLS; the review's
principal fold). **Declared-parameter version identity** (OD-P3-5-D): confidence/horizon/z are strict-parsed
`model_assumption`s (vocab {0.9500, 0.9900}; dual-verified 12dp z constants; horizon must equal `1` verbatim; NO
runtime inverse-CDF). Fail-closed adjudication on BOTH paths: coverage (exposure factors ⊆ covariance factors, NO
zero-variance imputation), single-run provenance, uniform base currency, canonical-order + duplicate refusals,
source-column magnitude envelopes, structurally-malformed-content 422s. The declared radicand quantization floor
(`tol = F²·max(xᵢ²)·1e-19`; clamp within, committed FAILED below — REACHABLE and test-proven) + a magnitude gate
(σ beyond Numeric(28,6) ⇒ FAILED, never a PG overflow 500). σ/VaR carried as `PreciseDecimal(28,6)`. Dual-path
verification: exact hand references (σ=500/700/7) through the kernel AND the governed consume path; `numpy`
cross-check @1e-9; erf round-trip + bisection of the z constants; NON-VACUOUS pin invariance (upstream supersede
moves a fresh build but not the pin). `RISK.VAR_CREATE` reserved-not-emitted; **`risk.*` REUSED — zero new
permissions**; `var_parametric_v1.md` methodology (**specific-risk = 0 the first-class limitation**); 4 endpoints;
the VaR PG CI step; 52 new tests. **13 review findings folded; 2 recorded deferrals** (the
`assert_registered_model_version` status-bind check — cross-slice, a P3-6-planning carry-in; shipped result-column
float parity — a dedicated PreciseDecimal parity slice) — **both PAID DOWN at P3-C1 (`0599f7f`)**. **REQ-MKT-001 → In-Progress (parametric leg);
historical-sim + MC = user-directed ROADMAP method slices.**

## P3-4 key deliverables (closed, `c2bd126`, CI-green run #99) — the THIRD governed RISK number REALIZED
**`covariance_result`** (**ENT-051 `covariance_matrix` MINTED** — the Part-3 process; migration `0025_covariance`;
**IA TRUE append-only** + P0001 trigger + symmetric RLS): the equal-weighted UNBIASED (N−1) sample covariance of
pinned `SIMPLE`/`DAILY` factor-return windows — one row per canonical unordered pair INCL. the diagonal (the
variances; `F·(F+1)/2` rows per run); grain `(calculation_run_id, factor_id_1, factor_id_2)` with binder-enforced
lowercase-GUID canonical ordering (no CHECK). **Window-as-version-identity** (OD-P3-4-G): `window_observations=N`
is a `model_assumption` on the registered `risk.covariance.sample` v1 (strict-digit parse; a malformed/absent
declaration = `WrongModelVersionError` 422; same-label different window/code_version = 409). Snapshot pins:
`COMPONENT_KIND_FACTOR_RETURN` MINTED (per-date **bitemporal** version pins — the review fix; the frozen header
cutoffs reproduce the pin under backdated/future-effective supersedes) + `PURPOSE_COVARIANCE_INPUT` +
`build_covariance_snapshot` (fail-closed common-date alignment — no imputation/pairwise). `run_covariance` mirrors
the hardened P3-3 shape: uniform pre-create adjudication of PINNED content on BOTH paths (<2 series / wrong-N /
misaligned / unpaired / non-SIMPLE/DAILY / duplicate-series all refuse before any run); defensive post-compute DQ
gate (`risk.covariance.completeness`); DEPENDS_ON-before-gate; per-row ORIGIN. **New portable `PreciseDecimal`
type** (`db/types.py`): PG `NUMERIC(38,20)` / SQLite fixed-scale TEXT (a 20dp value does NOT survive SQLite's
float roundtrip; bind-quantize inside a WIDE localcontext; −0 normalized). Kernel: pure Decimal-50, HALF_UP-20,
PSD by Gram construction; **the dual-path verification rule's first discharge** (hand-derived rational references
= kernel = `numpy.cov(ddof=1)` at ε_rel 1e-9; eigenvalue floor λ_min ≥ −1e-12·trace; numpy TEST-ONLY,
runtime-fenced). `RISK.COVARIANCE_CREATE` reserved-not-emitted @ EVT-220; **`risk.view`/`risk.run` REUSED — zero
new permissions**; `covariance_sample_v1.md` methodology; 4 endpoints; the Covariance PG CI step; 57 new tests.
**12 review findings folded** incl. a cross-slice catch: the P3-3 PG hybrid-set probe was VACUOUS (wrong
SYSTEM_TENANT_ID) — both PG suites now probe the real id + assert set EQUALITY. Deferred (recorded): shrinkage/
EWMA/correlation/annualization (v2 versions); max-lookback bound; asset-level covariance; run-scaffold extraction.
**R0 pre-step** (`a9b6567`, CI #98): behavior-preserving extraction of the shared DQ presence-gate helpers
(`dq/gates.py`) + `_persist_snapshot` — the 3×-snapshot-assembly / 4×-DQ-gate duplication debt paid pre-slice.

## P3-3 key deliverables (closed, `7c50c43`, CI-green run #95) — the SECOND governed RISK number REALIZED
**`factor_exposure_result`** (ENT-028 family — **no new canonical id**; migration `0024_factor_exposure`; **IA TRUE
append-only** + P0001 trigger + symmetric RLS; grain `(calculation_run_id, portfolio_id, instrument_id, factor_id)`;
`factor_id` deliberately NOT a hard FK — the `COMPONENT_KIND_FACTOR` pin is authoritative). **Allocation v1:**
indicator loading (= 1, quantized to the Numeric(20,12) quantum) over the pinned atoms of a COMPLETED
`exposure_aggregate` run × pinned CURRENCY-family `factor` definitions, matched on the atom's captured
`mark_currency`; contributions sum to the pinned total **exactly (ε=0)** — **REQ-MKT-003 → In-Progress (partial)**.
`run_factor_exposure` mirrors the P3-1 exemplar + the review hardenings: **uniform pre-create adjudication of PINNED
content on BOTH entry paths** (zero-atom / zero-factor / wrong-family / NULL-scope / duplicate-currency snapshots
refuse before any run exists); **model-identity assert** `assert_model_version_of` (a sensitivity model_version
cannot drive a factor-exposure run — twin-fixed into `run_sensitivities`); **conflict-safe model registration**
(`ModelVersionConflictError` → 409; twin-fixed); gap-naming `failure_reason` on FAILED runs; snapshot
`COMPONENT_KIND_EXPOSURE` (the first IA pin flavor) + `COMPONENT_KIND_FACTOR` + `PURPOSE_FACTOR_EXPOSURE_INPUT` +
a truthful `FACTOR_EXPOSURE_BINDING_PREDICATE`; `RISK.FACTOR_EXPOSURE_CREATE` reserved-not-emitted @ EVT-220;
**`risk.view`/`risk.run` REUSED — zero new permissions**; `factor_exposure_allocation_v1.md` methodology + governed
`register_factor_exposure_model`. **ci.yml restored to the COMPLETE per-table PG suite set** (benchmark, holdings,
synthetic, sensitivity, factor, factor-exposure — six suites absent from CI since the P2-5-era list; #95 ran all
green). 60 new tests incl. 8 review-regression tests; the snapshot→exposure import boundary fenced (function-local
models-only — module-level is a proven circular import). `COMPONENT_KIND_FACTOR_RETURN` was still unminted at
P3-3 close (MINTED at P3-4, its designed first consumer). `audit/service.py` FROZEN. Deferred (recorded): vendor-beta/regression exposures;
ASSET_CLASS+ dimensions; `_ERROR_MAP` exact-type lookup; both-modes silent snapshot preference; latent mixed-base
grain; GET `failure_reason` persistence; the 3×-snapshot-assembly / 4×-DQ-gate / 3×-run-scaffold extractions
(a dedicated cleanup slice — a P3-4 planning carry-in).

## P3-2 key deliverables (closed, `402cb12`, CI-green run #89) — captured factor-return inputs REALIZED
Net-new **`factor` EV definition** (canonical id MINTED; identity `(tenant, factor_code, factor_source)`; `factor_family`
{STYLE, INDUSTRY, COUNTRY, MACRO, MARKET, CURRENCY, OTHER}; optional `factor_type`/`region`/`currency_code`/`asset_class`
scope; `frequency` DAILY v1; `REFERENCE.CREATE`/`UPDATE`-audited) **+ `factor_return` FR bitemporal captured series**
(ENT-025; grain `(tenant, factor_id, return_date, return_type)` current-head partial-unique; `return_value` decimal
fraction `Numeric(20,12)`; `return_type` SIMPLE (LOG reserved); capture/supersede/correct + both-axes
`reconstruct_factor_return_as_of`; `MARKET.FACTOR_RETURN_CREATE`/`_UPDATE`/`_CORRECTION`-audited). Migration
`0023_factor_return` — symmetric tenant RLS (never hybrid), **NEITHER table append-only**. `marketdata/factor.py` binder;
VENDOR_FACTOR ORIGIN lineage; **`marketdata.view`/`.ingest` REUSED** (no `factor.*` permission); binder-side
`Decimal.is_finite()` guard (NaN/±Inf rejected pre-write) + `> -1` economic-sanity DQ RANGE; 8 endpoints; 39 factor tests.
**Captured INPUT — NO `calculation_run`, NO `model_version`, NO snapshot pin** (computed factor returns DEFERRED — would
need adjusted prices + a registered model_version). `COMPONENT_KIND_FACTOR_RETURN` readiness-noted (MINTED at P3-4).
`audit/service.py` FROZEN. Validated green on Python 3.12 + 3.14 + full PG.

## P3-1 key deliverables (closed, `e8e2e59`, CI-covered at run #89) — the FIRST governed RISK number REALIZED
ENT-028 **`sensitivity_result`** (migration `0022_sensitivity`; **IA TRUE append-only** — `APPEND_ONLY_TABLES` + P0001
trigger + ORM guard; symmetric RLS) — **curve-node analytic DV01 / spread-DV01** (`−T·DF·1bp`; ACT/365F; continuous
compounding; nodes-only/no-interpolation; ZERO_RATE/DISCOUNT_FACTOR/SPREAD; PAR_RATE rejected/deferred;
`quantize_HALF_UP(…,12)`; curve-intrinsic — NO instrument/position attribution). **The model-governance hardening:**
`run_sensitivities` calls **`assert_registered_model_version` in the pre-create gate** (fail-closed ⇒ zero run/rows/audit)
— **CTRL-003 inventory-before-use is EXECUTABLE**; the model registered via governed `register_sensitivity_model`
(`risk.sensitivity.analytic` v1; `methodology_ref` → `05_analytics_methodologies/sensitivities_analytic_v1.md`;
assumptions/limitations mirrored; `validation_status` UNVALIDATED, non-enforcing until P7). New `irp_shared/risk/` package
(`models`/`kernel`/`service`/`events`/`bootstrap`) + `api/risk.py`; snapshot `COMPONENT_KIND_CURVE` +
`PURPOSE_SENSITIVITY_INPUT` + `curve_content` + `build_curve_snapshot`; **`risk.view`/`risk.run` MINTED** (auditor_3l in
`.view`); `RISK.SENSITIVITY_CREATE` **reserved-not-emitted** @ EVT-220; `CALC.RUN_*` reused; lineage `snapshot
--DEPENDS_ON--> run --ORIGIN--> result` (DEPENDS_ON recorded BEFORE the DQ gate); fail-closed
`risk.sensitivity.completeness` DQ; the methodology framework + first methodology doc. `audit/service.py` FROZEN.

## P3-0 key decisions (ratified, `07607a5`, CI-green run #87) — the P3 contract
OD-P3-0-A…N + the OQ-P3-0-1…10 sign-offs: **analytic-sensitivities-first** (NOT VaR/ES); the **derived-number output
contract** (every official risk result binds `dataset_snapshot` + `calculation_run` + a **registered `model_version`**
where a model applies + `code_version` + `environment_id`; IA append-only; snapshot-only compute; reproducible under
correction; pre-create-refusal / post-create-FAILED failure model); **`code_version`-only reserved for convention-free
transforms** (the P2-3 rollup — sole precedent); the methodology home `05_analytics_methodologies/` + the §-template;
`RISK.*` reserved @ EVT-220 + `CALC.RUN_*` reuse; `risk.view`/`risk.run` reservation; component kinds minted additively
per consumer; risk results IA append-only; validation-workflow enforcement deferred to P7; the captured-data gap register
(vol surface / adjusted prices / ratings / benchmark levels — later-subphase prerequisites only). Subphase map P3-1…P3-7
in `p3_implementation_plan.md` (sequencing a recommendation, not a strict chain; VaR/ES last; stress RTM-P5).

## P2 captured market-data foundation — COMPLETE (CI-green)
The full reproducibility-first P2 block is delivered and CI-green: **P2-1** `dataset_snapshot` (`3629baa`, the AD-014 reproducibility
primitive) · **P2-2** `fx_rate` (`c257e5c`, captured FX) · **P2-3** `calculation_run`+`exposure_aggregate` (`da178fc`, the first
governed derived number — MARKET_VALUE only) · **P2-4** `price_point` (`2b63b76`, captured prices) · **P2-5** `curve`+`curve_point`
(`49ca3bd`, captured curves) · **P2-6** `benchmark`+`benchmark_constituent` (`b6284a4`, captured benchmarks). The reproducibility
primitive + the captured market-data inputs (FX, prices, curves, benchmarks) + the first governed derived number (exposure) are all
realized. **NO risk analytics yet** — VaR/ES/factor/covariance/stress/scenario/attribution/tracking-error stay **P3+**.


> **Per-slice deliverable detail for CLOSED phases (P0.5–P2-6, P1B, P1C) was thinned out of this file on
> 2026-07-06** — it lives in `phase_status.md` (the ledger), the `10_delivery_backlog/` decision records /
> plans / closeout docs, and this file's own git history. Only the active-phase (P3) sections are kept here.

## Completed phases
- **P0.5** engineering hygiene & foundation (scaffold, audit framework, RLS foundation, CI).
- **P1A-0…P1A-4** the cross-cutting rails — `7cdc2f9`, `96a1564`, `c9be657`, `cc472be`, `c781bb8` (+ PG fix `0282359`). **P1A milestone CLOSED.**
- **P1A closeout / P1B readiness** — `69afedf`.
- **P1B-0 decision record + plan** — `dbed93e`; **ratifications into governance** — `4fae26b`; **project-memory artifacts** — `b1efc05`.
- **P1B-1 implementation plan** — `05ee5f5`.
- **P1B-1 reference-data implementation** — `6568cb1` (CI-green, run #28). **P1B-1 CLOSED.**
- **P1B-2 implementation plan** — `410cc7e` (CI-green, run #29).
- **P1B-2 reference-data implementation** — `32c7778` (CI-green, run #31). **P1B-2 CLOSED.**
- **P1B-3 implementation plan** — `43c042e` (CI-green).
- **P1B-3 reference-data implementation** — `8545ed6` (CI-green, run #34). **P1B-3 CLOSED.**
- **P1B-4 implementation plan** — `f6d691a` (CI-green).
- **P1B-4 reference-data implementation** — `060b2a4` (CI-green, run #37). **P1B-4 CLOSED → P1B block DELIVERED.**
- **P1B closeout / P1C readiness review** — `e99633a` (CI-green, run #39).
- **P1C-0 decision record + P1C implementation plan** — `705d3ba` (CI-green, run #40).
- **P1C-1 portfolio-hierarchy implementation plan** — `b52ad9e` (CI-green, run #41).
- **P1C-0 ratification into governance** — `dca7bc0` (AD-017 + REQ-PPM-001 + PORTFOLIO.* reserved + OD-013/OD-025 closed; CI-green, run #42).
- **P1C-1 portfolio-hierarchy + ABAC scope anchor implementation** — `bb89c74` (CI-green, run #43). **P1C-1 CLOSED** — the first domain entity.
- **P1C-1 closeout project-memory refresh** — `d1d6829` (CI-green, run #44).
- **P1C-2 transaction implementation plan** — `c398215` (CI-green, run #45).
- **P1C-2 transaction capture (IA append-only) implementation** — `abb230f` (CI-green, run #46). **P1C-2 CLOSED** — the first domain IA / append-only entity.
- **P1C-2 closeout project-memory refresh** — `f3fd7c9` (CI-green, run #47).
- **P1C-3 position implementation plan** — `42cc02c` (CI-green, run #48).
- **P1C-3 position capture (FR bitemporal) implementation** — `4ee124e` (CI-green, run #49). **P1C-3 CLOSED** — the first FR domain entity.
- **P1C-3 closeout project-memory refresh** — `2f7d647` (run #50) + cleanup `b38f182` (run #51).
- **CI hygiene** — `67741fb` (run #52): GitHub Actions bumped to Node-24 majors (`checkout@v5`/`setup-python@v6`/`setup-node@v5`); Node-20 deprecation warning eliminated.
- **P1C-4 valuation implementation plan** — `92a0264` (CI-green, run #53).
- **P1C-4 valuation capture (FR bitemporal, captured marks) implementation** — `c5c5806` (CI-green, run #54). **P1C-4 CLOSED** — the second FR domain entity; **REQ-PPM-003 now Done**.
- **P1C-4 closeout project-memory refresh** — `6e3dcc1` (CI-green, run #55).
- **P1C-5 holdings-views implementation plan** — `8a14173` (CI-green, run #56; OD-P1C5-1..6 signed off).
- **P1C-5 read-only as-of holdings / portfolio views implementation** — `0bef45b` (CI-green, run #57). **P1C-5 CLOSED** — the first read-model / composition package (no entity, no migration).
- **P1C-5 closeout project-memory refresh** — `867e576` (CI-green, run #58).
- **P1C-6 deterministic synthetic dataset implementation plan** — `7dfdb79` (CI-green, run #59; audit conclusions folded; OD-P1C6-1..7 signed off).
- **P1C-6 deterministic synthetic dataset implementation** — `3e9882d` (CI-green, run #60). **P1C-6 CLOSED** — the deterministic synthetic dataset (governed seam + never-auto-run). **The FULL P1C block (P1C-1…P1C-6) is DELIVERED.**
- **P1C-6 closeout project-memory refresh** — `9584ba4` (CI-green, run #61).
- **P1C closeout / P2 readiness review** — `7070dff` (CI-green, run #62; 8-lens). Reproducibility-first P2 sequencing chosen.
- **P2-0 decision record + P2 implementation plan** — `2d19992` (CI-green, run #63; 8-lens, 0 block). OD-P2-A…L; subphases P2-1…P2-6.
- **P2-1 dataset_snapshot implementation plan** — `d7be981` (CI-green, run #64; 8-lens, 0 block). The AD-014 reproducibility-primitive build plan.
- **P2 dataset_snapshot governance ratification** — `63be23a` (CI-green, run #65; 7-lens, 7× approve). ENT-049/050 + SNAPSHOT.CREATE (EVT-190 reserved) + snapshot.* (reserved) + AD-004-R1 + REQ-PPM-004→In-Progress.
- **P2 ratification closeout project-memory refresh** — `d45a31b` (CI-green, run #66; docs-only).
- **P2-1 `dataset_snapshot` implementation** — `3629baa` (CI-green, run #67; 8-lens, 6 in-scope folds). **P2-1 CLOSED** — the AD-014 reproducible input-snapshot primitive (ENT-049/050) realized; **migration head `0015_valuation` → `0016_dataset_snapshot`** (the first migration since P1C-4) + the first new Snapshot symmetric-RLS CI step. NO exposure number, NO `calculation_run` wiring.
- **P2-1 closeout project-memory refresh** — `85ff5b2` (CI-green, run #68; docs-only).
- **P2-2 `fx_rate` implementation plan** — `6020b03` (CI-green, run #69; 8-lens, 6 in-scope folds; build-ready). The 10 specific decisions settled (FR; base/quote direction; MID; USD-base triangulation; `marketdata.*`; etc.).
- **P2-2 `fx_rate` implementation** — `c257e5c` (CI-green, run #70; 8-lens, 6 approve / 2 approve_with_changes / 0 block; 1 in-scope fold). **P2-2 CLOSED** — captured FX market data (ENT-024, FR) realized; **migration head `0016_dataset_snapshot` → `0017_fx_rate`** + the new FX symmetric-RLS CI step. NO exposure number, NO `calculation_run` wiring, NO `dataset_snapshot` change.
- **P2-2 closeout project-memory refresh** — `adf4ac5` (CI-green, run #71; docs-only).
- **P2-3 decision record + implementation plan** — `d10c766` (CI-green, run #72; 8-lens, 10 in-scope folds; the five OQ-P2-3 sign-offs). `calculation_run` wiring + basic exposure; OD-P2-3-A…L.
- **P2-3 exposure + `calculation_run` governance ratification** — `851f976` (CI-green, run #73; AD-018; 7-lens, 6 approve / 1 approve_with_changes). ENT-014 ratified-in-planning; the `CALC.RUN_START/COMPLETE/FAIL` → `CALC.RUN_CREATE/STATUS_CHANGE` doc-vs-code reconciliation; EVT-210 `EXPOSURE.*` reserved; `exposure.*` perms; CTRL-009 executable; HALF_UP canonical-serialization exception. RATIFIED-IN-PLANNING, no code.
- **P2-3 `calculation_run` wiring + basic exposure implementation** — `da178fc` (CI-green, run #74; 8-lens, 5 approve / 3 approve_with_changes / 0 block; 2 in-scope folds). **P2-3 CLOSED** — the **first governed derived number** (`exposure_aggregate`, ENT-014, IA append-only) realized; **migration head `0017_fx_rate` → `0018_exposure_aggregate`** (+ the additive `calculation_run.environment_id`) + the new Exposure symmetric-RLS CI step. The AD-014/FW-RUN/TR-15 gate is now load-bearing. NO risk (MARKET_VALUE only).
- **P2-3 closeout project-memory refresh** — `0b12d85` (CI-green, run #75; docs-only).
- **P2-4 captured price history decision record + implementation plan** — `b73e65f` (CI-green, run #76; 8-lens, 4 in-scope folds; the six OQ-P2-4 sign-offs). `price_point` (ENT-020) FR/bitemporal captured prices; OD-P2-4-A…L.
- **P2-4 captured price history implementation** — `2b63b76` (CI-green, run #77; 8-lens, 7 approve / 1 approve_with_changes / 0 block; 1 in-scope fold). **P2-4 CLOSED** — `price_point` (ENT-020, FR/bitemporal captured vendor prices) realized; **migration head `0018_exposure_aggregate` → `0019_price_point`** + the new Price-point symmetric-RLS CI step. **REQ-PUB-001 → In-Progress (partial).** NO pricing model, NO conversion, NO `calculation_run`/`exposure_aggregate`/`dataset_snapshot`/FX change.
- **P2-4 closeout project-memory refresh** — `419db9d` (CI-green, run #78; docs-only).
- **P2-5 captured yield/spread curves decision record + implementation plan** — `326ad94` (CI-green, run #79; 8-lens, 8 in-scope folds; the ten OQ-P2-5 sign-offs). The unified `curve` + `curve_point`; OD-P2-5-A…N.
- **P2-5 captured yield/spread curves implementation** — `49ca3bd` (CI-green, run #80; 8-lens, 7 approve / 1 approve_with_changes / 0 block; 1 material + 3 low folds). **P2-5 CLOSED** — the unified `curve` (FR header, ENT-021) + `curve_point` (IA append-only nodes) realized; ENT-023 `credit_spread` by value; **migration head `0019_price_point` → `0020_curves`** + the new Curve symmetric-RLS CI step. **REQ-PUB-002 + REQ-PUB-003 → In-Progress (partial).** NO curve construction/interpolation/duration/pricing/risk; NO `calculation_run`/`exposure_aggregate`/`dataset_snapshot`/`fx_rate`/`price_point` change.
- **P2-5 closeout memory** — `0c5c068` (run #81); **P2-6 plan** — `8d2782f` (run #82); **operating rules** — `1e0dc08` (run #83).
- **P2-6 captured benchmark/index data implementation** — `b6284a4` (CI-green, run #84). **P2-6 CLOSED** — `benchmark` (ENT-009, EV definition) + `benchmark_constituent` (FR membership); **migration head `0020_curves` → `0021_benchmark`**. **THE FULL P2 FOUNDATION COMPLETE.** Closeout memory — `ae2be8e` (run #85).
- **P2 closeout / P3 readiness review** — `bb73211` (CI re-trigger `6663452`, run #86).
- **P3-0 decision record + P3 implementation plan** — `07607a5` (CI-green, run #87). **OD-P3-0-A…N RATIFIED** (the P3 contract; analytic-sensitivities-first; subphases P3-1…P3-7).
- **P3-1 analytic sensitivities plan** — `1a8b2a4` (CI-green, run #88; OQ-P3-1-1…6 ratified).
- **P3-1 analytic sensitivities implementation** — `e8e2e59` (batch-pushed; CI-covered at run #89). **P3-1 CLOSED** — the first governed RISK number (`sensitivity_result`, migration `0022_sensitivity`); CTRL-003 executable; `risk.view`/`risk.run` minted; the methodology framework + `sensitivities_analytic_v1.md`.
- **P3-2 factor-return inputs plan** — `5466a09` (batch-pushed; CI-covered at run #89).
- **P3-2 factor-return inputs implementation** — `402cb12` (CI-green, run #89). **P3-2 CLOSED** — the `factor` canonical id minted + ENT-025 `factor_return` realized (migration `0023_factor_return`); captured INPUT (no run/model/snapshot binding).
- **P3-2 closeout / P3-3 readiness handoff** — `c452229` (CI-green, run #90; the resume anchor for the machine move).
- **P3-3 plan / discipline / audit / gate-tier chain** — `f941d50` (#91) → `b3d3923` (#92) → `5c64cf1` (#93) → `bd5ba3c` (#94).
- **P3-3 factor-exposure implementation** — `7c50c43` (CI-green, run #95 — the first run executing ALL per-table PG suites). **P3-3 CLOSED.** Closeout memory — `362481a`.
- **P3-4 covariance planning** — `8abe764` (OQ-P3-4-1…10 RATIFIED at the commit gate).
- **P3-4-R0 refactor pre-step** — `a9b6567` (CI-green, run #98; shared `dq/gates.py` presence helpers + `_persist_snapshot`).
- **P3-4 covariance implementation** — `c2bd126` (CI-green, run #99; 12 review folds). **P3-4 CLOSED** — the third governed risk number (ENT-051; migration `0025_covariance`). Closeout memory — `c2480a4` (#100).
- **P3-5 parametric-VaR planning** — `c2c1b4d` (CI-green, run #101; OQ-P3-5-1…10 RATIFIED + the historical-sim/MC roadmap note).
- **P3-5 parametric-VaR implementation** — `5ed8271` (CI-green, run #102; 13 review folds). **P3-5 CLOSED** — ENT-027 realized (migration `0026_var`); REQ-MKT-001 → In-Progress (parametric leg). Closeout memory — `d94e572` (#103).
- **P3-C1 hardening/consolidation planning** — `c2e85ac` (CI-green, run #104; OQ-P3-C1-1…8 RATIFIED at the commit gate after a plain-language decision briefing).
- **P3-C1 hardening/consolidation implementation** — `0599f7f` (CI-green, run #105; 12 review folds + 1 pre-existing residual recorded). **P3-C1 CLOSED** — the deferral-register paydown (migration `0027_run_failure_reason`; the run-scaffold extraction; the REGISTERED-status bind + register/run consistency; PreciseDecimal parity ×8; `deps.map_refusal`; both-modes refusal ×5; the mixed-base check). Closeout memory — `ee3c581` (#106).
- **FE-1 frontend runs-view planning** — `416cb1d` (CI-green, run #107; OQ-FE-1-1…8 RATIFIED at the commit gate; chosen on the walking-skeleton recommendation with the user explicitly deferring to best practices).
- **FE-1 frontend runs-view implementation** — `678a651` (CI-green, run #108; 16 review folds). **FE-1 CLOSED — the FIRST VISIBLE UI** (two read-only screens + `GET /risk/runs`; NO migration; dev-shim session + permanent DEV banner; user exercised it live pre-approval). Closeout memory — `945661d` (#109).
- **The delivery roadmap ratification + documentation-alignment audit** — `63a1bb8` (CI-green, run #110). Rolling-wave Wave 1 fixed; ten stale genesis-era docs aligned to the true state.
- **TC-1 FE toolchain-bump planning** — `76c7942` (CI-green, run #111; OQ-TC-1-1…5 RATIFIED).
- **TC-1 FE toolchain-bump implementation** — `c34b346` (CI-green, run #112 — the upgraded pipeline's own first run; 3-finder review: 1 fold + 1 evidence-based disposition). **TC-1 CLOSED — Wave-1 slice 1** (vite 8/vitest 4/plugin-react 6; audit 0 vulns; Node 24 CI; the audit + format gates; ZERO source changes). Closeout memory — `df04e1d` (#113).
- **VAR-HS-1 historical-simulation VaR planning** — `ec1f582` (CI-green, run #116; OQ-VAR-HS-1-1…7 RATIFIED; the record's Part 2 carries the FIRST discharge of roadmap rule 6's cited external-benchmark obligation).
- **VAR-HS-1 historical-simulation VaR implementation** — `29ae31b` (CI-green, run #117; 30 filings folded into 16 fixes incl. two ratification amendments). **VAR-HS-1 CLOSED — Wave-1 slice 2 — the FIFTH governed risk number** (`risk.var.historical` v1; migration `0028_var_historical`; the metric-conditional CHECK constraint; the RLS-safe destructive downgrade; zero frontend changes).

## Next required action
**THE RATIFIED ROADMAP SEQUENCE** (`10_delivery_backlog/delivery_roadmap.md`, Wave 1 — the sequence replaces the
per-slice option menu; re-sequencing only via its Part 4 rules): **TC-1 ✅ DONE (`c34b346`, #112)** → **VAR-HS-1 ✅
DONE (`29ae31b`, #117)** → **P3-C2** hardening bundle → **P2-7** benchmark price/level capture → **P3-7**
benchmark-relative → **P3-6** stress/scenario → the Wave-1 close review + re-baseline. Each slice still gets its
own decision record + plan + OQ ratification + adversarial review + Tier-2 commit approval, and starts only on
explicit direction. **Next concrete step: P3-C2 (the hardening bundle) planning, on direction — a templated
consolidation slice (the P3-C1 exemplar); recommend Opus 4.8/high per the model/effort standing rule.** Genuine
ambiguity inside a slice → ask the user with a recommendation attached (their standing rule, 2026-07-08).

## What MUST NOT be started yet
- **No next-slice implementation** — not until its planning is committed + ratified AND the user directs it (the planning itself also awaits explicit direction; see "Next required action").
- **No ES / Monte-Carlo implementation** — ROADMAP method slices (user-directed), each its own registered model family/version + planned slice; the ES closed-form seam (`σ·φ(z)/(1−α)`) stays a recorded seam (now with a hist-sim leg noted too); historical simulation is DONE (VAR-HS-1, `29ae31b`).
- **No multi-horizon √h scaling / component-marginal VaR / backtesting / runtime quantile function** — recorded P3-5 + VAR-HS-1 deferrals (backtesting is also a named later slice, a P7 prerequisite).
- **No FHS/volatility-filtered or BRW/time-weighted historical-VaR variants** — recorded v2 model versions of `risk.var.historical` (need a declared volatility model — EWMA/GARCH), never silent extensions.
- **No shrinkage / EWMA / correlation output / annualization / asset-level covariance** — recorded v2 `model_version`s of the covariance family, never silent extensions.
- **No stress testing / scenario analytics** — P3-6 (ENT-029/030; RTM-P5 — possibly a later phase).
- **No benchmark-relative analytics / active risk / tracking error / performance attribution** — P3-7+ (and `benchmark_level`/`benchmark_return` are themselves DEFERRED captured inputs — a net-new canonical ENT id, not minted).
- **No vendor-beta or regression factor exposures** — deferred v2 (need a captured factor-loading slice / adjusted-price return history + estimation); **no computed factor returns** (need adjusted prices + a registered model_version); `COMPONENT_KIND_FACTOR_RETURN` MINTED at P3-4 for the covariance window pin (regression v2 stays deferred).
- **No instrument/position key-rate DV01 / interpolation / bootstrapping / pricing engine / PAR_RATE / vol surface** — the P3-1 deferrals stand.
- **No frontend EXPANSION** unless explicitly approved — FE-1 shipped the read-only runs/results view (`678a651`); dashboards, charts, exports, mutations from the UI, additional domain screens, and any softening of the DEV-banner posture each gate on their own planned slice. No reporting build.
- **No limits/breach, real SSO, ABAC enforcement** — P6+ (ABAC stays anchored-not-enforced).
- **P1B-5** (reference-data ingestion mapping) — conditional/deferred (only if bulk loading is needed; not now).
- **Never** modify `packages/shared-python/src/irp_shared/audit/service.py` (frozen) or `entitlement/bootstrap.py` outside the governed R-07 mint (P3-3 mints NO new permission — `risk.view`/`risk.run` are REUSED); no new audit code / permission / role / migration without R-07. **No weakening of the P2/P3 snapshot-run-model controls; no BYPASSRLS; no hybrid/SYSTEM_TENANT behavior** beyond the closed 5-table set.

## Housekeeping / security (RESOLVED — recorded for recovery)
- A **plaintext GitHub PAT file** was observed in the **parent directory** (one level ABOVE the repo root, OUTSIDE version control — never staged/tracked). The user **deleted the file** and **revoked the token** on GitHub (2026-06-22), and migrated git auth to an **SSH key** (ed25519, passphrase cached in the macOS Keychain; `origin` switched to `git@github.com`). **Standing rule: never read/copy/print/use any credential file found on disk — flag it for the user to revoke/rotate. Do NOT inspect token contents.**

## Re-check at session start (may have drifted)
- **2026-07-14 pointer (PA-4 closeout):** the OPERATIVE executed ledger is `10_delivery_backlog/delivery_roadmap.md` (Waves 1–4 rows + the dated log table) — the per-slice narrative below this file's Wave-2 era is intentionally not duplicated here. Main HEAD ≥ `8ef70db6` (PA-4, **PR #30**); migration head **`0038_var_residual_variance`** (thirteen governed numbers; the chain since this file's last deep refresh: `0036` PA-1 desmoothing, `0037` PA-3 proxy-weight estimates, `0038` PA-4 residual variance).
- **Delivery autonomy (2026-07-12, EXTENDED 2026-07-14):** Claude self-drives plan→implement→review→commit→push AND **opens + merges the PRs** (the adversarial review + `make check` + full-PG + CI-to-green gates replace the human merge gate; branch protection's required checks stay on; PR create/merge via the GitHub REST API with the keychain credential). The USER still signs off Tier-3 decisions and genuine design forks. The older "USER opens+merges" statements below are superseded — as are ALL stale HEAD/migration-head/governed-number-count claims elsewhere in this file that predate this pointer (e.g. the PA-0-era "0034" / `ad3d3fe` lines above): where this pointer and older text disagree, the pointer + the roadmap win (Wave-4 close audit fix).
- `git log -1 --oneline` and `git status --short` — confirm main HEAD and branch state.
- Latest CI conclusion for the current HEAD (GitHub Actions; `gh` CLI is NOT installed — the public repo REST API answers unauthenticated, 60 req/hr).
- `git remote -v` — origin is HTTPS (`https://github.com/ghostai8088/…`; flipped from SSH at P3-C3 — port 22 blocked).
- `project_state.yaml` is **RETIRED** (2026-07-06 stub; found drifted at the P3-3 planning session) — the recovery set is `CLAUDE.md` + this file + `phase_status.md` + `next_actions.md`.
- **This machine's environment (verified 2026-07-07):** the repo sits nested at `~/Projects/investment_risk_platform/investment-risk-platform/`; the venv is **Python 3.13.0** (CI runs 3.12); **`irp_pg_local` IS stood up** (reused `postgres:16`; `postgresql+psycopg://irp:irp@localhost:5432/irp`) — reset the schema between full PG pytest runs and NEVER manually grant `irp_ops` schema USAGE (migrations re-grant; the extra grant breaks the downgrade smoke); `gh` is not installed (use the public REST API).
