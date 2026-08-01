"""The calmath leaf module (CAL-1b): v1 byte-identity, the v2 widening, and the ONE-implementation
parity that RETIRED the RM-1-era mirror + conformance pin (OQ-CAL-1-7).

The old pin swept ``perf.last_weekday_of_month == scheduling._last_weekday_of_month`` over
2024–2035 because two hand-copies could drift. Both sites now delegate to calmath, so the sweep
here pins the CONTRACT that replaced it: the empty-set business-day roll IS the weekday roll
(v1 grandfather identity), and the XNYS set diverges on EXACTLY the four recorded collision
months — no more, no fewer.
"""

from __future__ import annotations

from datetime import date

import pytest

from irp_shared.calmath import (
    NO_HOLIDAYS,
    is_month_end,
    last_business_day_of_month,
    last_weekday_of_month,
)
from irp_shared.reference.xnys_holidays import XNYS_HOLIDAYS, XNYS_RULE_72_OPEN_FRIDAYS

_XNYS = frozenset(d for d, _ in XNYS_HOLIDAYS)

#: The four weekday-rule holiday collisions 2024–2035 (the recorded residual CAL-1b makes
#: retirable) and the business-day answer for each — independently derived at the CAL-1 gate.
_COLLISIONS = {
    (2024, 3): (date(2024, 3, 29), date(2024, 3, 28)),  # Good Friday
    (2027, 5): (date(2027, 5, 31), date(2027, 5, 28)),  # Memorial Day (the forcing function)
    (2029, 3): (date(2029, 3, 30), date(2029, 3, 29)),  # Good Friday
    (2032, 5): (date(2032, 5, 31), date(2032, 5, 28)),  # Memorial Day
}


def test_the_empty_set_is_the_v1_grandfather_identity_over_the_whole_window() -> None:
    """The contract that replaced the mirror pin: last_business_day(NO_HOLIDAYS) IS the weekday
    roll, every month 2024–2035."""
    for year in range(2024, 2036):
        for month in range(1, 13):
            assert last_business_day_of_month(year, month, NO_HOLIDAYS) == last_weekday_of_month(
                year, month
            ), (year, month)


def test_the_xnys_set_diverges_on_exactly_the_four_collision_months() -> None:
    diverged: dict[tuple[int, int], tuple[date, date]] = {}
    for year in range(2024, 2036):
        for month in range(1, 13):
            weekday = last_weekday_of_month(year, month)
            business = last_business_day_of_month(year, month, _XNYS)
            if weekday != business:
                diverged[(year, month)] = (weekday, business)
    assert diverged == _COLLISIONS  # exact census: no more, no fewer, and the exact date pairs


def test_is_month_end_widens_and_never_substitutes() -> None:
    # v1 (empty set): the forcing-function date is REFUSED — the trap CAL-1b exists to retire.
    assert is_month_end(date(2027, 5, 28)) is False
    # v2 (XNYS): the same date is ACCEPTED...
    assert is_month_end(date(2027, 5, 28), _XNYS) is True
    # ...and everything v1 accepted STAYS accepted (widening, never substitution): the calendar
    # end AND the last weekday remain month-ends even when that weekday is the holiday itself.
    assert is_month_end(date(2027, 5, 31), _XNYS) is True  # calendar end (also Memorial Day)
    assert is_month_end(date(2026, 5, 29), _XNYS) is True  # last weekday (retro-stable 2026)
    assert is_month_end(date(2026, 5, 31), _XNYS) is True  # weekend calendar end
    # A mid-month date is nothing under either convention.
    assert is_month_end(date(2027, 5, 14), _XNYS) is False
    # The Rule 7.2 negatives are TRADING days, and last weekdays of December — month-ends under
    # BOTH conventions (their absence from the set is what keeps December's answer unmoved).
    for friday in XNYS_RULE_72_OPEN_FRIDAYS:
        assert friday not in _XNYS
        assert is_month_end(friday, _XNYS) is True


def test_an_exhausted_month_is_refused_not_walked_into_the_prior_month() -> None:
    """The fail-loud floor: a holiday set that consumes every weekday of a month is corrupt data,
    not a calendar fact — refuse, never return a date from the wrong month."""
    may_2027_weekdays = frozenset(
        date(2027, 5, day) for day in range(1, 32) if date(2027, 5, day).weekday() < 5
    )
    with pytest.raises(ValueError, match="no business day"):
        last_business_day_of_month(2027, 5, may_2027_weekdays)
