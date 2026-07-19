# DS-2 Implementation Plan — estimated-α + Okunev-White desmoothing (Wave-7 slice 4)

Companion to `ds_2_decision_record.md`. Sized **M**. ONE migration (`0042` — alpha nullable +
`alpha_stderr`). Two new declared estimator conventions on `perf.return.desmoothed_geltner`; the
DECLARED path byte-preserved (grandfather); GLM MA(k) stays the named v2 (the determinism obstacle
recorded). PA-3 consumption unchanged (it reads `metric_value` only — census-verified).

## Step sequence

**1 — The estimation kernel pieces (OD-A/OD-B).** In `perf/desmoothing_kernel.py` (pure, prec-50,
single terminal quantize): `lag_autocorrelation(series, lag)` — the T-denominator Box-Jenkins
sample autocorrelation (mean-centered; the shared convention both conventions cite); refuses a
constant series (zero denominator). `estimate_ar1_alpha(observed)` — α̂ = 1 − ρ̂₁ with the
fail-closed domain (ρ̂₁ ≤ 0 / ρ̂₁ = 1 ⇒ a typed kernel error the binder maps to 422) + the
Bartlett stderr 1/√n. `desmooth_okunev_white(observed, max_order)` — one deterministic pass per
order i = 1..m: ρ_i/ρ_2i on the CURRENT series, the '−' quadratic root (verifier-proved the sole
admissible branch, both signs of ρ_i — Vieta reciprocal roots) with the post-selection assert
|c_i| ≤ 1 (discriminant < 0 / **c_i ≥ 1** ⇒ typed error — ≥, not equality-only: the ulp-above-1
evasion; ρ_i = 0 ⇒ the identity pass, count preserved; ρ_i < 0 admissible — whitening, no sign
flip since (1−c_i) > 1), the lag-i filter `(r_t − c_i·r_{t−i})/(1−c_i)` dropping the first i
values per pass; STRUCTURAL floors enforced before any pass: n_observed ≥ m(m+1)/2 + 2 and each
pass's current length > 2i (the empty-sum-ρ̂_2i guard). The EXISTING
`desmooth_geltner` is BYTE-UNTOUCHED (the estimated convention calls it with α̂; the OW transform
is its own function).

**2 — The gate + registrars (OD-C).** In `perf/bootstrap.py`: `ESTIMATOR_CONVENTION` literals
(`DECLARED` implicit / `AR1_ESTIMATED` / `OKUNEV_WHITE_ITERATIVE`), the `estimator_convention=` /
`min_periods=` / `band_convention=` / `ow_max_order=` prefixes, and `declared_desmoothing_parameters`
adapting RS-1's `declared_proxy_weight_parameters` VERBATIM in mechanics: zero convention rows ⇒
DECLARED grandfather (requires `alpha=`, exactly today's parse — byte-preserved); >1 rows ⇒
`WrongModelVersionError`; per-branch companion validation + stray-literal refusal (an `alpha=` on
an estimated/OW version is a lying identity). Two registrars:
`register_desmoothed_return_estimated_model` (stamps convention + `min_periods` ≥ 6 +
`band_convention=BARTLETT_WHITE_NOISE`; label `v2-ar1-estimated`) and
`register_desmoothed_return_okunev_white_model` (stamps convention + `ow_max_order` 1..4; label
`v2-okunev-white`); 409 on same-label-different-declaration; both re-parse via the gate for the
conflict check.

**3 — The binder dispatch (OD-C).** `perf/desmoothing_service.py`: `run_desmoothed_return` parses
the convention via the new gate and dispatches through a registry map — DECLARED: today's path
byte-identical; AR1_ESTIMATED: build the observed series from pins (unchanged), floor-check
`n_observed ≥ max(min_periods, structural)`, α̂ + stderr from the kernel (kernel error ⇒ 422
pre-create), then the SAME Geltner inversion + persistence with `alpha = α̂` (echo = used) and
`alpha_stderr` on the summary row; OKUNEV_WHITE_ITERATIVE: the length-vs-order
floor pre-create (n_observed ≥ m(m+1)/2 + 2; per-pass length > 2i — kernel-typed errors mapped
to 422), then the OW transform, rows with `alpha = NULL`, `alpha_stderr = NULL`, summary as v1.
The refusal battery + magnitude gates unchanged.

**4 — Migration `0042_desmoothing_estimated_alpha` (OD-D).** `alpha` → nullable; ADD
`alpha_stderr` Numeric(20,12) nullable; ADD the CHECK `ck_desmoothed_result_stderr_summary_only`
(`alpha_stderr IS NULL OR metric_type = 'DESMOOTHING_SUMMARY'` — the 0028 DB-enforced-invariant
precedent carried; ≤63-char name asserted). Downgrade: drop `alpha_stderr`; destructive DELETE of
`alpha IS NULL` rows inside the 0028 6-statement RLS sandwich VERBATIM (trigger + FORCE RLS
disabled/restored; delete BEFORE the NOT-NULL re-tighten); the ≤63-identifier assert. ORM:
`DesmoothedReturnResult.alpha` → `nullable=True`; `alpha_stderr` added. Tests: a PG CHECK-level
test (OW row with NULL alpha survives; pre-0042 shape re-tightens on downgrade) + the
**non-superuser owner-via-membership downgrade-path test** (the 0041 mechanics verbatim:
MigrationContext(target_metadata), drive the real `downgrade()`, assert the destructive delete,
restore the widened state before returning).

**5 — The None-tolerance trio (OD-D).** THIRD site first (the verifier's R3): `api/perf.py`
`_dr_row_out` — `alpha=f"{row.alpha:f}"` (:743) gains the None guard its sibling nullable
columns already have; `DesmoothedReturnRowOut.alpha` → `str | None`; `alpha_stderr` echoed on
the summary row-out (additive). Then the serializer: `snapshot/serialize.py::desmoothed_return_content`:
the `alpha` value becomes None-tolerant (existing pins byte-identical — alpha is non-null on every
existing row; test-pinned both directions); **`alpha_stderr` is EXCLUDED** (the 0038/0040
false-drift landmine; test-pinned). The key set unchanged.

**6 — The API (OD-G).** Two new registrar endpoints (`POST /perf/models/desmoothing-estimated`,
`POST /perf/models/desmoothing-okunev-white` — or the perf router's home shape); the run/read
endpoints unchanged (dispatch on the bound version).

**7 — Constants + docs (OD-F).** The two new dossier limitation sets (AR1_ESTIMATED:
sampling-error / white-noise-band / structure-still-assumed; OW: fixed-sequence /
vendor-normalized-transcription / series-shortening) under the HG-1 fence. The family rewords for
NEW registrations: the declared-α rider → realized-as-convention; the single-lag rider → OW
REALIZED, **GLM clause PRESERVED with the determinism note** (the RS-1 bundling lesson). Dated
pa_1 amendment (v2 register partially discharged; the band-v2 line discharged). NEW referent
`05_analytics_methodologies/desmoothing_estimated_v1.md` carrying Part 2 verbatim grades (GLM
extraction-verified-but-v2 with the optimizer obstacle; OW verified-by-derivation + vendor,
primary gated, re-verify-before-extension; Bartlett declared-not-exact).

**8 — Demo stage 6 (OD-E).** `demo/ds2_stage6.py` + `scripts/run_demo_ds2.py`: seed
`PE-HARBORVIEW-IX` (16 quarterly marks, TD-1-realistic, generated from a declared true series
smoothed at known α_true = 0.4 — the claim is ESTIMATION-WITH-HONEST-UNCERTAINTY, NOT recovery:
the dossier states the deterministic draw's α̂, α_true, the ≈0.26 band, AND the expected upward
small-n bias — the verifier's R1 reframe); register the two versions; run DECLARED
(v1 on the new series) + AR1_ESTIMATED + OW; file the two INITIAL AWCs (evidence = own runs;
finding keys fail-loud; next_review_due per tier ceiling); **NO TRIGGERED** (the recorded
no-closable-condition honesty). Refuse-not-skip on the AR1_ESTIMATED-version probe; single commit.
Suites `test_demo_stage6_ds2.py` (+ `_pg.py`, the five-stage refuse-tolerant fixture + stage 6);
CI step after stage 5, before the downgrade smoke (which now exercises 0042's destructive delete
against stage-6 OW rows every run — the 0041 coupling precedent).

**9 — Tests + battery.** Kernel: exact-rational goldens for ρ̂₁/α̂/stderr; the OW zeroing property tested as the
ALGEBRAIC IDENTITY (the verifier's R2 respecification — c_i is generically irrational and the
FILTERED series' own sample autocorrelation is nonzero at finite n by truncation/re-centering):
assert the quadratic residual ρ̂_i·c² − (1+ρ̂_2i)·c + ρ̂_i ≈ 0 at a stated Decimal tolerance on
the ORIGINAL series' sample autocovariances (plus one perfect-square-discriminant fixture where
c is exactly rational), the '−'-root choice both signs of ρ_i, the identity-pass edge, the
length-vs-order floors, the fail-closed edges; the declared-path
byte-regression against shipped PA-1 goldens. Gate: the ambiguity/stray-literal battery (the RS-1
fold tests' shape). Service: dispatch, floors, the 422 mappings, pin reproduction (recompute α̂ +
the OW series from pins alone). `make check`; full local-PG fresh (all six demo suites in CI
order); `alembic check`; the downgrade smoke.

## Review composition (OD-G)
The ratified 4-finder shape (decision record Part 5): adversarial · numeric (the OW algebra is the
one genuinely new math — highest rigor there) · doctrine · scope-fence.

## Verification appendix (the standing planning pass)
Runs BEFORE ratification; the highest-value check is the independent re-derivation of the OW lag-i
quadratic (Part 2's settled ambiguity). Findings fold into the decision record before "Approve all."
