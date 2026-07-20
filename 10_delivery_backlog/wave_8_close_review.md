# Wave-8 Close Review — "fund the third leg" (private capital + the projection)

**Status: RATIFIED by the user 2026-07-20 ("Approve all" — OQ-W8C-1…6 all approved: the close
verdict; the register dispositions; Wave 9 = API-1 → FE-2 → SSO-1 → FE-3 with the 5-code
demo-completeness rider on API-1; FE-3's IA deferred to FE-3 planning as a Tier-3 USER decision).**
The mandatory rolling-wave close (roadmap Part 4
rule 2) after Wave 8 shipped its ratified sequence **BT-3 → CC-1 → CC-2**. Method: three
cross-cutting close auditors over the wave diff (`cc251b2..06b40b1`) — a cross-slice integration
sweep, a doc/register-coherence pass, and a completeness-critic + Wave-9-readiness assessment — on
top of each slice's own shipped 4-finder review. Opus-only (the Fable weekly allocation was scarce;
recorded, not the 71-agent ultracode of the Wave-7 close — proportionate to a three-slice wave whose
slices were each already reviewed with zero surviving HIGH).

---

## Part 1 — Did Wave 8 ship what was ratified? — YES; the fourth consecutive zero-shipped-defect close

The Part-2.11 ratified sequence (OQ-W7C-6 fork A) delivered in order, each with its own decision
record + plan + pre-ratification verifier pass + 4-finder review + closure stamps:

- **BT-3** (slice 1) — `risk.es_backtest`, the **16th governed number** (planning PR #68; impl PR #69
  = `109d11d`, CI #399; migration `0043`). The Acerbi-Szekely Z1/Z2 with the verdict DOMAIN-GATED to
  (0.9750, 250); Christoffersen shipped in-slice as `risk.var_backtest` v2. The ratified fetch MUSTs
  discharged (the '+1' grouping settled by the null-expectation identity; the −0.70/−1.8 thresholds
  at the three-route bar).
- **CC-1** (slice 2) — captured commitments/calls/distributions, **ENT-015/016** (planning PR #71 +
  the rule-7 amendment PR #73; impl PR #74 = `1cdc95b`, CI #420; migration `0044`). Capture-only
  (counts held 16/19/34/95); the `commitment.edit`/`.record`/`.view` three-code mint; EVT-240
  activated; rule 7 applied from birth.
- **CC-2** (slice 3, the headline) — `pacing.commitment_projection`, the **17th governed number**,
  **ENT-059** (planning PR #76; impl PR #77 = `1eaa703`, **CI #432**; migration `0045`). The
  deterministic Takahashi-Alexander pacing recursion — **the TA fetch MUST discharged via
  reproduction** (primary gated; the ES-HS-1/AS-2014 precedent), so the declared-parameter fallback
  rider did NOT fire. The five declared parameters are the version identity; NO constant minted. The
  `pacing.run`/`.view` mint (auditor in `.view`); EVT-250 reserved; **rule 7 all three legs + the
  platform's FIRST latest-resolver**. Demo stage 9 moved the counts to **20/35/96**.

**The close audit (three finders, wave diff `cc251b2..06b40b1`):**

- **Cross-slice integration — CLEAN (zero HIGH, zero MED).** All six composition seams verified: the
  linear migration chain `0043←0044←0045` with no cross-slice FK orphan (the CC-1 event tables carry
  provenance-only GUIDs, not FKs, so 0044's downgrade orphans nothing under 0045); the snapshot
  serializer purely additive (no existing content function gained a key — the 0038 landmine
  untripped); the demo count-flow structurally coherent (stage 9's idempotent-replay fixture makes
  it order-independent, not just order-correct); no EVT-decade collision (240 activated / 250
  reserved); the pacing↔private_capital AST fence holds (grep-verified, zero imports); both R-07
  parity tests present. **Wave 8 holds the three-wave zero-shipped-defect record — now four.**
- **Numeric/math (CC-2, the wave's only new number) — CONFIRMED correct** at ship: both hand-goldens
  re-derived to the last digit; the FAILED-gate cluster (the one real defect the review caught) was
  folded pre-merge.
- **No asserted-but-untested claims** across the three records; the honest residuals (REQ-PRV-001
  "aggregated" kept OPEN, the TA primary disclosed-as-reproduction) are disclosed, not gaps.

**At-close folds applied (doc/register hygiene, this review):** the SoD-table-breaking blank line
(`entitlement_sod_model.md`, which was orphaning the two Wave-8 rows from their header — the highest-
value fix); the stale canonical-id pointer (`ENT-059` minted → next free is ENT-060); three stale
"BT-3 candidate" forward-refs now that BT-3 shipped (the `var_parametric_es_v1.md` doc + two
`risk/events.py` comments); the `current_state.md` banner refreshed to the CC-2 truth with the prior
block explicitly demoted to history.

---

## Part 2 — The deferral register, reconciled

**Fixed at this close** (above): the SoD table break (CC-1 D-L5 — upgraded from "cosmetic" to
"breaks rendering of the rows under review"); the ENT-060 pointer (A1); the three fence-safe stale
refs (part of BT-3 D-F4); the current_state refresh (A2).

**Carried, with disposition:**

- **BT-3 D-F4 residual (the registered-limitation reword)** — the `VAR_BACKTEST_LIMITATIONS` strings
  still say Christoffersen is "a named BT-3 candidate" (it SHIPPED as v2) and the appraisal-frequency
  pairing is a candidate (still v2). **DEFERRED to a dedicated ES/var-backtest next-touch**, NOT a
  close-fold: the finding-key fence was pre-verified safe (no dossier `finding_key` matches these
  rows), but the reword is a genuine content split (Christoffersen-shipped vs appraisal-pairing-v2)
  on registered strings that feed the demo — a dedicated touch with the finding-key stage tests
  re-run, not a hygiene sweep. The already-filed immutable rows are preserved either way.
- **CC-1 A-9** (the demo seeds via service-direct calls under a view-only 1L registrar) — **ACCEPT as
  the standing demo-seeding convention** (the endpoint path enforces the maker verbs, test-pinned;
  does NOT recur for CC-2, where the 1L legitimately holds `pacing.run`). Trigger to revisit: only if
  the demo is ever refactored to seed through the API.
- **Two integration LOW notes** (close register): the pacing↔private_capital fence is grep-verified
  but not AST-tested (a durability gap consistent with the existing risk/perf/snapshot leaf
  convention — a candidate hardening, not a defect); the `SNAPSHOT_PURPOSES` allow-list still omits
  `PROXY_WEIGHT_INPUT`/`RESIDUAL_SHRINKAGE_INPUT` (the pre-existing RS-1/PA-3 tuple-bypass asymmetry;
  CC-2 did the right thing adding PACING to the enforced list).
- **CC-2 v2 register** (methodology backlog, not UI-shaped): the pacing "aggregated" portfolio-unfunded
  rollup (the REQ-PRV-001 clause honestly kept OPEN); quarterly periodicity; multi-commitment
  aggregation; the Jeet (SSRN 4819761) stochastic enhancement; an HG-1-style mark-staleness age gate.
- **Standing**: BT-3's per-(α,T) critical table v2 (offline MC); MG-2 remediation-lifecycle trigger
  (erosion; earliest real overdue 2027-07-19); SC-2 the named pull-forward (expired unspent); OD-B
  expire-a-mapping.

---

## Part 3 — The demo-completeness gap (the largest unverified-in-practice surface)

**The OQ-W7C-5 rider is unpaid a second wave.** Mechanically confirmed: **5 of the 20 registered
codes have ZERO living-tenant demo runs** — `risk.sensitivity.analytic`, `risk.active_risk.parametric`,
`risk.scenario.factor_shock`, `perf.benchmark_relative`, and the census-masked `risk.factor_exposure.proxy`
(registered + tiered but never run in proxy mode). Wave 8 met its *own* demo obligation (BT-3 runs at
stage 7, pacing at stage 9) but that was purely additive — it touched none of the five.

This is now the **highest-value carry-in for a UI wave specifically**: API-1's new entity/time reads
and FE-3's screens will render **empty** for those five families unless a demo stage exercises them.
Paying it turns the read surface into a *demonstrable* one and finally discharges OQ-W7C-5 — which is
why Part 6 recommends it ride API-1 rather than continue as a standing deferral.

---

## Part 4 — Outward benchmark + destination check (rule 6b, wave scale)

**Frontier.** Wave 8 funded the private-capital third leg. Against the best-in-breed frontier: the
capture substrate (bitemporal commitments + truly-immutable cashflow events with negation
corrections) and a reproducible, snapshot-pinned pacing projection are a genuinely governed take on
what most platforms do in spreadsheets. The honest residual is scope, not correctness: v1 is
per-(portfolio, instrument) at ANNUAL periodicity, single deterministic path — the portfolio rollup
and the stochastic path are named v2s, disclosed not hidden. On backtesting, BT-3 closed the 15th
number's exemption from the platform's own outcomes analysis; the FRTB nuance stands (desk
backtesting is VaR-based, so the ES-backtest trails the academic frontier, not the Basel floor).

**Thesis (`01_product_strategy/differentiation_thesis.md`).** §2.1 (private assets carry honest risk)
is now matched by §2.3-relevant machinery — but the **read surface is the gate**: F1 (governed reads
are run-centric — 13 families still lack entity/time reads) and F2 (the governance story is the
least-readable part of the API) mean the differentiator is *built* but not yet *legible* to a screen
or an agent. CC-2 shipped the first latest-resolver as the template; the back-fill is Wave-9 work.

---

## Part 5 — Process findings

- The **pre-ratification verifier pass held its value a third wave**: CC-1's two structural HIGHs and
  CC-2's period-geometry HIGH were caught *before* implementation, not at review.
- The **4-finder-on-Opus review caught a genuine HIGH+MED cluster on CC-2** (the FAILED gate that
  would have 500'd in production) under budget constraint — evidence the review tier is worth keeping
  even when Fable is scarce.
- **A compounding kernel is a new hazard class**: unlike the bounded-statistic numbers, pacing can run
  NAV away past the Decimal context; the lesson (kernel runaway ceiling + an envelope strictly below
  the result-column capacity, since PG-only overflow is invisible at the SQLite tier) is recorded for
  the next compounding number.
- **The local `alembic downgrade base` smoke** hit a pre-existing 0002-permission-seed vs
  app-bootstrap-grant FK conflict — **disproven as a real defect by CI #432**, whose downgrade-smoke
  step passed *after* full nine-stage demo seeding. It is a local-container artifact; the closeout
  register note that called it a carry is corrected here.

---

## Part 6 — Open decisions (OQ-W8C-1…6) — the ratification gate

- **OQ-W8C-1 — Close verdict.** Ratify: Wave 8 shipped as ratified (BT-3 → CC-1 → CC-2); the close
  audit found **zero shipped-code defects** (fourth consecutive clean close); the at-close doc/hygiene
  folds (Part 1) are applied.
- **OQ-W8C-2 — Register dispositions.** Ratify Part 2: the BT-3 D-F4 registered-string reword DEFERRED
  to a dedicated ES/var-backtest touch (fence pre-verified); CC-1 A-9 ACCEPTED as convention; the v2
  and standing items carried.
- **OQ-W8C-3 — Wave 9 sequence.** Ratify **Wave 9 = API-1 → FE-2 → SSO-1 → FE-3** (the candidate
  recorded 2026-07-20, now weighed at close per rule 2). The close finds the ordering coherent and
  correctly dependency-sequenced (API-1 lowest-risk/read-only first; FE-2 codegen over the final read
  surface; SSO-1 the identity gate before FE-3 faces a non-developer). Two planning-gate caveats to
  carry: **(a)** API-1's size is M/L-vs-L on whether the metric time-series + cross-family summary are
  in-scope or fast-follow (firm at API-1 planning); **(b)** FE-2 must preserve the
  PreciseDecimal-as-string contract — verify FastAPI's OpenAPI serializes decimals as `string`, not
  `number`, before committing to codegen (else it reintroduces the F3 `Number()` corruption).
- **OQ-W8C-4 — The demo-completeness rider.** Ratify that the 5 zero-run codes (Part 3) ride **API-1**
  as a named rider (a demo stage exercising sensitivity / active-risk / scenario / benchmark-relative /
  proxy-exposure), finally paying OQ-W7C-5 — so the Wave-9 read surface renders non-empty. (Alternative:
  a standalone hygiene slice, or continue deferring — recommended: ride API-1.)
- **OQ-W8C-5 — FE-3 information architecture** is a **Tier-3 USER decision deferred to FE-3 planning**
  (not an engineering default). The recommended spine is the living tenant's own
  capture → numbers → backtest → validation → limitations walk, not a generic run browser. Flagged,
  not decided now.
- **OQ-W8C-6 — Closure discipline** carries unchanged: the per-slice closure-stamp checklist
  (grep-for-"pending"/"candidate"; the CI-run-id backfill), the pre-ratification verifier pass, and
  rule 7 (every governed number ships entity/time reads in-slice; shipped families back-filled by
  API-1) all stand into Wave 9.

---

## Part 7 — Citation hygiene (carried for whoever plans Wave 9)

Wave 9 is a read-surface + FE + identity wave — lighter on external-methodology citation than the
math waves. The one live citation debt is the **BT-3 D-F4 registered-string reword** (Part 2), which a
future ES/var-backtest touch owns. No new paywalled-source reproductions are pending. For FE-2, the
"citation" that matters is the **OpenAPI decimal-serialization contract** (verify-before-codegen, per
OQ-W8C-3b) — the one place a governed number has visibly failed to check out in the UI (the FL-1 ES
`z×σ` drift), and the reason FE-2 exists.
