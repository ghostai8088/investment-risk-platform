# Wave-2 Close Review + Re-baseline (the mandatory Part-4 rule-2 wave-close)

| Field | Value |
|---|---|
| Status | **DRAFT for ratification (2026-07-12).** Wave-3 proposal below (Part 5); each Wave-3 slice still gets its own decision record + plan + OQ ratification + adversarial review. Delivery now runs under the **full-autonomy grant** (2026-07-12): Claude self-drives plan→implement→review→commit→push; the USER opens+merges every PR to `main` and signs off Tier-3 decisions (incl. THIS document's OQs). |
| Contract | `delivery_roadmap.md` Part 2.5 tail: "Wave-2 close = the same mandatory review + re-baseline (incl. the rule-6(b) outward benchmark review + the destination-progress check)." Plus Part 4 rule 6(b) / `differentiation_thesis.md` §2.1: an **outward-facing benchmark review** and an **explicit evaluation of progress toward the public+private destination**. |
| Grounding | Verified live at `main` HEAD **`3d5a6d0`** (PRs #1–#15 merged; migration head `0035_scenario`): `make check` **1269** passed / 266 skipped, full-PG **266** (clean-schema, no drift, downgrade smoke clean) + FE **52** green; `npm audit` (full tree, all severities) = **0 vulnerabilities**; local == origin; origin HTTPS (SSH:22 blocked, recorded). |

---

## Part 1 — Honest state audit (what Wave 2 promised vs. what shipped)

**Promised (ratified 2026-07-09 at the Wave-1 close):** PM-1 → P3-8 → BT-1 → PA-0 → P3-6, organized around the return-series triple unlock, with the private-asset foundation (PA-0) pulled INTO the wave.

**Delivered: all five ratified slices shipped, plus one ratified hygiene insertion (MD-H1, slice 4.5) — six closed slices, every one CI-green with its full gate set. Zero deviations** — unlike Wave 1 (where P3-6 slipped), Wave 2 landed exactly as ratified. Every slice from P3-8 on went through the mandatory branch-protection PR flow (the USER merged each PR).

**The platform as it stands (the executed ledger is `build_plan.md`; this is the wave delta):**
- **Ten governed numbers** (up from six): + governed **portfolio-return TWR** (PM-1, the FIRST non-risk `perf` family), **ex-post benchmark-relative AR/TD/TE/IR** (P3-8), **VaR backtesting** Kupiec+Basel (BT-1), and **deterministic factor-shock scenario P&L** (P3-6). Every one snapshot-gated + run-bound + registered-model-bound, IA append-only, reproducible under input correction — the governed-number contract held without exception across the wave, including across the FIRST non-risk family.
- **The return-series triple unlock DELIVERED end-to-end:** PM-1 minted the one missing primitive (a governed portfolio-return series, `perf.return.twr` v1, ENT-053), and all three recorded consumers landed on it in-wave — P3-8 (ex-post TE/IR — closes P3-7 OD-G exactly), BT-1 (realized-P&L backtesting — the P7 model-validation prerequisite + the Wave-1-named nearest supervisory gap), and the return-series rails that the private-asset desmoothing thread (PA-1) will reuse.
- **The thesis destination BEGAN:** PA-0 realized ENT-019 `proxy_mapping` (FR captured private→public factor proxies, migration `0034`) + the captured-appraisal/NAV convention — the substrate private holdings project onto. The desmoothing TRANSFORM was ratified as the capture-first split's PA-1 follow-on.
- **Wave-added surfaces:** the `perf.run`/`perf.view` R-07 mint + CAP-20 + REQ-PRF-001 (PM-1 — the only new permission family this wave); ENT-053/054/055 + ENT-019/029/030 realized; migrations `0031`–`0035`; run families PORTFOLIO_RETURN / BENCHMARK_RELATIVE / VAR_BACKTEST / SCENARIO (all reusing existing `.run`/`.view` except PM-1's mint); `COMPONENT_KIND_{PORTFOLIO_RETURN,BENCHMARK_RETURN,VAR,TRANSACTION,SCENARIO}` snapshot flavors.
- **Verification posture:** ~1269 tests (SQLite-tier, 266 PG-tier skipped without the DB) + 52 FE; per-table PG RLS/append-only CI steps COMPLETE for every new table (the P3-7 "grep `_pg` vs ci.yml" lesson held — each slice added its CI PG step in-slice; P3-6 added `test_scenario_pg.py`'s step).
- **Review discipline compounding:** the FULL multi-finder review ran on every governed-number slice (PM-1 5-finder; P3-8/BT-1/P3-6 4-finder local batteries in lieu of the cloud ultrareview Claude cannot launch). Real bugs were caught at the only cheap moment each time — the return magnitude/echo-overflow class (PM-1, BT-1, and again P3-6: the per-factor quantize detonation, folded), the NaN-value detonation (BT-1), the horizon-blind Basel gate (BT-1), the always-drift scenario snapshot-verify (P3-6). The **clean-code standing bar** (user, 2026-07-10: "as clean as possible") reactivated dedup folds as first-class from P3-8 on.
- **RTM honesty:** REQ-PRF-001 minted + In-Progress (PM-1); REQ-MKT-004 Draft→In-Progress (P3-6); REQ-MKT-005 minted (BT-1). No REQ newly CLOSED — correct: the platform ships REQ *legs*; closure needs later-wave prerequisites. No status inflation found.
- **Known honest gaps (all recorded, none silent):** the private-asset payload itself — **desmoothing (PA-1) is not yet built**, so appraisal marks still pass through un-transformed (the thesis §2.1 problem, staged not solved); the PM-1 captured-holdings-book bias PROPAGATES into every downstream perf number (named first-class in P3-8/BT-1); ES / MC / component-VaR still named-not-built; specific/idiosyncratic risk = 0 under CURRENCY-only factors; validation WORKFLOW (P7) absent though BT-1 now feeds it.

## Part 2 — Deferral-register reconciliation (consolidated; dispositions)

**PAID during Wave 2:** the **FR supersede window-coherence guard** (all six FR series — MD-H1; this was PA-0's + BT-1's family-wide integrity deferral, and it guarded P3-6's scenario_shock supersede from birth); the shared **IntegrityError→409 mapping** for capture endpoints (MD-H1 — PA-0's family-wide 500-on-duplicate deferral); the **concurrent first-registration race** across all governed-family registrars (MD-H1 — BT-1's deferral); the **P3-8 return-shape dedup's 3 closeout folds** (P3-8 cleanup PR). MD-H1 paid the three bug-shaped items *before* the wave close, exactly as the "pay the debt while fresh" precedent intends.

**OPEN — newly TIPPED this wave (recommendation: a Wave-3 hygiene slice, OQ-W2C-3):**
| Item | Status |
|---|---|
| **RD-1 — the `resolve_*_run` / `_resolve_run` helper family** (the run-of-type resolver + the COMPLETED-run pre-FK guard) | **TIPPED — 3+ near-verbatim copies** (var_backtest, active_risk, scenario), meeting the P3-4-R0 3rd-consumer rule. The clean form is one shared `calc/` helper taking an injectable `error=`/`not_visible=` (the `assert_portfolio_in_tenant(error=…)` precedent). Deferred at the P3-6 review (Part 6) pending this close. |

**OPEN — stay deferred with NAMED TRIGGERS (recommendation: ratify as-is, no Wave-3 slot):**
| Item | Trigger that activates it |
|---|---|
| FR-membership protocol generalization (P3-6 D-2 — `proxy_mapping` + `scenario_shock` are 2 full instances) | a THIRD FR-membership entity, OR RD-1 chooses to take the design-scale extraction |
| P3-7 **B** — shared covariance-pin adjudicator (2 copies) | the THIRD covariance consumer (still 2: var + active_risk) |
| P3-8/BT-1 return-shape adjudicator dedup (2 of 3 perf consumers) | the THIRD perf-return consumer |
| P3-7 **C** — `_persist_snapshot` lineage batching | benchmark/constituent-scale pin counts become real |
| Covariance v2s (Ledoit-Wolf / EWMA / correlation / annualization); FHS/BRW VaR; Monte-Carlo VaR | accuracy demand / a declared vol model / a seeded simulator+revaluation (QS-18) |
| Vendor-beta / regression factor exposures; computed factor returns; vol surface (ENT-022); PAR_RATE/interpolation/instrument-attributed sensitivities | their own demand triggers |
| `rating` capture + REQ-PUB-003 Coverage; P2-6 weight-SUM DQ | a credit-risk / benchmark-quality slice |
| WORM/anchored audit hardening; gitleaks (OD-049) | a pre-production hardening wave |
| Dev header-shim → real SSO/OIDC (RTM-P9) | **before anything internet-facing** (unchanged) |

**OPEN — a PA-1 prerequisite (must resolve IN PA-1 planning):** the **Okunev-White (2003) citation** for the desmoothing literature was flagged **UNVERIFIED** at PA-0 — resolve or replace it in PA-1's rule-6 research before relying on it.

**Ride-alongs from the Wave-1 close, now settled:** branch protection on `main` **DONE** (OD-050, 2026-07-10 — `enforce_admins`, all 5 CI checks required); npm audit gate `high`→`moderate` applied; ES leg still DEFERRED (nothing downstream needs it).

## Part 3 — Outward benchmark review (Part 4 rule 6(b); sources checked 2026-07-12)

- **Model governance / supervisory posture:** BT-1 closed the Wave-1-named nearest gap — the platform now performs **SR 11-7 "outcomes analysis"** (Kupiec POF + Basel traffic-light over realized P&L). The remaining supervisory ingredient is the **validation WORKFLOW itself** (independent review/approval states, periodic revalidation) — RTM-P7, still honestly staged (`validation_status=UNVALIDATED` non-enforcing on every version); BT-1's backtest evidence is exactly what that workflow will consume. Correct staging, not a gap papered over.
- **Performance measurement:** PM-1's chain-linked TWR (Modified-Dietz sub-periods) is the **GIPS 2020** baseline; P3-8's ex-post TE/IR follows the **ESMA 2012/832** ex-post definitions directly. Honest baselines with the captured-holdings-book bias named first-class — consistent with "boring base, innovation budget on reproducibility."
- **Private assets (the destination):** PA-0's proxy-mapping substrate matches the **proxying** leg of the thesis; the **desmoothing** leg (Geltner 1991/1993 AR(1); Getmansky-Lo-Makarov 2004) is the recognized state-of-the-art and is staged for PA-1 with the introduced uncertainty to be stated honestly (thesis §2.1). This is the differentiation payload and it is now UNBLOCKED (return series + proxy substrate both exist).
- **Security/engineering:** branch protection now ON (the Wave-1 "cheap, real safety" item, discharged) + symmetric FORCE RLS everywhere proprietary + a frozen hash-chained audit service + the full RLS proof matrix per table in CI. Weakest links, in order: the dev auth shim (recorded RTM-P9 boundary), homegrown secret-scan (gitleaks deferred OD-049), WORM/anchored audit hardening (pre-production). None urgent pre-internet-facing; all recorded.
- **Process note (new this wave):** the per-artifact commit gate was retired 2026-07-12 in favor of full delivery autonomy; the REAL controls (USER-merged PRs to `main` under branch protection + Tier-3 decision sign-off + unwaived verification gates + adversarial review before push) are unchanged. This tightens throughput without weakening what actually protects `main`.

## Part 4 — The destination check (thesis §2.1) and where Wave 3 points

Wave 1 built the public-market risk substrate (factors → covariance → VaR ×2 → ex-ante TE). Wave 2 built the return-series spine (PM-1) + its consumers (ex-post TE/IR, backtesting) **and began the private-asset thread** (PA-0 proxy-mapping substrate + the captured-appraisal convention). The thesis §2.1 destination — private assets no longer understating their own risk — now has **both prerequisites in place**: a governed return series (PM-1) and a private→public proxy substrate (PA-0). The one thing still missing is the **transformation math itself**.

The honest reading: **Wave 3 = the private-asset transformation payload.** PA-1 (desmoothing the appraisal return series — Geltner AR(1) v1, the ratified capture-first follow-on) is now UNBLOCKED and is THE differentiation slice — it is where the platform stops passing smoothed marks through as truth. Its natural companion is running the existing governed risk chain (exposure → factor-exposure → VaR) on a private holding **projected through `proxy_mapping`**, demonstrating end-to-end that a private position now carries honest, factor-based risk. Deferring the transformation math again would contradict the ratified destination for a second wave running.

## Part 5 — Wave-3 proposal (for ratification; same per-slice discipline)

| # | Slice | What / why | Size |
|---|---|---|---|
| 1 | **RD-1 — dedup hygiene (early)** | Pay the TIPPED `resolve_*_run` helper family (3 copies → one shared `calc/` resolver with injectable error class) before the code grows further — the clean-code standing bar, and the 3rd-consumer tipping rule is now MET. Test-and-refactor only; NO migration. Small; done first so PA-1 builds on the cleaned resolver. The FR-membership engine (D-2) stays trigger-based unless RD-1 elects the larger extraction. | S/M |
| 2 | **PA-1 — private-asset desmoothing (the thesis payload)** | Geltner AR(1) unsmoothing of captured appraisal return series → a governed desmoothed-return number with the introduced uncertainty stated honestly (thesis §2.1; §2.2 best-in-class bar). Rule-6 externals: Geltner (1991/1993), Getmansky-Lo-Makarov (2004) — and **resolve the UNVERIFIED Okunev-White citation** here. The differentiation slice, now unblocked by PM-1 + PA-0. | M/L |
| 3 | **PA-2 — private holdings on the public factor substrate (end-to-end)** | Project a private holding through `proxy_mapping` onto CURRENCY factors and run the governed exposure→factor-exposure→VaR chain — the demonstration that "private assets no longer understate risk." May fold into PA-1's scope at planning time (its record's call). | M |
| — | **Coarse beyond Wave 3** (themes, not sequenced): the **P7 validation workflow** (BT-1 now feeds it — the nearest supervisory ingredient); ES closed-form leg (seam recorded); credit/counterparty (RTM-P3); limits/breach/SoD (RTM-P6); reporting/dashboards (RTM-P8); SSO/OIDC before internet-facing (RTM-P9). | | — |

Part 4 re-sequencing rules carry over unchanged. Rolling-wave discipline: Wave 3 is named to slice-2/3 fidelity; beyond it stays coarse.

## Part 6 — Open questions for ratification

- **OQ-W2C-1 — Accept the Wave-2 close audit + reconciled deferral register (Parts 1–2).** *Recommend APPROVE — all five ratified slices + the MD-H1 insertion shipped CI-green, zero deviations; MD-H1 paid three bug-shaped deferrals in-wave.*
- **OQ-W2C-2 — Wave-3 spine = the private-asset transformation payload (PA-1 desmoothing → PA-2 proxy-risk end-to-end).** *Recommend APPROVE — the thesis §2.1 destination, now unblocked by PM-1 + PA-0; deferring the transformation math a second wave would contradict the ratified destination.*
- **OQ-W2C-3 — RD-1 dedup as the early Wave-3 hygiene slice (the `resolve_*_run` family has TIPPED at 3 consumers).** *Recommend APPROVE — the clean-code bar + the 3rd-consumer rule both fire; small, and PA-1 then builds on the cleaned resolver.*
- **OQ-W2C-4 — The trigger-based register stays as reconciled (FR-membership engine, covariance adjudicator B, return-shape dedup, lineage batching, the Wave-1 standing items) — no Wave-3 slots.** *Recommend APPROVE — none has reached its named trigger.*
- **OQ-W2C-5 — Outward benchmark review: the nearest remaining supervisory gap is the P7 validation WORKFLOW (BT-1 now feeds it); keep it a coarse post-Wave-3 theme, not pulled forward.** *Recommend APPROVE — the private-asset payload is the higher-leverage, thesis-aligned use of Wave 3; P7 is well-staged and not blocking.*
