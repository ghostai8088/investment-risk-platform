"""BT-3 kernel tests — the AS Z̄1/Z̄2 statistics + the Christoffersen Markov leg.

The identity fixtures are EXACT (``fractions.Fraction`` end-to-end where the algebra is
rational): the null-expectation identities E[Z̄2] = 0 and E[Z̄1 | N > 0] = 0 hold EXACTLY on a
finite discrete distribution whose tail is analytically known — and the '+1'-grouping
corruption (the ES-HS-1 debt's transcription-hazard class) provably BREAKS them. The corrupted
conditional statistic evaluates to −ES/(ES+1) ≈ −0.7004 at N(0,1)/a=0.025 — numerically
COINCIDING with the −0.70 critical — so these identity tests are the only mechanical defense
against a corruption that emits plausible-looking values (the planning verifier's finding)."""

from __future__ import annotations

import itertools
import math
import random
from decimal import Decimal
from fractions import Fraction

import pytest

from irp_shared.risk.es_backtest_kernel import (
    ES_DECISION_FAIL_TO_REJECT,
    ES_DECISION_REJECT,
    Z2_CRITICALS,
    AsZStatistics,
    EsBacktestKernelError,
    as_z_statistics,
    z2_verdict,
)
from irp_shared.risk.var_backtest_kernel import (
    CHI2_2DF_CRITICALS,
    DECISION_FAIL_TO_REJECT,
    DECISION_REJECT,
    VarBacktestKernelError,
    christoffersen_lr_cc,
    christoffersen_lr_ind,
    kupiec_decision,
    lr_cc_decision,
    markov_counts,
)

# --- The exact discrete distribution: X in {-10, -5, +1} with P = {1/50, 1/50, 48/50}.
# With VaR = 4 (positive forecast): exceptions are X in {-10, -5}, so the TRUE tail
# a = 2/50 = 1/25 and the TRUE ES = -E[X | X < -VaR] = (10 + 5)/2 = 15/2. The identity
# E[X·I] = -a·ES = -(2/50)·(15/2) = -15/50 holds by construction.
_OUTCOMES: tuple[tuple[Fraction, Fraction], ...] = (
    (Fraction(-10), Fraction(1, 50)),
    (Fraction(-5), Fraction(1, 50)),
    (Fraction(1), Fraction(48, 50)),
)
_VAR = Fraction(4)
_ES = Fraction(15, 2)
_TAIL_A = Fraction(1, 25)


def _z2_exact(seq: tuple[Fraction, ...], plus_one_outside: bool) -> Fraction:
    """Z̄2 over one outcome sequence, exact; ``plus_one_outside=False`` is the CORRUPTED
    inside-denominator grouping."""
    t = len(seq)
    if plus_one_outside:
        total = sum((x / _ES for x in seq if x + _VAR < 0), Fraction(0))
        return total / (t * _TAIL_A) + 1
    total = sum((x / (_ES + 1) for x in seq if x + _VAR < 0), Fraction(0))
    return total / (t * _TAIL_A)


def _z1_exact(seq: tuple[Fraction, ...], plus_one_outside: bool) -> Fraction | None:
    n = sum(1 for x in seq if x + _VAR < 0)
    if n == 0:
        return None
    if plus_one_outside:
        total = sum((x / _ES for x in seq if x + _VAR < 0), Fraction(0))
        return total / n + 1
    total = sum((x / (_ES + 1) for x in seq if x + _VAR < 0), Fraction(0))
    return total / n


def _seq_probability(seq: tuple[Fraction, ...]) -> Fraction:
    prob = Fraction(1)
    lookup = dict(_OUTCOMES)
    for x in seq:
        prob *= lookup[x]
    return prob


def test_z2_null_expectation_identity_exact_and_corruption_breaks_it() -> None:
    """EXACT over all length-2 i.i.d. sequences: E[Z̄2] = 0 with the '+1' outside; the
    corrupted grouping is bounded away from zero."""
    values = tuple(x for x, _ in _OUTCOMES)
    e_correct = Fraction(0)
    e_corrupt = Fraction(0)
    for seq in itertools.product(values, repeat=2):
        p = _seq_probability(seq)
        e_correct += p * _z2_exact(seq, plus_one_outside=True)
        e_corrupt += p * _z2_exact(seq, plus_one_outside=False)
    assert e_correct == 0
    assert e_corrupt != 0
    # The corrupted unconditional expectation is E[Z2_corrupt] = -ES/(ES+1) exactly:
    assert e_corrupt == -_ES / (_ES + 1)


def test_z1_conditional_null_expectation_identity_exact_and_corruption_breaks_it() -> None:
    """EXACT over all length-2 sequences: E[Z̄1 | N > 0] = 0 with the '+1' outside; the
    corrupted grouping lands at -ES/(ES+1) — the plausible-looking near-threshold value."""
    values = tuple(x for x, _ in _OUTCOMES)
    num_correct = Fraction(0)
    num_corrupt = Fraction(0)
    p_nonzero = Fraction(0)
    for seq in itertools.product(values, repeat=2):
        p = _seq_probability(seq)
        z1c = _z1_exact(seq, plus_one_outside=True)
        z1x = _z1_exact(seq, plus_one_outside=False)
        if z1c is None:
            continue
        assert z1x is not None
        p_nonzero += p
        num_correct += p * z1c
        num_corrupt += p * z1x
    assert p_nonzero > 0
    assert num_correct / p_nonzero == 0
    assert num_corrupt / p_nonzero == -_ES / (_ES + 1)


def test_kernel_matches_the_exact_fraction_reference_on_a_mixed_sequence() -> None:
    """The Decimal kernel reproduces the exact-Fraction Z̄1/Z̄2 on a hand sequence with two
    exceptions, to the 12dp quantum."""
    seq = (Fraction(-10), Fraction(1), Fraction(-5), Fraction(1), Fraction(1))
    pairs = [(Decimal(int(x)), Decimal(4), Decimal("7.5")) for x in seq]
    stats = as_z_statistics(pairs, Decimal("0.04"))
    z2_ref = _z2_exact(seq, plus_one_outside=True)  # = (-2)/(5·(1/25)) + 1 = -9
    z1_ref = _z1_exact(seq, plus_one_outside=True)  # = (-2)/2 + 1 = 0
    assert z2_ref == Fraction(-9)
    assert z1_ref == Fraction(0)
    assert stats.z2 == Decimal("-9.000000000000")
    assert stats.z1 == Decimal("0.000000000000")
    assert stats.n_exceptions == 2
    assert stats.n_pairs == 5


def test_z1_is_none_not_zero_at_zero_exceptions() -> None:
    pairs = [(Decimal("1"), Decimal(4), Decimal("7.5"))] * 6
    stats = as_z_statistics(pairs, Decimal("0.04"))
    assert stats.z1 is None
    assert stats.n_exceptions == 0
    # Z-bar-2 is well-defined (= +1) at zero breaches — the verdict suppression there is the
    # binder's POLICY (OD-BT-3-A/B cross-reference), not kernel arithmetic.
    assert stats.z2 == Decimal("1.000000000000")


def test_kernel_refusals() -> None:
    with pytest.raises(EsBacktestKernelError):
        as_z_statistics([], Decimal("0.025"))
    with pytest.raises(EsBacktestKernelError):
        as_z_statistics([(Decimal(1), Decimal(4), Decimal("7.5"))], Decimal("1"))
    with pytest.raises(EsBacktestKernelError):
        as_z_statistics([(Decimal(1), Decimal(4), Decimal(0))], Decimal("0.025"))
    with pytest.raises(EsBacktestKernelError):
        as_z_statistics([(Decimal(1), Decimal(-1), Decimal("7.5"))], Decimal("0.025"))
    with pytest.raises(EsBacktestKernelError):
        z2_verdict(Decimal("-1"), Decimal("0.10"))


def test_z2_verdict_boundary_is_strict_below() -> None:
    """REJECT strictly BELOW the critical; AT the critical fails to reject (one-sided left)."""
    assert z2_verdict(Decimal("-0.70"), Decimal("0.05")) == ES_DECISION_FAIL_TO_REJECT
    assert z2_verdict(Decimal("-0.700000000001"), Decimal("0.05")) == ES_DECISION_REJECT
    assert z2_verdict(Decimal("-1.8"), Decimal("0.0001")) == ES_DECISION_FAIL_TO_REJECT
    assert z2_verdict(Decimal("-1.9"), Decimal("0.0001")) == ES_DECISION_REJECT
    assert Z2_CRITICALS[Decimal("0.05")] == Decimal("-0.70")


def test_kernel_fuzz_against_independent_float_implementation() -> None:
    """500 seeded random paired series vs a float re-implementation at 1e-9 relative."""
    rng = random.Random(20260719)
    for _ in range(500):
        t = rng.randint(1, 60)
        pairs = []
        for _ in range(t):
            x = round(rng.uniform(-30, 10), 6)
            var = round(rng.uniform(0.5, 8), 6)
            es = round(var + rng.uniform(0.01, 6), 6)
            pairs.append((Decimal(str(x)), Decimal(str(var)), Decimal(str(es))))
        a = round(rng.uniform(0.005, 0.2), 4)
        stats = as_z_statistics(pairs, Decimal(str(a)))
        total = sum(float(x) / float(es) for x, var, es in pairs if -float(x) > float(var))
        n = sum(1 for x, var, _ in pairs if -float(x) > float(var))
        z2_f = total / (t * a) + 1
        assert math.isclose(float(stats.z2), z2_f, rel_tol=1e-9, abs_tol=1e-9)
        if n:
            assert stats.z1 is not None
            assert math.isclose(float(stats.z1), total / n + 1, rel_tol=1e-9, abs_tol=1e-9)
        else:
            assert stats.z1 is None
        assert stats.n_exceptions == n


# --- Christoffersen Markov leg ---


def test_markov_counts_and_exact_independence_gives_lr_zero() -> None:
    """(a) The transition counter reproduces a hand count; (b) a 2x2 whose MLEs coincide
    (pi01 = pi11 = pi2 = 1/4) has LR_ind = 0 EXACTLY."""
    series = [0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 0, 0]
    c = markov_counts(series)
    # Hand count of the 12 adjacent pairs of the series above:
    assert (c.n00, c.n01, c.n10, c.n11) == (5, 3, 3, 1)
    from irp_shared.risk.var_backtest_kernel import MarkovCounts

    balanced = MarkovCounts(n00=6, n01=2, n10=3, n11=1)  # pi01 = pi11 = pi2 = 1/4
    assert christoffersen_lr_ind(balanced) == Decimal("0.000000000000")


def test_lr_ind_matches_independent_float_reference_on_a_dependent_series() -> None:
    """Clustered exceptions: LR_ind recomputed independently in floats at 1e-9."""
    series = [0, 0, 1, 1, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 1, 1, 0]
    c = markov_counts(series)
    lr = christoffersen_lr_ind(c)
    assert lr is not None and lr > 0
    n00, n01, n10, n11 = c.n00, c.n01, c.n10, c.n11
    pi01 = n01 / (n00 + n01)
    pi11 = n11 / (n10 + n11)
    pi2 = (n01 + n11) / (n00 + n01 + n10 + n11)

    def _ll(x: int, total: int, p: float) -> float:
        out = 0.0
        if x > 0:
            out += x * math.log(p)
        if x < total:
            out += (total - x) * math.log(1 - p)
        return out

    log_alt = _ll(n01, n00 + n01, pi01) + _ll(n11, n10 + n11, pi11)
    log_null = _ll(n01 + n11, c.total, pi2)
    assert math.isclose(float(lr), 2 * (log_alt - log_null), rel_tol=1e-9, abs_tol=1e-9)


def test_lr_ind_degenerate_tables_return_none_never_zero() -> None:
    assert christoffersen_lr_ind(markov_counts([0, 0, 0, 0])) is None  # no exit from state 1
    assert christoffersen_lr_ind(markov_counts([0, 0, 0, 1])) is None  # trailing lone exception
    assert christoffersen_lr_ind(markov_counts([1, 1, 1, 1])) is None  # no exit from state 0
    with pytest.raises(VarBacktestKernelError):
        markov_counts([0])
    with pytest.raises(VarBacktestKernelError):
        markov_counts([0, 2])


def test_lr_cc_composition_and_df2_decision() -> None:
    lr_cc = christoffersen_lr_cc(Decimal("3.2"), Decimal("2.9"))
    assert lr_cc == Decimal("6.100000000000")
    assert lr_cc_decision(lr_cc, Decimal("0.05")) == DECISION_REJECT
    assert lr_cc_decision(Decimal("5.991465"), Decimal("0.05")) == DECISION_FAIL_TO_REJECT
    assert lr_cc_decision(Decimal("9.3"), Decimal("0.01")) == DECISION_REJECT
    with pytest.raises(VarBacktestKernelError):
        lr_cc_decision(Decimal("1"), Decimal("0.10"))
    # The df=2 constants are the exact closed form -2·ln(alpha):
    assert CHI2_2DF_CRITICALS[Decimal("0.05")] == Decimal("5.991465")
    # The LR_ind decision reuses the df=1 table (same shape as Kupiec):
    assert kupiec_decision(Decimal("3.9"), Decimal("0.05")) == DECISION_REJECT
    assert AsZStatistics(z2=Decimal("1"), z1=None, n_exceptions=0, n_pairs=250).n_pairs == 250
