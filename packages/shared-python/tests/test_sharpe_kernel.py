"""SR-1 pure-kernel tier (ENT-065 — the 22nd governed number).

**The RM-1 standing lesson is first-class scope here, not review-added:** *the REFUSAL logic was
well tested while the POSITIVE computational path was unpinned — an arithmetic-sum mutant replacing
the geometric link shipped a 2.8pp error with every tier green.* So this file opens with GOLDEN
VALUES computed by hand, independently of the implementation, and states the arithmetic in the test
so a reader can check it without running anything. A mutation to the estimator, the divisor, the
operand order, or the annualizer must break one of these.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext

import pytest

from irp_shared.perf.rolling_kernel import MonthlyReturn
from irp_shared.perf.sharpe_kernel import (
    ZERO_DISPERSION_REASON,
    SharpeKernelError,
    annualize_sharpe,
    build_excess_series,
    month_key,
    sharpe_ratio,
    sharpe_windows,
)
from irp_shared.perf.stats_kernel import (
    COMPUTE_PREC,
    StatsKernelError,
    mean_and_stdev_unquantized,
    mean_return,
    quantize_result,
    sample_stdev,
)

D = Decimal

#: The GOLDEN excess series. Chosen so every step is checkable with a pen:
#:
#:   sum        = 0.12  over 12 observations  =>  mean = 0.01
#:   deviations = 0, +.01, -.01, +.02, -.02, +.01, 0, -.01, +.01, 0, +.02, -.03
#:   sum of squares = (0+1+1+4+4+1+0+1+1+0+4+9) x 1e-4 = 26e-4 = 0.0026
#:   variance   = 0.0026 / 11          (n-1, the DISCLOSED divisor)
#:   sigma      = sqrt(0.000236363...) = 0.015374122295716148...
#:   SR         = 0.01 / sigma         = 0.650443635588  (12dp, HALF_UP)
_GOLDEN = [
    D(x)
    for x in (
        "0.01",
        "0.02",
        "0.00",
        "0.03",
        "-0.01",
        "0.02",
        "0.01",
        "0.00",
        "0.02",
        "0.01",
        "0.03",
        "-0.02",
    )
]
_GOLDEN_SHARPE = D("0.650443635588")
_GOLDEN_SHARPE_ANN = D("2.253202848596")


def _months(values: list[Decimal], *, year: int = 2025) -> list[MonthlyReturn]:
    """One relinked observation per calendar month, ending on the calendar month end."""
    out: list[MonthlyReturn] = []
    for i, value in enumerate(values):
        y, m = (year + i // 12, i % 12 + 1)
        last = {
            1: 31,
            2: 28,
            3: 31,
            4: 30,
            5: 31,
            6: 30,
            7: 31,
            8: 31,
            9: 30,
            10: 31,
            11: 30,
            12: 31,
        }[m]
        out.append(MonthlyReturn(month_end=date(y, m, last), value=value, n_sub_periods=1))
    return out


# --- 1. THE NUMBER ITSELF -----------------------------------------------------------------------


def test_the_golden_sharpe_ratio_matches_the_hand_computation() -> None:
    """The headline value, computed by hand in the module docstring above and pinned here.

    This is the test the RM-1 review said every governed number owes and RM-1 did not have: a
    mutation to the mean, the sum of squares, the divisor or the quantization changes this literal.
    """
    assert sharpe_ratio(_GOLDEN) == _GOLDEN_SHARPE


def test_the_divisor_is_n_MINUS_ONE_and_the_alternative_is_MEASURABLY_different() -> None:
    """The DISCLOSED divergence from Sharpe (1994)'s own endnote, executed against the KERNEL.

    The paper uses the POPULATION sigma (divisor T = 12); this platform uses n-1, making the ratio
    about 4.3% smaller at n = 12. That is above this record's own materiality bar, which is why
    it is disclosed in the registered assumptions rather than absorbed into the paper's brand.

    **The first version of this test was VACUOUS and its docstring said the opposite.** It compared
    the LITERAL ``_GOLDEN_SHARPE`` against a locally-recomputed population Sharpe and never called
    the kernel at all — so under the exact mutation it names (``n-1 -> n`` in ``stats_kernel``) it
    PASSED while five other tests failed. A guard for the slice's headline fidelity claim that
    cannot observe the code it guards is worse than none, because the docstring reads as coverage.
    """
    # THE CALL UNDER TEST — the kernel, not a literal.
    ours = sharpe_ratio(_GOLDEN)
    assert ours is not None

    with localcontext() as ctx:
        ctx.prec = COMPUTE_PREC
        mean = sum(_GOLDEN, D(0)) / D(12)
        pop_var = sum(((v - mean) ** 2 for v in _GOLDEN), D(0)) / D(12)  # divisor T, not T-1
        population_sharpe = (mean / pop_var.sqrt()).quantize(
            D(1).scaleb(-12), rounding=ROUND_HALF_UP
        )

    # The kernel must NOT agree with the population form...
    assert ours != population_sharpe
    # ...and the sample estimator it DOES use must be the n-1 one, checked against an independent
    # computation rather than against another call to the same function.
    with localcontext() as ctx:
        ctx.prec = COMPUTE_PREC
        sample_var = sum(((v - mean) ** 2 for v in _GOLDEN), D(0)) / D(11)
        expected = (mean / sample_var.sqrt()).quantize(D(1).scaleb(-12), rounding=ROUND_HALF_UP)
    assert ours == expected

    # Ours is SMALLER, by about 4.3% — the direction and magnitude the assumptions state. The exact
    # factor is sqrt(11/12); a divisor change moves this ratio and fails here.
    divergence = ours / population_sharpe
    assert D("0.954") < divergence < D("0.958"), f"the divergence moved: {divergence}"


def test_HALF_UP_rounding_is_LOAD_BEARING_not_merely_declared() -> None:
    """The registered assumptions and the methodology doc both say ``quantize_HALF_UP``. A review
    found the rounding mode could be switched to HALF_EVEN with the whole suite green, because every
    other fixture lands away from a tie.

    This one sits exactly on the tie, with an EVEN 12th digit — the only place the two modes differ.
    HALF_UP rounds away from zero on both signs; HALF_EVEN would round to the even neighbour.
    """
    tie_up = D("0.123456789012") + D("0.0000000000005")
    assert quantize_result(tie_up) == D("0.123456789013")  # HALF_EVEN gives ...012
    tie_down = D("-0.123456789012") - D("0.0000000000005")
    assert quantize_result(tie_down) == D("-0.123456789013")  # away from zero, not toward even


def test_the_annualization_reads_the_STORED_value_and_that_choice_is_OBSERVABLE() -> None:
    """``SR_ann = quantize(SR_STORED x sqrt(12))``, not ``quantize(unquantized_ratio x sqrt(12))``.

    The order is what makes the emitted PAIR reconcile exactly — a consumer multiplies the raw row
    by sqrt(12) and must land on the annualized row. A review found every fixture in this file gave
    byte-identical results under both orders, so the choice was declared and unguarded.

    This series separates them by 2 ulp at 12dp: it is an ordinary twelve-observation book of
    3-decimal monthly excess returns, not a constructed extreme.
    """
    series = [
        D(x)
        for x in (
            "-0.022",
            "0.006",
            "0.024",
            "0.021",
            "0.018",
            "-0.026",
            "-0.014",
            "-0.023",
            "0.001",
            "0.018",
            "-0.002",
            "0.000",
        )
    ]
    stored = sharpe_ratio(series)
    assert stored is not None

    with localcontext() as ctx:
        ctx.prec = COMPUTE_PREC
        mean, sigma = mean_and_stdev_unquantized(series)
        from_unquantized = ((mean / sigma) * D(12).sqrt()).quantize(
            D(1).scaleb(-12), rounding=ROUND_HALF_UP
        )
    # PREMISE: the two orders genuinely differ here, so the assertion below discriminates.
    assert annualize_sharpe(stored) != from_unquantized

    assert annualize_sharpe(stored) == D("0.015977287727")
    # And the pair reconciles EXACTLY from the stored value, which is the whole point of the order.
    with localcontext() as ctx:
        ctx.prec = COMPUTE_PREC
        assert annualize_sharpe(stored) == (stored * D(12).sqrt()).quantize(
            D(1).scaleb(-12), rounding=ROUND_HALF_UP
        )


def test_the_compute_precision_is_a_declared_MARGIN_not_a_tuned_minimum() -> None:
    """``COMPUTE_PREC = 50`` is pinned as a CONSTANT, and this test states honestly what that pin
    does and does not buy.

    A review observed that mutating it to 20 leaves the suite green and filed it as an unguarded
    convention. Investigated by search rather than by argument: over 20,000 randomised
    twelve-observation 12dp series I could find NO input where 28-digit and 50-digit accumulation
    produce different 12dp ratios at any plausible magnitude. That is the honest finding — on
    column-legal input the constant is **over-provisioned head-room, not a tuned minimum**, and no
    fixture can make it load-bearing without being a contrivance.

    So the pin is a literal, and the claim in the registered assumptions is worded as what it is:
    the accumulation happens at 50 digits. Manufacturing an exotic fixture to "guard" it would be
    the vacuous-test pattern this file exists to avoid — a test that looks like coverage and
    measures nothing anyone will ever hit.
    """
    assert COMPUTE_PREC == 50


def test_the_two_denominators_genuinely_differ_and_the_excess_one_is_used() -> None:
    """The discriminator, with its premise asserted first (the RM-1 lesson: a test whose earlier
    precondition fires first proves nothing about the thing it names)."""
    portfolio = [D("0.01")] * 12
    risk_free = [
        D(x)
        for x in (
            "0.003",
            "0.004",
            "0.002",
            "0.005",
            "0.003",
            "0.004",
            "0.002",
            "0.003",
            "0.005",
            "0.004",
            "0.002",
            "0.003",
        )
    ]
    excess = [p - r for p, r in zip(portfolio, risk_free, strict=True)]

    # PREMISE 1: the portfolio series is constant, so ITS sigma is exactly zero.
    assert sample_stdev(portfolio) == D("0E-12")
    # PREMISE 2: the excess series is not, so the two denominators cannot coincide.
    assert sample_stdev(excess) > 0

    # THE CLAIM: a real ratio is emitted. Under the portfolio-sigma reading this would be None.
    assert sharpe_ratio(excess) == D("6.212607441974")


def test_the_annualized_pair_reconciles_EXACTLY_from_the_stored_value() -> None:
    """A consumer must be able to multiply the raw row by sqrt(12) and land on the annualized row.

    Consumes the STORED ratio, exactly as the binder does — not a re-derivation, which would restate
    the implementation rather than test it (the RM-1 vacuous-reconciliation lesson).
    """
    stored = sharpe_ratio(_GOLDEN)
    assert stored is not None
    assert annualize_sharpe(stored) == _GOLDEN_SHARPE_ANN
    with localcontext() as ctx:
        ctx.prec = COMPUTE_PREC
        assert (stored * D(12).sqrt()).quantize(
            D(1).scaleb(-12), rounding=ROUND_HALF_UP
        ) == _GOLDEN_SHARPE_ANN


def test_a_negative_sharpe_annualizes_to_a_MORE_negative_sharpe() -> None:
    """Sign preservation — the direction most likely to be "fixed" by a well-meaning abs()."""
    negative = [-v for v in _GOLDEN]
    ratio = sharpe_ratio(negative)
    assert ratio is not None and ratio < 0
    assert annualize_sharpe(ratio) < ratio  # more negative, not less


# --- 2. THE SUPPRESSION PREDICATE ---------------------------------------------------------------


def test_a_genuinely_constant_excess_series_is_SUPPRESSED_not_zero() -> None:
    """Zero is a LEGITIMATE Sharpe ratio (a book that exactly earns cash), so "not computable" must
    never be reported as 0.0 — which is why the kernel returns None and the binder emits a flagged
    row."""
    assert sharpe_ratio([D("0.004")] * 12) is None


def test_a_book_that_exactly_earns_cash_scores_ZERO_and_is_NOT_suppressed() -> None:
    """The other side of the same coin, and the reason the suppression flag exists at all: a mean of
    exactly zero over a DISPERSED series is a real governed value."""
    excess = [D("0.01"), D("-0.01")] * 6
    assert sharpe_ratio(excess) == D("0E-12")


def test_a_NON_constant_series_whose_QUANTIZED_sigma_is_zero_still_EMITS() -> None:
    """THE EXECUTED REFUTATION of the operand order the draft record specified (verifier B1).

    Eleven values of 1E-12 and one 0 have a true sigma of about 2.9E-13, which QUANTIZES to 0E-12.
    Dividing the quantized operands therefore raises DivisionByZero on a perfectly legal input — an
    uncaught 500 where a governed number was owed. Single-quantization divides at 50 digits and
    emits.
    """
    series = [D("1E-12")] * 11 + [D("0")]
    # The premise, executed: the quantized sigma really is zero here.
    assert sample_stdev(series) == D("0E-12")
    # The unquantized one is not — and it is the one both the predicate and the division use.
    _mean, sigma = mean_and_stdev_unquantized(series)
    assert sigma != 0
    assert sharpe_ratio(series) == D("3.175426480543")


def test_the_zero_dispersion_reason_is_TRUE_under_its_own_predicate() -> None:
    """The reason a consumer reads says the series is CONSTANT. It is emitted only when the series
    is constant — so the two cannot drift apart into a reason that lies."""
    assert "constant excess series" in ZERO_DISPERSION_REASON
    assert sharpe_ratio([D("0.004")] * 12) is None  # constant  -> suppressed
    assert sharpe_ratio([D("1E-12")] * 11 + [D("0")]) is not None  # not constant -> emitted


# --- 3. THE EXCESS SERIES -----------------------------------------------------------------------


def test_the_subtraction_is_EXACT_at_12dp_across_sign_and_magnitude_extremes() -> None:
    """Both legs are 12dp fractions, so the difference is exact at that exponent — verified rather
    than assumed, because the whole construction rests on it."""
    cases = [
        (D("0.123456789012"), D("0.000000000001"), D("0.123456789011")),
        (D("-0.999999999999"), D("0.000000000001"), D("-1.000000000000")),
        (D("9999999.999999999999"), D("-0.000000000001"), D("10000000.000000000000")),
    ]
    for portfolio, risk_free, expected in cases:
        assert portfolio - risk_free == expected


def test_a_missing_risk_free_month_is_refused_BY_NAME() -> None:
    """No imputation, no carry-forward — and the refusal must name the month an operator has to go
    and capture."""
    months = _months([D("0.01")] * 3)
    rf = {month_key(m.month_end): D("0.003") for m in months}
    del rf[month_key(months[1].month_end)]
    with pytest.raises(SharpeKernelError) as caught:
        build_excess_series(months, rf)
    assert "2025-02" in str(caught.value)


def test_the_excess_series_carries_BOTH_operands_as_evidence() -> None:
    """A reviewer reconstructing a Sharpe row by hand needs the legs, not only the difference."""
    months = _months([D("0.02")])
    rf = {month_key(months[0].month_end): D("0.005")}
    (row,) = build_excess_series(months, rf)
    assert (row.portfolio_return, row.risk_free_return, row.excess) == (
        D("0.02"),
        D("0.005"),
        D("0.015"),
    )


# --- 4. THE WINDOWS -----------------------------------------------------------------------------


def test_windows_are_trailing_complete_and_span_from_the_PRIOR_month_close() -> None:
    months = _months([D("0.01")] * 14)
    rf = {month_key(m.month_end): D("0.002") + D("0.0001") * i for i, m in enumerate(months)}
    excess = build_excess_series(months, rf)
    opening = date(2024, 12, 31)
    windows = sharpe_windows(excess, 12, opening_boundary=opening)

    assert len(windows) == 3  # 14 observations, a 12-month window
    assert windows[0].period_start == opening  # d_0 for the FIRST window only
    assert windows[0].period_end == months[11].month_end
    assert windows[1].period_start == months[0].month_end  # thereafter: the prior month's close
    assert all(w.n_observations == 12 for w in windows)


def test_both_members_of_the_pair_are_absent_TOGETHER_or_present_TOGETHER() -> None:
    """A consumer keying (SHARPE_RATIO, SHARPE_RATIO_ANN) must never find one half missing and be
    unable to tell which was suppressed."""
    months = _months([D("0.01")] * 12)
    constant_rf = {month_key(m.month_end): D("0.004") for m in months}
    (window,) = sharpe_windows(
        build_excess_series(months, constant_rf), 12, opening_boundary=date(2024, 12, 31)
    )
    assert window.sharpe is None and window.annualized_sharpe is None

    varying_rf = {
        month_key(m.month_end): D("0.002") + D("0.0001") * i for i, m in enumerate(months)
    }
    (window,) = sharpe_windows(
        build_excess_series(months, varying_rf), 12, opening_boundary=date(2024, 12, 31)
    )
    assert window.sharpe is not None and window.annualized_sharpe is not None


# --- 5. THE SHARED ESTIMATOR (the SR-1 lift must not move three shipped families) ----------------


def test_the_extracted_accumulator_leaves_the_shipped_estimators_BIT_IDENTICAL() -> None:
    """``sample_stdev`` became a wrapper over ``mean_and_stdev_unquantized`` at SR-1. P3-8 (tracking
    error), DS-2 (desmoothing) and RM-1 (rolling volatility) all consume it, so any drift here moves
    three shipped governed numbers silently.

    Pinned against values computed independently at 50 digits, not against the function itself.
    """
    with localcontext() as ctx:
        ctx.prec = COMPUTE_PREC
        mean = sum(_GOLDEN, D(0)) / D(12)
        variance = sum(((v - mean) ** 2 for v in _GOLDEN), D(0)) / D(11)
        expected_sigma = variance.sqrt().quantize(D(1).scaleb(-12), rounding=ROUND_HALF_UP)
        expected_mean = mean.quantize(D(1).scaleb(-12), rounding=ROUND_HALF_UP)
    assert sample_stdev(_GOLDEN) == expected_sigma == D("0.015374122296")
    assert mean_return(_GOLDEN) == expected_mean == D("0.010000000000")


def test_the_mean_still_accepts_a_ONE_observation_series() -> None:
    """``mean_return`` was deliberately NOT re-expressed over the n>=2 helper: a mean is defined
    at n = 1, and routing it through the variance helper would tighten a shipped precondition."""
    assert mean_return([D("0.05")]) == D("0.050000000000")
    with pytest.raises(StatsKernelError):
        sample_stdev([D("0.05")])
