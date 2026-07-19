# Desmoothing estimator conventions v1 (`perf.return.desmoothed_geltner`) — DS-2

The Geltner desmoothing family gains DECLARED **estimator conventions**: the platform now
ESTIMATES the smoothing it corrects (the 1991→2003 fidelity step), each convention a new declared
version of the existing family — never a silent replacement. The declared-α v1 is grandfathered
(an absent `estimator_convention` means `DECLARED`, exactly the shipped identity).

## The three conventions

| Convention | What it does | Declared identity |
|---|---|---|
| `DECLARED` (grandfathered v1) | the Geltner inversion at a declared α | `alpha` (absent convention ⇒ this) |
| `AR1_ESTIMATED` (OD-DS-2-A) | α̂ = 1 − ρ̂₁ computed in-run + the band | `estimator_convention`, `min_periods`, `band_convention` |
| `OKUNEV_WHITE_ITERATIVE` (OD-DS-2-B) | the deterministic higher-order filter | `estimator_convention`, `ow_max_order` |

## AR1_ESTIMATED, pinned

ρ̂₁ = the lag-1 sample autocorrelation of the observed return series under the **T-denominator
(Box-Jenkins) convention** (mean-centered; |ρ̂₁| ≤ 1 by Cauchy-Schwarz); **α̂ = 1 − ρ̂₁**,
quantized once to the column scale and echoed in the `alpha` column (the echo = what the run
used). Fail-closed, never a silent clamp: ρ̂₁ ≤ 0 (no positive smoothing signal) refuses
pre-create — the declared-α version remains available; a constant series refuses; a declared
`min_periods` floor (structural ≥ 6) gates the estimate. The same Geltner inversion then runs
with α̂ — deterministic closed form, no optimizer, fully reproducible from the pinned marks.

**The band:** `alpha_stderr` = SE(ρ̂₁) under the declared `BARTLETT_WHITE_NOISE` convention
≈ 1/√n (SE(α̂) equals it by the delta method), persisted on the summary row (migration `0042`;
DB-guarded summary-only). Two honesty facts, both registered (executed at planning): the band is
**CONSERVATIVE** — it OVERSTATES SE(ρ̂₁) under AR(1) at lag 1 (the narrower exact-AR1 band
√((1−φ²)/n) is a named v2); and ρ̂₁ carries a **small-sample DOWNWARD bias** ≈ −(1+4φ)/n
(Kendall 1954; Marriott-Pope 1954), so **α̂ is biased UPWARD on short appraisal series**
(executed MC: E[α̂] ≈ 0.58 at n = 15 when the true α is 0.40 — conditional on acceptance,
ρ̂₁ > 0; ~5% of such draws refuse) — disclosed, never corrected in-run; a bias-corrected
estimator is a named v2.

## OKUNEV_WHITE_ITERATIVE, pinned

ONE deterministic pass per order i = 1..m (m = the declared `ow_max_order`, 1..4), ascending:
pass i measures ρ_i and ρ_2i on the CURRENT series and applies the **lag-i** filter

    r*_t = (r_t − c_i·r_{t−i}) / (1 − c_i)

with c_i the '−' root of `ρ_i·c² − (1+ρ_2i)·c + ρ_i = 0` — the sole admissible |c| ≤ 1 root
for a strictly positive discriminant (Vieta reciprocal roots; at disc = 0 with ρ_i < 0 the
double root c = −1 arrives, admissible and harmless; settled by first-principles derivation AND
executed proof at planning — a lag-i filter zeroes the lag-i autocorrelation, a lag-1 filter with the same
coefficient does not). Fail-closed: a negative discriminant (PSD-reachable); **c_i ≥ 1** (not
equality-only — the ulp-above-one evasion); the structural length-vs-order floor
(n ≥ m(m+1)/2 + 2, each pass's length > 2i — else ρ̂_2i would be an empty-sum artifact).
ρ_i = 0 ⇒ the identity pass, deterministically; **ρ_i < 0 is admissible and deliberate**
(whitening is the objective, both signs — unlike AR1_ESTIMATED's ρ̂₁ ≤ 0 refusal, where α̂
would leave the Geltner domain). Each pass drops its first i values (cumulative m(m+1)/2); the
filtered rows carry **`alpha` NULL** (no single α exists) and the c_i coefficients are NOT
persisted — fully reproducible from the pinned marks + the declared identity. The Geltner single
pass is the m=1 special case **under exact AR(1) structure only** (ρ₂ = ρ₁²; on sample data OW
m=1 ≠ AR1_ESTIMATED — never asserted equivalent).

## Downstream

The conventions change ONLY how the desmoothed series (and its α echo) is produced. PA-3 — the
sole governed consumer — reads metric_type/period grain/`metric_value` only, so the new series
flow through the proxy-weight seam byte-unchanged. The pin serializer's `alpha` value is
None-tolerant (OW rows pin null; existing pins byte-identical); `alpha_stderr` is deliberately
NOT a pin key (the false-drift landmine).

## External benchmarks (roadmap Part 4 rule 6 — fetched 2026-07-18)

- **Geltner (1991/1993)** — VERIFIED-carried from PA-1 (the v1 filter; the α ≈ 1 − ρ₁ offline
  convention this slice brings in-run).
- **Getmansky-Lo-Makarov (2004)**, *JFE* 74(3):529–609 — **EXTRACTION-VERIFIED to equation
  numbers** (the ledger's never-extraction-verified flag discharged): the MA(k) smoothing model
  (Eqs. 21–23), the smoothing index ξ = Σθ² (Eq. 34), the demeaned-MA(k) MLE via the
  Brockwell-Davis innovations algorithm (Eqs. 47–55), the Prop-3 closed-form k=2 asymptotics
  (Eqs. 56–58). **Ships as the NAMED v2, not in-slice**: the estimator requires constrained
  numerical optimization — a determinism/TR-09 obstacle this runtime has not admitted; the
  verification is banked for the v2.
- **Okunev & White (2003)**, SSRN 460641 (publ. Loudon-Okunev-White, *JFI* 16(2):46–61, 2006) —
  the method identity VERIFIED at PA-1 (OD-PA-1-J); the per-pass formula **REPRODUCED
  vendor-normalized + SETTLED BY DERIVATION** (the primary is GATED; the reproduction's rendered
  lag conflicted with its own quadratic and was resolved by first-principles algebra + executed
  proof) — re-verify against the primary or a second independent source before any extension.
- **Bartlett (1946)** / Box-Jenkins — the white-noise SE convention; **Kendall (1954) /
  Marriott-Pope (1954)** — the small-sample autocorrelation bias the α̂ limitation registers.

## Known limitations (first-class; mirrored into `model_limitation` rows)

AR1_ESTIMATED: sampling error ~1/√n on appraisal-length series; the small-sample UPWARD bias of
α̂ (disclosed, uncorrected); the CONSERVATIVE band (an identification convention, not an exact
CI); single-lag structure still assumed. OKUNEV_WHITE: the fixed ascending pass sequence (a
later pass perturbs earlier orders; repeat-until-tolerance is a named v2); the vendor-normalized
transcription grade; series shortening m(m+1)/2. Both inherit the family's standing rows.

## Reproducibility & governance

Deterministic Decimal (prec-50; single terminal quantize; no optimizer anywhere in-slice). Both
conventions reproduce from the pinned `DESMOOTHING_INPUT` marks + the declared identity alone.
Snapshot/run/model-bound, IA append-only; migration `0042` (alpha nullable + `alpha_stderr` +
the summary-only CHECK) carries the 0028-pattern destructive RLS-safe downgrade, proven under a
non-superuser owner-via-membership role.
