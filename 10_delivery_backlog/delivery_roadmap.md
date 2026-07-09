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
| 4 | **P2-7 — benchmark price/level capture** | The captured-input slice (`benchmark_level`/`benchmark_return`, a NET-NEW canonical ENT id) that unblocks every return-based benchmark-relative analytic. Follows the P2 captured-data pattern (FR/bitemporal; no run/model/snapshot binding). | M | none |
| 5 | **P3-7 — benchmark-relative analytics** | Tracking error / active risk over the P2-7 data + the existing engine — the P3 plan's final analytic leg. | M/L | slice 4 |
| 6 | **P3-6 — stress/scenario** | ENT-029/030 (scenario definitions + results). Sequenced LAST in the wave deliberately: our own P3-0 record flags it as RTM-P5-phase (possibly later); doing it after benchmark-relative completes the P3 analytics story without pulling it ahead of cheaper wins. If the Wave-1 close review argues for deferring it into Wave 2, that is an expected outcome, not a failure. | L | none (independent) |

**Wave-1 close = a phase-close review + re-baseline** (the P2→P3 readiness-review pattern): honest state audit,
deferral-register reconciliation, and the Wave-2 proposal briefed plain-language for ratification.

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
