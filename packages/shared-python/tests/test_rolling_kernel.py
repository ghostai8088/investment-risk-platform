"""RM-1 rolling-risk kernel (ENT-064) — the pure math, with every ratified choice pinned.

Both of RM-1's BLOCKING verifier findings lived in this file's subject matter (the alignment
criterion was vacuous; the drawdown was not determined), so the tests below are written as
refutations of specific defects rather than as coverage. Each names the defect it prevents.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from irp_shared.perf.rolling_kernel import (
    MonthlyReturn,
    RollingKernelError,
    SubPeriod,
    annualize_return,
    annualize_volatility,
    assert_above_total_loss,
    assert_month_aligned,
    is_month_end,
    last_weekday_of_month,
    max_drawdown,
    relink_to_months,
    rolling_windows,
)
from irp_shared.perf.stats_kernel import sample_stdev


def _months(*pairs: tuple[date, str]) -> list[MonthlyReturn]:
    return [MonthlyReturn(month_end=d, value=Decimal(v), n_sub_periods=1) for d, v in pairs]


# --- the month-end convention ----------------------------------------------------------------


def test_the_business_day_allowance_admits_a_gips_conforming_weekend_month_end() -> None:
    """GIPS 2.A.23.b says "the calendar month end OR THE LAST BUSINESS DAY of the month". The draft
    truncated the second clause, and the truncation is not cosmetic: 2026-01-31 is a SATURDAY and
    2026-05-31 a SUNDAY, so a firm valuing on the preceding Friday is fully conforming. A strict
    calendar-month-end gate would refuse a compliant book while citing GIPS as its authority."""
    assert date(2026, 1, 31).weekday() == 5  # Saturday — the premise, verified in the test
    assert date(2026, 5, 31).weekday() == 6  # Sunday
    for day in (date(2026, 1, 31), date(2026, 1, 30), date(2026, 5, 31), date(2026, 5, 29)):
        assert is_month_end(day), day
    for day in (date(2026, 1, 29), date(2026, 5, 28), date(2026, 3, 15)):
        assert not is_month_end(day), day


def test_the_mirrored_month_end_rule_agrees_with_the_scheduler(  # noqa: D401
) -> None:
    """THE CONFORMANCE PIN for a hand-mirrored contract (the SCH-2 standing rule).

    ``last_weekday_of_month`` is duplicated from ``scheduling.service`` rather than imported —
    importing it would drag the entire risk + exposure compute stack into ``perf`` for three lines
    of calendar arithmetic. A duplicate is only safe if it is pinned, so this sweeps every month
    over twelve years and asserts the two implementations are identical.
    """
    from irp_shared.scheduling.service import _last_weekday_of_month as scheduler_rule

    for year in range(2024, 2036):
        for month in range(1, 13):
            assert last_weekday_of_month(year, month) == scheduler_rule(year, month), (year, month)


# --- the THREE-condition alignment criterion --------------------------------------------------

_JAN = date(2026, 1, 30)  # Friday — January's last business day (the 31st is a Saturday)
_FEB = date(2026, 2, 28)
_MAR = date(2026, 3, 31)


def test_a_well_formed_month_grid_is_accepted() -> None:
    assert_month_aligned([_JAN, _FEB, _MAR])


def test_extra_intra_month_boundaries_are_allowed_and_do_not_break_alignment() -> None:
    """The criterion constrains which months are REPRESENTED, never how many boundaries a month may
    hold — the extra ones are relinked into their month. The demo fixture depends on this: it seeds
    a mid-month boundary precisely so one month genuinely relinks two sub-periods, because on a pure
    month-end calendar the relink is the identity and the slice's crux would never be exercised."""
    assert_month_aligned([_JAN, date(2026, 2, 13), _FEB, _MAR])


def test_a_within_month_series_is_refused_rather_than_passing_vacuously() -> None:
    """V1-B1 — THE defect that made the first draft self-contradictory. The draft's criterion was
    "every month-end inside the span is a boundary", which holds over the EMPTY SET for any series
    contained in one month. The demo campaign's 2026-05-18 -> 05-26 span contains no month-end at
    all, so it PASSED while the record's own prose said it must be refused."""
    with pytest.raises(RollingKernelError, match="not a month end"):
        assert_month_aligned([date(2026, 5, 18), date(2026, 5, 26)])


def test_a_partial_leading_month_is_refused_not_truncated() -> None:
    """V1-B2. `2026-01-15, 01-30, 02-28` satisfies "every interior month-end is a boundary" while
    pooling a 15-day observation with a 29-day one — standard deviations differing by ~1.3x, the
    exact heteroskedastic pooling the monthly grid exists to prevent. Truncating instead of refusing
    would silently change the caller's requested span; imputing a valuation is prohibited."""
    with pytest.raises(RollingKernelError, match="opens on 2026-01-15"):
        assert_month_aligned([date(2026, 1, 15), _JAN, _FEB])


def test_a_partial_trailing_month_is_refused() -> None:
    with pytest.raises(RollingKernelError, match="closes on 2026-03-16"):
        assert_month_aligned([_JAN, _FEB, date(2026, 3, 16)])


def test_a_missing_interior_month_is_refused_and_named() -> None:
    with pytest.raises(RollingKernelError, match="2026-02"):
        assert_month_aligned([_JAN, _MAR])


def test_a_span_inside_one_month_is_refused_with_an_HONEST_reason() -> None:
    """Both boundaries are legitimate January month-ends (the 30th is the last business day, the
    31st the calendar end), so conditions (1) and (2) pass — yet the span measures nothing. Without
    an explicit guard the interior-month walk still refuses, but blames "a missing February", which
    would send someone looking for data that was never required."""
    with pytest.raises(RollingKernelError, match="does not cover a whole calendar month"):
        assert_month_aligned([date(2026, 1, 30), date(2026, 1, 31)])


def test_unordered_or_duplicate_boundaries_are_refused() -> None:
    with pytest.raises(RollingKernelError, match="strictly increasing"):
        assert_month_aligned([_FEB, _JAN, _MAR])
    with pytest.raises(RollingKernelError, match="strictly increasing"):
        assert_month_aligned([_JAN, _JAN, _MAR])


# --- the relink -------------------------------------------------------------------------------


def test_a_month_with_one_sub_period_relinks_to_the_identity() -> None:
    """Verifier-held: ``link_periods`` on a single element is bit-identically the identity, because
    ``quantize((1+r)-1)`` is idempotent on 12dp input. So a pure month-end calendar is safe."""
    months = relink_to_months(
        [SubPeriod(_JAN, _FEB, Decimal("0.012345678901"))],
    )
    assert months[0].value == Decimal("0.012345678901")
    assert months[0].n_sub_periods == 1


def test_two_sub_periods_in_one_month_are_geometrically_linked() -> None:
    months = relink_to_months(
        [
            SubPeriod(_JAN, date(2026, 2, 13), Decimal("0.02")),
            SubPeriod(date(2026, 2, 13), _FEB, Decimal("0.03")),
        ]
    )
    assert len(months) == 1
    # (1.02 * 1.03) - 1 = 0.0506 exactly
    assert months[0].value == Decimal("0.050600000000")
    assert months[0].n_sub_periods == 2
    assert months[0].month_end == _FEB


# --- the 1 + m > 0 precondition ---------------------------------------------------------------


def test_a_total_loss_month_is_refused_and_named() -> None:
    """V1-B3. PM-1's only value gates are BMV > 0 and denominator > 0, so EMV = 0 is LEGAL and
    yields exactly -1.0 — and ``link_periods`` has no 1+r>0 guard, so -1 is ABSORBING. This is not
    the magnitude gate: -1 sits well inside _MAX_RESULT_ABS = 1E7."""
    with pytest.raises(RollingKernelError, match="2026-02-28"):
        assert_above_total_loss(_months((_JAN, "0.01"), (_FEB, "-1.0")))


def test_a_month_below_total_loss_is_refused() -> None:
    """Reachable via a large late TRANSFER_IN under PM-1's recorded no-cash-ledger limitation."""
    with pytest.raises(RollingKernelError, match="at or below -100%"):
        assert_above_total_loss(_months((_JAN, "-1.5")))


# --- maximum drawdown -------------------------------------------------------------------------


def test_the_base_point_is_an_observation_worth_10_percentage_points() -> None:
    """V1-B4, the choice worth 10pp. A window OPENING on a loss reports 0.00 if V_0 is omitted and
    0.10 if it is included — converting a real drawdown into a value indistinguishable from "no
    drawdown". Chekhlov sets w_0 = 0 and notes xi_0 is always zero: the base point IS an
    observation with drawdown zero."""
    returns = [Decimal("-0.10")] + [Decimal("0.01")] * 11
    assert max_drawdown(returns) == Decimal("0.100000000000")


def test_a_monotonically_rising_window_has_a_LEGITIMATE_zero_drawdown() -> None:
    """Zero is a real answer here, not an absence — which is exactly why the result table cannot use
    0 as a suppression sentinel (the ENT-064 nullable-value + explicit-flag design)."""
    assert max_drawdown([Decimal("0.01")] * 6) == Decimal("0.000000000000")


def test_the_running_peak_never_looks_ahead() -> None:
    """A later recovery must not shrink the drawdown that already happened: down 20% then up 100%
    still reports 0.20."""
    assert max_drawdown([Decimal("-0.20"), Decimal("1.00")]) == Decimal("0.200000000000")


def test_the_post_condition_bounds_the_ratio_to_zero_one() -> None:
    for returns in ([Decimal("-0.5"), Decimal("-0.5")], [Decimal("0.3"), Decimal("-0.9")]):
        assert Decimal(0) <= max_drawdown(returns) <= Decimal(1)


# --- annualization ----------------------------------------------------------------------------


def test_the_annualization_operator_is_sqrt_12() -> None:
    """GIPS 4.A.1.j's operator [V] — corroborated by reproducing CFA Institute's published 3-year
    figures from the underlying 36 monthly returns."""
    assert annualize_volatility(Decimal("0.050000000000")) == Decimal("0.173205080757")


def test_a_twelve_month_annualized_return_is_definitionally_the_cumulative_return() -> None:
    """OD-RM-1-G: at W = 12 the exponent is exactly 1. Emitting both would ship two governed numbers
    that are always identical, so the binder suppresses the annualized row at that window — and
    ``rolling_windows`` reports None rather than a duplicate."""
    assert annualize_return(Decimal("0.30"), 12) == Decimal("0.300000000000")


def test_annualizing_below_one_year_is_refused_as_defense_in_depth() -> None:
    """GIPS 2.A.12 is a hard MUST NOT. **Where it is actually enforced is the registered parameter
    domain {12, 36}** — no governed caller can reach W < 12 — so this guard is honest
    defense-in-depth, and calling it "the invariant" would be a vacuous control."""
    with pytest.raises(RollingKernelError, match="2.A.12"):
        annualize_return(Decimal("0.05"), 6)


# --- windows ----------------------------------------------------------------------------------


def _twenty_four_months() -> list[MonthlyReturn]:
    months: list[MonthlyReturn] = []
    year, month = 2025, 1
    for i in range(24):
        # A designed multi-month drawdown in the middle so MDD is not identically zero.
        value = "-0.04" if 8 <= i <= 12 else "0.01"
        months.append(
            MonthlyReturn(
                month_end=last_weekday_of_month(year, month),
                value=Decimal(value),
                n_sub_periods=1,
            )
        )
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def test_only_complete_windows_are_emitted() -> None:
    months = _twenty_four_months()
    windows = rolling_windows(months, 12, opening_boundary=date(2024, 12, 31))
    assert len(windows) == 13  # 24 months - 12 + 1
    assert all(w.n_observations == 12 for w in windows)
    assert windows[0].period_start == date(2024, 12, 31)  # d_0 opens the first window
    assert windows[1].period_start == months[0].month_end  # then the prior month's close


def test_mdd_36_is_at_least_mdd_12_at_a_common_end_date() -> None:
    """A 36-month window contains its trailing 12-month window, and sup(subset) <= sup(superset),
    so the longer window can never report the smaller drawdown — up to 1 ulp at 12dp, where a
    half-way rounding point can invert the last digit (a constructed witness exists; 20k random
    trials found none).

    **This is NOT the test that proves window-local rebasing**, though it was described that way in
    four places. Under a run-global peak the drawdown at each point is window-INDEPENDENT, so the
    inequality holds under both conventions and a run-global mutant passes this test unchanged. The
    discriminating test is ``test_the_drawdown_is_WINDOW_LOCAL_not_run_global``."""
    months = _twenty_four_months() + _twenty_four_months()[:12]  # 36 months
    w12 = rolling_windows(months, 12, opening_boundary=date(2024, 12, 31))[-1]
    w36 = rolling_windows(months, 36, opening_boundary=date(2024, 12, 31))[-1]
    assert w12.period_end == w36.period_end  # a COMMON end date, or the comparison is meaningless
    assert w36.max_drawdown >= w12.max_drawdown


def test_the_twelve_month_window_reports_no_annualized_return() -> None:
    windows = rolling_windows(_twenty_four_months(), 12, opening_boundary=date(2024, 12, 31))
    assert all(w.annualized_return is None for w in windows)


def test_a_thirty_six_month_window_does_report_one() -> None:
    months = _twenty_four_months() + _twenty_four_months()[:12]
    windows = rolling_windows(months, 36, opening_boundary=date(2024, 12, 31))
    assert windows[0].annualized_return is not None
    assert windows[0].annualized_return != windows[0].cumulative_return


def test_every_emitted_pair_reconciles_EXACTLY_from_the_stored_value() -> None:
    """V1-M13 — the declared quantize ORDER, tested on what is actually EMITTED.

    The whole justification for shipping both an unannualized and an annualized volatility row is
    that a reader can verify one from the other. That is only true if the annualization multiplies
    the ALREADY-QUANTIZED 12dp stored value rather than a higher-precision intermediate: reading
    the stored row and applying the public operator must land exactly on the stored annualized row,
    for every pair.

    (An earlier version of this test compared ``annualize_volatility(x)`` against its own formula,
    which merely restated the implementation — a mutation that changed the constant to an
    equivalent literal passed it. This version consumes the emitted rows instead.)
    """
    windows = rolling_windows(_twenty_four_months(), 12, opening_boundary=date(2024, 12, 31))
    assert windows, "no windows to reconcile"
    for window in windows:
        assert window.annualized_volatility == annualize_volatility(window.volatility)


# ------------------------------------------- the POSITIVE path, pinned to golden values ---
# The 4-finder review found the slice's refusal/alignment edges well covered and its COMPUTATIONAL
# path almost entirely unpinned: an arithmetic-sum mutant replacing the geometric link, and a
# volatility computed over the wrong slice, BOTH survived the whole suite. A governed number whose
# value is never asserted is not governed. These are the missing goldens.


def test_the_rolling_return_is_GEOMETRICALLY_linked_not_summed() -> None:
    """Twelve +2% months. The geometric link gives 1.02^12 - 1; an arithmetic sum gives 0.24 — a
    2.8pp error in the headline statistic that no other test could see."""
    months = _months(*[(last_weekday_of_month(2025, m), "0.02") for m in range(1, 13)])
    window = rolling_windows(months, 12, opening_boundary=date(2024, 12, 31))[0]
    assert window.cumulative_return == Decimal("0.268241794563")  # 1.02^12-1, HALF_UP 12dp
    assert window.cumulative_return != Decimal("0.240000000000")  # the summation mutant's answer


def test_the_volatility_is_computed_over_the_WHOLE_window() -> None:
    """A slice-off-by-one (``values[:-1]``) survives every reconciliation test, because the
    annualized row is derived from the SAME wrong sigma. Only a golden over a known sample catches
    it — so the sample here has a deliberately distinctive final observation."""
    values = ["0.01"] * 11 + ["0.20"]
    months = _months(*[(last_weekday_of_month(2025, m), v) for m, v in enumerate(values, start=1)])
    window = rolling_windows(months, 12, opening_boundary=date(2024, 12, 31))[0]
    assert window.n_observations == 12
    assert window.volatility == sample_stdev([Decimal(v) for v in values])
    # ...and NOT the 11-observation answer the off-by-one would give.
    assert window.volatility != sample_stdev([Decimal(v) for v in values[:-1]])


def test_the_drawdown_is_WINDOW_LOCAL_not_run_global() -> None:
    """THE discriminating test for OD-RM-1-H — and my first attempt at it did not discriminate.

    ``MDD_36 >= MDD_12`` does NOT distinguish the conventions: under a run-global peak the drawdown
    at each point is window-independent, so a max over a superset still dominates a max over a
    subset. The inequality holds either way, and the review proved a run-global mutant passes it.

    Nor is "a window that opens after a peak" enough on its own: if the run peak IS the window's
    opening level, the two conventions COINCIDE, because the rebasing is a scale factor and the
    ratio-to-peak is scale-invariant. My first fixture made exactly that mistake and the mutant
    survived it.

    What actually discriminates is a book already DECLINING when the window opens, so the run's
    high-water mark sits strictly ABOVE the window's opening level: months 1-6 rise 10%/mo (the run
    peak), months 7-12 fall 5%/mo, and the final window covers months 13-24, which merely drift with
    one small dip. Window-local sees only that dip. Run-global measures every point against a peak
    the window never contained, and reports roughly an order of magnitude more.
    """
    values = ["0.10"] * 6 + ["-0.05"] * 6 + ["0.01"] * 5 + ["-0.02"] + ["0.01"] * 6
    months = _months(
        *[(last_weekday_of_month(2025 + (i // 12), (i % 12) + 1), v) for i, v in enumerate(values)]
    )
    last = rolling_windows(months, 12, opening_boundary=date(2024, 12, 31))[-1]
    assert last.period_end == last_weekday_of_month(2026, 12)
    # Window-local: only the -2% dip inside this window, against the window's own running peak.
    assert last.max_drawdown < Decimal("0.05")
    # Run-global would carry the month-6 high-water mark in and report ~0.26 — an order of
    # magnitude larger. Pinning the small value is what refuses that implementation.
    assert last.max_drawdown < Decimal("0.10")


def test_an_interior_month_represented_ONLY_by_a_mid_month_boundary_is_refused() -> None:
    """February present only as a mid-month date would pool a 14-day observation with a 46-day one.

    **Honest note on which condition catches it.** This was written as a negative control for
    condition (3)'s ``is_month_end`` filter, and it is NOT one: dropping that filter leaves this
    test green, because the newer condition (5) — every measured month must CLOSE on a month-end —
    already refuses the same input. Given (5), the filter in (3) cannot change any outcome: a month
    whose last boundary is a month-end is in the set either way, and a month whose last boundary is
    not is refused by (5) first. The filter is kept as defense-in-depth and documented as
    subsumed, rather than left with a test that appears to guard it and does not."""
    # Wave-13 close: tightened from `match="2026-02"`. Conditions (3) and (5) BOTH mention that
    # month in their messages, so the loose pattern passed under either — which is precisely how a
    # condition-(5) deletion mutant survived this file. Matching the (5) wording makes the two
    # distinguishable.
    with pytest.raises(RollingKernelError, match="closes on 2026-02-13"):
        assert_month_aligned([date(2026, 1, 30), date(2026, 2, 13), date(2026, 3, 31)])


# --- the alignment conditions (4) and (5): the Wave-13 close's mutation controls ----------------


def test_condition_4_refuses_an_opening_boundary_that_is_not_last_in_its_month() -> None:
    """RM-1's 4-finder review folded a HIGH here — the alignment gate admitted a ONE-DAY "month" —
    and the fix landed in the kernel. But the close audit MUTATED condition (4) away and the entire
    committed suite still passed: no input anywhere in the repo discriminates it.

    That matters more than an ordinary coverage gap, because the slice's own closing gate asserts
    the opposite: *"every new guard is mutation-tested — the source is broken in a scratch copy and
    the test must fail — before the slice is called done"* (rm_1_decision_record.md; repeated in the
    registered methodology doc). The guard was real, the claim about it was not, and it is the claim
    a later slice would rely on.

    The counterexample is the record's own: 2026-01-30 (Friday, the last business day) followed by
    2026-01-31 (Saturday, the calendar end). Condition (1) passes on d_0, and the relink then emits a
    one-day January pooled into sigma, x sqrt(12), the drawdown and the 12-month return — a
    dispersion ratio of sqrt(31) ~ 5.6x against a whole month.
    """
    with pytest.raises(RollingKernelError, match="not the LAST boundary in its month"):
        assert_month_aligned(
            [date(2026, 1, 30), date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
        )


def test_condition_5_refuses_a_measured_month_closing_off_the_grid() -> None:
    """The other end of the same root cause, equally undefended before this close.

    2026-05-29 is the last weekday of May; 2026-05-30 is a Saturday and NOT a month end. Without
    condition (5) the May observation closes on 2026-05-30, and that date is then stamped into
    governed rows as ``period_end`` — a governed number carrying a boundary that is not on the grid
    its own model declares.
    """
    with pytest.raises(RollingKernelError, match="closes on 2026-05-30"):
        assert_month_aligned(
            [date(2026, 4, 30), date(2026, 5, 29), date(2026, 5, 30), date(2026, 6, 30)]
        )


def test_the_two_conditions_accept_the_shapes_they_must_not_refuse() -> None:
    """POSITIVE CONTROL. Conditions (4) and (5) refuse *specific* shapes; a mutant that refused
    every grid would satisfy both negatives above and break every legitimate book. Intra-month
    boundaries must still relink freely — only the month's CLOSING boundary is constrained."""
    assert_month_aligned([date(2025, 12, 31), date(2026, 1, 31), date(2026, 2, 28)])
    # an extra intra-month boundary is welcome: it relinks, and January still closes on the grid
    assert_month_aligned(
        [date(2025, 12, 31), date(2026, 1, 15), date(2026, 1, 31), date(2026, 2, 28)]
    )
