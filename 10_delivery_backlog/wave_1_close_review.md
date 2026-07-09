# Wave-1 Close Review + Re-baseline (the mandatory Part-4 rule-2 wave-close)

| Field | Value |
|---|---|
| Status | **RATIFIED by the user (2026-07-09: "Approved" — OQ-W1C-1…6 all approved as recommended, incl. the ES-leg deferral).** Wave 2 = PM-1 → P3-8 → BT-1 → PA-0 → P3-6 + the hygiene ride-alongs; each Wave-2 slice still gets its own decision record + plan + OQ ratification + review + Tier-2 commit approval, starting on explicit direction. |
| Contract | `delivery_roadmap.md` Part 2 tail: "Wave-1 close = a phase-close review + re-baseline (the P2→P3 readiness-review pattern): honest state audit, deferral-register reconciliation, and the Wave-2 proposal briefed plain-language for ratification." Plus Part 4 rule 6(b) / `differentiation_thesis.md`: an **outward-facing benchmark review** and the **public+private destination check** — "the Wave-1 close must explicitly weigh pulling private-asset foundations forward." Plus the TC-1 OD-D obligation: review ALL sub-high npm advisories (runtime AND dev) at wave close. |
| Grounding | Verified live at HEAD **`6a864c9`** (CI run **#133 green**; chain #98–#133 all green): migration head `0030_active_risk`; `make check` 1046 passed / full-PG 230 / FE 43 + build; `npm audit` (full tree, all severities) = **0 vulnerabilities**; local == origin; origin HTTPS (SSH:22 blocked on the current network, recorded). |

---

## Part 1 — Honest state audit (what Wave 1 promised vs. what shipped)

**Promised (ratified 2026-07-08):** TC-1 → VAR-HS-1 → P3-C2 → P2-7 → P3-7 → P3-6, with re-sequencing rules.

**Delivered:** slices 1–5 **plus two ratified insertions** (TD-1 test-data realism, slice 3.5; P3-C3 binder-consistency carry-in) — seven closed slices, every one CI-green with its full gate set. **P3-6 (stress/scenario) did NOT ship** — the one deviation, and a pre-authorized one (the roadmap itself: "if the Wave-1 close review argues for deferring it into Wave 2, that is an expected outcome, not a failure"). Its disposition is OQ-W1C-2.

**The platform as it stands (the executed ledger is `build_plan.md`; this is the wave delta):**
- **Six governed risk numbers** (DV01/spread-DV01, factor exposure, covariance, parametric VaR, historical VaR, ex-ante tracking error), every one snapshot-gated + run-bound + registered-model-bound, IA append-only, reproducible under input correction — the P3 output contract held without exception across the wave.
- **Wave-added surfaces:** the FE toolchain current + a blocking runtime `npm audit` CI gate (TC-1); `metric_type`-discriminated method families on one result table (VAR-HS-1); the shared governed-run scaffold under ALL binders incl. exposure (P3-C2); ENT-052 benchmark level/return capture (P2-7); ENT-027's second physical table + `COMPONENT_KIND_BENCHMARK` + the ACTIVE_RISK run family (P3-7); binder adjudication consistency (P3-C3).
- **Verification posture:** ~1,276 distinct tests (1,046 SQLite-tier + 230 PG-tier) + 43 FE; per-table PG RLS/append-only CI steps now COMPLETE (the P3-7 ultrareview found and closed a class gap: three `_pg` suites — one new, two pre-existing — had no CI step; the lesson "grep `_pg` files vs ci.yml steps at every slice" is recorded).
- **Review discipline compounding:** ~90 adversarial findings folded across the wave (16+30→16+9+~10+4-pass TD-1+21+…); the P3-7 slice piloted the **full multi-agent ultrareview** (10 finders → empirical verifiers → sweep) which caught a durable-value naming error (`run_type` = metric string) at the only cheap moment — evidence the heavier review earns its cost on migration-bearing methodology slices specifically.
- **RTM honesty:** ~18 REQs In-Progress, none newly CLOSED this wave — correct, not concerning: the platform ships REQ *legs* deliberately (e.g. REQ-MKT-001 has parametric + historical legs shipped; ES/MC named); REQ closure requires legs that are recorded prerequisites of later waves. No status inflation found.
- **Known honest gaps (all recorded, none silent):** ex-post TE/active return/IR blocked on a **portfolio-return series that does not exist** (P3-7 OD-G — the sharpest gap this wave *named*); specific/idiosyncratic risk = 0 under allocation-v1 currency-only factors; no shrinkage/EWMA covariance; dev header-shim auth (RTM-P9 boundary); stress absent (P3-6).

## Part 2 — Deferral-register reconciliation (consolidated; dispositions)

**PAID during Wave 1 (register → empty for these):** ALL four P3-3 review deferrals (error-map MRO walk, both-modes refusal, mixed-base grain, persisted `failure_reason` — paid at P3-C1); the scaffold-extraction cleanup (P3-4-R0 + P3-C1); BOTH P3-5 recorded deferrals (REGISTERED-status bind → P3-C1; result/captured-column float parity → P3-C1/P3-C2); the P3-C1 DQ-race residual (→ P3-C2); the P3-7 ultrareview item A + the factor_service wrapper (→ P3-C3); the two pre-existing missing CI PG steps (→ P3-7 fold).

**OPEN — stay deferred with NAMED TRIGGERS (recommendation: ratify as-is, no Wave-2 slot):**
| Item | Trigger that activates it |
|---|---|
| P3-7 **B** — shared covariance-pin adjudicator (2 copies, both test-pinned) | the THIRD covariance consumer lands (P3-4-R0 tipping-point rule) |
| P3-7 **C** — `_persist_snapshot` lineage batching | benchmark/constituent-scale data (hundreds+ pins) becomes real |
| Covariance v2s (Ledoit-Wolf shrinkage / EWMA / correlation / annualization) | accuracy demand or the FHS vol-model prerequisite (they share it) |
| FHS / BRW historical-VaR v2s | a declared vol model (EWMA/GARCH) — same trigger as above |
| Monte-Carlo VaR | seeded simulator + revaluation engine (QS-18) — unchanged |
| Vendor-beta / regression factor exposures; computed factor returns | a loadings-capture slice / adjusted-price history |
| Vol surface (ENT-022); PAR_RATE/interpolation; instrument-attributed sensitivities | their own demand triggers |
| `rating` capture + the REQ-PUB-003 Coverage test; P2-6 weight-SUM DQ (OQ-P2-6-8) | a credit-risk or benchmark-quality slice |
| WORM/anchored audit hardening; gitleaks (OD-049) | pre-production hardening wave |
| Dev header-shim → real SSO/OIDC (RTM-P9) | **before anything internet-facing** (unchanged, restated) |

**OPEN — cheap hygiene, proposed as Wave-2 ride-alongs (OQ-W1C-4):** (a) tighten the runtime npm-audit CI gate `high`→`moderate` — free while the tree is at zero (the TC-1 recorded consideration); (b) **branch protection on `main`** (OD-050) — near-zero cost, real safety; (c) ES closed-form leg — the seam is recorded in `var_service`, S-sized, if wanted alongside.

**TC-1 OD-D obligation DISCHARGED:** `npm audit` full tree, all severities = **0 vulnerabilities** (runtime AND dev) at `6a864c9`. Nothing to review; no frontend-job flakiness recurrence since #112 (the vitest-4 suspect stays closed).

## Part 3 — Outward benchmark review (Part 4 rule 6(b); sources checked 2026-07-09)

- **Architecture / model governance:** the snapshot+run+registered-model+IA contract with declared assumptions/limitations per version matches the SUBSTANCE of supervisory model-risk expectations (SR 11-7 / SS1/23: inventory-before-use, documented methodology, reproducibility). The gap vs. those frameworks is the **validation workflow itself** (independent review/approval states, periodic revalidation) — RTM-P7, honestly staged; `validation_status=UNVALIDATED` recorded non-enforcing on every version. **Backtesting** (SR 11-7 "outcomes analysis"; Basel traffic-light) is the nearest missing supervisory ingredient and is currently blocked on realized P&L — see Part 4.
- **Data design:** bitemporal FR + EV + IA-append-only with byte-stable pins and drift-verify is *ahead of* common practice (most shops reconstruct by convention, not by proof); the TR-09 supersede-invisibility tests are the differentiator worth keeping loud.
- **Methodology:** current numbers are deliberately the honest baselines (equal-weight sample covariance; plain HS; indicator loadings; ex-ante TE) with every deviation from the cited literature (Ledoit-Wolf, FHS/BRW, Barra multi-factor, ESMA ex-post) DECLARED and v2-pathed — consistent with the thesis's "boring base, innovation budget on reproducibility." The declared-parameter-as-version-identity pattern (windows, confidence/z, code_version-only) is stronger than typical vendor practice where parameters are request inputs.
- **Security/engineering:** symmetric FORCE RLS everywhere proprietary + a frozen hash-chained audit service + no-BYPASSRLS invariant is solid multi-tenant hygiene; CI runs the full RLS proof matrix per table. Weakest current links, in order: the dev auth shim (recorded boundary), absent branch protection (OD-050 — cheap), secret-scan is homegrown (gitleaks deferred OD-049). None is urgent pre-internet-facing; all are recorded.

## Part 4 — The destination check (thesis §2.1) and the pivotal fact

The thesis's hard problem is private assets **understating their own risk**; the cure is transformation mathematics — desmoothing appraisal **return series**, proxying private holdings onto the public factor substrate. Wave 1 completed that substrate (factors → covariance → VaR ×2 → TE). The pivotal fact for Wave 2 is that **one missing primitive — a governed portfolio-return series — is the prerequisite for THREE recorded destinations at once:**
1. **Ex-post TE / active return / tracking difference / IR** (the P3-7 OD-G deferral, ESMA-grade) — and `benchmark_return`'s first governed consumer;
2. **VaR backtesting** (Kupiec/traffic-light needs realized P&L) — the P7 model-validation prerequisite and the missing supervisory ingredient from Part 3;
3. **The private-asset return machinery itself** — desmoothing (Geltner; Getmansky-Lo-Makarov) operates ON return series; building governed return-series plumbing on PUBLIC data first means the private leg lands on proven rails.

Weighing "pull private-asset foundations forward" (the mandated check): **yes — but in dependency order.** Starting private-asset capture BEFORE the return-series primitive would build the destination's inputs with nowhere governed to run them. The honest reading of the thesis is therefore: Wave 2 = the return-series spine (public), THEN the private-asset foundations slice begins inside the same wave — not deferred to "a later theme" again.

## Part 5 — Wave-2 proposal (for ratification; same per-slice discipline)

| # | Slice | What / why | Size |
|---|---|---|---|
| 1 | **PM-1 — governed portfolio-return series** | Performance-measurement v1: flow-adjusted time-weighted returns (TWR; Modified-Dietz where sub-period marks are absent) over captured valuations + transactions — a NEW governed number family (`perf.return.twr` v1) with the full output contract. Rule-6 externals: GIPS 2020, CFA performance literature. **The triple unlock** (Part 4). | M/L |
| 2 | **P3-8 — ex-post benchmark-relative** | Realized TE / active return / tracking difference / IR over PM-1 + `benchmark_return` (its FIRST governed consumer — closes P3-7 OD-G exactly as recorded). Rule-6: ESMA 2012/832 now applies directly. | S/M |
| 3 | **BT-1 — VaR backtesting** | Kupiec POF + Basel traffic-light over realized P&L vs BOTH shipped VaR methods; the P7 prerequisite; SR 11-7 "outcomes analysis." | M |
| 4 | **PA-0 — private-asset foundations** | The destination begins: captured appraisal/NAV series (P2-style captured-data slice) + ENT-019 `proxy_mapping` realization + the desmoothing/proxy decision record (rule-6: Geltner 1993; Getmansky-Lo-Makarov 2004; Okunev-White). Planning may conclude it splits capture-first — that's its own record's call. | M/L |
| 5 | **P3-6 — stress/scenario** | Moved from Wave 1 (pre-authorized). Sequenced AFTER the return work deliberately: scenario P&L over a platform that also has realized-return machinery is a richer, better-grounded slice; RTM-P5 always said late. May defer again to Wave 3 at the next close — same rule. | L |
| — | **Hygiene ride-alongs** (no slice slot): CI audit gate → `moderate`; branch protection (OD-050); ES leg if wanted. | | S |

Part 4 re-sequencing rules carry over unchanged. Coarse beyond Wave 2: credit/counterparty (RTM-P3), limits/SoD (P6), validation workflow (P7 — BT-1 feeds it), reporting (P8), SSO (P9).

## Part 6 — Open questions for ratification

- **OQ-W1C-1 — Accept the Wave-1 close audit + reconciled deferral register (Parts 1–2).** *Recommend APPROVE.*
- **OQ-W1C-2 — P3-6 disposition: move to Wave-2 slot 5 (not dropped, not Wave-1-blocking).** *Recommend APPROVE — the pre-authorized outcome, now with a positive reason (richer after return machinery), not just deprioritization.*
- **OQ-W1C-3 — Wave-2 spine = PM-1 → P3-8 → BT-1 (the return-series triple unlock).** *Recommend APPROVE — the highest-leverage dependency-ordered sequence on the board; it converts three recorded deferrals into consumers of one new primitive.*
- **OQ-W1C-4 — Hygiene ride-alongs: npm gate → moderate; branch protection.** *Recommend APPROVE (both near-free; the audit tree is at zero right now).* ES leg: *recommend DEFER unless wanted — it's cheap but nothing downstream needs it yet.*
- **OQ-W1C-5 — PA-0 (private-asset foundations) IN Wave 2 at slot 4.** *Recommend APPROVE — the thesis check answered "forward, in dependency order"; deferring it to "a later theme" again would contradict the ratified destination.*
- **OQ-W1C-6 — B + C and the trigger-based register stay as reconciled (no Wave-2 slots).** *Recommend APPROVE.*
