# Wave-4 Close Review + Re-baseline (the mandatory Part-4 rule-2 wave-close)

| Field | Value |
|---|---|
| Status | **RATIFIED by the user (2026-07-14): OQ-W4C-1/3/4/5/6 approved as recommended; OQ-W4C-2 (the Wave-5 direction fork) answered "A: Self-governance".** Wave 5 (ratified, roadmap Part 2.8): **RD-3 (hygiene) → VW-1 (model-validation workflow, SR 11-7, incl. estimate-staleness governance) → BT-2 (total-series backtest) → ES-1 (parametric ES)** — "the numbers govern themselves"; multi-family factor capture teed as the Wave-6 headline. |
| Date | 2026-07-14 (main HEAD `2354a3f` at audit time) |
| Method | Three independent parallel auditors (shipped-as-ratified; deferral-register reconciliation; outward benchmark + destination check), every claim verified in code/git/CI — not from records — then fold-synthesized. Mechanical hygiene fixes found by the audit are applied ON THIS BRANCH (the Wave-3 precedent) and documented in Part 1. |
| Wave 4 | RD-2 (PR #26 = `cc9679b`) → PA-3 (PR #28 = `a98d380`, migration `0037`) → PA-4 (PR #30 = `8ef70db` + closeout PR #31 = `2354a3f`, migration `0038`). **First wave partially delivered under the 2026-07-14 EXTENDED autonomy grant** (PA-4's PRs opened + merged by Claude; RD-2/PA-3 merged by the user pre-extension). |

## Part 1 — Honest state audit (what Wave 4 promised vs. what shipped)

**Promised (ratified 2026-07-13 at the Wave-3 close, fork A "Deepen private assets"):** RD-2 (hygiene,
early) → PA-3 (regression-estimated proxy weights, the loop-closer) → a v2 companion chosen at planning.
**Delivered: all three, CI-green, in the ratified sequence — no re-sequencing, no slip.** The companion
call went to residual variance (OQ-PA-4-1), making Wave 4 the *estimate-to-total-risk* wave.

**Per-slice audit (each verified against its ratified record by an independent auditor):**

- **RD-2** (`11f890d` via **PR #26**; NO migration). **Verdict: SHIPPED-AS-RATIFIED.** OD-A…D all
  verified in code (the three `model/assumptions.py` primitives hold the SOLE surviving
  `select(ModelAssumption)`; zero `_single(` leftovers; all four resolver folds present). The
  `_DIGITS_PATTERN` dedup beyond enumerated scope was RECORDED. **One SILENT micro-deviation
  (note-level):** plan step 1 said "export via `model/__init__.py`" — the init is docstring-only and
  consumers import the module directly, matching the house import pattern; the plan text was wrong, the
  code is right, but the deviation was unrecorded until now. Recorded here; no code change (register:
  none — the house pattern is the standard).
- **PA-3** (`15ba13f`→`77149d6` via **PR #28**; migration `0037`). **Verdict: SHIPPED-AS-RATIFIED, with
  one MATERIAL amendment to ratified OD-E — fully RECORDED** (the Fable fold-synthesis pass:
  citation-carrying supersede / promote-or-repromote / correction-can-never-mint-REGRESSION, including
  the honest admission that the first fold over-closed and was corrected at `b078396`). Code verified
  live. One LOW inconsistency found + fixed on this branch: the roadmap log's "280 skipped" vs the
  record's contemporaneous "274 skipped" (harmonized to 274).
- **PA-4** (`d3a6eae`→`c04768e` via **PR #30**; closeout **PR #31**; migration `0038`). **Verdict:
  SHIPPED-AS-RATIFIED on substance** — both in-build refinements (declared `appraisal_days`;
  MV = factor-exposure sums) are properly recorded as Part-6.1 OD amendments, NOT silent; the
  `1−Σw` partial-proxy leg is claimed discharged NOWHERE (verified across roadmap/methodology/record);
  the 4-finder review + folds verified live in code (parse-back floor, mapping-method gate, CI PG step,
  symmetric predicate). **Record-hygiene defects found + fixed on this branch:** (a) the record was
  never stamped CLOSED (no PR #30/#31 refs anywhere — the closeout PR #31 omitted it; Part 6.5 now
  added); (b) the record's header still said "the USER merges the PR" — factually wrong for how PA-4
  shipped (amended); (c) `claude_operating_instructions.md:145` still carried a leftover "leaves the PR
  for the user to merge" contradicting the same file's own Tier-2 extension text (fixed).

**Wave headline verification:** thirteen governed numbers **CONFIRMED under the established ordinal
convention** — with the honest census note that a registrar count yields **14 registered model
families** (PA-2's `risk.factor_exposure.proxy` carries no ordinal — it re-produces
`factor_exposure_result` through the same binder) over **11 IA result tables** (HS/total VaR reuse
`var_result`; the proxy family reuses `factor_exposure_result`). Migration head
`0038_var_residual_variance`, single head, chain verified.

**Also fixed on this branch (audit findings 6–7):** `current_state.md`'s 2026-07-14 pointer now
supersedes ALL stale claims in that file (not just the merge-rule ones); `phase_status.md` +
`next_actions.md` (both frozen at the PA-0 era, contradicting the autonomy grant and understating the
platform) carry a STALE-BELOW banner pointing at the roadmap as the operative ledger. A full re-baseline
of those two ledgers is deliberately NOT done here — it is registered as wave-close-optional
housekeeping, not product work.

**Verification posture across the wave:** every slice CI-green (branch + merged-main runs verified via
the REST API); PA-3's PG leg first executed live in PR #28's CI (Docker unavailable locally at
delivery — recorded); PA-4 validated against a schema-reset local PG + CI; the full battery at the
wave end: ruff/mypy clean, full suite green incl. the PG leg. Review discipline: proportionate 4-finder
on RD-2 (3 CLEAN), FULL 4-finder incl. Fable-class numeric finders on PA-3 AND PA-4 (independent
re-derivations byte-exact both times; PA-4 additionally fuzzed 6000 cases + 12/12 adversarial probes).

## Part 2 — Deferral-register reconciliation (verified in code, not records)

**PAID during/for Wave 4:** PA-1 D-1 declared-parameter parse-back (RD-2); the RD-1 resolver census
undercount (RD-2); P3-7 deferral-1 var_service twins (P3-C3, pre-wave, verified still live); BT-1
deferral-B registrar race (MD-H1 — and the helper pattern HELD for both new Wave-4 registrars); PA-0
A/B (MD-H1); PA-2 v2 regression weights (PA-3 — the slice itself); PA-2 v2 residual variance (PA-4);
the Okunev-White flag (PA-1 planning, standing).

**NEWLY TIPPED this wave (recommendation: the early Wave-5 hygiene slice, RD-3 — OQ-W4C-3):**

| Item | Why tipped (verified) |
|---|---|
| **P3-8 `_reresolve_content` parse-hardening** | Trigger ("next slice touching the verify path") fired TWICE (PA-3 + PA-4 both edited it); the malformed-pin parse sites inside `_reresolve_content` still escape `verify_snapshot`'s except tuple as 500s, and the exposed class GREW with the three new component branches. |
| **PA-1 D-2 instrument-guard fold (the `proxy_mapping.py` half)** | Trigger ("next touch of the file") fired at PA-3 (three edits); `_resolve_instrument_id` is still hand-rolled, not a `reference/guards` delegate. The `reference/instrument.py:resolve_instrument` half is NOT foldable (returns the row — a resolver, not a guard); register note, not a fold. |
| **MD-H1 deferral C — annex adoption breadth** (GUC re-arm sweep + per-binder `parse_strict_decimal`) | Self-declared "a wave-close candidate (mechanical, zero behavior change)" — the trigger is definitionally NOW; only partial organic progress (PA-3's factor `return_value`). |
| *Ride-along:* **PG cross-module seed collision** (data_quality/lineage/synthetic under one unreset session) | Sole record is PA-4 Part 6.4; test-infra, pairs naturally with the re-arm sweep (per-module id namespacing or session reset). |

**NEWLY MINTED this close (the one gap the records had not yet named — OQ-W4C-4):**
**estimate staleness / refresh-cadence governance.** Nothing forces a promoted REGRESSION weight to
cite a recent estimate, expires one, or even records estimate age at total-VaR time — a years-stale
`σ_e` drives current total VaR indefinitely and silently. Registered with the natural home = the P7
validation workflow's ongoing-monitoring leg (SR 11-7), or a standalone DQ gate if P7 is not chosen.

**OPEN — trigger-based, stays (all verified NOT tipped):** P3-7 B covariance-pin adjudicator (counted:
still exactly 2 copies; PA-4 REUSES var_service's — no third); P3-8/BT-1 return-shape dedup (still 2
ENT-053 consumers; PA-3's ENT-056 adjudicator is the same pattern CLASS on a different entity —
pressure noted, trigger not met); P3-7 C lineage batching (constituent-scale pins now exist in two
snapshot flavors but only at test scale); FR-membership generalization (still 2 instances); PA-2 v2 A
proxy-aware active-risk; IRR/capital-calls (relabel PA-5/PM-2 on firing); PA-4 deferrals 1–3
(total-series backtest; quantize-then-gate alternative; shrinkage/EWMA/calendar-aware/HS-ES-total
v2s); PA-3 deferrals 1–2 (partial-unique singleton index; the platform-wide `[1E8−½ulp,1E8)` envelope
edge); the covariance/VaR v2 pool; vendor-beta/computed-factor-returns/vol-surface/PAR_RATE;
rating + REQ-PUB-003 + weight-SUM DQ; trading-calendar validation; WORM/gitleaks; SSO/OIDC
(unchanged: **before anything internet-facing**); MD-H1 A/B/D; the methodology scope-out pool.

## Part 3 — Outward benchmark review (Part 4 rule 6(b); sources = the records' own citations)

Ranked by supervisory/academic materiality × dependency-readiness given what NOW ships:

1. **P7 model-validation workflow (SR 11-7) — M.** All 13 governed models sit at a NON-ENFORCING
   `validation_status=UNVALIDATED`. Every ingredient it consumes exists (BT-1 outcomes analysis,
   machine-readable registry/assumptions/limitations, per-model methodology referents). The named
   "nearest supervisory gap" at THREE consecutive closes; the natural home for the newly-minted
   staleness-governance item; the first real WORKFLOW consumer of the thesis §2.3 AI-ready layer.
2. **Total-series backtesting — S code / M methodology.** The flagship differentiation number is
   currently exempt from the platform's own outcomes analysis (`METRIC_TYPES` exclusion — deliberate,
   recorded, and the first thing a supervisor would flag). The honest work is pairing semantics
   (daily VaR vs appraisal-driven realized P&L), not the constant swap.
3. **Parametric ES (FRTB) — S.** The closed-form seam (`ES = σ·φ(z)/(1−α)`, `ES_PARAMETRIC` reserved
   by value) has been recorded since P3-5; FRTB made 97.5% ES the regulatory measure. Over PA-4's
   `σ_total` the same form yields a total-ES for the private book nearly free.
4. **Multi-family factor coverage — L, gated.** The single biggest thesis-§2.2 realism gap
   (CURRENCY-only, verified), but it REQUIRES an equity/credit factor-returns capture slice first,
   and its realism payoff is largest after validation/staleness/shrinkage make the deeper numbers
   defensible. The natural Wave-6 headline.
5. **Residual shrinkage/EWMA (Barra/Axioma), desmoothing v2s, covariance v2s — S/M ride-alongs**,
   materiality capped until multi-family lands.

## Part 4 — The destination check (thesis §2.1/§2.2) and where Wave 5 points

**Wave-3 stub #1 (captured-not-estimated weights): DISCHARGED** — PA-3's estimate→promote loop is live,
symmetric, evidence-cited, and re-promotable; the full-chain integration proof now runs at the PA-4
layer (promote → factor risk → total VaR on the governed build path). PA-1's desmoothed series is
load-bearing twice over. **Wave-3 stub #2 (CURRENCY-only factors): OPEN**, verified.

**The chain now:** capture → desmooth → estimate (with stated uncertainty) → promote (deliberate,
cited) → factor risk → **total** VaR with a persisted decomposition. The destination has moved from
"reached with two stub links" to "**structurally complete and vendor-aligned**" (the PA-4 record's
MSCI benchmark: this is the shape every major carries). What remains is **fidelity** (multi-family,
shrinkage, desmoothing v2s) and **governance-of-time** (validation, staleness, backtest coverage) —
not missing structure. The honest-stub register after Wave 4: multi-family; `1−Σw` unmodeled;
proxy-aware active risk; estimate staleness (newly minted); total series unbacktested; diagonal
residuals; no FX in the residual leg; MANUAL-weight books still understate; Geltner-only desmoothing;
the IRR/capital-calls leg; PM-1 book bias; ES/MC/component-VaR; the P7 workflow itself.

**The direction argument (put honestly):** two consecutive waves deepened the private-asset payload and
the bet paid — but §2.2's bar is academic AND regulatory SOTA, and the outlier gaps have flipped
sides: the private chain now matches recognized structure at v1 fidelity, while the flagship number is
unvalidated, unbacktested, and missing the FRTB-preferred measure whose seam has been recorded since
P3-5. The deepest next private-asset rung (multi-family) needs an L-sized capture substrate anyway.

## Part 5 — Wave-5 proposal (for ratification; same per-slice discipline)

**Spine A (recommended): "the numbers govern themselves" —**

| # | Slice | What / why | Size |
|---|---|---|---|
| 1 | **RD-3 — hygiene (early)** | The three TIPPED items (`_reresolve_content` parse-hardening; the `proxy_mapping` instrument-guard fold; the MD-H1-C mechanical adoption sweep) + the PG seed-collision test-infra fix as ride-along. The RD-1/RD-2 precedent form. | S/M |
| 2 | **VW-1 — model-validation workflow (P7 / SR 11-7)** | Validation states + independent-review/approval transitions on the registry (today non-enforcing `UNVALIDATED` everywhere); periodic-revalidation triggers consuming BT-1 outcomes; the **estimate-staleness governance** item folded in as the ongoing-monitoring leg. The headline: the nearest supervisory gap, three closes running. | M |
| 3 | **BT-2 — total-series backtest** | Extend outcomes analysis to `VAR_PARAMETRIC_TOTAL` — the pairing-semantics methodology (daily VaR vs appraisal-marked realized P&L) done honestly, not a constant swap. Discharges PA-4 deferral 1. | S/M |
| 4 | **ES-1 — parametric ES leg** | The closed-form seam over BOTH σ and σ_total (`ES_PARAMETRIC` reserved since P3-5; FRTB's preferred measure). | S |

Then the **Wave-5 close review**, with **multi-family factor capture teed as the Wave-6 headline**
(shrinkage + desmoothing v2s riding when it lands).

**Spine B (the legitimate counter-case):** pull private-assets forward again — the equity/credit
factor-returns capture slice now (L), then multi-family proxying. Defensible under §2.1's sequencing
language; weaker because the realism gain is largest AFTER the governance rails exist, and fork B
(supervisory) has now been deferred at two consecutive closes. **Spine C:** breadth
(credit/limits/reporting themes) — no new argument this wave.

## Part 6 — Open questions for ratification

- **OQ-W4C-1 — Accept the Wave-4 close audit (Part 1):** all three ratified slices shipped CI-green in
  sequence; RD-2 + PA-3 + PA-4 SHIPPED-AS-RATIFIED (PA-3's OD-E amendment and PA-4's two OD refinements
  all properly recorded); the audit's 8 findings were record-hygiene/consistency class — the 5
  mechanical ones FIXED on this branch (PA-4 closure stamp; the two stale merge-rule lines; the PA-3
  skip-count; the stale-ledger banners), the RD-2 export micro-deviation recorded, none silent anymore.
  *Recommend APPROVE.*
- **OQ-W4C-2 — The Wave-5 direction fork: (A) "the numbers govern themselves" (VW-1 validation workflow
  + BT-2 total-backtest + ES-1, behind the RD-3 hygiene slice), (B) private-assets deeper now
  (equity/credit factor capture → multi-family), or (C) breadth.** *Recommend (A) — after two
  payload waves the flagship number is unvalidated, unbacktested, and missing the FRTB measure; A
  consumes three slices of already-shipped evidence and makes every future number cheaper to defend;
  multi-family becomes the Wave-6 headline with its capture substrate planned properly. **This is the
  genuine Tier-3 call — your decision.***
- **OQ-W4C-3 — RD-3 as the early Wave-5 hygiene slice** folding the three TIPPED items + the
  seed-collision test-infra ride-along. *Recommend APPROVE — all three triggers verifiably fired; the
  RD-1/RD-2 precedent; small.*
- **OQ-W4C-4 — MINT the estimate-staleness/refresh-cadence governance register item** (nothing ages or
  expires a promoted σ_e today; not previously recorded anywhere), homed in VW-1's ongoing-monitoring
  leg under spine A, or as a standalone DQ-gate item otherwise. *Recommend APPROVE — the one genuinely
  new gap this review found; minting it is due diligence regardless of the fork.*
- **OQ-W4C-5 — The trigger-based register stays as reconciled in Part 2** (incl. the counted-not-tipped
  verdicts on the covariance-pin and return-shape dedups, and the ENT-056 pattern-pressure note). *
  Recommend APPROVE — every trigger was verified in code, none met.*
- **OQ-W4C-6 — Accept the headline-count convention note:** "thirteen governed numbers" = the ordinal
  convention (13 ordinals over 14 registered families / 11 IA result tables; PA-2's proxy family
  deliberately carries no ordinal). *Recommend APPROVE — recording the census prevents a future
  auditor reading the registrars from calling the headline false.*
