# VAR-HS-1 Decision Record — Historical-Simulation VaR (Wave-1 slice 2)

| Field | Value |
|---|---|
| Status | **PLANNING RATIFIED** — OQ-VAR-HS-1-1…7 approved by the user at the commit gate (2026-07-08, after a plain-language briefing incl. the Part-2 benchmark verdict); implementation is a SEPARATE approval |
| Date | 2026-07-08 |
| Basis | `delivery_roadmap.md` Wave 1, slice 2 (user-directed method roadmap 2026-07-07). The FIRST slice under roadmap Part 4 rule 6 (thesis alignment — the cited external-benchmark section, Part 2 below). |
| Grounding | Verified against HEAD `afed75c`: the P3-5 parametric engine (`var_result`, ENT-027; declared-parameter identity; hard-FK provenance; `PreciseDecimal(28,6)`), the P3-3 factor-exposure totals (x), the P3-2 captured factor-return series, the P3-4 per-date bitemporal window pins (`COMPONENT_KIND_FACTOR_RETURN`), and the P3-C1 shared run scaffold are all shipped — historical simulation needs NO new captured data. |
| Sign-off | **OQ-VAR-HS-1-1…7 — APPROVED / RATIFIED by the user (2026-07-08: "Proceed" on the full package, all seven as recommended).** |

---

## Part 1 — Decisions at a glance

| ID | Topic | Decision |
|---|---|---|
| **OD-VHS-A** | method | **Factor-based historical simulation, plain equal-weight v1**: for each date `t` in the pinned window, the scenario P&L is `xᵀ·r_t` (x = a COMPLETED FACTOR_EXPOSURE run's per-factor totals; `r_t` = the pinned captured factor returns); VaR = the declared empirical quantile of the loss distribution. No distributional assumption (the method's entire point vs parametric); specific-risk = 0 stays the first-class limitation (same as parametric — x spans factors only). |
| **OD-VHS-B** | model identity | NEW registered model family **`risk.var.historical` v1** (never a silent variant of `risk.var.parametric`): declared assumptions = `confidence_level` (vocab {0.9500, 0.9900} — parity with parametric), `horizon_days` = 1 verbatim, `window_observations` = N (strict parse, the P3-4 contract), and **`quantile_convention`** (v1 pins ONE convention — see OD-VHS-D). Same-label/different-declaration ⇒ 409; non-REGISTERED twins refused (the P3-C1 contract). |
| **OD-VHS-C** | result shape | REUSE `var_result` (ENT-027) with **`metric_type='VAR_HISTORICAL'`** — the grain `(calculation_run_id, metric_type)` was designed for this. Parametric-only columns (`z_score`, `sigma`) become NULLABLE via additive **migration `0028_var_historical`** (no row changes; IA/RLS/trigger untouched); hist-sim rows carry `var_value`, window bounds, `n_factors`, `n_observations`, the provenance run FKs. The FE-1 view shows the runs with zero UI work (same VAR family). |
| **OD-VHS-D** | quantile convention | **The (⌈N·(1−c)⌉)-th smallest P&L (lower empirical order statistic), no interpolation, loss reported positive** — deterministic, exact under `Decimal` (no float quantile arithmetic), and conservative (it is the convention behind the Basel-era "3rd worst of 250 at 99%" reading). Interpolated estimators (Hyndman-Fan variants) are a RECORDED v2 declaration, never a silent change. |
| **OD-VHS-E** | window adequacy | Fail-closed floor: `window_observations ≥ ⌈1/(1−confidence)⌉` (at 99%, N ≥ 100 — below that the quantile is the sample minimum and the estimate is statistically meaningless); refusal pre-create. The methodology doc records the REGULATORY convention (≥1 year ≈ 250–253 obs) as guidance; the model declares its N and the platform enforces the declaration exactly (window-as-identity, the P3-4 pattern). |
| **OD-VHS-F** | governance | Identical governed shape: snapshot pins (FACTOR_EXPOSURE IA rows + per-date factor-return pins, `PURPOSE_VAR_INPUT` reuse or a sibling purpose), both-path pre-create adjudication (coverage: exposure factors ⊆ window factors; uniform base currency; canonical order; magnitude envelopes), own-tenant provenance re-resolution, the P3-C1 scaffold, `risk.*` REUSED (zero new permissions), `RISK.VAR_CREATE` stays reserved-not-emitted, methodology doc `var_historical_v1.md` (incl. the Part 2 benchmark section), 4 endpoints mirroring the parametric family. |
| **OD-VHS-G** | out of scope (recorded) | FHS/volatility-filtered and BRW/time-weighted variants (v2 model versions — see Part 2); ES (the FRTB-preferred measure — the recorded closed-form seam gains a hist-sim seam note); overlapping/multi-day horizons; backtesting (Kupiec/traffic-light — a named later slice, also a P7 prerequisite); Monte-Carlo (still gated). |

## Part 2 — External benchmark (roadmap rule 6 — sources checked 2026-07-08)

What the literature and regulation say, and where v1 stands:
1. **Plain HS is the industry workhorse but reacts slowly to volatility shifts**; filtered historical simulation
   (Barone-Adesi et al., 1999) and time-weighted BRW (Boudoukh–Richardson–Whitelaw, 1998) consistently outperform
   it in comparative studies ([Bank of England WP 525](https://www.bankofengland.co.uk/-/media/boe/files/working-paper/2015/filtered-historical-simulation-value-at-risk-models-and-their-competitors.pdf);
   [arXiv 2505.05646](https://arxiv.org/pdf/2505.05646); [Pritsker 2006, "The hidden dangers of historical simulation"](https://www.sciencedirect.com/science/article/abs/pii/S037842660500083X)).
   **Disposition:** v1 ships plain equal-weight DELIBERATELY (deterministic, assumption-free, auditable — the
   honest baseline), with FHS/BRW recorded as v2 model versions requiring a volatility model (EWMA/GARCH) — a
   dependency we will declare rather than smuggle.
2. **Window length is a real trade-off** (long = stale regimes; short = noise — the same sources). **Disposition:**
   window-as-declared-identity (the platform's existing pattern) + the OD-VHS-E adequacy floor; regime weighting
   deferred to the v2 family.
3. **Regulatory direction (Basel FRTB)** replaced 99% VaR with **97.5% Expected Shortfall** calibrated to a
   stressed period, with ~one year (253 scenarios) of data and liquidity horizons
   ([BIS d457 note](https://www.bis.org/bcbs/publ/d457_note.pdf); [BIS d305](https://www.bis.org/bcbs/publ/d305.pdf);
   [FRTB overview](https://en.wikipedia.org/wiki/Fundamental_Review_of_the_Trading_Book)); VaR remains the
   backtesting measure. **Disposition:** ES stays a recorded seam (now with a hist-sim leg noted); our
   confidence vocab retains 0.95/0.99 for method parity; the methodology doc cites the FRTB conventions as the
   regulatory reference point without claiming capital-model status.
4. **Quantile conventions vary**; the lower order statistic is the conservative, deterministic reading consistent
   with the Basel-era discrete convention. **Disposition:** OD-VHS-D pins it as a DECLARED parameter so a future
   interpolated estimator is a visible model-version change, never drift.

## Part 3 — Open decisions (OQ-VAR-HS-1-1…7) — **APPROVED / RATIFIED (2026-07-08, the plan-commit gate)**
- **OQ-1 — recommend APPROVE.** Factor-based plain equal-weight HS as v1; FHS/BRW as recorded v2s. (OD-VHS-A/G, Part 2.1.)
- **OQ-2 — recommend APPROVE.** New model family `risk.var.historical` with the four declared assumptions. (OD-VHS-B.)
- **OQ-3 — recommend APPROVE.** Reuse `var_result` + `metric_type='VAR_HISTORICAL'`; additive migration `0028` making `z_score`/`sigma` nullable. (OD-VHS-C.)
- **OQ-4 — recommend APPROVE.** The lower-order-statistic quantile convention as a declared parameter. (OD-VHS-D.)
- **OQ-5 — recommend APPROVE.** The window-adequacy floor `N ≥ ⌈1/(1−c)⌉`, refusal pre-create. (OD-VHS-E.)
- **OQ-6 — recommend APPROVE.** The identical governed shape (pins/adjudication/scaffold/zero new permissions/4 endpoints/methodology doc with the benchmark section). (OD-VHS-F.)
- **OQ-7 — recommend APPROVE.** The out-of-scope register (ES seam note; backtesting a named later slice). (OD-VHS-G.)

## Part 4 — Implementation readiness gate
Implementation-ready once OQ-VAR-HS-1-1…7 are ratified. Build contract = `var_hs_1_implementation_plan.md`.
**VAR-HS-1 planning implements nothing.**
