# P3-7 Decision Record — Benchmark-relative analytics: ex-ante active risk / tracking error (Wave-1 slice 5)

| Field | Value |
|---|---|
| Status | **IMPLEMENTED + REVIEWED — commit approved 2026-07-09.** OQ-P3-7-1…10 ratified; the full slice built (kernel, registrar `risk.active_risk.parametric` v1, `ACTIVE_RISK_INPUT` snapshot builder + `COMPONENT_KIND_BENCHMARK`, migration `0030_active_risk`, binder `active_risk_service.py`, API + FE, docs, tests); **FULL max-effort review complete (Part 6 — 10 finder angles + 6 empirical verifiers + gap sweep; 21 findings folded, 3 refuted/rejected-as-designed, 3 recorded-deferred)**; validation green post-fold. Closeout stamp follows CI-green. |
| Date | 2026-07-09 |
| Basis | `delivery_roadmap.md` Wave 1, slice 5: "Tracking error / active risk over the P2-7 data + the existing engine — the P3 plan's final analytic leg." The original contract (`p3_implementation_plan.md` §P3-7 + OD-P3-0-G/K): **"active risk / tracking error over captured benchmark membership… membership-based active risk uses the captured constituents + a risk model"**; performance attribution EXCLUDED; `COMPONENT_KIND_BENCHMARK` reserved for this slice. A **methodology slice** → roadmap Part 4 **rule 6 applies** (Part 2 below is the cited external-benchmark section). |
| Grounding | Verified against shipped HEAD `367f602`: FIVE governed risk numbers exist (DV01, factor exposure, covariance, parametric VaR, historical VaR); `factor_exposure_result` = per-atom `(run, portfolio, instrument, factor)` currency amounts under **allocation v1** (currency-indicator loadings; specific risk = 0); `covariance_result` = daily UNANNUALIZED sample covariance over `SIMPLE` factor returns; `var_result` = the single-summary-row precedent (grain `(calculation_run_id, metric_type)`; hard-FK upstream-run provenance). `benchmark` (ENT-009 EV) + `benchmark_constituent` (FR; `weight` fraction, RANGE [0,1]; **`constituent_currency` OPTIONAL**; weight-SUM completeness deferred at P2-6 OQ-P2-6-8) + `benchmark_level`/`benchmark_return` (ENT-052, P2-7) all captured. `RISK_RUN_TYPES` = {SENSITIVITY, FACTOR_EXPOSURE, COVARIANCE, VAR}; the FE lists risk families from a FAMILIES map (a new run_type needs one small additive FE entry — the P3-C2 exposure-family precedent). Migration head `0029_benchmark_series`; next free `0030`. The shared governed-run scaffold lives at `calc/scaffold.py`. |
| Sign-off | **PENDING — OQ-P3-7-1…10 below** |

---

## Part 1 — Decisions at a glance

| ID | Topic | Decision |
|---|---|---|
| **OD-P3-7-A** | slice character | The **SIXTH governed risk number**: **ex-ante active risk (parametric tracking error)** — RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND, IA append-only result, reproducible under input correction (the full P3 output contract). ONE migration (**`0030`**, the new result table only). **NO new permission** (`risk.view`/`risk.run` REUSED); **no new audit code emitted** (`CALC.RUN_*` reuse; `RISK.ACTIVE_RISK_CREATE` **reserved-not-minted** at the EVT-220 block — the P3-1…P3-5 precedent). `audit/service.py` FROZEN. |
| **OD-P3-7-B** | the methodology (v1) | **TE_daily = √(wₐᵀ Σ wₐ)** — the Grinold-Kahn/Roll ex-ante factor-model tracking error, DAILY and UNANNUALIZED (the P3-4 covariance convention; annualization is a declared later version). **wₐ = w_p − w_b** over the covariance factor set: the PORTFOLIO side = pinned `factor_exposure_result` amounts per factor ÷ the pinned portfolio value (net signed total of the pinned exposure atoms); the BENCHMARK side = pinned constituent weights (NORMALIZED by their sum — vendor rounding tolerance, declared) mapped to currency factors via each constituent's `constituent_currency` under the SAME allocation-v1 indicator mapping the portfolio side uses (methodological symmetry — both sides through one factor model). Exact-Decimal pipeline: Decimal-50 intermediates, `Decimal.sqrt`, radicand quantization floor `tol` (the P3-5 OD-P3-5-x pattern verbatim: clamp a tiny negative radicand within `tol`; genuinely negative beyond `tol` = post-create FAILED, reachable + test-proven); `te_value = quantize_HALF_UP(√·, 12)` `Numeric(20,12)` (a daily active-return volatility, a FRACTION — the factor-return scale, NOT currency). |
| **OD-P3-7-C** | result entity | **`active_risk_result`** — the third ENT-027 `risk_result` realization (**NO net-new canonical id** — the `var_result`/`factor_exposure_result` precedent). Single-summary-row grain **`(calculation_run_id, metric_type)`**, `metric_type = 'TRACKING_ERROR'` v1 (further active metrics reserved by value). Columns: `te_value Numeric(20,12)`; hard-FK provenance **`factor_exposure_run_id`** + **`covariance_run_id`** → `calculation_run.run_id` (the var_result precedent) + **`benchmark_id`** → `benchmark.id` + the carried `benchmark_effective_date` (WHICH membership set); `portfolio_value Numeric(28,6)` (the denominator, recorded as evidence); `input_snapshot_id`/`model_version_id` NON-NULL. **IA TRUE append-only** (`APPEND_ONLY_TABLES` + P0001 trigger + ORM guard); symmetric tenant-scoped RLS (NEVER hybrid). |
| **OD-P3-7-D** | model governance | New registered family **`risk.active_risk.parametric` v1** + methodology doc `05_analytics_methodologies/active_risk_parametric_v1.md`. **No free numeric request parameters** — the version identity IS the declared conventions (allocation-v1 mapping both sides; benchmark-weight normalization; daily-unannualized; the radicand floor; specific-active-risk = 0), recorded as `model_assumption`s/`model_limitation`s; a same-label re-register with a different `code_version` is a governed 409 (the registrar precedent). `assert_registered_model_version` load-bearing pre-create. |
| **OD-P3-7-E** | inputs + fail-closed gates | New snapshot purpose **`ACTIVE_RISK_INPUT`** pinning FOUR component kinds: `FACTOR_EXPOSURE` (IA pins, the portfolio side), `COVARIANCE` (IA pins, Σ), `FACTOR` (EV pins — the currency→factor mapping the benchmark side needs), and the **NEWLY MINTED `COMPONENT_KIND_BENCHMARK`** (the FR constituent-set pin — discharging the OD-P3-0-G reservation; pins the resolved membership rows for the declared `(benchmark_id, effective_date)`). Fail-closed, NO imputation (the VaR coverage precedent): portfolio factors ⊆ Σ factors; every benchmark constituent currency maps to a Σ factor; **a NULL `constituent_currency` on any pinned constituent = a pre-create refusal naming the gap** (the captured membership must carry currencies to be risk-mapped — an honest data requirement, not a silent fallback to the header currency, which would misattribute currency risk); Σw_b ≤ 0 refusal; portfolio value = 0 refusal; the P3-C1 both-modes input-ambiguity gate; post-create FAILED for the radicand/magnitude gates via the shared `calc/scaffold.py` (its SEVENTH consumer). |
| **OD-P3-7-F** | run + API + FE surface | `run_type = 'TRACKING_ERROR'` added to `RISK_RUN_TYPES` (listable via the existing `GET /risk/runs`; `risk.view` fence unchanged). Endpoints: `POST /risk/active-risk/runs` (gated `risk.run`) + the standard GET family (run + rows/summary, gated `risk.view`) — the VaR endpoint shapes. FE: one small ADDITIVE `FAMILIES` entry + detail columns in `types.ts` (the P3-C2 exposure-family precedent) — no structural FE change. |
| **OD-P3-7-G** | the ex-post leg — NAMED DEFERRAL + an honest roadmap correction | **Realized (ex-post) tracking error / active return is DEFERRED with its prerequisite named precisely.** The regulatory ex-post definition (ESMA: "volatility of the difference between the fund's return and the benchmark's return") needs BOTH sides' return series. P2-7 delivered the BENCHMARK side; the **PORTFOLIO return series does not exist**, and deriving it from captured marks + transactions (flow-adjusted TWR/Modified-Dietz) is a **performance-measurement methodology** (GIPS-grade) that the P3-0 contract explicitly excluded from P3-7 ("performance attribution excluded") — it must be its own planned slice. The roadmap's "P2-7 unblocks P3-7's return-based legs" is therefore made precise: P2-7 unblocked the benchmark HALF; the portfolio-return slice is the remaining prerequisite (roadmap amendment recorded at this slice's commit). Consequently the captured `benchmark_return` series' first governed consumer lands at that future slice (or a relative-VaR extension) — v1 here consumes membership, factor exposures, and covariance. Information ratio (needs realized active returns) defers with it. |
| **OD-P3-7-H** | rule-6 external benchmarks | Part 2 below — the cited-source section with per-source dispositions (Roll 1992; Grinold & Kahn 2000; Pope & Yadav 1994; CESR/10-788 2010; ESMA UCITS-ETF guidelines 2012/2014; Barra Risk Model Handbook 2007) and justified deviations. |
| **OD-P3-7-I** | proportionate review | **FULL 6-finder review + unreduced gates** (a new governed number + migration + methodology): make check + full-PG + downgrade smoke + fe-check + diff fence; a golden hand-reference kernel proof (an exact-arithmetic TE construction, the P3-4/P3-5 style) + the dual-path numpy cross-check (TEST-only). All new fixtures follow the TD-1 realism rule. |

## Part 2 — External benchmark research (roadmap Part 4 rule 6; sources + dates checked 2026-07-09)

| Source | What it establishes | Disposition here |
|---|---|---|
| **Roll, R. (1992), "A Mean/Variance Analysis of Tracking Error", *Journal of Portfolio Management* 18(4)** | The canonical definition of tracking error as the volatility of the active-return difference and the TEV-optimization frame. | ADOPTED as the definitional basis; v1 computes the ex-ante (forecast) form. |
| **Grinold, R. & Kahn, R. (2000), *Active Portfolio Management*, 2nd ed.** | Active risk ψ = stdev(active return); the factor-model ex-ante form ψ² = wₐᵀΣwₐ (+ specific term); the IR framework. | ADOPTED: TE² = wₐᵀΣwₐ over the registered sample covariance. **Deviation (declared):** the specific-risk term is 0 under allocation v1 (no idiosyncratic model) — carried as a first-class model limitation, exactly as P3-3/P3-5 record it. IR DEFERRED (needs realized active returns; OD-G). |
| **Pope, P. & Yadav, P. (1994), "Discovering Errors in Tracking Error", *JPM* 20(2)** | Measurement-frequency and serial-correlation effects bias TE estimates; naive √T annualization overstates/understates TE under autocorrelation. | GROUNDS the v1 choice to report DAILY UNANNUALIZED TE (consistent with the P3-4 covariance convention) and to keep annualization a separately-declared later model version rather than a silent √252. |
| **CESR/10-788 (2010), *Guidelines on Risk Measurement and the Calculation of Global Exposure and Counterparty Risk for UCITS*** | The relative-VaR approach (VaR of the fund vs a reference portfolio) as the regulatory sibling of active risk. | RECORDED as an adjacent seam: a later "relative VaR" extension can reuse this slice's active-weight construction + the P3-5 VaR machinery; not built here. |
| **ESMA Guidelines on ETFs and other UCITS issues (ESMA/2012/832, rev. 2014/937)** | The regulatory EX-POST definition: tracking error = "the volatility of the difference between the return of the fund and the return of the benchmark"; TE vs tracking-difference distinction. | GROUNDS OD-G: the ex-post measure requires both return series; deferred with the portfolio-return prerequisite named. The v1 record and methodology doc explicitly label the shipped number EX-ANTE so it cannot be conflated with the UCITS ex-post disclosure figure. |
| **MSCI Barra Risk Model Handbook (2007)** | Industry-standard factor decomposition of active risk into common-factor + specific components; benchmark exposures computed by mapping constituents through the same factor model as the portfolio. | ADOPTED: both sides map through the SAME allocation-v1 model (methodological symmetry); the common-factor-only limitation is declared (specific active risk = 0). |

**Net deviations from the cited state of the art, all declared as model assumptions/limitations:** (1) ex-ante only (ex-post deferred, OD-G); (2) daily unannualized; (3) specific/idiosyncratic active risk = 0 (allocation-v1 indicator loadings — currency-factor granularity only); (4) no IR/active-share; (5) benchmark weights normalized (vendor rounding) rather than gap-filled — with missing constituent currencies a refusal, never imputed.

## Part 3 — Out of scope (recorded)
Ex-post/realized TE, active return, tracking difference, IR (OD-G — deferred on the portfolio-return prerequisite); performance measurement/attribution (its own GIPS-grade slice); relative VaR (a recorded seam, CESR/10-788); annualization/√T scaling; active share; benchmark-relative sensitivities; any new captured data; any change to the P2-6/P2-7 capture surfaces; no new permission/audit code; no BYPASSRLS/hybrid; `audit/service.py` FROZEN.

## Part 4 — Open decisions (OQ-P3-7-1…10) — pending ratification
- **OQ-P3-7-1 — recommend APPROVE.** Slice scope = the SIXTH governed number: ex-ante active risk (parametric TE) v1; one migration (`0030`); permission + audit reuse. (OD-A.)
- **OQ-P3-7-2 — recommend APPROVE.** The methodology: TE_daily = √(wₐᵀΣwₐ), daily unannualized, Decimal-exact with the P3-5 radicand floor; `te_value` at 12dp fraction scale. (OD-B.)
- **OQ-P3-7-3 — recommend APPROVE.** `active_risk_result` as an ENT-027 realization (NO new canonical id), single-summary-row grain, hard-FK provenance (factor-exposure run, covariance run, benchmark) + `benchmark_effective_date` + `portfolio_value` evidence. (OD-C.)
- **OQ-P3-7-4 — recommend APPROVE.** New family `risk.active_risk.parametric` v1; conventions-as-version-identity (no free numeric params); methodology doc. (OD-D.)
- **OQ-P3-7-5 — recommend APPROVE.** `ACTIVE_RISK_INPUT` snapshots pinning FACTOR_EXPOSURE + COVARIANCE + FACTOR + the newly minted **`COMPONENT_KIND_BENCHMARK`** (discharges the OD-P3-0-G reservation). (OD-E.)
- **OQ-P3-7-6 — recommend APPROVE.** The fail-closed gates: coverage ⊆ Σ-factors both sides; **NULL `constituent_currency` = pre-create refusal** (no silent header-currency fallback); Σw_b ≤ 0 + zero-portfolio-value refusals; benchmark weights normalized by their sum (declared). *(Alternative considered: fall back to the benchmark header currency for currency-less constituents — REJECTED: it silently misattributes currency risk; the refusal makes the data gap visible and fixable at capture.)* (OD-E.)
- **OQ-P3-7-7 — recommend APPROVE.** `run_type TRACKING_ERROR` into `RISK_RUN_TYPES`; `POST /risk/active-risk/runs` + GET family; the small additive FE FAMILIES/detail entry. (OD-F.)
- **OQ-P3-7-8 — recommend APPROVE.** The ex-post leg's NAMED deferral + the precise roadmap correction: P2-7 unblocked the benchmark half; a portfolio-return series (a separately-planned performance-measurement slice) is the remaining prerequisite; `benchmark_return`'s first governed consumer moves there. *(This is the objective reading of the actual data dependencies; the alternative — deriving portfolio returns inside this run — would smuggle a GIPS-grade methodology into a risk slice against the P3-0 exclusion.)* (OD-G.)
- **OQ-P3-7-9 — recommend APPROVE.** The rule-6 external-benchmark section (Part 2) with its declared deviations. (OD-H.)
- **OQ-P3-7-10 — recommend APPROVE.** Full 6-finder review + unreduced gates + the golden hand-reference kernel proof + TEST-only numpy cross-check. (OD-I.)

## Part 5 — P3-7 implementation readiness gate
Implementation-ready once OQ-P3-7-1…10 are ratified. Build contract = `p3_7_implementation_plan.md`.
**P3-7 planning implements nothing.**

## Part 6 — Implementation + review log (2026-07-09)

**Built per `p3_7_implementation_plan.md` Steps 0–8:** pure kernel `active_risk_kernel.py` (Decimal-50,
12dp HALF_UP, the OD-P3-5-G radicand floor re-derived for the weight scale); registrar
`risk.active_risk.parametric` v1 (code_version-only identity, OD-P3-7-D); `ACTIVE_RISK_INPUT`
snapshot builder pinning FACTOR_EXPOSURE + COVARIANCE + FACTOR + the NEW `COMPONENT_KIND_BENCHMARK`
(FR-version constituent pins, TR-09); migration `0030_active_risk` (`active_risk_result`, IA
append-only, symmetric FORCE RLS, 3 hard-FK provenance columns incl. `benchmark_id`); binder
`active_risk_service.py` (active weights `wₐ = w_p − w_b`, both sides through ONE
`build_factor_index` — the Barra-style symmetry); API POST/GET family + FE FAMILIES entry; docs
(canonical ENT-027 cell, audit-taxonomy reserve, RTM REQ-PUB-003 consumer note, roadmap OD-G
precision amendment); tests (kernel goldens 0.0005/0.0007, consume-path golden **0.007211102551**,
numpy cross-check, pin invariance under upstream re-runs AND a benchmark restatement, PG
RLS/append-only/forged-tenant, endpoint, FE).

**Review — FULL max-effort multi-agent ("ultrareview", user-directed):** 10 finder angles
(line-by-line, removed-behavior, cross-file, language-pitfall, adversarial gate-bypass, reuse,
simplification, efficiency, altitude, conventions) → ~35 raw candidates → 22 deduped → **6
verifiers with mandatory empirical probes** (3-state verdicts) → a fresh-eyes gap sweep.
Honesty note: the adversarial cluster (V1–V6) is **defense-in-depth** — no API path lets a user
mint arbitrary snapshot content (`POST /snapshots` builds server-side); the adjudicator is a
deliberate trust boundary (the P3-5 envelope precedent), so those folds harden a gate users cannot
currently reach.

| # | Finding (verdict) | Fold |
|---|---|---|
| V1 | te ≥ ~1E38 → kernel quantize raise escaped as post-create 500, defeating the magnitude gate (CONFIRMED, empirical) | `_compute` catches `ActiveRiskKernelError` → committed FAILED run + DQ evidence; test via kernel seam |
| V2 | `TypeError` (JSON-null numerics, non-object content) escaped the malformed-pin catch → 500 (CONFIRMED) | `TypeError` added to the catch tuple; 3-leg null-field test |
| V3 | duplicate FACTOR pins, same id + conflicting `currency_code`, passed set-equality → wrong COMPLETED TE (CONFIRMED — the one silent-wrong-number finding) | per-id duplicate refusal (parity with exposure/constituent dup checks); test |
| V4 | weight/exposure sums ran at default prec-28 outside the localcontext — an exact-zero book could round past the `==0` refusal (CONFIRMED, adversarial-only) | all accumulation moved inside the prec-50 context; exact-zero-book test |
| V5 | all-NULL or >3-char `base_currency` passed the set-of-one uniformity check → post-create NOT-NULL/varchar(3) 500 (CONFIRMED) | 3-letter-string gate at adjudication; test |
| V6 | empty-string currency bypassed the `is None` named-gap refusal (CONFIRMED, hand-mint-only) | `_is_present_currency` (None + blank refused) in binder; test |
| V7 | `FactorNotVisible` missing from the endpoint tuple (PLAUSIBLE — covariance-endpoint parity) | added to the except tuple |
| V8 | active-risk snapshot refusals surfaced as "VaR snapshot input failed closed" (CONFIRMED) | `ActiveRiskSnapshotError` subclass + own map entry; test asserts the detail |
| V9 | `test_risk_runs_pg.py` never minted the new run type — PG listing proof gap (CONFIRMED) | `_RATIFIED` widened to five; comments fixed |
| V11/V13/V17 | dead code: unreachable defense-in-depth branch, dead `_ERROR_MAP` entry, no-op `_canonical_pair` (CONFIRMED, cosmetic) | removed (pair-completeness check retained — probe-proven reachable) |
| V14 | binding predicate `fx-rows` collided with FX=foreign-exchange (durable, API-visible); varchar(50) cap unenforced, one sibling at exactly 50 (CONFIRMED) | renamed `fexp-rows` (47 chars) pre-commit; import-time length assert over ALL predicates |
| V15 | covariance adjudication duplicated from `var_service` incl. a review hardening, UNTESTED in the copy (CONFIRMED) | reversed-pair + duplicate-pair refusals now test-pinned in this copy; extraction deferred (below) |
| V16a | verify re-resolved the one benchmark header once per constituent (CONFIRMED) | per-snapshot header memo in `verify_snapshot` |
| V19/V22 | aggregator names + fixture asserts decayed vs siblings (CONFIRMED, cosmetic) | `ActiveRiskResult`+`CovarianceResult`+`VarResult` registered in `irp_shared.models`; exposure-status + row-count asserts restored |
| V20/GS1 | stale "FOUR risk families" (OpenAPI + FE comment); "THIRD table under ENT-027" (two tables exist) (CONFIRMED) | FIVE; "SECOND physical table (third realization)" |
| GS2 | **`run_type` was the METRIC string `TRACKING_ERROR`** — every sibling keeps family ≠ metric; the reserved ex-post metrics would land under a misnomer (PLAUSIBLE→adopted) | **amends OQ-P3-7-7/OD-F: `RUN_TYPE_ACTIVE_RISK = "ACTIVE_RISK"`** (pre-commit = the only zero-cost moment; `metric_type` stays `TRACKING_ERROR`) |
| conventions | **CI had NO step for `test_active_risk_pg.py`** — the new table's RLS/append-only proofs never ran in CI (CONFIRMED; rule: every new tenant table → a CI RLS step) | step added; the two PRE-EXISTING gaps (`test_benchmark_series_pg.py`, `test_exposure_runs_pg.py`) fixed in the same edit |

**Refuted / rejected-as-designed (kept):** the build-path `resolve_benchmark` is NOT redundant (it
sets 404-over-409 precedence — REFUTED); the FE exhaustiveness test is NOT tautological (vitest
does not type-check — REFUTED); the benchmark pin correctly omits the header `record_version`
(capturing it would drift N constituent pins on display-only name edits — rejected-as-designed);
build-then-re-read adjudication is the declared uniform-both-paths design (as-designed).

**Recorded-DEFERRED (follow-up hardening candidates, NOT in this slice):**
1. **`var_service.py` twins of V2/V5** — the identical `TypeError` catch gap and
   `base_currency` uniformity-only gap exist in the shipped VaR binder (verifier-confirmed,
   byte-identical template class). Same-class fix, separate slice (touches a closed slice's binder).
2. **Shared covariance-pin adjudicator** — `_adjudicate_covariance` is the second copy of the v1
   covariance-contract validation (exception-type parameterization needed); extract at the third
   consumer or in a P3-C3-style hardening slice (the P3-4-R0 tipping-point precedent).
3. **`_persist_snapshot` per-component lineage SELECT+flush** — pre-existing shared-code seam,
   newly exercised at constituent scale; batch in a hardening slice.

**Validation (post-fold, all green):** `make check` (ruff format+lint, mypy 143 files, **1044
passed / 230 skipped**, secret-scan, docs-check) · **full-PG 230 passed** (incl. the three newly
CI'd `_pg` files) · downgrade smoke `0030 → 0029 → 0030` + `alembic check` no-op · `fe-check`
(tsc, **43 FE tests**, build) · diff fence (`audit/service.py` + `entitlement/bootstrap.py`
untouched; no new permission/audit code; no BYPASSRLS/hybrid).
