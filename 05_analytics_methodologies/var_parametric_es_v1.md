# Methodology — Parametric Expected Shortfall (`ES_c = k_c · σ`, 1-day) v1

> **Models:** `risk.var.parametric_es` (plain σ) and `risk.var.parametric_es_total` (PA-4's σ_total) · **Version:** `v1` (both) · **Referent:** both families' `model_version.methodology_ref` points here.
> **Status:** REGISTERED; `validation_status = UNVALIDATED` (recorded, **non-enforcing until a 2L validator records an outcome** — VW-1; a REJECTED latest outcome then refuses every new bind at the shared `assert_model_version_of` seam). This doc IS the methodology referent the governed `model_version` binds.
>
> **Two families, ONE referent, because the arithmetic is one multiplier.** They differ only in *which* governed σ they
> multiply — the plain factor σ_p (P3-5) or the factor+idiosyncratic σ_total (PA-4, carrying BT-2's staleness gate).
> Every input, adjudication, snapshot-binding and provenance rule of the underlying VaR family applies **verbatim**: a
> σ-multiple is exactly as honest as its σ, and no more.

## Purpose & applicability

The platform's **14th governed number**, and the first that answers the question VaR structurally
refuses. VaR is a **cut-off**: `VaR_99 = 1,163` says losses exceed 1,163 on 1% of days and says
**nothing whatsoever** about how bad those days are — a book losing 1,200 and a book losing
120,000,000 in the tail report the identical VaR. Expected Shortfall is the **mean of that tail**:

```
ES_c = k_c · σ_p ,   k_c := φ(Φ⁻¹(c)) / (1 − c)
```

Applicable wherever its underlying VaR family is applicable, at the same 1-day horizon over the
same governed factor evidence. `ES_PARAMETRIC` was **reserved by value since P3-5**; ES-1 realizes
it. **NO migration was required** — `var_result`'s `(calculation_run_id, metric_type)` grain
already permitted the value and every column already existed.

## The convention, pinned (OD-ES-1-A)

The seam P3-5 recorded — `ES = σ·φ(z)/(1−α)` — is **correct but under-specified**: it never
defines `α`, and the literature is genuinely split on that exact symbol (Acerbi–Tasche use the
**tail** probability; Gneiting uses the **confidence** level). This referent pins it and the
implementation does not rely on the symbol:

| Symbol | Meaning here |
|---|---|
| `c` | the **CONFIDENCE** level — `0.9750` ⇒ tail mass `0.0250` |
| `k_c` | `φ(Φ⁻¹(c)) / (1 − c)` — the registered ES multiplier |
| losses | **loss-positive** |
| `μ_L` | **0** (zero-mean), consistent with the shipped `VaR_c = z_c · σ_p` |

This is **Landsman & Valdez (2003)**'s elliptical tail-conditional-expectation closed form at
`μ = 0`.

**Definitional guard for later legs.** ES is the **α-tail-mean integral**, *never* `E[L | L > VaR]`
— the latter is TCE, which is **not coherent for discontinuous distributions** (Acerbi–Tasche
Example 5.4). The two coincide for continuous distributions (Cor. 5.3(i)), so under normality the
distinction costs nothing today. It is recorded because it will not be free later: an
**ES-over-historical-simulation** leg is discrete and must inherit the tail-mean estimator (the
mean of the worst `⌈n(1−c)⌉` losses), not the naive conditional average.

## `k_c` is a REGISTERED constant, not a runtime function (OD-ES-1-B)

`k_c` is the exact structural twin of the registered `z_c`: a per-confidence declared constant at
12dp, part of the version's declared-parameter identity and **identity-checked at bind** against
the registered table for the version's *own* declared confidence — a generically-minted version
cannot pair `c = 0.99` with the `0.95` multiplier and emit a governed number that is neither.

**No runtime normal function of any kind exists**: not the inverse CDF (barred since P3-5 —
*capability is not evidence*) and not the forward PDF φ. Computing `φ(z) = exp(−z²/2)/√(2π)` at
runtime is *feasible* (`Decimal.exp()` is spec-guaranteed correctly rounded), but `decimal` ships
no π, so it would require declaring a π constant anyway — buying nothing, since the vocabulary is
enumerated either way. **The tail arithmetic lives under model governance, not in code.**

| `c` | `z_c` (VaR) | `k_c` (ES) | `k_c / z_c` |
|---|---|---|---|
| 0.9500 | 1.644853626951 | **2.062712807507** | 1.254040 |
| 0.9750 | 1.959963984540 | **2.337802792201** | 1.192778 |
| 0.9900 | 2.326347874041 | **2.665214220346** | 1.145665 |

**How these digits were verified** (they are the deliverable — a wrong digit is wrong forever):
three independent routes agree to the last place — `Decimal` bisection on Φ at prec 50–80 with π
via Machin; stdlib `NormalDist.inv_cdf` (Wichura AS241, a *different* algorithm); and
composite-Simpson integration of the tail mean using **no closed form** (which independently
confirms `k_c` *is* the tail mean rather than merely asserting it). All are **correctly ROUNDED,
not truncated** — load-bearing at `c = 0.99`, where `k = 2.665214220345804…` rounds *up* to
`…346`. The battery pins all 12 digits **byte-exactly**, deriving `z` in-test by bisection: a
tolerance check fed the pre-rounded registered `z` cannot pin the 12th dp, because the injected
error `dk = −z·φ(z)·δz/(1−c)` puts the noise floor *above* the quantum being guarded.

`ES > VaR` at every confidence — structurally, via the Mills-ratio inequality `φ(z)/(1−Φ(z)) > z`,
so it holds for any confidence ever added (with equality only at `σ_p = 0`, where both are 0).

## Why ES, honestly (OD-ES-1-F, and the two corrections that survived review)

> ⚠️ **The tempting sentence — "we add ES because VaR is incoherent" — is WRONG as applied to this
> platform's own VaR, and must not appear in any document that binds this model.**

**Embrechts, McNeil & Straumann (2002)**, verbatim: *"In the elliptical world the use of VaR as a
measure of the risk of a portfolio Z makes sense because **VaR is a coherent risk measure in this
world**."* This platform's parametric VaR is delta-normal; normal ⊂ elliptical; PA-4's diagonal
residual keeps it normal. **Under the platform's own modelling assumption its VaR is already
subadditive** (`σ_p = √(x'Σx)` is a norm). The honest four-part rationale:

1. **Tail severity** — VaR is a cut-off and says nothing beyond it. Model-independent, and the
   only rationale BCBS themselves state.
2. **The HS-VaR leg is genuinely non-elliptical** — an empirical distribution is discrete, and
   there VaR's subadditivity really can fail, so a coherent ES has real content.
3. **Coherence as robustness insurance** — ES's coherence is **unconditional** (Acerbi–Tasche
   Prop. 3.1, any distribution with `E[X⁻] < ∞`); the parametric VaR's is **contingent on
   normality being true**. ES keeps the aggregation guarantee exactly when the model is *wrong*.
4. **Regulatory alignment** — 97.5% is FRTB's prescribed ES level (MAR33.3).

*(Sharp detail: Artzner's Remark under the monotonicity axiom rules out `ρ(X) = −E[X] + α·σ(X)` as
a functional on arbitrary variables — the σ-multiple form's coherence lives ONLY inside the
elliptical family. That is the cleanest statement of why this slice is about robustness, not about
fixing a defect in today's arithmetic.)*

> ⚠️ **Do NOT attribute a coherence rationale to BCBS.** Greps of **d457**, **bcbs265** and
> **d219** return **zero** occurrences of "coherent" / "sub-additive" / "subadditivity" /
> "elicitable". BCBS's stated rationale is **tail capture only** (d219: *"a number of weaknesses
> have been identified with VaR, including its inability to capture 'tail risk'"*). The coherence
> argument is **academic** (Artzner; Acerbi–Tasche) — cite each to its actual source.

**On the 97.5% ≈ 99% folklore.** bcbs265 §1.4(i) asserts 97.5% ES gives *"a broadly similar level
of risk capture as the existing 99th percentile VaR threshold"* — **without arithmetic and without
the normality qualifier**. Our own verified numbers: `k_0.975 / z_0.99 = 1.004923991931` (+0.49%),
and `ES_c = VaR_99` exactly at `c = 0.974232`. **The near-equivalence is a ~0.5% arithmetic
accident of the Gaussian and holds ONLY under normality** — under fat tails ES_97.5 exceeds
VaR_99 by more, which is precisely the more complete capture BCBS is buying.

## No ES backtest leg — and the reason is NOT "ES isn't backtestable"

ES rows are **deliberately excluded** from the backtestable metric vocabulary; a backtest over an
ES run refuses, and the refusal says so rather than calling the metric "unknown".

> ⚠️ **"ES cannot be backtested" is FALSE and must not be used to justify this.** Acerbi–Szekely
> (2014) give practical ES backtests; Fissler–Ziegel (2016) show ES is **jointly elicitable with
> VaR** (elicitable of order 2). Gneiting (2011)'s non-elicitability result is real but does not
> support the claim.

The honest justification is **(i) FRTB's own precedent** — MAR32.4/32.5 backtest a 99th-percentile
VaR and MAR32.18 backtests desk VaR at 97.5th *and* 99th; the ES number is used for **capital** and
is **never itself backtested anywhere in the standard** — and **(ii) parametric redundancy**: under
this leg's own normality ES is a fixed multiple of the σ the VaR leg already backtests, so an ES
backtest here is the VaR backtest with a rescaled threshold, adding no information. A genuine ES
backtest becomes meaningful when a non-elliptical **ES-over-HS** leg exists (a BT-3 candidate).

## Shape: a new model code through the same binder (OD-ES-1-C/D)

Each ES family is its own registered model code dispatched through the **same** `run_var` binder
(the PA-4 shape), emitting **ONE** `var_result` row with `metric_type = 'ES_PARAMETRIC'`. This
honours P3-5's ratified words (*"each method is its own registered model family/version"*).

**The alternative — an extra ES row on the existing VaR run — is DISQUALIFIED, not merely
dispreferred.** The snapshot builder pins **every** `var_result` row of a run with no metric_type
filter, and the backtest binder then refuses a snapshot whose pinned rows mix methods (and,
independently, refuses duplicate as-ofs, which two rows of one run necessarily share). Every
BT-1/BT-2 backtest over a post-ES parametric run would break, and a shipped v1 model would
silently start emitting two rows. Its true cost is re-opening BT-1/BT-2, not "appending a row".

## Known limitations

**Everything the underlying VaR family carries, verbatim** (the ES row *is* `k_c · σ_p`): zero
specific risk on the plain leg (the total leg adds it), joint normality, 1-day horizon only (no
`√h` scaling), CURRENCY-family factors only, sample-covariance estimation error. The total leg
additionally carries PA-4's diagonal-residual limitations and **BT-2's smoothing doctrine
unchanged** — on an appraisal-marked book the 1-day total σ is biased two ways by construction, and
the total ES inherits that bias directly.

**ES's coherence here is inherited-by-assumption, not demonstrated.** Under normality both VaR and
ES are coherent; the ES leg's practical content is tail severity + robustness-if-normality-fails.
Recorded so no reader over-claims.

**An ES row does not reconcile against its own columns.** `var_value = k_c · σ`, but `k_c` is on no
column — the row carries the arithmetically-**unused** quantile `z_score` instead, because the live
`ck_var_result_parametric_not_null` CHECK forces it non-NULL for every non-`VAR_HISTORICAL` row.
The multiplier lives only in the bound `model_version`'s declared `es_multiplier`, and the snapshot
serializer pins no multiplier key. **An ES row is reproducible THROUGH its model_version, never
from the row alone.** Read `var_value` as *the metric's number* and key off `metric_type` (the
shipped `VAR_HISTORICAL` precedent) — for an ES row that number is an ES, not a VaR. This is the
recorded cost of needing no migration, accepted with eyes open.

**Out of scope, each a separately declared later family/version:** ES over historical simulation
and Monte Carlo (each must inherit the tail-mean estimator above — and note an `ES_HISTORICAL` row
would **violate** the CHECK named above, so that leg *will* need a migration this one did not);
multi-horizon `√h`; a runtime quantile function; residual shrinkage/EWMA and calendar-aware
per-period trading-day counts on the total leg. ONE confidence level per registered version (the
declared-parameter identity). **This `v1` referent is immutable**; a future version carries forward
the cross-family limitations per the 2026-07-06 retrospective-audit rule.
