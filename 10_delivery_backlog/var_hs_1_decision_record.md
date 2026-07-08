# VAR-HS-1 Decision Record — Historical-Simulation VaR (Wave-1 slice 2)

| Field | Value |
|---|---|
| Status | **IMPLEMENTED and CLOSED** — plan `ec1f582` (CI #116 green); implementation `29ae31b` (CI **#117** green); OQ-VAR-HS-1-1…7 ratified 2026-07-08; the Tier-2 implementation commit was separately user-approved after the Part 5 review (30 filings, 16 folds incl. two ratification amendments — see Part 5) |
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

---

## Part 5 — Implementation adversarial review log (2026-07-08, independent-context, 6-finder)

Six finders (numeric / governance-tenancy / line-scan / cross-file / test-quality / conformance)
over the full working-tree diff; every candidate verified empirically. **30 filings → ~16 deduped
folds; 0 unresolved.** The cross-file tracer verified every pin-content key, builder guard, and
endpoint raise-path CLEAN; governance verified the enforcement invariants (provenance
re-resolution, both purpose fences, both-direction model identity, the 5th registrar's status
contract, zero new permissions/audit codes) present and correct in code.

**Ratification amendments (folded tightenings of the user-approved ODs):**
- **OD-VHS-E AMENDED:** the ratified floor `N ≥ ⌈1/(1−c)⌉` still yielded k=1 (the sample
  minimum — the floor's own stated refusal) at every integral boundary, incl. BOTH v1
  confidences. Tightened to guarantee **k ≥ 2**: `N·(1−c) > 1` strictly (21 @ 0.95; 101 @ 0.99),
  enforced at the registrar AND re-checked in `declared_hs_var_parameters` (the generic
  `POST /models` mint bypassed the floor entirely; window=0 additionally reached an
  IndexError 500 — three finders independently).
- **OD-VHS-C AMENDED (×2):** (1) `covariance_run_id` is ALSO nullable in 0028 — the method
  consumes no covariance run and a stuffed placeholder would be dishonest provenance; (2) the
  relaxation is METRIC-CONDITIONAL at the DB (`ck_var_result_parametric_not_null` CHECK) so a
  parametric row can never lose its declared parameters to a binder bug; and 0028's DOWNGRADE is
  DESTRUCTIVE (deletes VAR_HISTORICAL rows — unrepresentable pre-0028; the 0026 drop-table
  precedent) with the append-only trigger AND FORCE RLS disabled transactionally around the
  delete (the RLS policy binds even the table owner: under any non-superuser migrator the delete
  silently matched zero rows and bricked the downgrade midway — three finders independently; CI's
  green smoke had only ever proven the container-superuser path).
- **OD-VHS-F recorded picks:** a NEW `var_hs_service.py` binder (the plan's smaller-diff clause);
  the SIBLING purpose `PURPOSE_VAR_HS_INPUT` (now also a `SNAPSHOT_PURPOSES` member — it had been
  left out of the controlled vocabulary, three finders); **2 new POSTs + GET reuse** instead of
  "4 endpoints" (the reads are the parametric family's — same run family/table; verified
  functionally complete incl. the FE-1 listing and null-rendering with ZERO frontend changes).

**Code folds (numeric finder, all empirically verified):** the kernel's sort/negate/quantize
moved INSIDE the prec-50 context (at prec 28 a ≥1E22 result raised InvalidOperation — a raw 500
— and unary minus HALF_EVEN-rounded >28-digit P&Ls BEFORE the declared HALF_UP quantize); the
binder's per-factor totaling now runs at prec 50 (cross-method parity on duplicate-factor pins)
with a NEW per-factor-TOTAL envelope gate (m duplicates could reach m×1E22 with every pin
column-legal); the magnitude gate is now REACHABLE (was dead code) and test-proven to commit a
FAILED run with a persisted reason on BOTH engines.

**Registry/doc honesty folds:** the parametric `VAR_LIMITATIONS` no longer tells future
registrants that historical simulation "is a roadmap method" (it ships in this slice; existing
rows are registration-time snapshots, untouched); `VAR_HS_LIMITATIONS` gains the
backtesting/Monte-Carlo seam line; the `risk/__init__` docstring no longer denies the method the
module exports.

**Test folds (test-quality finder — incl. one probe-verified mutation survival):** a hand-minted
VAR_HS_INPUT snapshot vehicle now drives 16 adjudication-gate probes; the foreign/unknown pinned
run id refusal is tested (deleting the provenance re-resolution had survived all 17 tests —
the P3-5 principal-finding class, now defended); FAILED-run proofs on SQLite + PG + the reason
persistence; pin invariance is non-vacuous (the fresh build moves to 190 while the pin holds
200); reverse model identity + both purpose cross-feeds; six generic-mint malformed-declaration
refusals + the non-REGISTERED twin; typed `VarSnapshotError` asserts; all floor-shifted
references updated (N=21 ⇒ k=2 ⇒ VaR=200 — the hand constant survives).

Post-fold validation: `make check` 937 passed; full-PG **1142 passed** (clean reset run);
`alembic check` a no-op; the 0028 cycle proven twice in BOTH directions with real exit codes
over suite-created rows; frontend untouched (37 vitest green); the diff fence = the slice's
files only.
