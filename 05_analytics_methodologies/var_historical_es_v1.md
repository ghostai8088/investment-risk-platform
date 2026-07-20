# Historical-Simulation Expected Shortfall v1 (`risk.var.historical_es`) — ES-HS-1

The platform's 15th governed number and its FIRST empirical tail measure: the Acerbi-Tasche
discrete α-tail-mean over the SAME scenario P&L distribution the historical-simulation VaR
selects its order statistic from. Where the parametric ES is a registered multiplier over a
normality assumption (`k_c·σ` — it can never disagree with its VaR about the tail's shape),
this number averages the actual worst scenarios in the pinned window.

## Purpose & applicability

Empirical 1-day Expected Shortfall at a declared confidence over governed factor exposures ×
pinned captured factor-return windows — the `VAR_HS_INPUT` substrate, byte-identical to the
sibling `risk.var.historical` family's (one snapshot can feed both; a VaR-HS run and an ES-HS
run bound to the SAME `input_snapshot_id` form the coherent (VaR, ES) pair over one scenario
set). `metric_type='ES_HISTORICAL'` on the shared `var_result` grain; `var_value` holds the ES
(the generic-by-metric_type precedent); `z_score`/`sigma`/`covariance_run_id` honestly NULL
(migration `0041` widened the 0028 metric-conditional CHECK for exactly this shape — the
migration ES-1 recorded this leg would need).

## The estimator, pinned

With the window's scenario P&Ls sorted ascending (`pnl_(1)` the worst), `a = 1−c`,
`m = ⌊n·a⌋`, `w = n·a − m` (ALL exact Decimal — no float touches the selection):

    ES_c = −( Σ_{i≤m} pnl_(i) + w · pnl_(m+1) ) / (n·a)

— **Acerbi-Tasche Prop. 4.1**: the floor count plus the FRACTIONAL boundary weight, the exact
discrete α-tail-mean integral. **NEVER the mean of the worst ⌈n·a⌉ losses** — that quantity is
the TCE the ES-1 convention forbids (not coherent for discontinuous distributions) and it
WEAKLY understates ES — never exceeding it, strictly below at every fractional n·a with an
untied (m+1)-boundary, equal exactly at fully-tied tails (order 10%, up to ~14% depending on the tail shape, at
n=41 — the platform's own adequacy floor at c=0.975; the divergence direction is uniform, the
magnitude fixture-dependent). The estimator convention is REGISTRATION-DECLARED
(`estimator_convention='TAIL_MEAN_ACERBI_TASCHE_P41'`): an interpolated, simple-average, or
kernel-smoothed estimator is a NEW declared version, never silent drift. There is NO registered
constant in this family (no `es_multiplier`, no z) — and therefore a reproducibility gain over
the parametric ES: **the number is FULLY reproducible from the pinned snapshot content plus the
declared parameters alone**. `ES ≥ VaR` holds at raw precision on the same window by
construction (equality at tied tail scenarios); both may be negative when the whole tail is
gains — reported honestly, never clamped. Computed at Decimal prec-50 with ONE HALF_UP quantize
to 6dp.

## Declared identity

`confidence_level` (the shared v1 vocabulary {0.9500, 0.9750, 0.9900} — vocabulary membership
only, NO z arithmetic), `horizon_days=1`, `window_observations` under the SAME strict adequacy
floor as the VaR leg (`n·(1−c) > 1`, enforced at registration AND bind — it also keeps `m ≥ 1`,
so the fractional-weight estimator never degenerates to a single-scenario shape), and the
estimator convention above. Identity = (code_version, confidence, horizon, window, estimator
convention); same-label different-declaration is a governed 409.

## Shape

The SAME binder (`run_var_historical` — a registry-map family dispatch, the ES-1
`_VAR_FAMILIES` precedent), the SAME run endpoint, the SAME reads (metric_type-generic), ZERO
frontend changes. ONE new registrar endpoint (`POST /risk/models/var-historical-es`).
`risk.run`/`risk.view` REUSED — no permission mint; another ENT-027 realization — no new
entity; `audit/service.py` FROZEN.

## No backtest leg (v1) — the recorded tee

`ES_HISTORICAL` is DELIBERATELY absent from the backtestable vocabulary: the Kupiec/Basel
exception count is a QUANTILE test — statistically meaningless over a tail-mean series — and
the backtest binder refuses this metric with the recorded scope-out (never an
unknown-vocabulary miss). **The genuine Acerbi-Szekely ES backtest is the named BT-3
candidate** (with TIPPED Christoffersen, finally homed), carrying the pairing design input this
slice settled: pair the ES-HS run with its sibling VaR-HS run by shared `input_snapshot_id` —
the (VaR_t, ES_t) forecast pair AS 2014's Test 2 requires exists with zero schema change.

## External benchmark (roadmap Part 4 rule 6 — sources checked 2026-07-17)

- **Acerbi & Szekely 2014** ("Back-testing Expected Shortfall", Risk 27(11) 76–81; the MSCI
  Research Insight) — **verified-via-reproduction at per-source grades; the primary is GATED**
  (risk.net paywall; MSCI form-gate), disclosed rather than laundered:
  - the **Test-2 (Z2) statistic verified via ONE verbatim reproduction** —
    [Moldenhauer & Pitera, arXiv:1709.01337](https://arxiv.org/pdf/1709.01337) p.15 Eq. (6.2),
    quoting AS Eq. (6): `Z2 = ((1/T)·Σ X_t·1{X_t+VaR_t<0}/(α·ES_t)) + 1`, the `+1` OUTSIDE the
    sum — independently confirmed by the null-expectation identity (`E[X_t·I_t] = −α·ES_t`
    under a correct model ⇒ `E[Z2] = 0`); M-P also carry the AS traffic-light thresholds
    (−0.70/−1.8 in AS's convention) and the fork-deciding data requirement verbatim ("Test 2
    framework require IM methodology for both VaR and ES methodologies").
    **Sign-convention disclosure**: M-P p.15's PROSE describes Z in their flipped convention
    while the DISPLAYED equation is in AS's — the transcription follows the equation, with the
    direction derived from the formula + identity, not the prose.
  - [Kratz, Lok & McNeil, arXiv:1611.04851](https://arxiv.org/pdf/1611.04851) grounds ONLY the
    significance procedure ("Monte Carlo hypothesis tests") and the elicitability posture — it
    reproduces no formula.
  - **Test 1 (Z1)'s structure verified, its exact transcription VENDOR-NORMALIZED** (MathWorks
    Risk Toolbox docs; the fetched render mis-attached the `+1` and was identity-corrected) —
    **re-verify against the primary or a second independent source before BT-3 registers
    anything Z1-shaped; the −0.70/−1.8 threshold VALUES likewise rest on M-P's attribution
    alone and must meet the three-route constant bar before registration.**
- **Acerbi & Tasche 2002** (Prop. 4.1, the discrete α-tail-mean) — VERIFIED-carried from ES-1;
  the estimator this family declares.
- **Fissler & Ziegel 2016** (joint (VaR, ES) elicitability) — via
  [Nolde & Ziegel, arXiv:1608.05498](https://arxiv.org/pdf/1608.05498) p.4; the elicitability
  objection to ES backtesting conflates model selection with model testing (the AS point,
  already recorded at ES-1).
- **BCBS d457/FRTB** — VERIFIED-carried (ES-1/BT-2): MAR33's 97.5% ES is the capital measure
  while backtesting remains VaR-based — the regulatory footing for the BT-3 tee. This platform
  makes NO capital-model claim.

## Known limitations (first-class; mirrored into `model_limitation` rows)

- **Specific/idiosyncratic risk = 0** — x spans registered factors only, whichever exposure
  family produced it (family-neutral, the post-HG-1 framing).
- **Tail mass at the floor** — at 21/0.95 the effective tail mass is n·a = 1.05
  scenario-equivalents: ≈95% of the estimate's WEIGHT sits on the single worst scenario (a
  weight claim — at tied tails the ES equals the worst scenario exactly). The floor is a
  statistical MINIMUM; window size is the lever that buys tail resolution.
- **Window-bounded with sharper teeth** — the ES cannot exceed the worst scenario IN the
  pinned window, and the statistic lives ENTIRELY in the window's extreme tail: regime changes
  outside the window are invisible more consequentially than for the VaR leg.
- **Equal-weight inheritance** — the scenario substrate reacts slowly to volatility shifts;
  FHS/BRW variants are recorded v2 versions of the SIBLING VaR family and would flow through
  the shared substrate, each a new declared version here too.
- **Deliberately not backtestable v1** — the BT-3 tee above.
- **validation_status** — the standing VW-1/MG-1 enforcement posture.

## Reproducibility & governance

The row reproduces from its pinned snapshot + declared parameters alone (no registered
constant participates); TR-09 re-run invariance holds through the pinned content. The 0041
downgrade DELETES `ES_HISTORICAL` rows (unrepresentable under the 0028-form CHECK — the
recorded destructive-downgrade precedent, extended by ratification), with the append-only
trigger and FORCE RLS transactionally disabled around the delete; the RLS-safe path is proven
under a NON-superuser owner-member role in the PG suite (closing the recorded
superuser-only-smoke gap for this delete).

**Dated amendment (BT-3, 2026-07-19):** the "no backtest leg" section above and its
re-verification debt are DISCHARGED — the Acerbi-Szekely ES backtest SHIPPED at
`risk.es_backtest` (BT-3; see `es_backtest_v1.md`): the Z1 transcription re-verified via an
independent academic reproduction + the settling null-expectation identity (the vendor
render's '+1' corruption reproduced and disclosed a second time); the −0.70/−1.8 threshold
VALUES registered at the three-route bar (M-P attribution + Lund Table 1 + an executed seeded
MC at exactly (a=0.025, T=250)) — and SHARPENED: the criticals are α-, T-, and df-dependent,
so the verdict is DOMAIN-GATED to (0.9750, 250) with off-domain runs persisting evidence rows
and no verdict. The tee's limitation row is reworded for NEW registrations (the key substring
preserved); this version's own registered rows are immutable history.
