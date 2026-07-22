"""Unit tests for the shared appraisal↔factor period-alignment helper (PPF-1 OD-PPF-1-C).

Proves the convention PA-3 and PPF-1 share: SIMPLE-return compounding at prec-50, and the HALF-OPEN
``(period_start, period_end]`` coverage window (start EXCLUSIVE, end INCLUSIVE).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from irp_shared.risk.period_alignment import (
    compound_over_window,
    compound_simple_returns,
    covering_returns,
)


def test_compound_simple_returns_product_minus_one() -> None:
    # (1.01)(1.02)(0.99) - 1
    got = compound_simple_returns([Decimal("0.01"), Decimal("0.02"), Decimal("-0.01")])
    assert got == Decimal("1.01") * Decimal("1.02") * Decimal("0.99") - Decimal("1")


def test_compound_empty_is_zero() -> None:
    # No coverage compounds to 0 (identity − 1); callers gate on emptiness BEFORE compounding.
    assert compound_simple_returns([]) == Decimal("0")


def test_covering_window_is_half_open_start_exclusive_end_inclusive() -> None:
    rows = [
        (date(2026, 3, 31), Decimal("0.1")),  # == period_start  -> EXCLUDED
        (date(2026, 4, 15), Decimal("0.2")),  # inside            -> included
        (date(2026, 6, 30), Decimal("0.3")),  # == period_end    -> INCLUDED
        (date(2026, 7, 1), Decimal("0.4")),  # after             -> excluded
    ]
    vals = covering_returns(rows, period_start=date(2026, 3, 31), period_end=date(2026, 6, 30))
    assert vals == [Decimal("0.2"), Decimal("0.3")]


def test_compound_over_window_composes() -> None:
    rows = [
        (date(2026, 3, 31), Decimal("9")),  # excluded (== start)
        (date(2026, 4, 15), Decimal("0.05")),
        (date(2026, 6, 30), Decimal("0.03")),  # included (== end)
    ]
    got = compound_over_window(rows, period_start=date(2026, 3, 31), period_end=date(2026, 6, 30))
    assert got == Decimal("1.05") * Decimal("1.03") - Decimal("1")
