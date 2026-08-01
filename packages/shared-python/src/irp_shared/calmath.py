"""Pure business-day calendar arithmetic (CAL-1b, OQ-CAL-1-7) — a LEAF module.

**Zero irp_shared imports, no ORM, no session, no I/O** — importable by BOTH ``scheduling`` and
``perf`` without inverting the layering fence (scheduling imports the whole risk+exposure compute
stack, so perf must never import it; the RM-1-era hand-mirror + conformance pin existed only to
work around that, and dissolves here — the OQ-W12C-3b standing rule mandated the pin ON the
mirror, and the wave plan pre-sanctioned re-homing).

The holiday set is always a PASSED-IN ``frozenset[date]`` resolved by the caller — never read
from a database here. That keeps the scheduler's ``current_tick`` purity contract (pure in its
inputs; two concurrent polls with the same inputs compute the identical bucket) and keeps the
perf kernel's no-DB/no-I/O contract intact.

**The v1 grandfather is the EMPTY SET**: with ``holidays == frozenset()`` every function below is
byte-identical to the shipped weekend-only arithmetic (``last_business_day_of_month`` degenerates
to the last weekday; ``is_month_end`` to the shipped two-clause predicate). The v1↔v2 divergence
dates 2024–2035 are exactly the four weekday-rule holiday collisions (2024-03-29, 2027-05-31,
2029-03-30, 2032-05-31 — executed, pinned in ``test_calmath``).
"""

from __future__ import annotations

import calendar as _calendar
from datetime import date as dt_date
from datetime import timedelta

#: The empty holiday set — the explicit spelling of the v1 weekend-only grandfather.
NO_HOLIDAYS: frozenset[dt_date] = frozenset()


def last_weekday_of_month(year: int, month: int) -> dt_date:
    """The last Mon–Fri day of ``(year, month)`` — the shipped v1 weekend-only preceding roll.

    Re-homed verbatim from the RM-1-era pair (``perf.rolling_kernel`` / ``scheduling.service``);
    equal to ``last_business_day_of_month(year, month, NO_HOLIDAYS)`` by construction (pinned)."""
    day = _calendar.monthrange(year, month)[1]
    candidate = dt_date(year, month, day)
    while candidate.weekday() >= 5:  # 5=Sat, 6=Sun
        candidate -= timedelta(days=1)
    return candidate


def last_business_day_of_month(year: int, month: int, holidays: frozenset[dt_date]) -> dt_date:
    """The last day of ``(year, month)`` that is neither a weekend day nor in ``holidays`` —
    the QS-11 ``preceding`` roll, holiday-aware (the v2 convention).

    Fail-loud floor: a (mis-loaded) holiday set that exhausts the whole month raises rather than
    walking into the previous month — a month with zero business days is data corruption, not a
    calendar fact this platform serves."""
    day = _calendar.monthrange(year, month)[1]
    candidate = dt_date(year, month, day)
    while candidate.weekday() >= 5 or candidate in holidays:
        candidate -= timedelta(days=1)
        if candidate.month != month:
            raise ValueError(
                f"{year}-{month:02d} has no business day under the supplied holiday set "
                "(corrupt or mis-scoped holiday data — refused)"
            )
    return candidate


def is_month_end(day: dt_date, holidays: frozenset[dt_date] = NO_HOLIDAYS) -> bool:
    """Month-end acceptance under GIPS 2.A.23.a/b — the calendar month end OR the last business
    day of the month.

    **WIDENING, never substitution** (the ratified OQ-CAL-1-1 constraint): with the default empty
    set this is byte-identical to the shipped v1 predicate (calendar end OR last weekday); a
    non-empty set ADDS the holiday-preceding business day as a third accepted date class and
    removes nothing — a v1-compliant book stays compliant under v2. One month can therefore hold
    up to THREE accepted grid points; ``assert_month_aligned``'s five-condition criterion was
    verified safe under widening (substitution breaks conditions (1)/(2)/(5) on shipped
    weekend-roll series — the RM-1 truncation lesson)."""
    if day.day == _calendar.monthrange(day.year, day.month)[1] or day == last_weekday_of_month(
        day.year, day.month
    ):
        return True
    return bool(holidays) and day == last_business_day_of_month(day.year, day.month, holidays)
