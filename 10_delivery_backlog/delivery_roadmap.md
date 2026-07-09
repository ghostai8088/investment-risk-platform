# Delivery Roadmap (rolling-wave)

| Field | Value |
|---|---|
| Status | **RATIFIED by the user (2026-07-08: "Proceed" on the full package — Wave 1 order + the Part 4 re-sequencing rules — after a plain-language briefing incl. the documentation-alignment audit)** |
| Date | 2026-07-08 |
| Purpose | The operative near-term slice sequence + the re-baselining rules, so slice-boundary "what next?" decisions stop being ad-hoc menus (user direction 2026-07-08: a plan to avoid drift and rabbit holes, explicitly NOT immutable). |
| Relationship | `build_sequence.md` = the ratified RTM **theme/phase map** (what the platform must eventually contain, and roughly in what order — unchanged). `docs/project_memory/build_plan.md` = the **executed ledger** (what has shipped). THIS document = the **operative sequence** for the next wave of slices. The per-slice discipline (decision record + plan + OQ ratification + adversarial review + Tier-2 commit approval) is UNCHANGED by this document. |
| Basis | All P0.5–P3 records; the consolidated deferral registers; the FE-1 walking-skeleton direction; the user's standing preferences (plain-language gate briefings; objective recommendations; ask on ambiguity with a recommendation attached). |

---

## Part 1 — Principle: rolling-wave, not big-bang planning

High fidelity for the NEAR term (the ratified Wave 1 below — named slices, order, rationale); deliberately COARSE
beyond it (themes only). Detail is added when a wave closes, not before — a detailed twelve-month software plan is
fiction, and treating fiction as commitment produces its own drift (building to the plan after the facts have
changed). Phase boundaries were always revisit-able (`build_sequence.md` §7 has said so since genesis); this
document makes the revisiting DISCIPLINED (Part 4) instead of a menu at every slice boundary.

**Numbering note (drift, now reconciled):** the executed phases (P0.5, P1A/B/C, P2, P3…) diverged from
`build_sequence.md`'s RTM phase numbers early (the RTM map's P2 theme "public market data + market-risk core" was
executed as OUR P2+P3; the RTM's P5 stress theme is why stress carries the "RTM-P5" caveat). Cross-references
below always name which numbering they use.

## Part 2 — Wave 1: the ratified near-term sequence

Each slice still gets its own decision record + plan + gates; this table fixes ORDER and INTENT only.

| # | Slice | What / why | Size | Dependencies |
|---|---|---|---|---|
| 1 | **TC-1 — FE toolchain bump** ✅ **DONE** (`c34b346`, CI #112) | vite 5→current + vitest 2→current majors (closes the recorded dev-only advisory chain), CI Node alignment, + a **production-deps `npm audit` CI step** (runtime supply-chain issues turn CI red on their own). Mostly mechanical; do it while the frontend context is fresh. Keep-Vite/Vitest decision already accepted by the user (2026-07-08). | S | none |
| 2 | **VAR-HS-1 — historical-simulation VaR** | The second VaR method (user-directed roadmap 2026-07-07): factor-based historical simulation over the captured factor-return windows — its own registered model family + methodology doc + declared parameters (window adequacy, quantile interpolation). No new UI work needed: hist-sim runs surface in the FE-1 view automatically (same VAR run family). | M/L | none (data already captured) |
| 3 | **P3-C2 — hardening bundle** ✅ **DONE** (`6fb1a13`, CI green) | The accumulated recorded follow-ups swept in one consolidation slice (the P3-C1 pattern): exposure-family scaffold/`failure_reason` adoption (scaffold relocated risk→calc); exposure runs in the FE listing (`exposure.view` handling; source-switch); captured-input-table `PreciseDecimal` parity (incl. `transaction` via the review); the DQ-rule first-registration savepoint race. NO migration. Full 6-finder review, 9 folds. | M | none |
| 3.5 | **TD-1 — test-data realism audit** ✅ **DONE** (`ac92e0b` + follow-up `4534a38`, CI green) | A hygiene insertion (Part 4 rule 3) ahead of P2-7 implementation: retrospectively audited + remediated existing economic-value fixtures to the new fixture-realism standing rule (three-bucket classify-then-fix; test-and-docs-only diff fence). The base fixtures were already plausible; 8 signal-forcing/ordinary values in the factor-return/covariance/VaR/sensitivity/exposure test fixtures were remediated. NO golden re-derivation (chosen values preserve invariance/inequality/pinning asserts). 4 independent finder passes caught 2 author errors + 2 same-class completeness misses — all folded. NEW `08_testing_qa/test_data_realism.md` + a standing review-angle. TD-2 not needed. | M/L | none |
| 4 | **P2-7 — benchmark price/level capture** ✅ **DONE** (plan `04c4135`; impl `ea2863d`, CI green) | The captured-input slice (`benchmark_level`/`benchmark_return`, NET-NEW **ENT-052**) that unblocks every return-based benchmark-relative analytic. FR/bitemporal; captured returns ONLY (no calc from levels); migration `0029`; no new permission; six additive `MARKET.BENCHMARK_LEVEL_*`/`_RETURN_*` audit codes. Full 6-finder review, ~10 folds. **OD-G precision amendment (2026-07-09):** P2-7 unblocked the **ex-ante** benchmark-relative half only — the ex-ante tracking error consumes the benchmark **membership** (P2-6); the **ex-post** measure (realized TE / active return / IR / tracking difference) additionally requires a governed **portfolio-return series**, a separately-planned performance-measurement slice where `benchmark_return`'s first governed consumer lands. | M | none |
| 5 | **P3-7 — benchmark-relative analytics** ✅ **DONE** (plan `552b954`; impl `65e6dbe`, CI green) | Ex-ante active risk / tracking error `TE = √(wₐᵀΣwₐ)` over the existing factor-exposure + covariance engine and the captured benchmark membership — the P3 plan's final **ex-ante** analytic leg (`active_risk_result`, ENT-027; migration `0030`; `COMPONENT_KIND_BENCHMARK` minted; run family `ACTIVE_RISK`, metric `TRACKING_ERROR`). FULL max-effort multi-agent review (10 finders + 6 verifiers + sweep): 21 folds, 3 deferred findings recorded in the decision record Part 6 (var_service V2/V5 twins; shared covariance adjudicator; lineage batching). The **ex-post** leg (realized TE / active return / IR) is DEFERRED on the portfolio-return prerequisite (OD-G). | M/L | slice 4 |
| 6 | **P3-6 — stress/scenario** → **MOVED to Wave 2 slot 5** (Wave-1 close review, 2026-07-09 — the pre-authorized outcome, with a positive reason: scenario P&L is richer once realized-return machinery exists) | ENT-029/030 (scenario definitions + results). Sequenced LAST in the wave deliberately: our own P3-0 record flags it as RTM-P5-phase (possibly later); doing it after benchmark-relative completes the P3 analytics story without pulling it ahead of cheaper wins. If the Wave-1 close review argues for deferring it into Wave 2, that is an expected outcome, not a failure. | L | none (independent) |

**Wave 1 CLOSED (2026-07-09):** `wave_1_close_review.md` **RATIFIED** (OQ-W1C-1…6) — honest state audit + the
reconciled deferral register + the outward benchmark review + the destination check. Slices 1–5 + two ratified
insertions (TD-1, P3-C3) shipped CI-green; P3-6 moved to Wave 2 (pre-authorized). The TC-1 OD-D obligation
discharged (`npm audit` full tree, all severities = 0 at `6a864c9`).

## Part 2.5 — Wave 2: the ratified sequence (2026-07-09; same per-slice discipline)

**The organizing fact (from the close review Part 4):** ONE missing primitive — a governed portfolio-return
series — is the prerequisite for THREE recorded destinations (ex-post TE/IR per P3-7 OD-G; VaR backtesting;
the private-asset desmoothing machinery). Wave 2 builds it first, then its consumers, then begins the thesis
destination in dependency order.

| # | Slice | What / why | Size |
|---|---|---|---|
| 1 | **PM-1 — governed portfolio-return series** | Performance-measurement v1: flow-adjusted TWR (Modified-Dietz where sub-period marks are absent) over captured valuations + transactions — a NEW governed number family (`perf.return.twr` v1), full output contract. Rule-6 externals: GIPS 2020. The triple unlock. | M/L |
| 2 | **P3-8 — ex-post benchmark-relative** | Realized TE / active return / tracking difference / IR over PM-1 + `benchmark_return` (its FIRST governed consumer — closes P3-7 OD-G). Rule-6: ESMA 2012/832 applies directly. | S/M |
| 3 | **BT-1 — VaR backtesting** | Kupiec POF + Basel traffic-light over realized P&L vs BOTH shipped VaR methods; the P7 model-validation prerequisite (SR 11-7 "outcomes analysis"). | M |
| 4 | **PA-0 — private-asset foundations** | The thesis destination begins: captured appraisal/NAV series + ENT-019 `proxy_mapping` realization + the desmoothing/proxy decision record (rule-6: Geltner 1993; Getmansky-Lo-Makarov 2004; Okunev-White). Its planning may split capture-first. | M/L |
| 5 | **P3-6 — stress/scenario** | Moved from Wave 1; richer after the return work; may defer again to Wave 3 at the next close — same rule. | L |
| — | **Hygiene ride-alongs** (no slice slot): runtime npm-audit CI gate `high`→`moderate` (applied AT this close — the tree is at zero); branch protection on `main` (OD-050 — a GitHub settings action, see the close review); ES leg DEFERRED (OQ-W1C-4). | | S |

**Wave-2 close = the same mandatory review + re-baseline** (incl. the rule-6(b) outward benchmark review + the
destination-progress check).

## Part 3 — Beyond Wave 1 (coarse; themes from the RTM map, NOT sequenced yet)

- **VaR completions (on demand):** ES (closed-form seam already recorded); √h multi-horizon; component/marginal
  VaR; backtesting (also a prerequisite for the P7-theme model-validation workflow); Monte-Carlo (GATED: needs a
  seeded simulator + revaluation engine, QS-18).
- **Credit & counterparty risk** (RTM-P3 theme) · **Private assets + liquidity** (RTM-P4) · **Limits, breach
  workflow + SoD enforcement** (RTM-P6) · **Full model governance / validation workflow + DQ reconciliation**
  (RTM-P7) · **Reporting & dashboards** (RTM-P8) · **Real SSO/OIDC + admin + vendor adapters** (RTM-P9 — the dev
  header shim is replaced HERE at the latest, before anything internet-facing) · **BAU AI + hardening** (RTM-P10).
- **Frontend growth:** incremental read-only surfaces ride along where they're nearly free (the FE-1 view already
  absorbs new run families automatically); dashboards/reporting stay an RTM-P8 theme, not drive-by additions.
- Standing deferrals with NO assigned wave (each needs its own trigger): covariance v2s (shrinkage/EWMA/
  correlation/annualization); vendor-beta/regression factor exposures (needs a loadings capture slice); computed
  factor returns (needs adjusted prices); vol surface capture (ENT-022); PAR_RATE/interpolation/instrument-level
  sensitivity attribution; WORM/anchored audit hardening; gitleaks (OD-049); branch protection (OD-050).

## Part 4 — Re-sequencing rules (what makes this a plan, not a straitjacket)

1. **The default is the sequence.** At each slice close, the next Wave-1 slice proceeds on the user's go — no
   options menu is re-presented.
2. **Re-sequencing triggers (any of):** a wave closes (mandatory re-baseline); an adversarial review or build
   surfaces something structural; a dependency proves blocked or an assumption false; the user changes priorities.
3. **Every re-sequence is a recorded decision:** this document is amended with a one-line dated rationale and the
   change is briefed in plain language for ratification. Small hygiene insertions (a TC-1-sized slice) may be
   PROPOSED between slices but still ratify before starting.
4. **Ambiguity rule (user-stated, 2026-07-08):** where a slice hits a genuine fork, ask the user — always with an
   objective recommendation attached; the user decides.
5. **What never moves without its own gate:** the per-slice planning/review/commit discipline; the hard
   invariants (frozen audit service; no BYPASSRLS; R-07 for permissions/audit codes; the governed derived-number
   contract).

6. **Thesis alignment (ratified 2026-07-08 — see `01_product_strategy/differentiation_thesis.md`):**
   (a) every METHODOLOGY slice's decision record includes a **cited external-benchmark research section**
   (published/academic/regulatory sources + dates checked; deviations fixed or justified) — explicitly including
   transformation/proxy math when private-asset slices begin; (b) every wave-close re-baseline includes an
   **outward-facing benchmark review** (architecture / data design / methodologies / security / engineering
   practice vs. current published best practice) and **evaluates progress toward the public+private destination**
   — the Wave-1 close must explicitly weigh pulling private-asset foundations forward.
## Part 5 — Amendment log

| Date | Change | Why |
|---|---|---|
| 2026-07-08 | Document created; Wave 1 = TC-1 → VAR-HS-1 → P3-C2 → P2-7 → P3-7 → P3-6. | User direction: replace per-slice option menus with a ratified rolling-wave sequence. |
| 2026-07-08 | Part 4 rule 6 added (thesis alignment: per-methodology external-benchmark research; wave-close outward benchmark review + public/private destination check). TC-1 marked DONE. | The ratified differentiation thesis (`01_product_strategy/differentiation_thesis.md`); user-directed best-in-breed review approach. |
| 2026-07-08 | VAR-HS-1 (`29ae31b`, #117) then P3-C2 (`6fb1a13`, CI green) marked DONE. Wave-1 slices 1–3 complete; next = P2-7 (benchmark price/level capture). | Sequential slice completion per the ratified sequence. |
| 2026-07-09 | P2-7 planning ratified + committed (`04c4135`). **TD-1 (test-data realism audit) INSERTED as slice 3.5** ahead of P2-7 implementation (OQ-TD-1-1…6 ratified). | Part 4 rule 3 hygiene insertion: a new user standing rule (fixtures economically plausible by default) warranted a retrospective audit+remediation slice; user directed a full hygiene slice now. |
| 2026-07-09 | **TD-1 DONE** (`ac92e0b` + follow-up `4534a38`, CI green). Next = P2-7 implementation. | Slice complete: base fixtures already plausible; 8 fixtures remediated; 4 independent finder passes; new fixture-realism reference doc + standing review-angle. |
| 2026-07-09 | **P2-7 DONE** (`ea2863d`, CI green): ENT-052 benchmark_level/return, migration 0029. Wave-1 slices 1–4 complete; next = P3-7 (benchmark-relative analytics), now unblocked. | Sequential slice completion per the ratified sequence. |
| 2026-07-09 | **P3-7 DONE** (`65e6dbe`, CI green): ex-ante active risk / tracking error — `active_risk_result` (ENT-027), migration 0030, `COMPONENT_KIND_BENCHMARK`. First user-directed FULL max-effort multi-agent review ("ultrareview"): 21 folds incl. the run_type=ACTIVE_RISK family/metric split + 3 missing CI PG steps; 3 deferred findings recorded (decision record Part 6). Wave-1 slices 1–5 complete; remaining = P3-6 (stress) then the Wave-1 close review. | Sequential slice completion; the ultrareview folds ratified by the user 2026-07-09 ("fix them all"). |
| 2026-07-09 | **P3-C3 DONE** (`1bf172b`, CI #132 green): a hardening CARRY-IN (Part 4 rule 3) paying the P3-7 ultrareview's item-A deferral — binder adjudication consistency (`TypeError` + `base_currency` 3-letter shape gate across var/var_hs/factor so all binders fail-close identically on malformed pins; factor_service also gained the malformed-pin wrapper it entirely lacked — an OD-A Part-3 discovery). Test-and-binder only; NO migration/permission/audit. Items B (shared covariance adjudicator) + C (lineage batching) formally re-deferred (record OD-E). | User chose to pay the debt while fresh (Option 3, item A); B/C deferred on the P3-4-R0 tipping-point rule + scale-driven timing. |
| 2026-07-09 | **WAVE 1 CLOSED — `wave_1_close_review.md` RATIFIED (OQ-W1C-1…6)**: honest audit (5 slices + 2 insertions shipped, all CI-green; ~90 review findings folded; npm audit 0 at all severities); deferral register reconciled (all P3-3/P3-5/P3-C1 deferrals PAID in-wave; open items now trigger-based incl. P3-7 B+C); the outward benchmark review + the thesis destination check. **Wave 2 ratified (Part 2.5): PM-1 → P3-8 → BT-1 → PA-0 → P3-6** — organized around the return-series triple unlock (ex-post TE/IR + backtesting + desmoothing substrate share ONE missing primitive). P3-6 moved (pre-authorized). Ride-alongs: npm CI gate high→moderate applied at this close; branch protection = a user GitHub-settings action; ES deferred. | The mandatory Part-4 rule-2 wave-close re-baseline; user ratified 2026-07-09 ("Approved"). |
