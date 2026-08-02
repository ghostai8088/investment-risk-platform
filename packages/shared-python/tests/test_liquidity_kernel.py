"""The DB-free liquidity kernel (LQ-1).

Reference values are hand-computed and stated in each test, per the gate commitment that reference
literals are independently computed rather than recorded from a first run.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from irp_shared.classification.models import LIQUIDITY_TIER_CODES
from irp_shared.liquidity.kernel import Atom, compute_liquidity
from irp_shared.liquidity.models import BUCKET_UNCLASSIFIED


def _d(v: str) -> Decimal:
    return Decimal(v)


def test_shares_are_taken_against_the_long_book_and_sum_to_one() -> None:
    """Hand-computed: long = 600 + 300 + 100 = 1000; the -50 short is EXCLUDED.

    illiquid 300/1000 = 0.3 · highly liquid 600/1000 = 0.6 · untiered 100/1000 = 0.1.
    """
    r = compute_liquidity(
        (
            Atom("a", _d("600"), "HIGHLY_LIQUID"),
            Atom("b", _d("300"), "ILLIQUID"),
            Atom("c", _d("100"), None),
            Atom("d", _d("-50"), "ILLIQUID"),
        )
    )
    assert r.total_long == _d("1000.000000")
    assert r.illiquid_share == _d("0.300000")
    assert r.highly_liquid_share == _d("0.600000")
    assert r.coverage_ratio == _d("0.900000")
    assert sum(b.tier_share for b in r.buckets) == _d("1.000000")


def test_a_short_position_never_reduces_the_illiquid_share() -> None:
    """The LONG predicate is by VALUE SIGN. Netting a short against a long would let a book hide
    illiquidity by adding shorts — so the short must be invisible, not subtracted."""
    longs_only = compute_liquidity((Atom("a", _d("100"), "ILLIQUID"),))
    with_short = compute_liquidity(
        (Atom("a", _d("100"), "ILLIQUID"), Atom("b", _d("-90"), "HIGHLY_LIQUID"))
    )
    assert longs_only.illiquid_share == with_short.illiquid_share == _d("1.000000")


def test_every_declared_tier_is_emitted_even_at_zero() -> None:
    """A vector with holes is not a vector: a reader must be able to tell 'no illiquid holdings'
    from 'the illiquid bucket was never computed'."""
    r = compute_liquidity((Atom("a", _d("100"), "HIGHLY_LIQUID"),))
    codes = [b.bucket_code for b in r.buckets]
    assert codes == [*LIQUIDITY_TIER_CODES, BUCKET_UNCLASSIFIED]
    assert r.illiquid_share == _d("0.000000")


def test_untiered_exposure_stays_in_the_denominator() -> None:
    """The ratified OQ-LQ-1-19 semantics. Dropping the residual would SHRINK the denominator and
    inflate every reported share — the failure CON-1 recorded and this family inherits."""
    r = compute_liquidity(
        (Atom("a", _d("50"), "ILLIQUID"), Atom("b", _d("50"), None)),
    )
    # 50/100, NOT 50/50.
    assert r.illiquid_share == _d("0.500000")
    assert r.coverage_ratio == _d("0.500000")
    assert r.untiered_instrument_count == 1
    assert r.gaps


def test_a_fully_untiered_book_reports_zero_coverage_and_does_not_divide_by_zero() -> None:
    """Coverage 0 is the floor's whole purpose: the binder must be able to SEE an ungoverned book
    rather than receive a confident 0% illiquid."""
    r = compute_liquidity((Atom("a", _d("100"), None), Atom("b", _d("40"), None)))
    assert r.coverage_ratio == _d("0.000000")
    assert r.illiquid_share == _d("0.000000")
    assert r.untiered_instrument_count == 2
    assert r.gaps


def test_an_empty_or_wholly_short_book_is_a_structured_gap_not_a_division() -> None:
    for atoms in ((), (Atom("a", _d("-10"), "ILLIQUID"),)):
        r = compute_liquidity(atoms)
        assert r.total_long == _d("0")
        assert r.gaps, "a 0/0 book must report a gap for the binder to refuse on"
        assert r.buckets == ()


def test_untiered_count_is_by_INSTRUMENT_not_by_atom() -> None:
    """One instrument appearing in several pinned atoms is ONE data-quality problem, not three.
    Counting atoms would overstate the size of the gap in exactly the reports meant to size it."""
    r = compute_liquidity(
        (
            Atom("same", _d("10"), None),
            Atom("same", _d("20"), None),
            Atom("other", _d("30"), None),
        )
    )
    assert r.untiered_instrument_count == 2


@pytest.mark.parametrize(
    ("amount", "expected"),
    [("1", "0.333333"), ("2", "0.666667")],
)
def test_shares_round_half_up_at_six_places(amount: str, expected: str) -> None:
    """1/3 and 2/3 against a 3-unit book — the platform's ROUND_HALF_UP 6dp convention."""
    r = compute_liquidity(
        (Atom("a", _d(amount), "ILLIQUID"), Atom("b", _d(str(3 - int(amount))), "HIGHLY_LIQUID"))
    )
    assert r.illiquid_share == _d(expected)
