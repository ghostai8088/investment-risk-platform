# ES backtesting v1 — the Acerbi-Szekely Z statistics (`risk.es_backtest`, BT-3)

The SIXTEENTH governed number: outcomes analysis for the EMPIRICAL Expected Shortfall
(`ES_HISTORICAL`, ES-HS-1) — the number that ended the 15th governed number's exemption from the
platform's own outcomes analysis. Registered model `risk.es_backtest` v1; results on ENT-055
(`var_backtest_result`) under new metric types; run family `ES_BACKTEST` reusing
`risk.run`/`risk.view`.

## The statistics, pinned

Over an aligned paired series {(X_t, VaR_t, ES_t)} — X_t = the flow-adjusted realized P&L of the
BT-1 DIETZ sub-period convention (negative on loss), forecasts POSITIVE, the sibling (VaR-HS,
ES-HS) runs at each as-of sharing ONE `input_snapshot_id` — with the STRICT exception indicator
I_t = 1{X_t + VaR_t < 0} (byte-identical to BT-1's):

    Z2 = (1/(T·a)) · Σ_t X_t·I_t/ES_t + 1     (unconditional; a = 1 − confidence)
    Z1 = (1/N_T)  · Σ_t X_t·I_t/ES_t + 1      (conditional; N_T = Σ I_t; UNDEFINED at N_T = 0 —
                                               no row is emitted, never 0)

Under H0, E[Z2] = 0 and E[Z1 | N_T > 0] = 0; negative ⇒ risk UNDERSTATEMENT; one-sided. The
'+1' sits OUTSIDE the sum — settled by the null-expectation identity (E[X | X < −VaR] = −ES),
and load-bearing: the inside-denominator corruption evaluates to −ES/(ES+1) ≈ −0.7004 at
N(0,1)/a=0.025 — numerically COINCIDING with the −0.70 critical — so the suite's exact-Fraction
identity regression is the mechanical defense, not decoration.

## The verdict and its DOMAIN (the read rule)

REJECT iff the STORED 6dp Z2 < the registered left-tail critical for the declared significance:

    Z2_CRITICAL = { 0.05: −0.70,  0.0001: −1.8 }

**These criticals are valid ONLY at (paired confidence 0.9750, n_pairs = 250, near-normal
tails)** — they are α-, T-, AND df-DEPENDENT (executed at planning: ≈ −1.56 at a=0.005/T=250;
≈ −3.68 at a=0.025/T=10; −0.82/−4.4 at Student-t3; and the demo's own T=3 series produced
Z2 = −127.09). The verdict is therefore emitted ONLY inside that domain (the Basel-zone
domain-gate precedent); off-domain runs persist the Z evidence rows + `ES_PAIR_COUNT` and NO
verdict — **the read rule: an absent verdict is a recorded fact, mechanically derivable from
the persisted `ES_PAIR_COUNT` row + the version's registrar-stamped domain
(`verdict_confidence=0.9750`, `verdict_pairs=250`), never a gap.** A per-(α, T) critical table
is a named v2 under a governed OFFLINE derivation record (the TR-09 determinism bar — no
simulation at runtime, ever). Z1 is EVIDENCE, never a verdict (its criticals are
distribution-unstable — the recorded AS weakness). One-sidedness is registered: the Z tests
cannot flag over-conservatism; the two-sided Kupiec POF remains the coverage complement.

## The Christoffersen leg (`risk.var_backtest` v2-christoffersen, OD-BT-3-E)

The Markov independence test on the VaR exception series (a VaR-family leg — it ships as a v2
CONVENTION of the existing Kupiec model, `independence=CHRISTOFFERSEN_MARKOV`; the shipped v1
parses byte-identically via the absent-convention grandfather; the parse is the COUNTING
tri-state — ambiguity refuses, never grandfathers). Adjacent-day 2×2 transition counts n_ij
(FROM i TO j); LR_IND = 2[ln L(first-order Markov MLE) − ln L(single violation probability)],
χ²(1) against the shipped df=1 criticals; LR_CC = LR_UC + LR_IND, χ²(2) against
{0.05: 5.991465, 0.01: 9.210340} (the exact closed form −2·ln(α)). The applied convention —
LR_UC over the full N pairs, LR_IND over the N−1 transitions — is stated, not hidden. A
DEGENERATE table (no transition leaving a state) emits NEITHER row. First-order scope is
registered (longer-lag dependence is invisible; Christoffersen-Pelletier 2004 duration is the
named variant). The living tenant's stage-7 series is the live lesson: at n=3 NEITHER component
alone rejects while the joint LR_CC does.

## External benchmarks and citation grades (roadmap Part 4 rule 6; per-source, honest)

- **Z2 — VERIFIED VIA THREE INDEPENDENT ROUTES**: Zeliade Systems whitepaper zwp-011 v2.0
  (2020-12-16) §3.2.1 VERBATIM (`Z2(e,v,x) = x·1{x+v<0}/(αe) + 1`, the null identity, strict
  monotonicity); Fredriksson & Johansson, Lund University thesis (lup.lub.lu.se 9024227),
  algebraically identical form; Moldenhauer-Pitera arXiv:1709.01337v3 p.15 Eq. 6.2 + the
  null-expectation identity (carried from ES-HS-1).
- **Z1 — the ES-HS-1 vendor-normalized flag DISCHARGED**: Lund (independent) + MathWorks
  `esbacktestbysim` docs (vendor — whose HTML render reproduces the '+1' corruption, disclosed)
  + the settling identity. **The AS primary's own equation renderings remain unsighted** (Risk
  magazine paywall + MSCI form-gate) — disclosed; two sources + the identity over-determine
  the formula.
- **The −0.70/−1.8 threshold VALUES — three routes**: the M-P flipped-sign attribution
  (carried); Lund Table 1 ("Acerbi and Szekely's (2014) left tail critical values": 5% → −0.70,
  0.01% → −1.8 at N(0,1)/t100; −0.82/−4.4 at t3); and the BT-3 planning pass's EXECUTED seeded
  MC (−0.7001 / −1.78 ± 0.03 at exactly (a=0.025, T=250)). Zeliade §3.2.2 corroborates the
  α-dependence MECHANISM (≈ −1.2 at α=0.5%), not the values.
- **Christoffersen 1998 — paragraph-grade via two public sources**: Campbell, "A Review of
  Backtesting and Backtesting Procedures", Fed FEDS 2005-21 (the 2×2 Markov structure,
  N1/(N1+N3) = N2/(N2+N4)); Lund. The LR_ind ALGEBRA is pinned from the Evers-Rohde Hannover
  discussion paper dp-529 (public) — **with two disclosed source wobbles**: its n_ij prose
  swaps the index order against its own transition-matrix convention, and its LR rendering
  inverts the likelihood ratio against its own definitions (yielding a negative statistic);
  the likelihood structure + MLE dominance fix both, and the review re-derives from the 2×2
  MLEs exact-rationally. The primary (IER 39(4):841–862) is JSTOR-gated — grade:
  verified-via-reproduction, never claimed as sighted.
- **Regulatory posture (carried from the Wave-7 close, web-verified there)**: FRTB keeps desk
  backtesting VaR-based while 97.5% ES is the capital measure — this test trails the ACADEMIC
  frontier (AS 2014; Kratz-Lok-McNeil), not a Basel floor; 0.9750 is the externally-anchored
  verdict confidence (MAR33.3).

## Known limitations

Mirrored content-identically into `model_limitation` rows — see `ES_BACKTEST_LIMITATIONS`
(`risk/bootstrap.py`): the domain-bound verdict; one-sidedness; Z1-evidence-only; the
captured-holdings P&L bias + ACTUAL-P&L-only carries (BT-1); one paired family per run with
per-leg model-version uniformity; small-T honesty; the FRTB posture; validation_status.
