# PA-2 Decision Record — private holdings on the public factor substrate (Wave-3 slice 3)

> **Status: RATIFIED 2026-07-12** — OQ-PA-2-1…6 approved as recommended (user: "Approved").
> Drafted against `main` `f8bc20d` (PA-1 merged PR #19, CI green). Scope: the END-TO-END demonstration the thesis destination promises — a
> private holding, projected through its captured **`proxy_mapping`** weights (ENT-019, PA-0) onto
> the public CURRENCY factors, flows through the EXISTING governed chain (factor-exposure →
> covariance → VaR/active-risk/scenario) so **a private asset carries honest, factor-based risk**.
> NO new canonical entity, NO migration, NO new permission (subject to the OQs). Implementation
> follows ratification under the delivery-autonomy grant; the OQs are the Tier-3 gate.

## Part 1 — Decisions at a glance (OD-PA-2-A…G)

| # | Decision | Choice (recommended) |
|---|---|---|
| OD-PA-2-A | **The shape (the headline call): REUSE `factor_exposure_result` + the `FACTOR_EXPOSURE` run family; mint a NEW registered MODEL `risk.factor_exposure.proxy` v1.** | The proxy projection produces exactly the ENT-028 realization's shape (per-`(run, portfolio, instrument, factor)` exposure amounts with a `loading`), and every downstream consumer (covariance/VaR/active-risk/scenario) binds a COMPLETED `FACTOR_EXPOSURE` run WITHOUT caring which registered model produced it — so the end-to-end demonstration needs **ZERO downstream changes**: run the proxy model, then the existing VaR chain just works. The one-table/many-model-families precedent is VAR-HS-1 (`var_result` hosts `risk.var.parametric` + `risk.var.historical`). `code_version`-only identity (the weights are PINNED content, not parameters — the P3-6 shock-vector precedent). **NO migration.** |
| OD-PA-2-B | Allocation semantics (v1) | Per pinned exposure atom: **if the atom's instrument has ≥1 pinned CURRENT proxy row, allocate `exposure_amount × weight` per proxy factor (`loading = weight`, signed, quantize_HALF_UP 6dp); otherwise the allocation-v1 mark-currency indicator rule applies unchanged** (loading 1 on the atom's currency factor) — one run handles a MIXED public+private book, which IS the demonstration. A proxied instrument's rows replace (not add to) its indicator row. **The unallocated residual (1 − Σw) stays honestly unmodeled** (PA-0 OD-D: partial proxies are legitimate; the residual is derivable as `atom − Σ allocated` and a first-class `model_limitation` — no imputation, no synthetic "residual factor" in v1). Every proxy factor must be in the run's pinned factor list — an unpinned proxy factor fails CLOSED pre-create (no silent dropping). Contribution-sum-equals-total (REQ-MKT-003) holds only for UNPROXIED atoms; for proxied atoms the sum is `Σw × atom` BY DESIGN — test-asserted both ways. |
| OD-PA-2-C | Snapshot + reproducibility | REUSE purpose `FACTOR_EXPOSURE_INPUT` with a NEW binding predicate (`v1:exposure-run-atoms+factor-list+proxy-rows`) + a NEW **`COMPONENT_KIND_PROXY_MAPPING`** pin flavor: the CURRENT-HEAD `proxy_mapping` rows of every pinned atom's instrument (the FR per-row pin — the `benchmark_constituent`/`scenario_shock` flavor). TR-09 BOTH sides: a post-run proxy supersede cannot move a historical run; a re-run against the same snapshot reproduces byte-identically. The proxy binder refuses a snapshot whose predicate lacks the proxy rows (a plain allocation-v1 snapshot is not a proxy input). |
| OD-PA-2-D | PA-1's desmoothed series: NOT consumed in PA-2 | The proxy weights stay CAPTURED judgment calls (`mapping_method`, PA-0 OD-C). **Regression-estimated weights from the DESMOOTHED return series** (regress PA-1's output on factor returns — the moment PA-1's number becomes an input) is the recorded **v2** that closes the loop; it needs its own estimation conventions (window, standard errors) and stays out of v1. Recorded loudly so the PA-1→proxy connection isn't silently dropped. |
| OD-PA-2-E | Permission + audit + entities | REUSE `risk.run`/`risk.view` (a factor-exposure run is a risk calculation — the P3-3 family); `CALC.RUN_*` reused; NO new audit code (EVT-220 unchanged — `RISK.FACTOR_EXPOSURE_CREATE` stays reserved); NO new canonical id (ENT-028 gains its proxy-model realization note; ENT-019 gains its FIRST GOVERNED CONSUMER note — the PA-0 "will later snapshot-pin it" promise discharged). API: the existing `/risk/factor-exposures/runs` endpoint gains the proxy model registration route (`/risk/models/factor-exposure-proxy`) + the run accepts the proxy model_version (the binder dispatches on the bound model). FE: NO new family (the runs surface under `factor-exposures` automatically). |
| OD-PA-2-F | Rule-6 external research | The proxy/factor-mapping approach mirrors standard institutional practice: private-market risk systems express private holdings as loadings on public factor systems (public-market-equivalent benchmarking — **Kaplan & Schoar (2005)**, "Private Equity Performance: Returns, Persistence, and Capital Flows", *J. Finance* 60(4) — is the canonical PME reference for benchmarking private returns against public indices). The CURRENCY-family v1 scope is the platform's existing single-family scope (PA-0 OD-H), not a methodology claim; multi-family proxying (equity/credit factors) is the recorded extension WITH the regression-weights v2 (OD-D). No further citations asserted — the projection arithmetic (`exposure × weight`) is definitional, not a contested methodology (the honesty precedent: no decorative unverified citations). |
| OD-PA-2-G | Review + flow | **FULL 4-finder battery** (it changes a governed number's semantics even though it mints no table). Fixtures TD-1-realistic (a mixed book: one public bond + one PE fund with a partial two-factor proxy); the full-stack golden ships its derivation THROUGH VaR (the end-to-end number hand-derived); TR-09 both sides; no RUNNING orphan on any refusal; the MD-H1 design checklist (empty proxy set for a proxied run = the indicator path, NOT a refusal; unpinned proxy factor = refusal). Claude self-drives; the USER merges. |

## Part 2 — Limitations carried forward + out of scope (recorded)

1. **Captured weights only** — regression-from-desmoothed-returns (the PA-1 consumer) is the v2
   (OD-D); `mapping_method` records provenance.
2. **CURRENCY-family factors only** (the platform-wide v1 scope; PA-0 OD-H).
3. **The unallocated residual is unmodeled** (partial proxies, PA-0 OD-D) — derivable, recorded,
   never imputed; a residual/idiosyncratic variance term is a v2 candidate alongside the
   regression weights.
4. **Proxied rows break the sum-to-total identity BY DESIGN** (Σw × atom ≠ atom unless Σw = 1) —
   the REQ-MKT-003 exactness holds per-unproxied-atom and is test-asserted in both regimes.
5. Money-weighted/IRR + capital calls remain the PA-3 register item (unchanged).
6. `validation_status` UNVALIDATED (non-enforcing until P7).

## Part 3 — Open decisions (OQ-PA-2-1…6) — pending ratification

- **OQ-1** — REUSE `factor_exposure_result` + the `FACTOR_EXPOSURE` family; NEW model
  `risk.factor_exposure.proxy` v1 (`code_version`-only identity); NO migration; downstream chain
  untouched. *(Recommended: yes — OD-A; the VAR-HS-1 precedent.)*
- **OQ-2** — Allocation semantics per OD-B (proxied-else-indicator in one mixed-book run; honest
  unallocated residual; unpinned proxy factor fails closed). *(Recommended: yes.)*
- **OQ-3** — Snapshot per OD-C (purpose reused; NEW `COMPONENT_KIND_PROXY_MAPPING` + predicate;
  TR-09 both sides). *(Recommended: yes.)*
- **OQ-4** — The desmoothed-series connection (regression weights) is the recorded v2, NOT in
  PA-2. *(Recommended: yes — OD-D.)*
- **OQ-5** — No new permission/audit/canonical id; ENT-019 + ENT-028 registry notes only.
  *(Recommended: yes — OD-E.)*
- **OQ-6** — FULL 4-finder review. *(Recommended: yes — OD-G.)*

## Part 4 — Implementation readiness gate

On ratification of OQ-1…6, implementation proceeds against a compact build contract (no separate
plan document — the slice mints NO table and follows the P3-3/PA-1 exemplars step-for-step):
(1) `COMPONENT_KIND_PROXY_MAPPING` + `proxy_mapping_content` serializer + the extended
`build_factor_exposure_snapshot` (proxy rows pinned when the proxy model runs) + the
`_reresolve_content` branch FROM BIRTH (the P3-6 verify lesson); (2) `register_factor_exposure_proxy_model`
(bootstrap; `code_version`-only); (3) the binder dispatch in `factor_service` (proxied-else-indicator
kernel leg + the fail-closed gates); (4) API model route + FE nothing; (5) tests (SQLite mixed-book
golden THROUGH VaR + TR-09 + refusals + guards; PG legs ride the existing factor-exposure suites +
one proxy-pin case; endpoint cases); (6) docs (methodology `factor_exposure_proxy_v1.md`; ENT-019/028
registry notes; RTM REQ-PRV-005 consumer note); (7) full validation + the 4-finder battery.
Model/effort: **Fable 5 / High** (the allocation-semantics leg), Opus/High acceptable for the rest.
