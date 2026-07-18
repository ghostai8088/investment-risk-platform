"""RS-1 pure-kernel tests — the EWMA residual-variance convention (OD-RS-1-A) and the
empirical-Bayes cross-sectional shrinkage (OD-RS-1-B). Both are exercised against INDEPENDENT
exact-rational re-derivations (the numeric-finder discipline), never the kernels' own arithmetic."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from irp_shared.risk.proxy_weight_kernel import ProxyWeightKernelError, estimate_ols
from irp_shared.risk.residual_shrinkage_kernel import (
    MIN_COHORT_SIZE,
    ResidualShrinkageKernelError,
    ShrinkageMemberInput,
    shrink_residual_variances,
)

# A small, exactly-solvable OLS case (n=5, k=1): intercept + one factor.
_F = [Fraction(1), Fraction(2), Fraction(3), Fraction(4), Fraction(5)]
_Y = [Fraction(2), Fraction(4), Fraction(5), Fraction(4), Fraction(6)]


def _ols_residuals(f: list[Fraction], y: list[Fraction]) -> list[Fraction]:
    """Exact 2x2 normal-equations OLS (intercept + one factor); returns the residual vector."""
    n = len(y)
    sf = sum(f)
    sff = sum(v * v for v in f)
    sy = sum(y)
    sfy = sum(fi * yi for fi, yi in zip(f, y, strict=True))
    # [[n, sf],[sf, sff]] [b0,b1]' = [sy, sfy]'
    det = Fraction(n) * sff - sf * sf
    b0 = (sff * sy - sf * sfy) / det
    b1 = (Fraction(n) * sfy - sf * sy) / det
    return [yi - (b0 + b1 * fi) for fi, yi in zip(f, y, strict=True)]


def _d(fr: Fraction) -> Decimal:
    """Exact Fraction -> Decimal (prec-safe for the small integer values used here)."""
    return Decimal(fr.numerator) / Decimal(fr.denominator)


def _yx() -> tuple[list[Decimal], list[list[Decimal]]]:
    return [_d(v) for v in _Y], [[_d(v) for v in _F]]


def _close(actual: Decimal, expected: Fraction, tol: str = "1E-28") -> bool:
    return abs(actual - Decimal(expected.numerator) / Decimal(expected.denominator)) < Decimal(tol)


# --- EWMA (OD-RS-1-A) ---------------------------------------------------------------------------


def test_raw_path_residual_stdev_matches_classical_unbiased() -> None:
    """decay_lambda=None => the classical s^2 = e'e/(n-(k+1)) — byte-identical to pre-RS-1."""
    e = _ols_residuals(_F, _Y)
    ss_res = sum(v * v for v in e)
    classical_var = ss_res / Fraction(len(_Y) - 2)  # n - (k+1), k=1
    y, x = _yx()
    fit = estimate_ols(y, x)
    # residual_stdev = sqrt(classical_var)
    assert _close(fit.residual_stdev * fit.residual_stdev, classical_var)


def test_ewma_weights_sum_to_one_and_recency_orientation() -> None:
    """The EWMA variance = SUM w_i e_i^2 with w_i = (1-l) l^(n-1-i)/(1-l^n); most-recent i=n-1 gets
    the largest weight. Re-derived independently in Fraction."""
    lam = Fraction(9, 10)
    e = _ols_residuals(_F, _Y)
    n = len(e)
    one_minus = Fraction(1) - lam
    denom = Fraction(1) - lam**n
    weights = [one_minus * lam ** (n - 1 - i) / denom for i in range(n)]
    assert sum(weights) == Fraction(1)  # exact
    assert weights[-1] > weights[0]  # most-recent carries the largest weight
    ewma_var = sum(w * ei * ei for w, ei in zip(weights, e, strict=True))
    y, x = _yx()
    fit = estimate_ols(y, x, decay_lambda=Decimal("0.9"))
    assert _close(fit.residual_stdev * fit.residual_stdev, ewma_var)


def test_ewma_lambda_near_one_approaches_biased_equal_weight_mean() -> None:
    """As lambda -> 1-, the EWMA weights flatten to 1/n => the variance -> e'e/n (the BIASED mean,
    divided by n, NOT the n-k classical) — the recorded no-DOF-correction property."""
    e = _ols_residuals(_F, _Y)
    ss_res = sum(v * v for v in e)
    biased_mean = ss_res / Fraction(len(_Y))  # divided by n
    y, x = _yx()
    fit = estimate_ols(y, x, decay_lambda=Decimal("0.999999999"))
    # close to the /n mean, and DISTINCT from the /(n-k) classical
    assert _close(fit.residual_stdev * fit.residual_stdev, biased_mean, tol="1E-6")
    classical = ss_res / Fraction(len(_Y) - 2)
    assert abs(biased_mean - classical) > Fraction(0)  # the two divisors genuinely differ


def test_ewma_leaves_ols_output_byte_identical() -> None:
    """The s2 decoupling: coefficients, std_errors, and r_squared are UNCHANGED by decay_lambda —
    only residual_stdev diverges."""
    y, x = _yx()
    raw = estimate_ols(y, x)
    ewma = estimate_ols(y, x, decay_lambda=Decimal("0.9"))
    assert ewma.coefficients == raw.coefficients
    assert ewma.std_errors == raw.std_errors
    assert ewma.r_squared == raw.r_squared
    assert ewma.residual_stdev != raw.residual_stdev  # the one thing that changes


@pytest.mark.parametrize("bad", ["0", "1", "-0.5", "1.5"])
def test_ewma_rejects_out_of_range_lambda(bad: str) -> None:
    with pytest.raises(ProxyWeightKernelError) as exc:
        y, x = _yx()
        estimate_ols(y, x, decay_lambda=Decimal(bad))
    assert exc.value.reason == "decay-lambda-range"


# --- Empirical-Bayes shrinkage (OD-RS-1-B) ------------------------------------------------------


def _members(stdevs: list[str], n_obs: int, n_reg: int) -> list[ShrinkageMemberInput]:
    return [ShrinkageMemberInput(Decimal(s), n_obs, n_reg) for s in stdevs]


def _eb_golden(stdevs: list[Fraction], n_obs: int, n_reg: int) -> dict[str, object]:
    """Independent exact-rational empirical-Bayes re-derivation."""
    s2 = [s * s for s in stdevs]
    n = len(s2)
    dof = Fraction(n_obs - n_reg)
    pool = sum(s2) / Fraction(n)
    v = [Fraction(2) * (x * x) / dof for x in s2]
    v_bar = sum(v) / Fraction(n)
    s2_cross = sum((x - pool) ** 2 for x in s2) / Fraction(n - 1)
    tau2 = max(Fraction(0), s2_cross - v_bar)
    w = [Fraction(0) if (vi + tau2) == 0 else vi / (vi + tau2) for vi in v]
    shrunk = [wi * pool + (Fraction(1) - wi) * xi for wi, xi in zip(w, s2, strict=True)]
    return {"pool": pool, "tau2": tau2, "w": w, "shrunk": shrunk}


def test_eb_shrinkage_matches_independent_derivation_and_is_heterogeneous() -> None:
    stdevs = [Fraction(1, 10), Fraction(2, 10), Fraction(3, 10)]
    gold = _eb_golden(stdevs, n_obs=10, n_reg=2)
    est = shrink_residual_variances(_members(["0.1", "0.2", "0.3"], 10, 2))
    assert _close(est.pool_variance, gold["pool"])  # type: ignore[arg-type]
    assert _close(est.prior_dispersion, gold["tau2"])  # type: ignore[arg-type]
    w_gold = gold["w"]
    for mem, wg, sg in zip(est.members, w_gold, gold["shrunk"], strict=True):  # type: ignore[arg-type]
        assert _close(mem.shrinkage_weight, wg)
        assert _close(mem.shrunk_residual_stdev * mem.shrunk_residual_stdev, sg)
    # heterogeneous: the noisier (largest-variance) member shrinks MORE than the tightest
    assert est.members[2].shrinkage_weight > est.members[0].shrinkage_weight
    # every shrunk value lies BETWEEN its raw and the pool (a convex blend)
    for mem in est.members:
        lo = min(mem.raw_residual_variance, est.pool_variance)
        hi = max(mem.raw_residual_variance, est.pool_variance)
        sv = mem.shrunk_residual_stdev * mem.shrunk_residual_stdev
        assert lo <= sv <= hi


def test_eb_homogeneous_cohort_full_shrink_to_pool() -> None:
    """Identical estimates => S2_cross=0 => tau^2=0 => w_i=1 => every shrunk variance equals the
    pool (which equals the common variance)."""
    est = shrink_residual_variances(_members(["0.2", "0.2", "0.2", "0.2"], 12, 3))
    assert est.prior_dispersion == Decimal(0)
    for mem in est.members:
        assert mem.shrinkage_weight == Decimal(1)
        assert _close(
            mem.shrunk_residual_stdev * mem.shrunk_residual_stdev,
            Fraction(2, 10) ** 2,
        )


def test_eb_below_min_cohort_fails_closed() -> None:
    for n in range(0, MIN_COHORT_SIZE):
        with pytest.raises(ResidualShrinkageKernelError) as exc:
            shrink_residual_variances(_members(["0.1"] * n, 10, 2))
        assert exc.value.reason == "cohort-too-small"


def test_eb_non_positive_residual_df_fails_closed() -> None:
    # n_observations == n_regressors => dof 0 => no measurable sampling variance
    with pytest.raises(ResidualShrinkageKernelError) as exc:
        shrink_residual_variances(_members(["0.1", "0.2", "0.3"], 3, 3))
    assert exc.value.reason == "non-positive-residual-df"


def test_eb_reproducible_from_inputs_alone() -> None:
    """Two identical input cohorts produce byte-identical results (deterministic Decimal — the
    method-as-identity reproducibility contract)."""
    a = shrink_residual_variances(_members(["0.13", "0.27", "0.19", "0.31"], 15, 3))
    b = shrink_residual_variances(_members(["0.13", "0.27", "0.19", "0.31"], 15, 3))
    assert [m.shrunk_residual_stdev for m in a.members] == [
        m.shrunk_residual_stdev for m in b.members
    ]
    assert [m.shrinkage_weight for m in a.members] == [m.shrinkage_weight for m in b.members]
