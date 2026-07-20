"""Pure kernel tests for CC-2 pacing (the Takahashi-Alexander projection).

Hand-derived exact goldens (no DB); the mandatory grouping-discriminating golden (M-3); the
future-only start index; the bow=1 linearity + RD(L)=1 terminal identity; the leap-day anniversary
window; an independent exact-Fraction cross-check modelling quantize-then-roll; the domain refusals.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from irp_shared.pacing.pacing_kernel import (
    PacingAnchor,
    PacingKernelError,
    PacingParams,
    PacingPeriod,
    anniversary_window,
    project_commitment,
)


def _params(**kw) -> PacingParams:  # noqa: ANN003
    base = dict(
        rc_schedule=(Decimal("0.5"), Decimal("0.5"), Decimal("0.5"), Decimal("1.0")),
        fund_life=4,
        bow=Decimal("2"),
        growth=Decimal("0"),
        yield_floor=Decimal("0"),
    )
    base.update(kw)
    return PacingParams(**base)


def test_hand_derived_golden_new_commitment() -> None:
    # A new commitment (age 0), 1,000,000 committed, NAV 0; L=4, B=2, G=0, Y=0, rc=.5/.5/.5/1.
    # All (t/4)^2 are finite decimals so the golden is hand-checkable to the last digit.
    rows = project_commitment(
        _params(),
        PacingAnchor(current_age=0, unfunded=Decimal("1000000"), nav=Decimal("0")),
    )
    expected = (
        # t, call, dist, nav, unfunded_end
        (1, "500000.000000", "0.000000", "500000.000000", "500000.000000"),
        (2, "250000.000000", "125000.000000", "625000.000000", "250000.000000"),
        (3, "125000.000000", "351562.500000", "398437.500000", "125000.000000"),
        (4, "125000.000000", "398437.500000", "125000.000000", "0.000000"),
    )
    assert len(rows) == 4
    for row, (t, c, d, n, u) in zip(rows, expected, strict=True):
        assert row.period_index == t
        assert row.projected_call == Decimal(c)
        assert row.projected_distribution == Decimal(d)
        assert row.projected_nav == Decimal(n)
        assert row.unfunded_end == Decimal(u)


def test_persisted_rows_satisfy_the_recursion_identity_at_6dp() -> None:
    # QUANTIZE-THEN-ROLL: NAV(t) = quantize(NAV(t-1)(1+G)) + call - dist re-checks EXACTLY from the
    # persisted 6dp echoes (row-level auditability).
    params = _params(growth=Decimal("0.1"), bow=Decimal("1.5"), yield_floor=Decimal("0.05"))
    anchor = PacingAnchor(current_age=0, unfunded=Decimal("16200000"), nav=Decimal("11200000"))
    rows = project_commitment(params, anchor)
    prev_nav = anchor.nav
    prev_unfunded = anchor.unfunded
    gross = Decimal("1") + params.growth
    for row in rows:
        grown = (prev_nav * gross).quantize(Decimal("0.000001"))
        # The persisted identity holds within the quantize band of the single grow step.
        recomputed = (prev_nav * gross) + row.projected_call - row.projected_distribution
        assert row.projected_nav == recomputed.quantize(Decimal("0.000001"))
        assert row.unfunded_end == (prev_unfunded - row.projected_call).quantize(
            Decimal("0.000001")
        )
        assert grown >= 0
        prev_nav = row.projected_nav
        prev_unfunded = row.unfunded_end


def test_grouping_discriminating_golden() -> None:
    # M-3 (the BT-3 coincidence-hazard class): the ADOPTED max(Y,(t/L)^B) vs the wrong max(Y,t/L)^B.
    # Y=0.5, t/L=3/5=0.6, B=2.5 -> (0.6)^2.5 = 0.2788... so the ADOPTED RD is the floor 0.5;
    # the wrong grouping would give 0.6^2.5 = 0.2788. Isolate RD via nav*RD with G=0, no calls.
    params = PacingParams(
        rc_schedule=(Decimal("0"),) * 5,
        fund_life=5,
        bow=Decimal("2.5"),
        growth=Decimal("0"),
        yield_floor=Decimal("0.5"),
    )
    rows = project_commitment(
        params, PacingAnchor(current_age=2, unfunded=Decimal("0"), nav=Decimal("1000000"))
    )
    # Future-only: first row is age 3 (F1).
    assert rows[0].period_index == 3
    # RD(3) = max(0.5, 0.2788...) = 0.5 -> dist = 0.5 * 1,000,000 = 500,000 exactly. The wrong
    # grouping (0.2788 * 1,000,000 = 278,854.38) is provably excluded.
    assert rows[0].projected_distribution == Decimal("500000.000000")
    assert rows[0].projected_distribution != Decimal("278854.380000")


def test_bow_one_is_linear_rd() -> None:
    # B=1 -> RD(t) = t/L. At L=4, t=2 -> RD=0.5; isolate via nav*RD, no calls, G=0.
    params = PacingParams(
        rc_schedule=(Decimal("0"),) * 4,
        fund_life=4,
        bow=Decimal("1"),
        growth=Decimal("0"),
        yield_floor=Decimal("0"),
    )
    rows = project_commitment(
        params, PacingAnchor(current_age=1, unfunded=Decimal("0"), nav=Decimal("1000000"))
    )
    assert rows[0].period_index == 2
    assert rows[0].projected_distribution == Decimal("500000.000000")  # 2/4 * 1,000,000


def test_terminal_rd_is_one() -> None:
    # RD(L) = max(Y, (L/L)^B) = 1 for any B>0 -> the final period distributes the grown NAV fully.
    params = PacingParams(
        rc_schedule=(Decimal("0"),) * 3,
        fund_life=3,
        bow=Decimal("3.7"),
        growth=Decimal("0"),
        yield_floor=Decimal("0"),
    )
    rows = project_commitment(
        params, PacingAnchor(current_age=2, unfunded=Decimal("0"), nav=Decimal("777000"))
    )
    assert rows[-1].period_index == 3
    assert rows[-1].projected_distribution == Decimal("777000.000000")  # rd=1 * grown(G=0) nav
    assert rows[-1].projected_nav == Decimal("0.000000")


def test_future_only_start_and_past_life() -> None:
    # age 0 -> t=1..L; mid-life -> current_age+1..L; age >= L -> empty (the binder refuses it).
    p = _params()
    assert tuple(
        r.period_index
        for r in project_commitment(
            p, PacingAnchor(current_age=0, unfunded=Decimal("1000000"), nav=Decimal("0"))
        )
    ) == (1, 2, 3, 4)
    assert tuple(
        r.period_index
        for r in project_commitment(
            p, PacingAnchor(current_age=2, unfunded=Decimal("500000"), nav=Decimal("100000"))
        )
    ) == (3, 4)
    assert (
        project_commitment(p, PacingAnchor(current_age=4, unfunded=Decimal("0"), nav=Decimal("0")))
        == ()
    )


def test_anniversary_window_leap_day() -> None:
    # A Feb-29 vintage: the age-1 window ends on Feb-28 of the next (non-leap) year.
    assert anniversary_window(date(2024, 2, 29), 1) == (date(2024, 2, 29), date(2025, 2, 28))
    # Age-4 lands on a leap year again -> Feb 29 restored.
    assert anniversary_window(date(2024, 2, 29), 5) == (date(2028, 2, 29), date(2029, 2, 28))
    # Ordinary vintage: clean anniversaries.
    assert anniversary_window(date(2025, 6, 30), 2) == (date(2026, 6, 30), date(2027, 6, 30))


def test_exact_fraction_cross_check() -> None:
    # An INDEPENDENT reference (Fraction, modelling quantize-then-roll with a 6dp HALF_UP) at
    # fraction-friendly params confirms the Decimal kernel row-for-row.
    params = _params(growth=Decimal("0.25"), bow=Decimal("2"), yield_floor=Decimal("0"))
    anchor = PacingAnchor(current_age=0, unfunded=Decimal("2000000"), nav=Decimal("500000"))

    def q6(fr: Fraction) -> Fraction:
        scaled = fr * 1_000_000
        # HALF_UP on a Fraction.
        floor = scaled.numerator // scaled.denominator
        rem = scaled - floor
        rounded = floor + (1 if rem >= Fraction(1, 2) else 0)
        return Fraction(rounded, 1_000_000)

    L, B = params.fund_life, 2
    G = Fraction(1, 4)
    unf = Fraction(2_000_000)
    nav = Fraction(500_000)
    ref = []
    for t in range(1, L + 1):
        rc = Fraction(int(params.rc_schedule[min(t, len(params.rc_schedule)) - 1] * 10), 10)
        call = q6(rc * unf)
        frac_pow = Fraction(t, L) ** B  # B=2 integral -> exact
        rd = frac_pow  # Y=0
        dist = q6(rd * nav * (1 + G))
        nav = q6(nav * (1 + G) + call - dist)
        unf = q6(unf - call)
        ref.append((t, call, dist, nav, unf))

    rows = project_commitment(params, anchor)
    for row, (t, c, d, n, u) in zip(rows, ref, strict=True):
        assert row.period_index == t
        assert Fraction(row.projected_call) == c
        assert Fraction(row.projected_distribution) == d
        assert Fraction(row.projected_nav) == n
        assert Fraction(row.unfunded_end) == u


@pytest.mark.parametrize(
    "kw, reason",
    [
        (dict(fund_life=0), "FUND_LIFE_DOMAIN"),
        (dict(rc_schedule=()), "RC_SCHEDULE_EMPTY"),
        (dict(rc_schedule=(Decimal("0.5"),) * 5, fund_life=4), "RC_SCHEDULE_LENGTH"),
        (dict(rc_schedule=(Decimal("1.5"),)), "RC_RATE_DOMAIN"),
        (dict(bow=Decimal("0")), "BOW_DOMAIN"),
        (dict(growth=Decimal("-1")), "GROWTH_DOMAIN"),
        (dict(yield_floor=Decimal("1.5")), "YIELD_DOMAIN"),
    ],
)
def test_domain_refusals(kw: dict, reason: str) -> None:
    with pytest.raises(PacingKernelError) as exc:
        project_commitment(
            _params(**kw),
            PacingAnchor(current_age=0, unfunded=Decimal("1000000"), nav=Decimal("0")),
        )
    assert exc.value.reason == reason


def test_anchor_domain_refusals() -> None:
    for anchor, reason in (
        (PacingAnchor(current_age=-1, unfunded=Decimal("1"), nav=Decimal("0")), "AGE_DOMAIN"),
        (PacingAnchor(current_age=0, unfunded=Decimal("-1"), nav=Decimal("0")), "ANCHOR_DOMAIN"),
        (PacingAnchor(current_age=0, unfunded=Decimal("1"), nav=Decimal("-1")), "ANCHOR_DOMAIN"),
    ):
        with pytest.raises(PacingKernelError) as exc:
            project_commitment(_params(), anchor)
        assert exc.value.reason == reason


def test_frozen_result_shape() -> None:
    row = project_commitment(
        _params(), PacingAnchor(current_age=0, unfunded=Decimal("1000000"), nav=Decimal("0"))
    )[0]
    assert isinstance(row, PacingPeriod)
    with pytest.raises((AttributeError, Exception)):
        row.projected_call = Decimal("1")  # frozen


def test_runaway_growth_does_not_overflow_the_context() -> None:
    """A well-formed but extreme declared growth compounds NAV geometrically; the kernel must NOT
    raise decimal.InvalidOperation (the runaway-compounding safety cap). It stops early with an
    over-envelope value present, which the BINDER's magnitude gate then turns into a FAILED run."""
    from irp_shared.pacing.pacing_kernel import _MAGNITUDE_CEILING

    # growth=9999 (5000%+/yr), L=30, a funded anchor near the Numeric(28,6) column ceiling.
    rows = project_commitment(
        _params(
            rc_schedule=(Decimal("0.25"),),
            fund_life=30,
            bow=Decimal("2"),
            growth=Decimal("9999"),
            yield_floor=Decimal("0"),
        ),
        PacingAnchor(
            current_age=0, unfunded=Decimal("1000000"), nav=Decimal("9999999999999999.999999")
        ),
    )
    # It stopped early (did NOT run all 30 periods to a context overflow) and the last value is
    # past the ceiling — the binder gate (far below the ceiling) will FAIL such a run.
    assert len(rows) < 30
    assert any(v.copy_abs() > _MAGNITUDE_CEILING for v in (rows[-1].projected_nav,))


def test_complete_annual_periods_feb29_clamp_consistency() -> None:
    """A Feb-29 vintage viewed on the Feb-28 clamped anniversary counts as that age (not one less)
    — the binder's age boundary uses the SAME clamp as the projected windows."""
    from irp_shared.pacing.service import _complete_annual_periods

    v = date(2020, 2, 29)
    assert _complete_annual_periods(v, date(2023, 2, 28)) == 3  # the clamped 3rd anniversary
    assert _complete_annual_periods(v, date(2023, 2, 27)) == 2  # one day before → age 2
    assert _complete_annual_periods(v, date(2024, 2, 29)) == 4  # a real leap anniversary
    # A non-Feb-29 vintage is unaffected.
    assert _complete_annual_periods(date(2020, 6, 30), date(2023, 6, 29)) == 2
    assert _complete_annual_periods(date(2020, 6, 30), date(2023, 6, 30)) == 3
